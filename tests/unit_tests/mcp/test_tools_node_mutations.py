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

from unittest.mock import AsyncMock
from unittest.mock import MagicMock

import pytest

from nautilus_trader.mcp.client import NautilusApiError
from nautilus_trader.mcp.config import McpServerConfig
from nautilus_trader.mcp.safety import SafetyGuardrails
from nautilus_trader.mcp.tools.node_mutations import register_node_mutation_tools


@pytest.fixture
def mock_server():
    server = MagicMock()
    registered_tools = {}

    def tool_decorator():
        def decorator(fn):
            registered_tools[fn.__name__] = fn
            return fn
        return decorator

    server.tool = tool_decorator
    server._registered_tools = registered_tools
    return server


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.post = AsyncMock()
    return client


class TestNautilusNodeStop:
    @pytest.mark.asyncio
    async def test_read_only_blocks(self, mock_server, mock_client) -> None:
        config = McpServerConfig(read_only=True)
        safety = SafetyGuardrails(config)

        await register_node_mutation_tools(mock_server, mock_client, safety)
        tool = mock_server._registered_tools["nautilus_node_stop"]

        result = await tool()

        assert "Blocked" in result[0].text
        assert "read-only" in result[0].text
        mock_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_blocked_tool_rejected(self, mock_server, mock_client) -> None:
        config = McpServerConfig(blocked_tools=["nautilus_node_stop"])
        safety = SafetyGuardrails(config)

        await register_node_mutation_tools(mock_server, mock_client, safety)
        tool = mock_server._registered_tools["nautilus_node_stop"]

        result = await tool()

        assert "Blocked" in result[0].text
        assert "not allowed" in result[0].text

    @pytest.mark.asyncio
    async def test_standard_requires_confirmation(self, mock_server, mock_client) -> None:
        config = McpServerConfig(safety_level="STANDARD")
        safety = SafetyGuardrails(config)

        await register_node_mutation_tools(mock_server, mock_client, safety)
        tool = mock_server._registered_tools["nautilus_node_stop"]

        result = await tool(confirm=False)

        assert "confirm=true" in result[0].text
        mock_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_standard_confirmed_executes(self, mock_server, mock_client) -> None:
        config = McpServerConfig(safety_level="STANDARD")
        safety = SafetyGuardrails(config)
        mock_client.post.return_value = {"status": "stopping"}

        await register_node_mutation_tools(mock_server, mock_client, safety)
        tool = mock_server._registered_tools["nautilus_node_stop"]

        result = await tool(confirm=True)

        assert "stop initiated" in result[0].text.lower()
        assert "stopping" in result[0].text
        mock_client.post.assert_called_once_with("/api/v1/node/stop")

    @pytest.mark.asyncio
    async def test_unrestricted_no_confirmation_needed(self, mock_server, mock_client) -> None:
        config = McpServerConfig(safety_level="UNRESTRICTED")
        safety = SafetyGuardrails(config)
        mock_client.post.return_value = {"status": "stopping"}

        await register_node_mutation_tools(mock_server, mock_client, safety)
        tool = mock_server._registered_tools["nautilus_node_stop"]

        result = await tool(confirm=False)

        assert "stop initiated" in result[0].text.lower()
        mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_api_error_handled(self, mock_server, mock_client) -> None:
        config = McpServerConfig(safety_level="UNRESTRICTED")
        safety = SafetyGuardrails(config)
        mock_client.post.side_effect = NautilusApiError(500, "INTERNAL", "Server error")

        await register_node_mutation_tools(mock_server, mock_client, safety)
        tool = mock_server._registered_tools["nautilus_node_stop"]

        result = await tool()

        assert "Error" in result[0].text
        assert "Server error" in result[0].text
