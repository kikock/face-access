import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.access.runner import global_device_manager
from app.api.v1.routes import router as api_v1_router
from app.core.config import settings
from app.core.security import get_password_hash
from app.db.models import AdminUser, Device, SessionLocal, init_db
from app.services.state import get_gallery, get_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("face_access_app")


class WebSocketHub:
    """管理前端 WebSocket 实时推送连接池。"""
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self._loop = None

    def set_loop(self, loop):
        self._loop = loop

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    def broadcast_sync(self, message: dict):
        if not self.active_connections or not self._loop:
            return
        payload = json.dumps(message, ensure_ascii=False)
        for conn in list(self.active_connections):
            asyncio.run_coroutine_threadsafe(conn.send_text(payload), self._loop)


ws_hub = WebSocketHub()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. 初始化数据库表结构
    init_db()
    db = SessionLocal()
    try:
        # 仅当系统内不存在任何管理员账号时，初始化默认超级管理员 (admin / admin123456)
        if db.query(AdminUser).count() == 0:
            admin = AdminUser(
                username="admin",
                password_hash=get_password_hash("admin123456"),
                must_change_password=True,
            )
            db.add(admin)
            db.commit()
            logger.info("已自动创建默认初始管理员账号: admin / admin123456 (首次登录需改密)")

        # 2. 预热模型引擎与加载底库
        get_pipeline()
        get_gallery()

        # 3. 关联 WebSocket 回调并启动所有已启用的门禁设备
        ws_hub.set_loop(asyncio.get_running_loop())
        global_device_manager.set_broadcast_callback(ws_hub.broadcast_sync)

        devices = db.query(Device).filter(Device.enabled == True).all()
        for dev in devices:
            global_device_manager.start_device(dev)
    finally:
        db.close()

    yield

    # 停机清理
    logger.info("系统关闭，正在停止所有视频运行器...")
    global_device_manager.stop_all()


app = FastAPI(
    title=settings.PROJECT_NAME,
    lifespan=lifespan,
)

# 允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载 API 路由
app.include_router(api_v1_router, prefix=settings.API_V1_STR)


@app.websocket("/ws/events")
async def websocket_events_endpoint(websocket: WebSocket):
    await ws_hub.connect(websocket)
    try:
        while True:
            # 保持心跳连接
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_hub.disconnect(websocket)
    except Exception:
        ws_hub.disconnect(websocket)


@app.get("/health")
def health_check():
    pipe = get_pipeline()
    return {
        "status": "ok",
        "app": settings.PROJECT_NAME,
        "engine": pipe.backend_type,
        "liveness": pipe.has_liveness,
    }

