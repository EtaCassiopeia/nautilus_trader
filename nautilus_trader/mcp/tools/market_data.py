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


def register_market_data_tools(
    server: Server,
    client: NautilusClient,
    safety: SafetyGuardrails,
) -> None:
    """Register market data read-only tools."""

    @server.tool()
    async def nautilus_list_instruments(venue: str = "") -> list[TextContent]:
        """List available instruments, optionally filtered by venue."""
        try:
            params = {"venue": venue} if venue else None
            result = await client.get("/api/v1/cache/instruments", params=params)
            data = result.get("data", [])
            if not data:
                return [TextContent(type="text", text="No instruments found.")]
            lines = [f"Instruments ({len(data)}):"]
            for inst in data:
                if isinstance(inst, dict):
                    iid = inst.get("instrument_id", "N/A")
                    itype = inst.get("type", "N/A")
                    lines.append(f"  {iid} ({itype})")
                else:
                    lines.append(f"  {inst}")
            return [TextContent(type="text", text="\n".join(lines))]
        except NautilusApiError as e:
            return [TextContent(type="text", text=f"Error: {e.message}")]

    @server.tool()
    async def nautilus_get_instrument(instrument_id: str) -> list[TextContent]:
        """Get detailed information about a specific instrument."""
        try:
            result = await client.get(f"/api/v1/cache/instruments/{instrument_id}")
            data = result.get("data", {})
            lines = [f"Instrument: {instrument_id}"]
            for k, v in data.items():
                lines.append(f"  {k}: {v}")
            return [TextContent(type="text", text="\n".join(lines))]
        except NautilusApiError as e:
            return [TextContent(type="text", text=f"Error: {e.message}")]

    @server.tool()
    async def nautilus_get_latest_quote(instrument_id: str) -> list[TextContent]:
        """Get the latest bid/ask quote for an instrument."""
        try:
            result = await client.get(f"/api/v1/data/quotes/{instrument_id}")
            data = result.get("data", {})
            lines = [
                f"Quote: {instrument_id}",
                f"  Bid: {data.get('bid_price', 'N/A')} ({data.get('bid_size', 'N/A')})",
                f"  Ask: {data.get('ask_price', 'N/A')} ({data.get('ask_size', 'N/A')})",
                f"  Timestamp: {data.get('ts_event', 'N/A')}",
            ]
            return [TextContent(type="text", text="\n".join(lines))]
        except NautilusApiError as e:
            return [TextContent(type="text", text=f"Error: {e.message}")]

    @server.tool()
    async def nautilus_get_latest_bars(
        instrument_id: str,
        bar_type: str = "",
        count: int = 10,
    ) -> list[TextContent]:
        """Get recent OHLCV bars for an instrument."""
        try:
            params: dict = {"count": count}
            if bar_type:
                params["bar_type"] = bar_type
            result = await client.get(f"/api/v1/data/bars/{instrument_id}", params=params)
            data = result.get("data", [])
            if not data:
                return [TextContent(type="text", text=f"No bars found for {instrument_id}.")]
            lines = [f"Bars for {instrument_id} ({len(data)}):"]
            for bar in data:
                o = bar.get("open", "N/A")
                h = bar.get("high", "N/A")
                l = bar.get("low", "N/A")
                c = bar.get("close", "N/A")
                v = bar.get("volume", "N/A")
                lines.append(f"  O:{o}  H:{h}  L:{l}  C:{c}  V:{v}")
            return [TextContent(type="text", text="\n".join(lines))]
        except NautilusApiError as e:
            return [TextContent(type="text", text=f"Error: {e.message}")]
