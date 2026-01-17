"""Type definitions for GitHub package."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, List, Optional


@dataclass
class RateLimitInfo:
    """Rate limit information."""
    remaining: int
    limit: int
    reset_at: datetime
    used: int


@dataclass
class FileContent:
    """File content information."""
    path: str
    content: str
    size: int
    sha: str
    encoding: str


@dataclass
class Repository:
    """Repository information."""
    name: str
    full_name: str
    description: Optional[str]
    html_url: str
    clone_url: str
    language: Optional[str]
    is_private: bool
    is_archived: bool
    is_fork: bool
    stargazers_count: int
    forks_count: int
    open_issues_count: int
    created_at: datetime
    updated_at: datetime
    default_branch: str
