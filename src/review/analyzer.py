"""Code analysis engine for repository review."""

import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..core.config import get_config
from ..core.logging_ import get_logger
from ..github import GitHubClient, FileContent
from ..openai import OpenAIClient

logger = get_logger(__name__)

config = get_config()


@dataclass
class FileAnalysis:
    """Analysis result for a single file."""
    path: str
    file_type: str
    lines_of_code: int
    issues: List[Dict[str, Any]] = field(default_factory=list)
    todos: List[Dict[str, Any]] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    functions: List[str] = field(default_factory=list)
    classes: List[str] = field(default_factory=list)
    quality_score: int = 50
    summary: str = ""


class CodeAnalyzer:
    """Service for analyzing code in repositories."""

    def __init__(self, github_client: GitHubClient, openai_client: OpenAIClient):
        self.github = github_client
        self.openai = openai_client

    async def analyze_file(self, content: str, path: str) -> FileAnalysis:
        """Analyze a single file."""
        analysis = FileAnalysis(
            path=path,
            file_type=self._get_file_type(path),
            lines_of_code=len(content.splitlines()),
        )

        analysis.imports = self._extract_imports(content, path)
        analysis.functions = self._extract_functions(content, path)
        analysis.classes = self._extract_classes(content, path)
        analysis.todos = self._find_todos(content)

        quality_issues = self._find_quality_issues(content, path)
        analysis.issues.extend(quality_issues)

        analysis.quality_score = self._calculate_quality_score(analysis)

        if content:
            ai_result = await self.openai.analyze_code(content, path)
            if isinstance(ai_result, dict):
                if "issues" in ai_result and isinstance(ai_result["issues"], list):
                    # Only extend with dict issues, skip strings
                    valid_issues = [i for i in ai_result["issues"] if isinstance(i, dict)]
                    analysis.issues.extend(valid_issues)
                if "summary" in ai_result and isinstance(ai_result["summary"], str):
                    analysis.summary = ai_result["summary"]
                if "quality_score" in ai_result and isinstance(ai_result["quality_score"], (int, float)):
                    analysis.quality_score = int(ai_result["quality_score"])

        return analysis

    async def analyze_repository(
        self, full_name: str, files: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Analyze multiple files in a repository."""
        file_analyses: List[FileAnalysis] = []
        all_issues: List[Dict[str, Any]] = []
        all_todos: List[Dict[str, Any]] = []

        prioritized_files = self._prioritize_files(files)

        for file_info in prioritized_files[: config.review.max_files_per_repo]:
            file_content = await self.github.get_file_content(
                full_name, file_info["path"]
            )

            if file_content and self._should_analyze(file_info["path"]):
                analysis = await self.analyze_file(
                    file_content.content, file_info["path"]
                )
                file_analyses.append(analysis)
                all_issues.extend(analysis.issues)
                all_todos.extend(analysis.todos)

        return {
            "files_analyzed": len(file_analyses),
            "total_lines": sum(a.lines_of_code for a in file_analyses),
            "file_analyses": [self._analysis_to_dict(a) for a in file_analyses],
            "all_issues": all_issues,
            "all_todos": all_todos,
            "quality_breakdown": self._aggregate_quality(file_analyses),
        }

    def _get_file_type(self, path: str) -> str:
        """Determine file type from path."""
        ext = os.path.splitext(path)[1].lower()
        type_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".go": "go",
            ".rs": "rust",
            ".java": "java",
            ".cpp": "cpp",
            ".c": "c",
            ".h": "c",
            ".md": "markdown",
            ".json": "json",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".txt": "text",
            ".html": "html",
            ".css": "css",
            ".sql": "sql",
        }
        return type_map.get(ext, "unknown")

    def _should_analyze(self, path: str) -> bool:
        """Determine if a file should be analyzed."""
        for pattern in config.review.exclude_patterns:
            if pattern.endswith("/"):
                if pattern[:-1] in path.split("/"):
                    return False
            elif "*" in pattern:
                import fnmatch
                if fnmatch.fnmatch(path, pattern):
                    return False
            elif pattern in path:
                return False

        ext = os.path.splitext(path)[1]
        return ext in config.review.include_extensions

    def _prioritize_files(
        self, files: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Prioritize files for analysis."""
        priority_order = [
            "README.md",
            "setup.py",
            "pyproject.toml",
            "requirements.txt",
            "package.json",
            "go.mod",
            "Cargo.toml",
            "src/main.py",
            "main.py",
            "index.py",
            "app.py",
        ]

        def get_priority(file: Dict[str, Any]) -> int:
            name = file["name"]
            if name in priority_order:
                return priority_order.index(name)
            if file["type"] == "file":
                return 100
            return 200

        return sorted(files, key=get_priority)

    def _extract_imports(self, content: str, path: str) -> List[str]:
        """Extract import statements from code."""
        imports = []
        ext = os.path.splitext(path)[1].lower()

        if ext == ".py":
            import re
            patterns = [
                r"^import\s+(\w+)",
                r"^from\s+(\w+)\s+import",
                r"^import\s+(\w+(?:\.\w+)*)",
            ]
            for pattern in patterns:
                matches = re.findall(pattern, content, re.MULTILINE)
                imports.extend(matches[:10])

        elif ext in (".js", ".ts"):
            import re
            patterns = [
                r"require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)",
                r"import\s+(?:\{[^}]*\}|\*\s+as\s+\w+|\w+)\s+from\s+['\"]([^'\"]+)['\"]",
            ]
            for pattern in patterns:
                matches = re.findall(pattern, content)
                imports.extend(matches[:10])

        return list(set(imports))[:20]

    def _extract_functions(self, content: str, path: str) -> List[str]:
        """Extract function definitions from code."""
        functions = []
        ext = os.path.splitext(path)[1].lower()

        if ext == ".py":
            import re
            matches = re.findall(r"^def\s+(\w+)", content, re.MULTILINE)
            functions.extend(matches)

        elif ext in (".js", ".ts"):
            import re
            patterns = [
                r"function\s+(\w+)",
                r"const\s+(\w+)\s*=\s*(?:async\s*)?function",
                r"=>\s*function\s*(\w+)",
            ]
            for pattern in patterns:
                matches = re.findall(pattern, content)
                functions.extend(matches)

        return functions[:30]

    def _extract_classes(self, content: str, path: str) -> List[str]:
        """Extract class definitions from code."""
        classes = []
        ext = os.path.splitext(path)[1].lower()

        if ext == ".py":
            import re
            matches = re.findall(r"^class\s+(\w+)", content, re.MULTILINE)
            classes.extend(matches)

        elif ext in (".js", ".ts"):
            import re
            matches = re.findall(r"class\s+(\w+)", content)
            classes.extend(matches)

        return classes[:20]

    def _find_todos(self, content: str) -> List[Dict[str, Any]]:
        """Find TODO and FIXME comments."""
        todos = []
        import re

        patterns = [
            (r"TODO[:\s]+(.+)", "todo"),
            (r"FIXME[:\s]+(.+)", "fixme"),
            (r"HACK[:\s]+(.+)", "hack"),
            (r"XXX[:\s]+(.+)", "xxx"),
            (r"BUG[:\s]+(.+)", "bug"),
        ]

        for pattern, tag in patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches:
                todos.append({
                    "type": tag,
                    "description": match.strip(),
                    "priority": "high" if tag in ("fixme", "bug") else "medium",
                })

        return todos

    def _find_quality_issues(self, content: str, path: str) -> List[Dict[str, Any]]:
        """Find common quality issues."""
        issues = []
        ext = os.path.splitext(path)[1].lower()

        import re

        if ext == ".py":
            long_lines = [(i + 1, len(line))
                          for i, line in enumerate(content.splitlines())
                          if len(line) > 120]
            for line_num, length in long_lines[:5]:
                issues.append({
                    "file": path,
                    "type": "style",
                    "line": line_num,
                    "description": f"Line exceeds 120 characters ({length} chars)",
                    "severity": "low",
                })

            if "print(" in content and "debug" not in path.lower():
                issues.append({
                    "file": path,
                    "type": "code-smell",
                    "description": "print statements found (likely debug code)",
                    "severity": "low",
                })

        return issues[:10]

    def _calculate_quality_score(self, analysis: FileAnalysis) -> int:
        """Calculate quality score for a file."""
        score = 100

        score -= len(analysis.issues) * 5
        score -= len([t for t in analysis.todos if t["priority"] == "high"]) * 3
        score -= len([t for t in analysis.todos if t["priority"] != "high"]) * 1

        if analysis.lines_of_code > 500:
            score -= 10
        elif analysis.lines_of_code > 200:
            score -= 5

        if not analysis.imports and analysis.file_type not in ("markdown", "text"):
            score -= 5

        return max(0, min(100, score))

    def _aggregate_quality(
        self, analyses: List[FileAnalysis]
    ) -> Dict[str, float]:
        """Aggregate quality scores across files."""
        if not analyses:
            return {
                "overall": 0,
                "code_quality": 0,
                "documentation": 0,
                "structure": 0,
                "testing": 0,
            }

        avg_score = sum(a.quality_score for a in analyses) / len(analyses)

        doc_files = [a for a in analyses if a.file_type == "markdown"]
        doc_score = (
            sum(a.quality_score for a in doc_files) / len(doc_files)
            if doc_files
            else avg_score
        )

        return {
            "overall": avg_score,
            "code_quality": avg_score,
            "documentation": doc_score,
            "structure": avg_score,
            "testing": avg_score,
        }

    def _analysis_to_dict(self, analysis: FileAnalysis) -> Dict[str, Any]:
        """Convert FileAnalysis to dictionary."""
        return {
            "path": analysis.path,
            "file_type": analysis.file_type,
            "lines_of_code": analysis.lines_of_code,
            "issues": analysis.issues,
            "todos": analysis.todos,
            "imports": analysis.imports,
            "functions": analysis.functions,
            "classes": analysis.classes,
            "quality_score": analysis.quality_score,
            "summary": analysis.summary,
        }
