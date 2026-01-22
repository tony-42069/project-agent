# Project Agent 🤖

[![GitHub Release](https://img.shields.io/github/v/release/tony-42069/project-agent)](https://github.com/tony-42069/project-agent/releases)
[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](https://opensource.org/licenses/MIT)
[![GitHub Stars](https://img.shields.io/github/stars/tony-42069/project-agent)](https://github.com/tony-42069/project-agent/stargazers)
[![GitHub Forks](https://img.shields.io/github/forks/tony-42069/project-agent)](https://github.com/tony-42069/project-agent/network/members)

An AI-powered autonomous agent for managing, reviewing, and improving your entire GitHub repository portfolio. Automatically analyzes code quality, generates documentation, creates pull requests, and executes delegated tasks across all your public and private repositories.

## ✨ What It Does

- 🔍 **Scans all your repositories** (public + private) via GitHub API
- 📊 **Analyzes code quality** using GLM-4 for intelligent review
- 📝 **Generates status reports** (`REPO_STATUS.md`) for each repository
- 🐛 **Identifies bugs and stuck areas** with TODO/FIXME detection
- 🎯 **Recommends next steps** for each project
- 📋 **Creates PRs** for improvements and documentation updates
- 🤖 **Accepts commands** via Telegram bot
- ⚡ **Executes delegated tasks** like adding tests, fixing bugs, updating docs

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- GitHub Personal Access Token
- GLM-4 API Key (recommended) or OpenAI API Key
- Telegram Bot Token (optional, for commands)

### Installation

```bash
# Clone the repository
git clone https://github.com/tony-42069/project-agent.git
cd project-agent

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
.\venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys:
# - GITHUB_TOKEN=ghp_xxxxx
# - GLM_API_KEY=sk-xxxxx (or OPENAI_API_KEY)
# - TELEGRAM_BOT_TOKEN=12345:xxxxx
```

### Running the Agent

```bash
# Review all repositories
python -m src review

# Start the API server
python -m src api

# Start Telegram bot
python -m src bot
```

### Docker Deployment

```bash
# Deploy with Docker Compose
./deploy.sh
```

## 📖 Features

### Repository Discovery & Analysis
- Automatic scanning of all GitHub repositories
- Intelligent file prioritization for analysis
- Structure detection (Python, Node.js, Go, Rust, Java, C++)
- Documentation quality assessment

### AI-Powered Code Review
- GLM-4 powered comprehensive code analysis
- Quality scoring (code quality, documentation, structure, testing)
- Bug and issue detection
- TODO/FIXME identification
- Stuck area detection

### Automated Reporting
- `REPO_STATUS.md` generation for each repository
- Quality score visualization with progress bars
- Next steps recommendations
- Summary dashboard for all repositories

### Pull Request System
- Automatic branch creation
- PR description generation from reviews
- Review workflow management
- Merge scheduling

### Task Delegation
- Natural language command parsing
- Priority-based task queue
- Task execution engine
- Real-time status tracking

### Telegram Bot Commands
```
/help          - Show available commands
/status        - System status overview
/review <repo> - Review specific repository
/review all    - Review all repositories
/list          - List all tracked repositories
/pr <repo>     - Create PR for improvements
/execute "<task>" - Delegate a coding task
```

## 🏗️ Project Structure

```
project-agent/
├── src/
│   ├── api/           # FastAPI endpoints
│   ├── commands/      # Telegram bot & command parser
│   ├── core/          # Config, database, logging, security, monitoring
│   ├── github/        # GitHub API client
│   ├── openai/        # OpenAI integration
│   ├── report/        # Report generation & PR creation
│   ├── review/        # Code analysis & review orchestrator
│   └── tasks/         # Task delegation system
├── deploy/            # Systemd service file
├── scripts/           # Startup scripts
├── grafana/           # Grafana dashboards
├── prometheus.yml     # Prometheus config
├── docker-compose.yml # Docker orchestration
├── Dockerfile         # Container definition
├── config.yaml        # Application configuration
└── pyproject.toml     # Project metadata
```

## 🔧 Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GITHUB_TOKEN` | ✅ | GitHub Personal Access Token |
| `GLM_API_KEY` | ✅ | GLM-4 API Key |
| `OPENAI_API_KEY` | ❌ | OpenAI API Key (alternative to GLM) |
| `TELEGRAM_BOT_TOKEN` | ❌ | Telegram Bot Token |
| `TELEGRAM_WEBHOOK_URL` | ❌ | Telegram Webhook URL |

### Config Options (`config.yaml`)

```yaml
app:
  host: "0.0.0.0"
  port: 8000
  log_level: "INFO"

github:
  rate_limit_wait: 1.0
  max_retries: 3

openai:
  model: "glm-4"
  temperature: 0.3

review:
  max_files_per_repo: 100
  exclude_patterns: [*.pyc, node_modules/, .git/]
```

## 📊 Monitoring

The agent includes built-in monitoring with:

- **Prometheus Metrics**: `/metrics` endpoint
- **Health Checks**: `/health` endpoint
- **Grafana Dashboards**: Pre-configured visualizations
- **Uptime Tracking**: Availability monitoring

Access:
- API: http://localhost:8000
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (admin/admin)

## 🐳 Docker Deployment

```bash
# Build and start all services
docker-compose up -d

# View logs
docker-compose logs -f project-agent

# Stop services
docker-compose down
```

### Systemd Installation (VPS)

```bash
# Copy service file
sudo cp deploy/project-agent.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable and start
sudo systemctl enable project-agent
sudo systemctl start project-agent

# Check status
sudo systemctl status project-agent
```

## 📝 Usage Examples

### Review All Repositories

```bash
python -m src review all
```

### Review Specific Repository

```bash
python -m src review owner/repo-name
```

### Telegram Bot

```
/list                         # List all repositories
/review my-api-project        # Review specific repo
/status                       # Check system status
/execute "add tests to auth module"  # Delegate task
```

### API Endpoints

```bash
# List repositories
curl http://localhost:8000/api/v1/repositories

# Review repository
curl -X POST http://localhost:8000/api/v1/review \
  -H "Content-Type: application/json" \
  -d '{"repository_name": "owner/repo"}'

# Health check
curl http://localhost:8000/health

# Get metrics
curl http://localhost:8000/metrics
```

## 🔒 Security

- Rate limiting to prevent abuse
- API key authentication
- Audit logging for all actions
- Secure password hashing (PBKDF2)
- HMAC signature verification
- Docker security hardening

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [智谱AI](https://www.zhipuai.com/) for GLM-4
- [GitHub](https://github.com/) for the API
- [Python Telegram Bot](https://github.com/python-telegram-bot/python-telegram-bot) community
