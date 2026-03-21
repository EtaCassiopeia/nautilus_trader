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


def _mock_bar(
    bar_type: str = "AAPL.XNAS-1-MINUTE-LAST-EXTERNAL",
    open_price: str = "150.00",
    high: str = "151.00",
    low: str = "149.50",
    close: str = "150.75",
    volume: str = "10000",
    ts_event: int = 1_000_000_000,
    ts_init: int = 1_000_000_000,
):
    bar = MagicMock()
    bar.bar_type = bar_type
    bar.open = open_price
    bar.high = high
    bar.low = low
    bar.close = close
    bar.volume = volume
    bar.ts_event = ts_event
    bar.ts_init = ts_init
    return bar


def _mock_quote_tick(
    instrument_id: str = "AAPL.XNAS",
    bid_price: str = "150.00",
    ask_price: str = "150.05",
    bid_size: str = "100",
    ask_size: str = "200",
    ts_event: int = 1_000_000_000,
    ts_init: int = 1_000_000_000,
):
    tick = MagicMock()
    type(tick).instrument_id = PropertyMock(return_value=InstrumentId.from_str(instrument_id))
    tick.bid_price = bid_price
    tick.ask_price = ask_price
    tick.bid_size = bid_size
    tick.ask_size = ask_size
    tick.ts_event = ts_event
    tick.ts_init = ts_init
    return tick


def _mock_trade_tick(
    instrument_id: str = "AAPL.XNAS",
    price: str = "150.50",
    size: str = "50",
    aggressor_side_name: str = "BUYER",
    trade_id: str = "T-001",
    ts_event: int = 1_000_000_000,
    ts_init: int = 1_000_000_000,
):
    tick = MagicMock()
    type(tick).instrument_id = PropertyMock(return_value=InstrumentId.from_str(instrument_id))
    tick.price = price
    tick.size = size
    tick.aggressor_side = MagicMock()
    tick.aggressor_side.name = aggressor_side_name
    tick.trade_id = trade_id
    tick.ts_event = ts_event
    tick.ts_init = ts_init
    return tick


def _mock_kernel_with_data(
    bars=None,
    quote_tick=None,
    trade_ticks=None,
    has_quote_ticks: bool = False,
    has_trade_ticks: bool = False,
    subscribed_instruments=None,
    subscribed_quote_ticks=None,
    subscribed_trade_ticks=None,
    subscribed_bars=None,
):
    kernel = MagicMock()
    type(kernel).trader_id = PropertyMock(return_value="TRADER-001")
    kernel.is_running.return_value = True
    kernel.logger = MagicMock()

    cache = MagicMock()
    cache.bars.return_value = bars or []
    cache.quote_tick.return_value = quote_tick
    cache.trade_ticks.return_value = trade_ticks or []
    cache.has_quote_ticks.return_value = has_quote_ticks
    cache.has_trade_ticks.return_value = has_trade_ticks
    type(kernel).cache = PropertyMock(return_value=cache)

    data_engine = MagicMock()
    data_engine.id = "DataEngine-001"
    data_engine.state = MagicMock()
    data_engine.state.name = "RUNNING"
    data_engine.is_running = True
    data_engine.subscribed_instruments.return_value = subscribed_instruments or []
    data_engine.subscribed_quote_ticks.return_value = subscribed_quote_ticks or []
    data_engine.subscribed_trade_ticks.return_value = subscribed_trade_ticks or []
    data_engine.subscribed_bars.return_value = subscribed_bars or []
    type(kernel).data_engine = PropertyMock(return_value=data_engine)

    trader = MagicMock()
    trader.strategies.return_value = []
    trader.actors.return_value = []
    type(kernel).trader = PropertyMock(return_value=trader)

    portfolio = MagicMock()
    portfolio.balances_locked.return_value = {}
    portfolio.unrealized_pnls.return_value = {}
    portfolio.realized_pnls.return_value = {}
    portfolio.net_exposures.return_value = {}
    type(kernel).portfolio = PropertyMock(return_value=portfolio)

    risk_engine = MagicMock()
    risk_engine.state = MagicMock()
    risk_engine.state.name = "RUNNING"
    type(kernel).risk_engine = PropertyMock(return_value=risk_engine)

    return kernel


class TestDataStatus:
    @pytest.mark.asyncio
    async def test_returns_status(self) -> None:
        kernel = _mock_kernel_with_data(
            subscribed_instruments=["AAPL.XNAS"],
            subscribed_quote_ticks=["AAPL.XNAS"],
            subscribed_bars=["AAPL.XNAS-1-MINUTE-LAST-EXTERNAL"],
        )
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/data/status")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["component_id"] == "DataEngine-001"
        assert data["state"] == "RUNNING"
        assert data["is_running"] is True


class TestGetBars:
    @pytest.mark.asyncio
    async def test_bar_type_required(self) -> None:
        kernel = _mock_kernel_with_data()
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/data/bars/AAPL.XNAS")

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "BAR_TYPE_REQUIRED"

    @pytest.mark.asyncio
    async def test_returns_bars(self) -> None:
        bars = [
            _mock_bar(open_price="150.00", close="150.75"),
            _mock_bar(open_price="150.75", close="151.00"),
        ]
        kernel = _mock_kernel_with_data(bars=bars)
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get(
                "/api/v1/data/bars/AAPL.XNAS?bar_type=AAPL.XNAS-1-MINUTE-LAST-EXTERNAL",
            )

        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 2
        assert data[0]["open"] == "150.00"
        assert data[0]["close"] == "150.75"


class TestGetQuote:
    @pytest.mark.asyncio
    async def test_returns_latest_quote(self) -> None:
        tick = _mock_quote_tick(bid_price="150.00", ask_price="150.05")
        kernel = _mock_kernel_with_data(
            quote_tick=tick,
            has_quote_ticks=True,
        )
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/data/quotes/AAPL.XNAS")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["bid_price"] == "150.00"
        assert data["ask_price"] == "150.05"

    @pytest.mark.asyncio
    async def test_quotes_not_found(self) -> None:
        kernel = _mock_kernel_with_data(has_quote_ticks=False)
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/data/quotes/UNKNOWN.XNAS")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "QUOTES_NOT_FOUND"


class TestGetTrades:
    @pytest.mark.asyncio
    async def test_returns_trade_ticks(self) -> None:
        ticks = [
            _mock_trade_tick(price="150.50", size="50"),
            _mock_trade_tick(price="150.55", size="25"),
        ]
        kernel = _mock_kernel_with_data(
            trade_ticks=ticks,
            has_trade_ticks=True,
        )
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/data/trades/AAPL.XNAS")

        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 2
        assert data[0]["price"] == "150.50"
        assert data[1]["price"] == "150.55"

    @pytest.mark.asyncio
    async def test_trades_not_found(self) -> None:
        kernel = _mock_kernel_with_data(has_trade_ticks=False)
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/data/trades/UNKNOWN.XNAS")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "TRADES_NOT_FOUND"
