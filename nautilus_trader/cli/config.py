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
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class CliConfig:
    """
    Configuration for the NautilusTrader CLI client.

    Parameters
    ----------
    host : str
        API server host.
    port : int
        API server port.
    api_key : str, optional
        API key for authentication.
    output_format : str
        Default output format: "table", "json", or "csv".
    color : bool
        Whether to use colored output.

    """

    host: str = "localhost"
    port: int = 8001
    api_key: str | None = None
    output_format: Literal["table", "json", "csv"] = "table"
    color: bool = True

    @property
    def api_url(self) -> str:
        """Return the full API base URL."""
        return f"http://{self.host}:{self.port}"


def load_cli_config(**overrides: object) -> CliConfig:
    """
    Load CLI configuration from file, environment, and overrides.

    Priority: overrides > environment variables > config file > defaults.

    Parameters
    ----------
    **overrides
        Keyword arguments that override all other sources.

    Returns
    -------
    CliConfig

    """
    file_values: dict = {}

    config_path = Path.home() / ".nautilus" / "cli.toml"
    if config_path.exists():
        file_values = _load_toml(config_path)

    env_values = _load_env()

    # Merge: file < env < overrides
    merged = {**file_values, **env_values}

    # Apply overrides (skip None values — they mean "use default")
    for k, v in overrides.items():
        if v is not None:
            merged[k] = v

    # Filter to valid fields
    valid_fields = {f.name for f in CliConfig.__dataclass_fields__.values()}
    filtered = {k: v for k, v in merged.items() if k in valid_fields}

    return CliConfig(**filtered)


def _load_toml(path: Path) -> dict:
    """Load CLI configuration from a TOML file."""
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]

    with open(path, "rb") as f:
        raw = tomllib.load(f)

    result: dict = {}

    if "connection" in raw:
        conn = raw["connection"]
        if "host" in conn:
            result["host"] = conn["host"]
        if "port" in conn:
            result["port"] = conn["port"]
        if "api_key" in conn:
            result["api_key"] = conn["api_key"]

    if "output" in raw:
        output = raw["output"]
        if "format" in output:
            result["output_format"] = output["format"]
        if "color" in output:
            result["color"] = output["color"]

    return result


def _load_env() -> dict:
    """Load CLI configuration from environment variables."""
    result: dict = {}

    env_map = {
        "NAUTILUS_HOST": ("host", str),
        "NAUTILUS_PORT": ("port", int),
        "NAUTILUS_API_KEY": ("api_key", str),
    }

    for env_key, (config_key, type_fn) in env_map.items():
        value = os.environ.get(env_key)
        if value is not None:
            result[config_key] = type_fn(value)

    return result
