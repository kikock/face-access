# kikock 人脸识别服务平台 (`face-access`)

基于现代轻量化深度学习与高并发边缘服务架构构建的人脸底库管理与即时人脸识别门禁平台。
支持 **Windows / Linux x86_64** 跨平台纯 ONNX 运行，并已完整适配 **Rockchip RK3588 三核 NPU (6 TOPS)** 硬件加速与 Docker 容器化一键部署（端到端识别耗时低至 **20.93 ms**，较 CPU 提速 **7.17×**）。

---

## 核心架构特性

- **ONNX / RKNN 双模自适应引擎**：彻底剥离闭源 x86 C 动态库，自动探测运行环境——在 RK3588 上无缝绑定 NPU Core 0/1/2 并行推理；在通用 x86/ARM 服务器上自动运行 ONNX Runtime CPU，跨引擎特征余弦相似度高达 **`0.999988`**。
- **静默单目活体防伪 (`MiniFASNetV2`)**：无需眨眼配合即可毫秒级拦截照片打印、手机/平板屏幕翻拍攻击（真脸得分 `0.9999` vs 攻击样本 `0.0042~0.0056`），支持后台热切换“静默 / 眨眼 / 双重校验”模式及一键总开关。
- **10,000 级底库毫秒检索**：内置无锁/读写锁内存矩阵 `Gallery`，1 万特征全量点积比对延迟小于 1 毫秒。
- **企业级分离式批量导入与弹窗编辑**：
  - 信息与照片分离入库：支持 CSV 模板导入人员档案 + 多图或 `.zip` 压缩包按工号/姓名智能匹配人脸质检入库；
  - 人员档案与识别通道均支持在线弹窗编辑与热生效。
- **低延迟异步抗花屏视频流**：RTSP 强制 TCP 传输 + 独立异步最新帧拉取线程与推理线程解耦，杜绝缓冲区溢出及 H264 宏块花屏。
- **Vue 3 + Element Plus 现代化大屏**：实时 MJPEG 视频流预览、全双工 WebSocket 识别弹幕、1:1 / 1:N 算法测试台及在线模型热替换升级。

---

## 快速启动与部署

> 📘 **完整详尽的多平台部署手册（含 RK3588 容器化、RK3588 纯源码、Linux、Windows）请查阅**：
> **[docs/07_全平台部署指南_RK3588源码与Docker及多系统部署.md](./docs/07_全平台部署指南_RK3588源码与Docker及多系统部署.md)**

### 方式 A：Docker Compose 一键部署（推荐）
```bash
# 1. 通用 Linux / Windows Docker 环境 (ONNX Runtime CPU)
docker compose up -d --build

# 2. Rockchip RK3588 开发板环境 (直通 /dev/dri 与 NPU 硬加速)
DOCKER_BUILDKIT=0 COMPOSE_DOCKER_CLI_BUILD=0 \
  docker compose -f docker-compose.yml -f docker-compose.rk3588.yml up -d --build
```
访问管理后台：`http://<服务器IP>:3000`（默认初始管理员：`admin` / `admin123456`）

### 方式 B：Windows 一键脚本启动
- **一键启动**：双击 [`start_all.bat`](./start_all.bat) 或执行 `.\start_all.ps1`（自动拉起 FastAPI `:8000` 与 Vite `:3000` 并打开浏览器）。
- **一键停止**：双击 [`stop_all.bat`](./stop_all.bat) 或执行 `.\stop_all.ps1`。

### 方式 C：手动开发与测试
```bash
# 运行后端全量自动化测试套件 (12 passed)
cd backend
$env:PYTHONPATH="."
uv run pytest tests/ -s

# 手动启动后端与前端
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
cd ../frontend && npm install && npm run dev
```

---

## 技术文档

- **[全平台部署指南 (RK3588 源码/Docker + Linux + Windows)](./docs/07_全平台部署指南_RK3588源码与Docker及多系统部署.md)**：包含 RK3588 三核 NPU 容器直通部署、纯原生源码编译及常见故障排查。

---

## 开源致谢 (Acknowledgments)

本项目核心的轻量化三级深度学习级联权重（人脸检测、68点关键点定位及 Inception-ResNet-50 人脸特征提取网络）以及静默单目活体防伪模型初始导出并衍生自以下优秀开源项目，特此诚挚感谢：
- **[Faceplugin - Open Source Face Recognition SDK](https://github.com/Faceplugin-ltd/Open-Source-Face-Recognition-SDK)**：提供了高精度、纯本地化隐私友好的开源预训练人脸模型与基础结构参考，为本平台实现跨平台纯 ONNX 引擎与 RK3588 NPU 迁移奠定了坚实基础。
- **[minivision-ai - Silent-Face-Anti-Spoofing](https://github.com/minivision-ai/Silent-Face-Anti-Spoofing)**：提供了轻量级高精度 `MiniFASNetV2` 静默单目活体检测模型与多尺度防伪理念，使本平台具备了毫秒级抵御照片打印与屏幕翻拍攻击的能力。
