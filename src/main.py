"""Main entry point for Project Agent."""

import asyncio
import sys
from pathlib import Path

from .core.config import get_config
from .core.logging_ import get_logger

logger = get_logger(__name__)


def check_environment() -> bool:
    """Check that required environment variables are set."""
    from .core.config import settings

    required = ["GITHUB_TOKEN", "OPENAI_API_KEY"]

    missing = [var for var in required if not os.getenv(var)]
    if missing:
        logger.error(f"Missing required environment variables: {', '.join(missing)}")
        logger.info("Please set these variables in your .env file or environment")
        return False

    logger.info("Environment check passed")
    return True


async def run_review_all() -> None:
    """Run review on all repositories."""
    from .github import GitHubClient
    from .review import ReviewOrchestrator
    from .report import ReportGenerator, RepoCommitter
    from .core.database import Database

    config = get_config()
    db = Database()

    await db.connect()

    github = GitHubClient()
    repos = await github.list_all_repositories()

    logger.info(f"Found {len(repos)} repositories to review")

    orchestrator = ReviewOrchestrator(github)
    report_gen = ReportGenerator()
    committer = RepoCommitter(github)

    for repo in repos:
        logger.info(f"Reviewing repository: {repo.full_name}")

        try:
            result = await orchestrator.review_repository(repo)

            report = report_gen.generate_review_report(repo, result)

            await committer.commit_report(repo, report)

            await db.save_review_session(repo, result)

            logger.info(f"Completed review for {repo.full_name}")

        except Exception as e:
            logger.error(f"Failed to review {repo.full_name}: {e}")
            continue

    await db.close()
    logger.info("Review complete")


async def run_api_server() -> None:
    """Run the FastAPI server."""
    import uvicorn
    from .api.main import app
    from .core.config import settings

    config = get_config()

    uvicorn.run(
        app,
        host=config.app.host,
        port=config.app.port,
        log_level=config.app.log_level.lower(),
    )


async def run_telegram_bot() -> None:
    """Run the Telegram bot."""
    from .commands import TelegramBot
    from .core.config import settings

    bot = TelegramBot()
    await bot.run()


def main() -> int:
    """Main entry point."""
    import os

    if not check_environment():
        return 1

    config = get_config()

    if len(sys.argv) > 1:
        command = sys.argv[1].lower()

        if command == "review":
            asyncio.run(run_review_all())
            return 0

        elif command == "api":
            asyncio.run(run_api_server())
            return 0

        elif command == "bot":
            asyncio.run(run_telegram_bot())
            return 0

        elif command in ("--help", "-h", "help"):
            print("""
Project Agent - AI-powered GitHub project management

Usage: python -m src [command]

Commands:
    review    Review all repositories
    api       Run the FastAPI server
    bot       Run the Telegram bot

Options:
    --help, -h    Show this help message
            """)
            return 0

    logger.info("No command specified. Use 'review', 'api', or 'bot'")
    return 1


if __name__ == "__main__":
    sys.exit(main())
