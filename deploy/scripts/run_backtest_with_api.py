#!/usr/bin/env python3
# -------------------------------------------------------------------------------------------------
#  Backtest: EMA Cross strategy on ETHUSDT with simulated trades.
#
#  No exchange keys required — uses bundled test data.
#  Demonstrates strategies generating buy/sell signals, order fills,
#  and position management.
#
#  Usage:
#    uv run python deploy/scripts/run_backtest_with_api.py
# -------------------------------------------------------------------------------------------------

import time
from decimal import Decimal

import pandas as pd

from nautilus_trader.adapters.binance import BINANCE_VENUE
from nautilus_trader.backtest.config import BacktestEngineConfig
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.config import LoggingConfig
from nautilus_trader.examples.strategies.ema_cross import EMACross
from nautilus_trader.examples.strategies.ema_cross import EMACrossConfig
from nautilus_trader.model.currencies import ETH
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import AccountType
from nautilus_trader.model.enums import BookType
from nautilus_trader.model.enums import OmsType
from nautilus_trader.model.identifiers import TraderId
from nautilus_trader.model.objects import Money
from nautilus_trader.persistence.wranglers import TradeTickDataWrangler
from nautilus_trader.test_kit.providers import TestDataProvider
from nautilus_trader.test_kit.providers import TestInstrumentProvider


def main():
    # ── Configure engine ─────────────────────────────────────────────
    engine = BacktestEngine(
        config=BacktestEngineConfig(
            trader_id=TraderId("BACKTESTER-001"),
            logging=LoggingConfig(
                log_level="INFO",
                log_colors=True,
                use_pyo3=False,
            ),
        ),
    )

    # ── Add venue with starting balances ─────────────────────────────
    engine.add_venue(
        venue=BINANCE_VENUE,
        oms_type=OmsType.NETTING,
        book_type=BookType.L1_MBP,
        account_type=AccountType.CASH,
        base_currency=None,
        starting_balances=[Money(1_000_000.0, USDT), Money(10.0, ETH)],
        trade_execution=True,
    )

    # ── Add instrument ───────────────────────────────────────────────
    ETHUSDT = TestInstrumentProvider.ethusdt_binance()
    engine.add_instrument(ETHUSDT)

    # ── Load tick data and wrangle ───────────────────────────────────
    provider = TestDataProvider()
    wrangler = TradeTickDataWrangler(instrument=ETHUSDT)
    ticks = wrangler.process(provider.read_csv_ticks("binance/ethusdt-trades.csv"))
    engine.add_data(ticks)

    # ── Configure EMA cross strategy ─────────────────────────────────
    strategy = EMACross(
        config=EMACrossConfig(
            instrument_id=ETHUSDT.id,
            bar_type=BarType.from_str("ETHUSDT.BINANCE-250-TICK-LAST-INTERNAL"),
            fast_ema_period=10,
            slow_ema_period=20,
            trade_size=Decimal("0.10"),
            order_id_tag="001",
        ),
    )
    engine.add_strategy(strategy)

    # ── Run ──────────────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("  NautilusTrader Backtest — Crypto EMA Cross")
    print(f"  Trader:      BACKTESTER-001")
    print(f"  Venue:       BINANCE (simulated)")
    print(f"  Instrument:  ETHUSDT")
    print(f"  Strategy:    EMA Cross (fast=10, slow=20, 250-tick bars)")
    print(f"  Trade Size:  0.10 ETH per signal")
    print(f"  Capital:     1,000,000 USDT + 10 ETH")
    print(f"  Data:        {len(ticks):,} trade ticks")
    print("=" * 70)
    print()

    t0 = time.time()
    engine.run()
    elapsed = time.time() - t0

    # ── Results ──────────────────────────────────────────────────────
    print()
    print("=" * 70)
    print(f"  Backtest Complete ({elapsed:.1f}s)")
    print("=" * 70)

    with pd.option_context(
        "display.max_rows", 100,
        "display.max_columns", None,
        "display.width", 200,
    ):
        print("\n--- Account Report ---")
        print(engine.trader.generate_account_report(BINANCE_VENUE))

        fills = engine.trader.generate_order_fills_report()
        print(f"\n--- Order Fills ({len(fills)}) ---")
        print(fills)

        positions = engine.trader.generate_positions_report()
        print(f"\n--- Positions ({len(positions)}) ---")
        print(positions)

    engine.reset()
    engine.dispose()


if __name__ == "__main__":
    main()
