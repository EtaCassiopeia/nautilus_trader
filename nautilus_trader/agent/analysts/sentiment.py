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
from typing import Any

from nautilus_trader.agent.analysts.base import AnalystReport
from nautilus_trader.agent.analysts.base import BaseAnalyst


SENTIMENT_SYSTEM_PROMPT = """\
You are a market sentiment analyst for a trading system.
Analyze the provided events for sentiment signals about market conditions.

Evaluate:
1. **Order Flow**: Pattern of fills (aggressive buying/selling), order sizes
2. **Position Changes**: Direction and magnitude of position changes
3. **Market Moves**: Size and speed of price movements in recent events
4. **Event Patterns**: Frequency and clustering of events (e.g. rapid fills may indicate momentum)

In production this would also incorporate external news feeds and social sentiment.
For now, derive sentiment purely from the trading system's own event stream.

Respond with ONLY a JSON object (no markdown fences, no explanation):
{
    "signal": "BULLISH" | "BEARISH" | "NEUTRAL",
    "confidence": 0.0 to 1.0,
    "summary": "Brief explanation of the sentiment reading",
    "sentiment_factors": {
        "order_flow": "buying" | "selling" | "balanced",
        "position_bias": "long" | "short" | "flat",
        "event_intensity": "high" | "moderate" | "low",
        "momentum_signal": "positive" | "negative" | "neutral"
    }
}
"""


class SentimentAnalyst(BaseAnalyst):
    """
    Sentiment analyst that evaluates market sentiment from event data.

    Analyzes order fills, position changes, and market moves from the
    event stream to gauge overall market sentiment. In production, this
    would also incorporate external news and social sentiment APIs.

    Parameters
    ----------
    client : Any
        An initialized Anthropic AsyncAnthropic client.
    model : str
        The model to use for LLM calls.

    """

    def __init__(
        self,
        client: Any,
        model: str = "claude-haiku-4-20250414",
    ) -> None:
        super().__init__(name="sentiment", client=client, model=model)

    async def analyze(self, state: dict, events: list[dict]) -> AnalystReport:
        """
        Analyze events for sentiment signals.

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
        event_summary = self._summarize_events(events)

        user_message = (
            "Analyze the following trading events for market sentiment signals.\n\n"
            f"Event Summary:\n{json.dumps(event_summary, indent=2)}\n\n"
            f"Current State:\n{json.dumps(state, indent=2)}\n\n"
            f"Raw Events (most recent {min(len(events), 30)}):\n"
            f"{json.dumps(events[:30], indent=2)}"
        )

        response_text = await self._call_llm(SENTIMENT_SYSTEM_PROMPT, user_message)

        try:
            result = self._parse_llm_json(response_text)
        except (json.JSONDecodeError, KeyError):
            return AnalystReport(
                analyst_name=self._name,
                signal="NEUTRAL",
                confidence=0.0,
                summary=f"Failed to parse sentiment response: {response_text[:200]}",
                data={"raw_response": response_text},
                model_used=self._model,
            )

        return AnalystReport(
            analyst_name=self._name,
            signal=result.get("signal", "NEUTRAL"),
            confidence=min(max(result.get("confidence", 0.5), 0.0), 1.0),
            summary=result.get("summary", "No summary provided"),
            data=result.get("sentiment_factors", {}),
            model_used=self._model,
        )

    def _summarize_events(self, events: list[dict]) -> dict[str, Any]:
        """
        Produce a structured summary of events for the LLM.

        Parameters
        ----------
        events : list[dict]
            The raw event list.

        Returns
        -------
        dict

        """
        summary: dict[str, Any] = {
            "total_events": len(events),
            "event_types": {},
            "fills": [],
            "position_changes": [],
        }

        for event in events:
            event_type = event.get("type", "unknown")
            summary["event_types"][event_type] = (
                summary["event_types"].get(event_type, 0) + 1
            )

            if "fill" in event_type.lower() or "order" in event_type.lower():
                summary["fills"].append(event)
            if "position" in event_type.lower():
                summary["position_changes"].append(event)

        # Limit list sizes for the LLM context
        summary["fills"] = summary["fills"][:20]
        summary["position_changes"] = summary["position_changes"][:20]

        return summary
