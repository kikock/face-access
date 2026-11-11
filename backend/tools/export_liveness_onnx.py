"""
静默单目活体检测模型 (MiniFASNetV2) ONNX 导出与校验工具。
基于开源项目 minivision-ai/Silent-Face-Anti-Spoofing 的 2.7_80x80_MiniFASNetV2 权重。
输入规范: [1, 3, 80, 80] BGR float32 (值域 0.0~255.0，直接传入无需除以 255)
输出规范: [1, 3] raw logits (索引 1 为真实活体人脸 RealFace，0 与 2 为 Spoof 伪造攻击)
"""

import argparse
import hashlib
import json
import sys
from collections import OrderedDict
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort
import torch


def get_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def export_liveness(repo_dir: Path, output_dir: Path):
    sys.path.insert(0, str(repo_dir))
    from src.model_lib.MiniFASNet import MiniFASNetV2

    weight_path = repo_dir / "resources" / "anti_spoof_models" / "2.7_80x80_MiniFASNetV2.pth"
    if not weight_path.exists():
        raise FileNotFoundError(f"未找到活体权重文件: {weight_path}")

    # 80x80 输入对应的 conv6_kernel = ((80+15)//16, (80+15)//16) = (5, 5)
    model = MiniFASNetV2(conv6_kernel=(5, 5))
    state_dict = torch.load(str(weight_path), map_location="cpu")

    # 剥离多卡训练可能带有的 "module." 前缀
    first_key = next(iter(state_dict))
    if first_key.startswith("module."):
        cleaned = OrderedDict((k[7:], v) for k, v in state_dict.items())
        model.load_state_dict(cleaned)
    else:
        model.load_state_dict(state_dict)

    model.eval()

    output_dir.mkdir(parents=True, exist_ok=True)
    onnx_path = output_dir / "liveness.onnx"

    dummy_input = torch.randn(1, 3, 80, 80, dtype=torch.float32)

    print(f"[*] 正在导出静默活体模型至: {onnx_path} ...")
    torch.onnx.export(
        model,
        dummy_input,
        str(onnx_path),
        input_names=["input"],
        output_names=["logits"],
        opset_version=13,
        do_constant_folding=True,
    )

    # 数值精度对齐校验
    np.random.seed(42)
    test_arr = np.random.randint(0, 256, (1, 3, 80, 80)).astype(np.float32)
    with torch.no_grad():
        torch_out = model(torch.from_numpy(test_arr)).numpy()

    sess = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    onnx_out = sess.run(None, {"input": test_arr})[0]
    max_diff = float(np.max(np.abs(torch_out - onnx_out)))
    print(f"[+] PyTorch vs ONNX 最大绝对误差: {max_diff:.8e}")
    assert max_diff < 1e-4, f"导出误差过大: {max_diff}"

    # 更新 manifest.json
    manifest_path = output_dir / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {"model_version": "fp-irn50-v1", "opset": 13, "models": {}}

    manifest["models"]["liveness.onnx"] = {
        "sha256": get_sha256(onnx_path),
        "input_shape": [1, 3, 80, 80],
        "scale": 2.7,
        "max_abs_diff_vs_torch": max_diff,
        "backbone": "MiniFASNetV2",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[+] manifest.json 已更新！模型大小: {onnx_path.stat().st_size / 1024 / 1024:.2f} MB")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="导出静默单目活体模型 liveness.onnx")
    parser.add_argument("--repo", type=str, default="/home/ck/silent_face", help="Silent-Face-Anti-Spoofing 仓库路径")
    parser.add_argument("--output-dir", type=str, default=str(Path(__file__).resolve().parents[1] / "models"))
    args = parser.parse_args()
    export_liveness(Path(args.repo), Path(args.output_dir))

