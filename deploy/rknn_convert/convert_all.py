"""
RKNN 模型一键量化与转换核心调度脚本。
支持将 detector.onnx、landmark.onnx、feature.onnx 批量或按需转换为 RK3588 平台的 .rknn 格式。
"""

import argparse
import os
import sys
from pathlib import Path

# 添加当前目录与配置路径
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parents[1]
BACKEND_MODELS_DIR = PROJECT_ROOT / "backend" / "models"
OUTPUT_DIR = CURRENT_DIR / "models_rknn"
CALIBRATION_DIR = CURRENT_DIR / "data" / "calibration"

try:
    from configs.model_configs import (
        ALL_CONFIGS,
        DETECTOR_CONFIG,
        FEATURE_CONFIG,
        LANDMARK_CONFIG,
        LIVENESS_CONFIG,
    )
except ImportError:
    from deploy.rknn_convert.configs.model_configs import (
        ALL_CONFIGS,
        DETECTOR_CONFIG,
        FEATURE_CONFIG,
        LANDMARK_CONFIG,
        LIVENESS_CONFIG,
    )


def check_rknn_env():
    """检查当前环境是否正确安装 rknn-toolkit2。"""
    try:
        from rknn.api import RKNN
        return RKNN
    except ImportError:
        print("[!] 错误: 未检测到 rknn-toolkit2 安装！")
        print("    说明: RKNN-Toolkit2 模型量化工具仅原生支持 Linux x86_64 环境（如 Ubuntu 20.04/22.04、WSL2 或官方 Docker）。")
        print("    在 Windows 原生终端下无法直接运行量化转换，请通过 WSL2 或 Linux 宿主机执行此脚本。")
        print("    官方文档与安装包参见: https://github.com/rockchip-linux/rknn-toolkit2")
        return None


def convert_single_model(
    rknn_cls,
    config,
    onnx_path: Path,
    output_path: Path,
    target_platform: str = "rk3588",
    force_fp16: bool = False,
    dataset_path: Path = None,
) -> bool:
    """执行单个 ONNX 模型的 RKNN 转换与构建。"""
    print(f"\n{'='*60}")
    print(f"[*] 开始转换模型: {config.name}")
    print(f"    - 输入 ONNX: {onnx_path}")
    print(f"    - 目标 RKNN: {output_path}")
    print(f"    - 目标硬件: {target_platform}")
    print(f"    - 色彩类型: {config.color_type}")
    print(f"    - 均值矩阵: {config.mean_values}")
    print(f"    - 方差矩阵: {config.std_values}")

    if not onnx_path.exists():
        print(f"[x] 失败: 输入 ONNX 文件不存在: {onnx_path}")
        return False

    rknn = rknn_cls(verbose=True)

    # 1. 配置全局参数
    print("[*] 正在执行 rknn.config()...")
    rknn.config(
        mean_values=config.mean_values,
        std_values=config.std_values,
        target_platform=target_platform,
        optimization_level=config.optimization_level,
        quantized_algorithm=config.quantized_algorithm,
    )

    # 2. 加载 ONNX 模型
    print("[*] 正在加载 ONNX 算子图...")
    ret = rknn.load_onnx(model=str(onnx_path))
    if ret != 0:
        print(f"[x] 加载 ONNX 失败，错误码: {ret}")
        return False

    # 3. 构建模型 (INT8 量化或 FP16)
    do_quant = (not force_fp16) and config.default_quantize
    print(f"[*] 正在构建模型 (do_quantization={do_quant})...")

    calib_file = None
    if do_quant:
        if dataset_path and dataset_path.exists():
            calib_file = str(dataset_path)
            print(f"    - 使用指定校准文件: {calib_file}")
        else:
            default_calib = CALIBRATION_DIR / f"{config.onnx_filename.replace('.onnx', '')}_dataset.txt"
            if default_calib.exists():
                calib_file = str(default_calib)
                print(f"    - 使用默认校准文件: {calib_file}")
            else:
                print(f"[!] 警告: 未找到量化校准列表文件 {default_calib}，自动降级为 FP16 模式构建！")
                do_quant = False

    ret = rknn.build(do_quantization=do_quant, dataset=calib_file)
    if ret != 0:
        print(f"[x] 构建 RKNN 失败，错误码: {ret}")
        return False

    # 4. 导出 RKNN 模型文件
    output_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"[*] 正在导出 RKNN 文件至: {output_path}...")
    ret = rknn.export_rknn(str(output_path))
    if ret != 0:
        print(f"[x] 导出 RKNN 失败，错误码: {ret}")
        return False

    print(f"[+] 成功完成 {config.name} 转换！文件大小: {output_path.stat().st_size / 1024 / 1024:.2f} MB")
    rknn.release()
    return True


def main():
    parser = argparse.ArgumentParser(description="kikock 人脸识别系统 - RK3588 模型转换工具")
    parser.add_argument(
        "--model",
        type=str,
        choices=["all", "detector", "landmark", "feature", "liveness"],
        default="all",
        help="选择需要转换的目标模型 (默认: all)",
    )
    parser.add_argument(
        "--target-platform",
        type=str,
        default="rk3588",
        choices=["rk3588", "rk3566", "rk3568"],
        help="目标 Rockchip 芯片型号 (默认: rk3588)",
    )
    parser.add_argument(
        "--fp16",
        action="store_true",
        help="强制全部使用 FP16 精度（不进行 INT8 静态量化，保持最高精度）",
    )
    parser.add_argument(
        "--input-dir",
        type=str,
        default=str(BACKEND_MODELS_DIR),
        help="输入 ONNX 模型所在目录",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(OUTPUT_DIR),
        help="转换后 RKNN 模型存放目录",
    )
    args = parser.parse_args()

    rknn_cls = check_rknn_env()
    if rknn_cls is None:
        sys.exit(1)

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    target_configs = []
    if args.model == "all":
        target_configs = ALL_CONFIGS
    elif args.model == "detector":
        target_configs = [DETECTOR_CONFIG]
    elif args.model == "landmark":
        target_configs = [LANDMARK_CONFIG]
    elif args.model == "feature":
        target_configs = [FEATURE_CONFIG]
    elif args.model == "liveness":
        target_configs = [LIVENESS_CONFIG]

    success_count = 0
    for cfg in target_configs:
        onnx_file = input_dir / cfg.onnx_filename
        rknn_file = output_dir / cfg.rknn_filename
        calib_file = CALIBRATION_DIR / f"{cfg.onnx_filename.replace('.onnx', '')}_dataset.txt"

        ok = convert_single_model(
            rknn_cls=rknn_cls,
            config=cfg,
            onnx_path=onnx_file,
            output_path=rknn_file,
            target_platform=args.target_platform,
            force_fp16=args.fp16,
            dataset_path=calib_file,
        )
        if ok:
            success_count += 1

    print(f"\n{'='*60}")
    print(f"[+] 转换工作结束: 总计 {len(target_configs)} 个模型，成功 {success_count} 个。")
    if success_count < len(target_configs):
        sys.exit(2)


if __name__ == "__main__":
    main()

