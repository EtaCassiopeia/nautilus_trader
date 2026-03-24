#!/bin/bash
# ---------------------------------------------------------------------------
#  One-shot local setup for NautilusTrader AI Agent Control Plane
#
#  Usage:
#    ./deploy/scripts/setup-local.sh              # Start everything
#    ./deploy/scripts/setup-local.sh --infra-only # Just Redis + Postgres
#    ./deploy/scripts/setup-local.sh --down       # Stop everything
# ---------------------------------------------------------------------------
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEPLOY_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_DIR="$(dirname "$DEPLOY_DIR")"

cd "$DEPLOY_DIR"

# Parse args
INFRA_ONLY=false
DOWN=false
for arg in "$@"; do
    case $arg in
        --infra-only) INFRA_ONLY=true ;;
        --down)       DOWN=true ;;
    esac
done

if $DOWN; then
    echo "Stopping all services..."
    docker compose down
    exit 0
fi

# Ensure .env exists
if [ ! -f .env ]; then
    echo "No .env file found. Creating from defaults..."
    # .env is already committed with safe defaults
fi

# Create config directory for MCP
mkdir -p "$HOME/.nautilus"

if [ ! -f "$HOME/.nautilus/mcp.toml" ]; then
    echo "Installing MCP config to ~/.nautilus/mcp.toml"
    cp configs/mcp.toml "$HOME/.nautilus/mcp.toml"
fi

if [ ! -f "$HOME/.nautilus/cli.toml" ]; then
    echo "Installing CLI config to ~/.nautilus/cli.toml"
    cp configs/cli.toml "$HOME/.nautilus/cli.toml"
fi

echo ""
echo "=== NautilusTrader Local Setup ==="
echo ""

if $INFRA_ONLY; then
    echo "Starting infrastructure only (Redis + Postgres)..."
    docker compose up -d redis postgres
    echo ""
    echo "Infrastructure ready:"
    echo "  Redis:    localhost:6379"
    echo "  Postgres: localhost:5432 (user: nautilus, pass: pass)"
    echo ""
    echo "Now run the node locally:"
    echo "  python deploy/scripts/start_demo_node.py"
else
    echo "Building and starting all services..."
    docker compose up -d --build
    echo ""
    echo "Waiting for health checks..."
    sleep 5

    # Check health
    if curl -sf http://localhost:8001/health > /dev/null 2>&1; then
        echo "API server is healthy!"
    else
        echo "API server not responding yet — check: docker compose logs nautilus"
    fi

    echo ""
    echo "=== Services Running ==="
    echo "  API Server:  http://localhost:8001"
    echo "  API Docs:    http://localhost:8001/docs"
    echo "  Health:      http://localhost:8001/health"
    echo "  MCP (SSE):   http://localhost:8002/sse"
    echo "  Redis:       localhost:6379"
    echo "  Postgres:    localhost:5432"
fi

echo ""
echo "=== Quick Commands ==="
echo "  # Check status"
echo "  curl http://localhost:8001/health | python3 -m json.tool"
echo ""
echo "  # View logs"
echo "  docker compose -f deploy/docker-compose.yml logs -f nautilus"
echo ""
echo "  # Stop everything"
echo "  ./deploy/scripts/setup-local.sh --down"
echo ""
echo "  # Connect Claude Code (copy MCP config)"
echo "  cp deploy/mcp.json .mcp.json"
echo ""
echo "  # Start AI Agent (requires ANTHROPIC_API_KEY)"
echo "  python deploy/scripts/start_agent.py --mode MONITOR"
echo ""
