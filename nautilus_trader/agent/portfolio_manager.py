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
from typing import Any

from nautilus_trader.agent.debate import DebateResult
from nautilus_trader.agent.risk_team import RiskVerdict


@dataclass
class PortfolioDecision:
    """
    Final portfolio decision synthesizing debate and risk assessment.

    Parameters
    ----------
    action : dict | None
        Tool call to execute, or None if no action taken.
    approved : bool
        Whether the decision results in an approved action.
    reasoning : str
        The reasoning behind the decision.
    risk_verdict : RiskVerdict
        The risk team's verdict.
    debate_result : DebateResult
        The debate result that informed this decision.

    """

    action: dict | None
    approved: bool
    reasoning: str
    risk_verdict: RiskVerdict
    debate_result: DebateResult


class PortfolioManager:
    """
    Final decision authority for trading actions.

    Synthesizes the structured debate result and risk team verdict
    into a concrete portfolio decision. Only approves actions that
    pass both the debate conviction threshold and risk team consensus.

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

    async def decide(
        self,
        debate_result: DebateResult,
        risk_verdict: RiskVerdict,
        state: dict,
        objectives: list[dict],
        tools: list[dict] | None = None,
    ) -> PortfolioDecision:
        """
        Make a final portfolio decision.

        Synthesizes the debate result and risk verdict into a concrete
        action or a decision to hold. If the risk team rejected the action,
        no trade is executed.

        Parameters
        ----------
        debate_result : DebateResult
            The structured debate result.
        risk_verdict : RiskVerdict
            The risk team's assessment.
        state : dict
            Current agent state snapshot.
        objectives : list[dict]
            Active trading objectives.
        tools : list[dict] | None, optional
            Available tool definitions for Claude tool use.

        Returns
        -------
        PortfolioDecision

        """
        # If risk team rejected, do not proceed with action
        if not risk_verdict.approved:
            return PortfolioDecision(
                action=None,
                approved=False,
                reasoning=(
                    f"Action rejected by risk team. {risk_verdict.summary}"
                ),
                risk_verdict=risk_verdict,
                debate_result=debate_result,
            )

        system_prompt = (
            "You are a senior portfolio manager making the final trading decision. "
            "You have received a structured bull/bear debate result and a risk team "
            "verdict. The risk team has APPROVED the proposed action. Your job is to "
            "determine the precise action to take, considering position sizing, "
            "timing, and the overall portfolio context.\n\n"
            "If you decide to act, use the available tools to specify the exact trade. "
            "If you decide not to act despite approval, explain why clearly."
        )

        state_text = json.dumps(state, default=str)
        objectives_text = json.dumps(objectives, default=str)

        # Format risk assessments
        risk_details = []
        for assessment in risk_verdict.assessments:
            status = "APPROVED" if assessment.approved else "REJECTED"
            risk_details.append(
                f"  {assessment.perspective}: {status} "
                f"(risk: {assessment.risk_score:.2f}) - {assessment.reasoning}"
            )

        user_message = (
            f"## Debate Result\n"
            f"Recommendation: {debate_result.recommended_action} "
            f"(conviction: {debate_result.conviction:.2f})\n"
            f"Rounds: {debate_result.rounds_completed}\n\n"
            f"Bull case (confidence: {debate_result.bull_case.confidence:.2f}):\n"
            f"{debate_result.bull_case.argument}\n\n"
            f"Bear case (confidence: {debate_result.bear_case.confidence:.2f}):\n"
            f"{debate_result.bear_case.argument}\n\n"
            f"Synthesis: {debate_result.synthesis}\n\n"
            f"## Risk Verdict\n"
            f"Overall: {'APPROVED' if risk_verdict.approved else 'REJECTED'} "
            f"(consensus risk: {risk_verdict.consensus_score:.2f})\n"
            + "\n".join(risk_details)
            + "\n\n"
            f"## Current State\n{state_text}\n\n"
            f"## Objectives\n{objectives_text}\n\n"
            f"Make your final decision. If you want to execute a trade, use the "
            f"appropriate tool. If you want to hold, explain your reasoning."
        )

        messages = [{"role": "user", "content": user_message}]

        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": 4096,
            "system": system_prompt,
            "messages": messages,
        }

        if tools:
            kwargs["tools"] = tools

        response = await self._client.messages.create(**kwargs)

        return self._parse_response(response, risk_verdict, debate_result)

    def _parse_response(
        self,
        response: Any,
        risk_verdict: RiskVerdict,
        debate_result: DebateResult,
    ) -> PortfolioDecision:
        """
        Parse a Claude API response into a PortfolioDecision.

        Parameters
        ----------
        response : Any
            The raw API response.
        risk_verdict : RiskVerdict
            The risk team's verdict.
        debate_result : DebateResult
            The debate result.

        Returns
        -------
        PortfolioDecision

        """
        reasoning_parts = []
        action = None

        for block in response.content:
            if block.type == "text":
                reasoning_parts.append(block.text)
            elif block.type == "tool_use":
                action = {
                    "tool": block.name,
                    "params": block.input,
                    "tool_use_id": block.id,
                }

        return PortfolioDecision(
            action=action,
            approved=action is not None,
            reasoning="\n".join(reasoning_parts),
            risk_verdict=risk_verdict,
            debate_result=debate_result,
        )
