# NautilusTrader AI Agent Control Plane — Quick Start

## Prerequisites

| Requirement | Install |
|-------------|---------|
| Docker | [docker.com/get-docker](https://docs.docker.com/get-docker/) |
| Rust 1.94+ | `rustup update stable` |
| clang | Xcode CLI tools (macOS) or `apt install clang` (Linux) |
| capnproto | `brew install capnp` (macOS) or `apt install capnproto` (Linux) |
| uv | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |

## 1. Build

```bash
git clone https://github.com/EtaCassiopeia/nautilus_trader.git
cd nautilus_trader
git checkout feat/ai-agent-control-plane-combined

make install-debug    # ~5-10 min first time (compiles Rust + Cython)
```

## 2. Start Redis

```bash
docker compose -f deploy/docker-compose.dev.yml up -d redis
```

## 3. Pick a Run Mode

### A. Backtest — no keys required

Runs an EMA Cross strategy on bundled ETHUSDT tick data with simulated fills.

```bash
uv run python deploy/scripts/run_backtest_with_api.py
```

### B. Demo Node — no keys required

Starts the trading node with the REST API server. No exchange connected.

```bash
uv run python deploy/scripts/run_demo.py
```

Verify:
```bash
curl http://localhost:8001/health
curl http://localhost:8001/api/v1/node/status
```

Swagger UI: http://localhost:8001/docs

### C. Binance Testnet — free testnet keys

Get free keys at https://testnet.binance.vision/, then:

```bash
export BINANCE_TESTNET_API_KEY=your_key
export BINANCE_TESTNET_API_SECRET=your_secret

uv run python deploy/scripts/run_sandbox.py
```

Connects to live Binance testnet data. EMA Cross strategy generates BUY/SELL signals on 1-minute BTCUSDT bars.

### D. AI Agent — requires Anthropic key

```bash
export ANTHROPIC_API_KEY=sk-ant-...

# Monitor mode (read-only analysis, no trades)
uv run python deploy/scripts/start_enhanced_agent.py --mode MONITOR

# Full multi-agent pipeline with trading
uv run python deploy/scripts/start_enhanced_agent.py \
    --mode SEMI_AUTONOMOUS \
    --max-order-size 0.001 \
    --max-daily-loss -100 \
    --memory-path ./trades.jsonl
```

### E. Full Docker Stack — no local build needed

```bash
cd deploy
cp .env.example .env    # Edit with your API keys
docker compose up -d --build
```

| Service | Port | URL |
|---------|------|-----|
| NautilusTrader API | 8001 | http://localhost:8001 |
| MCP Server (SSE) | 8002 | http://localhost:8002/sse |
| Redis | 6379 | — |
| Postgres | 5432 | — |

## 4. Connect Claude Code

```bash
cp deploy/mcp.json .mcp.json
```

Claude Code gains access to 24 trading tools: query orders, portfolio, positions, submit orders, manage strategies, and more.

## 5. Use the CLI

```bash
uv run python -m nautilus_trader.cli.main node status
uv run python -m nautilus_trader.cli.main order list --format json
uv run python -m nautilus_trader.cli.main portfolio summary
```

## API Keys Summary

| Key | Required For | Free? | Where |
|-----|-------------|-------|-------|
| Binance Testnet | Modes C, D | Yes | https://testnet.binance.vision/ |
| Anthropic | Mode D only | No (~$5-50/day) | https://console.anthropic.com |

**Modes A and B require zero API keys.**

## What's Next

- Full architecture guide: [`docs/architecture/GUIDE.md`](architecture/GUIDE.md)
- Deployment options: [`deploy/README.md`](../deploy/README.md)
- Research analysis: [`docs/architecture/research/ai-trading-agents-analysis.md`](architecture/research/ai-trading-agents-analysis.md)
