"""OpenAI integration for code review and analysis."""

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion

from ..core.config import get_config
from ..core.logging_ import get_logger

logger = get_logger(__name__)

config = get_config()


def safe_parse_json(text: str) -> Dict[str, Any]:
    """Safely parse JSON from OpenAI response, handling markdown code blocks."""
    if not text or not text.strip():
        return {}

    text = text.strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to extract JSON from markdown code blocks
    patterns = [
        r'```json\s*([\s\S]*?)\s*```',
        r'```\s*([\s\S]*?)\s*```',
        r'\{[\s\S]*\}',
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            try:
                json_str = match.group(1) if '```' in pattern else match.group(0)
                return json.loads(json_str)
            except (json.JSONDecodeError, IndexError):
                continue

    # Return empty dict with error info if all parsing fails
    logger.warning(f"Failed to parse JSON from response: {text[:100]}...")
    return {"error": "Failed to parse response", "raw": text[:500]}


@dataclass
class QualityScore:
    """Quality scores for a repository."""
    overall: float
    code_quality: float
    documentation: float
    structure: float
    testing: float


@dataclass
class ReviewResult:
    """Result of a code review."""
    repository_name: str
    summary: str
    quality_score: QualityScore
    stuck_areas: List[str]
    next_steps: List[str]
    issues_found: List[Dict[str, Any]]
    recommendations: List[str]
    analyzed_files: int
    tokens_used: int
    completed_at: datetime


class ResponseCache:
    """Simple LRU cache for API responses."""

    def __init__(self, ttl: int = 3600):
        self.ttl = ttl
        self.cache: Dict[str, Dict[str, Any]] = {}

    def _hash(self, prompt: str) -> str:
        """Create a hash of the prompt."""
        return hashlib.md5(prompt.encode()).hexdigest()

    def get(self, prompt: str) -> Optional[str]:
        """Get cached response."""
        key = self._hash(prompt)
        if key in self.cache:
            data = self.cache[key]
            if time.time() - data["timestamp"] < self.ttl:
                return data["response"]
            del self.cache[key]
        return None

    def set(self, prompt: str, response: str) -> None:
        """Cache a response."""
        key = self._hash(prompt)
        self.cache[key] = {
            "response": response,
            "timestamp": time.time(),
        }

    def clear(self) -> None:
        """Clear the cache."""
        self.cache.clear()


class OpenAIClient:
    """OpenAI API client for code analysis."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv(config.openai.api_key_env)
        if not self.api_key:
            raise ValueError(f"OpenAI API key not set. Set {config.openai.api_key_env}")

        self.client = AsyncOpenAI(api_key=self.api_key)
        self.cache = ResponseCache(ttl=config.openai.cache_ttl)
        self.total_tokens_used = 0

    async def analyze_code(
        self,
        code: str,
        file_path: str,
        context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Analyze a piece of code and return insights."""
        prompt = f"""Analyze this code from {file_path}:

```{self._get_file_extension(file_path)}
{code}
```

{context if context else ''}

Provide a JSON response with:
1. quality_score (0-100)
2. issues (list of issues found)
3. suggestions (list of improvement suggestions)
4. summary (brief summary of the code)
"""

        if config.openai.cache_enabled:
            cached = self.cache.get(prompt)
            if cached:
                return safe_parse_json(cached)

        response = await self._call_api(prompt)
        self.cache.set(prompt, response)

        return safe_parse_json(response)

    async def review_repository(
        self,
        repo_name: str,
        file_contents: Dict[str, str],
        structure_info: Dict[str, Any],
    ) -> ReviewResult:
        """Perform a comprehensive review of a repository."""
        # Limit content to stay under token limits (roughly 4 chars per token)
        files_text = "\n\n".join(
            f"=== {path} ===\n{content[:1500]}"
            for path, content in list(file_contents.items())[:10]
        )

        prompt = f"""Review this repository: {repo_name}

Project Structure:
{json.dumps(structure_info, indent=2)}

Files:
{files_text}

Provide a comprehensive review in JSON format:
{{
    "summary": "Overall assessment of the repository",
    "quality_score": {{
        "overall": 0-100,
        "code_quality": 0-100,
        "documentation": 0-100,
        "structure": 0-100,
        "testing": 0-100
    }},
    "stuck_areas": ["areas where development appears stalled"],
    "next_steps": ["recommended next actions"],
    "issues_found": [
        {{
            "file": "path/to/file",
            "type": "bug|missing_docs|anti-pattern|security",
            "description": "description of issue",
            "severity": "high|medium|low"
        }}
    ],
    "recommendations": ["general recommendations"]
}}

Focus on identifying:
1. Incomplete features (TODO/FIXME comments)
2. Outdated or missing documentation
3. Code quality issues
4. Security concerns
5. Missing tests
"""

        if config.openai.cache_enabled:
            cached = self.cache.get(prompt)
            if cached:
                data = safe_parse_json(cached)
                return self._build_review_result(repo_name, data, len(file_contents))

        response = await self._call_api(prompt)
        self.cache.set(prompt, response)

        data = safe_parse_json(response)
        return self._build_review_result(repo_name, data, len(file_contents))

    async def suggest_improvements(
        self,
        code: str,
        file_path: str,
        current_issues: List[str],
    ) -> List[str]:
        """Suggest specific improvements for code."""
        prompt = f"""Suggest improvements for this code addressing these issues:
{chr(10).join(f'- {issue}' for issue in current_issues)}

File: {file_path}

```{self._get_file_extension(file_path)}
{code}
```

Provide a JSON array of improvement suggestions:
["suggestion 1", "suggestion 2", ...]"""

        response = await self._call_api(prompt)
        return safe_parse_json(response)

    async def generate_documentation(
        self,
        code: str,
        file_path: str,
        existing_doc: Optional[str] = None,
    ) -> str:
        """Generate or update documentation for a file."""
        prompt = f"""Generate documentation for this code:

```{self._get_file_extension(file_path)}
{code}
```

{f"Existing documentation:\n{existing_doc}" if existing_doc else ""}

Provide a comprehensive markdown documentation:"""

        return await self._call_api(prompt)

    async def _call_api(self, prompt: str, max_tokens: Optional[int] = None) -> str:
        """Make a call to the OpenAI API."""
        try:
            response: ChatCompletion = await self.client.chat.completions.create(
                model=config.openai.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert software engineer and code reviewer. "
                        "Always respond with valid JSON. Be thorough but concise.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=max_tokens or config.openai.max_tokens,
                temperature=config.openai.temperature,
            )

            self.total_tokens_used += response.usage.total_tokens
            content = response.choices[0].message.content

            if content is None:
                raise ValueError("Empty response from OpenAI")

            return content.strip()

        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise

    def _get_file_extension(self, file_path: str) -> str:
        """Get file extension for code block."""
        ext = file_path.split(".")[-1] if "." in file_path else ""
        lang_map = {
            "py": "python",
            "js": "javascript",
            "ts": "typescript",
            "go": "go",
            "rs": "rust",
            "java": "java",
            "cpp": "cpp",
            "c": "c",
            "h": "c",
            "md": "markdown",
            "json": "json",
            "yaml": "yaml",
            "yml": "yaml",
        }
        return lang_map.get(ext, ext)

    def _build_review_result(
        self, repo_name: str, data: Dict[str, Any], analyzed_files: int
    ) -> ReviewResult:
        """Build a ReviewResult from API response."""
        quality = data.get("quality_score", {})
        if isinstance(quality, dict):
            quality_score = QualityScore(
                overall=quality.get("overall", 50),
                code_quality=quality.get("code_quality", 50),
                documentation=quality.get("documentation", 50),
                structure=quality.get("structure", 50),
                testing=quality.get("testing", 50),
            )
        else:
            quality_score = QualityScore(
                overall=50, code_quality=50, documentation=50, structure=50, testing=50
            )

        return ReviewResult(
            repository_name=repo_name,
            summary=data.get("summary", ""),
            quality_score=quality_score,
            stuck_areas=data.get("stuck_areas", []),
            next_steps=data.get("next_steps", []),
            issues_found=data.get("issues_found", []),
            recommendations=data.get("recommendations", []),
            analyzed_files=analyzed_files,
            tokens_used=0,
            completed_at=datetime.utcnow(),
        )

    def get_token_usage(self) -> Dict[str, int]:
        """Get token usage statistics."""
        return {"total_tokens": self.total_tokens_used}

    def clear_cache(self) -> None:
        """Clear the response cache."""
        self.cache.clear()
