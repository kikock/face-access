import os
import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_health_check(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_admin_login_and_change_pwd(client):
    # 1. 未携带 Token 禁止修改
    unauth = client.post(
        "/api/v1/auth/change-password",
        json={"old_password": "admin123456", "new_password": "NewPassword123"},
    )
    assert unauth.status_code == 401

    # 2. 默认账密登录
    res = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123456"})
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["username"] == "admin"
    assert data["must_change_password"] is True
    headers = {"Authorization": f"Bearer {data['access_token']}"}

    # 3. 校验当前登录账号 /auth/me
    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["username"] == "admin"

    # 4. 原密码错误拦截
    bad_old = client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"old_password": "wrong", "new_password": "NewPassword123"},
    )
    assert bad_old.status_code == 400

    # 5. 同时修改账号名与密码
    chg = client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"old_password": "admin123456", "new_username": "admin_pro", "new_password": "NewPassword123"},
    )
    assert chg.status_code == 200
    assert chg.json()["username"] == "admin_pro"
    new_headers = {"Authorization": f"Bearer {chg.json()['access_token']}"}

    # 6. 旧账密失效，新账密可登录
    assert client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123456"}).status_code == 400
    login_new = client.post("/api/v1/auth/login", json={"username": "admin_pro", "password": "NewPassword123"})
    assert login_new.status_code == 200
    assert login_new.json()["must_change_password"] is False

    # 7. 还原默认账号以便后续幂等重复测试
    restore = client.post(
        "/api/v1/auth/change-password",
        headers=new_headers,
        json={"old_password": "NewPassword123", "new_username": "admin", "new_password": "admin123456"},
    )
    assert restore.status_code == 200


def test_person_lifecycle(client):
    unique_no = f"P_{uuid.uuid4().hex[:8]}"
    # 1. 创建人员
    p_data = {
        "person_no": unique_no,
        "name": "张工",
        "department": "技术部",
        "phone": "13800000000"
    }
    res = client.post("/api/v1/persons", json=p_data)
    assert res.status_code == 200
    created = res.json()
    p_id = created["id"]
    assert created["name"] == "张工"

    # 1.5 更新人员信息
    upd_res = client.put(f"/api/v1/persons/{p_id}", json={"name": "张工(改)", "department": "研发部", "enabled": True})
    assert upd_res.status_code == 200
    assert upd_res.json()["name"] == "张工(改)"
    assert upd_res.json()["department"] == "研发部"

    # 2. 上传人脸注册 (1.jpg)
    with open("d:/code/01_github_code/Open-Source-Face-Recognition-SDK/test/1.jpg", "rb") as f:
        res_face = client.post(f"/api/v1/persons/{p_id}/faces", files={"file": ("1.jpg", f, "image/jpeg")})
    assert res_face.status_code == 200
    face_data = res_face.json()
    assert "face_id" in face_data

    # 3. 1:N 搜索识别测试 (2.png 为同一人)
    with open("d:/code/01_github_code/Open-Source-Face-Recognition-SDK/test/2.png", "rb") as f:
        res_search = client.post("/api/v1/recognize/search", files={"file": ("2.png", f, "image/png")})
    assert res_search.status_code == 200
    hits = res_search.json()
    assert len(hits) >= 1
    assert hits[0]["person_no"] == unique_no
    assert hits[0]["score"] > 75.0

    # 4. 删除人员并同步检查
    del_res = client.delete(f"/api/v1/persons/{p_id}")
    assert del_res.status_code == 200


def test_liveness_config_toggle(client):
    """验证静默活体全局配置开关热更新与 system/status 状态同步"""
    res_put = client.put(
        "/api/v1/settings/recognition",
        json={"liveness_silent_enabled": False, "liveness_mode": "blink", "liveness_silent_threshold": 0.75},
    )
    assert res_put.status_code == 200
    assert res_put.json()["liveness_silent_enabled"] is False

    status_res = client.get("/api/v1/system/status")
    assert status_res.status_code == 200
    assert status_res.json()["liveness_silent_enabled"] is False

    # 还原默认开启状态
    res_restore = client.put(
        "/api/v1/settings/recognition",
        json={"liveness_silent_enabled": True, "liveness_mode": "silent", "liveness_silent_threshold": 0.80},
    )
    assert res_restore.status_code == 200
    assert res_restore.json()["liveness_silent_enabled"] is True


def test_batch_import_info_and_faces(client):
    """验证人员信息 CSV 批量导入与人脸照片分开批量关联上传"""
    tpl = client.get("/api/v1/persons/batch-template")
    assert tpl.status_code == 200

    pno = f"BATCH_{uuid.uuid4().hex[:6]}"
    csv_bytes = f"\ufeff工号,姓名,部门,联系电话,备注\n{pno},批量测试员,算法部,13900001111,测试\n".encode("utf-8")

    # 1. 批量导入基本信息
    res_info = client.post(
        "/api/v1/persons/batch-info",
        files={"file": ("persons.csv", csv_bytes, "text/csv")},
    )
    assert res_info.status_code == 200
    assert res_info.json()["created_count"] == 1

    # 2. 批量上传照片（工号_1.jpg 匹配 + 未匹配文件测试）
    with open("d:/code/01_github_code/Open-Source-Face-Recognition-SDK/test/1.jpg", "rb") as f:
        img_data = f.read()

    res_faces = client.post(
        "/api/v1/persons/batch-faces",
        files=[
            ("files", (f"{pno}_1.jpg", img_data, "image/jpeg")),
            ("files", ("UNKNOWN_999.jpg", img_data, "image/jpeg")),
        ],
    )
    assert res_faces.status_code == 200
    fdata = res_faces.json()
    assert fdata["total"] == 2
    assert fdata["success_count"] == 1
    assert fdata["failed_count"] == 1

    # 清理测试人员
    persons = client.get("/api/v1/persons").json()
    target = next((p for p in persons if p["person_no"] == pno), None)
    assert target is not None and len(target["faces"]) == 1
    client.delete(f"/api/v1/persons/{target['id']}")

