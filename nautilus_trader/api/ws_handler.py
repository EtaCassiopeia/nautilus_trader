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

import asyncio
import json
from typing import TYPE_CHECKING

from starlette.websockets import WebSocket
from starlette.websockets import WebSocketDisconnect
from starlette.websockets import WebSocketState

from nautilus_trader.api.config import EventStreamConfig
from nautilus_trader.common.component import Logger


if TYPE_CHECKING:
    from nautilus_trader.api.streaming import ClientConnection
    from nautilus_trader.api.streaming import EventStreamBridge


async def websocket_event_stream(
    websocket: WebSocket,
    bridge: EventStreamBridge,
    config: EventStreamConfig,
    logger: Logger,
) -> None:
    """
    Handle a single WebSocket client connection for event streaming.

    Protocol
    --------
    1. Client connects to ``/ws/events``
    2. Client may send a JSON subscribe message:
       ``{"action": "subscribe", "topics": ["events.*", "data.quotes.*"]}``
       If no subscribe message is sent within 5 seconds, subscribes to all topics.
    3. Optionally, client can send a replay request:
       ``{"action": "replay", "last_sequence": 42}``
    4. Server pushes serialized events as JSON text frames.
    5. Connection is maintained with ping/pong at configured intervals.

    Parameters
    ----------
    websocket : WebSocket
        The WebSocket connection.
    bridge : EventStreamBridge
        The event stream bridge managing client connections.
    config : EventStreamConfig
        The streaming configuration.
    logger : Logger
        The logger instance.

    """
    await websocket.accept()

    client_id = f"{websocket.client.host}:{websocket.client.port}" if websocket.client else "unknown"

    # Wait for optional subscribe message
    topics = None
    try:
        initial_msg = await asyncio.wait_for(
            websocket.receive_text(),
            timeout=5.0,
        )
        parsed = json.loads(initial_msg)
        if parsed.get("action") == "subscribe":
            topics = parsed.get("topics")
    except (asyncio.TimeoutError, json.JSONDecodeError, WebSocketDisconnect):
        pass  # Subscribe to all topics

    conn = bridge.add_client(client_id, topics=topics)
    if conn is None:
        await websocket.close(code=1013, reason="Max clients reached")
        return

    try:
        # Start sender and receiver tasks
        sender_task = asyncio.create_task(_sender(websocket, conn, config, logger))
        receiver_task = asyncio.create_task(_receiver(websocket, bridge, conn, logger))

        done, pending = await asyncio.wait(
            [sender_task, receiver_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    except Exception as e:
        logger.error(f"WebSocket error for {client_id}: {e}")
    finally:
        bridge.remove_client(client_id)
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.close()
            except Exception:
                pass


async def _sender(
    websocket: WebSocket,
    conn: ClientConnection,
    config: EventStreamConfig,
    logger: Logger,
) -> None:
    """Send events from the client queue to the WebSocket."""
    ping_interval = config.ping_interval_secs

    while True:
        try:
            event = await asyncio.wait_for(
                conn.queue.get(),
                timeout=ping_interval,
            )
        except asyncio.TimeoutError:
            # Send ping to keep connection alive
            try:
                await websocket.send_json({"type": "ping"})
            except Exception:
                return
            continue

        if event is None:
            return  # Sentinel — close requested

        try:
            await websocket.send_json(event)
        except Exception:
            return


async def _receiver(
    websocket: WebSocket,
    bridge: EventStreamBridge,
    conn: ClientConnection,
    logger: Logger,
) -> None:
    """Receive messages from the WebSocket client (handles replay, pong, close)."""
    while True:
        try:
            data = await websocket.receive_text()
        except WebSocketDisconnect:
            return
        except Exception:
            return

        try:
            msg = json.loads(data)
        except json.JSONDecodeError:
            continue

        action = msg.get("action")

        if action == "replay":
            last_seq = msg.get("last_sequence", -1)
            events = bridge.replay_for_client(conn.client_id, last_seq)
            for event in events:
                conn.try_enqueue(event)

        elif action == "pong":
            pass  # Client responded to ping

        elif action == "subscribe":
            topics = msg.get("topics")
            conn.topics = topics
