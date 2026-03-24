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

import os
import tempfile
from pathlib import Path

import pytest

from nautilus_trader.mcp.config import McpServerConfig
from nautilus_trader.mcp.config import _load_env
from nautilus_trader.mcp.config import _load_toml
from nautilus_trader.mcp.config import load_config


class TestMcpServerConfig:
    def test_defaults(self) -> None:
        config = McpServerConfig()

        assert config.api_url == "http://localhost:8001"
        assert config.api_key is None
        assert config.safety_level == "STANDARD"
        assert config.read_only is False
        assert config.allowed_tools is None
        assert config.blocked_tools is None
        assert config.max_order_quantity is None
        assert config.allowed_instruments is None
        assert config.blocked_instruments is None
        assert config.transport == "stdio"
        assert config.sse_host == "127.0.0.1"
        assert config.sse_port == 8002

    def test_custom_values(self) -> None:
        config = McpServerConfig(
            api_url="http://remote:9000",
            api_key="secret",
            safety_level="STRICT",
            read_only=True,
            max_order_quantity="1.0",
            allowed_instruments=["BTCUSDT-PERP.BINANCE"],
            transport="sse",
            sse_port=9002,
        )

        assert config.api_url == "http://remote:9000"
        assert config.api_key == "secret"
        assert config.safety_level == "STRICT"
        assert config.read_only is True
        assert config.max_order_quantity == "1.0"
        assert config.allowed_instruments == ["BTCUSDT-PERP.BINANCE"]
        assert config.transport == "sse"
        assert config.sse_port == 9002

    def test_frozen(self) -> None:
        config = McpServerConfig()
        with pytest.raises(AttributeError):
            config.api_url = "http://other"  # type: ignore[misc]


class TestLoadToml:
    def test_load_full_config(self) -> None:
        toml_content = b"""
[connection]
api_url = "http://remote:9000"
api_key = "my-key"

[safety]
safety_level = "STRICT"
read_only = true

[guardrails]
max_order_quantity = "0.5"
allowed_instruments = ["BTCUSDT-PERP.BINANCE", "ETHUSDT-PERP.BINANCE"]

[tools]
blocked = ["nautilus_node_stop"]

[transport]
transport = "sse"
sse_host = "0.0.0.0"
sse_port = 9002
"""
        with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as f:
            f.write(toml_content)
            f.flush()
            result = _load_toml(Path(f.name))

        os.unlink(f.name)

        assert result["api_url"] == "http://remote:9000"
        assert result["api_key"] == "my-key"
        assert result["safety_level"] == "STRICT"
        assert result["read_only"] is True
        assert result["max_order_quantity"] == "0.5"
        assert result["allowed_instruments"] == ["BTCUSDT-PERP.BINANCE", "ETHUSDT-PERP.BINANCE"]
        assert result["blocked_tools"] == ["nautilus_node_stop"]
        assert result["transport"] == "sse"
        assert result["sse_host"] == "0.0.0.0"
        assert result["sse_port"] == 9002

    def test_load_partial_config(self) -> None:
        toml_content = b"""
[connection]
api_url = "http://custom:8080"
"""
        with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as f:
            f.write(toml_content)
            f.flush()
            result = _load_toml(Path(f.name))

        os.unlink(f.name)

        assert result == {"api_url": "http://custom:8080"}


class TestLoadEnv:
    def test_load_env_vars(self, monkeypatch) -> None:
        monkeypatch.setenv("NAUTILUS_API_URL", "http://env:8001")
        monkeypatch.setenv("NAUTILUS_API_KEY", "env-key")
        monkeypatch.setenv("NAUTILUS_SAFETY_LEVEL", "STRICT")
        monkeypatch.setenv("NAUTILUS_MCP_TRANSPORT", "sse")
        monkeypatch.setenv("NAUTILUS_MCP_SSE_PORT", "9999")
        monkeypatch.setenv("NAUTILUS_MCP_READ_ONLY", "true")
        monkeypatch.setenv("NAUTILUS_MAX_ORDER_QUANTITY", "2.0")

        result = _load_env()

        assert result["api_url"] == "http://env:8001"
        assert result["api_key"] == "env-key"
        assert result["safety_level"] == "STRICT"
        assert result["transport"] == "sse"
        assert result["sse_port"] == 9999
        assert result["read_only"] is True
        assert result["max_order_quantity"] == "2.0"

    def test_load_env_empty(self) -> None:
        result = _load_env()
        # Should not include keys that aren't set
        assert "api_url" not in result or os.environ.get("NAUTILUS_API_URL") is not None


class TestLoadConfig:
    def test_defaults_when_no_file(self) -> None:
        config = load_config(config_path="/nonexistent/path.toml")

        assert config.api_url == "http://localhost:8001"
        assert config.safety_level == "STANDARD"

    def test_overrides_take_precedence(self) -> None:
        config = load_config(
            config_path="/nonexistent/path.toml",
            api_url="http://override:8001",
            safety_level="STRICT",
        )

        assert config.api_url == "http://override:8001"
        assert config.safety_level == "STRICT"

    def test_file_values_used(self) -> None:
        toml_content = b"""
[connection]
api_url = "http://from-file:8001"
api_key = "file-key"
"""
        with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as f:
            f.write(toml_content)
            f.flush()
            config = load_config(config_path=f.name)

        os.unlink(f.name)

        assert config.api_url == "http://from-file:8001"
        assert config.api_key == "file-key"

    def test_env_overrides_file(self, monkeypatch) -> None:
        toml_content = b"""
[connection]
api_url = "http://from-file:8001"
"""
        monkeypatch.setenv("NAUTILUS_API_URL", "http://from-env:8001")

        with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as f:
            f.write(toml_content)
            f.flush()
            config = load_config(config_path=f.name)

        os.unlink(f.name)

        assert config.api_url == "http://from-env:8001"

    def test_overrides_override_env(self, monkeypatch) -> None:
        monkeypatch.setenv("NAUTILUS_API_URL", "http://from-env:8001")

        config = load_config(
            config_path="/nonexistent/path.toml",
            api_url="http://from-override:8001",
        )

        assert config.api_url == "http://from-override:8001"
