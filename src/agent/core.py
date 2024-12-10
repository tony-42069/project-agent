# src/agent/core.py

from typing import Dict, List, Optional
import os
from datetime import datetime

class Project:
    def __init__(self, name: str, description: str, repo_url: str):
        self.name = name
        self.description = description
        self.repo_url = repo_url
        self.created_at = datetime.now()
        self.tasks: List[Task] = []
        self.status = "initialized"

class Task:
    def __init__(self, title: str, description: str, priority: int = 1):
        self.title = title
        self.description = description
        self.priority = priority
        self.status = "pending"
        self.created_at = datetime.now()
        self.completed_at: Optional[datetime] = None

class ProjectAgent:
    def __init__(self, github_token: str, openai_api_key: str):
        self.github_token = github_token
        self.openai_api_key = openai_api_key
        self.projects: Dict[str, Project] = {}

    def create_project(self, name: str, description: str, repo_url: str) -> Project:
        """Create a new project"""
        if name in self.projects:
            raise ValueError(f"Project {name} already exists")
        
        project = Project(name, description, repo_url)
        self.projects[name] = project
        return project

    def add_task(self, project_name: str, task_title: str, task_description: str, priority: int = 1) -> Task:
        """Add a task to a project"""
        if project_name not in self.projects:
            raise ValueError(f"Project {project_name} does not exist")
        
        project = self.projects[project_name]
        task = Task(task_title, task_description, priority)
        project.tasks.append(task)
        return task

    def get_project_status(self, project_name: str) -> Dict:
        """Get the current status of a project"""
        if project_name not in self.projects:
            raise ValueError(f"Project {project_name} does not exist")
        
        project = self.projects[project_name]
        total_tasks = len(project.tasks)
        completed_tasks = len([t for t in project.tasks if t.status == "completed"])
        
        return {
            "name": project.name,
            "description": project.description,
            "status": project.status,
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "completion_percentage": (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
        }

    def list_projects(self) -> List[Dict]:
        """List all projects and their basic info"""
        return [
            {
                "name": project.name,
                "description": project.description,
                "status": project.status,
                "tasks_count": len(project.tasks)
            }
            for project in self.projects.values()
        ]

if __name__ == "__main__":
    # Example usage
    agent = ProjectAgent(
        github_token=os.getenv("GITHUB_TOKEN"),
        openai_api_key=os.getenv("OPENAI_API_KEY")
    )

    # Create a new project
    project = agent.create_project(
        name="awesome-api",
        description="An awesome API project",
        repo_url="https://github.com/username/awesome-api"
    )

    # Add some tasks
    agent.add_task(
        project_name="awesome-api",
        task_title="Setup project structure",
        task_description="Initialize the project with basic folder structure and dependencies",
        priority=1
    )

    # Get project status
    status = agent.get_project_status("awesome-api")
    print(f"Project Status: {status}")