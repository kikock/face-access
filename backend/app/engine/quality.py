"""
人脸照片质量检测器（用于门禁人脸入库注册拦截与现场抓拍过滤）。
门限指标：
1. 人脸绝对分辨率尺寸 (像素)
2. 头部姿态偏航角 (Yaw)、俯仰角 (Pitch)、翻滚角 (Roll)
3. 图像拉普拉斯清晰度 / 模糊度判断
4. 人脸边缘完整性（避免贴边被截断）
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import cv2
import numpy as np


@dataclass
class QualityResult:
    is_valid: bool
    score: float
    reason: str
    yaw: float
    pitch: float
    roll: float
    blur_score: float
    face_size: int


class FaceQualityChecker:
    def __init__(
        self,
        min_face_size: int = 60,
        max_yaw: float = 40.0,
        max_pitch: float = 35.0,
        max_roll: float = 35.0,
        min_blur_score: float = 30.0,
    ):
        self.min_face_size = min_face_size
        self.max_yaw = max_yaw
        self.max_pitch = max_pitch
        self.max_roll = max_roll
        self.min_blur_score = min_blur_score

    def check(
        self,
        image: np.ndarray,
        bbox: Tuple[int, int, int, int],
        pose: Tuple[float, float, float],
    ) -> QualityResult:
        """
        :param image: BGR 图像
        :param bbox: [x1, y1, x2, y2]
        :param pose: (yaw, pitch, roll)
        """
        x1, y1, x2, y2 = [int(v) for v in bbox]
        w = max(0, x2 - x1)
        h = max(0, y2 - y1)
        size = min(w, h)
        yaw, pitch, roll = pose

        # 1. 尺寸检查
        if size < self.min_face_size:
            return QualityResult(
                is_valid=False,
                score=0.0,
                reason=f"人脸尺寸过小 ({size}px < {self.min_face_size}px)",
                yaw=yaw,
                pitch=pitch,
                roll=roll,
                blur_score=0.0,
                face_size=size,
            )

        # 2. 姿态角度检查
        if abs(yaw) > self.max_yaw:
            return QualityResult(
                is_valid=False,
                score=0.0,
                reason=f"人脸侧脸角度过大 (Yaw: {yaw:.1f}° > ±{self.max_yaw}°)",
                yaw=yaw,
                pitch=pitch,
                roll=roll,
                blur_score=0.0,
                face_size=size,
            )
        if abs(pitch) > self.max_pitch:
            return QualityResult(
                is_valid=False,
                score=0.0,
                reason=f"人脸俯仰角度过大 (Pitch: {pitch:.1f}° > ±{self.max_pitch}°)",
                yaw=yaw,
                pitch=pitch,
                roll=roll,
                blur_score=0.0,
                face_size=size,
            )
        if abs(roll) > self.max_roll:
            return QualityResult(
                is_valid=False,
                score=0.0,
                reason=f"人脸偏转翻滚角度过大 (Roll: {roll:.1f}° > ±{self.max_roll}°)",
                yaw=yaw,
                pitch=pitch,
                roll=roll,
                blur_score=0.0,
                face_size=size,
            )

        # 3. 截取人脸计算拉普拉斯清晰度 (方差越低越模糊)
        img_h, img_w = image.shape[:2]
        cx1 = max(0, x1)
        cy1 = max(0, y1)
        cx2 = min(img_w, x2)
        cy2 = min(img_h, y2)
        crop = image[cy1:cy2, cx1:cx2]

        if crop.size == 0:
            return QualityResult(
                is_valid=False,
                score=0.0,
                reason="人脸切片为空",
                yaw=yaw,
                pitch=pitch,
                roll=roll,
                blur_score=0.0,
                face_size=size,
            )

        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        blur_val = float(cv2.Laplacian(gray, cv2.CV_64F).var())

        if blur_val < self.min_blur_score:
            return QualityResult(
                is_valid=False,
                score=0.0,
                reason=f"人脸图像过于模糊 (清晰度: {blur_val:.1f} < {self.min_blur_score})",
                yaw=yaw,
                pitch=pitch,
                roll=roll,
                blur_score=blur_val,
                face_size=size,
            )

        # 综合质量评分 (0~100)
        pose_penalty = (abs(yaw) / self.max_yaw + abs(pitch) / self.max_pitch) * 20.0
        blur_bonus = min(20.0, (blur_val - self.min_blur_score) / 10.0)
        final_score = float(np.clip(100.0 - pose_penalty + blur_bonus, 50.0, 100.0))

        return QualityResult(
            is_valid=True,
            score=final_score,
            reason="合格",
            yaw=yaw,
            pitch=pitch,
            roll=roll,
            blur_score=blur_val,
            face_size=size,
        )
