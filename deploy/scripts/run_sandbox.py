#!/usr/bin/env python3
# -------------------------------------------------------------------------------------------------
#  Run NautilusTrader with Binance testnet and a simple EMA cross strategy.
#
#  Prerequisites:
#    - Redis running (docker compose -f deploy/docker-compose.dev.yml up -d redis)
#    - BINANCE_API_KEY and BINANCE_API_SECRET env vars set (testnet keys)
#
#  Get testnet keys at: https://testnet.binance.vision/
#
#  Usage:
#    uv run python deploy/scripts/run_sandbox.py
# -------------------------------------------------------------------------------------------------

import os
import sys
from decimal import Decimal

# Check for API keys early
if not os.environ.get("BINANCE_API_KEY") or not os.environ.get("BINANCE_API_SECRET"):
    print("=" * 60)
    print("BINANCE_API_KEY and BINANCE_API_SECRET must be set.")
    print()
    print("Get free testnet keys at: https://testnet.binance.vision/")
    print()
    print("Then run:")
    print("  export BINANCE_API_KEY=your_key")
    print("  export BINANCE_API_SECRET=your_secret")
    print("  uv run python deploy/scripts/run_sandbox.py")
    print("=" * 60)
    sys.exit(1)

from nautilus_trader.adapters.binance import BINANCE
from nautilus_trader.adapters.binance import BinanceAccountType
from nautilus_trader.adapters.binance import BinanceDataClientConfig
from nautilus_trader.adapters.binance import BinanceExecClientConfig
from nautilus_trader.adapters.binance import BinanceLiveDataClientFactory
from nautilus_trader.adapters.binance import BinanceLiveExecClientFactory
from nautilus_trader.api.config import ApiServerConfig
from nautilus_trader.api.config import EventStreamConfig
from nautilus_trader.config import InstrumentProviderConfig
from nautilus_trader.config import LiveExecEngineConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.config import TradingNodeConfig
from nautilus_trader.examples.strategies.ema_cross import EMACross
from nautilus_trader.examples.strategies.ema_cross import EMACrossConfig
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import TraderId


def main():
    symbol = os.environ.get("SYMBOL", "BTCUSDT")
    instrument_id = InstrumentId.from_str(f"{symbol}.BINANCE")

    config_node = TradingNodeConfig(
        trader_id=TraderId("SANDBOX-001"),
        logging=LoggingConfig(
            log_level="INFO",
            log_level_file="DEBUG",
        ),
        exec_engine=LiveExecEngineConfig(
            reconciliation=False,
        ),
        data_clients={
            BINANCE: BinanceDataClientConfig(
                api_key=None,  # reads BINANCE_API_KEY env var
                api_secret=None,  # reads BINANCE_API_SECRET env var
                account_type=BinanceAccountType.SPOT,
                testnet=True,
                instrument_provider=InstrumentProviderConfig(load_all=True),
            ),
        },
        exec_clients={
            BINANCE: BinanceExecClientConfig(
                api_key=None,
                api_secret=None,
                account_type=BinanceAccountType.SPOT,
                testnet=True,
                instrument_provider=InstrumentProviderConfig(load_all=True),
                max_retries=3,
            ),
        },
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
        timeout_connection=30.0,
        timeout_reconciliation=10.0,
        timeout_portfolio=10.0,
        timeout_disconnection=10.0,
        timeout_post_stop=5.0,
    )

    node = TradingNode(config=config_node)

    # Add data client and exec client factories
    node.add_data_client_factory(BINANCE, BinanceLiveDataClientFactory)
    node.add_exec_client_factory(BINANCE, BinanceLiveExecClientFactory)

    # Configure EMA cross strategy
    strategy_config = EMACrossConfig(
        instrument_id=instrument_id,
        bar_type=f"{instrument_id}-1-MINUTE-LAST-EXTERNAL",
        fast_ema_period=10,
        slow_ema_period=20,
        trade_size=Decimal("0.001"),  # Small size for testnet
        order_id_tag="001",
    )
    strategy = EMACross(config=strategy_config)
    node.trader.add_strategy(strategy)

    node.build()

    print()
    print("=" * 60)
    print(f"  NautilusTrader Sandbox")
    print(f"  Trader:     SANDBOX-001")
    print(f"  Exchange:   Binance Spot (testnet)")
    print(f"  Symbol:     {symbol}")
    print(f"  Strategy:   EMA Cross (10/20)")
    print(f"  API:        http://localhost:8001")
    print(f"  Docs:       http://localhost:8001/docs")
    print(f"  Health:     http://localhost:8001/health")
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
