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
from nautilus_trader.api.dependencies import get_portfolio
from nautilus_trader.api.models.responses import error_response
from nautilus_trader.api.models.responses import ok_response
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import Venue


router = APIRouter(prefix="/api/v1/portfolio", tags=["portfolio"])


def _money_dict(money_map: dict) -> dict:
    """Convert a dict of Currency -> Money/Decimal values to serializable dict."""
    return {str(k): str(v) for k, v in money_map.items()}


def _position_summary(position) -> dict:
    """Convert a Position object to a summary dict."""
    return {
        "instrument_id": str(position.instrument_id),
        "strategy_id": str(position.strategy_id),
        "side": position.side.name,
        "quantity": str(position.quantity),
        "avg_px_open": str(position.avg_px_open),
        "unrealized_pnl": str(position.unrealized_pnl) if position.unrealized_pnl is not None else None,
        "realized_pnl": str(position.realized_pnl),
        "ts_opened": position.ts_opened,
        "ts_last": position.ts_last,
    }


@router.get("")
async def portfolio_summary(portfolio=Depends(get_portfolio)):
    """Full portfolio summary."""
    try:
        return ok_response({
            "balances_locked": _money_dict(portfolio.balances_locked()),
            "unrealized_pnls": _money_dict(portfolio.unrealized_pnls()),
            "realized_pnls": _money_dict(portfolio.realized_pnls()),
            "net_exposures": _money_dict(portfolio.net_exposures()),
        })
    except Exception as e:
        return error_response(
            code="PORTFOLIO_QUERY_FAILED",
            message=str(e),
            status_code=500,
        )


@router.get("/balances")
async def portfolio_balances(
    venue: str | None = Query(None),
    portfolio=Depends(get_portfolio),
):
    """Account balances, optionally filtered by venue."""
    try:
        if venue is not None:
            v = Venue(venue)
            balances = portfolio.balances_locked(v)
        else:
            balances = portfolio.balances_locked()
        return ok_response(_money_dict(balances))
    except Exception as e:
        return error_response(
            code="BALANCES_QUERY_FAILED",
            message=str(e),
            status_code=500,
        )


@router.get("/positions")
async def portfolio_positions(
    instrument_id: str | None = Query(None),
    cache=Depends(get_cache),
):
    """Open positions, optionally filtered by instrument."""
    try:
        positions = cache.positions_open()

        if instrument_id is not None:
            iid = InstrumentId.from_str(instrument_id)
            positions = [p for p in positions if p.instrument_id == iid]

        return ok_response([_position_summary(p) for p in positions])
    except Exception as e:
        return error_response(
            code="POSITIONS_QUERY_FAILED",
            message=str(e),
            status_code=500,
        )


@router.get("/pnl")
async def portfolio_pnl(portfolio=Depends(get_portfolio)):
    """P&L summary."""
    try:
        return ok_response({
            "unrealized_pnls": _money_dict(portfolio.unrealized_pnls()),
            "realized_pnls": _money_dict(portfolio.realized_pnls()),
        })
    except Exception as e:
        return error_response(
            code="PNL_QUERY_FAILED",
            message=str(e),
            status_code=500,
        )


@router.get("/exposure")
async def portfolio_exposure(portfolio=Depends(get_portfolio)):
    """Net exposures."""
    try:
        return ok_response({
            "net_exposures": _money_dict(portfolio.net_exposures()),
        })
    except Exception as e:
        return error_response(
            code="EXPOSURE_QUERY_FAILED",
            message=str(e),
            status_code=500,
        )
