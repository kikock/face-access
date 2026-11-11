import json
import logging
from typing import Optional
from app.core.config import settings
from app.db.models import SessionLocal, Face, Setting
from app.engine.gallery import Gallery
from app.engine.pipeline import FacePipeline
from app.engine.quality import FaceQualityChecker

logger = logging.getLogger(__name__)

global_pipeline: Optional[FacePipeline] = None
global_gallery: Optional[Gallery] = None
_cached_settings: Optional[dict] = None

DEFAULT_RECOGNITION_SETTINGS = {
    "det_threshold": 0.6,
    "nms_iou_threshold": 0.3,
    "default_recog_threshold": 75.0,
    "default_continuous_frames": 3,
    "liveness_ear_threshold": 0.22,
    "liveness_silent_enabled": True,
    "liveness_silent_threshold": 0.80,
    "liveness_mode": "silent",
    "min_face_size": 60,
    "max_yaw": 40.0,
    "max_pitch": 35.0,
    "max_roll": 35.0,
    "min_blur_score": 30.0,
    "door_open_duration_seconds": 3,
    "person_cooldown_seconds": 5,
}


def get_current_settings() -> dict:
    db = SessionLocal()
    try:
        record = db.query(Setting).filter(Setting.key == "recognition_params").first()
        if record and record.value_json:
            try:
                saved = json.loads(record.value_json)
                merged = dict(DEFAULT_RECOGNITION_SETTINGS)
                merged.update(saved)
                return merged
            except Exception as e:
                logger.error(f"解析系统配置 JSON 失败: {e}")
        return dict(DEFAULT_RECOGNITION_SETTINGS)
    finally:
        db.close()


def get_cached_settings() -> dict:
    """高频零 IO 获取识别与活体配置（内存缓存，配置更新时即时刷新）"""
    global _cached_settings
    if _cached_settings is None:
        _cached_settings = get_current_settings()
    return _cached_settings


def save_current_settings(new_settings: dict) -> dict:
    global _cached_settings
    merged = dict(DEFAULT_RECOGNITION_SETTINGS)
    merged.update(new_settings)
    db = SessionLocal()
    try:
        record = db.query(Setting).filter(Setting.key == "recognition_params").first()
        if not record:
            record = Setting(key="recognition_params", value_json=json.dumps(merged, ensure_ascii=False))
            db.add(record)
        else:
            record.value_json = json.dumps(merged, ensure_ascii=False)
        db.commit()
    finally:
        db.close()

    _cached_settings = merged

    # 热更新当前运行中的 Pipeline 质量检测阈值与 NMS 阈值
    global global_pipeline
    if global_pipeline is not None:
        global_pipeline.det_threshold = float(merged.get("det_threshold", 0.6))
        global_pipeline.nms_iou_threshold = float(merged.get("nms_iou_threshold", 0.3))
        global_pipeline.liveness_threshold = float(merged.get("liveness_silent_threshold", 0.80))
        global_pipeline.quality_checker = FaceQualityChecker(
            min_face_size=int(merged.get("min_face_size", 60)),
            max_yaw=float(merged.get("max_yaw", 40.0)),
            max_pitch=float(merged.get("max_pitch", 35.0)),
            max_roll=float(merged.get("max_roll", 35.0)),
            min_blur_score=float(merged.get("min_blur_score", 30.0)),
        )
    return merged


def reload_pipeline() -> FacePipeline:
    """热重载人脸推理 Pipeline (例如更新模型文件后)"""
    global global_pipeline
    logger.info(f"重新加载 ONNX FacePipeline 模型引擎: {settings.MODELS_DIR} ...")
    cfg = get_current_settings()
    checker = FaceQualityChecker(
        min_face_size=int(cfg.get("min_face_size", 60)),
        max_yaw=float(cfg.get("max_yaw", 40.0)),
        max_pitch=float(cfg.get("max_pitch", 35.0)),
        max_roll=float(cfg.get("max_roll", 35.0)),
        min_blur_score=float(cfg.get("min_blur_score", 30.0)),
    )
    global_pipeline = FacePipeline(
        model_dir=settings.MODELS_DIR,
        quality_checker=checker,
        det_threshold=float(cfg.get("det_threshold", 0.6)),
        nms_iou_threshold=float(cfg.get("nms_iou_threshold", 0.3)),
        rknn_model_dir=settings.RKNN_MODELS_DIR,
        backend=settings.FACE_BACKEND,
        liveness_threshold=float(cfg.get("liveness_silent_threshold", 0.80)),
    )
    logger.info(f"FacePipeline 模型引擎重载完毕 [backend={global_pipeline.backend_type}]")
    return global_pipeline


def get_pipeline() -> FacePipeline:
    global global_pipeline
    if global_pipeline is None:
        global_pipeline = reload_pipeline()
    return global_pipeline


def reload_gallery() -> Gallery:
    """从数据库重新全量加载向量到内存 Gallery 底库"""
    global global_gallery
    if global_gallery is None:
        global_gallery = Gallery(feature_dim=256)
    db = SessionLocal()
    try:
        faces = db.query(Face).all()
        if faces:
            import numpy as np
            face_ids = [f.id for f in faces]
            person_ids = [f.person_id for f in faces]
            raw_bytes = [f.feature for f in faces]
            feats = np.frombuffer(b"".join(raw_bytes), dtype=np.float32).reshape(-1, 256)
            global_gallery.load_bulk(face_ids, person_ids, feats)
            logger.info(f"底库向量加载完毕，共装载 {len(face_ids)} 条人脸特征")
        else:
            global_gallery.clear()
            logger.info("数据库暂无人脸特征记录，底库初始化为空")
    finally:
        db.close()
    return global_gallery


def get_gallery() -> Gallery:
    global global_gallery
    if global_gallery is None:
        global_gallery = reload_gallery()
    return global_gallery
