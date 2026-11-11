FROM python:3.11-slim-bookworm

LABEL maintainer="kikock <team@kikock.com>"
LABEL description="kikock 人脸识别服务平台后端 API 容器"

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

# 安装基础依赖与 OpenCV/图形运行时底层 C 库
RUN sed -i 's/deb.debian.org/mirrors.ustc.edu.cn/g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
        curl \
        ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 安装 Python 业务与深度学习依赖
RUN pip install --upgrade pip && \
    pip install \
        "fastapi>=0.115" \
        "uvicorn[standard]>=0.30" \
        "sqlalchemy>=2.0" \
        "pydantic>=2.7" \
        "pydantic-settings>=2.3" \
        "python-multipart>=0.0.9" \
        "pyjwt>=2.8" \
        "bcrypt>=4.1" \
        "numpy>=1.26,<2.0" \
        "opencv-python-headless>=4.9,<4.11" \
        "onnxruntime>=1.18" \
        "httpx>=0.27" && \
    if [ "$(uname -m)" = "aarch64" ]; then \
        pip install "rknn-toolkit-lite2==2.3.2"; \
    fi

# 复制后端代码与必要文件
COPY backend/app /app/app
COPY backend/models /app/models

# 预创建持久化数据目录
RUN mkdir -p /app/data/uploads /app/data/snapshots

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

