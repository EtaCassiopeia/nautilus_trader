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
from decimal import Decimal
from typing import Any


def serialize_event(event: Any, topic: str = "", sequence: int = 0) -> dict:
    """
    Serialize a NautilusTrader event into a JSON-serializable envelope.

    Parameters
    ----------
    event : Any
        The event object to serialize.
    topic : str
        The MessageBus topic this event was published on.
    sequence : int
        Monotonic sequence number for client ordering.

    Returns
    -------
    dict

    """
    event_type = type(event).__name__

    # Try to_dict() — most domain objects implement this as a classmethod
    if hasattr(event, "to_dict"):
        try:
            data = _sanitize_dict(event.to_dict(event))
        except TypeError:
            try:
                data = _sanitize_dict(event.to_dict())
            except Exception:
                data = {"__str__": str(event)}
    else:
        data = {"__str__": str(event)}

    ts_event = getattr(event, "ts_event", 0)
    ts_init = getattr(event, "ts_init", 0)

    return {
        "type": event_type,
        "topic": topic,
        "ts_event": ts_event,
        "ts_init": ts_init,
        "ts_server": datetime.now(timezone.utc).isoformat(),
        "sequence": sequence,
        "data": data,
    }


def _sanitize_dict(d: dict) -> dict:
    """Ensure all values in a dict are JSON-serializable."""
    return {key: _sanitize_value(value) for key, value in d.items()}


def _sanitize_value(value: Any) -> Any:
    """Convert a single value to a JSON-serializable form."""
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return _sanitize_dict(value)
    if isinstance(value, (list, tuple)):
        return [_sanitize_value(v) for v in value]
    # Enum-like objects (have .name and .value)
    if hasattr(value, "name") and hasattr(value, "value"):
        return value.name
    return str(value)
