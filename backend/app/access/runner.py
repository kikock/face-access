import asyncio
import logging
import os
import threading
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# 强制 FFmpeg 拉取 RTSP 使用 TCP 传输，彻底消除 UDP 丢包引起的 H264 宏块花屏
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")

import cv2
import numpy as np

from app.core.config import settings
from app.db.models import AccessEvent, Device, Person, SessionLocal
from app.services.state import get_cached_settings, get_gallery, get_pipeline

logger = logging.getLogger(__name__)


class DeviceRunner:
    """单个视频设备（RTSP/USB/本地视频）的独立异步采流与门禁判定运行器。"""

    def __init__(self, device: Device, broadcast_callback=None):
        self.device_id = device.id
        self.device_name = device.name
        self.source_type = device.source_type
        self.source_uri = (device.source_uri or "").strip()
        self.threshold = device.threshold
        self.liveness_enabled = device.liveness_enabled
        self.broadcast_callback = broadcast_callback

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._grab_thread: Optional[threading.Thread] = None

        # 原始抓帧缓存 (供实时推理取最新瞬间帧，避免 FFmpeg 内部队列积压导致花屏与高延迟)
        self._raw_frame: Optional[np.ndarray] = None
        self._raw_seq: int = 0
        self._raw_lock = threading.Lock()

        # 供前端 MJPEG 预览的展示帧缓存
        self._latest_frame: Optional[np.ndarray] = None
        self._frame_lock = threading.Lock()

        # 门禁决策跟踪状态：person_id -> 连续确认命中计数
        self._person_hits: Dict[int, int] = defaultdict(int)
        # 门禁决策跟踪状态：person_id -> 上次成功通行时间戳
        self._person_cooldown: Dict[int, float] = {}
        # 活体眨眼检测窗口：person_id -> 历史 EAR 列表 [(timestamp, ear), ...]
        self._ear_history: Dict[int, List[Tuple[float, float]]] = defaultdict(list)

    def start(self):
        if self._running:
            return
        self._running = True
        self._grab_thread = threading.Thread(target=self._grabber_loop, daemon=True)
        self._thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._grab_thread.start()
        self._thread.start()
        logger.info(f"设备运行器 [{self.device_name} (ID: {self.device_id})] 启动成功")

    def stop(self):
        self._running = False
        if self._grab_thread and self._grab_thread.is_alive():
            self._grab_thread.join(timeout=2.0)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info(f"设备运行器 [{self.device_name}] 已停止")

    def get_latest_jpeg(self) -> Optional[bytes]:
        with self._frame_lock:
            if self._latest_frame is None:
                return None
            ret, buf = cv2.imencode(".jpg", self._latest_frame)
            return buf.tobytes() if ret else None

    def _resolve_source_uri(self):
        """解析视频源参数。若为未配置的空 URI 返回 None 避免死循环探测不存在的设备。"""
        if not self.source_uri:
            return None
        if self.source_type == "usb":
            try:
                return int(self.source_uri)
            except ValueError:
                # 兼容 Linux /dev/videoX 设备路径
                return self.source_uri
        return self.source_uri

    def _grabber_loop(self):
        """独立高速抓帧线程：专职消费 RTSP/USB 解码流并保留最新帧，防止缓冲积压花屏。"""
        uri = self._resolve_source_uri()
        if uri is None:
            logger.warning(f"设备 [{self.device_name}] 未配置有效的视频源 URI，已挂起等待配置更新")
            while self._running:
                time.sleep(1.0)
            return

        cap = None
        fail_count = 0

        while self._running:
            if cap is None or not cap.isOpened():
                logger.info(f"设备 [{self.device_name}] 正在连接视频源: {uri} ...")
                if self.source_type == "rtsp":
                    cap = cv2.VideoCapture(uri, cv2.CAP_FFMPEG)
                else:
                    cap = cv2.VideoCapture(uri)

                if cap is not None and cap.isOpened():
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    fail_count = 0
                    logger.info(f"设备 [{self.device_name}] 视频流连接就绪 (TCP低延迟模式)")
                else:
                    fail_count += 1
                    wait_sec = min(30.0, 5.0 * fail_count)
                    logger.warning(f"设备 [{self.device_name}] 视频源打开失败，{wait_sec:.0f}秒后重试")
                    if cap:
                        cap.release()
                        cap = None
                    for _ in range(int(wait_sec * 2)):
                        if not self._running:
                            break
                        time.sleep(0.5)
                    continue

            ret, frame = cap.read()
            if not ret or frame is None:
                if self.source_type == "file":
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    time.sleep(0.03)
                    continue
                logger.warning(f"设备 [{self.device_name}] 视频读取丢帧或断开，正在重连...")
                cap.release()
                cap = None
                time.sleep(2.0)
                continue

            with self._raw_lock:
                self._raw_frame = frame
                self._raw_seq += 1

            # 同步更新展示缓存供前端 MJPEG 实时流畅预览
            with self._frame_lock:
                self._latest_frame = frame

            # 本地文件模拟适度控制帧率，实时 RTSP 流全速消费不堵塞
            if self.source_type == "file":
                time.sleep(0.033)

        if cap:
            cap.release()

    def _worker_loop(self):
        """AI 推理工作线程：总是获取最新瞬间帧进行检测、活体防伪与 1:N 检索。"""
        pipeline = get_pipeline()
        gallery = get_gallery()
        last_seq = -1

        while self._running:
            frame = None
            with self._raw_lock:
                if self._raw_frame is not None and self._raw_seq != last_seq:
                    frame = self._raw_frame.copy()
                    last_seq = self._raw_seq

            if frame is None:
                time.sleep(0.02)
                continue

            # 执行人脸检测与比对
            try:
                recog_cfg = get_cached_settings()
                silent_enabled = bool(recog_cfg.get("liveness_silent_enabled", True))
                liveness_mode = str(recog_cfg.get("liveness_mode", settings.LIVENESS_MODE))
                cont_frames = int(recog_cfg.get("default_continuous_frames", settings.DEFAULT_CONTINUOUS_FRAMES))
                cooldown_sec = float(recog_cfg.get("person_cooldown_seconds", settings.PERSON_COOLDOWN_SECONDS))
                ear_thresh = float(recog_cfg.get("liveness_ear_threshold", settings.LIVENESS_EAR_THRESHOLD))

                need_silent = self.liveness_enabled and silent_enabled and (liveness_mode in ("silent", "both"))
                faces = pipeline.process_image(
                    frame, extract_embedding=True, max_faces=3, check_liveness=need_silent
                )
                now = time.time()

                for face in faces:
                    if not face.quality.is_valid:
                        continue
                    if face.feature is None:
                        continue

                    # 1:N 检索
                    hits = gallery.search(
                        face.feature, top_k=1, threshold=self.threshold
                    )

                    if not hits:
                        # 陌生人
                        continue

                    top_hit = hits[0]
                    pid = top_hit.person_id
                    score = top_hit.score

                    # 检查冷却时间
                    last_pass = self._person_cooldown.get(pid, 0.0)
                    if now - last_pass < cooldown_sec:
                        continue

                    # 活体防伪拦截（支持 silent 单目静默 / blink 眨眼 / both 双重校验）
                    if self.liveness_enabled:
                        # 1. 静默单目活体拦截 (当全局开关启用时针对照片/手机屏幕翻拍攻击瞬间拦截)
                        if need_silent and face.is_live is False:
                            logger.warning(
                                f"【防伪拦截】通道 [{self.device_name}] 检测到非活体攻击 "
                                f"(人员ID: {pid}, 活体置信度: {face.liveness_score:.3f})"
                            )
                            self._person_hits[pid] = 0
                            continue

                        # 2. EAR 眨眼动作跟踪
                        if liveness_mode in ("blink", "both"):
                            self._ear_history[pid].append((now, face.ear))
                            self._ear_history[pid] = [
                                (t, e) for (t, e) in self._ear_history[pid] if now - t <= 5.0
                            ]

                    self._person_hits[pid] += 1

                    # 判定连续帧命中
                    if self._person_hits[pid] >= cont_frames:
                        liveness_ok = True
                        if self.liveness_enabled and liveness_mode in ("blink", "both"):
                            ears = [e for (_, e) in self._ear_history[pid]]
                            if len(ears) >= 3:
                                min_ear = min(ears)
                                if min_ear > ear_thresh:
                                    liveness_ok = False
                            else:
                                liveness_ok = False

                        if liveness_ok or not self.liveness_enabled:
                            # 触发开门与事件写入
                            self._trigger_access_granted(
                                person_id=pid,
                                score=score,
                                snapshot_img=frame,
                                bbox=face.bbox,
                            )
                            self._person_hits[pid] = 0
                            self._person_cooldown[pid] = now

                # 适度让出线程调度
                time.sleep(0.01)

            except Exception as e:
                logger.error(f"设备 [{self.device_name}] 处理帧异常: {e}")
                time.sleep(0.1)

    def _trigger_access_granted(
        self, person_id: int, score: float, snapshot_img: np.ndarray, bbox: Tuple[int, int, int, int]
    ):
        db = SessionLocal()
        try:
            person = db.query(Person).filter(Person.id == person_id).first()
            if not person or not person.enabled:
                return

            # 有效期校验
            now_dt = datetime.utcnow()
            if person.valid_from and now_dt < person.valid_from:
                return
            if person.valid_to and now_dt > person.valid_to:
                return

            # 通道运行状态下正常记录抓拍照片与写入数据库
            snap_name = f"snap_dev{self.device_id}_{int(time.time()*1000)}.jpg"
            snap_path = settings.SNAPSHOT_DIR / snap_name

            # 抓拍图上绘制绿色人脸框与姓名
            vis = snapshot_img.copy()
            x1, y1, x2, y2 = bbox
            cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(
                vis,
                f"{person.name} ({score:.1f})",
                (x1, max(20, y1 - 10)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2,
            )
            cv2.imwrite(str(snap_path), vis)

            # 记录数据库事件
            event = AccessEvent(
                device_id=self.device_id,
                person_id=person.id,
                result="granted",
                score=score,
                snapshot_path=snap_name,
                reason="人脸识别比对通过",
            )
            db.add(event)
            db.commit()
            db.refresh(event)

            logger.info(
                f"【识别成功】通道 [{self.device_name}] 命中人员: {person.name} (工号: {person.person_no}), 得分: {score:.1f}"
            )

            # 前端页面通过 WebSocket 实时接收识别消息
            if self.broadcast_callback:
                self.broadcast_callback(
                    {
                        "type": "access_event",
                        "event_id": event.id,
                        "device_id": self.device_id,
                        "person_id": person.id,
                        "person_name": person.name,
                        "person_no": person.person_no,
                        "score": score,
                        "snapshot": snap_name,
                        "time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                    }
                )

        finally:
            db.close()


class DeviceManager:
    """管理系统内所有视频设备运行器的单例管理器。"""

    def __init__(self):
        self._runners: Dict[int, DeviceRunner] = {}
        self._broadcast_cb = None

    def set_broadcast_callback(self, cb):
        self._broadcast_cb = cb

    def start_device(self, device: Device):
        if device.id in self._runners:
            self._runners[device.id].stop()
        runner = DeviceRunner(device, broadcast_callback=self._broadcast_cb)
        self._runners[device.id] = runner
        runner.start()

    def stop_device(self, device_id: int):
        if device_id in self._runners:
            self._runners[device_id].stop()
            del self._runners[device_id]

    def get_runner(self, device_id: int) -> Optional[DeviceRunner]:
        return self._runners.get(device_id)

    def stop_all(self):
        for runner in self._runners.values():
            runner.stop()
        self._runners.clear()


global_device_manager = DeviceManager()

