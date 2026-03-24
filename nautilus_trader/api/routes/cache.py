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
from nautilus_trader.model.identifiers import AccountId
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import Venue


router = APIRouter(prefix="/api/v1/cache", tags=["cache"])


def _instrument_summary(instrument) -> dict:
    """Convert an Instrument object to a summary dict."""
    return {
        "instrument_id": str(instrument.id),
        "instrument_type": type(instrument).__name__,
        "venue": str(instrument.venue),
        "underlying": str(instrument.underlying) if hasattr(instrument, "underlying") and instrument.underlying else None,
        "quote_currency": str(instrument.quote_currency) if hasattr(instrument, "quote_currency") and instrument.quote_currency else None,
        "is_inverse": instrument.is_inverse if hasattr(instrument, "is_inverse") else None,
        "price_precision": instrument.price_precision,
        "size_precision": instrument.size_precision,
        "tick_size": str(instrument.tick_size) if hasattr(instrument, "tick_size") else None,
        "lot_size": str(instrument.lot_size) if hasattr(instrument, "lot_size") and instrument.lot_size else None,
        "ts_init": instrument.ts_init,
    }


def _account_summary(account) -> dict:
    """Convert an Account object to a summary dict."""
    return {
        "account_id": str(account.id),
        "account_type": type(account).__name__,
        "base_currency": str(account.base_currency) if account.base_currency else None,
        "is_cash_account": account.is_cash_account,
        "is_margin_account": account.is_margin_account,
        "event_count": account.event_count,
        "last_event": str(account.last_event) if account.last_event else None,
        "ts_init": account.ts_init if hasattr(account, "ts_init") else None,
    }


@router.get("/instruments")
async def list_instruments(
    venue: str | None = Query(None),
    cache=Depends(get_cache),
):
    """List cached instruments, optionally filtered by venue."""
    try:
        if venue is not None:
            v = Venue(venue)
            instruments = cache.instruments(venue=v)
        else:
            instruments = cache.instruments()

        return ok_response([_instrument_summary(i) for i in instruments])
    except Exception as e:
        return error_response(
            code="INSTRUMENTS_QUERY_FAILED",
            message=str(e),
            status_code=500,
        )


@router.get("/instruments/{instrument_id}")
async def get_instrument(instrument_id: str, cache=Depends(get_cache)):
    """Get instrument detail by instrument ID."""
    try:
        iid = InstrumentId.from_str(instrument_id)
        instrument = cache.instrument(iid)
        if instrument is None:
            return error_response(
                code="INSTRUMENT_NOT_FOUND",
                message=f"Instrument '{instrument_id}' not found",
                status_code=404,
            )
        return ok_response(_instrument_summary(instrument))
    except Exception as e:
        return error_response(
            code="INSTRUMENT_QUERY_FAILED",
            message=str(e),
            status_code=500,
        )


@router.get("/accounts")
async def list_accounts(cache=Depends(get_cache)):
    """List cached accounts."""
    try:
        accounts = cache.accounts()
        return ok_response([_account_summary(a) for a in accounts])
    except Exception as e:
        return error_response(
            code="ACCOUNTS_QUERY_FAILED",
            message=str(e),
            status_code=500,
        )


@router.get("/accounts/{account_id}")
async def get_account(account_id: str, cache=Depends(get_cache)):
    """Get account detail by account ID."""
    try:
        aid = AccountId(account_id)
        account = cache.account(aid)
        if account is None:
            return error_response(
                code="ACCOUNT_NOT_FOUND",
                message=f"Account '{account_id}' not found",
                status_code=404,
            )
        return ok_response(_account_summary(account))
    except Exception as e:
        return error_response(
            code="ACCOUNT_QUERY_FAILED",
            message=str(e),
            status_code=500,
        )
