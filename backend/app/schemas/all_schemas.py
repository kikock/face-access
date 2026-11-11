from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict


class AdminLoginReq(BaseModel):
    username: str
    password: str


class TokenResp(BaseModel):
    access_token: str
    token_type: str = "bearer"
    must_change_password: bool = False


class ChangePasswordReq(BaseModel):
    old_password: str
    new_password: str


class PersonCreate(BaseModel):
    person_no: str
    name: str
    department: Optional[str] = ""
    phone: Optional[str] = ""
    remark: Optional[str] = ""
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None


class PersonUpdate(BaseModel):
    name: Optional[str] = None
    department: Optional[str] = None
    phone: Optional[str] = None
    enabled: Optional[bool] = None
    remark: Optional[str] = None
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None


class FaceItemResp(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    image_path: str
    quality_score: float
    created_at: datetime


class PersonResp(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    person_no: str
    name: str
    department: str
    phone: str
    enabled: bool
    remark: str
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    created_at: datetime
    faces: List[FaceItemResp] = []


class DeviceCreate(BaseModel):
    name: str
    source_type: str = "rtsp"  # rtsp, usb, file
    source_uri: str = ""
    threshold: float = 75.0
    liveness_enabled: bool = True


class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    source_type: Optional[str] = None
    source_uri: Optional[str] = None
    enabled: Optional[bool] = None
    threshold: Optional[float] = None
    liveness_enabled: Optional[bool] = None


class DeviceResp(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    source_type: str
    source_uri: str
    enabled: bool
    threshold: float
    liveness_enabled: bool
    created_at: datetime


class AccessEventResp(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    device_id: Optional[int]
    person_id: Optional[int]
    person_name: Optional[str] = None
    person_no: Optional[str] = None
    result: str
    score: float
    snapshot_path: str
    reason: str
    created_at: str


class SearchResultItem(BaseModel):
    person_id: int
    person_no: str
    name: str
    department: str
    score: float
    cosine: float
    liveness_score: Optional[float] = None
    is_live: Optional[bool] = None

