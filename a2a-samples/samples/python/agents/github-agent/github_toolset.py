"""GitHub API 도구 세트 모듈.

이 모듈은 GitHub API와 상호작용하기 위한 도구 세트를 제공합니다.
PyGithub 라이브러리를 사용하여 저장소 정보, 커밋 히스토리,
저장소 검색 기능을 구현합니다.

주요 기능:
    - 사용자 저장소 목록 조회 (최근 업데이트 기준)
    - 특정 저장소의 최근 커밋 조회
    - 활발한 저장소 검색

클래스:
    GitHubUser: GitHub 사용자 정보 모델
    GitHubRepository: GitHub 저장소 정보 모델
    GitHubCommit: GitHub 커밋 정보 모델
    GitHubResponse: API 응답 기본 모델
    RepositoryResponse: 저장소 조회 응답 모델
    CommitResponse: 커밋 조회 응답 모델
    GitHubToolset: GitHub API 도구 세트
"""
import os

from datetime import datetime, timedelta
from typing import Any

from github import Auth, Github
from pydantic import BaseModel


class GitHubUser(BaseModel):
    """GitHub 사용자 정보 모델.

    Attributes:
        login: GitHub 사용자 아이디.
        name: 사용자 이름 (선택사항).
        email: 사용자 이메일 (선택사항).
    """

    login: str
    name: str | None = None
    email: str | None = None


class GitHubRepository(BaseModel):
    """GitHub 저장소 정보 모델.

    Attributes:
        name: 저장소 이름.
        full_name: 전체 이름 (owner/repo 형식).
        description: 저장소 설명 (선택사항).
        url: 저장소 URL.
        updated_at: 마지막 업데이트 시간 (ISO 형식).
        pushed_at: 마지막 푸시 시간 (ISO 형식, 선택사항).
        language: 주 프로그래밍 언어 (선택사항).
        stars: 스타 수.
        forks: 포크 수.
    """

    name: str
    full_name: str
    description: str | None = None
    url: str
    updated_at: str
    pushed_at: str | None = None
    language: str | None = None
    stars: int
    forks: int


class GitHubCommit(BaseModel):
    """GitHub 커밋 정보 모델.

    Attributes:
        sha: 커밋 SHA (처음 8자).
        message: 커밋 메시지 (첫 번째 줄만).
        author: 작성자 이름.
        date: 커밋 날짜 (ISO 형식).
        url: 커밋 URL.
    """

    sha: str
    message: str
    author: str
    date: str
    url: str


class GitHubResponse(BaseModel):
    """GitHub API 응답 기본 모델.

    모든 API 응답의 공통 필드를 정의합니다.

    Attributes:
        status: 응답 상태 ('success' 또는 'error').
        message: 응답 메시지.
        count: 반환된 항목 수 (선택사항).
        error_message: 오류 메시지 (오류 시에만, 선택사항).
    """

    status: str
    message: str
    count: int | None = None
    error_message: str | None = None


class RepositoryResponse(GitHubResponse):
    """저장소 조회 응답 모델.

    저장소 목록을 포함하는 응답입니다.

    Attributes:
        data: 저장소 정보 리스트 (선택사항).
    """

    data: list[GitHubRepository] | None = None


class CommitResponse(GitHubResponse):
    """커밋 조회 응답 모델.

    커밋 목록을 포함하는 응답입니다.

    Attributes:
        data: 커밋 정보 리스트 (선택사항).
    """

    data: list[GitHubCommit] | None = None


class GitHubToolset:
    """GitHub API 도구 세트.

    저장소 조회, 커밋 히스토리, 저장소 검색 등 GitHub API와
    상호작용하는 도구들을 제공합니다. OpenAI 함수 호출 형식으로
    사용할 수 있도록 설계되었습니다.

    Attributes:
        _github_client: PyGithub 클라이언트 인스턴스 (지연 초기화).
    """

    def __init__(self) -> None:
        """GitHubToolset 인스턴스를 초기화합니다."""
        self._github_client = None

    def _get_github_client(self) -> Github:
        """인증된 GitHub 클라이언트를 반환합니다.

        GITHUB_TOKEN 환경 변수가 설정되어 있으면 인증된 클라이언트를 생성하고,
        그렇지 않으면 비인증 클라이언트를 생성합니다 (API 호출 제한이 있음).

        Returns:
            Github: PyGithub 클라이언트 인스턴스.
        """
        if self._github_client is None:
            github_token = os.getenv('GITHUB_TOKEN')
            if github_token:
                # 토큰 인증으로 클라이언트 생성
                auth = Auth.Token(github_token)
                self._github_client = Github(auth=auth)
            else:
                # 비인증 모드 (API 호출 제한 있음)
                print(
                    'Warning: No GITHUB_TOKEN found, using unauthenticated access (limited rate)'
                )
                self._github_client = Github()
        return self._github_client

    def get_user_repositories(
        self,
        username: str | None = None,
        days: int | None = None,
        limit: int | None = None,
    ) -> RepositoryResponse:
        """사용자의 최근 업데이트된 저장소 목록을 조회합니다.

        Args:
            username: GitHub 사용자 이름 (선택사항, 기본값: 인증된 사용자).
            days: 최근 업데이트 기간 (일 단위, 기본값: 30일).
            limit: 반환할 최대 저장소 수 (기본값: 10).

        Returns:
            RepositoryResponse: 상태, 저장소 목록, 메타데이터를 포함합니다.
        """
        # 기본값 설정
        if days is None:
            days = 30
        if limit is None:
            limit = 10

        try:
            github = self._get_github_client()

            if username:
                # 특정 사용자 조회
                user = github.get_user(username)
            else:
                try:
                    # 인증된 사용자 (토큰 필요)
                    user = github.get_user()
                except Exception:
                    # 토큰 없이는 인증된 사용자를 가져올 수 없음
                    return RepositoryResponse(
                        status='error',
                        message='Username is required when not using authentication token',
                        error_message='Username is required when not using authentication token',
                    )

            repos = []
            cutoff_date = datetime.now() - timedelta(days=days)

            # 업데이트 시간 기준 내림차순 정렬
            for repo in user.get_repos(sort='updated', direction='desc'):
                if len(repos) >= limit:
                    break

                # 기간 내 업데이트된 저장소만 포함
                if repo.updated_at >= cutoff_date:
                    repos.append(
                        GitHubRepository(
                            name=repo.name,
                            full_name=repo.full_name,
                            description=repo.description,
                            url=repo.html_url,
                            updated_at=repo.updated_at.isoformat(),
                            pushed_at=repo.pushed_at.isoformat()
                            if repo.pushed_at
                            else None,
                            language=repo.language,
                            stars=repo.stargazers_count,
                            forks=repo.forks_count,
                        )
                    )

            return RepositoryResponse(
                status='success',
                data=repos,
                count=len(repos),
                message=f'Successfully retrieved {len(repos)} repositories updated in the last {days} days',
            )
        except Exception as e:
            return RepositoryResponse(
                status='error',
                message=f'Failed to get repositories: {e!s}',
                error_message=f'Failed to get repositories: {e!s}',
            )

    def get_recent_commits(
        self, repo_name: str, days: int | None = None, limit: int | None = None
    ) -> CommitResponse:
        """특정 저장소의 최근 커밋을 조회합니다.

        Args:
            repo_name: 저장소 이름 ('owner/repo' 형식).
            days: 조회할 기간 (일 단위, 기본값: 7일).
            limit: 반환할 최대 커밋 수 (기본값: 10).

        Returns:
            CommitResponse: 상태, 커밋 목록, 메타데이터를 포함합니다.
        """
        # 기본값 설정
        if days is None:
            days = 7
        if limit is None:
            limit = 10

        try:
            github = self._get_github_client()

            repo = github.get_repo(repo_name)
            commits = []
            cutoff_date = datetime.now() - timedelta(days=days)

            # 기간 내 커밋 조회
            for commit in repo.get_commits(since=cutoff_date):
                if len(commits) >= limit:
                    break

                commits.append(
                    GitHubCommit(
                        sha=commit.sha[:8],  # SHA 앞 8자리만 표시
                        message=commit.commit.message.split('\n')[
                            0
                        ],  # 첫 번째 줄만 사용
                        author=commit.commit.author.name,
                        date=commit.commit.author.date.isoformat(),
                        url=commit.html_url,
                    )
                )

            return CommitResponse(
                status='success',
                data=commits,
                count=len(commits),
                message=f'Successfully retrieved {len(commits)} commits for repository {repo_name} in the last {days} days',
            )
        except Exception as e:
            return CommitResponse(
                status='error',
                message=f'Failed to get commits: {e!s}',
                error_message=f'Failed to get commits: {e!s}',
            )

    def search_repositories(
        self, query: str, sort: str | None = None, limit: int | None = None
    ) -> RepositoryResponse:
        """활발한 활동이 있는 저장소를 검색합니다.

        최근 30일 내에 푸시가 있었던 저장소만 검색 결과에 포함됩니다.

        Args:
            query: 검색 쿼리 문자열.
            sort: 정렬 방법 ('updated', 'stars', 'forks' 중 선택, 기본값: 'updated').
            limit: 반환할 최대 저장소 수 (기본값: 10).

        Returns:
            RepositoryResponse: 상태, 검색 결과, 메타데이터를 포함합니다.
        """
        # 기본값 설정
        if sort is None:
            sort = 'updated'
        if limit is None:
            limit = 10

        try:
            github = self._get_github_client()

            # 최근 활동 필터를 쿼리에 추가 (30일 내 푸시)
            search_query = f'{query} pushed:>={datetime.now() - timedelta(days=30):%Y-%m-%d}'

            repos = []
            results = github.search_repositories(
                query=search_query, sort=sort, order='desc'
            )

            for repo in results[:limit]:
                repos.append(
                    GitHubRepository(
                        name=repo.name,
                        full_name=repo.full_name,
                        description=repo.description,
                        url=repo.html_url,
                        updated_at=repo.updated_at.isoformat(),
                        pushed_at=repo.pushed_at.isoformat()
                        if repo.pushed_at
                        else None,
                        language=repo.language,
                        stars=repo.stargazers_count,
                        forks=repo.forks_count,
                    )
                )

            return RepositoryResponse(
                status='success',
                data=repos,
                count=len(repos),
                message=f'Successfully searched for {len(repos)} repositories matching "{query}"',
            )
        except Exception as e:
            return RepositoryResponse(
                status='error',
                message=f'Failed to search repositories: {e!s}',
                error_message=f'Failed to search repositories: {e!s}',
            )

    def get_tools(self) -> dict[str, Any]:
        """OpenAI 함수 호출용 도구 딕셔너리를 반환합니다.

        Returns:
            dict: 도구 이름을 키로, 도구 인스턴스를 값으로 하는 딕셔너리.
        """
        return {
            'get_user_repositories': self,
            'get_recent_commits': self,
            'search_repositories': self,
        }
