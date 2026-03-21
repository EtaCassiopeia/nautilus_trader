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

from datetime import datetime
from datetime import timezone
from typing import Any

from fastapi.responses import JSONResponse


def ok_response(data: Any, status_code: int = 200) -> JSONResponse:
    """Standard success response."""
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ok",
            "data": data,
            "ts": datetime.now(timezone.utc).isoformat(),
        },
    )


def error_response(
    code: str,
    message: str,
    status_code: int = 400,
    detail: Any = None,
) -> JSONResponse:
    """Standard error response."""
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "error",
            "error": {
                "code": code,
                "message": message,
                "detail": detail,
            },
            "ts": datetime.now(timezone.utc).isoformat(),
        },
    )
