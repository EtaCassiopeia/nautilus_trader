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

from nautilus_trader.agent.analysts.base import AnalystReport
from nautilus_trader.agent.config import EnhancedAgentConfig
from nautilus_trader.agent.config import ModelConfig
from nautilus_trader.agent.debate import DebatePosition
from nautilus_trader.agent.debate import DebateResult
from nautilus_trader.agent.enhanced_orchestrator import EnhancedOrchestrator
from nautilus_trader.agent.modes import AgentMode
from nautilus_trader.agent.portfolio_manager import PortfolioDecision
from nautilus_trader.agent.risk_team import RiskAssessment
from nautilus_trader.agent.risk_team import RiskVerdict


class TestEnhancedOrchestrator:
    def _make_orchestrator(self, **kwargs) -> EnhancedOrchestrator:
        config = EnhancedAgentConfig(**kwargs)
        return EnhancedOrchestrator(config)

    def test_init(self) -> None:
        orch = self._make_orchestrator()

        assert orch.is_running is False
        assert orch.mode == AgentMode.MONITOR
        assert orch.cycle_count == 0

    def test_add_event(self) -> None:
        orch = self._make_orchestrator()

        orch.add_event({"type": "OrderFilled"})

        assert len(orch._event_buffer) == 1

    def test_add_objective(self) -> None:
        orch = self._make_orchestrator()

        orch.add_objective({"objective_id": "o1", "priority": 1, "description": "test"})

        assert len(orch._objectives) == 1

    def test_record_decision_bounds_list(self) -> None:
        orch = self._make_orchestrator()

        bull = DebatePosition(perspective="BULL", argument="x", confidence=0.7, key_points=[])
        bear = DebatePosition(perspective="BEAR", argument="y", confidence=0.3, key_points=[])
        debate = DebateResult(
            bull_case=bull, bear_case=bear,
            synthesis="test", recommended_action="HOLD",
            conviction=0.5, rounds_completed=1,
        )
        decision = PortfolioDecision(
            action=None, approved=False, reasoning="test",
            risk_verdict=None, debate_result=debate,
        )

        for _ in range(250):
            orch._record_decision(decision)

        assert len(orch._decisions) == 200

    @pytest.mark.asyncio
    async def test_run_cycle_not_running(self) -> None:
        orch = self._make_orchestrator()
        orch._running = False

        result = await orch.run_cycle()

        assert result is None

    @pytest.mark.asyncio
    async def test_run_cycle_with_kill_switch(self) -> None:
        orch = self._make_orchestrator(mode="AUTONOMOUS")
        orch._running = True
        orch._guardrails.kill_switch.trigger("test")

        # Mock the client
        orch._client = MagicMock()
        orch._client.get = AsyncMock(return_value={"data": {}})

        result = await orch.run_cycle()

        assert result is None

    @pytest.mark.asyncio
    async def test_run_cycle_hold_decision(self) -> None:
        orch = self._make_orchestrator(mode="AUTONOMOUS", enable_debate=True)
        orch._running = True

        # Mock client
        orch._client = MagicMock()
        orch._client.get = AsyncMock(return_value={"data": {}})

        # Mock analyst team
        mock_report = AnalystReport(
            analyst_name="technical",
            signal="NEUTRAL",
            confidence=0.5,
            summary="Mixed signals",
            data={},
            model_used="test",
        )
        orch._analyst_team = MagicMock()
        orch._analyst_team.analyze = AsyncMock(return_value=[mock_report])

        # Mock debate returning HOLD
        bull = DebatePosition(perspective="BULL", argument="x", confidence=0.4, key_points=[])
        bear = DebatePosition(perspective="BEAR", argument="y", confidence=0.6, key_points=[])
        orch._debate = MagicMock()
        orch._debate.debate = AsyncMock(return_value=DebateResult(
            bull_case=bull, bear_case=bear,
            synthesis="No clear direction",
            recommended_action="HOLD",
            conviction=0.3, rounds_completed=2,
        ))

        result = await orch.run_cycle()

        assert result is not None
        assert result.approved is False
        assert orch.cycle_count == 1

    @pytest.mark.asyncio
    async def test_run_cycle_risk_rejection(self) -> None:
        orch = self._make_orchestrator(mode="AUTONOMOUS", enable_debate=True, enable_risk_team=True)
        orch._running = True

        # Mock client
        orch._client = MagicMock()
        orch._client.get = AsyncMock(return_value={"data": {}})

        # Mock analyst team
        mock_report = AnalystReport(
            analyst_name="technical", signal="BULLISH",
            confidence=0.8, summary="Strong uptrend",
            data={}, model_used="test",
        )
        orch._analyst_team = MagicMock()
        orch._analyst_team.analyze = AsyncMock(return_value=[mock_report])

        # Mock debate returning BUY
        bull = DebatePosition(perspective="BULL", argument="x", confidence=0.8, key_points=[])
        bear = DebatePosition(perspective="BEAR", argument="y", confidence=0.2, key_points=[])
        orch._debate = MagicMock()
        orch._debate.debate = AsyncMock(return_value=DebateResult(
            bull_case=bull, bear_case=bear,
            synthesis="Buy signal", recommended_action="BUY",
            conviction=0.8, rounds_completed=2,
        ))

        # Mock risk team rejecting
        orch._risk_team = MagicMock()
        orch._risk_team.evaluate = AsyncMock(return_value=RiskVerdict(
            assessments=[
                RiskAssessment(perspective="AGGRESSIVE", approved=True, reasoning="OK", risk_score=0.3, concerns=[]),
                RiskAssessment(perspective="NEUTRAL", approved=False, reasoning="Too risky", risk_score=0.7, concerns=["high exposure"]),
                RiskAssessment(perspective="CONSERVATIVE", approved=False, reasoning="No", risk_score=0.9, concerns=["market volatility"]),
            ],
            approved=False,
            consensus_score=0.63,
            summary="Risk team rejected: 1/3 approved, need 2/3",
        ))

        result = await orch.run_cycle()

        assert result is not None
        assert result.approved is False
        assert "Risk team rejected" in result.reasoning
