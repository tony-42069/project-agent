"""FastAPI application for Project Agent."""

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ..core.config import get_config
from ..core.database import Database
from ..core.logging_ import get_logger
from ..github import GitHubClient
from ..openai import OpenAIClient
from ..report import ReportGenerator
from ..review import ReviewOrchestrator

logger = get_logger(__name__)

config = get_config()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan."""
    db = Database()
    await db.connect()
    yield
    await db.close()


app = FastAPI(
    title="Project Agent",
    description="AI-powered GitHub repository management",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

github = GitHubClient()
openai = OpenAIClient()
db = Database()
orchestrator = ReviewOrchestrator(github, openai, db)
report_gen = ReportGenerator()


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    timestamp: datetime
    version: str


class RepoListResponse(BaseModel):
    """Repository list response."""
    repositories: List[Dict[str, Any]]
    total: int


class ReviewResponse(BaseModel):
    """Review response."""
    repository_name: str
    status: str
    summary: str
    quality_scores: Dict[str, float]
    stuck_areas: List[str]
    next_steps: List[str]


class ReviewRequest(BaseModel):
    """Review request."""
    repository_name: str


class CommandRequest(BaseModel):
    """Command request."""
    command: str


class CommandResponse(BaseModel):
    """Command response."""
    success: bool
    message: str
    result: Optional[Dict[str, Any]] = None


@app.get("/", response_model=Dict[str, str])
async def root():
    """Root endpoint."""
    return {"message": "Project Agent API", "version": "0.1.0"}


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow(),
        version="0.1.0",
    )


@app.get("/api/v1/repositories", response_model=RepoListResponse)
async def list_repositories(include_archived: bool = False, limit: int = 100):
    """List all repositories."""
    try:
        await db.connect()
        repos = await db.list_repositories(include_archived=include_archived, limit=limit)

        if not repos:
            repos = await github.list_all_repositories()

        return RepoListResponse(
            repositories=[
                {
                    "name": r.name if hasattr(r, "name") else r["name"],
                    "full_name": r.full_name if hasattr(r, "full_name") else r["full_name"],
                    "description": r.description if hasattr(r, "description") else r.get("description"),
                    "language": r.language if hasattr(r, "language") else r.get("language"),
                    "is_private": r.is_private if hasattr(r, "is_private") else r.get("is_private"),
                }
                for r in repos
            ],
            total=len(repos),
        )
    except Exception as e:
        logger.error(f"Error listing repositories: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/review", response_model=ReviewResponse)
async def review_repository(request: ReviewRequest):
    """Review a specific repository."""
    try:
        repo = await github.get_repository(request.repository_name)

        if not repo:
            raise HTTPException(status_code=404, detail=f"Repository {request.repository_name} not found")

        result = await orchestrator.review_repository(repo)

        return ReviewResponse(
            repository_name=result.get("repository_name", request.repository_name),
            status=result.get("status", "unknown"),
            summary=result.get("summary", ""),
            quality_scores=result.get("quality_scores", {}),
            stuck_areas=result.get("stuck_areas", []),
            next_steps=result.get("next_steps", []),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reviewing repository: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/command", response_model=CommandResponse)
async def execute_command(request: CommandRequest):
    """Execute a command."""
    from ..commands.parser import CommandParser

    parser = CommandParser()
    command = parser.parse(request.command)

    if command.verb == "review" and command.noun == "all":
        try:
            repos = await github.list_all_repositories()
            results = await orchestrator.review_all(repos)
            summary = report_gen.generate_summary_dashboard(results)

            return CommandResponse(
                success=True,
                message=f"Reviewed {len(repos)} repositories",
                result={"summary": summary},
            )
        except Exception as e:
            return CommandResponse(success=False, message=str(e))

    elif command.verb == "list":
        try:
            repos = await github.list_all_repositories()
            repo_list = [r.full_name for r in repos]
            return CommandResponse(
                success=True,
                message=f"Found {len(repos)} repositories",
                result={"repositories": repo_list},
            )
        except Exception as e:
            return CommandResponse(success=False, message=str(e))

    elif command.verb == "status":
        rate_info = github.get_rate_limit_info()
        return CommandResponse(
            success=True,
            message="System is running",
            result={"rate_limit": rate_info.__dict__ if rate_info else None},
        )

    return CommandResponse(
        success=False,
        message=f"Unknown command: {command.verb}",
    )


@app.get("/api/v1/dashboard")
async def get_dashboard():
    """Get dashboard summary."""
    try:
        repos = await github.list_all_repositories()
        results = await orchestrator.review_all(repos)

        summary = report_gen.generate_summary_dashboard(results)

        return {
            "success": True,
            "dashboard": summary,
        }
    except Exception as e:
        logger.error(f"Error generating dashboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/rate-limit")
async def get_rate_limit():
    """Get GitHub rate limit status."""
    rate_info = github.get_rate_limit_info()
    if rate_info:
        return {
            "remaining": rate_info.remaining,
            "limit": rate_info.limit,
            "reset_at": rate_info.reset_at.isoformat(),
            "used": rate_info.used,
        }
    return {"error": "Rate limit info not available"}
