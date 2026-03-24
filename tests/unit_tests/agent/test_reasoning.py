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

from unittest.mock import MagicMock

import pytest

from nautilus_trader.agent.config import AgentConfig
from nautilus_trader.agent.reasoning import ReasoningEngine
from nautilus_trader.agent.reasoning import ReasoningResult


class TestReasoningResult:
    def test_no_action(self) -> None:
        result = ReasoningResult(reasoning="No action needed.")

        assert result.reasoning == "No action needed."
        assert result.action is None

    def test_with_action(self) -> None:
        result = ReasoningResult(
            reasoning="Price is favorable",
            action={"tool": "submit_order", "params": {"quantity": "0.5"}},
        )

        assert result.action is not None
        assert result.action["tool"] == "submit_order"


class TestReasoningEngine:
    def test_init(self) -> None:
        config = AgentConfig(model="claude-sonnet-4-20250514")
        engine = ReasoningEngine(config)

        assert engine._model == "claude-sonnet-4-20250514"

    def test_set_system_prompt(self) -> None:
        config = AgentConfig()
        engine = ReasoningEngine(config)

        engine.set_system_prompt("- Max order: 1.0", "- list_orders")

        assert engine._system_prompt is not None
        assert "MONITOR" in engine._system_prompt

    @pytest.mark.asyncio
    async def test_reason_without_start_raises(self) -> None:
        config = AgentConfig()
        engine = ReasoningEngine(config)

        with pytest.raises(RuntimeError, match="not started"):
            await engine.reason(state={}, events=[], objectives=[])

    def test_parse_text_response(self) -> None:
        config = AgentConfig()
        engine = ReasoningEngine(config)

        # Mock response with text only
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "No action needed at this time."
        mock_response.content = [text_block]
        mock_response.id = "msg_123"
        mock_response.model = "claude-sonnet-4-20250514"
        mock_response.stop_reason = "end_turn"
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50

        result = engine._parse_response(mock_response)

        assert result.reasoning == "No action needed at this time."
        assert result.action is None
        assert result.raw_response["id"] == "msg_123"

    def test_parse_tool_use_response(self) -> None:
        config = AgentConfig()
        engine = ReasoningEngine(config)

        # Mock response with text + tool use
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Price dipped, placing limit order."

        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = "nautilus_submit_order"
        tool_block.input = {"instrument_id": "BTCUSDT-PERP.BINANCE", "quantity": "0.5"}
        tool_block.id = "toolu_123"

        mock_response = MagicMock()
        mock_response.content = [text_block, tool_block]
        mock_response.id = "msg_456"
        mock_response.model = "claude-sonnet-4-20250514"
        mock_response.stop_reason = "tool_use"
        mock_response.usage.input_tokens = 200
        mock_response.usage.output_tokens = 100

        result = engine._parse_response(mock_response)

        assert result.reasoning == "Price dipped, placing limit order."
        assert result.action is not None
        assert result.action["tool"] == "nautilus_submit_order"
        assert result.action["params"]["quantity"] == "0.5"
        assert result.action["tool_use_id"] == "toolu_123"
