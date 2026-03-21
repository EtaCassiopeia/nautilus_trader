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

from mcp.server import Server
from mcp.types import TextContent

from nautilus_trader.mcp.client import NautilusApiError
from nautilus_trader.mcp.client import NautilusClient
from nautilus_trader.mcp.safety import SafetyGuardrails


def register_order_tools(
    server: Server,
    client: NautilusClient,
    safety: SafetyGuardrails,
) -> None:
    """Register order read-only tools."""

    @server.tool()
    async def nautilus_list_orders(
        status: str = "all",
        strategy_id: str = "",
        instrument_id: str = "",
        limit: int = 50,
    ) -> list[TextContent]:
        """List orders with optional filtering by status (open/closed/all), strategy_id, instrument_id, and limit."""
        try:
            params: dict = {"status": status, "limit": limit}
            if strategy_id:
                params["strategy_id"] = strategy_id
            if instrument_id:
                params["instrument_id"] = instrument_id

            result = await client.get("/api/v1/orders", params=params)
            data = result.get("data", [])
            if not data:
                return [TextContent(type="text", text="No orders found.")]

            lines = [f"Orders ({len(data)}):"]
            for o in data:
                oid = o.get("client_order_id", "N/A")
                inst = o.get("instrument_id", "N/A")
                side = o.get("side", "N/A")
                otype = o.get("order_type", "N/A")
                qty = o.get("quantity", "N/A")
                ostat = o.get("status", "N/A")
                filled = o.get("filled_qty", "0")
                lines.append(f"  {oid}  {side} {qty} {inst} ({otype})  Status: {ostat}  Filled: {filled}")
            return [TextContent(type="text", text="\n".join(lines))]
        except NautilusApiError as e:
            return [TextContent(type="text", text=f"Error: {e.message}")]

    @server.tool()
    async def nautilus_get_order(client_order_id: str) -> list[TextContent]:
        """Get detailed information about a specific order by its client order ID."""
        try:
            result = await client.get(f"/api/v1/orders/{client_order_id}")
            data = result.get("data", {})
            lines = [
                f"Order: {client_order_id}",
                f"  Instrument: {data.get('instrument_id', 'N/A')}",
                f"  Side: {data.get('side', 'N/A')}",
                f"  Type: {data.get('order_type', 'N/A')}",
                f"  Quantity: {data.get('quantity', 'N/A')}",
                f"  Price: {data.get('price', 'N/A')}",
                f"  Status: {data.get('status', 'N/A')}",
                f"  Filled: {data.get('filled_qty', '0')}",
                f"  Avg Px: {data.get('avg_px', 'N/A')}",
                f"  Strategy: {data.get('strategy_id', 'N/A')}",
            ]
            return [TextContent(type="text", text="\n".join(lines))]
        except NautilusApiError as e:
            if e.status_code == 404:
                return [TextContent(
                    type="text",
                    text=f"Order '{client_order_id}' not found. Use nautilus_list_orders to see available orders.",
                )]
            return [TextContent(type="text", text=f"Error: {e.message}")]
