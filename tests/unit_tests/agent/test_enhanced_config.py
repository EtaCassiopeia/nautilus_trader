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
from nautilus_trader.agent.config import EnhancedAgentConfig
from nautilus_trader.agent.config import ModelConfig


class TestModelConfig:
    def test_defaults(self) -> None:
        config = ModelConfig()

        assert config.triage_model == "claude-haiku-4-5-20251001"
        assert config.analyst_model == "claude-sonnet-4-20250514"
        assert config.debate_model == "claude-opus-4-20250514"
        assert config.risk_model == "claude-sonnet-4-20250514"
        assert config.decision_model == "claude-opus-4-20250514"

    def test_custom_values(self) -> None:
        config = ModelConfig(
            triage_model="custom-triage",
            analyst_model="custom-analyst",
        )

        assert config.triage_model == "custom-triage"
        assert config.analyst_model == "custom-analyst"
        # Others keep defaults
        assert config.debate_model == "claude-opus-4-20250514"

    def test_frozen(self) -> None:
        config = ModelConfig()
        with pytest.raises(AttributeError):
            config.triage_model = "changed"  # type: ignore[misc]


class TestEnhancedAgentConfig:
    def test_defaults(self) -> None:
        config = EnhancedAgentConfig()

        # Inherited AgentConfig defaults
        assert config.mode == "MONITOR"
        assert config.api_url == "http://localhost:8001"
        assert config.model == "claude-sonnet-4-20250514"

        # Enhanced defaults
        assert isinstance(config.models, ModelConfig)
        assert config.max_debate_rounds == 2
        assert config.risk_consensus_threshold == 2
        assert config.enable_memory is True
        assert config.memory_storage_path is None
        assert config.enable_debate is True
        assert config.enable_risk_team is True
        assert config.analysts == ["technical", "sentiment", "risk"]

    def test_custom_values(self) -> None:
        models = ModelConfig(triage_model="custom-triage")
        config = EnhancedAgentConfig(
            mode="AUTONOMOUS",
            models=models,
            max_debate_rounds=5,
            risk_consensus_threshold=3,
            enable_memory=False,
            memory_storage_path="/tmp/memories.jsonl",
            enable_debate=False,
            enable_risk_team=False,
            analysts=["technical", "macro"],
        )

        assert config.mode == "AUTONOMOUS"
        assert config.models.triage_model == "custom-triage"
        assert config.max_debate_rounds == 5
        assert config.risk_consensus_threshold == 3
        assert config.enable_memory is False
        assert config.memory_storage_path == "/tmp/memories.jsonl"
        assert config.enable_debate is False
        assert config.enable_risk_team is False
        assert config.analysts == ["technical", "macro"]

    def test_inherits_from_agent_config(self) -> None:
        config = EnhancedAgentConfig()

        assert isinstance(config, AgentConfig)

    def test_effective_ws_url_inherited(self) -> None:
        config = EnhancedAgentConfig(api_url="http://localhost:9000")

        assert config.effective_ws_url == "ws://localhost:9000/ws/events"

    def test_frozen(self) -> None:
        config = EnhancedAgentConfig()
        with pytest.raises(AttributeError):
            config.max_debate_rounds = 10  # type: ignore[misc]
