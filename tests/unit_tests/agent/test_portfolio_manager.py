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

from unittest.mock import AsyncMock
from unittest.mock import MagicMock

import pytest

from nautilus_trader.agent.debate import DebatePosition
from nautilus_trader.agent.debate import DebateResult
from nautilus_trader.agent.portfolio_manager import PortfolioDecision
from nautilus_trader.agent.portfolio_manager import PortfolioManager
from nautilus_trader.agent.risk_team import RiskAssessment
from nautilus_trader.agent.risk_team import RiskVerdict


def _make_debate_result(action: str = "BUY", conviction: float = 0.7) -> DebateResult:
    return DebateResult(
        bull_case=DebatePosition("BULL", "Bull argument", 0.7, ["Strong trend"]),
        bear_case=DebatePosition("BEAR", "Bear argument", 0.5, ["Overbought"]),
        synthesis="Bull case stronger.",
        recommended_action=action,
        conviction=conviction,
        rounds_completed=2,
    )


def _make_risk_verdict(approved: bool = True) -> RiskVerdict:
    assessments = [
        RiskAssessment("AGGRESSIVE", True, "Good trade.", 0.2),
        RiskAssessment("NEUTRAL", approved, "Acceptable." if approved else "Risky.", 0.5),
        RiskAssessment("CONSERVATIVE", False, "Too risky.", 0.8),
    ]
    approvals = sum(1 for a in assessments if a.approved)
    return RiskVerdict(
        assessments=assessments,
        approved=approvals >= 2,
        consensus_score=0.5,
        summary=f"{approvals}/3 approve",
    )


class TestPortfolioDecision:
    def test_with_action(self) -> None:
        debate_result = _make_debate_result()
        risk_verdict = _make_risk_verdict(approved=True)

        decision = PortfolioDecision(
            action={"tool": "submit_order", "params": {"quantity": "0.5"}},
            approved=True,
            reasoning="Executing buy based on debate conviction.",
            risk_verdict=risk_verdict,
            debate_result=debate_result,
        )

        assert decision.approved is True
        assert decision.action is not None
        assert decision.action["tool"] == "submit_order"

    def test_no_action(self) -> None:
        debate_result = _make_debate_result(action="HOLD")
        risk_verdict = _make_risk_verdict(approved=False)

        decision = PortfolioDecision(
            action=None,
            approved=False,
            reasoning="Risk team rejected the action.",
            risk_verdict=risk_verdict,
            debate_result=debate_result,
        )

        assert decision.approved is False
        assert decision.action is None


class TestPortfolioManager:
    def test_init(self) -> None:
        client = MagicMock()
        manager = PortfolioManager(client, model="test-model")

        assert manager._model == "test-model"

    def test_init_default_model(self) -> None:
        client = MagicMock()
        manager = PortfolioManager(client)

        assert manager._model == "claude-opus-4-20250514"

    @pytest.mark.asyncio
    async def test_decide_risk_rejected(self) -> None:
        """When risk team rejects, no LLM call is made and action is None."""
        client = MagicMock()
        client.messages.create = AsyncMock()

        manager = PortfolioManager(client, model="test-model")
        debate_result = _make_debate_result()
        risk_verdict = _make_risk_verdict(approved=False)

        decision = await manager.decide(
            debate_result=debate_result,
            risk_verdict=risk_verdict,
            state={"portfolio_value": 100000},
            objectives=[{"type": "maximize_returns"}],
        )

        assert decision.approved is False
        assert decision.action is None
        assert "rejected by risk team" in decision.reasoning.lower()
        # No LLM call should have been made
        client.messages.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_decide_risk_approved_with_tool_use(self) -> None:
        """When risk approves and LLM returns tool use, action is set."""
        client = MagicMock()

        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Executing buy order based on strong conviction."

        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = "submit_order"
        tool_block.input = {"instrument_id": "BTCUSDT-PERP.BINANCE", "quantity": "0.5"}
        tool_block.id = "toolu_abc123"

        mock_response = MagicMock()
        mock_response.content = [text_block, tool_block]

        client.messages.create = AsyncMock(return_value=mock_response)

        manager = PortfolioManager(client, model="test-model")
        debate_result = _make_debate_result()
        risk_verdict = _make_risk_verdict(approved=True)

        decision = await manager.decide(
            debate_result=debate_result,
            risk_verdict=risk_verdict,
            state={"portfolio_value": 100000},
            objectives=[{"type": "maximize_returns"}],
            tools=[{"name": "submit_order", "description": "Submit an order"}],
        )

        assert decision.approved is True
        assert decision.action is not None
        assert decision.action["tool"] == "submit_order"
        assert decision.action["params"]["quantity"] == "0.5"
        assert decision.action["tool_use_id"] == "toolu_abc123"
        client.messages.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_decide_risk_approved_no_tool_use(self) -> None:
        """When risk approves but LLM returns only text, no action is taken."""
        client = MagicMock()

        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Decided to hold despite approval. Waiting for better entry."

        mock_response = MagicMock()
        mock_response.content = [text_block]

        client.messages.create = AsyncMock(return_value=mock_response)

        manager = PortfolioManager(client, model="test-model")
        debate_result = _make_debate_result(action="HOLD")
        risk_verdict = _make_risk_verdict(approved=True)

        decision = await manager.decide(
            debate_result=debate_result,
            risk_verdict=risk_verdict,
            state={},
            objectives=[],
        )

        assert decision.approved is False
        assert decision.action is None
        assert "hold" in decision.reasoning.lower()

    @pytest.mark.asyncio
    async def test_decide_passes_tools_to_llm(self) -> None:
        """Verify that tools are passed through to the LLM call."""
        client = MagicMock()

        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Holding."

        mock_response = MagicMock()
        mock_response.content = [text_block]

        client.messages.create = AsyncMock(return_value=mock_response)

        manager = PortfolioManager(client, model="test-model")
        debate_result = _make_debate_result()
        risk_verdict = _make_risk_verdict(approved=True)

        tools = [
            {"name": "submit_order", "description": "Submit order"},
            {"name": "cancel_order", "description": "Cancel order"},
        ]

        await manager.decide(
            debate_result=debate_result,
            risk_verdict=risk_verdict,
            state={},
            objectives=[],
            tools=tools,
        )

        call_kwargs = client.messages.create.call_args[1]
        assert "tools" in call_kwargs
        assert len(call_kwargs["tools"]) == 2
