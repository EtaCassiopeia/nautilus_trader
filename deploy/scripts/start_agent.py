#!/usr/bin/env python3
# -------------------------------------------------------------------------------------------------
#  Start the AI Agent orchestrator against a running NautilusTrader node.
#
#  Usage:
#    python deploy/scripts/start_agent.py                        # MONITOR mode (default)
#    python deploy/scripts/start_agent.py --mode ADVISORY
#    python deploy/scripts/start_agent.py --mode SEMI_AUTONOMOUS
#    python deploy/scripts/start_agent.py --mode AUTONOMOUS      # Full auto (use with caution)
# -------------------------------------------------------------------------------------------------

import argparse
import asyncio
import logging
import os
import sys

from nautilus_trader.agent.config import AgentConfig
from nautilus_trader.agent.config import GuardrailConfig
from nautilus_trader.agent.orchestrator import AgentOrchestrator


def parse_args():
    parser = argparse.ArgumentParser(description="NautilusTrader AI Agent")
    parser.add_argument(
        "--mode",
        choices=["MONITOR", "ADVISORY", "SEMI_AUTONOMOUS", "AUTONOMOUS"],
        default="MONITOR",
        help="Agent operating mode (default: MONITOR)",
    )
    parser.add_argument(
        "--api-url",
        default=os.environ.get("NAUTILUS_API_URL", "http://localhost:8001"),
        help="NautilusTrader API URL",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("NAUTILUS_API_KEY"),
        help="API key for authentication",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("AGENT_MODEL", "claude-sonnet-4-20250514"),
        help="Claude model for reasoning",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=5.0,
        help="Decision cycle interval in seconds (default: 5)",
    )
    parser.add_argument(
        "--max-order-size",
        default=None,
        help="Maximum single order size (decimal string)",
    )
    parser.add_argument(
        "--max-daily-loss",
        default=None,
        help="Daily loss limit to trigger kill switch (decimal string, e.g. '-5000')",
    )
    return parser.parse_args()


async def main():
    args = parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    guardrails = GuardrailConfig(
        max_single_order_size=args.max_order_size,
        max_daily_loss=args.max_daily_loss,
        max_orders_per_minute=10,
    )

    config = AgentConfig(
        mode=args.mode,
        api_url=args.api_url,
        api_key=args.api_key,
        model=args.model,
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
        event_batch_interval_secs=args.interval,
        guardrails=guardrails,
    )

    agent = AgentOrchestrator(config)

    try:
        await agent.start()
        print(f"Agent running in {args.mode} mode — Ctrl+C to stop")
        await agent.run_loop()
    except KeyboardInterrupt:
        print("\nShutting down agent...")
    finally:
        await agent.stop()


if __name__ == "__main__":
    asyncio.run(main())
