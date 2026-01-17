"""Task dispatcher for managing task queues and work distribution."""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from ..core.config import get_config
from ..core.logging_ import get_logger
from .interpreter import Task, TaskPriority, TaskStatus, TaskType

logger = get_logger(__name__)

config = get_config()


class QueueType(Enum):
    """Types of task queues."""
    GENERAL = "general"
    CRITICAL = "critical"
    BACKGROUND = "background"
    REPO_SPECIFIC = "repo_specific"


@dataclass
class QueueStats:
    """Statistics for a queue."""
    queue_name: str
    total_tasks: int = 0
    pending_tasks: int = 0
    processing_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    avg_processing_time: float = 0.0


@dataclass
class WorkerInfo:
    """Information about a worker."""
    id: str
    name: str
    status: str
    current_task: Optional[str]
    tasks_completed: int
    tasks_failed: int
    started_at: datetime


class TaskDispatcher:
    """Manages task queues and distributes work to workers."""

    def __init__(self, max_workers: int = 5):
        self.queues: Dict[QueueType, asyncio.Queue] = {
            queue_type: asyncio.Queue(maxsize=100) for queue_type in QueueType
        }
        self.repo_queues: Dict[str, asyncio.Queue] = {}
        self.workers: Dict[str, WorkerInfo] = {}
        self.worker_tasks: Dict[str, asyncio.Task] = {}
        self.max_workers = max_workers
        self.running = False
        self.task_handlers: Dict[TaskType, Callable] = {}
        self.completed_tasks: List[Task] = []
        self.failed_tasks: List[Task] = []

    def register_handler(
        self, task_type: TaskType, handler: Callable[[Task], Any]
    ) -> None:
        """Register a handler for a task type."""
        self.task_handlers[task_type] = handler
        logger.info(f"Registered handler for task type: {task_type.value}")

    async def enqueue(
        self,
        task: Task,
        queue_type: QueueType = QueueType.GENERAL,
        repo_name: Optional[str] = None,
    ) -> bool:
        """Add a task to the queue."""
        try:
            if queue_type == QueueType.REPO_SPECIFIC and repo_name:
                if repo_name not in self.repo_queues:
                    self.repo_queues[repo_name] = asyncio.Queue(maxsize=50)
                await self.repo_queues[repo_name].put(task)
            else:
                await self.queues[queue_type].put(task)

            logger.info(f"Enqueued task: {task.id} ({task.task_type.value})")
            return True

        except asyncio.QueueFull:
            logger.warning(f"Queue full, task {task.id} dropped")
            return False

    async def enqueue_batch(
        self, tasks: List[Task], queue_type: QueueType = QueueType.GENERAL
    ) -> int:
        """Add multiple tasks to the queue."""
        enqueued = 0
        for task in tasks:
            if await self.enqueue(task, queue_type):
                enqueued += 1
        return enqueued

    async def dequeue(self, queue_type: QueueType) -> Optional[Task]:
        """Take a task from the queue."""
        try:
            return await asyncio.wait_for(
                self.queues[queue_type].get(),
                timeout=1.0,
            )
        except asyncio.TimeoutError:
            return None

    async def process_task(self, task: Task) -> bool:
        """Process a single task."""
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = datetime.utcnow()

        handler = self.task_handlers.get(task.task_type)
        if not handler:
            logger.warning(f"No handler for task type: {task.task_type.value}")
            task.error = f"No handler for task type: {task.task_type.value}"
            task.status = TaskStatus.FAILED
            self.failed_tasks.append(task)
            return False

        try:
            logger.info(f"Processing task: {task.id}")
            result = await handler(task)

            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.utcnow()
            task.result = str(result) if result else "Completed successfully"
            self.completed_tasks.append(task)

            logger.info(f"Task completed: {task.id}")
            return True

        except Exception as e:
            logger.error(f"Task failed: {task.id} - {e}")
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.retries += 1

            if task.retries < task.max_retries:
                task.status = TaskStatus.QUEUED
                await self.enqueue(task)
            else:
                self.failed_tasks.append(task)

            return False

    async def worker_loop(self, worker_id: str, queue_type: QueueType) -> None:
        """Worker loop for processing tasks from a queue."""
        worker = WorkerInfo(
            id=worker_id,
            name=f"Worker-{worker_id}",
            status="running",
            current_task=None,
            tasks_completed=0,
            tasks_failed=0,
            started_at=datetime.utcnow(),
        )
        self.workers[worker_id] = worker

        logger.info(f"Worker {worker_id} started for queue {queue_type.value}")

        while self.running:
            try:
                task = await self.dequeue(queue_type)
                if task:
                    worker.current_task = task.id
                    worker.status = "processing"

                    success = await self.process_task(task)

                    if success:
                        worker.tasks_completed += 1
                    else:
                        worker.tasks_failed += 1

                    worker.current_task = None
                    worker.status = "running"

            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}")
                await asyncio.sleep(1)

        logger.info(f"Worker {worker_id} stopped")

    async def start_workers(
        self, queue_type: QueueType, num_workers: Optional[int] = None
    ) -> List[str]:
        """Start workers for a queue."""
        workers = []
        count = num_workers or min(2, self.max_workers)

        for i in range(count):
            worker_id = f"{queue_type.value}-{uuid.uuid4().hex[:8]}"
            self.worker_tasks[worker_id] = asyncio.create_task(
                self.worker_loop(worker_id, queue_type)
            )
            workers.append(worker_id)

        logger.info(f"Started {count} workers for {queue_type.value}")
        return workers

    async def start_all_workers(self) -> None:
        """Start workers for all queues."""
        self.running = True

        for queue_type in QueueType:
            await self.start_workers(queue_type)

    async def stop_workers(self) -> None:
        """Stop all workers."""
        self.running = False

        for task in self.worker_tasks.values():
            task.cancel()

        self.worker_tasks.clear()
        logger.info("All workers stopped")

    async def get_next_task(self, priority: List[QueueType] = None) -> Optional[Task]:
        """Get the next task respecting priority order."""
        priority = priority or [
            QueueType.CRITICAL,
            QueueType.GENERAL,
            QueueType.BACKGROUND,
        ]

        for queue_type in priority:
            task = await self.dequeue(queue_type)
            if task:
                return task

        return None

    def get_queue_stats(self, queue_type: QueueType) -> QueueStats:
        """Get statistics for a queue."""
        q = self.queues[queue_type]

        completed = [t for t in self.completed_tasks if t.status == TaskStatus.COMPLETED]
        failed = [t for t in self.failed_tasks if t.status == TaskStatus.FAILED]

        processing_times = [
            (t.completed_at - t.started_at).total_seconds()
            for t in completed
            if t.started_at and t.completed_at
        ]

        avg_time = sum(processing_times) / len(processing_times) if processing_times else 0

        return QueueStats(
            queue_name=queue_type.value,
            total_tasks=q.qsize() + len(completed) + len(failed),
            pending_tasks=q.qsize(),
            processing_tasks=sum(
                1 for w in self.workers.values() if w.current_task
            ),
            completed_tasks=len(completed),
            failed_tasks=len(failed),
            avg_processing_time=avg_time,
        )

    def get_all_stats(self) -> Dict[str, QueueStats]:
        """Get statistics for all queues."""
        return {qt.value: self.get_queue_stats(qt) for qt in QueueType}

    def get_worker_status(self) -> List[WorkerInfo]:
        """Get status of all workers."""
        return list(self.workers.values())

    def clear_queue(self, queue_type: QueueType) -> int:
        """Clear all tasks from a queue."""
        count = 0
        q = self.queues[queue_type]

        while not q.empty():
            try:
                q.get_nowait()
                count += 1
            except asyncio.QueueEmpty:
                break

        logger.info(f"Cleared {count} tasks from {queue_type.value}")
        return count

    def clear_all_queues(self) -> Dict[str, int]:
        """Clear all queues."""
        return {qt.value: self.clear_queue(qt) for qt in QueueType}

    async def wait_for_completion(self, timeout: Optional[float] = None) -> bool:
        """Wait for all tasks to complete."""
        try:
            await asyncio.wait_for(
                self._all_tasks_done(),
                timeout=timeout,
            )
            return True
        except asyncio.TimeoutError:
            return False

    async def _all_tasks_done(self) -> None:
        """Wait until all queues are empty."""
        while True:
            all_empty = all(q.empty() for q in self.queues.values())
            all_empty = all_empty and all(
                q.empty() for q in self.repo_queues.values()
            )
            all_idle = all(w.current_task is None for w in self.workers.values())

            if all_empty and all_idle:
                break

            await asyncio.sleep(1)

    def get_pending_tasks(self, limit: int = 50) -> List[Task]:
        """Get pending tasks across all queues."""
        tasks = []

        for queue_type in QueueType:
            q = self.queues[queue_type]
            temp_list = []
            while not q.empty() and len(temp_list) < limit:
                try:
                    task = q.get_nowait()
                    temp_list.append(task)
                    tasks.append(task)
                except asyncio.QueueEmpty:
                    break

            for task in temp_list:
                await q.put(task)

        return tasks[:limit]
