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
from nautilus_trader.model.identifiers import AccountId
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import Venue


def _mock_instrument(
    instrument_id: str = "AAPL.XNAS",
    instrument_type: str = "Equity",
    venue: str = "XNAS",
    price_precision: int = 2,
    size_precision: int = 0,
    ts_init: int = 1_000_000_000,
):
    instrument = MagicMock()
    type(instrument).id = PropertyMock(return_value=InstrumentId.from_str(instrument_id))
    type(instrument).venue = PropertyMock(return_value=Venue(venue))
    type(instrument).__name__ = instrument_type
    instrument.underlying = None
    instrument.quote_currency = "USD"
    instrument.is_inverse = False
    instrument.price_precision = price_precision
    instrument.size_precision = size_precision
    instrument.tick_size = "0.01"
    instrument.lot_size = "1"
    instrument.ts_init = ts_init
    return instrument


def _mock_account(
    account_id: str = "SIM-001",
    account_type: str = "CashAccount",
    base_currency: str = "USD",
    is_cash: bool = True,
    is_margin: bool = False,
    event_count: int = 1,
):
    account = MagicMock()
    type(account).id = PropertyMock(return_value=AccountId(account_id))
    type(account).__name__ = account_type
    account.base_currency = base_currency
    account.is_cash_account = is_cash
    account.is_margin_account = is_margin
    account.event_count = event_count
    account.last_event = None
    account.ts_init = 1_000_000_000
    return account


def _mock_kernel_with_cache(instruments=None, accounts=None):
    kernel = MagicMock()
    type(kernel).trader_id = PropertyMock(return_value="TRADER-001")
    kernel.is_running.return_value = True
    kernel.logger = MagicMock()

    cache = MagicMock()
    cache.instruments.return_value = instruments or []
    cache.instrument.return_value = None
    cache.accounts.return_value = accounts or []
    cache.account.return_value = None
    type(kernel).cache = PropertyMock(return_value=cache)

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

    data_engine = MagicMock()
    data_engine.state = MagicMock()
    data_engine.state.name = "RUNNING"
    type(kernel).data_engine = PropertyMock(return_value=data_engine)

    risk_engine = MagicMock()
    risk_engine.state = MagicMock()
    risk_engine.state.name = "RUNNING"
    type(kernel).risk_engine = PropertyMock(return_value=risk_engine)

    return kernel


class TestListInstruments:
    @pytest.mark.asyncio
    async def test_empty_list(self) -> None:
        kernel = _mock_kernel_with_cache()
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/cache/instruments")

        assert response.status_code == 200
        assert response.json()["data"] == []

    @pytest.mark.asyncio
    async def test_returns_instrument_summaries(self) -> None:
        instruments = [
            _mock_instrument(instrument_id="AAPL.XNAS", venue="XNAS"),
            _mock_instrument(instrument_id="MSFT.XNAS", venue="XNAS"),
        ]
        kernel = _mock_kernel_with_cache(instruments=instruments)
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/cache/instruments")

        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 2
        assert data[0]["instrument_id"] == "AAPL.XNAS"
        assert data[1]["instrument_id"] == "MSFT.XNAS"

    @pytest.mark.asyncio
    async def test_filter_by_venue(self) -> None:
        instruments = [
            _mock_instrument(instrument_id="AAPL.XNAS", venue="XNAS"),
        ]
        kernel = _mock_kernel_with_cache(instruments=instruments)
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/cache/instruments?venue=XNAS")

        assert response.status_code == 200
        kernel.cache.instruments.assert_called_once()


class TestGetInstrument:
    @pytest.mark.asyncio
    async def test_instrument_found(self) -> None:
        instrument = _mock_instrument(instrument_id="AAPL.XNAS")
        kernel = _mock_kernel_with_cache()
        kernel.cache.instrument.return_value = instrument
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/cache/instruments/AAPL.XNAS")

        assert response.status_code == 200
        assert response.json()["data"]["instrument_id"] == "AAPL.XNAS"

    @pytest.mark.asyncio
    async def test_instrument_not_found(self) -> None:
        kernel = _mock_kernel_with_cache()
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/cache/instruments/UNKNOWN.XNAS")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "INSTRUMENT_NOT_FOUND"


class TestListAccounts:
    @pytest.mark.asyncio
    async def test_empty_list(self) -> None:
        kernel = _mock_kernel_with_cache()
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/cache/accounts")

        assert response.status_code == 200
        assert response.json()["data"] == []

    @pytest.mark.asyncio
    async def test_returns_account_summaries(self) -> None:
        accounts = [
            _mock_account(account_id="SIM-001"),
            _mock_account(account_id="SIM-002"),
        ]
        kernel = _mock_kernel_with_cache(accounts=accounts)
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/cache/accounts")

        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 2
        assert data[0]["account_id"] == "SIM-001"
        assert data[1]["account_id"] == "SIM-002"


class TestGetAccount:
    @pytest.mark.asyncio
    async def test_account_found(self) -> None:
        account = _mock_account(account_id="SIM-001")
        kernel = _mock_kernel_with_cache()
        kernel.cache.account.return_value = account
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/cache/accounts/SIM-001")

        assert response.status_code == 200
        assert response.json()["data"]["account_id"] == "SIM-001"
        assert response.json()["data"]["base_currency"] == "USD"

    @pytest.mark.asyncio
    async def test_account_not_found(self) -> None:
        kernel = _mock_kernel_with_cache()
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/cache/accounts/UNKNOWN-001")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "ACCOUNT_NOT_FOUND"
