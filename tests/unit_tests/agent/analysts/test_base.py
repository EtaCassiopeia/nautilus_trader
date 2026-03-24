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

import pytest

from nautilus_trader.agent.analysts.base import AnalystReport
from nautilus_trader.agent.analysts.base import BaseAnalyst


class TestAnalystReport:
    def test_valid_bullish_report(self) -> None:
        report = AnalystReport(
            analyst_name="technical",
            signal="BULLISH",
            confidence=0.85,
            summary="Strong uptrend with EMA crossover",
            data={"trend": "up"},
            model_used="claude-haiku-4-20250414",
        )

        assert report.analyst_name == "technical"
        assert report.signal == "BULLISH"
        assert report.confidence == 0.85
        assert report.data == {"trend": "up"}

    def test_valid_bearish_report(self) -> None:
        report = AnalystReport(
            analyst_name="sentiment",
            signal="BEARISH",
            confidence=0.6,
            summary="Negative order flow detected",
        )

        assert report.signal == "BEARISH"
        assert report.data == {}

    def test_valid_neutral_report(self) -> None:
        report = AnalystReport(
            analyst_name="risk",
            signal="NEUTRAL",
            confidence=0.5,
            summary="Balanced exposure",
        )

        assert report.signal == "NEUTRAL"

    def test_invalid_signal_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid signal"):
            AnalystReport(
                analyst_name="test",
                signal="SIDEWAYS",
                confidence=0.5,
                summary="Test",
            )

    def test_confidence_below_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="Confidence must be between"):
            AnalystReport(
                analyst_name="test",
                signal="NEUTRAL",
                confidence=-0.1,
                summary="Test",
            )

    def test_confidence_above_one_raises(self) -> None:
        with pytest.raises(ValueError, match="Confidence must be between"):
            AnalystReport(
                analyst_name="test",
                signal="NEUTRAL",
                confidence=1.1,
                summary="Test",
            )

    def test_confidence_boundary_zero(self) -> None:
        report = AnalystReport(
            analyst_name="test",
            signal="NEUTRAL",
            confidence=0.0,
            summary="Test",
        )

        assert report.confidence == 0.0

    def test_confidence_boundary_one(self) -> None:
        report = AnalystReport(
            analyst_name="test",
            signal="BULLISH",
            confidence=1.0,
            summary="Test",
        )

        assert report.confidence == 1.0


class TestBaseAnalyst:
    def test_cannot_instantiate_directly(self) -> None:
        with pytest.raises(TypeError):
            BaseAnalyst(name="test", client=None, model="test-model")  # type: ignore[abstract]

    def test_parse_llm_json_plain(self) -> None:
        class ConcreteAnalyst(BaseAnalyst):
            async def analyze(self, state: dict, events: list[dict]) -> AnalystReport:
                raise NotImplementedError

        analyst = ConcreteAnalyst(name="test", client=None, model="test-model")
        result = analyst._parse_llm_json('{"signal": "BULLISH", "confidence": 0.8}')

        assert result["signal"] == "BULLISH"
        assert result["confidence"] == 0.8

    def test_parse_llm_json_with_code_fences(self) -> None:
        class ConcreteAnalyst(BaseAnalyst):
            async def analyze(self, state: dict, events: list[dict]) -> AnalystReport:
                raise NotImplementedError

        analyst = ConcreteAnalyst(name="test", client=None, model="test-model")
        text = '```json\n{"signal": "BEARISH", "confidence": 0.6}\n```'
        result = analyst._parse_llm_json(text)

        assert result["signal"] == "BEARISH"
        assert result["confidence"] == 0.6
