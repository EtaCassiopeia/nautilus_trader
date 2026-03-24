# -------------------------------------------------------------------------------------------------
#  Copyright (C) 2015-2026 Nautech Systems Pty Ltd. All rights reserved.
#  https://nautechsystems.io
#
#  Licensed under the GNU Lesser General Public License Version 3.0 (the "License");
#  You may not use this file except in compliance with the License.
#  You may obtain a copy of the License at https://www.gnu.org/licenses/lgpl-3.0.en.html
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
# -------------------------------------------------------------------------------------------------

from __future__ import annotations

import click

from nautilus_trader.cli.client import CliApiError
from nautilus_trader.cli.client import CliClient
from nautilus_trader.cli.config import load_cli_config
from nautilus_trader.cli.output import format_error
from nautilus_trader.cli.output import format_output


class Context:
    """Shared CLI context holding the client and configuration."""

    def __init__(self, client: CliClient, output_format: str) -> None:
        self.client = client
        self.output_format = output_format


pass_context = click.make_pass_decorator(Context)


@click.group()
@click.option("--host", default=None, help="API server host")
@click.option("--port", default=None, type=int, help="API server port")
@click.option("--api-key", default=None, help="API key for authentication")
@click.option(
    "--format",
    "output_format",
    default=None,
    type=click.Choice(["table", "json", "csv"]),
    help="Output format",
)
@click.option("--no-color", is_flag=True, default=False, help="Disable colored output")
@click.pass_context
def cli(ctx, host, port, api_key, output_format, no_color):
    """NautilusTrader command-line interface."""
    config = load_cli_config(
        host=host,
        port=port,
        api_key=api_key,
        output_format=output_format,
    )

    client = CliClient(
        api_url=config.api_url,
        api_key=config.api_key,
    )

    ctx.ensure_object(dict)
    ctx.obj = Context(
        client=client,
        output_format=config.output_format,
    )


# ── Node commands ──────────────────────────────────────────────────────────────


@cli.group()
def node():
    """Node management commands."""


@node.command()
@pass_context
def status(ctx):
    """Show node status."""
    try:
        result = ctx.client.get("/api/v1/node/status")
        data = result.get("data", result)
        click.echo(format_output(data, ctx.output_format, title="Node Status"))
    except CliApiError as e:
        click.echo(format_error(e.code, e.message), err=True)
        raise SystemExit(1)


@node.command()
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation prompt")
@pass_context
def stop(ctx, yes):
    """Stop the trading node."""
    if not yes:
        click.confirm("Stop the trading node?", abort=True)

    try:
        result = ctx.client.post("/api/v1/node/stop")
        click.echo("Node stop requested.")
    except CliApiError as e:
        click.echo(format_error(e.code, e.message), err=True)
        raise SystemExit(1)


# ── Strategy commands ──────────────────────────────────────────────────────────


@cli.group()
def strategy():
    """Strategy management commands."""


@strategy.command("list")
@click.option("--state", default=None, help="Filter by state (RUNNING, STOPPED, etc.)")
@pass_context
def strategy_list(ctx, state):
    """List all strategies."""
    try:
        params = {}
        if state:
            params["state"] = state
        result = ctx.client.get("/api/v1/strategies", params=params if params else None)
        data = result.get("data", [])
        click.echo(format_output(data, ctx.output_format, title="Strategies"))
    except CliApiError as e:
        click.echo(format_error(e.code, e.message), err=True)
        raise SystemExit(1)


@strategy.command()
@click.argument("strategy_id")
@pass_context
def start(ctx, strategy_id):
    """Start a strategy."""
    try:
        ctx.client.post(f"/api/v1/strategies/{strategy_id}/start")
        click.echo(f"Strategy '{strategy_id}' start requested.")
    except CliApiError as e:
        click.echo(format_error(e.code, e.message), err=True)
        raise SystemExit(1)


@strategy.command()
@click.argument("strategy_id")
@pass_context
def stop_strategy(ctx, strategy_id):
    """Stop a strategy."""
    try:
        ctx.client.post(f"/api/v1/strategies/{strategy_id}/stop")
        click.echo(f"Strategy '{strategy_id}' stop requested.")
    except CliApiError as e:
        click.echo(format_error(e.code, e.message), err=True)
        raise SystemExit(1)


@strategy.command()
@click.argument("strategy_id")
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation prompt")
@pass_context
def remove(ctx, strategy_id, yes):
    """Remove a strategy."""
    if not yes:
        click.confirm(f"Remove strategy '{strategy_id}'?", abort=True)

    try:
        ctx.client.delete(f"/api/v1/strategies/{strategy_id}")
        click.echo(f"Strategy '{strategy_id}' removed.")
    except CliApiError as e:
        click.echo(format_error(e.code, e.message), err=True)
        raise SystemExit(1)


@strategy.command("market-exit")
@click.argument("strategy_id")
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation prompt")
@pass_context
def market_exit(ctx, strategy_id, yes):
    """Market-exit all positions for a strategy."""
    if not yes:
        click.confirm(
            f"Market-exit all positions for strategy '{strategy_id}'?",
            abort=True,
        )

    try:
        ctx.client.post(f"/api/v1/strategies/{strategy_id}/market-exit")
        click.echo(f"Market exit requested for strategy '{strategy_id}'.")
    except CliApiError as e:
        click.echo(format_error(e.code, e.message), err=True)
        raise SystemExit(1)


# ── Order commands ─────────────────────────────────────────────────────────────


@cli.group()
def order():
    """Order management commands."""


@order.command("list")
@click.option("--status", "order_status", default="all", help="Filter: open, closed, all")
@click.option("--strategy-id", default=None, help="Filter by strategy ID")
@click.option("--instrument-id", default=None, help="Filter by instrument ID")
@click.option("--limit", default=50, type=int, help="Max orders to return")
@pass_context
def order_list(ctx, order_status, strategy_id, instrument_id, limit):
    """List orders."""
    try:
        params = {"status": order_status, "limit": limit}
        if strategy_id:
            params["strategy_id"] = strategy_id
        if instrument_id:
            params["instrument_id"] = instrument_id

        result = ctx.client.get("/api/v1/orders", params=params)
        data = result.get("data", [])
        columns = [
            "client_order_id", "instrument_id", "side", "order_type",
            "quantity", "status", "filled_qty",
        ]
        click.echo(format_output(data, ctx.output_format, columns=columns, title="Orders"))
    except CliApiError as e:
        click.echo(format_error(e.code, e.message), err=True)
        raise SystemExit(1)


@order.command()
@click.argument("client_order_id")
@pass_context
def get(ctx, client_order_id):
    """Get order details."""
    try:
        result = ctx.client.get(f"/api/v1/orders/{client_order_id}")
        data = result.get("data", result)
        click.echo(format_output(data, ctx.output_format, title=f"Order {client_order_id}"))
    except CliApiError as e:
        click.echo(format_error(e.code, e.message), err=True)
        raise SystemExit(1)


@order.command()
@click.argument("client_order_id")
@pass_context
def cancel(ctx, client_order_id):
    """Cancel an order."""
    try:
        ctx.client.delete(f"/api/v1/orders/{client_order_id}")
        click.echo(f"Cancel requested for order '{client_order_id}'.")
    except CliApiError as e:
        click.echo(format_error(e.code, e.message), err=True)
        raise SystemExit(1)


@order.command("cancel-all")
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation prompt")
@pass_context
def cancel_all(ctx, yes):
    """Cancel all open orders."""
    if not yes:
        click.confirm("Cancel ALL open orders?", abort=True)

    try:
        ctx.client.post("/api/v1/orders/cancel-all")
        click.echo("Cancel-all requested.")
    except CliApiError as e:
        click.echo(format_error(e.code, e.message), err=True)
        raise SystemExit(1)


# ── Portfolio commands ─────────────────────────────────────────────────────────


@cli.group()
def portfolio():
    """Portfolio commands."""


@portfolio.command()
@pass_context
def summary(ctx):
    """Full portfolio overview."""
    try:
        result = ctx.client.get("/api/v1/portfolio")
        data = result.get("data", result)
        click.echo(format_output(data, ctx.output_format, title="Portfolio Summary"))
    except CliApiError as e:
        click.echo(format_error(e.code, e.message), err=True)
        raise SystemExit(1)


@portfolio.command()
@click.option("--venue", default=None, help="Filter by venue")
@pass_context
def balances(ctx, venue):
    """Account balances."""
    try:
        params = {}
        if venue:
            params["venue"] = venue
        result = ctx.client.get("/api/v1/portfolio/balances", params=params if params else None)
        data = result.get("data", result)
        click.echo(format_output(data, ctx.output_format, title="Balances"))
    except CliApiError as e:
        click.echo(format_error(e.code, e.message), err=True)
        raise SystemExit(1)


@portfolio.command()
@click.option("--instrument-id", default=None, help="Filter by instrument")
@pass_context
def positions(ctx, instrument_id):
    """Open positions."""
    try:
        params = {}
        if instrument_id:
            params["instrument_id"] = instrument_id
        result = ctx.client.get("/api/v1/portfolio/positions", params=params if params else None)
        data = result.get("data", [])
        columns = [
            "instrument_id", "strategy_id", "side", "quantity",
            "avg_px_open", "unrealized_pnl",
        ]
        click.echo(format_output(data, ctx.output_format, columns=columns, title="Positions"))
    except CliApiError as e:
        click.echo(format_error(e.code, e.message), err=True)
        raise SystemExit(1)


@portfolio.command()
@pass_context
def pnl(ctx):
    """P&L summary."""
    try:
        result = ctx.client.get("/api/v1/portfolio/pnl")
        data = result.get("data", result)
        click.echo(format_output(data, ctx.output_format, title="P&L"))
    except CliApiError as e:
        click.echo(format_error(e.code, e.message), err=True)
        raise SystemExit(1)


@portfolio.command()
@pass_context
def exposure(ctx):
    """Net exposures."""
    try:
        result = ctx.client.get("/api/v1/portfolio/exposure")
        data = result.get("data", result)
        click.echo(format_output(data, ctx.output_format, title="Exposure"))
    except CliApiError as e:
        click.echo(format_error(e.code, e.message), err=True)
        raise SystemExit(1)


# ── Market commands ────────────────────────────────────────────────────────────


@cli.group()
def market():
    """Market data commands."""


@market.command()
@click.option("--venue", default=None, help="Filter by venue")
@pass_context
def instruments(ctx, venue):
    """List instruments."""
    try:
        params = {}
        if venue:
            params["venue"] = venue
        result = ctx.client.get("/api/v1/cache/instruments", params=params if params else None)
        data = result.get("data", [])
        click.echo(format_output(data, ctx.output_format, title="Instruments"))
    except CliApiError as e:
        click.echo(format_error(e.code, e.message), err=True)
        raise SystemExit(1)


@market.command()
@click.argument("instrument_id")
@pass_context
def quote(ctx, instrument_id):
    """Latest quote for an instrument."""
    try:
        result = ctx.client.get(f"/api/v1/data/quotes/{instrument_id}")
        data = result.get("data", result)
        click.echo(format_output(data, ctx.output_format, title=f"Quote: {instrument_id}"))
    except CliApiError as e:
        click.echo(format_error(e.code, e.message), err=True)
        raise SystemExit(1)


@market.command()
@click.argument("instrument_id")
@click.option("--bar-type", default=None, help="Bar type string")
@click.option("--count", default=10, type=int, help="Number of bars")
@pass_context
def bars(ctx, instrument_id, bar_type, count):
    """Recent bars for an instrument."""
    try:
        params = {"count": count}
        if bar_type:
            params["bar_type"] = bar_type
        result = ctx.client.get(f"/api/v1/data/bars/{instrument_id}", params=params)
        data = result.get("data", [])
        click.echo(format_output(data, ctx.output_format, title=f"Bars: {instrument_id}"))
    except CliApiError as e:
        click.echo(format_error(e.code, e.message), err=True)
        raise SystemExit(1)


# ── Risk commands ──────────────────────────────────────────────────────────────


@cli.group()
def risk():
    """Risk management commands."""


@risk.command()
@pass_context
def state(ctx):
    """Risk engine state."""
    try:
        result = ctx.client.get("/api/v1/risk/status")
        data = result.get("data", result)
        click.echo(format_output(data, ctx.output_format, title="Risk State"))
    except CliApiError as e:
        click.echo(format_error(e.code, e.message), err=True)
        raise SystemExit(1)


def main():
    """Entry point."""
    cli()


if __name__ == "__main__":
    main()
