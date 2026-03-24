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

import asyncio
import json
from collections import deque
from typing import Any

from nautilus_trader.api.config import EventStreamConfig
from nautilus_trader.api.serialization import serialize_event
from nautilus_trader.common.component import Logger


class RingBuffer:
    """
    A fixed-size ring buffer for storing recent serialized events.

    When the buffer is full, the oldest event is discarded to make room.

    Parameters
    ----------
    maxlen : int
        Maximum number of events to store. If 0, the buffer is disabled.

    """

    def __init__(self, maxlen: int) -> None:
        self._maxlen = maxlen
        self._buffer: deque[dict] = deque(maxlen=maxlen) if maxlen > 0 else deque(maxlen=0)
        self._sequence: int = 0

    @property
    def sequence(self) -> int:
        """Return the current sequence number (total events received)."""
        return self._sequence

    def append(self, event: dict) -> int:
        """
        Append an event to the buffer and return its sequence number.

        Parameters
        ----------
        event : dict
            The serialized event dict.

        Returns
        -------
        int

        """
        seq = self._sequence
        self._sequence += 1
        if self._maxlen > 0:
            event["sequence"] = seq
            self._buffer.append(event)
        return seq

    def replay_from(self, last_sequence: int) -> list[dict]:
        """
        Return all buffered events with sequence > last_sequence.

        Parameters
        ----------
        last_sequence : int
            The last sequence number the client received.

        Returns
        -------
        list[dict]

        """
        if self._maxlen == 0:
            return []
        return [e for e in self._buffer if e.get("sequence", -1) > last_sequence]

    def __len__(self) -> int:
        return len(self._buffer)


class ClientConnection:
    """
    Represents a single WebSocket client connection with its own event queue.

    Parameters
    ----------
    client_id : str
        Unique identifier for the client.
    queue_size : int
        Maximum number of events to buffer for this client.
    topics : list[str] | None
        Topic patterns the client is subscribed to. None means all topics.

    """

    def __init__(
        self,
        client_id: str,
        queue_size: int,
        topics: list[str] | None = None,
    ) -> None:
        self.client_id = client_id
        self.topics = topics
        self.queue: asyncio.Queue[dict | None] = asyncio.Queue(maxsize=queue_size)
        self.dropped_count: int = 0

    def matches_topic(self, topic: str) -> bool:
        """Return whether this client should receive events for the given topic."""
        if self.topics is None:
            return True
        return any(_topic_matches(pattern, topic) for pattern in self.topics)

    def try_enqueue(self, event: dict) -> bool:
        """
        Try to enqueue an event. Returns False if the queue is full (event dropped).

        Parameters
        ----------
        event : dict
            The serialized event.

        Returns
        -------
        bool

        """
        try:
            self.queue.put_nowait(event)
            return True
        except asyncio.QueueFull:
            self.dropped_count += 1
            return False

    async def close(self) -> None:
        """Signal the client to disconnect by sending a sentinel."""
        try:
            self.queue.put_nowait(None)
        except asyncio.QueueFull:
            pass


def _topic_matches(pattern: str, topic: str) -> bool:
    """
    Match a topic against a pattern with wildcard support.

    Supports `*` (any characters) and `?` (single character).

    """
    if pattern == "*":
        return True

    pi = ti = 0
    plen = len(pattern)
    tlen = len(topic)
    star_pi = star_ti = -1

    while ti < tlen:
        if pi < plen and (pattern[pi] == topic[ti] or pattern[pi] == "?"):
            pi += 1
            ti += 1
        elif pi < plen and pattern[pi] == "*":
            star_pi = pi
            star_ti = ti
            pi += 1
        elif star_pi >= 0:
            pi = star_pi + 1
            star_ti += 1
            ti = star_ti
        else:
            return False

    while pi < plen and pattern[pi] == "*":
        pi += 1

    return pi == plen


class EventStreamBridge:
    """
    Bridges the NautilusTrader message bus to WebSocket event streams.

    Subscribes to message bus topics and fans out serialized events to
    connected WebSocket clients. Maintains a ring buffer for reconnection
    replay.

    Parameters
    ----------
    config : EventStreamConfig
        The streaming configuration.
    logger : Logger
        The logger instance.

    """

    def __init__(self, config: EventStreamConfig, logger: Logger) -> None:
        self._config = config
        self._log = logger
        self._ring_buffer = RingBuffer(config.replay_buffer_size)
        self._clients: dict[str, ClientConnection] = {}

    @property
    def client_count(self) -> int:
        """Return the number of connected clients."""
        return len(self._clients)

    @property
    def ring_buffer(self) -> RingBuffer:
        """Return the ring buffer."""
        return self._ring_buffer

    def add_client(
        self,
        client_id: str,
        topics: list[str] | None = None,
    ) -> ClientConnection | None:
        """
        Register a new client. Returns None if max clients reached.

        Parameters
        ----------
        client_id : str
            Unique client identifier.
        topics : list[str] | None
            Topic filter patterns. None subscribes to all.

        Returns
        -------
        ClientConnection | None

        """
        if len(self._clients) >= self._config.max_clients:
            self._log.warning(
                f"Max clients ({self._config.max_clients}) reached, "
                f"rejecting client {client_id}",
            )
            return None

        if client_id in self._clients:
            self._log.warning(f"Client {client_id} already connected, replacing")
            # Don't await close here — just overwrite
            del self._clients[client_id]

        conn = ClientConnection(
            client_id=client_id,
            queue_size=self._config.client_queue_size,
            topics=topics,
        )
        self._clients[client_id] = conn
        self._log.info(f"Client {client_id} connected (total: {len(self._clients)})")
        return conn

    def remove_client(self, client_id: str) -> None:
        """
        Remove a client connection.

        Parameters
        ----------
        client_id : str
            The client identifier to remove.

        """
        if client_id in self._clients:
            conn = self._clients.pop(client_id)
            if conn.dropped_count > 0:
                self._log.warning(
                    f"Client {client_id} disconnected, dropped {conn.dropped_count} events",
                )
            else:
                self._log.info(
                    f"Client {client_id} disconnected (total: {len(self._clients)})",
                )

    def on_event(self, event: Any) -> None:
        """
        Handle an incoming event from the message bus.

        Serializes the event, appends to the ring buffer, and fans out
        to all matching client queues.

        Parameters
        ----------
        event : Any
            The event object from the message bus.

        """
        topic = getattr(event, "_topic", "")
        serialized = serialize_event(event, topic=topic)
        seq = self._ring_buffer.append(serialized)

        for conn in list(self._clients.values()):
            if conn.matches_topic(topic):
                conn.try_enqueue(serialized)

    def replay_for_client(self, client_id: str, last_sequence: int) -> list[dict]:
        """
        Get replay events for a reconnecting client.

        Parameters
        ----------
        client_id : str
            The client identifier.
        last_sequence : int
            The last sequence the client received.

        Returns
        -------
        list[dict]

        """
        conn = self._clients.get(client_id)
        if conn is None:
            return []

        events = self._ring_buffer.replay_from(last_sequence)
        return [e for e in events if conn.matches_topic(e.get("topic", ""))]

    async def close_all(self) -> None:
        """Close all client connections."""
        for conn in list(self._clients.values()):
            await conn.close()
        self._clients.clear()
        self._log.info("All event stream clients closed")
