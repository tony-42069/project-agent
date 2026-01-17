"""Task status tracking and history management."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.config import get_config
from ..core.logging_ import get_logger
from .interpreter import Task, TaskPriority, TaskStatus, TaskType

logger = get_logger(__name__)

config = get_config()


@dataclass
class TaskHistoryEntry:
    """An entry in the task history."""
    timestamp: datetime
    task_id: str
    action: str
    details: str
    user: Optional[str]


@dataclass
class TaskMetrics:
    """Metrics for task execution."""
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    pending_tasks: int = 0
    avg_completion_time: float = 0.0
    success_rate: float = 0.0
    by_type: Dict[str, int] = field(default_factory=dict)
    by_priority: Dict[str, int] = field(default_factory=dict)


class TaskStatusTracker:
    """Tracks task status and maintains history."""

    def __init__(self, storage_path: Optional[str] = None):
        self.storage_path = storage_path or "data/task_history.json"
        self._ensure_storage()
        self.active_tasks: Dict[str, Task] = {}
        self.history: List[TaskHistoryEntry] = []

    def _ensure_storage(self) -> None:
        """Ensure storage directory exists."""
        Path(self.storage_path).parent.mkdir(parents=True, exist_ok=True)

    def register_task(self, task: Task) -> None:
        """Register a new task."""
        self.active_tasks[task.id] = task
        self._add_history(task.id, "created", f"Task created: {task.title}")

        logger.info(f"Registered task: {task.id}")

    def update_status(
        self,
        task_id: str,
        status: TaskStatus,
        details: str = "",
        result: Optional[str] = None,
    ) -> bool:
        """Update the status of a task."""
        if task_id not in self.active_tasks:
            logger.warning(f"Task not found: {task_id}")
            return False

        task = self.active_tasks[task_id]
        old_status = task.status
        task.status = status

        if status == TaskStatus.IN_PROGRESS:
            task.started_at = datetime.utcnow()
            self._add_history(task_id, "started", details or f"Task started: {task.title}")

        elif status == TaskStatus.COMPLETED:
            task.completed_at = datetime.utcnow()
            task.result = result
            self._add_history(task_id, "completed", details or f"Task completed: {task.title}")
            self._save_task(task)

        elif status == TaskStatus.FAILED:
            task.completed_at = datetime.utcnow()
            task.error = details
            self._add_history(task_id, "failed", details)
            self._save_task(task)

        elif status == TaskStatus.CANCELLED:
            self._add_history(task_id, "cancelled", details)
            self._save_task(task)

        logger.info(f"Task {task_id} status: {old_status.value} -> {status.value}")
        return True

    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID."""
        return self.active_tasks.get(task_id)

    def get_tasks_by_status(self, status: TaskStatus) -> List[Task]:
        """Get all tasks with a specific status."""
        return [t for t in self.active_tasks.values() if t.status == status]

    def get_tasks_by_repository(self, repo: str) -> List[Task]:
        """Get all tasks for a specific repository."""
        return [t for t in self.active_tasks.values() if t.repository == repo]

    def get_tasks_by_type(self, task_type: TaskType) -> List[Task]:
        """Get all tasks of a specific type."""
        return [t for t in self.active_tasks.values() if t.task_type == task_type]

    def get_tasks_by_priority(self, priority: TaskPriority) -> List[Task]:
        """Get all tasks with a specific priority."""
        return [t for t in self.active_tasks.values() if t.priority == priority]

    def get_active_tasks(self) -> List[Task]:
        """Get all active (non-completed) tasks."""
        return [
            t for t in self.active_tasks.values()
            if t.status not in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]
        ]

    def get_completed_tasks(self, limit: int = 100) -> List[Task]:
        """Get completed tasks."""
        completed = [
            t for t in self.active_tasks.values()
            if t.status == TaskStatus.COMPLETED
        ]
        return sorted(completed, key=lambda t: t.completed_at or datetime.min, reverse=True)[:limit]

    def get_failed_tasks(self, limit: int = 50) -> List[Task]:
        """Get failed tasks."""
        failed = [
            t for t in self.active_tasks.values()
            if t.status == TaskStatus.FAILED
        ]
        return sorted(failed, key=lambda t: t.completed_at or datetime.min, reverse=True)[:limit]

    def cancel_task(self, task_id: str, reason: str = "Cancelled by user") -> bool:
        """Cancel a task."""
        return self.update_status(task_id, TaskStatus.CANCELLED, reason)

    def retry_task(self, task_id: str) -> bool:
        """Retry a failed task."""
        if task_id not in self.active_tasks:
            return False

        task = self.active_tasks[task_id]
        if task.status != TaskStatus.FAILED:
            return False

        task.retries += 1
        task.status = TaskStatus.PENDING
        task.error = None
        task.started_at = None
        task.completed_at = None

        self._add_history(task_id, "retried", f"Retry attempt {task.retries}")
        logger.info(f"Retrying task: {task_id} (attempt {task.retries})")

        return True

    def add_note(self, task_id: str, note: str) -> bool:
        """Add a note to a task."""
        if task_id not in self.active_tasks:
            return False

        task = self.active_tasks[task_id]
        if "notes" not in task.metadata:
            task.metadata["notes"] = []

        task.metadata["notes"].append({
            "timestamp": datetime.utcnow().isoformat(),
            "note": note,
        })

        return True

    def get_metrics(self) -> TaskMetrics:
        """Calculate task metrics."""
        tasks = list(self.active_tasks.values())

        if not tasks:
            return TaskMetrics()

        completed = [t for t in tasks if t.status == TaskStatus.COMPLETED]
        failed = [t for t in tasks if t.status == TaskStatus.FAILED]
        pending = [t for t in tasks if t.status in [TaskStatus.PENDING, TaskStatus.QUEUED, TaskStatus.IN_PROGRESS]]

        completion_times = []
        for t in completed:
            if t.started_at and t.completed_at:
                duration = (t.completed_at - t.started_at).total_seconds()
                completion_times.append(duration)

        avg_time = sum(completion_times) / len(completion_times) if completion_times else 0.0
        success_rate = len(completed) / len(tasks) * 100 if tasks else 0.0

        by_type = {}
        by_priority = {}
        for t in tasks:
            ttype = t.task_type.value
            by_type[ttype] = by_type.get(ttype, 0) + 1

            pname = t.priority.name
            by_priority[pname] = by_priority.get(pname, 0) + 1

        return TaskMetrics(
            total_tasks=len(tasks),
            completed_tasks=len(completed),
            failed_tasks=len(failed),
            pending_tasks=len(pending),
            avg_completion_time=avg_time,
            success_rate=success_rate,
            by_type=by_type,
            by_priority=by_priority,
        )

    def get_history(
        self,
        task_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[TaskHistoryEntry]:
        """Get task history."""
        if task_id:
            history = [h for h in self.history if h.task_id == task_id]
        else:
            history = self.history

        return sorted(history, key=lambda h: h.timestamp, reverse=True)[:limit]

    def _add_history(
        self, task_id: str, action: str, details: str, user: Optional[str] = None
    ) -> None:
        """Add an entry to the history."""
        entry = TaskHistoryEntry(
            timestamp=datetime.utcnow(),
            task_id=task_id,
            action=action,
            details=details,
            user=user,
        )
        self.history.append(entry)
        self._save_history()

    def _save_task(self, task: Task) -> None:
        """Save a completed task to storage."""
        try:
            storage_file = Path(self.storage_path).parent / "completed_tasks.json"

            completed = []
            if storage_file.exists():
                with open(storage_file, "r") as f:
                    completed = json.load(f)

            completed.append({
                "id": task.id,
                "title": task.title,
                "description": task.description,
                "task_type": task.task_type.value,
                "priority": task.priority.name,
                "status": task.status.value,
                "repository": task.repository,
                "created_at": task.created_at.isoformat(),
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                "result": task.result,
                "error": task.error,
            })

            with open(storage_file, "w") as f:
                json.dump(completed[-100:], f, indent=2)

        except Exception as e:
            logger.error(f"Failed to save task: {e}")

    def _save_history(self) -> None:
        """Save history to storage."""
        try:
            storage_file = Path(self.storage_path).parent / "task_history.json"

            history_data = [
                {
                    "timestamp": h.timestamp.isoformat(),
                    "task_id": h.task_id,
                    "action": h.action,
                    "details": h.details,
                    "user": h.user,
                }
                for h in self.history[-500:]
            ]

            with open(storage_file, "w") as f:
                json.dump(history_data, f, indent=2)

        except Exception as e:
            logger.error(f"Failed to save history: {e}")

    def generate_report(self) -> str:
        """Generate a text report of task status."""
        metrics = self.get_metrics()
        active = self.get_active_tasks()

        lines = [
            "Task Status Report",
            "=" * 40,
            f"Generated: {datetime.utcnow().isoformat()}",
            "",
            "Metrics:",
            f"  Total Tasks: {metrics.total_tasks}",
            f"  Completed: {metrics.completed_tasks}",
            f"  Failed: {metrics.failed_tasks}",
            f"  Pending: {metrics.pending_tasks}",
            f"  Success Rate: {metrics.success_rate:.1f}%",
            f"  Avg Completion Time: {metrics.avg_completion_time:.1f}s",
            "",
            "By Type:",
        ]

        for ttype, count in metrics.by_type.items():
            lines.append(f"  {ttype}: {count}")

        lines.append("")
        lines.append("Active Tasks:")
        for task in active[:10]:
            lines.append(f"  - [{task.status.value}] {task.title}")

        return "\n".join(lines)

    def clear_completed(self) -> int:
        """Clear completed tasks from active tracking."""
        to_remove = [
            task_id for task_id, task in self.active_tasks.items()
            if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]
        ]

        for task_id in to_remove:
            del self.active_tasks[task_id]

        logger.info(f"Cleared {len(to_remove)} completed tasks")
        return len(to_remove)
