# ADR-002: Real-Time Event Streaming via WebSocket

| Field       | Value                                      |
|-------------|--------------------------------------------|
| **Status**  | Proposed                                   |
| **Date**    | 2026-03-21                                 |
| **Authors** | Mohsen Zainalpour                          |
| **Depends** | ADR-001 (API Server)                       |
| **Relates** | ADR-003, ADR-005                           |

## Context

NautilusTrader generates a rich stream of events during trading operations: order lifecycle events (submitted, accepted, filled, canceled, rejected), position changes (opened, changed, closed), risk alerts, component state changes, and market data updates. These events flow through the internal `MessageBus` (`nautilus_trader/common/component.pyx`), which supports pub/sub with wildcard topic patterns (`*` for one or more characters, `?` for a single character).

**Currently, events are only observable in-process.** A strategy can subscribe to MessageBus topics via `self.msgbus.subscribe(topic, handler)`, but no mechanism exists for external consumers to receive events in real-time.

The `MessageBus` already supports an optional Redis backing (`RedisMessageBusDatabase`) for cross-node streaming via the `external_streams` config, and `TradingNode` has a `publish_bus_message()` method and `_stream_processors` list. However, this Redis-based approach is designed for node-to-node communication, not for lightweight external API consumers like AI agents, dashboards, or monitoring tools.

AI agent integration (ADR-005) requires real-time event access to enable event-driven reasoning: an agent must know when orders fill, positions change, or risk thresholds are breached in order to make timely decisions. Polling the REST API (ADR-001) is insufficient for latency-sensitive reactions.

### Event Types in the System

| Category        | Event Types                                                                         |
|-----------------|------------------------------------------------------------------------------------- |
| **Order**       | OrderInitialized, OrderSubmitted, OrderAccepted, OrderRejected, OrderCanceled, OrderExpired, OrderTriggered, OrderFilled, OrderUpdated |
| **Position**    | PositionOpened, PositionChanged, PositionClosed                                      |
| **Account**     | AccountState                                                                         |
| **Risk**        | TradingStateChanged, RiskEvent                                                       |
| **Component**   | ComponentStateChanged                                                                |
| **Time**        | TimeEvent                                                                            |
| **Custom**      | Any user-defined events published to `data.*` or custom topics                       |

## Decision

**Add a WebSocket endpoint to the embedded API server (ADR-001) that streams MessageBus events to external consumers in real-time as JSON.**

The implementation consists of:

1. **`EventStreamBridge`** — A new `Actor` that subscribes to configurable MessageBus topics and forwards events to connected WebSocket clients.
2. **WebSocket endpoint** at `/api/v1/events/stream` on the API server.
3. **Per-client subscription filtering** — Clients specify which topic patterns they want after connecting.
4. **Per-client bounded queues** with backpressure handling to prevent slow consumers from affecting the trading engine.

### EventStreamBridge Architecture

```
MessageBus                     EventStreamBridge (Actor)              WebSocket Clients
┌──────────┐                  ┌─────────────────────────┐           ┌──────────────┐
│ publish() │──topic match──▶ │ on_event() handler      │           │  Client A    │
│           │                 │   ├─ serialize to JSON   │──push──▶ │  (filter: *) │
│           │                 │   ├─ assign sequence #   │           ├──────────────┤
│           │                 │   ├─ store in ring buf   │           │  Client B    │
│           │                 │   └─ enqueue per-client  │──push──▶ │  (filter:    │
│           │                 │                          │           │  order.*)    │
└──────────┘                  │ manage_connections()     │           ├──────────────┤
                              │   ├─ accept new clients  │           │  Client C    │
                              │   ├─ handle disconnects  │──push──▶ │  (filter:    │
                              │   └─ ping/pong health    │           │  position.*) │
                              └─────────────────────────┘           └──────────────┘
```

The `EventStreamBridge` is registered as an `Actor` within the `NautilusKernel`, giving it access to the `MessageBus`, `Cache`, and `Clock` through standard lifecycle management.

### Event Envelope Format

All events are wrapped in a standard JSON envelope:

```json
{
  "type": "OrderFilled",
  "topic": "events.order.filled",
  "ts_event": 1711036800000000000,
  "ts_init": 1711036800000000000,
  "ts_server": "2026-03-21T12:00:00.000000Z",
  "sequence": 42,
  "data": {
    "trader_id": "TRADER-001",
    "strategy_id": "EMACross-001",
    "instrument_id": "BTCUSDT-PERP.BINANCE",
    "client_order_id": "O-20260321-001",
    "venue_order_id": "B-123456",
    "side": "BUY",
    "order_type": "MARKET",
    "last_qty": "0.100",
    "last_px": "67450.50",
    "currency": "USDT",
    "commission": "3.37",
    "liquidity_side": "TAKER"
  }
}
```

| Field        | Type    | Description                                           |
|------------- |---------|-------------------------------------------------------|
| `type`       | string  | Event class name                                      |
| `topic`      | string  | MessageBus topic the event was published on           |
| `ts_event`   | integer | Event timestamp in nanoseconds                        |
| `ts_init`    | integer | Object initialization timestamp in nanoseconds        |
| `ts_server`  | string  | Server timestamp in ISO 8601 (for human readability)  |
| `sequence`   | integer | Monotonically increasing per-connection sequence number|
| `data`       | object  | Event-specific payload from `to_dict()`               |

### Topic Filtering

After connecting, clients send a subscription message to specify their topic filters:

```json
{"action": "subscribe", "topics": ["events.order.*", "events.position.*"]}
```

Clients can update their subscription at any time:

```json
{"action": "subscribe", "topics": ["events.*"]}
```

To subscribe to everything:

```json
{"action": "subscribe", "topics": ["*"]}
```

Topic patterns follow the same wildcard syntax as the `MessageBus`: `*` matches one or more characters, `?` matches exactly one character.

### Backpressure

Slow consumers must not degrade the trading engine's performance:

- **Per-client bounded queue**: Each connected client has an `asyncio.Queue` with configurable max size (default: 10,000 events).
- **Overflow policy**: When a client's queue is full, the oldest events are dropped and a synthetic `EventStreamOverflow` event is injected:
  ```json
  {"type": "EventStreamOverflow", "topic": "system.stream", "data": {"dropped_count": 157, "reason": "client_queue_full"}}
  ```
- **Client health**: The server sends WebSocket ping frames every 30 seconds. If 3 consecutive pongs are missed, the client is disconnected.
- **Max clients**: Configurable limit on concurrent WebSocket connections (default: 10).

### Reconnection Replay

To support brief disconnections without losing events:

- **Ring buffer**: The `EventStreamBridge` maintains a fixed-size ring buffer of the most recent N events (configurable, default: 1,000).
- **Replay protocol**: After reconnecting, a client can request replay from a specific sequence number:
  ```json
  {"action": "replay", "from_sequence": 385}
  ```
- **Replay response**: The server sends all buffered events with sequence numbers >= `from_sequence`, followed by a resume marker, then continues with live events.
- **Out-of-range**: If the requested sequence is outside the buffer window, the server sends a `ReplayUnavailable` event and begins streaming from the current position.

### Serialization

- **Primary**: Domain objects serialized via their `to_dict()` method (most Cython objects already implement this).
- **Fallback**: Objects without `to_dict()` are serialized via `str()` representation, wrapped as `{"__str__": "..."}`.
- **Numeric precision**: `Decimal` and `Price`/`Quantity` values are serialized as strings to preserve precision.
- **Timestamps**: Raw nanosecond integers in `ts_event`/`ts_init`, plus ISO 8601 string in `ts_server`.

## Consequences

### Positive

- **Real-time observability**: External tools can monitor all trading activity as it happens.
- **AI agent event-driven control**: The agent orchestration loop (ADR-005) can react to events immediately rather than polling.
- **Decoupled consumers**: WebSocket clients are fully decoupled from the trading engine — connecting or disconnecting clients has zero impact on trading.
- **Topic filtering**: Clients receive only the events they care about, reducing bandwidth and processing overhead.
- **Reconnection support**: Brief network interruptions don't cause event loss for clients.

### Negative

- **Serialization overhead**: Every event matching a subscription must be serialized to JSON. For high-frequency market data events, this can be significant. Mitigation: clients should subscribe to specific topics rather than `*`.
- **Memory for client queues**: Each client queue consumes memory (bounded by `max_queue_size`). With 10 clients and 10,000 events each, this is manageable.
- **Client lifecycle management**: The server must handle connection failures, slow clients, and stale connections gracefully.
- **Not a full event store**: The ring buffer provides limited replay. For full event replay, clients should use the Redis-backed MessageBus or a dedicated event store.

### Neutral

- The `EventStreamBridge` follows the existing `Actor` pattern, so it integrates naturally with NautilusTrader's lifecycle management.
- WebSocket is a well-understood protocol with broad client library support across all languages.
