# ADR-005: AI Agent Orchestration Loop

| Field       | Value                                      |
|-------------|--------------------------------------------|
| **Status**  | Proposed                                   |
| **Date**    | 2026-03-21                                 |
| **Authors** | Mohsen Zainalpour                          |
| **Depends** | ADR-001, ADR-002, ADR-003                  |
| **Relates** | ADR-004                                    |

## Context

With the API server (ADR-001), event streaming (ADR-002), and MCP server (ADR-003) in place, NautilusTrader becomes fully accessible to external AI agents. The remaining challenge is **orchestration**: an autonomous loop that receives events, reasons about them using an LLM, and takes actions to achieve high-level trading objectives.

Today, NautilusTrader requires trading logic to be encoded as Python `Strategy` subclasses. Each strategy implements deterministic event handlers (`on_bar()`, `on_quote()`, `on_order_filled()`) with hard-coded decision logic. This approach works well for systematic strategies with clearly defined rules, but falls short for:

1. **Adaptive behavior**: Reacting to regime changes, news events, or unusual market conditions that weren't anticipated in the strategy code.
2. **Multi-strategy coordination**: Adjusting strategy allocations, starting/stopping strategies based on portfolio-level conditions.
3. **Natural language objectives**: Expressing goals like "build a 10 BTC position over 24 hours, scaling in on dips" without coding a custom strategy.
4. **Risk oversight**: Continuous monitoring of portfolio risk with nuanced judgment calls that go beyond simple threshold-based rules.
5. **Operational management**: Handling the operational aspects of trading (reconciliation anomalies, adapter errors, strategy health) that currently require human attention.

An AI agent loop bridges this gap by adding a reasoning layer on top of the existing execution infrastructure.

### Design Principles

- **The agent is a consumer, not a replacement.** It uses the same API, events, and tools as any other external client. It does not modify NautilusTrader internals.
- **Safety is non-negotiable.** An autonomous agent managing capital must have hard limits that cannot be overridden by reasoning.
- **Graceful degradation.** If the agent fails, crashes, or loses connectivity, the trading system continues operating with its existing strategies. The agent is additive.
- **Transparency.** Every agent decision is logged with its reasoning, input state, and outcome for post-hoc review.

## Decision

**Create an AI agent orchestration framework (`nautilus_trader/agent/`) that connects to NautilusTrader via the event stream and API, uses Claude for reasoning, and executes actions within configurable safety guardrails.**

### Agent Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Agent Orchestrator                        │
│                                                             │
│  ┌─────────────────┐   ┌──────────────────┐                │
│  │ Event Processor  │   │  State Manager   │                │
│  │                  │   │                  │                │
│  │ WebSocket client │   │ Portfolio snap   │                │
│  │ Event batching   │   │ Decision history │                │
│  │ Priority queue   │   │ Objective state  │                │
│  │ Context window   │   │ Persistence      │                │
│  └────────┬─────────┘   └────────┬─────────┘                │
│           │                       │                          │
│  ┌────────▼───────────────────────▼─────────┐               │
│  │           Reasoning Engine               │               │
│  │                                          │               │
│  │  Claude API (tool use)                   │               │
│  │  System prompt + objectives + state      │               │
│  │  Multi-turn for complex decisions        │               │
│  └────────────────────┬─────────────────────┘               │
│                       │                                      │
│  ┌────────────────────▼─────────────────────┐               │
│  │           Safety Layer                    │               │
│  │                                          │               │
│  │  Pre-action validation                   │               │
│  │  Position limits, loss limits            │               │
│  │  Rate limiting, instrument allowlists    │               │
│  │  Human-in-the-loop escalation            │               │
│  │  Kill switch                             │               │
│  └────────────────────┬─────────────────────┘               │
│                       │                                      │
│  ┌────────────────────▼─────────────────────┐               │
│  │           Action Executor                 │               │
│  │                                          │               │
│  │  MCP tool calls or direct API calls      │               │
│  │  Execution verification                  │               │
│  │  Outcome recording                       │               │
│  └──────────────────────────────────────────┘               │
└─────────────────────────────────────────────────────────────┘
         │                              ▲
         │ Actions (HTTP)               │ Events (WebSocket)
         ▼                              │
┌─────────────────────────────────────────────────────────────┐
│              NautilusTrader (via API + Events)               │
└─────────────────────────────────────────────────────────────┘
```

### Operating Modes

The agent supports four operating modes with increasing levels of autonomy:

| Mode              | Event Processing | Queries | Mutations        | Use Case                    |
|-------------------|-----------------|---------|------------------|-----------------------------|
| `MONITOR`         | Yes             | Yes     | None             | Observability, alerting     |
| `ADVISORY`        | Yes             | Yes     | Suggest only     | Human-in-the-loop trading   |
| `SEMI_AUTONOMOUS` | Yes             | Yes     | Low-risk auto    | Supervised automation       |
| `AUTONOMOUS`      | Yes             | Yes     | All within limits| Full AI-directed trading    |

**Mode escalation rules:**
- `SEMI_AUTONOMOUS` auto-executes: queries, small orders within limits, strategy start/stop
- `SEMI_AUTONOMOUS` escalates: large orders, market exits, cancel-all, risk limit changes
- `AUTONOMOUS` auto-executes everything within guardrail limits
- All modes log decisions with reasoning

### Objective System

Agents are directed by high-level objectives rather than step-by-step instructions:

```python
# Portfolio-level objective
PortfolioObjective(
    description="Maintain portfolio delta between -0.1 and +0.1",
    priority=1,
    check_interval_secs=60,
)

# Position-level objective
PositionObjective(
    description="Build a 10 BTC long position, scaling in over 24h, max 0.5 BTC per entry, prefer buying on 1% dips",
    instrument_id="BTCUSDT-PERP.BINANCE",
    priority=2,
    constraints={"max_entry_size": "0.5", "time_horizon_hours": 24},
)

# Monitoring objective
MonitoringObjective(
    description="Alert if daily realized P&L drops below -$5000",
    priority=1,
    alert_channel="webhook",
)

# Strategy management objective
StrategyObjective(
    description="Start the momentum strategy when BTC 1h volume exceeds 2x the 30-day average",
    strategy_id="Momentum-001",
    priority=3,
)
```

Each objective has:
- **description**: Natural language goal (fed to Claude as context)
- **priority**: Determines processing order when objectives conflict
- **constraints**: Hard limits specific to this objective
- **status**: `ACTIVE`, `PAUSED`, `COMPLETED`, `FAILED`
- **progress**: Trackable metrics (e.g., "4.2 / 10 BTC accumulated")

### Safety Guardrails

Safety guardrails are **hard limits enforced programmatically** — they cannot be overridden by Claude's reasoning:

```python
class GuardrailConfig(NautilusConfig, frozen=True):
    max_position_size: dict[str, str] = {}       # per-instrument max
    max_portfolio_exposure: str | None = None     # total exposure cap
    max_daily_loss: str | None = None             # daily loss kill switch
    max_orders_per_minute: int = 10               # order rate limit
    max_single_order_size: str | None = None      # per-order cap
    instrument_allowlist: list[str] | None = None  # only trade these
    instrument_blocklist: list[str] = []           # never trade these
    require_stop_loss: bool = False                # all positions need stops
    human_approval_threshold: str | None = None    # order value for escalation
    kill_switch_conditions: list[str] = []         # auto-halt conditions
```

**Kill switch**: If any kill switch condition is triggered (e.g., daily loss limit hit), the agent:
1. Immediately stops submitting new orders
2. Optionally cancels all open orders
3. Switches to `MONITOR` mode
4. Alerts the operator
5. Requires manual restart to resume trading

### Event Processing

The agent processes events in batches to manage Claude API costs and latency:

1. **Ingestion**: WebSocket client receives events from NautilusTrader
2. **Filtering**: Events filtered by relevance to active objectives
3. **Batching**: Events accumulated over a configurable window (default: 1 second) or until a high-priority event arrives (order fill, position change)
4. **Context assembly**: Current state (positions, portfolio, objectives) combined with event batch
5. **Reasoning**: Claude processes the context and decides on actions
6. **Execution**: Actions validated against guardrails and executed via API
7. **Recording**: Decision, reasoning, and outcome logged

**Context window management**: To control token usage, the agent maintains a sliding window of recent events. Older events are summarized (by Claude) into compressed state updates.

### Decision Audit Trail

Every decision is recorded:

```json
{
  "decision_id": "d-20260321-001",
  "timestamp": "2026-03-21T12:00:00Z",
  "mode": "SEMI_AUTONOMOUS",
  "trigger": {
    "events": ["OrderFilled(O-001, BUY 0.5 BTC @ 67450)"],
    "objective": "Build 10 BTC position"
  },
  "reasoning": "Position is now 4.5 BTC. Target is 10 BTC. Current price is near 24h low. Objective says to prefer buying on dips. Placing another 0.5 BTC limit order 0.5% below current price.",
  "action": {
    "tool": "nautilus_submit_order",
    "params": {"instrument_id": "BTCUSDT-PERP.BINANCE", "side": "BUY", "type": "LIMIT", "quantity": "0.5", "price": "67112.50"}
  },
  "guardrail_check": {
    "passed": true,
    "checks": ["position_limit: 5.0/10.0 OK", "order_size: 0.5/1.0 OK", "rate_limit: 3/10 OK"]
  },
  "outcome": {
    "status": "executed",
    "order_id": "O-002"
  }
}
```

## Consequences

### Positive

- **AI-directed trading**: Natural language objectives replace hard-coded strategy logic for adaptive scenarios.
- **Portfolio-level intelligence**: An agent can coordinate across multiple strategies, something individual strategies cannot do.
- **Operational automation**: Routine operational tasks (health monitoring, anomaly detection, reconciliation review) can be delegated to the agent.
- **Auditability**: Every decision includes reasoning traces, enabling post-hoc review and improvement.
- **Graceful degradation**: The agent is additive — if it fails, existing strategies continue running.

### Negative

- **Latency**: Claude API calls add 500ms-5s per decision cycle. This is unsuitable for latency-sensitive HFT but acceptable for medium-frequency strategies and portfolio management.
- **Token costs**: Each decision cycle consumes Claude API tokens. At $15/M tokens for Opus, a highly active agent processing events every second could cost $50-200/day. Batching and filtering mitigate this.
- **AI reasoning errors**: Claude may misinterpret market conditions or make suboptimal decisions. Safety guardrails limit the blast radius, but errors with real capital are possible.
- **Complexity**: The agent framework adds significant complexity. It must handle: API failures, WebSocket disconnections, Claude API outages, state recovery, and objective conflicts.
- **Regulatory considerations**: Autonomous AI-directed trading may have regulatory implications depending on jurisdiction. Users are responsible for compliance.

### Neutral

- The agent framework is entirely optional and has no impact on existing NautilusTrader functionality.
- The choice of Claude as the reasoning engine is pragmatic (best tool-use support) but the architecture is LLM-agnostic — the reasoning engine interface can be adapted to other models.
- Starting in `MONITOR` mode and progressively increasing autonomy is the recommended adoption path.
