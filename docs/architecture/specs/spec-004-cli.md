# SPEC-004: Comprehensive CLI

## Overview

The NautilusTrader CLI provides a command-line interface for managing and querying a running NautilusTrader node. It communicates with the node exclusively through the REST API (SPEC-001), making it a thin client that can run from any machine with network access to the trading node.

The CLI is built with [Click](https://click.palletsprojects.com/) for command parsing and argument handling, and uses [Rich](https://rich.readthedocs.io/) for formatted table output in the terminal. It supports multiple output formats (table, JSON, CSV) for integration with shell scripts and other tools.

## Module Structure

```
nautilus_trader/cli/
├── __init__.py
├── main.py            # Click CLI app entry point
├── commands/
│   ├── __init__.py
│   ├── node.py        # Node management commands
│   ├── strategy.py    # Strategy management commands
│   ├── order.py       # Order management commands
│   ├── portfolio.py   # Portfolio query commands
│   ├── risk.py        # Risk management commands
│   ├── market.py      # Market data commands
│   └── events.py      # Event streaming commands
├── client.py          # HTTP client for API communication
├── output.py          # Output formatting (table, json, csv)
└── config.py          # CLI configuration (connection settings)
```

## Entry Point

The CLI is accessible via two methods:

1. **Module execution**: `python -m nautilus_trader.cli`
2. **Console script**: `nautilus` (registered via `pyproject.toml` / `setup.cfg` console_scripts entry point)

```toml
# pyproject.toml
[project.scripts]
nautilus = "nautilus_trader.cli.main:cli"
```

## CLI Architecture

### `main.py`

The top-level Click group that aggregates all command groups.

```python
import click

from nautilus_trader.cli.commands import events, market, node, order, portfolio, risk, strategy
from nautilus_trader.cli.config import load_config


@click.group()
@click.option("--host", default=None, help="API server host (default: from config or localhost)")
@click.option("--port", default=None, type=int, help="API server port (default: from config or 8001)")
@click.option("--api-key", default=None, help="API key for authentication")
@click.option("--format", "output_format", type=click.Choice(["table", "json", "csv"]), default=None,
              help="Output format (default: from config or table)")
@click.option("--no-color", is_flag=True, default=False, help="Disable colored output")
@click.option("-v", "--verbose", is_flag=True, default=False, help="Enable verbose output")
@click.pass_context
def cli(ctx: click.Context, host, port, api_key, output_format, no_color, verbose):
    """NautilusTrader CLI — manage and query a running trading node."""
    config = load_config()

    # CLI flags override config file values
    ctx.ensure_object(dict)
    ctx.obj["host"] = host or config.get("host", "localhost")
    ctx.obj["port"] = port or config.get("port", 8001)
    ctx.obj["api_key"] = api_key or config.get("api_key")
    ctx.obj["format"] = output_format or config.get("format", "table")
    ctx.obj["no_color"] = no_color or config.get("no_color", False)
    ctx.obj["verbose"] = verbose


cli.add_command(node.node)
cli.add_command(strategy.strategy)
cli.add_command(order.order)
cli.add_command(portfolio.portfolio)
cli.add_command(risk.risk)
cli.add_command(market.market)
cli.add_command(events.events)
```

### `client.py`

Synchronous HTTP client for API communication. Uses `httpx` in synchronous mode (CLI commands are not async).

```python
import httpx
import sys


class ApiClient:
    """Synchronous HTTP client for the NautilusTrader REST API."""

    def __init__(self, host: str, port: int, api_key: str | None = None) -> None:
        self._base_url = f"http://{host}:{port}"
        self._headers = {}
        if api_key:
            self._headers["X-Api-Key"] = api_key

    def get(self, path: str, params: dict | None = None) -> dict:
        """Send a GET request. Exits with error on failure."""
        try:
            response = httpx.get(
                f"{self._base_url}{path}",
                params=params,
                headers=self._headers,
                timeout=30.0,
            )
            return self._handle_response(response)
        except httpx.ConnectError:
            click.echo(f"Error: Cannot connect to {self._base_url}. Is the trading node running?", err=True)
            sys.exit(1)

    def post(self, path: str, json: dict | None = None) -> dict: ...
    def put(self, path: str, json: dict | None = None) -> dict: ...
    def patch(self, path: str, json: dict | None = None) -> dict: ...
    def delete(self, path: str) -> dict: ...

    def _handle_response(self, response: httpx.Response) -> dict:
        """Handle HTTP response, exiting with formatted error on non-2xx."""
        if response.status_code >= 400:
            try:
                error_body = response.json()
                click.echo(f"Error ({response.status_code}): {error_body.get('error', 'Unknown error')}", err=True)
                detail = error_body.get("detail")
                if detail:
                    click.echo(f"Detail: {detail}", err=True)
            except Exception:
                click.echo(f"Error ({response.status_code}): {response.text}", err=True)
            sys.exit(1)
        return response.json()
```

A helper function creates the client from the Click context:

```python
def get_client(ctx: click.Context) -> ApiClient:
    """Create an ApiClient from Click context."""
    return ApiClient(
        host=ctx.obj["host"],
        port=ctx.obj["port"],
        api_key=ctx.obj["api_key"],
    )
```

### `output.py`

Output formatting utilities that render API responses in different formats.

```python
from rich.console import Console
from rich.table import Table
import csv
import io
import json


class OutputFormatter:
    """Format API responses for terminal output."""

    def __init__(self, format: str, no_color: bool = False) -> None:
        self._format = format
        self._console = Console(no_color=no_color)

    def render_table(self, data: list[dict], columns: list[str], title: str | None = None) -> None:
        """Render data as a formatted table, JSON, or CSV based on configured format."""
        if self._format == "json":
            self._console.print_json(json.dumps(data, indent=2))
        elif self._format == "csv":
            self._render_csv(data, columns)
        else:
            self._render_rich_table(data, columns, title)

    def render_dict(self, data: dict, title: str | None = None) -> None:
        """Render a single dict as key-value pairs."""
        if self._format == "json":
            self._console.print_json(json.dumps(data, indent=2))
        elif self._format == "csv":
            writer = csv.writer(sys.stdout)
            writer.writerow(["key", "value"])
            for k, v in data.items():
                writer.writerow([k, v])
        else:
            if title:
                self._console.print(f"\n[bold]{title}[/bold]")
            for key, value in data.items():
                self._console.print(f"  {key}: {value}")

    def render_message(self, message: str) -> None:
        """Render a simple message."""
        if self._format == "json":
            self._console.print_json(json.dumps({"message": message}))
        else:
            self._console.print(message)

    def _render_rich_table(self, data: list[dict], columns: list[str], title: str | None) -> None:
        table = Table(title=title, show_header=True, header_style="bold")
        for col in columns:
            table.add_column(col)
        for row in data:
            table.add_row(*[str(row.get(col, "")) for col in columns])
        self._console.print(table)

    def _render_csv(self, data: list[dict], columns: list[str]) -> None:
        writer = csv.DictWriter(sys.stdout, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(data)
```

A helper creates the formatter from Click context:

```python
def get_formatter(ctx: click.Context) -> OutputFormatter:
    return OutputFormatter(
        format=ctx.obj["format"],
        no_color=ctx.obj["no_color"],
    )
```

### `config.py`

Configuration file loading from `~/.nautilus/cli.toml`.

```python
import tomllib
from pathlib import Path


DEFAULT_CONFIG_PATH = Path.home() / ".nautilus" / "cli.toml"


def load_config(path: Path | None = None) -> dict:
    """
    Load CLI configuration from TOML file.

    Returns a flat dict with connection and output settings.
    Missing file or missing keys return defaults.
    """
    config_path = path or DEFAULT_CONFIG_PATH
    if not config_path.exists():
        return {}

    with open(config_path, "rb") as f:
        raw = tomllib.load(f)

    result = {}
    connection = raw.get("connection", {})
    result["host"] = connection.get("host", "localhost")
    result["port"] = connection.get("port", 8001)
    result["api_key"] = connection.get("api_key")

    output = raw.get("output", {})
    result["format"] = output.get("format", "table")
    result["no_color"] = not output.get("color", True)

    return result
```

## Command Reference

### `nautilus node` — Node Management

#### `nautilus node status`

Show the current node status including trader ID, environment, state, uptime, and component health.

```bash
$ nautilus node status

Node Status
============
  Trader ID:    TRADER-001
  Instance ID:  a1b2c3d4-e5f6-7890-abcd-ef1234567890
  Environment:  LIVE
  State:        RUNNING
  Uptime:       2h 15m 30s

Components:
  DataEngine:      RUNNING
  RiskEngine:      RUNNING
  ExecutionEngine: RUNNING

  Strategies: 3 (2 running, 1 stopped)
  Actors:     1
```

```bash
$ nautilus node status --format json
{
  "trader_id": "TRADER-001",
  "environment": "LIVE",
  "state": "RUNNING",
  "uptime_seconds": 8130.5,
  ...
}
```

**Implementation:**

```python
@click.group()
def node():
    """Manage the trading node."""

@node.command()
@click.pass_context
def status(ctx):
    """Show current node status."""
    client = get_client(ctx)
    fmt = get_formatter(ctx)
    data = client.get("/api/v1/node/status")
    fmt.render_dict(data, title="Node Status")
```

#### `nautilus node stop`

Stop the trading node gracefully.

```bash
$ nautilus node stop
Are you sure you want to stop the trading node? [y/N]: y
Shutdown initiated (timeout: 30s)

$ nautilus node stop --force
Shutdown initiated (timeout: 30s)
```

| Option    | Description                           |
|-----------|---------------------------------------|
| `--force` | Skip confirmation prompt              |
| `--timeout` | Shutdown timeout in seconds (default: 30) |

**Implementation:**

```python
@node.command()
@click.option("--force", is_flag=True, help="Skip confirmation")
@click.option("--timeout", default=30, type=int, help="Shutdown timeout in seconds")
@click.pass_context
def stop(ctx, force, timeout):
    """Stop the trading node."""
    if not force:
        click.confirm("Are you sure you want to stop the trading node?", abort=True)
    client = get_client(ctx)
    fmt = get_formatter(ctx)
    result = client.post("/api/v1/node/stop", json={"timeout_seconds": timeout})
    fmt.render_message(f"Shutdown initiated (timeout: {timeout}s)")
```

#### `nautilus node config`

Show the current node configuration (secrets redacted).

```bash
$ nautilus node config
```

### `nautilus strategy` — Strategy Management

#### `nautilus strategy list`

List all strategies with their state and key metrics.

```bash
$ nautilus strategy list

Strategies
===========
  Strategy ID     Type       State     Orders  Positions
  EMACross-001    EMACross   RUNNING   47      2
  BollingerMR-01  BollingerMR STOPPED  123     0
  GridBot-001     GridBot    RUNNING   1050    5

$ nautilus strategy list --state RUNNING

Strategies (RUNNING)
====================
  Strategy ID     Type       State     Orders  Positions
  EMACross-001    EMACross   RUNNING   47      2
  GridBot-001     GridBot    RUNNING   1050    5
```

| Option    | Description                        |
|-----------|------------------------------------|
| `--state` | Filter by state: RUNNING, STOPPED, etc. |

**Implementation:**

```python
@click.group()
def strategy():
    """Manage trading strategies."""

@strategy.command("list")
@click.option("--state", default=None, help="Filter by strategy state")
@click.pass_context
def list_strategies(ctx, state):
    """List all strategies."""
    client = get_client(ctx)
    fmt = get_formatter(ctx)
    params = {}
    if state:
        params["state"] = state
    data = client.get("/api/v1/strategies", params=params)
    fmt.render_table(
        data["strategies"],
        columns=["strategy_id", "strategy_type", "state", "order_count", "position_count"],
        title="Strategies",
    )
```

#### `nautilus strategy create`

Create a new strategy from a JSON config file or inline JSON.

```bash
$ nautilus strategy create --config strategy_config.json
Strategy created: EMACross-002 (INITIALIZED)

$ nautilus strategy create --config '{"strategy_path":"nautilus_trader.examples.strategies.ema_cross:EMACross","config_path":"nautilus_trader.examples.strategies.ema_cross:EMACrossConfig","config":{"fast_ema_period":10}}'
Strategy created: EMACross-002 (INITIALIZED)

$ nautilus strategy create --config strategy_config.json --start
Strategy created: EMACross-002 (RUNNING)
```

| Option     | Description                                                |
|------------|------------------------------------------------------------|
| `--config` | JSON config: file path or inline JSON string (required)    |
| `--start`  | Start the strategy immediately after creation              |

**Implementation:**

```python
@strategy.command()
@click.option("--config", "config_input", required=True, help="JSON config (file path or inline JSON)")
@click.option("--start", is_flag=True, help="Start immediately after creation")
@click.pass_context
def create(ctx, config_input, start):
    """Create a new strategy from config."""
    client = get_client(ctx)
    fmt = get_formatter(ctx)

    # Try to read as file first, then parse as inline JSON
    config_path = Path(config_input)
    if config_path.exists():
        with open(config_path) as f:
            config_data = json.load(f)
    else:
        try:
            config_data = json.loads(config_input)
        except json.JSONDecodeError:
            click.echo(f"Error: '{config_input}' is not a valid file path or JSON string", err=True)
            sys.exit(1)

    config_data["start"] = start
    result = client.post("/api/v1/strategies", json=config_data)
    fmt.render_message(f"Strategy created: {result['strategy_id']} ({result['state']})")
```

#### `nautilus strategy start <strategy_id>`

Start a stopped or initialized strategy.

```bash
$ nautilus strategy start EMACross-001
Strategy started: EMACross-001
```

#### `nautilus strategy stop <strategy_id>`

Stop a running strategy.

```bash
$ nautilus strategy stop EMACross-001
Strategy stopped: EMACross-001
```

#### `nautilus strategy remove <strategy_id>`

Remove a strategy from the trader. Must be stopped first.

```bash
$ nautilus strategy remove EMACross-001
Are you sure you want to remove strategy EMACross-001? [y/N]: y
Strategy removed: EMACross-001

$ nautilus strategy remove EMACross-001 --force
Strategy removed: EMACross-001
```

| Option    | Description                |
|-----------|----------------------------|
| `--force` | Skip confirmation prompt   |

#### `nautilus strategy market-exit <strategy_id>`

Market exit all positions managed by a strategy.

```bash
$ nautilus strategy market-exit EMACross-001
This will close 2 open positions at market price. Continue? [y/N]: y
Market exit initiated: 2 positions closing
  O-20231114-001  SELL 0.05 BTCUSDT-PERP.BINANCE
  O-20231114-002  BUY  1.00 ETHUSDT-PERP.BINANCE
```

#### `nautilus strategy state <strategy_id>`

Get detailed state information for a strategy.

```bash
$ nautilus strategy state EMACross-001

Strategy: EMACross-001
======================
  Type:    EMACross
  State:   RUNNING
  Created: 2023-11-14T22:13:20Z

Config:
  fast_ema_period: 10
  slow_ema_period: 20
  instrument_id: BTCUSDT-PERP.BINANCE

Open Orders: 1
  O-20231114-003  BUY  0.01  LIMIT  42000.00  GTC  ACCEPTED

Open Positions: 1
  BTCUSDT-PERP.BINANCE  LONG  0.05  entry: 42150.50  pnl: +125.30 USDT
```

### `nautilus order` — Order Management

#### `nautilus order list`

List orders with optional filtering.

```bash
$ nautilus order list
$ nautilus order list --status open
$ nautilus order list --status open --strategy EMACross-001
$ nautilus order list --instrument BTCUSDT-PERP.BINANCE --status closed --limit 20
```

| Option           | Description                                        |
|------------------|----------------------------------------------------|
| `--status`       | Filter: `open`, `closed`, `all` (default: `all`)  |
| `--strategy`     | Filter by strategy ID                             |
| `--instrument`   | Filter by instrument ID                           |
| `--venue`        | Filter by venue                                   |
| `--side`         | Filter by side: `BUY`, `SELL`                      |
| `--limit`        | Max results (default: 100)                         |

Output (table format):
```
Orders (open)
==============
  Client Order ID   Instrument              Side  Type   Qty    Price      Status    Strategy
  O-20231114-001    BTCUSDT-PERP.BINANCE    BUY   LIMIT  0.01   42000.00  ACCEPTED  EMACross-001
  O-20231114-003    ETHUSDT-PERP.BINANCE    SELL  MARKET 1.00   -         SUBMITTED GridBot-001
```

#### `nautilus order get <client_order_id>`

Get detailed order information including the full event history.

```bash
$ nautilus order get O-20231114-001

Order: O-20231114-001
=====================
  Instrument:    BTCUSDT-PERP.BINANCE
  Strategy:      EMACross-001
  Side:          BUY
  Type:          LIMIT
  Quantity:      0.01
  Price:         42000.00
  Time in Force: GTC
  Status:        FILLED
  Filled Qty:    0.01
  Avg Price:     41998.50
  Venue Order:   123456789

Event History:
  2023-11-14T22:13:20Z  OrderInitialized
  2023-11-14T22:13:21Z  OrderSubmitted
  2023-11-14T22:13:22Z  OrderAccepted
  2023-11-14T22:14:20Z  OrderFilled (0.01 @ 41998.50)
```

#### `nautilus order submit`

Submit a new order interactively.

```bash
$ nautilus order submit --instrument BTCUSDT-PERP.BINANCE --side BUY --type MARKET --quantity 0.01
Submit order: BUY 0.01 BTCUSDT-PERP.BINANCE @ MARKET? [y/N]: y
Order submitted: O-20231114-004 (INITIALIZED)

$ nautilus order submit --instrument BTCUSDT-PERP.BINANCE --side BUY --type LIMIT --quantity 0.01 --price 42000.00
Submit order: BUY 0.01 BTCUSDT-PERP.BINANCE @ LIMIT 42000.00 GTC? [y/N]: y
Order submitted: O-20231114-005 (INITIALIZED)

$ nautilus order submit --instrument BTCUSDT-PERP.BINANCE --side BUY --type MARKET --quantity 0.01 --force
Order submitted: O-20231114-006 (INITIALIZED)
```

| Option          | Description                                              |
|-----------------|----------------------------------------------------------|
| `--instrument`  | Instrument ID (required)                                 |
| `--side`        | `BUY` or `SELL` (required)                               |
| `--type`        | `MARKET`, `LIMIT`, `STOP_MARKET`, `STOP_LIMIT` (required) |
| `--quantity`    | Order quantity (required)                                |
| `--price`       | Limit price (required for LIMIT, STOP_LIMIT)             |
| `--trigger`     | Trigger price (required for STOP_MARKET, STOP_LIMIT)     |
| `--tif`         | Time in force: `GTC`, `IOC`, `FOK`, `DAY` (default: GTC) |
| `--strategy`    | Strategy ID to attribute the order to                    |
| `--reduce-only` | Reduce-only flag                                         |
| `--post-only`   | Post-only flag                                           |
| `--force`       | Skip confirmation prompt                                 |

**Implementation:**

```python
@order.command()
@click.option("--instrument", required=True, help="Instrument ID")
@click.option("--side", required=True, type=click.Choice(["BUY", "SELL"]))
@click.option("--type", "order_type", required=True, type=click.Choice(["MARKET", "LIMIT", "STOP_MARKET", "STOP_LIMIT"]))
@click.option("--quantity", required=True, help="Order quantity")
@click.option("--price", default=None, help="Limit price")
@click.option("--trigger", default=None, help="Trigger price")
@click.option("--tif", default="GTC", type=click.Choice(["GTC", "IOC", "FOK", "DAY"]), help="Time in force")
@click.option("--strategy", default=None, help="Strategy ID")
@click.option("--reduce-only", is_flag=True, help="Reduce-only order")
@click.option("--post-only", is_flag=True, help="Post-only order")
@click.option("--force", is_flag=True, help="Skip confirmation")
@click.pass_context
def submit(ctx, instrument, side, order_type, quantity, price, trigger, tif, strategy, reduce_only, post_only, force):
    """Submit a new order."""
    # Validate required conditional parameters
    if order_type in ("LIMIT", "STOP_LIMIT") and price is None:
        click.echo("Error: --price is required for LIMIT and STOP_LIMIT orders", err=True)
        sys.exit(1)
    if order_type in ("STOP_MARKET", "STOP_LIMIT") and trigger is None:
        click.echo("Error: --trigger is required for STOP_MARKET and STOP_LIMIT orders", err=True)
        sys.exit(1)

    # Build confirmation message
    price_str = f" @ {price}" if price else ""
    desc = f"{side} {quantity} {instrument} {order_type}{price_str} {tif}"

    if not force:
        click.confirm(f"Submit order: {desc}?", abort=True)

    body = {
        "instrument_id": instrument,
        "side": side,
        "order_type": order_type,
        "quantity": quantity,
        "time_in_force": tif,
        "reduce_only": reduce_only,
        "post_only": post_only,
    }
    if price:
        body["price"] = price
    if trigger:
        body["trigger_price"] = trigger
    if strategy:
        body["strategy_id"] = strategy

    client = get_client(ctx)
    fmt = get_formatter(ctx)
    result = client.post("/api/v1/orders", json=body)
    fmt.render_message(f"Order submitted: {result['client_order_id']} ({result['status']})")
```

#### `nautilus order cancel <client_order_id>`

Cancel an open order.

```bash
$ nautilus order cancel O-20231114-001
Cancel request submitted for O-20231114-001
```

#### `nautilus order modify <client_order_id>`

Modify an open order.

```bash
$ nautilus order modify O-20231114-001 --quantity 0.02 --price 41500.00
Modify request submitted for O-20231114-001 (qty: 0.02, price: 41500.00)
```

| Option       | Description              |
|--------------|--------------------------|
| `--quantity`  | New order quantity       |
| `--price`     | New order price          |

At least one of `--quantity` or `--price` must be provided.

#### `nautilus order cancel-all`

Cancel all open orders with optional filtering.

```bash
$ nautilus order cancel-all
Cancel ALL open orders? This cannot be undone. [y/N]: y
Cancel requests submitted for 5 orders

$ nautilus order cancel-all --instrument BTCUSDT-PERP.BINANCE
Cancel all open orders for BTCUSDT-PERP.BINANCE? [y/N]: y
Cancel requests submitted for 2 orders

$ nautilus order cancel-all --strategy EMACross-001 --force
Cancel requests submitted for 3 orders
```

| Option         | Description                         |
|----------------|-------------------------------------|
| `--instrument` | Only cancel orders for this instrument |
| `--strategy`   | Only cancel orders from this strategy  |
| `--side`       | Only cancel orders on this side        |
| `--force`      | Skip confirmation prompt               |

### `nautilus portfolio` — Portfolio Queries

#### `nautilus portfolio summary`

Full portfolio overview.

```bash
$ nautilus portfolio summary

Portfolio Summary (TRADER-001)
===============================

Balances:
  Venue     Currency  Total       Free        Locked
  BINANCE   USDT      50,000.00   45,000.00   5,000.00
  BINANCE   BTC       1.50        1.50        0.00

Open Positions:
  Instrument              Side   Qty    Entry       Unrealized PnL   Currency
  BTCUSDT-PERP.BINANCE    LONG   0.05   42,150.50   +125.30          USDT
  ETHUSDT-PERP.BINANCE    SHORT  1.00   2,250.00    -15.20           USDT

P&L Summary:
  Realized:    +1,500.00 USDT
  Unrealized:  +110.10 USDT
  Commissions: -42.50 USDT
```

#### `nautilus portfolio balances`

Account balances.

```bash
$ nautilus portfolio balances
$ nautilus portfolio balances --venue BINANCE
```

| Option    | Description           |
|-----------|-----------------------|
| `--venue` | Filter by venue name  |

#### `nautilus portfolio positions`

Open positions.

```bash
$ nautilus portfolio positions
$ nautilus portfolio positions --instrument BTCUSDT-PERP.BINANCE
```

| Option         | Description               |
|----------------|---------------------------|
| `--instrument` | Filter by instrument ID   |

#### `nautilus portfolio pnl`

Realized and unrealized P&L.

```bash
$ nautilus portfolio pnl
$ nautilus portfolio pnl --venue BINANCE
```

| Option    | Description        |
|-----------|--------------------|
| `--venue` | Filter by venue    |

#### `nautilus portfolio exposure`

Net exposures by instrument and venue.

```bash
$ nautilus portfolio exposure

Net Exposure
=============
  Instrument              Venue    Side   Qty    Notional     Currency
  BTCUSDT-PERP.BINANCE    BINANCE  LONG   0.05   2,107.53     USDT
  ETHUSDT-PERP.BINANCE    BINANCE  SHORT  1.00   2,250.00     USDT

Total by Currency:
  USDT: 4,357.53
```

### `nautilus risk` — Risk Management

#### `nautilus risk state`

Show current risk engine state and limits.

```bash
$ nautilus risk state

Risk Engine
============
  State:          RUNNING
  Trading State:  ACTIVE

Limits:
  Max Order Submit Rate:  10/s
  Max Order Modify Rate:  10/s
  Max Notional (BTCUSDT-PERP.BINANCE): 100,000.00 USDT
```

#### `nautilus risk limits`

View or update risk limits.

```bash
$ nautilus risk limits
# Shows current limits (same as risk state)

$ nautilus risk limits --set max_order_submit_rate="5/00:00:01"
Risk limits updated

$ nautilus risk limits --set max_notional_per_order.BTCUSDT-PERP.BINANCE=50000.00
Risk limits updated
```

| Option  | Description                         |
|---------|-------------------------------------|
| `--set` | Set a limit (key=value format)      |

### `nautilus market` — Market Data

#### `nautilus market instruments`

List available instruments.

```bash
$ nautilus market instruments
$ nautilus market instruments --venue BINANCE
$ nautilus market instruments --search BTC
$ nautilus market instruments --venue BINANCE --search ETH

Instruments
============
  Instrument ID              Type              Base   Quote  Tick Size  Lot Size
  BTCUSDT-PERP.BINANCE       CryptoPerpetual   BTC    USDT   0.01       0.001
  ETHUSDT-PERP.BINANCE       CryptoPerpetual   ETH    USDT   0.01       0.001
  BTCUSDT.BINANCE            CurrencyPair      BTC    USDT   0.01       0.00001
```

| Option     | Description                        |
|------------|------------------------------------|
| `--venue`  | Filter by venue                    |
| `--search` | Search by symbol (case-insensitive)|
| `--type`   | Filter by instrument type          |
| `--limit`  | Max results (default: 100)         |

#### `nautilus market quote <instrument_id>`

Get the latest quote for an instrument.

```bash
$ nautilus market quote BTCUSDT-PERP.BINANCE

Quote: BTCUSDT-PERP.BINANCE
============================
  Bid:  42,100.50 (1.500)
  Ask:  42,101.00 (2.300)
  Spread: 0.50 (0.001%)
  Time: 2023-11-14T23:13:20Z
```

#### `nautilus market bars <instrument_id>`

Get recent OHLCV bars.

```bash
$ nautilus market bars BTCUSDT-PERP.BINANCE --bar-type "BTCUSDT-PERP.BINANCE-1-MINUTE-LAST-EXTERNAL" --count 5

Bars: BTCUSDT-PERP.BINANCE (1-MINUTE)
=======================================
  Time                   Open       High       Low        Close      Volume
  2023-11-14T23:09:00Z   42,100.00  42,150.00  42,050.00  42,120.00  150.500
  2023-11-14T23:10:00Z   42,120.00  42,180.00  42,100.00  42,160.00  200.300
  ...
```

| Option       | Description                        |
|--------------|------------------------------------|
| `--bar-type` | Full bar type string (required)    |
| `--count`    | Number of bars (default: 10)       |

### `nautilus events` — Event Streaming

#### `nautilus events stream`

Stream live events from the trading node to the terminal. Connects to the WebSocket endpoint defined in SPEC-002.

```bash
$ nautilus events stream
# Streams all events (events.*)

$ nautilus events stream --topics "events.order.*,events.position.*"
# Streams only order and position events

$ nautilus events stream --format json
# Output each event as a JSON line (for piping to jq or other tools)

$ nautilus events stream --topics "events.order.filled" --format json | jq '.data.last_px'
# Filter filled order prices with jq
```

| Option     | Description                                               |
|------------|-----------------------------------------------------------|
| `--topics` | Comma-separated topic patterns (default: `events.*`)       |
| `--replay` | Replay from sequence number before streaming live events   |

Output (table format — human-readable):
```
[23:13:20] OrderSubmitted    EMACross-001  BUY 0.01 BTCUSDT-PERP.BINANCE LIMIT 42000.00
[23:13:21] OrderAccepted     EMACross-001  O-20231114-001 → venue: 123456789
[23:14:20] OrderFilled       EMACross-001  BUY 0.01 @ 41998.50 BTCUSDT-PERP.BINANCE
[23:14:20] PositionChanged   EMACross-001  LONG 0.05 → 0.06 BTCUSDT-PERP.BINANCE
```

Output (JSON format):
```json
{"type":"OrderFilled","topic":"events.order.filled","ts_event":1700003660000000000,"sequence":42,"data":{"instrument_id":"BTCUSDT-PERP.BINANCE","side":"BUY","last_qty":"0.01","last_px":"41998.50"}}
```

**Implementation:**

```python
import asyncio
import websockets
import json

@events.command()
@click.option("--topics", default="events.*", help="Comma-separated topic patterns")
@click.option("--replay", default=None, type=int, help="Replay from sequence number")
@click.pass_context
def stream(ctx, topics, replay):
    """Stream live events from the trading node."""
    host = ctx.obj["host"]
    port = ctx.obj["port"]
    api_key = ctx.obj["api_key"]
    output_format = ctx.obj["format"]

    url = f"ws://{host}:{port}/api/v1/events/stream"
    if api_key:
        url += f"?api_key={api_key}"

    topic_list = [t.strip() for t in topics.split(",")]

    async def _stream():
        async with websockets.connect(url) as ws:
            # Subscribe
            await ws.send(json.dumps({"action": "subscribe", "topics": topic_list}))

            # Replay if requested
            if replay is not None:
                await ws.send(json.dumps({"action": "replay", "from_sequence": replay}))

            # Read events
            async for message in ws:
                event = json.loads(message)
                if output_format == "json":
                    click.echo(json.dumps(event))
                else:
                    _print_event_human(event)

    try:
        asyncio.run(_stream())
    except KeyboardInterrupt:
        pass  # Clean exit on Ctrl+C
```

## Global Options

All global options are defined on the top-level `cli` group and passed down via Click context:

| Option       | Short | Default       | Description                     |
|--------------|-------|---------------|---------------------------------|
| `--host`     |       | `localhost`   | API server host                 |
| `--port`     |       | `8001`        | API server port                 |
| `--api-key`  |       | None          | API key for authentication      |
| `--format`   |       | `table`       | Output format: table, json, csv |
| `--no-color` |       | False         | Disable colored output          |
| `--verbose`  | `-v`  | False         | Enable verbose output           |

Global options can be set persistently via the configuration file (see below) and overridden per-invocation via CLI flags.

## Output Formatting

### Table Format (default)

Uses the [Rich](https://rich.readthedocs.io/) library for formatted, colored tables in the terminal. Tables auto-resize to terminal width. Long values are truncated with `...`.

### JSON Format

Raw JSON output, one JSON document per command. Suitable for:
- Piping to `jq` for filtering and transformation
- Parsing in shell scripts
- Integration with other tools

```bash
$ nautilus portfolio positions --format json | jq '.positions[] | select(.side == "LONG")'
```

### CSV Format

Standard CSV output with headers. Suitable for:
- Importing into spreadsheets
- Processing with `csvtool`, `awk`, or `cut`
- Data analysis pipelines

```bash
$ nautilus order list --status closed --format csv > orders.csv
```

## Configuration File

### Location

`~/.nautilus/cli.toml`

### Format

```toml
[connection]
host = "localhost"
port = 8001
api_key = "my-secret-api-key"

[output]
format = "table"     # table, json, csv
color = true         # false to disable colors
```

### Priority

Configuration is resolved in this order (highest priority first):

1. CLI flags (`--host`, `--port`, etc.)
2. Environment variables (`NAUTILUS_HOST`, `NAUTILUS_PORT`, `NAUTILUS_API_KEY`)
3. Configuration file (`~/.nautilus/cli.toml`)
4. Built-in defaults

### Environment Variables

| Variable          | Description           |
|-------------------|-----------------------|
| `NAUTILUS_HOST`   | API server host       |
| `NAUTILUS_PORT`   | API server port       |
| `NAUTILUS_API_KEY` | API key              |
| `NAUTILUS_FORMAT`  | Output format         |

## Shell Completions

The CLI supports shell completion installation for bash, zsh, and fish.

```bash
# Install completions
$ nautilus --install-completion bash
$ nautilus --install-completion zsh
$ nautilus --install-completion fish

# Or manually source (bash)
$ eval "$(_NAUTILUS_COMPLETE=bash_source nautilus)"

# Or manually source (zsh)
$ eval "$(_NAUTILUS_COMPLETE=zsh_source nautilus)"
```

Click provides completion support via the `_<APP>_COMPLETE` environment variable convention. The `--install-completion` command is a convenience wrapper that appends the appropriate `eval` line to the user's shell profile (`.bashrc`, `.zshrc`, or `config.fish`).

Completions include:
- Command and subcommand names
- Option names
- Enum values for options with `type=click.Choice()`
- File path completion for `--config` options

## Exit Codes

| Code | Meaning                              |
|------|--------------------------------------|
| 0    | Success                              |
| 1    | Error (API error, connection error)  |
| 2    | Usage error (invalid arguments)      |
| 130  | Interrupted (Ctrl+C)                 |

## Error Display

Errors are displayed to stderr with clear formatting:

```bash
$ nautilus order get O-nonexistent
Error (404): Order not found
Detail: {"client_order_id": "O-nonexistent"}

$ nautilus node status
Error: Cannot connect to http://localhost:8001. Is the trading node running?
```

In verbose mode (`-v`), additional information is shown:
- Full HTTP request/response details
- Request timing
- Response headers
