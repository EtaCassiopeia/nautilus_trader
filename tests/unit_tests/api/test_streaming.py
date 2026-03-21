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

import asyncio
from unittest.mock import MagicMock

import pytest

from nautilus_trader.api.config import EventStreamConfig
from nautilus_trader.api.streaming import ClientConnection
from nautilus_trader.api.streaming import EventStreamBridge
from nautilus_trader.api.streaming import RingBuffer
from nautilus_trader.api.streaming import _topic_matches


class TestRingBuffer:
    def test_empty_buffer(self) -> None:
        buf = RingBuffer(maxlen=10)

        assert len(buf) == 0
        assert buf.sequence == 0
        assert buf.replay_from(-1) == []

    def test_append_increments_sequence(self) -> None:
        buf = RingBuffer(maxlen=10)

        seq0 = buf.append({"type": "test1"})
        seq1 = buf.append({"type": "test2"})

        assert seq0 == 0
        assert seq1 == 1
        assert buf.sequence == 2
        assert len(buf) == 2

    def test_overflow_discards_oldest(self) -> None:
        buf = RingBuffer(maxlen=3)

        buf.append({"type": "e0"})
        buf.append({"type": "e1"})
        buf.append({"type": "e2"})
        buf.append({"type": "e3"})  # Pushes out e0

        assert len(buf) == 3
        assert buf.sequence == 4
        events = buf.replay_from(-1)
        assert len(events) == 3
        assert events[0]["type"] == "e1"
        assert events[2]["type"] == "e3"

    def test_replay_from_sequence(self) -> None:
        buf = RingBuffer(maxlen=10)

        buf.append({"type": "e0"})
        buf.append({"type": "e1"})
        buf.append({"type": "e2"})

        events = buf.replay_from(0)
        assert len(events) == 2
        assert events[0]["sequence"] == 1
        assert events[1]["sequence"] == 2

    def test_replay_from_latest_returns_empty(self) -> None:
        buf = RingBuffer(maxlen=10)

        buf.append({"type": "e0"})
        buf.append({"type": "e1"})

        events = buf.replay_from(1)
        assert len(events) == 0

    def test_disabled_buffer_zero_maxlen(self) -> None:
        buf = RingBuffer(maxlen=0)

        seq = buf.append({"type": "test"})
        assert seq == 0
        assert buf.sequence == 1
        assert len(buf) == 0
        assert buf.replay_from(-1) == []


class TestTopicMatches:
    def test_exact_match(self) -> None:
        assert _topic_matches("events.order", "events.order") is True

    def test_no_match(self) -> None:
        assert _topic_matches("events.order", "events.trade") is False

    def test_wildcard_star(self) -> None:
        assert _topic_matches("events.*", "events.order") is True
        assert _topic_matches("events.*", "events.trade.fill") is True

    def test_wildcard_star_all(self) -> None:
        assert _topic_matches("*", "anything.goes.here") is True

    def test_wildcard_question(self) -> None:
        assert _topic_matches("events.?rder", "events.order") is True
        assert _topic_matches("events.?rder", "events.xrder") is True
        assert _topic_matches("events.?rder", "events.orders") is False

    def test_prefix_star(self) -> None:
        assert _topic_matches("data.*", "data.quotes.AAPL") is True
        assert _topic_matches("data.*", "events.order") is False

    def test_empty_strings(self) -> None:
        assert _topic_matches("", "") is True
        assert _topic_matches("*", "") is True
        assert _topic_matches("", "nonempty") is False


class TestClientConnection:
    def test_matches_all_topics_when_none(self) -> None:
        conn = ClientConnection("c1", queue_size=10, topics=None)

        assert conn.matches_topic("events.order") is True
        assert conn.matches_topic("data.quotes") is True

    def test_matches_specific_topics(self) -> None:
        conn = ClientConnection("c1", queue_size=10, topics=["events.*"])

        assert conn.matches_topic("events.order") is True
        assert conn.matches_topic("data.quotes") is False

    def test_matches_multiple_patterns(self) -> None:
        conn = ClientConnection("c1", queue_size=10, topics=["events.*", "data.quotes.*"])

        assert conn.matches_topic("events.order") is True
        assert conn.matches_topic("data.quotes.AAPL") is True
        assert conn.matches_topic("data.trades.AAPL") is False

    def test_enqueue_success(self) -> None:
        conn = ClientConnection("c1", queue_size=10)

        assert conn.try_enqueue({"type": "test"}) is True
        assert conn.queue.qsize() == 1
        assert conn.dropped_count == 0

    def test_enqueue_full_drops(self) -> None:
        conn = ClientConnection("c1", queue_size=2)

        assert conn.try_enqueue({"type": "e1"}) is True
        assert conn.try_enqueue({"type": "e2"}) is True
        assert conn.try_enqueue({"type": "e3"}) is False
        assert conn.dropped_count == 1

    @pytest.mark.asyncio
    async def test_close_sends_sentinel(self) -> None:
        conn = ClientConnection("c1", queue_size=10)

        await conn.close()

        item = conn.queue.get_nowait()
        assert item is None


class TestEventStreamBridge:
    def _make_bridge(self, **kwargs) -> EventStreamBridge:
        config = EventStreamConfig(**kwargs)
        logger = MagicMock()
        return EventStreamBridge(config, logger)

    def test_add_client(self) -> None:
        bridge = self._make_bridge()

        conn = bridge.add_client("c1")

        assert conn is not None
        assert bridge.client_count == 1

    def test_add_client_max_reached(self) -> None:
        bridge = self._make_bridge(max_clients=1)

        conn1 = bridge.add_client("c1")
        conn2 = bridge.add_client("c2")

        assert conn1 is not None
        assert conn2 is None
        assert bridge.client_count == 1

    def test_add_client_replaces_existing(self) -> None:
        bridge = self._make_bridge()

        conn1 = bridge.add_client("c1", topics=["events.*"])
        conn2 = bridge.add_client("c1", topics=["data.*"])

        assert conn2 is not None
        assert bridge.client_count == 1
        assert conn2.topics == ["data.*"]

    def test_remove_client(self) -> None:
        bridge = self._make_bridge()
        bridge.add_client("c1")

        bridge.remove_client("c1")

        assert bridge.client_count == 0

    def test_remove_nonexistent_client(self) -> None:
        bridge = self._make_bridge()

        bridge.remove_client("nonexistent")  # Should not raise

        assert bridge.client_count == 0

    def test_on_event_fans_out(self) -> None:
        bridge = self._make_bridge()
        bridge.add_client("c1")
        bridge.add_client("c2")

        event = MagicMock()
        event._topic = "events.order"
        event.ts_event = 1000
        event.ts_init = 2000
        type(event).__name__ = "OrderFilled"
        event.to_dict = MagicMock(side_effect=TypeError)

        bridge.on_event(event)

        c1 = bridge._clients["c1"]
        c2 = bridge._clients["c2"]
        assert c1.queue.qsize() == 1
        assert c2.queue.qsize() == 1

    def test_on_event_filters_by_topic(self) -> None:
        bridge = self._make_bridge()
        bridge.add_client("c1", topics=["events.*"])
        bridge.add_client("c2", topics=["data.*"])

        event = MagicMock()
        event._topic = "events.order"
        event.ts_event = 1000
        event.ts_init = 2000

        bridge.on_event(event)

        c1 = bridge._clients["c1"]
        c2 = bridge._clients["c2"]
        assert c1.queue.qsize() == 1
        assert c2.queue.qsize() == 0

    def test_on_event_appends_to_ring_buffer(self) -> None:
        bridge = self._make_bridge(replay_buffer_size=100)

        event = MagicMock()
        event._topic = "events.order"
        event.ts_event = 1000
        event.ts_init = 2000

        bridge.on_event(event)

        assert len(bridge.ring_buffer) == 1
        assert bridge.ring_buffer.sequence == 1

    def test_replay_for_client(self) -> None:
        bridge = self._make_bridge(replay_buffer_size=100)
        bridge.add_client("c1")

        # Publish 3 events
        for i in range(3):
            event = MagicMock()
            event._topic = "events.order"
            event.ts_event = i * 1000
            event.ts_init = i * 1000
            bridge.on_event(event)

        # Client requests replay from sequence 1
        replayed = bridge.replay_for_client("c1", last_sequence=0)
        assert len(replayed) == 2

    def test_replay_for_nonexistent_client(self) -> None:
        bridge = self._make_bridge()

        result = bridge.replay_for_client("nonexistent", last_sequence=0)
        assert result == []

    @pytest.mark.asyncio
    async def test_close_all(self) -> None:
        bridge = self._make_bridge()
        bridge.add_client("c1")
        bridge.add_client("c2")

        await bridge.close_all()

        assert bridge.client_count == 0
