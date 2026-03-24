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

from typing import TYPE_CHECKING

from nautilus_trader.mcp.safety import CRITICAL
from nautilus_trader.mcp.safety import WRITE


if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from nautilus_trader.mcp.client import NautilusClient
    from nautilus_trader.mcp.safety import SafetyGuardrails


async def register_strategy_mutation_tools(
    server: FastMCP,
    client: NautilusClient,
    safety: SafetyGuardrails,
) -> None:
    """
    Register strategy mutation tools with the MCP server.

    Parameters
    ----------
    server : FastMCP
        The MCP server instance.
    client : NautilusClient
        The NautilusTrader API client.
    safety : SafetyGuardrails
        The safety guardrails instance.

    """

    @server.tool()
    async def nautilus_start_strategy(strategy_id: str) -> list:
        """Start a strategy by its ID."""
        from mcp.types import TextContent

        from nautilus_trader.mcp.client import NautilusApiError

        validation = safety.validate_mutation("nautilus_start_strategy", WRITE)
        if not validation.is_valid:
            return [TextContent(type="text", text=f"Blocked: {validation.rejection_reason}")]

        if validation.requires_confirmation:
            return [TextContent(type="text", text=validation.confirmation_message)]

        try:
            result = await client.post(f"/api/v1/strategies/{strategy_id}/start")
            status = result.get("status", "unknown")
            return [TextContent(
                type="text",
                text=f"Strategy '{strategy_id}' started. Status: {status}",
            )]
        except NautilusApiError as e:
            return [TextContent(type="text", text=f"Error: {e.message}")]

    @server.tool()
    async def nautilus_stop_strategy(strategy_id: str) -> list:
        """Stop a strategy by its ID."""
        from mcp.types import TextContent

        from nautilus_trader.mcp.client import NautilusApiError

        validation = safety.validate_mutation("nautilus_stop_strategy", WRITE)
        if not validation.is_valid:
            return [TextContent(type="text", text=f"Blocked: {validation.rejection_reason}")]

        if validation.requires_confirmation:
            return [TextContent(type="text", text=validation.confirmation_message)]

        try:
            result = await client.post(f"/api/v1/strategies/{strategy_id}/stop")
            status = result.get("status", "unknown")
            return [TextContent(
                type="text",
                text=f"Strategy '{strategy_id}' stopped. Status: {status}",
            )]
        except NautilusApiError as e:
            return [TextContent(type="text", text=f"Error: {e.message}")]

    @server.tool()
    async def nautilus_remove_strategy(strategy_id: str, confirm: bool = False) -> list:
        """Remove a strategy by its ID. This is a CRITICAL action that requires confirmation."""
        from mcp.types import TextContent

        from nautilus_trader.mcp.client import NautilusApiError

        validation = safety.validate_mutation("nautilus_remove_strategy", CRITICAL)
        if not validation.is_valid:
            return [TextContent(type="text", text=f"Blocked: {validation.rejection_reason}")]

        if validation.requires_confirmation and not confirm:
            return [TextContent(type="text", text=validation.confirmation_message)]

        try:
            result = await client.delete(f"/api/v1/strategies/{strategy_id}")
            status = result.get("status", "unknown")
            return [TextContent(
                type="text",
                text=f"Strategy '{strategy_id}' removed. Status: {status}",
            )]
        except NautilusApiError as e:
            return [TextContent(type="text", text=f"Error: {e.message}")]

    @server.tool()
    async def nautilus_market_exit_strategy(
        strategy_id: str,
        confirm: bool = False,
    ) -> list:
        """Market exit a strategy. This is a CRITICAL action that requires confirmation."""
        from mcp.types import TextContent

        from nautilus_trader.mcp.client import NautilusApiError

        validation = safety.validate_mutation("nautilus_market_exit_strategy", CRITICAL)
        if not validation.is_valid:
            return [TextContent(type="text", text=f"Blocked: {validation.rejection_reason}")]

        if validation.requires_confirmation and not confirm:
            return [TextContent(type="text", text=validation.confirmation_message)]

        try:
            result = await client.post(f"/api/v1/strategies/{strategy_id}/market-exit")
            status = result.get("status", "unknown")
            return [TextContent(
                type="text",
                text=f"Market exit initiated for strategy '{strategy_id}'. Status: {status}",
            )]
        except NautilusApiError as e:
            return [TextContent(type="text", text=f"Error: {e.message}")]
