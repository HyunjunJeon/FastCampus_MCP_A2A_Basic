"""GitHub 에이전트 생성 모듈.

이 모듈은 GitHub API와 상호작용하는 OpenAI 기반 에이전트를 생성합니다.
GitHubToolset을 초기화하고 시스템 프롬프트와 함께 반환합니다.
"""
from github_toolset import GitHubToolset  # type: ignore[import-untyped]


def create_agent() -> dict:
    """OpenAI 에이전트와 도구를 생성합니다.

    GitHubToolset을 초기화하고, GitHub 저장소 조회를 위한
    시스템 프롬프트와 함께 에이전트 설정을 반환합니다.

    Returns:
        dict: 에이전트 설정을 포함하는 딕셔너리.
            - tools (dict): OpenAI 함수 호출용 도구 딕셔너리
            - system_prompt (str): 에이전트 동작을 정의하는 시스템 프롬프트

    Note:
        시스템 프롬프트는 영문으로 유지됩니다 (LLM 지시사항).
        에이전트는 저장소 정보, 커밋 히스토리, 저장소 검색 기능을 제공합니다.
    """
    # GitHub API 도구 세트 초기화
    toolset = GitHubToolset()
    tools = toolset.get_tools()

    # 시스템 프롬프트 - 영문 유지 (LLM 지시사항)
    return {
        'tools': tools,
        'system_prompt': """You are a GitHub agent that can help users query information about GitHub repositories and recent project updates.

Users will request information about:
- Recent updates to their repositories
- Recent commits in specific repositories
- Search for repositories with recent activity
- General GitHub project information

Use the provided tools for interacting with the GitHub API.

When displaying repository information, include relevant details like:
- Repository name and description
- Last updated time
- Programming language
- Stars and forks count
- Recent commit information when available

Always provide helpful and accurate information based on the GitHub API results. Respond in Chinese unless the user specifically requests English.""",
    }
