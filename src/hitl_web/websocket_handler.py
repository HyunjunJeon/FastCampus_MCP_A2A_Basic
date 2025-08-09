"""
HITL WebSocket 핸들러 - 실시간 알림
"""

import json
from src.utils.logging_config import get_logger
from typing import Set, Dict, Any
from fastapi import WebSocket, WebSocketDisconnect

from hitl.manager import hitl_manager
from hitl.notifications import NotificationService


logger = get_logger(__name__)


class WebSocketManager:
    """WebSocket 연결 관리자"""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.notification_service: NotificationService = None

    async def connect(self, websocket: WebSocket):
        """WebSocket 연결"""
        await websocket.accept()
        self.active_connections.add(websocket)

        # 알림 서비스 구독 (처음 연결 시에만)
        if self.notification_service is None:
            self.notification_service = hitl_manager.notification_service
            if self.notification_service:
                self.notification_service.subscribe("web", self._broadcast_notification)

        logger.info(f"WebSocket 연결됨. 총 연결: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        """WebSocket 연결 해제"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket 연결 해제됨. 총 연결: {len(self.active_connections)}")

    async def send_personal_message(
        self, message: Dict[str, Any], websocket: WebSocket
    ):
        """개별 메시지 전송"""
        try:
            await websocket.send_text(json.dumps(message))
        except Exception as e:
            logger.error(f"개별 메시지 전송 실패: {e}")
            self.disconnect(websocket)

    async def broadcast(self, message: Dict[str, Any]):
        """전체 브로드캐스트"""
        if not self.active_connections:
            return

        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_text(json.dumps(message))
            except Exception as e:
                logger.error(f"브로드캐스트 실패: {e}")
                disconnected.add(connection)

        # 실패한 연결 제거
        for conn in disconnected:
            self.disconnect(conn)

    async def _broadcast_notification(self, notification_data: Dict[str, Any]):
        """알림 브로드캐스트"""
        await self.broadcast({"type": "notification", "data": notification_data})


# 전역 WebSocket 매니저
websocket_manager = WebSocketManager()


async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 엔드포인트"""
    await websocket_manager.connect(websocket)
    try:
        while True:
            # 클라이언트로부터 메시지 수신 (keepalive 등)
            data = await websocket.receive_text()
            message = json.loads(data)

            if message.get("type") == "ping":
                await websocket_manager.send_personal_message(
                    {"type": "pong", "timestamp": message.get("timestamp")}, websocket
                )
            elif message.get("type") == "subscribe":
                # 특정 이벤트 구독 처리 (향후 확장)
                await websocket_manager.send_personal_message(
                    {"type": "subscribed", "channel": message.get("channel")}, websocket
                )

    except WebSocketDisconnect:
        websocket_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket 오류: {e}")
        websocket_manager.disconnect(websocket)
