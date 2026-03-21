# NautilusTrader — Local Deployment

Run NautilusTrader with the AI Agent Control Plane locally using Docker Compose.

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Docker Compose Stack                                     │
│                                                           │
│  ┌─────────┐  ┌──────────────────┐  ┌──────────────────┐ │
│  │  Redis   │  │  NautilusTrader  │  │   MCP Server     │ │
│  │  :6379   │◄─│  + API Server    │◄─│   (SSE :8002)    │ │
│  └─────────┘  │  :8001           │  └──────────────────┘ │
│  ┌─────────┐  └──────────────────┘           ▲           │
│  │Postgres │         ▲    ▲                   │           │
│  │  :5432  │         │    │                   │           │
│  └─────────┘         │    │                   │           │
└──────────────────────┼────┼───────────────────┼───────────┘
                       │    │                   │
              ┌────────┘    │                   │
              │             │                   │
     ┌────────▼──┐   ┌──────▼──┐   ┌────────────▼──┐
     │    CLI    │   │  Agent  │   │  Claude Code  │
     │ nautilus  │   │  Loop   │   │  (MCP client) │
     │  node ... │   │         │   │               │
     └───────────┘   └─────────┘   └───────────────┘
```

## Quick Start

### 1. Start infrastructure only (Redis + Postgres)

```bash
cd deploy
docker compose up -d redis postgres
```

### 2. Build and start everything

```bash
cd deploy
cp .env.example .env   # edit with your API keys
docker compose up -d --build
```

### 3. Verify the node is running

```bash
curl http://localhost:8001/health
```

### 4. Use the CLI

```bash
# From the project root (requires nautilus_trader installed)
python -m nautilus_trader.cli.main node status
python -m nautilus_trader.cli.main strategy list
python -m nautilus_trader.cli.main portfolio summary
```

### 5. Connect Claude Code via MCP

Copy the MCP config to your project root:

```bash
cp deploy/mcp.json .mcp.json
```

Now Claude Code can use NautilusTrader tools like `nautilus_node_status`,
`nautilus_list_orders`, `nautilus_get_portfolio_summary`, etc.

For Docker (SSE transport), use the `nautilus-trader-sse` server config instead.

### 6. Start the AI Agent

```bash
# Monitor mode (read-only, no trading actions)
python deploy/scripts/start_agent.py --mode MONITOR

# Advisory mode (suggests actions, requires human approval)
python deploy/scripts/start_agent.py --mode ADVISORY

# Semi-autonomous (auto-executes low-risk, escalates high-risk)
python deploy/scripts/start_agent.py --mode SEMI_AUTONOMOUS \
    --max-order-size 0.1 \
    --max-daily-loss -1000

# Set your Anthropic API key first
export ANTHROPIC_API_KEY=sk-ant-...
```

## Configuration

### Exchange Adapters

Copy and edit the example config:

```bash
cp deploy/configs/node.json.example deploy/configs/node.json
```

Set exchange API keys in `.env`:

```bash
BINANCE_API_KEY=your-key
BINANCE_API_SECRET=your-secret
BINANCE_TESTNET=true
```

### MCP Safety Levels

| Level          | Behavior                                    |
|----------------|---------------------------------------------|
| `UNRESTRICTED` | No confirmation for any action              |
| `STANDARD`     | Confirmation for critical ops (default)     |
| `STRICT`       | Confirmation for all mutations              |

Set via `MCP_SAFETY_LEVEL` in `.env`.

### API Authentication

Set `NAUTILUS_API_KEY` in `.env` to require `X-Api-Key` header on all API requests.

## Services

| Service    | Port  | Description                              |
|------------|-------|------------------------------------------|
| Redis      | 6379  | Message bus backing store                |
| Postgres   | 5432  | Cache & persistence                      |
| Nautilus   | 8001  | Trading node + REST API + WebSocket      |
| MCP Server | 8002  | MCP server (SSE transport)               |

## Stopping

```bash
cd deploy
docker compose down          # Stop containers
docker compose down -v       # Stop and remove volumes (purge data)
```

## Next Steps: Cloud Deployment

This setup is designed to be portable to AWS/GCP/Azure:

- **ECS/Fargate**: Use the `deploy/nautilus.dockerfile` as-is
- **EKS/Kubernetes**: Generate manifests from the docker-compose with `kompose`
- **Terraform**: Add `deploy/terraform/` for infrastructure-as-code
- **Secrets**: Swap `.env` for AWS Secrets Manager / Parameter Store
- **Networking**: Replace bridge network with VPC subnets
- **Monitoring**: Add CloudWatch/Prometheus sidecar
