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
from abc import ABC
from abc import abstractmethod
from dataclasses import dataclass
from dataclasses import field
from typing import Any

VALID_SIGNALS = {"BULLISH", "BEARISH", "NEUTRAL"}


@dataclass
class AnalystReport:
    """
    Report produced by an analyst agent.

    Parameters
    ----------
    analyst_name : str
        The name of the analyst (e.g. "technical", "sentiment").
    signal : str
        The directional signal: "BULLISH", "BEARISH", or "NEUTRAL".
    confidence : float
        Confidence level from 0.0 to 1.0.
    summary : str
        Human-readable analysis summary.
    data : dict
        Structured data backing the analysis.
    model_used : str
        Which LLM model generated this report.

    """

    analyst_name: str
    signal: str
    confidence: float
    summary: str
    data: dict = field(default_factory=dict)
    model_used: str = ""

    def __post_init__(self) -> None:
        if self.signal not in VALID_SIGNALS:
            raise ValueError(
                f"Invalid signal '{self.signal}', must be one of {VALID_SIGNALS}",
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"Confidence must be between 0.0 and 1.0, got {self.confidence}",
            )


class BaseAnalyst(ABC):
    """
    Base class for all analyst agents.

    Each analyst specializes in a domain (technical, sentiment, risk, etc.)
    and produces an AnalystReport with a signal and confidence level.

    Parameters
    ----------
    name : str
        The analyst name identifier.
    client : Any
        An initialized Anthropic AsyncAnthropic client.
    model : str
        The model to use for LLM calls (e.g. "claude-haiku-4-20250414").

    """

    def __init__(self, name: str, client: Any, model: str) -> None:
        self._name = name
        self._client = client
        self._model = model

    @property
    def name(self) -> str:
        """Return the analyst name."""
        return self._name

    @property
    def model(self) -> str:
        """Return the model identifier."""
        return self._model

    @abstractmethod
    async def analyze(self, state: dict, events: list[dict]) -> AnalystReport:
        """
        Analyze the current state and events to produce a report.

        Parameters
        ----------
        state : dict
            Current agent state snapshot.
        events : list[dict]
            Recent event batch.

        Returns
        -------
        AnalystReport

        """

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
            The text response from the LLM.

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

    def _parse_llm_json(self, text: str) -> dict:
        """
        Extract and parse JSON from an LLM response.

        Handles responses that may contain markdown code fences
        around the JSON content.

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
            # Strip markdown code fences
            lines = cleaned.split("\n")
            lines = lines[1:]  # Remove opening fence
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]  # Remove closing fence
            cleaned = "\n".join(lines)
        return json.loads(cleaned)
