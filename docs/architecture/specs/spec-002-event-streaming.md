# SPEC-002: Event Streaming

## Overview

The Event Streaming system provides real-time delivery of NautilusTrader events to external consumers over WebSocket. It enables UIs, monitoring tools, CLIs, and AI agents to observe the trading system's behavior as it happens — order fills, position changes, risk alerts, market data updates, and component state transitions.

The system is built around the `EventStreamBridge`, an `Actor` that lives inside the `NautilusKernel`, subscribes to `MessageBus` topics, and fans out events to connected WebSocket clients. Each client specifies which event topics it wants to receive, and the bridge handles serialization, backpressure, and connection lifecycle.

## Module Structure

```
nautilus_trader/api/
├── streaming.py       # EventStreamBridge actor + WebSocket handler
└── serialization.py   # Event-to-JSON serialization utilities
```

The WebSocket route is registered with the FastAPI application created in `server.py` (SPEC-001). The `EventStreamBridge` actor is created and added to the kernel during API server startup.

## WebSocket Endpoint

### Connection

- **Path**: `/api/v1/events/stream`
- **Protocol**: Standard WebSocket upgrade over HTTP
- **Authentication**: Same as REST API — `X-Api-Key` passed as query parameter `?api_key=<key>` (headers are not reliably supported in WebSocket handshakes across all clients)
- **Subprotocol**: None required

### Connection Flow

```
Client                                    Server
  |                                         |
  |  GET /api/v1/events/stream?api_key=...  |
  |  Upgrade: websocket                     |
  | ---------------------------------------->|
  |                                         |
  |  101 Switching Protocols                |
  |<---------------------------------------- |
  |                                         |
  |  {"action":"subscribe",                 |
  |   "topics":["events.order.*"]}          |
  | ---------------------------------------->|
  |                                         |
  |  {"type":"subscribed",                  |
  |   "topics":["events.order.*"],          |
  |   "sequence":0}                         |
  |<---------------------------------------- |
  |                                         |
  |  {"type":"OrderFilled","topic":...,     |
  |   "sequence":1,"data":{...}}            |
  |<---------------------------------------- |
  |                                         |
  |  ping                                   |
  |<---------------------------------------- |
  |  pong                                   |
  | ---------------------------------------->|
  |                                         |
```

### Client Messages

Clients send JSON messages to control their subscription.

#### Subscribe

Add topic subscriptions. Can be sent multiple times to add more topics.

```json
{
  "action": "subscribe",
  "topics": ["events.order.*", "events.position.*"]
}
```

#### Unsubscribe

Remove topic subscriptions.

```json
{
  "action": "unsubscribe",
  "topics": ["events.order.*"]
}
```

#### Replay

Request replay of missed events from the ring buffer (see Reconnection section).

```json
{
  "action": "replay",
  "from_sequence": 42
}
```

#### List Subscriptions

Query current subscriptions.

```json
{
  "action": "list_subscriptions"
}
```

Response:
```json
{
  "type": "subscriptions",
  "topics": ["events.order.*", "events.position.*"],
  "sequence": 156
}
```

### Server Messages

All server messages follow the event envelope format (see below), except for control messages:

#### Control Messages

```json
{"type": "subscribed", "topics": ["events.order.*"], "sequence": 0}
{"type": "unsubscribed", "topics": ["events.order.*"], "sequence": 156}
{"type": "subscriptions", "topics": ["events.order.*"], "sequence": 156}
{"type": "error", "message": "Invalid topic pattern: [invalid", "sequence": 156}
{"type": "overflow", "dropped_count": 50, "sequence": 200}
{"type": "replay_complete", "from_sequence": 42, "to_sequence": 155, "count": 113}
```

### Error Handling

| Condition                  | Server Behavior                                           |
|---------------------------|-----------------------------------------------------------|
| Invalid JSON from client  | Send error message, keep connection open                  |
| Unknown action            | Send error message, keep connection open                  |
| Invalid topic pattern     | Send error message, keep connection open                  |
| Client queue overflow     | Drop oldest events, send overflow notification            |
| Server shutdown           | Send close frame with code 1001 (Going Away)              |
| Client sends binary frame | Send error message, keep connection open                  |
| Max clients exceeded      | Reject connection with HTTP 503 before upgrade            |

## EventStreamBridge

### Class Design

`EventStreamBridge` extends `Actor` and is registered with the `NautilusKernel` as a system actor (not user-managed). It bridges the internal `MessageBus` event system with external WebSocket consumers.

```python
class EventStreamBridge(Actor):
    """
    Bridges MessageBus events to WebSocket clients.

    This actor subscribes to all configured MessageBus topic patterns and
    fans out received events to connected WebSocket clients based on their
    individual topic subscriptions.
    """

    def __init__(self, config: EventStreamConfig) -> None: ...

    # Actor lifecycle
    def on_start(self) -> None: ...
    def on_stop(self) -> None: ...

    # Connection management
    async def handle_websocket(self, websocket: WebSocket) -> None: ...

    # Internal
    def _on_event(self, event: Event) -> None: ...
    def _matches_subscription(self, topic: str, patterns: list[str]) -> bool: ...
```

### Configuration

```python
class EventStreamConfig(ActorConfig):
    """Configuration for EventStreamBridge."""

    # Topic patterns to subscribe to on the MessageBus.
    # These define the MAXIMUM set of events available to clients.
    # Individual clients further filter via their subscribe messages.
    source_topics: list[str] = [
        "events.order.*",
        "events.position.*",
        "events.account.*",
        "events.risk.*",
        "events.component.*",
    ]

    # Per-client bounded queue size
    client_queue_size: int = 10_000

    # Maximum concurrent WebSocket clients
    max_clients: int = 10

    # Ping interval in seconds (for connection health)
    ping_interval_seconds: int = 30

    # Number of missed pongs before disconnect
    max_missed_pongs: int = 3

    # Ring buffer size for replay support
    replay_buffer_size: int = 1_000
```

### Startup Behavior

When `on_start()` is called:

1. Subscribe to each pattern in `source_topics` on the `MessageBus`.
2. The handler `_on_event` is registered for each subscription.
3. Initialize the ring buffer for replay support.
4. Log the subscribed topics.

### Event Processing Pipeline

When an event arrives from the `MessageBus`:

1. `_on_event(event)` is called synchronously on the event loop.
2. The event is serialized to JSON using `serialize_event()` (see Serialization section).
3. The serialized event is assigned a monotonically increasing global sequence number.
4. The event is appended to the ring buffer (overwriting oldest if full).
5. For each connected client:
   a. Check if the event's topic matches any of the client's subscription patterns.
   b. If matched, attempt to put the serialized event into the client's `asyncio.Queue`.
   c. If the queue is full, drop the oldest item and enqueue the new event. Increment the client's drop counter.
6. If any client's drop counter crosses a threshold (100 events), send an overflow notification.

### Connection Management

Each connected client is tracked with a `ClientConnection` dataclass:

```python
@dataclass
class ClientConnection:
    websocket: WebSocket
    client_id: str              # Auto-generated UUID
    subscriptions: list[str]    # Topic patterns
    queue: asyncio.Queue        # Bounded event queue
    sequence: int               # Last sent sequence number
    connected_at: float         # Time of connection
    last_pong: float            # Time of last pong received
    dropped_count: int          # Events dropped due to overflow
```

**Connection lifecycle:**

1. Client connects via WebSocket upgrade.
2. If max_clients reached, reject with HTTP 503.
3. Authenticate (if API key configured).
4. Create `ClientConnection` with empty subscription list.
5. Start two concurrent tasks:
   - **Reader task**: Reads client messages (subscribe/unsubscribe/replay).
   - **Writer task**: Dequeues events from the client's queue and sends them.
   - **Ping task**: Sends WebSocket pings at `ping_interval_seconds`.
6. On disconnect (client close, error, or missed pongs), clean up the connection.

```python
async def handle_websocket(self, websocket: WebSocket) -> None:
    """Handle a single WebSocket connection lifecycle."""
    if len(self._clients) >= self._config.max_clients:
        await websocket.close(code=1013, reason="Max clients reached")
        return

    await websocket.accept()
    client = ClientConnection(
        websocket=websocket,
        client_id=str(uuid.uuid4()),
        subscriptions=[],
        queue=asyncio.Queue(maxsize=self._config.client_queue_size),
        sequence=0,
        connected_at=time.time(),
        last_pong=time.time(),
        dropped_count=0,
    )
    self._clients[client.client_id] = client

    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(self._reader_loop(client))
            tg.create_task(self._writer_loop(client))
            tg.create_task(self._ping_loop(client))
    except* WebSocketDisconnect:
        pass
    finally:
        del self._clients[client.client_id]
```

## Event Envelope Format

Every event sent to clients is wrapped in a standard envelope:

```json
{
  "type": "OrderFilled",
  "topic": "events.order.filled",
  "ts_event": 1700003600000000000,
  "ts_event_iso": "2023-11-14T23:13:20.000000000Z",
  "ts_init": 1700003600000000000,
  "ts_init_iso": "2023-11-14T23:13:20.000000000Z",
  "sequence": 42,
  "data": {
    "trader_id": "TRADER-001",
    "strategy_id": "EMACross-001",
    "instrument_id": "BTCUSDT-PERP.BINANCE",
    "client_order_id": "O-20231114-001",
    "venue_order_id": "123456789",
    "order_side": "BUY",
    "order_type": "LIMIT",
    "last_qty": "0.01",
    "last_px": "42000.00",
    "currency": "USDT",
    "commission": "0.42",
    "liquidity_side": "MAKER"
  }
}
```

| Field          | Type      | Description                                            |
|----------------|-----------|--------------------------------------------------------|
| `type`         | `string`  | Event class name (e.g., `OrderFilled`, `PositionOpened`) |
| `topic`        | `string`  | MessageBus topic the event was published on            |
| `ts_event`     | `integer` | Event timestamp in nanoseconds since Unix epoch        |
| `ts_event_iso` | `string`  | Event timestamp as ISO 8601 string (nanosecond precision) |
| `ts_init`      | `integer` | Event initialization timestamp in nanoseconds          |
| `ts_init_iso`  | `string`  | Initialization timestamp as ISO 8601 string            |
| `sequence`     | `integer` | Monotonically increasing sequence number per connection |
| `data`         | `object`  | Event-specific data from `event.to_dict()`             |

### Sequence Numbers

- Sequence numbers are **per-connection**, starting at 1 for the first event.
- Control messages also carry a sequence number but do NOT increment it — they report the current sequence.
- Sequence numbers are used by clients for replay requests and gap detection.

## Supported Event Types

### Order Events

All order events inherit from `OrderEvent`. The `data` field contains the event's `to_dict()` output.

| Event Type          | Topic                      | Key Fields in `data`                              |
|---------------------|----------------------------|---------------------------------------------------|
| `OrderInitialized`  | `events.order.initialized` | `instrument_id`, `order_side`, `order_type`, `quantity`, `price`, `time_in_force` |
| `OrderSubmitted`    | `events.order.submitted`   | `client_order_id`, `account_id`                   |
| `OrderAccepted`     | `events.order.accepted`    | `client_order_id`, `venue_order_id`               |
| `OrderRejected`     | `events.order.rejected`    | `client_order_id`, `reason`                       |
| `OrderCanceled`     | `events.order.canceled`    | `client_order_id`, `venue_order_id`               |
| `OrderExpired`      | `events.order.expired`     | `client_order_id`, `venue_order_id`               |
| `OrderTriggered`    | `events.order.triggered`   | `client_order_id`, `venue_order_id`               |
| `OrderFilled`       | `events.order.filled`      | `client_order_id`, `venue_order_id`, `last_qty`, `last_px`, `commission`, `liquidity_side` |
| `OrderUpdated`      | `events.order.updated`     | `client_order_id`, `venue_order_id`, `quantity`, `price` |

### Position Events

| Event Type        | Topic                        | Key Fields in `data`                              |
|-------------------|------------------------------|---------------------------------------------------|
| `PositionOpened`  | `events.position.opened`     | `instrument_id`, `entry`, `side`, `quantity`, `avg_px_open`, `currency` |
| `PositionChanged` | `events.position.changed`    | `instrument_id`, `side`, `quantity`, `avg_px_open`, `unrealized_pnl`, `realized_pnl` |
| `PositionClosed`  | `events.position.closed`     | `instrument_id`, `side`, `avg_px_open`, `avg_px_close`, `realized_pnl`, `duration_ns` |

### Account Events

| Event Type     | Topic                     | Key Fields in `data`                               |
|----------------|---------------------------|---------------------------------------------------|
| `AccountState` | `events.account.state`    | `account_id`, `account_type`, `balances`, `margins`, `is_reported` |

### Risk Events

| Event Type            | Topic                         | Key Fields in `data`                   |
|-----------------------|-------------------------------|---------------------------------------|
| `TradingStateChanged` | `events.risk.trading_state`   | `state` (ACTIVE, REDUCING, HALTED)    |

### Component Events

| Event Type              | Topic                          | Key Fields in `data`                   |
|-------------------------|--------------------------------|---------------------------------------|
| `ComponentStateChanged` | `events.component.state`       | `component_id`, `component_type`, `state_from`, `state_to` |

### Custom / Data Events

Market data and custom events can also be streamed using `data.*` topic patterns:

| Topic Pattern             | Description                        | Key Fields in `data`                    |
|---------------------------|------------------------------------|-----------------------------------------|
| `data.quotes.{venue}.*`   | Quote ticks by venue               | `instrument_id`, `bid_price`, `ask_price`, `bid_size`, `ask_size` |
| `data.trades.{venue}.*`   | Trade ticks by venue               | `instrument_id`, `price`, `size`, `aggressor_side`, `trade_id` |
| `data.bars.*`             | Bar data                           | `bar_type`, `open`, `high`, `low`, `close`, `volume` |
| `data.custom.*`           | User-defined custom data           | Varies                                  |

Note: Data events (quotes, trades, bars) generate high volume. Clients subscribing to these topics should be prepared for significant throughput and should use appropriate backpressure handling.

## Topic Filter Syntax

Topic filters use the same wildcard convention as the NautilusTrader `MessageBus`:

| Pattern                       | Matches                                           |
|-------------------------------|---------------------------------------------------|
| `events.*`                    | All events                                        |
| `events.order.*`              | All order events                                  |
| `events.order.filled`         | Only OrderFilled events                           |
| `events.position.*`           | All position events                               |
| `events.account.*`            | All account events                                |
| `data.*`                      | All data events (quotes, trades, bars)            |
| `data.quotes.*`               | All quotes across all venues                      |
| `data.quotes.BINANCE.*`       | All Binance quotes                                |
| `data.quotes.BINANCE.BTCUSDT` | Quotes for a specific instrument on Binance       |
| `*`                           | Everything (use with caution)                     |

### Pattern Matching Implementation

```python
def _matches_subscription(self, topic: str, patterns: list[str]) -> bool:
    """Check if a topic matches any of the subscription patterns."""
    for pattern in patterns:
        if pattern == "*":
            return True
        if pattern == topic:
            return True
        if pattern.endswith(".*"):
            prefix = pattern[:-2]
            if topic.startswith(prefix + ".") or topic == prefix:
                return True
    return False
```

Topics are matched using prefix matching with `.*` as the wildcard suffix. This is intentionally simple and aligns with how `MessageBus` topics work in NautilusTrader.

## Backpressure

### Per-Client Bounded Queue

Each client has an `asyncio.Queue` with a configurable maximum size (default: 10,000 events). This decouples event production (MessageBus handler) from consumption (WebSocket send).

**Overflow policy:** When a client's queue is full:

1. The oldest event is removed from the queue (`queue.get_nowait()`).
2. The new event is enqueued.
3. The client's `dropped_count` is incremented.
4. When `dropped_count` reaches a notification threshold (every 100 drops), an overflow notification is enqueued:

```json
{
  "type": "overflow",
  "dropped_count": 100,
  "sequence": 500,
  "message": "100 events dropped due to slow consumption. Consider reducing subscription scope."
}
```

### Client Health Monitoring

WebSocket ping/pong frames are used to detect stale connections:

1. Server sends a WebSocket ping every `ping_interval_seconds` (default: 30s).
2. Server tracks the time of the last received pong.
3. If `max_missed_pongs` (default: 3) consecutive pings receive no pong, the connection is forcibly closed.
4. This prevents resource leaks from clients that disconnect without sending a close frame.

```python
async def _ping_loop(self, client: ClientConnection) -> None:
    """Send periodic pings and monitor for missed pongs."""
    while True:
        await asyncio.sleep(self._config.ping_interval_seconds)
        elapsed = time.time() - client.last_pong
        if elapsed > self._config.ping_interval_seconds * self._config.max_missed_pongs:
            self._log.warning(f"Client {client.client_id} missed {self._config.max_missed_pongs} pongs, disconnecting")
            await client.websocket.close(code=1001, reason="Ping timeout")
            return
        await client.websocket.ping()
```

### Max Clients

The server enforces a maximum number of concurrent WebSocket connections (default: 10). When the limit is reached, new connections are rejected before the WebSocket upgrade with an HTTP 503 response. This prevents resource exhaustion from excessive concurrent consumers.

## Reconnection and Replay

### Ring Buffer

The `EventStreamBridge` maintains a ring buffer of the last N events (configurable, default: 1,000). Each event in the buffer retains its global sequence number.

```python
class EventRingBuffer:
    """Fixed-size ring buffer for event replay."""

    def __init__(self, capacity: int) -> None:
        self._buffer: list[dict] = [None] * capacity
        self._capacity = capacity
        self._write_pos: int = 0
        self._count: int = 0

    def append(self, event: dict) -> None: ...
    def get_from_sequence(self, sequence: int) -> list[dict]: ...

    @property
    def oldest_sequence(self) -> int | None: ...

    @property
    def newest_sequence(self) -> int | None: ...
```

### Replay Protocol

When a client reconnects and needs to catch up on missed events:

1. Client connects and subscribes to desired topics.
2. Client sends a replay request:

```json
{
  "action": "replay",
  "from_sequence": 42
}
```

3. Server checks if sequence 42 is within the ring buffer window.
4. If yes: server sends all events from sequence 42 to current, filtered by the client's active subscriptions:

```json
{"type": "OrderFilled", "topic": "events.order.filled", "sequence": 42, "data": {...}}
{"type": "OrderFilled", "topic": "events.order.filled", "sequence": 43, "data": {...}}
...
{"type": "replay_complete", "from_sequence": 42, "to_sequence": 155, "count": 113}
```

5. If no (sequence too old / outside buffer window): server sends an error:

```json
{
  "type": "error",
  "message": "Sequence 42 is outside the replay buffer window. Oldest available: 500",
  "sequence": 656
}
```

6. After replay, the client continues receiving live events normally.

**Important:** Replay events are filtered through the client's current subscription patterns. Events in the buffer that don't match the client's subscriptions are skipped.

### Client-Side Recommendations

Clients should implement the following reconnection strategy:

1. Track the last received sequence number.
2. On disconnect, attempt reconnection with exponential backoff (1s, 2s, 4s, 8s, max 30s).
3. After reconnecting, re-subscribe to the same topics.
4. Send a replay request with `from_sequence = last_received_sequence + 1`.
5. If replay fails (sequence too old), the client must re-sync state by querying the REST API.

## Serialization

### `serialization.py`

Provides utilities for converting NautilusTrader domain objects to JSON-serializable dictionaries.

```python
def serialize_event(event: Event, topic: str, sequence: int) -> dict:
    """
    Serialize a NautilusTrader event to an event envelope dict.

    Parameters
    ----------
    event : Event
        The event to serialize.
    topic : str
        The MessageBus topic the event was published on.
    sequence : int
        The sequence number for this event.

    Returns
    -------
    dict
        JSON-serializable event envelope.
    """
```

### Serialization Rules

1. **Primary method**: Call `event.to_dict()` if available. This is the canonical serialization for all Cython domain objects.

2. **Fallback**: If `to_dict()` is not available or raises an error, use `str(event)` and wrap it:
   ```json
   {"type": "Unknown", "topic": "...", "data": {"repr": "Event(...)"}}
   ```

3. **Timestamp handling**:
   - Raw nanosecond timestamps are preserved as integers (`ts_event`, `ts_init`).
   - ISO 8601 string representations are added alongside (`ts_event_iso`, `ts_init_iso`).
   - Conversion uses `pandas.Timestamp` or manual arithmetic for nanosecond precision.

4. **Decimal values**: Serialized as strings to preserve precision. This applies to prices, quantities, P&L values, and commission amounts. Example: `"42150.50"` not `42150.5`.

5. **Enum values**: Serialized as their string names. Example: `"BUY"` not `1`.

6. **Identifiers**: All NautilusTrader identifiers (`TraderId`, `StrategyId`, `InstrumentId`, etc.) are serialized as their string values.

7. **None values**: Omitted from the output dictionary (not serialized as `null`), except where their absence would be semantically confusing (e.g., `venue_order_id` on a submitted but not yet accepted order is included as `null`).

### Performance Considerations

- Serialization happens on the event loop thread. For high-throughput data events (quotes, trades), this can become a bottleneck.
- Mitigation: the serialization result is computed once and shared across all clients (not serialized per-client).
- The `to_dict()` method on Cython objects is generally fast (microseconds), but `json.dumps()` adds overhead.
- For data events, consider using `orjson` for faster JSON serialization (~5x faster than stdlib `json`).
- If serialization latency becomes a problem, consider moving serialization to a separate thread using `asyncio.to_thread()`, though this adds complexity around thread-safe access to Cython objects.
