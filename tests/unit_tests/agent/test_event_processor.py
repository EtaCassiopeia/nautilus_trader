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

import time

from nautilus_trader.agent.config import AgentConfig
from nautilus_trader.agent.event_processor import AgentState
from nautilus_trader.agent.event_processor import EventProcessor
from nautilus_trader.agent.event_processor import HIGH_PRIORITY_EVENT_TYPES


class TestAgentState:
    def test_initial_state_is_empty(self) -> None:
        state = AgentState()

        assert state.positions == {}
        assert state.portfolio == {}
        assert state.active_orders == {}
        assert state.strategies == {}
        assert state.last_update_ts == 0.0

    def test_position_opened_updates_positions(self) -> None:
        state = AgentState()

        state.update_from_event({
            "type": "PositionOpened",
            "instrument_id": "BTCUSDT-PERP.BINANCE",
            "side": "LONG",
            "quantity": "1.5",
            "avg_px_open": "50000.0",
            "unrealized_pnl": "0.0",
        })

        assert "BTCUSDT-PERP.BINANCE" in state.positions
        pos = state.positions["BTCUSDT-PERP.BINANCE"]
        assert pos["side"] == "LONG"
        assert pos["quantity"] == "1.5"

    def test_position_changed_updates_existing(self) -> None:
        state = AgentState()
        state.update_from_event({
            "type": "PositionOpened",
            "instrument_id": "BTCUSDT-PERP.BINANCE",
            "side": "LONG",
            "quantity": "1.0",
        })

        state.update_from_event({
            "type": "PositionChanged",
            "instrument_id": "BTCUSDT-PERP.BINANCE",
            "side": "LONG",
            "quantity": "2.0",
        })

        assert state.positions["BTCUSDT-PERP.BINANCE"]["quantity"] == "2.0"

    def test_position_closed_removes_position(self) -> None:
        state = AgentState()
        state.update_from_event({
            "type": "PositionOpened",
            "instrument_id": "BTCUSDT-PERP.BINANCE",
            "side": "LONG",
            "quantity": "1.0",
        })

        state.update_from_event({
            "type": "PositionClosed",
            "instrument_id": "BTCUSDT-PERP.BINANCE",
        })

        assert "BTCUSDT-PERP.BINANCE" not in state.positions

    def test_position_closed_for_unknown_instrument_is_noop(self) -> None:
        state = AgentState()

        state.update_from_event({
            "type": "PositionClosed",
            "instrument_id": "UNKNOWN",
        })

        assert state.positions == {}

    def test_order_submitted_adds_active_order(self) -> None:
        state = AgentState()

        state.update_from_event({
            "type": "OrderSubmitted",
            "client_order_id": "O-001",
            "instrument_id": "ETHUSDT-PERP.BINANCE",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": "10.0",
            "price": "3000.0",
        })

        assert "O-001" in state.active_orders
        order = state.active_orders["O-001"]
        assert order["instrument_id"] == "ETHUSDT-PERP.BINANCE"
        assert order["status"] == "OrderSubmitted"

    def test_order_filled_removes_active_order(self) -> None:
        state = AgentState()
        state.update_from_event({
            "type": "OrderSubmitted",
            "client_order_id": "O-001",
            "instrument_id": "ETHUSDT-PERP.BINANCE",
            "quantity": "10.0",
        })

        state.update_from_event({
            "type": "OrderFilled",
            "client_order_id": "O-001",
        })

        assert "O-001" not in state.active_orders

    def test_order_canceled_removes_active_order(self) -> None:
        state = AgentState()
        state.update_from_event({
            "type": "OrderSubmitted",
            "client_order_id": "O-002",
            "instrument_id": "ETHUSDT-PERP.BINANCE",
            "quantity": "5.0",
        })

        state.update_from_event({
            "type": "OrderCanceled",
            "client_order_id": "O-002",
        })

        assert "O-002" not in state.active_orders

    def test_portfolio_update(self) -> None:
        state = AgentState()

        state.update_from_event({
            "type": "PortfolioUpdate",
            "total_equity": "100000.0",
            "unrealized_pnl": "500.0",
        })

        assert state.portfolio["total_equity"] == "100000.0"
        assert state.portfolio["unrealized_pnl"] == "500.0"
        assert "type" not in state.portfolio

    def test_strategy_state_update(self) -> None:
        state = AgentState()

        state.update_from_event({
            "type": "StrategyStateUpdate",
            "strategy_id": "EMA_CROSS-001",
            "is_active": True,
            "signal": "LONG",
        })

        assert "EMA_CROSS-001" in state.strategies
        assert state.strategies["EMA_CROSS-001"]["is_active"] is True

    def test_unknown_event_type_updates_timestamp(self) -> None:
        state = AgentState()

        state.update_from_event({"type": "SomeOtherEvent"})

        assert state.last_update_ts > 0.0

    def test_snapshot_returns_serializable_dict(self) -> None:
        state = AgentState()
        state.update_from_event({
            "type": "PositionOpened",
            "instrument_id": "BTCUSDT-PERP.BINANCE",
            "side": "LONG",
            "quantity": "1.0",
        })

        snap = state.snapshot()

        assert isinstance(snap, dict)
        assert "positions" in snap
        assert "portfolio" in snap
        assert "active_orders" in snap
        assert "strategies" in snap
        assert "last_update_ts" in snap
        assert "BTCUSDT-PERP.BINANCE" in snap["positions"]

    def test_event_with_missing_instrument_id_is_noop_for_positions(self) -> None:
        state = AgentState()

        state.update_from_event({
            "type": "PositionOpened",
        })

        assert state.positions == {}

    def test_event_with_missing_client_order_id_is_noop_for_orders(self) -> None:
        state = AgentState()

        state.update_from_event({
            "type": "OrderSubmitted",
        })

        assert state.active_orders == {}


class TestEventProcessor:
    def _make_processor(self, **kwargs) -> EventProcessor:
        config = AgentConfig(**kwargs)
        return EventProcessor(config)

    def test_initial_state(self) -> None:
        proc = self._make_processor()

        assert proc.buffer_size == 0
        assert proc.state.positions == {}

    def test_ingest_adds_to_buffer(self) -> None:
        proc = self._make_processor()

        proc.ingest({"type": "QuoteTickUpdate", "bid": "50000"})

        assert proc.buffer_size == 1

    def test_ingest_updates_state(self) -> None:
        proc = self._make_processor()

        proc.ingest({
            "type": "PositionOpened",
            "instrument_id": "BTCUSDT-PERP.BINANCE",
            "side": "LONG",
            "quantity": "1.0",
        })

        assert "BTCUSDT-PERP.BINANCE" in proc.state.positions

    def test_flush_returns_and_clears_buffer(self) -> None:
        proc = self._make_processor()
        proc.ingest({"type": "QuoteTickUpdate", "bid": "50000"})
        proc.ingest({"type": "QuoteTickUpdate", "bid": "50001"})

        batch = proc.flush()

        assert len(batch) == 2
        assert proc.buffer_size == 0

    def test_flush_empty_buffer(self) -> None:
        proc = self._make_processor()

        batch = proc.flush()

        assert batch == []

    def test_should_flush_false_when_empty(self) -> None:
        proc = self._make_processor()

        assert proc.should_flush() is False

    def test_should_flush_true_on_high_priority_event(self) -> None:
        proc = self._make_processor(event_batch_interval_secs=999.0)

        proc.ingest({"type": "OrderFilled", "client_order_id": "O-001"})

        assert proc.should_flush() is True

    def test_should_flush_true_on_position_change(self) -> None:
        proc = self._make_processor(event_batch_interval_secs=999.0)

        proc.ingest({
            "type": "PositionClosed",
            "instrument_id": "BTCUSDT-PERP.BINANCE",
        })

        assert proc.should_flush() is True

    def test_should_flush_false_before_interval(self) -> None:
        proc = self._make_processor(event_batch_interval_secs=999.0)

        proc.ingest({"type": "QuoteTickUpdate", "bid": "50000"})

        assert proc.should_flush() is False

    def test_should_flush_true_after_interval(self) -> None:
        proc = self._make_processor(event_batch_interval_secs=0.5)
        # Backdate the last flush time
        proc._last_flush_time = time.time() - 1.0

        proc.ingest({"type": "QuoteTickUpdate", "bid": "50000"})

        assert proc.should_flush() is True

    def test_flush_resets_flush_timer(self) -> None:
        proc = self._make_processor(event_batch_interval_secs=999.0)
        proc._last_flush_time = time.time() - 1000.0
        proc.ingest({"type": "QuoteTickUpdate"})

        assert proc.should_flush() is True

        proc.flush()
        proc.ingest({"type": "QuoteTickUpdate"})

        assert proc.should_flush() is False

    def test_get_context_includes_state_and_events(self) -> None:
        proc = self._make_processor()
        proc.ingest({
            "type": "PositionOpened",
            "instrument_id": "BTCUSDT-PERP.BINANCE",
            "side": "LONG",
            "quantity": "1.0",
        })

        ctx = proc.get_context()

        assert "state" in ctx
        assert "recent_events" in ctx
        assert len(ctx["recent_events"]) == 1
        assert "BTCUSDT-PERP.BINANCE" in ctx["state"]["positions"]

    def test_sliding_window_caps_at_max_context_events(self) -> None:
        proc = self._make_processor(max_context_events=3)

        for i in range(5):
            proc.ingest({"type": "QuoteTickUpdate", "seq": i})

        ctx = proc.get_context()

        assert len(ctx["recent_events"]) == 3
        # Should contain the last 3 events (indices 2, 3, 4)
        assert ctx["recent_events"][0]["seq"] == 2
        assert ctx["recent_events"][2]["seq"] == 4

    def test_sliding_window_independent_of_flush(self) -> None:
        proc = self._make_processor(max_context_events=10)

        proc.ingest({"type": "QuoteTickUpdate", "seq": 0})
        proc.ingest({"type": "QuoteTickUpdate", "seq": 1})
        proc.flush()
        proc.ingest({"type": "QuoteTickUpdate", "seq": 2})

        ctx = proc.get_context()

        # All 3 events should be in recent_events despite the flush
        assert len(ctx["recent_events"]) == 3

    def test_all_high_priority_types_trigger_flush(self) -> None:
        for event_type in HIGH_PRIORITY_EVENT_TYPES:
            proc = self._make_processor(event_batch_interval_secs=999.0)
            proc.ingest({"type": event_type})

            assert proc.should_flush() is True, (
                f"Expected {event_type} to trigger flush"
            )

    def test_multiple_ingests_accumulate_in_buffer(self) -> None:
        proc = self._make_processor()

        for i in range(10):
            proc.ingest({"type": "QuoteTickUpdate", "seq": i})

        assert proc.buffer_size == 10

        batch = proc.flush()

        assert len(batch) == 10
        assert proc.buffer_size == 0
