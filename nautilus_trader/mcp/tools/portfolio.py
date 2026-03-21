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


def register_portfolio_tools(
    server: Server,
    client: NautilusClient,
    safety: SafetyGuardrails,
) -> None:
    """Register portfolio read-only tools."""

    @server.tool()
    async def nautilus_get_portfolio_summary() -> list[TextContent]:
        """Get a comprehensive portfolio overview including balances, positions, and P&L."""
        try:
            result = await client.get("/api/v1/portfolio")
            data = result.get("data", {})
            lines = ["Portfolio Summary:"]

            for section in ["balances_locked", "unrealized_pnls", "realized_pnls", "net_exposures"]:
                section_data = data.get(section, {})
                lines.append(f"\n  {section.replace('_', ' ').title()}:")
                if section_data:
                    for k, v in section_data.items():
                        lines.append(f"    {k}: {v}")
                else:
                    lines.append("    (none)")

            return [TextContent(type="text", text="\n".join(lines))]
        except NautilusApiError as e:
            return [TextContent(type="text", text=f"Error: {e.message}")]

    @server.tool()
    async def nautilus_get_balances(venue: str = "") -> list[TextContent]:
        """Get account balances, optionally filtered by venue."""
        try:
            params = {"venue": venue} if venue else None
            result = await client.get("/api/v1/portfolio/balances", params=params)
            data = result.get("data", {})
            if not data:
                return [TextContent(type="text", text="No balances found.")]
            lines = ["Balances:"]
            for k, v in data.items():
                lines.append(f"  {k}: {v}")
            return [TextContent(type="text", text="\n".join(lines))]
        except NautilusApiError as e:
            return [TextContent(type="text", text=f"Error: {e.message}")]

    @server.tool()
    async def nautilus_get_positions(instrument_id: str = "") -> list[TextContent]:
        """Get open positions, optionally filtered by instrument ID."""
        try:
            params = {"instrument_id": instrument_id} if instrument_id else None
            result = await client.get("/api/v1/portfolio/positions", params=params)
            data = result.get("data", [])
            if not data:
                return [TextContent(type="text", text="No open positions.")]
            lines = [f"Open Positions ({len(data)}):"]
            for p in data:
                inst = p.get("instrument_id", "N/A")
                side = p.get("side", "N/A")
                qty = p.get("quantity", "N/A")
                entry = p.get("avg_px_open", "N/A")
                upnl = p.get("unrealized_pnl", "N/A")
                lines.append(f"  {inst}  {side} {qty}  entry: {entry}  unrealized: {upnl}")
            return [TextContent(type="text", text="\n".join(lines))]
        except NautilusApiError as e:
            return [TextContent(type="text", text=f"Error: {e.message}")]

    @server.tool()
    async def nautilus_get_pnl() -> list[TextContent]:
        """Get realized and unrealized P&L breakdown."""
        try:
            result = await client.get("/api/v1/portfolio/pnl")
            data = result.get("data", {})
            lines = ["P&L:"]
            for section in ["unrealized_pnls", "realized_pnls"]:
                section_data = data.get(section, {})
                lines.append(f"  {section.replace('_', ' ').title()}:")
                if section_data:
                    for k, v in section_data.items():
                        lines.append(f"    {k}: {v}")
                else:
                    lines.append("    (none)")
            return [TextContent(type="text", text="\n".join(lines))]
        except NautilusApiError as e:
            return [TextContent(type="text", text=f"Error: {e.message}")]

    @server.tool()
    async def nautilus_get_exposure() -> list[TextContent]:
        """Get net exposure by currency."""
        try:
            result = await client.get("/api/v1/portfolio/exposure")
            data = result.get("data", {})
            exposures = data.get("net_exposures", {})
            if not exposures:
                return [TextContent(type="text", text="No net exposures.")]
            lines = ["Net Exposures:"]
            for k, v in exposures.items():
                lines.append(f"  {k}: {v}")
            return [TextContent(type="text", text="\n".join(lines))]
        except NautilusApiError as e:
            return [TextContent(type="text", text=f"Error: {e.message}")]
