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

from nautilus_trader.api.dependencies import get_kernel
from nautilus_trader.api.dependencies import get_trader
from nautilus_trader.api.models.responses import ok_response


router = APIRouter(prefix="/api/v1/node", tags=["node"])


@router.get("/status")
async def get_status(kernel=Depends(get_kernel), trader=Depends(get_trader)):
    """Return current node state and health information."""
    return ok_response({
        "trader_id": str(kernel.trader_id),
        "instance_id": str(kernel.instance_id),
        "machine_id": kernel.machine_id,
        "environment": kernel.environment.name,
        "is_running": kernel.is_running(),
        "strategies_count": len(trader.strategy_ids()),
        "actors_count": len(trader.actor_ids()),
    })


@router.post("/stop")
async def stop_node(kernel=Depends(get_kernel)):
    """Initiate graceful shutdown of the trading node."""
    kernel.loop.call_soon(kernel.stop)
    return ok_response({"message": "Shutdown initiated"})
