# ADR-004: Comprehensive CLI for System Control

| Field       | Value                                      |
|-------------|--------------------------------------------|
| **Status**  | Proposed                                   |
| **Date**    | 2026-03-21                                 |
| **Authors** | Mohsen Zainalpour                          |
| **Depends** | ADR-001 (API Server)                       |
| **Relates** | ADR-002 (Event Streaming)                  |

## Context

NautilusTrader's current CLI is minimal. The only entry point is `python -m nautilus_trader.live` (`nautilus_trader/live/__main__.py`), which uses Click and accepts two options:
- `--raw <json>` — raw JSON configuration string
- `--fsspec-url <url>` — remote configuration file URL

This CLI can only **start** a trading node. Once running, there is no way to interact with the node from the command line. Operators cannot:
- Check if the node is healthy
- List or manage strategies
- View portfolio state or open positions
- Submit or cancel orders
- Stream events to a terminal
- Script any management operations

This is a significant gap for production operations where shell-level access is the primary interface for:
- **Monitoring scripts** that check node health and alert on anomalies
- **CI/CD pipelines** that deploy and verify strategy configurations
- **Incident response** where operators need to quickly cancel orders or stop strategies
- **Automation** where cron jobs or shell scripts manage trading schedules
- **Development** where engineers test strategy configurations without writing Python

With the REST API (ADR-001) in place, a comprehensive CLI becomes a thin client that translates command-line arguments into HTTP requests.

## Decision

**Extend the CLI using Click to provide comprehensive control over a running NautilusTrader node by wrapping the REST API (ADR-001).** The CLI is implemented in a new module `nautilus_trader/cli/` and installed as a console entry point `nautilus`.

### Command Groups

```
nautilus
├── node
│   ├── start         # Start a trading node from config
│   ├── stop          # Stop a running node
│   ├── status        # Show node status
│   └── config        # Show current configuration
├── strategy
│   ├── list          # List all strategies
│   ├── create        # Create from config JSON/file
│   ├── start         # Start a strategy
│   ├── stop          # Stop a strategy
│   ├── remove        # Remove a strategy
│   ├── market-exit   # Market-exit all positions
│   └── state         # Detailed strategy state
├── order
│   ├── list          # List orders (with filters)
│   ├── get           # Get order details
│   ├── submit        # Submit a new order
│   ├── cancel        # Cancel an order
│   ├── modify        # Modify quantity/price
│   └── cancel-all    # Cancel all orders
├── portfolio
│   ├── summary       # Full portfolio overview
│   ├── balances      # Account balances
│   ├── positions     # Open positions
│   ├── pnl           # Realized + unrealized P&L
│   └── exposure      # Net exposures
├── risk
│   ├── state         # Risk engine state
│   └── limits        # View/update risk limits
├── market
│   ├── instruments   # List instruments
│   ├── quote         # Latest quote
│   └── bars          # Recent bars
└── events
    └── stream        # Live event stream to terminal
```

### Output Formats

All commands support `--format` flag:
- `table` (default) — Pretty-printed tables using `rich` for terminal rendering
- `json` — Raw JSON for scripting and piping to `jq`
- `csv` — CSV output for spreadsheet import

### Connection Configuration

Global options on every command:
- `--host` (default: `localhost`)
- `--port` (default: `8001`)
- `--api-key` (default: from config file or env var)
- `--no-color` — disable colored output
- `-v / --verbose` — verbose output with request/response details

Persistent configuration via `~/.nautilus/cli.toml`:
```toml
[connection]
host = "localhost"
port = 8001
api_key = "sk-..."

[output]
format = "table"
color = true
```

Environment variables: `NAUTILUS_HOST`, `NAUTILUS_PORT`, `NAUTILUS_API_KEY`.

Priority: CLI flags > environment variables > config file > defaults.

### Destructive Operation Safety

Commands that modify state require explicit confirmation:
- `nautilus order cancel-all` — prompts "Cancel N open orders? [y/N]"
- `nautilus strategy market-exit` — prompts "Market-exit strategy X with N open positions? [y/N]"
- `nautilus node stop` — prompts "Stop trading node TRADER-001? [y/N]"

Bypass with `--yes` / `-y` flag for scripting.

### Event Streaming

`nautilus events stream` connects to the WebSocket endpoint (ADR-002) and prints events to stdout:

```bash
# Pretty-printed event stream
nautilus events stream --topics "events.order.*,events.position.*"

# JSON stream for piping
nautilus events stream --format json | jq '.data'

# Filter to specific instruments
nautilus events stream --topics "events.order.*" --format json
```

## Consequences

### Positive

- **Scriptable**: All operations composable with standard Unix tools (grep, jq, awk, cron).
- **Zero new dependencies for users**: Click is already a dependency. `rich` is the only new optional dependency for table formatting.
- **CI/CD integration**: Strategies can be deployed, verified, and managed in automated pipelines.
- **Incident response**: Operators can quickly act on running nodes without Python scripting.
- **Shell completions**: Click supports bash/zsh/fish completion generation out of the box via `nautilus --install-completion`.

### Negative

- **API sync**: CLI commands must stay in sync with the REST API. Mitigation: CLI commands are thin wrappers — most logic is a single HTTP call.
- **Another surface to test**: Each CLI command needs testing. Mitigation: integration tests that start a node and exercise CLI commands against it.
- **Limited interactivity**: CLI is command-based, not a REPL. For interactive exploration, users should use Claude via MCP (ADR-003).

### Neutral

- The existing `python -m nautilus_trader.live` entry point is preserved unchanged. The new CLI is a superset.
- Click was chosen over alternatives (argparse, typer) because it's already a project dependency and its group/command pattern maps naturally to the API structure.
