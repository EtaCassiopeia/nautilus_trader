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

import asyncio

from nautilus_trader.agent.analysts.base import AnalystReport
from nautilus_trader.agent.analysts.base import BaseAnalyst


class AnalystTeam:
    """
    Runs a team of analyst agents in parallel and aggregates their reports.

    Parameters
    ----------
    analysts : list[BaseAnalyst]
        The analyst agents to run.

    """

    def __init__(self, analysts: list[BaseAnalyst]) -> None:
        self._analysts = list(analysts)

    @property
    def analysts(self) -> list[BaseAnalyst]:
        """Return the list of analysts."""
        return list(self._analysts)

    async def analyze(self, state: dict, events: list[dict]) -> list[AnalystReport]:
        """
        Run all analysts in parallel and return their reports.

        Parameters
        ----------
        state : dict
            Current agent state snapshot.
        events : list[dict]
            Recent event batch.

        Returns
        -------
        list[AnalystReport]

        """
        return await asyncio.gather(
            *(a.analyze(state, events) for a in self._analysts),
        )

    def format_reports(self, reports: list[AnalystReport]) -> str:
        """
        Format all analyst reports into a single context string.

        Parameters
        ----------
        reports : list[AnalystReport]
            The reports to format.

        Returns
        -------
        str

        """
        if not reports:
            return "No analyst reports available."

        sections = []
        for report in reports:
            section = (
                f"## {report.analyst_name.upper()} Analyst\n"
                f"Signal: {report.signal} (confidence: {report.confidence:.0%})\n"
                f"Summary: {report.summary}\n"
                f"Model: {report.model_used}"
            )
            sections.append(section)

        consensus = self._compute_consensus(reports)
        header = f"# Analyst Team Report\nConsensus: {consensus}\n"

        return header + "\n" + "\n\n".join(sections)

    def _compute_consensus(self, reports: list[AnalystReport]) -> str:
        """
        Compute a weighted consensus signal from analyst reports.

        Parameters
        ----------
        reports : list[AnalystReport]
            The analyst reports.

        Returns
        -------
        str
            The consensus signal description.

        """
        if not reports:
            return "NO DATA"

        signal_scores = {"BULLISH": 0.0, "BEARISH": 0.0, "NEUTRAL": 0.0}
        total_confidence = 0.0

        for report in reports:
            signal_scores[report.signal] += report.confidence
            total_confidence += report.confidence

        if total_confidence == 0.0:
            return "NEUTRAL (no confidence)"

        dominant_signal = max(signal_scores, key=signal_scores.get)  # type: ignore[arg-type]
        dominant_weight = signal_scores[dominant_signal] / total_confidence

        return f"{dominant_signal} ({dominant_weight:.0%} weight)"
