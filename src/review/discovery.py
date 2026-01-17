"""Repository discovery service for scanning GitHub repositories."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..core.config import get_config
from ..core.logging_ import get_logger
from ..github import GitHubClient, Repository

logger = get_logger(__name__)

config = get_config()


@dataclass
class ScanResult:
    """Result of a repository scan."""
    total_repos: int
    public_repos: int
    private_repos: int
    archived_repos: int
    forked_repos: int
    scanned_at: datetime
    repos: List[Repository]


class RepoDiscovery:
    """Service for discovering and scanning repositories."""

    def __init__(self, github_client: GitHubClient):
        self.github = github_client
        self._repo_cache: Dict[str, Repository] = {}

    async def discover_all(
        self,
        include_forks: bool = False,
        include_archived: bool = False,
        max_repos: Optional[int] = None,
    ) -> ScanResult:
        """Discover all repositories for the authenticated user."""
        logger.info("Starting repository discovery...")

        all_repos = await self.github.list_all_repositories(include_forks=include_forks)

        filtered_repos = []
        for repo in all_repos:
            if repo.is_archived and not include_archived:
                continue

            if repo.is_fork and not include_forks:
                continue

            filtered_repos.append(repo)
            self._repo_cache[repo.full_name] = repo

        public_repos = sum(1 for r in filtered_repos if not r.is_private)
        private_repos = sum(1 for r in filtered_repos if r.is_private)
        archived_repos = sum(1 for r in filtered_repos if r.is_archived)
        forked_repos = sum(1 for r in filtered_repos if r.is_fork)

        if max_repos:
            filtered_repos = filtered_repos[:max_repos]

        result = ScanResult(
            total_repos=len(filtered_repos),
            public_repos=public_repos,
            private_repos=private_repos,
            archived_repos=archived_repos,
            forked_repos=forked_repos,
            scanned_at=datetime.utcnow(),
            repos=filtered_repos,
        )

        logger.info(
            f"Discovery complete: {result.total_repos} repos "
            f"({result.public_repos} public, {result.private_repos} private)"
        )

        return result

    async def discover_by_topic(self, topic: str) -> List[Repository]:
        """Discover repositories with a specific topic."""
        repos = []
        all_repos = await self.github.list_all_repositories()

        for repo in all_repos:
            if topic.lower() in repo.full_name.lower():
                repos.append(repo)

        logger.info(f"Found {len(repos)} repos matching topic: {topic}")
        return repos

    async def discover_by_language(self, language: str) -> List[Repository]:
        """Discover repositories by programming language."""
        repos = []
        all_repos = await self.github.list_all_repositories()

        for repo in all_repos:
            if repo.language and repo.language.lower() == language.lower():
                repos.append(repo)

        logger.info(f"Found {len(repos)} {language} repositories")
        return repos

    async def get_repository(self, full_name: str) -> Optional[Repository]:
        """Get a specific repository by full name."""
        if full_name in self._repo_cache:
            return self._repo_cache[full_name]

        repo = await self.github.get_repository(full_name)
        if repo:
            self._repo_cache[full_name] = repo

        return repo

    def get_cached_repos(self) -> Dict[str, Repository]:
        """Get all cached repositories."""
        return self._repo_cache.copy()

    def clear_cache(self) -> None:
        """Clear the repository cache."""
        self._repo_cache.clear()
        logger.info("Repository cache cleared")

    async def scan_for_activity(
        self, days: int = 30
    ) -> List[Repository]:
        """Find repositories with recent activity."""
        from datetime import timedelta

        cutoff = datetime.utcnow() - timedelta(days=days)
        active_repos = []

        all_repos = await self.github.list_all_repositories()

        for repo in all_repos:
            if repo.updated_at and repo.updated_at >= cutoff:
                active_repos.append(repo)

        active_repos.sort(key=lambda r: r.updated_at, reverse=True)

        logger.info(f"Found {len(active_repos)} repos with activity in last {days} days")
        return active_repos

    def categorize_repos(self, repos: List[Repository]) -> Dict[str, List[Repository]]:
        """Categorize repositories by various criteria."""
        categories = {
            "by_language": {},
            "by_status": {
                "archived": [],
                "active": [],
                "forked": [],
                "official": [],
            },
            "by_visibility": {
                "public": [],
                "private": [],
            },
        }

        for repo in repos:
            lang = repo.language or "Unknown"
            if lang not in categories["by_language"]:
                categories["by_language"][lang] = []
            categories["by_language"][lang].append(repo)

            if repo.is_archived:
                categories["by_status"]["archived"].append(repo)
            elif repo.is_fork:
                categories["by_status"]["forked"].append(repo)
            else:
                categories["by_status"]["official"].append(repo)
                categories["by_status"]["active"].append(repo)

            if repo.is_private:
                categories["by_visibility"]["private"].append(repo)
            else:
                categories["by_visibility"]["public"].append(repo)

        return categories

    def generate_report(self, scan_result: ScanResult) -> str:
        """Generate a text report of the discovery results."""
        lines = [
            "Repository Discovery Report",
            "=" * 40,
            f"Scanned at: {scan_result.scanned_at.isoformat()}",
            "",
            "Summary:",
            f"  Total Repositories: {scan_result.total_repos}",
            f"  Public: {scan_result.public_repos}",
            f"  Private: {scan_result.private_repos}",
            f"  Archived: {scan_result.archived_repos}",
            f"  Forked: {scan_result.forked_repos}",
            "",
            "Repositories:",
        ]

        for repo in scan_result.repos:
            visibility = "🔒" if repo.is_private else "📦"
            archived = "📦" if repo.is_archived else ""
            lines.append(
                f"  {visibility} {archived} {repo.full_name} "
                f"({repo.language or 'N/A'})"
            )

        return "\n".join(lines)
