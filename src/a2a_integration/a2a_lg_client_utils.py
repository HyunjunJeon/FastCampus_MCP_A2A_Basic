"""A2A 클라이언트 유틸리티 모듈.

A2A 프로토콜 표준 클라이언트를 생성하고 관리하는 유틸리티를 제공합니다.

주요 기능:
    - AgentCard 자동 조회 및 해석
    - 다중 전송 프로토콜 지원 (JSON-RPC, HTTP+JSON, gRPC)
    - 스트리밍 응답 처리 및 증분 병합
    - DataPart(JSON) 자동 수집 및 병합
    - 클라이언트 선호도 협상
    - 출력 모드 제한
"""

from typing import Any
from a2a.types import AgentCard, Message, Role, TransportProtocol, DataPart, Part
from a2a.client import A2ACardResolver, ClientConfig, ClientFactory, A2AClientError
from a2a.client.helpers import create_text_message_object
from uuid import uuid4
from src.utils.logging_config import get_logger
from src.utils.http_client import http_client

logger = get_logger(__name__)


class A2AClientManager:
    """A2A 표준 클라이언트 매니저.

    A2A 에이전트와 통신하기 위한 클라이언트를 생성하고 관리합니다.
    컨텍스트 매니저 패턴을 지원하여 자동 초기화 및 종료가 가능합니다.

    주요 기능:
        - AgentCard 자동 조회 및 해석
        - 다중 전송 프로토콜 협상 (JSON-RPC, HTTP+JSON, gRPC)
        - 스트리밍 응답 처리 및 증분 병합
        - DataPart(JSON) 자동 수집
        - 중복 제거 및 텍스트 병합

    텍스트 쿼리 (send_query):
        스트리밍 이벤트의 텍스트 파트를 증분 병합하여 중복 없이 출력합니다.

    JSON 쿼리 (send_data):
        - 텍스트 파트: 진행 로그 및 에이전트 텍스트를 증분 출력
        - DataPart: 응답 전체에서 발견된 모든 JSON을 수집하여 리스트로 반환
          (툴 호출 중간 결과 및 최종 구조화 결과 포함)

    중복 방지 정책:
        스트리밍이 없을 때만 최종 텍스트를 1회 출력합니다.
        스트리밍이 있었다면 최종 텍스트에만 존재하는 추가 부분만 출력합니다.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        streaming: bool = True,
        polling: bool = False,
        use_client_preference: bool = False,
        accepted_output_modes: list[str] | None = None,
        supported_transports: list[TransportProtocol] | None = None,
    ):
        """A2A 클라이언트 매니저를 초기화합니다.

        Args:
            base_url: A2A 서버의 기본 URL.
            streaming: 스트리밍 모드 활성화 여부 (기본: True).
            polling: 폴링 모드 활성화 여부 (기본: False).
            use_client_preference: 클라이언트가 선호하는 전송 프로토콜을 우선 사용할지 여부.
                True이면 supported_transports 리스트 순서대로 시도합니다.
            accepted_output_modes: 수락할 출력 모드 리스트.
                None이면 모든 모드를 수락합니다.
            supported_transports: 지원할 전송 프로토콜 리스트.
                None이면 JSON-RPC, HTTP+JSON, gRPC 순서로 시도합니다.

        Examples:
            기본 사용:
                >>> async with A2AClientManager("http://localhost:8080") as client:
                ...     result = await client.send_query("안녕하세요")

            gRPC 우선 사용:
                >>> manager = A2AClientManager(
                ...     base_url="http://localhost:8080",
                ...     use_client_preference=True,
                ...     supported_transports=[TransportProtocol.grpc, TransportProtocol.jsonrpc],
                ... )
        """
        self.base_url = base_url
        self.streaming = streaming
        self.polling = polling
        self.use_client_preference = use_client_preference
        self.accepted_output_modes = accepted_output_modes or []
        self.supported_transports = supported_transports
        self.client = None
        self.agent_card: AgentCard | None = None
        self._httpx_client = None

    async def __aenter__(self):
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def initialize(self) -> "A2AClientManager":
        """A2A 클라이언트를 초기화합니다.

        원격 서버에서 AgentCard를 조회하고 적절한 전송 프로토콜을 선택하여
        실제 통신 클라이언트를 생성합니다.

        Returns:
            초기화된 A2AClientManager 인스턴스 (self).

        Raises:
            httpx.HTTPError: AgentCard 조회 실패 시.
            A2AClientError: 클라이언트 생성 실패 시.

        Note:
            컨텍스트 매니저 (async with)를 사용하면 자동으로 호출됩니다.
        """
        # 공통 HTTP 클라이언트 세션을 사용해 Agent Card를 1회 조회
        resolver = A2ACardResolver(
            httpx_client=http_client,
            base_url=self.base_url,
        )
        self.agent_card: AgentCard = await resolver.get_agent_card()
        
        # A2A SDK 0.3.11 ClientConfig 구성
        config_kwargs = {
            "streaming": self.streaming,
            "supported_transports": self.supported_transports or [
                TransportProtocol.jsonrpc,  # JSON-RPC 2.0 기본 프로토콜
                TransportProtocol.http_json,  # RESTful HTTP+JSON
                TransportProtocol.grpc,  # gRPC (A2A SDK 0.3.11+)
            ],
        }
        
        if self.polling:
            config_kwargs["polling"] = self.polling
        if self.use_client_preference:
            config_kwargs["use_client_preference"] = self.use_client_preference
        if self.accepted_output_modes:
            config_kwargs["accepted_output_modes"] = self.accepted_output_modes
        
        config = ClientConfig(**config_kwargs)
        factory = ClientFactory(config=config)
        self.client = factory.create(card=self.agent_card)
        return self

    async def get_agent_card(self) -> AgentCard:
        """초기화 시 획득한 AgentCard를 반환합니다.

        Returns:
            AgentCard 인스턴스.

        Raises:
            RuntimeError: 초기화되지 않은 상태에서 호출 시.
        """
        if self.agent_card is None:
            raise RuntimeError("클라이언트가 초기화되지 않았습니다. initialize()를 먼저 호출하세요.")
        return self.agent_card

    async def close(self):
        """내부 HTTP 클라이언트를 정리합니다.

        Note:
            컨텍스트 매니저 (async with)를 사용하면 자동으로 호출됩니다.
        """
        if self._httpx_client:
            await self._httpx_client.aclose()

    def get_agent_info(self) -> dict[str, Any]:
        """에이전트 카드의 요약 정보를 딕셔너리로 반환합니다.

        UI 표시나 로깅용으로 사용할 수 있는 간단한 메타데이터를 제공합니다.

        Returns:
            에이전트 정보를 담은 딕셔너리. 포함 필드:
                - name: 에이전트 이름
                - description: 에이전트 설명
                - url: 서비스 URL
                - capabilities: 지원 기능 (streaming, push_notifications 등)
                - default_input_modes: 기본 입력 모드
                - default_output_modes: 기본 출력 모드
                - skills: 스킬 목록 (name, description)
        """
        return {
            "name": self.agent_card.name,
            "description": self.agent_card.description,
            "url": self.agent_card.url,
            "capabilities": self.agent_card.capabilities.model_dump(),
            "default_input_modes": self.agent_card.default_input_modes,
            "default_output_modes": self.agent_card.default_output_modes,
            "skills": [
                {"name": skill.name, "description": skill.description}
                for skill in self.agent_card.skills
            ],
        }

    async def send_query(self, user_query: str) -> str:
        """텍스트 질의를 에이전트에게 전송하고 응답을 반환합니다.

        스트리밍 이벤트의 텍스트 파트를 증분 병합하여 중복 없이 최종 응답을 구성합니다.

        Args:
            user_query: 에이전트에게 전송할 텍스트 질의.

        Returns:
            에이전트의 최종 응답 텍스트.

        Raises:
            RuntimeError: 클라이언트가 초기화되지 않은 경우.
            A2AClientError: 통신 오류 발생 시.
        """
        if not self.client:
            raise RuntimeError("클라이언트가 초기화되지 않았습니다. initialize()를 먼저 호출하세요.")
        message: Message = create_text_message_object(role=Role.user, content=user_query)
        response_text = ""

        async for event in self.client.send_message(message):
            had_part = False
            for text_content in self._iter_texts_from_event(event):
                had_part = True
                if not text_content:
                    continue
                response_text = self._merge_incremental_text(response_text, text_content)
            if not had_part:
                # 단일 텍스트만 추출도 지원
                text_content = self._extract_text_from_event(event)
                if text_content:
                    response_text = self._merge_incremental_text(response_text, text_content)

        return response_text.strip()

    async def send_data(self, data: dict[str, Any]) -> Any:
        """JSON 데이터를 DataPart로 전송하고 모든 DataPart 응답을 수집합니다.

        Args:   
            data: 전송할 JSON 딕셔너리.

        Returns:
            응답에서 발견된 모든 `DataPart.data` 딕셔너리의 리스트.
            (도구 호출 중간 결과 + 최종 구조화 결과 포함)

        Raises:
            A2AClientError: 클라이언트 미초기화 시.
            ValueError: 응답에서 `DataPart`를 하나도 찾지 못한 경우.
        """
        if not self.client:
            raise A2AClientError("클라이언트가 초기화되지 않았습니다. initialize()를 먼저 호출하세요.")

        # DataPart 를 포함한 Message 구성
        message = Message(
            role=Role.user,
            parts=[Part(root=DataPart(data=data))],
            message_id=str(uuid4()),
        )
        

        response_text = ""
        final_artifact_texts: list[str] = []
        collected_data_parts: list[dict[str, Any]] = []

        async for event in self.client.send_message(message):
            # 1) 스트리밍/중간 업데이트 텍스트 누적 및 델타 로그 (여러 파트 분리 처리)
            had_text = False
            for text_content in self._iter_texts_from_event(event):
                had_text = True
                new_text = self._merge_incremental_text(response_text, text_content)
                delta = self._compute_delta(response_text, new_text)
                if delta:
                    logger.debug(delta)
                response_text = new_text
            if not had_text:
                # 호환성: 단일 텍스트 추출 경로도 유지
                text_content = self._extract_text_from_event(event)
                if text_content:
                    new_text = self._merge_incremental_text(response_text, text_content)
                    delta = self._compute_delta(response_text, new_text)
                    if delta:
                        logger.debug(delta)
                    response_text = new_text

            # 2) DataPart(JSON) 추출
            for data_obj in self._iter_data_from_event(event):
                # heartbeat 형태의 DataPart는 수집/로깅에서 제외하여 로그 스팸과 메모리 사용을 줄인다
                try:
                    if isinstance(data_obj, dict) and ("heartbeat" in data_obj):
                        continue
                except Exception:
                    pass

                collected_data_parts.append(data_obj)
                try:
                    logger.debug(f"A2A DataPart 수신: keys={list(data_obj.keys())}")
                except Exception:
                    pass

            # 3) 최종 아티팩트의 텍스트 별도 추적(중복 억제 판단용) - 여러 파트 지원
            if isinstance(event, tuple) and len(event) >= 1:
                task = event[0]
                if hasattr(task, "artifacts") and task.artifacts:
                    for artifact in task.artifacts:
                        for part in getattr(artifact, "parts", []) or []:
                            root = getattr(part, "root", None)
                            if (
                                getattr(root, "kind", None) == "text"
                                and isinstance(getattr(root, "text", None), str)
                            ):
                                final_artifact_texts.append(root.text)

        # 4) 최종 아티팩트 텍스트 출력 정책
        #    - 기본: 스트리밍 텍스트만 로그로 출력
        #    - 스트리밍이 전혀 없고 최종 아티팩트만 있는 경우: 최종 텍스트를 보강 출력하도록 허용
        sanitized_stream = response_text.strip()
        sanitized_final_joined = "".join(final_artifact_texts) or "".strip()
        if sanitized_final_joined and not sanitized_stream:
            # 스트리밍이 없었다면 최종 텍스트를 한 번만 출력 (로그 레벨은 debug로 낮춤)
            logger.debug(sanitized_final_joined)
        elif sanitized_final_joined and sanitized_final_joined != sanitized_stream:
            # 스트리밍이 있었더라도, 최종 텍스트에 추가분이 있으면 그 추가분만 1회 출력
            tail = self._compute_delta(sanitized_stream, sanitized_final_joined).strip()
            if tail:
                logger.debug(tail)
        if not collected_data_parts:
            raise ValueError("에이전트 응답에서 DataPart(JSON)를 찾지 못했습니다.")

        return collected_data_parts

    async def send_data_merged(self, data: dict[str, Any], merge_mode: str = "smart") -> dict[str, Any]:
        """JSON 데이터를 전송하고 모든 DataPart 응답을 병합하여 반환합니다.

        Args:
            data: 전송할 JSON 딕셔너리.
            merge_mode: 병합 전략 ('smart', 'last', 'append' 중 하나).
                - 'smart': 딥 머지 + 리스트는 키 기반 고유 추가 (기본값, 권장)
                - 'last': 마지막 값 우선 (얕은 덮어쓰기)
                - 'append': 리스트는 이어붙이고 중복 제거, 스칼라는 마지막 값 우선

        Returns:
            병합된 단일 딕셔너리 결과.

        Note:
            여러 DataPart를 개별적으로 처리하려면 send_data()를 사용하고,
            즉시 병합된 단일 결과가 필요하면 이 메서드를 사용합니다.
        """
        parts = await self.send_data(data)
        return self._merge_data_parts(parts, mode=merge_mode)

    def _merge_data_parts(self, parts: list[dict[str, Any]], mode: str = "smart") -> dict[str, Any]:
        """다수의 DataPart 딕셔너리 리스트를 단일 딕셔너리로 병합합니다.

        Args:
            parts: 병합할 DataPart 딕셔너리 리스트.
            mode: 병합 전략 ('smart', 'last', 'append').

        Returns:
            병합된 단일 딕셔너리.

        병합 규칙:
            - smart: dict는 재귀 병합, 리스트는 순서 유지 + 중복 제거, 스칼라는 마지막 값 우선
            - last: 얕은 덮어쓰기 (뒤의 dict가 앞을 덮음)
            - append: 리스트는 이어붙인 뒤 중복 제거, 스칼라는 마지막 값 우선, dict는 얕게 병합
        """
        if not isinstance(parts, list):
            return {}

        if mode not in {"smart", "last", "append"}:
            mode = "smart"

        result: dict[str, Any] = {}

        def is_simple_scalar(value: Any) -> bool:
            return isinstance(value, (str, int, float, bool)) or value is None

        def dedup_list(items: list[Any]) -> list[Any]:
            seen: set[str] = set()
            deduped: list[Any] = []
            for item in items:
                try:
                    key = (
                        str(item)
                        if is_simple_scalar(item)
                        else __import__("json").dumps(item, sort_keys=True, default=str)
                    )
                except Exception:
                    key = str(item)
                if key in seen:
                    continue
                seen.add(key)
                deduped.append(item)
            return deduped

        def deep_merge_dict(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
            merged: dict[str, Any] = dict(a)
            for k, v in b.items():
                if k not in merged:
                    merged[k] = v
                    continue
                prev = merged[k]
                if isinstance(prev, dict) and isinstance(v, dict):
                    merged[k] = deep_merge_dict(prev, v)
                elif isinstance(prev, list) and isinstance(v, list):
                    merged[k] = dedup_list(prev + v)
                else:
                    # 스칼라/타입 불일치: b가 우선
                    merged[k] = v
            return merged

        for part in parts:
            if not isinstance(part, dict):
                continue
            if mode == "last":
                result.update(part)
                continue
            if mode == "append":
                # 얕은 병합 + 리스트는 이어붙이고 dedup
                for k, v in part.items():
                    if k not in result:
                        result[k] = v
                        continue
                    if isinstance(result[k], list) and isinstance(v, list):
                        result[k] = dedup_list(result[k] + v)
                    else:
                        result[k] = v
                continue
            # smart (기본)
            result = deep_merge_dict(result, part)

        return result

    async def respond_to_input_required(
        self,
        *,
        context_id: str,
        task_id: str,
        resume_value: Any,
    ) -> str:
        """input-required 상태의 작업에 사용자 응답을 전송하여 재개합니다.

        Args:
            context_id: 재개할 작업의 컨텍스트 ID.
            task_id: 재개할 작업의 태스크 ID.
            resume_value: 사용자 응답 값 (텍스트 또는 JSON).

        Returns:
            재개 후 에이전트의 최종 응답 텍스트.

        Raises:
            A2AClientError: 클라이언트가 초기화되지 않았거나 통신 오류 발생 시.

        Note:
            동일한 context_id와 task_id를 유지하여 서버가 기존 작업을 이어받도록 합니다.
            재개 값은 DataPart의 {"resume": <value>} 형태로 전달됩니다.
        """
        if not self.client:
            raise A2AClientError("클라이언트가 초기화되지 않았습니다. initialize()를 먼저 호출하세요.")

        # 우선 DataPart 형태로 전달 (서버가 resume 키를 우선적으로 인식하도록)
        message = Message(
            role=Role.user,
            parts=[Part(root=DataPart(data={"resume": resume_value}))],
            message_id=str(uuid4()),
            context_id=context_id,
            task_id=task_id,
        )

        response_text = ""
        async for event in self.client.send_message(message):
            had_part = False
            for text_content in self._iter_texts_from_event(event):
                had_part = True
                if not text_content:
                    continue
                response_text = self._merge_incremental_text(response_text, text_content)
            if not had_part:
                text_content = self._extract_text_from_event(event)
                if text_content:
                    response_text = self._merge_incremental_text(response_text, text_content)

        return response_text.strip()

    def _extract_text_from_event(self, event) -> str:
        if not isinstance(event, tuple) or len(event) < 1:
            return ""
        task = event[0]
        if hasattr(task, "artifacts") and task.artifacts:
            for artifact in task.artifacts:
                if hasattr(artifact, "parts") and artifact.parts:
                    for part in artifact.parts:
                        if hasattr(part, "root") and hasattr(part.root, "text"):
                            return part.root.text
        elif hasattr(task, "history") and task.history:
            last_message = task.history[-1]
            if (
                hasattr(last_message, "role")
                and last_message.role.value == "agent"
                and hasattr(last_message, "parts")
                and last_message.parts
            ):
                for part in last_message.parts:
                    if hasattr(part, "root") and hasattr(part.root, "text"):
                        return part.root.text
        return ""

    def _iter_texts_from_event(self, event):
        """이벤트에서 모든 텍스트 파트를 순서대로 생성합니다.

        - 우선 `task.artifacts`를 순회하며 각 `artifact.parts` 중 `kind == "text"`를 모두 yield
        - artifacts가 없으면 `task.history[-1].parts`에서 `kind == "text"`를 yield
        - 최종 아티팩트(name == "result")의 텍스트도 포함합니다. 스트리밍이 없고 최종만 존재하는 경우를 위해서입니다.
        """
        if not isinstance(event, tuple) or len(event) < 1:
            return
        task = event[0]
        if hasattr(task, "artifacts") and task.artifacts:
            for artifact in task.artifacts:
                if hasattr(artifact, "parts") and artifact.parts:
                    for part in artifact.parts:
                        root = getattr(part, "root", None)
                        text = getattr(root, "text", None) if root is not None else None
                        if isinstance(text, str):
                            yield text
            return
        if hasattr(task, "history") and task.history:
            last_message = task.history[-1]
            if (
                hasattr(last_message, "role")
                and last_message.role.value == "agent"
                and hasattr(last_message, "parts")
                and last_message.parts
            ):
                for part in last_message.parts:
                    root = getattr(part, "root", None)
                    text = getattr(root, "text", None) if root is not None else None
                    if isinstance(text, str):
                        yield text

    def _merge_incremental_text(self, existing: str, new: str) -> str:
        """증분 텍스트 병합 유틸리티.

        스트리밍 텍스트와 최종 아티팩트가 섞여 올 때 중복 없이 병합합니다.
        - 최종 아티팩트가 전체 텍스트를 재송신: new가 existing 접두 ⇒ new로 교체
        - 델타가 증가분만 올 때: 접미사/접두사 최대 중첩 길이를 찾아 증가분만 추가
        - 불일치 시: 가장 긴 접미사-접두사 중첩 기준으로 이어붙임
        """
        if not existing:
            return new
        if new.startswith(existing):
            return new
        if existing.startswith(new):
            return existing
        max_overlap = min(len(existing), len(new))
        overlap = 0
        for k in range(max_overlap, 0, -1):
            if existing.endswith(new[:k]):
                overlap = k
                break
        return existing + new[overlap:]

    def _compute_delta(self, old: str, new: str) -> str:
        """증분 델타 계산 유틸리티.

        기존 누적 텍스트(old)와 신규 텍스트(new)의 겹치는 접두/접미를 고려해
        실제로 추가된 부분만 반환합니다. 로그/스트리밍 출력량 절감을 위해 사용합니다.
        """
        if new.startswith(old):
            return new[len(old):]
        max_overlap = min(len(old), len(new))
        for k in range(max_overlap, 0, -1):
            if old.endswith(new[:k]):
                return new[k:]
        return new

    def _extract_data_from_event(self, event) -> dict[str, Any] | None:
        """이벤트에서 DataPart(JSON)를 추출하여 반환합니다.

        스트리밍 아티팩트 혹은 최종 히스토리 메시지에서 `kind == "data"` 인 파트를 탐색합니다.
        발견 시 해당 `data` 딕셔너리를 반환하고, 없으면 None을 반환합니다.
        """
        if not isinstance(event, tuple) or len(event) < 1:
            return None
        task = event[0]

        # 아티팩트 내 DataPart 우선 탐색
        if hasattr(task, "artifacts") and task.artifacts:
            for artifact in task.artifacts:
                if hasattr(artifact, "parts") and artifact.parts:
                    for part in artifact.parts:
                        root = getattr(part, "root", None)
                        if root is not None and getattr(root, "kind", None) == "data":
                            return getattr(root, "data", None)

        # 마지막 에이전트 메시지에서 DataPart 탐색
        if hasattr(task, "history") and task.history:
            last_message = task.history[-1]
            if (
                hasattr(last_message, "role")
                and last_message.role.value == "agent"
                and hasattr(last_message, "parts")
                and last_message.parts
            ):
                for part in last_message.parts:
                    root = getattr(part, "root", None)
                    if root is not None and getattr(root, "kind", None) == "data":
                        return getattr(root, "data", None)

        return None

    def _iter_data_from_event(self, event):
        """이벤트에서 모든 DataPart(JSON)의 data 딕셔너리를 순서대로 생성합니다.

        - artifacts → parts에서 `kind == "data"` 인 모든 파트를 순회하여 data를 yield
        - artifacts가 없을 경우, history의 마지막 메시지 parts 중 `kind == "data"`를 yield
        - 일부 런타임은 다수의 DataPart를 한 이벤트에 포함할 수 있으므로, 단일 반환이 아닌 제너레이터로 제공
        """
        if not isinstance(event, tuple) or len(event) < 1:
            return
        task = event[0]
        if hasattr(task, "artifacts") and task.artifacts:
            for artifact in task.artifacts:
                if hasattr(artifact, "parts") and artifact.parts:
                    for part in artifact.parts:
                        root = getattr(part, "root", None)
                        if root is not None and getattr(root, "kind", None) == "data":
                            data_obj = getattr(root, "data", None)
                            if isinstance(data_obj, dict):
                                yield data_obj

        elif hasattr(task, "history") and task.history:
            last_message = task.history[-1]
            if (
                hasattr(last_message, "role")
                and last_message.role.value == "agent"
                and hasattr(last_message, "parts")
                and last_message.parts
            ):
                for part in last_message.parts:
                    root = getattr(part, "root", None)
                    if root is not None and getattr(root, "kind", None) == "data":
                        data_obj = getattr(root, "data", None)
                        if isinstance(data_obj, dict):
                            yield data_obj


async def query_a2a_agent(
    user_query: str, 
    base_url: str = "http://localhost:8080",
) -> str:
    async with A2AClientManager(base_url=base_url) as manager:
        return await manager.send_query(user_query)

async def query_data_a2a_agent(
    data: dict[str, Any],
    base_url: str = "http://localhost:8080",
) -> dict[str, Any]:
    async with A2AClientManager(base_url=base_url) as manager:
        return await manager.send_data(data)