"""MCP 클라이언트 모듈.

이 모듈은 MCP 서버와 통신하기 위한 클라이언트 함수들을 제공합니다.

주요 기능:
    - SSE/STDIO 전송 프로토콜 지원
    - 에이전트 검색 (find_agent)
    - 리소스 조회 (find_resource)
    - 여행 데이터 조회 도구 (search_flights, search_hotels, query_db)

실행 방법:
    python -m a2a_mcp.mcp.client --find_agent "book flight"
"""
# type:ignore
import asyncio
import json
import os

from contextlib import asynccontextmanager

import click

from fastmcp.utilities.logging import get_logger
from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult, ReadResourceResult


logger = get_logger(__name__)

# --- 환경 변수 설정 ---
env = {
    'GOOGLE_API_KEY': os.getenv('GOOGLE_API_KEY'),
}


@asynccontextmanager
async def init_session(host, port, transport):
    """지정된 전송 프로토콜로 MCP ClientSession을 초기화하고 관리합니다.

    SSE 또는 STDIO 전송을 사용하여 MCP 서버에 연결을 설정합니다.
    연결 설정 및 해제를 처리하고 통신 준비된 ClientSession을 반환합니다.

    Args:
        host: MCP 서버 호스트명 (SSE용).
        port: MCP 서버 포트 번호 (SSE용).
        transport: 사용할 전송 프로토콜 ('sse' 또는 'stdio').

    Yields:
        ClientSession: 초기화되어 사용 준비된 MCP 클라이언트 세션.

    Raises:
        ValueError: 지원하지 않는 전송 유형.
    """
    if transport == 'sse':
        url = f'http://{host}:{port}/sse'
        async with sse_client(url) as (read_stream, write_stream):
            async with ClientSession(
                read_stream=read_stream, write_stream=write_stream
            ) as session:
                logger.debug('SSE ClientSession created, initializing...')
                await session.initialize()
                logger.info('SSE ClientSession initialized successfully.')
                yield session
    elif transport == 'stdio':
        if not os.getenv('GOOGLE_API_KEY'):
            logger.error('GOOGLE_API_KEY is not set')
            raise ValueError('GOOGLE_API_KEY is not set')
        stdio_params = StdioServerParameters(
            command='uv',
            args=['run', 'a2a-mcp'],
            env=env,
        )
        async with stdio_client(stdio_params) as (read_stream, write_stream):
            async with ClientSession(
                read_stream=read_stream,
                write_stream=write_stream,
            ) as session:
                logger.debug('STDIO ClientSession created, initializing...')
                await session.initialize()
                logger.info('STDIO ClientSession initialized successfully.')
                yield session
    else:
        logger.error(f'Unsupported transport type: {transport}')
        raise ValueError(
            f"Unsupported transport type: {transport}. Must be 'sse' or 'stdio'."
        )


async def find_agent(session: ClientSession, query) -> CallToolResult:
    """MCP 서버의 'find_agent' 도구를 호출합니다.

    Args:
        session: 활성 ClientSession.
        query: 에이전트 검색을 위한 자연어 쿼리.

    Returns:
        CallToolResult: 도구 호출 결과.
    """
    logger.info(f"Calling 'find_agent' tool with query: '{query[:50]}...'")
    return await session.call_tool(
        name='find_agent',
        arguments={
            'query': query,
        },
    )


async def find_resource(session: ClientSession, resource) -> ReadResourceResult:
    """MCP 서버에서 리소스를 조회합니다.

    Args:
        session: 활성 ClientSession.
        resource: 조회할 리소스 URI (예: 'resource://agent_cards/list').

    Returns:
        ReadResourceResult: 리소스 조회 결과.
    """
    logger.info(f'Reading resource: {resource}')
    return await session.read_resource(resource)


async def search_flights(session: ClientSession) -> CallToolResult:
    """MCP 서버의 'search_flights' 도구를 호출합니다.

    Args:
        session: 활성 ClientSession.

    Returns:
        CallToolResult: 항공편 검색 결과.
    """
    # 구현 예정
    logger.info("Calling 'search_flights' tool'")
    return await session.call_tool(
        name='search_flights',
        arguments={
            'departure_airport': 'SFO',
            'arrival_airport': 'LHR',
            'start_date': '2025-06-03',
            'end_date': '2025-06-09',
        },
    )


async def search_hotels(session: ClientSession) -> CallToolResult:
    """MCP 서버의 'search_hotels' 도구를 호출합니다.

    Args:
        session: 활성 ClientSession.

    Returns:
        CallToolResult: 호텔 검색 결과.
    """
    # 구현 예정
    logger.info("Calling 'search_hotels' tool'")
    return await session.call_tool(
        name='search_hotels',
        arguments={
            'location': 'A Suite room in St Pancras Square in London',
            'check_in_date': '2025-06-03',
            'check_out_date': '2025-06-09',
        },
    )


async def query_db(session: ClientSession) -> CallToolResult:
    """MCP 서버의 'query_travel_data' 도구를 호출합니다.

    Args:
        session: 활성 ClientSession.

    Returns:
        CallToolResult: 데이터베이스 쿼리 결과.
    """
    logger.info("Calling 'query_db' tool'")
    return await session.call_tool(
        name='query_travel_data',
        arguments={
            'query': "SELECT id, name, city, hotel_type, room_type, price_per_night FROM hotels WHERE city='London'",
        },
    )


# --- 테스트 유틸리티 ---
async def main(host, port, transport, query, resource, tool):
    """MCP 서버에 연결하고 명령을 실행하는 메인 비동기 함수.

    로컬 테스트용으로 사용됩니다.

    Args:
        host: 서버 호스트명.
        port: 서버 포트.
        transport: 연결 전송 프로토콜 ('sse' 또는 'stdio').
        query: find_agent 도구용 쿼리 문자열 (선택).
        resource: 조회할 리소스 URI (선택).
        tool: 실행할 도구 이름 (선택). 유효 옵션:
            'search_flights', 'search_hotels', 'query_db'.
    """
    logger.info('Starting Client to connect to MCP')
    async with init_session(host, port, transport) as session:
        if query:
            result = await find_agent(session, query)
            data = json.loads(result.content[0].text)
            logger.info(json.dumps(data, indent=2))
        if resource:
            result = await find_resource(session, resource)
            logger.info(result)
            data = json.loads(result.contents[0].text)
            logger.info(json.dumps(data, indent=2))
        if tool:
            if tool == 'search_flights':
                results = await search_flights(session)
                logger.info(results.model_dump())
            if tool == 'search_hotels':
                result = await search_hotels(session)
                data = json.loads(result.content[0].text)
                logger.info(json.dumps(data, indent=2))
            if tool == 'query_db':
                result = await query_db(session)
                logger.info(result)
                data = json.loads(result.content[0].text)
                logger.info(json.dumps(data, indent=2))


# --- 커맨드라인 테스터 ---
@click.command()
@click.option('--host', default='localhost', help='SSE Host')
@click.option('--port', default='10100', help='SSE Port')
@click.option('--transport', default='stdio', help='MCP Transport')
@click.option('--find_agent', help='Query to find an agent')
@click.option('--resource', help='URI of the resource to locate')
@click.option('--tool_name', type=click.Choice(['search_flights', 'search_hotels', 'query_db']),
              help='Tool to execute: search_flights, search_hotels, or query_db')
def cli(host, port, transport, find_agent, resource, tool_name):
    """Agent Cards MCP 서버와 상호작용하는 커맨드라인 클라이언트."""
    asyncio.run(main(host, port, transport, find_agent, resource, tool_name))


if __name__ == '__main__':
    cli()
