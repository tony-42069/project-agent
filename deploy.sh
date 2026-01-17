#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${SCRIPT_DIR}"
DEPLOY_DIR="/opt/project-agent"
VERSION=$(python -c "from src import __version__; print(__version__)")

echo "=========================================="
echo "Project Agent Deployment Script v${VERSION}"
echo "=========================================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Warning: Not running as root. Some operations may require sudo."
fi

# Function to check command availability
check_command() {
    if ! command -v "$1" &> /dev/null; then
        echo "Error: $1 is required but not installed."
        exit 1
    fi
}

check_command docker
check_command docker-compose

echo "[1/7] Stopping existing containers..."
cd "${PROJECT_DIR}"
docker-compose down --remove-orphans 2>/dev/null || true

echo "[2/7] Building Docker image..."
docker build -t project-agent:${VERSION} .
docker tag project-agent:${VERSION} project-agent:latest

echo "[3/7] Creating deployment directory..."
sudo mkdir -p ${DEPLOY_DIR}/{data,logs,reports,venv}
sudo chown -R $(id -u):$(id -g) ${DEPLOY_DIR} 2>/dev/null || true

echo "[4/7] Setting up environment..."
if [ ! -f "${PROJECT_DIR}/.env" ]; then
    echo "Warning: .env file not found. Creating from example..."
    cp "${PROJECT_DIR}/.env.example" "${PROJECT_DIR}/.env"
fi

echo "[5/7] Starting services..."
docker-compose up -d

echo "[6/7] Waiting for services to be healthy..."
sleep 5
for i in {1..30}; do
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        echo "  ✓ API is healthy"
        break
    fi
    echo "  Waiting for API... ($i/30)"
    sleep 1
done

echo "[7/7] Verifying deployment..."
if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    echo ""
    echo "=========================================="
    echo "✓ Deployment successful!"
    echo "=========================================="
    echo ""
    echo "Services:"
    echo "  - API:     http://localhost:8000"
    echo "  - Metrics: http://localhost:8000/metrics"
    echo "  - Grafana: http://localhost:3000 (admin/admin)"
    echo "  - Prometheus: http://localhost:9090"
    echo ""
    echo "Next steps:"
    echo "  1. Edit .env with your API keys"
    echo "  2. Restart: docker-compose restart project-agent"
    echo "  3. View logs: docker-compose logs -f project-agent"
else
    echo ""
    echo "Error: Deployment may have failed. Check logs with:"
    echo "  docker-compose logs project-agent"
    exit 1
fi
