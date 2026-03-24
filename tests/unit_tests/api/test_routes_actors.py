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
from nautilus_trader.model.identifiers import ComponentId


def _mock_actor(actor_id: str, state_name: str = "RUNNING"):
    actor = MagicMock()
    type(actor).id = PropertyMock(return_value=ComponentId(actor_id))
    actor.state = MagicMock()
    actor.state.name = state_name
    type(actor).__name__ = "MockActor"
    return actor


def _mock_kernel_with_actors(actors=None):
    kernel = MagicMock()
    type(kernel).trader_id = PropertyMock(return_value="TRADER-001")
    kernel.is_running.return_value = True
    kernel.logger = MagicMock()

    trader = MagicMock()
    trader.strategies.return_value = []
    trader.actors.return_value = actors or []
    trader.strategy_ids.return_value = []
    trader.actor_ids.return_value = [a.id for a in (actors or [])]
    type(kernel).trader = PropertyMock(return_value=trader)

    data_engine = MagicMock()
    data_engine.state = MagicMock()
    data_engine.state.name = "RUNNING"
    type(kernel).data_engine = PropertyMock(return_value=data_engine)

    risk_engine = MagicMock()
    risk_engine.state = MagicMock()
    risk_engine.state.name = "RUNNING"
    type(kernel).risk_engine = PropertyMock(return_value=risk_engine)

    return kernel


class TestListActors:
    @pytest.mark.asyncio
    async def test_empty_list(self) -> None:
        kernel = _mock_kernel_with_actors([])
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/actors")

        assert response.status_code == 200
        assert response.json()["data"] == []

    @pytest.mark.asyncio
    async def test_returns_actor_summaries(self) -> None:
        actors = [
            _mock_actor("DataCollector-001", "RUNNING"),
            _mock_actor("RiskMonitor-002", "STOPPED"),
        ]
        kernel = _mock_kernel_with_actors(actors)
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/actors")

        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 2
        assert data[0]["actor_id"] == "DataCollector-001"
        assert data[0]["state"] == "RUNNING"
        assert data[1]["actor_id"] == "RiskMonitor-002"
        assert data[1]["state"] == "STOPPED"


class TestGetActor:
    @pytest.mark.asyncio
    async def test_returns_actor_detail(self) -> None:
        actors = [_mock_actor("DataCollector-001", "RUNNING")]
        kernel = _mock_kernel_with_actors(actors)
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/actors/DataCollector-001")

        assert response.status_code == 200
        assert response.json()["data"]["actor_id"] == "DataCollector-001"
        assert response.json()["data"]["state"] == "RUNNING"

    @pytest.mark.asyncio
    async def test_not_found(self) -> None:
        kernel = _mock_kernel_with_actors([])
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/actors/NoSuch-001")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "ACTOR_NOT_FOUND"
