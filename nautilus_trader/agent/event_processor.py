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

import time
from collections import deque
from dataclasses import dataclass
from dataclasses import field
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from nautilus_trader.agent.config import AgentConfig


# Event types that trigger an immediate flush rather than waiting for the batch interval.
HIGH_PRIORITY_EVENT_TYPES: frozenset[str] = frozenset({
    "OrderFilled",
    "PositionOpened",
    "PositionChanged",
    "PositionClosed",
})


@dataclass
class AgentState:
    """
    Tracks current agent state derived from the event stream.

    The state is updated incrementally as events arrive, providing an
    up-to-date view of positions, portfolio, orders, and strategies.

    """

    positions: dict[str, dict] = field(default_factory=dict)
    portfolio: dict = field(default_factory=dict)
    active_orders: dict[str, dict] = field(default_factory=dict)
    strategies: dict[str, dict] = field(default_factory=dict)
    last_update_ts: float = 0.0

    def update_from_event(self, event: dict) -> None:
        """
        Update state based on an event type.

        Parameters
        ----------
        event : dict
            The event dictionary, expected to contain at least a "type" key.

        """
        event_type = event.get("type", "")
        self.last_update_ts = time.time()

        if event_type in ("PositionOpened", "PositionChanged"):
            instrument_id = event.get("instrument_id", "")
            if instrument_id:
                self.positions[instrument_id] = {
                    "instrument_id": instrument_id,
                    "side": event.get("side", ""),
                    "quantity": event.get("quantity", "0"),
                    "avg_px_open": event.get("avg_px_open", ""),
                    "unrealized_pnl": event.get("unrealized_pnl", ""),
                }

        elif event_type == "PositionClosed":
            instrument_id = event.get("instrument_id", "")
            self.positions.pop(instrument_id, None)

        elif event_type in ("OrderSubmitted", "OrderAccepted", "OrderUpdated"):
            client_order_id = event.get("client_order_id", "")
            if client_order_id:
                self.active_orders[client_order_id] = {
                    "client_order_id": client_order_id,
                    "instrument_id": event.get("instrument_id", ""),
                    "side": event.get("side", ""),
                    "order_type": event.get("order_type", ""),
                    "quantity": event.get("quantity", "0"),
                    "price": event.get("price", ""),
                    "status": event_type,
                }

        elif event_type in ("OrderFilled", "OrderCanceled", "OrderExpired", "OrderRejected"):
            client_order_id = event.get("client_order_id", "")
            self.active_orders.pop(client_order_id, None)

        elif event_type == "PortfolioUpdate":
            self.portfolio = {
                k: v for k, v in event.items()
                if k != "type"
            }

        elif event_type == "StrategyStateUpdate":
            strategy_id = event.get("strategy_id", "")
            if strategy_id:
                self.strategies[strategy_id] = {
                    k: v for k, v in event.items()
                    if k != "type"
                }

    def snapshot(self) -> dict:
        """
        Return a serializable snapshot of current state.

        Returns
        -------
        dict

        """
        return {
            "positions": dict(self.positions),
            "portfolio": dict(self.portfolio),
            "active_orders": dict(self.active_orders),
            "strategies": dict(self.strategies),
            "last_update_ts": self.last_update_ts,
        }


class EventProcessor:
    """
    Processes events from the WebSocket stream, batches them, and maintains state.

    Events are accumulated in a buffer and flushed either when the configured
    batch interval elapses or when a high-priority event (e.g. order fill,
    position change) arrives. A sliding window of recent events is maintained
    for context assembly.

    Parameters
    ----------
    config : AgentConfig
        The agent configuration.

    """

    def __init__(self, config: AgentConfig) -> None:
        self._batch_interval = config.event_batch_interval_secs
        self._max_context_events = config.max_context_events
        self._event_buffer: list[dict] = []
        self._recent_events: deque[dict] = deque(maxlen=config.max_context_events)
        self._state = AgentState()
        self._last_flush_time: float = time.time()

    @property
    def state(self) -> AgentState:
        """Return the current agent state."""
        return self._state

    @property
    def buffer_size(self) -> int:
        """Return the number of events in the current batch buffer."""
        return len(self._event_buffer)

    def ingest(self, event: dict) -> None:
        """
        Add an event to the current batch and update state.

        Parameters
        ----------
        event : dict
            The event dictionary.

        """
        self._event_buffer.append(event)
        self._recent_events.append(event)
        self._state.update_from_event(event)

    def should_flush(self) -> bool:
        """
        Check if the event buffer should be flushed.

        Flush is triggered when:
        - The batch interval has elapsed since the last flush, or
        - The buffer contains a high-priority event.

        Returns
        -------
        bool

        """
        if not self._event_buffer:
            return False

        # High-priority events trigger immediate flush
        for event in self._event_buffer:
            if event.get("type", "") in HIGH_PRIORITY_EVENT_TYPES:
                return True

        # Time-based flush
        elapsed = time.time() - self._last_flush_time
        return elapsed >= self._batch_interval

    def flush(self) -> list[dict]:
        """
        Return and clear the current event batch.

        Returns
        -------
        list[dict]
            The events that were in the buffer.

        """
        batch = list(self._event_buffer)
        self._event_buffer.clear()
        self._last_flush_time = time.time()
        return batch

    def get_context(self) -> dict:
        """
        Build context dict for the reasoning engine.

        The context includes the current state snapshot and a window of
        recent events, capped at ``max_context_events``.

        Returns
        -------
        dict

        """
        return {
            "state": self._state.snapshot(),
            "recent_events": list(self._recent_events),
        }
