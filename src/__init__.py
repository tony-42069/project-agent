"""Project Agent - AI-powered agent for managing and reviewing GitHub projects."""

__version__ = "0.1.0"
__author__ = "Project Agent"

from .core import Config, settings, Database, get_db, LoggingMixin, get_logger
from .github import GitHubClient
from .llm import LLMClient
from .review import CodeAnalyzer, ReviewOrchestrator, RepoDiscovery, DocumentationAnalyzer
from .report import (
    ReportGenerator,
    RepoCommitter,
    BranchManager,
    PRCreator,
    ReviewWorkflow,
)
from .tasks import (
    TaskDispatcher,
    TaskExecutor,
    TaskInterpreter,
    Task,
    TaskPriority,
    TaskStatus,
    TaskType,
)

__all__ = [
    "__version__",
    "Config",
    "settings",
    "Database",
    "get_db",
    "LoggingMixin",
    "get_logger",
    "GitHubClient",
    "LLMClient",
    "CodeAnalyzer",
    "ReviewOrchestrator",
    "RepoDiscovery",
    "DocumentationAnalyzer",
    "ReportGenerator",
    "RepoCommitter",
    "BranchManager",
    "PRCreator",
    "ReviewWorkflow",
    "TaskDispatcher",
    "TaskExecutor",
    "TaskInterpreter",
    "Task",
    "TaskPriority",
    "TaskStatus",
    "TaskType",
]
