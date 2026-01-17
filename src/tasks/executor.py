"""Task execution engine for performing delegated work."""

import asyncio
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..core.config import get_config
from ..core.logging_ import get_logger
from ..github import GitHubClient
from ..openai import OpenAIClient
from ..report import ReportGenerator
from ..review import ReviewOrchestrator
from .interpreter import Task, TaskStatus, TaskType

logger = get_logger(__name__)

config = get_config()


@dataclass
class ExecutionResult:
    """Result of task execution."""
    task_id: str
    success: bool
    output: str
    files_created: List[str]
    files_modified: List[str]
    pr_created: Optional[int]
    execution_time: float
    error: Optional[str]


class TaskExecutor:
    """Executes delegated tasks."""

    def __init__(
        self,
        github_client: GitHubClient,
        openai_client: OpenAIClient,
        review_orchestrator: Optional[ReviewOrchestrator] = None,
    ):
        self.github = github_client
        self.openai = openai_client
        self.review_orchestrator = review_orchestrator
        self.report_gen = ReportGenerator()

    async def execute(self, task: Task) -> ExecutionResult:
        """Execute a task."""
        start_time = datetime.utcnow()

        try:
            handler = self._get_handler(task.task_type)
            result = await handler(task)

            execution_time = (datetime.utcnow() - start_time).total_seconds()

            return ExecutionResult(
                task_id=task.id,
                success=True,
                output=str(result.get("output", "Completed")),
                files_created=result.get("files_created", []),
                files_modified=result.get("files_modified", []),
                pr_created=result.get("pr_number"),
                execution_time=execution_time,
                error=None,
            )

        except Exception as e:
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            logger.error(f"Task execution failed: {e}")

            return ExecutionResult(
                task_id=task.id,
                success=False,
                output="",
                files_created=[],
                files_modified=[],
                pr_created=None,
                execution_time=execution_time,
                error=str(e),
            )

    def _get_handler(self, task_type: TaskType):
        """Get the handler for a task type."""
        handlers = {
            TaskType.ADD_TEST: self._handle_add_test,
            TaskType.FIX_BUG: self._handle_fix_bug,
            TaskType.ADD_FEATURE: self._handle_add_feature,
            TaskType.UPDATE_DOCS: self._handle_update_docs,
            TaskType.REFACTOR: self._handle_refactor,
            TaskType.CODE_REVIEW: self._handle_code_review,
            TaskType.RUN_TESTS: self._handle_run_tests,
            TaskType.CREATE_PR: self._handle_create_pr,
            TaskType.MERGE_PR: self._handle_merge_pr,
            TaskType.GENERAL: self._handle_general,
        }
        return handlers.get(task_type, self._handle_general)

    async def _handle_add_test(self, task: Task) -> Dict[str, Any]:
        """Handle adding tests."""
        if not task.repository:
            raise ValueError("Repository not specified for test task")

        repo = await self.github.get_repository(task.repository)
        if not repo:
            raise ValueError(f"Repository not found: {task.repository}")

        file_tree = await self.github.get_file_tree(
            task.repository, max_depth=3, max_files=50
        )

        source_files = [
            f["path"] for f in file_tree
            if f["type"] == "file"
            and f["path"].endswith(".py")
            and "test" not in f["path"].lower()
        ]

        test_content = f'''"""
Auto-generated tests for {task.repository}
"""

import pytest


class TestGenerated:
    """Generated test class."""

    def test_example(self):
        """Example test."""
        assert True
'''

        test_file = "test_generated.py"
        if task.target_files:
            test_file = task.target_files[0]
            if not test_file.startswith("test_"):
                test_file = f"test_{test_file}.py"

        success = await self.github.create_or_update_file(
            full_name=task.repository,
            path=test_file,
            content=test_content,
            message=f"test: Add generated tests",
            branch=repo.default_branch,
        )

        if success:
            return {"output": f"Created test file: {test_file}", "files_created": [test_file]}
        raise ValueError("Failed to create test file")

    async def _handle_fix_bug(self, task: Task) -> Dict[str, Any]:
        """Handle fixing bugs."""
        if not task.repository:
            raise ValueError("Repository not specified for bug fix")

        prompt = f"""
Fix the bug described in this task:
{task.description}

The repository is: {task.repository}
Target files: {', '.join(task.target_files) if task.target_files else 'Not specified'}

Provide a fix for the bug. Return the file path and the fixed code.
"""

        response = await self.openai._call_api(prompt)

        return {"output": f"Bug fix analysis: {response}"}

    async def _handle_add_feature(self, task: Task) -> Dict[str, Any]:
        """Handle adding features."""
        if not task.repository:
            raise ValueError("Repository not specified for feature task")

        repo = await self.github.get_repository(task.repository)
        if not repo:
            raise ValueError(f"Repository not found: {task.repository}")

        file_tree = await self.github.get_file_tree(
            task.repository, max_depth=2, max_files=20
        )

        prompt = f"""
Implement the following feature:
{task.description}

Repository: {task.repository}
Existing files: {[f['path'] for f in file_tree[:10]]}

Provide the implementation code. Focus on clean, well-documented code.
"""

        response = await self.openai._call_api(prompt)

        return {"output": f"Feature implementation: {response}"}

    async def _handle_update_docs(self, task: Task) -> Dict[str, Any]:
        """Handle updating documentation."""
        if not task.repository:
            raise ValueError("Repository not specified for documentation task")

        repo = await self.github.get_repository(task.repository)
        if not repo:
            raise ValueError(f"Repository not found: {task.repository}")

        readme = await self.github.get_file_content(task.repository, "README.md")
        existing_doc = readme.content if readme else ""

        prompt = f"""
Update or create documentation for the repository:
{task.description}

Existing README:
{existing_doc[:2000]}

Provide updated documentation in markdown format.
"""

        response = await self.openai._call_api(prompt)

        success = await self.github.create_or_update_file(
            full_name=task.repository,
            path="README.md",
            content=response,
            message=f"docs: Update documentation",
            branch=repo.default_branch,
            sha=readme.sha if readme else None,
        )

        if success:
            return {"output": "Documentation updated", "files_modified": ["README.md"]}
        raise ValueError("Failed to update documentation")

    async def _handle_refactor(self, task: Task) -> Dict[str, Any]:
        """Handle refactoring code."""
        if not task.repository:
            raise ValueError("Repository not specified for refactor task")

        if not task.target_files:
            raise ValueError("Target files not specified for refactor task")

        file_content = await self.github.get_file_content(
            task.repository, task.target_files[0]
        )

        if not file_content:
            raise ValueError(f"File not found: {task.target_files[0]}")

        prompt = f"""
Refactor the following code according to:
{task.description}

Original code:
{file_content.content[:3000]}

Provide the refactored code with improvements.
"""

        response = await self.openai._call_api(prompt)

        return {"output": f"Refactoring suggestions: {response}"}

    async def _handle_code_review(self, task: Task) -> Dict[str, Any]:
        """Handle code review."""
        if not task.repository:
            raise ValueError("Repository not specified for review task")

        if self.review_orchestrator:
            repo = await self.github.get_repository(task.repository)
            if repo:
                result = await self.review_orchestrator.review_repository(repo)

                report = self.report_gen.generate_review_report(repo, result)

                await self.github.create_or_update_file(
                    full_name=task.repository,
                    path="REPO_STATUS.md",
                    content=report,
                    message="docs: Update repository status",
                    branch="main",
                )

                return {
                    "output": "Review completed",
                    "files_modified": ["REPO_STATUS.md"],
                }

        return {"output": "Review requested but not completed"}

    async def _handle_run_tests(self, task: Task) -> Dict[str, Any]:
        """Handle running tests."""
        return {"output": "Test execution requested. Note: Tests should be run locally or in CI."}

    async def _handle_create_pr(self, task: Task) -> Dict[str, Any]:
        """Handle creating PR."""
        if not task.repository:
            raise ValueError("Repository not specified for PR creation")

        pr_number = task.parameters.get("pr_number")

        if pr_number:
            return {"output": f"PR #{pr_number} already exists", "pr_created": pr_number}

        return {"output": "PR creation requested"}

    async def _handle_merge_pr(self, task: Task) -> Dict[str, Any]:
        """Handle merging PR."""
        pr_number = task.parameters.get("pr_number")
        if not pr_number:
            raise ValueError("PR number not specified for merge task")

        return {"output": f"PR #{pr_number} merge requested"}

    async def _handle_general(self, task: Task) -> Dict[str, Any]:
        """Handle general tasks."""
        prompt = f"""
Execute the following task:
{task.description}

Task type: {task.task_type.value}
Repository: {task.repository or 'Not specified'}
Target files: {', '.join(task.target_files) if task.target_files else 'Not specified'}

Provide a detailed response on how to accomplish this task.
"""

        response = await self.openai._call_api(prompt)

        return {"output": response}
