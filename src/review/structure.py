"""Structure analyzer for detecting project types and architecture."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..core.config import get_config
from ..core.logging_ import get_logger

logger = get_logger(__name__)

config = get_config()


@dataclass
class ProjectType:
    """Detected project type information."""
    name: str
    language: str
    framework: Optional[str]
    build_system: Optional[str]
    confidence: float


@dataclass
class StructureInfo:
    """Complete structure analysis result."""
    project_type: ProjectType
    directory_tree: Dict[str, Any] = field(default_factory=dict)
    key_files: Dict[str, bool] = field(default_factory=dict)
    test_directories: List[str] = field(default_factory=list)
    documentation_files: List[str] = field(default_factory=list)
    config_files: List[str] = field(default_factory=list)
    source_directories: List[str] = field(default_factory=list)
    detected_patterns: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


class StructureAnalyzer:
    """Analyzes repository structure to detect project type and architecture."""

    PROJECT_PATTERNS = {
        "python": {
            "files": ["setup.py", "pyproject.toml", "requirements.txt", "Pipfile"],
            "dirs": ["src", "tests", "docs"],
            "frameworks": {
                "django": ["django", "DRF"],
                "flask": ["flask"],
                "fastapi": ["fastapi"],
                "pytest": ["pytest"],
                "celery": ["celery"],
            },
        },
        "javascript": {
            "files": ["package.json", "yarn.lock", "pnpm-lock.yaml"],
            "dirs": ["src", "tests", "public"],
            "frameworks": {
                "react": ["react", "react-dom"],
                "vue": ["vue"],
                "angular": ["@angular/core"],
                "express": ["express"],
                "next": ["next"],
            },
        },
        "typescript": {
            "files": ["tsconfig.json", "package.json"],
            "dirs": ["src", "tests"],
            "frameworks": {
                "react": ["react", "react-dom"],
                "vue": ["vue"],
                "nest": ["@nestjs/core"],
            },
        },
        "go": {
            "files": ["go.mod", "go.sum", "Gopkg.toml"],
            "dirs": ["cmd", "internal", "pkg", "test"],
            "frameworks": {
                "gin": ["github.com/gin-gonic/gin"],
                "echo": ["github.com/labstack/echo"],
                "fiber": ["github.com/gofiber/fiber"],
            },
        },
        "rust": {
            "files": ["Cargo.toml", "Cargo.lock"],
            "dirs": ["src", "tests", "examples"],
            "frameworks": {
                "actix": ["actix-web"],
                "rocket": ["rocket"],
                "warp": ["warp"],
            },
        },
        "java": {
            "files": ["pom.xml", "build.gradle", "settings.gradle"],
            "dirs": ["src/main", "src/test", "src/main/java"],
            "frameworks": {
                "spring": ["org.springframework"],
                "maven": ["maven"],
            },
        },
        "cpp": {
            "files": ["CMakeLists.txt", "Makefile", "setup.py"],
            "dirs": ["include", "src", "lib"],
            "frameworks": {},
        },
    }

    KEY_FILES = {
        "README.md": "Project documentation",
        "readme.md": "Project documentation",
        "CONTRIBUTING.md": "Contribution guidelines",
        "CODE_OF_CONDUCT.md": "Community guidelines",
        "LICENSE": "License file",
        "COPYING": "License file",
        "Dockerfile": "Docker configuration",
        "docker-compose.yml": "Docker Compose configuration",
        ".dockerignore": "Docker ignore file",
        ".gitignore": "Git ignore file",
        ".env.example": "Environment template",
        ".eslintrc": "ESLint configuration",
        ".prettierrc": "Prettier configuration",
        "pytest.ini": "Pytest configuration",
        "mypy.ini": "Mypy configuration",
        "tox.ini": "Tox configuration",
    }

    TEST_DIRS = [
        "test",
        "tests",
        "__tests__",
        "spec",
        "specs",
        "testing",
        "Test",
        "Tests",
    ]

    DOC_DIRS = [
        "doc",
        "docs",
        "documentation",
        "Doc",
        "Docs",
    ]

    def __init__(self):
        self.detected_language = None
        self.detected_framework = None

    def analyze(
        self,
        file_tree: List[Dict[str, Any]],
        file_contents: Optional[Dict[str, str]] = None,
    ) -> StructureInfo:
        """Analyze repository structure."""
        result = StructureInfo()

        self._categorize_files(file_tree, result)

        self._detect_project_type(result)

        self._detect_framework(file_contents, result)

        self._analyze_directories(file_tree, result)

        self._detect_patterns(result)

        self._generate_recommendations(result)

        return result

    def _categorize_files(
        self, file_tree: List[Dict[str, Any]], result: StructureInfo
    ) -> None:
        """Categorize files by type."""
        for item in file_tree:
            path = item["path"]
            name = item["name"]

            if item["type"] == "dir":
                if name.lower() in [d.lower() for d in self.TEST_DIRS]:
                    result.test_directories.append(path)
                elif name.lower() in [d.lower() for d in self.DOC_DIRS]:
                    result.documentation_files.append(path)
                elif name in ("src", "lib", "include", "internal"):
                    result.source_directories.append(path)
            else:
                if name in self.KEY_FILES:
                    result.key_files[name] = True

                for config_file in self.KEY_FILES:
                    if config_file.lower() in path.lower():
                        result.config_files.append(path)

    def _detect_project_type(self, result: StructureInfo) -> None:
        """Detect the programming language and project type."""
        for lang, patterns in self.PROJECT_PATTERNS.items():
            matched_files = 0

            for file_pattern in patterns["files"]:
                if file_pattern in result.key_files:
                    matched_files += 1

            if matched_files > 0:
                result.project_type = ProjectType(
                    name=f"{lang.title()} Project",
                    language=lang,
                    framework=None,
                    confidence=min(1.0, matched_files / len(patterns["files"]) + 0.3),
                )
                self.detected_language = lang
                return

        result.project_type = ProjectType(
            name="Unknown Project",
            language="unknown",
            framework=None,
            confidence=0.0,
        )

    def _detect_framework(
        self, file_contents: Optional[Dict[str, str]], result: StructureInfo
    ) -> None:
        """Detect the framework used."""
        if not file_contents or self.detected_language not in self.PROJECT_PATTERNS:
            return

        frameworks = self.PROJECT_PATTERNS[self.detected_language].get("frameworks", {})

        for framework, indicators in frameworks.items():
            for indicator in indicators:
                for path, content in file_contents.items():
                    if indicator in content:
                        result.project_type.framework = framework
                        self.detected_framework = framework
                        return

    def _analyze_directories(
        self, file_tree: List[Dict[str, Any]], result: StructureInfo
    ) -> None:
        """Analyze directory structure."""
        dirs = {item["path"]: item for item in file_tree if item["type"] == "dir"}

        result.directory_tree = self._build_tree(file_tree)

        if not result.source_directories:
            common_src_dirs = ["app", "lib", "core", "modules", "packages"]
            for dir_name in common_src_dirs:
                for path in dirs:
                    if path.endswith(f"/{dir_name}") or path == dir_name:
                        result.source_directories.append(path)
                        break

    def _build_tree(self, file_tree: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Build a tree structure from flat file list."""
        tree = {}

        for item in file_tree:
            parts = item["path"].split("/")
            current = tree

            for i, part in enumerate(parts):
                if part not in current:
                    current[part] = {}

                if i == len(parts) - 1:
                    current[part] = {"_file": item}
                else:
                    if "_files" not in current[part]:
                        current[part]["_files"] = []

                current = current[part]

        return tree

    def _detect_patterns(self, result: StructureInfo) -> None:
        """Detect common project patterns."""
        patterns = []

        if result.test_directories:
            patterns.append("has_tests")

        if "README.md" in result.key_files:
            patterns.append("has_documentation")

        if any("docker" in f.lower() for f in result.config_files):
            patterns.append("has_docker")

        if any(
            f in result.config_files
            for f in [".eslintrc", ".prettierrc", "tsconfig.json"]
        ):
            patterns.append("has_linting")

        if any(
            f in result.config_files
            for f in ["pyproject.toml", "package.json", "go.mod"]
        ):
            patterns.append("has_dependency_management")

        if any("github" in f.lower() for f in result.config_files):
            patterns.append("has_ci_cd")

        if result.source_directories:
            patterns.append("modular_structure")

        result.detected_patterns = patterns

    def _generate_recommendations(self, result: StructureInfo) -> None:
        """Generate recommendations based on analysis."""
        recommendations = []

        if not result.documentation_files and "README.md" not in result.key_files:
            recommendations.append("Add a README.md file with project documentation")

        if not result.test_directories:
            recommendations.append("Consider adding tests for better code quality")

        if not any("docker" in f.lower() for f in result.config_files):
            recommendations.append("Consider adding Docker configuration for deployment")

        if not any(
            f in result.config_files
            for f in [".gitignore", ".dockerignore"]
        ):
            recommendations.append("Add .gitignore and .dockerignore files")

        if result.detected_language == "python" and "requirements.txt" not in result.key_files:
            recommendations.append("Add requirements.txt for Python dependencies")

        if result.detected_language == "javascript" and "package.json" not in result.key_files:
            recommendations.append("Add package.json for Node.js dependencies")

        result.recommendations = recommendations

    def get_structure_summary(self, info: StructureInfo) -> str:
        """Generate a text summary of the structure."""
        lines = [
            f"Project Type: {info.project_type.name}",
            f"Language: {info.project_type.language}",
        ]

        if info.project_type.framework:
            lines.append(f"Framework: {info.project_type.framework}")

        lines.append(f"Confidence: {info.project_type.confidence:.0%}")
        lines.append(f"Source Directories: {', '.join(info.source_directories)}")
        lines.append(f"Test Directories: {', '.join(info.test_directories)}")

        if info.detected_patterns:
            lines.append(f"Patterns: {', '.join(info.detected_patterns)}")

        if info.recommendations:
            lines.append("Recommendations:")
            for rec in info.recommendations:
                lines.append(f"  - {rec}")

        return "\n".join(lines)
