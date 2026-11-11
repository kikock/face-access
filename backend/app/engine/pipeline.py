"""
跨平台人脸端到端推理流水线 (FacePipeline)。
使用 ONNX Runtime CPU 执行（预留 RKNN/NPU 接口），修复了原开源 SDK 的四大核心问题：
1. 内存隔离：无全局共享缓冲区，每个请求及线程分配独占图像空间，杜绝特征串号。
2. 跨平台解耦：完全摒弃 x86-64 closed C 动态库，基于 OpenCV 算法实现对齐与 solvePnP 姿态估计。
3. 动态配置与懒加载：支持显式注入模型路径，不再受限于当前工作目录相对路径。
4. 纯 NumPy 高性能 NMS 与后处理。
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np
import onnxruntime as ort

from app.engine.align import align_face_68
from app.engine.liveness import crop_liveness_patch, parse_liveness_logits
from app.engine.pose import compute_eye_aspect_ratio, estimate_head_pose
from app.engine.quality import FaceQualityChecker, QualityResult

logger = logging.getLogger(__name__)


@dataclass
class DetectedFace:
    bbox: Tuple[int, int, int, int]  # (x1, y1, x2, y2)
    score: float
    landmark: np.ndarray  # (68, 2)
    pose: Tuple[float, float, float]  # (yaw, pitch, roll)
    ear: float  # Eye Aspect Ratio
    quality: QualityResult
    feature: Optional[np.ndarray] = None  # (256,) 归一化特征向量
    aligned_face: Optional[np.ndarray] = None  # (128, 128, 3) 切片
    liveness_score: Optional[float] = None  # 静默单目活体真人置信度 (0.0~1.0)
    is_live: Optional[bool] = None  # 是否通过静默活体校验


def _hard_nms(boxes: np.ndarray, scores: np.ndarray, iou_thresh: float = 0.3) -> List[int]:
    """纯 NumPy 实现的高性能硬 NMS。"""
    if len(boxes) == 0:
        return []
    x1 = boxes[:, 0]
    y1 = boxes[:, 1]
    x2 = boxes[:, 2]
    y2 = boxes[:, 3]
    areas = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]

    keep: List[int] = []
    while order.size > 0:
        i = int(order[0])
        keep.append(i)
        if order.size == 1:
            break
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        w = np.maximum(0.0, xx2 - xx1)
        h = np.maximum(0.0, yy2 - yy1)
        inter = w * h
        ovr = inter / (areas[i] + areas[order[1:]] - inter + 1e-6)
        inds = np.where(ovr <= iou_thresh)[0]
        order = order[inds + 1]
    return keep


class FacePipeline:
    def __init__(
        self,
        model_dir: str | Path,
        quality_checker: Optional[FaceQualityChecker] = None,
        det_threshold: float = 0.6,
        nms_iou_threshold: float = 0.3,
        rknn_model_dir: Optional[str | Path] = None,
        backend: str = "auto",
        liveness_threshold: float = 0.80,
    ):
        self.model_dir = Path(model_dir)
        self.rknn_model_dir = Path(rknn_model_dir) if rknn_model_dir else self.model_dir
        self.det_threshold = det_threshold
        self.nms_iou_threshold = nms_iou_threshold
        self.liveness_threshold = liveness_threshold
        self.quality_checker = quality_checker or FaceQualityChecker()
        self.backend_type: str = "onnx"
        self.has_liveness: bool = False

        # 独立锁确保多线程同时访问底层 NPU 驱动句柄安全
        self._det_lock = threading.Lock()
        self._lm_lock = threading.Lock()
        self._feat_lock = threading.Lock()
        self._liveness_lock = threading.Lock()

        self.sess_det = None
        self.sess_lm = None
        self.sess_feat = None
        self.sess_liveness = None
        self.rknn_det = None
        self.rknn_lm = None
        self.rknn_feat = None
        self.rknn_liveness = None

        use_rknn = False
        if backend in ("auto", "rknn"):
            use_rknn = self._try_init_rknn(strict=(backend == "rknn"))

        if not use_rknn:
            self._init_onnx()

    def _try_init_rknn(self, strict: bool = False) -> bool:
        """尝试初始化 RK3588 NPU 运行时 (rknn-toolkit-lite2) 并绑定 3 个独立 NPU 核心。"""
        det_path = self.rknn_model_dir / "detector_rk3588.rknn"
        lm_path = self.rknn_model_dir / "landmark_rk3588.rknn"
        feat_path = self.rknn_model_dir / "feature_rk3588.rknn"

        if not (det_path.exists() and lm_path.exists() and feat_path.exists()):
            if strict:
                raise FileNotFoundError(f"未在 {self.rknn_model_dir} 找到完整的 RKNN 模型文件集")
            return False

        try:
            from rknnlite.api import RKNNLite
        except ImportError:
            if strict:
                raise RuntimeError("未安装 rknn-toolkit-lite2 运行库，无法启用 RKNN 硬件加速")
            return False

        try:
            logger.info(f"检测到 RKNN 运行环境，正在加载 NPU 模型目录: {self.rknn_model_dir}")
            rknn_det = RKNNLite()
            rknn_lm = RKNNLite()
            rknn_feat = RKNNLite()

            if rknn_det.load_rknn(str(det_path)) != 0:
                raise RuntimeError(f"加载检测 RKNN 失败: {det_path}")
            if rknn_lm.load_rknn(str(lm_path)) != 0:
                raise RuntimeError(f"加载关键点 RKNN 失败: {lm_path}")
            if rknn_feat.load_rknn(str(feat_path)) != 0:
                raise RuntimeError(f"加载特征 RKNN 失败: {feat_path}")

            # 分别绑定 RK3588 的 Core 0 / Core 1 / Core 2 实现多核流水线负载均衡
            if rknn_det.init_runtime(core_mask=RKNNLite.NPU_CORE_0) != 0:
                raise RuntimeError("初始化检测模型 NPU Core 0 失败")
            if rknn_lm.init_runtime(core_mask=RKNNLite.NPU_CORE_1) != 0:
                raise RuntimeError("初始化关键点模型 NPU Core 1 失败")
            if rknn_feat.init_runtime(core_mask=RKNNLite.NPU_CORE_2) != 0:
                raise RuntimeError("初始化特征模型 NPU Core 2 失败")

            self.rknn_det = rknn_det
            self.rknn_lm = rknn_lm
            self.rknn_feat = rknn_feat

            # 可选加载静默单目活体模型 (MiniFASNetV2)
            liveness_rknn_path = self.rknn_model_dir / "liveness_rk3588.rknn"
            if liveness_rknn_path.exists():
                rknn_live = RKNNLite()
                if rknn_live.load_rknn(str(liveness_rknn_path)) == 0:
                    core_auto = getattr(RKNNLite, "NPU_CORE_AUTO", RKNNLite.NPU_CORE_0)
                    if rknn_live.init_runtime(core_mask=core_auto) == 0:
                        self.rknn_liveness = rknn_live
                        self.has_liveness = True
                        logger.info("静默单目活体模型 (liveness_rk3588.rknn) 加载成功")

            self.backend_type = "rknn"
            logger.info("RK3588 三核 NPU 推理流水线启动成功 (Core 0/1/2 已并行绑定)")
            return True
        except Exception as exc:
            logger.warning(f"初始化 RKNN NPU 引擎失败，准备降级回 ONNX CPU 模式: {exc}")
            if strict:
                raise
            return False

    def _init_onnx(self):
        """初始化标准跨平台 ONNX Runtime CPU 会话。"""
        opt = ort.SessionOptions()
        opt.intra_op_num_threads = max(1, os.cpu_count() or 4)
        opt.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        self.sess_det = ort.InferenceSession(
            str(self.model_dir / "detector.onnx"), opt, providers=["CPUExecutionProvider"]
        )
        self.sess_lm = ort.InferenceSession(
            str(self.model_dir / "landmark.onnx"), opt, providers=["CPUExecutionProvider"]
        )
        self.sess_feat = ort.InferenceSession(
            str(self.model_dir / "feature.onnx"), opt, providers=["CPUExecutionProvider"]
        )

        self.det_in_name = self.sess_det.get_inputs()[0].name
        self.lm_in_name = self.sess_lm.get_inputs()[0].name
        self.feat_in_name = self.sess_feat.get_inputs()[0].name

        liveness_onnx_path = self.model_dir / "liveness.onnx"
        if liveness_onnx_path.exists():
            self.sess_liveness = ort.InferenceSession(
                str(liveness_onnx_path), opt, providers=["CPUExecutionProvider"]
            )
            self.liveness_in_name = self.sess_liveness.get_inputs()[0].name
            self.has_liveness = True
            logger.info("静默单目活体模型 (liveness.onnx) 加载成功")

        self.backend_type = "onnx"
        logger.info(f"ONNX Runtime CPU 推理引擎初始化完毕: {self.model_dir}")

    def detect(self, image: np.ndarray, max_faces: int = 10) -> List[Tuple[Tuple[int, int, int, int], float]]:
        """
        人脸框目标检测。
        输入图像 BGR (H, W, 3)。
        输出人脸列表：[((x1, y1, x2, y2), score), ...]
        """
        h, w = image.shape[:2]
        # 预处理：RGB 转换、缩放到 320x240
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, (320, 240), interpolation=cv2.INTER_LINEAR)

        if self.backend_type == "rknn":
            # RKNN 模型内置均值方差硬件级归一化，直接传入 NHWC uint8
            inp_rknn = np.expand_dims(resized, axis=0)
            with self._det_lock:
                scores_raw, boxes_raw = self.rknn_det.inference(inputs=[inp_rknn], data_format="nhwc")
        else:
            inp = ((resized.astype(np.float32) - 127.0) / 128.0).transpose(2, 0, 1)[None, ...]
            scores_raw, boxes_raw = self.sess_det.run(None, {self.det_in_name: inp})

        scores_arr = scores_raw[0, :, 1]  # 人脸正类置信度
        boxes_arr = boxes_raw[0]  # 归一化角点 (x1, y1, x2, y2)

        # 阈值过滤
        mask = scores_arr > self.det_threshold
        if not np.any(mask):
            return []

        filtered_scores = scores_arr[mask]
        filtered_boxes = boxes_arr[mask].copy()

        # 反算回原始图像绝对坐标
        filtered_boxes[:, 0] *= w
        filtered_boxes[:, 1] *= h
        filtered_boxes[:, 2] *= w
        filtered_boxes[:, 3] *= h

        # 边界修剪限制在图像内
        filtered_boxes[:, 0] = np.clip(filtered_boxes[:, 0], 0, w - 1)
        filtered_boxes[:, 1] = np.clip(filtered_boxes[:, 1], 0, h - 1)
        filtered_boxes[:, 2] = np.clip(filtered_boxes[:, 2], 0, w - 1)
        filtered_boxes[:, 3] = np.clip(filtered_boxes[:, 3], 0, h - 1)

        keep_idx = _hard_nms(filtered_boxes, filtered_scores, self.nms_iou_threshold)
        keep_idx = keep_idx[:max_faces]

        results = []
        for idx in keep_idx:
            box = tuple(map(int, np.round(filtered_boxes[idx])))
            score = float(filtered_scores[idx])
            results.append((box, score))
        return results

    def extract_landmark(self, gray_image: np.ndarray, bbox: Tuple[int, int, int, int]) -> np.ndarray:
        """
        基于 MobileFaceNet 提取人脸 68 点特征关键点。
        """
        img_h, img_w = gray_image.shape[:2]
        x1, y1, x2, y2 = bbox
        rw = x2 - x1
        rh = y2 - y1
        cx = (x1 + x2) * 0.5
        cy = (y1 + y2) * 0.5
        sz = np.sqrt(max(1.0, rw * rh))
        rx = cx - sz * 0.5
        ry = cy - sz * 0.5

        # 扩展外扩边界
        ex_x = int(rx - 0.05 * sz)
        ex_y = int(ry - 0.00 * sz)
        ex_w = int(1.10 * sz)
        ex_h = int(1.10 * sz)

        cl_x = int(np.clip(ex_x, 0, img_w - 1))
        cl_y = int(np.clip(ex_y, 0, img_h - 1))
        cl_w = int(np.clip(ex_x + ex_w, 0, img_w - 1) - cl_x)
        cl_h = int(np.clip(ex_y + ex_h, 0, img_h - 1) - cl_y)

        crop = gray_image[cl_y : cl_y + cl_h, cl_x : cl_x + cl_w]
        if crop.size == 0:
            return np.zeros((68, 2), dtype=np.float32)

        crop_res = cv2.resize(crop, (64, 64), interpolation=cv2.INTER_LINEAR)

        if self.backend_type == "rknn":
            inp_rknn = crop_res[None, :, :, None]
            with self._lm_lock:
                out = self.rknn_lm.inference(inputs=[inp_rknn], data_format="nhwc")[0]
        else:
            inp = (crop_res.astype(np.float32) / 256.0)[None, None, :, :]
            out = self.sess_lm.run(None, {self.lm_in_name: inp})[0]

        lm = out.reshape(68, 2).copy()
        lm[:, 0] = lm[:, 0] * cl_w + cl_x
        lm[:, 1] = lm[:, 1] * cl_h + cl_y
        return lm

    def extract_feature(self, aligned_image: np.ndarray) -> np.ndarray:
        """从 128x128 对齐切片提取 256 维 L2 归一化特征向量。"""
        if self.backend_type == "rknn":
            inp_rknn = np.expand_dims(aligned_image, axis=0)
            with self._feat_lock:
                out = self.rknn_feat.inference(inputs=[inp_rknn], data_format="nhwc")[0][0].astype(np.float32)
        else:
            inp = (aligned_image.astype(np.float32) / 256.0).transpose(2, 0, 1)[None, ...]
            out = self.sess_feat.run(None, {self.feat_in_name: inp})[0][0]

        norm = np.linalg.norm(out)
        if norm > 1e-6:
            out = out / norm
        return out

    def check_liveness(
        self, image: np.ndarray, bbox: Tuple[int, int, int, int]
    ) -> Tuple[Optional[float], Optional[bool]]:
        """
        基于 MiniFASNetV2 静默单目活体模型判定真脸 vs 纸张/屏幕翻拍攻击。
        返回: (liveness_score: 0.0~1.0, is_live: bool)，未加载模型时返回 (None, None)。
        """
        if not self.has_liveness:
            return None, None

        patch = crop_liveness_patch(image, bbox, scale=2.7, out_w=80, out_h=80)
        if self.backend_type == "rknn" and self.rknn_liveness is not None:
            inp_rknn = np.expand_dims(patch, axis=0)
            with self._liveness_lock:
                logits = self.rknn_liveness.inference(inputs=[inp_rknn], data_format="nhwc")[0]
        elif self.sess_liveness is not None:
            # 原版 MiniFASNetV2 输入值域为 0~255 BGR float32，严禁除以 255
            inp_onnx = patch.astype(np.float32).transpose(2, 0, 1)[None, ...]
            logits = self.sess_liveness.run(None, {self.liveness_in_name: inp_onnx})[0]
        else:
            return None, None

        return parse_liveness_logits(logits, threshold=self.liveness_threshold)

    def process_image(
        self,
        image: np.ndarray,
        extract_embedding: bool = True,
        max_faces: int = 5,
        check_liveness: bool = True,
    ) -> List[DetectedFace]:
        """
        完整执行检测、关键点、姿态、活体 EAR、静默单目活体、质量评估及特征提取全流程。
        线程安全，每次均分配独占局部变量。
        """
        raw_faces = self.detect(image, max_faces=max_faces)
        if not raw_faces:
            return []

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        results: List[DetectedFace] = []

        for bbox, score in raw_faces:
            landmark = self.extract_landmark(gray, bbox)
            pose = estimate_head_pose(landmark, image.shape[:2])
            ear = compute_eye_aspect_ratio(landmark)
            quality = self.quality_checker.check(image, bbox, pose)

            liveness_score: Optional[float] = None
            is_live: Optional[bool] = None
            if check_liveness and self.has_liveness:
                liveness_score, is_live = self.check_liveness(image, bbox)

            feature: Optional[np.ndarray] = None
            aligned: Optional[np.ndarray] = None

            if extract_embedding:
                aligned = align_face_68(image, landmark)
                feature = self.extract_feature(aligned)

            results.append(
                DetectedFace(
                    bbox=bbox,
                    score=score,
                    landmark=landmark,
                    pose=pose,
                    ear=ear,
                    quality=quality,
                    feature=feature,
                    aligned_face=aligned,
                    liveness_score=liveness_score,
                    is_live=is_live,
                )
            )

        return results

