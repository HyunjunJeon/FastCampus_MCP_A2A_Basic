"""HITL 알림 서비스 모듈.

이 모듈은 HITL 승인 요청에 대한 다중 채널 알림 시스템을 제공합니다.

주요 기능:
    - 추상 알림 채널 인터페이스 (NotificationChannel)
    - 이메일, Slack, 웹 푸시 등 다양한 채널 구현체
    - 우선순위 기반 채널 라우팅
    - 병렬 알림 전송

Example:
    >>> service = NotificationService()
    >>> await service.initialize()
    >>> await service.send_approval_notification(approval_request)
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional
from abc import ABC, abstractmethod
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from .models import ApprovalRequest
from src.utils.http_client import http_client

logger = logging.getLogger(__name__)


class NotificationChannel(ABC):
    """알림 채널 추상 인터페이스.

    HITL 승인 요청을 다양한 채널(이메일, Slack, 웹 푸시 등)로
    전달하기 위한 공통 인터페이스를 정의합니다.

    Subclasses:
        EmailNotificationChannel: SMTP 기반 이메일 알림
        SlackNotificationChannel: Slack 웹훅 기반 알림
        WebPushNotificationChannel: 웹 푸시 알림 (미구현)
    """

    @abstractmethod
    async def send(self, request: ApprovalRequest) -> bool:
        """승인 요청 알림을 전송합니다.

        Args:
            request: 전송할 승인 요청 객체.

        Returns:
            전송 성공 여부.
        """
        pass


class EmailNotificationChannel(NotificationChannel):
    """SMTP 기반 이메일 알림 채널.

    SMTP 서버를 통해 승인 요청 알림 이메일을 전송합니다.
    TLS 암호화를 지원하며, 비동기 처리를 위해 스레드 풀을 사용합니다.

    Attributes:
        smtp_host: SMTP 서버 호스트.
        smtp_port: SMTP 서버 포트.
        username: SMTP 인증 사용자명.
        password: SMTP 인증 비밀번호.
        from_email: 발신자 이메일 주소.
        to_emails: 수신자 이메일 주소 목록.
    """

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        username: str,
        password: str,
        from_email: str,
        to_emails: List[str],
    ) -> None:
        """EmailNotificationChannel 인스턴스를 초기화합니다.

        Args:
            smtp_host: SMTP 서버 호스트.
            smtp_port: SMTP 서버 포트 (기본: 587).
            username: SMTP 인증 사용자명.
            password: SMTP 인증 비밀번호.
            from_email: 발신자 이메일 주소.
            to_emails: 수신자 이메일 주소 목록.
        """
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

    def _send_email(self, msg: MIMEMultipart) -> None:
        """동기 이메일 전송"""
        with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
            server.starttls()
            server.login(self.username, self.password)
            server.send_message(msg)

class SlackNotificationChannel(NotificationChannel):
    """Slack 웹훅 기반 알림 채널.

    Slack Incoming Webhook을 통해 승인 요청 알림을 전송합니다.
    Block Kit 형식의 리치 메시지를 지원하며, 우선순위에 따른 이모지 표시와
    승인 페이지 링크 버튼을 포함합니다.

    Attributes:
        webhook_url: Slack Incoming Webhook URL.
        channel: 대상 채널 (선택적, 웹훅 기본 채널 사용).
    """

    def __init__(self, webhook_url: str, channel: Optional[str] = None) -> None:
        """SlackNotificationChannel 인스턴스를 초기화합니다.

        Args:
            webhook_url: Slack Incoming Webhook URL.
            channel: 대상 채널. None이면 웹훅 기본 채널 사용.
        """
        self.webhook_url = webhook_url
        self.channel = channel

    async def send(self, request: ApprovalRequest) -> bool:
        """Slack으로 승인 요청 알림을 전송합니다.

        Args:
            request: 전송할 승인 요청 객체.

        Returns:
            전송 성공 여부 (HTTP 200 응답 시 True).
        """
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

            # Slack 전송 (공통 http 클라이언트 사용)
            response = await http_client.post(self.webhook_url, json=message)
            success = response.status_code == 200

            if success:
                logger.info(f"Slack 알림 전송 완료: {request.request_id}")
            else:
                try:
                    logger.error(
                        f"Slack 전송 실패: status={response.status_code} body={response.text}"
                    )
                except Exception:
                    logger.error(f"Slack 전송 실패: status={response.status_code}")

            return success

        except Exception as e:
            logger.error(f"Slack 알림 전송 오류: {e}")
            return False

class WebPushNotificationChannel(NotificationChannel):
    """웹 푸시 알림 채널 (구현 예정).

    VAPID 프로토콜을 사용하여 웹 브라우저에 푸시 알림을 전송합니다.
    pywebpush 라이브러리를 통해 구현 예정입니다.

    Attributes:
        vapid_private_key: VAPID 개인 키.
        vapid_claims: VAPID 클레임 (sub, exp 등).
        subscriptions: 구독자 정보 목록.

    Note:
        현재 미구현 상태이며, send() 메서드는 항상 True를 반환합니다.
    """

    def __init__(self, vapid_private_key: str, vapid_claims: Dict[str, str]) -> None:
        """WebPushNotificationChannel 인스턴스를 초기화합니다.

        Args:
            vapid_private_key: VAPID 개인 키.
            vapid_claims: VAPID 클레임 딕셔너리.
        """
        self.vapid_private_key = vapid_private_key
        self.vapid_claims = vapid_claims
        self.subscriptions: List[Dict[str, Any]] = []

    async def send(self, request: ApprovalRequest) -> bool:
        """웹 푸시 알림을 전송합니다 (미구현).

        Args:
            request: 전송할 승인 요청 객체.

        Returns:
            항상 True (미구현).
        """
        # 구현 예정 (pywebpush 라이브러리 사용)
        logger.info(f"웹 푸시 알림 (미구현): {request.request_id}")
        return True


class NotificationService:
    """다중 채널 통합 알림 서비스.

    여러 알림 채널(이메일, Slack, 웹 푸시 등)을 등록하고 관리하며,
    승인 요청 발생 시 우선순위에 따라 적절한 채널로 알림을 전송합니다.

    Attributes:
        channels: 등록된 알림 채널 딕셔너리 (이름 -> 채널).

    Example:
        >>> service = NotificationService()
        >>> await service.initialize()  # 환경변수에서 채널 설정 로드
        >>> service.register_channel("custom", CustomChannel())
        >>> await service.send_approval_notification(request)
    """

    def __init__(self) -> None:
        """NotificationService 인스턴스를 초기화합니다."""
        self.channels: Dict[str, NotificationChannel] = {}
        self._initialized = False

    async def initialize(self) -> None:
        """알림 서비스를 초기화합니다.

        환경변수에서 알림 채널 설정을 로드하고 활성화합니다.

        환경변수:
            SLACK_WEBHOOK_URL: Slack 웹훅 URL (설정 시 Slack 채널 활성화)
            SMTP_HOST: SMTP 서버 호스트 (설정 시 이메일 채널 활성화)
            SMTP_PORT: SMTP 서버 포트 (기본: 587)
            SMTP_USERNAME: SMTP 인증 사용자명
            SMTP_PASSWORD: SMTP 인증 비밀번호
            FROM_EMAIL: 발신자 이메일
            TO_EMAILS: 수신자 이메일 (쉼표 구분)
        """
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

    async def shutdown(self) -> None:
        """서비스 종료"""
        self.channels.clear()
        self._initialized = False

    async def send_approval_notification(self, request: ApprovalRequest) -> None:
        """모든 채널로 승인 알림 전송"""
        if not self._initialized:
            logger.warning("알림 서비스가 초기화되지 않았습니다")
            return

        # 우선순위별 채널 선택
        channels_to_use: List[str]
        if request.priority == "critical":
            # 모든 채널로 전송
            channels_to_use = list(self.channels.keys())
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

    def register_channel(self, name: str, channel: NotificationChannel) -> None:
        """알림 채널 등록"""
        self.channels[name] = channel
        logger.info(f"알림 채널 등록: {name}")

    def unregister_channel(self, name: str) -> None:
        """알림 채널 제거"""
        if name in self.channels:
            del self.channels[name]
            logger.info(f"알림 채널 제거: {name}")
