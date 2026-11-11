import os
from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "kikock 人脸识别服务平台"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = "kikock-face-access-super-secret-key-change-in-prod"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7天

    # 路径配置
    BASE_DIR: Path = Path(__file__).resolve().parents[2]
    DATA_DIR: Path = BASE_DIR / "data"
    MODELS_DIR: Path = BASE_DIR / "models"
    RKNN_MODELS_DIR: Path = BASE_DIR / "models_rknn"
    UPLOAD_DIR: Path = DATA_DIR / "uploads"
    SNAPSHOT_DIR: Path = DATA_DIR / "snapshots"
    DATABASE_URL: str = f"sqlite:///{DATA_DIR}/face_access.db"

    # 推理后端配置: "auto" (优先 RKNN NPU，不可用时回退 ONNX) | "onnx" | "rknn"
    FACE_BACKEND: str = "auto"

    # 算法与门禁默认配置
    DEFAULT_RECOG_THRESHOLD: float = 75.0  # 相似度门限 (0~100)
    DEFAULT_CONTINUOUS_FRAMES: int = 3      # 连续确认命中帧数
    LIVENESS_EAR_THRESHOLD: float = 0.22   # 闭眼 EAR 门限
    LIVENESS_SILENT_THRESHOLD: float = 0.80  # 静默单目活体真人置信度门限
    LIVENESS_MODE: str = "silent"          # 活体策略: silent (单目静默) | blink (眨眼) | both (双重)
    DOOR_OPEN_DURATION_SECONDS: int = 3    # 开门脉冲保持时长 (秒)
    PERSON_COOLDOWN_SECONDS: int = 5       # 同一人通行冷却时长 (秒)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()

# 确保目录初始化
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
settings.SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

