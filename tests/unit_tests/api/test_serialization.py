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

from decimal import Decimal
from enum import Enum

from nautilus_trader.api.serialization import _sanitize_dict
from nautilus_trader.api.serialization import _sanitize_value
from nautilus_trader.api.serialization import serialize_event


class _MockEnum(Enum):
    BUY = 1
    SELL = 2


class _EventWithClassmethodToDict:
    ts_event = 1000000000
    ts_init = 2000000000

    @classmethod
    def to_dict(cls, obj):
        return {"field": "value", "count": 42}


class _EventWithInstanceToDict:
    ts_event = 3000000000
    ts_init = 4000000000

    def to_dict(self):
        return {"instance_field": "data"}


class _EventWithoutToDict:
    ts_event = 5000000000
    ts_init = 6000000000

    def __str__(self):
        return "PlainEvent(x=1)"


def test_serialize_event_with_classmethod_to_dict() -> None:
    event = _EventWithClassmethodToDict()
    result = serialize_event(event, topic="events.test", sequence=7)

    assert result["type"] == "_EventWithClassmethodToDict"
    assert result["topic"] == "events.test"
    assert result["ts_event"] == 1000000000
    assert result["ts_init"] == 2000000000
    assert result["sequence"] == 7
    assert result["data"] == {"field": "value", "count": 42}
    assert "ts_server" in result


def test_serialize_event_with_instance_to_dict() -> None:
    event = _EventWithInstanceToDict()
    result = serialize_event(event)

    assert result["type"] == "_EventWithInstanceToDict"
    assert result["data"] == {"instance_field": "data"}
    assert result["ts_event"] == 3000000000


def test_serialize_event_without_to_dict() -> None:
    event = _EventWithoutToDict()
    result = serialize_event(event)

    assert result["type"] == "_EventWithoutToDict"
    assert result["data"] == {"__str__": "PlainEvent(x=1)"}
    assert result["ts_event"] == 5000000000


def test_serialize_event_default_topic_and_sequence() -> None:
    event = _EventWithClassmethodToDict()
    result = serialize_event(event)

    assert result["topic"] == ""
    assert result["sequence"] == 0


def test_serialize_event_no_timestamps() -> None:
    class NoTimestamp:
        pass

    result = serialize_event(NoTimestamp())
    assert result["ts_event"] == 0
    assert result["ts_init"] == 0


def test_sanitize_dict_preserves_primitives() -> None:
    d = {"s": "hello", "i": 42, "f": 3.14, "b": True, "n": None}
    result = _sanitize_dict(d)
    assert result == d


def test_sanitize_dict_converts_bytes() -> None:
    result = _sanitize_dict({"data": b"\xde\xad"})
    assert result["data"] == "dead"


def test_sanitize_dict_converts_decimal() -> None:
    result = _sanitize_dict({"price": Decimal("67450.50")})
    assert result["price"] == "67450.50"


def test_sanitize_dict_converts_nested() -> None:
    result = _sanitize_dict({"outer": {"inner": Decimal("1.5")}})
    assert result["outer"]["inner"] == "1.5"


def test_sanitize_dict_converts_lists() -> None:
    result = _sanitize_dict({"items": [Decimal("1"), Decimal("2")]})
    assert result["items"] == ["1", "2"]


def test_sanitize_value_converts_enum() -> None:
    assert _sanitize_value(_MockEnum.BUY) == "BUY"
    assert _sanitize_value(_MockEnum.SELL) == "SELL"


def test_sanitize_value_tuple_to_list() -> None:
    result = _sanitize_value((1, "a", Decimal("3")))
    assert result == [1, "a", "3"]


def test_sanitize_value_fallback_to_str() -> None:
    class Custom:
        def __str__(self):
            return "custom-repr"

    assert _sanitize_value(Custom()) == "custom-repr"
