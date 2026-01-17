"""Commit report files to repositories."""

from datetime import datetime
from typing import Any, Dict, Optional

from ..core.config import get_config
from ..core.logging_ import get_logger
from ..github import GitHubClient, Repository

logger = get_logger(__name__)

config = get_config()


class RepoCommitter:
    """Commits generated reports to repositories."""

    def __init__(self, github_client: GitHubClient):
        self.github = github_client

    async def commit_report(
        self,
        repo: Repository,
        report_content: str,
        branch_name: Optional[str] = None,
    ) -> bool:
        """Commit a report to the repository."""
        # Use repo's default branch if no branch specified
        branch = branch_name or repo.default_branch or "main"
        file_path = "REPO_STATUS.md"

        try:
            existing_content = await self.github.get_file_content(
                repo.full_name, file_path
            )
            sha = existing_content.sha if existing_content else None
        except Exception:
            sha = None

        success = await self.github.create_or_update_file(
            full_name=repo.full_name,
            path=file_path,
            content=report_content,
            message=config.report.commit_message,
            branch=branch,
            sha=sha,
        )

        if success:
            logger.info(f"Committed report to {repo.full_name}")
        else:
            logger.error(f"Failed to commit report to {repo.full_name}")

        return success

    async def create_feature_branch(
        self, repo: Repository, branch_name: str, source_branch: str = "main"
    ) -> bool:
        """Create a feature branch for updates."""
        return await self.github.create_branch(
            full_name=repo.full_name,
            branch_name=branch_name,
            source_branch=source_branch,
        )

    async def commit_multiple_files(
        self,
        repo: Repository,
        files: Dict[str, str],
        commit_message: str,
        branch: str = "main",
    ) -> bool:
        """Commit multiple files to a repository."""
        for path, content in files.items():
            success = await self.github.create_or_update_file(
                full_name=repo.full_name,
                path=path,
                content=content,
                message=commit_message,
                branch=branch,
            )
            if not success:
                logger.error(f"Failed to commit {path} to {repo.full_name}")
                return False

        logger.info(f"Committed {len(files)} files to {repo.full_name}")
        return True

    async def create_pr(
        self,
        repo: Repository,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str = "main",
    ) -> int:
        """Create a pull request for committed changes."""
        pr_number = await self.github.create_pull_request(
            full_name=repo.full_name,
            title=title,
            body=body,
            head=head_branch,
            base=base_branch,
        )

        if pr_number:
            logger.info(f"Created PR #{pr_number} in {repo.full_name}")
        else:
            logger.error(f"Failed to create PR in {repo.full_name}")

        return pr_number or 0

    async def update_readme(
        self,
        repo: Repository,
        status_badge: str,
        section_content: str,
    ) -> bool:
        """Update README with status information."""
        try:
            existing_content = await self.github.get_file_content(
                repo.full_name, "README.md"
            )
            sha = existing_content.sha if existing_content else None
            current_content = existing_content.content if existing_content else ""

            if existing_content:
                if status_badge not in current_content:
                    new_content = f"{status_badge}\n\n## Project Status\n\n{section_content}\n\n{current_content}"
                else:
                    new_content = current_content
            else:
                new_content = f"""# {repo.name}

{status_badge}

## Project Status

{section_content}

---
*This file was updated by Project Agent*
"""

            return await self.github.create_or_update_file(
                full_name=repo.full_name,
                path="README.md",
                content=new_content,
                message="docs: Update project status badge",
                branch=repo.default_branch,
                sha=sha,
            )

        except Exception as e:
            logger.error(f"Failed to update README for {repo.full_name}: {e}")
            return False
