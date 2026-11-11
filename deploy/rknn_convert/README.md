# RK3588 (RKNN) 模型转换与量化工作区

本目录包含将 kikock 人脸识别服务平台的三个核心 ONNX 模型转换为 Rockchip RK3588 NPU 专用 `.rknn` 格式的完整自动化工具链。

---

## 目录结构

```
deploy/rknn_convert/
├── configs/
│   └── model_configs.py        # 模型输入输出尺寸、均值/方差矩阵及量化配置
├── data/
│   └── calibration/            # INT8 量化校准数据集存储与说明
│       ├── dataset_guide.md    # 校准集制作规范说明
│       └── prepare_calibration.py # 自动从图片提取校准切片的脚本
├── models_rknn/                # 转换生成的 .rknn 模型目标输出目录
├── convert_all.py              # 一键量化与转换主脚本 (支持 target_platform=rk3588)
├── verify_accuracy.py          # ONNX 与 RKNN 精度与余弦相似度离线比对工具
├── requirements.txt            # Python 依赖清单
└── README.md                   # 本说明文件
```

---

## 快速使用步骤

### 1. 运行环境要求
由于 Rockchip 官方的 `rknn-toolkit2` 底层依赖 Linux 专有的交叉编译驱动库，**模型转换必须在 Linux x86_64 环境下执行**：
- Ubuntu 20.04 / 22.04 LTS
- 或 Windows 11 的 **WSL2 (Ubuntu)**
- 或使用官方提供的 Docker 镜像

### 2. 安装环境依赖
```bash
# 激活 python 3.10 或 3.11 虚拟环境
pip install -r requirements.txt

# 安装 Rockchip 官方 rknn-toolkit2 包 (版本 1.6.0 或 2.0.0+)
pip install rknn-toolkit2 -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 3. 生成量化校准集 (可选，用于 INT8 高速推理)
```bash
python data/calibration/prepare_calibration.py
```

### 4. 执行一键转换
```bash
# 全部转换 (默认针对 RK3588，特征网络自动采用保真策略)
python convert_all.py --target-platform rk3588

# 若要求 100% 零精度损失，可强制全部采用 FP16 模式：
python convert_all.py --target-platform rk3588 --fp16
```

### 5. 精度验证
```bash
python verify_accuracy.py
```
若余弦相似度 $\ge 0.98$ 则表示量化成功，可安全拷贝至 RK3588 开发板上使用 `rknn-toolkit-lite2` 进行 NPU 加速运行。

