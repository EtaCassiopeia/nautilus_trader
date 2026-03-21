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

import os
from dataclasses import dataclass
from dataclasses import field
from typing import Any

from nautilus_trader.agent.config import AgentConfig
from nautilus_trader.agent.prompts import build_context_message
from nautilus_trader.agent.prompts import build_system_prompt
from nautilus_trader.agent.prompts import format_guardrail_summary


@dataclass
class ReasoningResult:
    """
    Result from the reasoning engine.

    Parameters
    ----------
    reasoning : str
        The agent's reasoning text.
    action : dict | None
        Tool call to execute, or None if no action.
    raw_response : dict
        The full API response.

    """

    reasoning: str
    action: dict | None = None
    raw_response: dict = field(default_factory=dict)


class ReasoningEngine:
    """
    Interfaces with Claude for agent decision-making.

    Manages the conversation with Claude, builds context prompts,
    and parses tool-use responses into actionable results.

    Parameters
    ----------
    config : AgentConfig
        The agent configuration.

    """

    def __init__(self, config: AgentConfig) -> None:
        self._config = config
        self._model = config.model
        self._api_key = config.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._system_prompt: str | None = None
        self._client: Any = None

    async def start(self) -> None:
        """Initialize the Anthropic client."""
        try:
            import anthropic
            self._client = anthropic.AsyncAnthropic(api_key=self._api_key)
        except ImportError:
            raise RuntimeError(
                "The 'anthropic' package is required for the reasoning engine. "
                "Install it with: pip install anthropic"
            )

    async def stop(self) -> None:
        """Clean up the client."""
        if self._client is not None:
            await self._client.close()
            self._client = None

    def set_system_prompt(
        self,
        guardrail_summary: str,
        tool_descriptions: str,
    ) -> None:
        """
        Build and set the system prompt.

        Parameters
        ----------
        guardrail_summary : str
            Summary of active guardrails.
        tool_descriptions : str
            Available tool descriptions.

        """
        self._system_prompt = build_system_prompt(
            mode=self._config.mode,
            guardrail_summary=guardrail_summary,
            tool_descriptions=tool_descriptions,
        )

    async def reason(
        self,
        state: dict,
        events: list[dict],
        objectives: list[dict],
        recent_decisions: list[dict] | None = None,
        tools: list[dict] | None = None,
    ) -> ReasoningResult:
        """
        Send context to Claude and get a reasoning result.

        Parameters
        ----------
        state : dict
            Current agent state snapshot.
        events : list[dict]
            Recent event batch.
        objectives : list[dict]
            Active objectives.
        recent_decisions : list[dict], optional
            Recent decision history.
        tools : list[dict], optional
            Tool definitions for Claude tool use.

        Returns
        -------
        ReasoningResult

        """
        if self._client is None:
            raise RuntimeError("Reasoning engine not started. Call start() first.")

        context_msg = build_context_message(
            state=state,
            events=events,
            objectives=objectives,
            recent_decisions=recent_decisions,
        )

        messages = [{"role": "user", "content": context_msg}]

        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": 4096,
            "messages": messages,
        }

        if self._system_prompt:
            kwargs["system"] = self._system_prompt

        if tools:
            kwargs["tools"] = tools

        response = await self._client.messages.create(**kwargs)

        return self._parse_response(response)

    def _parse_response(self, response: Any) -> ReasoningResult:
        """Parse a Claude API response into a ReasoningResult."""
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

        return ReasoningResult(
            reasoning="\n".join(reasoning_parts),
            action=action,
            raw_response={
                "id": response.id,
                "model": response.model,
                "stop_reason": response.stop_reason,
                "usage": {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                },
            },
        )
