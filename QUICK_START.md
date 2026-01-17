# Quick Start - Get Project Agent Running in 5 Minutes

## 1. Get Your API Keys

**GitHub:**
- Go to https://github.com/settings/tokens
- Generate new token (classic)
- Select: `repo`, `read:user`, `user:email`
- Copy the token

**OpenAI:**
- Go to https://platform.openai.com/api-keys
- Create new secret key
- Copy the key

**Telegram (optional):**
- Message @BotFather on Telegram
- `/newbot`
- Copy the bot token

## 2. Install and Configure

```bash
# Clone and enter
git clone https://github.com/tony-42069/project-agent.git
cd project-agent

# Create virtual environment
python -m venv venv
.\venv\Scripts\activate  # Windows
# OR
source venv/bin/activate  # Linux/Mac

# Install
pip install -r requirements.txt

# Configure
cp .env.example .env
```

## 3. Edit .env File

Open `.env` and add your keys:

```
GITHUB_TOKEN=ghp_your_github_token_here
OPENAI_API_KEY=sk-your_openai_key_here
TELEGRAM_BOT_TOKEN=your_telegram_token  # optional
```

## 4. Run It

**Option A: Review all your repos now**
```bash
python -m src review
```

**Option B: Start the API server**
```bash
python -m src api
```
Then visit http://localhost:8000

**Option C: Start Telegram bot**
```bash
python -m src bot
```

## That's It! 🎉

The agent will:
- Scan all your GitHub repos
- Analyze each one with AI
- Create `REPO_STATUS.md` in each repository
- Give you a summary when complete

---

**Need Docker instead?** Just run:
```bash
./deploy.sh
```
