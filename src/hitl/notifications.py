"""
HITL 알림 서비스
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional
from abc import ABC, abstractmethod
import aiohttp
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from .models import ApprovalRequest

logger = logging.getLogger(__name__)


class NotificationChannel(ABC):
    """알림 채널 인터페이스"""

    @abstractmethod
    async def send(self, request: ApprovalRequest) -> bool:
        """알림 전송"""
        pass

# 구현체 샘플
class EmailNotificationChannel(NotificationChannel):
    """이메일 알림 채널"""

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        username: str,
        password: str,
        from_email: str,
        to_emails: List[str],
    ):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.from_email = from_email
        self.to_emails = to_emails

    async def send(self, request: ApprovalRequest) -> bool:
        """이메일 알림 전송"""
        try:
            # 이메일 구성
            msg = MIMEMultipart()
            msg["From"] = self.from_email
            msg["To"] = ", ".join(self.to_emails)
            msg["Subject"] = f"[HITL] 승인 요청: {request.title}"

            # 본문 작성
            body = f"""
새로운 승인 요청이 있습니다.

제목: {request.title}
유형: {request.approval_type.value}
우선순위: {request.priority}
에이전트: {request.agent_id}

설명:
{request.description}

승인 페이지: http://localhost:8090/

요청 ID: {request.request_id}
만료 시간: {request.expires_at}
"""

            msg.attach(MIMEText(body, "plain"))

            # 이메일 전송 (비동기 처리를 위해 스레드 사용)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._send_email, msg)

            logger.info(f"이메일 알림 전송 완료: {request.request_id}")
            return True

        except Exception as e:
            logger.error(f"이메일 전송 실패: {e}")
            return False

    def _send_email(self, msg):
        """동기 이메일 전송"""
        with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
            server.starttls()
            server.login(self.username, self.password)
            server.send_message(msg)

# 구현체 샘플
class SlackNotificationChannel(NotificationChannel):
    """Slack 알림 채널"""

    def __init__(self, webhook_url: str, channel: Optional[str] = None):
        self.webhook_url = webhook_url
        self.channel = channel

    async def send(self, request: ApprovalRequest) -> bool:
        """Slack 알림 전송"""
        try:
            # 메시지 구성
            priority_emoji = {
                "critical": "🚨",
                "high": "⚠️",
                "medium": "📌",
                "low": "💬",
            }

            message = {
                "text": f"{priority_emoji.get(request.priority, '📌')} 새로운 HITL 승인 요청",
                "blocks": [
                    {
                        "type": "header",
                        "text": {"type": "plain_text", "text": request.title},
                    },
                    {
                        "type": "section",
                        "fields": [
                            {
                                "type": "mrkdwn",
                                "text": f"*유형:* {request.approval_type.value}",
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*우선순위:* {request.priority}",
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*에이전트:* {request.agent_id}",
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*만료:* {request.expires_at.strftime('%H:%M:%S') if request.expires_at else 'N/A'}",
                            },
                        ],
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*설명:*\n{request.description}",
                        },
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "승인 페이지로 이동",
                                },
                                "url": f"http://localhost:8090/#request/{request.request_id}",
                                "style": "primary",
                            }
                        ],
                    },
                ],
            }

            if self.channel:
                message["channel"] = self.channel

            # Slack 전송
            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json=message) as response:
                    success = response.status == 200

                    if success:
                        logger.info(f"Slack 알림 전송 완료: {request.request_id}")
                    else:
                        logger.error(f"Slack 전송 실패: {response.status}")

                    return success

        except Exception as e:
            logger.error(f"Slack 알림 전송 오류: {e}")
            return False

# 구현체 샘플
class WebPushNotificationChannel(NotificationChannel):
    """웹 푸시 알림 채널"""

    def __init__(self, vapid_private_key: str, vapid_claims: Dict[str, str]):
        self.vapid_private_key = vapid_private_key
        self.vapid_claims = vapid_claims
        self.subscriptions: List[Dict[str, Any]] = []

    async def send(self, request: ApprovalRequest) -> bool:
        """웹 푸시 알림 전송"""
        # 구현 예정 (pywebpush 라이브러리 사용)
        logger.info(f"웹 푸시 알림 (미구현): {request.request_id}")
        return True


class NotificationService:
    """통합 알림 서비스"""

    def __init__(self):
        self.channels: Dict[str, NotificationChannel] = {}
        self._initialized = False

    async def initialize(self):
        """알림 서비스 초기화"""
        # 환경변수에서 설정 로드
        import os

        # Slack 설정
        slack_webhook = os.getenv("SLACK_WEBHOOK_URL")
        if slack_webhook:
            self.channels["slack"] = SlackNotificationChannel(slack_webhook)
            logger.info("Slack 알림 채널 활성화")

        # 이메일 설정 (예시)
        smtp_host = os.getenv("SMTP_HOST")
        if smtp_host:
            self.channels["email"] = EmailNotificationChannel(
                smtp_host=smtp_host,
                smtp_port=int(os.getenv("SMTP_PORT", "587")),
                username=os.getenv("SMTP_USERNAME", ""),
                password=os.getenv("SMTP_PASSWORD", ""),
                from_email=os.getenv("FROM_EMAIL", "hitl@example.com"),
                to_emails=os.getenv("TO_EMAILS", "").split(","),
            )
            logger.info("이메일 알림 채널 활성화")

        self._initialized = True
        logger.info(f"알림 서비스 초기화 완료: {len(self.channels)}개 채널")

    async def shutdown(self):
        """서비스 종료"""
        self.channels.clear()
        self._initialized = False

    async def send_approval_notification(self, request: ApprovalRequest):
        """모든 채널로 승인 알림 전송"""
        if not self._initialized:
            logger.warning("알림 서비스가 초기화되지 않았습니다")
            return

        # 우선순위별 채널 선택
        if request.priority == "critical":
            # 모든 채널로 전송
            channels_to_use = self.channels.keys()
        elif request.priority == "high":
            # Slack과 이메일만
            channels_to_use = ["slack", "email"]
        else:
            # Slack만
            channels_to_use = ["slack"]

        # 병렬 전송
        tasks = []
        for channel_name in channels_to_use:
            if channel_name in self.channels:
                channel = self.channels[channel_name]
                tasks.append(channel.send(request))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            success_count = sum(1 for r in results if r is True)
            logger.info(f"알림 전송 완료: {success_count}/{len(tasks)} 채널")

    def register_channel(self, name: str, channel: NotificationChannel):
        """알림 채널 등록"""
        self.channels[name] = channel
        logger.info(f"알림 채널 등록: {name}")

    def unregister_channel(self, name: str):
        """알림 채널 제거"""
        if name in self.channels:
            del self.channels[name]
            logger.info(f"알림 채널 제거: {name}")
