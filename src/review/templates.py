"""Review prompt templates for code analysis."""

from typing import Any, Dict


class ReviewTemplates:
    """Collection of prompt templates for code review."""

    REPOSITORY_OVERVIEW = """
Review this repository: {repo_name}

Project Information:
- Name: {name}
- Description: {description}
- Language: {language}
- Stars: {stars}
- Forks: {forks}
- Open Issues: {issues}
- Created: {created}
- Last Updated: {updated}

Structure:
{structure}

Provide a concise overview (2-3 sentences) of what this repository is about and its current state.
"""

    CODE_QUALITY_ASSESSMENT = """
Assess the code quality of this repository:

{files_content}

Evaluate:
1. Code organization and architecture
2. Naming conventions
3. Error handling
4. Code duplication
5. Complexity

Rate each aspect 1-10 and provide specific examples of issues found.
"""

    STUCK_AREAS_DETECTION = """
Analyze this repository for areas where development appears to be stuck:

{files_content}

Look for:
1. TODO comments that haven't been addressed
2. FIXME comments
3. Incomplete features (missing implementations)
4. Deprecated code still in use
5. Outdated dependencies
6. Broken builds or commented-out code

List all stuck areas with file paths and line numbers if available.
"""

    NEXT_STEPS_RECOMMENDATION = """
Based on the analysis of this repository, recommend next steps:

Current State:
{summary}

Issues Found:
{issues}

Quality Scores:
- Overall: {overall}
- Code Quality: {code_quality}
- Documentation: {documentation}
- Structure: {structure}
- Testing: {testing}

Provide a prioritized list (most important first) of actions to improve this repository.
"""

    FULL_REVIEW_SUMMARY = """
Generate a comprehensive review summary for this repository:

Repository: {repo_name}

Overview:
{overview}

Quality Assessment:
{quality_assessment}

Stuck Areas:
{stuck_areas}

Next Steps:
{next_steps}

Format as a well-structured markdown document with clear sections.
"""

    DOCUMENTATION_REVIEW = """
Review the documentation in this repository:

README Content:
{readme}

Other Documentation:
{docs}

Identify:
1. Missing documentation
2. Outdated information
3. Incomplete sections
4. Unclear explanations
5. Missing examples

Provide specific recommendations for improvement.
"""

    STRUCTURE_ANALYSIS = """
Analyze the project structure:

Directory Tree:
{tree}

Configuration Files:
{configs}

Identify:
1. Project type and technology stack
2. Missing standard files
3. Inconsistent organization
4. Potential build/deployment issues
5. Recommendations for structure improvements
"""

    @classmethod
    def format(
        cls, template_name: str, **kwargs: Any
    ) -> str:
        """Format a template with provided values."""
        template = getattr(cls, template_name.upper(), None)
        if template is None:
            raise ValueError(f"Unknown template: {template_name}")
        return template.format(**kwargs)
