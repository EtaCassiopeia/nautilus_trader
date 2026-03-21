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

from nautilus_trader.common.config import NautilusConfig
from nautilus_trader.common.config import NonNegativeInt
from nautilus_trader.common.config import PositiveFloat
from nautilus_trader.common.config import PositiveInt


class EventStreamConfig(NautilusConfig, frozen=True):
    """
    Configuration for the WebSocket event streaming endpoint.

    Parameters
    ----------
    max_clients : PositiveInt, default 10
        Maximum number of concurrent WebSocket clients.
    client_queue_size : PositiveInt, default 10_000
        Maximum number of events buffered per client before dropping.
    replay_buffer_size : NonNegativeInt, default 1_000
        Number of recent events kept in a ring buffer for reconnection replay.
        Set to 0 to disable replay.
    ping_interval_secs : PositiveFloat, default 30.0
        Interval between WebSocket ping frames.
    ping_timeout_secs : PositiveFloat, default 10.0
        Time to wait for a pong response before considering the client dead.

    """

    max_clients: PositiveInt = 10
    client_queue_size: PositiveInt = 10_000
    replay_buffer_size: NonNegativeInt = 1_000
    ping_interval_secs: PositiveFloat = 30.0
    ping_timeout_secs: PositiveFloat = 10.0


class ApiServerConfig(NautilusConfig, frozen=True):
    """
    Configuration for the embedded API server.

    Parameters
    ----------
    enabled : bool, default False
        If the API server should be started with the trading node.
    host : str, default "127.0.0.1"
        The host interface to bind to. Use "0.0.0.0" for remote access.
    port : PositiveInt, default 8001
        The port to listen on.
    api_key : str, optional
        API key for authentication via ``X-Api-Key`` header.
        When ``None``, authentication is disabled.
    cors_origins : list[str], default []
        Allowed CORS origins. Empty list disables CORS headers.
    max_connections : PositiveInt, default 100
        Maximum concurrent HTTP connections.
    request_timeout_secs : PositiveFloat, default 30.0
        Timeout for individual HTTP requests in seconds.
    event_stream : EventStreamConfig, optional
        Configuration for the WebSocket event streaming endpoint.
        When ``None``, event streaming is disabled.

    """

    enabled: bool = False
    host: str = "127.0.0.1"
    port: PositiveInt = 8001
    api_key: str | None = None
    cors_origins: list[str] = []
    max_connections: PositiveInt = 100
    request_timeout_secs: PositiveFloat = 30.0
    event_stream: EventStreamConfig | None = None
