"""Task interpreter for parsing natural language commands into actionable tasks."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from ..core.logging_ import get_logger

logger = get_logger(__name__)


class TaskPriority(Enum):
    """Task priority levels."""
    CRITICAL = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4


class TaskStatus(Enum):
    """Task status levels."""
    PENDING = "pending"
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskType(Enum):
    """Types of tasks."""
    ADD_TEST = "add_test"
    FIX_BUG = "fix_bug"
    ADD_FEATURE = "add_feature"
    UPDATE_DOCS = "update_docs"
    REFACTOR = "refactor"
    CODE_REVIEW = "code_review"
    RUN_TESTS = "run_tests"
    DEPLOY = "deploy"
    CREATE_PR = "create_pr"
    MERGE_PR = "merge_pr"
    GENERAL = "general"


@dataclass
class Task:
    """A task to be executed."""
    id: str
    title: str
    description: str
    task_type: TaskType
    priority: TaskPriority
    status: TaskStatus
    repository: Optional[str]
    target_files: List[str]
    command: str
    parameters: Dict[str, Any]
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    result: Optional[str]
    error: Optional[str]
    retries: int = 0
    max_retries: int = 3
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedTask:
    """Result of task parsing."""
    task_type: TaskType
    title: str
    description: str
    priority: TaskPriority
    repository: Optional[str]
    target_files: List[str]
    parameters: Dict[str, Any]
    confidence: float


class TaskInterpreter:
    """Interprets natural language commands into structured tasks."""

    INTENT_PATTERNS = {
        TaskType.ADD_TEST: [
            r"(?:add|create|write|implement)\s+(?:a\s+)?test",
            r"test\s+(?:the\s+)?(?:file|function|class|module)",
            r"(?:add|create)\s+(?:unit\s+)?test",
            r"write\s+(?:unit\s+)?test",
            r"spec",
        ],
        TaskType.FIX_BUG: [
            r"fix\s+(?:the\s+)?(?:bug|error|issue|problem)",
            r"resolve\s+(?:the\s+)?(?:bug|error|issue)",
            r"(?:debug|debugging)",
            r"repair\s+(?:the\s+)?",
        ],
        TaskType.ADD_FEATURE: [
            r"(?:add|create|implement|build)\s+(?:a\s+)?(?:new\s+)?feature",
            r"(?:add|create|implement)\s+(?:a\s+)?(?:new\s+)?function",
            r"(?:add|create|implement)\s+(?:a\s+)?(?:new\s+)?endpoint",
            r"build\s+(?:a\s+)?(?:new\s+)?",
            r"create\s+(?:a\s+)?(?:new\s+)?",
        ],
        TaskType.UPDATE_DOCS: [
            r"(?:update|add|create|write)\s+(?:the\s+)?(?:project\s+)?doc",
            r"(?:update|add|create)\s+readme",
            r"(?:document|documenting)",
            r"(?:add|create)\s+(?:some\s+)?doc",
        ],
        TaskType.REFACTOR: [
            r"refactor",
            r"(?:clean|clean up|cleanup)\s+(?:the\s+)?(?:code)?",
            r"improve\s+(?:the\s+)?(?:code\s+)?(?:quality)?",
            r"restructur",
            r"optimiz",
        ],
        TaskType.CODE_REVIEW: [
            r"(?:review|analyze|check|examine)\s+(?:the\s+)?(?:code|repo)",
            r"(?:perform|do)\s+(?:a\s+)?(?:code\s+)?review",
            r"assess\s+(?:the\s+)?",
        ],
        TaskType.RUN_TESTS: [
            r"(?:run|execute|start)\s+(?:the\s+)?test",
            r"test\s+(?:the\s+)?(?:application|project|code)",
            r"pytest",
        ],
        TaskType.DEPLOY: [
            r"(?:deploy|deployment|release)",
            r"(?:push\s+to|ship)",
            r"(?:put\s+into|go\s+live)",
        ],
        TaskType.CREATE_PR: [
            r"(?:create|make)\s+(?:a\s+)?(?:pull\s+)?request",
            r"(?:create|make)\s+(?:a\s+)?pr",
            r"(?:submit|open)\s+(?:a\s+)?(?:pull\s+)?request",
        ],
        TaskType.MERGE_PR: [
            r"(?:merge|combine|squash)\s+(?:the\s+)?(?:pr|pull\s+request)",
            r"(?:merge|combine)\s+(?:the\s+)?(?:branch|code)",
        ],
    }

    PRIORITY_INDICATORS = {
        TaskPriority.CRITICAL: ["critical", "urgent", "asap", "immediately", "emergency"],
        TaskPriority.HIGH: ["important", "soon", "high priority", "must"],
        TaskPriority.MEDIUM: ["should", "would be nice", "when possible", "medium"],
        TaskPriority.LOW: ["low priority", "eventually", "sometime", "nice to have"],
    }

    def __init__(self):
        self._task_counter = 0

    def interpret(
        self,
        command: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> ParsedTask:
        """Interpret a natural language command into a task."""
        command_lower = command.lower()

        task_type = self._detect_intent(command_lower)
        priority = self._detect_priority(command_lower)
        repository = self._extract_repository(command, context)
        target_files = self._extract_file_paths(command)
        parameters = self._extract_parameters(command, task_type)
        title = self._generate_title(command, task_type)
        description = self._generate_description(command, task_type, context)
        confidence = self._calculate_confidence(command_lower, task_type)

        return ParsedTask(
            task_type=task_type,
            title=title,
            description=description,
            priority=priority,
            repository=repository,
            target_files=target_files,
            parameters=parameters,
            confidence=confidence,
        )

    def create_task(
        self,
        command: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Task:
        """Create a full Task object from a command."""
        parsed = self.interpret(command, context)

        self._task_counter += 1
        task_id = f"task-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{self._task_counter:04d}"

        return Task(
            id=task_id,
            title=parsed.title,
            description=parsed.description,
            task_type=parsed.task_type,
            priority=parsed.priority,
            status=TaskStatus.PENDING,
            repository=parsed.repository,
            target_files=parsed.target_files,
            command=command,
            parameters=parsed.parameters,
            created_at=datetime.utcnow(),
            started_at=None,
            completed_at=None,
            result=None,
            error=None,
            retries=0,
            max_retries=3,
            metadata={"confidence": parsed.confidence},
        )

    def _detect_intent(self, command: str) -> TaskType:
        """Detect the intent of the command."""
        for intent_type, patterns in self.INTENT_PATTERNS.items():
            for pattern in patterns:
                if pattern in command:
                    return intent_type
        return TaskType.GENERAL

    def _detect_priority(self, command: str) -> TaskPriority:
        """Detect the priority of the task."""
        command_lower = command.lower()

        for priority, indicators in self.PRIORITY_INDICATORS.items():
            for indicator in indicators:
                if indicator in command_lower:
                    return priority

        return TaskPriority.MEDIUM

    def _extract_repository(
        self, command: str, context: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """Extract repository name from command."""
        import re

        patterns = [
            r"(?:repo(?:sitory)?\s+)?([a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+)",
            r"(?:for|in)\s+([a-zA-Z0-9_-]+)",
            r"project\s+([a-zA-Z0-9_-]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, command, re.IGNORECASE)
            if match:
                repo = match.group(1)
                if "/" not in repo and context:
                    if "default_repo" in context:
                        repo = f"{context['default_repo'].split('/')[0]}/{repo}"
                return repo

        if context and "default_repo" in context:
            return context["default_repo"]

        return None

    def _extract_file_paths(self, command: str) -> List[str]:
        """Extract file paths from command."""
        import re

        patterns = [
            r"([a-zA-Z0-9/_.-]+\.py)",
            r"([a-zA-Z0-9/_.-]+\.js)",
            r"([a-zA-Z0-9/_.-]+\.ts)",
            r"([a-zA-Z0-9/_.-]+\.go)",
            r"in\s+([a-zA-Z0-9/_.-]+)",
            r"file\s+([a-zA-Z0-9/_.-]+)",
        ]

        files = []
        for pattern in patterns:
            matches = re.findall(pattern, command, re.IGNORECASE)
            files.extend(matches)

        return list(set(files))[:10]

    def _extract_parameters(
        self, command: str, task_type: TaskType
    ) -> Dict[str, Any]:
        """Extract parameters from command."""
        import re

        parameters = {}

        branch_match = re.search(r"(?:branch|feature)\s+([a-zA-Z0-9_-]+)", command)
        if branch_match:
            parameters["branch_name"] = branch_match.group(1)

        pr_match = re.search(r"(?:pr|pull request)\s*(?:#)?(\d+)", command)
        if pr_match:
            parameters["pr_number"] = int(pr_match.group(1))

        limit_match = re.search(r"(?:limit\s+)?(\d+)\s+(?:files|repos|items)", command)
        if limit_match:
            parameters["limit"] = int(limit_match.group(1))

        force_match = re.search(r"(?:force|forcefully|now)", command)
        if force_match:
            parameters["force"] = True

        return parameters

    def _generate_title(self, command: str, task_type: TaskType) -> str:
        """Generate a title for the task."""
        title_prefixes = {
            TaskType.ADD_TEST: "Add tests",
            TaskType.FIX_BUG: "Fix bug",
            TaskType.ADD_FEATURE: "Add feature",
            TaskType.UPDATE_DOCS: "Update documentation",
            TaskType.REFACTOR: "Refactor code",
            TaskType.CODE_REVIEW: "Review code",
            TaskType.RUN_TESTS: "Run tests",
            TaskType.DEPLOY: "Deploy",
            TaskType.CREATE_PR: "Create PR",
            TaskType.MERGE_PR: "Merge PR",
            TaskType.GENERAL: "Execute task",
        }

        return f"{title_prefixes.get(task_type, 'Task')}: {command[:50]}"

    def _generate_description(
        self,
        command: str,
        task_type: TaskType,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate a description for the task."""
        descriptions = {
            TaskType.ADD_TEST: f"Add tests as requested: {command}",
            TaskType.FIX_BUG: f"Fix bug as requested: {command}",
            TaskType.ADD_FEATURE: f"Add feature as requested: {command}",
            TaskType.UPDATE_DOCS: f"Update documentation as requested: {command}",
            TaskType.REFACTOR: f"Refactor as requested: {command}",
            TaskType.CODE_REVIEW: f"Review code as requested: {command}",
            TaskType.RUN_TESTS: f"Run tests as requested: {command}",
            TaskType.DEPLOY: f"Deploy as requested: {command}",
            TaskType.CREATE_PR: f"Create pull request as requested: {command}",
            TaskType.MERGE_PR: f"Merge pull request as requested: {command}",
            TaskType.GENERAL: f"Execute: {command}",
        }

        if context:
            if "repository" in context:
                descriptions[task_type] += f" in repository: {context['repository']}"

        return descriptions.get(task_type, command)

    def _calculate_confidence(self, command: str, detected_type: TaskType) -> float:
        """Calculate confidence score for the interpretation."""
        if detected_type == TaskType.GENERAL:
            return 0.5

        base_confidence = 0.7

        for pattern in self.INTENT_PATTERNS.get(detected_type, []):
            if pattern in command:
                base_confidence += 0.1

        return min(0.95, base_confidence)

    def batch_interpret(
        self, commands: List[str], context: Optional[Dict[str, Any]] = None
    ) -> List[ParsedTask]:
        """Interpret multiple commands."""
        return [self.interpret(cmd, context) for cmd in commands]

    def create_task_batch(
        self, commands: List[str], context: Optional[Dict[str, Any]] = None
    ) -> List[Task]:
        """Create multiple tasks from commands."""
        return [self.create_task(cmd, context) for cmd in commands]
