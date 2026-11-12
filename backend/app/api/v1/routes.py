import csv
import io
import json
import logging
import os
import re
import shutil
import time
from pathlib import Path
from typing import List, Optional
import zipfile

import cv2
import numpy as np
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.access.runner import global_device_manager
from app.core.config import settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    get_password_hash,
    verify_password,
)
from app.db.models import (
    AccessEvent,
    AdminUser,
    Device,
    Face,
    Person,
    SessionLocal,
)
from app.schemas.all_schemas import (
    AccessEventResp,
    AdminLoginReq,
    ChangePasswordReq,
    DeviceCreate,
    DeviceResp,
    DeviceUpdate,
    PersonCreate,
    PersonResp,
    PersonUpdate,
    SearchResultItem,
    TokenResp,
)
from app.services.state import (
    get_cached_settings,
    get_current_settings,
    get_gallery,
    get_pipeline,
    reload_gallery,
    reload_pipeline,
    save_current_settings,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_admin(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> AdminUser:
    """从 Authorization: Bearer <token> 解析当前已登录管理员账号"""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录或登录已失效")
    token = authorization.split(" ", 1)[1].strip()
    username = decode_access_token(token)
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录凭证无效或已过期")
    user = db.query(AdminUser).filter(AdminUser.username == username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="管理员账号不存在")
    return user


# ==================== 1. 系统认证 ====================
@router.post("/auth/login", response_model=TokenResp)
def login(req: AdminLoginReq, db: Session = Depends(get_db)):
    user = db.query(AdminUser).filter(AdminUser.username == req.username).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=400, detail="用户名或密码错误")
    token = create_access_token(user.username)
    return TokenResp(
        access_token=token,
        username=user.username,
        must_change_password=user.must_change_password,
    )


@router.get("/auth/me")
def get_me(current_user: AdminUser = Depends(get_current_admin)):
    return {
        "username": current_user.username,
        "must_change_password": current_user.must_change_password,
    }


@router.post("/auth/change-password")
def change_password(
    req: ChangePasswordReq,
    current_user: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """修改当前登录管理员的登录账号与/或密码"""
    if not verify_password(req.old_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="原密码错误")

    new_username = (req.new_username or "").strip()
    new_password = req.new_password or ""

    changed = False

    if new_username and new_username != current_user.username:
        if len(new_username) < 3:
            raise HTTPException(status_code=400, detail="新账号长度不能少于 3 个字符")
        conflict = (
            db.query(AdminUser)
            .filter(AdminUser.username == new_username, AdminUser.id != current_user.id)
            .first()
        )
        if conflict:
            raise HTTPException(status_code=400, detail=f"账号 {new_username} 已被占用")
        current_user.username = new_username
        changed = True

    if new_password:
        if len(new_password) < 6:
            raise HTTPException(status_code=400, detail="新密码长度不能少于 6 个字符")
        current_user.password_hash = get_password_hash(new_password)
        current_user.must_change_password = False
        changed = True

    if not changed:
        raise HTTPException(status_code=400, detail="请输入要修改的新账号或新密码")

    db.commit()
    db.refresh(current_user)
    new_token = create_access_token(current_user.username)
    return {
        "message": "账号与密码修改成功，请使用新凭据登录",
        "username": current_user.username,
        "access_token": new_token,
    }


# ==================== 2. 人员与人脸档案管理 ====================
@router.get("/persons", response_model=List[PersonResp])
def list_persons(db: Session = Depends(get_db)):
    return db.query(Person).order_by(Person.id.desc()).all()


@router.post("/persons", response_model=PersonResp)
def create_person(req: PersonCreate, db: Session = Depends(get_db)):
    exists = db.query(Person).filter(Person.person_no == req.person_no).first()
    if exists:
        raise HTTPException(status_code=400, detail=f"工号/学号 {req.person_no} 已存在")
    person = Person(**req.model_dump())
    db.add(person)
    db.commit()
    db.refresh(person)
    return person


@router.put("/persons/{person_id}", response_model=PersonResp)
def update_person(person_id: int, req: PersonUpdate, db: Session = Depends(get_db)):
    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="人员不存在")
    for k, v in req.model_dump(exclude_unset=True).items():
        setattr(person, k, v)
    db.commit()
    db.refresh(person)
    return person


@router.delete("/persons/{person_id}")
def delete_person(person_id: int, db: Session = Depends(get_db)):
    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="人员不存在")
    # 从内存向量库同步剔除
    get_gallery().remove_by_person(person_id)
    db.delete(person)
    db.commit()
    return {"message": "人员已删除"}


@router.get("/persons/batch-template")
def download_person_batch_template():
    """下载人员基本信息批量导入 CSV 模板（UTF-8 BOM 编码，Excel 打开零乱码）"""
    csv_content = (
        "\ufeff"
        "工号(person_no),姓名(name),部门(department),联系电话(phone),备注(remark)\n"
        "P1001,张三,研发部,13800138001,测试样本1\n"
        "P1002,李四,安保部,13800138002,测试样本2\n"
    )
    return Response(
        content=csv_content.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=persons_import_template.csv"},
    )


@router.post("/persons/batch-info")
async def batch_import_persons_info(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    批量导入人员基本信息 (CSV 文件，与人脸照片分离导入)。
    若工号已存在则更新其信息，不存在则新建档案。
    """
    raw = await file.read()
    text = None
    for enc in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise HTTPException(status_code=400, detail="无法解码 CSV 文件，请保存为 UTF-8 或 GBK 编码")

    reader = csv.DictReader(io.StringIO(text.strip()))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV 文件格式无效或缺少表头")

    def _pick(row: dict, aliases: tuple[str, ...]) -> str:
        for k, v in row.items():
            if k is None:
                continue
            kl = k.strip().lower()
            for alias in aliases:
                if alias in kl:
                    return (v or "").strip()
        return ""

    created_count = 0
    updated_count = 0
    skipped_count = 0
    errors: List[str] = []

    for idx, row in enumerate(reader, start=2):
        person_no = _pick(row, ("person_no", "工号", "学号"))
        name = _pick(row, ("name", "姓名"))
        department = _pick(row, ("department", "部门", "班级", "组织"))
        phone = _pick(row, ("phone", "电话", "手机"))
        remark = _pick(row, ("remark", "备注"))

        if not person_no or not name:
            skipped_count += 1
            errors.append(f"第 {idx} 行缺少工号或姓名，已跳过")
            continue

        existing = db.query(Person).filter(Person.person_no == person_no).first()
        if existing:
            existing.name = name
            if department:
                existing.department = department
            if phone:
                existing.phone = phone
            if remark:
                existing.remark = remark
            updated_count += 1
        else:
            db.add(
                Person(
                    person_no=person_no,
                    name=name,
                    department=department,
                    phone=phone,
                    remark=remark,
                )
            )
            created_count += 1

    db.commit()
    return {
        "message": f"人员信息导入完成：新增 {created_count} 人，更新 {updated_count} 人，跳过 {skipped_count} 行",
        "created_count": created_count,
        "updated_count": updated_count,
        "skipped_count": skipped_count,
        "errors": errors[:20],
    }


@router.post("/persons/batch-faces")
async def batch_upload_faces(
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    """
    批量上传人脸照片（支持多图或 .zip 压缩包），根据文件名（工号 / 工号_序号 / 姓名）
    自动匹配对应人员档案并完成质量校验与特征入库。
    """
    supported_exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    image_items: List[tuple[str, bytes]] = []

    for uf in files:
        fname = uf.filename or "unknown"
        ext = Path(fname).suffix.lower()
        data = await uf.read()
        if ext == ".zip":
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as zf:
                    for info in zf.infolist():
                        if info.is_dir():
                            continue
                        raw_name = info.filename
                        # 兼容 Windows ZIP 默认 GBK 中文文件名编码
                        if not (info.flag_bits & 0x800):
                            try:
                                raw_name = raw_name.encode("cp437").decode("gbk")
                            except Exception:
                                pass
                        if "__MACOSX" in raw_name or Path(raw_name).name.startswith("."):
                            continue
                        if Path(raw_name).suffix.lower() in supported_exts:
                            image_items.append((Path(raw_name).name, zf.read(info)))
            except zipfile.BadZipFile:
                raise HTTPException(status_code=400, detail=f"压缩包文件损坏: {fname}")
        elif ext in supported_exts:
            image_items.append((Path(fname).name, data))

    if not image_items:
        raise HTTPException(status_code=400, detail="未检测到有效的图片或 ZIP 照片压缩包")

    all_persons = db.query(Person).all()
    by_no = {p.person_no.strip(): p for p in all_persons}
    # 按工号长度降序排序，防止带下划线工号 (如 EMP_1001) 被短工号误匹配
    sorted_nos = sorted(by_no.keys(), key=len, reverse=True)
    by_name: dict[str, list[Person]] = {}
    for p in all_persons:
        by_name.setdefault(p.name.strip(), []).append(p)
    sorted_names = sorted(by_name.keys(), key=len, reverse=True)

    def _match_key(stem_str: str, key: str) -> bool:
        return stem_str == key or any(stem_str.startswith(key + sep) for sep in ("_", "-", " "))

    pipeline = get_pipeline()
    gallery = get_gallery()

    results = []
    success_count = 0
    failed_count = 0

    for fname, img_bytes in image_items:
        stem = Path(fname).stem.strip()
        prefix = re.split(r"[_\-\s]+", stem)[0].strip()

        # 优先匹配工号（支持含下划线/短横线工号 + 序号后缀），次选唯一姓名匹配
        matched_person = by_no.get(stem)
        if not matched_person:
            for k in sorted_nos:
                if _match_key(stem, k):
                    matched_person = by_no[k]
                    break

        if not matched_person:
            name_hits = by_name.get(stem) or []
            if not name_hits:
                for n in sorted_names:
                    if _match_key(stem, n):
                        name_hits = by_name[n]
                        break
            if len(name_hits) == 1:
                matched_person = name_hits[0]
            elif len(name_hits) > 1:
                failed_count += 1
                results.append(
                    {
                        "filename": fname,
                        "matched_person": "-",
                        "status": "failed",
                        "reason": f"存在多名同名人员 [{stem}]，请改用工号命名",
                        "quality_score": 0.0,
                    }
                )
                continue

        if not matched_person:
            failed_count += 1
            results.append(
                {
                    "filename": fname,
                    "matched_person": "-",
                    "status": "failed",
                    "reason": f"未匹配到工号或姓名 [{prefix}]，请先导入人员信息",
                    "quality_score": 0.0,
                }
            )
            continue

        image = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            failed_count += 1
            results.append(
                {
                    "filename": fname,
                    "matched_person": f"{matched_person.name} ({matched_person.person_no})",
                    "status": "failed",
                    "reason": "图像解码失败或已损坏",
                    "quality_score": 0.0,
                }
            )
            continue

        faces = pipeline.process_image(image, extract_embedding=True, max_faces=2, check_liveness=False)
        if len(faces) == 0:
            failed_count += 1
            results.append(
                {
                    "filename": fname,
                    "matched_person": f"{matched_person.name} ({matched_person.person_no})",
                    "status": "failed",
                    "reason": "未检测到有效人脸",
                    "quality_score": 0.0,
                }
            )
            continue
        if len(faces) > 1:
            failed_count += 1
            results.append(
                {
                    "filename": fname,
                    "matched_person": f"{matched_person.name} ({matched_person.person_no})",
                    "status": "failed",
                    "reason": "照片中检测到多张人脸，请使用单人照",
                    "quality_score": 0.0,
                }
            )
            continue

        face_info = faces[0]
        if not face_info.quality.is_valid:
            failed_count += 1
            results.append(
                {
                    "filename": fname,
                    "matched_person": f"{matched_person.name} ({matched_person.person_no})",
                    "status": "failed",
                    "reason": f"质检未通过: {face_info.quality.reason}",
                    "quality_score": round(face_info.quality.score, 1),
                }
            )
            continue

        save_name = f"person_{matched_person.id}_{int(time.time()*1000)}_{len(results)}.jpg"
        cv2.imwrite(str(settings.UPLOAD_DIR / save_name), image)
        feat_bytes = face_info.feature.astype(np.float32).tobytes()
        face = Face(
            person_id=matched_person.id,
            image_path=save_name,
            feature=feat_bytes,
            quality_score=face_info.quality.score,
            yaw=face_info.pose[0],
            pitch=face_info.pose[1],
            roll=face_info.pose[2],
        )
        db.add(face)
        db.commit()
        db.refresh(face)
        gallery.add(face.id, matched_person.id, face_info.feature)

        success_count += 1
        results.append(
            {
                "filename": fname,
                "matched_person": f"{matched_person.name} ({matched_person.person_no})",
                "status": "success",
                "reason": "质检通过并已入库",
                "quality_score": round(face_info.quality.score, 1),
            }
        )

    return {
        "total": len(image_items),
        "success_count": success_count,
        "failed_count": failed_count,
        "results": results,
    }


@router.post("/persons/{person_id}/faces")
async def register_face(
    person_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)
):
    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="人员不存在")

    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=400, detail="无效或已损坏的图像文件")

    pipeline = get_pipeline()
    faces = pipeline.process_image(image, extract_embedding=True, max_faces=2)
    if len(faces) == 0:
        raise HTTPException(status_code=400, detail="未检测到任何人脸")
    if len(faces) > 1:
        raise HTTPException(status_code=400, detail="注册照片中包含多张人脸，请使用单人清晰照片")

    face_info = faces[0]
    if not face_info.quality.is_valid:
        raise HTTPException(
            status_code=400, detail=f"人脸质量不合格: {face_info.quality.reason}"
        )

    # 保存图片
    file_name = f"person_{person.id}_{int(time.time()*1000)}.jpg"
    save_path = settings.UPLOAD_DIR / file_name
    cv2.imwrite(str(save_path), image)

    feat_bytes = face_info.feature.astype(np.float32).tobytes()
    face = Face(
        person_id=person.id,
        image_path=file_name,
        feature=feat_bytes,
        quality_score=face_info.quality.score,
        yaw=face_info.pose[0],
        pitch=face_info.pose[1],
        roll=face_info.pose[2],
    )
    db.add(face)
    db.commit()
    db.refresh(face)

    # 动态写入内存 Gallery 检索库
    get_gallery().add(face.id, person.id, face_info.feature)

    return {
        "message": "人脸注册成功",
        "face_id": face.id,
        "quality_score": face.quality_score,
        "yaw": face.yaw,
        "pitch": face.pitch,
    }


@router.delete("/faces/{face_id}")
def delete_face(face_id: int, db: Session = Depends(get_db)):
    face = db.query(Face).filter(Face.id == face_id).first()
    if not face:
        raise HTTPException(status_code=404, detail="人脸记录不存在")
    get_gallery().remove(face_id)
    db.delete(face)
    db.commit()
    return {"message": "人脸已删除"}


@router.get("/uploads/{filename}")
def get_upload_image(filename: str):
    path = settings.UPLOAD_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="图片不存在")
    return FileResponse(str(path))


@router.get("/snapshots/{filename}")
def get_snapshot_image(filename: str):
    path = settings.SNAPSHOT_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="抓拍图片不存在")
    return FileResponse(str(path))


# ==================== 3. 实时识别与 1:1 / 1:N 测试台 ====================
@router.post("/recognize/search", response_model=List[SearchResultItem])
async def search_face(
    file: UploadFile = File(...),
    threshold: float = Form(70.0),
    top_k: int = Form(3),
    db: Session = Depends(get_db),
):
    contents = await file.read()
    image = cv2.imdecode(np.frombuffer(contents, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=400, detail="图像解析失败")

    pipeline = get_pipeline()
    faces = pipeline.process_image(image, extract_embedding=True, max_faces=1)
    if not faces:
        return []

    feat = faces[0].feature
    hits = get_gallery().search(feat, top_k=top_k, threshold=threshold)
    res = []
    for h in hits:
        p = db.query(Person).filter(Person.id == h.person_id).first()
        if p:
            res.append(
                SearchResultItem(
                    person_id=p.id,
                    person_no=p.person_no,
                    name=p.name,
                    department=p.department,
                    score=h.score,
                    cosine=h.cosine,
                    liveness_score=round(faces[0].liveness_score, 4) if faces[0].liveness_score is not None else None,
                    is_live=faces[0].is_live,
                )
            )
    return res


@router.post("/recognize/liveness")
async def detect_face_liveness(file: UploadFile = File(...)):
    """静默单目活体检测独立接口（防御照片打印/电子屏幕翻拍攻击）"""
    contents = await file.read()
    image = cv2.imdecode(np.frombuffer(contents, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=400, detail="图像解析失败")

    pipeline = get_pipeline()
    if not pipeline.has_liveness:
        raise HTTPException(status_code=503, detail="当前未挂载静默活体模型 (liveness.onnx / liveness_rk3588.rknn)")

    faces = pipeline.process_image(image, extract_embedding=False, max_faces=1, check_liveness=True)
    if not faces:
        raise HTTPException(status_code=400, detail="未检测到有效人脸")

    face = faces[0]
    return {
        "is_live": bool(face.is_live),
        "liveness_score": round(float(face.liveness_score or 0.0), 4),
        "threshold": pipeline.liveness_threshold,
        "bbox": list(face.bbox),
        "engine": pipeline.backend_type,
    }


@router.post("/recognize/compare")
async def compare_two_faces(
    file1: UploadFile = File(...), file2: UploadFile = File(...)
):
    c1 = await file1.read()
    c2 = await file2.read()
    img1 = cv2.imdecode(np.frombuffer(c1, np.uint8), cv2.IMREAD_COLOR)
    img2 = cv2.imdecode(np.frombuffer(c2, np.uint8), cv2.IMREAD_COLOR)
    if img1 is None or img2 is None:
        raise HTTPException(status_code=400, detail="图片解析失败")

    pipeline = get_pipeline()
    f1 = pipeline.process_image(img1, extract_embedding=True, max_faces=1)
    f2 = pipeline.process_image(img2, extract_embedding=True, max_faces=1)
    if not f1 or not f2:
        raise HTTPException(status_code=400, detail="其中一张图片未检测到有效人脸")

    cos = float(np.dot(f1[0].feature, f2[0].feature))
    score = (cos + 1.0) * 50.0
    return {
        "similarity_score": round(score, 2),
        "cosine": round(cos, 4),
        "same_person": score >= 75.0,
    }


# ==================== 4. 视频抓拍通道与流媒体管理 ====================
@router.get("/devices", response_model=List[DeviceResp])
def list_devices(db: Session = Depends(get_db)):
    return db.query(Device).all()


@router.post("/devices", response_model=DeviceResp)
def create_device(req: DeviceCreate, db: Session = Depends(get_db)):
    dev = Device(**req.model_dump())
    db.add(dev)
    db.commit()
    db.refresh(dev)
    if dev.enabled:
        global_device_manager.start_device(dev)
    return dev


@router.put("/devices/{device_id}", response_model=DeviceResp)
def update_device(device_id: int, req: DeviceUpdate, db: Session = Depends(get_db)):
    dev = db.query(Device).filter(Device.id == device_id).first()
    if not dev:
        raise HTTPException(status_code=404, detail="设备不存在")
    for k, v in req.model_dump(exclude_unset=True).items():
        setattr(dev, k, v)
    db.commit()
    db.refresh(dev)
    if dev.enabled:
        global_device_manager.start_device(dev)
    else:
        global_device_manager.stop_device(dev.id)
    return dev


@router.delete("/devices/{device_id}")
def delete_device(device_id: int, db: Session = Depends(get_db)):
    dev = db.query(Device).filter(Device.id == device_id).first()
    if not dev:
        raise HTTPException(status_code=404, detail="设备不存在")
    global_device_manager.stop_device(device_id)
    db.delete(dev)
    db.commit()
    return {"message": "设备已删除"}


@router.get("/devices/{device_id}/stream")
def device_mjpeg_stream(device_id: int):
    runner = global_device_manager.get_runner(device_id)
    if not runner:
        raise HTTPException(status_code=400, detail="设备未在运行中")

    def frame_generator():
        while True:
            jpeg = runner.get_latest_jpeg()
            if jpeg:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
                )
            time.sleep(0.04)

    return StreamingResponse(
        frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


# ==================== 5. 通行记录与大屏状态 ====================
@router.get("/events")
def list_events(
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db)
):
    """分页获取人脸识别历史日志"""
    page = max(1, page)
    page_size = min(100, max(1, page_size))
    total = db.query(AccessEvent).count()
    events = (
        db.query(AccessEvent)
        .order_by(AccessEvent.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = []
    for e in events:
        p_name = e.person.name if e.person else "未知/陌生人"
        p_no = e.person.person_no if e.person else "-"
        items.append(
            AccessEventResp(
                id=e.id,
                device_id=e.device_id,
                person_id=e.person_id,
                person_name=p_name,
                person_no=p_no,
                result=e.result,
                score=e.score,
                snapshot_path=e.snapshot_path,
                reason=e.reason,
                created_at=e.created_at.strftime("%Y-%m-%d %H:%M:%S") if e.created_at else "-",
            )
        )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": items,
    }


@router.delete("/events/clear")
def clear_all_events(db: Session = Depends(get_db)):
    """一键清理所有人脸识别历史日志与本地抓拍缓存"""
    # 1. 查询所有抓拍图片文件并物理删除
    events = db.query(AccessEvent).all()
    cleaned_files = 0
    for e in events:
        if e.snapshot_path:
            snap_file = settings.SNAPSHOT_DIR / e.snapshot_path
            if snap_file.exists():
                try:
                    snap_file.unlink()
                    cleaned_files += 1
                except Exception as err:
                    logger.warning(f"删除抓拍图片文件失败: {err}")
    # 2. 清空数据库记录
    deleted_count = db.query(AccessEvent).delete()
    db.commit()
    logger.info(f"已清理所有识别历史记录: 共清空 {deleted_count} 条数据，删除 {cleaned_files} 张抓拍图")
    return {
        "message": f"成功清空 {deleted_count} 条识别记录与本地抓拍图片",
        "deleted_count": deleted_count,
        "cleaned_files": cleaned_files,
    }


@router.get("/system/status")
def system_status(db: Session = Depends(get_db)):
    person_cnt = db.query(Person).count()
    face_cnt = db.query(Face).count()
    device_cnt = db.query(Device).count()
    event_cnt = db.query(AccessEvent).count()
    manifest_path = settings.MODELS_DIR / "manifest.json"
    model_version = "fp-irn50-v1"
    if manifest_path.exists():
        try:
            m = json.loads(manifest_path.read_text(encoding="utf-8"))
            model_version = m.get("model_version", model_version)
        except Exception:
            pass
    pipe = get_pipeline()
    cfg = get_cached_settings()
    engine_label = (
        "RK3588 NPU (rknn-toolkit-lite2)"
        if pipe.backend_type == "rknn"
        else "ONNX Runtime (CPU)"
    )
    return {
        "status": "online",
        "person_count": person_cnt,
        "face_feature_count": face_cnt,
        "gallery_memory_size": get_gallery().size(),
        "device_count": device_cnt,
        "access_event_count": event_cnt,
        "model_version": model_version,
        "inference_engine": engine_label,
        "liveness_model_loaded": pipe.has_liveness,
        "liveness_silent_enabled": bool(cfg.get("liveness_silent_enabled", True)),
        "liveness_mode": str(cfg.get("liveness_mode", "silent")),
    }


# ==================== 6. 识别参数配置与模型热升级 ====================
@router.get("/settings/recognition")
def get_recognition_config():
    """获取全局识别与质检算法参数"""
    return get_current_settings()


@router.put("/settings/recognition")
def update_recognition_config(req: dict):
    """保存并热生效全局识别参数"""
    return save_current_settings(req)


@router.get("/models/info")
def get_model_info():
    """获取当前系统部署的模型清单与版本指标"""
    manifest_path = settings.MODELS_DIR / "manifest.json"
    if not manifest_path.exists():
        return {
            "model_version": "fp-irn50-v1",
            "opset": 13,
            "models": {},
        }
    return json.loads(manifest_path.read_text(encoding="utf-8"))


@router.post("/models/upgrade")
async def upgrade_model(
    model_type: str = Form(...),  # feature, detector, landmark
    model_version: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    模型热升级接口：上传替换 .onnx 文件，自动重载推理会话；
    若升级特征模型 (feature)，自动触发底库已有照片批量重新提取与底库刷新。
    """
    valid_types = {
        "feature": "feature.onnx",
        "detector": "detector.onnx",
        "landmark": "landmark.onnx",
        "liveness": "liveness.onnx",
    }
    if model_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"不支持的模型类型: {model_type}，有效值为: {list(valid_types.keys())}")

    filename = valid_types[model_type]
    target_path = settings.MODELS_DIR / filename
    backup_path = settings.MODELS_DIR / f"{filename}.bak"

    # 1. 备份原模型
    if target_path.exists():
        shutil.copy2(target_path, backup_path)

    # 2. 写入新模型
    contents = await file.read()
    with open(target_path, "wb") as f:
        f.write(contents)

    # 3. 尝试热重载验证模型文件是否合法
    try:
        pipeline = reload_pipeline()
    except Exception as e:
        # 回滚原模型
        if backup_path.exists():
            shutil.copy2(backup_path, target_path)
            reload_pipeline()
        logger.error(f"模型升级后验证失败，已自动回滚: {e}")
        raise HTTPException(status_code=400, detail=f"新模型加载失败，已自动回滚: {str(e)}")

    # 4. 更新 manifest.json
    manifest_path = settings.MODELS_DIR / "manifest.json"
    manifest_data = {"model_version": model_version or "fp-irn50-v2", "models": {}}
    if manifest_path.exists():
        try:
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    if model_version:
        manifest_data["model_version"] = model_version
    import hashlib
    manifest_data.setdefault("models", {})[filename] = {
        "sha256": hashlib.sha256(contents).hexdigest(),
        "size_bytes": len(contents),
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    manifest_path.write_text(json.dumps(manifest_data, ensure_ascii=False, indent=2), encoding="utf-8")

    # 5. 若升级的是特征提取模型，则必须将底库人脸照片全部重新提取并更新底库
    reindexed_count = 0
    if model_type == "feature":
        faces = db.query(Face).all()
        for face in faces:
            img_file = settings.UPLOAD_DIR / face.image_path
            if img_file.exists():
                img = cv2.imread(str(img_file))
                if img is not None:
                    # 使用新模型重新对齐和提取特征
                    processed = pipeline.process_image(img, extract_embedding=True, max_faces=1)
                    if processed and processed[0].feature is not None:
                        new_feat = processed[0].feature
                        face.feature = new_feat.astype(np.float32).tobytes()
                        face.model_version = manifest_data.get("model_version", "updated")
                        reindexed_count += 1
        db.commit()
        # 刷新内存向量底库
        reload_gallery()

    return {
        "message": f"模型 [{model_type}] 升级成功并已热加载",
        "model_file": filename,
        "model_version": manifest_data.get("model_version"),
        "reindexed_faces": reindexed_count,
    }


