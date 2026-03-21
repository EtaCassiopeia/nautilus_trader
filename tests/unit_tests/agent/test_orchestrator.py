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

from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from nautilus_trader.agent.config import AgentConfig
from nautilus_trader.agent.config import GuardrailConfig
from nautilus_trader.agent.modes import AgentMode
from nautilus_trader.agent.orchestrator import AgentOrchestrator
from nautilus_trader.agent.reasoning import ReasoningResult


class TestAgentOrchestrator:
    def _make_orchestrator(self, **kwargs) -> AgentOrchestrator:
        config = AgentConfig(**kwargs)
        return AgentOrchestrator(config)

    def test_init(self) -> None:
        orch = self._make_orchestrator()

        assert orch.is_running is False
        assert orch.mode == AgentMode.MONITOR

    def test_add_event(self) -> None:
        orch = self._make_orchestrator()

        orch.add_event({"type": "OrderFilled", "data": {}})
        orch.add_event({"type": "PositionChanged", "data": {}})

        assert len(orch._event_buffer) == 2

    def test_add_event_trims_buffer(self) -> None:
        orch = self._make_orchestrator(max_context_events=3)

        for i in range(5):
            orch.add_event({"type": f"Event{i}"})

        assert len(orch._event_buffer) == 3
        assert orch._event_buffer[0]["type"] == "Event2"

    def test_add_objective(self) -> None:
        orch = self._make_orchestrator()

        orch.add_objective({
            "objective_id": "obj-1",
            "description": "Build position",
            "priority": 1,
        })

        assert len(orch._objectives) == 1

    def test_add_objectives_sorted_by_priority(self) -> None:
        orch = self._make_orchestrator()

        orch.add_objective({"objective_id": "low", "description": "Low", "priority": 3})
        orch.add_objective({"objective_id": "high", "description": "High", "priority": 1})

        assert orch._objectives[0]["objective_id"] == "high"

    def test_remove_objective(self) -> None:
        orch = self._make_orchestrator()
        orch.add_objective({"objective_id": "obj-1", "description": "Test"})

        orch.remove_objective("obj-1")

        assert len(orch._objectives) == 0

    def test_record_decision_bounds_list(self) -> None:
        orch = self._make_orchestrator()

        for i in range(150):
            orch._record_decision(
                ReasoningResult(reasoning=f"Decision {i}"),
                outcome={"status": "no_action"},
            )

        assert len(orch._decisions) == 100

    def test_tool_descriptions_monitor_no_mutations(self) -> None:
        orch = self._make_orchestrator(mode="MONITOR")

        descriptions = orch._get_tool_descriptions()

        assert "nautilus_node_status" in descriptions
        assert "nautilus_submit_order" not in descriptions

    def test_tool_descriptions_autonomous_has_mutations(self) -> None:
        orch = self._make_orchestrator(mode="AUTONOMOUS")

        descriptions = orch._get_tool_descriptions()

        assert "nautilus_submit_order" in descriptions
        assert "nautilus_cancel_order" in descriptions

    @pytest.mark.asyncio
    async def test_run_cycle_no_action(self) -> None:
        orch = self._make_orchestrator(mode="MONITOR")
        orch._running = True

        # Mock client and reasoning
        orch._client = MagicMock()
        orch._client.get = AsyncMock(return_value={"data": {}})

        orch._reasoning = MagicMock()
        orch._reasoning.reason = AsyncMock(
            return_value=ReasoningResult(reasoning="Nothing to do"),
        )

        result = await orch.run_cycle()

        assert result is not None
        assert result.action is None
        assert len(orch._decisions) == 1
        assert orch._decisions[0]["outcome"]["status"] == "no_action"

    @pytest.mark.asyncio
    async def test_run_cycle_blocked_by_guardrails(self) -> None:
        orch = self._make_orchestrator(mode="MONITOR")
        orch._running = True

        orch._client = MagicMock()
        orch._client.get = AsyncMock(return_value={"data": {}})

        orch._reasoning = MagicMock()
        orch._reasoning.reason = AsyncMock(
            return_value=ReasoningResult(
                reasoning="Should submit order",
                action={"tool": "nautilus_submit_order", "params": {"quantity": "1.0"}},
            ),
        )

        result = await orch.run_cycle()

        assert result is not None
        assert len(orch._decisions) == 1
        assert orch._decisions[0]["outcome"]["status"] == "blocked"

    @pytest.mark.asyncio
    async def test_run_cycle_not_running(self) -> None:
        orch = self._make_orchestrator()
        orch._running = False

        result = await orch.run_cycle()

        assert result is None

    @pytest.mark.asyncio
    async def test_dispatch_get(self) -> None:
        orch = self._make_orchestrator()
        orch._client = MagicMock()
        orch._client.get = AsyncMock(return_value={"status": "ok"})

        result = await orch._dispatch_tool(
            "nautilus_node_status",
            {},
        )

        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_dispatch_post(self) -> None:
        orch = self._make_orchestrator()
        orch._client = MagicMock()
        orch._client.post = AsyncMock(return_value={"status": "ok"})

        result = await orch._dispatch_tool(
            "nautilus_submit_order",
            {"instrument_id": "BTCUSDT", "quantity": "0.5"},
        )

        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_dispatch_unknown_tool_raises(self) -> None:
        orch = self._make_orchestrator()

        with pytest.raises(ValueError, match="Unknown tool"):
            await orch._dispatch_tool("unknown_tool", {})
