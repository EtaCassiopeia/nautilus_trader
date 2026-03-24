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


async def register_order_mutation_tools(
    server: FastMCP,
    client: NautilusClient,
    safety: SafetyGuardrails,
) -> None:
    """
    Register order mutation tools with the MCP server.

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
    async def nautilus_submit_order(
        instrument_id: str,
        side: str,
        order_type: str,
        quantity: str,
        price: str | None = None,
        time_in_force: str = "GTC",
        confirm: bool = False,
    ) -> list:
        """Submit a new order. This is a CRITICAL action validated against safety guardrails."""
        from mcp.types import TextContent

        from nautilus_trader.mcp.client import NautilusApiError

        order_dict = {
            "instrument_id": instrument_id,
            "side": side,
            "order_type": order_type,
            "quantity": quantity,
        }

        validation = safety.validate_order(order_dict)
        if not validation.is_valid:
            return [TextContent(type="text", text=f"Blocked: {validation.rejection_reason}")]

        if validation.requires_confirmation and not confirm:
            return [TextContent(type="text", text=validation.confirmation_message)]

        payload: dict = {
            "instrument_id": instrument_id,
            "side": side,
            "order_type": order_type,
            "quantity": quantity,
            "time_in_force": time_in_force,
        }
        if price is not None:
            payload["price"] = price

        try:
            result = await client.post("/api/v1/orders", json=payload)
            order_id = result.get("client_order_id", "unknown")
            status = result.get("status", "unknown")
            return [TextContent(
                type="text",
                text=f"Order submitted. ID: {order_id}, Status: {status}",
            )]
        except NautilusApiError as e:
            return [TextContent(type="text", text=f"Error: {e.message}")]

    @server.tool()
    async def nautilus_cancel_order(client_order_id: str) -> list:
        """Cancel an order by its client order ID."""
        from mcp.types import TextContent

        from nautilus_trader.mcp.client import NautilusApiError

        validation = safety.validate_mutation("nautilus_cancel_order", WRITE)
        if not validation.is_valid:
            return [TextContent(type="text", text=f"Blocked: {validation.rejection_reason}")]

        if validation.requires_confirmation:
            return [TextContent(type="text", text=validation.confirmation_message)]

        try:
            result = await client.delete(f"/api/v1/orders/{client_order_id}")
            status = result.get("status", "unknown")
            return [TextContent(
                type="text",
                text=f"Order '{client_order_id}' canceled. Status: {status}",
            )]
        except NautilusApiError as e:
            return [TextContent(type="text", text=f"Error: {e.message}")]

    @server.tool()
    async def nautilus_modify_order(
        client_order_id: str,
        quantity: str | None = None,
        price: str | None = None,
    ) -> list:
        """Modify an existing order by its client order ID."""
        from mcp.types import TextContent

        from nautilus_trader.mcp.client import NautilusApiError

        validation = safety.validate_mutation("nautilus_modify_order", WRITE)
        if not validation.is_valid:
            return [TextContent(type="text", text=f"Blocked: {validation.rejection_reason}")]

        if validation.requires_confirmation:
            return [TextContent(type="text", text=validation.confirmation_message)]

        payload: dict = {}
        if quantity is not None:
            payload["quantity"] = quantity
        if price is not None:
            payload["price"] = price

        try:
            result = await client.patch(f"/api/v1/orders/{client_order_id}", json=payload)
            status = result.get("status", "unknown")
            return [TextContent(
                type="text",
                text=f"Order '{client_order_id}' modified. Status: {status}",
            )]
        except NautilusApiError as e:
            return [TextContent(type="text", text=f"Error: {e.message}")]

    @server.tool()
    async def nautilus_cancel_all_orders(confirm: bool = False) -> list:
        """Cancel all orders. This is a CRITICAL action that requires confirmation."""
        from mcp.types import TextContent

        from nautilus_trader.mcp.client import NautilusApiError

        validation = safety.validate_mutation("nautilus_cancel_all_orders", CRITICAL)
        if not validation.is_valid:
            return [TextContent(type="text", text=f"Blocked: {validation.rejection_reason}")]

        if validation.requires_confirmation and not confirm:
            return [TextContent(type="text", text=validation.confirmation_message)]

        try:
            result = await client.post("/api/v1/orders/cancel-all")
            count = result.get("canceled_count", "unknown")
            return [TextContent(
                type="text",
                text=f"All orders canceled. Count: {count}",
            )]
        except NautilusApiError as e:
            return [TextContent(type="text", text=f"Error: {e.message}")]
