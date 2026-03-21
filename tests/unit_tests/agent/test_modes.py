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

from nautilus_trader.agent.modes import ActionRisk
from nautilus_trader.agent.modes import AgentMode
from nautilus_trader.agent.modes import check_permission
from nautilus_trader.agent.modes import classify_action


class TestAgentMode:
    def test_monitor_mode(self) -> None:
        assert AgentMode.MONITOR.value == "MONITOR"

    def test_all_modes(self) -> None:
        modes = [m.value for m in AgentMode]
        assert modes == ["MONITOR", "ADVISORY", "SEMI_AUTONOMOUS", "AUTONOMOUS"]


class TestCheckPermission:
    # MONITOR mode
    def test_monitor_allows_queries(self) -> None:
        allowed, needs_approval = check_permission(AgentMode.MONITOR, ActionRisk.QUERY)
        assert allowed is True
        assert needs_approval is False

    def test_monitor_blocks_low_risk(self) -> None:
        allowed, _ = check_permission(AgentMode.MONITOR, ActionRisk.LOW)
        assert allowed is False

    def test_monitor_blocks_high_risk(self) -> None:
        allowed, _ = check_permission(AgentMode.MONITOR, ActionRisk.HIGH)
        assert allowed is False

    def test_monitor_blocks_critical(self) -> None:
        allowed, _ = check_permission(AgentMode.MONITOR, ActionRisk.CRITICAL)
        assert allowed is False

    # ADVISORY mode
    def test_advisory_allows_queries_no_approval(self) -> None:
        allowed, needs_approval = check_permission(AgentMode.ADVISORY, ActionRisk.QUERY)
        assert allowed is True
        assert needs_approval is False

    def test_advisory_allows_low_with_approval(self) -> None:
        allowed, needs_approval = check_permission(AgentMode.ADVISORY, ActionRisk.LOW)
        assert allowed is True
        assert needs_approval is True

    def test_advisory_allows_high_with_approval(self) -> None:
        allowed, needs_approval = check_permission(AgentMode.ADVISORY, ActionRisk.HIGH)
        assert allowed is True
        assert needs_approval is True

    def test_advisory_allows_critical_with_approval(self) -> None:
        allowed, needs_approval = check_permission(AgentMode.ADVISORY, ActionRisk.CRITICAL)
        assert allowed is True
        assert needs_approval is True

    # SEMI_AUTONOMOUS mode
    def test_semi_auto_allows_queries(self) -> None:
        allowed, needs_approval = check_permission(AgentMode.SEMI_AUTONOMOUS, ActionRisk.QUERY)
        assert allowed is True
        assert needs_approval is False

    def test_semi_auto_allows_low_no_approval(self) -> None:
        allowed, needs_approval = check_permission(AgentMode.SEMI_AUTONOMOUS, ActionRisk.LOW)
        assert allowed is True
        assert needs_approval is False

    def test_semi_auto_allows_high_with_approval(self) -> None:
        allowed, needs_approval = check_permission(AgentMode.SEMI_AUTONOMOUS, ActionRisk.HIGH)
        assert allowed is True
        assert needs_approval is True

    def test_semi_auto_allows_critical_with_approval(self) -> None:
        allowed, needs_approval = check_permission(AgentMode.SEMI_AUTONOMOUS, ActionRisk.CRITICAL)
        assert allowed is True
        assert needs_approval is True

    # AUTONOMOUS mode
    def test_autonomous_allows_all_no_approval(self) -> None:
        for risk in ActionRisk:
            allowed, needs_approval = check_permission(AgentMode.AUTONOMOUS, risk)
            assert allowed is True
            assert needs_approval is False


class TestClassifyAction:
    def test_query_actions(self) -> None:
        assert classify_action("node_status") == ActionRisk.QUERY
        assert classify_action("list_orders") == ActionRisk.QUERY
        assert classify_action("get_portfolio") == ActionRisk.QUERY

    def test_low_risk_actions(self) -> None:
        assert classify_action("start_strategy") == ActionRisk.LOW
        assert classify_action("stop_strategy") == ActionRisk.LOW
        assert classify_action("cancel_order") == ActionRisk.LOW

    def test_high_risk_actions(self) -> None:
        assert classify_action("submit_order") == ActionRisk.HIGH
        assert classify_action("modify_order") == ActionRisk.HIGH

    def test_critical_actions(self) -> None:
        assert classify_action("cancel_all_orders") == ActionRisk.CRITICAL
        assert classify_action("market_exit") == ActionRisk.CRITICAL
        assert classify_action("node_stop") == ActionRisk.CRITICAL

    def test_unknown_action_defaults_to_high(self) -> None:
        assert classify_action("unknown_action") == ActionRisk.HIGH
