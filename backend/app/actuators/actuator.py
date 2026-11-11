import abc
import json
import logging
from typing import Any, Dict
import httpx

logger = logging.getLogger(__name__)


class BaseActuator(abc.ABC):
    @abc.abstractmethod
    async def open_door(self, device_id: int, duration_seconds: int = 3, reason: str = "") -> bool:
        pass


class SimulatorActuator(BaseActuator):
    """模拟器执行器：输出审计控制台日志并模拟继电器吸合与断开。"""
    async def open_door(self, device_id: int, duration_seconds: int = 3, reason: str = "") -> bool:
        logger.info(
            f"[模拟器执行器] 设备 {device_id} 触发开门动作 -> 持续 {duration_seconds} 秒 (原因: {reason})"
        )
        return True


class WebhookActuator(BaseActuator):
    """HTTP Webhook 执行器：向第三方门禁控制器或中控系统分发开门信号。"""
    def __init__(self, config_json: str):
        self.config: Dict[str, Any] = {}
        try:
            self.config = json.loads(config_json) if config_json else {}
        except Exception:
            pass
        self.url = self.config.get("url", "")
        self.token = self.config.get("token", "")

    async def open_door(self, device_id: int, duration_seconds: int = 3, reason: str = "") -> bool:
        if not self.url:
            logger.warning(f"设备 {device_id} 未配置 Webhook URL，忽略开门分发")
            return False
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        payload = {
            "device_id": device_id,
            "action": "open_door",
            "duration_seconds": duration_seconds,
            "reason": reason,
        }
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                res = await client.post(self.url, json=payload, headers=headers)
                logger.info(f"设备 {device_id} Webhook 开门响应状态: {res.status_code}")
                return res.status_code < 400
        except Exception as e:
            logger.error(f"设备 {device_id} Webhook 开门请求失败: {e}")
            return False


def get_actuator(actuator_type: str, config_json: str = "{}") -> BaseActuator:
    if actuator_type == "webhook":
        return WebhookActuator(config_json)
    return SimulatorActuator()

