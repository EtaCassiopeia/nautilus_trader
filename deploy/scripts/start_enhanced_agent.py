#!/usr/bin/env python3
# -------------------------------------------------------------------------------------------------
#  Start the Enhanced Multi-Agent AI Trading Orchestrator.
#
#  Architecture:
#    Events → Analyst Team (parallel) → Bull/Bear Debate → Risk Team → Portfolio Manager
#
#  Usage:
#    python deploy/scripts/start_enhanced_agent.py --mode MONITOR
#    python deploy/scripts/start_enhanced_agent.py --mode ADVISORY
#    python deploy/scripts/start_enhanced_agent.py --mode SEMI_AUTONOMOUS \
#        --max-order-size 0.1 --max-daily-loss -1000
#    python deploy/scripts/start_enhanced_agent.py --mode AUTONOMOUS \
#        --debate-rounds 3 --analysts technical,sentiment,risk
# -------------------------------------------------------------------------------------------------

import argparse
import asyncio
import logging
import os
import sys

from nautilus_trader.agent.config import EnhancedAgentConfig
from nautilus_trader.agent.config import GuardrailConfig
from nautilus_trader.agent.config import ModelConfig
from nautilus_trader.agent.enhanced_orchestrator import EnhancedOrchestrator


def parse_args():
    parser = argparse.ArgumentParser(description="NautilusTrader Enhanced AI Agent")
    parser.add_argument(
        "--mode",
        choices=["MONITOR", "ADVISORY", "SEMI_AUTONOMOUS", "AUTONOMOUS"],
        default="MONITOR",
        help="Agent operating mode (default: MONITOR)",
    )
    parser.add_argument(
        "--api-url",
        default=os.environ.get("NAUTILUS_API_URL", "http://localhost:8001"),
    )
    parser.add_argument("--api-key", default=os.environ.get("NAUTILUS_API_KEY"))
    parser.add_argument("--interval", type=float, default=10.0,
                        help="Decision cycle interval in seconds (default: 10)")
    parser.add_argument("--debate-rounds", type=int, default=2,
                        help="Max bull/bear debate rounds (default: 2)")
    parser.add_argument("--analysts", default="technical,sentiment,risk",
                        help="Comma-separated list of analysts (default: technical,sentiment,risk)")
    parser.add_argument("--no-debate", action="store_true", help="Disable bull/bear debate")
    parser.add_argument("--no-risk-team", action="store_true", help="Disable risk team")
    parser.add_argument("--no-memory", action="store_true", help="Disable cross-cycle memory")
    parser.add_argument("--memory-path", default=None, help="Path for memory persistence")
    parser.add_argument("--max-order-size", default=None)
    parser.add_argument("--max-daily-loss", default=None)

    # Model overrides
    parser.add_argument("--triage-model", default="claude-haiku-4-5-20251001")
    parser.add_argument("--analyst-model", default="claude-sonnet-4-20250514")
    parser.add_argument("--debate-model", default="claude-opus-4-20250514")
    parser.add_argument("--risk-model", default="claude-sonnet-4-20250514")
    parser.add_argument("--decision-model", default="claude-opus-4-20250514")

    return parser.parse_args()


async def main():
    args = parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    models = ModelConfig(
        triage_model=args.triage_model,
        analyst_model=args.analyst_model,
        debate_model=args.debate_model,
        risk_model=args.risk_model,
        decision_model=args.decision_model,
    )

    guardrails = GuardrailConfig(
        max_single_order_size=args.max_order_size,
        max_daily_loss=args.max_daily_loss,
        max_orders_per_minute=10,
    )

    config = EnhancedAgentConfig(
        mode=args.mode,
        api_url=args.api_url,
        api_key=args.api_key,
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
        event_batch_interval_secs=args.interval,
        models=models,
        max_debate_rounds=args.debate_rounds,
        enable_debate=not args.no_debate,
        enable_risk_team=not args.no_risk_team,
        enable_memory=not args.no_memory,
        memory_storage_path=args.memory_path,
        analysts=args.analysts.split(","),
        guardrails=guardrails,
    )

    agent = EnhancedOrchestrator(config)

    print()
    print("=" * 70)
    print("  NautilusTrader Enhanced AI Agent")
    print(f"  Mode:          {args.mode}")
    print(f"  Analysts:      {args.analysts}")
    print(f"  Debate:        {'ON' if not args.no_debate else 'OFF'} ({args.debate_rounds} rounds)")
    print(f"  Risk Team:     {'ON' if not args.no_risk_team else 'OFF'}")
    print(f"  Memory:        {'ON' if not args.no_memory else 'OFF'}")
    print(f"  Cycle:         every {args.interval}s")
    print(f"  Models:")
    print(f"    Triage:      {args.triage_model}")
    print(f"    Analysts:    {args.analyst_model}")
    print(f"    Debate:      {args.debate_model}")
    print(f"    Risk:        {args.risk_model}")
    print(f"    Decision:    {args.decision_model}")
    print("=" * 70)
    print()

    try:
        await agent.start()
        print("Agent running — Ctrl+C to stop\n")
        await agent.run_loop()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        await agent.stop()


if __name__ == "__main__":
    asyncio.run(main())
