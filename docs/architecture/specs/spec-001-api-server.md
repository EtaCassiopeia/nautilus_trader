# SPEC-001: API Server

## Overview

The NautilusTrader API Server exposes the trading system's full capabilities over HTTP, enabling external tools, UIs, CLIs, and AI agents to query state and issue commands. It is built on FastAPI, runs in-process with the `NautilusKernel`, and provides both synchronous request/response endpoints and a WebSocket endpoint for event streaming (see SPEC-002).

The server is an optional component: it is only started when `ApiServerConfig.enabled = True` in the node configuration. When enabled, it binds to a configurable host/port and serves a versioned REST API under the `/api/v1/` prefix.

## Module Structure

```
nautilus_trader/api/
├── __init__.py
├── config.py          # ApiServerConfig
├── server.py          # FastAPI app factory + lifecycle
├── dependencies.py    # FastAPI dependency injection (kernel access)
├── middleware.py      # Auth, CORS, request logging
├── routes/
│   ├── __init__.py
│   ├── node.py        # Node lifecycle endpoints
│   ├── strategies.py  # Strategy CRUD endpoints
│   ├── actors.py      # Actor CRUD endpoints
│   ├── orders.py      # Order management endpoints
│   ├── portfolio.py   # Portfolio query endpoints
│   ├── cache.py       # Cache query endpoints
│   ├── risk.py        # Risk configuration endpoints
│   └── market_data.py # Market data query endpoints
└── models/
    ├── __init__.py
    ├── requests.py    # Pydantic request models
    └── responses.py   # Pydantic response models
```

## Configuration

### `ApiServerConfig`

Defined in `nautilus_trader/api/config.py`. Extends `NautilusConfig`.

| Field              | Type            | Default         | Description                                      |
|--------------------|-----------------|-----------------|--------------------------------------------------|
| `enabled`          | `bool`          | `False`         | Whether to start the API server                  |
| `host`             | `str`           | `"127.0.0.1"`   | Bind address                                     |
| `port`             | `int`           | `8001`          | Bind port                                        |
| `api_key`          | `str \| None`   | `None`          | API key for authentication (None = no auth)      |
| `cors_origins`     | `list[str]`     | `[]`            | Allowed CORS origins (empty = CORS disabled)     |
| `max_connections`  | `int`           | `100`           | Maximum concurrent HTTP connections               |
| `ssl_certfile`     | `str \| None`   | `None`          | Path to SSL certificate file                     |
| `ssl_keyfile`      | `str \| None`   | `None`          | Path to SSL key file                             |

Example configuration in a node config:

```python
from nautilus_trader.api.config import ApiServerConfig

config = TradingNodeConfig(
    api_server=ApiServerConfig(
        enabled=True,
        host="0.0.0.0",
        port=8001,
        api_key="my-secret-key",
        cors_origins=["http://localhost:3000"],
    ),
    # ... rest of node config
)
```

## Server Lifecycle

### `server.py` — App Factory and Lifecycle

The module provides a `create_app(kernel: NautilusKernel, config: ApiServerConfig) -> FastAPI` factory function and a lifecycle manager.

**Startup sequence:**

1. `NautilusKernel` is fully initialized (cache populated, execution engine ready).
2. `create_app()` is called, constructing the FastAPI application with all routes mounted.
3. The kernel reference is stored in `app.state.kernel` for dependency injection.
4. Middleware is applied (auth, CORS, request logging).
5. `uvicorn.Server` is created with `loop="none"` to reuse the existing asyncio event loop.
6. The server is started as a task on the node's event loop via `asyncio.create_task(server.serve())`.

**Shutdown sequence:**

1. Node shutdown signal is received.
2. `server.shutdown()` is called, which triggers graceful uvicorn shutdown.
3. Active WebSocket connections are closed with code 1001 (Going Away).
4. Active HTTP requests are given up to 5 seconds to complete.
5. The server task is awaited to completion.

```python
# server.py — key interfaces

async def create_app(
    kernel: NautilusKernel,
    config: ApiServerConfig,
) -> FastAPI:
    """Create and configure the FastAPI application."""

class ApiServer:
    """Manages the lifecycle of the API server within the trading node."""

    def __init__(self, kernel: NautilusKernel, config: ApiServerConfig) -> None: ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...

    @property
    def is_running(self) -> bool: ...
```

### `dependencies.py` — Dependency Injection

FastAPI dependencies that provide access to kernel subsystems. These are constructed once and reused across all requests.

```python
# dependencies.py

from fastapi import Depends, Request

def get_kernel(request: Request) -> NautilusKernel:
    """Retrieve the NautilusKernel from app state."""
    return request.app.state.kernel

def get_cache(kernel: NautilusKernel = Depends(get_kernel)) -> CacheFacade:
    """Retrieve the cache facade."""
    return kernel.cache

def get_portfolio(kernel: NautilusKernel = Depends(get_kernel)) -> PortfolioFacade:
    """Retrieve the portfolio facade."""
    return kernel.portfolio

def get_trader(kernel: NautilusKernel = Depends(get_kernel)) -> Trader:
    """Retrieve the trader instance."""
    return kernel.trader

def get_controller(kernel: NautilusKernel = Depends(get_kernel)) -> Controller:
    """Retrieve the controller for mutations."""
    return kernel.trader.controller  # or equivalent path

def get_message_bus(kernel: NautilusKernel = Depends(get_kernel)) -> MessageBus:
    """Retrieve the message bus."""
    return kernel.msgbus

def get_emitter(kernel: NautilusKernel = Depends(get_kernel)) -> RiskEngine:
    """Retrieve the risk engine."""
    return kernel.risk_engine
```

### `middleware.py` — Auth, CORS, Request Logging

```python
# middleware.py

class ApiKeyMiddleware:
    """
    Validates X-Api-Key header against configured key.
    Returns 401 if key is missing or invalid.
    Skipped if api_key is None in config.
    Allows /docs, /openapi.json, /health without auth.
    """

class RequestLoggingMiddleware:
    """
    Logs every request: method, path, status code, latency.
    Uses the nautilus_trader logging infrastructure (not stdlib logging).
    """
```

CORS is applied via FastAPI's built-in `CORSMiddleware` using the `cors_origins` config field.

## API Endpoints

All endpoints are prefixed with `/api/v1/`. The server also exposes:
- `GET /health` — Health check, returns `{"status": "ok"}` (no auth required)
- `GET /docs` — Swagger UI (no auth required)
- `GET /openapi.json` — OpenAPI schema (no auth required)

### Node Lifecycle (`routes/node.py`)

#### `GET /api/v1/node/status`

Returns the current node status.

**Response 200:**
```json
{
  "trader_id": "TRADER-001",
  "instance_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "machine_id": "hostname-abc",
  "environment": "LIVE",
  "state": "RUNNING",
  "ts_started": 1700000000000000000,
  "ts_started_iso": "2023-11-14T22:13:20.000Z",
  "uptime_seconds": 3600.5,
  "component_states": {
    "DataEngine": "RUNNING",
    "RiskEngine": "RUNNING",
    "ExecutionEngine": "RUNNING"
  },
  "strategy_count": 3,
  "actor_count": 1
}
```

**Example:**
```bash
curl -H "X-Api-Key: my-key" http://localhost:8001/api/v1/node/status
```

#### `POST /api/v1/node/stop`

Initiates graceful shutdown of the trading node.

**Request body (optional):**
```json
{
  "timeout_seconds": 30
}
```

**Response 200:**
```json
{
  "message": "Shutdown initiated",
  "timeout_seconds": 30
}
```

**Error 409:**
```json
{
  "error": "Node is already stopping",
  "code": "NODE_ALREADY_STOPPING",
  "detail": null
}
```

**Example:**
```bash
curl -X POST -H "X-Api-Key: my-key" \
  -H "Content-Type: application/json" \
  -d '{"timeout_seconds": 30}' \
  http://localhost:8001/api/v1/node/stop
```

#### `GET /api/v1/node/config`

Returns the current node configuration with secrets redacted.

**Response 200:**
```json
{
  "trader_id": "TRADER-001",
  "environment": "LIVE",
  "data_engine": { "...": "..." },
  "risk_engine": { "...": "..." },
  "exec_engine": { "...": "..." },
  "api_server": {
    "enabled": true,
    "host": "0.0.0.0",
    "port": 8001,
    "api_key": "***REDACTED***"
  }
}
```

### Strategy Management (`routes/strategies.py`)

#### `GET /api/v1/strategies`

List all strategies with their current state.

**Query parameters:**
| Param   | Type   | Description                         |
|---------|--------|-------------------------------------|
| `state` | `str`  | Filter by state: RUNNING, STOPPED, etc. |

**Response 200:**
```json
{
  "strategies": [
    {
      "strategy_id": "EMACross-001",
      "strategy_type": "EMACross",
      "state": "RUNNING",
      "order_count": 47,
      "position_count": 2,
      "ts_created": 1700000000000000000,
      "config": { "fast_period": 10, "slow_period": 20 }
    }
  ],
  "count": 1
}
```

**Example:**
```bash
curl -H "X-Api-Key: my-key" http://localhost:8001/api/v1/strategies
curl -H "X-Api-Key: my-key" "http://localhost:8001/api/v1/strategies?state=RUNNING"
```

#### `POST /api/v1/strategies`

Create a new strategy from an `ImportableStrategyConfig`.

**Request body:**
```json
{
  "strategy_path": "nautilus_trader.examples.strategies.ema_cross:EMACross",
  "config_path": "nautilus_trader.examples.strategies.ema_cross:EMACrossConfig",
  "config": {
    "instrument_id": "BTCUSDT-PERP.BINANCE",
    "bar_type": "BTCUSDT-PERP.BINANCE-1-MINUTE-LAST-EXTERNAL",
    "fast_ema_period": 10,
    "slow_ema_period": 20,
    "trade_size": "0.01"
  },
  "start": false
}
```

| Field           | Type   | Required | Description                                   |
|-----------------|--------|----------|-----------------------------------------------|
| `strategy_path` | `str`  | Yes      | Importable path to strategy class             |
| `config_path`   | `str`  | Yes      | Importable path to strategy config class      |
| `config`        | `dict` | Yes      | Strategy configuration parameters             |
| `start`         | `bool` | No       | Whether to start immediately (default: false) |

**Response 201:**
```json
{
  "strategy_id": "EMACross-001",
  "state": "INITIALIZED",
  "message": "Strategy created successfully"
}
```

**Error 400:**
```json
{
  "error": "Invalid strategy configuration",
  "code": "INVALID_CONFIG",
  "detail": "Cannot import strategy class from path: nautilus_trader.examples.strategies.ema_cross:EMACross"
}
```

**Error 409:**
```json
{
  "error": "Strategy already exists",
  "code": "STRATEGY_EXISTS",
  "detail": {"strategy_id": "EMACross-001"}
}
```

#### `GET /api/v1/strategies/{strategy_id}`

Get detailed information about a specific strategy.

**Response 200:**
```json
{
  "strategy_id": "EMACross-001",
  "strategy_type": "EMACross",
  "state": "RUNNING",
  "config": { "fast_period": 10, "slow_period": 20 },
  "order_count": 47,
  "open_orders": [],
  "position_count": 2,
  "open_positions": [
    {
      "instrument_id": "BTCUSDT-PERP.BINANCE",
      "side": "LONG",
      "quantity": "0.05",
      "avg_px_open": "42150.50",
      "unrealized_pnl": "125.30"
    }
  ],
  "ts_created": 1700000000000000000,
  "ts_last_state_change": 1700003600000000000
}
```

**Error 404:**
```json
{
  "error": "Strategy not found",
  "code": "STRATEGY_NOT_FOUND",
  "detail": {"strategy_id": "EMACross-999"}
}
```

#### `POST /api/v1/strategies/{strategy_id}/start`

Start a stopped or initialized strategy.

**Response 200:**
```json
{
  "strategy_id": "EMACross-001",
  "state": "RUNNING",
  "message": "Strategy started"
}
```

**Error 409:**
```json
{
  "error": "Strategy is already running",
  "code": "STRATEGY_ALREADY_RUNNING",
  "detail": null
}
```

#### `POST /api/v1/strategies/{strategy_id}/stop`

Stop a running strategy.

**Response 200:**
```json
{
  "strategy_id": "EMACross-001",
  "state": "STOPPED",
  "message": "Strategy stopped"
}
```

#### `POST /api/v1/strategies/{strategy_id}/market-exit`

Market exit all positions managed by this strategy.

**Response 200:**
```json
{
  "strategy_id": "EMACross-001",
  "positions_closed": 2,
  "orders_submitted": [
    {"client_order_id": "O-20231114-001", "instrument_id": "BTCUSDT-PERP.BINANCE", "side": "SELL", "quantity": "0.05"}
  ],
  "message": "Market exit initiated for 2 positions"
}
```

#### `DELETE /api/v1/strategies/{strategy_id}`

Remove a strategy from the trader. Strategy must be stopped first.

**Response 200:**
```json
{
  "strategy_id": "EMACross-001",
  "message": "Strategy removed"
}
```

**Error 409:**
```json
{
  "error": "Cannot remove a running strategy",
  "code": "STRATEGY_RUNNING",
  "detail": "Stop the strategy before removing it"
}
```

### Actor Management (`routes/actors.py`)

#### `GET /api/v1/actors`

List all actors.

**Response 200:**
```json
{
  "actors": [
    {
      "actor_id": "DataProcessor-001",
      "actor_type": "DataProcessor",
      "state": "RUNNING"
    }
  ],
  "count": 1
}
```

#### `POST /api/v1/actors`

Create a new actor from config. Same pattern as strategy creation.

**Request body:**
```json
{
  "actor_path": "mypackage.actors:MyActor",
  "config_path": "mypackage.actors:MyActorConfig",
  "config": {},
  "start": false
}
```

**Response 201:**
```json
{
  "actor_id": "MyActor-001",
  "state": "INITIALIZED",
  "message": "Actor created successfully"
}
```

#### `POST /api/v1/actors/{actor_id}/start`

Start a stopped actor.

**Response 200:**
```json
{
  "actor_id": "MyActor-001",
  "state": "RUNNING",
  "message": "Actor started"
}
```

#### `POST /api/v1/actors/{actor_id}/stop`

Stop a running actor.

**Response 200:**
```json
{
  "actor_id": "MyActor-001",
  "state": "STOPPED",
  "message": "Actor stopped"
}
```

#### `DELETE /api/v1/actors/{actor_id}`

Remove an actor. Must be stopped first.

**Response 200:**
```json
{
  "actor_id": "MyActor-001",
  "message": "Actor removed"
}
```

### Order Management (`routes/orders.py`)

#### `GET /api/v1/orders`

List orders with filtering.

**Query parameters:**
| Param           | Type   | Description                                   |
|-----------------|--------|-----------------------------------------------|
| `status`        | `str`  | Filter: `open`, `closed`, `all` (default: `all`) |
| `strategy_id`   | `str`  | Filter by strategy ID                         |
| `instrument_id` | `str`  | Filter by instrument ID                       |
| `venue`         | `str`  | Filter by venue                               |
| `side`          | `str`  | Filter by side: `BUY`, `SELL`                 |
| `limit`         | `int`  | Max results (default: 100, max: 1000)         |
| `offset`        | `int`  | Pagination offset                             |

**Response 200:**
```json
{
  "orders": [
    {
      "client_order_id": "O-20231114-001",
      "venue_order_id": "123456789",
      "instrument_id": "BTCUSDT-PERP.BINANCE",
      "strategy_id": "EMACross-001",
      "side": "BUY",
      "order_type": "LIMIT",
      "quantity": "0.01",
      "price": "42000.00",
      "time_in_force": "GTC",
      "status": "ACCEPTED",
      "filled_qty": "0.00",
      "avg_px": null,
      "ts_init": 1700000000000000000,
      "ts_last": 1700000000000000000
    }
  ],
  "count": 1,
  "total": 47
}
```

**Example:**
```bash
curl -H "X-Api-Key: my-key" "http://localhost:8001/api/v1/orders?status=open&strategy_id=EMACross-001"
```

#### `GET /api/v1/orders/{client_order_id}`

Get detailed order information including full event history.

**Response 200:**
```json
{
  "client_order_id": "O-20231114-001",
  "venue_order_id": "123456789",
  "instrument_id": "BTCUSDT-PERP.BINANCE",
  "strategy_id": "EMACross-001",
  "side": "BUY",
  "order_type": "LIMIT",
  "quantity": "0.01",
  "price": "42000.00",
  "time_in_force": "GTC",
  "status": "FILLED",
  "filled_qty": "0.01",
  "avg_px": "41998.50",
  "ts_init": 1700000000000000000,
  "ts_last": 1700000060000000000,
  "events": [
    {"type": "OrderInitialized", "ts_event": 1700000000000000000},
    {"type": "OrderSubmitted", "ts_event": 1700000001000000000},
    {"type": "OrderAccepted", "ts_event": 1700000002000000000},
    {"type": "OrderFilled", "ts_event": 1700000060000000000, "fill_qty": "0.01", "fill_px": "41998.50"}
  ]
}
```

**Error 404:**
```json
{
  "error": "Order not found",
  "code": "ORDER_NOT_FOUND",
  "detail": {"client_order_id": "O-nonexistent"}
}
```

#### `POST /api/v1/orders`

Submit a new order. The order is routed through the `Controller` which publishes to the `MessageBus`, then processed by the `ExecutionEngine` and `RiskEngine` before submission to the venue.

**Request body:**
```json
{
  "instrument_id": "BTCUSDT-PERP.BINANCE",
  "side": "BUY",
  "order_type": "LIMIT",
  "quantity": "0.01",
  "price": "42000.00",
  "time_in_force": "GTC",
  "strategy_id": "EMACross-001",
  "post_only": false,
  "reduce_only": false,
  "tags": ["api-order"]
}
```

| Field           | Type    | Required | Description                                       |
|-----------------|---------|----------|---------------------------------------------------|
| `instrument_id` | `str`   | Yes      | Full instrument ID                                |
| `side`          | `str`   | Yes      | `BUY` or `SELL`                                   |
| `order_type`    | `str`   | Yes      | `MARKET`, `LIMIT`, `STOP_MARKET`, `STOP_LIMIT`    |
| `quantity`      | `str`   | Yes      | Order quantity as decimal string                  |
| `price`         | `str`   | Cond.    | Required for LIMIT and STOP_LIMIT orders          |
| `trigger_price` | `str`   | Cond.    | Required for STOP_MARKET and STOP_LIMIT orders    |
| `time_in_force` | `str`   | No       | `GTC` (default), `IOC`, `FOK`, `DAY`, `GTD`      |
| `expire_time`   | `str`   | Cond.    | Required if time_in_force is GTD (ISO 8601)       |
| `strategy_id`   | `str`   | No       | Strategy to attribute the order to                |
| `post_only`     | `bool`  | No       | Post-only flag (default: false)                   |
| `reduce_only`   | `bool`  | No       | Reduce-only flag (default: false)                 |
| `tags`          | `list`  | No       | Optional tags for the order                       |

**Response 202:**
```json
{
  "client_order_id": "O-20231114-002",
  "instrument_id": "BTCUSDT-PERP.BINANCE",
  "side": "BUY",
  "order_type": "LIMIT",
  "quantity": "0.01",
  "price": "42000.00",
  "status": "INITIALIZED",
  "message": "Order submitted for processing"
}
```

Note: 202 Accepted is used because order submission is asynchronous. The order may still be rejected by the risk engine or venue.

**Error 400:**
```json
{
  "error": "Invalid order parameters",
  "code": "INVALID_ORDER",
  "detail": "Price is required for LIMIT orders"
}
```

**Error 422:**
```json
{
  "error": "Instrument not found",
  "code": "INSTRUMENT_NOT_FOUND",
  "detail": {"instrument_id": "INVALID-ID"}
}
```

**Example:**
```bash
curl -X POST -H "X-Api-Key: my-key" \
  -H "Content-Type: application/json" \
  -d '{"instrument_id":"BTCUSDT-PERP.BINANCE","side":"BUY","order_type":"MARKET","quantity":"0.01"}' \
  http://localhost:8001/api/v1/orders
```

#### `DELETE /api/v1/orders/{client_order_id}`

Cancel an open order.

**Response 200:**
```json
{
  "client_order_id": "O-20231114-001",
  "message": "Cancel request submitted"
}
```

**Error 409:**
```json
{
  "error": "Order is not in a cancelable state",
  "code": "ORDER_NOT_CANCELABLE",
  "detail": {"status": "FILLED"}
}
```

#### `PATCH /api/v1/orders/{client_order_id}`

Modify an open order's quantity or price.

**Request body:**
```json
{
  "quantity": "0.02",
  "price": "41500.00"
}
```

At least one of `quantity` or `price` must be provided.

**Response 200:**
```json
{
  "client_order_id": "O-20231114-001",
  "message": "Modify request submitted",
  "new_quantity": "0.02",
  "new_price": "41500.00"
}
```

#### `POST /api/v1/orders/cancel-all`

Cancel all open orders, optionally filtered.

**Request body (optional):**
```json
{
  "instrument_id": "BTCUSDT-PERP.BINANCE",
  "strategy_id": "EMACross-001",
  "side": "BUY"
}
```

**Response 200:**
```json
{
  "orders_canceled": 5,
  "client_order_ids": ["O-001", "O-002", "O-003", "O-004", "O-005"],
  "message": "Cancel requests submitted for 5 orders"
}
```

### Portfolio (`routes/portfolio.py`)

#### `GET /api/v1/portfolio`

Full portfolio summary.

**Response 200:**
```json
{
  "trader_id": "TRADER-001",
  "balances": {
    "BINANCE": {
      "total": "50000.00",
      "locked": "5000.00",
      "free": "45000.00",
      "currency": "USDT"
    }
  },
  "positions": [
    {
      "instrument_id": "BTCUSDT-PERP.BINANCE",
      "side": "LONG",
      "quantity": "0.05",
      "avg_px_open": "42150.50",
      "unrealized_pnl": "125.30",
      "realized_pnl": "1500.00",
      "currency": "USDT"
    }
  ],
  "total_unrealized_pnl": "125.30",
  "total_realized_pnl": "1500.00",
  "ts_snapshot": 1700003600000000000
}
```

#### `GET /api/v1/portfolio/balances`

Account balances, optionally filtered by venue.

**Query parameters:**
| Param   | Type  | Description               |
|---------|-------|---------------------------|
| `venue` | `str` | Filter by venue name      |

**Response 200:**
```json
{
  "balances": [
    {
      "venue": "BINANCE",
      "account_id": "BINANCE-001",
      "balances": [
        {"currency": "USDT", "total": "50000.00", "locked": "5000.00", "free": "45000.00"},
        {"currency": "BTC", "total": "1.50", "locked": "0.00", "free": "1.50"}
      ]
    }
  ]
}
```

#### `GET /api/v1/portfolio/positions`

Open positions.

**Query parameters:**
| Param           | Type  | Description                   |
|-----------------|-------|-------------------------------|
| `instrument_id` | `str` | Filter by instrument ID       |
| `venue`         | `str` | Filter by venue               |
| `side`          | `str` | Filter by side: LONG, SHORT   |

**Response 200:**
```json
{
  "positions": [
    {
      "instrument_id": "BTCUSDT-PERP.BINANCE",
      "strategy_id": "EMACross-001",
      "side": "LONG",
      "quantity": "0.05",
      "signed_qty": "0.05",
      "avg_px_open": "42150.50",
      "avg_px_close": null,
      "unrealized_pnl": "125.30",
      "realized_pnl": "0.00",
      "commission": "5.20",
      "currency": "USDT",
      "ts_opened": 1700000000000000000,
      "ts_last": 1700003600000000000,
      "duration_ns": 3600000000000
    }
  ],
  "count": 1
}
```

#### `GET /api/v1/portfolio/positions/{instrument_id}`

Position for a specific instrument.

**Response 200:** Same structure as single position object above.

**Error 404:**
```json
{
  "error": "No open position for instrument",
  "code": "POSITION_NOT_FOUND",
  "detail": {"instrument_id": "ETHUSDT-PERP.BINANCE"}
}
```

#### `GET /api/v1/portfolio/pnl`

Realized and unrealized P&L summary.

**Query parameters:**
| Param   | Type  | Description               |
|---------|-------|---------------------------|
| `venue` | `str` | Filter by venue           |

**Response 200:**
```json
{
  "realized_pnl": {
    "USDT": "1500.00",
    "BTC": "0.005"
  },
  "unrealized_pnl": {
    "USDT": "125.30"
  },
  "total_pnl": {
    "USDT": "1625.30",
    "BTC": "0.005"
  },
  "commissions": {
    "USDT": "42.50"
  }
}
```

#### `GET /api/v1/portfolio/exposure`

Net exposure by instrument and venue.

**Response 200:**
```json
{
  "exposures": [
    {
      "instrument_id": "BTCUSDT-PERP.BINANCE",
      "venue": "BINANCE",
      "side": "LONG",
      "quantity": "0.05",
      "notional_value": "2107.53",
      "currency": "USDT"
    }
  ],
  "total_exposure_by_currency": {
    "USDT": "2107.53"
  }
}
```

### Cache Queries (`routes/cache.py`)

#### `GET /api/v1/cache/instruments`

List instruments available in the cache.

**Query parameters:**
| Param     | Type  | Description                        |
|-----------|-------|------------------------------------|
| `venue`   | `str` | Filter by venue                    |
| `search`  | `str` | Search by symbol (case-insensitive)|
| `type`    | `str` | Instrument type filter             |
| `limit`   | `int` | Max results (default: 100)         |

**Response 200:**
```json
{
  "instruments": [
    {
      "instrument_id": "BTCUSDT-PERP.BINANCE",
      "symbol": "BTCUSDT-PERP",
      "venue": "BINANCE",
      "instrument_type": "CryptoPerpetual",
      "base_currency": "BTC",
      "quote_currency": "USDT",
      "price_precision": 2,
      "size_precision": 3,
      "tick_size": "0.01",
      "lot_size": "0.001",
      "min_quantity": "0.001",
      "max_quantity": "1000.0"
    }
  ],
  "count": 1
}
```

#### `GET /api/v1/cache/instruments/{instrument_id}`

Get full instrument details.

**Response 200:** Full instrument object with all fields from `to_dict()`.

#### `GET /api/v1/cache/accounts`

List all accounts.

**Response 200:**
```json
{
  "accounts": [
    {
      "account_id": "BINANCE-001",
      "account_type": "MARGIN",
      "venue": "BINANCE",
      "base_currency": null,
      "is_connected": true
    }
  ],
  "count": 1
}
```

#### `GET /api/v1/cache/accounts/{account_id}`

Get account details.

**Response 200:** Full account state including balances, margins.

### Risk (`routes/risk.py`)

#### `GET /api/v1/risk/state`

Current risk engine state and active limits.

**Response 200:**
```json
{
  "state": "RUNNING",
  "trading_state": "ACTIVE",
  "pre_trade_checks": true,
  "max_order_submit_rate": "10/00:00:01",
  "max_order_modify_rate": "10/00:00:01",
  "max_notional_per_order": {
    "BTCUSDT-PERP.BINANCE": "100000.00"
  }
}
```

#### `PUT /api/v1/risk/limits`

Update risk limits.

**Request body:**
```json
{
  "max_order_submit_rate": "5/00:00:01",
  "max_notional_per_order": {
    "BTCUSDT-PERP.BINANCE": "50000.00"
  }
}
```

**Response 200:**
```json
{
  "message": "Risk limits updated",
  "limits": { "...": "..." }
}
```

### Market Data (`routes/market_data.py`)

#### `GET /api/v1/data/quotes/{instrument_id}`

Latest quote tick for an instrument.

**Response 200:**
```json
{
  "instrument_id": "BTCUSDT-PERP.BINANCE",
  "bid_price": "42100.50",
  "ask_price": "42101.00",
  "bid_size": "1.500",
  "ask_size": "2.300",
  "ts_event": 1700003600000000000,
  "ts_init": 1700003600000000000
}
```

**Error 404 if no quote available.**

#### `GET /api/v1/data/trades/{instrument_id}`

Latest trade tick.

**Response 200:**
```json
{
  "instrument_id": "BTCUSDT-PERP.BINANCE",
  "price": "42100.75",
  "size": "0.500",
  "aggressor_side": "BUY",
  "trade_id": "987654321",
  "ts_event": 1700003600000000000,
  "ts_init": 1700003600000000000
}
```

#### `GET /api/v1/data/bars/{instrument_id}`

Latest bars for an instrument.

**Query parameters:**
| Param      | Type  | Description                                 |
|------------|-------|---------------------------------------------|
| `bar_type` | `str` | Full bar type string (required)             |
| `count`    | `int` | Number of bars to return (default: 10, max: 1000) |

**Response 200:**
```json
{
  "bar_type": "BTCUSDT-PERP.BINANCE-1-MINUTE-LAST-EXTERNAL",
  "bars": [
    {
      "open": "42100.00",
      "high": "42150.00",
      "low": "42050.00",
      "close": "42120.00",
      "volume": "150.500",
      "ts_event": 1700003600000000000,
      "ts_init": 1700003600000000000
    }
  ],
  "count": 10
}
```

#### `POST /api/v1/data/subscribe`

Subscribe to market data. Triggers internal data subscriptions through the `DataEngine`.

**Request body:**
```json
{
  "data_type": "quotes",
  "instrument_id": "BTCUSDT-PERP.BINANCE"
}
```

| Field           | Type  | Required | Description                           |
|-----------------|-------|----------|---------------------------------------|
| `data_type`     | `str` | Yes      | `quotes`, `trades`, `bars`            |
| `instrument_id` | `str` | Yes      | Instrument to subscribe to            |
| `bar_type`      | `str` | Cond.    | Required if data_type is `bars`       |

**Response 200:**
```json
{
  "message": "Subscription created",
  "data_type": "quotes",
  "instrument_id": "BTCUSDT-PERP.BINANCE"
}
```

## Internal Architecture

### Integration with NautilusKernel

The API server does NOT create its own kernel. It receives a reference to the existing `NautilusKernel` at construction time. All access to trading system state goes through the kernel's public interfaces:

- **CacheFacade** (`kernel.cache`): All read queries for instruments, orders, positions, accounts, and market data. This is the primary read path and is safe to call from any coroutine on the event loop.
- **PortfolioFacade** (`kernel.portfolio`): Portfolio-level aggregations (balances, P&L, exposure). Also safe for concurrent reads.
- **Trader** (`kernel.trader`): Strategy and actor management (add, start, stop, remove).
- **Controller**: Strategy lifecycle mutations are dispatched through the `Controller`, which ensures proper sequencing.

### Mutation Flow

All mutations (order submission, strategy management, configuration changes) follow this pattern:

1. HTTP handler validates the request using Pydantic models.
2. Handler constructs the appropriate command object (e.g., `SubmitOrder`, `TradingCommand`).
3. Command is published to the `MessageBus` via the appropriate method.
4. The `ExecutionEngine` or `Controller` processes the command on the next event loop iteration.
5. The HTTP response is returned immediately with a 202 (for async operations) or 200 (for synchronous state changes).

This ensures that all mutations pass through the same pipeline as internally-generated commands, preserving risk checks, audit logging, and event generation.

### Thread Safety

The FastAPI server runs on the **same asyncio event loop** as the `NautilusKernel`. This means:

- All handler coroutines execute on the same thread as the kernel's event processing.
- No locking is required for cache reads or message bus publications.
- Blocking operations (e.g., file I/O for config) must use `asyncio.to_thread()`.
- The `uvicorn` server is configured with `loop="none"` to avoid creating a separate event loop.

This design eliminates race conditions between API requests and internal event processing at the cost of serializing all operations on a single thread. For the expected API load (tens of requests per second, not thousands), this is an acceptable tradeoff.

## Authentication

### API Key Authentication

When `ApiServerConfig.api_key` is set (non-None), the `ApiKeyMiddleware` enforces authentication:

1. Every request must include the `X-Api-Key` header.
2. The header value is compared against the configured key using `hmac.compare_digest()` for constant-time comparison.
3. Unauthenticated requests receive a 401 response.

**Exempt paths** (no auth required):
- `GET /health`
- `GET /docs`
- `GET /redoc`
- `GET /openapi.json`

When `api_key` is None, no authentication is enforced. This is suitable for local development and backtesting.

### Future Authorization

The current design supports a single API key with full access. Future iterations may add:
- Per-endpoint role-based access (read-only keys, trade-only keys).
- JWT-based authentication for multi-user setups.
- Rate limiting per API key.

These are NOT in scope for the initial implementation.

## Error Handling

### Standard Error Response

All error responses follow a consistent format:

```json
{
  "error": "Human-readable error message",
  "code": "MACHINE_READABLE_CODE",
  "detail": null
}
```

| Field    | Type              | Description                                   |
|----------|-------------------|-----------------------------------------------|
| `error`  | `str`             | Human-readable description of the error       |
| `code`   | `str`             | Machine-readable error code (UPPER_SNAKE_CASE) |
| `detail` | `any \| null`     | Additional context (object, string, or null)   |

### HTTP Status Code Mapping

| Status | Meaning                    | When Used                                                |
|--------|----------------------------|----------------------------------------------------------|
| 200    | OK                         | Successful read or synchronous mutation                  |
| 201    | Created                    | Resource created (strategy, actor)                       |
| 202    | Accepted                   | Async operation accepted (order submission)              |
| 400    | Bad Request                | Invalid request body or parameters                       |
| 401    | Unauthorized               | Missing or invalid API key                               |
| 404    | Not Found                  | Resource not found (order, strategy, instrument)         |
| 409    | Conflict                   | State conflict (strategy already running, order filled)  |
| 422    | Unprocessable Entity       | Valid JSON but semantically invalid                      |
| 429    | Too Many Requests          | Rate limit exceeded (future)                             |
| 500    | Internal Server Error      | Unexpected error in handler                              |
| 503    | Service Unavailable        | Node is shutting down or not yet initialized             |

### Error Codes

Error codes are namespaced by resource:

- `NODE_*`: Node lifecycle errors
- `STRATEGY_*`: Strategy management errors
- `ORDER_*`: Order management errors
- `INSTRUMENT_*`: Instrument lookup errors
- `POSITION_*`: Position lookup errors
- `AUTH_*`: Authentication errors
- `INTERNAL_*`: Internal server errors

### Exception Handling

A global exception handler catches all unhandled exceptions in route handlers:

```python
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log.error(f"Unhandled exception in {request.method} {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "code": "INTERNAL_ERROR",
            "detail": str(exc) if kernel.environment != "LIVE" else None,
        },
    )
```

In LIVE environments, exception details are NOT exposed in responses to avoid leaking internal state.

## OpenAPI

FastAPI automatically generates an OpenAPI 3.1 specification from the route definitions and Pydantic models.

- **Swagger UI**: `GET /docs` — Interactive API documentation and testing.
- **ReDoc**: `GET /redoc` — Alternative API documentation view.
- **OpenAPI JSON**: `GET /openapi.json` — Machine-readable schema.

The OpenAPI spec includes:
- All request/response models with JSON Schema types.
- Path parameters, query parameters, and request body schemas.
- Error response schemas.
- Authentication requirements (API key in header).
- Example values for request/response bodies.

The OpenAPI metadata is configured in the app factory:

```python
app = FastAPI(
    title="NautilusTrader API",
    description="REST API for NautilusTrader trading node management",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)
```
