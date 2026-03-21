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


def register_strategy_tools(
    server: Server,
    client: NautilusClient,
    safety: SafetyGuardrails,
) -> None:
    """Register strategy read-only tools."""

    @server.tool()
    async def nautilus_list_strategies(state: str = "") -> list[TextContent]:
        """List all strategies with their current state. Optionally filter by state (RUNNING, STOPPED, etc.)."""
        try:
            params = {}
            if state:
                params["state"] = state
            result = await client.get("/api/v1/strategies", params=params if params else None)
            data = result.get("data", [])
            if not data:
                return [TextContent(type="text", text="No strategies found.")]

            lines = [f"Strategies ({len(data)}):"]
            for s in data:
                sid = s.get("strategy_id", "N/A")
                stype = s.get("type", "N/A")
                sstate = s.get("state", "N/A")
                lines.append(f"  {sid} ({stype}) — {sstate}")
            return [TextContent(type="text", text="\n".join(lines))]
        except NautilusApiError as e:
            return [TextContent(type="text", text=f"Error: {e.message}")]
