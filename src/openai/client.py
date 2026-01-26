"""LLM integration for code review - supports MiniMax M2.1 and OpenAI."""

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..core.config import get_config
from ..core.logging_ import get_logger

logger = get_logger(__name__)

config = get_config()


def safe_parse_json(text: str) -> Dict[str, Any]:
    """Safely parse JSON from API response, handling markdown code blocks."""
    if not text or not text.strip():
        return {}

    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

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
        return hashlib.md5(prompt.encode()).hexdigest()

    def get(self, prompt: str) -> Optional[str]:
        key = self._hash(prompt)
        if key in self.cache:
            data = self.cache[key]
            if time.time() - data["timestamp"] < self.ttl:
                return data["response"]
            del self.cache[key]
        return None

    def set(self, prompt: str, response: str) -> None:
        key = self._hash(prompt)
        self.cache[key] = {
            "response": response,
            "timestamp": time.time(),
        }

    def clear(self) -> None:
        self.cache.clear()


class LLMClient:
    """Unified LLM client supporting MiniMax M2.1 and OpenAI."""

    def __init__(self, api_key: Optional[str] = None):
        minimax_key = os.getenv("MINIMAX_API_KEY")
        openai_key = os.getenv("OPENAI_API_KEY")

        if minimax_key:
            self.provider = "minimax"
            self.api_key = minimax_key
        elif openai_key:
            self.provider = "openai"
            self.api_key = openai_key
        elif api_key:
            self.provider = "minimax"
            self.api_key = api_key
        else:
            raise ValueError("No API key found. Set MINIMAX_API_KEY or OPENAI_API_KEY")

        self.cache = ResponseCache(ttl=3600)
        self.total_tokens_used = 0
        self.model = "MiniMax-M2.1"

        logger.info(f"Using LLM provider: {self.provider}")

    async def _call_minimax(self, prompt: str) -> str:
        """Call MiniMax M2.1 API."""
        import httpx

        api_base = getattr(config.minimax, 'api_base', 'https://api.minimax.chat/v1/text/chatcompletion_v2')
        model = getattr(config.minimax, 'model', 'MiniMax-M2.1')

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                api_base,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are an expert software engineer and code reviewer. "
                            "Always respond with valid JSON. Be thorough but concise.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 4096,
                    "temperature": 0.3,
                },
            )
            response.raise_for_status()
            data = response.json()

            if "choices" in data and len(data["choices"]) > 0:
                content = data["choices"][0]["message"]["content"]
                return content.strip()
            else:
                raise ValueError(f"Unexpected MiniMax response format: {data}")

    async def _call_openai(self, prompt: str) -> str:
        """Call OpenAI API."""
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self.api_key)
        response = await client.chat.completions.create(
            model=getattr(config.openai, 'model', 'gpt-4o'),
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert software engineer and code reviewer. "
                    "Always respond with valid JSON. Be thorough but concise.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=getattr(config.openai, 'max_tokens', 4096),
            temperature=getattr(config.openai, 'temperature', 0.3),
        )

        content = response.choices[0].message.content
        if content is None:
            raise ValueError("Empty response from OpenAI")
        return content.strip()

    async def _call_api(self, prompt: str) -> str:
        """Call the appropriate LLM API based on configured provider."""
        if self.provider == "minimax":
            return await self._call_minimax(prompt)
        else:
            return await self._call_openai(prompt)

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


# Backward compatibility alias
OpenAIClient = LLMClient
