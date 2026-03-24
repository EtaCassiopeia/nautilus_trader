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

from nautilus_trader.cli.config import CliConfig
from nautilus_trader.cli.config import load_cli_config


class TestCliConfig:
    def test_defaults(self) -> None:
        config = CliConfig()

        assert config.host == "localhost"
        assert config.port == 8001
        assert config.api_key is None
        assert config.output_format == "table"
        assert config.color is True

    def test_api_url(self) -> None:
        config = CliConfig(host="remote", port=9000)

        assert config.api_url == "http://remote:9000"

    def test_frozen(self) -> None:
        config = CliConfig()
        with pytest.raises(AttributeError):
            config.host = "other"  # type: ignore[misc]


class TestLoadCliConfig:
    def test_defaults_when_no_file(self) -> None:
        config = load_cli_config()

        assert config.host == "localhost"
        assert config.port == 8001

    def test_overrides(self) -> None:
        config = load_cli_config(host="remote", port=9000)

        assert config.host == "remote"
        assert config.port == 9000

    def test_none_overrides_ignored(self) -> None:
        config = load_cli_config(host=None)

        assert config.host == "localhost"

    def test_env_vars(self, monkeypatch) -> None:
        monkeypatch.setenv("NAUTILUS_HOST", "env-host")
        monkeypatch.setenv("NAUTILUS_PORT", "9999")

        config = load_cli_config()

        assert config.host == "env-host"
        assert config.port == 9999

    def test_overrides_beat_env(self, monkeypatch) -> None:
        monkeypatch.setenv("NAUTILUS_HOST", "env-host")

        config = load_cli_config(host="override-host")

        assert config.host == "override-host"
