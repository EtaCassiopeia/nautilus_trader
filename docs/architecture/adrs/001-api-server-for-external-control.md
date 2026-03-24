# ADR-001: Embedded API Server for External Control

| Field       | Value                                      |
|-------------|--------------------------------------------|
| **Status**  | Proposed                                   |
| **Date**    | 2026-03-21                                 |
| **Authors** | Mohsen Zainalpour                          |
| **Relates** | ADR-002, ADR-003, ADR-004, ADR-005         |

## Context

NautilusTrader is a high-performance algorithmic trading platform built in Python and Rust (via PyO3). The platform's live trading entry point, `TradingNode` (`nautilus_trader/live/node.py`), wraps `NautilusKernel` (`nautilus_trader/system/kernel.py`), which orchestrates all core subsystems: `MessageBus`, `Cache`, `Portfolio`, `DataEngine`, `ExecEngine`, `RiskEngine`, `Trader`, and `Controller`.

**The system currently has no external control surface.** All interactions — starting strategies, submitting orders, querying portfolio state — must happen in-process via Python code. The `Controller` class (`nautilus_trader/trading/controller.py`) provides runtime strategy and actor management through methods like `create_strategy()`, `stop_strategy()`, and `market_exit_strategy()`, but these are only accessible from within the same Python process.

This limitation blocks several critical use cases:

1. **AI Agent Integration**: Claude and other AI agents need to monitor and control trading operations through structured APIs. There is no way for an external process to send commands or receive events.
2. **Headless Operation**: Production deployments require remote monitoring and control without a Python REPL attached to the process.
3. **Multi-tool Workflows**: Operators need to compose NautilusTrader with external monitoring dashboards, alerting systems, and CI/CD pipelines.
4. **CLI Control**: A command-line interface for managing a running node requires a network API to communicate with the node process.

The existing internal primitives are well-designed for external exposure:
- `Controller` already handles command dispatch via `CreateStrategy`, `StartStrategy`, `StopStrategy`, `RemoveStrategy`, and equivalent actor commands (defined in `nautilus_trader/trading/messages.py`).
- `CacheFacade` provides read-only access to instruments, orders, positions, and accounts.
- `PortfolioFacade` provides read-only access to balances, margins, P&L, and exposures.
- `MessageBus` supports pub/sub with wildcard topic patterns and optional Redis backing.
- All configurations inherit from `NautilusConfig` (based on `msgspec.Struct`) and are JSON-serializable.

What is missing is a thin HTTP layer to expose these primitives externally.

## Decision

**Embed a FastAPI-based REST + WebSocket API server inside the `TradingNode` process**, running on the same asyncio event loop. The server is implemented in a new module `nautilus_trader/api/` and serves as the canonical external control surface for all NautilusTrader operations.

### Why FastAPI

| Criterion                | FastAPI | Flask  | aiohttp | gRPC   |
|--------------------------|---------|--------|---------|--------|
| Async-native             | Yes     | No     | Yes     | Yes    |
| OpenAPI auto-generation  | Yes     | Plugin | No      | N/A    |
| WebSocket support        | Yes     | Plugin | Yes     | Stream |
| JSON Schema validation   | Yes     | No     | No      | Proto  |
| Learning curve           | Low     | Low    | Medium  | High   |
| MCP/Agent compatibility  | High    | Medium | Medium  | Low    |

FastAPI is chosen because:
- **Async-native**: Runs directly on the `TradingNode`'s asyncio event loop without blocking the trading engines.
- **OpenAPI auto-generation**: Produces a machine-readable API schema from code, which the MCP server (ADR-003) and CLI (ADR-004) can consume to stay in sync.
- **Pydantic/JSON Schema validation**: Request and response models are validated automatically, catching malformed inputs before they reach the trading core.
- **Minimal overhead**: Adds no background threads or separate event loops when integrated correctly.

### API Surface Groups

The server exposes endpoints organized into these groups:

| Group               | Purpose                                        | Access Pattern |
|----------------------|------------------------------------------------|----------------|
| **Node Lifecycle**   | Status, shutdown, configuration                | Read + Control |
| **Strategy Mgmt**    | Create, start, stop, remove, market-exit       | CRUD           |
| **Actor Mgmt**       | Create, start, stop, remove                    | CRUD           |
| **Order Mgmt**       | Submit, cancel, modify, list, query            | CRUD           |
| **Portfolio**        | Balances, positions, P&L, exposures            | Read-only      |
| **Cache Queries**    | Instruments, orders, positions, accounts       | Read-only      |
| **Risk**             | State, limits configuration                    | Read + Write   |
| **Market Data**      | Quotes, trades, bars, subscriptions            | Read + Control |
| **Event Stream**     | WebSocket real-time event streaming            | Stream (ADR-002)|

All endpoints are versioned under `/api/v1/`.

### Thread Safety Model

The API server runs on the **same asyncio event loop** as the `TradingNode`. This eliminates cross-thread synchronization issues because:

1. **Mutations** (order submission, strategy lifecycle) are dispatched through the existing `Controller.execute()` method, which publishes commands to the `MessageBus`. The MessageBus is designed for single-loop operation.
2. **Queries** (portfolio, cache) access `CacheFacade` and `PortfolioFacade`, which are read-only facades. These are safe to call from any coroutine on the same event loop.
3. **No new threads are introduced.** The FastAPI ASGI server (uvicorn) is started as an asyncio task within the existing loop.

```
HTTP Request → FastAPI handler (coroutine on node's event loop)
  ├── Query? → CacheFacade / PortfolioFacade → JSON response
  └── Mutation? → Controller.execute(command) → MessageBus → Engine → JSON response
```

### Authentication

- **Mechanism**: API key in `X-Api-Key` request header.
- **Default**: Disabled (no authentication required). This is safe because the server binds to `127.0.0.1` by default.
- **Production**: Configure an API key via `ApiServerConfig.api_key`. When set, all requests must include the matching key.
- **Future**: Per-endpoint authorization, OAuth2/JWT support, and TLS termination can be added without changing the core design.

### Configuration

A new `ApiServerConfig` is added to `TradingNodeConfig`:

```python
class ApiServerConfig(NautilusConfig, frozen=True):
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 8001
    api_key: str | None = None
    cors_origins: list[str] = []
    max_connections: int = 100
    request_timeout_secs: float = 30.0

class TradingNodeConfig(NautilusKernelConfig, frozen=True):
    # ... existing fields ...
    api_server: ApiServerConfig | None = None  # NEW
```

### Server Lifecycle

1. **Startup**: When `TradingNode.run_async()` is called and `api_server` config is present with `enabled=True`, the API server is started as an asyncio task alongside the engine queue tasks.
2. **Running**: The server accepts HTTP and WebSocket connections. All handlers are coroutines on the node's event loop.
3. **Shutdown**: When the node stops (via signal or `node.stop()`), the API server is shut down gracefully, closing all connections.

## Consequences

### Positive

- **External Control**: All NautilusTrader operations become accessible from any HTTP client — scripts, dashboards, AI agents, mobile apps.
- **AI Agent Integration**: The REST API serves as the foundation for the MCP server (ADR-003) and agent orchestration (ADR-005).
- **Headless Operation**: Production nodes can be monitored and controlled remotely without attaching a Python REPL.
- **OpenAPI Documentation**: Interactive API docs available at `/docs` (Swagger UI) and machine-readable schema at `/openapi.json`.
- **Zero Core Changes**: The API server is a thin layer over existing `Controller`, `CacheFacade`, and `PortfolioFacade` — no changes to Cython or Rust core required.
- **Same-Loop Safety**: Running on the node's event loop avoids all cross-thread synchronization complexity.

### Negative

- **New Dependencies**: FastAPI and uvicorn become dependencies (optional, only needed when API server is enabled).
- **Attack Surface**: An HTTP server is an attack surface. Binding to `127.0.0.1` by default and requiring API keys for remote access mitigates this.
- **API Stability**: Once external consumers depend on the API, breaking changes require versioning discipline (`/api/v1/`, `/api/v2/`).
- **Event Loop Contention**: Long-running API handlers could block the trading event loop. All handlers must be non-blocking and complete quickly. CPU-bound operations (e.g., large cache queries) may need `run_in_executor`.
- **Serialization Overhead**: Cython domain objects must be serialized to JSON for API responses. Many objects already have `to_dict()` methods, but coverage gaps need to be filled.

### Neutral

- The API server is **disabled by default** — existing users are unaffected unless they opt in via configuration.
- The module structure (`nautilus_trader/api/`) is self-contained and does not modify existing package structure.
