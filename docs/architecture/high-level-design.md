# NautilusTrader AI Control Plane -- High-Level Design

## 1. Executive Summary

NautilusTrader is a high-performance algorithmic trading platform built on a hybrid
Python/Cython/Rust architecture. It provides institutional-grade backtesting and live
trading with sub-microsecond internal latency on the critical path.

This design introduces a complete external **control plane** that enables AI agents
(primarily Claude, via Anthropic's API) to monitor, analyze, and control the trading
system through natural language and structured tool interfaces. The control plane is
composed of five new components layered non-invasively on top of the existing
architecture:

| # | Component | Purpose |
|---|-----------|---------|
| 1 | **API Server** | REST + WebSocket gateway into the running kernel |
| 2 | **Event Streaming** | Real-time event delivery to external consumers |
| 3 | **MCP Server** | Model Context Protocol interface for AI tool use |
| 4 | **CLI** | Human-friendly command-line interface over the API |
| 5 | **Agent Orchestration** | Event-driven AI agent loop with safety guardrails |

Design goals:

- **Zero impact on the critical path.** No changes to Cython/Rust hot paths.
- **In-process integration.** The API server shares the TradingNode's asyncio event
  loop -- no IPC overhead for queries.
- **Additive only.** All five components are optional; existing deployments are
  unaffected.
- **Safety first.** Graduated autonomy levels with hard guardrails for live trading.

---

## 2. Current Architecture

NautilusTrader is organized around a central kernel that wires together specialized
engines, a message bus, and user-defined strategies.

### Key Components

| Component | Role |
|-----------|------|
| `NautilusKernel` | Central orchestrator. Instantiates and wires all subsystems. Owns the asyncio event loop, clock, logger, and component registry. Defined in `nautilus_trader/system/kernel.py`. |
| `TradingNode` | Live trading entry point. Wraps `NautilusKernel`, builds data/exec clients via `TradingNodeBuilder`, and runs engine queue tasks on the event loop. Defined in `nautilus_trader/live/node.py`. |
| `MessageBus` | Internal pub/sub with wildcard topic matching. Supports endpoint registration (point-to-point commands) and topic subscription (broadcast events). Optional Redis backing for external streaming. Cython implementation in `nautilus_trader/common/component.pyx`. |
| `Controller` | Runtime strategy/actor management. Extends `Actor`, registers `Controller.execute` on the MessageBus, and dispatches `CreateStrategy`, `RemoveStrategy`, `StartStrategy`, `StopStrategy` (and actor equivalents) commands to the `Trader`. Defined in `nautilus_trader/trading/controller.py`. |
| `Cache` / `CacheFacade` | In-memory store of instruments, orders, positions, accounts. `CacheFacade` provides a read-only view. |
| `Portfolio` / `PortfolioFacade` | Tracks balances, margins, unrealized P&L, and net exposures. `PortfolioFacade` provides a read-only view. |
| `DataEngine` | Processes market data requests and responses. Manages data client lifecycle. Live variant runs async queue tasks. |
| `ExecutionEngine` | Processes execution commands and events. Manages execution client lifecycle. Handles reconciliation in live mode. |
| `RiskEngine` | Pre-trade risk checks. Validates orders against configurable limits before they reach the execution engine. |
| `Trader` | Container for strategies, actors, and execution algorithms. Provides lifecycle management (start/stop/dispose). |
| Strategies / Actors | User-defined trading logic (`Strategy`) and auxiliary logic (`Actor`). Communicate via the `MessageBus`. |

### Configuration

All configuration uses frozen `msgspec.Struct` classes that are fully
JSON-serializable. The hierarchy is:

```
NautilusConfig (base)
  -> NautilusKernelConfig (kernel-level settings, engines, actors, strategies)
       -> TradingNodeConfig (adds live-specific engine configs, data/exec clients)
```

### Current Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         TradingNode                                     │
│                    (asyncio event loop)                                  │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                      NautilusKernel                               │  │
│  │                                                                   │  │
│  │  ┌────────────┐   ┌──────────────────────────────────────────┐   │  │
│  │  │            │   │            MessageBus                    │   │  │
│  │  │ Controller │──>│  - endpoint registration (point-to-point)│   │  │
│  │  │            │   │  - topic subscription (pub/sub)          │   │  │
│  │  └────────────┘   │  - optional Redis external streaming     │   │  │
│  │                    └──────────┬───────────────────────────────┘   │  │
│  │                               │ publish / subscribe              │  │
│  │        ┌──────────────────────┼──────────────────────┐           │  │
│  │        │                      │                      │           │  │
│  │  ┌─────┴──────┐  ┌───────────┴────────┐  ┌──────────┴───────┐  │  │
│  │  │ DataEngine │  │  ExecutionEngine    │  │   RiskEngine     │  │  │
│  │  │            │  │                    │  │                  │  │  │
│  │  │ cmd queue  │  │  cmd queue         │  │  cmd queue      │  │  │
│  │  │ req queue  │  │  evt queue         │  │  evt queue      │  │  │
│  │  │ res queue  │  │                    │  │                  │  │  │
│  │  │ data queue │  │  reconciliation    │  │  pre-trade       │  │  │
│  │  └─────┬──────┘  └───────────┬────────┘  │  risk checks    │  │  │
│  │        │                      │           └──────────┬───────┘  │  │
│  │        │                      │                      │          │  │
│  │  ┌─────┴──────────────────────┴──────────────────────┴───────┐  │  │
│  │  │                        Trader                              │  │  │
│  │  │  ┌────────────┐  ┌────────────┐  ┌─────────────────────┐  │  │  │
│  │  │  │ Strategy A │  │ Strategy B │  │  ExecAlgorithm      │  │  │  │
│  │  │  └────────────┘  └────────────┘  └─────────────────────┘  │  │  │
│  │  │  ┌────────────┐  ┌────────────┐                           │  │  │
│  │  │  │  Actor A   │  │  Actor B   │                           │  │  │
│  │  │  └────────────┘  └────────────┘                           │  │  │
│  │  └────────────────────────────────────────────────────────────┘  │  │
│  │                                                                   │  │
│  │  ┌──────────┐  ┌──────────────┐  ┌────────────────────────────┐  │  │
│  │  │  Cache   │  │  Portfolio   │  │  Clock / Logger / Guards   │  │  │
│  │  │  Facade  │  │  Facade      │  │                            │  │  │
│  │  └──────────┘  └──────────────┘  └────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                    Data / Exec Clients                             │  │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │  │
│  │  │ Binance Data    │  │ Binance Exec    │  │  Other Venues   │  │  │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Target Architecture

The target architecture adds five components above the existing kernel. Critically,
the API Server runs **in-process** on the TradingNode's asyncio event loop, giving it
zero-copy access to `Cache`, `Portfolio`, and `Controller` without serialization
overhead.

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        AI Control Plane                                   │
│                                                                          │
│  ┌───────────────┐   ┌──────────────┐   ┌────────────────────────────┐  │
│  │ Claude Agent   │   │     CLI      │   │   Other AI Agents          │  │
│  │ Orchestrator   │   │  (Click)     │   │   (future)                 │  │
│  │                │   │              │   │                            │  │
│  │ - objectives   │   │ - table/json │   │                            │  │
│  │ - guardrails   │   │ - shell comp │   │                            │  │
│  │ - audit trail  │   │ - config     │   │                            │  │
│  └───────┬───────┘   └──────┬───────┘   └────────────┬───────────────┘  │
│          │                   │                         │                  │
│  ┌───────┴───────────────────┴─────────────────────────┴───────────────┐ │
│  │                        MCP Server                                   │ │
│  │             (Tool Discovery + Safety Guardrails)                    │ │
│  │                                                                     │ │
│  │  Tools:  node.*  strategy.*  order.*  portfolio.*  risk.*  data.*  │ │
│  │  Resources:  status  portfolio-snapshot  event-cursor               │ │
│  │  Safety:  UNRESTRICTED | STANDARD | STRICT                         │ │
│  └───────────────────────────┬─────────────────────────────────────────┘ │
│                               │ HTTP / WebSocket                         │
│  ┌───────────────────────────┴─────────────────────────────────────────┐ │
│  │                     API Server (FastAPI)                             │ │
│  │                                                                     │ │
│  │  REST Endpoints                │  WebSocket Event Stream            │ │
│  │  ─────────────                 │  ──────────────────────            │ │
│  │  GET  /api/v1/node/status      │  WS /api/v1/events                │ │
│  │  GET  /api/v1/strategies       │    - topic-based filtering        │ │
│  │  POST /api/v1/strategies       │    - per-client bounded queues    │ │
│  │  GET  /api/v1/orders           │    - reconnection replay          │ │
│  │  POST /api/v1/orders           │                                   │ │
│  │  GET  /api/v1/portfolio        │  EventStreamBridge (Actor)        │ │
│  │  GET  /api/v1/positions        │    - subscribes to MessageBus     │ │
│  │  ...                           │    - serializes to JSON           │ │
│  └───────────────────────────┬─────────────────────────────────────────┘ │
└──────────────────────────────┼───────────────────────────────────────────┘
                               │ in-process (shared asyncio event loop)
┌──────────────────────────────┼───────────────────────────────────────────┐
│                    NautilusKernel (existing, unchanged)                   │
│                                                                          │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌───────────────────┐  │
│  │ Controller │  │ MessageBus │  │   Cache    │  │    Portfolio      │  │
│  ├────────────┤  ├────────────┤  ├────────────┤  ├───────────────────┤  │
│  │ DataEngine │  │ ExecEngine │  │ RiskEngine │  │  Trader/Strats   │  │
│  └────────────┘  └────────────┘  └────────────┘  └───────────────────┘  │
└──────────────────────────────────────────────────────────────────────────┘
```

### Key Design Decisions

1. **In-process API server.** FastAPI runs as an ASGI app on the TradingNode's
   existing asyncio event loop via `uvicorn`. This avoids IPC and serialization for
   queries -- the API handler directly calls `cache.orders()` or
   `portfolio.balances()`.

2. **EventStreamBridge as an Actor.** The bridge is registered as a standard
   `Actor` via the `Controller`, giving it full access to `MessageBus.subscribe()`.
   This means no changes to `MessageBus` internals.

3. **MCP as a translation layer.** The MCP server translates between Claude's
   tool-calling protocol and the REST/WebSocket API. It adds safety guardrails but
   contains no business logic.

4. **Additive configuration.** A single optional field on `TradingNodeConfig`
   enables the entire control plane. Existing configs and deployments are unaffected.

---

## 4. Component Design

### 4.1 API Server (SPEC-001)

**Purpose:** Expose the running NautilusKernel to external consumers via HTTP.

**Integration point:** The API server is started inside `TradingNode.run_async()`
as an additional task alongside the engine queue tasks. It shares the same asyncio
event loop.

**Endpoints (representative, not exhaustive):**

| Method | Path | Backend |
|--------|------|---------|
| `GET` | `/api/v1/node/status` | `NautilusKernel` state |
| `GET` | `/api/v1/node/config` | `NautilusKernelConfig` (redacted) |
| `GET` | `/api/v1/strategies` | `Cache.strategies()` |
| `POST` | `/api/v1/strategies` | `Controller` -> `CreateStrategy` |
| `DELETE` | `/api/v1/strategies/{id}` | `Controller` -> `RemoveStrategy` |
| `POST` | `/api/v1/strategies/{id}/start` | `Controller` -> `StartStrategy` |
| `POST` | `/api/v1/strategies/{id}/stop` | `Controller` -> `StopStrategy` |
| `GET` | `/api/v1/orders` | `Cache.orders()` |
| `POST` | `/api/v1/orders` | `ExecEngine` submit |
| `DELETE` | `/api/v1/orders/{id}` | `ExecEngine` cancel |
| `GET` | `/api/v1/positions` | `Cache.positions()` |
| `GET` | `/api/v1/portfolio/balances` | `PortfolioFacade.balances()` |
| `GET` | `/api/v1/portfolio/unrealized-pnls` | `PortfolioFacade.unrealized_pnls()` |
| `GET` | `/api/v1/instruments` | `Cache.instruments()` |
| `GET` | `/api/v1/actors` | `Cache.actors()` |
| `POST` | `/api/v1/actors` | `Controller` -> `CreateActor` |
| `GET` | `/api/v1/risk` | `RiskEngine` state |
| `WS` | `/api/v1/events` | `EventStreamBridge` |

**Authentication:** API key passed via `X-Nautilus-Api-Key` header. Configured
in `ApiServerConfig.api_key`. All endpoints require authentication except
`GET /api/v1/node/status` (health check).

**OpenAPI:** Auto-generated by FastAPI. Available at `/api/v1/docs` (Swagger UI)
and `/api/v1/openapi.json`.

**Configuration:**

```python
class ApiServerConfig(NautilusConfig, frozen=True):
    host: str = "127.0.0.1"
    port: int = 8001
    api_key: str | None = None       # None = no auth (dev only)
    cors_origins: list[str] = []
    ssl_certfile: str | None = None
    ssl_keyfile: str | None = None
    rate_limit_mutations: int = 60   # per minute
    max_ws_clients: int = 10
```

### 4.2 Event Streaming (SPEC-002)

**Purpose:** Deliver real-time domain events to external consumers via WebSocket.

**Core component -- EventStreamBridge:**

The `EventStreamBridge` is an `Actor` that subscribes to configurable MessageBus
topics and forwards serialized events to connected WebSocket clients.

```
MessageBus                EventStreamBridge              WebSocket Clients
    │                          (Actor)                        │
    │  publish(topic, event)     │                            │
    ├─────────────────────────> │                            │
    │                           │  serialize to JSON          │
    │                           │  write to ring buffer       │
    │                           │  fan out to client queues   │
    │                           ├───────────────────────────> │
    │                           │                     client 1│
    │                           ├───────────────────────────> │
    │                           │                     client 2│
```

**Subscription protocol:** Clients send a JSON subscription message after
connecting:

```json
{
    "type": "subscribe",
    "topics": ["data.quotes.*", "events.order.*", "events.position.*"],
    "replay_from": 1234567890
}
```

**Backpressure:** Each client has a bounded `asyncio.Queue`. If a client falls
behind and the queue fills, the oldest events are dropped and the client receives
a `gap` notification with the sequence range it missed.

**Ring buffer:** The bridge maintains a fixed-size ring buffer (default 10,000
events) to support reconnection replay. Clients can request replay from a
sequence number.

**Configuration:**

```python
class EventStreamConfig(NautilusConfig, frozen=True):
    topics: list[str] = ["events.*"]       # MessageBus topic patterns
    client_queue_size: int = 1_000
    ring_buffer_size: int = 10_000
    max_clients: int = 10
```

### 4.3 MCP Server (SPEC-003)

**Purpose:** Expose NautilusTrader operations as MCP (Model Context Protocol)
tools that Claude and other AI agents can discover and invoke.

**Deployment:** The MCP server can run as either:
- **Embedded mode:** Mounted as an additional route set on the API server.
- **Standalone mode:** Separate process connecting to the API server via HTTP.

Standalone mode is recommended for production to isolate the AI interface from the
trading process.

**Tool categories:**

| Category | Tools | Examples |
|----------|-------|---------|
| `node` | Node lifecycle and status | `node.status`, `node.config`, `node.shutdown` |
| `strategy` | Strategy CRUD and lifecycle | `strategy.list`, `strategy.create`, `strategy.start`, `strategy.stop`, `strategy.remove` |
| `order` | Order management | `order.list`, `order.submit`, `order.cancel`, `order.cancel_all` |
| `portfolio` | Portfolio queries | `portfolio.balances`, `portfolio.positions`, `portfolio.unrealized_pnls`, `portfolio.net_exposures` |
| `data` | Market data queries | `data.instruments`, `data.quotes`, `data.bars`, `data.subscribe` |
| `risk` | Risk state and controls | `risk.state`, `risk.set_max_order_rate`, `risk.set_max_notional` |

**MCP Resources:**

| URI | Description |
|-----|-------------|
| `nautilus://status` | Current node status and uptime |
| `nautilus://portfolio` | Portfolio snapshot (balances, positions, P&L) |
| `nautilus://events?cursor={seq}` | Event stream cursor for polling |

**Safety levels:**

| Level | Behavior |
|-------|----------|
| `UNRESTRICTED` | All tools available. No confirmation prompts. For backtesting/sandbox. |
| `STANDARD` | Mutation tools require confirmation. Read tools unrestricted. Default for sandbox. |
| `STRICT` | All mutation tools blocked. Read-only access. Default for live. Auto-selected when `environment == LIVE`. |

**Configuration:**

```python
class McpServerConfig(NautilusConfig, frozen=True):
    transport: str = "stdio"                # "stdio" | "http"
    api_base_url: str = "http://127.0.0.1:8001"
    api_key: str | None = None
    safety_level: str = "STANDARD"          # "UNRESTRICTED" | "STANDARD" | "STRICT"
    auto_strict_on_live: bool = True
```

### 4.4 CLI (SPEC-004)

**Purpose:** Human-friendly command-line interface for interacting with a running
NautilusTrader node. Wraps the REST API.

**Implementation:** Click-based CLI with command groups mirroring the API
structure.

**Command groups:**

```
nautilus-ctl node status
nautilus-ctl node config
nautilus-ctl node shutdown

nautilus-ctl strategy list [--format table|json|csv]
nautilus-ctl strategy create <config-file>
nautilus-ctl strategy start <strategy-id>
nautilus-ctl strategy stop <strategy-id>
nautilus-ctl strategy remove <strategy-id>

nautilus-ctl order list [--status open|closed|all] [--strategy <id>]
nautilus-ctl order submit <order-json>
nautilus-ctl order cancel <client-order-id>
nautilus-ctl order cancel-all [--strategy <id>]

nautilus-ctl portfolio balances [--venue <venue>]
nautilus-ctl portfolio positions [--instrument <id>]
nautilus-ctl portfolio pnl

nautilus-ctl risk state
nautilus-ctl risk set-max-order-rate <rate>

nautilus-ctl data instruments [--venue <venue>]
nautilus-ctl data quotes <instrument-id>

nautilus-ctl events stream [--topics "events.order.*,events.position.*"]
```

**Output formats:** `--format` flag on all query commands supports `table`
(default, using `rich`), `json`, and `csv`.

**Connection configuration:** Stored in `~/.nautilus-ctl.toml`:

```toml
[default]
host = "127.0.0.1"
port = 8001
api_key = "..."
```

**Shell completions:** Generated via Click's built-in completion support for
bash, zsh, and fish.

### 4.5 Agent Orchestration (SPEC-005)

**Purpose:** Event-driven AI agent loop that uses Claude to reason about trading
system state and take actions through the MCP tool interface.

**Architecture:**

```
┌───────────────────────────────────────────────────────────────┐
│                    Agent Orchestrator                          │
│                                                               │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────────┐│
│  │  Event       │  │  Reasoning   │  │  Action Executor     ││
│  │  Collector   │  │  Engine      │  │                      ││
│  │              │  │  (Claude)    │  │  - MCP tool calls    ││
│  │  - WS client │  │              │  │  - confirmation gate ││
│  │  - batching  │  │  - context   │  │  - audit logging     ││
│  │  - filtering │  │  - objectives│  │                      ││
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘│
│         │                  │                     │            │
│  ┌──────┴──────────────────┴─────────────────────┴──────────┐│
│  │                    State Manager                          ││
│  │                                                           ││
│  │  - objective tracking        - decision audit trail       ││
│  │  - conversation history      - guardrail state            ││
│  │  - portfolio snapshots       - alert history              ││
│  └───────────────────────────────────────────────────────────┘│
└───────────────────────────────────────────────────────────────┘
```

**Operating modes:**

| Mode | Description | Human Involvement |
|------|-------------|-------------------|
| **Monitor** | Observe and report. No actions taken. | None needed. Agent produces alerts and summaries. |
| **Advisory** | Observe, analyze, and recommend. No actions taken. | Human reviews recommendations. |
| **Semi-autonomous** | Execute pre-approved action types. Escalate novel situations. | Human approves non-routine actions. |
| **Autonomous** | Full decision-making within guardrail bounds. | Human monitors via audit trail. Emergency kill switch. |

**Objective system:** The agent operates against a set of declared objectives:

```python
@dataclass
class Objective:
    id: str
    description: str                    # Natural language goal
    constraints: list[str]              # Hard constraints
    success_criteria: list[str]         # Measurable success conditions
    priority: int                       # 1 = highest
    status: ObjectiveStatus             # ACTIVE | PAUSED | COMPLETED | FAILED
```

Example objective:
```python
Objective(
    id="obj-001",
    description="Maintain delta-neutral portfolio across all BTC instruments",
    constraints=["Max absolute delta: 0.5 BTC", "Max single order size: 0.1 BTC"],
    success_criteria=["Portfolio delta within +/- 0.1 BTC for 95% of time"],
    priority=1,
    status=ObjectiveStatus.ACTIVE,
)
```

**Safety guardrails:**

| Guardrail | Description |
|-----------|-------------|
| Position limits | Max position size per instrument and aggregate |
| Loss limits | Max drawdown per session, per day, cumulative |
| Rate limits | Max actions per minute / per hour |
| Instrument allowlist | Only trade explicitly approved instruments |
| Kill switch | Immediate halt: cancel all orders, flatten positions |
| Environment lock | Agent cannot escalate from SANDBOX to LIVE |
| Action budget | Max total actions per session before forced pause |

**Agent loop (simplified):**

```
loop:
    events = collect_events(timeout=5s)
    context = build_context(events, state, objectives)
    response = claude.messages.create(
        model="...",
        system=system_prompt,
        messages=context,
        tools=mcp_tools,
    )
    for tool_call in response.tool_calls:
        if guardrails.check(tool_call):
            result = mcp.call_tool(tool_call)
            audit_log.record(tool_call, result)
        else:
            audit_log.record(tool_call, BLOCKED, reason)
    update_state(response, results)
```

---

## 5. Data Flow Diagrams

### 5.1 Command Flow (Agent -> NautilusTrader)

An AI agent instructs the system to start a strategy:

```
Claude Agent                MCP Server              API Server           NautilusKernel
    │                           │                       │                       │
    │  tool_call:               │                       │                       │
    │  strategy.start(          │                       │                       │
    │    id="MyStrat-001")      │                       │                       │
    ├──────────────────────────>│                       │                       │
    │                           │  POST /api/v1/        │                       │
    │                           │  strategies/          │                       │
    │                           │  MyStrat-001/start    │                       │
    │                           ├─────────────────────>│                       │
    │                           │                       │  controller.execute(  │
    │                           │                       │    StartStrategy(     │
    │                           │                       │      id=MyStrat-001)) │
    │                           │                       ├─────────────────────>│
    │                           │                       │                       │
    │                           │                       │  MessageBus           │
    │                           │                       │  .send(               │
    │                           │                       │    "Controller        │
    │                           │                       │     .execute",        │
    │                           │                       │    StartStrategy)     │
    │                           │                       │       │               │
    │                           │                       │       v               │
    │                           │                       │  Controller           │
    │                           │                       │  .start_strategy()    │
    │                           │                       │       │               │
    │                           │                       │       v               │
    │                           │                       │  Trader               │
    │                           │                       │  .start_strategy()    │
    │                           │                       │       │               │
    │                           │                       │       v               │
    │                           │                       │  Strategy.start()     │
    │                           │                       │                       │
    │                           │      200 OK           │                       │
    │                           │<─────────────────────│                       │
    │  tool_result: success     │                       │                       │
    │<──────────────────────────│                       │                       │
```

### 5.2 Event Flow (NautilusTrader -> Agent)

A strategy fills an order and the event reaches the agent:

```
Strategy          MessageBus        EventStreamBridge      WebSocket       Agent
    │                  │                    │                   │              │
    │  OrderFilled     │                    │                   │              │
    │  event emitted   │                    │                   │              │
    ├─────────────────>│                    │                   │              │
    │                  │  publish(          │                   │              │
    │                  │  "events.order.    │                   │              │
    │                  │   OrderFilled",    │                   │              │
    │                  │   event)           │                   │              │
    │                  ├───────────────────>│                   │              │
    │                  │                    │  serialize(event) │              │
    │                  │                    │  -> JSON          │              │
    │                  │                    │                   │              │
    │                  │                    │  write to ring    │              │
    │                  │                    │  buffer [seq=N]   │              │
    │                  │                    │                   │              │
    │                  │                    │  enqueue to all   │              │
    │                  │                    │  matching clients │              │
    │                  │                    ├──────────────────>│              │
    │                  │                    │                   │  WS frame    │
    │                  │                    │                   ├─────────────>│
    │                  │                    │                   │              │
    │                  │                    │                   │  {           │
    │                  │                    │                   │   "seq": N,  │
    │                  │                    │                   │   "topic":   │
    │                  │                    │                   │    "events.  │
    │                  │                    │                   │     order.   │
    │                  │                    │                   │     Filled", │
    │                  │                    │                   │   "event":   │
    │                  │                    │                   │    { ... }   │
    │                  │                    │                   │  }           │
```

### 5.3 Query Flow (Agent -> NautilusTrader -> Agent)

The agent queries portfolio balances:

```
Claude Agent           MCP Server            API Server           NautilusKernel
    │                       │                     │                      │
    │  tool_call:           │                     │                      │
    │  portfolio.balances() │                     │                      │
    ├──────────────────────>│                     │                      │
    │                       │  GET /api/v1/       │                      │
    │                       │  portfolio/balances │                      │
    │                       ├────────────────────>│                      │
    │                       │                     │                      │
    │                       │                     │  portfolio_facade    │
    │                       │                     │  .balances()         │
    │                       │                     │  (in-process, no     │
    │                       │                     │   serialization)     │
    │                       │                     ├─────────────────────>│
    │                       │                     │                      │
    │                       │                     │<─────────────────────│
    │                       │                     │  dict[Venue,         │
    │                       │                     │    Money]            │
    │                       │                     │                      │
    │                       │   200 OK            │                      │
    │                       │   { "BINANCE":      │                      │
    │                       │     { "total":       │                      │
    │                       │       "10432.50      │                      │
    │                       │        USDT" } }    │                      │
    │                       │<────────────────────│                      │
    │                       │                     │                      │
    │  tool_result:         │                     │                      │
    │  { balances... }      │                     │                      │
    │<──────────────────────│                     │                      │
```

---

## 6. Integration Points

### 6.1 NautilusKernel Integration

The API server integrates at the `TradingNode` level, not the `NautilusKernel`
level. This keeps the kernel unchanged.

**Startup sequence in `TradingNode.run_async()`:**

```python
async def run_async(self) -> None:
    # ... existing startup ...
    await self.kernel.start_async()

    tasks: list[asyncio.Task] = [
        self.kernel.data_engine.get_cmd_queue_task(),
        self.kernel.data_engine.get_req_queue_task(),
        self.kernel.data_engine.get_res_queue_task(),
        self.kernel.data_engine.get_data_queue_task(),
        self.kernel.risk_engine.get_cmd_queue_task(),
        self.kernel.risk_engine.get_evt_queue_task(),
        self.kernel.exec_engine.get_cmd_queue_task(),
        self.kernel.exec_engine.get_evt_queue_task(),
    ]

    # NEW: Start API server if configured
    if self._config.api_server:
        api_task = asyncio.create_task(
            self._start_api_server()
        )
        tasks.append(api_task)

    # ... existing external streaming setup ...
    await asyncio.gather(*tasks)
```

**EventStreamBridge registration:**

The `EventStreamBridge` is registered as an `Actor` during API server startup.
It uses standard `MessageBus.subscribe()` calls, requiring no changes to the
message bus.

```python
bridge = EventStreamBridge(config=event_stream_config)
self.kernel.trader.add_actor(bridge)
```

**No Cython/Rust changes required.** All integration uses existing Python-level
APIs: `CacheFacade`, `PortfolioFacade`, `Controller.execute()`,
`MessageBus.subscribe()`.

### 6.2 Configuration Integration

All new configuration nests into `TradingNodeConfig` via a single optional field:

```python
class TradingNodeConfig(NautilusKernelConfig, frozen=True):
    # ... existing fields ...
    environment: Environment = Environment.LIVE
    trader_id: TraderId = "TRADER-001"
    data_engine: LiveDataEngineConfig = LiveDataEngineConfig()
    risk_engine: LiveRiskEngineConfig = LiveRiskEngineConfig()
    exec_engine: LiveExecEngineConfig = LiveExecEngineConfig()
    data_clients: dict[str, LiveDataClientConfig] = {}
    exec_clients: dict[str, LiveExecClientConfig] = {}

    # NEW
    api_server: ApiServerConfig | None = None
```

When `api_server` is `None` (the default), the API server is not started and there
is zero overhead. This preserves full backward compatibility.

The `ApiServerConfig` contains the `EventStreamConfig` as a nested field:

```python
class ApiServerConfig(NautilusConfig, frozen=True):
    host: str = "127.0.0.1"
    port: int = 8001
    api_key: str | None = None
    event_stream: EventStreamConfig = EventStreamConfig()
    # ...
```

The MCP server and agent orchestrator are configured independently since they run
as separate processes.

### 6.3 MessageBus Integration

The control plane integrates with the MessageBus through two standard mechanisms:

**Subscribing to events (EventStreamBridge):**

```python
# Standard topic subscription -- no MessageBus changes needed
self.msgbus.subscribe(topic="events.order.*", handler=self._on_event)
self.msgbus.subscribe(topic="events.position.*", handler=self._on_event)
self.msgbus.subscribe(topic="data.quotes.*", handler=self._on_event)
```

**Sending commands (API Server -> Controller):**

```python
# Standard endpoint send -- no MessageBus changes needed
# Controller.register_base() already registers "Controller.execute"
self.msgbus.send(endpoint="Controller.execute", msg=StartStrategy(strategy_id))
```

The MessageBus's existing wildcard matching and endpoint registration are
sufficient for all control plane needs. No changes to `MessageBus` internals,
Cython code, or the Redis backing layer are required.

---

## 7. Security Model

### Authentication

| Layer | Mechanism |
|-------|-----------|
| API Server | API key in `X-Nautilus-Api-Key` header |
| MCP Server | Inherits API key for API calls; MCP transport auth is separate |
| CLI | API key from config file or `NAUTILUS_API_KEY` env var |
| Agent | API key configured in orchestrator settings |

API keys are configured via environment variables or the `ApiServerConfig`. They
are never logged or included in API responses.

### Authorization

The initial design uses a single API key (all-or-nothing access). Future versions
may add role-based access control:

| Role | Permissions |
|------|-------------|
| `reader` | All GET endpoints, event streaming |
| `trader` | Reader + order submission, strategy lifecycle |
| `admin` | Trader + node shutdown, configuration changes |

### Network Security

- **Bind address:** Default `127.0.0.1` (localhost only). Must be explicitly
  changed to `0.0.0.0` for remote access.
- **TLS:** Optional TLS via `ssl_certfile` / `ssl_keyfile` in `ApiServerConfig`.
  Required if binding to non-localhost.
- **CORS:** Configurable origin allowlist. Empty by default (no cross-origin
  requests).

### Rate Limiting

- Mutation endpoints (POST, DELETE): configurable limit, default 60/minute.
- Query endpoints (GET): no rate limit (in-process, negligible cost).
- WebSocket connections: max client limit (default 10).

### MCP Safety Enforcement

| Environment | Default Safety Level | Mutations | Confirmation |
|-------------|---------------------|-----------|-------------|
| `BACKTEST` | `UNRESTRICTED` | Allowed | None |
| `SANDBOX` | `STANDARD` | Allowed | Required for destructive actions |
| `LIVE` | `STRICT` | Blocked | N/A |

The `auto_strict_on_live` flag (default `True`) forces `STRICT` mode when
`environment == Environment.LIVE`, regardless of the configured safety level.
This can only be overridden by explicitly setting `auto_strict_on_live = False`.

### Agent Guardrails

Guardrails are enforced at the agent orchestration layer, independent of the
API/MCP safety levels:

```python
class AgentGuardrails(NautilusConfig, frozen=True):
    max_position_size: dict[str, float] = {}          # instrument -> max qty
    max_aggregate_exposure_usd: float = 100_000.0
    max_drawdown_pct: float = 5.0                     # per session
    max_daily_loss_usd: float = 10_000.0
    max_actions_per_minute: int = 10
    max_actions_per_session: int = 1_000
    allowed_instruments: list[str] | None = None       # None = all
    kill_switch_enabled: bool = True
```

---

## 8. Deployment Topology

### 8.1 Single-Process (Simplest)

Everything runs in one process. Suitable for development and sandbox testing.

```
┌──────────────────────────────────────────────┐
│              Single Process                   │
│                                              │
│  ┌────────────────────────────────────────┐  │
│  │          TradingNode                   │  │
│  │                                        │  │
│  │  NautilusKernel                        │  │
│  │    + API Server (FastAPI/uvicorn)      │  │
│  │    + EventStreamBridge (Actor)         │  │
│  │    + MCP Server (embedded, stdio)      │  │
│  └────────────────────────────────────────┘  │
│                                              │
│  ┌────────────────────────────────────────┐  │
│  │  Claude Agent (async task)             │  │
│  │    - connects via localhost WS/HTTP    │  │
│  └────────────────────────────────────────┘  │
└──────────────────────────────────────────────┘
```

**Pros:** Simplest deployment. No network configuration.
**Cons:** Agent crash could affect trading node. No process isolation.

### 8.2 Multi-Process (Recommended)

Trading node and agent in separate processes on the same machine.

```
┌───────────────────────────────┐   ┌───────────────────────────────┐
│         Process 1              │   │         Process 2              │
│                                │   │                                │
│  ┌──────────────────────────┐ │   │  ┌──────────────────────────┐ │
│  │      TradingNode         │ │   │  │     MCP Server           │ │
│  │                          │ │   │  │                          │ │
│  │  NautilusKernel          │ │   │  │  - tool definitions     │ │
│  │    + API Server          │ │   │  │  - safety guardrails    │ │
│  │    + EventStreamBridge   │ │   │  │  - API client           │ │
│  │                          │ │   │  └──────────┬───────────────┘ │
│  └──────────┬───────────────┘ │   │             │                  │
│             │ :8001            │   │  ┌──────────┴───────────────┐ │
└─────────────┼─────────────────┘   │  │     Claude Agent         │ │
              │  HTTP / WebSocket    │  │                          │ │
              │                      │  │  - event loop            │ │
              └──────────────────────│  │  - objectives            │ │
                                     │  │  - guardrails            │ │
                                     │  └──────────────────────────┘ │
                                     │                                │
                                     │  ┌──────────────────────────┐ │
                                     │  │     CLI (interactive)    │ │
                                     │  └──────────────────────────┘ │
                                     └────────────────────────────────┘
```

**Pros:** Process isolation. Agent crash does not affect trading.
**Cons:** Slightly more complex setup. Requires network configuration.

### 8.3 Distributed (Production)

Multiple trading nodes with centralized management.

```
┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐
│   TradingNode A      │  │   TradingNode B      │  │   TradingNode C      │
│   (Binance spot)     │  │   (Binance futures)   │  │   (dYdX)             │
│                      │  │                      │  │                      │
│   API :8001          │  │   API :8001          │  │   API :8001          │
└──────────┬───────────┘  └──────────┬───────────┘  └──────────┬───────────┘
           │                         │                          │
           └─────────────┬───────────┘──────────────────────────┘
                         │  HTTP / WebSocket
              ┌──────────┴──────────────────────────────┐
              │            API Gateway / Router           │
              │         (nginx or custom proxy)          │
              └──────────┬──────────────────────────────┘
                         │
              ┌──────────┴──────────────────────────────┐
              │          MCP Server                      │
              │   - routes tools to correct node         │
              │   - aggregates portfolio across nodes    │
              │   - unified event stream                 │
              └──────────┬──────────────────────────────┘
                         │
              ┌──────────┴──────────────────────────────┐
              │          Claude Agent                     │
              │   - manages all nodes via single MCP     │
              │   - cross-venue reasoning                │
              │   - aggregate risk management            │
              └─────────────────────────────────────────┘

              ┌─────────────────────────────────────────┐
              │          Redis                           │
              │   - MessageBus backing (cross-node)     │
              │   - shared state                        │
              └─────────────────────────────────────────┘
```

**Pros:** Multi-venue. Centralized risk. Single agent for all nodes.
**Cons:** Operational complexity. Requires Redis. Network latency for commands.

---

## 9. Implementation Roadmap

### Phase 1: Foundation (API Server + Event Streaming)

**Goal:** External consumers can query and control a running TradingNode.

| Task | Description | Estimated Effort |
|------|-------------|-----------------|
| 1.1 | Define `ApiServerConfig` and `EventStreamConfig` as `msgspec.Struct` | S |
| 1.2 | Add `api_server` field to `TradingNodeConfig` | S |
| 1.3 | Implement FastAPI app with health check endpoint | S |
| 1.4 | Implement uvicorn startup in `TradingNode.run_async()` | M |
| 1.5 | Implement query endpoints (strategies, orders, positions, portfolio) | M |
| 1.6 | Implement mutation endpoints (strategy CRUD, order submit/cancel) | M |
| 1.7 | Implement API key authentication middleware | S |
| 1.8 | Implement `EventStreamBridge` actor | L |
| 1.9 | Implement WebSocket endpoint with subscription protocol | L |
| 1.10 | Integration tests against `TradingNode` in sandbox mode | L |

**Deliverable:** A running TradingNode exposing REST + WebSocket on a
configurable port.

### Phase 2: External Interfaces (MCP Server + CLI)

**Goal:** Claude Code can discover and use all trading tools. Humans can use
the CLI.

| Task | Description | Estimated Effort |
|------|-------------|-----------------|
| 2.1 | Define MCP tool schemas for all API endpoints | M |
| 2.2 | Implement MCP server with stdio transport | M |
| 2.3 | Implement safety level enforcement | M |
| 2.4 | Implement MCP resources (status, portfolio, events) | S |
| 2.5 | Implement CLI command groups with Click | L |
| 2.6 | Implement output formatters (table, json, csv) | M |
| 2.7 | Implement CLI config file support | S |
| 2.8 | Integration test: Claude Code + MCP + live sandbox | L |

**Deliverable:** `nautilus-mcp` server and `nautilus-ctl` CLI, both fully
functional against a running TradingNode.

### Phase 3: AI Agent (Orchestration)

**Goal:** Claude can autonomously manage a sandbox trading session.

| Task | Description | Estimated Effort |
|------|-------------|-----------------|
| 3.1 | Implement agent event loop with Claude API | L |
| 3.2 | Implement objective system (define, track, evaluate) | M |
| 3.3 | Implement guardrail enforcement layer | L |
| 3.4 | Implement state persistence and decision audit trail | M |
| 3.5 | Implement kill switch mechanism | M |
| 3.6 | Implement operating mode transitions | S |
| 3.7 | End-to-end testing with sandbox TradingNode | XL |

**Deliverable:** Agent orchestrator capable of managing a complete trading
session against a sandbox venue.

### Phase 4: Hardening

**Goal:** Production readiness.

| Task | Description | Estimated Effort |
|------|-------------|-----------------|
| 4.1 | Security audit (auth, TLS, input validation) | L |
| 4.2 | Performance benchmarks (API latency, event throughput) | M |
| 4.3 | Chaos testing (client disconnect, agent crash, network partition) | L |
| 4.4 | Documentation (user guide, API reference, deployment guide) | L |
| 4.5 | Example configurations and notebooks | M |
| 4.6 | Production readiness checklist and review | M |

**Deliverable:** Production-grade control plane with documentation and examples.

---

## 10. Dependencies

### New Python Dependencies

| Package | Purpose | Phase |
|---------|---------|-------|
| `fastapi` | REST API framework | 1 |
| `uvicorn` | ASGI server | 1 |
| `websockets` | WebSocket support (likely already available via existing deps) | 1 |
| `httpx` | Async HTTP client for MCP server and CLI | 2 |
| `click` | CLI framework | 2 |
| `rich` | Terminal table rendering for CLI | 2 |
| `anthropic` | Claude API client for agent orchestration | 3 |

### Dependency Management

All new dependencies are optional and gated behind extras:

```toml
[project.optional-dependencies]
api = ["fastapi>=0.100", "uvicorn[standard]>=0.20"]
cli = ["click>=8.0", "httpx>=0.24", "rich>=13.0"]
agent = ["anthropic>=0.40", "httpx>=0.24"]
control-plane = ["nautilus_trader[api,cli,agent]"]
```

### Existing Dependencies Used

| Package | Already In Use | Used By Control Plane For |
|---------|---------------|--------------------------|
| `msgspec` | Yes | JSON serialization of domain objects |
| `asyncio` | Yes | Event loop sharing with API server |
| `uvloop` | Yes (optional) | Event loop performance |

---

## 11. Risks and Mitigations

| # | Risk | Impact | Likelihood | Mitigation |
|---|------|--------|------------|------------|
| 1 | AI agent makes costly trading error in live mode | **CRITICAL** | Medium | Graduated safety levels. `STRICT` mode auto-enabled for `LIVE`. Kill switch. Position limits. Loss limits. All actions audit-logged. |
| 2 | API server crash takes down trading node | **HIGH** | Low | API server runs as isolated asyncio task with top-level exception handler. Unhandled exceptions in the API do not propagate to engine queue tasks. Watchdog restarts API task on failure. |
| 3 | WebSocket backpressure causes memory growth | **MEDIUM** | Medium | Per-client bounded queues (default 1,000 events). Oldest events dropped when queue full. Max client limit (default 10). Gap notification sent to client. |
| 4 | API key leak enables unauthorized trading | **HIGH** | Low | Env-var configuration (not in config files). TLS required for non-localhost. Token rotation support. Rate limiting on mutations. `STRICT` mode blocks mutations entirely in live. |
| 5 | MCP tool schema drifts from API, causing agent errors | **LOW** | Medium | Tool schemas generated from shared Pydantic models (same models used by FastAPI and MCP). CI check validates schema consistency. |
| 6 | Event stream serialization adds latency to critical path | **MEDIUM** | Low | `EventStreamBridge` serializes asynchronously in its own handler. MessageBus `publish()` returns immediately after handler dispatch. No blocking on WebSocket writes. |
| 7 | Agent consumes excessive Claude API tokens | **LOW** | High | Token budget per session. Event batching and summarization to reduce context size. Configurable reasoning interval. |
| 8 | Concurrent API mutations cause race conditions | **MEDIUM** | Medium | All mutations route through `Controller.execute()` which processes commands sequentially via the MessageBus. API server does not bypass the command path. |

---

## 12. Success Criteria

### Functional Requirements

- [ ] All existing NautilusTrader control operations (strategy CRUD, order
  management, actor lifecycle) accessible via REST API endpoints.
- [ ] Real-time domain events (order fills, position changes, quotes)
  streamable to external consumers via WebSocket with less than 10ms added
  latency.
- [ ] Claude Code can discover and use all trading tools via MCP protocol
  with correct parameter schemas and return types.
- [ ] CLI (`nautilus-ctl`) provides full parity with the REST API for all
  query and mutation operations.
- [ ] Agent orchestrator can autonomously manage a complete trading session
  in sandbox mode, including strategy deployment, monitoring, and risk
  management.

### Non-Functional Requirements

- [ ] Zero performance degradation on the critical trading path (order
  submission to exchange latency unchanged).
- [ ] API server query latency under 5ms for cache/portfolio reads (p99).
- [ ] Event streaming throughput of at least 10,000 events/second per client.
- [ ] API server startup adds less than 500ms to TradingNode boot time.
- [ ] All new code covered by tests (unit + integration) at 80%+ coverage.
- [ ] No new required dependencies -- all control plane packages are optional
  extras.

### Safety Requirements

- [ ] No mutation possible in `STRICT` safety mode.
- [ ] Kill switch cancels all open orders and flattens all positions within
  5 seconds.
- [ ] All agent actions recorded in audit trail with timestamps, tool calls,
  parameters, results, and reasoning.
- [ ] Agent cannot escalate its own operating mode or safety level.
- [ ] Guardrail violations produce alerts and are logged, never silently
  ignored.
