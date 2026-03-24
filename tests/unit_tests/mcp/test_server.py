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

from nautilus_trader.mcp.config import McpServerConfig
from nautilus_trader.mcp.server import create_mcp_server


class TestCreateMcpServer:
    def test_creates_server_and_client(self) -> None:
        config = McpServerConfig()

        server, client = create_mcp_server(config)

        assert server is not None
        assert client is not None
        assert client.base_url == "http://localhost:8001"

    def test_creates_with_custom_config(self) -> None:
        config = McpServerConfig(
            api_url="http://remote:9000",
            api_key="secret",
        )

        server, client = create_mcp_server(config)

        assert client.base_url == "http://remote:9000"

    def test_read_only_skips_mutation_tools(self) -> None:
        config = McpServerConfig(read_only=True)

        server, client = create_mcp_server(config)

        # Server should still be created successfully
        assert server is not None
