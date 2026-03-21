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


if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from nautilus_trader.mcp.client import NautilusClient
    from nautilus_trader.mcp.safety import SafetyGuardrails


async def register_node_mutation_tools(
    server: FastMCP,
    client: NautilusClient,
    safety: SafetyGuardrails,
) -> None:
    """
    Register node mutation tools with the MCP server.

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
    async def nautilus_node_stop(confirm: bool = False) -> list:
        """Stop the NautilusTrader node. This is a CRITICAL action that requires confirmation."""
        from mcp.types import TextContent

        from nautilus_trader.mcp.client import NautilusApiError

        validation = safety.validate_mutation("nautilus_node_stop", CRITICAL)
        if not validation.is_valid:
            return [TextContent(type="text", text=f"Blocked: {validation.rejection_reason}")]

        if validation.requires_confirmation and not confirm:
            return [TextContent(type="text", text=validation.confirmation_message)]

        try:
            result = await client.post("/api/v1/node/stop")
            status = result.get("status", "unknown")
            return [TextContent(type="text", text=f"Node stop initiated. Status: {status}")]
        except NautilusApiError as e:
            return [TextContent(type="text", text=f"Error: {e.message}")]
