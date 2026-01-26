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

    # Extract status
    status_match = re.search(r"\*\*Status[:\s]*[:\*]*\s*(.+?)(?:\n|\*\*|$)", content, re.IGNORECASE)
    if status_match:
        result["status"] = status_match.group(1).strip().strip("*")

    # Extract quality scores
    score_patterns = {
        "overall": r"Overall[:\s]+(\d+)",
        "code_quality": r"Code Quality[:\s]+(\d+)",
        "documentation": r"Documentation[:\s]+(\d+)",
        "structure": r"Structure[:\s]+(\d+)",
        "testing": r"Testing[:\s]+(\d+)",
    }
    for key, pattern in score_patterns.items():
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            result[f"{key}_score"] = int(match.group(1))

    if "overall" not in result or result["overall_score"] == 0:
        overall_match = re.search(r"Quality Score[:\s]*[:\*]*\s*(\d+)/?(\d*)", content, re.IGNORECASE)
        if overall_match:
            result["overall_score"] = int(overall_match.group(1))

    # Extract summary
    summary_match = re.search(r"## Summary\s*\n(.+?)(?:\n##|$)", content, re.DOTALL)
    if summary_match:
        result["summary"] = summary_match.group(1).strip()[:500]

    # Extract stuck areas
    stuck_section = re.search(r"Stuck Areas?[:\s]*\n([\s\S]*?)(?:\n##|\n###|$)", content, re.IGNORECASE)
    if stuck_section:
        areas = re.findall(r"[-•*]\s*(.+)", stuck_section.group(1))
        result["stuck_areas"] = [a.strip() for a in areas if a.strip()]

    # Extract next steps
    next_steps_section = re.search(r"Next Steps?[:\s]*\n([\s\S]*?)(?:\n##|\n###|$)", content, re.IGNORECASE)
    if next_steps_section:
        steps = re.findall(r"[-•*]\s*(.+)", next_steps_section.group(1))
        result["next_steps"] = [s.strip() for s in steps if s.strip()]

    # Extract issues
    issues_section = re.search(r"Issues? Found[:\s]*\n([\s\S]*?)(?:\n##|\n###|$)", content, re.IGNORECASE)
    if issues_section:
        issues = re.findall(r"[-•*]\s*(.+)", issues_section.group(1))
        result["issues"] = [i.strip() for i in issues if i.strip()]

    # Extract last updated date
    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", content)
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

            # Upsert into repositories table
            await db.execute(
                """
                INSERT INTO repositories (name, full_name, description, html_url, 
                                         clone_url, language, is_private, is_archived,
                                         is_fork, stargazers_count, forks_count, 
                                         open_issues_count, created_at, updated_at, 
                                         last_reviewed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(full_name) DO UPDATE SET
                    description = excluded.description,
                    language = excluded.language,
                    is_archived = excluded.is_archived,
                    stargazers_count = excluded.stargazers_count,
                    forks_count = excluded.forks_count,
                    open_issues_count = excluded.open_issues_count,
                    updated_at = excluded.updated_at,
                    last_reviewed_at = excluded.last_reviewed_at
                """,
                (
                    repo.name,
                    full_name,
                    repo.description,
                    repo.html_url,
                    repo.clone_url,
                    repo.language,
                    int(repo.is_private),
                    int(repo.is_archived),
                    int(repo.is_fork),
                    repo.stargazers_count,
                    repo.forks_count,
                    repo.open_issues_count,
                    repo.created_at,
                    repo.updated_at,
                    parsed.get("last_updated") or datetime.utcnow(),
                ),
            )

            # Get repository ID
            result = await db.fetchone(
                "SELECT id FROM repositories WHERE full_name = ?", (full_name,)
            )
            if result:
                repo_id = result[0]

                # Insert review session
                await db.execute(
                    """
                    INSERT INTO review_sessions (repository_id, status, overall_score,
                                                quality_score, documentation_score,
                                                structure_score, testing_score, summary,
                                                stuck_areas, next_steps, started_at, 
                                                completed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        repo_id,
                        parsed.get("status", "unknown"),
                        parsed.get("overall_score", 0),
                        parsed.get("code_quality_score", 0),
                        parsed.get("documentation_score", 0),
                        parsed.get("structure_score", 0),
                        parsed.get("testing_score", 0),
                        parsed.get("summary", "")[:1000],
                        str(parsed.get("stuck_areas", [])),
                        str(parsed.get("next_steps", [])),
                        parsed.get("last_updated") or datetime.utcnow(),
                        datetime.utcnow(),
                    ),
                )

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
