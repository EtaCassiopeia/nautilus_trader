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


RISK_SYSTEM_PROMPT = """\
You are a portfolio risk analyst for a trading system.
Evaluate the current portfolio risk based on position data and account metrics.

Evaluate:
1. **Position Concentration**: How concentrated is the portfolio in single instruments?
2. **Unrealized P&L**: Current unrealized gains/losses and their magnitude
3. **Exposure**: Total long/short exposure relative to account equity
4. **Drawdown Risk**: Current drawdown level and trajectory

Risk assessment guidelines:
- BEARISH signal = high risk, recommend reducing exposure
- NEUTRAL signal = moderate risk, current exposure is acceptable
- BULLISH signal = low risk, room to increase exposure

Respond with ONLY a JSON object (no markdown fences, no explanation):
{
    "signal": "BULLISH" | "BEARISH" | "NEUTRAL",
    "confidence": 0.0 to 1.0,
    "summary": "Brief risk assessment",
    "risk_metrics": {
        "concentration_risk": "high" | "moderate" | "low",
        "pnl_status": "profit" | "loss" | "flat",
        "exposure_level": "overexposed" | "normal" | "underexposed",
        "drawdown_severity": "severe" | "moderate" | "minimal",
        "position_count": <int>,
        "total_exposure_pct": <float or null>
    }
}
"""


class RiskAnalyst(BaseAnalyst):
    """
    Risk analyst that evaluates portfolio risk metrics.

    Queries portfolio and account endpoints via the NautilusClient to
    assess position concentration, unrealized P&L, exposure levels,
    and drawdown risk.

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
        super().__init__(name="risk", client=client, model=model)
        self._nautilus_client = nautilus_client

    async def analyze(self, state: dict, events: list[dict]) -> AnalystReport:
        """
        Evaluate portfolio risk from positions and account data.

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
        portfolio_data = await self._fetch_portfolio_data()

        user_message = (
            "Evaluate the portfolio risk based on the following data.\n\n"
            f"Portfolio Data:\n{json.dumps(portfolio_data, indent=2)}\n\n"
            f"Current State:\n{json.dumps(state, indent=2)}\n\n"
            f"Recent Events ({len(events)} total):\n{json.dumps(events[:10], indent=2)}"
        )

        response_text = await self._call_llm(RISK_SYSTEM_PROMPT, user_message)

        try:
            result = self._parse_llm_json(response_text)
        except (json.JSONDecodeError, KeyError):
            return AnalystReport(
                analyst_name=self._name,
                signal="NEUTRAL",
                confidence=0.0,
                summary=f"Failed to parse risk analysis response: {response_text[:200]}",
                data={"raw_response": response_text},
                model_used=self._model,
            )

        return AnalystReport(
            analyst_name=self._name,
            signal=result.get("signal", "NEUTRAL"),
            confidence=min(max(result.get("confidence", 0.5), 0.0), 1.0),
            summary=result.get("summary", "No summary provided"),
            data=result.get("risk_metrics", {}),
            model_used=self._model,
        )

    async def _fetch_portfolio_data(self) -> dict[str, Any]:
        """
        Fetch positions and account data from the NautilusTrader API.

        Returns
        -------
        dict

        """
        portfolio_data: dict[str, Any] = {}

        try:
            positions = await self._nautilus_client.get("/api/v1/portfolio/positions")
            portfolio_data["positions"] = positions
        except Exception as e:
            portfolio_data["positions_error"] = str(e)

        try:
            accounts = await self._nautilus_client.get("/api/v1/portfolio/accounts")
            portfolio_data["accounts"] = accounts
        except Exception as e:
            portfolio_data["accounts_error"] = str(e)

        return portfolio_data
