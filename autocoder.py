from typing import List, Dict
import requests
from github import Github
import os
import json
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

class AutoCoder:
    def __init__(self):
        # Load tokens from environment variables
        self.hf_token = os.getenv("HF_TOKEN")
        self.github_token = os.getenv("GITHUB_TOKEN")
        self.slack_token = os.getenv("SLACK_BOT_TOKEN")
        self.slack_channel = os.getenv("SLACK_CHANNEL_ID")
        
        self.github = Github(self.github_token)
        self.headers = {"Authorization": f"Bearer {self.hf_token}"}
        self.API_URL = "https://api-inference.huggingface.co/models/codellama/CodeLlama-34b-Instruct-hf"
        self.current_project = None
        self.context = []
        
        # Initialize Slack client if token is available
        self.slack_client = WebClient(token=self.slack_token) if self.slack_token else None

    def send_slack_message(self, message: str) -> bool:
        """Send a message to Slack channel"""
        if not self.slack_client or not self.slack_channel:
            return False
            
        try:
            self.slack_client.chat_postMessage(
                channel=self.slack_channel,
                text=message
            )
            return True
        except SlackApiError as e:
            print(f"Error sending message to Slack: {e.response['error']}")
            return False

    def notify_progress(self, message: str):
        """Send progress notification to both console and Slack"""
        print(message)
        self.send_slack_message(message)

    def understand_project(self, project_idea: str) -> Dict:
        """Takes a project idea and breaks it down into actionable components"""
        
        prompt = f"""Break down this project into concrete components:
        Project: {project_idea}
        
        Provide:
        1. Core features
        2. Technical requirements
        3. System architecture
        4. Implementation steps
        5. Potential challenges
        
        Format as JSON."""
        
        response = self.generate_code(prompt)
        try:
            project_plan = json.loads(response)
            self.context.append({"type": "project_plan", "content": project_plan})
            return project_plan
        except:
            # If JSON parsing fails, return simplified structure
            return {
                "components": [
                    {"name": "main", "specs": project_idea}
                ]
            }

    def generate_code(self, prompt: str) -> str:
        """Generate code using CodeLlama"""
        payload = {
            "inputs": f"Write production-ready code for: {prompt}\nCode:",
            "parameters": {
                "max_length": 2000,
                "temperature": 0.7,
                "top_p": 0.95
            }
        }
        
        response = requests.post(self.API_URL, headers=self.headers, json=payload)
        return response.json()[0]["generated_text"]

    def create_repository(self, name: str, description: str) -> Dict:
        """Creates a new GitHub repository"""
        try:
            repo = self.github.get_user().create_repo(
                name=name,
                description=description,
                private=True,
                auto_init=True
            )
            return {"success": True, "repo": repo}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def commit_code(self, repo_name: str, file_path: str, content: str, commit_message: str):
        """Commits code to repository"""
        try:
            repo = self.github.get_user().get_repo(repo_name)
            
            # Create or update file
            try:
                contents = repo.get_contents(file_path)
                repo.update_file(
                    file_path,
                    commit_message,
                    content,
                    contents.sha
                )
            except:
                repo.create_file(
                    file_path,
                    commit_message,
                    content
                )
                
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def improve_code(self, code: str) -> str:
        """Suggests improvements to the code"""
        prompt = f"""Review and improve this code while maintaining functionality:
        {code}
        
        Improved version:"""
        
        return self.generate_code(prompt)

    def autonomous_development(self, project_idea: str):
        """Main function to autonomously develop a project"""
        
        self.notify_progress("🤖 Starting autonomous development...")
        
        # 1. Understand the project
        plan = self.understand_project(project_idea)
        self.notify_progress("📋 Project plan created")
        
        # 2. Create repository name from project idea
        repo_name = "-".join(project_idea.split()[:3]).lower()
        
        # 3. Create repository
        repo_result = self.create_repository(repo_name, project_idea)
        if not repo_result["success"]:
            error_msg = f"Failed to create repository: {repo_result.get('error')}"
            self.notify_progress(error_msg)
            return
        
        repo = repo_result["repo"]
        self.notify_progress(f"📁 Repository created: {repo_name}")
        
        # 4. Generate and commit code for each component
        for component in plan.get("components", [{"name": "main", "specs": project_idea}]):
            # Generate initial code
            code = self.generate_code(component.get("specs", project_idea))
            
            # Try to improve the code
            try:
                improved_code = self.improve_code(code)
            except:
                improved_code = code
            
            # Commit to repository
            file_path = f"src/{component['name']}.py"
            result = self.commit_code(
                repo_name,
                file_path,
                improved_code,
                f"Add {component['name']} implementation"
            )
            
            if result["success"]:
                self.notify_progress(f"✨ Component completed: {component['name']}")
            else:
                self.notify_progress(f"❌ Failed to commit {component['name']}: {result.get('error')}")
        
        # 5. Add README
        self.commit_code(
            repo_name,
            "README.md",
            f"# {repo_name}\n\n{project_idea}\n\n## Generated Code\nThis project was automatically generated by AutoCoder.",
            "Add README"
        )
        self.notify_progress("📝 README added")

        completion_msg = f"🚀 Project development completed!\nCheck your new project at: {repo.html_url}"
        self.notify_progress(completion_msg)
        return {"success": True, "repo_url": repo.html_url}

    def monitor_progress(self):
        """Monitors development progress and provides updates"""
        if not self.current_project:
            return "No active project"
            
        # Add progress monitoring logic here
        pass

if __name__ == "__main__":
    agent = AutoCoder()
    
    # Example project idea - CHANGE THIS TO YOUR IDEA
    project_idea = "Build a Discord bot that can track crypto prices and alert users on significant changes"
    result = agent.autonomous_development(project_idea)