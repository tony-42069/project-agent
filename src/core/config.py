"""Configuration loader with environment variable support."""

import os
from pathlib import Path
from typing import Any, Dict, Optional
from dataclasses import dataclass, field

import yaml
from dotenv import load_dotenv

load_dotenv()


@dataclass
class AppConfig:
    name: str = "project-agent"
    debug: bool = False
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8000


@dataclass
class DatabaseConfig:
    path: str = "data/project_agent.db"
    echo: bool = False


@dataclass
class GitHubConfig:
    api_url: str = "https://api.github.com"
    token_env: str = "GITHUB_TOKEN"
    rate_limit_wait: float = 1.0
    max_retries: int = 3
    timeout: int = 30


@dataclass
class OpenAIConfig:
    api_key_env: str = "OPENAI_API_KEY"
    model: str = "gpt-4o"
    max_tokens: int = 4096
    temperature: float = 0.3
    cache_enabled: bool = True
    cache_ttl: int = 3600


@dataclass
class TelegramConfig:
    enabled: bool = True
    token_env: str = "TELEGRAM_BOT_TOKEN"
    webhook_url_env: str = "TELEGRAM_WEBHOOK_URL"
    poll_timeout: int = 10


@dataclass
class ReviewConfig:
    max_files_per_repo: int = 100
    file_size_limit: int = 100000
    exclude_patterns: list = field(default_factory=list)
    include_extensions: list = field(default_factory=list)


@dataclass
class ReportConfig:
    output_dir: str = "reports"
    branch_name: str = "repo-status-update"
    commit_message: str = "docs: Update REPO_STATUS.md with latest review"


@dataclass
class TaskConfig:
    queue_size: int = 10
    timeout: int = 300
    max_retries: int = 2


@dataclass
class MonitoringConfig:
    health_check_interval: int = 60
    metrics_enabled: bool = True


@dataclass
class Config:
    app: AppConfig = field(default_factory=AppConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    github: GitHubConfig = field(default_factory=GitHubConfig)
    openai: OpenAIConfig = field(default_factory=OpenAIConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    review: ReviewConfig = field(default_factory=ReviewConfig)
    report: ReportConfig = field(default_factory=ReportConfig)
    task: TaskConfig = field(default_factory=TaskConfig)
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Config":
        config = cls()

        if "app" in data:
            config.app = AppConfig(**data["app"])

        if "database" in data:
            config.database = DatabaseConfig(**data["database"])

        if "github" in data:
            config.github = GitHubConfig(**data["github"])

        if "openai" in data:
            config.openai = OpenAIConfig(**data["openai"])

        if "telegram" in data:
            config.telegram = TelegramConfig(**data["telegram"])

        if "review" in data:
            config.review = ReviewConfig(**data["review"])

        if "report" in data:
            config.report = ReportConfig(**data["report"])

        if "task" in data:
            config.task = TaskConfig(**data["task"])

        if "monitoring" in data:
            config.monitoring = MonitoringConfig(**data["monitoring"])

        return config

    @classmethod
    def load(cls, config_path: Optional[str] = None) -> "Config":
        if config_path is None:
            config_path = os.getenv("CONFIG_PATH", "config.yaml")

        path = Path(config_path)

        if path.exists():
            with open(path, "r") as f:
                data = yaml.safe_load(f)
            return cls.from_dict(data or {})

        return cls()


def get_config() -> Config:
    return Config.load()


settings = get_config()
