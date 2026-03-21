#!/bin/bash
set -e

echo "=== NautilusTrader Node ==="
echo "Trader ID: ${NAUTILUS_TRADER_ID:-TRADER-001}"
echo "Environment: ${NAUTILUS_ENVIRONMENT:-sandbox}"
echo "API Server: ${NAUTILUS_API_HOST:-0.0.0.0}:${NAUTILUS_API_PORT:-8001}"

# If a custom script or command was passed, run it
if [ $# -gt 0 ]; then
    exec "$@"
fi

# Default: start with the JSON config from configs/ or build one from env vars
CONFIG_FILE="/opt/nautilus/configs/node.json"

if [ -f "$CONFIG_FILE" ]; then
    echo "Starting from config: $CONFIG_FILE"
    exec python3 -m nautilus_trader.live --raw "$(cat "$CONFIG_FILE")" --start true
else
    echo "No config file found at $CONFIG_FILE"
    echo "Starting demo node with API server (no exchange adapters)..."
    exec python3 /opt/nautilus/scripts/start_demo_node.py
fi
