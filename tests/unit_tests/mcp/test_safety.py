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

from nautilus_trader.mcp.config import McpServerConfig
from nautilus_trader.mcp.safety import CRITICAL
from nautilus_trader.mcp.safety import READ
from nautilus_trader.mcp.safety import STANDARD
from nautilus_trader.mcp.safety import STRICT
from nautilus_trader.mcp.safety import UNRESTRICTED
from nautilus_trader.mcp.safety import WRITE
from nautilus_trader.mcp.safety import SafetyGuardrails


class TestSafetyLevels:
    def test_default_safety_level(self) -> None:
        config = McpServerConfig()
        guardrails = SafetyGuardrails(config)

        assert guardrails.safety_level == STANDARD
        assert guardrails.effective_safety_level == STANDARD

    def test_unrestricted_safety_level(self) -> None:
        config = McpServerConfig(safety_level="UNRESTRICTED")
        guardrails = SafetyGuardrails(config)

        assert guardrails.safety_level == UNRESTRICTED

    def test_strict_safety_level(self) -> None:
        config = McpServerConfig(safety_level="STRICT")
        guardrails = SafetyGuardrails(config)

        assert guardrails.safety_level == STRICT


class TestEnvironmentEscalation:
    def test_unrestricted_escalates_in_live(self) -> None:
        config = McpServerConfig(safety_level="UNRESTRICTED")
        guardrails = SafetyGuardrails(config)

        level = guardrails.get_effective_safety_level("LIVE")

        assert level == STANDARD

    def test_standard_stays_in_live(self) -> None:
        config = McpServerConfig(safety_level="STANDARD")
        guardrails = SafetyGuardrails(config)

        level = guardrails.get_effective_safety_level("LIVE")

        assert level == STANDARD

    def test_strict_stays_in_live(self) -> None:
        config = McpServerConfig(safety_level="STRICT")
        guardrails = SafetyGuardrails(config)

        level = guardrails.get_effective_safety_level("LIVE")

        assert level == STRICT

    def test_unrestricted_stays_in_sandbox(self) -> None:
        config = McpServerConfig(safety_level="UNRESTRICTED")
        guardrails = SafetyGuardrails(config)

        level = guardrails.get_effective_safety_level("SANDBOX")

        assert level == UNRESTRICTED

    def test_set_environment_persists(self) -> None:
        config = McpServerConfig(safety_level="UNRESTRICTED")
        guardrails = SafetyGuardrails(config)

        guardrails.set_environment("LIVE")

        assert guardrails.effective_safety_level == STANDARD


class TestRequiresConfirmation:
    def test_read_never_requires_confirmation(self) -> None:
        for level in [UNRESTRICTED, STANDARD, STRICT]:
            config = McpServerConfig(safety_level=level)
            guardrails = SafetyGuardrails(config)

            assert guardrails.requires_confirmation("any_tool", READ) is False

    def test_unrestricted_never_requires_confirmation(self) -> None:
        config = McpServerConfig(safety_level="UNRESTRICTED")
        guardrails = SafetyGuardrails(config)

        assert guardrails.requires_confirmation("tool", WRITE) is False
        assert guardrails.requires_confirmation("tool", CRITICAL) is False

    def test_standard_requires_for_critical_only(self) -> None:
        config = McpServerConfig(safety_level="STANDARD")
        guardrails = SafetyGuardrails(config)

        assert guardrails.requires_confirmation("tool", WRITE) is False
        assert guardrails.requires_confirmation("tool", CRITICAL) is True

    def test_strict_requires_for_write_and_critical(self) -> None:
        config = McpServerConfig(safety_level="STRICT")
        guardrails = SafetyGuardrails(config)

        assert guardrails.requires_confirmation("tool", WRITE) is True
        assert guardrails.requires_confirmation("tool", CRITICAL) is True


class TestToolAllowed:
    def test_all_allowed_by_default(self) -> None:
        config = McpServerConfig()
        guardrails = SafetyGuardrails(config)

        assert guardrails.is_tool_allowed("any_tool") is True

    def test_blocklist_blocks(self) -> None:
        config = McpServerConfig(blocked_tools=["nautilus_node_stop"])
        guardrails = SafetyGuardrails(config)

        assert guardrails.is_tool_allowed("nautilus_node_stop") is False
        assert guardrails.is_tool_allowed("nautilus_list_orders") is True

    def test_allowlist_restricts(self) -> None:
        config = McpServerConfig(allowed_tools=["nautilus_list_orders", "nautilus_get_order"])
        guardrails = SafetyGuardrails(config)

        assert guardrails.is_tool_allowed("nautilus_list_orders") is True
        assert guardrails.is_tool_allowed("nautilus_node_stop") is False

    def test_blocklist_takes_precedence(self) -> None:
        config = McpServerConfig(
            allowed_tools=["nautilus_node_stop"],
            blocked_tools=["nautilus_node_stop"],
        )
        guardrails = SafetyGuardrails(config)

        assert guardrails.is_tool_allowed("nautilus_node_stop") is False


class TestValidateOrder:
    def test_valid_order(self) -> None:
        config = McpServerConfig(safety_level="UNRESTRICTED")
        guardrails = SafetyGuardrails(config)

        result = guardrails.validate_order({
            "instrument_id": "BTCUSDT-PERP.BINANCE",
            "side": "BUY",
            "order_type": "MARKET",
            "quantity": "0.5",
        })

        assert result.is_valid is True
        assert result.requires_confirmation is False

    def test_read_only_rejects(self) -> None:
        config = McpServerConfig(read_only=True)
        guardrails = SafetyGuardrails(config)

        result = guardrails.validate_order({
            "instrument_id": "BTCUSDT-PERP.BINANCE",
            "quantity": "0.5",
        })

        assert result.is_valid is False
        assert "read-only" in result.rejection_reason

    def test_blocked_instrument_rejects(self) -> None:
        config = McpServerConfig(
            safety_level="UNRESTRICTED",
            blocked_instruments=["BTCUSDT-PERP.BINANCE"],
        )
        guardrails = SafetyGuardrails(config)

        result = guardrails.validate_order({
            "instrument_id": "BTCUSDT-PERP.BINANCE",
            "quantity": "0.5",
        })

        assert result.is_valid is False
        assert "blocked" in result.rejection_reason

    def test_allowlist_rejects_unlisted(self) -> None:
        config = McpServerConfig(
            safety_level="UNRESTRICTED",
            allowed_instruments=["ETHUSDT-PERP.BINANCE"],
        )
        guardrails = SafetyGuardrails(config)

        result = guardrails.validate_order({
            "instrument_id": "BTCUSDT-PERP.BINANCE",
            "quantity": "0.5",
        })

        assert result.is_valid is False
        assert "not in the allowed list" in result.rejection_reason

    def test_allowlist_permits_listed(self) -> None:
        config = McpServerConfig(
            safety_level="UNRESTRICTED",
            allowed_instruments=["BTCUSDT-PERP.BINANCE"],
        )
        guardrails = SafetyGuardrails(config)

        result = guardrails.validate_order({
            "instrument_id": "BTCUSDT-PERP.BINANCE",
            "quantity": "0.5",
        })

        assert result.is_valid is True

    def test_max_quantity_rejects(self) -> None:
        config = McpServerConfig(
            safety_level="UNRESTRICTED",
            max_order_quantity="1.0",
        )
        guardrails = SafetyGuardrails(config)

        result = guardrails.validate_order({
            "instrument_id": "BTCUSDT-PERP.BINANCE",
            "quantity": "1.5",
        })

        assert result.is_valid is False
        assert "exceeds maximum" in result.rejection_reason

    def test_max_quantity_allows_within_limit(self) -> None:
        config = McpServerConfig(
            safety_level="UNRESTRICTED",
            max_order_quantity="1.0",
        )
        guardrails = SafetyGuardrails(config)

        result = guardrails.validate_order({
            "instrument_id": "BTCUSDT-PERP.BINANCE",
            "quantity": "0.5",
        })

        assert result.is_valid is True

    def test_invalid_quantity_rejects(self) -> None:
        config = McpServerConfig(
            safety_level="UNRESTRICTED",
            max_order_quantity="1.0",
        )
        guardrails = SafetyGuardrails(config)

        result = guardrails.validate_order({
            "instrument_id": "BTCUSDT-PERP.BINANCE",
            "quantity": "not-a-number",
        })

        assert result.is_valid is False
        assert "Invalid quantity" in result.rejection_reason

    def test_standard_requires_confirmation(self) -> None:
        config = McpServerConfig(safety_level="STANDARD")
        guardrails = SafetyGuardrails(config)

        result = guardrails.validate_order({
            "instrument_id": "BTCUSDT-PERP.BINANCE",
            "side": "BUY",
            "order_type": "MARKET",
            "quantity": "0.5",
        })

        assert result.is_valid is True
        assert result.requires_confirmation is True
        assert "confirm=true" in result.confirmation_message

    def test_unrestricted_no_confirmation(self) -> None:
        config = McpServerConfig(safety_level="UNRESTRICTED")
        guardrails = SafetyGuardrails(config)

        result = guardrails.validate_order({
            "instrument_id": "BTCUSDT-PERP.BINANCE",
            "quantity": "0.5",
        })

        assert result.is_valid is True
        assert result.requires_confirmation is False


class TestValidateMutation:
    def test_read_only_blocks_mutations(self) -> None:
        config = McpServerConfig(read_only=True)
        guardrails = SafetyGuardrails(config)

        result = guardrails.validate_mutation("nautilus_start_strategy", WRITE)

        assert result.is_valid is False
        assert "read-only" in result.rejection_reason

    def test_read_only_allows_reads(self) -> None:
        config = McpServerConfig(read_only=True)
        guardrails = SafetyGuardrails(config)

        result = guardrails.validate_mutation("nautilus_list_orders", READ)

        assert result.is_valid is True

    def test_blocked_tool_rejected(self) -> None:
        config = McpServerConfig(blocked_tools=["nautilus_node_stop"])
        guardrails = SafetyGuardrails(config)

        result = guardrails.validate_mutation("nautilus_node_stop", CRITICAL)

        assert result.is_valid is False
        assert "not allowed" in result.rejection_reason

    def test_allowed_tool_passes(self) -> None:
        config = McpServerConfig(safety_level="UNRESTRICTED")
        guardrails = SafetyGuardrails(config)

        result = guardrails.validate_mutation("nautilus_start_strategy", WRITE)

        assert result.is_valid is True
        assert result.requires_confirmation is False

    def test_standard_critical_requires_confirmation(self) -> None:
        config = McpServerConfig(safety_level="STANDARD")
        guardrails = SafetyGuardrails(config)

        result = guardrails.validate_mutation("nautilus_node_stop", CRITICAL)

        assert result.is_valid is True
        assert result.requires_confirmation is True
