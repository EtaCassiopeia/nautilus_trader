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

import time
from dataclasses import dataclass
from dataclasses import field
from decimal import Decimal
from decimal import InvalidOperation
from typing import TYPE_CHECKING

from nautilus_trader.agent.modes import ActionRisk
from nautilus_trader.agent.modes import AgentMode
from nautilus_trader.agent.modes import check_permission


if TYPE_CHECKING:
    from nautilus_trader.agent.config import AgentConfig
    from nautilus_trader.agent.config import GuardrailConfig


@dataclass
class GuardrailCheckResult:
    """
    Result of a guardrail validation check.

    Parameters
    ----------
    passed : bool
        Whether all checks passed.
    checks : list[str]
        Descriptions of each check performed.
    rejection_reason : str, optional
        Reason for rejection, if any.
    needs_approval : bool
        Whether the action needs human approval.

    """

    passed: bool
    checks: list[str] = field(default_factory=list)
    rejection_reason: str | None = None
    needs_approval: bool = False


class KillSwitch:
    """
    Automatic kill switch for the AI agent.

    When triggered, the kill switch:
    1. Blocks all new order submissions
    2. Switches the agent to MONITOR mode
    3. Records the trigger reason
    4. Requires manual reset to resume trading

    """

    def __init__(self) -> None:
        self._triggered = False
        self._trigger_reason: str | None = None
        self._trigger_time: float | None = None

    @property
    def is_triggered(self) -> bool:
        """Return whether the kill switch is active."""
        return self._triggered

    @property
    def trigger_reason(self) -> str | None:
        """Return the reason the kill switch was triggered."""
        return self._trigger_reason

    @property
    def trigger_time(self) -> float | None:
        """Return the Unix timestamp when the kill switch was triggered."""
        return self._trigger_time

    def trigger(self, reason: str) -> None:
        """
        Trigger the kill switch.

        Parameters
        ----------
        reason : str
            Why the kill switch was triggered.

        """
        if not self._triggered:
            self._triggered = True
            self._trigger_reason = reason
            self._trigger_time = time.time()

    def reset(self) -> None:
        """Reset the kill switch (manual operation)."""
        self._triggered = False
        self._trigger_reason = None
        self._trigger_time = None


class RateLimiter:
    """
    Token-bucket rate limiter for order submissions.

    Parameters
    ----------
    max_per_minute : int
        Maximum number of orders allowed per minute.

    """

    def __init__(self, max_per_minute: int) -> None:
        self._max_per_minute = max_per_minute
        self._timestamps: list[float] = []

    @property
    def max_per_minute(self) -> int:
        """Return the maximum orders per minute."""
        return self._max_per_minute

    def check(self) -> bool:
        """
        Check if an order can be submitted without exceeding the rate limit.

        Returns
        -------
        bool

        """
        now = time.time()
        cutoff = now - 60.0

        # Prune old timestamps
        self._timestamps = [t for t in self._timestamps if t > cutoff]

        return len(self._timestamps) < self._max_per_minute

    def record(self) -> None:
        """Record an order submission."""
        self._timestamps.append(time.time())

    @property
    def current_count(self) -> int:
        """Return the number of orders in the current window."""
        now = time.time()
        cutoff = now - 60.0
        self._timestamps = [t for t in self._timestamps if t > cutoff]
        return len(self._timestamps)


class AgentGuardrails:
    """
    Safety guardrails for the AI agent.

    Validates all agent actions against configured safety limits.
    These checks are enforced programmatically and cannot be overridden
    by the agent's reasoning.

    Parameters
    ----------
    config : AgentConfig
        The agent configuration.

    """

    def __init__(self, config: AgentConfig) -> None:
        self._config = config
        self._guardrails = config.guardrails
        self._mode = AgentMode(config.mode)
        self._kill_switch = KillSwitch()
        self._rate_limiter = RateLimiter(self._guardrails.max_orders_per_minute)

    @property
    def mode(self) -> AgentMode:
        """Return the current operating mode."""
        return self._mode

    @mode.setter
    def mode(self, value: AgentMode) -> None:
        """Set the operating mode."""
        self._mode = value

    @property
    def kill_switch(self) -> KillSwitch:
        """Return the kill switch."""
        return self._kill_switch

    @property
    def rate_limiter(self) -> RateLimiter:
        """Return the rate limiter."""
        return self._rate_limiter

    def validate_action(
        self,
        action_name: str,
        action_risk: ActionRisk,
        params: dict | None = None,
    ) -> GuardrailCheckResult:
        """
        Validate an agent action against all guardrails.

        Parameters
        ----------
        action_name : str
            The name of the action.
        action_risk : ActionRisk
            The risk level of the action.
        params : dict, optional
            Action parameters (for order validation).

        Returns
        -------
        GuardrailCheckResult

        """
        checks: list[str] = []

        # 1. Kill switch
        if self._kill_switch.is_triggered:
            if action_risk != ActionRisk.QUERY:
                return GuardrailCheckResult(
                    passed=False,
                    checks=["kill_switch: TRIGGERED"],
                    rejection_reason=(
                        f"Kill switch is active: {self._kill_switch.trigger_reason}. "
                        "Only queries are allowed. Manual reset required."
                    ),
                )
            checks.append("kill_switch: TRIGGERED (queries allowed)")

        # 2. Mode permission
        allowed, needs_approval = check_permission(self._mode, action_risk)
        if not allowed:
            return GuardrailCheckResult(
                passed=False,
                checks=[f"mode_check: {self._mode.value} blocks {action_risk.value}"],
                rejection_reason=(
                    f"Action '{action_name}' ({action_risk.value}) is not allowed "
                    f"in {self._mode.value} mode."
                ),
            )
        checks.append(f"mode_check: {self._mode.value} allows {action_risk.value}")

        # 3. Order-specific checks
        if params and action_name in ("submit_order", "submit_small_order"):
            order_result = self._validate_order(params, checks)
            if not order_result.passed:
                return order_result

        return GuardrailCheckResult(
            passed=True,
            checks=checks,
            needs_approval=needs_approval,
        )

    def _validate_order(
        self,
        params: dict,
        checks: list[str],
    ) -> GuardrailCheckResult:
        """Validate order-specific guardrails."""
        instrument_id = params.get("instrument_id", "")
        quantity_str = params.get("quantity", "0")

        # Instrument blocklist
        if instrument_id in self._guardrails.instrument_blocklist:
            return GuardrailCheckResult(
                passed=False,
                checks=checks + [f"instrument_blocklist: {instrument_id} BLOCKED"],
                rejection_reason=f"Instrument '{instrument_id}' is in the blocklist.",
            )

        # Instrument allowlist
        if self._guardrails.instrument_allowlist is not None:
            if instrument_id not in self._guardrails.instrument_allowlist:
                return GuardrailCheckResult(
                    passed=False,
                    checks=checks + [f"instrument_allowlist: {instrument_id} NOT ALLOWED"],
                    rejection_reason=(
                        f"Instrument '{instrument_id}' is not in the allowlist."
                    ),
                )
        checks.append(f"instrument_check: {instrument_id} OK")

        # Max single order size
        try:
            quantity = Decimal(quantity_str)
        except InvalidOperation:
            return GuardrailCheckResult(
                passed=False,
                checks=checks + [f"quantity_parse: INVALID '{quantity_str}'"],
                rejection_reason=f"Invalid order quantity: '{quantity_str}'",
            )

        if self._guardrails.max_single_order_size is not None:
            max_size = Decimal(self._guardrails.max_single_order_size)
            if quantity > max_size:
                return GuardrailCheckResult(
                    passed=False,
                    checks=checks + [f"order_size: {quantity}/{max_size} EXCEEDED"],
                    rejection_reason=(
                        f"Order quantity {quantity} exceeds maximum {max_size}."
                    ),
                )
            checks.append(f"order_size: {quantity}/{max_size} OK")

        # Rate limit
        if not self._rate_limiter.check():
            return GuardrailCheckResult(
                passed=False,
                checks=checks + [
                    f"rate_limit: {self._rate_limiter.current_count}/"
                    f"{self._rate_limiter.max_per_minute} EXCEEDED",
                ],
                rejection_reason=(
                    f"Order rate limit exceeded: "
                    f"{self._rate_limiter.current_count}/{self._rate_limiter.max_per_minute} "
                    f"per minute."
                ),
            )
        checks.append(
            f"rate_limit: {self._rate_limiter.current_count}/"
            f"{self._rate_limiter.max_per_minute} OK",
        )

        return GuardrailCheckResult(passed=True, checks=checks)

    def check_daily_loss(self, realized_pnl: str) -> bool:
        """
        Check if daily loss limit has been breached and trigger kill switch.

        Parameters
        ----------
        realized_pnl : str
            Current daily realized P&L as a decimal string.

        Returns
        -------
        bool
            True if within limits, False if kill switch was triggered.

        """
        if self._guardrails.max_daily_loss is None:
            return True

        try:
            pnl = Decimal(realized_pnl)
            limit = Decimal(self._guardrails.max_daily_loss)
        except InvalidOperation:
            return True

        if pnl <= limit:
            self._kill_switch.trigger(
                f"Daily loss limit breached: P&L {pnl} <= limit {limit}",
            )
            self._mode = AgentMode.MONITOR
            return False

        return True
