"""
静默单目活体检测预处理与后处理算法模块 (Silent-Face-Anti-Spoofing / MiniFASNetV2)。
"""

from __future__ import annotations

from typing import Tuple

import cv2
import numpy as np


def _get_scaled_box(
    src_w: int, src_h: int, bbox: Tuple[int, int, int, int], scale: float = 2.7
) -> Tuple[int, int, int, int]:
    """
    依据原版 Silent-Face-Anti-Spoofing 的 CropImage._get_new_box 算法，
    以人脸框中心为基准按 scale 倍数等比外扩并钳位至图像有效边界内。
    输入 bbox 为 (x1, y1, x2, y2)。
    """
    x1, y1, x2, y2 = bbox
    box_w = max(1.0, float(x2 - x1))
    box_h = max(1.0, float(y2 - y1))

    eff_scale = min((src_h - 1) / box_h, min((src_w - 1) / box_w, scale))
    new_width = box_w * eff_scale
    new_height = box_h * eff_scale

    center_x = x1 + box_w * 0.5
    center_y = y1 + box_h * 0.5

    left_top_x = center_x - new_width * 0.5
    left_top_y = center_y - new_height * 0.5
    right_bottom_x = center_x + new_width * 0.5
    right_bottom_y = center_y + new_height * 0.5

    if left_top_x < 0:
        right_bottom_x -= left_top_x
        left_top_x = 0.0
    if left_top_y < 0:
        right_bottom_y -= left_top_y
        left_top_y = 0.0
    if right_bottom_x > src_w - 1:
        left_top_x -= right_bottom_x - src_w + 1
        right_bottom_x = float(src_w - 1)
    if right_bottom_y > src_h - 1:
        left_top_y -= right_bottom_y - src_h + 1
        right_bottom_y = float(src_h - 1)

    lx = int(max(0, round(left_top_x)))
    ly = int(max(0, round(left_top_y)))
    rx = int(min(src_w - 1, round(right_bottom_x)))
    ry = int(min(src_h - 1, round(right_bottom_y)))
    return lx, ly, rx, ry


def crop_liveness_patch(
    image: np.ndarray,
    bbox: Tuple[int, int, int, int],
    scale: float = 2.7,
    out_w: int = 80,
    out_h: int = 80,
) -> np.ndarray:
    """
    从原始 BGR 图像裁切多尺度上下文人脸区域并缩放到 80x80 BGR。
    注意：MiniFASNetV2 需要看到人脸外围边框/屏幕边缘/纸张纹理以识别翻拍伪造。
    """
    src_h, src_w = image.shape[:2]
    lx, ly, rx, ry = _get_scaled_box(src_w, src_h, bbox, scale=scale)
    crop = image[ly : ry + 1, lx : rx + 1]
    if crop.size == 0:
        return np.zeros((out_h, out_w, 3), dtype=np.uint8)
    return cv2.resize(crop, (out_w, out_h), interpolation=cv2.INTER_LINEAR)


def parse_liveness_logits(logits: np.ndarray, threshold: float = 0.80) -> Tuple[float, bool]:
    """
    解析 3 分类模型输出 logits:
    - 索引 0: 打印照片攻击 (Spoof Print)
    - 索引 1: 真实活体人脸 (Real Face)
    - 索引 2: 屏幕翻拍/其它伪造 (Spoof Replay)
    返回: (real_prob: 0.0~1.0, is_live: bool)
    """
    vec = logits.reshape(-1).astype(np.float64)
    shifted = vec - np.max(vec)
    exp_v = np.exp(shifted)
    probs = exp_v / np.sum(exp_v)

    real_score = float(probs[1])
    pred_label = int(np.argmax(probs))
    is_live = (pred_label == 1) and (real_score >= threshold)
    return real_score, is_live

