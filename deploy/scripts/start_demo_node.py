#!/usr/bin/env python3
# -------------------------------------------------------------------------------------------------
#  Demo node that starts NautilusTrader with the API server enabled
#  but no exchange adapters. Useful for testing the control plane locally.
#
#  To connect a real exchange, use deploy/configs/node.json instead.
# -------------------------------------------------------------------------------------------------

import os

from nautilus_trader.api.config import ApiServerConfig
from nautilus_trader.api.config import EventStreamConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.config import TradingNodeConfig
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.identifiers import TraderId


def main():
    trader_id = os.environ.get("NAUTILUS_TRADER_ID", "TRADER-001")
    api_host = os.environ.get("NAUTILUS_API_HOST", "0.0.0.0")
    api_port = int(os.environ.get("NAUTILUS_API_PORT", "8001"))
    api_key = os.environ.get("NAUTILUS_API_KEY") or None

    config = TradingNodeConfig(
        trader_id=TraderId(trader_id),
        logging=LoggingConfig(
            log_level="INFO",
            log_level_file="DEBUG",
        ),
        api_server=ApiServerConfig(
            enabled=True,
            host=api_host,
            port=api_port,
            api_key=api_key,
            cors_origins=["*"],
            event_stream=EventStreamConfig(
                max_clients=10,
                replay_buffer_size=1_000,
            ),
        ),
    )

    node = TradingNode(config=config)
    node.build()

    try:
        print(f"NautilusTrader node starting — API on {api_host}:{api_port}")
        node.run()
    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        node.stop()
        node.dispose()


if __name__ == "__main__":
    main()
