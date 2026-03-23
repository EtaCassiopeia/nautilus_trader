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

import json
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path


@dataclass
class TradeMemory:
    """
    A recorded trade memory for cross-cycle learning.

    Parameters
    ----------
    trade_id : str
        Unique identifier for this trade.
    timestamp : str
        ISO 8601 formatted timestamp of the trade.
    instrument_id : str
        The instrument that was traded.
    side : str
        Trade side: "BUY" or "SELL".
    quantity : str
        Trade quantity as a decimal string.
    entry_reasoning : str
        Why the trade was made.
    market_conditions : dict
        State snapshot at decision time.
    outcome : dict or None
        Filled after trade closes: pnl, duration, etc.

    """

    trade_id: str
    timestamp: str
    instrument_id: str
    side: str
    quantity: str
    entry_reasoning: str
    market_conditions: dict = field(default_factory=dict)
    outcome: dict | None = None


class TradingMemory:
    """
    Persistent memory for cross-cycle learning.

    Maintains a list of trade memories and optionally persists them to a
    JSONL file on disk. Supports querying by instrument, outcome, and
    formatting memories as context for the reasoning engine.

    Parameters
    ----------
    storage_path : str, optional
        Path to the JSONL file for persistent storage. If None, memories
        are only stored in memory.
    max_memories : int
        Maximum number of trade memories to retain.

    """

    def __init__(
        self,
        storage_path: str | None = None,
        max_memories: int = 500,
    ) -> None:
        self._memories: list[TradeMemory] = []
        self._storage_path = Path(storage_path) if storage_path else None
        self._max_memories = max_memories

        if self._storage_path is not None:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            self._load()

    def remember_trade(self, memory: TradeMemory) -> None:
        """
        Store a trade memory.

        Appends the memory to the in-memory list and persists to file
        if a storage path is configured. Evicts the oldest memory when
        the maximum is exceeded.

        Parameters
        ----------
        memory : TradeMemory
            The trade memory to store.

        """
        self._memories.append(memory)

        if len(self._memories) > self._max_memories:
            self._memories = self._memories[-self._max_memories :]

        self._save()

    def update_outcome(self, trade_id: str, outcome: dict) -> None:
        """
        Update a trade's outcome after it closes.

        Parameters
        ----------
        trade_id : str
            The trade identifier to update.
        outcome : dict
            Outcome data (pnl, duration, etc.).

        """
        for memory in self._memories:
            if memory.trade_id == trade_id:
                memory.outcome = outcome
                self._save()
                return

    def get_recent(self, count: int = 10) -> list[TradeMemory]:
        """
        Get the most recent trade memories.

        Parameters
        ----------
        count : int
            Number of recent memories to return.

        Returns
        -------
        list[TradeMemory]
            Most recent trade memories, oldest first.

        """
        return self._memories[-count:] if len(self._memories) > count else list(self._memories)

    def get_by_instrument(self, instrument_id: str, count: int = 5) -> list[TradeMemory]:
        """
        Get memories for a specific instrument.

        Parameters
        ----------
        instrument_id : str
            The instrument identifier to filter by.
        count : int
            Maximum number of memories to return.

        Returns
        -------
        list[TradeMemory]
            Matching memories, most recent last.

        """
        matches = [m for m in self._memories if m.instrument_id == instrument_id]
        return matches[-count:] if len(matches) > count else matches

    def get_winning_patterns(self) -> list[TradeMemory]:
        """
        Get trades that resulted in positive P&L.

        Returns
        -------
        list[TradeMemory]
            Trades with positive pnl in their outcome.

        """
        return [
            m
            for m in self._memories
            if m.outcome is not None and float(m.outcome.get("pnl", 0)) > 0
        ]

    def get_losing_patterns(self) -> list[TradeMemory]:
        """
        Get trades that resulted in negative P&L.

        Returns
        -------
        list[TradeMemory]
            Trades with negative pnl in their outcome.

        """
        return [
            m
            for m in self._memories
            if m.outcome is not None and float(m.outcome.get("pnl", 0)) < 0
        ]

    def get_performance_summary(self) -> dict:
        """
        Summarize win rate, average profit, average loss, etc.

        Returns
        -------
        dict
            Performance summary with keys: total_trades, completed_trades,
            wins, losses, win_rate, avg_profit, avg_loss.

        """
        completed = [m for m in self._memories if m.outcome is not None]
        if not completed:
            return {
                "total_trades": len(self._memories),
                "completed_trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0.0,
                "avg_profit": 0.0,
                "avg_loss": 0.0,
            }

        profits = []
        losses = []
        for m in completed:
            pnl = float(m.outcome.get("pnl", 0))  # type: ignore[union-attr]
            if pnl > 0:
                profits.append(pnl)
            elif pnl < 0:
                losses.append(pnl)

        wins = len(profits)
        loss_count = len(losses)
        total_completed = len(completed)

        return {
            "total_trades": len(self._memories),
            "completed_trades": total_completed,
            "wins": wins,
            "losses": loss_count,
            "win_rate": wins / total_completed if total_completed > 0 else 0.0,
            "avg_profit": sum(profits) / wins if wins > 0 else 0.0,
            "avg_loss": sum(losses) / loss_count if loss_count > 0 else 0.0,
        }

    def to_context(self, instrument_id: str | None = None, count: int = 10) -> str:
        """
        Format memories as a context string for the reasoning engine.

        Parameters
        ----------
        instrument_id : str, optional
            If provided, filter memories to this instrument.
        count : int
            Number of recent memories to include.

        Returns
        -------
        str
            Formatted context string summarizing recent trade memories.

        """
        if instrument_id is not None:
            memories = self.get_by_instrument(instrument_id, count)
        else:
            memories = self.get_recent(count)

        if not memories:
            return "No previous trade memories."

        lines = ["=== Trade Memory ==="]
        for m in memories:
            outcome_str = ""
            if m.outcome is not None:
                pnl = m.outcome.get("pnl", "unknown")
                outcome_str = f" | outcome: pnl={pnl}"
            lines.append(
                f"[{m.timestamp}] {m.instrument_id} {m.side} {m.quantity}"
                f" - {m.entry_reasoning}{outcome_str}"
            )

        summary = self.get_performance_summary()
        lines.append(
            f"--- Performance: {summary['wins']}W/{summary['losses']}L"
            f" ({summary['win_rate']:.0%} win rate)"
            f" avg_profit={summary['avg_profit']:.2f}"
            f" avg_loss={summary['avg_loss']:.2f}"
        )

        return "\n".join(lines)

    def _save(self) -> None:
        """Persist all memories to the JSONL file, overwriting existing content."""
        if self._storage_path is None:
            return

        with self._storage_path.open("w") as f:
            for memory in self._memories:
                f.write(json.dumps(asdict(memory)) + "\n")

    def _load(self) -> None:
        """Load memories from the JSONL file if it exists."""
        if self._storage_path is None or not self._storage_path.exists():
            return

        loaded: list[TradeMemory] = []
        with self._storage_path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                loaded.append(TradeMemory(**data))

        # Respect max_memories limit
        if len(loaded) > self._max_memories:
            loaded = loaded[-self._max_memories :]

        self._memories = loaded
