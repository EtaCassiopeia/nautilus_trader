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

import json
from typing import Any


SYSTEM_PROMPT = """\
You are an AI trading agent operating within NautilusTrader. You process market events, \
analyze portfolio state, and take actions to achieve trading objectives.

## Operating Mode: {mode}

{mode_description}

## Safety Guardrails

You are subject to hard safety limits that CANNOT be overridden:
{guardrail_summary}

## Available Tools

You can use these tools to interact with the trading system:
{tool_descriptions}

## Decision Framework

For each decision cycle:
1. Analyze the current state and recent events
2. Check progress on active objectives
3. Determine if any action is needed
4. If acting, explain your reasoning clearly
5. Choose the appropriate tool and parameters

Always explain your reasoning before taking action. Consider risk, position sizing, \
and market conditions. When uncertain, prefer inaction over action.
"""

MODE_DESCRIPTIONS = {
    "MONITOR": (
        "You are in MONITOR mode. You can observe events and query state, "
        "but you CANNOT submit any mutations (orders, strategy changes, etc.). "
        "Focus on analysis, alerting, and generating insights."
    ),
    "ADVISORY": (
        "You are in ADVISORY mode. You can observe events, query state, and SUGGEST "
        "actions, but all mutations require human approval. Present your suggestions "
        "clearly with reasoning so the operator can make informed decisions."
    ),
    "SEMI_AUTONOMOUS": (
        "You are in SEMI_AUTONOMOUS mode. You can auto-execute low-risk actions "
        "(queries, small orders within limits, strategy start/stop). High-risk actions "
        "(large orders, market exits, cancel-all) require human approval."
    ),
    "AUTONOMOUS": (
        "You are in AUTONOMOUS mode. You can execute all actions within guardrail limits "
        "without human approval. Exercise careful judgment — you are fully responsible "
        "for the outcomes of your decisions."
    ),
}


def build_system_prompt(
    mode: str,
    guardrail_summary: str,
    tool_descriptions: str,
) -> str:
    """
    Build the system prompt for the reasoning engine.

    Parameters
    ----------
    mode : str
        The agent operating mode.
    guardrail_summary : str
        Summary of active guardrails.
    tool_descriptions : str
        Descriptions of available MCP tools.

    Returns
    -------
    str

    """
    return SYSTEM_PROMPT.format(
        mode=mode,
        mode_description=MODE_DESCRIPTIONS.get(mode, "Unknown mode."),
        guardrail_summary=guardrail_summary,
        tool_descriptions=tool_descriptions,
    )


def build_context_message(
    state: dict,
    events: list[dict],
    objectives: list[dict],
    recent_decisions: list[dict] | None = None,
) -> str:
    """
    Build a context message for the reasoning engine.

    Parameters
    ----------
    state : dict
        Current agent state snapshot.
    events : list[dict]
        Recent event batch.
    objectives : list[dict]
        Active objectives.
    recent_decisions : list[dict], optional
        Recent decision history.

    Returns
    -------
    str

    """
    parts = []

    # Objectives
    if objectives:
        parts.append("## Active Objectives\n")
        for obj in objectives:
            priority = obj.get("priority", "?")
            desc = obj.get("description", "No description")
            status = obj.get("status", "UNKNOWN")
            progress = obj.get("progress", {})
            parts.append(f"- [{priority}] {desc} (status: {status})")
            if progress:
                progress_str = ", ".join(f"{k}: {v}" for k, v in progress.items())
                parts.append(f"  Progress: {progress_str}")
        parts.append("")

    # Portfolio state
    if state:
        parts.append("## Current State\n")
        parts.append(f"```json\n{json.dumps(state, indent=2, default=str)}\n```\n")

    # Recent events
    if events:
        parts.append(f"## Recent Events ({len(events)} events)\n")
        for event in events[-20:]:  # Limit to most recent 20
            event_type = event.get("type", "Unknown")
            topic = event.get("topic", "")
            ts = event.get("ts_event", "")
            data = event.get("data", {})
            parts.append(f"- **{event_type}** (topic: {topic}, ts: {ts})")
            if data:
                data_str = json.dumps(data, default=str)
                if len(data_str) > 200:
                    data_str = data_str[:200] + "..."
                parts.append(f"  Data: {data_str}")
        parts.append("")

    # Recent decisions
    if recent_decisions:
        parts.append(f"## Recent Decisions ({len(recent_decisions)})\n")
        for dec in recent_decisions[-5:]:
            action = dec.get("action", {})
            reasoning = dec.get("reasoning", "")
            outcome = dec.get("outcome", {})
            parts.append(f"- Action: {action.get('tool', 'none')}")
            if reasoning:
                parts.append(f"  Reasoning: {reasoning[:100]}...")
            parts.append(f"  Outcome: {outcome.get('status', 'unknown')}")
        parts.append("")

    parts.append(
        "Based on the above state and events, analyze the situation and determine "
        "if any action is needed to advance your objectives. If you decide to act, "
        "explain your reasoning first, then use the appropriate tool."
    )

    return "\n".join(parts)


def format_guardrail_summary(guardrails: dict) -> str:
    """
    Format guardrail configuration as a human-readable summary.

    Parameters
    ----------
    guardrails : dict
        Guardrail configuration as a dict.

    Returns
    -------
    str

    """
    lines = []

    if guardrails.get("max_single_order_size"):
        lines.append(f"- Max single order size: {guardrails['max_single_order_size']}")

    if guardrails.get("max_orders_per_minute"):
        lines.append(f"- Max orders per minute: {guardrails['max_orders_per_minute']}")

    if guardrails.get("max_daily_loss"):
        lines.append(f"- Max daily loss: {guardrails['max_daily_loss']}")

    if guardrails.get("max_portfolio_exposure"):
        lines.append(f"- Max portfolio exposure: {guardrails['max_portfolio_exposure']}")

    if guardrails.get("instrument_allowlist"):
        instruments = ", ".join(guardrails["instrument_allowlist"])
        lines.append(f"- Allowed instruments: {instruments}")

    if guardrails.get("instrument_blocklist"):
        instruments = ", ".join(guardrails["instrument_blocklist"])
        lines.append(f"- Blocked instruments: {instruments}")

    if guardrails.get("max_position_size"):
        for inst, size in guardrails["max_position_size"].items():
            lines.append(f"- Max position for {inst}: {size}")

    if guardrails.get("require_stop_loss"):
        lines.append("- Stop-loss required for all positions")

    if not lines:
        lines.append("- No specific guardrails configured (default limits apply)")

    return "\n".join(lines)
