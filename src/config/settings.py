# src/config/settings.py

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# API Keys
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Project Settings
DEFAULT_BRANCH = "main"
DEFAULT_COMMIT_MESSAGE = "Project initialized by AI Agent"

# GitHub Settings
GITHUB_API_URL = "https://api.github.com"
GITHUB_HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

# Agent Settings
MAX_RETRIES = 3
TIMEOUT = 30  # seconds