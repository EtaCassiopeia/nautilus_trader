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

from __future__ import annotations

from fastapi import APIRouter
from fastapi import Depends
from fastapi import Query

from nautilus_trader.api.dependencies import get_cache
from nautilus_trader.api.models.responses import error_response
from nautilus_trader.api.models.responses import ok_response
from nautilus_trader.model.identifiers import ClientOrderId
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import StrategyId


router = APIRouter(prefix="/api/v1/orders", tags=["orders"])


def _order_summary(order) -> dict:
    """Convert an Order object to a summary dict."""
    return {
        "client_order_id": str(order.client_order_id),
        "venue_order_id": str(order.venue_order_id) if order.venue_order_id is not None else None,
        "strategy_id": str(order.strategy_id),
        "instrument_id": str(order.instrument_id),
        "side": order.side.name,
        "order_type": order.order_type.name,
        "quantity": str(order.quantity),
        "price": str(order.price) if hasattr(order, "price") and order.price is not None else None,
        "time_in_force": order.time_in_force.name,
        "status": order.status.name,
        "filled_qty": str(order.filled_qty),
        "avg_px": str(order.avg_px) if order.avg_px is not None else None,
        "ts_init": order.ts_init,
        "ts_last": order.ts_last,
    }


def _filter_orders(orders, strategy_id: str | None, instrument_id: str | None, limit: int):
    """Filter and limit a list of orders."""
    result = list(orders)

    if strategy_id is not None:
        sid = StrategyId(strategy_id)
        result = [o for o in result if o.strategy_id == sid]

    if instrument_id is not None:
        iid = InstrumentId.from_str(instrument_id)
        result = [o for o in result if o.instrument_id == iid]

    return result[:limit]


@router.get("")
async def list_orders(
    status: str = Query("all", pattern="^(open|closed|all)$"),
    strategy_id: str | None = Query(None),
    instrument_id: str | None = Query(None),
    limit: int = Query(100, ge=1),
    cache=Depends(get_cache),
):
    """List orders with optional filters."""
    try:
        if status == "open":
            orders = cache.orders_open()
        elif status == "closed":
            orders = cache.orders_closed()
        else:
            orders = cache.orders()

        filtered = _filter_orders(orders, strategy_id, instrument_id, limit)
        return ok_response([_order_summary(o) for o in filtered])
    except Exception as e:
        return error_response(
            code="ORDERS_QUERY_FAILED",
            message=str(e),
            status_code=500,
        )


@router.get("/{client_order_id}")
async def get_order(client_order_id: str, cache=Depends(get_cache)):
    """Get order detail by client order ID."""
    order = cache.order(ClientOrderId(client_order_id))
    if order is None:
        return error_response(
            code="ORDER_NOT_FOUND",
            message=f"Order '{client_order_id}' not found",
            status_code=404,
        )
    return ok_response(_order_summary(order))


@router.delete("/{client_order_id}")
async def cancel_order(client_order_id: str, cache=Depends(get_cache)):
    """Cancel an order by client order ID."""
    # TODO: Orders are cancelled through strategies via the execution engine.
    # This requires locating the strategy that owns the order and calling
    # strategy.cancel_order(). Implement when strategy-level order management
    # routes are finalized.
    order = cache.order(ClientOrderId(client_order_id))
    if order is None:
        return error_response(
            code="ORDER_NOT_FOUND",
            message=f"Order '{client_order_id}' not found",
            status_code=404,
        )
    return error_response(
        code="NOT_IMPLEMENTED",
        message="Order cancellation via API is not yet implemented. "
        "Orders must be cancelled through their owning strategy.",
        status_code=501,
    )


@router.post("/cancel-all")
async def cancel_all_orders(cache=Depends(get_cache)):
    """Cancel all open orders."""
    # TODO: Requires iterating strategies and calling cancel_all_orders()
    # on each. Implement when strategy-level order management routes are finalized.
    return error_response(
        code="NOT_IMPLEMENTED",
        message="Bulk order cancellation via API is not yet implemented. "
        "Orders must be cancelled through their owning strategy.",
        status_code=501,
    )
