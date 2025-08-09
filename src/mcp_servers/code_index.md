# Code Index - mcp_servers
## Code Index - mcp_servers

MCP(Model Context Protocol) 서버 모음. 표준화된 도구 응답과 헬스/런 유틸을 포함.

### Files

- __init__.py: 패키지 초기화.
- base_mcp_server.py: 표준 응답/에러 모델, FastMCP 서버 베이스와 헬스엔드포인트.

### Submodules

- arxiv_search/
  - __init__.py: 패키지 초기화.
  - arxiv_client.py: arXiv 검색/상세 조회 클라이언트.
  - server.py: arXiv MCP 서버 도구 등록/실행.

- serper_search/
  - __init__.py: 패키지 초기화.
  - serper_dev_client.py: Serper API 래퍼와 표준화 모델.
  - server.py: Google 검색 MCP 서버 도구 등록.

- tavily_search/
  - __init__.py: 패키지 초기화.
  - tavily_search_client.py: Tavily API 래퍼.
  - server.py: Tavily MCP 서버 도구 등록.

### Related

- 상위: [../code_index.md](../code_index.md), [../../code_index.md](../../code_index.md)

## 📁 MCP Servers Module

Model Context Protocol (MCP) 서버 구현 모듈
다양한 외부 서비스를 MCP 프로토콜로 통합하여 LLM이 사용할 수 있는 도구로 제공

## 파일 구조

### 📄 __init__.py

- MCP 서버 패키지 초기화
- 서버 클래스 export

### 📄 base_mcp_server.py

- __클래스__: `StandardResponse`, `ErrorResponse`, `BaseMCPServer`
- 모든 MCP 서버의 기본 추상 클래스
- 공통 프로토콜 구현
- 에러 처리와 응답 포맷 표준화

## 📁 arxiv_search/ - arXiv 논문 검색 서버

### 📄 __init__.py

- arXiv 검색 패키지 초기화

### 📄 arxiv_client.py

- arXiv API 클라이언트 구현
- 논문 검색과 메타데이터 수집
- PDF 다운로드와 초록 추출

### 📄 server.py

- __클래스__: `ArxivSearchServer`
- __인스턴스__: `server`
- arXiv 검색을 MCP 도구로 제공
- 학술 논문 검색 특화 기능

## 📁 serper_search/ - Serper.dev 웹 검색 서버

### 📄 __init__.py

- Serper 검색 패키지 초기화

### 📄 serper_dev_client.py

- Serper.dev API 클라이언트
- 웹 검색, 이미지 검색, 뉴스 검색
- 검색 결과 구조화 및 필터링

### 📄 server.py

- __클래스__: `SerperSearchServer`
- __인스턴스__: `server`
- 웹 검색을 MCP 도구로 제공
- 실시간 웹 정보 접근

## 📁 tavily_search/ - Tavily AI 검색 서버

### 📄 __init__.py

- Tavily 검색 패키지 초기화

### 📄 tavily_search_client.py

- Tavily API 클라이언트
- AI 최적화 검색
- 컨텍스트 추출과 요약

### 📄 server.py

- __클래스__: `TavilySearchServer`
- __인스턴스__: `server`
- AI 기반 검색을 MCP 도구로 제공
- LLM 친화적 결과 포맷

## BaseMCPServer 구조

```python
class BaseMCPServer:
    @abstractmethod
    async def list_tools() -> list[Tool]
    
    @abstractmethod
    async def call_tool(name: str, arguments: dict) -> ToolResult
    
    async def handle_request(request: Request) -> Response
    
    async def start_server(host: str, port: int)
```

## MCP 도구 정의 형식

```python
Tool(
    name="search",
    description="웹 검색을 수행합니다",
    inputSchema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "검색 쿼리"
            },
            "max_results": {
                "type": "number",
                "description": "최대 결과 수"
            }
        },
        "required": ["query"]
    }
)
```

## 각 서버별 주요 도구

### ArxivSearchServer

- `search_papers`: 논문 검색
- `get_paper_details`: 논문 상세 정보
- `download_pdf`: PDF 다운로드

### SerperSearchServer

- `web_search`: 일반 웹 검색
- `image_search`: 이미지 검색
- `news_search`: 뉴스 검색
- `shopping_search`: 쇼핑 검색

### TavilySearchServer

- `search`: AI 최적화 검색
- `get_context`: 컨텍스트 추출
- `summarize`: 검색 결과 요약

## 서버 실행 방법

### 독립 실행

```bash
# arXiv 서버
python -m mcp_servers.arxiv_search.server --port 8000

# Serper 서버
python -m mcp_servers.serper_search.server --port 8001

# Tavily 서버
python -m mcp_servers.tavily_search.server --port 8002
```

### FastMCP 통합

```python
from fastmcp import FastMCP
from mcp_servers.arxiv_search.server import server

app = FastMCP("research-tools")
app.include_server(server)
```

### 환경 변수 설정

```bash
# API 키 설정
export SERPER_API_KEY="your-key"
export TAVILY_API_KEY="your-key"

# 서버 설정
export MCP_SERVER_HOST="0.0.0.0"
export MCP_SERVER_PORT="8000"
```

## LangChain 통합

```python
from langchain_mcp import MCPToolkit

# MCP 서버 연결
toolkit = MCPToolkit(
    server_url="http://localhost:8000"
)

# 도구 가져오기
tools = toolkit.get_tools()

# 에이전트에 통합
agent = create_react_agent(
    llm=llm,
    tools=tools
)
```

## 의존성

- FastMCP: MCP 프로토콜 구현
- aiohttp: 비동기 HTTP 클라이언트
- 각 서비스별 API 클라이언트 라이브러리
