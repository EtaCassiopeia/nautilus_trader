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
from decimal import Decimal
from decimal import InvalidOperation
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from nautilus_trader.mcp.config import McpServerConfig


# Risk levels for MCP tools
READ = "READ"
WRITE = "WRITE"
CRITICAL = "CRITICAL"

# Safety levels
UNRESTRICTED = "UNRESTRICTED"
STANDARD = "STANDARD"
STRICT = "STRICT"


@dataclass
class ValidationResult:
    """
    Result of a safety validation check.

    Parameters
    ----------
    is_valid : bool
        Whether the action passed validation.
    requires_confirmation : bool
        Whether the action needs explicit confirmation before execution.
    rejection_reason : str, optional
        Reason the action was rejected, if is_valid is False.
    confirmation_message : str, optional
        Message to present to the user when confirmation is required.

    """

    is_valid: bool
    requires_confirmation: bool
    rejection_reason: str | None = None
    confirmation_message: str | None = None


class SafetyGuardrails:
    """
    Pre-action validation and confirmation logic for MCP tools.

    Validates tool invocations against configured guardrails including
    read-only mode, instrument allowlists/blocklists, order quantity
    limits, and confirmation requirements based on safety level.

    Parameters
    ----------
    config : McpServerConfig
        The MCP server configuration with safety settings.

    """

    def __init__(self, config: McpServerConfig) -> None:
        self._config = config
        self._effective_safety_level: str | None = None

    @property
    def safety_level(self) -> str:
        """Return the configured safety level (before environment escalation)."""
        return self._config.safety_level

    @property
    def effective_safety_level(self) -> str:
        """Return the effective safety level (after environment escalation)."""
        if self._effective_safety_level is not None:
            return self._effective_safety_level
        return self._config.safety_level

    @property
    def is_read_only(self) -> bool:
        """Return whether the server is in read-only mode."""
        return self._config.read_only

    def set_environment(self, environment: str) -> None:
        """
        Set the trading environment and apply auto-escalation rules.

        When the trading node is running in LIVE environment,
        UNRESTRICTED safety is escalated to STANDARD.

        Parameters
        ----------
        environment : str
            The trading environment (e.g., "LIVE", "SANDBOX", "BACKTEST").

        """
        self._effective_safety_level = self.get_effective_safety_level(environment)

    def get_effective_safety_level(self, environment: str) -> str:
        """
        Calculate the effective safety level given the environment.

        Parameters
        ----------
        environment : str
            The trading environment.

        Returns
        -------
        str

        """
        level = self._config.safety_level
        if environment == "LIVE" and level == UNRESTRICTED:
            return STANDARD
        return level

    def requires_confirmation(self, tool_name: str, risk_level: str) -> bool:
        """
        Check if a tool invocation requires confirmation.

        Parameters
        ----------
        tool_name : str
            The name of the MCP tool.
        risk_level : str
            The risk level of the tool (READ, WRITE, CRITICAL).

        Returns
        -------
        bool

        """
        level = self.effective_safety_level

        if risk_level == READ:
            return False

        if level == UNRESTRICTED:
            return False

        if level == STRICT:
            return risk_level in (WRITE, CRITICAL)

        # STANDARD
        return risk_level == CRITICAL

    def is_tool_allowed(self, tool_name: str) -> bool:
        """
        Check if a tool is allowed by the configured allowlist/blocklist.

        Parameters
        ----------
        tool_name : str
            The name of the MCP tool.

        Returns
        -------
        bool

        """
        # Blocklist takes precedence
        if self._config.blocked_tools is not None:
            if tool_name in self._config.blocked_tools:
                return False

        # Allowlist
        if self._config.allowed_tools is not None:
            return tool_name in self._config.allowed_tools

        return True

    def validate_order(self, order: dict) -> ValidationResult:
        """
        Validate an order against configured guardrails.

        Checks
        ------
        1. Read-only mode
        2. Instrument allowlist/blocklist
        3. Maximum order quantity
        4. Confirmation requirement based on safety level

        Parameters
        ----------
        order : dict
            The order parameters including instrument_id, quantity, side, etc.

        Returns
        -------
        ValidationResult

        """
        # 1. Read-only mode
        if self._config.read_only:
            return ValidationResult(
                is_valid=False,
                requires_confirmation=False,
                rejection_reason="Server is in read-only mode. Order submission is disabled.",
            )

        instrument_id = order.get("instrument_id", "")

        # 2. Instrument blocklist
        if self._config.blocked_instruments is not None:
            if instrument_id in self._config.blocked_instruments:
                return ValidationResult(
                    is_valid=False,
                    requires_confirmation=False,
                    rejection_reason=f"Instrument '{instrument_id}' is blocked.",
                )

        # 3. Instrument allowlist
        if self._config.allowed_instruments is not None:
            if instrument_id not in self._config.allowed_instruments:
                allowed = ", ".join(self._config.allowed_instruments)
                return ValidationResult(
                    is_valid=False,
                    requires_confirmation=False,
                    rejection_reason=(
                        f"Instrument '{instrument_id}' is not in the allowed list. "
                        f"Allowed: {allowed}"
                    ),
                )

        # 4. Max order quantity
        quantity_str = order.get("quantity", "0")
        if self._config.max_order_quantity is not None:
            try:
                quantity = Decimal(quantity_str)
                max_qty = Decimal(self._config.max_order_quantity)
                if quantity > max_qty:
                    return ValidationResult(
                        is_valid=False,
                        requires_confirmation=False,
                        rejection_reason=(
                            f"Order quantity {quantity} exceeds maximum "
                            f"allowed quantity {max_qty}."
                        ),
                    )
            except InvalidOperation:
                return ValidationResult(
                    is_valid=False,
                    requires_confirmation=False,
                    rejection_reason=f"Invalid quantity: '{quantity_str}'",
                )

        # 5. Confirmation requirement
        needs_confirmation = self.requires_confirmation(
            "nautilus_submit_order",
            CRITICAL,
        )

        confirmation_msg = None
        if needs_confirmation:
            side = order.get("side", "UNKNOWN")
            order_type = order.get("order_type", "UNKNOWN")
            confirmation_msg = (
                f"Order confirmation required:\n"
                f"  Action: {side} {quantity_str} {instrument_id} @ {order_type}\n"
                f"\nCall this tool again with confirm=true to submit."
            )

        return ValidationResult(
            is_valid=True,
            requires_confirmation=needs_confirmation,
            confirmation_message=confirmation_msg,
        )

    def validate_mutation(self, tool_name: str, risk_level: str) -> ValidationResult:
        """
        Validate a non-order mutation (strategy start/stop, etc.).

        Parameters
        ----------
        tool_name : str
            The MCP tool name.
        risk_level : str
            The risk level of the tool.

        Returns
        -------
        ValidationResult

        """
        if self._config.read_only and risk_level != READ:
            return ValidationResult(
                is_valid=False,
                requires_confirmation=False,
                rejection_reason="Server is in read-only mode. Mutations are disabled.",
            )

        if not self.is_tool_allowed(tool_name):
            return ValidationResult(
                is_valid=False,
                requires_confirmation=False,
                rejection_reason=f"Tool '{tool_name}' is not allowed by server configuration.",
            )

        needs_confirmation = self.requires_confirmation(tool_name, risk_level)

        return ValidationResult(
            is_valid=True,
            requires_confirmation=needs_confirmation,
            confirmation_message=(
                f"Confirmation required for '{tool_name}'. "
                f"Call again with confirm=true to proceed."
            ) if needs_confirmation else None,
        )
