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

import asyncio
import logging
import sys
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server

from nautilus_trader.mcp.client import NautilusClient
from nautilus_trader.mcp.config import McpServerConfig
from nautilus_trader.mcp.config import load_config
from nautilus_trader.mcp.safety import SafetyGuardrails


logger = logging.getLogger("nautilus_mcp")


def create_mcp_server(config: McpServerConfig) -> tuple[Server, NautilusClient]:
    """
    Create and configure the MCP server with all tools registered.

    Parameters
    ----------
    config : McpServerConfig
        The MCP server configuration.

    Returns
    -------
    tuple[Server, NautilusClient]

    """
    server = Server("nautilus-trader")
    client = NautilusClient(config.api_url, config.api_key)
    safety = SafetyGuardrails(config)

    # Register tools from each module (lazy imports to avoid circular deps)
    _register_tools(server, client, safety, config)

    return server, client


def _register_tools(
    server: Server,
    client: NautilusClient,
    safety: SafetyGuardrails,
    config: McpServerConfig,
) -> None:
    """Register all tool modules with the MCP server."""
    # Read-only tools
    try:
        from nautilus_trader.mcp.tools.node import register_node_tools
        register_node_tools(server, client, safety)
    except (ImportError, AttributeError) as e:
        logger.debug(f"Node tools module not available: {e}")

    try:
        from nautilus_trader.mcp.tools.strategies import register_strategy_tools
        register_strategy_tools(server, client, safety)
    except (ImportError, AttributeError):
        logger.debug("Strategy tools module not available")

    try:
        from nautilus_trader.mcp.tools.orders import register_order_tools
        register_order_tools(server, client, safety)
    except (ImportError, AttributeError):
        logger.debug("Order tools module not available")

    try:
        from nautilus_trader.mcp.tools.portfolio import register_portfolio_tools
        register_portfolio_tools(server, client, safety)
    except (ImportError, AttributeError):
        logger.debug("Portfolio tools module not available")

    try:
        from nautilus_trader.mcp.tools.market_data import register_market_data_tools
        register_market_data_tools(server, client, safety)
    except (ImportError, AttributeError):
        logger.debug("Market data tools module not available")

    try:
        from nautilus_trader.mcp.tools.risk import register_risk_tools
        register_risk_tools(server, client, safety)
    except (ImportError, AttributeError):
        logger.debug("Risk tools module not available")

    # Mutation tools
    if not config.read_only:
        try:
            from nautilus_trader.mcp.tools.node_mutations import register_node_mutation_tools
            register_node_mutation_tools(server, client, safety)
        except (ImportError, AttributeError):
            logger.debug("Node mutation tools module not available")

        try:
            from nautilus_trader.mcp.tools.strategy_mutations import register_strategy_mutation_tools
            register_strategy_mutation_tools(server, client, safety)
        except (ImportError, AttributeError):
            logger.debug("Strategy mutation tools module not available")

        try:
            from nautilus_trader.mcp.tools.order_mutations import register_order_mutation_tools
            register_order_mutation_tools(server, client, safety)
        except (ImportError, AttributeError):
            logger.debug("Order mutation tools module not available")

        try:
            from nautilus_trader.mcp.tools.risk_mutations import register_risk_mutation_tools
            register_risk_mutation_tools(server, client, safety)
        except (ImportError, AttributeError):
            logger.debug("Risk mutation tools module not available")

    # Resources
    try:
        from nautilus_trader.mcp.resources import register_resources
        register_resources(server, client)
    except (ImportError, AttributeError):
        logger.debug("Resources module not available")


async def run_stdio(config: McpServerConfig) -> None:
    """
    Run the MCP server with stdio transport.

    Parameters
    ----------
    config : McpServerConfig
        The MCP server configuration.

    """
    server, client = create_mcp_server(config)

    try:
        await client.start()

        # Check connectivity
        if await client.health_check():
            logger.info(f"Connected to NautilusTrader API at {config.api_url}")
        else:
            logger.warning(
                f"Cannot reach NautilusTrader API at {config.api_url}. "
                "Tools will fail until the API becomes available.",
            )

        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )
    finally:
        await client.stop()


async def run_sse(config: McpServerConfig) -> None:
    """
    Run the MCP server with SSE transport.

    Parameters
    ----------
    config : McpServerConfig
        The MCP server configuration.

    """
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.routing import Route

    import uvicorn

    server, client = create_mcp_server(config)
    sse = SseServerTransport("/messages")

    async def handle_sse(request):
        async with sse.connect_sse(
            request.scope,
            request.receive,
            request._send,
        ) as streams:
            await server.run(
                streams[0],
                streams[1],
                server.create_initialization_options(),
            )

    app = Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Route("/messages", endpoint=sse.handle_post_message, methods=["POST"]),
        ],
    )

    try:
        await client.start()

        if await client.health_check():
            logger.info(f"Connected to NautilusTrader API at {config.api_url}")
        else:
            logger.warning(
                f"Cannot reach NautilusTrader API at {config.api_url}. "
                "Tools will fail until the API becomes available.",
            )

        uvi_config = uvicorn.Config(
            app=app,
            host=config.sse_host,
            port=config.sse_port,
            log_level="warning",
        )
        uvi_server = uvicorn.Server(uvi_config)
        logger.info(f"MCP SSE server listening on {config.sse_host}:{config.sse_port}")
        await uvi_server.serve()
    finally:
        await client.stop()


def main() -> None:
    """Entry point for the MCP server (``python -m nautilus_trader.mcp.server``)."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    config = load_config()

    if config.transport == "stdio":
        asyncio.run(run_stdio(config))
    elif config.transport == "sse":
        asyncio.run(run_sse(config))
    else:
        logger.error(f"Unknown transport: {config.transport}")
        sys.exit(1)


if __name__ == "__main__":
    main()
