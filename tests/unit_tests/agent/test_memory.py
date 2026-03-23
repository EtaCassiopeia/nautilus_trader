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

import json

from nautilus_trader.agent.memory import TradeMemory
from nautilus_trader.agent.memory import TradingMemory


def _make_memory(
    trade_id: str = "t-1",
    instrument_id: str = "BTCUSDT-PERP.BINANCE",
    side: str = "BUY",
    outcome: dict | None = None,
) -> TradeMemory:
    return TradeMemory(
        trade_id=trade_id,
        timestamp="2026-03-21T12:00:00Z",
        instrument_id=instrument_id,
        side=side,
        quantity="1.0",
        entry_reasoning="Price crossed above resistance.",
        market_conditions={"rsi": 65, "trend": "bullish"},
        outcome=outcome,
    )


class TestTradeMemory:
    def test_defaults(self) -> None:
        memory = TradeMemory(
            trade_id="t-1",
            timestamp="2026-03-21T12:00:00Z",
            instrument_id="BTCUSDT-PERP.BINANCE",
            side="BUY",
            quantity="1.0",
            entry_reasoning="Test trade.",
        )

        assert memory.trade_id == "t-1"
        assert memory.instrument_id == "BTCUSDT-PERP.BINANCE"
        assert memory.side == "BUY"
        assert memory.market_conditions == {}
        assert memory.outcome is None

    def test_full_construction(self) -> None:
        memory = _make_memory(outcome={"pnl": "150.0", "duration": "2h"})

        assert memory.trade_id == "t-1"
        assert memory.market_conditions["rsi"] == 65
        assert memory.outcome["pnl"] == "150.0"


class TestTradingMemory:
    def test_remember_and_get_recent(self) -> None:
        mem = TradingMemory()
        mem.remember_trade(_make_memory("t-1"))
        mem.remember_trade(_make_memory("t-2"))

        recent = mem.get_recent(10)
        assert len(recent) == 2
        assert recent[0].trade_id == "t-1"
        assert recent[1].trade_id == "t-2"

    def test_get_recent_limits_count(self) -> None:
        mem = TradingMemory()
        for i in range(20):
            mem.remember_trade(_make_memory(f"t-{i}"))

        recent = mem.get_recent(5)
        assert len(recent) == 5
        assert recent[0].trade_id == "t-15"
        assert recent[4].trade_id == "t-19"

    def test_get_recent_returns_all_when_fewer_than_count(self) -> None:
        mem = TradingMemory()
        mem.remember_trade(_make_memory("t-1"))

        recent = mem.get_recent(10)
        assert len(recent) == 1

    def test_max_memories_eviction(self) -> None:
        mem = TradingMemory(max_memories=5)
        for i in range(10):
            mem.remember_trade(_make_memory(f"t-{i}"))

        recent = mem.get_recent(100)
        assert len(recent) == 5
        assert recent[0].trade_id == "t-5"

    def test_update_outcome(self) -> None:
        mem = TradingMemory()
        mem.remember_trade(_make_memory("t-1"))

        mem.update_outcome("t-1", {"pnl": "200.0", "duration": "1h"})

        recent = mem.get_recent()
        assert recent[0].outcome == {"pnl": "200.0", "duration": "1h"}

    def test_update_outcome_nonexistent_trade(self) -> None:
        mem = TradingMemory()
        mem.remember_trade(_make_memory("t-1"))

        # Should not raise
        mem.update_outcome("t-999", {"pnl": "100.0"})

        assert mem.get_recent()[0].outcome is None

    def test_get_by_instrument(self) -> None:
        mem = TradingMemory()
        mem.remember_trade(_make_memory("t-1", instrument_id="BTCUSDT-PERP.BINANCE"))
        mem.remember_trade(_make_memory("t-2", instrument_id="ETHUSDT-PERP.BINANCE"))
        mem.remember_trade(_make_memory("t-3", instrument_id="BTCUSDT-PERP.BINANCE"))

        btc_memories = mem.get_by_instrument("BTCUSDT-PERP.BINANCE")
        assert len(btc_memories) == 2
        assert btc_memories[0].trade_id == "t-1"
        assert btc_memories[1].trade_id == "t-3"

    def test_get_by_instrument_limits_count(self) -> None:
        mem = TradingMemory()
        for i in range(10):
            mem.remember_trade(_make_memory(f"t-{i}", instrument_id="BTCUSDT-PERP.BINANCE"))

        results = mem.get_by_instrument("BTCUSDT-PERP.BINANCE", count=3)
        assert len(results) == 3
        assert results[0].trade_id == "t-7"

    def test_get_winning_patterns(self) -> None:
        mem = TradingMemory()
        mem.remember_trade(_make_memory("t-1", outcome={"pnl": "150.0"}))
        mem.remember_trade(_make_memory("t-2", outcome={"pnl": "-50.0"}))
        mem.remember_trade(_make_memory("t-3", outcome={"pnl": "200.0"}))
        mem.remember_trade(_make_memory("t-4"))  # No outcome

        winners = mem.get_winning_patterns()
        assert len(winners) == 2
        assert winners[0].trade_id == "t-1"
        assert winners[1].trade_id == "t-3"

    def test_get_losing_patterns(self) -> None:
        mem = TradingMemory()
        mem.remember_trade(_make_memory("t-1", outcome={"pnl": "150.0"}))
        mem.remember_trade(_make_memory("t-2", outcome={"pnl": "-50.0"}))
        mem.remember_trade(_make_memory("t-3", outcome={"pnl": "-100.0"}))

        losers = mem.get_losing_patterns()
        assert len(losers) == 2
        assert losers[0].trade_id == "t-2"
        assert losers[1].trade_id == "t-3"

    def test_get_performance_summary_no_trades(self) -> None:
        mem = TradingMemory()

        summary = mem.get_performance_summary()
        assert summary["total_trades"] == 0
        assert summary["completed_trades"] == 0
        assert summary["win_rate"] == 0.0

    def test_get_performance_summary_no_completed(self) -> None:
        mem = TradingMemory()
        mem.remember_trade(_make_memory("t-1"))

        summary = mem.get_performance_summary()
        assert summary["total_trades"] == 1
        assert summary["completed_trades"] == 0

    def test_get_performance_summary(self) -> None:
        mem = TradingMemory()
        mem.remember_trade(_make_memory("t-1", outcome={"pnl": "100.0"}))
        mem.remember_trade(_make_memory("t-2", outcome={"pnl": "200.0"}))
        mem.remember_trade(_make_memory("t-3", outcome={"pnl": "-50.0"}))
        mem.remember_trade(_make_memory("t-4"))  # No outcome

        summary = mem.get_performance_summary()
        assert summary["total_trades"] == 4
        assert summary["completed_trades"] == 3
        assert summary["wins"] == 2
        assert summary["losses"] == 1
        assert summary["win_rate"] == 2 / 3
        assert summary["avg_profit"] == 150.0
        assert summary["avg_loss"] == -50.0

    def test_to_context_empty(self) -> None:
        mem = TradingMemory()

        assert mem.to_context() == "No previous trade memories."

    def test_to_context_with_memories(self) -> None:
        mem = TradingMemory()
        mem.remember_trade(_make_memory("t-1", outcome={"pnl": "100.0"}))
        mem.remember_trade(_make_memory("t-2"))

        context = mem.to_context()
        assert "=== Trade Memory ===" in context
        assert "BTCUSDT-PERP.BINANCE" in context
        assert "BUY" in context
        assert "pnl=100.0" in context
        assert "Performance:" in context

    def test_to_context_filters_by_instrument(self) -> None:
        mem = TradingMemory()
        mem.remember_trade(_make_memory("t-1", instrument_id="BTCUSDT-PERP.BINANCE"))
        mem.remember_trade(_make_memory("t-2", instrument_id="ETHUSDT-PERP.BINANCE"))

        context = mem.to_context(instrument_id="ETHUSDT-PERP.BINANCE")
        assert "ETHUSDT-PERP.BINANCE" in context
        # Only the ETH trade should appear in the memory lines (BTC may appear in summary)
        lines = context.split("\n")
        memory_lines = [l for l in lines if "BUY" in l]
        assert len(memory_lines) == 1
        assert "ETHUSDT-PERP.BINANCE" in memory_lines[0]

    def test_persists_to_jsonl_file(self, tmp_path) -> None:
        storage_file = tmp_path / "memories.jsonl"
        mem = TradingMemory(storage_path=str(storage_file))

        mem.remember_trade(_make_memory("t-1"))
        mem.remember_trade(_make_memory("t-2"))

        lines = storage_file.read_text().strip().split("\n")
        assert len(lines) == 2

        first = json.loads(lines[0])
        assert first["trade_id"] == "t-1"
        assert first["instrument_id"] == "BTCUSDT-PERP.BINANCE"

        second = json.loads(lines[1])
        assert second["trade_id"] == "t-2"

    def test_loads_from_existing_jsonl_file(self, tmp_path) -> None:
        storage_file = tmp_path / "memories.jsonl"

        # Write memories with first instance
        mem1 = TradingMemory(storage_path=str(storage_file))
        mem1.remember_trade(_make_memory("t-1"))
        mem1.remember_trade(_make_memory("t-2"))

        # Load with a new instance
        mem2 = TradingMemory(storage_path=str(storage_file))
        recent = mem2.get_recent()
        assert len(recent) == 2
        assert recent[0].trade_id == "t-1"
        assert recent[1].trade_id == "t-2"

    def test_persists_outcome_update(self, tmp_path) -> None:
        storage_file = tmp_path / "memories.jsonl"
        mem = TradingMemory(storage_path=str(storage_file))
        mem.remember_trade(_make_memory("t-1"))

        mem.update_outcome("t-1", {"pnl": "300.0"})

        # Reload and verify
        mem2 = TradingMemory(storage_path=str(storage_file))
        assert mem2.get_recent()[0].outcome == {"pnl": "300.0"}

    def test_creates_parent_directories(self, tmp_path) -> None:
        storage_file = tmp_path / "nested" / "dir" / "memories.jsonl"
        mem = TradingMemory(storage_path=str(storage_file))

        mem.remember_trade(_make_memory("t-1"))

        assert storage_file.exists()

    def test_no_file_when_path_is_none(self) -> None:
        mem = TradingMemory()

        mem.remember_trade(_make_memory("t-1"))

        # Should not raise; just stores in memory
        assert len(mem.get_recent()) == 1
