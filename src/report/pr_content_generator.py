"""PR content generation service for creating PR descriptions."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..core.config import get_config
from ..core.logging_ import get_logger

logger = get_logger(__name__)

config = get_config()


@dataclass
class PRTemplate:
    """PR template configuration."""
    name: str
    description: str
    sections: List[str]
    body_template: str


@dataclass
class PRContent:
    """Generated PR content."""
    title: str
    body: str
    sections: Dict[str, str]
    checklist: List[str]
    labels: List[str]


class PRContentGenerator:
    """Generates pull request content from reviews and analysis."""

    DEFAULT_TEMPLATES = {
        "improvement": PRTemplate(
            name="improvement",
            description="Improvement to existing functionality",
            sections=["description", "changes", "testing", "checklist"],
            body_template="""
## Description
{description}

## Changes Made
{changes}

## Testing
{testing}

## Checklist
- [ ] Code follows project style guidelines
- [ ] Tests added or updated
- [ ] Documentation updated
- [ ] No breaking changes
            """,
        ),
        "feature": PRTemplate(
            name="feature",
            description="New feature implementation",
            sections=["overview", "motivation", "changes", "testing", "checklist"],
            body_template="""
## Overview
{overview}

## Motivation
{motivation}

## Changes Made
{changes}

## Testing
{testing}

## Checklist
- [ ] Feature implemented as specified
- [ ] Tests added for new functionality
- [ ] Documentation added or updated
- [ ] Code reviewed by at least one contributor
            """,
        ),
        "bugfix": PRTemplate(
            name="bugfix",
            description="Bug fix",
            sections=["bug", "root_cause", "fix", "testing", "checklist"],
            body_template="""
## Bug Description
{bug}

## Root Cause
{root_cause}

## Fix Applied
{fix}

## Testing
{testing}

## Checklist
- [ ] Bug reproduced and verified fixed
- [ ] Tests added to prevent regression
- [ ] Documentation updated if needed
            """,
        ),
        "docs": PRTemplate(
            name="docs",
            description="Documentation update",
            sections=["changes", "checklist"],
            body_template="""
## Documentation Changes
{changes}

## Checklist
- [ ] Documentation is accurate
- [ ] Examples verified
- [ ] No documentation build errors
            """,
        ),
        "review": PRTemplate(
            name="review",
            description="Repository review and status update",
            sections=["summary", "quality_scores", "issues", "recommendations", "checklist"],
            body_template="""
## Repository Review Summary

{summary}

### Quality Scores
| Category | Score |
|----------|-------|
| Overall | {overall_score} |
| Code Quality | {code_quality} |
| Documentation | {documentation} |
| Structure | {structure} |
| Testing | {testing} |

## Issues Found
{issues}

## Recommendations
{recommendations}

## Checklist
- [ ] Review completed
- [ ] Status report generated
- [ ] No critical issues pending
            """,
        ),
    }

    def __init__(self):
        self.templates = self.DEFAULT_TEMPLATES.copy()

    def register_template(self, template: PRTemplate) -> None:
        """Register a custom PR template."""
        self.templates[template.name] = template

    def generate_pr_content(
        self,
        template_name: str,
        data: Dict[str, Any],
    ) -> PRContent:
        """Generate PR content using a template."""
        if template_name not in self.templates:
            template_name = "improvement"

        template = self.templates[template_name]
        sections = {}

        for section in template.sections:
            if section in data:
                sections[section] = self._format_section(section, data[section])
            else:
                sections[section] = ""

        body = template.body_template.format(**sections)

        checklist = self._generate_checklist(template_name, data)
        labels = self._generate_labels(template_name, data)

        title = self._generate_title(template_name, data)

        return PRContent(
            title=title,
            body=body,
            sections=sections,
            checklist=checklist,
            labels=labels,
        )

    def generate_review_pr_content(
        self,
        repo_name: str,
        review_result: Dict[str, Any],
    ) -> PRContent:
        """Generate PR content for a repository review."""
        scores = review_result.get("quality_scores", {})

        data = {
            "summary": review_result.get("summary", "Review completed"),
            "overall_score": f"{scores.get('overall', 0):.0f}%",
            "code_quality": f"{scores.get('code_quality', 0):.0f}%",
            "documentation": f"{scores.get('documentation', 0):.0f}%",
            "structure": f"{scores.get('structure', 0):.0f}%",
            "testing": f"{scores.get('testing', 0):.0f}%",
            "issues": self._format_issues(review_result.get("issues_found", [])),
            "recommendations": self._format_recommendations(
                review_result.get("next_steps", [])
            ),
            "stuck_areas": self._format_list(
                review_result.get("stuck_areas", [])
            ),
        }

        return self.generate_pr_content("review", {"repo_name": repo_name, **data})

    def _format_section(self, section: str, content: Any) -> str:
        """Format a section of the PR body."""
        if isinstance(content, list):
            return self._format_list(content)
        elif isinstance(content, dict):
            return self._format_dict(content)
        return str(content)

    def _format_list(self, items: List[str]) -> str:
        """Format a list as markdown."""
        if not items:
            return "None"
        return "\n".join(f"- {item}" for item in items)

    def _format_dict(self, data: Dict[str, Any]) -> str:
        """Format a dictionary as markdown table."""
        if not data:
            return "None"

        rows = []
        for key, value in data.items():
            rows.append(f"| {key} | {value} |")

        header = "| Key | Value |\n|---|---|\n"
        return header + "\n".join(rows)

    def _format_issues(self, issues: List[Dict[str, Any]]) -> str:
        """Format issues as a markdown table."""
        if not issues:
            return "No critical issues found."

        rows = ["| Severity | File | Description |", "|---|---|---|"]
        for issue in issues[:20]:
            severity = issue.get("severity", "unknown")
            file = issue.get("file", "Unknown")
            desc = issue.get("description", "")[:60]
            rows.append(f"| {severity} | {file} | {desc} |")

        return "\n".join(rows)

    def _format_recommendations(self, recommendations: List[str]) -> str:
        """Format recommendations as a numbered list."""
        if not recommendations:
            return "No specific recommendations."
        return "\n".join(f"{i+1}. {r}" for i, r in enumerate(recommendations[:10]))

    def _generate_checklist(
        self, template_name: str, data: Dict[str, Any]
    ) -> List[str]:
        """Generate a checklist for the PR."""
        checklist = [
            "Code follows project style guidelines",
            "Tests pass locally",
            "Documentation updated if applicable",
        ]

        if template_name == "bugfix":
            checklist.append("Bug is reproducible and fixed")
            checklist.append("Regression tests added")

        elif template_name == "feature":
            checklist.append("Feature works as specified")
            checklist.append("Edge cases handled")

        elif template_name == "docs":
            checklist.append("Documentation is accurate")
            checklist.append("No build errors")

        return checklist

    def _generate_labels(self, template_name: str, data: Dict[str, Any]) -> List[str]:
        """Generate labels for the PR."""
        label_map = {
            "improvement": ["enhancement", "automated"],
            "feature": ["feature", "automated"],
            "bugfix": ["bug", "automated"],
            "docs": ["documentation", "automated"],
            "review": ["review", "automated"],
        }

        return label_map.get(template_name, ["automated"])

    def _generate_title(self, template_name: str, data: Dict[str, Any]) -> str:
        """Generate a PR title."""
        title_prefixes = {
            "improvement": "Improvement:",
            "feature": "Feature:",
            "bugfix": "Bugfix:",
            "docs": "Docs:",
            "review": "Review:",
        }

        prefix = title_prefixes.get(template_name, "Update:")

        if "repo_name" in data:
            return f"{prefix} {data['repo_name']} status update"
        elif "feature_name" in data:
            return f"{prefix} {data['feature_name']}"
        else:
            return f"{prefix} Automated update"

    def get_available_templates(self) -> List[PRTemplate]:
        """Get list of available PR templates."""
        return list(self.templates.values())
