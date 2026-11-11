"""
RKNN 模型转换参数与超参数配置中心。
定义人脸检测、关键点解算、特征提取三级网络的输入输出形状、色彩空间、归一化均值方差以及量化策略。
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ModelConvertConfig:
    """单个模型的转换参数配置。"""
    name: str
    onnx_filename: str
    rknn_filename: str
    input_shape: List[List[int]]
    mean_values: List[List[float]]
    std_values: List[List[float]]
    color_type: str  # 'rgb', 'bgr', 'gray'
    default_quantize: bool  # 是否默认开启 INT8 静态量化
    quantized_algorithm: str = "normal"  # 'normal' 或 'mmse' 或 'kl_divergence'
    optimization_level: int = 3
    notes: str = ""


# 三级流水线模型定义
DETECTOR_CONFIG = ModelConvertConfig(
    name="人脸检测网络 (SSD-Slim)",
    onnx_filename="detector.onnx",
    rknn_filename="detector_rk3588.rknn",
    input_shape=[[1, 3, 240, 320]],
    # 原 ONNX 输入公式：(pixel - 127.0) / 128.0，输入通道为 RGB
    mean_values=[[127.0, 127.0, 127.0]],
    std_values=[[128.0, 128.0, 128.0]],
    color_type="rgb",
    default_quantize=True,
    quantized_algorithm="normal",
    notes="检测定位框容错率较高，推荐 INT8 量化以换取极致帧率"
)

LANDMARK_CONFIG = ModelConvertConfig(
    name="关键点回归网络 (MobileFaceNet)",
    onnx_filename="landmark.onnx",
    rknn_filename="landmark_rk3588.rknn",
    input_shape=[[1, 1, 64, 64]],
    # 原 ONNX 输入公式：pixel / 256.0，输入为单通道灰度图
    mean_values=[[0.0]],
    std_values=[[256.0]],
    color_type="gray",
    default_quantize=True,
    quantized_algorithm="normal",
    notes="68 点回归输出，模型参数量仅 1MB，量化后速度约 1.5ms"
)

FEATURE_CONFIG = ModelConvertConfig(
    name="特征提取网络 (Inception-ResNet-50)",
    onnx_filename="feature.onnx",
    rknn_filename="feature_rk3588.rknn",
    input_shape=[[1, 3, 128, 128]],
    # 原 ONNX 输入公式：pixel / 256.0，输入为 128x128 BGR 对齐切片
    mean_values=[[0.0, 0.0, 0.0]],
    std_values=[[256.0, 256.0, 256.0]],
    color_type="bgr",
    # 特征网络核心：推荐默认 FP16 精度保障 0 误识率；若算力吃紧可选高质量 INT8 量化
    default_quantize=False,
    quantized_algorithm="mmse",
    notes="特征表示向量直接决定余弦距离比对。建议首选 FP16 保证零精度损失，次选 INT8 + MMSE 算法"
)

LIVENESS_CONFIG = ModelConvertConfig(
    name="静默单目活体网络 (MiniFASNetV2)",
    onnx_filename="liveness.onnx",
    rknn_filename="liveness_rk3588.rknn",
    input_shape=[[1, 3, 80, 80]],
    # 原版 Silent-Face-Anti-Spoofing 输入直接为 0~255 BGR，不除 255
    mean_values=[[0.0, 0.0, 0.0]],
    std_values=[[1.0, 1.0, 1.0]],
    color_type="bgr",
    default_quantize=False,
    quantized_algorithm="normal",
    notes="2.7 倍尺度外扩 80x80 BGR 人脸切片，识别真人脸与屏幕/纸张翻拍攻击"
)

ALL_CONFIGS = [DETECTOR_CONFIG, LANDMARK_CONFIG, FEATURE_CONFIG, LIVENESS_CONFIG]

