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

from nautilus_trader.agent.analysts.base import AnalystReport
from nautilus_trader.agent.debate import DebateFramework
from nautilus_trader.agent.debate import DebatePosition
from nautilus_trader.agent.debate import DebateResult


class TestDebatePosition:
    def test_valid_bull_position(self) -> None:
        position = DebatePosition(
            perspective="BULL",
            argument="Strong uptrend with increasing volume.",
            confidence=0.8,
            key_points=["Volume increasing", "Above 200 MA"],
        )

        assert position.perspective == "BULL"
        assert position.confidence == 0.8
        assert len(position.key_points) == 2

    def test_valid_bear_position(self) -> None:
        position = DebatePosition(
            perspective="BEAR",
            argument="Overbought RSI signals reversal.",
            confidence=0.6,
            key_points=["RSI above 70"],
        )

        assert position.perspective == "BEAR"
        assert position.confidence == 0.6

    def test_default_key_points(self) -> None:
        position = DebatePosition(
            perspective="BULL",
            argument="Test argument.",
            confidence=0.5,
        )

        assert position.key_points == []

    def test_invalid_perspective_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid perspective"):
            DebatePosition(
                perspective="NEUTRAL",
                argument="Test",
                confidence=0.5,
            )

    def test_confidence_below_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="Confidence must be between"):
            DebatePosition(
                perspective="BULL",
                argument="Test",
                confidence=-0.1,
            )

    def test_confidence_above_one_raises(self) -> None:
        with pytest.raises(ValueError, match="Confidence must be between"):
            DebatePosition(
                perspective="BEAR",
                argument="Test",
                confidence=1.1,
            )


class TestDebateResult:
    def _make_result(
        self,
        action: str = "HOLD",
        conviction: float = 0.5,
    ) -> DebateResult:
        return DebateResult(
            bull_case=DebatePosition(
                perspective="BULL",
                argument="Bull arg",
                confidence=0.7,
            ),
            bear_case=DebatePosition(
                perspective="BEAR",
                argument="Bear arg",
                confidence=0.6,
            ),
            synthesis="Balanced view.",
            recommended_action=action,
            conviction=conviction,
            rounds_completed=2,
        )

    def test_valid_buy(self) -> None:
        result = self._make_result(action="BUY", conviction=0.8)

        assert result.recommended_action == "BUY"
        assert result.conviction == 0.8
        assert result.rounds_completed == 2

    def test_valid_sell(self) -> None:
        result = self._make_result(action="SELL", conviction=0.7)

        assert result.recommended_action == "SELL"

    def test_valid_hold(self) -> None:
        result = self._make_result(action="HOLD", conviction=0.3)

        assert result.recommended_action == "HOLD"

    def test_invalid_action_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid recommended_action"):
            self._make_result(action="WAIT")

    def test_conviction_out_of_range_raises(self) -> None:
        with pytest.raises(ValueError, match="Conviction must be between"):
            self._make_result(conviction=1.5)


def _make_mock_llm_response(response_json: dict) -> MagicMock:
    """Create a mock Anthropic API response containing JSON text."""
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = json.dumps(response_json)

    mock_response = MagicMock()
    mock_response.content = [text_block]
    return mock_response


def _make_analyst_reports() -> list[AnalystReport]:
    """Create sample analyst reports for testing."""
    return [
        AnalystReport(
            analyst_name="technical",
            signal="BULLISH",
            confidence=0.75,
            summary="Strong uptrend with volume confirmation.",
            model_used="test-model",
        ),
        AnalystReport(
            analyst_name="sentiment",
            signal="NEUTRAL",
            confidence=0.5,
            summary="Mixed sentiment signals.",
            model_used="test-model",
        ),
    ]


class TestDebateFramework:
    def test_init(self) -> None:
        client = MagicMock()
        framework = DebateFramework(client, model="test-model")

        assert framework._model == "test-model"

    def test_init_default_model(self) -> None:
        client = MagicMock()
        framework = DebateFramework(client)

        assert framework._model == "claude-opus-4-20250514"

    @pytest.mark.asyncio
    async def test_debate_flow(self) -> None:
        """Test the full debate flow with mocked LLM responses."""
        client = MagicMock()

        # Set up sequential responses for:
        # 1. Bull initial case
        # 2. Bear initial case
        # 3-4. Round 1 rebuttals (bull, bear)
        # 5-6. Round 2 rebuttals (bull, bear)
        # 7. Synthesis
        responses = [
            _make_mock_llm_response({
                "argument": "Strong bullish momentum.",
                "confidence": 0.8,
                "key_points": ["Uptrend", "Volume"],
            }),
            _make_mock_llm_response({
                "argument": "Overbought conditions.",
                "confidence": 0.6,
                "key_points": ["RSI high", "Resistance near"],
            }),
            _make_mock_llm_response({
                "argument": "Refined bull case after rebuttal.",
                "confidence": 0.75,
                "key_points": ["Momentum strong", "Fundamentals solid"],
            }),
            _make_mock_llm_response({
                "argument": "Refined bear case after rebuttal.",
                "confidence": 0.65,
                "key_points": ["Risk elevated", "Macro headwinds"],
            }),
            _make_mock_llm_response({
                "argument": "Final bull case.",
                "confidence": 0.7,
                "key_points": ["Long term trend intact"],
            }),
            _make_mock_llm_response({
                "argument": "Final bear case.",
                "confidence": 0.6,
                "key_points": ["Short term correction likely"],
            }),
            _make_mock_llm_response({
                "synthesis": "Bull case stronger on balance.",
                "recommended_action": "BUY",
                "conviction": 0.7,
            }),
        ]

        client.messages.create = AsyncMock(side_effect=responses)

        framework = DebateFramework(client, model="test-model")
        reports = _make_analyst_reports()

        result = await framework.debate(
            analyst_reports=reports,
            state={"portfolio_value": 100000},
            max_rounds=2,
        )

        assert isinstance(result, DebateResult)
        assert result.recommended_action == "BUY"
        assert result.conviction == 0.7
        assert result.rounds_completed == 2
        assert result.bull_case.perspective == "BULL"
        assert result.bear_case.perspective == "BEAR"
        assert result.synthesis == "Bull case stronger on balance."
        assert client.messages.create.call_count == 7

    @pytest.mark.asyncio
    async def test_debate_zero_rounds(self) -> None:
        """Test debate with zero rebuttal rounds."""
        client = MagicMock()

        responses = [
            _make_mock_llm_response({
                "argument": "Bull case.",
                "confidence": 0.7,
                "key_points": ["Point A"],
            }),
            _make_mock_llm_response({
                "argument": "Bear case.",
                "confidence": 0.5,
                "key_points": ["Point B"],
            }),
            _make_mock_llm_response({
                "synthesis": "Hold recommended.",
                "recommended_action": "HOLD",
                "conviction": 0.4,
            }),
        ]

        client.messages.create = AsyncMock(side_effect=responses)

        framework = DebateFramework(client, model="test-model")
        reports = _make_analyst_reports()

        result = await framework.debate(
            analyst_reports=reports,
            state={},
            max_rounds=0,
        )

        assert result.recommended_action == "HOLD"
        assert result.rounds_completed == 0
        assert client.messages.create.call_count == 3

    def test_format_reports(self) -> None:
        client = MagicMock()
        framework = DebateFramework(client)
        reports = _make_analyst_reports()

        text = framework._format_reports(reports)

        assert "technical" in text
        assert "BULLISH" in text
        assert "sentiment" in text
        assert "NEUTRAL" in text

    def test_parse_json_plain(self) -> None:
        client = MagicMock()
        framework = DebateFramework(client)

        result = framework._parse_json('{"key": "value"}')

        assert result == {"key": "value"}

    def test_parse_json_with_code_fences(self) -> None:
        client = MagicMock()
        framework = DebateFramework(client)

        text = '```json\n{"key": "value"}\n```'
        result = framework._parse_json(text)

        assert result == {"key": "value"}
