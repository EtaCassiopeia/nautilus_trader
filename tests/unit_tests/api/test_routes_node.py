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


def _mock_kernel():
    kernel = MagicMock()
    type(kernel).trader_id = PropertyMock(return_value="TRADER-001")
    type(kernel).instance_id = PropertyMock(return_value="abc-123")
    type(kernel).machine_id = PropertyMock(return_value="test-host")
    type(kernel).environment = PropertyMock(
        return_value=MagicMock(name="SANDBOX"),
    )
    kernel.environment.name = "SANDBOX"
    kernel.is_running.return_value = True
    kernel.logger = MagicMock()

    trader = MagicMock()
    trader.strategy_ids.return_value = ["S-001", "S-002"]
    trader.actor_ids.return_value = ["A-001"]
    type(kernel).trader = PropertyMock(return_value=trader)

    return kernel


class TestNodeStatusRoute:
    @pytest.mark.asyncio
    async def test_returns_node_status(self) -> None:
        kernel = _mock_kernel()
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/node/status")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["trader_id"] == "TRADER-001"
        assert data["instance_id"] == "abc-123"
        assert data["machine_id"] == "test-host"
        assert data["is_running"] is True
        assert data["strategies_count"] == 2
        assert data["actors_count"] == 1


class TestNodeStopRoute:
    @pytest.mark.asyncio
    async def test_initiates_shutdown(self) -> None:
        kernel = _mock_kernel()
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post("/api/v1/node/stop")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["message"] == "Shutdown initiated"
