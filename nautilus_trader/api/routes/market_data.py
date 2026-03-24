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
from nautilus_trader.api.dependencies import get_data_engine
from nautilus_trader.api.models.responses import error_response
from nautilus_trader.api.models.responses import ok_response
from nautilus_trader.model.data import BarType
from nautilus_trader.model.identifiers import InstrumentId


router = APIRouter(prefix="/api/v1/data", tags=["data"])


def _bar_summary(bar) -> dict:
    """Convert a Bar object to a summary dict."""
    return {
        "bar_type": str(bar.bar_type),
        "open": str(bar.open),
        "high": str(bar.high),
        "low": str(bar.low),
        "close": str(bar.close),
        "volume": str(bar.volume),
        "ts_event": bar.ts_event,
        "ts_init": bar.ts_init,
    }


def _quote_tick_summary(tick) -> dict:
    """Convert a QuoteTick object to a summary dict."""
    return {
        "instrument_id": str(tick.instrument_id),
        "bid_price": str(tick.bid_price),
        "ask_price": str(tick.ask_price),
        "bid_size": str(tick.bid_size),
        "ask_size": str(tick.ask_size),
        "ts_event": tick.ts_event,
        "ts_init": tick.ts_init,
    }


def _trade_tick_summary(tick) -> dict:
    """Convert a TradeTick object to a summary dict."""
    return {
        "instrument_id": str(tick.instrument_id),
        "price": str(tick.price),
        "size": str(tick.size),
        "aggressor_side": tick.aggressor_side.name,
        "trade_id": str(tick.trade_id),
        "ts_event": tick.ts_event,
        "ts_init": tick.ts_init,
    }


@router.get("/status")
async def data_status(data_engine=Depends(get_data_engine)):
    """Return data engine status information."""
    try:
        return ok_response({
            "component_id": str(data_engine.id),
            "state": data_engine.state.name,
            "is_running": data_engine.is_running,
            "subscribed_instruments": [str(i) for i in data_engine.subscribed_instruments()],
            "subscribed_quote_ticks": [str(i) for i in data_engine.subscribed_quote_ticks()],
            "subscribed_trade_ticks": [str(i) for i in data_engine.subscribed_trade_ticks()],
            "subscribed_bars": [str(b) for b in data_engine.subscribed_bars()],
        })
    except Exception as e:
        return error_response(
            code="DATA_STATUS_FAILED",
            message=str(e),
            status_code=500,
        )


@router.get("/bars/{instrument_id}")
async def get_bars(
    instrument_id: str,
    bar_type: str | None = Query(None),
    limit: int = Query(100, ge=1),
    cache=Depends(get_cache),
):
    """Get recent bars from cache for an instrument."""
    try:
        if bar_type is not None:
            bt = BarType.from_str(bar_type)
            bars = cache.bars(bt)
            bars = bars[:limit]
            return ok_response([_bar_summary(b) for b in bars])
        else:
            return error_response(
                code="BAR_TYPE_REQUIRED",
                message="Query parameter 'bar_type' is required "
                "(e.g. 'AAPL.XNAS-1-MINUTE-LAST-EXTERNAL')",
                status_code=400,
            )
    except Exception as e:
        return error_response(
            code="BARS_QUERY_FAILED",
            message=str(e),
            status_code=500,
        )


@router.get("/quotes/{instrument_id}")
async def get_quote(instrument_id: str, cache=Depends(get_cache)):
    """Get latest quote tick from cache for an instrument."""
    try:
        iid = InstrumentId.from_str(instrument_id)
        if not cache.has_quote_ticks(iid):
            return error_response(
                code="QUOTES_NOT_FOUND",
                message=f"No quote ticks found for '{instrument_id}'",
                status_code=404,
            )
        tick = cache.quote_tick(iid)
        return ok_response(_quote_tick_summary(tick))
    except Exception as e:
        return error_response(
            code="QUOTES_QUERY_FAILED",
            message=str(e),
            status_code=500,
        )


@router.get("/trades/{instrument_id}")
async def get_trades(
    instrument_id: str,
    limit: int = Query(100, ge=1),
    cache=Depends(get_cache),
):
    """Get recent trade ticks from cache for an instrument."""
    try:
        iid = InstrumentId.from_str(instrument_id)
        if not cache.has_trade_ticks(iid):
            return error_response(
                code="TRADES_NOT_FOUND",
                message=f"No trade ticks found for '{instrument_id}'",
                status_code=404,
            )
        ticks = cache.trade_ticks(iid)
        ticks = ticks[:limit]
        return ok_response([_trade_tick_summary(t) for t in ticks])
    except Exception as e:
        return error_response(
            code="TRADES_QUERY_FAILED",
            message=str(e),
            status_code=500,
        )
