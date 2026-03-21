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

from nautilus_trader.api.dependencies import get_trader
from nautilus_trader.api.models.requests import CreateStrategyRequest
from nautilus_trader.api.models.responses import error_response
from nautilus_trader.api.models.responses import ok_response
from nautilus_trader.model.identifiers import StrategyId
from nautilus_trader.trading.config import ImportableStrategyConfig


router = APIRouter(prefix="/api/v1/strategies", tags=["strategies"])


def _strategy_summary(strategy) -> dict:
    """Convert a Strategy object to a summary dict."""
    return {
        "strategy_id": str(strategy.id),
        "strategy_type": type(strategy).__name__,
        "state": strategy.state.name,
        "order_id_tag": strategy.order_id_tag,
    }


@router.get("")
async def list_strategies(trader=Depends(get_trader)):
    """List all registered strategies."""
    strategies = trader.strategies()
    return ok_response([_strategy_summary(s) for s in strategies])


@router.post("")
async def create_strategy(request: CreateStrategyRequest, trader=Depends(get_trader)):
    """Create a new strategy from an importable config."""
    try:
        config = ImportableStrategyConfig(
            strategy_path=request.strategy_path,
            config_path=request.config_path,
            config=request.config,
        )

        from nautilus_trader.trading.controller import Controller

        # Find the controller registered with the trader
        controller = None
        for actor in trader.actors():
            if isinstance(actor, Controller):
                controller = actor
                break

        if controller is None:
            return error_response(
                code="NO_CONTROLLER",
                message="No Controller is registered with the trader. "
                "A Controller is required for runtime strategy management.",
                status_code=500,
            )

        controller.create_strategy_from_config(config, start=request.start)

        return ok_response(
            {"message": f"Strategy created (start={request.start})"},
            status_code=201,
        )
    except Exception as e:
        return error_response(
            code="STRATEGY_CREATE_FAILED",
            message=str(e),
            status_code=400,
        )


@router.get("/{strategy_id}")
async def get_strategy(strategy_id: str, trader=Depends(get_trader)):
    """Get detailed strategy state."""
    sid = StrategyId(strategy_id)
    for strategy in trader.strategies():
        if strategy.id == sid:
            return ok_response(_strategy_summary(strategy))

    return error_response(
        code="STRATEGY_NOT_FOUND",
        message=f"Strategy '{strategy_id}' not found",
        status_code=404,
    )


@router.post("/{strategy_id}/start")
async def start_strategy(strategy_id: str, trader=Depends(get_trader)):
    """Start a stopped strategy."""
    sid = StrategyId(strategy_id)
    try:
        trader.start_strategy(sid)
        return ok_response({"strategy_id": strategy_id, "action": "started"})
    except Exception as e:
        return error_response(
            code="STRATEGY_START_FAILED",
            message=str(e),
            status_code=400,
        )


@router.post("/{strategy_id}/stop")
async def stop_strategy(strategy_id: str, trader=Depends(get_trader)):
    """Stop a running strategy."""
    sid = StrategyId(strategy_id)
    try:
        trader.stop_strategy(sid)
        return ok_response({"strategy_id": strategy_id, "action": "stopped"})
    except Exception as e:
        return error_response(
            code="STRATEGY_STOP_FAILED",
            message=str(e),
            status_code=400,
        )


@router.post("/{strategy_id}/market-exit")
async def market_exit_strategy(strategy_id: str, trader=Depends(get_trader)):
    """Market-exit all positions for a strategy."""
    sid = StrategyId(strategy_id)
    try:
        trader.market_exit_strategy(sid)
        return ok_response({"strategy_id": strategy_id, "action": "market_exit"})
    except Exception as e:
        return error_response(
            code="STRATEGY_MARKET_EXIT_FAILED",
            message=str(e),
            status_code=400,
        )


@router.delete("/{strategy_id}")
async def remove_strategy(strategy_id: str, trader=Depends(get_trader)):
    """Remove a strategy (stops it first if running)."""
    sid = StrategyId(strategy_id)
    try:
        trader.remove_strategy(sid)
        return ok_response({"strategy_id": strategy_id, "action": "removed"})
    except Exception as e:
        return error_response(
            code="STRATEGY_REMOVE_FAILED",
            message=str(e),
            status_code=400,
        )
