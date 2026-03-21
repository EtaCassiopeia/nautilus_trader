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

import msgspec

from nautilus_trader.api.config import ApiServerConfig
from nautilus_trader.api.config import EventStreamConfig
from nautilus_trader.common.config import msgspec_encoding_hook
from nautilus_trader.live.config import TradingNodeConfig


class TestEventStreamConfig:
    def test_defaults(self) -> None:
        config = EventStreamConfig()

        assert config.max_clients == 10
        assert config.client_queue_size == 10_000
        assert config.replay_buffer_size == 1_000
        assert config.ping_interval_secs == 30.0
        assert config.ping_timeout_secs == 10.0

    def test_custom_values(self) -> None:
        config = EventStreamConfig(
            max_clients=5,
            client_queue_size=5_000,
            replay_buffer_size=500,
            ping_interval_secs=15.0,
            ping_timeout_secs=5.0,
        )

        assert config.max_clients == 5
        assert config.client_queue_size == 5_000
        assert config.replay_buffer_size == 500

    def test_json_round_trip(self) -> None:
        config = EventStreamConfig(max_clients=3, replay_buffer_size=0)
        encoded = msgspec.json.encode(config, enc_hook=msgspec_encoding_hook)
        decoded = msgspec.json.decode(encoded, type=EventStreamConfig)

        assert decoded == config

    def test_frozen(self) -> None:
        config = EventStreamConfig()
        try:
            config.max_clients = 20  # type: ignore[misc]
            raise AssertionError("Expected AttributeError")
        except AttributeError:
            pass


class TestApiServerConfig:
    def test_defaults(self) -> None:
        config = ApiServerConfig()

        assert config.enabled is False
        assert config.host == "127.0.0.1"
        assert config.port == 8001
        assert config.api_key is None
        assert config.cors_origins == []
        assert config.max_connections == 100
        assert config.request_timeout_secs == 30.0
        assert config.event_stream is None

    def test_custom_values(self) -> None:
        config = ApiServerConfig(
            enabled=True,
            host="0.0.0.0",
            port=9000,
            api_key="test-key-123",
            cors_origins=["http://localhost:3000"],
            max_connections=50,
            request_timeout_secs=10.0,
            event_stream=EventStreamConfig(max_clients=5),
        )

        assert config.enabled is True
        assert config.host == "0.0.0.0"
        assert config.port == 9000
        assert config.api_key == "test-key-123"
        assert config.cors_origins == ["http://localhost:3000"]
        assert config.max_connections == 50
        assert config.request_timeout_secs == 10.0
        assert config.event_stream is not None
        assert config.event_stream.max_clients == 5

    def test_json_round_trip(self) -> None:
        config = ApiServerConfig(
            enabled=True,
            host="0.0.0.0",
            port=9000,
            api_key="secret",
            event_stream=EventStreamConfig(max_clients=3),
        )
        encoded = msgspec.json.encode(config, enc_hook=msgspec_encoding_hook)
        decoded = msgspec.json.decode(encoded, type=ApiServerConfig)

        assert decoded == config
        assert decoded.event_stream is not None
        assert decoded.event_stream.max_clients == 3

    def test_json_round_trip_no_event_stream(self) -> None:
        config = ApiServerConfig(enabled=True)
        encoded = msgspec.json.encode(config, enc_hook=msgspec_encoding_hook)
        decoded = msgspec.json.decode(encoded, type=ApiServerConfig)

        assert decoded == config
        assert decoded.event_stream is None

    def test_frozen(self) -> None:
        config = ApiServerConfig()
        try:
            config.enabled = True  # type: ignore[misc]
            raise AssertionError("Expected AttributeError")
        except AttributeError:
            pass


class TestTradingNodeConfigWithApiServer:
    def test_api_server_default_none(self) -> None:
        config = TradingNodeConfig()

        assert config.api_server is None

    def test_api_server_configured(self) -> None:
        config = TradingNodeConfig(
            api_server=ApiServerConfig(
                enabled=True,
                port=9000,
            ),
        )

        assert config.api_server is not None
        assert config.api_server.enabled is True
        assert config.api_server.port == 9000

    def test_trading_node_config_json_round_trip_with_api_server(self) -> None:
        config = TradingNodeConfig(
            api_server=ApiServerConfig(
                enabled=True,
                host="0.0.0.0",
                port=9000,
                api_key="my-key",
                event_stream=EventStreamConfig(max_clients=5),
            ),
        )
        encoded = msgspec.json.encode(config, enc_hook=msgspec_encoding_hook)
        decoded = msgspec.json.decode(encoded, type=TradingNodeConfig)

        assert decoded.api_server is not None
        assert decoded.api_server.enabled is True
        assert decoded.api_server.port == 9000
        assert decoded.api_server.api_key == "my-key"
        assert decoded.api_server.event_stream is not None
        assert decoded.api_server.event_stream.max_clients == 5

    def test_trading_node_config_json_round_trip_without_api_server(self) -> None:
        config = TradingNodeConfig()
        encoded = msgspec.json.encode(config, enc_hook=msgspec_encoding_hook)
        decoded = msgspec.json.decode(encoded, type=TradingNodeConfig)

        assert decoded.api_server is None
