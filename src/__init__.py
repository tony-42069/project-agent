"""Project Agent - AI-powered agent for managing and reviewing GitHub projects."""

__version__ = "0.1.0"
__author__ = "Project Agent"

from .core import Config, settings, Database, get_db, LoggingMixin, get_logger
from .github import GitHubClient
from .openai import OpenAIClient
from .review import CodeAnalyzer, ReviewOrchestrator

__all__ = [
    "__version__",
    "Config",
    "settings",
    "Database",
    "get_db",
    "LoggingMixin",
    "get_logger",
    "GitHubClient",
    "OpenAIClient",
    "CodeAnalyzer",
    "ReviewOrchestrator",
]
