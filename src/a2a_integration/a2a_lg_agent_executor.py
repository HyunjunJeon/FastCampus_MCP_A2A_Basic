"""
LangGraph Agent를 A2A 프로토콜로 래핑하는 AgentExecutor 구현
공식 A2A 0.3.0 패턴을 따름
"""

from datetime import datetime

from typing import Any, Callable
from langgraph.graph.state import CompiledStateGraph
from langchain_core.messages import AIMessage, HumanMessage, filter_messages
from src.utils.logging_config import get_logger

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import InternalError, InvalidParamsError, Part, TaskState, TextPart, UnsupportedOperationError
from a2a.utils import new_agent_text_message, new_task
from a2a.utils.errors import ServerError, TaskNotFoundError

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

    def _default_extract_text(self, result: dict[str, Any]) -> str:
        """LangGraph astream 청크에서 사람이 읽을 수 있는 텍스트를 최대한 복원.

        우선순위:
        1) result['messages'] 내 메시지들의 텍스트 합성
        2) 일반 키(delta/content/text/output_text) 추출
        3) 메시지/청크 객체의 content/text 속성 사용
        """
        if not result:
            return ""

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

    def _extract_ai_text_for_stream(self, result: dict[str, Any]) -> str:
        """스트리밍 단계에서 사용할 AI 전용 텍스트 추출.

        - 오직 `AIMessage`의 content에서만 텍스트를 추출해 도구(JSON) 출력 노이즈를 배제.
        - 기타 일반 키(delta/content/text 등)는 무시하여 중간 JSON이 전송되지 않도록 함.
        """
        if not isinstance(result, dict):
            return ""
        messages = result.get("messages")
        if isinstance(messages, list) and messages:
            try:
                # 마지막 AI 메시지 우선
                filtered = filter_messages(messages, include_types=[AIMessage])
                if filtered:
                    last_ai = filtered[-1]
                    content = getattr(last_ai, "content", None)
                    if isinstance(content, str):
                        return content
                    # 리스트 형태 content 처리
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
                # AI 메시지가 없으면 아무것도 보내지 않음
                return ""
            except Exception:
                return ""
        return ""

    def _validate_request(self, context: RequestContext) -> bool:
        if context.get_user_input() is None:
            return True
        return False

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        error = self._validate_request(context)
        if error:
            raise ServerError(error=InvalidParamsError())

        query = context.get_user_input()
        task = context.current_task
        if not task:
            task = new_task(context.message)
            await event_queue.enqueue_event(task)

        updater = TaskUpdater(event_queue, task.id, task.context_id)
        # 상태 변경은 기록하되, 텍스트 메시지는 보내지 않음(최종 결과에 섞이지 않도록)
        await updater.update_status(TaskState.submitted)

        try:
            logger.info(f"A2A Agent 요청 처리 시작 - 유저 질의:{query}")

            last_result: Any | None = None
            accumulated_text: str = ""
            # NOTE: 랭그래프를 astream 으로 실행
            # 작업 시작 상태만 갱신 (불필요한 상태 텍스트 전송 금지)
            await updater.update_status(TaskState.working)
            async for chunk in self.graph.astream({"messages": [HumanMessage(content=query)]}):
                last_result = chunk
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
                    # 중간 업데이트 실패는 치명적이지 않으므로 무시하고 계속 진행
                    pass

            # 최종 결과는 마지막 스트림 청크에서만 추출 (중복 실행 방지)
            final_text = self._extract_result_text(last_result or {})
            if not final_text:
                final_text = accumulated_text or "결과 텍스트를 생성하지 못했습니다."

            await updater.add_artifact(
                [Part(root=TextPart(text=final_text))],
                # artifact_id=str(uuid.uuid4()), # 안줘도 내부에서 만들어줌
                name='result',
            )
            # 완료 이벤트만 전송 (텍스트 메시지로 결과를 중복 전송하지 않음)
            await updater.complete()

        except Exception as e:
            logger.error(f'A2A 실행 중 오류: {e}')
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


