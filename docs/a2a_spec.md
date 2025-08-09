# A2A Protocol Specification

> 이 문서는 프로젝트에서 사용하는 A2A 0.3.0 기반의 프로토콜 사양을 정리한 것입니다.

## 목차

1. [개요](#개요)
2. [핵심 개념](#핵심-개념)
3. [전송 프로토콜 & 데이터 형식](#전송-프로토콜--데이터-형식)
4. [인증 및 권한 부여](#인증-및-권한-부여)
5. [Agent Card (에이전트 발견)](#agent-card-에이전트-발견)
6. [프로토콜 데이터 객체](#프로토콜-데이터-객체)
7. [RPC 메소드](#rpc-메소드)
8. [에러 처리](#에러-처리)
9. [Agent 구현](#agent-구현)
10. [클라이언트 구현](#클라이언트-구현)
11. [확장 기능](#확장-기능)
12. [실시간 이벤트 강화 패턴](#실시간-이벤트-강화-패턴)

## 개요

A2A (Agent-to-Agent) 프로토콜은 독립적인 AI 에이전트 시스템 간의 표준화된 통신과 상호 운용성을 지원하는 개방형 표준입니다.

### 주요 목표

- **상호 운용성**: 서로 다른 에이전트 시스템 간의 통신 격차 해소
- **협업**: 에이전트가 작업을 위임하고, 컨텍스트를 교환하며, 복잡한 사용자 요청에 대해 협력할 수 있도록 지원
- **발견**: 에이전트가 다른 에이전트의 기능을 동적으로 찾고 이해할 수 있도록 지원
- **유연성**: 동기식 요청/응답, 실시간 업데이트를 위한 스트리밍, 장기 실행 작업을 위한 비동기 푸시 알림 등 다양한 상호작용 모드 지원
- **보안성**: 표준 웹 보안 관행에 의존하는 엔터프라이즈 환경에 적합한 보안 통신 패턴 지원
- **비동기성**: 장기 실행 작업과 인간 개입 시나리오를 포함하는 상호작용을 기본적으로 지원

### 핵심 설계 원칙

- **단순성**: 기존의 잘 이해된 표준 재사용 (HTTP, JSON-RPC 2.0, Server-Sent Events)
- **엔터프라이즈 준비**: 확립된 엔터프라이즈 관행과 일치하여 인증, 권한 부여, 보안, 개인정보보호, 추적 및 모니터링 해결
- **비동기 우선**: (잠재적으로 매우) 장기 실행 작업과 인간 개입 상호작용을 위해 설계됨
- **모달리티 비관련**: 텍스트, 오디오/비디오(파일 참조를 통해), 구조화된 데이터/양식 등 다양한 콘텐츠 유형의 교환 지원
- **불투명한 실행**: 에이전트는 내부 생각, 계획 또는 도구 구현을 공유할 필요 없이 선언된 기능과 교환된 정보를 기반으로 협력

### 주요 특징

- **표준화된 통신**: JSON-RPC 2.0 기반의 통신 프로토콜
- **다중 전송 지원**: JSON-RPC, gRPC, HTTP+JSON/REST 전송 프로토콜 지원
- **스트리밍 지원**: Server-Sent Events (SSE)를 통한 실시간 응답
- **상태 관리**: Task 기반의 작업 상태 추적 및 생명주기 관리
- **확장 가능**: 커스텀 메시지 타입과 확장 지원
- **멀티모달 지원**: 텍스트, 파일, 구조화된 데이터 등 다양한 콘텐츠 유형 지원
- **푸시 알림**: 장기 실행 작업을 위한 비동기 웹훅 지원

## 핵심 개념

### 1. A2A Client

요청을 시작하는 애플리케이션이나 에이전트로, 사용자나 다른 시스템을 대신하여 A2A Server에 요청을 보냅니다.

### 2. A2A Server (Remote Agent)

A2A 호환 HTTP 엔드포인트를 노출하는 에이전트나 에이전트 시스템으로, 작업을 처리하고 응답을 제공합니다.

### 3. Agent Card

A2A Server가 게시하는 JSON 메타데이터 문서로, ID, 기능, 스킬, 서비스 엔드포인트, 인증 요구사항을 설명합니다.

### 4. Message

클라이언트와 원격 에이전트 간의 통신 턴으로, `role` ("user" 또는 "agent")을 가지며 하나 이상의 `Parts`를 포함합니다.

### 5. Task

A2A에서 관리하는 작업의 기본 단위로, 고유한 ID로 식별됩니다. Task는 상태를 가지며 정의된 생명주기를 거칩니다.

### 6. Part

Message나 Artifact 내의 가장 작은 콘텐츠 단위입니다.(예: `TextPart`, `FilePart`, `DataPart`).

### 7. Artifact

에이전트가 작업의 결과로 생성하는 출력물(문서, 이미지, 구조화된 데이터 등)로, `Parts`로 구성됩니다.

### 8. Streaming (SSE)

Server-Sent Events를 통해 전달되는 작업의 실시간, 증분 업데이트 (상태 변경, 아티팩트 청크).

### 9. Push Notifications

장기 실행 또는 연결이 끊어진 시나리오를 위해 서버가 시작하는 HTTP POST 요청을 통해 전달되는 비동기 작업 업데이트. Client 의 WebHook URL 이 반드시 필요함.

## 전송 프로토콜 & 데이터 형식

### 전송 계층 요구사항

- **HTTPS 필수**: 모든 A2A 통신은 HTTPS를 통해 이루어져야 함(개발 및 테스트에서만 HTTP 허용)
- **다중 프로토콜 지원**: 에이전트는 최소 하나의 전송 프로토콜을 구현해야 함
- **기능적 동등성**: 여러 전송을 지원하는 경우, 모든 전송에서 동일한 기능 제공

### 지원되는 전송 프로토콜

#### 1. JSON-RPC 2.0 Transport

가장 일반적으로 사용되는 기본 전송 프로토콜:

```python
# JSON-RPC 요청 예제
{
    "jsonrpc": "2.0",
    "id": "request-id",
    "method": "message/send",
    "params": {
        "message": {
            "kind": "message",
            "messageId": "msg-123",
            "role": "user",
            "parts": [
                {"kind": "text", "text": "Hello"}
            ]
        }
    }
}
```

**요구사항**:

- Content-Type: `application/json`
- JSON-RPC 2.0 스펙 준수
- 메소드 이름: `{category}/{action}` 패턴 (예: `message/send`)

#### 2. gRPC Transport(v0.3.0 추가)

높은 성능이 필요한 환경을 위한 선택적 프로토콜:

**요구사항**:

- Protocol Buffers v3 사용
- `a2a.proto` 정의 파일 준수
- TLS 암호화 필수
- HTTP/2 기반

#### 3. HTTP+JSON Transport

RESTful 패턴을 선호하는 환경을 위한 선택적 프로토콜:

```python
# REST 엔드포인트 예제
POST /v1/message:send
GET /v1/tasks/{id}
POST /v1/tasks/{id}:cancel
```

**요구사항**:

- 적절한 HTTP Method 사용 (GET, POST, PUT, DELETE)
- RESTful URI 패턴 준수
- HTTP 상태 코드 적절히 사용

### 스트리밍 전송 (Server-Sent Events)

실시간 업데이트를 위한 스트리밍 지원:

```python
# SSE 스트림 예제
data: {"id":"req-123","jsonrpc":"2.0","result":{"kind":"status-update","status":{"state":"working"}}}

data: {"id":"req-123","jsonrpc":"2.0","result":{"kind":"message","message":{"role":"agent","parts":[{"kind":"text","text":"Processing..."}]}}}

data: {"id":"req-123","jsonrpc":"2.0","result":{"kind":"status-update","status":{"state":"completed"},"final":true}}
```

**특징**:

- Content-Type: `text/event-stream`
- W3C Server-Sent Events 표준 준수
- 실시간 작업 상태 업데이트
- 아티팩트 청크 전송 지원

### 메소드 매핑

각 전송 프로토콜별 메소드 매핑:

| JSON-RPC | gRPC | REST | 설명 |
|----------|------|------|------|
| `message/send` | `SendMessage` | `POST /v1/message:send` | 메시지 전송 |
| `message/stream` | `SendStreamingMessage` | `POST /v1/message:stream` | 스트리밍 메시지 전송 |
| `tasks/get` | `GetTask` | `GET /v1/tasks/{id}` | 작업 상태 조회 |
| `tasks/cancel` | `CancelTask` | `POST /v1/tasks/{id}:cancel` | 작업 취소 |
| `tasks/resubscribe` | `TaskSubscription` | `POST /v1/tasks/{id}:subscribe` | 작업 스트림 재구독 |

### 전송 선택 및 협상

```python
# Agent Card에서 전송 프로토콜 선언
{
    "preferredTransport": "JSONRPC",
    "additionalInterfaces": [
        {"url": "https://api.example.com/a2a/v1", "transport": "JSONRPC"},
        {"url": "https://api.example.com/a2a/grpc", "transport": "GRPC"},
        {"url": "https://api.example.com/a2a/json", "transport": "HTTP+JSON"}
    ]
}
```

## 인증 및 권한 부여

### 전송 보안

- **HTTPS 필수**: 프로덕션 환경에서는 반드시 HTTPS 사용
- **TLS 1.3+** 권장: 강력한 암호화 스위트와 함께

### 클라이언트 인증 프로세스

1. **요구사항 발견**: Agent Card의 `securitySchemes` 필드를 통해 인증 요구사항 확인
2. **자격 증명 획득**: 밴드 외(out-of-band) 프로세스를 통한 자격 증명 취득
3. **자격 증명 전송**: HTTP 헤더를 통한 자격 증명 포함

```python
# 인증 헤더 예제
Authorization: Bearer <access_token>
X-API-Key: <api_key>
```

### 지원되는 인증 스킴

#### 1. API Key 인증

```python
{
    "type": "apiKey",
    "in": "header",
    "name": "X-API-Key"
}
```

#### 2. HTTP Bearer 인증

```python
{
    "type": "http",
    "scheme": "bearer",
    "bearerFormat": "JWT"
}
```

#### 3. OAuth 2.0

```python
{
    "type": "oauth2",
    "flows": {
        "authorizationCode": {
            "authorizationUrl": "https://example.com/oauth/authorize",
            "tokenUrl": "https://example.com/oauth/token",
            "scopes": {
                "read": "읽기 접근",
                "write": "쓰기 접근"
            }
        }
    }
}
```

#### 4. OpenID Connect

```python
{
    "type": "openIdConnect",
    "openIdConnectUrl": "https://accounts.google.com/.well-known/openid-configuration"
}
```

### 작업 중 인증 (보조 자격 증명)

에이전트가 작업 실행 중 추가 자격 증명이 필요한 경우:

1. 작업 상태를 `auth-required`로 전환
2. `TaskStatus.message`에 필요한 인증 정보 제공
3. 클라이언트가 필요한 자격 증명을 밴드 외에서 획득
4. 후속 메시지에서 자격 증명 제공

## Agent Card (Agent Discovery 의 핵심)

### 목적

Agent Card는 에이전트의 ID, 기능, 스킬, 서비스 엔드포인트, 인증 요구사항을 설명하는 JSON 메타데이터 문서입니다.

### 발견 메커니즘

1. **Well-Known URI**: `https://{domain}/.well-known/agent-card.json`
2. **레지스트리/카탈로그**: 큐레이션된 에이전트 카탈로그 쿼리
3. **직접 구성**: Agent Card URL 또는 콘텐츠를 사전 구성

### Agent Card 구조

```python
{
    "protocolVersion": "0.3.0",
    "name": "Research Agent",
    "description": "AI 연구 지원 에이전트",
    "url": "https://research-agent.example.com/a2a/v1",
    "preferredTransport": "JSONRPC",
    "provider": {
        "organization": "Example AI Labs",
        "url": "https://example-ai.com"
    },
    "version": "1.0.0",
    "capabilities": {
        "streaming": true,
        "pushNotifications": true,
        "stateTransitionHistory": false
    },
    "defaultInputModes": ["text/plain", "application/json"],
    "defaultOutputModes": ["text/plain", "application/json"],
    "skills": [
        {
            "id": "research-papers",
            "name": "논문 검색 및 분석",
            "description": "학술 논문을 검색하고 내용을 분석합니다",
            "tags": ["research", "papers", "analysis"],
            "examples": [
                "2023년 LLM 관련 논문을 찾아줘",
                "이 논문의 핵심 내용을 요약해줘"
            ]
        }
    ],
    "securitySchemes": {
        "oauth": {
            "type": "oauth2",
            "flows": {
                "authorizationCode": {
                    "authorizationUrl": "https://auth.example.com/oauth/authorize",
                    "tokenUrl": "https://auth.example.com/oauth/token",
                    "scopes": {
                        "research": "연구 기능 접근"
                    }
                }
            }
        }
    },
    "security": [{"oauth": ["research"]}]
}
```

### 핵심 필드

직접 구현하지 않고 a2a.types 내에 있는 객체들을 활용한다.

#### AgentCapabilities

```python
{
    "streaming": true,           # SSE 스트리밍 지원
    "pushNotifications": true,   # 푸시 알림 지원
    "stateTransitionHistory": false,  # 상태 전환 기록 제공
    "extensions": []             # 프로토콜 확장
}
```

#### AgentSkill

```python
{
    "id": "unique-skill-id",
    "name": "스킬 이름",
    "description": "상세 설명",
    "tags": ["태그1", "태그2"],
    "examples": ["사용 예제"],
    "inputModes": ["text/plain"],   # 지원되는 입력 타입
    "outputModes": ["text/plain"],  # 지원되는 출력 타입
    "security": []                  # 스킬별 보안 요구사항
}
```

#### AgentInterface

```python
{
    "url": "https://api.example.com/a2a/grpc",
    "transport": "GRPC"
}
```

## 프로토콜 데이터 객체

직접 구현하지 않고 a2a.types 내에 있는 객체들을 활용한다.

### Task 객체

작업의 상태가 있는 단위를 나타냅니다:

```python
from a2a.types import Task, TaskStatus, TaskState

task = Task(
    id="task-123",
    context_id="ctx-456",
    status=TaskStatus(
        state=TaskState.working,
        message=None,
        timestamp="2024-01-01T10:00:00Z"
    ),
    history=[],
    artifacts=[],
    kind="task"
)
```

### TaskState 열거형

작업의 생명주기 상태:

```python
class TaskState(Enum):
    submitted = "submitted"        # 제출됨
    working = "working"           # 작업 중
    input_required = "input-required"  # 입력 필요
    completed = "completed"       # 완료됨
    canceled = "canceled"         # 취소됨
    failed = "failed"            # 실패
    rejected = "rejected"        # 거부됨
    auth_required = "auth-required"   # 인증 필요
    unknown = "unknown"          # 알 수 없음
```

### Message 객체

단일 통신 턴을 나타냅니다:

```python
from a2a.types import Message, TextPart

message = Message(
    role="user",  # "user" 또는 "agent"
    parts=[
        TextPart(
            kind="text",
            text="안녕하세요!"
        )
    ],
    message_id="msg-789",
    task_id="task-123",
    context_id="ctx-456",
    kind="message"
)
```

### Part 유니온 타입

메시지나 아티팩트 내의 콘텐츠 부분:

#### TextPart

```python
from a2a.types import TextPart

text_part = TextPart(
    kind="text",
    text="텍스트 콘텐츠",
    metadata={"language": "ko"}
)
```

#### FilePart

```python
from a2a.types import FilePart, FileWithBytes, FileWithUri

# 바이트로 파일 데이터 제공
file_part_bytes = FilePart(
    kind="file",
    file=FileWithBytes(
        name="document.pdf",
        mime_type="application/pdf",
        bytes="<base64-encoded-content>"
    )
)

# URI로 파일 위치 제공
file_part_uri = FilePart(
    kind="file",
    file=FileWithUri(
        name="image.jpg",
        mime_type="image/jpeg",
        uri="https://example.com/files/image.jpg"
    )
)
```

#### DataPart

```python
from a2a.types import DataPart

data_part = DataPart(
    kind="data",
    data={
        "key": "value",
        "numbers": [1, 2, 3],
        "nested": {"field": "data"}
    }
)
```

### Artifact 객체

에이전트가 생성한 유형의 출력물:

```python
from a2a.types import Artifact, TextPart

artifact = Artifact(
    artifact_id="artifact-123",
    name="보고서",
    description="분석 보고서",
    parts=[
        TextPart(
            kind="text",
            text="보고서 내용..."
        )
    ]
)
```

## RPC 메소드

### 핵심 메소드 (필수)

#### 1. message/send

메시지를 에이전트에게 전송하여 새로운 상호작용을 시작하거나 기존 상호작용을 계속합니다.

```python
# 요청
{
    "jsonrpc": "2.0",
    "id": "req-1",
    "method": "message/send",
    "params": {
        "message": {
            "kind": "message",
            "messageId": "msg-1",
            "role": "user",
            "parts": [
                {"kind": "text", "text": "안녕하세요!"}
            ]
        },
        "configuration": {
            "acceptedOutputModes": ["text/plain"],
            "historyLength": 10,
            "blocking": false
        }
    }
}

# 응답 - Task 또는 Message 반환
{
    "jsonrpc": "2.0",
    "id": "req-1",
    "result": {
        "kind": "task",
        "id": "task-123",
        "contextId": "ctx-456",
        "status": {
            "state": "completed"
        }
    }
}
```

#### 2. tasks/get

이전에 시작된 작업의 현재 상태를 조회합니다.

#### 3. tasks/cancel

진행 중인 작업의 취소를 요청합니다.

### 선택적 메소드

#### 1. message/stream

메시지를 전송하고 Server-Sent Events를 통해 실시간 업데이트를 구독합니다.

#### 2. tasks/resubscribe

기존 작업의 SSE 스트림에 재연결합니다.

#### 3. Push Notification 메소드들

- `tasks/pushNotificationConfig/set`: 푸시 알림 구성 설정
- `tasks/pushNotificationConfig/get`: 푸시 알림 구성 조회
- `tasks/pushNotificationConfig/list`: 푸시 알림 구성 목록
- `tasks/pushNotificationConfig/delete`: 푸시 알림 구성 삭제

## 에러 처리

### 표준 JSON-RPC 에러

| 코드 | 이름 | 설명 |
|------|------|------|
| -32700 | Parse error | 잘못된 JSON |
| -32600 | Invalid Request | 잘못된 JSON-RPC 요청 |
| -32601 | Method not found | 메소드를 찾을 수 없음 |
| -32602 | Invalid params | 잘못된 매개변수 |
| -32603 | Internal error | 내부 서버 에러 |

### A2A 특정 에러

A2A SDK 에서 제공하는 공식 에러를 사용 또는 상속받아 커스터마이징 하도록 한다.

| 코드 | 이름 | 설명 |
|------|------|------|
| -32001 | TaskNotFoundError | 작업을 찾을 수 없음 |
| -32002 | TaskNotCancelableError | 취소할 수 없는 작업 |
| -32003 | PushNotificationNotSupportedError | 푸시 알림 미지원 |
| -32004 | UnsupportedOperationError | 지원되지 않는 작업 |
| -32005 | ContentTypeNotSupportedError | 지원되지 않는 콘텐츠 타입 |
| -32006 | InvalidAgentResponseError | 잘못된 에이전트 응답 |
| -32007 | AuthenticatedExtendedCardNotConfiguredError | 인증된 확장 카드 미구성 |

## Agent 구현

### AgentExecutor 패턴

```python
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import TaskState
from a2a.utils import new_agent_text_message

class MyAgentExecutor(AgentExecutor):
    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        task_updater = TaskUpdater(
            event_queue=event_queue,
            task_id=context.task_id,
            context_id=context.context_id
        )
        
        try:
            await task_updater.update_status(TaskState.working)
            
            # 실제 작업 처리
            user_text = self._extract_text(context.message)
            result = await self.process_with_tools(user_text)
            
            # 응답 전송
            message = new_agent_text_message(result)
            await event_queue.enqueue_event(message)
            
            await task_updater.complete()
            
        except asyncio.CancelledError:
            cancel_message = new_agent_text_message("작업이 취소되었습니다.")
            await event_queue.enqueue_event(cancel_message)
            await task_updater.cancel()
            raise
        except Exception as e:
            await task_updater.failed()
            error_message = new_agent_text_message(f"오류 발생: {str(e)}")
            await event_queue.enqueue_event(error_message)
```

### 서버 애플리케이션 설정

```python
from a2a.server.apps import A2AStarletteApplication
from a2a.server.tasks import InMemoryTaskStore

# Agent Card 정의
agent_card = AgentCard(
    name="My Research Agent",
    description="연구 지원 AI 에이전트",
    version="1.0.0",
    url="http://localhost:8080/",
    preferred_transport="JSONRPC",
    default_input_modes=["text/plain", "application/json"],
    default_output_modes=["text/plain", "application/json"],
    capabilities=AgentCapabilities(streaming=True)
)

# A2A 애플리케이션 생성
app = A2AStarletteApplication(
    agent_card=agent_card,
    http_handler=MyRequestHandler(),
    task_store=InMemoryTaskStore()
)

# 서버 실행
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app.build(),
        host="0.0.0.0",
        port=8080,
        timeout_keep_alive=300
    )
```

### MCP 통합 -> LangGraph Agent 가 실제 로직 모듈이므로 Step1 과 변화되는건 없음

```python
from langchain_mcp_adapters.client import MultiServerMCPClient

class MCPIntegratedAgent(AgentExecutor):
    def __init__(self):
        self.mcp_client = MultiServerMCPClient({
            "tavily": {
                "command": "python",
                "args": ["src/mcp_servers/tavily_search/server.py"]
            }
        })
    
    async def execute(self, context: RequestContext, event_queue: EventQueue):
        user_query = self._extract_text(context.message)
        
        # MCP 도구 사용
        tools = await self.mcp_client.get_tools()
        
        # TODO tools 중에서 적절한 툴을 골라서 실행

        
        # TODO: 결과 처리 및 응답
        response = self.process_results(search_results)
        message = new_agent_text_message(response)
        await event_queue.enqueue_event(message)
```

## 클라이언트 구현

### 기본 클라이언트

```python
from a2a.client import ClientFactory, ClientConfig, A2ACardResolver
import httpx

async def basic_client_example():
    async with httpx.AsyncClient() as http_client:
        # Agent Card 조회
        resolver = A2ACardResolver(http_client, "https://agent.example.com")
        agent_card = await resolver.get_agent_card()
        
        # 클라이언트 생성
        config = ClientConfig(httpx_client=http_client, streaming=True)
        factory = ClientFactory(config)
        client = factory.create(agent_card)
        
        # 메시지 전송
        message = # TODO 메시지 전송 방법 확인 필요(공식 문서 또는 예제 문서 참조)
        response = await client.send_message(message)
        print(f"응답: {response}")
```

### 스트리밍 클라이언트

```python
async def streaming_example():
    # 스트리밍 메시지 전송
    message = new_user_text_message("긴 보고서를 작성해주세요")
    
    async for task, update in client.send_message_streaming(message):
        if update is None:
            print(f"작업 시작: {task.id}")
        elif isinstance(update, TaskStatusUpdateEvent):
            print(f"상태 변경: {update.status.state}")
            if update.final:
                break
        elif isinstance(update, TaskArtifactUpdateEvent):
            # 아티팩트 업데이트 처리
            artifact = update.artifact
            for part in artifact.parts:
                if isinstance(part, TextPart):
                    print(f"콘텐츠: {part.text}")
```

## 확장 기능

### Push Notifications

```python
# 푸시 알림 설정
push_config = PushNotificationConfig(
    id="webhook-1",
    url="https://client.example.com/webhook/a2a-notifications",
    token="secure-client-token",
    authentication=PushNotificationAuthenticationInfo(
        schemes=["Bearer"],
        credentials="webhook-auth-token"
    )
)
```

### Multi-Modal Support

```python
# 이미지와 텍스트가 포함된 메시지
message = Message(
    role="user",
    parts=[
        TextPart(kind="text", text="이 이미지를 분석해주세요"),
        FilePart(
            kind="file",
            file=FileWithBytes(
                name="image.jpg",
                mime_type="image/jpeg",
                bytes="<base64-encoded-image>"
            )
        )
    ],
    message_id="multimodal-msg",
    kind="message"
)
```

## 실시간 이벤트 강화 패턴

### Enhanced Researcher Pattern

```python
@dataclass
class ResearchProgress:
    """연구 진행 상태 추적"""
    researcher_id: str
    researcher_color: str
    current_step: int = 0
    total_steps: int = 6
    notes_collected: int = 0

async def _send_progress_event(
    event_queue: EventQueue,
    progress: ResearchProgress,
    event_type: str,
    detail: str = ""
):
    """표준화된 진행 상태 이벤트 전송"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    base_msg = f"{progress.researcher_color} 연구원 {progress.researcher_id}"
    
    if event_type == "start":
        message = f"{base_msg}: 🚀 연구 시작 - {detail}"
    elif event_type == "tool_start":
        percentage = int((progress.current_step / progress.total_steps) * 100)
        message = f"{base_msg}: 🔬 {detail} 사용 중... ({percentage}% 완료)"
    elif event_type == "complete":
        message = f"{base_msg}: 🎉 연구 완료 - {detail}"
    
    full_message = f"[{timestamp}] {message}"
    await event_queue.enqueue_event(new_agent_text_message(full_message))
```

### HITL (Human-In-The-Loop) 통합

```python
class HITLAgent(AgentExecutor):
    """인간 개입 루프 지원 에이전트"""
    
    async def execute(self, context: RequestContext, event_queue: EventQueue):
        task_updater = TaskUpdater(
            event_queue=event_queue,
            task_id=context.task_id,
            context_id=context.context_id
        )
        
        try:
            # 1단계: 자동 분석
            user_query = self._extract_text(context.message)
            initial_analysis = await self._analyze_query(user_query)
            
            # 2단계: 승인 요청
            approval_message = new_agent_text_message(
                f"다음 분석을 진행하시겠습니까?\n\n{initial_analysis}\n\n"
                "승인하려면 'yes' 또는 'approve'를 입력하세요."
            )
            await event_queue.enqueue_event(approval_message)
            
            # 입력 대기 상태로 전환
            await task_updater.update_status(TaskState.input_required)
            
        except asyncio.CancelledError:
            cancel_message = new_agent_text_message(
                "작업이 사용자에 의해 취소되었습니다."
            )
            await event_queue.enqueue_event(cancel_message)
            await task_updater.cancel()
            raise
```

## 모범 사례

### 에러 처리

```python
try:
    await task_updater.update_status(TaskState.working)
    result = await self.process_with_mcp_tools(user_input)
    await task_updater.complete()
    
except asyncio.CancelledError:
    # 사용자 취소 처리
    cancel_message = new_agent_text_message("작업이 취소되었습니다.")
    await event_queue.enqueue_event(cancel_message)
    await task_updater.cancel()
    raise
except Exception as e:
    await task_updater.failed()
    error_message = new_agent_text_message(f"오류: {str(e)}")
    await event_queue.enqueue_event(error_message)
```

### 성능 최적화

```python
# MCP 클라이언트 연결 관리
from langchain_mcp_adapters.client import MultiServerMCPClient

class OptimizedMCPAgent:
    def __init__(self):
        # 서버별 세션 관리 및 재사용
        self.mcp_client = MultiServerMCPClient({
            "tavily": {
                "command": "python", 
                "args": ["src/mcp_servers/tavily_search/server.py"]
            }
        })
        
        # 결과 캐싱
        self._cache = {}
    
    async def cached_tool_call(self, server: str, tool: str, args: dict):
        """캐싱을 포함한 MCP 도구 호출"""
        cache_key = f"{server}:{tool}:{hash(str(args))}"
        
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        result = await self.mcp_client.call_tool(server, tool, args)
        self._cache[cache_key] = result
        return result
```

## 참고 자료

- **A2A Protocol Specification**: <https://a2a-protocol.org/latest/specification/>
- **A2A SDK Python API**: <https://a2a-protocol.org/latest/sdk/python/api/>
- **A2A SDK Python 문서**: `docs/a2a-python_0.3.0.txt`
- **A2A 샘플 코드**: `docs/a2a-samples_0.3.0.txt`
- **LangChain MCP Adapters**: `docs/langchain-mcp-adapters.txt`
- **Model Context Protocol**: <https://modelcontextprotocol.io/>

## 버전 히스토리

**0.3.0**: 현재 프로젝트에서 사용 중인 버전

- RequestHandler 추상 클래스 도입
- 다중 전송 프로토콜 지원 (JSON-RPC, gRPC, HTTP+JSON/REST)
- SSE 스트리밍 지원 강화
- TaskArtifactUpdateEvent 추가로 대용량 콘텐츠 청크 전송 지원
- Multi-modal 메시지 지원 (텍스트, 파일, 구조화된 데이터)
- 보안 스킴 다양화 (API Key, OAuth2, OpenID Connect, mTLS 등)
- Agent Card 구조 개선 및 확장 지원
- Enhanced Researcher Pattern 구현
- HITL (Human-In-The-Loop) 통합
- 한국어 주석 및 문서화 개선
