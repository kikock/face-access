# kikock 人脸识别服务平台 — 全平台部署指南 (RK3588 源码/Docker 及多系统)

| 属性 | 详情 |
| :--- | :--- |
| **适用版本** | v1.2.0 (支持 RK3588 三核 NPU + 静默单目活体防伪 + 批量导入) |
| **覆盖硬件** | Rockchip RK3588 / RK3588S (`aarch64`)、x86_64 Linux、Windows 10/11 |
| **文档编号** | KIKOCK-DOC-DEPLOY-008 |

---

## 0. 部署架构与方案选型矩阵

| 目标平台 | 部署方式 | 推理后端 | 单张人脸端到端耗时 | 适用场景 |
| :--- | :--- | :--- | :--- | :--- |
| **RK3588 (ARM64)** | **Docker 容器化 (首选)** | RKNN 三核 NPU (`rknn-toolkit-lite2`) | **~20.9 ms** | 边缘盒/工控机生产交付、多机批量装机、隔离运维 |
| **RK3588 (ARM64)** | **纯源码部署** | RKNN 三核 NPU (`rknn-toolkit-lite2`) | **~20.9 ms** | 需直接深度调试板端硬件 GPIO/串口或极度受限无 Docker 环境 |
| **Linux x86_64 / ARM64** | **Docker 容器化** | ONNX Runtime (CPU) | ~80-150 ms | 通用云主机、本地 Linux 服务器快速拉起 |
| **Windows 10/11** | **一键脚本 / 源码** | ONNX Runtime (CPU) | ~80-150 ms | 开发调试、桌面端演示、轻量办公网独立部署 |

---

## 1. Rockchip RK3588 (ARM64) 详细部署方案

### 1.1 前置硬件与驱动核验
在 RK3588 开发板（推荐 Ubuntu 22.04 / 24.04 或 Debian 12，内核 5.10 / 6.1）执行以下检查：
```bash
# 1. 确认系统为 aarch64 架构与 NPU 内核驱动就绪
uname -m                                  # 应输出 aarch64
dmesg | grep -i rknpu                     # 确认 RKNPU 驱动正常加载 (如 0.9.8)
ls -l /dev/dri/                           # Linux 6.1 内核 NPU 节点通常位于 /dev/dri/renderD128 或 renderD129

# 2. 确认板端动态库 librknnrt.so 存在且查看版本号
ls -lh /usr/lib/librknnrt.so
python3 -c "import re; print(re.findall(b'librknnrt version: [^\x00]+', open('/usr/lib/librknnrt.so','rb').read()))"
```
*(注意：若固件 `librknnrt.so` 为 `2.3.x`，`rknn-toolkit-lite2` 需配套 `2.3.2`；若为 `1.6.0`，需对应 `1.6.0`。)*

---

### 1.2 RK3588 Docker 容器化部署（生产环境首选）

#### 步骤 1：安装 Docker 与 Compose v2
```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2
sudo usermod -aG docker $USER
# 注销重登或 newgrp docker 使权限生效
```

#### 步骤 2：规避 `overlayroot` 存储陷阱（Firefly/Rockchip 固件关键步骤！）
部分 RK3588 固件根分区 `/` 运行在 `overlayroot` 上，物理大容量空间在 `/userdata`。若不迁移 Docker 存储路径会触发 `mount source: "overlay" ... err: invalid argument` 报错。
```bash
sudo mkdir -p /userdata/docker /etc/docker
cat << 'EOF' | sudo tee /etc/docker/daemon.json
{
  "data-root": "/userdata/docker",
  "storage-driver": "overlay2",
  "features": {
    "containerd-snapshotter": false
  },
  "registry-mirrors": [
    "https://docker.1ms.run",
    "https://docker.xuanyuan.me"
  ]
}
EOF
sudo systemctl restart docker
docker info | grep -E "Storage Driver|Docker Root Dir"
```

#### 步骤 3：拉取项目并一键构建启动（直通 NPU 硬件）
```bash
mkdir -p /userdata/kikock-face-access && cd /userdata/kikock-face-access
git clone https://github.com/kikock/face-access.git .

# 使用传统构建引擎避免 BuildKit 跨分区缓存问题，并叠加 RK3588 NPU 直通配置
DOCKER_BUILDKIT=0 COMPOSE_DOCKER_CLI_BUILD=0 \
  docker compose -f docker-compose.yml -f docker-compose.rk3588.yml up -d --build
```
*(提示：`docker-compose.rk3588.yml` 会自动将宿主机的 `/dev/dri` 与 `/usr/lib/librknnrt.so` 透传进容器，并开启 `FACE_BACKEND=auto` 绑定三核 NPU。)*

#### 步骤 4：跨设备离线批量镜像分发（无网环境）
在已构建好的设备上导出离线镜像包，直接拷贝到同型号板卡免编译秒启：
```bash
# 导出
docker save kikock/face-access-backend:latest kikock/face-access-frontend:latest | gzip > face-access-arm64.tar.gz

# 在新设备导入并运行
docker load -i face-access-arm64.tar.gz
docker compose -f docker-compose.yml -f docker-compose.rk3588.yml up -d
```

---

### 1.3 RK3588 纯原生源码部署（无 Docker 方式）

若需要在宿主机直接以系统进程方式运行：

#### 步骤 1：准备系统与 Python 3.11 隔离环境
```bash
sudo apt-get update
sudo apt-get install -y python3-dev libgl1 libglib2.0-0 nginx curl

# 安装 uv 包管理器并创建 Python 3.11 虚拟环境
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.local/bin/env
cd /userdata/kikock-face-access/backend
uv python install 3.11
uv venv .venv --python 3.11
source .venv/bin/activate
```

#### 步骤 2：安装业务依赖与 NPU 运行库
```bash
uv pip install fastapi "uvicorn[standard]" sqlalchemy pydantic pydantic-settings \
  python-multipart pyjwt bcrypt "numpy>=1.26,<2.0" "opencv-python-headless>=4.9,<4.11" \
  onnxruntime httpx

# 安装匹配板端驱动的 rknn-toolkit-lite2
uv pip install rknn-toolkit-lite2==2.3.2
```

#### 步骤 3：配置模型链接与 Systemd 后端守护服务
```bash
# 链接已转换好的 RKNN 模型至 backend/models_rknn
ln -s /userdata/kikock-face-access/deploy/rknn_convert/models_rknn /userdata/kikock-face-access/backend/models_rknn

# 创建 Systemd 服务 (/etc/systemd/system/face-access-backend.service)
cat << 'EOF' | sudo tee /etc/systemd/system/face-access-backend.service
[Unit]
Description=kikock Face Access Backend (RK3588 NPU)
After=network.target

[Service]
Type=simple
User=firefly
WorkingDirectory=/userdata/kikock-face-access/backend
Environment="FACE_BACKEND=auto"
Environment="RKNN_MODELS_DIR=/userdata/kikock-face-access/backend/models_rknn"
ExecStart=/userdata/kikock-face-access/backend/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now face-access-backend
```

#### 步骤 4：前端静态打包与 Nginx 网关托管
```bash
# 安装 Node.js 22 (可用 nvm 或 NodeSource)，打包前端 dist
cd /userdata/kikock-face-access/frontend
npm ci --registry=https://registry.npmmirror.com
npm run build

# 部署至 Nginx 静态目录并应用反向代理配置
sudo mkdir -p /var/www/face-access
sudo cp -r dist/* /var/www/face-access/
sudo cp /userdata/kikock-face-access/deploy/docker/nginx.conf /etc/nginx/sites-available/face-access
# 将 nginx.conf 中的 root 改为 /var/www/face-access，proxy_pass 指向 http://127.0.0.1:8000
sudo sed -i 's|/usr/share/nginx/html|/var/www/face-access|g; s|http://backend:8000|http://127.0.0.1:8000|g' /etc/nginx/sites-available/face-access
sudo ln -sf /etc/nginx/sites-available/face-access /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl restart nginx
```

---

## 2. 通用 Linux (x86_64 / 云主机) 部署方案

### 2.1 Docker 通用一键部署（推荐）
在任意安装了 Docker 的 Ubuntu / CentOS / Debian 服务器上：
```bash
git clone https://github.com/kikock/face-access.git
cd face-access

# 直接启动（默认启用 ONNX Runtime CPU 多核优化推理）
docker compose up -d --build
```
访问 `http://<服务器IP>:3000` 即可进入管理大屏（默认账密：`admin` / `admin123456`）。

### 2.2 Linux 纯源码部署
1. 安装 `uv`（`curl -LsSf https://astral.sh/uv/install.sh | sh`）和 Node.js 22。
2. 启动后端：
   ```bash
   cd backend
   uv sync
   uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
3. 启动前端（开发模式或 Nginx 托管 `npm run build` 产物）：
   ```bash
   cd frontend
   npm install
   npm run dev -- --host 0.0.0.0 --port 3000
   ```

---

## 3. Windows 10 / 11 部署方案

### 3.1 环境准备
推荐使用 `mise` 或手动安装 Python 3.11 + `uv` + Node.js 22：
```powershell
# 若已安装 mise
mise trust
mise install
```

### 3.2 一键启停脚本（推荐）
项目根目录内置开箱即用的跨终端启停脚本：
* **启动服务**：在资源管理器双击 [`start_all.bat`](../start_all.bat) 或在 PowerShell 执行 `.\start_all.ps1`
  * 自动检测端口占用、后台拉起 FastAPI 后端 (`:8000`) 与 Vite 前端 (`:3000`) 并自动打开浏览器。
* **停止服务**：双击 [`stop_all.bat`](../stop_all.bat) 或执行 `.\stop_all.ps1` 自动释放端口与子进程。

### 3.3 自动化测试套件运行
```powershell
cd backend
$env:PYTHONPATH="."
uv run pytest tests/ -s
```

---

## 4. 部署上线验收清单与故障排查

### 4.1 上线核心健康检查
```bash
# 1. 验证健康探针（RK3588 应返回 engine="rknn", liveness=true）
curl http://<设备IP>:3000/health

# 2. 验证系统引擎与实时指标
curl http://<设备IP>:3000/api/v1/system/status
```

### 4.2 常见问题速查
1. **RTSP 视频流出现花屏（`corrupted macroblock`）或延迟过大**：
   - 本项目已在 `runner.py` 默认配置 `OPENCV_FFMPEG_CAPTURE_OPTIONS="rtsp_transport;tcp"` 并采用独立高速异步抓帧线程解耦。若推送端路由器屏蔽了 TCP 传输，请确保推流服务（如 MediaMTX / 摄像头后台）已开启 RTSP over TCP 支持。
2. **USB 摄像头在 Docker 容器内无法打开 (`/dev/video0`)**：
   - 需在 `docker-compose.yml`（或 `docker-compose.rk3588.yml`）的 `devices` 段添加设备直通映射，例如 `- /dev/video0:/dev/video0`。
3. **如何临时关闭静默单目活体检测**：
   - 登录管理后台 $\rightarrow$ **识别参数与模型** $\rightarrow$ 关闭 **静默单目活体总开关** $\rightarrow$ 点击 **保存并即时热生效**，顶部状态徽章将实时更新为“已关闭”。
