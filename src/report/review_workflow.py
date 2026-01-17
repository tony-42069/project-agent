"""Review workflow management for pull requests."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..core.config import get_config
from ..core.logging_ import get_logger
from ..github import GitHubClient
from .pr_creator import PRCreator, PRInfo

logger = get_logger(__name__)

config = get_config()


@dataclass
class ReviewComment:
    """A review comment."""
    id: int
    path: str
    line: int
    body: str
    author: str
    created_at: datetime
    status: str


@dataclass
class ReviewState:
    """State of a review."""
    pr_number: int
    status: str
    comments: List[ReviewComment]
    approvals: int
    requested_changes: int
    review_started_at: datetime
    last_updated: datetime


@dataclass
class ReviewAction:
    """Action to take on a review."""
    action: str
    body: str
    event: str
    line: Optional[int]
    path: Optional[str]


class ReviewWorkflow:
    """Manages the review workflow for pull requests."""

    def __init__(self, github_client: GitHubClient):
        self.github = github_client
        self.pr_creator = PRCreator(github_client)

    async def get_review_state(
        self, full_name: str, pr_number: int
    ) -> Optional[ReviewState]:
        """Get the current review state of a PR."""
        try:
            pr_info = await self.pr_creator.get_pr_info(full_name, pr_number)
            if not pr_info:
                return None

            repo = self.github.client.get_repo(full_name)
            pr = repo.get_pull(pr_number)

            comments = []
            for comment in pr.get_comments():
                comments.append(
                    ReviewComment(
                        id=comment.id,
                        path=comment.path,
                        line=comment.line or 0,
                        body=comment.body,
                        author=comment.user.login,
                        created_at=comment.created_at,
                        status=comment.state,
                    )
                )

            approvals = 0
            requested_changes = 0

            for review in pr.get_reviews():
                if review.state == "APPROVED":
                    approvals += 1
                elif review.state == "CHANGES_REQUESTED":
                    requested_changes += 1

            return ReviewState(
                pr_number=pr_number,
                status=pr.state,
                comments=comments,
                approvals=approvals,
                requested_changes=requested_changes,
                review_started_at=pr.created_at,
                last_updated=datetime.utcnow(),
            )

        except Exception as e:
            logger.error(f"Error getting review state: {e}")
            return None

    async def submit_review(
        self,
        full_name: str,
        pr_number: int,
        event: str,
        body: str = "",
        comments: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        """Submit a review for a pull request."""
        try:
            repo = self.github.client.get_repo(full_name)
            pr = repo.get_pull(pr_number)

            if comments:
                pr.create_review(
                    body=body,
                    event=event,
                    comments=comments,
                )
            else:
                pr.create_review(
                    body=body,
                    event=event,
                )

            logger.info(f"Submitted {event} review for PR #{pr_number}")
            return True

        except Exception as e:
            logger.error(f"Error submitting review: {e}")
            return False

    async def approve_pr(
        self,
        full_name: str,
        pr_number: int,
        body: str = "LGTM! Approved by Project Agent.",
    ) -> bool:
        """Approve a pull request."""
        return await self.submit_review(
            full_name=full_name,
            pr_number=pr_number,
            event="APPROVE",
            body=body,
        )

    async def request_changes(
        self,
        full_name: str,
        pr_number: int,
        body: str = "Changes requested by Project Agent.",
        comments: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        """Request changes on a pull request."""
        return await self.submit_review(
            full_name=full_name,
            pr_number=pr_number,
            event="REQUEST_CHANGES",
            body=body,
            comments=comments,
        )

    async def comment_on_pr(
        self,
        full_name: str,
        pr_number: int,
        body: str,
        commit_id: Optional[str] = None,
        path: Optional[str] = None,
        line: Optional[int] = None,
    ) -> bool:
        """Add a general comment to a PR."""
        try:
            repo = self.github.client.get_repo(full_name)
            pr = repo.get_pull(pr_number)

            if path and line:
                pr.create_comment(body, path=path, line=line)
            else:
                pr.create_issue_comment(body)

            return True

        except Exception as e:
            logger.error(f"Error commenting on PR: {e}")
            return False

    async def check_mergeable(
        self, full_name: str, pr_number: int
    ) -> Dict[str, Any]:
        """Check if a PR is mergeable."""
        try:
            repo = self.github.client.get_repo(full_name)
            pr = repo.get_pull(pr_number)

            checks = {
                "mergeable": pr.mergeable,
                "mergeable_state": pr.mergeable_state,
                "rebaseable": pr.rebaseable,
                "draft": pr.draft,
                "conflicts": pr.mergeable_state == "dirty",
                "can_merge": pr.mergeable and pr.mergeable_state in ("clean", "unstable"),
            }

            if not checks["mergeable"]:
                checks["message"] = "PR has merge conflicts"
            elif checks["mergeable_state"] == "dirty":
                checks["message"] = "PR has merge conflicts"
            elif not checks["can_merge"]:
                checks["message"] = f"PR in {pr.mergeable_state} state"

            return checks

        except Exception as e:
            logger.error(f"Error checking mergeable: {e}")
            return {"error": str(e)}

    async def schedule_merge(
        self,
        full_name: str,
        pr_number: int,
        merge_method: str = "squash",
        delay_hours: int = 0,
    ) -> Dict[str, Any]:
        """Schedule a PR to be merged after a delay."""
        result = {
            "scheduled": False,
            "pr_number": pr_number,
            "merge_method": merge_method,
            "delay_hours": delay_hours,
            "message": "",
        }

        checks = await self.check_mergeable(full_name, pr_number)
        if not checks.get("can_merge"):
            result["message"] = f"Cannot schedule merge: {checks.get('message', 'Unknown error')}"
            return result

        if delay_hours > 0:
            result["message"] = f"Merge scheduled in {delay_hours} hours"
            result["scheduled"] = True
        else:
            success = await self.pr_creator.merge_pr(
                full_name=full_name,
                pr_number=pr_number,
                merge_method=merge_method,
            )
            result["merged"] = success
            result["message"] = "PR merged" if success else "Failed to merge PR"

        return result

    async def get_review_history(
        self, full_name: str, pr_number: int
    ) -> List[Dict[str, Any]]:
        """Get the review history of a PR."""
        try:
            repo = self.github.client.get_repo(full_name)
            pr = repo.get_pull(pr_number)

            history = []
            for review in pr.get_reviews():
                history.append({
                    "id": review.id,
                    "user": review.user.login,
                    "state": review.state,
                    "body": review.body,
                    "submitted_at": review.submitted_at.isoformat() if review.submitted_at else None,
                    "commit_id": review.commit_id,
                })

            return history

        except Exception as e:
            logger.error(f"Error getting review history: {e}")
            return []

    async def auto_review_pr(
        self,
        full_name: str,
        pr_number: int,
        review_result: Dict[str, Any],
    ) -> bool:
        """Automatically review a PR based on analysis."""
        try:
            checks = await self.check_mergeable(full_name, pr_number)

            if not checks.get("can_merge"):
                await self.request_changes(
                    full_name=full_name,
                    pr_number=pr_number,
                    body=f"Cannot merge PR: {checks.get('message', 'Merge conflicts detected')}",
                )
                return False

            issues = review_result.get("issues_found", [])
            critical_issues = [i for i in issues if i.get("severity") == "high"]

            if critical_issues:
                await self.request_changes(
                    full_name=full_name,
                    pr_number=pr_number,
                    body=f"Found {len(critical_issues)} critical issues that must be addressed before merging.",
                )
                return False

            await self.approve_pr(
                full_name=full_name,
                pr_number=pr_number,
                body=f"Auto-approved by Project Agent. Quality score: {review_result.get('quality_scores', {}).get('overall', 0):.0f}%",
            )
            return True

        except Exception as e:
            logger.error(f"Error in auto review: {e}")
            return False

    async def get_pending_reviews(
        self, full_name: str
    ) -> List[PRInfo]:
        """Get all PRs awaiting review."""
        prs = await self.pr_creator.list_prs(full_name, state="open")

        pending = []
        for pr in prs:
            state = await self.get_review_state(full_name, pr.number)
            if state and state.approvals == 0:
                pending.append(pr)

        return pending

    def generate_review_report(self, state: ReviewState) -> str:
        """Generate a text report of the review state."""
        lines = [
            f"Review Report for PR #{state.pr_number}",
            "=" * 40,
            f"Status: {state.status}",
            f"Approvals: {state.approvals}",
            f"Changes Requested: {state.requested_changes}",
            f"Comments: {len(state.comments)}",
            f"Review Started: {state.review_started_at.isoformat()}",
            "",
            "Comments:",
        ]

        for comment in state.comments:
            lines.append(f"  - {comment.author}: {comment.body[:50]}")

        return "\n".join(lines)
