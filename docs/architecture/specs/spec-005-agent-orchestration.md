# SPEC-005: AI Agent Orchestration

## Overview

The Agent Orchestration system is an event-driven AI agent loop that connects to NautilusTrader via the API server (SPEC-001) and event stream (SPEC-002), uses Claude for reasoning, and executes actions through MCP tools (SPEC-003) or direct API calls. It enables AI-directed trading where high-level objectives expressed in natural language are pursued autonomously within configurable safety guardrails.

The agent is a **consumer** of the NautilusTrader control plane — it uses the same APIs as the CLI or any other external client. It does not modify NautilusTrader internals.

## Module Structure

```
nautilus_trader/agent/
├── __init__.py
├── config.py              # AgentConfig, GuardrailConfig, ObjectiveConfig
├── orchestrator.py        # Main agent orchestration loop
├── event_processor.py     # Event ingestion, filtering, batching
├── reasoning.py           # Claude API integration and tool dispatch
├── state.py               # Agent state management and persistence
├── safety.py              # Guardrail enforcement and kill switch
├── objectives.py          # Objective definition, tracking, progress
├── modes.py               # Operating mode definitions and permissions
├── audit.py               # Decision audit trail logging
└── prompts/
    ├── __init__.py
    ├── system.py          # System prompts for each operating mode
    ├── analysis.py        # Market analysis prompt templates
    └── trading.py         # Trading decision prompt templates
```

## Configuration

### AgentConfig

```python
class AgentConfig(NautilusConfig, frozen=True):
    """Top-level agent configuration.

    Parameters
    ----------
    mode : str, default "MONITOR"
        Operating mode: MONITOR, ADVISORY, SEMI_AUTONOMOUS, AUTONOMOUS.
    model : str, default "claude-sonnet-4-20250514"
        Claude model for reasoning. Use claude-opus-4-0-20250415 for complex decisions.
    api_url : str, default "http://127.0.0.1:8001"
        NautilusTrader API server URL.
    api_key : str, optional
        API key for NautilusTrader API authentication.
    anthropic_api_key : str, optional
        Anthropic API key. Falls back to ANTHROPIC_API_KEY env var.
    objectives : list[ObjectiveConfig], default []
        High-level objectives the agent pursues.
    guardrails : GuardrailConfig
        Safety guardrails (hard limits, not overridable by reasoning).
    event_topics : list[str], default ["events.*"]
        MessageBus topic patterns to subscribe to.
    event_batch_interval_ms : int, default 1000
        Time window for batching events before processing.
    event_batch_max_size : int, default 50
        Max events per batch (triggers early processing).
    max_context_events : int, default 100
        Sliding window of recent events maintained in context.
    max_tokens_per_decision : int, default 4096
        Token budget per decision cycle.
    decision_log_path : str, default "agent_decisions.jsonl"
        Path for decision audit trail.
    state_persistence_path : str, default "agent_state.json"
        Path for agent state persistence.
    state_save_interval_secs : float, default 60.0
        Interval between automatic state saves.
    alert_webhook_url : str, optional
        Webhook URL for critical alerts.
    """
    mode: str = "MONITOR"
    model: str = "claude-sonnet-4-20250514"
    api_url: str = "http://127.0.0.1:8001"
    api_key: str | None = None
    anthropic_api_key: str | None = None
    objectives: list[ObjectiveConfig] = []
    guardrails: GuardrailConfig = GuardrailConfig()
    event_topics: list[str] = ["events.*"]
    event_batch_interval_ms: int = 1000
    event_batch_max_size: int = 50
    max_context_events: int = 100
    max_tokens_per_decision: int = 4096
    decision_log_path: str = "agent_decisions.jsonl"
    state_persistence_path: str = "agent_state.json"
    state_save_interval_secs: float = 60.0
    alert_webhook_url: str | None = None
```

### GuardrailConfig

```python
class GuardrailConfig(NautilusConfig, frozen=True):
    """Hard safety limits enforced programmatically.

    These limits CANNOT be overridden by Claude's reasoning.
    They are checked before every action is executed.
    """
    max_position_size: dict[str, str] = {}
        # Per-instrument max position. e.g., {"BTCUSDT-PERP.BINANCE": "10.0"}
    max_portfolio_exposure_usd: str | None = None
        # Total portfolio exposure cap in USD equivalent.
    max_daily_loss_usd: str | None = None
        # Daily loss limit. Triggers kill switch when breached.
    max_orders_per_minute: int = 10
        # Rate limit on order submissions.
    max_single_order_size: str | None = None
        # Maximum quantity for any single order.
    max_single_order_notional_usd: str | None = None
        # Maximum notional value for any single order.
    instrument_allowlist: list[str] | None = None
        # Only trade these instruments. None = all allowed.
    instrument_blocklist: list[str] = []
        # Never trade these instruments.
    require_stop_loss: bool = False
        # All new positions must have an associated stop loss.
    max_open_positions: int | None = None
        # Maximum number of concurrent open positions.
    human_approval_threshold_usd: str | None = None
        # Order notional above this requires human approval.
    kill_switch_on_daily_loss: bool = True
        # Auto-activate kill switch when daily loss limit hit.
    kill_switch_on_error: bool = False
        # Auto-activate kill switch on any agent error.
```

### ObjectiveConfig

```python
class ObjectiveConfig(NautilusConfig, frozen=True):
    """Configuration for a single agent objective.

    Parameters
    ----------
    objective_type : str
        Type: PORTFOLIO, POSITION, MONITORING, STRATEGY, RISK, CUSTOM.
    description : str
        Natural language description of the objective.
    priority : int, default 5
        Priority (1 = highest). Used for conflict resolution.
    instrument_id : str, optional
        Target instrument (for position objectives).
    strategy_id : str, optional
        Target strategy (for strategy objectives).
    constraints : dict, default {}
        Objective-specific constraints (fed to Claude as context).
    check_interval_secs : float, default 60.0
        How often to evaluate this objective (independent of events).
    auto_complete : bool, default False
        If True, objective can be marked COMPLETED by the agent.
    """
    objective_type: str = "CUSTOM"
    description: str = ""
    priority: int = 5
    instrument_id: str | None = None
    strategy_id: str | None = None
    constraints: dict = {}
    check_interval_secs: float = 60.0
    auto_complete: bool = False
```

## Agent Lifecycle

### 1. Initialization

```
AgentOrchestrator.__init__(config)
  ├── Validate config
  ├── Initialize HTTP client (for API calls)
  ├── Initialize Anthropic client (for Claude API)
  ├── Load persisted state (if exists)
  └── Initialize guardrail checker
```

### 2. Startup

```
AgentOrchestrator.start()
  ├── Query node status (GET /api/v1/node/status)
  │   └── Verify node is running and environment matches expectations
  ├── Query current state
  │   ├── GET /api/v1/strategies → populate strategy state
  │   ├── GET /api/v1/portfolio → populate portfolio state
  │   ├── GET /api/v1/portfolio/positions → populate position state
  │   └── GET /api/v1/risk/state → populate risk state
  ├── Connect to event stream (WebSocket /api/v1/events/stream)
  │   └── Subscribe to configured topic patterns
  ├── Initialize objectives from config
  ├── Start event processing loop
  ├── Start periodic objective check loop
  └── Start state persistence loop
```

### 3. Main Loop

```
while running:
  ├── Collect events (batched by time window or max size)
  ├── Filter events by relevance to active objectives
  ├── If no relevant events and no periodic check due:
  │   └── Continue (sleep until next event or check)
  ├── Assemble context:
  │   ├── Current portfolio state
  │   ├── Active objectives + progress
  │   ├── Recent event batch
  │   ├── Recent decision history (last N decisions)
  │   └── Guardrail state (remaining limits)
  ├── Call Claude with context + available tools
  │   ├── Claude reasons about events and objectives
  │   ├── Claude decides on actions (tool calls)
  │   └── Multi-turn if complex reasoning needed
  ├── For each proposed action:
  │   ├── Validate against guardrails (safety.py)
  │   ├── Check mode permissions (modes.py)
  │   ├── If blocked: log reason, skip action
  │   ├── If escalation needed: queue for human approval
  │   └── If allowed: execute via API
  ├── Record decision in audit trail
  ├── Update objective progress
  └── Update context window (slide forward, summarize old events)
```

### 4. Shutdown

```
AgentOrchestrator.stop()
  ├── Stop event processing loop
  ├── Disconnect WebSocket
  ├── Persist current state
  ├── Flush decision audit log
  └── (Existing strategies continue running — agent is additive)
```

## Operating Modes

### Mode Definitions

```python
class AgentMode(Enum):
    MONITOR = "MONITOR"
    ADVISORY = "ADVISORY"
    SEMI_AUTONOMOUS = "SEMI_AUTONOMOUS"
    AUTONOMOUS = "AUTONOMOUS"
```

### Permission Matrix

| Action Category          | MONITOR | ADVISORY | SEMI_AUTONOMOUS | AUTONOMOUS |
|--------------------------|---------|----------|-----------------|------------|
| Query portfolio/cache    | Yes     | Yes      | Yes             | Yes        |
| Query market data        | Yes     | Yes      | Yes             | Yes        |
| Generate alerts          | Yes     | Yes      | Yes             | Yes        |
| Suggest actions          | No      | Yes      | Yes             | Yes        |
| Start/stop strategies    | No      | No       | Yes             | Yes        |
| Submit small orders*     | No      | No       | Yes             | Yes        |
| Submit large orders**    | No      | No       | Escalate        | Yes        |
| Cancel orders            | No      | No       | Yes             | Yes        |
| Cancel ALL orders        | No      | No       | Escalate        | Yes        |
| Market exit strategy     | No      | No       | Escalate        | Yes        |
| Modify risk limits       | No      | No       | No              | Escalate   |
| Stop node               | No      | No       | No              | No***      |

\* Small = below `human_approval_threshold_usd`
\*\* Large = above `human_approval_threshold_usd`
\*\*\* Node stop always requires human confirmation

### ADVISORY Mode Output

In ADVISORY mode, the agent generates structured suggestions:

```json
{
  "suggestion_id": "s-20260321-001",
  "timestamp": "2026-03-21T12:00:00Z",
  "objective": "Build 10 BTC position",
  "analysis": "BTC dropped 1.2% in the last hour. Current position is 4.5 BTC. This dip aligns with the entry criteria in the objective.",
  "proposed_action": {
    "tool": "nautilus_submit_order",
    "params": {
      "instrument_id": "BTCUSDT-PERP.BINANCE",
      "side": "BUY",
      "order_type": "LIMIT",
      "quantity": "0.5",
      "price": "67112.50"
    }
  },
  "reasoning": "Placing a limit order 0.5% below current mid price to catch the dip. 0.5 BTC is within the per-entry constraint.",
  "risk_assessment": "Position would be 5.0/10.0 BTC. Within all guardrails.",
  "awaiting_approval": true
}
```

## Event Processing

### EventProcessor

```python
class EventProcessor:
    """Manages WebSocket connection and event batching."""

    def __init__(self, config: AgentConfig):
        self._ws: WebSocket | None = None
        self._event_queue: asyncio.Queue = asyncio.Queue()
        self._batch_interval = config.event_batch_interval_ms / 1000
        self._batch_max_size = config.event_batch_max_size
        self._context_window: deque = deque(maxlen=config.max_context_events)

    async def connect(self, url: str, topics: list[str]) -> None:
        """Connect to event stream and subscribe to topics."""

    async def get_batch(self) -> list[dict]:
        """Collect events into a batch (time-bounded or size-bounded)."""

    def get_context_window(self) -> list[dict]:
        """Return the current sliding window of recent events."""
```

### Event Priority

Events are processed in priority order when multiple arrive simultaneously:

| Priority | Event Types                                         |
|----------|-----------------------------------------------------|
| 1 (high) | OrderRejected, TradingStateChanged (to HALTED)      |
| 2        | OrderFilled, PositionOpened, PositionClosed          |
| 3        | PositionChanged, OrderAccepted, OrderCanceled        |
| 4        | AccountState, ComponentStateChanged                  |
| 5 (low)  | Market data events, TimeEvent                        |

### Context Window Management

To control Claude API token usage:

1. **Recent events** (last N): Included verbatim in context
2. **Older events**: Periodically summarized by Claude into compressed state updates
3. **State snapshots**: Current portfolio/position state queried fresh each cycle (not derived from events)

## Reasoning Engine

### System Prompt Structure

```
You are an AI trading agent managing a NautilusTrader system.

## Current State
- Environment: {SANDBOX|LIVE}
- Mode: {MONITOR|ADVISORY|SEMI_AUTONOMOUS|AUTONOMOUS}
- Portfolio: {current balances, positions, P&L}
- Active Strategies: {list with states}

## Your Objectives (in priority order)
1. {objective description + constraints + progress}
2. ...

## Safety Guardrails
- Max position sizes: {...}
- Daily loss limit: $X (used: $Y, remaining: $Z)
- Max order size: ...
- Allowed instruments: ...

## Recent Events
{event batch}

## Recent Decisions
{last N decisions with outcomes}

## Available Tools
{MCP tool schemas}

## Instructions
- Analyze the events in the context of your objectives
- Decide on actions (or no action) and explain your reasoning
- Use tools to query additional state if needed before acting
- Never exceed guardrail limits (they are enforced, but avoid even attempting)
- In {mode}, you {can/cannot} {action permissions}
```

### Tool Dispatch

The reasoning engine makes Claude API calls with tool definitions matching the MCP tools (SPEC-003). When Claude returns tool calls:

1. Tool call is intercepted by the safety layer
2. Guardrails are checked
3. Mode permissions are verified
4. If allowed, the tool call is executed via the NautilusTrader API
5. Result is fed back to Claude for multi-turn reasoning if needed

## Safety Layer

### Pre-Action Validation Pipeline

```
Proposed Action
  │
  ├─ 1. Mode Permission Check
  │     └─ Is this action allowed in current mode?
  │        ├─ No → BLOCKED (log reason)
  │        └─ Yes → continue
  │
  ├─ 2. Instrument Check
  │     └─ Is instrument in allowlist and not in blocklist?
  │        ├─ No → BLOCKED
  │        └─ Yes → continue
  │
  ├─ 3. Position Size Check
  │     └─ Would resulting position exceed max_position_size?
  │        ├─ Yes → BLOCKED
  │        └─ No → continue
  │
  ├─ 4. Order Size Check
  │     └─ Is order quantity within max_single_order_size?
  │        ├─ No → BLOCKED
  │        └─ Yes → continue
  │
  ├─ 5. Portfolio Exposure Check
  │     └─ Would total exposure exceed max_portfolio_exposure?
  │        ├─ Yes → BLOCKED
  │        └─ No → continue
  │
  ├─ 6. Daily Loss Check
  │     └─ Has daily loss limit been breached?
  │        ├─ Yes → KILL SWITCH
  │        └─ No → continue
  │
  ├─ 7. Rate Limit Check
  │     └─ Within max_orders_per_minute?
  │        ├─ No → DELAYED (retry after cooldown)
  │        └─ Yes → continue
  │
  ├─ 8. Human Approval Check
  │     └─ Is notional above human_approval_threshold?
  │        ├─ Yes → ESCALATE (queue for approval)
  │        └─ No → continue
  │
  └─ 9. Stop Loss Check
        └─ Does position have stop loss (if required)?
           ├─ No → BLOCKED (must submit stop with position)
           └─ Yes → EXECUTE
```

### Kill Switch

When triggered, the kill switch:

```python
async def activate_kill_switch(self, reason: str) -> None:
    """Halt all agent trading activity immediately."""
    self._killed = True
    self._mode = AgentMode.MONITOR  # Downgrade to read-only

    # Optionally cancel all open orders
    if self._config.guardrails.kill_switch_cancel_orders:
        await self._api_client.post("/api/v1/orders/cancel-all")

    # Alert operator
    await self._alert(
        level="CRITICAL",
        message=f"Kill switch activated: {reason}",
    )

    # Log
    self._log.critical(f"KILL SWITCH: {reason}")
```

Kill switch requires manual reset: `agent.reset_kill_switch()` (programmatic) or restart.

## State Management

### AgentState

```python
@dataclass
class AgentState:
    objectives: list[ObjectiveState]       # Objective progress tracking
    decisions: deque[Decision]             # Recent decision history (bounded)
    daily_pnl: Decimal                     # Tracked daily P&L for loss limits
    daily_orders_submitted: int            # Daily order count
    orders_this_minute: deque[float]       # Timestamps for rate limiting
    kill_switch_active: bool               # Kill switch state
    kill_switch_reason: str | None         # Why kill switch was activated
    last_portfolio_snapshot: dict           # Last known portfolio state
    context_summary: str                   # Compressed summary of older events
    started_at: str                        # Agent start timestamp
    total_decisions: int                   # Total decisions made
    total_actions_executed: int            # Total actions executed
    total_actions_blocked: int             # Total actions blocked by guardrails
```

### Persistence

State is saved to JSON periodically and on shutdown:

```python
async def save_state(self) -> None:
    """Persist current state to disk."""
    state_dict = self._state.to_dict()
    async with aiofiles.open(self._config.state_persistence_path, 'w') as f:
        await f.write(json.dumps(state_dict, indent=2))
```

On restart, the agent loads persisted state and resumes from where it left off. Objectives maintain their progress, and the daily P&L counter is preserved (reset at UTC midnight).

## Decision Audit Trail

Every decision is appended to a JSONL file:

```json
{
  "decision_id": "d-20260321-042",
  "timestamp": "2026-03-21T14:23:17.456Z",
  "mode": "SEMI_AUTONOMOUS",
  "cycle_number": 42,
  "trigger": {
    "type": "event_batch",
    "events": [
      {"type": "PositionChanged", "instrument": "BTCUSDT-PERP.BINANCE", "quantity": "4.5"}
    ],
    "objective_id": "obj-001"
  },
  "context_summary": {
    "portfolio_value_usd": "105230.00",
    "open_positions": 2,
    "daily_pnl_usd": "+1230.00",
    "active_objectives": 3
  },
  "reasoning": "Position increased to 4.5 BTC after last fill. Target is 10 BTC. Current price $67,450 is 1.2% below 24h VWAP. Objective prefers buying on dips. Placing next entry.",
  "actions": [
    {
      "tool": "nautilus_submit_order",
      "params": {"instrument_id": "BTCUSDT-PERP.BINANCE", "side": "BUY", "type": "LIMIT", "quantity": "0.5", "price": "67112.50"},
      "guardrail_result": {"passed": true, "checks_run": 9, "checks_passed": 9},
      "execution_result": {"status": "executed", "order_id": "O-20260321-043"},
      "latency_ms": 1247
    }
  ],
  "tokens_used": {"input": 2847, "output": 523},
  "total_latency_ms": 1834
}
```

## Observability

### Metrics

The agent exposes metrics for monitoring:

| Metric                         | Type    | Description                              |
|--------------------------------|---------|------------------------------------------|
| `agent.decisions.total`        | Counter | Total decision cycles executed            |
| `agent.actions.executed`       | Counter | Actions successfully executed             |
| `agent.actions.blocked`        | Counter | Actions blocked by guardrails             |
| `agent.actions.escalated`      | Counter | Actions escalated for human approval      |
| `agent.latency.decision_ms`   | Gauge   | Last decision cycle latency               |
| `agent.tokens.used`           | Counter | Total Claude API tokens consumed          |
| `agent.daily_pnl_usd`        | Gauge   | Current daily P&L                         |
| `agent.kill_switch.active`    | Gauge   | Kill switch state (0/1)                   |
| `agent.objectives.active`     | Gauge   | Number of active objectives               |
| `agent.events.processed`      | Counter | Total events processed                    |
| `agent.events.queue_depth`    | Gauge   | Current event queue depth                 |

### Alerts

Configurable alerts via webhook or stdout:

| Condition                      | Level    | Action                                  |
|--------------------------------|----------|-----------------------------------------|
| Kill switch activated          | CRITICAL | Webhook + stdout                        |
| Daily loss > 80% of limit     | WARNING  | Webhook                                 |
| Guardrail blocked action       | INFO     | Stdout (decision log)                   |
| WebSocket disconnected         | WARNING  | Auto-reconnect + webhook if > 60s       |
| Claude API error               | ERROR    | Retry with backoff, webhook if persistent|
| Objective completed            | INFO     | Webhook                                 |

## Example: Full Agent Session

```python
from nautilus_trader.agent.config import AgentConfig, GuardrailConfig, ObjectiveConfig
from nautilus_trader.agent.orchestrator import AgentOrchestrator

config = AgentConfig(
    mode="SEMI_AUTONOMOUS",
    model="claude-sonnet-4-20250514",
    api_url="http://localhost:8001",
    objectives=[
        ObjectiveConfig(
            objective_type="POSITION",
            description="Build a 10 BTC long position over 24 hours. "
                       "Scale in on 1%+ dips. Max 0.5 BTC per entry. "
                       "Use limit orders 0.3-0.5% below mid.",
            instrument_id="BTCUSDT-PERP.BINANCE",
            priority=1,
            constraints={
                "max_entry_size": "0.5",
                "time_horizon_hours": 24,
                "entry_strategy": "buy_dips",
                "dip_threshold_pct": 1.0,
            },
        ),
        ObjectiveConfig(
            objective_type="MONITORING",
            description="Alert if unrealized loss on any single position exceeds $2000",
            priority=1,
        ),
    ],
    guardrails=GuardrailConfig(
        max_position_size={"BTCUSDT-PERP.BINANCE": "10.0"},
        max_daily_loss_usd="5000",
        max_orders_per_minute=5,
        max_single_order_size="0.5",
        instrument_allowlist=["BTCUSDT-PERP.BINANCE"],
    ),
    event_topics=[
        "events.order.*",
        "events.position.*",
        "data.bars.BTCUSDT-PERP.BINANCE.*",
    ],
    event_batch_interval_ms=2000,
)

agent = AgentOrchestrator(config)
await agent.start()  # Connects, queries state, begins processing
# ... agent runs autonomously ...
await agent.stop()   # Graceful shutdown, state persisted
```

## Dependencies

| Package     | Version  | Purpose                           |
|-------------|----------|-----------------------------------|
| `anthropic` | >=0.40   | Claude API client                 |
| `httpx`     | >=0.27   | Async HTTP client for API calls   |
| `websockets`| >=12.0   | WebSocket client for event stream |
| `aiofiles`  | >=24.1   | Async file I/O for state/audit    |
