"""Type definitions for OpenAI package."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, List


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
