# 第一阶段：前端编译打包
FROM node:22-alpine AS builder

WORKDIR /build

# 切换 npm 国内镜像源提升安装速度
RUN npm config set registry https://registry.npmmirror.com

COPY frontend/package*.json ./
RUN sed -i 's|https://registry.npmjs.org|https://registry.npmmirror.com|g' package-lock.json && \
    npm ci --registry=https://registry.npmmirror.com

COPY frontend/ ./
RUN npm run build

# 第二阶段：Nginx 轻量化托管与反代网关
FROM nginx:1.27-alpine

LABEL maintainer="kikock <team@kikock.com>"
LABEL description="kikock 人脸识别服务平台前端大屏与 API 网关容器"

# 替换 Nginx 默认配置以支持 WebSocket 升级与 MJPEG 视频流透传
COPY deploy/docker/nginx.conf /etc/nginx/conf.d/default.conf

# 复制编译产物至托管目录
COPY --from=builder /build/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]

