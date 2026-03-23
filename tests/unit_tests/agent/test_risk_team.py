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
from unittest.mock import AsyncMock
from unittest.mock import MagicMock

import pytest

from nautilus_trader.agent.debate import DebatePosition
from nautilus_trader.agent.debate import DebateResult
from nautilus_trader.agent.risk_team import RiskAssessment
from nautilus_trader.agent.risk_team import RiskTeam
from nautilus_trader.agent.risk_team import RiskVerdict


class TestRiskAssessment:
    def test_valid_aggressive(self) -> None:
        assessment = RiskAssessment(
            perspective="AGGRESSIVE",
            approved=True,
            reasoning="Acceptable risk/reward ratio.",
            risk_score=0.3,
            concerns=["Moderate volatility"],
        )

        assert assessment.perspective == "AGGRESSIVE"
        assert assessment.approved is True
        assert assessment.risk_score == 0.3

    def test_valid_neutral(self) -> None:
        assessment = RiskAssessment(
            perspective="NEUTRAL",
            approved=True,
            reasoning="Balanced assessment.",
            risk_score=0.5,
        )

        assert assessment.perspective == "NEUTRAL"
        assert assessment.concerns == []

    def test_valid_conservative(self) -> None:
        assessment = RiskAssessment(
            perspective="CONSERVATIVE",
            approved=False,
            reasoning="Too much risk.",
            risk_score=0.8,
            concerns=["High drawdown risk", "Low liquidity"],
        )

        assert assessment.approved is False
        assert len(assessment.concerns) == 2

    def test_invalid_perspective_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid perspective"):
            RiskAssessment(
                perspective="MODERATE",
                approved=True,
                reasoning="Test",
                risk_score=0.5,
            )

    def test_risk_score_below_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="Risk score must be between"):
            RiskAssessment(
                perspective="NEUTRAL",
                approved=True,
                reasoning="Test",
                risk_score=-0.1,
            )

    def test_risk_score_above_one_raises(self) -> None:
        with pytest.raises(ValueError, match="Risk score must be between"):
            RiskAssessment(
                perspective="NEUTRAL",
                approved=True,
                reasoning="Test",
                risk_score=1.1,
            )


class TestRiskVerdict:
    def test_approved_verdict(self) -> None:
        assessments = [
            RiskAssessment("AGGRESSIVE", True, "OK", 0.2),
            RiskAssessment("NEUTRAL", True, "OK", 0.4),
            RiskAssessment("CONSERVATIVE", False, "Too risky", 0.7),
        ]

        verdict = RiskVerdict(
            assessments=assessments,
            approved=True,
            consensus_score=0.433,
            summary="2/3 approve",
        )

        assert verdict.approved is True
        assert len(verdict.assessments) == 3

    def test_rejected_verdict(self) -> None:
        assessments = [
            RiskAssessment("AGGRESSIVE", True, "OK", 0.3),
            RiskAssessment("NEUTRAL", False, "Risky", 0.6),
            RiskAssessment("CONSERVATIVE", False, "Too risky", 0.9),
        ]

        verdict = RiskVerdict(
            assessments=assessments,
            approved=False,
            consensus_score=0.6,
            summary="1/3 approve",
        )

        assert verdict.approved is False


def _make_debate_result() -> DebateResult:
    """Create a sample debate result for testing."""
    return DebateResult(
        bull_case=DebatePosition("BULL", "Bull argument", 0.7, ["Point A"]),
        bear_case=DebatePosition("BEAR", "Bear argument", 0.5, ["Point B"]),
        synthesis="Moderate bullish bias.",
        recommended_action="BUY",
        conviction=0.65,
        rounds_completed=2,
    )


def _make_mock_llm_response(response_json: dict) -> MagicMock:
    """Create a mock Anthropic API response containing JSON text."""
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = json.dumps(response_json)

    mock_response = MagicMock()
    mock_response.content = [text_block]
    return mock_response


class TestRiskTeam:
    def test_init(self) -> None:
        client = MagicMock()
        team = RiskTeam(client, model="test-model")

        assert team._model == "test-model"

    def test_init_default_model(self) -> None:
        client = MagicMock()
        team = RiskTeam(client)

        assert team._model == "claude-sonnet-4-20250514"

    @pytest.mark.asyncio
    async def test_evaluate_all_approve(self) -> None:
        """Test evaluation where all three perspectives approve."""
        client = MagicMock()

        responses = [
            _make_mock_llm_response({
                "approved": True,
                "reasoning": "Good risk/reward.",
                "risk_score": 0.2,
                "concerns": [],
            }),
            _make_mock_llm_response({
                "approved": True,
                "reasoning": "Acceptable risk.",
                "risk_score": 0.4,
                "concerns": ["Minor volatility"],
            }),
            _make_mock_llm_response({
                "approved": True,
                "reasoning": "Within limits.",
                "risk_score": 0.5,
                "concerns": ["Position size large"],
            }),
        ]

        client.messages.create = AsyncMock(side_effect=responses)

        team = RiskTeam(client, model="test-model")
        debate_result = _make_debate_result()

        verdict = await team.evaluate(
            proposed_action={"tool": "submit_order", "params": {"quantity": "1.0"}},
            debate_result=debate_result,
            state={"portfolio_value": 100000},
        )

        assert verdict.approved is True
        assert len(verdict.assessments) == 3
        assert client.messages.create.call_count == 3

    @pytest.mark.asyncio
    async def test_evaluate_two_approve_consensus(self) -> None:
        """Test 2/3 approval consensus rule."""
        client = MagicMock()

        responses = [
            _make_mock_llm_response({
                "approved": True,
                "reasoning": "Aggressive approves.",
                "risk_score": 0.3,
                "concerns": [],
            }),
            _make_mock_llm_response({
                "approved": True,
                "reasoning": "Neutral approves.",
                "risk_score": 0.5,
                "concerns": [],
            }),
            _make_mock_llm_response({
                "approved": False,
                "reasoning": "Conservative rejects.",
                "risk_score": 0.8,
                "concerns": ["High risk", "Uncertain macro"],
            }),
        ]

        client.messages.create = AsyncMock(side_effect=responses)

        team = RiskTeam(client, model="test-model")
        debate_result = _make_debate_result()

        verdict = await team.evaluate(
            proposed_action={"tool": "submit_order", "params": {}},
            debate_result=debate_result,
            state={},
        )

        assert verdict.approved is True
        assert "APPROVED" in verdict.summary

    @pytest.mark.asyncio
    async def test_evaluate_two_reject(self) -> None:
        """Test 1/3 approval results in rejection."""
        client = MagicMock()

        responses = [
            _make_mock_llm_response({
                "approved": True,
                "reasoning": "Aggressive approves.",
                "risk_score": 0.3,
                "concerns": [],
            }),
            _make_mock_llm_response({
                "approved": False,
                "reasoning": "Neutral rejects.",
                "risk_score": 0.7,
                "concerns": ["Poor timing"],
            }),
            _make_mock_llm_response({
                "approved": False,
                "reasoning": "Conservative rejects.",
                "risk_score": 0.9,
                "concerns": ["Extreme risk"],
            }),
        ]

        client.messages.create = AsyncMock(side_effect=responses)

        team = RiskTeam(client, model="test-model")
        debate_result = _make_debate_result()

        verdict = await team.evaluate(
            proposed_action={"tool": "submit_order", "params": {}},
            debate_result=debate_result,
            state={},
        )

        assert verdict.approved is False
        assert "REJECTED" in verdict.summary

    @pytest.mark.asyncio
    async def test_evaluate_consensus_score(self) -> None:
        """Test that consensus score is the average of individual risk scores."""
        client = MagicMock()

        responses = [
            _make_mock_llm_response({
                "approved": True,
                "reasoning": "OK",
                "risk_score": 0.3,
                "concerns": [],
            }),
            _make_mock_llm_response({
                "approved": True,
                "reasoning": "OK",
                "risk_score": 0.6,
                "concerns": [],
            }),
            _make_mock_llm_response({
                "approved": False,
                "reasoning": "No",
                "risk_score": 0.9,
                "concerns": [],
            }),
        ]

        client.messages.create = AsyncMock(side_effect=responses)

        team = RiskTeam(client, model="test-model")
        debate_result = _make_debate_result()

        verdict = await team.evaluate(
            proposed_action={},
            debate_result=debate_result,
            state={},
        )

        assert verdict.consensus_score == pytest.approx(0.6, abs=0.01)
