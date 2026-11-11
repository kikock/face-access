from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class AdminUser(Base):
    __tablename__ = "admin_users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, index=True, nullable=False)
    password_hash = Column(String(256), nullable=False)
    must_change_password = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Person(Base):
    __tablename__ = "persons"
    id = Column(Integer, primary_key=True, index=True)
    person_no = Column(String(64), unique=True, index=True, nullable=False)  # 工号/学号
    name = Column(String(64), nullable=False)
    department = Column(String(128), default="")
    phone = Column(String(32), default="")
    enabled = Column(Boolean, default=True)
    valid_from = Column(DateTime, nullable=True)
    valid_to = Column(DateTime, nullable=True)
    remark = Column(String(256), default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    faces = relationship("Face", back_populates="person", cascade="all, delete-orphan")
    events = relationship("AccessEvent", back_populates="person")


class Face(Base):
    __tablename__ = "faces"
    id = Column(Integer, primary_key=True, index=True)
    person_id = Column(Integer, ForeignKey("persons.id", ondelete="CASCADE"), nullable=False)
    image_path = Column(String(256), nullable=False)
    feature = Column(LargeBinary, nullable=False)  # 256维 float32 字节数据 (1024 字节)
    model_version = Column(String(32), default="fp-irn50-v1")
    quality_score = Column(Float, default=100.0)
    yaw = Column(Float, default=0.0)
    pitch = Column(Float, default=0.0)
    roll = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)

    person = relationship("Person", back_populates="faces")


class Device(Base):
    __tablename__ = "devices"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(64), nullable=False)
    source_type = Column(String(32), default="file")  # rtsp, usb, file
    source_uri = Column(String(512), default="")
    enabled = Column(Boolean, default=True)
    actuator_type = Column(String(32), default="simulator")  # simulator, webhook, gpio
    actuator_config = Column(Text, default="{}")  # JSON 配置
    threshold = Column(Float, default=75.0)
    liveness_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    events = relationship("AccessEvent", back_populates="device")


class AccessEvent(Base):
    __tablename__ = "access_events"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="SET NULL"), nullable=True)
    person_id = Column(Integer, ForeignKey("persons.id", ondelete="SET NULL"), nullable=True)
    result = Column(String(32), nullable=False)  # granted, denied, stranger, spoof_suspect
    score = Column(Float, default=0.0)
    snapshot_path = Column(String(256), default="")
    reason = Column(String(256), default="")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    person = relationship("Person", back_populates="events")
    device = relationship("Device", back_populates="events")


class Setting(Base):
    __tablename__ = "settings"
    key = Column(String(64), primary_key=True)
    value_json = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


def init_db():
    Base.metadata.create_all(bind=engine)

