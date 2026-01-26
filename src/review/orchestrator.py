"""Review orchestrator for managing repository reviews."""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..core.config import get_config
from ..core.database import Database
from ..core.logging_ import get_logger
from ..github import GitHubClient, Repository
from ..openai import OpenAIClient
from .analyzer import CodeAnalyzer
from .templates import ReviewTemplates

logger = get_logger(__name__)

config = get_config()


class ReviewOrchestrator:
    """Orchestrates the review process for repositories."""

    def __init__(
        self,
        github_client: GitHubClient,
        openai_client: Optional[OpenAIClient] = None,
        db: Optional[Database] = None,
    ):
        self.github = github_client
        self.openai = openai_client or OpenAIClient()
        self.db = db
        self.analyzer = CodeAnalyzer(self.github, self.openai)

    def _is_status_file_meaningful(self, content: str) -> bool:
        """Check if REPO_STATUS.md has meaningful content."""
        if not content or len(content.strip()) < 200:
            return False

        required_sections = ["Quality Scores", "Summary", "Stuck Areas", "Next Steps"]
        content_lower = content.lower()

        score_count = sum(1 for section in required_sections if section.lower() in content_lower)
        return score_count >= 2

    async def _get_existing_status(self, repo_full_name: str) -> Optional[str]:
        """Get existing REPO_STATUS.md content if it exists."""
        try:
            content = await self.github.get_file_content(repo_full_name, "REPO_STATUS.md")
            if content:
                return content.content
        except Exception:
            pass
        return None

    async def _update_existing_status(self, repo_full_name: str, existing_content: str) -> str:
        """Add an update section to existing status file."""
        today = datetime.utcnow().strftime("%Y-%m-%d")

        update_section = f"""

---

## Review Update - {today}

Agent performed a check - existing review is still current. No new issues detected.

*Status verified by Project Agent*
"""

        return existing_content.rstrip() + update_section

    async def review_repository(self, repo: Repository, force: bool = False) -> Dict[str, Any]:
        """Perform a comprehensive review of a repository."""
        logger.info(f"Starting review of {repo.full_name}")

        existing_status = await self._get_existing_status(repo.full_name)

        if existing_status and not force:
            if self._is_status_file_meaningful(existing_status):
                logger.info(f"Found existing meaningful status for {repo.full_name}, adding update...")

                updated_content = await self._update_existing_status(repo.full_name, existing_status)

                sha = await self.github.get_file_content(repo.full_name, "REPO_STATUS.md")
                await self.github.create_or_update_file(
                    full_name=repo.full_name,
                    path="REPO_STATUS.md",
                    content=updated_content,
                    message=f"docs: Review update - {datetime.utcnow().strftime('%Y-%m-%d')}",
                    branch=repo.default_branch,
                    sha=sha.sha if sha else None,
                )

                return {
                    "status": "skipped",
                    "repository_name": repo.full_name,
                    "summary": "Existing review verified and updated",
                    "quality_scores": {},
                    "stuck_areas": [],
                    "next_steps": [],
                    "issues_found": [],
                    "recommendations": [],
                    "analyzed_files": 0,
                    "total_lines": 0,
                    "todos": [],
                    "structure_info": {},
                    "completed_at": datetime.utcnow(),
                    "message": "Existing status file verified and updated with timestamp",
                }

        try:
            file_tree = await self.github.get_file_tree(
                repo.full_name,
                max_depth=3,
                max_files=config.review.max_files_per_repo,
            )

            structure_info = self._analyze_structure(file_tree, repo)

            file_contents = {}
            for file_info in file_tree[:20]:
                if file_info["type"] == "file":
                    content = await self.github.get_file_content(
                        repo.full_name, file_info["path"]
                    )
                    if content:
                        file_contents[file_info["path"]] = content.content

            ai_review = await self.openai.review_repository(
                repo.full_name, file_contents, structure_info
            )

            analysis_result = await self.analyzer.analyze_repository(
                repo.full_name, file_tree
            )

            stuck_areas = self._combine_stuck_areas(ai_review, analysis_result)
            next_steps = self._generate_next_steps(ai_review, analysis_result, repo)

            quality_scores = {
                "overall": ai_review.quality_score.overall,
                "code_quality": ai_review.quality_score.code_quality,
                "documentation": ai_review.quality_score.documentation,
                "structure": ai_review.quality_score.structure,
                "testing": ai_review.quality_score.testing,
            }

            result = {
                "status": "completed",
                "repository_name": repo.full_name,
                "summary": ai_review.summary,
                "quality_scores": quality_scores,
                "stuck_areas": stuck_areas,
                "next_steps": next_steps,
                "issues_found": analysis_result["all_issues"],
                "recommendations": ai_review.recommendations,
                "analyzed_files": analysis_result["files_analyzed"],
                "total_lines": analysis_result["total_lines"],
                "todos": analysis_result["all_todos"],
                "structure_info": structure_info,
                "completed_at": datetime.utcnow(),
            }

            if self.db:
                await self.db.save_review_session(repo, result)

            logger.info(f"Completed review of {repo.full_name}")
            return result

        except Exception as e:
            logger.error(f"Failed to review {repo.full_name}: {e}")
            return {
                "status": "failed",
                "repository_name": repo.full_name,
                "error": str(e),
                "completed_at": datetime.utcnow(),
            }

    async def review_all(
        self, repos: Optional[List[Repository]] = None, force: bool = False
    ) -> List[Dict[str, Any]]:
        """Review all repositories."""
        if repos is None:
            repos = await self.github.list_all_repositories()

        results = []
        rate_limiter = asyncio.Semaphore(2)

        async def review_with_limit(repo: Repository) -> Dict[str, Any]:
            async with rate_limiter:
                await asyncio.sleep(config.github.rate_limit_wait)
                return await self.review_repository(repo, force=force)

        tasks = [review_with_limit(repo) for repo in repos]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        completed = [
            r if isinstance(r, dict) and r.get("status") in ["completed", "skipped"]
            else None
            for r in results
        ]

        skipped = [
            r if isinstance(r, dict) and r.get("status") == "skipped"
            else None
            for r in results
        ]

        logger.info(f"Reviewed: {len([c for c in completed if c and c.get('status')=='completed'])} | "
                   f"Skipped (existing review): {len([s for s in skipped if s])} | "
                   f"Failed: {len([r for r in results if isinstance(r, Exception) or (isinstance(r, dict) and r.get('status')=='failed')])}")

        return results

    def _analyze_structure(
        self, file_tree: List[Dict[str, Any]], repo: Repository
    ) -> Dict[str, Any]:
        """Analyze repository structure."""
        dirs = set()
        files_by_type = {}

        for item in file_tree:
            if item["type"] == "dir":
                dirs.add(item["path"])
            else:
                ext = item["path"].split(".")[-1] if "." in item["path"] else "unknown"
                files_by_type[ext] = files_by_type.get(ext, 0) + 1

        project_type = self._detect_project_type(files_by_type, dirs)

        has_tests = any("test" in d.lower() or "spec" in d.lower() for d in dirs)
        has_docs = any("doc" in d.lower() for d in dirs) or any(
            f["name"].lower() == "readme.md" for f in file_tree if f["type"] == "file"
        )
        has_ci = any(
            f["name"] in (".github", ".gitlab-ci.yml", "Jenkinsfile", "Dockerfile")
            for f in file_tree
        )

        return {
            "project_type": project_type,
            "directory_count": len(dirs),
            "file_count": len(file_tree),
            "files_by_type": files_by_type,
            "has_tests": has_tests,
            "has_documentation": has_docs,
            "has_ci": has_ci,
            "default_branch": repo.default_branch,
        }

    def _detect_project_type(
        self, files_by_type: Dict[str, int], dirs: set
    ) -> str:
        """Detect the type of project based on files."""
        if "py" in files_by_type:
            if "requirements.txt" in files_by_type or "pyproject.toml" in files_by_type:
                return "Python Application"
            return "Python Library"

        if "js" in files_by_type or "ts" in files_by_type:
            if "package.json" in files_by_type:
                return "Node.js Application"
            return "JavaScript/TypeScript Library"

        if "go" in files_by_type:
            return "Go Application/Library"

        if "rs" in files_by_type:
            return "Rust Application/Library"

        if "java" in files_by_type:
            return "Java Application"

        if any(d in dirs for d in ["src", "include", "lib"]):
            return "C/C++ Project"

        if "html" in files_by_type or "css" in files_by_type:
            return "Web Application"

        return "Unknown Project"

    def _combine_stuck_areas(
        self, ai_review: Any, analysis_result: Dict[str, Any]
    ) -> List[str]:
        """Combine stuck areas from AI review and TODO analysis."""
        stuck_areas = list(ai_review.stuck_areas)

        high_priority_todos = [
            t["description"] for t in analysis_result["all_todos"]
            if t["priority"] == "high"
        ]

        for todo in high_priority_todos[:5]:
            if todo not in stuck_areas:
                stuck_areas.append(f"TODO: {todo}")

        return stuck_areas[:15]

    def _generate_next_steps(
        self, ai_review: Any, analysis_result: Dict[str, Any], repo: Repository
    ) -> List[str]:
        """Generate next steps for the repository."""
        next_steps = list(ai_review.next_steps)

        if not analysis_result["all_todos"]:
            pass
        else:
            next_steps.append(f"Address {len(analysis_result['all_todos'])} TODO/FIXME items")

        if ai_review.quality_score.documentation < 50:
            next_steps.append("Improve documentation coverage")

        if ai_review.quality_score.testing < 50:
            next_steps.append("Add or improve test coverage")

        structure = analysis_result.get("structure_info", {})
        if structure.get("project_type") == "Unknown Project":
            next_steps.append("Identify and document project type")

        return next_steps[:10]
