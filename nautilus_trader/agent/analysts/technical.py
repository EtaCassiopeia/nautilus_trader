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
from nautilus_trader.mcp.client import NautilusClient


TECHNICAL_SYSTEM_PROMPT = """\
You are a technical analysis expert for financial markets.
Analyze the provided market data including price action, EMAs, RSI, MACD, and volume.

Evaluate:
1. **Trend**: EMA crossovers (fast vs slow), price relative to EMAs
2. **Momentum**: RSI levels (overbought >70, oversold <30), MACD histogram direction
3. **Volume**: Volume trends relative to price movement, volume confirmation
4. **Price Action**: Recent bar patterns, support/resistance levels, range analysis

Respond with ONLY a JSON object (no markdown fences, no explanation):
{
    "signal": "BULLISH" | "BEARISH" | "NEUTRAL",
    "confidence": 0.0 to 1.0,
    "summary": "Brief explanation of the technical setup",
    "indicators": {
        "trend": "up" | "down" | "sideways",
        "rsi": <value or null>,
        "macd_histogram": "positive" | "negative" | "neutral",
        "volume_trend": "increasing" | "decreasing" | "stable",
        "ema_alignment": "bullish" | "bearish" | "mixed"
    }
}
"""


class TechnicalAnalyst(BaseAnalyst):
    """
    Technical analyst that evaluates price action and indicators.

    Queries the NautilusTrader REST API for bars and quotes via the
    NautilusClient, then uses an LLM to interpret the technical picture.

    Parameters
    ----------
    client : Any
        An initialized Anthropic AsyncAnthropic client.
    nautilus_client : NautilusClient
        Client for querying the NautilusTrader REST API.
    model : str
        The model to use for LLM calls.

    """

    def __init__(
        self,
        client: Any,
        nautilus_client: NautilusClient,
        model: str = "claude-haiku-4-20250414",
    ) -> None:
        super().__init__(name="technical", client=client, model=model)
        self._nautilus_client = nautilus_client

    async def analyze(self, state: dict, events: list[dict]) -> AnalystReport:
        """
        Analyze market data using technical indicators.

        Parameters
        ----------
        state : dict
            Current agent state snapshot. Expected to contain
            'instrument_ids' with a list of instrument identifiers.
        events : list[dict]
            Recent event batch.

        Returns
        -------
        AnalystReport

        """
        market_data = await self._fetch_market_data(state)

        user_message = (
            "Analyze the following market data and provide your technical assessment.\n\n"
            f"Market Data:\n{json.dumps(market_data, indent=2)}\n\n"
            f"Recent Events ({len(events)} total):\n{json.dumps(events[:20], indent=2)}"
        )

        response_text = await self._call_llm(TECHNICAL_SYSTEM_PROMPT, user_message)

        try:
            result = self._parse_llm_json(response_text)
        except (json.JSONDecodeError, KeyError):
            return AnalystReport(
                analyst_name=self._name,
                signal="NEUTRAL",
                confidence=0.0,
                summary=f"Failed to parse technical analysis response: {response_text[:200]}",
                data={"raw_response": response_text},
                model_used=self._model,
            )

        return AnalystReport(
            analyst_name=self._name,
            signal=result.get("signal", "NEUTRAL"),
            confidence=min(max(result.get("confidence", 0.5), 0.0), 1.0),
            summary=result.get("summary", "No summary provided"),
            data=result.get("indicators", {}),
            model_used=self._model,
        )

    async def _fetch_market_data(self, state: dict) -> dict:
        """
        Fetch bars and quotes from the NautilusTrader API.

        Parameters
        ----------
        state : dict
            Agent state containing instrument identifiers.

        Returns
        -------
        dict

        """
        market_data: dict[str, Any] = {}
        instrument_ids = state.get("instrument_ids", [])

        for instrument_id in instrument_ids[:5]:  # Limit to 5 instruments
            try:
                bars = await self._nautilus_client.get(
                    "/api/v1/data/bars",
                    params={"instrument_id": instrument_id, "limit": 50},
                )
                market_data[instrument_id] = {"bars": bars}
            except Exception as e:
                market_data[instrument_id] = {"error": str(e)}

            try:
                quotes = await self._nautilus_client.get(
                    "/api/v1/data/quotes",
                    params={"instrument_id": instrument_id, "limit": 10},
                )
                if instrument_id in market_data:
                    market_data[instrument_id]["quotes"] = quotes
            except Exception:
                pass  # Quotes are supplementary

        return market_data
