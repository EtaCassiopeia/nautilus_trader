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

from enum import Enum
from enum import unique


@unique
class AgentMode(Enum):
    """
    Operating modes for the AI agent with increasing levels of autonomy.

    ``MONITOR``
        Observe-only mode. The agent processes events and can query state,
        but cannot submit any mutations. Suitable for monitoring and alerting.

    ``ADVISORY``
        The agent processes events, queries state, and can suggest actions,
        but all mutations require human approval. Suitable for human-in-the-loop
        trading.

    ``SEMI_AUTONOMOUS``
        The agent auto-executes low-risk mutations (queries, small orders
        within limits, strategy start/stop) but escalates high-risk actions
        (large orders, market exits, cancel-all, risk limit changes) to the
        operator for approval.

    ``AUTONOMOUS``
        The agent executes all actions within guardrail limits without human
        approval. Suitable for fully automated AI-directed trading.
    """

    MONITOR = "MONITOR"
    ADVISORY = "ADVISORY"
    SEMI_AUTONOMOUS = "SEMI_AUTONOMOUS"
    AUTONOMOUS = "AUTONOMOUS"


@unique
class ActionRisk(Enum):
    """Risk classification for agent actions."""

    QUERY = "QUERY"
    LOW = "LOW"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# Permission matrix: (mode, action_risk) -> allowed, needs_approval
_PERMISSION_MATRIX: dict[tuple[AgentMode, ActionRisk], tuple[bool, bool]] = {
    # MONITOR: queries only
    (AgentMode.MONITOR, ActionRisk.QUERY): (True, False),
    (AgentMode.MONITOR, ActionRisk.LOW): (False, False),
    (AgentMode.MONITOR, ActionRisk.HIGH): (False, False),
    (AgentMode.MONITOR, ActionRisk.CRITICAL): (False, False),
    # ADVISORY: queries + suggestions (mutations returned as suggestions, not executed)
    (AgentMode.ADVISORY, ActionRisk.QUERY): (True, False),
    (AgentMode.ADVISORY, ActionRisk.LOW): (True, True),
    (AgentMode.ADVISORY, ActionRisk.HIGH): (True, True),
    (AgentMode.ADVISORY, ActionRisk.CRITICAL): (True, True),
    # SEMI_AUTONOMOUS: auto-execute low-risk, escalate high-risk
    (AgentMode.SEMI_AUTONOMOUS, ActionRisk.QUERY): (True, False),
    (AgentMode.SEMI_AUTONOMOUS, ActionRisk.LOW): (True, False),
    (AgentMode.SEMI_AUTONOMOUS, ActionRisk.HIGH): (True, True),
    (AgentMode.SEMI_AUTONOMOUS, ActionRisk.CRITICAL): (True, True),
    # AUTONOMOUS: auto-execute everything within guardrails
    (AgentMode.AUTONOMOUS, ActionRisk.QUERY): (True, False),
    (AgentMode.AUTONOMOUS, ActionRisk.LOW): (True, False),
    (AgentMode.AUTONOMOUS, ActionRisk.HIGH): (True, False),
    (AgentMode.AUTONOMOUS, ActionRisk.CRITICAL): (True, False),
}


def check_permission(mode: AgentMode, risk: ActionRisk) -> tuple[bool, bool]:
    """
    Check if an action is permitted and whether it needs approval.

    Parameters
    ----------
    mode : AgentMode
        The current agent operating mode.
    risk : ActionRisk
        The risk level of the action.

    Returns
    -------
    tuple[bool, bool]
        (is_allowed, needs_approval). If is_allowed is False, the action
        is blocked regardless of approval. If needs_approval is True,
        the action requires human confirmation before execution.

    """
    return _PERMISSION_MATRIX.get((mode, risk), (False, False))


# Action classification for common operations
ACTION_CLASSIFICATIONS: dict[str, ActionRisk] = {
    # Queries
    "node_status": ActionRisk.QUERY,
    "list_strategies": ActionRisk.QUERY,
    "list_orders": ActionRisk.QUERY,
    "get_order": ActionRisk.QUERY,
    "get_portfolio": ActionRisk.QUERY,
    "get_positions": ActionRisk.QUERY,
    "get_balances": ActionRisk.QUERY,
    "get_pnl": ActionRisk.QUERY,
    "get_exposure": ActionRisk.QUERY,
    "list_instruments": ActionRisk.QUERY,
    "get_instrument": ActionRisk.QUERY,
    "get_quote": ActionRisk.QUERY,
    "get_bars": ActionRisk.QUERY,
    "get_risk_state": ActionRisk.QUERY,
    # Low-risk mutations
    "start_strategy": ActionRisk.LOW,
    "stop_strategy": ActionRisk.LOW,
    "cancel_order": ActionRisk.LOW,
    "submit_small_order": ActionRisk.LOW,
    # High-risk mutations
    "submit_order": ActionRisk.HIGH,
    "modify_order": ActionRisk.HIGH,
    "remove_strategy": ActionRisk.HIGH,
    # Critical mutations
    "cancel_all_orders": ActionRisk.CRITICAL,
    "market_exit": ActionRisk.CRITICAL,
    "node_stop": ActionRisk.CRITICAL,
    "set_risk_limits": ActionRisk.CRITICAL,
}


def classify_action(action_name: str) -> ActionRisk:
    """
    Classify an action by its risk level.

    Parameters
    ----------
    action_name : str
        The action name.

    Returns
    -------
    ActionRisk
        Defaults to HIGH if the action is not in the classification table.

    """
    return ACTION_CLASSIFICATIONS.get(action_name, ActionRisk.HIGH)
