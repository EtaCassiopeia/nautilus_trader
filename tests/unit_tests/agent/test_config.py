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


class TestGuardrailConfig:
    def test_defaults(self) -> None:
        config = GuardrailConfig()

        assert config.max_position_size == {}
        assert config.max_portfolio_exposure is None
        assert config.max_daily_loss is None
        assert config.max_orders_per_minute == 10
        assert config.max_single_order_size is None
        assert config.instrument_allowlist is None
        assert config.instrument_blocklist == []
        assert config.require_stop_loss is False
        assert config.human_approval_threshold is None
        assert config.kill_switch_conditions == []

    def test_custom_values(self) -> None:
        config = GuardrailConfig(
            max_position_size={"BTCUSDT-PERP.BINANCE": "10.0"},
            max_daily_loss="-5000.00",
            max_orders_per_minute=5,
            instrument_allowlist=["BTCUSDT-PERP.BINANCE"],
            require_stop_loss=True,
        )

        assert config.max_position_size == {"BTCUSDT-PERP.BINANCE": "10.0"}
        assert config.max_daily_loss == "-5000.00"
        assert config.max_orders_per_minute == 5
        assert config.instrument_allowlist == ["BTCUSDT-PERP.BINANCE"]
        assert config.require_stop_loss is True

    def test_frozen(self) -> None:
        config = GuardrailConfig()
        with pytest.raises(AttributeError):
            config.max_orders_per_minute = 20  # type: ignore[misc]


class TestAgentConfig:
    def test_defaults(self) -> None:
        config = AgentConfig()

        assert config.mode == "MONITOR"
        assert config.api_url == "http://localhost:8001"
        assert config.api_key is None
        assert config.ws_url is None
        assert config.model == "claude-sonnet-4-20250514"
        assert config.event_batch_interval_secs == 1.0
        assert config.event_topics == ["events.*"]
        assert config.max_context_events == 50
        assert isinstance(config.guardrails, GuardrailConfig)

    def test_effective_ws_url_from_http(self) -> None:
        config = AgentConfig(api_url="http://localhost:8001")

        assert config.effective_ws_url == "ws://localhost:8001/ws/events"

    def test_effective_ws_url_from_https(self) -> None:
        config = AgentConfig(api_url="https://trading.example.com:8001")

        assert config.effective_ws_url == "wss://trading.example.com:8001/ws/events"

    def test_explicit_ws_url(self) -> None:
        config = AgentConfig(
            api_url="http://localhost:8001",
            ws_url="ws://custom:9999/events",
        )

        assert config.effective_ws_url == "ws://custom:9999/events"

    def test_custom_mode(self) -> None:
        config = AgentConfig(mode="AUTONOMOUS")

        assert config.mode == "AUTONOMOUS"

    def test_frozen(self) -> None:
        config = AgentConfig()
        with pytest.raises(AttributeError):
            config.mode = "AUTONOMOUS"  # type: ignore[misc]
