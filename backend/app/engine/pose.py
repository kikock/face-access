"""
人脸头部姿态估计与眼部纵横比 (EAR) 活体眨眼检测模块。
使用 3D 人脸标准模型与 cv2.solvePnP 求解人脸在相机坐标系下的 3 个旋转角（Yaw、Pitch、Roll），
摆脱原闭源 C 动态库。
"""

from __future__ import annotations

from typing import Tuple

import cv2
import numpy as np

# 标准 3D 人脸关键点几何坐标（坐标系与图像对齐：X朝右，Y朝下，Z朝前）
# 取 6 个核心关键点：鼻尖、下巴、左眼外角、右眼外角、左嘴角、右嘴角
MODEL_POINTS_6 = np.array(
    [
        (0.0, 0.0, 0.0),  # 鼻尖 (点 30)
        (0.0, 100.0, -25.0),  # 下巴 (点 8)
        (-60.0, -40.0, -30.0),  # 左眼外角 (点 36)
        (60.0, -40.0, -30.0),  # 右眼外角 (点 45)
        (-40.0, 40.0, -20.0),  # 左嘴角 (点 48)
        (40.0, 40.0, -20.0),  # 右嘴角 (点 54)
    ],
    dtype=np.float64,
)


def estimate_head_pose(
    landmark_68: np.ndarray, image_shape: Tuple[int, int]
) -> Tuple[float, float, float]:
    """
    计算头部偏航角 (Yaw)、俯仰角 (Pitch)、翻滚角 (Roll)。

    :param landmark_68: (68, 2) 人脸关键点数组
    :param image_shape: (H, W) 图像尺寸
    :return: (yaw, pitch, roll) 角度值（单位：度）
    """
    pts = np.asarray(landmark_68, dtype=np.float64).reshape(68, 2)
    image_points = np.array(
        [
            pts[30],  # 鼻尖
            pts[8],  # 下巴
            pts[36],  # 左眼外角
            pts[45],  # 右眼外角
            pts[48],  # 左嘴角
            pts[54],  # 右嘴角
        ],
        dtype=np.float64,
    )

    h, w = image_shape[:2]
    focal_length = float(w)
    center = (w / 2.0, h / 2.0)
    camera_matrix = np.array(
        [[focal_length, 0.0, center[0]], [0.0, focal_length, center[1]], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    dist_coeffs = np.zeros((4, 1), dtype=np.float64)

    success, rotation_vector, _ = cv2.solvePnP(
        MODEL_POINTS_6,
        image_points,
        camera_matrix,
        dist_coeffs,
        flags=cv2.SOLVEPNP_EPNP,
    )

    if not success:
        return 0.0, 0.0, 0.0

    rot_matrix, _ = cv2.Rodrigues(rotation_vector)
    # 通过 RQDecomp3x3 分解获得欧拉角 (Pitch, Yaw, Roll)
    angles, _, _, _, _, _ = cv2.RQDecomp3x3(rot_matrix)
    pitch = float(angles[0])
    yaw = float(angles[1])
    roll = float(angles[2])
    return yaw, pitch, roll


def compute_eye_aspect_ratio(landmark_68: np.ndarray) -> float:
    """
    计算人脸双眼 Eye Aspect Ratio (EAR) 平均值，用于眨眼检测活体判定。
    左眼点集: 36~41; 右眼点集: 42~47.
    """
    pts = np.asarray(landmark_68, dtype=np.float32).reshape(68, 2)

    def _single_ear(eye_pts: np.ndarray) -> float:
        # 竖直两对特征点间距
        v1 = np.linalg.norm(eye_pts[1] - eye_pts[5])
        v2 = np.linalg.norm(eye_pts[2] - eye_pts[4])
        # 水平两眼角间距
        h = np.linalg.norm(eye_pts[0] - eye_pts[3])
        if h < 1e-4:
            return 0.0
        return float((v1 + v2) / (2.0 * h))

    left_ear = _single_ear(pts[36:42])
    right_ear = _single_ear(pts[42:48])
    return (left_ear + right_ear) * 0.5
