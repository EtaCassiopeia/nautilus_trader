# SPEC-003: MCP Server

## Overview

The NautilusTrader MCP (Model Context Protocol) server exposes trading system capabilities as tools that AI assistants (Claude, GPT, etc.) can discover and invoke. It acts as a bridge between AI agents and the NautilusTrader REST API (SPEC-001), translating MCP tool calls into HTTP requests and formatting responses for LLM consumption.

The MCP server runs as a **separate process** from the trading node. It connects to the NautilusTrader API over HTTP, which means it can be started, stopped, and restarted independently without affecting the trading system. This separation also means the MCP server can be run on a different machine from the trading node.

The server implements the MCP specification using the `mcp` Python SDK and communicates with AI clients via stdio transport (for CLI integration) or SSE/streamable HTTP transport (for remote access).

## Module Structure

```
nautilus_trader/mcp/
├── __init__.py
├── server.py          # MCP server setup and tool registration
├── config.py          # McpServerConfig
├── tools/
│   ├── __init__.py
│   ├── node.py        # Node management tools
│   ├── strategies.py  # Strategy management tools
│   ├── orders.py      # Order management tools
│   ├── portfolio.py   # Portfolio query tools
│   ├── market_data.py # Market data tools
│   └── risk.py        # Risk management tools
├── resources.py       # MCP resource definitions
├── safety.py          # Safety guardrails and confirmation logic
└── client.py          # HTTP client wrapper for NautilusTrader API
```

## Configuration

### `McpServerConfig`

Defined in `nautilus_trader/mcp/config.py`.

```python
@dataclass
class McpServerConfig:
    """Configuration for the NautilusTrader MCP server."""

    # Connection to NautilusTrader API
    api_url: str = "http://localhost:8001"
    api_key: str | None = None

    # Safety
    safety_level: Literal["UNRESTRICTED", "STANDARD", "STRICT"] = "STANDARD"
    read_only: bool = False

    # Tool filtering
    allowed_tools: list[str] | None = None    # None = all tools enabled
    blocked_tools: list[str] | None = None    # Takes precedence over allowed_tools

    # Order guardrails
    max_order_quantity: str | None = None      # Maximum quantity per order (decimal string)
    allowed_instruments: list[str] | None = None  # Instrument allowlist (None = all)
    blocked_instruments: list[str] | None = None  # Instrument blocklist

    # Transport
    transport: Literal["stdio", "sse"] = "stdio"
    sse_host: str = "127.0.0.1"
    sse_port: int = 8002
```

### Configuration File

The MCP server can be configured via a TOML file at `~/.nautilus/mcp.toml`:

```toml
[connection]
api_url = "http://localhost:8001"
api_key = "my-secret-key"

[safety]
safety_level = "STANDARD"
read_only = false

[guardrails]
max_order_quantity = "1.0"
allowed_instruments = ["BTCUSDT-PERP.BINANCE", "ETHUSDT-PERP.BINANCE"]

[transport]
transport = "stdio"
```

Configuration priority: CLI flags > environment variables > config file > defaults.

## HTTP Client (`client.py`)

The MCP server communicates with the NautilusTrader API through a thin HTTP client wrapper.

```python
class NautilusClient:
    """HTTP client for the NautilusTrader API."""

    def __init__(self, api_url: str, api_key: str | None = None) -> None:
        self._base_url = api_url.rstrip("/")
        self._api_key = api_key
        self._session: httpx.AsyncClient | None = None

    async def start(self) -> None:
        """Initialize the HTTP session."""
        headers = {}
        if self._api_key:
            headers["X-Api-Key"] = self._api_key
        self._session = httpx.AsyncClient(
            base_url=self._base_url,
            headers=headers,
            timeout=30.0,
        )

    async def stop(self) -> None:
        """Close the HTTP session."""
        if self._session:
            await self._session.aclose()

    async def get(self, path: str, params: dict | None = None) -> dict: ...
    async def post(self, path: str, json: dict | None = None) -> dict: ...
    async def put(self, path: str, json: dict | None = None) -> dict: ...
    async def patch(self, path: str, json: dict | None = None) -> dict: ...
    async def delete(self, path: str) -> dict: ...
```

All methods raise `NautilusApiError` on non-2xx responses, providing the error code and detail from the API's standard error format.

## MCP Server Setup (`server.py`)

```python
from mcp.server import Server
from mcp.server.stdio import stdio_server

def create_mcp_server(config: McpServerConfig) -> Server:
    """Create and configure the MCP server with all tools registered."""
    server = Server("nautilus-trader")
    client = NautilusClient(config.api_url, config.api_key)
    safety = SafetyGuardrails(config)

    # Register tools from each module
    register_node_tools(server, client, safety)
    register_strategy_tools(server, client, safety)
    register_order_tools(server, client, safety)
    register_portfolio_tools(server, client, safety)
    register_market_data_tools(server, client, safety)
    register_risk_tools(server, client, safety)

    # Register resources
    register_resources(server, client)

    # Filter tools based on config
    if config.allowed_tools is not None:
        server.filter_tools(allow=config.allowed_tools)
    if config.blocked_tools is not None:
        server.filter_tools(block=config.blocked_tools)
    if config.read_only:
        server.filter_tools(block=[t for t in server.tools if t.risk_level != "READ"])

    return server

async def main() -> None:
    """Entry point for the MCP server."""
    config = load_config()
    server = create_mcp_server(config)

    if config.transport == "stdio":
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream)
    elif config.transport == "sse":
        from mcp.server.sse import SseServerTransport
        transport = SseServerTransport("/messages")
        # ... SSE setup with Starlette
```

## MCP Tool Definitions

Each tool is defined with a name, description, input JSON Schema, and safety level. The description is written for LLM consumption — it should be clear, specific, and include enough context for the AI to use the tool correctly.

### Node Tools (`tools/node.py`)

#### `nautilus_node_status`

Get the current status and health of the NautilusTrader node.

- **Risk level**: READ
- **API call**: `GET /api/v1/node/status`

**Input schema:**
```json
{
  "type": "object",
  "properties": {},
  "required": []
}
```

**Output:** Formatted text with node status including trader ID, environment, state, uptime, and component states.

**Example invocation:**
```
Tool: nautilus_node_status
Input: {}
Output:
  Node Status:
    Trader ID: TRADER-001
    Environment: LIVE
    State: RUNNING
    Uptime: 2h 15m 30s
    Components:
      DataEngine: RUNNING
      RiskEngine: RUNNING
      ExecutionEngine: RUNNING
    Strategies: 3 (2 running, 1 stopped)
    Actors: 1
```

#### `nautilus_node_stop`

Stop the NautilusTrader node gracefully.

- **Risk level**: CRITICAL
- **Safety**: Always requires confirmation regardless of safety level
- **API call**: `POST /api/v1/node/stop`

**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "timeout_seconds": {
      "type": "integer",
      "description": "Seconds to wait for graceful shutdown before forcing",
      "default": 30
    },
    "confirm": {
      "type": "boolean",
      "description": "Must be true to confirm the stop action"
    }
  },
  "required": ["confirm"]
}
```

**Output:** Confirmation message or error if `confirm` is not true.

### Strategy Tools (`tools/strategies.py`)

#### `nautilus_list_strategies`

List all strategies with their current state.

- **Risk level**: READ
- **API call**: `GET /api/v1/strategies`

**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "state": {
      "type": "string",
      "enum": ["RUNNING", "STOPPED", "INITIALIZED", "DISPOSED"],
      "description": "Filter by strategy state"
    }
  },
  "required": []
}
```

**Output:** Formatted table of strategies with ID, type, state, order count, and position count.

#### `nautilus_create_strategy`

Create a new strategy from a configuration.

- **Risk level**: WRITE
- **API call**: `POST /api/v1/strategies`

**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "strategy_path": {
      "type": "string",
      "description": "Importable path to the strategy class (e.g., 'mypackage.strategies:MyStrategy')"
    },
    "config_path": {
      "type": "string",
      "description": "Importable path to the strategy config class (e.g., 'mypackage.strategies:MyStrategyConfig')"
    },
    "config": {
      "type": "object",
      "description": "Strategy configuration parameters as a JSON object"
    },
    "start": {
      "type": "boolean",
      "description": "Whether to start the strategy immediately after creation",
      "default": false
    }
  },
  "required": ["strategy_path", "config_path", "config"]
}
```

#### `nautilus_start_strategy`

Start a stopped or initialized strategy.

- **Risk level**: WRITE
- **API call**: `POST /api/v1/strategies/{strategy_id}/start`

**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "strategy_id": {
      "type": "string",
      "description": "The strategy ID to start (e.g., 'EMACross-001')"
    }
  },
  "required": ["strategy_id"]
}
```

#### `nautilus_stop_strategy`

Stop a running strategy.

- **Risk level**: WRITE
- **API call**: `POST /api/v1/strategies/{strategy_id}/stop`

**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "strategy_id": {
      "type": "string",
      "description": "The strategy ID to stop"
    }
  },
  "required": ["strategy_id"]
}
```

#### `nautilus_remove_strategy`

Remove a strategy from the trader. Strategy must be stopped first.

- **Risk level**: CRITICAL (in LIVE environment), WRITE (otherwise)
- **API call**: `DELETE /api/v1/strategies/{strategy_id}`

**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "strategy_id": {
      "type": "string",
      "description": "The strategy ID to remove"
    },
    "confirm": {
      "type": "boolean",
      "description": "Must be true to confirm removal in LIVE environment"
    }
  },
  "required": ["strategy_id"]
}
```

#### `nautilus_market_exit_strategy`

Market exit all positions managed by a strategy. This submits market orders to close all open positions.

- **Risk level**: CRITICAL
- **Safety**: Always requires confirmation
- **API call**: `POST /api/v1/strategies/{strategy_id}/market-exit`

**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "strategy_id": {
      "type": "string",
      "description": "The strategy ID to market exit"
    },
    "confirm": {
      "type": "boolean",
      "description": "Must be true to confirm market exit"
    }
  },
  "required": ["strategy_id", "confirm"]
}
```

### Order Tools (`tools/orders.py`)

#### `nautilus_list_orders`

List orders with optional filtering.

- **Risk level**: READ
- **API call**: `GET /api/v1/orders`

**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "status": {
      "type": "string",
      "enum": ["open", "closed", "all"],
      "description": "Filter by order status",
      "default": "all"
    },
    "strategy_id": {
      "type": "string",
      "description": "Filter by strategy ID"
    },
    "instrument_id": {
      "type": "string",
      "description": "Filter by instrument ID"
    },
    "limit": {
      "type": "integer",
      "description": "Maximum number of orders to return",
      "default": 50
    }
  },
  "required": []
}
```

#### `nautilus_get_order`

Get detailed information about a specific order including its event history.

- **Risk level**: READ
- **API call**: `GET /api/v1/orders/{client_order_id}`

**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "client_order_id": {
      "type": "string",
      "description": "The client order ID (e.g., 'O-20231114-001')"
    }
  },
  "required": ["client_order_id"]
}
```

#### `nautilus_submit_order`

Submit a new order to the trading system. The order passes through risk checks before being sent to the venue.

- **Risk level**: CRITICAL
- **Safety**: Requires confirmation in STANDARD and STRICT modes
- **API call**: `POST /api/v1/orders`

**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "instrument_id": {
      "type": "string",
      "description": "Full instrument ID (e.g., 'BTCUSDT-PERP.BINANCE')"
    },
    "side": {
      "type": "string",
      "enum": ["BUY", "SELL"],
      "description": "Order side"
    },
    "order_type": {
      "type": "string",
      "enum": ["MARKET", "LIMIT", "STOP_MARKET", "STOP_LIMIT"],
      "description": "Order type"
    },
    "quantity": {
      "type": "string",
      "description": "Order quantity as a decimal string (e.g., '0.01')"
    },
    "price": {
      "type": "string",
      "description": "Limit price as a decimal string. Required for LIMIT and STOP_LIMIT orders."
    },
    "trigger_price": {
      "type": "string",
      "description": "Trigger price for STOP_MARKET and STOP_LIMIT orders."
    },
    "time_in_force": {
      "type": "string",
      "enum": ["GTC", "IOC", "FOK", "DAY", "GTD"],
      "description": "Time in force (default: GTC)",
      "default": "GTC"
    },
    "strategy_id": {
      "type": "string",
      "description": "Strategy to attribute this order to"
    },
    "reduce_only": {
      "type": "boolean",
      "description": "Whether this order should only reduce an existing position",
      "default": false
    },
    "post_only": {
      "type": "boolean",
      "description": "Whether this order should only add liquidity (maker only)",
      "default": false
    },
    "confirm": {
      "type": "boolean",
      "description": "Must be true to confirm order submission"
    }
  },
  "required": ["instrument_id", "side", "order_type", "quantity", "confirm"]
}
```

**Pre-submission validation (in MCP server):**
1. If `max_order_quantity` is configured, reject orders exceeding it.
2. If `allowed_instruments` is configured, reject orders for unlisted instruments.
3. If `blocked_instruments` is configured, reject orders for blocked instruments.
4. If `read_only` is true, reject all orders.
5. If `confirm` is not true (and safety level requires it), return a confirmation prompt instead of submitting.

**Output:** Order submission result including client_order_id and status, or a confirmation prompt with order details and estimated notional value.

#### `nautilus_cancel_order`

Cancel an open order.

- **Risk level**: WRITE
- **API call**: `DELETE /api/v1/orders/{client_order_id}`

**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "client_order_id": {
      "type": "string",
      "description": "The client order ID to cancel"
    }
  },
  "required": ["client_order_id"]
}
```

#### `nautilus_modify_order`

Modify an open order's quantity or price.

- **Risk level**: WRITE
- **API call**: `PATCH /api/v1/orders/{client_order_id}`

**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "client_order_id": {
      "type": "string",
      "description": "The client order ID to modify"
    },
    "quantity": {
      "type": "string",
      "description": "New quantity as a decimal string"
    },
    "price": {
      "type": "string",
      "description": "New price as a decimal string"
    }
  },
  "required": ["client_order_id"]
}
```

#### `nautilus_cancel_all_orders`

Cancel all open orders, optionally filtered by instrument or strategy.

- **Risk level**: CRITICAL
- **Safety**: Always requires confirmation
- **API call**: `POST /api/v1/orders/cancel-all`

**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "instrument_id": {
      "type": "string",
      "description": "Only cancel orders for this instrument"
    },
    "strategy_id": {
      "type": "string",
      "description": "Only cancel orders from this strategy"
    },
    "confirm": {
      "type": "boolean",
      "description": "Must be true to confirm cancellation"
    }
  },
  "required": ["confirm"]
}
```

### Portfolio Tools (`tools/portfolio.py`)

#### `nautilus_get_portfolio_summary`

Get a comprehensive portfolio overview including balances, positions, and P&L.

- **Risk level**: READ
- **API call**: `GET /api/v1/portfolio`

**Input schema:**
```json
{
  "type": "object",
  "properties": {},
  "required": []
}
```

**Output:** Formatted summary with balances table, positions table, and P&L summary.

#### `nautilus_get_balances`

Get account balances, optionally filtered by venue.

- **Risk level**: READ
- **API call**: `GET /api/v1/portfolio/balances`

**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "venue": {
      "type": "string",
      "description": "Filter balances by venue (e.g., 'BINANCE')"
    }
  },
  "required": []
}
```

#### `nautilus_get_positions`

Get open positions with unrealized and realized P&L.

- **Risk level**: READ
- **API call**: `GET /api/v1/portfolio/positions`

**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "instrument_id": {
      "type": "string",
      "description": "Filter by instrument ID"
    },
    "venue": {
      "type": "string",
      "description": "Filter by venue"
    }
  },
  "required": []
}
```

#### `nautilus_get_pnl`

Get realized and unrealized P&L breakdown.

- **Risk level**: READ
- **API call**: `GET /api/v1/portfolio/pnl`

**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "venue": {
      "type": "string",
      "description": "Filter by venue"
    }
  },
  "required": []
}
```

#### `nautilus_get_exposure`

Get net exposure by instrument and venue.

- **Risk level**: READ
- **API call**: `GET /api/v1/portfolio/exposure`

**Input schema:**
```json
{
  "type": "object",
  "properties": {},
  "required": []
}
```

### Market Data Tools (`tools/market_data.py`)

#### `nautilus_list_instruments`

List available instruments with optional search filtering.

- **Risk level**: READ
- **API call**: `GET /api/v1/cache/instruments`

**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "venue": {
      "type": "string",
      "description": "Filter by venue"
    },
    "search": {
      "type": "string",
      "description": "Search instruments by symbol (case-insensitive)"
    },
    "instrument_type": {
      "type": "string",
      "description": "Filter by instrument type (e.g., 'CryptoPerpetual', 'CurrencyPair')"
    },
    "limit": {
      "type": "integer",
      "description": "Maximum number of instruments to return",
      "default": 50
    }
  },
  "required": []
}
```

#### `nautilus_get_instrument`

Get detailed information about a specific instrument including tick size, lot size, and trading constraints.

- **Risk level**: READ
- **API call**: `GET /api/v1/cache/instruments/{instrument_id}`

**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "instrument_id": {
      "type": "string",
      "description": "Full instrument ID (e.g., 'BTCUSDT-PERP.BINANCE')"
    }
  },
  "required": ["instrument_id"]
}
```

#### `nautilus_get_latest_quote`

Get the latest bid/ask quote for an instrument.

- **Risk level**: READ
- **API call**: `GET /api/v1/data/quotes/{instrument_id}`

**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "instrument_id": {
      "type": "string",
      "description": "Instrument ID to get the quote for"
    }
  },
  "required": ["instrument_id"]
}
```

#### `nautilus_get_latest_bars`

Get recent OHLCV bars for an instrument.

- **Risk level**: READ
- **API call**: `GET /api/v1/data/bars/{instrument_id}`

**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "instrument_id": {
      "type": "string",
      "description": "Instrument ID"
    },
    "bar_type": {
      "type": "string",
      "description": "Full bar type string (e.g., 'BTCUSDT-PERP.BINANCE-1-MINUTE-LAST-EXTERNAL')"
    },
    "count": {
      "type": "integer",
      "description": "Number of bars to return (default: 10, max: 100)",
      "default": 10
    }
  },
  "required": ["instrument_id", "bar_type"]
}
```

### Risk Tools (`tools/risk.py`)

#### `nautilus_get_risk_state`

Get the current risk engine state, trading state, and active risk limits.

- **Risk level**: READ
- **API call**: `GET /api/v1/risk/state`

**Input schema:**
```json
{
  "type": "object",
  "properties": {},
  "required": []
}
```

#### `nautilus_set_risk_limits`

Update risk engine parameters and limits.

- **Risk level**: CRITICAL
- **Safety**: Always requires confirmation
- **API call**: `PUT /api/v1/risk/limits`

**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "max_order_submit_rate": {
      "type": "string",
      "description": "Maximum order submission rate (e.g., '10/00:00:01' for 10 per second)"
    },
    "max_notional_per_order": {
      "type": "object",
      "description": "Maximum notional value per order, keyed by instrument ID",
      "additionalProperties": {"type": "string"}
    },
    "confirm": {
      "type": "boolean",
      "description": "Must be true to confirm risk limit changes"
    }
  },
  "required": ["confirm"]
}
```

## MCP Resources

Resources provide read-only snapshots of trading system state that can be included in LLM context.

### `nautilus://status`

Node status snapshot. Auto-refreshes every 30 seconds.

```json
{
  "uri": "nautilus://status",
  "name": "Trading Node Status",
  "description": "Current state of the NautilusTrader node including uptime, environment, and component health",
  "mimeType": "application/json"
}
```

### `nautilus://portfolio`

Portfolio state snapshot. Auto-refreshes every 10 seconds.

```json
{
  "uri": "nautilus://portfolio",
  "name": "Portfolio State",
  "description": "Current portfolio state including balances, open positions, and P&L",
  "mimeType": "application/json"
}
```

### `nautilus://events`

Recent event history. Supports cursor-based pagination.

```json
{
  "uri": "nautilus://events",
  "name": "Recent Events",
  "description": "Recent trading events (orders, positions, risk) from the last 5 minutes",
  "mimeType": "application/json"
}
```

## Safety Guardrails (`safety.py`)

### Safety Levels

| Level          | Behavior                                                                                       |
|----------------|-----------------------------------------------------------------------------------------------|
| `UNRESTRICTED` | No confirmation required for any action. Suitable for backtesting and paper trading.          |
| `STANDARD`     | Confirmation required for: order submission, strategy removal, market exit, cancel all, node stop. Default. |
| `STRICT`       | Confirmation required for ALL mutations. Read-only mode available.                            |

### Risk Levels Per Tool

Each tool is annotated with a risk level that determines confirmation behavior:

| Risk Level | Description                          | UNRESTRICTED | STANDARD        | STRICT          |
|------------|--------------------------------------|--------------|-----------------|-----------------|
| `READ`     | Read-only queries, no state changes | No confirm   | No confirm      | No confirm      |
| `WRITE`    | State mutations (start/stop/modify) | No confirm   | No confirm      | Confirm required |
| `CRITICAL` | Dangerous operations (orders, exits)| No confirm   | Confirm required | Confirm required |

### Environment Auto-Escalation

When the MCP server detects (via `nautilus_node_status`) that the trading node is running in `LIVE` environment:

- `UNRESTRICTED` is escalated to `STANDARD`
- `STANDARD` remains `STANDARD`
- `STRICT` remains `STRICT`

This prevents accidental unguarded operations on live trading systems. The escalation is logged as a warning.

### Confirmation Protocol

When a tool requires confirmation:

1. The tool is called without `confirm: true`.
2. The tool returns a detailed summary of what the action will do, including:
   - The specific action being taken
   - Affected resources (instrument, strategy, order)
   - Estimated impact (notional value, number of positions affected)
   - Current portfolio/position context
3. The LLM presents this to the user and asks for confirmation.
4. If confirmed, the tool is called again with `confirm: true`.
5. The action is executed.

Example flow for order submission:
```
User: "Buy 0.5 BTC on Binance"

AI calls: nautilus_submit_order(instrument_id="BTCUSDT-PERP.BINANCE", side="BUY", order_type="MARKET", quantity="0.5")

Tool returns:
  "Order confirmation required:
   Action: BUY 0.5 BTCUSDT-PERP.BINANCE @ MARKET
   Estimated notional: ~$21,050 (at current price $42,100)
   Current position: LONG 0.05 (avg entry $42,150.50)
   After fill: LONG 0.55

   Call this tool again with confirm=true to submit."

AI: "I'd like to submit a market buy order for 0.5 BTC on Binance perpetual. The estimated notional value is approximately $21,050 at the current price of $42,100. This would increase your existing long position from 0.05 to 0.55 BTC. Shall I proceed?"

User: "Yes"

AI calls: nautilus_submit_order(..., confirm=true)
```

### Guardrail Validation

```python
class SafetyGuardrails:
    """Pre-action validation and confirmation logic."""

    def __init__(self, config: McpServerConfig) -> None: ...

    def validate_order(self, order: dict) -> ValidationResult:
        """
        Validate an order against configured guardrails.

        Checks:
        1. read_only mode
        2. instrument allowlist/blocklist
        3. max_order_quantity
        4. confirmation requirement based on safety level

        Returns ValidationResult with is_valid, requires_confirmation, and rejection_reason.
        """

    def requires_confirmation(self, tool_name: str, risk_level: str) -> bool:
        """Check if a tool invocation requires confirmation at the current safety level."""

    def get_effective_safety_level(self, environment: str) -> str:
        """Get the effective safety level, accounting for environment escalation."""
```

```python
@dataclass
class ValidationResult:
    is_valid: bool
    requires_confirmation: bool
    rejection_reason: str | None = None
    confirmation_message: str | None = None
```

## `.mcp.json` Integration

To register the NautilusTrader MCP server for discovery by Claude Code and other MCP-compatible tools, add the following to `.mcp.json` in the project root or `~/.mcp.json` globally:

### stdio transport (recommended for local use)

```json
{
  "mcpServers": {
    "nautilus-trader": {
      "command": "python",
      "args": ["-m", "nautilus_trader.mcp.server"],
      "env": {
        "NAUTILUS_API_URL": "http://localhost:8001",
        "NAUTILUS_API_KEY": "my-secret-key",
        "NAUTILUS_SAFETY_LEVEL": "STANDARD"
      }
    }
  }
}
```

### With uvx (if published as a package)

```json
{
  "mcpServers": {
    "nautilus-trader": {
      "command": "uvx",
      "args": ["nautilus-trader-mcp"],
      "env": {
        "NAUTILUS_API_URL": "http://localhost:8001",
        "NAUTILUS_API_KEY": "my-secret-key"
      }
    }
  }
}
```

### SSE transport (for remote access)

```json
{
  "mcpServers": {
    "nautilus-trader": {
      "url": "http://trading-server:8002/sse"
    }
  }
}
```

## Tool Output Formatting

All tool outputs are formatted as human-readable text suitable for LLM consumption, not raw JSON. This makes it easier for the AI to interpret and present results naturally.

Example output from `nautilus_get_portfolio_summary`:

```
Portfolio Summary (TRADER-001)
==============================

Balances:
  BINANCE (USDT):
    Total:  50,000.00
    Free:   45,000.00
    Locked:  5,000.00

Open Positions (2):
  BTCUSDT-PERP.BINANCE  LONG  0.05  entry: 42,150.50  unrealized: +125.30 USDT
  ETHUSDT-PERP.BINANCE  SHORT 1.00  entry: 2,250.00   unrealized: -15.20 USDT

P&L:
  Realized:    +1,500.00 USDT
  Unrealized:    +110.10 USDT
  Commissions:   -42.50 USDT
```

For tools that return large datasets (instrument lists, order lists), the output is truncated with a note indicating how many more results are available and how to filter.

## Error Handling

MCP tool errors are returned as tool results with `isError: true`:

```python
@server.tool()
async def nautilus_get_order(client_order_id: str) -> list[TextContent]:
    try:
        result = await client.get(f"/api/v1/orders/{client_order_id}")
        return [TextContent(type="text", text=format_order(result))]
    except NautilusApiError as e:
        if e.status_code == 404:
            return [TextContent(
                type="text",
                text=f"Order '{client_order_id}' not found. Use nautilus_list_orders to see available orders.",
            )]
        raise
```

Error messages include:
- What went wrong
- Suggested next steps or alternative tools to try
- Relevant context (e.g., "Did you mean 'BTCUSDT-PERP.BINANCE'?")
