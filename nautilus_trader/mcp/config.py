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

import os
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class McpServerConfig:
    """
    Configuration for the NautilusTrader MCP server.

    Parameters
    ----------
    api_url : str
        Base URL of the NautilusTrader REST API.
    api_key : str, optional
        API key for authentication via ``X-Api-Key`` header.
    safety_level : str
        Safety level: UNRESTRICTED, STANDARD, or STRICT.
    read_only : bool
        If True, all mutation tools are disabled.
    allowed_tools : list[str], optional
        Explicit allowlist of tool names. None enables all tools.
    blocked_tools : list[str], optional
        Blocklist of tool names. Takes precedence over allowed_tools.
    max_order_quantity : str, optional
        Maximum quantity per order as a decimal string.
    allowed_instruments : list[str], optional
        Instrument allowlist. None allows all.
    blocked_instruments : list[str], optional
        Instrument blocklist.
    transport : str
        MCP transport: "stdio" or "sse".
    sse_host : str
        Host for SSE transport.
    sse_port : int
        Port for SSE transport.

    """

    api_url: str = "http://localhost:8001"
    api_key: str | None = None
    safety_level: Literal["UNRESTRICTED", "STANDARD", "STRICT"] = "STANDARD"
    read_only: bool = False
    allowed_tools: list[str] | None = None
    blocked_tools: list[str] | None = None
    max_order_quantity: str | None = None
    allowed_instruments: list[str] | None = None
    blocked_instruments: list[str] | None = None
    transport: Literal["stdio", "sse"] = "stdio"
    sse_host: str = "127.0.0.1"
    sse_port: int = 8002


def load_config(
    config_path: str | Path | None = None,
    **overrides: object,
) -> McpServerConfig:
    """
    Load MCP server configuration from file, environment, and overrides.

    Priority: overrides > environment variables > config file > defaults.

    Parameters
    ----------
    config_path : str or Path, optional
        Path to TOML configuration file.
        Defaults to ``~/.nautilus/mcp.toml`` if it exists.
    **overrides
        Keyword arguments that override all other sources.

    Returns
    -------
    McpServerConfig

    """
    file_values: dict = {}

    # 1. Load from file
    if config_path is None:
        config_path = Path.home() / ".nautilus" / "mcp.toml"

    if isinstance(config_path, str):
        config_path = Path(config_path)

    if config_path.exists():
        file_values = _load_toml(config_path)

    # 2. Load from environment
    env_values = _load_env()

    # 3. Merge: file < env < overrides
    merged = {**file_values, **env_values, **overrides}

    # Filter to only valid McpServerConfig fields
    valid_fields = {f.name for f in McpServerConfig.__dataclass_fields__.values()}
    filtered = {k: v for k, v in merged.items() if k in valid_fields}

    return McpServerConfig(**filtered)


def _load_toml(path: Path) -> dict:
    """Load configuration from a TOML file."""
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]

    with open(path, "rb") as f:
        raw = tomllib.load(f)

    result: dict = {}

    # Flatten sections into flat config
    if "connection" in raw:
        conn = raw["connection"]
        if "api_url" in conn:
            result["api_url"] = conn["api_url"]
        if "api_key" in conn:
            result["api_key"] = conn["api_key"]

    if "safety" in raw:
        safety = raw["safety"]
        if "safety_level" in safety:
            result["safety_level"] = safety["safety_level"]
        if "read_only" in safety:
            result["read_only"] = safety["read_only"]

    if "guardrails" in raw:
        guardrails = raw["guardrails"]
        if "max_order_quantity" in guardrails:
            result["max_order_quantity"] = guardrails["max_order_quantity"]
        if "allowed_instruments" in guardrails:
            result["allowed_instruments"] = guardrails["allowed_instruments"]
        if "blocked_instruments" in guardrails:
            result["blocked_instruments"] = guardrails["blocked_instruments"]

    if "tools" in raw:
        tools = raw["tools"]
        if "allowed" in tools:
            result["allowed_tools"] = tools["allowed"]
        if "blocked" in tools:
            result["blocked_tools"] = tools["blocked"]

    if "transport" in raw:
        transport = raw["transport"]
        if "transport" in transport:
            result["transport"] = transport["transport"]
        if "sse_host" in transport:
            result["sse_host"] = transport["sse_host"]
        if "sse_port" in transport:
            result["sse_port"] = transport["sse_port"]

    return result


def _load_env() -> dict:
    """Load configuration from environment variables."""
    result: dict = {}

    env_map = {
        "NAUTILUS_API_URL": "api_url",
        "NAUTILUS_API_KEY": "api_key",
        "NAUTILUS_SAFETY_LEVEL": "safety_level",
        "NAUTILUS_MCP_TRANSPORT": "transport",
        "NAUTILUS_MCP_SSE_HOST": "sse_host",
        "NAUTILUS_MCP_SSE_PORT": "sse_port",
        "NAUTILUS_MCP_READ_ONLY": "read_only",
        "NAUTILUS_MAX_ORDER_QUANTITY": "max_order_quantity",
    }

    for env_key, config_key in env_map.items():
        value = os.environ.get(env_key)
        if value is not None:
            if config_key == "sse_port":
                result[config_key] = int(value)
            elif config_key == "read_only":
                result[config_key] = value.lower() in ("true", "1", "yes")
            else:
                result[config_key] = value

    return result
