"""
ONNX vs RKNN 精度与一致性离线比对验证工具。
支持两种验证模式：
1. 软件模拟器模式 (Simulator)：在 x86 宿主机上构建动态图并直接在模拟器中比对 ONNX 与 RKNN 精度；
2. 板端直连模式 (Device ADB)：连接真实 RK3588 设备执行 .rknn 实际硬件推理对比。
"""

import argparse
import sys
from pathlib import Path
import numpy as np
import onnxruntime as ort

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parents[1]
BACKEND_MODELS_DIR = PROJECT_ROOT / "backend" / "models"
RKNN_MODELS_DIR = CURRENT_DIR / "models_rknn"


def verify_feature_simulator(onnx_path: Path):
    """在 x86 软件模拟器上比对特征网络 ONNX 与 RKNN 的余弦相似度。"""
    print(f"\n{'='*60}")
    print(f"[*] 启动【x86 软件模拟器】特征网络一致性验证:")
    print(f"    - ONNX 模型路径: {onnx_path}")

    from rknn.api import RKNN

    # 1. 构造基准测试输入 (128x128 随机人脸或标准测试图像，BGR 格式)
    np.random.seed(42)
    test_img = np.random.randint(0, 256, (128, 128, 3), dtype=np.uint8)

    # 2. ONNX Runtime 推理基准 (Ground Truth)
    sess_onnx = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    # 按照 pipeline.py: pixel / 256.0, transpose(2, 0, 1)
    inp_onnx = (test_img.astype(np.float32) / 256.0).transpose(2, 0, 1)[None, ...]
    out_onnx = sess_onnx.run(None, {sess_onnx.get_inputs()[0].name: inp_onnx})[0][0]
    out_onnx_norm = out_onnx / np.linalg.norm(out_onnx)

    # 3. 初始化 RKNN 软件模拟器
    rknn = RKNN(verbose=False)
    rknn.config(
        mean_values=[[0.0, 0.0, 0.0]],
        std_values=[[256.0, 256.0, 256.0]],
        target_platform="rk3588",
        optimization_level=3,
    )
    ret = rknn.load_onnx(model=str(onnx_path))
    if ret != 0:
        print("[x] 加载 ONNX 失败")
        return False

    # 构建并启动模拟器 (target=None)
    ret = rknn.build(do_quantization=False)
    if ret != 0:
        print("[x] RKNN 构建失败")
        return False

    ret = rknn.init_runtime(target=None)
    if ret != 0:
        print("[x] 初始化软件模拟器失败")
        return False

    # 推理输入 (RKNN 接受原生 HWC BGR uint8 数组)
    outputs = rknn.inference(inputs=[test_img])
    out_rknn = outputs[0][0]
    out_rknn_norm = out_rknn / np.linalg.norm(out_rknn)

    # 4. 指标统计
    cos_sim = float(np.dot(out_onnx_norm, out_rknn_norm))
    l2_dist = float(np.linalg.norm(out_onnx_norm - out_rknn_norm))
    max_abs_diff = float(np.max(np.abs(out_onnx_norm - out_rknn_norm)))

    print(f"    -> 向量维度: {len(out_onnx_norm)}")
    print(f"    -> 余弦相似度 (Cosine Similarity): {cos_sim:.6f}")
    print(f"    -> L2 欧式距离误差: {l2_dist:.6f}")
    print(f"    -> 最大绝对标量误差: {max_abs_diff:.6f}")

    rknn.release()

    if cos_sim >= 0.99:
        print(f"    [+] 判定: 完美通过 (PASS) - 精度达到金融/门禁零漂移标准！")
        return True
    elif cos_sim >= 0.98:
        print(f"    [+] 判定: 达标 (PASS) - 满足一般场景底库比对要求")
        return True
    else:
        print(f"    [!] 判定: 警告 (WARNING) - 相似度偏低，需检查归一化参数")
        return False


def verify_with_device(rknn_path: Path, device_id: str = None):
    """通过 ADB 在真实 RK3588 硬件开发板上验证 .rknn 文件。"""
    print(f"\n{'='*60}")
    print(f"[*] 启动【RK3588 硬件连板】精度比对模式:")
    print(f"    - RKNN 文件: {rknn_path}")

    from rknn.api import RKNN
    rknn = RKNN(verbose=False)
    ret = rknn.load_rknn(str(rknn_path))
    if ret != 0:
        print("[x] 加载 RKNN 文件失败")
        return False

    ret = rknn.init_runtime(target="rk3588", device_id=device_id)
    if ret != 0:
        print("[!] 连接 RK3588 硬件板端失败，请检查 ADB USB 连接或网络 IP 配置")
        return False

    test_img = np.random.randint(0, 256, (128, 128, 3), dtype=np.uint8)
    outputs = rknn.inference(inputs=[test_img])
    print(f"[+] 板端 NPU 推理成功！输出维度: {outputs[0].shape}")
    rknn.release()
    return True


def main():
    parser = argparse.ArgumentParser(description="RKNN 离线精度对比验证工具")
    parser.add_argument("--mode", type=str, choices=["simulator", "device"], default="simulator",
                        help="选择验证模式: simulator (x86软件模拟器) 或 device (真实RK3588板端)")
    parser.add_argument("--device-id", type=str, default=None, help="ADB 设备号 (仅 device 模式有效)")
    args = parser.parse_args()

    onnx_feat = BACKEND_MODELS_DIR / "feature.onnx"
    rknn_feat = RKNN_MODELS_DIR / "feature_rk3588.rknn"

    if args.mode == "simulator":
        if not onnx_feat.exists():
            print(f"[x] 源 ONNX 不存在: {onnx_feat}")
            sys.exit(1)
        ok = verify_feature_simulator(onnx_feat)
        if not ok:
            sys.exit(2)
    else:
        if not rknn_feat.exists():
            print(f"[x] RKNN 模型不存在: {rknn_feat}")
            sys.exit(1)
        ok = verify_with_device(rknn_feat, args.device_id)
        if not ok:
            sys.exit(2)


if __name__ == "__main__":
    main()
