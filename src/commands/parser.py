"""Command parser for natural language commands."""

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class Command:
    """Parsed command."""
    verb: str
    noun: Optional[str]
    modifiers: Dict[str, Any]
    original_text: str


class CommandParser:
    """Parses natural language commands into structured commands."""

    COMMAND_PATTERNS = {
        "review": [
            r"review\s+(?:all|every|my\s+repos?)",
            r"review\s+(?:the\s+)?repo(?:sitory)?\s+([^\s]+)",
            r"check\s+(?:out\s+)?([^\s]+)",
            r"analyze\s+([^\s]+)",
        ],
        "list": [
            r"list\s+(?:all\s+)?repos(?:itories)?",
            r"show\s+(?:me\s+)?repos",
            r"what\s+repos(?:itories)?\s+(?:do\s+I\s+have)?",
        ],
        "status": [
            r"status",
            r"how\s+(?:is|are)\s+(?:things|it|they)",
            r"what['s]?\s+(?:the\s+)?status",
        ],
        "create_pr": [
            r"create\s+(?:a\s+)?pr\s+(?:for\s+)?([^\s]+)",
            r"make\s+(?:a\s+)?pull\s+request\s+(?:for\s+)?([^\s]+)",
            r"pr\s+(?:for\s+)?([^\s]+)",
        ],
        "merge_pr": [
            r"merge\s+(?:pr|pull\s+request)\s*(?:#)?(\d+)",
            r"merge\s+(?:the\s+)?(\d+)",
        ],
        "execute": [
            r"execute\s+(?:['\"]?)(.+?)(?:['\"]?)\s*$",
            r"do\s+(?:['\"]?)(.+?)(?:['\"]?)$",
            r"delegate\s+(?:['\"]?)(.+?)(?:['\"]?)$",
            r"work\s+on\s+(?:['\"]?)(.+?)(?:['\"]?)$",
        ],
        "help": [
            r"help",
            r"what\s+(?:can\s+you\s+do|[']s]\s+up)",
            r"show\s+(?:me\s+)?commands",
        ],
        "update_docs": [
            r"update\s+(?:the\s+)?readme\s+(?:for\s+)?([^\s]+)",
            r"update\s+docs\s+(?:for\s+)?([^\s]+)",
        ],
        "refresh": [
            r"refresh",
            r"run\s+again",
            r"restart",
        ],
    }

    def parse(self, text: str) -> Command:
        """Parse a command from text."""
        text = text.strip().lower()

        for verb, patterns in self.COMMAND_PATTERNS.items():
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    modifiers = self._extract_modifiers(match)
                    noun = self._extract_noun(match)

                    return Command(
                        verb=verb,
                        noun=noun,
                        modifiers=modifiers,
                        original_text=text,
                    )

        return Command(
            verb="unknown",
            noun=None,
            modifiers={},
            original_text=text,
        )

    def _extract_modifiers(self, match: re.Match) -> Dict[str, Any]:
        """Extract modifiers from regex match."""
        modifiers = {}

        groups = match.groups()
        if len(groups) > 1:
            modifiers["target"] = groups[1] if len(groups) > 1 else None

        return modifiers

    def _extract_noun(self, match: re.Match) -> Optional[str]:
        """Extract the main noun from regex match."""
        groups = match.groups()
        if groups and groups[0]:
            return groups[0]
        return None

    def get_help_text(self) -> str:
        """Get help text for available commands."""
        return """
**Available Commands:**

1. **Review Repositories**
   - `/review all` - Review all repositories
   - `/review <repo_name>` - Review a specific repository
   - `/analyze <repo_name>` - Analyze a specific repository

2. **List Repositories**
   - `/list` - List all tracked repositories
   - `/list repos` - List all your repositories

3. **Status**
   - `/status` - Show overall system status
   - `/how are things` - Check current status

4. **Pull Requests**
   - `/pr <repo_name>` - Create PR for improvements
   - `/merge <pr_number>` - Merge a pull request

5. **Task Execution**
   - `/execute "<task>"` - Delegate a coding task
   - `/do "fix the bug in file.py"` - Execute a specific task
   - `/delegate "update documentation"` - Delegate work

6. **Documentation**
   - `/update docs <repo_name>` - Update documentation for a repo

7. **System**
   - `/refresh` - Refresh all reviews
   - `/help` - Show this help message

**Examples:**
- `review all`
- `analyze my-api-project`
- `create pr for web-app`
- `execute "add tests to auth module"`
- `merge 42`
"""


class TaskInterpreter:
    """Interprets natural language tasks into actionable items."""

    def __init__(self):
        self.parsers = {
            "add_test": self._parse_add_test,
            "fix_bug": self._parse_fix_bug,
            "add_feature": self._parse_add_feature,
            "update_docs": self._parse_update_docs,
            "refactor": self._parse_refactor,
            "improve": self._parse_improve,
        }

    def interpret(self, task_description: str) -> Dict[str, Any]:
        """Interpret a task description."""
        description = task_description.lower()

        if "test" in description or "spec" in description:
            return self._parse_add_test(task_description)

        if any(word in description for word in ["fix", "bug", "error", "issue"]):
            return self._parse_fix_bug(task_description)

        if any(word in description for word in ["add", "implement", "create", "new"]):
            return self._parse_add_feature(task_description)

        if any(word in description for word in ["document", "readme", "doc"]):
            return self._parse_update_docs(task_description)

        if any(word in description for word in ["refactor", "improve", "clean"]):
            return self._parse_refactor(task_description)

        return {
            "action": "general",
            "description": task_description,
            "priority": "medium",
            "target_repo": None,
            "target_file": None,
        }

    def _parse_add_test(self, description: str) -> Dict[str, Any]:
        """Parse a test-related task."""
        files = self._extract_file_paths(description)
        return {
            "action": "add_tests",
            "description": description,
            "priority": "medium",
            "target_repo": self._extract_repo_name(description),
            "target_files": files if files else None,
        }

    def _parse_fix_bug(self, description: str) -> Dict[str, Any]:
        """Parse a bug fix task."""
        files = self._extract_file_paths(description)
        return {
            "action": "fix_bug",
            "description": description,
            "priority": "high",
            "target_repo": self._extract_repo_name(description),
            "target_files": files if files else None,
        }

    def _parse_add_feature(self, description: str) -> Dict[str, Any]:
        """Parse a feature addition task."""
        return {
            "action": "add_feature",
            "description": description,
            "priority": "medium",
            "target_repo": self._extract_repo_name(description),
            "target_files": None,
        }

    def _parse_update_docs(self, description: str) -> Dict[str, Any]:
        """Parse a documentation update task."""
        return {
            "action": "update_docs",
            "description": description,
            "priority": "low",
            "target_repo": self._extract_repo_name(description),
            "target_files": None,
        }

    def _parse_refactor(self, description: str) -> Dict[str, Any]:
        """Parse a refactoring task."""
        files = self._extract_file_paths(description)
        return {
            "action": "refactor",
            "description": description,
            "priority": "low",
            "target_repo": self._extract_repo_name(description),
            "target_files": files if files else None,
        }

    def _extract_file_paths(self, description: str) -> List[str]:
        """Extract file paths from description."""
        patterns = [
            r"([\w/\.-]+\.py)",
            r"([\w/\.-]+\.js)",
            r"([\w/\.-]+\.ts)",
            r"in\s+([\w/\.-]+)",
        ]
        files = []
        for pattern in patterns:
            matches = re.findall(pattern, description)
            files.extend(matches)
        return list(set(files))[:5]

    def _extract_repo_name(self, description: str) -> Optional[str]:
        """Extract repository name from description."""
        patterns = [
            r"(?:repo(?:sitory)?\s+)?([\w-]+)",
            r"for\s+([\w-]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, description, re.IGNORECASE)
            if match:
                return match.group(1)
        return None
