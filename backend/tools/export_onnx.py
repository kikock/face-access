"""
从原始 Open-Source-Face-Recognition-SDK 导出 ONNX 模型。

用法（在 backend 目录下）：
    uv run --group export python tools/export_onnx.py --sdk D:/code/01_github_code/Open-Source-Face-Recognition-SDK

产物：
    models/detector.onnx   输入 [1,3,240,320] RGB，(x-127)/128；输出 scores[1,N,2]、boxes[1,N,4]（归一化角点坐标）
    models/landmark.onnx   输入 [1,1,64,64] 灰度 /256；输出 [1,136]（相对裁剪框的归一化坐标）
    models/feature.onnx    输入 [1,3,128,128] BGR /256；输出 [1,256]（未归一化）
    models/manifest.json   模型版本、SHA256、导出时的一致性误差
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import types
from pathlib import Path

import numpy as np

BACKEND_DIR = Path(__file__).resolve().parents[1]
MODEL_VERSION = "fp-irn50-v1"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _max_diff_onnx(onnx_path: Path, torch_model, dummy) -> float:
    """对比 ONNX Runtime 与 PyTorch 的输出最大绝对误差。"""
    import onnxruntime as ort
    import torch

    sess = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    with torch.no_grad():
        ref = torch_model(dummy)
    ref = ref if isinstance(ref, (tuple, list)) else (ref,)
    outs = sess.run(None, {sess.get_inputs()[0].name: dummy.numpy()})
    return float(max(np.abs(r.numpy() - o).max() for r, o in zip(ref, outs)))


def main() -> int:
    parser = argparse.ArgumentParser(description="导出原 SDK 模型为 ONNX")
    parser.add_argument("--sdk", required=True, help="原 SDK 根目录")
    parser.add_argument("--out", default=str(BACKEND_DIR / "models"), help="输出目录")
    parser.add_argument("--opset", type=int, default=13)
    args = parser.parse_args()

    sdk = Path(args.sdk).resolve()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    if not (sdk / "run.py").exists():
        print(f"错误：{sdk} 不是有效的原 SDK 目录（缺少 run.py）")
        return 2

    import torch
    import torch.nn.functional as F

    # 原 SDK 使用相对路径加载权重，必须切换工作目录
    os.chdir(sdk)
    sys.path.insert(0, str(sdk))

    # ---- 特征模型：去掉 max_pool2d 的索引输出（导出更干净，也便于后续 RKNN 转换）----
    import face_feature.irn50_pytorch as irn_mod

    def _max_pool2d_no_idx(*a, **kw):
        kw.pop("return_indices", None)
        return F.max_pool2d(*a, **kw), None

    proxy = types.SimpleNamespace(**{k: getattr(F, k) for k in dir(F) if not k.startswith("__")})
    proxy.max_pool2d = _max_pool2d_no_idx
    irn_mod.F = proxy
    feat_model = irn_mod.irn50_pytorch("./face_feature/irn50_pytorch.npy").eval()

    from face_detect.detect_imgs import net as det_net  # is_test=True：已包含 softmax 与框解码
    from face_landmark.GetLandmark import model_landmark

    det_net.eval()
    model_landmark.eval()

    specs = [
        ("detector.onnx", det_net, torch.randn(1, 3, 240, 320), ["input"], ["scores", "boxes"]),
        ("landmark.onnx", model_landmark, torch.rand(1, 1, 64, 64), ["input"], ["landmark"]),
        ("feature.onnx", feat_model, torch.rand(1, 3, 128, 128), ["input"], ["feature"]),
    ]

    manifest: dict = {"model_version": MODEL_VERSION, "opset": args.opset, "models": {}}
    for name, model, dummy, in_names, out_names in specs:
        path = out / name
        with torch.no_grad():
            torch.onnx.export(
                model, dummy, str(path),
                input_names=in_names, output_names=out_names,
                opset_version=args.opset, do_constant_folding=True,
            )
        diff = _max_diff_onnx(path, model, dummy)
        manifest["models"][name] = {
            "sha256": _sha256(path),
            "input_shape": list(dummy.shape),
            "max_abs_diff_vs_torch": diff,
        }
        print(f"[完成] {name}  与 PyTorch 最大误差 = {diff:.3e}")

    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"模型清单已写入 {out / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

