"""Branch management service for creating and managing feature branches."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..core.config import get_config
from ..core.logging_ import get_logger
from ..github import GitHubClient

logger = get_logger(__name__)

config = get_config()


@dataclass
class BranchInfo:
    """Branch information."""
    name: str
    sha: str
    is_default: bool
    is_protected: bool
    commit_message: str
    commit_author: str
    commit_date: datetime


@dataclass
class BranchCreationResult:
    """Result of branch creation."""
    success: bool
    branch_name: str
    sha: str
    error: Optional[str] = None


class BranchManager:
    """Manages GitHub repository branches."""

    BRANCH_PREFIXES = {
        "feature": "feature/",
        "bugfix": "bugfix/",
        "hotfix": "hotfix/",
        "release": "release/",
        "docs": "docs/",
        "refactor": "refactor/",
        "review": "review/",
    }

    DEFAULT_PATTERNS = [
        "main",
        "master",
        "develop",
        "dev",
        "production",
    ]

    def __init__(self, github_client: GitHubClient):
        self.github = github_client

    async def create_branch(
        self,
        full_name: str,
        branch_name: str,
        source_branch: str = "main",
        prefix: Optional[str] = None,
    ) -> BranchCreationResult:
        """Create a new branch from a source branch."""
        try:
            full_branch_name = f"{prefix}{branch_name}" if prefix else branch_name

            if await self.branch_exists(full_name, full_branch_name):
                logger.info(f"Branch {full_branch_name} already exists in {full_name}")
                return BranchCreationResult(
                    success=True,
                    branch_name=full_branch_name,
                    sha="",
                    error="Branch already exists",
                )

            success = await self.github.create_branch(
                full_name=full_name,
                branch_name=full_branch_name,
                source_branch=source_branch,
            )

            if success:
                logger.info(f"Created branch {full_branch_name} in {full_name}")
                return BranchCreationResult(
                    success=True,
                    branch_name=full_branch_name,
                    sha="",
                    error=None,
                )
            else:
                return BranchCreationResult(
                    success=False,
                    branch_name=full_branch_name,
                    sha="",
                    error="Failed to create branch",
                )

        except Exception as e:
            logger.error(f"Error creating branch: {e}")
            return BranchCreationResult(
                success=False,
                branch_name=branch_name,
                sha="",
                error=str(e),
            )

    async def branch_exists(self, full_name: str, branch_name: str) -> bool:
        """Check if a branch exists."""
        try:
            from github import GithubException

            repo = self.github.client.get_repo(full_name)
            repo.get_branch(branch_name)
            return True

        except Exception:
            return False

    async def get_branch_info(self, full_name: str, branch_name: str) -> Optional[BranchInfo]:
        """Get information about a branch."""
        try:
            from github import GithubException

            repo = self.github.client.get_repo(full_name)
            branch = repo.get_branch(branch_name)

            return BranchInfo(
                name=branch.name,
                sha=branch.commit.sha,
                is_default=branch.name == repo.default_branch,
                is_protected=branch.protected,
                commit_message=branch.commit.commit.message,
                commit_author=branch.commit.commit.author.name,
                commit_date=branch.commit.commit.author.date,
            )

        except Exception as e:
            logger.error(f"Error getting branch info: {e}")
            return None

    async def list_branches(
        self, full_name: str, limit: int = 100
    ) -> List[BranchInfo]:
        """List all branches in a repository."""
        try:
            repo = self.github.client.get_repo(full_name)
            branches = []

            for branch in repo.get_branches()[:limit]:
                branches.append(
                    BranchInfo(
                        name=branch.name,
                        sha=branch.commit.sha,
                        is_default=branch.name == repo.default_branch,
                        is_protected=branch.protected,
                        commit_message=branch.commit.commit.message,
                        commit_author=branch.commit.commit.author.name,
                        commit_date=branch.commit.commit.author.date,
                    )
                )

            return branches

        except Exception as e:
            logger.error(f"Error listing branches: {e}")
            return []

    async def delete_branch(self, full_name: str, branch_name: str) -> bool:
        """Delete a branch."""
        try:
            from github import GithubException

            if branch_name in self.DEFAULT_PATTERNS:
                logger.warning(f"Cannot delete default branch: {branch_name}")
                return False

            repo = self.github.client.get_repo(full_name)
            ref = f"refs/heads/{branch_name}"
            repo.get_git_ref(ref).delete()
            logger.info(f"Deleted branch {branch_name} from {full_name}")
            return True

        except Exception as e:
            logger.error(f"Error deleting branch: {e}")
            return False

    def generate_branch_name(
        self,
        prefix: str,
        identifier: str,
        max_length: int = 50,
    ) -> str:
        """Generate a standardized branch name."""
        clean_identifier = identifier.lower()
        clean_identifier = "".join(
            c if c.isalnum() or c in "-_" else "-" for c in clean_identifier
        )
        clean_identifier = "-".join(
            filter(None, clean_identifier.split("-"))
        )[:max_length]

        if prefix in self.BRANCH_PREFIXES:
            prefix = self.BRANCH_PREFIXES[prefix]

        branch_name = f"{prefix}{clean_identifier}"

        return branch_name

    async def create_feature_branch(
        self,
        full_name: str,
        feature_name: str,
        source_branch: str = "main",
    ) -> BranchCreationResult:
        """Create a feature branch."""
        branch_name = self.generate_branch_name("feature", feature_name)
        return await self.create_branch(
            full_name=full_name,
            branch_name=branch_name,
            source_branch=source_branch,
            prefix="",
        )

    async def create_review_branch(
        self,
        full_name: str,
        repo_name: str,
        review_type: str = "status",
    ) -> BranchCreationResult:
        """Create a branch for review updates."""
        branch_name = self.generate_branch_name(
            "review",
            f"{repo_name}-{review_type}",
        )
        return await self.create_branch(
            full_name=full_name,
            branch_name=branch_name,
            source_branch="main",
            prefix="",
        )

    async def get_default_branch(self, full_name: str) -> str:
        """Get the default branch name for a repository."""
        try:
            repo = self.github.client.get_repo(full_name)
            return repo.default_branch
        except Exception:
            return "main"

    async def get_recent_branches(
        self, full_name: str, days: int = 30, limit: int = 20
    ) -> List[BranchInfo]:
        """Get recently updated branches."""
        from datetime import timedelta

        cutoff = datetime.utcnow() - timedelta(days=days)
        all_branches = await self.list_branches(full_name, limit=100)

        recent = [
            b for b in all_branches
            if b.commit_date and b.commit_date >= cutoff
        ]

        return sorted(recent, key=lambda b: b.commit_date, reverse=True)[:limit]

    def is_protected_branch(self, branch_name: str) -> bool:
        """Check if a branch name matches protected patterns."""
        return branch_name.lower() in [p.lower() for p in self.DEFAULT_PATTERNS]
