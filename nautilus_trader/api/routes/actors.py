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
from nautilus_trader.api.models.responses import error_response
from nautilus_trader.api.models.responses import ok_response
from nautilus_trader.model.identifiers import ComponentId


router = APIRouter(prefix="/api/v1/actors", tags=["actors"])


def _actor_summary(actor) -> dict:
    """Convert an Actor object to a summary dict."""
    return {
        "actor_id": str(actor.id),
        "actor_type": type(actor).__name__,
        "state": actor.state.name,
    }


@router.get("")
async def list_actors(trader=Depends(get_trader)):
    """List all registered actors."""
    actors = trader.actors()
    return ok_response([_actor_summary(a) for a in actors])


@router.get("/{actor_id}")
async def get_actor(actor_id: str, trader=Depends(get_trader)):
    """Get actor detail by ID."""
    aid = ComponentId(actor_id)
    for actor in trader.actors():
        if actor.id == aid:
            return ok_response(_actor_summary(actor))

    return error_response(
        code="ACTOR_NOT_FOUND",
        message=f"Actor '{actor_id}' not found",
        status_code=404,
    )
