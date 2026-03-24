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

from nautilus_trader.api.dependencies import get_risk_engine
from nautilus_trader.api.models.responses import error_response
from nautilus_trader.api.models.responses import ok_response


router = APIRouter(prefix="/api/v1/risk", tags=["risk"])


@router.get("/status")
async def risk_status(risk_engine=Depends(get_risk_engine)):
    """Return risk engine status information."""
    try:
        return ok_response({
            "component_id": str(risk_engine.id),
            "state": risk_engine.state.name,
            "is_running": risk_engine.is_running,
            "is_bypassed": risk_engine.is_bypassed,
            "trading_state": risk_engine.trading_state.name,
            "command_count": risk_engine.command_count,
            "event_count": risk_engine.event_count,
        })
    except Exception as e:
        return error_response(
            code="RISK_STATUS_FAILED",
            message=str(e),
            status_code=500,
        )


@router.get("/config")
async def risk_config(risk_engine=Depends(get_risk_engine)):
    """Return current risk engine configuration."""
    try:
        max_notionals = risk_engine.max_notionals_per_order()
        return ok_response({
            "is_bypassed": risk_engine.is_bypassed,
            "max_order_submit_rate": str(risk_engine.max_order_submit_rate()),
            "max_order_modify_rate": str(risk_engine.max_order_modify_rate()),
            "max_notionals_per_order": {
                str(k): str(v) for k, v in max_notionals.items()
            },
            "trading_state": risk_engine.trading_state.name,
            "debug": risk_engine.debug,
        })
    except Exception as e:
        return error_response(
            code="RISK_CONFIG_FAILED",
            message=str(e),
            status_code=500,
        )
