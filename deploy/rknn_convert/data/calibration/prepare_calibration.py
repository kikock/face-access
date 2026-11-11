"""
自动提取与生成三级模型 RKNN 量化校准数据集脚本。
扫描指定图片目录，利用 OpenCV 提取原图、裁剪框与对齐切片，生成对应的 txt 列表。
"""

import os
import sys
from pathlib import Path
import cv2
import numpy as np

# 将项目目录加入 sys.path 以便复用 backend 的对齐与推理基础逻辑（如可用）
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def prepare_sample_datasets(image_dir: Path, output_dir: Path, max_samples: int = 150):
    """
    处理源图片目录并导出符合三级网络规格的校准集：
    1. detector: 320x240 RGB 图像
    2. landmark: 64x64 灰度图像
    3. feature: 128x128 BGR 图像
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    det_dir = output_dir / "detector"
    lm_dir = output_dir / "landmark"
    feat_dir = output_dir / "feature"
    for d in [det_dir, lm_dir, feat_dir]:
        d.mkdir(parents=True, exist_ok=True)

    det_list_file = output_dir / "detector_dataset.txt"
    lm_list_file = output_dir / "landmark_dataset.txt"
    feat_list_file = output_dir / "feature_dataset.txt"

    supported_exts = {".jpg", ".jpeg", ".png", ".bmp"}
    img_paths = [p for p in image_dir.rglob("*") if p.suffix.lower() in supported_exts]

    print(f"[*] 扫描到源图像 {len(img_paths)} 张，目标提取最多 {max_samples} 组校准样本...")

    det_lines = []
    lm_lines = []
    feat_lines = []

    count = 0
    for p in img_paths:
        if count >= max_samples:
            break
        img = cv2.imread(str(p))
        if img is None:
            continue

        # 1. 检测网络输入切片 (320x240 RGB)
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        det_resized = cv2.resize(img_rgb, (320, 240), interpolation=cv2.INTER_LINEAR)
        det_path = det_dir / f"det_{count:04d}.png"
        # 保存时使用 cv2.imwrite 需转回 BGR
        cv2.imwrite(str(det_path), cv2.cvtColor(det_resized, cv2.COLOR_RGB2BGR))
        det_lines.append(str(det_path.resolve()))

        # 2. 关键点网络切片 (64x64 Gray)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape
        # 居中中心裁切模拟人脸框
        sz = min(h, w)
        cy, cx = h // 2, w // 2
        crop_gray = gray[max(0, cy - sz // 2) : min(h, cy + sz // 2), max(0, cx - sz // 2) : min(w, cx + sz // 2)]
        if crop_gray.size > 0:
            lm_resized = cv2.resize(crop_gray, (64, 64), interpolation=cv2.INTER_LINEAR)
            lm_path = lm_dir / f"lm_{count:04d}.png"
            cv2.imwrite(str(lm_path), lm_resized)
            lm_lines.append(str(lm_path.resolve()))

        # 3. 特征网络切片 (128x128 BGR)
        crop_bgr = img[max(0, cy - sz // 2) : min(h, cy + sz // 2), max(0, cx - sz // 2) : min(w, cx + sz // 2)]
        if crop_bgr.size > 0:
            feat_resized = cv2.resize(crop_bgr, (128, 128), interpolation=cv2.INTER_LINEAR)
            feat_path = feat_dir / f"feat_{count:04d}.png"
            cv2.imwrite(str(feat_path), feat_resized)
            feat_lines.append(str(feat_path.resolve()))

        count += 1

    det_list_file.write_text("\n".join(det_lines), encoding="utf-8")
    lm_list_file.write_text("\n".join(lm_lines), encoding="utf-8")
    feat_list_file.write_text("\n".join(feat_lines), encoding="utf-8")

    print(f"[+] 校准集构建完成！共导出 {count} 组数据。")
    print(f"    - 检测校准列表: {det_list_file}")
    print(f"    - 关键点校准列表: {lm_list_file}")
    print(f"    - 特征校准列表: {feat_list_file}")


if __name__ == "__main__":
    # 默认从 backend/data/uploads 采样，若不存在则回退至当前目录
    default_source = BACKEND_DIR / "data" / "uploads"
    if not default_source.exists():
        default_source = BACKEND_DIR
    prepare_sample_datasets(default_source, CURRENT_DIR, max_samples=100)

