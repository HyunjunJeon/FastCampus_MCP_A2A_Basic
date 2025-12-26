"""A2A-MCP 패키지 초기화 모듈.

MCP 서버를 시작하기 위한 편의 메서드를 제공합니다.

사용 가능한 서버:
    - mcp-server: 에이전트 카드 MCP 서버 (기본값)

실행 예시:
    a2a-mcp --run mcp-server --host localhost --port 10100
"""
import click

from a2a_mcp.mcp import server


@click.command()
@click.option('--run', 'command', default='mcp-server', help='Command to run')
@click.option(
    '--host',
    'host',
    default='localhost',
    help='Host on which the server is started or the client connects to',
)
@click.option(
    '--port',
    'port',
    default=10100,
    help='Port on which the server is started or the client connects to',
)
@click.option(
    '--transport',
    'transport',
    default='stdio',
    help='MCP Transport',
)
def main(command, host, port, transport) -> None:
    """지정된 서버를 시작합니다.

    Args:
        command: 실행할 서버 유형 ('mcp-server').
        host: 서버 바인딩 호스트.
        port: 서버 바인딩 포트.
        transport: MCP 전송 프로토콜 ('stdio', 'sse').

    Raises:
        ValueError: 알 수 없는 서버 유형.
    """
    # TODO: 다른 서버 추가, 동적 포트 할당 고려
    if command == 'mcp-server':
        server.serve(host, port, transport)
    else:
        raise ValueError(f'Unknown run option: {command}')
