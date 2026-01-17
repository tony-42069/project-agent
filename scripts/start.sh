#!/bin/bash
set -e

PROJECT_DIR="/opt/project-agent"
VENV_DIR="${PROJECT_DIR}/venv"
DATA_DIR="${PROJECT_DIR}/data"
LOG_DIR="${PROJECT_DIR}/logs"
REPORT_DIR="${PROJECT_DIR}/reports"

echo "========================================="
echo "Project Agent Startup Script"
echo "========================================="

# Create directories
echo "[1/5] Creating directories..."
mkdir -p ${DATA_DIR}
mkdir -p ${LOG_DIR}
mkdir -p ${REPORT_DIR}
mkdir -p ${LOG_DIR}/archive

# Activate virtual environment
echo "[2/5] Activating virtual environment..."
source ${VENV_DIR}/bin/activate

# Set permissions
echo "[3/5] Setting permissions..."
chown -R project-agent:project-agent ${DATA_DIR} 2>/dev/null || true
chown -R project-agent:project-agent ${LOG_DIR} 2>/dev/null || true
chown -R project-agent:project-agent ${REPORT_DIR} 2>/dev/null || true

# Rotate logs
echo "[4/5] Rotating logs..."
if [ -f "${LOG_DIR}/agent.log" ]; then
    gzip -c "${LOG_DIR}/agent.log" > "${LOG_DIR}/archive/agent.log.$(date +%Y%m%d%H%M%S).gz" 2>/dev/null || true
    truncate -s 0 "${LOG_DIR}/agent.log" 2>/dev/null || true
fi

# Start the application
echo "[5/5] Starting Project Agent..."
cd ${PROJECT_DIR}

exec python -m src api \
    --host 0.0.0.0 \
    --port 8000 \
    2>&1 | tee -a ${LOG_DIR}/agent.log
