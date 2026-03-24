# ADR-003: MCP Server for Claude Integration

| Field       | Value                                      |
|-------------|--------------------------------------------|
| **Status**  | Proposed                                   |
| **Date**    | 2026-03-21                                 |
| **Authors** | Mohsen Zainalpour                          |
| **Depends** | ADR-001 (API Server), ADR-002 (Event Streaming) |
| **Relates** | ADR-005 (Agent Orchestration)              |

## Context

With the REST API (ADR-001) and event streaming (ADR-002) in place, NautilusTrader becomes programmatically accessible from external processes. However, AI agents — particularly Claude via Claude Code — interact with external systems through the **Model Context Protocol (MCP)**, not raw HTTP calls.

MCP is Anthropic's open standard for connecting AI models to external tools and data sources. An MCP server exposes three primitives:
- **Tools**: Callable functions with JSON Schema input/output definitions (e.g., `nautilus_submit_order`)
- **Resources**: Readable data endpoints with URI schemes (e.g., `nautilus://portfolio`)
- **Prompts**: Reusable prompt templates for common workflows

When Claude Code discovers an MCP server (via `.mcp.json` at the project root), it automatically makes the server's tools available as callable functions during conversations. This enables natural interactions like:

> "Show me all open positions and their unrealized P&L"
> "Start the EMACross strategy on BTCUSDT with a 10/20 period configuration"
> "Cancel all open orders for the momentum strategy"

Without an MCP server, an operator would need to manually construct HTTP requests, manage authentication, and interpret raw JSON responses. The MCP layer translates between Claude's natural language tool-calling interface and NautilusTrader's structured API.

### Why MCP Over Direct API Calls

| Aspect              | Direct API (curl/httpx) | MCP Server              |
|----------------------|------------------------|--------------------------|
| Tool discovery       | Manual (read docs)     | Automatic (schema)       |
| Input validation     | Client-side            | Schema-enforced          |
| Safety guardrails    | None                   | Built-in confirmation    |
| AI integration       | Prompt engineering     | Native tool use          |
| Context management   | Manual                 | Resources + cursors      |
| Multi-agent reuse    | Custom per agent       | Standard protocol        |

## Decision

**Create a standalone MCP server (`nautilus_trader/mcp/`) that connects to the NautilusTrader API server and exposes trading operations as MCP tools with built-in safety guardrails.**

The MCP server:
- Runs as a separate process (or as a subprocess spawned by Claude Code)
- Communicates with NautilusTrader via the REST API + WebSocket (ADR-001, ADR-002)
- Implements safety guardrails that are environment-aware (SANDBOX vs LIVE)
- Is discoverable via `.mcp.json` for Claude Code integration

### Tool Categories

#### Node Management
| Tool                    | Description                     | Risk Level |
|-------------------------|---------------------------------|------------|
| `nautilus_node_status`  | Get node health and state       | READ       |
| `nautilus_node_stop`    | Stop the trading node           | CRITICAL   |

#### Strategy Management
| Tool                           | Description                              | Risk Level |
|--------------------------------|------------------------------------------|------------|
| `nautilus_list_strategies`     | List all strategies with state           | READ       |
| `nautilus_create_strategy`     | Create strategy from config              | WRITE      |
| `nautilus_start_strategy`      | Start a stopped strategy                 | WRITE      |
| `nautilus_stop_strategy`       | Stop a running strategy                  | WRITE      |
| `nautilus_remove_strategy`     | Remove strategy from trader              | CRITICAL   |
| `nautilus_market_exit_strategy`| Market-exit all positions for strategy   | CRITICAL   |

#### Order Management
| Tool                         | Description                        | Risk Level |
|------------------------------|------------------------------------|------------|
| `nautilus_list_orders`       | List orders with filters           | READ       |
| `nautilus_get_order`         | Get order details                  | READ       |
| `nautilus_submit_order`      | Submit a new order                 | WRITE      |
| `nautilus_cancel_order`      | Cancel an open order               | WRITE      |
| `nautilus_modify_order`      | Modify order quantity/price        | WRITE      |
| `nautilus_cancel_all_orders` | Cancel all open orders             | CRITICAL   |

#### Portfolio & Market Data
| Tool                         | Description                        | Risk Level |
|------------------------------|------------------------------------|------------|
| `nautilus_get_portfolio`     | Full portfolio summary             | READ       |
| `nautilus_get_balances`      | Account balances by venue          | READ       |
| `nautilus_get_positions`     | Open positions with P&L            | READ       |
| `nautilus_get_pnl`           | Realized and unrealized P&L        | READ       |
| `nautilus_get_exposure`      | Net exposure by instrument/venue   | READ       |
| `nautilus_list_instruments`  | List available instruments         | READ       |
| `nautilus_get_instrument`    | Get instrument details             | READ       |
| `nautilus_get_latest_quote`  | Latest quote for instrument        | READ       |
| `nautilus_get_latest_bars`   | Recent bars for instrument         | READ       |

#### Risk Management
| Tool                         | Description                        | Risk Level |
|------------------------------|------------------------------------|------------|
| `nautilus_get_risk_state`    | Current risk engine state          | READ       |
| `nautilus_set_risk_limits`   | Update risk parameters             | CRITICAL   |

### MCP Resources

| Resource URI            | Description                              |
|-------------------------|------------------------------------------|
| `nautilus://status`     | Node status snapshot (auto-refreshing)   |
| `nautilus://portfolio`  | Portfolio state snapshot                  |
| `nautilus://events`     | Event stream cursor (paginated history)  |

### Safety Guardrails

Safety is implemented at the MCP layer, independent of the API server's own authentication. Three safety levels are supported:

| Level          | READ tools | WRITE tools          | CRITICAL tools            |
|----------------|------------|----------------------|---------------------------|
| `UNRESTRICTED` | Allowed    | Allowed              | Allowed                   |
| `STANDARD`     | Allowed    | Allowed              | Confirmation required     |
| `STRICT`       | Allowed    | Confirmation required| Confirmation required      |

**Environment awareness**: When the connected NautilusTrader node is in `LIVE` environment (as opposed to `SANDBOX`), the safety level is automatically escalated by one tier (e.g., `STANDARD` becomes `STRICT` for LIVE).

**Confirmation mechanism**: For tools requiring confirmation, the MCP server returns a response asking Claude to confirm the action with the user before proceeding. The tool includes a `confirm` parameter that must be set to `true` on the second invocation.

**Additional guardrails**:
- `read_only` mode: When enabled, all WRITE and CRITICAL tools return errors.
- `allowed_instruments`: Restrict order submission to a specific set of instruments.
- `max_order_quantity`: Cap the maximum quantity for any single order.
- `allowed_tools` / `blocked_tools`: Allowlist or blocklist specific tools.

### Configuration

```python
class McpServerConfig(NautilusConfig, frozen=True):
    api_url: str = "http://127.0.0.1:8001"
    api_key: str | None = None
    safety_level: str = "STANDARD"  # UNRESTRICTED, STANDARD, STRICT
    allowed_tools: list[str] | None = None
    blocked_tools: list[str] | None = None
    read_only: bool = False
    max_order_quantity: str | None = None
    allowed_instruments: list[str] | None = None
```

### `.mcp.json` Integration

Claude Code discovers MCP servers via `.mcp.json` at the project root:

```json
{
  "mcpServers": {
    "nautilus-trader": {
      "command": "python",
      "args": ["-m", "nautilus_trader.mcp"],
      "env": {
        "NAUTILUS_API_URL": "http://127.0.0.1:8001",
        "NAUTILUS_API_KEY": "",
        "NAUTILUS_SAFETY_LEVEL": "STANDARD"
      }
    }
  }
}
```

## Consequences

### Positive

- **Natural language trading**: Claude can execute trading operations through conversation, with full tool discovery and schema validation.
- **Safety by design**: Built-in confirmation prompts and environment-aware restrictions prevent accidental destructive actions.
- **Reusable**: The MCP server works with any MCP-compatible AI client, not just Claude Code.
- **Structured discovery**: AI agents automatically discover available operations without documentation lookup.
- **Composable**: Multiple MCP servers can coexist — NautilusTrader tools alongside database tools, monitoring tools, etc.

### Negative

- **Additional process**: The MCP server is a separate process that must be running alongside the trading node.
- **Latency**: An MCP tool call traverses: Claude → MCP server → HTTP → API server → Kernel, adding ~10-50ms per call compared to in-process access. This is acceptable for control operations but unsuitable for high-frequency trading decisions.
- **Schema sync**: MCP tool definitions must stay in sync with the REST API. Mitigation: generate tool schemas from the OpenAPI spec.
- **Token costs**: Each tool call consumes Claude API tokens. Complex multi-step workflows (e.g., "rebalance portfolio to target weights") may require many tool calls.

### Neutral

- The MCP server is optional — NautilusTrader functions identically without it.
- MCP is an open standard with growing ecosystem support, reducing vendor lock-in risk.
