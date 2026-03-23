# NautilusTrader AI Agent Control Plane — Architecture, Design & Operations Guide

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture](#2-architecture)
3. [Component Deep Dive](#3-component-deep-dive)
4. [Enhanced Multi-Agent Trading System](#4-enhanced-multi-agent-trading-system)
5. [Configuration Reference](#5-configuration-reference)
6. [Running the System](#6-running-the-system)
7. [Operating the AI Agent](#7-operating-the-ai-agent)
8. [Safety & Risk Management](#8-safety--risk-management)
9. [API Reference](#9-api-reference)
10. [Extending the System](#10-extending-the-system)

---

## 1. System Overview

The AI Agent Control Plane transforms NautilusTrader from a code-only trading platform into an AI-controllable system. It adds four layers on top of the existing trading engine:

```
┌─────────────────────────────────────────────────────────────────────┐
│  Layer 4: AI Agents                                                  │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  Enhanced Multi-Agent Orchestrator                           │    │
│  │  ┌──────────┐  ┌───────────┐  ┌──────────┐  ┌───────────┐ │    │
│  │  │ Analyst  │→ │ Bull/Bear │→ │  Risk    │→ │ Portfolio │ │    │
│  │  │  Team    │  │  Debate   │  │  Team    │  │  Manager  │ │    │
│  │  └──────────┘  └───────────┘  └──────────┘  └───────────┘ │    │
│  └─────────────────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────────────────┤
│  Layer 3: Control Plane                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │
│  │ REST API │  │WebSocket │  │MCP Server│  │      CLI         │   │
│  │  :8001   │  │ /ws      │  │  :8002   │  │  nautilus ...    │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘   │
├─────────────────────────────────────────────────────────────────────┤
│  Layer 2: NautilusTrader Core                                        │
│  Data Engine │ Risk Engine │ Exec Engine │ Cache │ Strategies        │
├─────────────────────────────────────────────────────────────────────┤
│  Layer 1: Infrastructure                                             │
│  Redis (message bus) │ Postgres (persistence) │ Exchange Adapters    │
└─────────────────────────────────────────────────────────────────────┘
```

### What Each Layer Does

| Layer | Packages | Purpose |
|-------|----------|---------|
| **Infrastructure** | Redis, Postgres, Binance/Bybit/... | Data transport, persistence, market connectivity |
| **Core** | `nautilus_trader.*` (Cython/Rust) | Microsecond-latency trading engine with 400+ indicators |
| **Control Plane** | `nautilus_trader.api`, `.mcp`, `.cli` | External access via REST, WebSocket, MCP, and CLI |
| **AI Agents** | `nautilus_trader.agent` | Multi-agent reasoning, debate, risk assessment, and execution |

---

## 2. Architecture

### 2.1 Module Map

```
nautilus_trader/
├── api/                          # REST API + WebSocket
│   ├── config.py                 #   ApiServerConfig, EventStreamConfig
│   ├── server.py                 #   FastAPI app factory, ApiServer lifecycle
│   ├── middleware.py             #   API key auth, request logging, CORS
│   ├── dependencies.py           #   DI providers (get_cache, get_portfolio, ...)
│   ├── serialization.py          #   Event → JSON serialization
│   ├── streaming.py              #   EventStreamBridge, RingBuffer, ClientConnection
│   ├── ws_handler.py             #   WebSocket event stream handler
│   ├── models/
│   │   ├── requests.py           #   Request schemas
│   │   └── responses.py          #   ok_response(), error_response()
│   └── routes/
│       ├── node.py               #   GET/POST /api/v1/node/*
│       ├── strategies.py         #   CRUD /api/v1/strategies/*
│       ├── orders.py             #   CRUD /api/v1/orders/*
│       ├── portfolio.py          #   GET /api/v1/portfolio/*
│       ├── cache.py              #   GET /api/v1/cache/*
│       ├── market_data.py        #   GET /api/v1/data/*
│       ├── risk.py               #   GET /api/v1/risk/*
│       └── actors.py             #   GET /api/v1/actors/*
│
├── mcp/                          # Model Context Protocol server
│   ├── config.py                 #   McpServerConfig (TOML, env, overrides)
│   ├── client.py                 #   NautilusClient (async httpx wrapper)
│   ├── server.py                 #   MCP server factory, stdio/SSE transport
│   ├── safety.py                 #   SafetyGuardrails (3-tier + confirmation)
│   ├── resources.py              #   nautilus://status, nautilus://portfolio
│   └── tools/
│       ├── node.py               #   nautilus_node_status
│       ├── strategies.py         #   nautilus_list_strategies
│       ├── orders.py             #   nautilus_list_orders, nautilus_get_order
│       ├── portfolio.py          #   5 portfolio query tools
│       ├── market_data.py        #   instruments, quotes, bars
│       ├── risk.py               #   nautilus_get_risk_state
│       ├── node_mutations.py     #   nautilus_node_stop
│       ├── strategy_mutations.py #   start/stop/remove/market-exit
│       ├── order_mutations.py    #   submit/cancel/modify/cancel-all
│       └── risk_mutations.py     #   nautilus_set_risk_limits
│
├── cli/                          # Command-line interface
│   ├── config.py                 #   CliConfig (TOML, env, flags)
│   ├── client.py                 #   CliClient (sync httpx)
│   ├── output.py                 #   Table, JSON, CSV formatters
│   └── main.py                   #   Click command groups
│
└── agent/                        # AI Agent framework
    ├── config.py                 #   AgentConfig, EnhancedAgentConfig, ModelConfig
    ├── modes.py                  #   AgentMode enum, permission matrix
    ├── guardrails.py             #   KillSwitch, RateLimiter, AgentGuardrails
    ├── objectives.py             #   Objective, ObjectiveManager
    ├── audit.py                  #   Decision, AuditLog (JSONL persistence)
    ├── event_processor.py        #   AgentState, EventProcessor
    ├── prompts.py                #   System prompt templates
    ├── reasoning.py              #   ReasoningEngine (single-agent, Claude API)
    ├── orchestrator.py           #   AgentOrchestrator (single-agent loop)
    ├── memory.py                 #   TradeMemory, TradingMemory (cross-cycle)
    ├── debate.py                 #   DebateFramework (bull/bear)
    ├── risk_team.py              #   RiskTeam (3-perspective consensus)
    ├── portfolio_manager.py      #   PortfolioManager (final decision)
    ├── enhanced_orchestrator.py  #   EnhancedOrchestrator (multi-agent)
    └── analysts/
        ├── base.py               #   BaseAnalyst, AnalystReport
        ├── technical.py          #   TechnicalAnalyst (bars, quotes, indicators)
        ├── sentiment.py          #   SentimentAnalyst (event flow)
        ├── risk.py               #   RiskAnalyst (portfolio metrics)
        └── team.py               #   AnalystTeam (parallel execution)
```

### 2.2 Data Flow

```
Exchange (Binance, Bybit, ...)
    │
    ▼
NautilusTrader Core
    │
    ├── Events (order fills, position changes, bars, quotes)
    │       │
    │       ├──► WebSocket (/ws/events) ──► AI Agent Event Buffer
    │       │
    │       └──► EventStreamBridge ──► Ring Buffer (replay)
    │
    ├── State (via REST API)
    │       │
    │       ├──► AI Agent (queries portfolio, orders, positions)
    │       ├──► MCP Server (tool calls from Claude)
    │       └──► CLI (human operator)
    │
    └── Actions (via REST API)
            │
            ◄── AI Agent (submit order, start/stop strategy)
            ◄── MCP Server (Claude tool use)
            ◄── CLI (operator commands)
```

---

## 3. Component Deep Dive

### 3.1 REST API Server (`nautilus_trader/api/`)

The API server embeds inside the `TradingNode` process, running on the same asyncio event loop. This ensures thread-safe access to all kernel subsystems without inter-process communication.

**Activation**: Set `api_server` in `TradingNodeConfig`:
```python
TradingNodeConfig(
    api_server=ApiServerConfig(
        enabled=True,
        host="0.0.0.0",
        port=8001,
    ),
)
```

**Middleware stack** (last added runs first):
1. **CORSMiddleware** — Cross-origin resource sharing (optional)
2. **RequestLoggingMiddleware** — Logs method, path, status, latency
3. **ApiKeyMiddleware** — Validates `X-Api-Key` header (optional)

**Response envelope**:
```json
// Success
{"status": "ok", "data": {...}, "ts": "2026-03-23T12:00:00Z"}

// Error
{"status": "error", "error": {"code": "NOT_FOUND", "message": "..."}, "ts": "..."}
```

### 3.2 WebSocket Event Streaming (`nautilus_trader/api/streaming.py`)

The `EventStreamBridge` subscribes to the NautilusTrader message bus and fans out serialized events to connected WebSocket clients.

**Key components**:
- **RingBuffer** — Fixed-size circular buffer storing recent events for reconnection replay. Configurable `maxlen` (0 to disable).
- **ClientConnection** — Per-client event queue with topic filtering and backpressure (drops events when queue is full, tracks `dropped_count`).
- **Topic matching** — Wildcard patterns using `*` (any characters) and `?` (single character), matching NautilusTrader's message bus pattern syntax.

**WebSocket protocol**:
1. Client connects to `/ws/events`
2. Client sends optional subscribe: `{"action": "subscribe", "topics": ["events.*"]}`
3. Server pushes JSON event frames
4. Reconnect replay: `{"action": "replay", "last_sequence": 42}`
5. Ping/pong keepalive at configurable intervals

### 3.3 MCP Server (`nautilus_trader/mcp/`)

The MCP (Model Context Protocol) server runs as a **separate process** from the trading node. It connects to the REST API over HTTP, translating MCP tool calls into API requests.

**Transports**:
- **stdio** — For local Claude Code integration. Claude Code starts the process.
- **SSE** — For remote access. Runs as an HTTP server on `:8002`.

**24 tools** organized by function:

| Category | Read Tools | Mutation Tools |
|----------|-----------|----------------|
| Node | `nautilus_node_status` | `nautilus_node_stop` |
| Strategies | `nautilus_list_strategies` | `start`, `stop`, `remove`, `market_exit` |
| Orders | `nautilus_list_orders`, `get_order` | `submit`, `cancel`, `modify`, `cancel_all` |
| Portfolio | `summary`, `balances`, `positions`, `pnl`, `exposure` | — |
| Market Data | `instruments`, `get_instrument`, `quote`, `bars` | — |
| Risk | `nautilus_get_risk_state` | `nautilus_set_risk_limits` |

**Safety guardrails** (3-tier):

| Level | Read | Write | Critical |
|-------|------|-------|----------|
| UNRESTRICTED | No confirm | No confirm | No confirm |
| STANDARD | No confirm | No confirm | **Confirm required** |
| STRICT | No confirm | **Confirm required** | **Confirm required** |

Auto-escalation: `UNRESTRICTED` → `STANDARD` when trading node is in `LIVE` environment.

### 3.4 CLI (`nautilus_trader/cli/`)

Click-based command-line interface wrapping the REST API.

```
nautilus node status|stop
nautilus strategy list|start|stop|remove|market-exit
nautilus order list|get|cancel|cancel-all
nautilus portfolio summary|balances|positions|pnl|exposure
nautilus market instruments|quote|bars
nautilus risk state
```

**Output formats**: `--format table` (default), `--format json`, `--format csv`
**Config priority**: CLI flags > env vars > `~/.nautilus/cli.toml` > defaults

---

## 4. Enhanced Multi-Agent Trading System

### 4.1 Research Background

The enhanced architecture is based on analysis of three AI trading agent research projects:

- **TradingAgents** (TauricResearch) — Multi-agent trading firm simulation with bull/bear debate
- **AI-Trader** (HKUDS, arXiv:2512.10971) — Benchmarking autonomous agents in live markets
- **AI4Trade** — Agent marketplace with signal sharing

Key findings that shaped the design:
1. **Multi-agent debate reduces confirmation bias** (TradingAgents)
2. **Risk control capability determines cross-market robustness** (AI-Trader)
3. **General intelligence does not guarantee trading capability** (AI-Trader)
4. **Two-tier model strategy** reduces costs 10x while maintaining decision quality (TradingAgents)

### 4.2 Enhanced Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Enhanced Decision Cycle                                         │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  1. ANALYST TEAM  (parallel, Sonnet)                     │    │
│  │  ┌──────────────┐ ┌────────────────┐ ┌───────────────┐ │    │
│  │  │  Technical   │ │   Sentiment    │ │     Risk      │ │    │
│  │  │              │ │                │ │               │ │    │
│  │  │ Fetches bars │ │ Analyzes event │ │ Evaluates     │ │    │
│  │  │ & quotes via │ │ flow: fills,   │ │ positions,    │ │    │
│  │  │ API. Analyzes│ │ position moves │ │ exposure,     │ │    │
│  │  │ EMAs, RSI,   │ │ for momentum   │ │ concentration │ │    │
│  │  │ MACD, volume │ │ signals        │ │ and drawdown  │ │    │
│  │  └──────┬───────┘ └───────┬────────┘ └──────┬────────┘ │    │
│  │         └─────────────────┼─────────────────┘          │    │
│  │                    AnalystReport[]                       │    │
│  └────────────────────────┬────────────────────────────────┘    │
│                           ▼                                      │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  2. BULL/BEAR DEBATE  (Opus, configurable rounds)       │    │
│  │                                                          │    │
│  │  Round 1: Generate initial bull & bear cases             │    │
│  │  Round 2: Each side rebuts the other                     │    │
│  │  Round N: Additional rebuttals (configurable)            │    │
│  │  Final:   Synthesize → BUY / SELL / HOLD + conviction    │    │
│  │                                                          │    │
│  │  ┌──────────┐        ┌──────────┐                       │    │
│  │  │   BULL   │◄──────►│   BEAR   │                       │    │
│  │  │Researcher│ rebut  │Researcher│                       │    │
│  │  └──────────┘        └──────────┘                       │    │
│  └────────────────────────┬────────────────────────────────┘    │
│                           ▼                                      │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  3. RISK TEAM  (parallel, Sonnet, 2/3 consensus)        │    │
│  │                                                          │    │
│  │  ┌────────────┐  ┌──────────┐  ┌──────────────┐        │    │
│  │  │ Aggressive │  │ Neutral  │  │ Conservative │        │    │
│  │  │ "Focus on  │  │ "Balance │  │ "Prioritize  │        │    │
│  │  │  upside"   │  │  risk &  │  │  capital     │        │    │
│  │  │            │  │  reward" │  │  preservation"│        │    │
│  │  └─────┬──────┘  └────┬─────┘  └──────┬───────┘        │    │
│  │        └──────────────┼───────────────┘                │    │
│  │              Consensus: ≥2 of 3 must approve            │    │
│  └────────────────────────┬────────────────────────────────┘    │
│                           ▼                                      │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  4. PORTFOLIO MANAGER  (Opus, final authority)           │    │
│  │                                                          │    │
│  │  Inputs: debate result + risk verdict + state +          │    │
│  │          objectives + trade memory                       │    │
│  │                                                          │    │
│  │  Output: APPROVE with tool call  OR  REJECT with reason  │    │
│  └────────────────────────┬────────────────────────────────┘    │
│                           ▼                                      │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  5. GUARDRAILS  (programmatic, cannot be overridden)     │    │
│  │                                                          │    │
│  │  Kill switch │ Mode permissions │ Rate limit │            │    │
│  │  Instrument lists │ Position limits │ Daily loss          │    │
│  └────────────────────────┬────────────────────────────────┘    │
│                           ▼                                      │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  6. EXECUTION  (via NautilusTrader REST API)             │    │
│  │                                                          │    │
│  │  Action dispatched → API call → Order submitted          │    │
│  │  Result recorded to memory + audit trail                 │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

### 4.3 Two-Tier Model Strategy

Different models are used for different tasks to optimize cost and quality:

| Stage | Model | Why |
|-------|-------|-----|
| Event triage | **Haiku** (claude-haiku-4-5) | Fast, cheap — processes high-volume events |
| Analyst team | **Sonnet** (claude-sonnet-4) | Good reasoning at moderate cost — 3 parallel calls |
| Bull/Bear debate | **Opus** (claude-opus-4) | Deep reasoning for adversarial arguments — 5-7 calls |
| Risk assessment | **Sonnet** (claude-sonnet-4) | Balanced analysis — 3 parallel calls |
| Portfolio decision | **Opus** (claude-opus-4) | Critical decision with tool use — 1 call |

**Cost estimate per cycle**: ~$0.05-0.15 (vs ~$0.50+ with Opus for everything)

### 4.4 Analyst Reports

Each analyst produces a structured `AnalystReport`:

```python
@dataclass
class AnalystReport:
    analyst_name: str     # "technical", "sentiment", "risk"
    signal: str           # "BULLISH", "BEARISH", "NEUTRAL"
    confidence: float     # 0.0 to 1.0
    summary: str          # Human-readable analysis
    data: dict            # Structured backing data
    model_used: str       # Which Claude model generated this
```

**TechnicalAnalyst** — Fetches bars and quotes via `/api/v1/data/bars` and `/api/v1/data/quotes`. Analyzes EMA crossovers, RSI (overbought >70, oversold <30), MACD histogram, volume trends, and price action patterns.

**SentimentAnalyst** — Analyzes the event stream: order fill patterns (aggressive buying/selling), position change directions, event intensity and clustering. In production, extend with external news/social APIs.

**RiskAnalyst** — Fetches positions via `/api/v1/portfolio/positions` and accounts via `/api/v1/cache/accounts`. Evaluates concentration risk, unrealized P&L, exposure levels, and drawdown severity.

**AnalystTeam** — Runs all analysts in parallel via `asyncio.gather()`. Computes a confidence-weighted consensus signal.

### 4.5 Bull/Bear Debate

Inspired by TradingAgents' structured debate framework:

1. **Generate** — Bull researcher builds the bullish case from analyst reports. Bear researcher builds the bearish case.
2. **Rebut** — Each side critiques the other's argument (configurable rounds, default 2).
3. **Synthesize** — An impartial synthesis produces: recommendation (BUY/SELL/HOLD), conviction score (0-1), and summary.

```python
@dataclass
class DebateResult:
    bull_case: DebatePosition    # Final bull argument
    bear_case: DebatePosition    # Final bear argument
    synthesis: str               # Impartial conclusion
    recommended_action: str      # "BUY", "SELL", "HOLD"
    conviction: float            # 0.0 to 1.0
    rounds_completed: int
```

**Why debate matters**: The TradingAgents paper showed that bull/bear debate significantly reduces confirmation bias — a single-agent LLM tends to anchor on its first interpretation.

### 4.6 Risk Team (3-Perspective Consensus)

Three risk assessors evaluate the proposed action in parallel:

| Perspective | Bias | Typical Behavior |
|------------|------|-----------------|
| **Aggressive** | Pro-trade | Approves unless catastrophic risk |
| **Neutral** | Balanced | Weighs risk vs reward evenly |
| **Conservative** | Risk-averse | Rejects unless risk is minimal |

**Consensus rule**: Action is approved only if **≥2 of 3** assessors approve (configurable via `risk_consensus_threshold`).

```python
@dataclass
class RiskVerdict:
    assessments: list[RiskAssessment]  # 3 assessments
    approved: bool                      # 2/3 consensus
    consensus_score: float              # Average risk score
    summary: str
```

### 4.7 Cross-Cycle Memory

The `TradingMemory` system persists trade decisions and outcomes across cycles:

```python
@dataclass
class TradeMemory:
    trade_id: str
    timestamp: str
    instrument_id: str
    side: str                  # "BUY" or "SELL"
    quantity: str
    entry_reasoning: str       # Why the trade was made
    market_conditions: dict    # State snapshot at decision time
    outcome: dict | None       # P&L, duration (filled after close)
```

**Learning queries**:
- `get_winning_patterns()` — Trades with positive P&L
- `get_losing_patterns()` — Trades with negative P&L
- `get_performance_summary()` — Win rate, avg profit, avg loss
- `get_by_instrument()` — Past trades for a specific instrument

Memory context is included in the Portfolio Manager's prompt so it can learn from past mistakes and successes.

### 4.8 Portfolio Manager

The final decision authority. Receives:
- Debate result (recommendation + conviction)
- Risk verdict (consensus + scores)
- Current portfolio state
- Active objectives
- Trade memory context

Uses Claude Opus with tool-use to select the appropriate action:

```python
@dataclass
class PortfolioDecision:
    action: dict | None       # Tool call to execute, or None
    approved: bool
    reasoning: str
    risk_verdict: RiskVerdict
    debate_result: DebateResult
```

Short-circuits with rejection if the risk team disapproves (no LLM call needed).

---

## 5. Configuration Reference

### 5.1 EnhancedAgentConfig

```python
@dataclass(frozen=True)
class EnhancedAgentConfig(AgentConfig):
    # Model selection (two-tier strategy)
    models: ModelConfig                    # See below

    # Debate
    max_debate_rounds: int = 2            # Bull/bear rebuttal rounds
    enable_debate: bool = True            # Toggle debate framework

    # Risk team
    risk_consensus_threshold: int = 2     # N of 3 must approve
    enable_risk_team: bool = True         # Toggle risk team

    # Memory
    enable_memory: bool = True            # Toggle cross-cycle memory
    memory_storage_path: str | None       # JSONL file for persistence

    # Analysts
    analysts: list[str] = ["technical", "sentiment", "risk"]
```

### 5.2 ModelConfig

```python
@dataclass(frozen=True)
class ModelConfig:
    triage_model:   str = "claude-haiku-4-5-20251001"   # Event classification
    analyst_model:  str = "claude-sonnet-4-20250514"     # Analyst team
    debate_model:   str = "claude-opus-4-20250514"       # Deep reasoning
    risk_model:     str = "claude-sonnet-4-20250514"     # Risk assessment
    decision_model: str = "claude-opus-4-20250514"       # Portfolio manager
```

### 5.3 GuardrailConfig

```python
@dataclass(frozen=True)
class GuardrailConfig:
    max_position_size: dict[str, str]      # Per-instrument max
    max_portfolio_exposure: str | None      # Total exposure cap
    max_daily_loss: str | None             # Kill switch threshold
    max_orders_per_minute: int = 10        # Rate limit
    max_single_order_size: str | None      # Per-order cap
    instrument_allowlist: list[str] | None # Only trade these
    instrument_blocklist: list[str] = []   # Never trade these
    require_stop_loss: bool = False        # Require stops on all positions
    human_approval_threshold: str | None   # Notional value for escalation
    kill_switch_conditions: list[str] = [] # Auto-halt conditions
```

### 5.4 Operating Modes

| Mode | Queries | Low-Risk | High-Risk | Critical |
|------|---------|----------|-----------|----------|
| **MONITOR** | Auto | Blocked | Blocked | Blocked |
| **ADVISORY** | Auto | Needs approval | Needs approval | Needs approval |
| **SEMI_AUTONOMOUS** | Auto | Auto | Needs approval | Needs approval |
| **AUTONOMOUS** | Auto | Auto | Auto | Auto |

---

## 6. Running the System

### 6.1 Prerequisites

- Docker and Docker Compose
- Python 3.12+ with NautilusTrader compiled (or use Docker for everything)
- Redis (required for message bus)
- Anthropic API key (for AI Agent)

### 6.2 Quick Start — Infrastructure + Demo Node

```bash
# Start Redis
docker compose -f deploy/docker-compose.dev.yml up -d redis

# Start demo node (no exchange, API server only)
uv run python deploy/scripts/run_demo.py
```

Verify: `curl http://localhost:8001/health`

### 6.3 Binance Testnet Sandbox

```bash
# Set testnet keys (free at https://testnet.binance.vision/)
export BINANCE_TESTNET_API_KEY=your_key
export BINANCE_TESTNET_API_SECRET=your_secret

# Start with live data feed + EMA Cross strategy
uv run python deploy/scripts/run_sandbox.py
```

### 6.4 Backtest Simulation (No Keys Required)

```bash
uv run python deploy/scripts/run_backtest_with_api.py
```

Runs an EMA Cross strategy on bundled ETHUSDT tick data with simulated fills.

### 6.5 Full Docker Stack

```bash
cd deploy
cp .env.example .env    # Edit with API keys
docker compose up -d --build
```

Services: Redis (:6379), Postgres (:5432), NautilusTrader (:8001), MCP Server (:8002)

### 6.6 Connect Claude Code

```bash
cp deploy/mcp.json .mcp.json
```

Claude Code auto-discovers the MCP server and gains access to all 24 trading tools.

---

## 7. Operating the AI Agent

### 7.1 Single-Agent Mode (Original)

```bash
export ANTHROPIC_API_KEY=sk-ant-...

python deploy/scripts/start_agent.py --mode MONITOR
python deploy/scripts/start_agent.py --mode SEMI_AUTONOMOUS --max-order-size 0.1
```

### 7.2 Enhanced Multi-Agent Mode

```bash
export ANTHROPIC_API_KEY=sk-ant-...

# Full pipeline: analysts → debate → risk team → portfolio manager
python deploy/scripts/start_enhanced_agent.py \
    --mode SEMI_AUTONOMOUS \
    --analysts technical,sentiment,risk \
    --debate-rounds 2 \
    --max-order-size 0.1 \
    --max-daily-loss -5000 \
    --memory-path ./trade_memory.jsonl \
    --interval 10
```

### 7.3 Command-Line Options

| Flag | Default | Description |
|------|---------|-------------|
| `--mode` | `MONITOR` | Operating mode |
| `--api-url` | `http://localhost:8001` | NautilusTrader API |
| `--interval` | `10` | Seconds between decision cycles |
| `--analysts` | `technical,sentiment,risk` | Comma-separated analyst list |
| `--debate-rounds` | `2` | Bull/bear rebuttal rounds |
| `--no-debate` | — | Disable debate (skip to risk team) |
| `--no-risk-team` | — | Disable risk team (skip to portfolio manager) |
| `--no-memory` | — | Disable cross-cycle memory |
| `--memory-path` | — | JSONL file for memory persistence |
| `--max-order-size` | — | Per-order quantity limit |
| `--max-daily-loss` | — | Kill switch threshold (e.g., `-5000`) |
| `--triage-model` | `claude-haiku-4-5-20251001` | Event triage model |
| `--analyst-model` | `claude-sonnet-4-20250514` | Analyst team model |
| `--debate-model` | `claude-opus-4-20250514` | Debate model |
| `--risk-model` | `claude-sonnet-4-20250514` | Risk team model |
| `--decision-model` | `claude-opus-4-20250514` | Portfolio manager model |

### 7.4 Recommended Configurations

**Conservative start** (monitor only, full analysis):
```bash
python deploy/scripts/start_enhanced_agent.py --mode MONITOR --interval 30
```

**Paper trading** (execute small orders on testnet):
```bash
python deploy/scripts/start_enhanced_agent.py \
    --mode SEMI_AUTONOMOUS \
    --max-order-size 0.001 \
    --max-daily-loss -100 \
    --debate-rounds 3 \
    --memory-path ./paper_trades.jsonl
```

**Cost-optimized** (use Sonnet everywhere, skip Opus):
```bash
python deploy/scripts/start_enhanced_agent.py \
    --mode MONITOR \
    --debate-model claude-sonnet-4-20250514 \
    --decision-model claude-sonnet-4-20250514 \
    --interval 60
```

**Minimal pipeline** (fast, no debate/risk):
```bash
python deploy/scripts/start_enhanced_agent.py \
    --mode ADVISORY \
    --no-debate --no-risk-team \
    --analysts technical
```

---

## 8. Safety & Risk Management

### 8.1 Defense in Depth

Safety is enforced at four independent layers:

```
Layer 1: MCP Safety Guardrails
  └── Confirmation protocol, read-only mode, tool filtering

Layer 2: Agent Operating Mode
  └── Permission matrix (MONITOR → AUTONOMOUS)

Layer 3: Programmatic Guardrails (cannot be overridden by LLM)
  ├── Kill switch (daily loss trigger)
  ├── Rate limiter (orders per minute)
  ├── Instrument allow/blocklists
  ├── Position size limits
  └── Order size limits

Layer 4: NautilusTrader Risk Engine
  └── Pre-trade risk checks, max order rates, notional limits
```

### 8.2 Kill Switch

Triggers automatically when:
- Daily realized P&L drops below `max_daily_loss`
- Any configured `kill_switch_conditions` are met

When triggered:
1. All new order submissions are **blocked**
2. Agent switches to **MONITOR** mode
3. Trigger reason is logged
4. **Manual reset required** (`kill_switch.reset()`)

### 8.3 Decision Audit Trail

Every decision is recorded with full context:

```json
{
    "cycle": 42,
    "timestamp": "2026-03-23T12:00:00Z",
    "mode": "SEMI_AUTONOMOUS",
    "approved": true,
    "action": {"tool": "nautilus_submit_order", "params": {...}},
    "reasoning": "Technical: bullish (80%), debate: BUY (75% conviction), risk: approved (0.35 score)",
    "debate": {"recommendation": "BUY", "conviction": 0.75},
    "risk": {"approved": true, "score": 0.35}
}
```

---

## 9. API Reference

### REST Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Node health (public) |
| GET | `/api/v1/node/status` | Node status |
| POST | `/api/v1/node/stop` | Stop node |
| GET | `/api/v1/strategies` | List strategies |
| POST | `/api/v1/strategies/{id}/start` | Start strategy |
| POST | `/api/v1/strategies/{id}/stop` | Stop strategy |
| DELETE | `/api/v1/strategies/{id}` | Remove strategy |
| GET | `/api/v1/orders` | List orders (`?status=open&limit=50`) |
| GET | `/api/v1/orders/{id}` | Order detail |
| DELETE | `/api/v1/orders/{id}` | Cancel order |
| POST | `/api/v1/orders/cancel-all` | Cancel all |
| GET | `/api/v1/portfolio` | Portfolio summary |
| GET | `/api/v1/portfolio/balances` | Balances (`?venue=BINANCE`) |
| GET | `/api/v1/portfolio/positions` | Positions |
| GET | `/api/v1/portfolio/pnl` | P&L |
| GET | `/api/v1/portfolio/exposure` | Exposures |
| GET | `/api/v1/cache/instruments` | Instruments (`?venue=BINANCE`) |
| GET | `/api/v1/cache/instruments/{id}` | Instrument detail |
| GET | `/api/v1/data/bars/{id}` | Bars (`?bar_type=...&count=10`) |
| GET | `/api/v1/data/quotes/{id}` | Latest quote |
| GET | `/api/v1/data/trades/{id}` | Recent trades |
| GET | `/api/v1/risk/status` | Risk engine state |
| GET | `/api/v1/risk/config` | Risk config |
| GET | `/api/v1/actors` | List actors |
| WS | `/ws/events` | Live event stream |

### MCP Tools

See `nautilus_trader/mcp/tools/` for 14 read-only + 10 mutation tools.

---

## 10. Extending the System

### 10.1 Adding a Custom Analyst

```python
from nautilus_trader.agent.analysts.base import BaseAnalyst, AnalystReport

class NewsAnalyst(BaseAnalyst):
    def __init__(self, client, news_api_key: str, model: str = "claude-haiku-4-5-20251001"):
        super().__init__(name="news", client=client, model=model)
        self._news_api_key = news_api_key

    async def analyze(self, state: dict, events: list[dict]) -> AnalystReport:
        # Fetch news from external API
        headlines = await self._fetch_headlines()

        # Ask LLM to analyze sentiment
        response = await self._call_llm(
            system_prompt="You are a news sentiment analyst...",
            user_message=f"Headlines:\n{headlines}\n\nReturn JSON with signal, confidence, summary.",
        )

        parsed = self._parse_llm_json(response)
        return AnalystReport(
            analyst_name=self.name,
            signal=parsed.get("signal", "NEUTRAL"),
            confidence=parsed.get("confidence", 0.5),
            summary=parsed.get("summary", ""),
            data=parsed,
            model_used=self.model,
        )
```

Register in `EnhancedOrchestrator.start()` by adding to the analyst name → class mapping.

### 10.2 Adding Custom Risk Perspectives

Extend `RiskTeam` with domain-specific perspectives (e.g., "Regulatory", "Liquidity"):

```python
# Add to risk_team.py PERSPECTIVES dict
PERSPECTIVES = {
    "AGGRESSIVE": "Focus on maximizing returns...",
    "NEUTRAL": "Balance risk and reward...",
    "CONSERVATIVE": "Prioritize capital preservation...",
    "LIQUIDITY": "Evaluate market liquidity and slippage risk...",
}
```

### 10.3 Custom Objectives

```python
agent.add_objective({
    "objective_id": "btc-accumulation",
    "description": "Build a 10 BTC position over 24h, scaling in on 1% dips",
    "priority": 1,
    "constraints": {"max_entry_size": "0.5", "time_horizon_hours": 24},
})
```

Objectives are included in the Portfolio Manager's context, guiding decision-making.

---

## Document History

| Date | Change |
|------|--------|
| 2026-03-21 | Initial control plane architecture (API, MCP, CLI, single-agent) |
| 2026-03-23 | Enhanced multi-agent architecture (analysts, debate, risk team, memory) |
