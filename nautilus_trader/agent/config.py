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

from dataclasses import dataclass
from dataclasses import field
from typing import Literal


@dataclass(frozen=True)
class GuardrailConfig:
    """
    Hard safety limits for the AI agent.

    These are enforced programmatically and cannot be overridden
    by the agent's reasoning.

    Parameters
    ----------
    max_position_size : dict[str, str]
        Maximum position size per instrument (decimal strings).
    max_portfolio_exposure : str, optional
        Maximum total portfolio exposure.
    max_daily_loss : str, optional
        Daily loss limit. Triggers kill switch when breached.
    max_orders_per_minute : int
        Maximum order submission rate.
    max_single_order_size : str, optional
        Maximum quantity for a single order.
    instrument_allowlist : list[str], optional
        Only trade these instruments. None allows all.
    instrument_blocklist : list[str]
        Never trade these instruments.
    require_stop_loss : bool
        Whether all positions require stop-loss orders.
    human_approval_threshold : str, optional
        Order notional value above which human approval is required.
    kill_switch_conditions : list[str]
        Conditions that trigger automatic kill switch.

    """

    max_position_size: dict[str, str] = field(default_factory=dict)
    max_portfolio_exposure: str | None = None
    max_daily_loss: str | None = None
    max_orders_per_minute: int = 10
    max_single_order_size: str | None = None
    instrument_allowlist: list[str] | None = None
    instrument_blocklist: list[str] = field(default_factory=list)
    require_stop_loss: bool = False
    human_approval_threshold: str | None = None
    kill_switch_conditions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AgentConfig:
    """
    Configuration for the AI agent orchestrator.

    Parameters
    ----------
    mode : str
        Operating mode: MONITOR, ADVISORY, SEMI_AUTONOMOUS, AUTONOMOUS.
    api_url : str
        NautilusTrader API URL.
    api_key : str, optional
        API key for authentication.
    ws_url : str, optional
        WebSocket URL for event streaming. Derived from api_url if not set.
    model : str
        Claude model to use for reasoning.
    anthropic_api_key : str, optional
        Anthropic API key. Falls back to ANTHROPIC_API_KEY env var.
    event_batch_interval_secs : float
        Time to accumulate events before processing.
    event_topics : list[str]
        Event topics to subscribe to.
    max_context_events : int
        Maximum events in the sliding context window.
    decision_log_path : str, optional
        Path to write decision audit log.
    guardrails : GuardrailConfig
        Safety guardrail configuration.

    """

    mode: Literal["MONITOR", "ADVISORY", "SEMI_AUTONOMOUS", "AUTONOMOUS"] = "MONITOR"
    api_url: str = "http://localhost:8001"
    api_key: str | None = None
    ws_url: str | None = None
    model: str = "claude-sonnet-4-20250514"
    anthropic_api_key: str | None = None
    event_batch_interval_secs: float = 1.0
    event_topics: list[str] = field(default_factory=lambda: ["events.*"])
    max_context_events: int = 50
    decision_log_path: str | None = None
    guardrails: GuardrailConfig = field(default_factory=GuardrailConfig)

    @property
    def effective_ws_url(self) -> str:
        """Return the WebSocket URL, deriving from api_url if not set."""
        if self.ws_url:
            return self.ws_url
        # Convert http(s) to ws(s)
        url = self.api_url.rstrip("/")
        if url.startswith("https://"):
            return url.replace("https://", "wss://", 1) + "/ws/events"
        return url.replace("http://", "ws://", 1) + "/ws/events"
