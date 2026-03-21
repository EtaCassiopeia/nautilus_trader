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
from nautilus_trader.mcp.tools.order_mutations import register_order_mutation_tools


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
    client.patch = AsyncMock()
    return client


class TestNautilusSubmitOrder:
    @pytest.mark.asyncio
    async def test_read_only_blocks(self, mock_server, mock_client) -> None:
        config = McpServerConfig(read_only=True)
        safety = SafetyGuardrails(config)

        await register_order_mutation_tools(mock_server, mock_client, safety)
        tool = mock_server._registered_tools["nautilus_submit_order"]

        result = await tool(
            instrument_id="BTCUSDT-PERP.BINANCE",
            side="BUY",
            order_type="MARKET",
            quantity="0.5",
        )

        assert "Blocked" in result[0].text
        assert "read-only" in result[0].text

    @pytest.mark.asyncio
    async def test_blocked_instrument_rejects(self, mock_server, mock_client) -> None:
        config = McpServerConfig(
            safety_level="UNRESTRICTED",
            blocked_instruments=["BTCUSDT-PERP.BINANCE"],
        )
        safety = SafetyGuardrails(config)

        await register_order_mutation_tools(mock_server, mock_client, safety)
        tool = mock_server._registered_tools["nautilus_submit_order"]

        result = await tool(
            instrument_id="BTCUSDT-PERP.BINANCE",
            side="BUY",
            order_type="MARKET",
            quantity="0.5",
        )

        assert "Blocked" in result[0].text
        assert "blocked" in result[0].text

    @pytest.mark.asyncio
    async def test_max_quantity_rejects(self, mock_server, mock_client) -> None:
        config = McpServerConfig(
            safety_level="UNRESTRICTED",
            max_order_quantity="1.0",
        )
        safety = SafetyGuardrails(config)

        await register_order_mutation_tools(mock_server, mock_client, safety)
        tool = mock_server._registered_tools["nautilus_submit_order"]

        result = await tool(
            instrument_id="BTCUSDT-PERP.BINANCE",
            side="BUY",
            order_type="MARKET",
            quantity="5.0",
        )

        assert "Blocked" in result[0].text
        assert "exceeds maximum" in result[0].text

    @pytest.mark.asyncio
    async def test_standard_requires_confirmation(self, mock_server, mock_client) -> None:
        config = McpServerConfig(safety_level="STANDARD")
        safety = SafetyGuardrails(config)

        await register_order_mutation_tools(mock_server, mock_client, safety)
        tool = mock_server._registered_tools["nautilus_submit_order"]

        result = await tool(
            instrument_id="BTCUSDT-PERP.BINANCE",
            side="BUY",
            order_type="MARKET",
            quantity="0.5",
            confirm=False,
        )

        assert "confirm=true" in result[0].text
        mock_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_confirmed_submits(self, mock_server, mock_client) -> None:
        config = McpServerConfig(safety_level="STANDARD")
        safety = SafetyGuardrails(config)
        mock_client.post.return_value = {
            "client_order_id": "O-001",
            "status": "accepted",
        }

        await register_order_mutation_tools(mock_server, mock_client, safety)
        tool = mock_server._registered_tools["nautilus_submit_order"]

        result = await tool(
            instrument_id="BTCUSDT-PERP.BINANCE",
            side="BUY",
            order_type="MARKET",
            quantity="0.5",
            confirm=True,
        )

        assert "O-001" in result[0].text
        assert "accepted" in result[0].text
        mock_client.post.assert_called_once_with(
            "/api/v1/orders",
            json={
                "instrument_id": "BTCUSDT-PERP.BINANCE",
                "side": "BUY",
                "order_type": "MARKET",
                "quantity": "0.5",
                "time_in_force": "GTC",
            },
        )

    @pytest.mark.asyncio
    async def test_with_price(self, mock_server, mock_client) -> None:
        config = McpServerConfig(safety_level="UNRESTRICTED")
        safety = SafetyGuardrails(config)
        mock_client.post.return_value = {
            "client_order_id": "O-002",
            "status": "accepted",
        }

        await register_order_mutation_tools(mock_server, mock_client, safety)
        tool = mock_server._registered_tools["nautilus_submit_order"]

        result = await tool(
            instrument_id="BTCUSDT-PERP.BINANCE",
            side="BUY",
            order_type="LIMIT",
            quantity="1.0",
            price="50000.00",
        )

        call_kwargs = mock_client.post.call_args
        assert call_kwargs[1]["json"]["price"] == "50000.00"

    @pytest.mark.asyncio
    async def test_api_error_handled(self, mock_server, mock_client) -> None:
        config = McpServerConfig(safety_level="UNRESTRICTED")
        safety = SafetyGuardrails(config)
        mock_client.post.side_effect = NautilusApiError(400, "INVALID", "Bad order")

        await register_order_mutation_tools(mock_server, mock_client, safety)
        tool = mock_server._registered_tools["nautilus_submit_order"]

        result = await tool(
            instrument_id="BTCUSDT-PERP.BINANCE",
            side="BUY",
            order_type="MARKET",
            quantity="0.5",
        )

        assert "Error" in result[0].text
        assert "Bad order" in result[0].text


class TestNautilusCancelOrder:
    @pytest.mark.asyncio
    async def test_read_only_blocks(self, mock_server, mock_client) -> None:
        config = McpServerConfig(read_only=True)
        safety = SafetyGuardrails(config)

        await register_order_mutation_tools(mock_server, mock_client, safety)
        tool = mock_server._registered_tools["nautilus_cancel_order"]

        result = await tool(client_order_id="O-001")

        assert "Blocked" in result[0].text

    @pytest.mark.asyncio
    async def test_success(self, mock_server, mock_client) -> None:
        config = McpServerConfig(safety_level="STANDARD")
        safety = SafetyGuardrails(config)
        mock_client.delete.return_value = {"status": "canceled"}

        await register_order_mutation_tools(mock_server, mock_client, safety)
        tool = mock_server._registered_tools["nautilus_cancel_order"]

        result = await tool(client_order_id="O-001")

        assert "canceled" in result[0].text.lower()
        mock_client.delete.assert_called_once_with("/api/v1/orders/O-001")

    @pytest.mark.asyncio
    async def test_strict_requires_confirmation(self, mock_server, mock_client) -> None:
        config = McpServerConfig(safety_level="STRICT")
        safety = SafetyGuardrails(config)

        await register_order_mutation_tools(mock_server, mock_client, safety)
        tool = mock_server._registered_tools["nautilus_cancel_order"]

        result = await tool(client_order_id="O-001")

        assert "confirm=true" in result[0].text


class TestNautilusModifyOrder:
    @pytest.mark.asyncio
    async def test_success(self, mock_server, mock_client) -> None:
        config = McpServerConfig(safety_level="STANDARD")
        safety = SafetyGuardrails(config)
        mock_client.patch.return_value = {"status": "modified"}

        await register_order_mutation_tools(mock_server, mock_client, safety)
        tool = mock_server._registered_tools["nautilus_modify_order"]

        result = await tool(client_order_id="O-001", quantity="2.0", price="51000.00")

        assert "modified" in result[0].text.lower()
        mock_client.patch.assert_called_once_with(
            "/api/v1/orders/O-001",
            json={"quantity": "2.0", "price": "51000.00"},
        )

    @pytest.mark.asyncio
    async def test_read_only_blocks(self, mock_server, mock_client) -> None:
        config = McpServerConfig(read_only=True)
        safety = SafetyGuardrails(config)

        await register_order_mutation_tools(mock_server, mock_client, safety)
        tool = mock_server._registered_tools["nautilus_modify_order"]

        result = await tool(client_order_id="O-001", quantity="2.0")

        assert "Blocked" in result[0].text


class TestNautilusCancelAllOrders:
    @pytest.mark.asyncio
    async def test_standard_requires_confirmation(self, mock_server, mock_client) -> None:
        config = McpServerConfig(safety_level="STANDARD")
        safety = SafetyGuardrails(config)

        await register_order_mutation_tools(mock_server, mock_client, safety)
        tool = mock_server._registered_tools["nautilus_cancel_all_orders"]

        result = await tool(confirm=False)

        assert "confirm=true" in result[0].text
        mock_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_confirmed_executes(self, mock_server, mock_client) -> None:
        config = McpServerConfig(safety_level="STANDARD")
        safety = SafetyGuardrails(config)
        mock_client.post.return_value = {"canceled_count": 5}

        await register_order_mutation_tools(mock_server, mock_client, safety)
        tool = mock_server._registered_tools["nautilus_cancel_all_orders"]

        result = await tool(confirm=True)

        assert "canceled" in result[0].text.lower()
        assert "5" in result[0].text
        mock_client.post.assert_called_once_with("/api/v1/orders/cancel-all")

    @pytest.mark.asyncio
    async def test_read_only_blocks(self, mock_server, mock_client) -> None:
        config = McpServerConfig(read_only=True)
        safety = SafetyGuardrails(config)

        await register_order_mutation_tools(mock_server, mock_client, safety)
        tool = mock_server._registered_tools["nautilus_cancel_all_orders"]

        result = await tool(confirm=True)

        assert "Blocked" in result[0].text
