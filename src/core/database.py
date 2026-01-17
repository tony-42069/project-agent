"""Database layer using SQLAlchemy with async support."""

import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker

from .config import get_config
from .logging_ import get_logger

logger = get_logger(__name__)

config = get_config()


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


class Repository(Base):
    """Repository metadata model."""
    __tablename__ = "repositories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    full_name = Column(String(500), nullable=False, unique=True)
    description = Column(Text)
    html_url = Column(String(1000))
    clone_url = Column(String(1000))
    language = Column(String(100))
    is_private = Column(Integer, default=0)
    is_archived = Column(Integer, default=0)
    is_fork = Column(Integer, default=0)
    stargazers_count = Column(Integer, default=0)
    forks_count = Column(Integer, default=0)
    open_issues_count = Column(Integer, default=0)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    last_reviewed_at = Column(DateTime)
    created_at_db = Column(DateTime, default=datetime.utcnow)

    review_sessions = relationship("ReviewSession", back_populates="repository")


class ReviewSession(Base):
    """Review session model."""
    __tablename__ = "review_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    repository_id = Column(Integer, ForeignKey("repositories.id"), nullable=False)
    status = Column(String(50), default="pending")
    overall_score = Column(Float)
    quality_score = Column(Float)
    documentation_score = Column(Float)
    structure_score = Column(Float)
    testing_score = Column(Float)
    summary = Column(Text)
    stuck_areas = Column(Text)
    next_steps = Column(Text)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    error_message = Column(Text)

    repository = relationship("Repository", back_populates="review_sessions")


class Task(Base):
    """Task model for tracking work items."""
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(500), nullable=False)
    description = Column(Text)
    repository_name = Column(String(500))
    status = Column(String(50), default="pending")
    priority = Column(Integer, default=1)
    command = Column(Text)
    result = Column(Text)
    error = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)


class PRStatus(Base):
    """Pull request status tracking model."""
    __tablename__ = "pr_status"

    id = Column(Integer, primary_key=True, autoincrement=True)
    repository_name = Column(String(500), nullable=False)
    pr_number = Column(Integer)
    branch_name = Column(String(500))
    status = Column(String(50), default="draft")
    title = Column(String(500))
    body = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    merged_at = Column(DateTime)
    closed_at = Column(DateTime)


class Database:
    """Database connection manager."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or config.database.path
        self.async_engine = None
        self.async_session = None

    async def connect(self) -> None:
        """Initialize database connection."""
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        async_url = f"sqlite+aiosqlite:///{self.db_path}"

        self.async_engine = create_async_engine(
            async_url,
            echo=config.database.echo,
            pool_pre_ping=True,
        )

        self.async_session = async_sessionmaker(
            self.async_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        async with self.async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        logger.info(f"Connected to database: {self.db_path}")

    async def close(self) -> None:
        """Close database connection."""
        if self.async_engine:
            await self.async_engine.dispose()
            logger.info("Database connection closed")

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get a database session."""
        if not self.async_session:
            await self.connect()

        async with self.async_session() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def save_repository(self, repo_data: Dict[str, Any]) -> Repository:
        """Save or update repository metadata."""
        async with self.session() as session:
            existing = await session.execute(
                Repository.__table__.select().where(
                    Repository.full_name == repo_data["full_name"]
                )
            )
            result = existing.fetchone()

            if result:
                for key, value in repo_data.items():
                    setattr(result, key, value)
                repo = result
            else:
                repo = Repository(**repo_data)
                session.add(repo)

            await session.flush()
            return repo

    async def save_review_session(
        self, repo: Any, review_result: Dict[str, Any]
    ) -> ReviewSession:
        """Save a review session."""
        async with self.session() as session:
            review = ReviewSession(
                repository_id=repo.id if hasattr(repo, "id") else repo["id"],
                status=review_result.get("status", "completed"),
                overall_score=review_result.get("overall_score"),
                quality_score=review_result.get("quality_score"),
                documentation_score=review_result.get("documentation_score"),
                structure_score=review_result.get("structure_score"),
                testing_score=review_result.get("testing_score"),
                summary=review_result.get("summary"),
                stuck_areas=review_result.get("stuck_areas"),
                next_steps=review_result.get("next_steps"),
                completed_at=datetime.utcnow(),
            )
            session.add(review)
            return review

    async def get_repository(self, full_name: str) -> Optional[Repository]:
        """Get repository by full name."""
        async with self.session() as session:
            result = await session.execute(
                Repository.__table__.select().where(Repository.full_name == full_name)
            )
            return result.fetchone()

    async def list_repositories(
        self, include_archived: bool = False, limit: int = 100
    ) -> List[Repository]:
        """List all tracked repositories."""
        async with self.session() as session:
            query = Repository.__table__.select()
            if not include_archived:
                query = query.where(Repository.is_archived == 0)
            query = query.limit(limit)

            result = await session.execute(query)
            return result.fetchall()

    async def create_task(self, task_data: Dict[str, Any]) -> Task:
        """Create a new task."""
        async with self.session() as session:
            task = Task(**task_data)
            session.add(task)
            return task

    async def update_task(
        self, task_id: int, updates: Dict[str, Any]
    ) -> Optional[Task]:
        """Update a task."""
        async with self.session() as session:
            result = await session.execute(
                Task.__table__.select().where(Task.id == task_id)
            )
            task = result.fetchone()
            if task:
                for key, value in updates.items():
                    setattr(task, key, value)
            return task


async def get_db() -> AsyncGenerator[Database, None]:
    """Dependency for getting database connection."""
    db = Database()
    await db.connect()
    try:
        yield db
    finally:
        await db.close()
