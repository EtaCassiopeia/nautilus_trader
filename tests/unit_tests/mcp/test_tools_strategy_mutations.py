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
from nautilus_trader.mcp.tools.strategy_mutations import register_strategy_mutation_tools


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
    client.delete = AsyncMock()
    return client


class TestNautilusStartStrategy:
    @pytest.mark.asyncio
    async def test_read_only_blocks(self, mock_server, mock_client) -> None:
        config = McpServerConfig(read_only=True)
        safety = SafetyGuardrails(config)

        await register_strategy_mutation_tools(mock_server, mock_client, safety)
        tool = mock_server._registered_tools["nautilus_start_strategy"]

        result = await tool(strategy_id="strat-001")

        assert "Blocked" in result[0].text
        assert "read-only" in result[0].text

    @pytest.mark.asyncio
    async def test_strict_requires_confirmation(self, mock_server, mock_client) -> None:
        config = McpServerConfig(safety_level="STRICT")
        safety = SafetyGuardrails(config)

        await register_strategy_mutation_tools(mock_server, mock_client, safety)
        tool = mock_server._registered_tools["nautilus_start_strategy"]

        result = await tool(strategy_id="strat-001")

        assert "confirm=true" in result[0].text

    @pytest.mark.asyncio
    async def test_standard_no_confirmation_for_write(self, mock_server, mock_client) -> None:
        config = McpServerConfig(safety_level="STANDARD")
        safety = SafetyGuardrails(config)
        mock_client.post.return_value = {"status": "running"}

        await register_strategy_mutation_tools(mock_server, mock_client, safety)
        tool = mock_server._registered_tools["nautilus_start_strategy"]

        result = await tool(strategy_id="strat-001")

        assert "started" in result[0].text.lower()
        assert "strat-001" in result[0].text
        mock_client.post.assert_called_once_with("/api/v1/strategies/strat-001/start")

    @pytest.mark.asyncio
    async def test_api_error_handled(self, mock_server, mock_client) -> None:
        config = McpServerConfig(safety_level="UNRESTRICTED")
        safety = SafetyGuardrails(config)
        mock_client.post.side_effect = NautilusApiError(404, "NOT_FOUND", "Strategy not found")

        await register_strategy_mutation_tools(mock_server, mock_client, safety)
        tool = mock_server._registered_tools["nautilus_start_strategy"]

        result = await tool(strategy_id="strat-999")

        assert "Error" in result[0].text
        assert "Strategy not found" in result[0].text


class TestNautilusStopStrategy:
    @pytest.mark.asyncio
    async def test_success(self, mock_server, mock_client) -> None:
        config = McpServerConfig(safety_level="STANDARD")
        safety = SafetyGuardrails(config)
        mock_client.post.return_value = {"status": "stopped"}

        await register_strategy_mutation_tools(mock_server, mock_client, safety)
        tool = mock_server._registered_tools["nautilus_stop_strategy"]

        result = await tool(strategy_id="strat-001")

        assert "stopped" in result[0].text.lower()
        mock_client.post.assert_called_once_with("/api/v1/strategies/strat-001/stop")


class TestNautilusRemoveStrategy:
    @pytest.mark.asyncio
    async def test_standard_requires_confirmation(self, mock_server, mock_client) -> None:
        config = McpServerConfig(safety_level="STANDARD")
        safety = SafetyGuardrails(config)

        await register_strategy_mutation_tools(mock_server, mock_client, safety)
        tool = mock_server._registered_tools["nautilus_remove_strategy"]

        result = await tool(strategy_id="strat-001", confirm=False)

        assert "confirm=true" in result[0].text
        mock_client.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_confirmed_executes(self, mock_server, mock_client) -> None:
        config = McpServerConfig(safety_level="STANDARD")
        safety = SafetyGuardrails(config)
        mock_client.delete.return_value = {"status": "removed"}

        await register_strategy_mutation_tools(mock_server, mock_client, safety)
        tool = mock_server._registered_tools["nautilus_remove_strategy"]

        result = await tool(strategy_id="strat-001", confirm=True)

        assert "removed" in result[0].text.lower()
        mock_client.delete.assert_called_once_with("/api/v1/strategies/strat-001")


class TestNautilusMarketExitStrategy:
    @pytest.mark.asyncio
    async def test_standard_requires_confirmation(self, mock_server, mock_client) -> None:
        config = McpServerConfig(safety_level="STANDARD")
        safety = SafetyGuardrails(config)

        await register_strategy_mutation_tools(mock_server, mock_client, safety)
        tool = mock_server._registered_tools["nautilus_market_exit_strategy"]

        result = await tool(strategy_id="strat-001", confirm=False)

        assert "confirm=true" in result[0].text

    @pytest.mark.asyncio
    async def test_confirmed_executes(self, mock_server, mock_client) -> None:
        config = McpServerConfig(safety_level="STANDARD")
        safety = SafetyGuardrails(config)
        mock_client.post.return_value = {"status": "exiting"}

        await register_strategy_mutation_tools(mock_server, mock_client, safety)
        tool = mock_server._registered_tools["nautilus_market_exit_strategy"]

        result = await tool(strategy_id="strat-001", confirm=True)

        assert "market exit" in result[0].text.lower()
        mock_client.post.assert_called_once_with("/api/v1/strategies/strat-001/market-exit")

    @pytest.mark.asyncio
    async def test_read_only_blocks(self, mock_server, mock_client) -> None:
        config = McpServerConfig(read_only=True)
        safety = SafetyGuardrails(config)

        await register_strategy_mutation_tools(mock_server, mock_client, safety)
        tool = mock_server._registered_tools["nautilus_market_exit_strategy"]

        result = await tool(strategy_id="strat-001", confirm=True)

        assert "Blocked" in result[0].text
