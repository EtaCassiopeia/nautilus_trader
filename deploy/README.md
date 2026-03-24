# NautilusTrader AI Agent Control Plane — Deployment Guide

## Architecture Overview

```
┌───────────────────────────────────────────────────────────────────┐
│  Docker Compose Stack                                             │
│                                                                   │
│  ┌───────────┐  ┌────────────────────────┐  ┌──────────────────┐ │
│  │  Redis    │  │   NautilusTrader       │  │   MCP Server     │ │
│  │  :6379    │◄─│   Trading Node         │◄─│   (SSE :8002)    │ │
│  └───────────┘  │   + REST API  :8001    │  └──────────────────┘ │
│  ┌───────────┐  │   + WebSocket /ws      │           ▲           │
│  │ Postgres  │  └────────────────────────┘           │           │
│  │  :5432    │          ▲      ▲                     │           │
│  └───────────┘          │      │                     │           │
└─────────────────────────┼──────┼─────────────────────┼───────────┘
                          │      │                     │
                 ┌────────┘      │                     │
                 │               │                     │
        ┌────────▼────┐  ┌───────▼─────┐  ┌───────────▼───┐
        │    CLI      │  │  AI Agent   │  │  Claude Code  │
        │  nautilus   │  │  Orchestr.  │  │  (via MCP)    │
        │  node ...   │  │             │  │               │
        └─────────────┘  └─────────────┘  └───────────────┘
```

The stack has four layers:

| Layer | Component | Role |
|-------|-----------|------|
| **Infrastructure** | Redis, Postgres | Message bus, cache persistence |
| **Core** | NautilusTrader node | Trading engine with exchange adapters |
| **Control Plane** | REST API, WebSocket, MCP Server | External access to the trading system |
| **Clients** | CLI, AI Agent, Claude Code | Consume the control plane |

---

## Deployment Modes

### Mode 1: Full Docker Stack

Everything runs in Docker. Best for CI, staging, or when you don't have the Cython build toolchain installed locally.

```bash
cd deploy
cp .env.example .env       # Edit with your values
docker compose up -d --build
```

Services started:

| Container | Image | Ports | Health Check |
|-----------|-------|-------|--------------|
| `nautilus-redis` | `redis:7-alpine` | 6379 | `redis-cli ping` |
| `nautilus-postgres` | `postgres:16-alpine` | 5432 | `pg_isready` |
| `nautilus-node` | Built from `nautilus.dockerfile` | **8001** | `GET /health` |
| `nautilus-mcp` | Same image, different entrypoint | **8002** | — |

**Build time**: The first build compiles Cython extensions and Rust libraries (~15-30 minutes depending on hardware). Subsequent builds use Docker layer caching.

```bash
# Watch the build
docker compose up --build 2>&1 | tail -f

# Check health after startup
curl http://localhost:8001/health | python3 -m json.tool

# View logs
docker compose logs -f nautilus
docker compose logs -f mcp-server
```

### Mode 2: Infrastructure in Docker, Node on Host

Run Redis and Postgres in Docker while running the trading node directly on your machine. Best for active development where you have NautilusTrader compiled locally.

```bash
# Start infrastructure
docker compose -f deploy/docker-compose.dev.yml up -d

# Start the trading node on your host
python deploy/scripts/start_demo_node.py
```

The `docker-compose.dev.yml` only starts Redis and Postgres — no NautilusTrader build required.

### Mode 3: One-Shot Bootstrap

The `setup-local.sh` script handles everything in one command:

```bash
# Start everything + install CLI/MCP configs to ~/.nautilus/
./deploy/scripts/setup-local.sh

# Infrastructure only
./deploy/scripts/setup-local.sh --infra-only

# Stop everything
./deploy/scripts/setup-local.sh --down
```

What the script does:
1. Creates `~/.nautilus/mcp.toml` and `~/.nautilus/cli.toml` if missing
2. Starts Docker Compose services
3. Waits for health checks
4. Prints connection info

---

## Configuration Reference

### Environment Variables (`.env.example`)

Copy to `.env` and edit:

```bash
cp deploy/.env.example deploy/.env
```

| Variable | Default | Description |
|----------|---------|-------------|
| `NAUTILUS_TRADER_ID` | `TRADER-001` | Unique trader identifier |
| `NAUTILUS_ENVIRONMENT` | `sandbox` | Trading environment label |
| `NAUTILUS_API_KEY` | *(empty)* | API key for REST/MCP auth. Empty = no auth |
| `API_PORT` | `8001` | Host port for REST API |
| `MCP_SAFETY_LEVEL` | `STANDARD` | MCP safety tier (see below) |
| `MCP_PORT` | `8002` | Host port for MCP SSE server |
| `REDIS_PORT` | `6379` | Host port for Redis |
| `POSTGRES_USER` | `nautilus` | Postgres username |
| `POSTGRES_PASSWORD` | `pass` | Postgres password |
| `POSTGRES_DB` | `nautilus` | Postgres database name |
| `POSTGRES_PORT` | `5432` | Host port for Postgres |
| `BINANCE_API_KEY` | — | Binance API key |
| `BINANCE_API_SECRET` | — | Binance API secret |
| `BINANCE_TESTNET` | — | Set `true` for Binance testnet |
| `ANTHROPIC_API_KEY` | — | Anthropic API key (for AI Agent) |

---

### Trading Node Configuration (`configs/node.json`)

The trading node is configured via a JSON file that maps to `TradingNodeConfig`. Copy the example and edit:

```bash
cp deploy/configs/node.json.example deploy/configs/node.json
```

#### Top-level fields

```jsonc
{
    // Unique identifier for this trader instance
    "trader_id": "TRADER-001",

    // Logging configuration
    "logging": {
        "log_level": "INFO",       // Console: DEBUG, INFO, WARNING, ERROR
        "log_level_file": "DEBUG"  // File log level
    },

    // Execution engine settings
    "exec_engine": {
        "reconciliation": false,              // Reconcile orders on connect
        "reconciliation_lookback_mins": 1440  // How far back to look (24h)
    },

    // Timeouts (seconds)
    "timeout_connection": 30.0,
    "timeout_reconciliation": 10.0,
    "timeout_portfolio": 10.0,
    "timeout_disconnection": 10.0,
    "timeout_post_stop": 5.0
}
```

#### Exchange adapters (`data_clients` / `exec_clients`)

Each adapter requires a factory path, config path, and adapter-specific config:

```jsonc
{
    "data_clients": {
        "BINANCE": {
            "factory_path": "nautilus_trader.adapters.binance:BinanceLiveDataClientFactory",
            "config_path": "nautilus_trader.adapters.binance:BinanceDataClientConfig",
            "config": {
                "api_key": null,            // Falls back to BINANCE_API_KEY env var
                "api_secret": null,         // Falls back to BINANCE_API_SECRET env var
                "account_type": "SPOT",     // SPOT, USDT_FUTURE, COIN_FUTURE
                "testnet": true,            // Use testnet endpoints
                "instrument_provider": {
                    "load_all": true         // Load all available instruments
                }
            }
        }
    },
    "exec_clients": {
        "BINANCE": {
            "factory_path": "nautilus_trader.adapters.binance:BinanceLiveExecClientFactory",
            "config_path": "nautilus_trader.adapters.binance:BinanceExecClientConfig",
            "config": {
                "api_key": null,
                "api_secret": null,
                "account_type": "SPOT",
                "testnet": true,
                "instrument_provider": {
                    "load_all": true
                },
                "max_retries": 3
            }
        }
    }
}
```

**Supported exchanges**: Binance (spot/futures), Bybit, Kraken, OKX, Deribit, dYdX, Hyperliquid, Interactive Brokers, Betfair, Polymarket, Architect AX.

When `api_key` or `api_secret` is `null`, NautilusTrader reads from environment variables named `{EXCHANGE}_API_KEY` and `{EXCHANGE}_API_SECRET`.

#### API Server (`api_server`)

```jsonc
{
    "api_server": {
        "enabled": true,              // Must be true to start API server
        "host": "0.0.0.0",           // Bind address ("127.0.0.1" for local only)
        "port": 8001,                 // Listen port
        "api_key": null,              // Require X-Api-Key header (null = no auth)
        "cors_origins": ["*"],        // Allowed CORS origins ([] = no CORS)
        "max_connections": 100,       // Max concurrent HTTP connections
        "request_timeout_secs": 30.0, // Per-request timeout

        // WebSocket event streaming (null = disabled)
        "event_stream": {
            "max_clients": 10,              // Max concurrent WS clients
            "client_queue_size": 10000,     // Events buffered per client
            "replay_buffer_size": 1000,     // Events kept for reconnect replay
            "ping_interval_secs": 30.0,     // WS keepalive interval
            "ping_timeout_secs": 10.0       // Pong wait timeout
        }
    }
}
```

**Demo mode**: If no `configs/node.json` exists, the container starts `start_demo_node.py` which creates a node with the API server enabled but no exchange adapters — useful for testing the control plane.

---

### MCP Server Configuration (`configs/mcp.toml`)

The MCP server bridges AI agents (Claude, etc.) to the trading node. Configuration priority: CLI flags > environment variables > config file > defaults.

Install to the default location:

```bash
cp deploy/configs/mcp.toml ~/.nautilus/mcp.toml
```

#### Config file format

```toml
[connection]
api_url = "http://localhost:8001"   # NautilusTrader REST API URL
# api_key = "your-api-key"         # Must match the node's api_key

[safety]
safety_level = "STANDARD"          # UNRESTRICTED | STANDARD | STRICT
read_only = false                  # true = block all mutations

[guardrails]
# max_order_quantity = "1.0"                     # Max quantity per order
# allowed_instruments = ["BTCUSDT-PERP.BINANCE"] # Instrument allowlist
# blocked_instruments = []                        # Instrument blocklist

[transport]
transport = "stdio"                # stdio (for Claude Code) | sse (for remote)
# sse_host = "0.0.0.0"
# sse_port = 8002
```

#### Environment variables

| Variable | Config Field | Example |
|----------|-------------|---------|
| `NAUTILUS_API_URL` | `api_url` | `http://localhost:8001` |
| `NAUTILUS_API_KEY` | `api_key` | `sk-abc123` |
| `NAUTILUS_SAFETY_LEVEL` | `safety_level` | `STANDARD` |
| `NAUTILUS_MCP_TRANSPORT` | `transport` | `stdio` |
| `NAUTILUS_MCP_SSE_HOST` | `sse_host` | `0.0.0.0` |
| `NAUTILUS_MCP_SSE_PORT` | `sse_port` | `8002` |
| `NAUTILUS_MCP_READ_ONLY` | `read_only` | `true` |
| `NAUTILUS_MAX_ORDER_QUANTITY` | `max_order_quantity` | `1.0` |

#### Safety levels

| Level | Read tools | Write tools | Critical tools |
|-------|-----------|-------------|----------------|
| **UNRESTRICTED** | No confirm | No confirm | No confirm |
| **STANDARD** | No confirm | No confirm | **Confirm required** |
| **STRICT** | No confirm | **Confirm required** | **Confirm required** |

**Environment auto-escalation**: When the trading node is in `LIVE` environment, `UNRESTRICTED` is automatically escalated to `STANDARD` to prevent accidental unguarded operations.

#### MCP tools available

**Read-only tools** (all safety levels):

| Tool | Description |
|------|-------------|
| `nautilus_node_status` | Node health, trader ID, running state |
| `nautilus_list_strategies` | List strategies with optional state filter |
| `nautilus_list_orders` | List orders (filter: status, strategy, instrument) |
| `nautilus_get_order` | Order detail by client_order_id |
| `nautilus_get_portfolio_summary` | Balances, P&L, exposures |
| `nautilus_get_balances` | Account balances (optional venue filter) |
| `nautilus_get_positions` | Open positions (optional instrument filter) |
| `nautilus_get_pnl` | Realized + unrealized P&L |
| `nautilus_get_exposure` | Net exposures by currency |
| `nautilus_list_instruments` | Cached instruments (optional venue filter) |
| `nautilus_get_instrument` | Instrument details by ID |
| `nautilus_get_latest_quote` | Latest bid/ask quote |
| `nautilus_get_latest_bars` | Recent OHLCV bars |
| `nautilus_get_risk_state` | Risk engine state |

**Mutation tools** (subject to safety level):

| Tool | Risk | Description |
|------|------|-------------|
| `nautilus_start_strategy` | WRITE | Start a strategy |
| `nautilus_stop_strategy` | WRITE | Stop a strategy |
| `nautilus_cancel_order` | WRITE | Cancel one order |
| `nautilus_modify_order` | WRITE | Modify order qty/price |
| `nautilus_submit_order` | CRITICAL | Submit a new order |
| `nautilus_cancel_all_orders` | CRITICAL | Cancel all open orders |
| `nautilus_remove_strategy` | CRITICAL | Remove a strategy |
| `nautilus_market_exit_strategy` | CRITICAL | Market-exit all positions |
| `nautilus_node_stop` | CRITICAL | Stop the trading node |
| `nautilus_set_risk_limits` | CRITICAL | Update risk limits |

#### Connecting Claude Code

**Option A — stdio transport** (recommended for local Claude Code):

```bash
# Copy to project root
cp deploy/mcp.json .mcp.json
```

Content of `.mcp.json`:
```json
{
    "mcpServers": {
        "nautilus-trader": {
            "command": "python3",
            "args": ["-m", "nautilus_trader.mcp.server"],
            "env": {
                "NAUTILUS_API_URL": "http://localhost:8001",
                "NAUTILUS_SAFETY_LEVEL": "STANDARD"
            }
        }
    }
}
```

Claude Code will auto-discover and start the MCP server process.

**Option B — SSE transport** (when MCP server runs in Docker):

```json
{
    "mcpServers": {
        "nautilus-trader": {
            "url": "http://localhost:8002/sse"
        }
    }
}
```

---

### CLI Configuration (`configs/cli.toml`)

Install to the default location:

```bash
cp deploy/configs/cli.toml ~/.nautilus/cli.toml
```

```toml
[connection]
host = "localhost"
port = 8001
# api_key = "your-api-key"

[output]
format = "table"   # table | json | csv
color = true
```

#### Environment variables

| Variable | Config Field |
|----------|-------------|
| `NAUTILUS_HOST` | `host` |
| `NAUTILUS_PORT` | `port` |
| `NAUTILUS_API_KEY` | `api_key` |

#### CLI flags (override everything)

```bash
python -m nautilus_trader.cli.main --host remote-server --port 9000 --api-key sk-abc --format json <command>
```

#### Command reference

```bash
# Node management
nautilus node status              # Show node health and state
nautilus node stop [-y]           # Stop the trading node (prompts for confirmation)

# Strategy management
nautilus strategy list [--state RUNNING]
nautilus strategy start <strategy_id>
nautilus strategy stop <strategy_id>             # Named 'stop-strategy' to avoid conflict
nautilus strategy remove <strategy_id> [-y]
nautilus strategy market-exit <strategy_id> [-y]

# Order management
nautilus order list [--status open|closed|all] [--strategy-id X] [--instrument-id X] [--limit 50]
nautilus order get <client_order_id>
nautilus order cancel <client_order_id>
nautilus order cancel-all [-y]

# Portfolio
nautilus portfolio summary
nautilus portfolio balances [--venue BINANCE]
nautilus portfolio positions [--instrument-id X]
nautilus portfolio pnl
nautilus portfolio exposure

# Market data
nautilus market instruments [--venue BINANCE]
nautilus market quote <instrument_id>
nautilus market bars <instrument_id> [--bar-type X] [--count 10]

# Risk
nautilus risk state
```

The `-y` / `--yes` flag skips confirmation prompts for destructive operations.

**Output formats**:
- `--format table` — human-readable aligned columns (default)
- `--format json` — raw JSON for piping to `jq`
- `--format csv` — CSV for spreadsheet import

---

### AI Agent Configuration

The AI agent is an autonomous loop that connects to NautilusTrader via the REST API, reasons about market events using Claude, and executes actions within safety guardrails.

#### Starting the agent

```bash
export ANTHROPIC_API_KEY=sk-ant-...

# Monitor mode — observe only, no mutations
python deploy/scripts/start_agent.py --mode MONITOR

# Advisory — suggests actions, needs human approval for everything
python deploy/scripts/start_agent.py --mode ADVISORY

# Semi-autonomous — auto-executes low-risk, escalates high-risk
python deploy/scripts/start_agent.py --mode SEMI_AUTONOMOUS

# Fully autonomous — executes within guardrail limits
python deploy/scripts/start_agent.py --mode AUTONOMOUS
```

#### Command-line options

| Flag | Default | Description |
|------|---------|-------------|
| `--mode` | `MONITOR` | Operating mode |
| `--api-url` | `http://localhost:8001` | NautilusTrader API URL |
| `--api-key` | *(from env)* | API authentication key |
| `--model` | `claude-sonnet-4-20250514` | Claude model for reasoning |
| `--interval` | `5.0` | Decision cycle interval (seconds) |
| `--max-order-size` | *(none)* | Max single order quantity |
| `--max-daily-loss` | *(none)* | Daily loss kill switch threshold |

#### Operating modes

| Mode | Queries | Low-Risk Mutations | High-Risk Mutations | Critical Mutations |
|------|---------|-------------------|--------------------|--------------------|
| **MONITOR** | Auto | Blocked | Blocked | Blocked |
| **ADVISORY** | Auto | Needs approval | Needs approval | Needs approval |
| **SEMI_AUTONOMOUS** | Auto | Auto | Needs approval | Needs approval |
| **AUTONOMOUS** | Auto | Auto | Auto | Auto |

**Low-risk**: start/stop strategy, cancel single order, small orders within limits.
**High-risk**: submit order, modify order, remove strategy.
**Critical**: cancel-all, market exit, node stop, change risk limits.

#### Guardrail configuration (programmatic)

Guardrails are hard limits that cannot be overridden by the agent's reasoning:

```python
from nautilus_trader.agent.config import AgentConfig, GuardrailConfig

config = AgentConfig(
    mode="SEMI_AUTONOMOUS",
    guardrails=GuardrailConfig(
        max_single_order_size="0.5",              # Max qty per order
        max_orders_per_minute=10,                  # Rate limit
        max_daily_loss="-5000",                    # Kill switch threshold
        max_portfolio_exposure="100000",           # Total exposure cap
        instrument_allowlist=[                     # Only trade these
            "BTCUSDT-PERP.BINANCE",
            "ETHUSDT-PERP.BINANCE",
        ],
        instrument_blocklist=[],                   # Never trade these
        max_position_size={                        # Per-instrument limits
            "BTCUSDT-PERP.BINANCE": "10.0",
        },
        require_stop_loss=False,                   # Require stops on all positions
        human_approval_threshold="10000",          # Notional value escalation
    ),
)
```

#### Kill switch

The kill switch triggers automatically when:
- Daily realized P&L drops below `max_daily_loss`
- Any configured `kill_switch_conditions` are met

When triggered:
1. All new order submissions are blocked
2. Agent switches to `MONITOR` mode
3. Reason is logged
4. **Manual reset required** to resume trading

---

## REST API Endpoints

Base URL: `http://localhost:8001`

### Health

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Node health (always public, no auth) |

### Node

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/node/status` | Node status and health |
| POST | `/api/v1/node/stop` | Stop the trading node |

### Strategies

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/strategies` | List all strategies |
| GET | `/api/v1/strategies/{id}` | Strategy detail |
| POST | `/api/v1/strategies` | Create strategy from config |
| POST | `/api/v1/strategies/{id}/start` | Start a strategy |
| POST | `/api/v1/strategies/{id}/stop` | Stop a strategy |
| POST | `/api/v1/strategies/{id}/market-exit` | Market-exit positions |
| DELETE | `/api/v1/strategies/{id}` | Remove a strategy |

### Orders

| Method | Path | Query Params | Description |
|--------|------|-------------|-------------|
| GET | `/api/v1/orders` | `status`, `strategy_id`, `instrument_id`, `limit` | List orders |
| GET | `/api/v1/orders/{client_order_id}` | — | Order detail |
| DELETE | `/api/v1/orders/{client_order_id}` | — | Cancel order |
| POST | `/api/v1/orders/cancel-all` | — | Cancel all orders |

### Portfolio

| Method | Path | Query Params | Description |
|--------|------|-------------|-------------|
| GET | `/api/v1/portfolio` | — | Full summary |
| GET | `/api/v1/portfolio/balances` | `venue` | Account balances |
| GET | `/api/v1/portfolio/positions` | `instrument_id` | Open positions |
| GET | `/api/v1/portfolio/pnl` | — | P&L breakdown |
| GET | `/api/v1/portfolio/exposure` | — | Net exposures |

### Cache

| Method | Path | Query Params | Description |
|--------|------|-------------|-------------|
| GET | `/api/v1/cache/instruments` | `venue` | List instruments |
| GET | `/api/v1/cache/instruments/{id}` | — | Instrument detail |
| GET | `/api/v1/cache/accounts` | — | List accounts |
| GET | `/api/v1/cache/accounts/{id}` | — | Account detail |

### Market Data

| Method | Path | Query Params | Description |
|--------|------|-------------|-------------|
| GET | `/api/v1/data/status` | — | Data engine status |
| GET | `/api/v1/data/bars/{instrument_id}` | `bar_type`, `count` | Recent bars |
| GET | `/api/v1/data/quotes/{instrument_id}` | — | Latest quote |
| GET | `/api/v1/data/trades/{instrument_id}` | `count` | Recent trades |

### Risk

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/risk/status` | Risk engine state |
| GET | `/api/v1/risk/config` | Risk configuration |

### Actors

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/actors` | List registered actors |
| GET | `/api/v1/actors/{actor_id}` | Actor detail |

### WebSocket

| Path | Description |
|------|-------------|
| `/ws/events` | Live event stream (requires `event_stream` config) |

**WebSocket protocol**:
1. Connect to `/ws/events`
2. Optionally send: `{"action": "subscribe", "topics": ["events.*"]}`
3. Receive JSON event frames
4. Reconnect replay: `{"action": "replay", "last_sequence": 42}`

All REST responses follow the envelope format:
```json
{"status": "ok", "data": { ... }, "ts": "2026-03-21T12:00:00Z"}
```

Error responses:
```json
{"status": "error", "error": {"code": "NOT_FOUND", "message": "..."}, "ts": "..."}
```

---

## File Layout

```
deploy/
├── README.md                          # This file
├── .env.example                       # Environment variable template
├── docker-compose.yml                 # Full stack (Redis + Postgres + Node + MCP)
├── docker-compose.dev.yml             # Infrastructure only (Redis + Postgres)
├── nautilus.dockerfile                 # Multi-stage build for NautilusTrader
├── mcp.json                           # Claude Code MCP server registration
├── configs/
│   ├── node.json.example              # Trading node config template
│   ├── mcp.toml                       # MCP server config template
│   └── cli.toml                       # CLI config template
└── scripts/
    ├── setup-local.sh                 # One-shot bootstrap
    ├── entrypoint.sh                  # Docker container entrypoint
    ├── start_demo_node.py             # Demo node (API server, no exchange)
    └── start_agent.py                 # AI Agent startup script
```

---

## Operational Commands

```bash
# ── Lifecycle ──────────────────────────────────────────────────
./deploy/scripts/setup-local.sh                 # Bootstrap everything
./deploy/scripts/setup-local.sh --infra-only    # Just Redis + Postgres
./deploy/scripts/setup-local.sh --down          # Stop everything

# ── Docker Compose ─────────────────────────────────────────────
cd deploy
docker compose up -d --build                    # Build and start all
docker compose up -d redis postgres             # Start infra only
docker compose logs -f nautilus                 # Follow node logs
docker compose logs -f mcp-server               # Follow MCP logs
docker compose ps                               # Service status
docker compose down                             # Stop (preserve data)
docker compose down -v                          # Stop and purge volumes

# ── Health Checks ──────────────────────────────────────────────
curl http://localhost:8001/health
curl http://localhost:8001/docs                  # Swagger UI

# ── CLI ────────────────────────────────────────────────────────
python -m nautilus_trader.cli.main node status
python -m nautilus_trader.cli.main --format json portfolio summary | jq .

# ── MCP Server (standalone) ───────────────────────────────────
python -m nautilus_trader.mcp.server             # stdio transport
NAUTILUS_MCP_TRANSPORT=sse python -m nautilus_trader.mcp.server  # SSE on :8002

# ── AI Agent ───────────────────────────────────────────────────
export ANTHROPIC_API_KEY=sk-ant-...
python deploy/scripts/start_agent.py --mode MONITOR
python deploy/scripts/start_agent.py --mode SEMI_AUTONOMOUS --max-order-size 0.1
```

---

## Cloud Deployment (Future)

This local setup is designed to port directly to cloud infrastructure:

| Local | AWS Equivalent |
|-------|---------------|
| Docker Compose | ECS/Fargate task definitions |
| `deploy/.env` | Secrets Manager / Parameter Store |
| Redis container | ElastiCache for Redis |
| Postgres container | RDS for PostgreSQL |
| Bridge network | VPC with private subnets |
| Docker health checks | ECS health checks + CloudWatch |
| `docker compose logs` | CloudWatch Logs |

Next steps for cloud:
1. Add `deploy/terraform/` with AWS infrastructure modules
2. Create ECR repository for the Docker image
3. Set up ECS service with auto-scaling
4. Configure ALB for the API server with TLS
5. Add monitoring with CloudWatch dashboards
