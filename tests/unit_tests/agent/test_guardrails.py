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

import pytest

from nautilus_trader.agent.config import AgentConfig
from nautilus_trader.agent.config import GuardrailConfig
from nautilus_trader.agent.guardrails import AgentGuardrails
from nautilus_trader.agent.guardrails import KillSwitch
from nautilus_trader.agent.guardrails import RateLimiter
from nautilus_trader.agent.modes import ActionRisk
from nautilus_trader.agent.modes import AgentMode


class TestKillSwitch:
    def test_initial_state(self) -> None:
        ks = KillSwitch()

        assert ks.is_triggered is False
        assert ks.trigger_reason is None

    def test_trigger(self) -> None:
        ks = KillSwitch()

        ks.trigger("Daily loss exceeded")

        assert ks.is_triggered is True
        assert ks.trigger_reason == "Daily loss exceeded"
        assert ks.trigger_time is not None

    def test_trigger_idempotent(self) -> None:
        ks = KillSwitch()

        ks.trigger("First reason")
        ks.trigger("Second reason")

        assert ks.trigger_reason == "First reason"

    def test_reset(self) -> None:
        ks = KillSwitch()
        ks.trigger("Test")

        ks.reset()

        assert ks.is_triggered is False
        assert ks.trigger_reason is None


class TestRateLimiter:
    def test_allows_within_limit(self) -> None:
        rl = RateLimiter(max_per_minute=5)

        assert rl.check() is True
        assert rl.current_count == 0

    def test_blocks_when_exceeded(self) -> None:
        rl = RateLimiter(max_per_minute=2)

        rl.record()
        rl.record()

        assert rl.check() is False
        assert rl.current_count == 2

    def test_allows_after_window(self) -> None:
        rl = RateLimiter(max_per_minute=1)

        # Manually backdate the timestamp
        import time
        rl._timestamps = [time.time() - 61.0]

        assert rl.check() is True


class TestAgentGuardrails:
    def _make_guardrails(self, **kwargs) -> AgentGuardrails:
        guardrail_config = GuardrailConfig(**{
            k: v for k, v in kwargs.items()
            if k in GuardrailConfig.__dataclass_fields__
        })
        agent_config = AgentConfig(
            mode=kwargs.get("mode", "AUTONOMOUS"),
            guardrails=guardrail_config,
        )
        return AgentGuardrails(agent_config)

    # Kill switch tests
    def test_kill_switch_blocks_mutations(self) -> None:
        g = self._make_guardrails()
        g.kill_switch.trigger("Test trigger")

        result = g.validate_action("submit_order", ActionRisk.HIGH)

        assert result.passed is False
        assert "Kill switch" in result.rejection_reason

    def test_kill_switch_allows_queries(self) -> None:
        g = self._make_guardrails()
        g.kill_switch.trigger("Test trigger")

        result = g.validate_action("list_orders", ActionRisk.QUERY)

        assert result.passed is True

    # Mode permission tests
    def test_monitor_blocks_orders(self) -> None:
        g = self._make_guardrails(mode="MONITOR")

        result = g.validate_action("submit_order", ActionRisk.HIGH)

        assert result.passed is False
        assert "MONITOR" in result.rejection_reason

    def test_autonomous_allows_orders(self) -> None:
        g = self._make_guardrails(mode="AUTONOMOUS")

        result = g.validate_action("submit_order", ActionRisk.HIGH, params={
            "instrument_id": "BTCUSDT-PERP.BINANCE",
            "quantity": "0.5",
        })

        assert result.passed is True
        assert result.needs_approval is False

    def test_semi_autonomous_needs_approval_for_high(self) -> None:
        g = self._make_guardrails(mode="SEMI_AUTONOMOUS")

        result = g.validate_action("submit_order", ActionRisk.HIGH, params={
            "instrument_id": "BTCUSDT-PERP.BINANCE",
            "quantity": "0.5",
        })

        assert result.passed is True
        assert result.needs_approval is True

    # Instrument checks
    def test_blocklist_rejects(self) -> None:
        g = self._make_guardrails(
            instrument_blocklist=["BTCUSDT-PERP.BINANCE"],
        )

        result = g.validate_action("submit_order", ActionRisk.HIGH, params={
            "instrument_id": "BTCUSDT-PERP.BINANCE",
            "quantity": "0.5",
        })

        assert result.passed is False
        assert "blocklist" in result.rejection_reason

    def test_allowlist_rejects_unlisted(self) -> None:
        g = self._make_guardrails(
            instrument_allowlist=["ETHUSDT-PERP.BINANCE"],
        )

        result = g.validate_action("submit_order", ActionRisk.HIGH, params={
            "instrument_id": "BTCUSDT-PERP.BINANCE",
            "quantity": "0.5",
        })

        assert result.passed is False
        assert "allowlist" in result.rejection_reason

    # Order size checks
    def test_max_order_size_rejects(self) -> None:
        g = self._make_guardrails(max_single_order_size="1.0")

        result = g.validate_action("submit_order", ActionRisk.HIGH, params={
            "instrument_id": "BTCUSDT-PERP.BINANCE",
            "quantity": "1.5",
        })

        assert result.passed is False
        assert "exceeds maximum" in result.rejection_reason

    def test_max_order_size_allows_within(self) -> None:
        g = self._make_guardrails(max_single_order_size="1.0")

        result = g.validate_action("submit_order", ActionRisk.HIGH, params={
            "instrument_id": "BTCUSDT-PERP.BINANCE",
            "quantity": "0.5",
        })

        assert result.passed is True

    def test_invalid_quantity_rejects(self) -> None:
        g = self._make_guardrails()

        result = g.validate_action("submit_order", ActionRisk.HIGH, params={
            "instrument_id": "BTCUSDT-PERP.BINANCE",
            "quantity": "not-a-number",
        })

        assert result.passed is False
        assert "Invalid" in result.rejection_reason

    # Rate limit
    def test_rate_limit_rejects(self) -> None:
        g = self._make_guardrails(max_orders_per_minute=1)
        g.rate_limiter.record()

        result = g.validate_action("submit_order", ActionRisk.HIGH, params={
            "instrument_id": "BTCUSDT-PERP.BINANCE",
            "quantity": "0.5",
        })

        assert result.passed is False
        assert "rate limit" in result.rejection_reason

    # Daily loss kill switch
    def test_daily_loss_triggers_kill_switch(self) -> None:
        g = self._make_guardrails(max_daily_loss="-5000")

        result = g.check_daily_loss("-6000")

        assert result is False
        assert g.kill_switch.is_triggered is True
        assert g.mode == AgentMode.MONITOR

    def test_daily_loss_within_limit(self) -> None:
        g = self._make_guardrails(max_daily_loss="-5000")

        result = g.check_daily_loss("-3000")

        assert result is True
        assert g.kill_switch.is_triggered is False

    def test_daily_loss_no_limit_configured(self) -> None:
        g = self._make_guardrails()

        result = g.check_daily_loss("-999999")

        assert result is True
