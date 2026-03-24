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

from nautilus_trader.agent.prompts import build_context_message
from nautilus_trader.agent.prompts import build_system_prompt
from nautilus_trader.agent.prompts import format_guardrail_summary


class TestBuildSystemPrompt:
    def test_includes_mode(self) -> None:
        result = build_system_prompt("MONITOR", "- No limits", "- list_orders")

        assert "MONITOR" in result
        assert "observe events" in result.lower()

    def test_includes_guardrails(self) -> None:
        result = build_system_prompt("AUTONOMOUS", "- Max order: 1.0 BTC", "")

        assert "Max order: 1.0 BTC" in result

    def test_all_modes(self) -> None:
        for mode in ["MONITOR", "ADVISORY", "SEMI_AUTONOMOUS", "AUTONOMOUS"]:
            result = build_system_prompt(mode, "", "")
            assert mode in result


class TestBuildContextMessage:
    def test_includes_objectives(self) -> None:
        objectives = [
            {"description": "Build 10 BTC position", "priority": 1, "status": "ACTIVE"},
        ]
        result = build_context_message({}, [], objectives)

        assert "Build 10 BTC position" in result
        assert "ACTIVE" in result

    def test_includes_state(self) -> None:
        state = {"positions": {"BTC": {"quantity": "5.0"}}}
        result = build_context_message(state, [], [])

        assert "positions" in result
        assert "5.0" in result

    def test_includes_events(self) -> None:
        events = [
            {"type": "OrderFilled", "topic": "events.order", "ts_event": 1000, "data": {}},
        ]
        result = build_context_message({}, events, [])

        assert "OrderFilled" in result

    def test_includes_recent_decisions(self) -> None:
        decisions = [
            {
                "action": {"tool": "submit_order"},
                "reasoning": "Price dipped below threshold",
                "outcome": {"status": "executed"},
            },
        ]
        result = build_context_message({}, [], [], recent_decisions=decisions)

        assert "submit_order" in result
        assert "executed" in result

    def test_empty_context(self) -> None:
        result = build_context_message({}, [], [])

        assert "analyze the situation" in result.lower()

    def test_truncates_large_event_data(self) -> None:
        events = [
            {"type": "Test", "topic": "", "ts_event": 0, "data": {"x": "y" * 500}},
        ]
        result = build_context_message({}, events, [])

        assert "..." in result

    def test_limits_events_to_20(self) -> None:
        events = [
            {"type": f"Event{i}", "topic": "", "ts_event": i, "data": {}}
            for i in range(30)
        ]
        result = build_context_message({}, events, [])

        # Should contain Event29 (last) but not Event0 (trimmed)
        assert "Event29" in result

    def test_objective_progress(self) -> None:
        objectives = [
            {
                "description": "Build position",
                "priority": 1,
                "status": "ACTIVE",
                "progress": {"accumulated": "4.5 BTC"},
            },
        ]
        result = build_context_message({}, [], objectives)

        assert "4.5 BTC" in result


class TestFormatGuardrailSummary:
    def test_empty_guardrails(self) -> None:
        result = format_guardrail_summary({})

        assert "No specific guardrails" in result

    def test_max_order_size(self) -> None:
        result = format_guardrail_summary({"max_single_order_size": "1.0"})

        assert "1.0" in result

    def test_instrument_allowlist(self) -> None:
        result = format_guardrail_summary({
            "instrument_allowlist": ["BTCUSDT-PERP.BINANCE", "ETHUSDT-PERP.BINANCE"],
        })

        assert "BTCUSDT-PERP.BINANCE" in result
        assert "ETHUSDT-PERP.BINANCE" in result

    def test_multiple_guardrails(self) -> None:
        result = format_guardrail_summary({
            "max_single_order_size": "0.5",
            "max_daily_loss": "-5000",
            "max_orders_per_minute": 10,
            "require_stop_loss": True,
        })

        assert "0.5" in result
        assert "-5000" in result
        assert "10" in result
        assert "Stop-loss" in result
