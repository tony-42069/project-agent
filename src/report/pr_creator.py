"""Pull request creation and management service."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..core.config import get_config
from ..core.logging_ import get_logger
from ..github import GitHubClient
from .branch_manager import BranchManager
from .pr_content_generator import PRContentGenerator, PRContent

logger = get_logger(__name__)

config = get_config()


@dataclass
class PRInfo:
    """Pull request information."""
    number: int
    title: str
    body: str
    state: str
    head_branch: str
    base_branch: str
    html_url: str
    created_at: datetime
    merged_at: Optional[datetime]
    closed_at: Optional[datetime]
    author: str


@dataclass
 class PRCreationResult:
    """Result of PR creation."""
    success: bool
    pr_number: Optional[int]
    pr_url: Optional[str]
    error: Optional[str] = None


class PRCreator:
    """Creates and manages pull requests."""

    def __init__(self, github_client: GitHubClient):
        self.github = github_client
        self.branch_manager = BranchManager(github_client)
        self.content_generator = PRContentGenerator()

    async def create_pr(
        self,
        full_name: str,
        title: str,
        body: str,
        head: str,
        base: str = "main",
        draft: bool = True,
    ) -> PRCreationResult:
        """Create a pull request."""
        try:
            pr_number = await self.github.create_pull_request(
                full_name=full_name,
                title=title,
                body=body,
                head=head,
                base=base,
            )

            if pr_number:
                repo = self.github.client.get_repo(full_name)
                pr = repo.get_pull(pr_number)

                if draft:
                    pr.create_review_draft(
                        event="COMMENT",
                        body="Draft PR - ready for review"
                    )

                logger.info(f"Created PR #{pr_number} in {full_name}")
                return PRCreationResult(
                    success=True,
                    pr_number=pr_number,
                    pr_url=pr.html_url,
                    error=None,
                )
            else:
                return PRCreationResult(
                    success=False,
                    pr_number=None,
                    pr_url=None,
                    error="Failed to create PR",
                )

        except Exception as e:
            logger.error(f"Error creating PR: {e}")
            return PRCreationResult(
                success=False,
                pr_number=None,
                pr_url=None,
                error=str(e),
            )

    async def create_review_pr(
        self,
        full_name: str,
        repo_name: str,
        review_result: Dict[str, Any],
        branch_name: str = "main",
        create_branch: bool = True,
    ) -> PRCreationResult:
        """Create a PR with review results."""
        try:
            default_branch = await self.branch_manager.get_default_branch(full_name)

            if create_branch:
                branch_result = await self.branch_manager.create_review_branch(
                    full_name=full_name,
                    repo_name=repo_name,
                    review_type="status",
                )

                if not branch_result.success and "already exists" not in str(branch_result.error):
                    return PRCreationResult(
                        success=False,
                        pr_number=None,
                        pr_url=None,
                        error=f"Failed to create branch: {branch_result.error}",
                    )

                head_branch = branch_result.branch_name
            else:
                head_branch = branch_name

            pr_content = self.content_generator.generate_review_pr_content(
                repo_name=repo_name,
                review_result=review_result,
            )

            return await self.create_pr(
                full_name=full_name,
                title=pr_content.title,
                body=pr_content.body,
                head=head_branch,
                base=default_branch,
                draft=True,
            )

        except Exception as e:
            logger.error(f"Error creating review PR: {e}")
            return PRCreationResult(
                success=False,
                pr_number=None,
                pr_url=None,
                error=str(e),
            )

    async def create_pr_from_content(
        self,
        full_name: str,
        content: PRContent,
        head_branch: str,
        base_branch: str = "main",
    ) -> PRCreationResult:
        """Create a PR using pre-generated content."""
        return await self.create_pr(
            full_name=full_name,
            title=content.title,
            body=content.body,
            head=head_branch,
            base=base_branch,
            draft=True,
        )

    async def get_pr_info(self, full_name: str, pr_number: int) -> Optional[PRInfo]:
        """Get information about a pull request."""
        try:
            repo = self.github.client.get_repo(full_name)
            pr = repo.get_pull(pr_number)

            return PRInfo(
                number=pr.number,
                title=pr.title,
                body=pr.body,
                state=pr.state,
                head_branch=pr.head.ref,
                base_branch=pr.base.ref,
                html_url=pr.html_url,
                created_at=pr.created_at,
                merged_at=pr.merged_at,
                closed_at=pr.closed_at,
                author=pr.user.login,
            )

        except Exception as e:
            logger.error(f"Error getting PR info: {e}")
            return None

    async def list_prs(
        self,
        full_name: str,
        state: str = "open",
        limit: int = 30,
    ) -> List[PRInfo]:
        """List pull requests in a repository."""
        try:
            repo = self.github.client.get_repo(full_name)

            prs = []
            for pr in repo.get_pulls(state=state)[:limit]:
                prs.append(
                    PRInfo(
                        number=pr.number,
                        title=pr.title,
                        body=pr.body,
                        state=pr.state,
                        head_branch=pr.head.ref,
                        base_branch=pr.base.ref,
                        html_url=pr.html_url,
                        created_at=pr.created_at,
                        merged_at=pr.merged_at,
                        closed_at=pr.closed_at,
                        author=pr.user.login,
                    )
                )

            return prs

        except Exception as e:
            logger.error(f"Error listing PRs: {e}")
            return []

    async def update_pr(
        self,
        full_name: str,
        pr_number: int,
        title: Optional[str] = None,
        body: Optional[str] = None,
    ) -> bool:
        """Update a pull request."""
        try:
            repo = self.github.client.get_repo(full_name)
            pr = repo.get_pull(pr_number)

            if title:
                pr.edit(title=title)
            if body:
                pr.edit(body=body)

            logger.info(f"Updated PR #{pr_number} in {full_name}")
            return True

        except Exception as e:
            logger.error(f"Error updating PR: {e}")
            return False

    async def add_comment(
        self,
        full_name: str,
        pr_number: int,
        comment: str,
    ) -> bool:
        """Add a comment to a pull request."""
        try:
            repo = self.github.client.get_repo(full_name)
            pr = repo.get_pull(pr_number)
            pr.create_issue_comment(comment)
            return True

        except Exception as e:
            logger.error(f"Error adding comment: {e}")
            return False

    async def close_pr(
        self,
        full_name: str,
        pr_number: int,
        comment: Optional[str] = None,
    ) -> bool:
        """Close a pull request."""
        try:
            repo = self.github.client.get_repo(full_name)
            pr = repo.get_pull(pr_number)
            pr.edit(state="closed")

            if comment:
                pr.create_issue_comment(comment)

            logger.info(f"Closed PR #{pr_number} in {full_name}")
            return True

        except Exception as e:
            logger.error(f"Error closing PR: {e}")
            return False

    async def merge_pr(
        self,
        full_name: str,
        pr_number: int,
        merge_method: str = "squash",
        commit_title: Optional[str] = None,
    ) -> bool:
        """Merge a pull request."""
        try:
            repo = self.github.client.get_repo(full_name)
            pr = repo.get_pull(pr_number)

            if pr.mergeable:
                merged = pr.merge(
                    merge_method=merge_method,
                    commit_title=commit_title,
                )

                if merged:
                    logger.info(f"Merged PR #{pr_number} in {full_name}")
                    return True

            logger.warning(f"PR #{pr_number} not mergeable")
            return False

        except Exception as e:
            logger.error(f"Error merging PR: {e}")
            return False

    async def add_labels(
        self,
        full_name: str,
        pr_number: int,
        labels: List[str],
    ) -> bool:
        """Add labels to a pull request."""
        try:
            repo = self.github.client.get_repo(full_name)
            pr = repo.get_pull(pr_number)

            for label in labels:
                try:
                    repo.get_label(label)
                    pr.add_to_labels(label)
                except Exception:
                    logger.warning(f"Label '{label}' not found in repository")

            return True

        except Exception as e:
            logger.error(f"Error adding labels: {e}")
            return False

    async def request_reviews(
        self,
        full_name: str,
        pr_number: int,
        reviewers: List[str],
    ) -> bool:
        """Request reviews for a pull request."""
        try:
            repo = self.github.client.get_repo(full_name)
            pr = repo.get_pull(pr_number)

            pr.create_review_requests(reviewers=reviewers)
            logger.info(f"Requested reviews for PR #{pr_number}")
            return True

        except Exception as e:
            logger.error(f"Error requesting reviews: {e}")
            return False

    def get_content_generator(self) -> PRContentGenerator:
        """Get the PR content generator."""
        return self.content_generator
