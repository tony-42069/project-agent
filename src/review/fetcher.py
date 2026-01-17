"""File fetching system with concurrent downloads and caching."""

import asyncio
import hashlib
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.config import get_config
from ..core.logging_ import get_logger
from ..github import GitHubClient

logger = get_logger(__name__)

config = get_config()


@dataclass
class FetchedFile:
    """A fetched file with content and metadata."""
    path: str
    content: str
    size: int
    sha: str
    fetch_time: float
    from_cache: bool = False


@dataclass
class FetchStats:
    """Statistics for file fetching operations."""
    total_files: int = 0
    cached_files: int = 0
    fetched_files: int = 0
    failed_files: int = 0
    total_bytes: int = 0
    total_time: float = 0.0


class FileFetcher:
    """Fetches files from GitHub with concurrency and caching."""

    def __init__(self, github_client: GitHubClient, cache_dir: Optional[str] = None):
        self.github = github_client
        self.cache_dir = Path(cache_dir) if cache_dir else Path("data/file_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, FetchedFile] = {}
        self._stats = FetchStats()

    def _get_cache_key(self, full_name: str, path: str) -> str:
        """Generate a cache key for a file."""
        key = f"{full_name}/{path}"
        return hashlib.md5(key.encode()).hexdigest()

    def _get_cache_path(self, full_name: str, path: str) -> Path:
        """Get the cache file path for a file."""
        key = self._get_cache_key(full_name, path)
        return self.cache_dir / f"{key}.cache"

    def _is_cache_valid(self, cache_path: Path) -> bool:
        """Check if a cache file is still valid."""
        if not cache_path.exists():
            return False

        max_age = config.openai.cache_ttl
        age = time.time() - cache_path.stat().st_mtime

        return age < max_age

    def _get_from_cache(self, full_name: str, path: str) -> Optional[FetchedFile]:
        """Get a file from the local cache."""
        cache_path = self._get_cache_path(full_name, path)

        if not self._is_cache_valid(cache_path):
            return None

        try:
            import json

            with open(cache_path, "r") as f:
                data = json.load(f)

            return FetchedFile(
                path=data["path"],
                content=data["content"],
                size=data["size"],
                sha=data["sha"],
                fetch_time=data["fetch_time"],
                from_cache=True,
            )
        except Exception as e:
            logger.debug(f"Cache read failed: {e}")
            return None

    def _save_to_cache(self, full_name: str, file: FetchedFile) -> None:
        """Save a file to the local cache."""
        cache_path = self._get_cache_path(full_name, file.path)

        try:
            import json

            cache_data = {
                "path": file.path,
                "content": file.content,
                "size": file.size,
                "sha": file.sha,
                "fetch_time": file.fetch_time,
            }

            with open(cache_path, "w") as f:
                json.dump(cache_data, f)
        except Exception as e:
            logger.debug(f"Cache write failed: {e}")

    async def fetch_file(
        self, full_name: str, path: str, use_cache: bool = True
    ) -> Optional[FetchedFile]:
        """Fetch a single file from a repository."""
        start_time = time.time()

        if use_cache:
            cached = self._get_from_cache(full_name, path)
            if cached:
                self._stats.cached_files += 1
                logger.debug(f"Cache hit: {full_name}/{path}")
                return cached

        file_content = await self.github.get_file_content(full_name, path)

        if not file_content:
            self._stats.failed_files += 1
            return None

        fetch_time = time.time() - start_time

        fetched = FetchedFile(
            path=file_content.path,
            content=file_content.content,
            size=file_content.size,
            sha=file_content.sha,
            fetch_time=fetch_time,
            from_cache=False,
        )

        self._stats.fetched_files += 1
        self._stats.total_bytes += file_content.size
        self._stats.total_time += fetch_time

        if use_cache:
            self._save_to_cache(full_name, fetched)

        return fetched

    async def fetch_files(
        self,
        full_name: str,
        paths: List[str],
        max_concurrent: int = 5,
        use_cache: bool = True,
    ) -> Dict[str, FetchedFile]:
        """Fetch multiple files concurrently."""
        semaphore = asyncio.Semaphore(max_concurrent)

        async def fetch_with_semaphore(path: str) -> tuple[str, Optional[FetchedFile]]:
            async with semaphore:
                result = await self.fetch_file(full_name, path, use_cache)
                return path, result

        tasks = [fetch_with_semaphore(path) for path in paths]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        fetched = {}
        for path, result in results:
            if isinstance(result, Exception):
                logger.error(f"Error fetching {path}: {result}")
                self._stats.failed_files += 1
            elif result:
                fetched[path] = result

        self._stats.total_files = len(paths)
        return fetched

    async def fetch_directory_tree(
        self,
        full_name: str,
        max_files: int = 100,
        max_depth: int = 3,
        use_cache: bool = True,
    ) -> Dict[str, FetchedFile]:
        """Fetch all files from a repository directory tree."""
        file_tree = await self.github.get_file_tree(
            full_name, max_depth=max_depth, max_files=max_files
        )

        file_paths = [
            f["path"] for f in file_tree if f["type"] == "file"
        ]

        logger.info(f"Fetching {len(file_paths)} files from {full_name}")

        fetched = await self.fetch_files(
            full_name, file_paths, max_concurrent=5, use_cache=use_cache
        )

        return fetched

    async def fetch_key_files(
        self,
        full_name: str,
        key_files: List[str],
        use_cache: bool = True,
    ) -> Dict[str, FetchedFile]:
        """Fetch key files from a repository."""
        existing_paths = []

        for key_file in key_files:
            try:
                content = await self.github.get_file_content(full_name, key_file)
                if content:
                    existing_paths.append(key_file)
            except Exception:
                pass

        return await self.fetch_files(
            full_name, existing_paths or key_files, max_concurrent=3, use_cache=use_cache
        )

    def get_stats(self) -> FetchStats:
        """Get fetching statistics."""
        return self._stats

    def clear_cache(self, older_than: Optional[int] = None) -> int:
        """Clear the file cache."""
        removed = 0

        for cache_file in self.cache_dir.glob("*.cache"):
            if older_than:
                age = time.time() - cache_file.stat().st_mtime
                if age > older_than:
                    cache_file.unlink()
                    removed += 1
            else:
                cache_file.unlink()
                removed += 1

        self._cache.clear()
        logger.info(f"Cleared {removed} cache files")
        return removed

    async def prioritize_files(
        self, full_name: str, files: List[Dict[str, Any]]
    ) -> List[str]:
        """Prioritize files for fetching based on importance."""
        priority_order = [
            "README.md",
            "readme.md",
            "SETUP.md",
            "setup.py",
            "pyproject.toml",
            "requirements.txt",
            "package.json",
            "go.mod",
            "Cargo.toml",
            "Makefile",
            "CMakeLists.txt",
            "Dockerfile",
            "docker-compose.yml",
            ".env.example",
            "index.js",
            "main.py",
            "app.py",
            "server.py",
        ]

        priority_map = {}
        for i, pattern in enumerate(priority_order):
            priority_map[pattern] = i

        def get_priority(file: Dict[str, Any]) -> int:
            name = file["name"]
            if name in priority_map:
                return priority_map[name]

            ext = Path(name).suffix.lower()
            if ext in (".py", ".js", ".ts", ".go", ".rs"):
                return 50 + priority_order.index(name) if name in priority_order else 100

            if ext in (".md", ".txt", ".json", ".yaml", ".yml"):
                return 30

            return 200

        sorted_files = sorted(files, key=get_priority)
        return [f["path"] for f in sorted_files]

    def estimate_fetch_time(self, files: List[str]) -> float:
        """Estimate fetch time for a list of files."""
        avg_time = (
            self._stats.total_time / self._stats.fetched_files
            if self._stats.fetched_files > 0
            else 0.1
        )
        return len(files) * avg_time
