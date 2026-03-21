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

from enum import Enum
from unittest.mock import MagicMock
from unittest.mock import PropertyMock

import pytest
from httpx import ASGITransport
from httpx import AsyncClient

from nautilus_trader.api.config import ApiServerConfig
from nautilus_trader.api.server import create_app
from nautilus_trader.model.identifiers import StrategyId


class _MockState(Enum):
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"


def _mock_strategy(strategy_id: str, state_name: str = "RUNNING"):
    strategy = MagicMock()
    type(strategy).id = PropertyMock(return_value=StrategyId(strategy_id))
    strategy.state = MagicMock()
    strategy.state.name = state_name
    strategy.order_id_tag = strategy_id.split("-")[-1]
    type(strategy).__name__ = "MockStrategy"
    return strategy


def _mock_kernel_with_strategies(strategies=None):
    kernel = MagicMock()
    type(kernel).trader_id = PropertyMock(return_value="TRADER-001")
    kernel.is_running.return_value = True
    kernel.logger = MagicMock()

    trader = MagicMock()
    trader.strategies.return_value = strategies or []
    trader.strategy_ids.return_value = [s.id for s in (strategies or [])]
    trader.actor_ids.return_value = []
    trader.actors.return_value = []
    type(kernel).trader = PropertyMock(return_value=trader)

    return kernel


class TestListStrategies:
    @pytest.mark.asyncio
    async def test_empty_list(self) -> None:
        kernel = _mock_kernel_with_strategies([])
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/strategies")

        assert response.status_code == 200
        assert response.json()["data"] == []

    @pytest.mark.asyncio
    async def test_returns_strategy_summaries(self) -> None:
        strategies = [
            _mock_strategy("EMACross-001", "RUNNING"),
            _mock_strategy("Momentum-002", "STOPPED"),
        ]
        kernel = _mock_kernel_with_strategies(strategies)
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/strategies")

        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 2
        assert data[0]["strategy_id"] == "EMACross-001"
        assert data[0]["state"] == "RUNNING"
        assert data[1]["strategy_id"] == "Momentum-002"
        assert data[1]["state"] == "STOPPED"


class TestGetStrategy:
    @pytest.mark.asyncio
    async def test_returns_strategy_detail(self) -> None:
        strategies = [_mock_strategy("EMACross-001", "RUNNING")]
        kernel = _mock_kernel_with_strategies(strategies)
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/strategies/EMACross-001")

        assert response.status_code == 200
        assert response.json()["data"]["strategy_id"] == "EMACross-001"

    @pytest.mark.asyncio
    async def test_not_found(self) -> None:
        kernel = _mock_kernel_with_strategies([])
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/strategies/NoSuch-001")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "STRATEGY_NOT_FOUND"


class TestStartStrategy:
    @pytest.mark.asyncio
    async def test_start_success(self) -> None:
        kernel = _mock_kernel_with_strategies([])
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post("/api/v1/strategies/EMACross-001/start")

        assert response.status_code == 200
        assert response.json()["data"]["action"] == "started"

    @pytest.mark.asyncio
    async def test_start_failure(self) -> None:
        kernel = _mock_kernel_with_strategies([])
        kernel.trader.start_strategy.side_effect = ValueError("Strategy not found")
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post("/api/v1/strategies/NoSuch-001/start")

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "STRATEGY_START_FAILED"


class TestStopStrategy:
    @pytest.mark.asyncio
    async def test_stop_success(self) -> None:
        kernel = _mock_kernel_with_strategies([])
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post("/api/v1/strategies/EMACross-001/stop")

        assert response.status_code == 200
        assert response.json()["data"]["action"] == "stopped"


class TestRemoveStrategy:
    @pytest.mark.asyncio
    async def test_remove_success(self) -> None:
        kernel = _mock_kernel_with_strategies([])
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.delete("/api/v1/strategies/EMACross-001")

        assert response.status_code == 200
        assert response.json()["data"]["action"] == "removed"


class TestMarketExitStrategy:
    @pytest.mark.asyncio
    async def test_market_exit_success(self) -> None:
        kernel = _mock_kernel_with_strategies([])
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/v1/strategies/EMACross-001/market-exit",
            )

        assert response.status_code == 200
        assert response.json()["data"]["action"] == "market_exit"
