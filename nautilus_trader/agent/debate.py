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
from dataclasses import dataclass
from dataclasses import field
from typing import Any

from nautilus_trader.agent.analysts.base import AnalystReport


@dataclass
class DebatePosition:
    """
    A position taken in a bull/bear debate.

    Parameters
    ----------
    perspective : str
        The debate perspective: "BULL" or "BEAR".
    argument : str
        The reasoning behind the position.
    confidence : float
        Confidence level from 0.0 to 1.0.
    key_points : list[str]
        Supporting bullet points.

    """

    perspective: str
    argument: str
    confidence: float
    key_points: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.perspective not in ("BULL", "BEAR"):
            raise ValueError(
                f"Invalid perspective '{self.perspective}', must be 'BULL' or 'BEAR'",
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"Confidence must be between 0.0 and 1.0, got {self.confidence}",
            )


@dataclass
class DebateResult:
    """
    Result from a structured bull/bear debate.

    Parameters
    ----------
    bull_case : DebatePosition
        The bull (optimistic) position.
    bear_case : DebatePosition
        The bear (pessimistic) position.
    synthesis : str
        Synthesized conclusion from the debate.
    recommended_action : str
        Recommended action: "BUY", "SELL", or "HOLD".
    conviction : float
        Overall conviction level from 0.0 to 1.0.
    rounds_completed : int
        Number of debate rounds completed.

    """

    bull_case: DebatePosition
    bear_case: DebatePosition
    synthesis: str
    recommended_action: str
    conviction: float
    rounds_completed: int

    def __post_init__(self) -> None:
        if self.recommended_action not in ("BUY", "SELL", "HOLD"):
            raise ValueError(
                f"Invalid recommended_action '{self.recommended_action}', "
                "must be 'BUY', 'SELL', or 'HOLD'",
            )
        if not 0.0 <= self.conviction <= 1.0:
            raise ValueError(
                f"Conviction must be between 0.0 and 1.0, got {self.conviction}",
            )


class DebateFramework:
    """
    Structured bull/bear debate for trading decisions.

    Runs a multi-round debate between bull and bear perspectives,
    then synthesizes the arguments into a final recommendation.

    Parameters
    ----------
    client : Any
        An initialized Anthropic AsyncAnthropic client.
    model : str, optional
        The model to use for LLM calls.

    """

    def __init__(self, client: Any, model: str = "claude-opus-4-20250514") -> None:
        self._client = client
        self._model = model

    async def debate(
        self,
        analyst_reports: list[AnalystReport],
        state: dict,
        max_rounds: int = 2,
    ) -> DebateResult:
        """
        Run a structured bull/bear debate.

        Generates initial bull and bear cases from analyst reports,
        then each side rebuts the other for the specified number of rounds,
        and finally synthesizes into a recommendation.

        Parameters
        ----------
        analyst_reports : list[AnalystReport]
            Reports from analyst agents to inform the debate.
        state : dict
            Current agent state snapshot.
        max_rounds : int, optional
            Number of rebuttal rounds (default 2).

        Returns
        -------
        DebateResult

        """
        # Generate initial cases
        bull_case = await self._generate_case("BULL", analyst_reports, state)
        bear_case = await self._generate_case("BEAR", analyst_reports, state)

        # Run rebuttal rounds
        for _ in range(max_rounds):
            bull_case = await self._rebut(bull_case, bear_case, "BULL")
            bear_case = await self._rebut(bear_case, bull_case, "BEAR")

        # Synthesize final recommendation
        synthesis, recommended_action, conviction = await self._synthesize(
            bull_case,
            bear_case,
            analyst_reports,
        )

        return DebateResult(
            bull_case=bull_case,
            bear_case=bear_case,
            synthesis=synthesis,
            recommended_action=recommended_action,
            conviction=conviction,
            rounds_completed=max_rounds,
        )

    async def _generate_case(
        self,
        perspective: str,
        analyst_reports: list[AnalystReport],
        state: dict,
    ) -> DebatePosition:
        """
        Generate an initial bull or bear case from analyst reports.

        Parameters
        ----------
        perspective : str
            "BULL" or "BEAR".
        analyst_reports : list[AnalystReport]
            Reports from analyst agents.
        state : dict
            Current agent state snapshot.

        Returns
        -------
        DebatePosition

        """
        reports_text = self._format_reports(analyst_reports)
        state_text = json.dumps(state, default=str)

        label = "bullish (optimistic)" if perspective == "BULL" else "bearish (pessimistic)"

        system_prompt = (
            f"You are an expert {label} financial analyst. "
            f"Your role is to make the strongest possible {perspective} case "
            f"based on the available data. Be specific and cite evidence from "
            f"the analyst reports and market state."
        )

        user_message = (
            f"Based on the following analyst reports and market state, "
            f"make the strongest {perspective} case.\n\n"
            f"## Analyst Reports\n{reports_text}\n\n"
            f"## Market State\n{state_text}\n\n"
            f"Respond in JSON format:\n"
            f'{{"argument": "your detailed argument", '
            f'"confidence": 0.0-1.0, '
            f'"key_points": ["point 1", "point 2", ...]}}'
        )

        response_text = await self._call_llm(system_prompt, user_message)
        parsed = self._parse_json(response_text)

        return DebatePosition(
            perspective=perspective,
            argument=parsed.get("argument", ""),
            confidence=max(0.0, min(1.0, float(parsed.get("confidence", 0.5)))),
            key_points=parsed.get("key_points", []),
        )

    async def _rebut(
        self,
        own_case: DebatePosition,
        opponent_case: DebatePosition,
        perspective: str,
    ) -> DebatePosition:
        """
        Rebut the opponent's case and strengthen own position.

        Parameters
        ----------
        own_case : DebatePosition
            The current position to refine.
        opponent_case : DebatePosition
            The opponent's position to rebut.
        perspective : str
            "BULL" or "BEAR".

        Returns
        -------
        DebatePosition

        """
        label = "bullish" if perspective == "BULL" else "bearish"

        system_prompt = (
            f"You are an expert {label} financial analyst engaged in a debate. "
            f"Review the opponent's argument and strengthen your own position. "
            f"Address their strongest points while reinforcing your case."
        )

        user_message = (
            f"## Your Previous Argument ({perspective})\n"
            f"{own_case.argument}\n\n"
            f"## Opponent's Argument ({opponent_case.perspective})\n"
            f"{opponent_case.argument}\n\n"
            f"## Opponent's Key Points\n"
            + "\n".join(f"- {p}" for p in opponent_case.key_points)
            + "\n\n"
            f"Rebut the opponent and strengthen your {perspective} case. "
            f"Respond in JSON format:\n"
            f'{{"argument": "your refined argument", '
            f'"confidence": 0.0-1.0, '
            f'"key_points": ["point 1", "point 2", ...]}}'
        )

        response_text = await self._call_llm(system_prompt, user_message)
        parsed = self._parse_json(response_text)

        return DebatePosition(
            perspective=perspective,
            argument=parsed.get("argument", ""),
            confidence=max(0.0, min(1.0, float(parsed.get("confidence", 0.5)))),
            key_points=parsed.get("key_points", []),
        )

    async def _synthesize(
        self,
        bull: DebatePosition,
        bear: DebatePosition,
        analyst_reports: list[AnalystReport],
    ) -> tuple[str, str, float]:
        """
        Synthesize the debate into a final recommendation.

        Parameters
        ----------
        bull : DebatePosition
            The final bull case.
        bear : DebatePosition
            The final bear case.
        analyst_reports : list[AnalystReport]
            Original analyst reports for reference.

        Returns
        -------
        tuple[str, str, float]
            A tuple of (synthesis text, recommended action, conviction).

        """
        reports_text = self._format_reports(analyst_reports)

        system_prompt = (
            "You are an impartial portfolio strategist. You have observed a "
            "structured debate between bull and bear analysts. Synthesize their "
            "arguments into a balanced conclusion and recommend an action. "
            "Consider the strength of each side's evidence and reasoning."
        )

        user_message = (
            f"## Bull Case (confidence: {bull.confidence:.2f})\n"
            f"{bull.argument}\n\n"
            f"Key points:\n"
            + "\n".join(f"- {p}" for p in bull.key_points)
            + "\n\n"
            f"## Bear Case (confidence: {bear.confidence:.2f})\n"
            f"{bear.argument}\n\n"
            f"Key points:\n"
            + "\n".join(f"- {p}" for p in bear.key_points)
            + "\n\n"
            f"## Original Analyst Reports\n{reports_text}\n\n"
            f"Synthesize the debate and recommend an action. "
            f"Respond in JSON format:\n"
            f'{{"synthesis": "your balanced conclusion", '
            f'"recommended_action": "BUY" or "SELL" or "HOLD", '
            f'"conviction": 0.0-1.0}}'
        )

        response_text = await self._call_llm(system_prompt, user_message)
        parsed = self._parse_json(response_text)

        synthesis = parsed.get("synthesis", "")
        action = parsed.get("recommended_action", "HOLD")
        if action not in ("BUY", "SELL", "HOLD"):
            action = "HOLD"
        conviction = max(0.0, min(1.0, float(parsed.get("conviction", 0.5))))

        return synthesis, action, conviction

    async def _call_llm(self, system_prompt: str, user_message: str) -> str:
        """
        Call the Anthropic API with the given prompts.

        Parameters
        ----------
        system_prompt : str
            The system prompt for the LLM.
        user_message : str
            The user message content.

        Returns
        -------
        str

        """
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=2048,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )

        text_parts = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)

        return "\n".join(text_parts)

    def _format_reports(self, analyst_reports: list[AnalystReport]) -> str:
        """Format analyst reports into a readable text block."""
        parts = []
        for report in analyst_reports:
            parts.append(
                f"### {report.analyst_name}\n"
                f"Signal: {report.signal} (confidence: {report.confidence:.2f})\n"
                f"{report.summary}"
            )
        return "\n\n".join(parts)

    def _parse_json(self, text: str) -> dict:
        """
        Extract and parse JSON from an LLM response.

        Handles responses that may contain markdown code fences.

        Parameters
        ----------
        text : str
            The raw LLM response text.

        Returns
        -------
        dict

        """
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = lines[1:]  # Remove opening fence
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]  # Remove closing fence
            cleaned = "\n".join(lines)
        return json.loads(cleaned)
