"""Script to sync all REPO_STATUS.md files from GitHub to the database."""

import asyncio
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.core.config import get_config
from src.core.database import Database
from src.core.logging_ import get_logger
from src.github import GitHubClient

logger = get_logger(__name__)
config = get_config()


def parse_repo_status(content: str) -> Dict[str, Any]:
    """Parse a REPO_STATUS.md file and extract structured data."""
    if not content:
        return {}

    result = {
        "status": "unknown",
        "overall_score": 0,
        "summary": "",
        "stuck_areas": [],
        "next_steps": [],
        "issues": [],
        "last_updated": None,
    }

    # Extract status from Summary section
    summary_match = re.search(r"## Summary\s*\n(.+?)(?:\n##|$)", content, re.DOTALL)
    if summary_match:
        summary_text = summary_match.group(1).strip()
        result["summary"] = summary_text[:500]
        # Determine status based on summary content
        if "verified and updated" in summary_text.lower():
            result["status"] = "completed"
        elif "incomplete" in summary_text.lower():
            result["status"] = "incomplete"
        elif "needs review" in summary_text.lower():
            result["status"] = "needs_review"
        elif "no issues" in summary_text.lower() or "no critical" in summary_text.lower():
            result["status"] = "healthy"

    # Extract quality scores from table format: | **Overall** | `███` 0% |
    score_patterns = {
        "overall": r"\*\*Overall\*\*.*?(\d+)\s*%",
        "code_quality": r"Code Quality.*?(\d+)\s*%",
        "documentation": r"Documentation.*?(\d+)\s*%",
        "structure": r"Structure.*?(\d+)\s*%",
        "testing": r"Testing.*?(\d+)\s*%",
    }

    for key, pattern in score_patterns.items():
        match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
        if match:
            result[f"{key}_score"] = int(match.group(1))

    # Extract stuck areas
    stuck_section = re.search(r"## Stuck Areas?\s*\n([\s\S]*?)(?:\n##|\n\n##|$)", content)
    if stuck_section:
        areas_text = stuck_section.group(1)
        if "no stuck areas" not in areas_text.lower():
            areas = re.findall(r"[-•*]\s*(.+)", areas_text)
            result["stuck_areas"] = [a.strip() for a in areas if a.strip()]

    # Extract next steps
    next_steps_section = re.search(r"## Next Steps?\s*\n([\s\S]*?)(?:\n##|\n\n##|$)", content)
    if next_steps_section:
        steps_text = next_steps_section.group(1)
        if "no specific next steps" not in steps_text.lower():
            steps = re.findall(r"[-•*]\s*(.+)", steps_text)
            result["next_steps"] = [s.strip() for s in steps if s.strip()]

    # Extract issues
    issues_section = re.search(r"## Issues? Found?\s*\n([\s\S]*?)(?:\n##|\n\n##|$)", content)
    if issues_section:
        issues_text = issues_section.group(1)
        if "no critical issues" not in issues_text.lower() and "no issues" not in issues_text.lower():
            issues = re.findall(r"[-•*]\s*(.+)", issues_text)
            result["issues"] = [i.strip() for i in issues if i.strip()]

    # Extract generated date
    date_match = re.search(r"Generated:\s*(\d{4}-\d{2}-\d{2})", content)
    if date_match:
        try:
            result["last_updated"] = datetime.strptime(date_match.group(1), "%Y-%m-%d")
        except ValueError:
            pass

    return result


async def sync_repo_status():
    """Sync all REPO_STATUS.md files to the database."""
    db = Database()
    github = GitHubClient()

    await db.connect()

    logger.info("Fetching all repositories from GitHub...")
    repos = await github.list_all_repositories()
    logger.info(f"Found {len(repos)} repositories")

    synced = 0
    errors = []

    for repo in repos:
        full_name = repo.full_name
        logger.info(f"Processing: {full_name}")

        try:
            # Get the REPO_STATUS.md file
            status_file = await github.get_file_content(full_name, "REPO_STATUS.md")

            if not status_file:
                logger.warning(f"No REPO_STATUS.md found for {full_name}")
                continue

            # Parse the content
            parsed = parse_repo_status(status_file.content)

            # Save repository using db method
            repo_data = {
                "name": repo.name,
                "full_name": full_name,
                "description": repo.description,
                "html_url": repo.html_url,
                "clone_url": repo.clone_url,
                "language": repo.language,
                "is_private": int(repo.is_private),
                "is_archived": int(repo.is_archived),
                "is_fork": int(repo.is_fork),
                "stargazers_count": repo.stargazers_count,
                "forks_count": repo.forks_count,
                "open_issues_count": repo.open_issues_count,
                "created_at": repo.created_at,
                "updated_at": repo.updated_at,
                "last_reviewed_at": parsed.get("last_updated") or datetime.utcnow(),
            }

            await db.save_repository(repo_data)

            # Get the repository from database
            db_repo = await db.get_repository(full_name)
            if db_repo:
                # Save review session
                review_result = {
                    "status": parsed.get("status", "completed"),
                    "overall_score": parsed.get("overall_score", 0),
                    "quality_score": parsed.get("code_quality_score", 0),
                    "documentation_score": parsed.get("documentation_score", 0),
                    "structure_score": parsed.get("structure_score", 0),
                    "testing_score": parsed.get("testing_score", 0),
                    "summary": parsed.get("summary", "")[:1000],
                    "stuck_areas": str(parsed.get("stuck_areas", [])),
                    "next_steps": str(parsed.get("next_steps", [])),
                }

                await db.save_review_session(db_repo, review_result)

                logger.info(f"  ✓ Synced: {full_name} | Status: {parsed.get('status')} | Score: {parsed.get('overall_score')}")
                synced += 1
            else:
                errors.append(full_name)

        except Exception as e:
            logger.error(f"  ✗ Error processing {full_name}: {e}")
            errors.append(full_name)

    await db.close()

    logger.info(f"\n{'='*50}")
    logger.info(f"Sync complete!")
    logger.info(f"  Synced: {synced} repositories")
    logger.info(f"  Errors: {len(errors)}")
    logger.info(f"{'='*50}")

    return synced, errors


if __name__ == "__main__":
    asyncio.run(sync_repo_status())
