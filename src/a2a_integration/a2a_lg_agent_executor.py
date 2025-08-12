"""
LangGraph Agent를 A2A 프로토콜로 래핑하는 AgentExecutor 구현
공식 A2A 0.3.0 패턴을 따름
"""

from typing import Any, Callable
import json
from langgraph.graph.state import CompiledStateGraph
from langchain_core.messages import AIMessage, HumanMessage, convert_to_messages, filter_messages
from src.utils.logging_config import get_logger

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import InternalError, Part, TaskState, TextPart, DataPart
from a2a.utils import new_agent_text_message, new_task, get_data_parts
from a2a.utils.errors import ServerError, TaskNotFoundError
from langgraph.types import Command

logger = get_logger(__name__)


class LangGraphWrappedA2AExecutor(AgentExecutor):
    """
    LangGraph Agent를 A2A 프로토콜로 Wrapping
    """

    def __init__(
        self,
        graph: CompiledStateGraph,
        result_extractor: Callable[[dict[str, Any]], str] | None = None,
    ):
        self.graph = graph
        self._extract_result_text = result_extractor or self._default_extract_text

    def _get_graph_input_field_names(self) -> set[str]:
        """그래프의 입력 스키마에서 기대하는 필드 이름 집합을 추출한다.

        - get_input_schema() → Pydantic 모델/TypedDict/dict 등 지원
        - input_schema 속성도 시도
        - 실패 시 빈 집합 반환
        """
        schema: Any | None = None
        try:
            getter = getattr(self.graph, "get_input_schema", None)
            if callable(getter):
                schema = getter()
            elif hasattr(self.graph, "input_schema"):
                schema = getattr(self.graph, "input_schema")
        except Exception:
            schema = None

        field_names: set[str] = set()
        if schema is None:
            return field_names

        # Pydantic v2 모델 타입/인스턴스 처리
        try:
            from pydantic import BaseModel as _PDBase

            if isinstance(schema, type) and issubclass(schema, _PDBase):
                return set(getattr(schema, "model_fields", {}).keys())
            if isinstance(schema, _PDBase):
                return set(getattr(schema, "model_fields", {}).keys())
        except Exception:
            pass

        # TypedDict or dataclass-like: __annotations__ 기반
        try:
            annotations = getattr(schema, "__annotations__", None)
            if isinstance(annotations, dict):
                field_names.update(annotations.keys())
        except Exception:
            pass

        # dict 스키마
        if isinstance(schema, dict):
            field_names.update(schema.keys())

        return field_names

    def _looks_like_messages_field(self, name: str) -> bool:
        """필드명이 메시지 배열을 의미하는지 휴리스틱으로 판단."""
        return "messages" in (name or "").lower()

    def _convert_to_lc_messages_if_needed(self, value: Any) -> Any:
        """list 형태의 메시지 유사 구조를 LangChain 메시지로 변환.

        - dict 리스트나 OpenAI 포맷 등이 들어올 수 있으므로 convert_to_messages 시도
        - 이미 LC 메시지인 경우는 그대로 통과
        - 실패 시 원본 반환
        """
        try:
            if isinstance(value, list) and value:
                return convert_to_messages(value)
        except Exception:
            return value
        return value

    def _build_graph_input_from_payload(self, payload: dict[str, Any] | None, query: str | None) -> dict[str, Any]:
        """그래프 입력 스키마를 반영해 DataPart payload를 범용적으로 매핑한다.

        우선순위:
        1) 그래프 입력 스키마(get_input_schema/input_schema)로 기대 필드 확인
        2) payload 내 해당 키 존재 시 그대로 사용하되, messages 계열은 LC 메시지로 변환
        3) 미존재 시 기본 HumanMessage(query)를 해당 messages 필드에 주입
        4) 스키마 정보가 없으면 기존 관용: payload.messages 또는 conversation.messages → messages 변환
           둘 다 없으면 {"messages": [HumanMessage(query)]}
        """
        expected_fields = self._get_graph_input_field_names()
        base_messages = [HumanMessage(content=str(query))] if (query and str(query)) else []
        if not isinstance(payload, dict):
            payload = {}

        # 스키마가 정의된 경우: 스키마에 맞춰 조립
        if expected_fields:
            graph_input: dict[str, Any] = {}
            # 1) 스키마 필드 채우기
            for field in expected_fields:
                if field in payload:
                    value = payload[field]
                    if self._looks_like_messages_field(field):
                        graph_input[field] = self._convert_to_lc_messages_if_needed(value)
                    else:
                        graph_input[field] = value
                else:
                    if self._looks_like_messages_field(field) and base_messages:
                        graph_input[field] = base_messages

            # 2) payload 잔여 키 병합(스키마 외 키는 그대로 통과)
            for k, v in payload.items():
                if k in graph_input:
                    continue
                if self._looks_like_messages_field(k):
                    graph_input[k] = self._convert_to_lc_messages_if_needed(v)
                else:
                    graph_input[k] = v
            return graph_input

        # 스키마가 없는 경우: 관용적 처리
        input_messages = (
            payload.get("messages")
            or (payload.get("conversation", {}) or {}).get("messages")
        )
        if isinstance(input_messages, list) and input_messages:
            return {"messages": self._convert_to_lc_messages_if_needed(input_messages), **{k: v for k, v in payload.items() if k not in ("messages",)}}
        return {"messages": base_messages or [HumanMessage(content="")], **payload}

    def _default_extract_text(self, result: dict[str, Any]) -> str:
        """LangGraph astream 청크에서 사람이 읽을 수 있는 텍스트를 최대한 복원.

        우선순위:
        1) (중첩 포함) messages 리스트를 찾아 마지막 AI 메시지의 텍스트 추출
        2) 일반 키(delta/content/text/output_text) 추출
        3) 메시지/청크 객체의 content/text 속성 사용
        """
        if not result:
            return ""

        # 1차: 중첩된 구조에서 messages 리스트를 찾아서 AI 텍스트 추출
        try:
            messages = self._find_messages_list(result)
            if messages:
                text = self._extract_text_from_messages(messages)
                if isinstance(text, str) and text.strip():
                    return text.strip()
        except Exception:
            pass

        def extract_text_from_content(content: Any) -> str:
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                pieces: list[str] = []
                for part in content:
                    if isinstance(part, dict):
                        # 일반 텍스트 필드
                        if isinstance(part.get("text"), str):
                            pieces.append(part["text"])
                        # 출력 전용 텍스트 타입
                        elif part.get("type") in {"output_text", "text"} and isinstance(part.get("text"), str):
                            pieces.append(part["text"]) 
                        # 일부 라이브러리는 content에 텍스트를 실을 수 있음
                        elif isinstance(part.get("content"), str):
                            pieces.append(part["content"]) 
                    else:
                        text_attr = getattr(part, "text", None)
                        if isinstance(text_attr, str):
                            pieces.append(text_attr)
                return "".join(pieces)
            return ""

        def collect_strings(value: Any, limit: int = 5) -> list[str]:
            """중첩 구조에서 의미 있는 문자열들을 수집 (상한 제한)."""
            results: list[str] = []
            if not value:
                return results
            if isinstance(value, str):
                return [value]
            if isinstance(value, dict):
                # 우선순위 키 먼저 확인
                for key in ("text", "content", "output_text", "delta"):
                    v = value.get(key)
                    if isinstance(v, str) and v:
                        results.append(v)
                # 그 외 키들도 순회
                for v in value.values():
                    results.extend(collect_strings(v, limit))
                    if len(results) >= limit:
                        break
            elif isinstance(value, list):
                for item in value:
                    results.extend(collect_strings(item, limit))
                    if len(results) >= limit:
                        break
            else:
                # 객체의 content/text 속성 시도
                for attr in ("content", "text"):
                    if hasattr(value, attr):
                        v = getattr(value, attr)
                        if isinstance(v, str) and v:
                            results.append(v)
                        else:
                            results.extend(collect_strings(v, limit))
            return results

        # Case 1: dict-like with messages/output/response
        messages: Any | None = None
        if isinstance(result, dict):
            if isinstance(result.get("messages"), list):
                messages = result["messages"]
            elif isinstance(result.get("output"), list):
                messages = result["output"]
            elif isinstance(result.get("response"), list):
                messages = result["response"]

        if messages is not None:
            # Try direct content extraction from each message
            try:
                pieces: list[str] = []
                for msg in messages:
                    content = getattr(msg, "content", msg)
                    text = extract_text_from_content(content)
                    if text:
                        pieces.append(text)
                if pieces:
                    return "".join(pieces).strip()
            except Exception:
                pass

            # Fallback to filtering AIMessage instances
            try:
                filtered = filter_messages(messages, include_types=[AIMessage])
                if filtered:
                    last_ai = filtered[-1]
                    text = extract_text_from_content(getattr(last_ai, "content", ""))
                    if text:
                        return text.strip()
            except Exception:
                pass

        # Case 2: common textual keys in dict chunk
        if isinstance(result, dict):
            for key in ("delta", "content", "text", "output_text"):
                value = result.get(key)
                if isinstance(value, str) and value:
                    return value

        # Case 3: message-like object
        content_attr = getattr(result, "content", None)
        text_attr = getattr(result, "text", None)
        if isinstance(content_attr, str):
            return content_attr
        if isinstance(text_attr, str):
            return text_attr
        if content_attr is not None:
            text = extract_text_from_content(content_attr)
            if text:
                return text

        # 최종 완전 대체: 중첩 구조에서 문자열 수집 후 반환
        strings = collect_strings(result)
        if strings:
            return "\n".join([s for s in strings if isinstance(s, str) and s.strip()][:3]).strip()
        return ""

    def _extract_interrupt_payload(self, chunk: Any) -> Any | None:
        """스트림 청크에서 LangGraph interrupt 페이로드를 탐지 및 추출.

        LangGraph 문서 기준으로 인터럽트는 스트림에 `{"__interrupt__": (Interrupt(...), ...)}` 형태로 나타난다.
        구현체 간 차이를 고려하여 유연하게 값 추출을 시도한다.
        """
        try:
            if not isinstance(chunk, dict):
                return None
            intr = chunk.get("__interrupt__")
            if intr is None:
                return None
            # intr 는 보통 tuple/list 안에 Interrupt 객체가 들어있다.
            candidates = intr if isinstance(intr, (list, tuple)) else [intr]
            for item in candidates:
                # 1) 객체의 value 속성 시도
                value = getattr(item, "value", None)
                if value is not None:
                    return value
                # 2) dict 로 표현된 경우 value 키 시도
                if isinstance(item, dict) and "value" in item:
                    return item.get("value")
            # 3) 원시값 자체 반환
            return candidates[0] if candidates else True
        except Exception:
            return None

    def _extract_ai_text_for_stream(self, result: dict[str, Any]) -> str:
        """스트리밍 단계에서 사용할 AI 전용 텍스트 추출을 단순/견고하게 수행.

        - (중첩 포함) messages 리스트를 먼저 찾고, 마지막 AI 메시지의 텍스트만 반환
        - 도구 호출/툴 메시지 등 비-에이전트 텍스트는 배제하여 노이즈를 줄임
        - 실패 시 빈 문자열
        """
        try:
            if not isinstance(result, dict):
                return ""
            messages = self._find_messages_list(result)
            if not messages:
                return ""
            text = self._extract_text_from_messages(messages)
            return text or ""
        except Exception:
            return ""

    def _extract_structured_output(self, result: Any) -> dict[str, Any]:
        """그래프 최종 청크에서 구조화 가능한 핵심 필드만 안전하게 추출한다.

        - supervisor 서브그래프는 보통 {'supervisor_tools': {'notes': [...], 'research_brief': '...'}} 형태로 산출
        - 메시지 객체 등 비직렬화 가능한 값은 제외하고, 최소 필드만 반환
        - 허용 키: notes(list[str]), raw_notes(list[str]), research_brief(str), final_report(str)
        """
        allowed_keys: set[str] = {"notes", "raw_notes", "research_brief", "final_report"}

        def is_json_compat(value: Any) -> bool:
            if isinstance(value, (str, int, float, bool)) or value is None:
                return True
            if isinstance(value, list):
                return all(isinstance(x, (str, int, float, bool)) or x is None for x in value)
            if isinstance(value, dict):
                return all(isinstance(k, str) and is_json_compat(v) for k, v in value.items())
            return False

        extracted: dict[str, Any] = {}

        def try_assign(key: str, value: Any):
            if key not in allowed_keys:
                return
            if key in {"notes", "raw_notes"}:
                if isinstance(value, list):
                    # 리스트 평탄화 + 문자열만 보존
                    flattened: list[str] = []
                    for item in value:
                        if isinstance(item, str):
                            flattened.append(item)
                        elif isinstance(item, list):
                            flattened.extend([x for x in item if isinstance(x, str)])
                    if flattened:
                        extracted[key] = flattened
                return
            # 스칼라 문자열 위주 보존
            if isinstance(value, str) and value:
                extracted[key] = value

        def walk(obj: Any):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    try_assign(k, v)
                    walk(v)
            elif isinstance(obj, list):
                for item in obj:
                    walk(item)

        walk(result)

        # notes/raw_notes가 없고 research_brief만 있는 경우도 허용
        safe_extracted = {k: v for k, v in extracted.items() if is_json_compat(v)}
        return safe_extracted


    def _find_messages_list(self, result: dict[str, Any]) -> list[Any] | None:
        """청크(dict)에서 messages 리스트를 탐색해 반환.

        - 최상위 'messages'가 있으면 사용
        - 없으면 1단계 중첩(dict 값)에서 'messages'를 탐색
        - 그 외에는 None
        """
        if not isinstance(result, dict) or not result:
            return None
        if isinstance(result.get("messages"), list):
            return result.get("messages")
        # 1단계 중첩 탐색 (예: {'react_agent': {'messages': [...]}})
        for value in result.values():
            if isinstance(value, dict) and isinstance(value.get("messages"), list):
                return value.get("messages")
        return None

    def _extract_text_from_messages(self, messages: list[Any]) -> str:
        """메시지 리스트에서 마지막 AI 메시지의 텍스트를 간단/안전하게 추출.

        - 우선 `AIMessage`만 필터링해 마지막 항목의 content에서 텍스트 추출
        - content가 리스트인 경우 dict 파트의 'text'를 이어붙임
        - 실패 시 빈 문자열
        """
        try:
            filtered = filter_messages(messages, include_types=[AIMessage])
            if not filtered:
                return ""
            last_ai = filtered[-1]
            content = getattr(last_ai, "content", None)
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                pieces: list[str] = []
                for part in content:
                    if isinstance(part, dict) and isinstance(part.get("text"), str):
                        pieces.append(part["text"])
                    else:
                        text_attr = getattr(part, "text", None)
                        if isinstance(text_attr, str):
                            pieces.append(text_attr)
                return "".join(pieces)
            return ""
        except Exception:
            return ""

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        # NOTE: Validate 하지 않음 - 유저 질의는 없을 수도 있음(Text 로 보냈을 때만 있음 - get_user_input)
        query = context.get_user_input()
        logger.info(f"A2A Agent 요청 처리 시작 - get_user_input: {query}")
        # 클라이언트가 DataPart(JSON)로 보낸 입력 감지
        incoming_parts: list[Part] = []
        if context.message and getattr(context.message, "parts", None):
            try:
                incoming_parts = get_data_parts(context.message.parts)
            except Exception:
                incoming_parts = []
        # 태스크 확인 및 생성
        task = context.current_task
        if not task:
            task = new_task(context.message)
            await event_queue.enqueue_event(task)
        
        # 태스크 업데이트 준비
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        await updater.update_status(TaskState.submitted) # Submitted 상태로 변경
        try:
            # 그래프 입력 구성: JSON(DataPart) 이면 메시지 필드를 LangChain 메시지로 변환,
            # 아니면 기본 텍스트 입력을 안전한 기본 키들에 주입
            graph_input: dict[str, Any]
            if incoming_parts:
                try:
                    last_part = incoming_parts[-1]
                    # get_data_parts는 보통 dict 리스트를 반환한다. (docs: list[dict[str, Any]])
                    if isinstance(last_part, dict):
                        payload = last_part
                    else:
                        root = getattr(last_part, "root", None)
                        payload = getattr(root, "data", None)
                    logger.info(f"A2A Agent 요청 처리 시작 - DataPart payload: {payload}")
                    if isinstance(payload, dict) and payload:
                        graph_input = self._build_graph_input_from_payload(payload, query)
                    else:
                        graph_input = self._build_graph_input_from_payload({}, query)
                except Exception as e:
                    logger.warning(f"DataPart 파싱 실패, 기본 텍스트 입력으로 진행: {e}")
                    graph_input = self._build_graph_input_from_payload({}, query)
            else:
                graph_input = self._build_graph_input_from_payload({}, query)

            last_result: Any | None = None
            accumulated_text: str = ""
            await updater.start_work() # Working 상태로 변경
            logger.info(f"A2A Agent 요청 처리 시작 - LangGraph Input: {graph_input}")

            # 동일한 대화 쓰레드를 위해 thread_id 지정 (태스크 ID 기반 고정)
            thread_id = getattr(task, "id", None) or getattr(context, "task_id", "")
            config = {"configurable": {"thread_id": str(thread_id)}}

            # 재개 여부 판정: 이전 상태가 input-required 라면 resume 로직 적용
            is_resume = False
            try:
                task_status = getattr(task, "status", None)
                state_value = getattr(getattr(task_status, "state", None), "value", None) or getattr(task_status, "state", None)
                # state 가 Enum 이면 .value, 문자열이면 그대로 비교
                if str(state_value) in {"input-required", "input_required"}:
                    is_resume = True
            except Exception:
                is_resume = False

            # resume 값 추출 (텍스트가 우선, DataPart 에 resume/answer/user_input/value 키가 있으면 사용)
            resume_value: Any = None
            if is_resume:
                # DataPart 에서 찾기
                resume_keys = ("resume", "answer", "user_input", "value")
                payload = None
                if incoming_parts:
                    try:
                        payload = incoming_parts[-1] if isinstance(incoming_parts[-1], dict) else getattr(getattr(incoming_parts[-1], "root", None), "data", None)
                    except Exception:
                        payload = None
                if isinstance(payload, dict):
                    for k in resume_keys:
                        if k in payload and payload[k] is not None:
                            resume_value = payload[k]
                            break
                # 텍스트 질의 사용
                if resume_value is None and isinstance(query, str) and query.strip():
                    resume_value = query.strip()

            invoke_input: Any = Command(resume=resume_value) if is_resume else graph_input

            async for chunk in self.graph.astream(invoke_input, config=config):
                logger.info(f"A2A Agent 요청 처리 시작 - LangGraph Output: {chunk}")
                last_result = chunk

                # 0) 인터럽트 발생 감지 → input-required 로 전환하고 종료
                try:
                    interrupt_payload = self._extract_interrupt_payload(chunk)
                except Exception:
                    interrupt_payload = None
                if interrupt_payload is not None:
                    # 메시지 구성: payload 에 question/action 키가 있으면 우선 사용
                    try:
                        if isinstance(interrupt_payload, dict):
                            question = interrupt_payload.get("question") or interrupt_payload.get("action")
                            prompt_str = question or json.dumps(interrupt_payload, ensure_ascii=False)
                        else:
                            prompt_str = str(interrupt_payload)
                    except Exception:
                        prompt_str = "추가 입력이 필요합니다. 내용을 입력해 주세요."

                    await updater.update_status(
                        TaskState.input_required,
                        new_agent_text_message(prompt_str, task.context_id, task.id),
                        final=True,
                    )
                    return

                try:
                    partial_text = self._extract_ai_text_for_stream(chunk) or ""
                    if partial_text:
                        # 증가분 계산: 누적 텍스트의 접미사와 부분 텍스트의 중복을 제거하여 전송량 최소화
                        if accumulated_text and partial_text.startswith(accumulated_text):
                            delta = partial_text[len(accumulated_text):]
                        else:
                            # 일반적인 모델은 전체 누적 문자열을 내보내므로 위 분기에서 대부분 처리됨
                            # 그렇지 않은 경우 중복을 간단히 제거
                            common_prefix_len = 0
                            max_len = min(len(accumulated_text), len(partial_text))
                            while common_prefix_len < max_len and accumulated_text[common_prefix_len] == partial_text[common_prefix_len]:
                                common_prefix_len += 1
                            delta = partial_text[common_prefix_len:]

                        accumulated_text = partial_text
                        if delta:
                            await updater.update_status(
                                TaskState.working,
                                new_agent_text_message(delta, task.context_id, task.id),
                            )
                except Exception:
                    pass

            # 최종 결과는 마지막 스트림 청크에서만 추출 (중복 실행 방지)
            final_text = self._extract_result_text(last_result or {})
            if not final_text:
                final_text = accumulated_text or "결과 텍스트를 생성하지 못했습니다."

            # 최종 텍스트 아티팩트
            await updater.add_artifact(
                [Part(root=TextPart(text=final_text))]
            )

            # JSON(DataPart) 아티팩트도 함께 제공하여 DataPart 기반 클라이언트가 안전하게 파싱 가능하도록 한다
            try:
                response_payload: dict[str, Any] = {"text": final_text}
                await updater.add_artifact(
                    [Part(root=DataPart(data=response_payload))]
                )
            except Exception:
                pass

            # 구조화 가능한 결과(예: notes, research_brief)를 별도 DataPart로 제공
            try:
                structured_payload = self._extract_structured_output(last_result or {})
                if structured_payload:
                    await updater.add_artifact(
                        [Part(root=DataPart(data=structured_payload))]
                    )
            except Exception:
                # 구조 데이터가 직렬화 불가한 경우 무시하고 텍스트만 제공
                pass
            await updater.complete()

        except Exception as e:
            logger.error(f'A2A 실행 중 오류: {e}')
            # TaskStatus.message 는 Message 타입이어야 함
            error_message = new_agent_text_message(
                f"A2A 실행 중 오류: {e}", task.context_id, task.id
            )
            await updater.failed(message=error_message)
            raise ServerError(error=InternalError()) from e

    async def cancel(
        self,
        context: RequestContext,
        event_queue: EventQueue
    ) -> None:
        task = context.current_task
        if not task:
            raise ServerError(error=TaskNotFoundError())

        updater = TaskUpdater(event_queue, task.id, task.context_id)
        message = new_agent_text_message("사용자의 요청으로 작업이 취소되었습니다.", task.context_id, task.id)
        await event_queue.enqueue_event(message)
        await updater.cancel(message)
