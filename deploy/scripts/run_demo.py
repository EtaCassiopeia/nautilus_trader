#!/usr/bin/env python3
# -------------------------------------------------------------------------------------------------
#  Demo: Start NautilusTrader with the API server — no exchange keys required.
#
#  This starts a live node in "demo" mode with the API server enabled.
#  No exchange adapters are connected, but you can interact with the API,
#  add strategies, and test the control plane.
#
#  Usage:
#    uv run python deploy/scripts/run_demo.py
#
#  Then try:
#    curl http://localhost:8001/health
#    curl http://localhost:8001/api/v1/node/status
#    curl http://localhost:8001/api/v1/strategies
#    curl http://localhost:8001/api/v1/portfolio
# -------------------------------------------------------------------------------------------------

from nautilus_trader.api.config import ApiServerConfig
from nautilus_trader.api.config import EventStreamConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.config import TradingNodeConfig
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.identifiers import TraderId


def main():
    config = TradingNodeConfig(
        trader_id=TraderId("DEMO-001"),
        logging=LoggingConfig(
            log_level="INFO",
        ),
        api_server=ApiServerConfig(
            enabled=True,
            host="0.0.0.0",
            port=8001,
            cors_origins=["*"],
            event_stream=EventStreamConfig(
                max_clients=10,
                replay_buffer_size=1_000,
            ),
        ),
    )

    node = TradingNode(config=config)
    node.build()

    print()
    print("=" * 60)
    print("  NautilusTrader Demo Node")
    print("  Trader:  DEMO-001")
    print("  API:     http://localhost:8001")
    print("  Docs:    http://localhost:8001/docs")
    print("  Health:  http://localhost:8001/health")
    print()
    print("  No exchange adapters — API-only for testing.")
    print("  Press Ctrl+C to stop.")
    print("=" * 60)
    print()

    try:
        node.run()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        node.stop()
        node.dispose()


if __name__ == "__main__":
    main()
