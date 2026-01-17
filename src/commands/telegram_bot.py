"""Telegram bot for command interface."""

import asyncio
import os
from typing import Optional

from python_telegram_bot import Application, CommandHandler, ContextTypes, MessageHandler
from python_telegram_bot.filters import TEXT

from ..core.config import get_config
from ..core.database import Database
from ..core.logging_ import get_logger
from ..github import GitHubClient
from ..openai import OpenAIClient
from ..report import ReportGenerator
from ..review import ReviewOrchestrator
from .parser import CommandParser

logger = get_logger(__name__)

config = get_config()


class TelegramBot:
    """Telegram bot for controlling Project Agent."""

    def __init__(self):
        self.token = os.getenv(config.telegram.token_env)
        if not self.token:
            raise ValueError(f"Telegram token not set. Set {config.telegram.token_env}")

        self.application = Application.builder().token(self.token).build()
        self.parser = CommandParser()
        self.github = GitHubClient()
        self.openai = OpenAIClient()
        self.db = Database()
        self.orchestrator = ReviewOrchestrator(self.github, self.openai, self.db)
        self.report_gen = ReportGenerator()

    async def start(self, update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        welcome_message = """
👋 Welcome to Project Agent!

I can help you manage and review your GitHub repositories.

**Available Commands:**
- `/review all` - Review all repositories
- `/review <repo>` - Review a specific repository
- `/list` - List all repositories
- `/status` - Check system status
- `/pr <repo>` - Create PR for improvements
- `/execute "<task>"` - Delegate a coding task
- `/help` - Show this message

What would you like me to do?
"""
        await update.message.reply_text(welcome_message, parse_mode="Markdown")

    async def help_command(self, update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        help_text = self.parser.get_help_text()
        await update.message.reply_text(help_text, parse_mode="Markdown")

    async def list_repos(self, update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /list command."""
        await update.message.reply_text("🔍 Fetching your repositories...")

        try:
            await self.db.connect()
            repos = await self.db.list_repositories()

            if not repos:
                repos = await self.github.list_all_repositories()

            if not repos:
                await update.message.reply_text("No repositories found.")
                return

            repo_list = "\n".join(
                f"• {r.full_name if hasattr(r, 'full_name') else r['full_name']}"
                for r in repos[:30]
            )

            message = f"**Your Repositories ({len(repos)}):**\n\n{repo_list}"
            if len(repos) > 30:
                message += f"\n...and {len(repos) - 30} more"

            await update.message.reply_text(message, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Error listing repos: {e}")
            await update.message.reply_text(f"Error: {e}")

    async def review_repo(self, update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /review command."""
        target = context.args[0] if context.args else "all"

        if target == "all":
            await update.message.reply_text("🔍 Starting review of all repositories...")
            await self._review_all(update)
        else:
            await update.message.reply_text(f"🔍 Reviewing repository: {target}...")
            await self._review_single(update, target)

    async def _review_all(self, update):
        """Review all repositories."""
        try:
            repos = await self.github.list_all_repositories()
            await update.message.reply_text(f"Found {len(repos)} repositories. Starting review...")

            results = await self.orchestrator.review_all(repos)

            completed = [r for r in results if r.get("status") == "completed"]
            failed = len(results) - len(completed)

            summary = self.report_gen.generate_summary_dashboard(results)
            await update.message.reply_text(summary[:4000], parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Error reviewing all repos: {e}")
            await update.message.reply_text(f"Error: {e}")

    async def _review_single(self, update, repo_name: str):
        """Review a single repository."""
        try:
            repo = await self.github.get_repository(repo_name)

            if not repo:
                await update.message.reply_text(f"Repository '{repo_name}' not found.")
                return

            result = await self.orchestrator.review_repository(repo)

            if result.get("status") == "completed":
                report = self.report_gen.generate_review_report(repo, result)
                await update.message.reply_text(report[:4000], parse_mode="Markdown")
            else:
                await update.message.reply_text(f"Failed to review: {result.get('error')}")

        except Exception as e:
            logger.error(f"Error reviewing {repo_name}: {e}")
            await update.message.reply_text(f"Error: {e}")

    async def check_status(self, update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command."""
        try:
            rate_info = self.github.get_rate_limit_info()

            status_message = "**System Status**\n\n"
            status_message += f"✅ Bot is running\n"

            if rate_info:
                status_message += f"\n**GitHub Rate Limit:**\n"
                status_message += f"• Remaining: {rate_info.remaining}/{rate_info.limit}\n"
                status_message += f"• Reset at: {rate_info.reset_at}"

            await update.message.reply_text(status_message, parse_mode="Markdown")

        except Exception as e:
            await update.message.reply_text(f"Error: {e}")

    async def create_pr(self, update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /pr command."""
        if not context.args:
            await update.message.reply_text("Please specify a repository. Usage: /pr <repo_name>")
            return

        repo_name = context.args[0]
        await update.message.reply_text(f"Creating PR for {repo_name}...")

        await update.message.reply_text("This feature is coming soon!")

    async def execute_task(self, update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /execute command."""
        if not context.args:
            await update.message.reply_text(
                "Please specify a task. Usage: /execute \"<task description>\""
            )
            return

        task = " ".join(context.args)
        await update.message.reply_text(f"🎯 Delegating task: {task}")

        await update.message.reply_text("This feature is coming soon!")

    async def handle_text(self, update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages."""
        text = update.message.text

        command = self.parser.parse(text)

        if command.verb == "help":
            await self.help_command(update, context)
        elif command.verb == "list":
            await self.list_repos(update, context)
        elif command.verb == "status":
            await self.check_status(update, context)
        elif command.verb == "review":
            await self.review_repo(update, context)
        elif command.verb == "create_pr":
            await self.create_pr(update, context)
        elif command.verb == "execute":
            await self.execute_task(update, context)
        else:
            await update.message.reply_text(
                "I didn't understand that command. Type /help for available commands."
            )

    async def run(self):
        """Run the bot."""
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("list", self.list_repos))
        self.application.add_handler(CommandHandler("review", self.review_repo))
        self.application.add_handler(CommandHandler("status", self.check_status))
        self.application.add_handler(CommandHandler("pr", self.create_pr))
        self.application.add_handler(CommandHandler("execute", self.execute_task))
        self.application.add_handler(MessageHandler(TEXT, self.handle_text))

        await self.db.connect()
        logger.info("Starting Telegram bot...")

        await self.application.start()
        await self.application.updater.start_polling(
            poll_interval=config.telegram.poll_timeout
        )

        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass
        finally:
            await self.db.close()
            await self.application.stop()
