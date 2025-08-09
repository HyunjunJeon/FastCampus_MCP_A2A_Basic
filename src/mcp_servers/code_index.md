# Code Index - mcp_servers

MCP(Model Context Protocol) 서버 모음.
표준화된 도구 응답과 Health/Run 유틸을 포함.

## Files

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
