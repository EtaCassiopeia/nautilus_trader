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

from nautilus_trader.agent.audit import AuditLog
from nautilus_trader.agent.audit import Decision


def _make_decision(decision_id: str = "d-1") -> Decision:
    return Decision(
        decision_id=decision_id,
        timestamp="2026-03-21T12:00:00Z",
        mode="AUTONOMOUS",
        trigger={"event": "price_update", "objective_id": "obj-1"},
        reasoning="Price crossed above resistance, entering long.",
        action={"tool": "submit_order", "params": {"side": "BUY", "quantity": "1.0"}},
        guardrail_check={"passed": True, "checks": ["mode_check: OK"]},
        outcome={"status": "submitted", "order_id": "O-001"},
    )


class TestDecision:
    def test_defaults(self) -> None:
        decision = Decision(
            decision_id="d-1",
            timestamp="2026-03-21T12:00:00Z",
            mode="MONITOR",
        )

        assert decision.decision_id == "d-1"
        assert decision.timestamp == "2026-03-21T12:00:00Z"
        assert decision.mode == "MONITOR"
        assert decision.trigger == {}
        assert decision.reasoning == ""
        assert decision.action is None
        assert decision.guardrail_check == {}
        assert decision.outcome == {}

    def test_full_construction(self) -> None:
        decision = _make_decision()

        assert decision.decision_id == "d-1"
        assert decision.mode == "AUTONOMOUS"
        assert decision.trigger["event"] == "price_update"
        assert decision.action["tool"] == "submit_order"
        assert decision.guardrail_check["passed"] is True
        assert decision.outcome["order_id"] == "O-001"


class TestAuditLog:
    def test_record_and_get_recent(self) -> None:
        log = AuditLog()
        d1 = _make_decision("d-1")
        d2 = _make_decision("d-2")

        log.record(d1)
        log.record(d2)

        recent = log.get_recent(10)
        assert len(recent) == 2
        assert recent[0].decision_id == "d-1"
        assert recent[1].decision_id == "d-2"

    def test_get_recent_limits_count(self) -> None:
        log = AuditLog()
        for i in range(20):
            log.record(_make_decision(f"d-{i}"))

        recent = log.get_recent(5)
        assert len(recent) == 5
        assert recent[0].decision_id == "d-15"
        assert recent[4].decision_id == "d-19"

    def test_get_recent_returns_all_when_fewer_than_count(self) -> None:
        log = AuditLog()
        log.record(_make_decision("d-1"))

        recent = log.get_recent(10)
        assert len(recent) == 1

    def test_in_memory_buffer_respects_max(self) -> None:
        log = AuditLog(max_in_memory=5)
        for i in range(10):
            log.record(_make_decision(f"d-{i}"))

        recent = log.get_recent(100)
        assert len(recent) == 5
        assert recent[0].decision_id == "d-5"

    def test_to_context(self) -> None:
        log = AuditLog()
        log.record(_make_decision("d-1"))
        log.record(_make_decision("d-2"))
        log.record(_make_decision("d-3"))

        context = log.to_context(count=2)

        assert len(context) == 2
        assert context[0]["decision_id"] == "d-2"
        assert context[1]["decision_id"] == "d-3"
        assert isinstance(context[0], dict)
        assert "reasoning" in context[0]

    def test_to_context_empty(self) -> None:
        log = AuditLog()

        assert log.to_context() == []

    def test_persists_to_jsonl_file(self, tmp_path) -> None:
        log_file = tmp_path / "audit.jsonl"
        log = AuditLog(log_path=str(log_file))

        log.record(_make_decision("d-1"))
        log.record(_make_decision("d-2"))

        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 2

        first = json.loads(lines[0])
        assert first["decision_id"] == "d-1"
        assert first["mode"] == "AUTONOMOUS"

        second = json.loads(lines[1])
        assert second["decision_id"] == "d-2"

    def test_creates_parent_directories(self, tmp_path) -> None:
        log_file = tmp_path / "nested" / "dir" / "audit.jsonl"
        log = AuditLog(log_path=str(log_file))

        log.record(_make_decision("d-1"))

        assert log_file.exists()

    def test_no_file_when_path_is_none(self) -> None:
        log = AuditLog()

        log.record(_make_decision("d-1"))

        # Should not raise; just stores in memory
        assert len(log.get_recent()) == 1
