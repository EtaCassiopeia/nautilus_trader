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
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import StrategyId


def _mock_position(
    instrument_id: str = "AAPL.XNAS",
    strategy_id: str = "EMACross-001",
    side_name: str = "LONG",
    quantity: str = "100",
    avg_px_open: str = "150.50",
    unrealized_pnl: str = "250.00",
    realized_pnl: str = "0.00",
    ts_opened: int = 1_000_000_000,
    ts_last: int = 1_000_000_000,
):
    position = MagicMock()
    type(position).instrument_id = PropertyMock(return_value=InstrumentId.from_str(instrument_id))
    type(position).strategy_id = PropertyMock(return_value=StrategyId(strategy_id))
    position.side = MagicMock()
    position.side.name = side_name
    position.quantity = quantity
    position.avg_px_open = avg_px_open
    position.unrealized_pnl = unrealized_pnl
    position.realized_pnl = realized_pnl
    position.ts_opened = ts_opened
    position.ts_last = ts_last
    return position


def _mock_kernel_with_portfolio(
    balances_locked=None,
    unrealized_pnls=None,
    realized_pnls=None,
    net_exposures=None,
    positions_open=None,
):
    kernel = MagicMock()
    type(kernel).trader_id = PropertyMock(return_value="TRADER-001")
    kernel.is_running.return_value = True
    kernel.logger = MagicMock()

    portfolio = MagicMock()
    portfolio.balances_locked.return_value = balances_locked or {}
    portfolio.unrealized_pnls.return_value = unrealized_pnls or {}
    portfolio.realized_pnls.return_value = realized_pnls or {}
    portfolio.net_exposures.return_value = net_exposures or {}
    type(kernel).portfolio = PropertyMock(return_value=portfolio)

    cache = MagicMock()
    cache.positions_open.return_value = positions_open or []
    type(kernel).cache = PropertyMock(return_value=cache)

    trader = MagicMock()
    trader.strategies.return_value = []
    trader.actors.return_value = []
    type(kernel).trader = PropertyMock(return_value=trader)

    return kernel


class TestPortfolioSummary:
    @pytest.mark.asyncio
    async def test_empty_portfolio(self) -> None:
        kernel = _mock_kernel_with_portfolio()
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/portfolio")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["balances_locked"] == {}
        assert data["unrealized_pnls"] == {}
        assert data["realized_pnls"] == {}
        assert data["net_exposures"] == {}

    @pytest.mark.asyncio
    async def test_portfolio_with_values(self) -> None:
        kernel = _mock_kernel_with_portfolio(
            unrealized_pnls={"USD": "1500.00"},
            realized_pnls={"USD": "3200.00"},
            net_exposures={"USD": "50000.00"},
        )
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/portfolio")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["unrealized_pnls"] == {"USD": "1500.00"}
        assert data["realized_pnls"] == {"USD": "3200.00"}


class TestPortfolioPositions:
    @pytest.mark.asyncio
    async def test_empty_positions(self) -> None:
        kernel = _mock_kernel_with_portfolio()
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/portfolio/positions")

        assert response.status_code == 200
        assert response.json()["data"] == []

    @pytest.mark.asyncio
    async def test_returns_position_summaries(self) -> None:
        positions = [
            _mock_position(instrument_id="AAPL.XNAS", side_name="LONG", quantity="100"),
            _mock_position(instrument_id="MSFT.XNAS", side_name="SHORT", quantity="50"),
        ]
        kernel = _mock_kernel_with_portfolio(positions_open=positions)
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/portfolio/positions")

        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 2
        assert data[0]["instrument_id"] == "AAPL.XNAS"
        assert data[0]["side"] == "LONG"
        assert data[1]["instrument_id"] == "MSFT.XNAS"
        assert data[1]["side"] == "SHORT"


class TestPortfolioPnL:
    @pytest.mark.asyncio
    async def test_pnl_summary(self) -> None:
        kernel = _mock_kernel_with_portfolio(
            unrealized_pnls={"USD": "500.00"},
            realized_pnls={"USD": "1200.00"},
        )
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/portfolio/pnl")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["unrealized_pnls"] == {"USD": "500.00"}
        assert data["realized_pnls"] == {"USD": "1200.00"}


class TestPortfolioExposure:
    @pytest.mark.asyncio
    async def test_exposure_summary(self) -> None:
        kernel = _mock_kernel_with_portfolio(
            net_exposures={"USD": "75000.00"},
        )
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/portfolio/exposure")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["net_exposures"] == {"USD": "75000.00"}
