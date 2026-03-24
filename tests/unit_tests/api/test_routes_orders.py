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
from nautilus_trader.model.identifiers import ClientOrderId
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import StrategyId


def _mock_order(
    client_order_id: str = "O-20240101-001",
    venue_order_id: str | None = "V-001",
    strategy_id: str = "EMACross-001",
    instrument_id: str = "AAPL.XNAS",
    side_name: str = "BUY",
    order_type_name: str = "LIMIT",
    quantity: str = "100",
    price: str = "150.50",
    time_in_force_name: str = "GTC",
    status_name: str = "ACCEPTED",
    filled_qty: str = "0",
    avg_px=None,
    ts_init: int = 1_000_000_000,
    ts_last: int = 1_000_000_000,
):
    order = MagicMock()
    type(order).client_order_id = PropertyMock(return_value=ClientOrderId(client_order_id))
    order.venue_order_id = venue_order_id
    type(order).strategy_id = PropertyMock(return_value=StrategyId(strategy_id))
    type(order).instrument_id = PropertyMock(return_value=InstrumentId.from_str(instrument_id))
    order.side = MagicMock()
    order.side.name = side_name
    order.order_type = MagicMock()
    order.order_type.name = order_type_name
    order.quantity = quantity
    order.price = price
    order.time_in_force = MagicMock()
    order.time_in_force.name = time_in_force_name
    order.status = MagicMock()
    order.status.name = status_name
    order.filled_qty = filled_qty
    order.avg_px = avg_px
    order.ts_init = ts_init
    order.ts_last = ts_last
    return order


def _mock_kernel_with_orders(orders=None):
    kernel = MagicMock()
    type(kernel).trader_id = PropertyMock(return_value="TRADER-001")
    kernel.is_running.return_value = True
    kernel.logger = MagicMock()

    cache = MagicMock()
    cache.orders.return_value = orders or []
    cache.orders_open.return_value = [o for o in (orders or []) if o.status.name != "FILLED"]
    cache.orders_closed.return_value = [o for o in (orders or []) if o.status.name == "FILLED"]
    cache.order.return_value = None
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

    return kernel


class TestListOrders:
    @pytest.mark.asyncio
    async def test_empty_list(self) -> None:
        kernel = _mock_kernel_with_orders([])
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/orders")

        assert response.status_code == 200
        assert response.json()["data"] == []

    @pytest.mark.asyncio
    async def test_returns_order_summaries(self) -> None:
        orders = [
            _mock_order(client_order_id="O-001", status_name="ACCEPTED"),
            _mock_order(client_order_id="O-002", status_name="FILLED", filled_qty="100", avg_px="151.00"),
        ]
        kernel = _mock_kernel_with_orders(orders)
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/orders")

        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 2
        assert data[0]["client_order_id"] == "O-001"
        assert data[0]["status"] == "ACCEPTED"
        assert data[1]["client_order_id"] == "O-002"
        assert data[1]["status"] == "FILLED"
        assert data[1]["filled_qty"] == "100"

    @pytest.mark.asyncio
    async def test_filter_by_status_open(self) -> None:
        orders = [
            _mock_order(client_order_id="O-001", status_name="ACCEPTED"),
            _mock_order(client_order_id="O-002", status_name="FILLED"),
        ]
        kernel = _mock_kernel_with_orders(orders)
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/orders?status=open")

        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 1
        assert data[0]["client_order_id"] == "O-001"


class TestGetOrder:
    @pytest.mark.asyncio
    async def test_order_found(self) -> None:
        order = _mock_order(client_order_id="O-001")
        kernel = _mock_kernel_with_orders([])
        kernel.cache.order.return_value = order
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/orders/O-001")

        assert response.status_code == 200
        assert response.json()["data"]["client_order_id"] == "O-001"
        assert response.json()["data"]["side"] == "BUY"

    @pytest.mark.asyncio
    async def test_order_not_found(self) -> None:
        kernel = _mock_kernel_with_orders([])
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/orders/O-NONEXIST")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "ORDER_NOT_FOUND"


class TestCancelOrder:
    @pytest.mark.asyncio
    async def test_cancel_not_implemented(self) -> None:
        order = _mock_order(client_order_id="O-001")
        kernel = _mock_kernel_with_orders([])
        kernel.cache.order.return_value = order
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.delete("/api/v1/orders/O-001")

        assert response.status_code == 501
        assert response.json()["error"]["code"] == "NOT_IMPLEMENTED"


class TestCancelAllOrders:
    @pytest.mark.asyncio
    async def test_cancel_all_not_implemented(self) -> None:
        kernel = _mock_kernel_with_orders([])
        app = create_app(kernel, ApiServerConfig())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post("/api/v1/orders/cancel-all")

        assert response.status_code == 501
        assert response.json()["error"]["code"] == "NOT_IMPLEMENTED"
