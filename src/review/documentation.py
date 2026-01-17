"""Documentation analyzer for reviewing and improving documentation."""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..core.config import get_config
from ..core.logging_ import get_logger

logger = get_logger(__name__)

config = get_config()


@dataclass
class DocIssue:
    """A documentation issue."""
    type: str
    severity: str
    file: str
    description: str
    suggestion: str


@dataclass
class DocAnalysis:
    """Complete documentation analysis result."""
    has_readme: bool = False
    has_license: bool = False
    has_contributing: bool = False
    has_code_of_conduct: bool = False
    has_api_docs: bool = False
    has_setup_instructions: bool = False
    has_examples: bool = False
    readme_quality: int = 0
    issues: List[DocIssue] = field(default_factory=list)
    missing_docs: List[str] = field(default_factory=list)
    outdated_info: List[str] = field(default_factory=list)
    tech_stack: List[str] = field(default_factory=list)
    summary: str = ""


class DocumentationAnalyzer:
    """Analyzes documentation quality and completeness."""

    README_SECTIONS = [
        ("title", r"^#\s+.+"),
        ("description", r"(?i)description[:\s]*.{10,}"),
        ("installation", r"(?i)(install|setup|getting started)"),
        ("usage", r"(?i)usage[:\s]*|example[s]?[:\s]*"),
        ("features", r"(?i)features[:\s]*"),
        ("contributing", r"(?i)contributing[:\s]*"),
        ("license", r"(?i)license[:\s]*"),
        ("contact", r"(?i)(contact|author)[:\s]*"),
    ]

    LICENSE_FILES = [
        "LICENSE",
        "LICENSE.md",
        "LICENSE.txt",
        "COPYING",
        "COPYING.md",
        "UNLICENSE",
    ]

    def __init__(self):
        self._tech_stack_patterns = {
            "python": [r"python", r"django", r"flask", r"fastapi", r"pytest"],
            "javascript": [r"node\.?js", r"react", r"vue", r"express", r"npm"],
            "typescript": [r"typescript", r"react", r"vue", r"nestjs"],
            "go": [r"golang", r"go\s+1\.\d+"],
            "rust": [r"rust", r"cargo"],
            "database": [r"postgresql", r"mysql", r"mongodb", r"redis", r"sqlite"],
            "devops": [r"docker", r"kubernetes", r"aws", r"ci/cd", r"github actions"],
        }

    def analyze(
        self,
        file_contents: Dict[str, str],
        structure_info: Optional[Dict[str, Any]] = None,
    ) -> DocAnalysis:
        """Analyze documentation in a repository."""
        analysis = DocAnalysis()

        self._check_required_docs(analysis, file_contents)
        self._analyze_readme(analysis, file_contents)
        self._extract_tech_stack(analysis, file_contents)
        self._check_setup_instructions(analysis, file_contents)
        self._check_examples(analysis, file_contents)
        self._identify_missing_docs(analysis)
        self._detect_outdated_info(analysis, file_contents)
        self._generate_summary(analysis)

        return analysis

    def _check_required_docs(self, analysis: DocAnalysis, file_contents: Dict[str, str]) -> None:
        """Check for required documentation files."""
        paths = list(file_contents.keys())

        for path in paths:
            path_lower = path.lower()

            if "readme" in path_lower:
                analysis.has_readme = True

            if any(lic in path for lic in self.LICENSE_FILES):
                analysis.has_license = True

            if "contributing" in path_lower:
                analysis.has_contributing = True

            if "code of conduct" in path_lower or "codeofconduct" in path_lower:
                analysis.has_code_of_conduct = True

            if "api" in path_lower and "doc" in path_lower:
                analysis.has_api_docs = True

    def _analyze_readme(self, analysis: DocAnalysis, file_contents: Dict[str, str]) -> None:
        """Analyze README quality and completeness."""
        readme_content = None
        readme_path = None

        for path, content in file_contents.items():
            if "readme" in path.lower() and path.endswith((".md", ".txt")):
                readme_content = content
                readme_path = path
                break

        if not readme_content:
            analysis.issues.append(
                DocIssue(
                    type="missing_file",
                    severity="high",
                    file="README.md",
                    description="No README file found",
                    suggestion="Create a README.md with project overview, installation, and usage instructions",
                )
            )
            return

        score = 50

        sections_found = 0
        for section_name, pattern in self.README_SECTIONS:
            if re.search(pattern, readme_content):
                sections_found += 1

        score += sections_found * 7
        score = min(100, score)

        analysis.readme_quality = score

        if score < 60:
            analysis.issues.append(
                DocIssue(
                    type="incomplete_readme",
                    severity="medium",
                    file=readme_path,
                    description=f"README is incomplete ({score:.0f}%)",
                    suggestion="Add missing sections: description, installation, usage, features",
                )
            )

        if len(readme_content) < 200:
            analysis.issues.append(
                DocIssue(
                    type="too_short",
                    severity="low",
                    file=readme_path,
                    description="README is very short",
                    suggestion="Add more detailed documentation",
                )
            )

        if "todo" in readme_content.lower():
            analysis.issues.append(
                DocIssue(
                    type="outdated",
                    severity="low",
                    file=readme_path,
                    description="README contains TODO items",
                    suggestion="Review and complete or remove TODO items from README",
                )
            )

        if not re.search(r"!\[.+\]\(.+\)", readme_content) and len(readme_content) > 500:
            if readme_path:
                analysis.issues.append(
                    DocIssue(
                        type="missing_images",
                        severity="low",
                        file=readme_path,
                        description="No images/screenshots in README",
                        suggestion="Consider adding screenshots or diagrams to improve documentation",
                    )
                )

    def _extract_tech_stack(self, analysis: DocAnalysis, file_contents: Dict[str, str]) -> None:
        """Extract technology stack from documentation."""
        all_content = " ".join(file_contents.values()).lower()

        detected = set()

        for category, patterns in self._tech_stack_patterns.items():
            for pattern in patterns:
                if re.search(pattern, all_content):
                    detected.add(category)

        analysis.tech_stack = sorted(list(detected))

    def _check_setup_instructions(
        self, analysis: DocAnalysis, file_contents: Dict[str, str]
    ) -> None:
        """Check for setup/installation instructions."""
        setup_patterns = [
            r"(?i)pip\s+install",
            r"(?i)npm\s+install",
            r"(?i)yarn\s+add",
            r"(?i)docker\s+build",
            r"(?i)docker-compose\s+up",
            r"(?i)go\s+get",
            r"(?i)cargo\s+build",
            r"(?i)make\s+install",
            r"(?i)python\s+-m\s+venv",
            r"(?i)virtualenv",
        ]

        has_install = any(
            re.search(pattern, content)
            for content in file_contents.values()
            for pattern in setup_patterns
        )

        if has_install:
            analysis.has_setup_instructions = True
        else:
            missing_section = any(
                re.search(pattern, content)
                for content in file_contents.values()
                for pattern in [
                    r"(?i)setup[:\s]*|install[:\s]*|getting started[:\s]*"
                ]
            )

            if not missing_section:
                analysis.issues.append(
                    DocIssue(
                        type="missing_section",
                        severity="medium",
                        file="README.md",
                        description="No setup/installation instructions found",
                        suggestion="Add installation and setup instructions",
                    )
                )

    def _check_examples(self, analysis: DocAnalysis, file_contents: Dict[str, str]) -> None:
        """Check for code examples."""
        example_patterns = [
            r"```\w+",
            r"(?i)example[s]?[:\s]*",
            r"(?i)usage[:\s]*",
            r"(?i)how\s+to\s+use",
        ]

        has_examples = any(
            re.search(pattern, content)
            for content in file_contents.values()
            for pattern in example_patterns
        )

        if has_examples:
            analysis.has_examples = True
        else:
            analysis.issues.append(
                DocIssue(
                    type="missing_examples",
                    severity="low",
                    file="Documentation",
                    description="No code examples found",
                    suggestion="Add usage examples and code snippets",
                )
            )

    def _identify_missing_docs(self, analysis: DocAnalysis) -> None:
        """Identify missing documentation files."""
        missing = []

        if not analysis.has_readme:
            missing.append("README.md - Main project documentation")

        if not analysis.has_license:
            missing.append("LICENSE - License information")

        if not analysis.has_contributing:
            missing.append("CONTRIBUTING.md - Contribution guidelines")

        if not analysis.has_code_of_conduct:
            missing.append("CODE_OF_CONDUCT.md - Community guidelines")

        if not analysis.has_api_docs:
            missing.append("API documentation")

        analysis.missing_docs = missing

    def _detect_outdated_info(
        self, analysis: DocAnalysis, file_contents: Dict[str, str]
    ) -> None:
        """Detect potentially outdated information."""
        outdated = []

        for path, content in file_contents.items():
            content_lower = content.lower()

            if "todo" in content_lower:
                outdated.append(f"TODO items in {path}")

            if "fixme" in content_lower:
                outdated.append(f"FIXME items in {path}")

            if "deprecated" in content_lower:
                outdated.append(f"Deprecated code in {path}")

            version_patterns = [
                (r"python\s+2\.\d+", "Python 2.x mentioned"),
                (r"node\s+[0-9]+\.[0-9]+\.[0-9]+", "Specific Node version mentioned"),
                (r"old\s+version|outdated", "Old/outdated references"),
            ]

            for pattern, desc in version_patterns:
                if re.search(pattern, content_lower):
                    outdated.append(f"{desc} in {path}")
                    break

        analysis.outdated_info = outdated[:10]

    def _generate_summary(self, analysis: DocAnalysis) -> None:
        """Generate a summary of the documentation analysis."""
        score = 100

        if not analysis.has_readme:
            score -= 30
        elif analysis.readme_quality < 70:
            score -= 20

        if not analysis.has_license:
            score -= 15

        if not analysis.has_contributing:
            score -= 10

        if not analysis.has_examples:
            score -= 10

        if analysis.issues:
            for issue in analysis.issues:
                if issue.severity == "high":
                    score -= 15
                elif issue.severity == "medium":
                    score -= 10
                else:
                    score -= 5

        score = max(0, min(100, score))

        status = "Excellent"
        if score < 90:
            status = "Good"
        if score < 70:
            status = "Needs Improvement"
        if score < 50:
            status = "Poor"

        analysis.summary = f"""Documentation Score: {score}/100 ({status})

Files Found:
- README: {'✓' if analysis.has_readme else '✗'} (Quality: {analysis.readme_quality}%)
- License: {'✓' if analysis.has_license else '✗'}
- Contributing: {'✓' if analysis.has_contributing else '✗'}
- Code of Conduct: {'✓' if analysis.has_code_of_conduct else '✗'}
- Setup Instructions: {'✓' if analysis.has_setup_instructions else '✗'}
- Examples: {'✓' if analysis.has_examples else '✗'}

Issues Found: {len(analysis.issues)}
Missing Documentation: {len(analysis.missing_docs)}
Outdated Information: {len(analysis.outdated_info)}

Detected Tech Stack: {', '.join(analysis.tech_stack) if analysis.tech_stack else 'Unknown'}
"""

    def get_quick_score(self, analysis: DocAnalysis) -> int:
        """Get a quick documentation quality score."""
        score = 0

        if analysis.has_readme:
            score += 30
            score += analysis.readme_quality // 5

        if analysis.has_license:
            score += 15

        if analysis.has_contributing:
            score += 10

        if analysis.has_setup_instructions:
            score += 10

        if analysis.has_examples:
            score += 10

        if not analysis.issues:
            score += 15

        score = min(100, score)
        return score
