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
import logging
from dataclasses import asdict
from typing import Any

from nautilus_trader.agent.config import AgentConfig
from nautilus_trader.agent.guardrails import AgentGuardrails
from nautilus_trader.agent.modes import AgentMode
from nautilus_trader.agent.modes import classify_action
from nautilus_trader.agent.prompts import format_guardrail_summary
from nautilus_trader.agent.reasoning import ReasoningEngine
from nautilus_trader.agent.reasoning import ReasoningResult
from nautilus_trader.mcp.client import NautilusApiError
from nautilus_trader.mcp.client import NautilusClient


logger = logging.getLogger("nautilus_agent")


class AgentOrchestrator:
    """
    Main orchestration loop for the AI trading agent.

    Connects to NautilusTrader via the REST API and event stream,
    processes events, reasons about actions using Claude, and executes
    decisions within safety guardrails.

    Parameters
    ----------
    config : AgentConfig
        The agent configuration.

    """

    def __init__(self, config: AgentConfig) -> None:
        self._config = config
        self._client = NautilusClient(
            api_url=config.api_url,
            api_key=config.api_key,
        )
        self._guardrails = AgentGuardrails(config)
        self._reasoning = ReasoningEngine(config)

        # State
        self._event_buffer: list[dict] = []
        self._state: dict = {}
        self._objectives: list[dict] = []
        self._decisions: list[dict] = []
        self._running = False

    @property
    def is_running(self) -> bool:
        """Return whether the orchestrator is running."""
        return self._running

    @property
    def mode(self) -> AgentMode:
        """Return the current operating mode."""
        return self._guardrails.mode

    @property
    def guardrails(self) -> AgentGuardrails:
        """Return the guardrails instance."""
        return self._guardrails

    async def start(self) -> None:
        """
        Start the agent orchestrator.

        Initializes the API client, reasoning engine, and begins
        the event processing loop.
        """
        logger.info(f"Starting agent in {self._config.mode} mode")

        await self._client.start()

        # Check API connectivity
        if not await self._client.health_check():
            raise RuntimeError(
                f"Cannot connect to NautilusTrader API at {self._config.api_url}"
            )
        logger.info(f"Connected to NautilusTrader API at {self._config.api_url}")

        await self._reasoning.start()

        # Build system prompt with guardrail summary
        guardrail_dict = asdict(self._config.guardrails)
        guardrail_summary = format_guardrail_summary(guardrail_dict)
        self._reasoning.set_system_prompt(
            guardrail_summary=guardrail_summary,
            tool_descriptions=self._get_tool_descriptions(),
        )

        # Load initial state
        await self._refresh_state()

        self._running = True
        logger.info("Agent orchestrator started")

    async def stop(self) -> None:
        """Stop the agent orchestrator gracefully."""
        logger.info("Stopping agent orchestrator")
        self._running = False

        await self._reasoning.stop()
        await self._client.stop()

        logger.info("Agent orchestrator stopped")

    async def run_cycle(self) -> ReasoningResult | None:
        """
        Execute a single decision cycle.

        1. Refresh state from API
        2. Send context to reasoning engine
        3. Validate proposed action against guardrails
        4. Execute action if permitted
        5. Record decision

        Returns
        -------
        ReasoningResult | None
            The reasoning result, or None if no cycle was needed.

        """
        if not self._running:
            return None

        # 1. Refresh state
        await self._refresh_state()

        # 2. Check daily loss
        realized_pnl = self._state.get("realized_pnls", {})
        for currency, pnl in realized_pnl.items():
            if not self._guardrails.check_daily_loss(str(pnl)):
                logger.warning(f"Kill switch triggered: daily loss limit breached ({pnl} {currency})")
                return None

        # 3. Reason
        try:
            result = await self._reasoning.reason(
                state=self._state,
                events=self._event_buffer,
                objectives=self._objectives,
                recent_decisions=self._decisions[-5:] if self._decisions else None,
            )
        except Exception as e:
            logger.error(f"Reasoning failed: {e}")
            return None

        # 4. Clear event buffer after reasoning
        self._event_buffer.clear()

        # 5. Process action
        if result.action:
            await self._execute_action(result)
        else:
            self._record_decision(result, outcome={"status": "no_action"})

        return result

    async def run_loop(self) -> None:
        """
        Run the continuous event processing loop.

        Executes decision cycles at the configured interval until stopped.
        """
        logger.info("Starting agent loop")

        while self._running:
            try:
                await self.run_cycle()
            except Exception as e:
                logger.error(f"Error in agent loop: {e}")

            await asyncio.sleep(self._config.event_batch_interval_secs)

    def add_event(self, event: dict) -> None:
        """
        Add an event to the processing buffer.

        Parameters
        ----------
        event : dict
            Serialized event from the WebSocket stream.

        """
        self._event_buffer.append(event)

        # Trim buffer if too large
        if len(self._event_buffer) > self._config.max_context_events:
            self._event_buffer = self._event_buffer[-self._config.max_context_events:]

    def add_objective(self, objective: dict) -> None:
        """
        Add an objective for the agent to pursue.

        Parameters
        ----------
        objective : dict
            Objective definition with description, priority, constraints, etc.

        """
        self._objectives.append(objective)
        self._objectives.sort(key=lambda o: o.get("priority", 99))

    def remove_objective(self, objective_id: str) -> None:
        """Remove an objective by ID."""
        self._objectives = [
            o for o in self._objectives if o.get("objective_id") != objective_id
        ]

    async def _refresh_state(self) -> None:
        """Refresh state from the API."""
        try:
            portfolio = await self._client.get("/api/v1/portfolio")
            self._state = portfolio.get("data", {})
        except NautilusApiError as e:
            logger.error(f"Failed to refresh state: {e}")
        except Exception as e:
            logger.error(f"Unexpected error refreshing state: {e}")

    async def _execute_action(self, result: ReasoningResult) -> None:
        """Execute an action from the reasoning result."""
        action = result.action
        if action is None:
            return

        tool_name = action["tool"]
        params = action.get("params", {})

        # Map tool name to action name for classification
        action_name = tool_name.replace("nautilus_", "")
        risk = classify_action(action_name)

        # Validate against guardrails
        check = self._guardrails.validate_action(action_name, risk, params=params)

        if not check.passed:
            logger.warning(f"Action blocked: {check.rejection_reason}")
            self._record_decision(
                result,
                guardrail_check={"passed": False, "checks": check.checks},
                outcome={"status": "blocked", "reason": check.rejection_reason},
            )
            return

        if check.needs_approval:
            logger.info(f"Action needs approval: {tool_name}")
            self._record_decision(
                result,
                guardrail_check={"passed": True, "checks": check.checks},
                outcome={"status": "needs_approval"},
            )
            return

        # Execute via API
        try:
            api_result = await self._dispatch_tool(tool_name, params)
            outcome = {"status": "executed", "result": api_result}

            # Record order rate limit
            if "order" in tool_name.lower() and "submit" in tool_name.lower():
                self._guardrails.rate_limiter.record()

        except NautilusApiError as e:
            outcome = {"status": "api_error", "code": e.code, "message": e.message}
            logger.error(f"API error executing {tool_name}: {e}")
        except Exception as e:
            outcome = {"status": "error", "message": str(e)}
            logger.error(f"Error executing {tool_name}: {e}")

        self._record_decision(
            result,
            guardrail_check={"passed": True, "checks": check.checks},
            outcome=outcome,
        )

    async def _dispatch_tool(self, tool_name: str, params: dict) -> dict:
        """Dispatch a tool call to the appropriate API endpoint."""
        # Map tool names to API calls
        dispatch_map: dict[str, tuple[str, str]] = {
            "nautilus_node_status": ("GET", "/api/v1/node/status"),
            "nautilus_list_strategies": ("GET", "/api/v1/strategies"),
            "nautilus_list_orders": ("GET", "/api/v1/orders"),
            "nautilus_get_order": ("GET", "/api/v1/orders/{client_order_id}"),
            "nautilus_get_portfolio_summary": ("GET", "/api/v1/portfolio"),
            "nautilus_get_positions": ("GET", "/api/v1/portfolio/positions"),
            "nautilus_get_balances": ("GET", "/api/v1/portfolio/balances"),
            "nautilus_get_pnl": ("GET", "/api/v1/portfolio/pnl"),
            "nautilus_get_exposure": ("GET", "/api/v1/portfolio/exposure"),
            "nautilus_submit_order": ("POST", "/api/v1/orders"),
            "nautilus_cancel_order": ("DELETE", "/api/v1/orders/{client_order_id}"),
            "nautilus_cancel_all_orders": ("POST", "/api/v1/orders/cancel-all"),
            "nautilus_start_strategy": ("POST", "/api/v1/strategies/{strategy_id}/start"),
            "nautilus_stop_strategy": ("POST", "/api/v1/strategies/{strategy_id}/stop"),
            "nautilus_node_stop": ("POST", "/api/v1/node/stop"),
        }

        if tool_name not in dispatch_map:
            raise ValueError(f"Unknown tool: {tool_name}")

        method, path_template = dispatch_map[tool_name]

        # Format path with params
        path = path_template
        for key, value in params.items():
            placeholder = "{" + key + "}"
            if placeholder in path:
                path = path.replace(placeholder, str(value))

        if method == "GET":
            return await self._client.get(path, params=params)
        elif method == "POST":
            return await self._client.post(path, json=params)
        elif method == "DELETE":
            return await self._client.delete(path)
        else:
            raise ValueError(f"Unsupported method: {method}")

    def _record_decision(
        self,
        result: ReasoningResult,
        guardrail_check: dict | None = None,
        outcome: dict | None = None,
    ) -> None:
        """Record a decision in the audit log."""
        from datetime import datetime, timezone

        decision = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": self._guardrails.mode.value,
            "reasoning": result.reasoning,
            "action": result.action,
            "guardrail_check": guardrail_check or {},
            "outcome": outcome or {},
        }

        self._decisions.append(decision)

        # Keep bounded
        if len(self._decisions) > 100:
            self._decisions = self._decisions[-100:]

        logger.info(
            f"Decision: {outcome.get('status', 'unknown') if outcome else 'unknown'} "
            f"| Action: {result.action.get('tool', 'none') if result.action else 'none'}"
        )

    def _get_tool_descriptions(self) -> str:
        """Get tool descriptions for the system prompt."""
        tools = [
            "- nautilus_node_status: Get node health and status",
            "- nautilus_list_strategies: List all strategies with state",
            "- nautilus_list_orders: List orders with filters (status, strategy, instrument)",
            "- nautilus_get_order: Get order detail by ID",
            "- nautilus_get_portfolio_summary: Full portfolio overview",
            "- nautilus_get_positions: Open positions",
            "- nautilus_get_balances: Account balances",
            "- nautilus_get_pnl: P&L summary",
            "- nautilus_get_exposure: Net exposures",
        ]

        if self._guardrails.mode != AgentMode.MONITOR:
            tools.extend([
                "- nautilus_submit_order: Submit a new order (requires instrument, side, type, quantity)",
                "- nautilus_cancel_order: Cancel an order by ID",
                "- nautilus_cancel_all_orders: Cancel all open orders",
                "- nautilus_start_strategy: Start a strategy",
                "- nautilus_stop_strategy: Stop a strategy",
                "- nautilus_node_stop: Stop the trading node (critical)",
            ])

        return "\n".join(tools)
