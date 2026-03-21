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

from unittest.mock import MagicMock
from unittest.mock import PropertyMock

import pytest
from httpx import ASGITransport
from httpx import AsyncClient

from nautilus_trader.api.config import ApiServerConfig
from nautilus_trader.api.server import create_app


def _mock_kernel_with_risk(
    state_name: str = "RUNNING",
    is_running: bool = True,
    is_bypassed: bool = False,
    trading_state_name: str = "ACTIVE",
    command_count: int = 0,
    event_count: int = 0,
    max_order_submit_rate: tuple = (100, "00:00:01"),
    max_order_modify_rate: tuple = (100, "00:00:01"),
    max_notionals: dict | None = None,
    debug: bool = False,
):
    kernel = MagicMock()
    type(kernel).trader_id = PropertyMock(return_value="TRADER-001")
    kernel.is_running.return_value = True
    kernel.logger = MagicMock()

    risk_engine = MagicMock()
    risk_engine.id = "RiskEngine-001"
    risk_engine.state = MagicMock()
    risk_engine.state.name = state_name
    risk_engine.is_running = is_running
    risk_engine.is_bypassed = is_bypassed
    risk_engine.trading_state = MagicMock()
    risk_engine.trading_state.name = trading_state_name
    risk_engine.command_count = command_count
    risk_engine.event_count = event_count
    risk_engine.max_order_submit_rate.return_value = max_order_submit_rate
    risk_engine.max_order_modify_rate.return_value = max_order_modify_rate
    risk_engine.max_notionals_per_order.return_value = max_notionals or {}
    risk_engine.debug = debug
    type(kernel).risk_engine = PropertyMock(return_value=risk_engine)

    trader = MagicMock()
    trader.strategies.return_value = []
    trader.actors.return_value = []
    type(kernel).trader = PropertyMock(return_value=trader)

    data_engine = MagicMock()
    data_engine.state = MagicMock()
    data_engine.state.name = "RUNNING"
    type(kernel).data_engine = PropertyMock(return_value=data_engine)

    return kernel


class TestRiskStatus:
    @pytest.mark.asyncio
    async def test_returns_status(self) -> None:
        kernel = _mock_kernel_with_risk(
            state_name="RUNNING",
            is_running=True,
            is_bypassed=False,
            trading_state_name="ACTIVE",
            command_count=42,
            event_count=15,
        )
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/risk/status")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["component_id"] == "RiskEngine-001"
        assert data["state"] == "RUNNING"
        assert data["is_running"] is True
        assert data["is_bypassed"] is False
        assert data["trading_state"] == "ACTIVE"
        assert data["command_count"] == 42
        assert data["event_count"] == 15

    @pytest.mark.asyncio
    async def test_bypassed_engine(self) -> None:
        kernel = _mock_kernel_with_risk(is_bypassed=True)
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/risk/status")

        assert response.status_code == 200
        assert response.json()["data"]["is_bypassed"] is True


class TestRiskConfig:
    @pytest.mark.asyncio
    async def test_returns_config(self) -> None:
        kernel = _mock_kernel_with_risk(
            is_bypassed=False,
            trading_state_name="ACTIVE",
            debug=False,
        )
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/risk/config")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["is_bypassed"] is False
        assert data["trading_state"] == "ACTIVE"
        assert data["debug"] is False
        assert data["max_notionals_per_order"] == {}

    @pytest.mark.asyncio
    async def test_config_with_notionals(self) -> None:
        kernel = _mock_kernel_with_risk(
            max_notionals={"AAPL.XNAS": 100_000},
        )
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/risk/config")

        assert response.status_code == 200
        data = response.json()["data"]
        assert "AAPL.XNAS" in data["max_notionals_per_order"]
