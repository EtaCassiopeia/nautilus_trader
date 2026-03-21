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

import json

from mcp.server import Server
from mcp.types import Resource
from mcp.types import TextContent

from nautilus_trader.mcp.client import NautilusApiError
from nautilus_trader.mcp.client import NautilusClient


def register_resources(server: Server, client: NautilusClient) -> None:
    """Register MCP resources for the NautilusTrader server."""

    @server.list_resources()
    async def list_resources() -> list[Resource]:
        return [
            Resource(
                uri="nautilus://status",
                name="Trading Node Status",
                description="Current state of the NautilusTrader node",
                mimeType="application/json",
            ),
            Resource(
                uri="nautilus://portfolio",
                name="Portfolio State",
                description="Current portfolio state including balances, positions, and P&L",
                mimeType="application/json",
            ),
        ]

    @server.read_resource()
    async def read_resource(uri: str) -> str:
        try:
            if uri == "nautilus://status":
                result = await client.get("/health")
                return json.dumps(result, indent=2, default=str)
            elif uri == "nautilus://portfolio":
                result = await client.get("/api/v1/portfolio")
                return json.dumps(result, indent=2, default=str)
            else:
                return json.dumps({"error": f"Unknown resource: {uri}"})
        except NautilusApiError as e:
            return json.dumps({"error": e.message})
