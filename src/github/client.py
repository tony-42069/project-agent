"""GitHub API client with rate limiting and retry logic."""

import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from github import Github
from github.Repository import Repository as GithubRepo
from tenacity import (
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .config import get_config
from .logging_ import get_logger

logger = get_logger(__name__)

config = get_config()


@dataclass
class RateLimitInfo:
    """Rate limit information."""
    remaining: int
    limit: int
    reset_at: datetime
    used: int


@dataclass
class FileContent:
    """File content information."""
    path: str
    content: str
    size: int
    sha: str
    encoding: str


@dataclass
class Repository:
    """Repository information."""
    name: str
    full_name: str
    description: Optional[str]
    html_url: str
    clone_url: str
    language: Optional[str]
    is_private: bool
    is_archived: bool
    is_fork: bool
    stargazers_count: int
    forks_count: int
    open_issues_count: int
    created_at: datetime
    updated_at: datetime
    default_branch: str

    @classmethod
    def from_github(cls, repo: GithubRepo) -> "Repository":
        """Create Repository from PyGithub object."""
        return cls(
            name=repo.name,
            full_name=repo.full_name,
            description=repo.description,
            html_url=repo.html_url,
            clone_url=repo.clone_url,
            language=repo.language,
            is_private=repo.private,
            is_archived=repo.archived,
            is_fork=repo.fork,
            stargazers_count=repo.stargazers_count,
            forks_count=repo.forks_count,
            open_issues_count=repo.open_issues_count,
            created_at=repo.created_at,
            updated_at=repo.updated_at,
            default_branch=repo.default_branch,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage."""
        return {
            "name": self.name,
            "full_name": self.full_name,
            "description": self.description,
            "html_url": self.html_url,
            "clone_url": self.clone_url,
            "language": self.language,
            "is_private": int(self.is_private),
            "is_archived": int(self.is_archived),
            "is_fork": int(self.is_fork),
            "stargazers_count": self.stargazers_count,
            "forks_count": self.forks_count,
            "open_issues_count": self.open_issues_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class GitHubClient:
    """GitHub API client with rate limiting and retry logic."""

    def __init__(self, token: Optional[str] = None):
        self.token = token or os.getenv(config.github.token_env)
        if not self.token:
            raise ValueError(f"GitHub token not set. Set {config.github.token_env}")

        self.client = Github(
            login_or_token=self.token,
            timeout=config.github.timeout,
        )
        self._rate_limit_info: Optional[RateLimitInfo] = None

    def _handle_rate_limit(self) -> None:
        """Handle rate limiting by waiting if necessary."""
        rate_limit = self.client.get_rate_limit()
        core = rate_limit.core

        self._rate_limit_info = RateLimitInfo(
            remaining=core.remaining,
            limit=core.limit,
            reset_at=core.reset,
            used=core.used,
        )

        if core.remaining < 10:
            wait_time = (core.reset - datetime.utcnow()).total_seconds()
            if wait_time > 0:
                logger.warning(f"Rate limit low ({core.remaining}). Waiting {wait_time:.1f}s")
                time.sleep(min(wait_time + 1, 60))

    def _retry_strategy(self) -> Retrying:
        """Create retry strategy for API calls."""
        return Retrying(
            stop=stop_after_attempt(config.github.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(Exception),
            reraise=True,
        )

    async def list_all_repositories(self, include_forks: bool = False) -> List[Repository]:
        """List all repositories for the authenticated user."""
        repositories = []
        user = self.client.get_user()

        self._handle_rate_limit()

        for repo in user.get_repos(type="all"):
            self._handle_rate_limit()

            if repo.archived and not include_forks:
                continue

            if repo.fork and not include_forks:
                continue

            repositories.append(Repository.from_github(repo))

        logger.info(f"Found {len(repositories)} repositories")
        return repositories

    async def get_repository(self, full_name: str) -> Optional[Repository]:
        """Get a specific repository by full name."""
        try:
            self._handle_rate_limit()
            repo = self.client.get_repo(full_name)
            return Repository.from_github(repo)
        except Exception as e:
            logger.error(f"Failed to get repository {full_name}: {e}")
            return None

    async def get_file_content(
        self, full_name: str, path: str
    ) -> Optional[FileContent]:
        """Get the content of a file from a repository."""
        try:
            self._handle_rate_limit()
            repo = self.client.get_repo(full_name)
            file_content = repo.get_contents(path)

            if isinstance(file_content, list):
                return None

            return FileContent(
                path=file_content.path,
                content=file_content.decoded_content.decode("utf-8"),
                size=file_content.size,
                sha=file_content.sha,
                encoding=file_content.encoding,
            )
        except Exception as e:
            logger.debug(f"Failed to get file {path} from {full_name}: {e}")
            return None

    async def list_directory(
        self, full_name: str, path: str = ""
    ) -> List[Dict[str, Any]]:
        """List contents of a directory in a repository."""
        contents = []
        try:
            self._handle_rate_limit()
            repo = self.client.get_repo(full_name)
            files = repo.get_contents(path)

            for file in files:
                contents.append({
                    "name": file.name,
                    "path": file.path,
                    "type": file.type,
                    "size": file.size,
                    "sha": file.sha,
                })

        except Exception as e:
            logger.error(f"Failed to list directory {path} in {full_name}: {e}")

        return contents

    async def get_file_tree(
        self, full_name: str, max_depth: int = 3, max_files: int = 100
    ) -> List[Dict[str, Any]]:
        """Get a tree of files from a repository."""
        tree = []
        visited = set()

        async def crawl(path: str, depth: int):
            if depth > max_depth or len(tree) >= max_files:
                return

            files = await self.list_directory(full_name, path)
            for file in files:
                if file["path"] in visited:
                    continue
                visited.add(file["path"])
                tree.append(file)

                if file["type"] == "dir" and depth < max_depth:
                    await crawl(file["path"], depth + 1)

        await crawl("", 0)
        return tree

    async def create_branch(
        self, full_name: str, branch_name: str, source_branch: str = "main"
    ) -> bool:
        """Create a new branch from an existing branch."""
        try:
            self._handle_rate_limit()
            repo = self.client.get_repo(full_name)

            source = repo.get_branch(source_branch)
            repo.create_git_ref(
                ref=f"refs/heads/{branch_name}",
                sha=source.commit.sha,
            )
            logger.info(f"Created branch {branch_name} in {full_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to create branch {branch_name} in {full_name}: {e}")
            return False

    async def create_or_update_file(
        self,
        full_name: str,
        path: str,
        content: str,
        message: str,
        branch: str = "main",
        sha: Optional[str] = None,
    ) -> bool:
        """Create or update a file in a repository."""
        try:
            self._handle_rate_limit()
            repo = self.client.get_repo(full_name)

            if sha:
                repo.update_file(path, message, content, sha, branch=branch)
            else:
                repo.create_file(path, message, content, branch=branch)

            logger.info(f"{'Updated' if sha else 'Created'} file {path} in {full_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to create/update file {path} in {full_name}: {e}")
            return False

    async def create_pull_request(
        self,
        full_name: str,
        title: str,
        body: str,
        head: str,
        base: str = "main",
    ) -> Optional[int]:
        """Create a pull request."""
        try:
            self._handle_rate_limit()
            repo = self.client.get_repo(full_name)
            pr = repo.create_pull(title=title, body=body, head=head, base=base)
            logger.info(f"Created PR #{pr.number} in {full_name}")
            return pr.number

        except Exception as e:
            logger.error(f"Failed to create PR in {full_name}: {e}")
            return None

    def get_rate_limit_info(self) -> Optional[RateLimitInfo]:
        """Get current rate limit information."""
        return self._rate_limit_info
