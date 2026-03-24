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
from nautilus_trader.agent.analysts.team import AnalystTeam


class StubAnalyst(BaseAnalyst):
    """Stub analyst that returns a preconfigured report."""

    def __init__(self, name: str, signal: str, confidence: float) -> None:
        super().__init__(name=name, client=None, model="test-model")
        self._signal = signal
        self._confidence = confidence

    async def analyze(self, state: dict, events: list[dict]) -> AnalystReport:
        return AnalystReport(
            analyst_name=self._name,
            signal=self._signal,
            confidence=self._confidence,
            summary=f"{self._name} says {self._signal}",
            data={},
            model_used=self._model,
        )


class TestAnalystTeam:
    def test_init_with_analysts(self) -> None:
        analysts = [
            StubAnalyst("a1", "BULLISH", 0.8),
            StubAnalyst("a2", "BEARISH", 0.6),
        ]
        team = AnalystTeam(analysts)

        assert len(team.analysts) == 2

    @pytest.mark.asyncio
    async def test_analyze_runs_all_analysts(self) -> None:
        analysts = [
            StubAnalyst("tech", "BULLISH", 0.8),
            StubAnalyst("sent", "BEARISH", 0.6),
            StubAnalyst("risk", "NEUTRAL", 0.5),
        ]
        team = AnalystTeam(analysts)

        reports = await team.analyze(state={}, events=[])

        assert len(reports) == 3
        assert reports[0].analyst_name == "tech"
        assert reports[0].signal == "BULLISH"
        assert reports[1].analyst_name == "sent"
        assert reports[1].signal == "BEARISH"
        assert reports[2].analyst_name == "risk"
        assert reports[2].signal == "NEUTRAL"

    @pytest.mark.asyncio
    async def test_analyze_empty_team(self) -> None:
        team = AnalystTeam([])

        reports = await team.analyze(state={}, events=[])

        assert reports == []

    def test_format_reports_with_data(self) -> None:
        reports = [
            AnalystReport(
                analyst_name="technical",
                signal="BULLISH",
                confidence=0.85,
                summary="Strong uptrend",
                model_used="claude-haiku-4-20250414",
            ),
            AnalystReport(
                analyst_name="sentiment",
                signal="BEARISH",
                confidence=0.6,
                summary="Negative flow",
                model_used="claude-haiku-4-20250414",
            ),
        ]
        team = AnalystTeam([])

        result = team.format_reports(reports)

        assert "# Analyst Team Report" in result
        assert "TECHNICAL Analyst" in result
        assert "SENTIMENT Analyst" in result
        assert "BULLISH" in result
        assert "BEARISH" in result
        assert "85%" in result
        assert "Consensus:" in result

    def test_format_reports_empty(self) -> None:
        team = AnalystTeam([])

        result = team.format_reports([])

        assert result == "No analyst reports available."

    def test_consensus_bullish_dominant(self) -> None:
        reports = [
            AnalystReport(
                analyst_name="a1",
                signal="BULLISH",
                confidence=0.9,
                summary="Bull",
                model_used="test",
            ),
            AnalystReport(
                analyst_name="a2",
                signal="BULLISH",
                confidence=0.7,
                summary="Bull",
                model_used="test",
            ),
            AnalystReport(
                analyst_name="a3",
                signal="BEARISH",
                confidence=0.3,
                summary="Bear",
                model_used="test",
            ),
        ]
        team = AnalystTeam([])

        consensus = team._compute_consensus(reports)

        assert "BULLISH" in consensus

    def test_consensus_no_reports(self) -> None:
        team = AnalystTeam([])

        consensus = team._compute_consensus([])

        assert consensus == "NO DATA"

    def test_consensus_zero_confidence(self) -> None:
        reports = [
            AnalystReport(
                analyst_name="a1",
                signal="NEUTRAL",
                confidence=0.0,
                summary="No data",
                model_used="test",
            ),
        ]
        team = AnalystTeam([])

        consensus = team._compute_consensus(reports)

        assert "no confidence" in consensus
