import cv2
import numpy as np
import pytest

from app.engine.align import align_face_68
from app.engine.gallery import Gallery
from app.engine.pipeline import FacePipeline
from app.engine.pose import compute_eye_aspect_ratio, estimate_head_pose
from app.engine.quality import FaceQualityChecker

SDK_TEST_IMG1 = "d:/code/01_github_code/Open-Source-Face-Recognition-SDK/test/1.jpg"
SDK_TEST_IMG2 = "d:/code/01_github_code/Open-Source-Face-Recognition-SDK/test/2.png"
MODELS_DIR = "models"


def test_align_and_pose():
    img = cv2.imread(SDK_TEST_IMG1)
    assert img is not None, "测试图片读取失败"
    lm = np.load("tools/test_lm.npy")
    aligned = align_face_68(img, lm)
    assert aligned.shape == (128, 128, 3)

    yaw, pitch, roll = estimate_head_pose(lm, img.shape[:2])
    assert abs(yaw) < 45.0
    assert abs(pitch) < 45.0

    ear = compute_eye_aspect_ratio(lm)
    assert 0.1 < ear < 0.6


def test_gallery_1_to_n():
    gallery = Gallery(feature_dim=256)
    f1 = np.random.randn(256).astype(np.float32)
    f1 /= np.linalg.norm(f1)
    gallery.add(face_id=1, person_id=101, feature=f1)

    f2 = np.random.randn(256).astype(np.float32)
    f2 /= np.linalg.norm(f2)
    gallery.add(face_id=2, person_id=102, feature=f2)

    assert gallery.size() == 2

    # 查询 f1，得分应当接近 100
    hits = gallery.search(f1, top_k=2, threshold=75.0)
    assert len(hits) >= 1
    assert hits[0].person_id == 101
    assert hits[0].score > 99.0

    # 删除
    assert gallery.remove(1) is True
    assert gallery.size() == 1
    hits_after = gallery.search(f1, top_k=2, threshold=75.0)
    assert len(hits_after) == 0


def test_pipeline_end_to_end_sdk_images():
    pipeline = FacePipeline(model_dir=MODELS_DIR)

    img1 = cv2.imread(SDK_TEST_IMG1)
    img2 = cv2.imread(SDK_TEST_IMG2)
    assert img1 is not None and img2 is not None

    faces1 = pipeline.process_image(img1)
    faces2 = pipeline.process_image(img2)

    assert len(faces1) >= 1
    assert len(faces2) >= 1

    feat1 = faces1[0].feature
    feat2 = faces2[0].feature
    assert feat1 is not None and feat2 is not None

    # 计算 1.jpg 与 2.png 的余弦相似度并换算打分
    cos = float(np.dot(feat1, feat2))
    score = (cos + 1.0) * 50.0
    print(f"\n1.jpg 与 2.png 经 ONNX Pipeline 比对分: {score:.2f}")
    # 原 SDK 官方示例同一人阈值 75
    assert score > 75.0, f"同一人比对得分未达到门禁通过阈值: {score}"


def test_pipeline_rknn_auto_fallback_to_onnx(tmp_path):
    """当不存在 RKNN 模型文件或驱动时，auto 模式应无痛回退到 ONNX CPU 引擎"""
    pipeline = FacePipeline(
        model_dir=MODELS_DIR,
        rknn_model_dir=tmp_path,
        backend="auto",
    )
    assert pipeline.backend_type == "onnx"


def test_pipeline_rknn_strict_mode_raises(tmp_path):
    """强制开启 rknn 模式下若缺少 RKNN 文件应显式抛出异常"""
    with pytest.raises(FileNotFoundError):
        FacePipeline(
            model_dir=MODELS_DIR,
            rknn_model_dir=tmp_path,
            backend="rknn",
        )


def test_pipeline_rknn_mock_inference(tmp_path, monkeypatch):
    """使用 Mock RKNNLite 模拟全流程 3 核绑定与 NHWC uint8 输入张量规范验证"""
    import sys
    import types

    for name in ("detector_rk3588.rknn", "landmark_rk3588.rknn", "feature_rk3588.rknn"):
        (tmp_path / name).write_bytes(b"mock-rknn")

    bound_cores = []
    recorded_inputs = []

    class FakeRKNNLite:
        NPU_CORE_0 = 1
        NPU_CORE_1 = 2
        NPU_CORE_2 = 4

        def __init__(self):
            self.model_name = ""

        def load_rknn(self, path):
            self.model_name = path
            return 0

        def init_runtime(self, core_mask=0):
            bound_cores.append(core_mask)
            return 0

        def inference(self, inputs, data_format="nhwc"):
            assert data_format == "nhwc"
            arr = inputs[0]
            assert arr.dtype == np.uint8
            recorded_inputs.append(arr.shape)

            if "detector" in self.model_name:
                scores = np.zeros((1, 4420, 2), dtype=np.float32)
                scores[0, 0, 1] = 0.99
                boxes = np.zeros((1, 4420, 4), dtype=np.float32)
                boxes[0, 0] = [0.2, 0.2, 0.8, 0.8]
                return [scores, boxes]
            elif "landmark" in self.model_name:
                lm = np.full((1, 136), 0.5, dtype=np.float32)
                return [lm]
            else:
                feat = np.ones((1, 256), dtype=np.float32)
                return [feat]

    fake_api = types.ModuleType("rknnlite.api")
    fake_api.RKNNLite = FakeRKNNLite
    fake_pkg = types.ModuleType("rknnlite")
    fake_pkg.api = fake_api

    monkeypatch.setitem(sys.modules, "rknnlite", fake_pkg)
    monkeypatch.setitem(sys.modules, "rknnlite.api", fake_api)

    pipeline = FacePipeline(
        model_dir=MODELS_DIR,
        rknn_model_dir=tmp_path,
        backend="rknn",
    )
    assert pipeline.backend_type == "rknn"
    # 验证已分别绑定 Core 0 / Core 1 / Core 2
    assert bound_cores == [1, 2, 4]

    dummy_img = np.zeros((480, 640, 3), dtype=np.uint8)
    faces = pipeline.detect(dummy_img)
    assert len(faces) == 1

    gray = np.zeros((480, 640), dtype=np.uint8)
    lm = pipeline.extract_landmark(gray, faces[0][0])
    assert lm.shape == (68, 2)

    aligned = np.zeros((128, 128, 3), dtype=np.uint8)
    feat = pipeline.extract_feature(aligned)
    assert feat.shape == (256,)
    assert np.isclose(np.linalg.norm(feat), 1.0, atol=1e-4)

    # 验证输入 NPU 张量严格对齐 [1, 240, 320, 3], [1, 64, 64, 1], [1, 128, 128, 3]
    assert recorded_inputs == [(1, 240, 320, 3), (1, 64, 64, 1), (1, 128, 128, 3)]


def test_silent_liveness_real_vs_spoof():
    """验证 MiniFASNetV2 静默单目活体对真实人脸 (image_T1) 与翻拍假脸 (image_F1/F2) 的判别精度"""
    pipeline = FacePipeline(model_dir=MODELS_DIR, backend="onnx")
    assert pipeline.has_liveness is True

    real_img = cv2.imread("tests/fixtures/liveness/image_T1.jpg")
    fake_img1 = cv2.imread("tests/fixtures/liveness/image_F1.jpg")
    fake_img2 = cv2.imread("tests/fixtures/liveness/image_F2.jpg")
    assert real_img is not None and fake_img1 is not None and fake_img2 is not None

    real_faces = pipeline.process_image(real_img, extract_embedding=False)
    fake_faces1 = pipeline.process_image(fake_img1, extract_embedding=False)
    fake_faces2 = pipeline.process_image(fake_img2, extract_embedding=False)

    assert len(real_faces) >= 1 and real_faces[0].is_live is True
    assert real_faces[0].liveness_score > 0.85

    assert len(fake_faces1) >= 1 and fake_faces1[0].is_live is False
    assert fake_faces1[0].liveness_score < 0.50

    assert len(fake_faces2) >= 1 and fake_faces2[0].is_live is False
    assert fake_faces2[0].liveness_score < 0.50
    print(
        f"\n[静默活体自检] 真脸得分: {real_faces[0].liveness_score:.4f} | "
        f"伪造1得分: {fake_faces1[0].liveness_score:.4f} | 伪造2得分: {fake_faces2[0].liveness_score:.4f}"
    )



