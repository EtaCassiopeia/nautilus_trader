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
import json
from dataclasses import dataclass
from dataclasses import field
from typing import Any

from nautilus_trader.agent.debate import DebateResult


VALID_PERSPECTIVES = {"AGGRESSIVE", "NEUTRAL", "CONSERVATIVE"}


@dataclass
class RiskAssessment:
    """
    A risk assessment from a single perspective.

    Parameters
    ----------
    perspective : str
        The risk perspective: "AGGRESSIVE", "NEUTRAL", or "CONSERVATIVE".
    approved : bool
        Whether the action is approved from this perspective.
    reasoning : str
        The reasoning behind the assessment.
    risk_score : float
        Risk score from 0.0 (no risk) to 1.0 (maximum risk).
    concerns : list[str]
        Specific risk concerns identified.

    """

    perspective: str
    approved: bool
    reasoning: str
    risk_score: float
    concerns: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.perspective not in VALID_PERSPECTIVES:
            raise ValueError(
                f"Invalid perspective '{self.perspective}', "
                f"must be one of {VALID_PERSPECTIVES}",
            )
        if not 0.0 <= self.risk_score <= 1.0:
            raise ValueError(
                f"Risk score must be between 0.0 and 1.0, got {self.risk_score}",
            )


@dataclass
class RiskVerdict:
    """
    Combined risk verdict from all perspectives.

    Parameters
    ----------
    assessments : list[RiskAssessment]
        Individual risk assessments.
    approved : bool
        True if consensus approves (at least 2 of 3).
    consensus_score : float
        Average risk score across assessments.
    summary : str
        Summary of the risk verdict.

    """

    assessments: list[RiskAssessment]
    approved: bool
    consensus_score: float
    summary: str


class RiskTeam:
    """
    Three-perspective risk assessment team.

    Evaluates proposed actions from aggressive, neutral, and conservative
    viewpoints. The action is approved if at least 2 of 3 perspectives approve.

    Parameters
    ----------
    client : Any
        An initialized Anthropic AsyncAnthropic client.
    model : str, optional
        The model to use for LLM calls.

    """

    def __init__(self, client: Any, model: str = "claude-sonnet-4-20250514") -> None:
        self._client = client
        self._model = model

    async def evaluate(
        self,
        proposed_action: dict,
        debate_result: DebateResult,
        state: dict,
    ) -> RiskVerdict:
        """
        Run risk assessments from all three perspectives in parallel.

        The action is approved if at least 2 of 3 perspectives approve
        (consensus rule).

        Parameters
        ----------
        proposed_action : dict
            The proposed trading action to evaluate.
        debate_result : DebateResult
            The debate result informing this action.
        state : dict
            Current agent state snapshot.

        Returns
        -------
        RiskVerdict

        """
        assessments = await asyncio.gather(
            self._assess("AGGRESSIVE", proposed_action, debate_result, state),
            self._assess("NEUTRAL", proposed_action, debate_result, state),
            self._assess("CONSERVATIVE", proposed_action, debate_result, state),
        )

        approvals = sum(1 for a in assessments if a.approved)
        approved = approvals >= 2
        consensus_score = sum(a.risk_score for a in assessments) / len(assessments)

        all_concerns = []
        for assessment in assessments:
            all_concerns.extend(assessment.concerns)

        summary_parts = []
        for assessment in assessments:
            status = "APPROVED" if assessment.approved else "REJECTED"
            summary_parts.append(
                f"{assessment.perspective}: {status} "
                f"(risk: {assessment.risk_score:.2f})"
            )

        verdict_str = "APPROVED" if approved else "REJECTED"
        summary = (
            f"Risk verdict: {verdict_str} ({approvals}/3 approve, "
            f"avg risk: {consensus_score:.2f})\n"
            + "\n".join(summary_parts)
        )

        return RiskVerdict(
            assessments=list(assessments),
            approved=approved,
            consensus_score=consensus_score,
            summary=summary,
        )

    async def _assess(
        self,
        perspective: str,
        proposed_action: dict,
        debate_result: DebateResult,
        state: dict,
    ) -> RiskAssessment:
        """
        Assess risk from a single perspective.

        Parameters
        ----------
        perspective : str
            "AGGRESSIVE", "NEUTRAL", or "CONSERVATIVE".
        proposed_action : dict
            The proposed trading action.
        debate_result : DebateResult
            The debate result informing this action.
        state : dict
            Current agent state snapshot.

        Returns
        -------
        RiskAssessment

        """
        perspective_descriptions = {
            "AGGRESSIVE": (
                "You are an aggressive risk manager who favors taking calculated "
                "risks for higher returns. You approve trades that have reasonable "
                "upside potential even with moderate risk. You only reject trades "
                "with extreme downside risk or poor risk/reward ratios."
            ),
            "NEUTRAL": (
                "You are a balanced risk manager who weighs risk and reward equally. "
                "You approve trades with favorable risk/reward ratios and reject "
                "those where risks outweigh potential gains. You seek a balanced approach."
            ),
            "CONSERVATIVE": (
                "You are a conservative risk manager focused on capital preservation. "
                "You are skeptical of trades and only approve those with strong "
                "evidence, limited downside, and clear risk management. You reject "
                "trades with significant uncertainty or potential for large losses."
            ),
        }

        system_prompt = (
            f"{perspective_descriptions[perspective]}\n\n"
            f"Evaluate the proposed trading action and provide your risk assessment."
        )

        action_text = json.dumps(proposed_action, default=str)
        state_text = json.dumps(state, default=str)

        user_message = (
            f"## Proposed Action\n{action_text}\n\n"
            f"## Debate Summary\n"
            f"Recommended: {debate_result.recommended_action} "
            f"(conviction: {debate_result.conviction:.2f})\n"
            f"Bull confidence: {debate_result.bull_case.confidence:.2f}\n"
            f"Bear confidence: {debate_result.bear_case.confidence:.2f}\n"
            f"Synthesis: {debate_result.synthesis}\n\n"
            f"## Current State\n{state_text}\n\n"
            f"Assess the risk from a {perspective} perspective. "
            f"Respond in JSON format:\n"
            f'{{"approved": true/false, '
            f'"reasoning": "your assessment", '
            f'"risk_score": 0.0-1.0, '
            f'"concerns": ["concern 1", "concern 2", ...]}}'
        )

        response_text = await self._call_llm(system_prompt, user_message)
        parsed = self._parse_json(response_text)

        return RiskAssessment(
            perspective=perspective,
            approved=bool(parsed.get("approved", False)),
            reasoning=parsed.get("reasoning", ""),
            risk_score=max(0.0, min(1.0, float(parsed.get("risk_score", 0.5)))),
            concerns=parsed.get("concerns", []),
        )

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
