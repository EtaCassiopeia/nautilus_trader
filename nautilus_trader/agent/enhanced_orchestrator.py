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
import os
from dataclasses import asdict
from datetime import datetime
from datetime import timezone
from typing import Any

from nautilus_trader.agent.analysts.base import AnalystReport
from nautilus_trader.agent.analysts.risk import RiskAnalyst
from nautilus_trader.agent.analysts.sentiment import SentimentAnalyst
from nautilus_trader.agent.analysts.team import AnalystTeam
from nautilus_trader.agent.analysts.technical import TechnicalAnalyst
from nautilus_trader.agent.config import EnhancedAgentConfig
from nautilus_trader.agent.debate import DebateFramework
from nautilus_trader.agent.debate import DebateResult
from nautilus_trader.agent.guardrails import AgentGuardrails
from nautilus_trader.agent.memory import TradingMemory
from nautilus_trader.agent.memory import TradeMemory
from nautilus_trader.agent.modes import AgentMode
from nautilus_trader.agent.modes import classify_action
from nautilus_trader.agent.portfolio_manager import PortfolioDecision
from nautilus_trader.agent.portfolio_manager import PortfolioManager
from nautilus_trader.agent.risk_team import RiskTeam
from nautilus_trader.agent.risk_team import RiskVerdict
from nautilus_trader.mcp.client import NautilusApiError
from nautilus_trader.mcp.client import NautilusClient


logger = logging.getLogger("nautilus_agent.enhanced")


class EnhancedOrchestrator:
    """
    Enhanced multi-agent orchestrator with analyst team, bull/bear debate,
    three-perspective risk assessment, and cross-cycle memory.

    Architecture
    ------------
    Events → Event Classifier (Haiku)
                    ↓
    Analyst Team (parallel: technical, sentiment, risk) [Sonnet]
                    ↓
    Bull/Bear Debate [Opus]
                    ↓
    Risk Team (aggressive, neutral, conservative) [Sonnet]
                    ↓
    Portfolio Manager (final decision) [Opus]
                    ↓
    Guardrails → Execution → Memory

    Parameters
    ----------
    config : EnhancedAgentConfig
        The enhanced agent configuration.

    """

    def __init__(self, config: EnhancedAgentConfig) -> None:
        self._config = config
        self._client = NautilusClient(
            api_url=config.api_url,
            api_key=config.api_key,
        )
        self._guardrails = AgentGuardrails(config)
        self._anthropic_client: Any = None

        # Components (initialized in start())
        self._analyst_team: AnalystTeam | None = None
        self._debate: DebateFramework | None = None
        self._risk_team: RiskTeam | None = None
        self._portfolio_manager: PortfolioManager | None = None
        self._memory: TradingMemory | None = None

        # State
        self._event_buffer: list[dict] = []
        self._state: dict = {}
        self._objectives: list[dict] = []
        self._decisions: list[dict] = []
        self._running = False
        self._cycle_count = 0

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def mode(self) -> AgentMode:
        return self._guardrails.mode

    @property
    def cycle_count(self) -> int:
        return self._cycle_count

    async def start(self) -> None:
        """Initialize all components and connect to the trading node."""
        logger.info(f"Starting enhanced orchestrator in {self._config.mode} mode")

        # API client
        await self._client.start()
        if not await self._client.health_check():
            raise RuntimeError(
                f"Cannot connect to NautilusTrader API at {self._config.api_url}"
            )
        logger.info(f"Connected to NautilusTrader at {self._config.api_url}")

        # Anthropic client
        try:
            import anthropic
            api_key = self._config.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY", "")
            self._anthropic_client = anthropic.AsyncAnthropic(api_key=api_key)
        except ImportError:
            raise RuntimeError("The 'anthropic' package is required.")

        models = self._config.models

        # Analyst team
        analysts = []
        for name in self._config.analysts:
            if name == "technical":
                analysts.append(TechnicalAnalyst(
                    client=self._anthropic_client,
                    nautilus_client=self._client,
                    model=models.analyst_model,
                ))
            elif name == "sentiment":
                analysts.append(SentimentAnalyst(
                    client=self._anthropic_client,
                    model=models.analyst_model,
                ))
            elif name == "risk":
                analysts.append(RiskAnalyst(
                    client=self._anthropic_client,
                    nautilus_client=self._client,
                    model=models.analyst_model,
                ))
        self._analyst_team = AnalystTeam(analysts)

        # Debate framework
        if self._config.enable_debate:
            self._debate = DebateFramework(
                client=self._anthropic_client,
                model=models.debate_model,
            )

        # Risk team
        if self._config.enable_risk_team:
            self._risk_team = RiskTeam(
                client=self._anthropic_client,
                model=models.risk_model,
                consensus_threshold=self._config.risk_consensus_threshold,
            )

        # Portfolio manager
        self._portfolio_manager = PortfolioManager(
            client=self._anthropic_client,
            model=models.decision_model,
        )

        # Cross-cycle memory
        if self._config.enable_memory:
            self._memory = TradingMemory(
                storage_path=self._config.memory_storage_path,
            )

        # Load initial state
        await self._refresh_state()

        self._running = True
        logger.info("Enhanced orchestrator started")

    async def stop(self) -> None:
        """Stop the orchestrator and clean up resources."""
        logger.info("Stopping enhanced orchestrator")
        self._running = False

        if self._anthropic_client is not None:
            await self._anthropic_client.close()
            self._anthropic_client = None

        await self._client.stop()
        logger.info("Enhanced orchestrator stopped")

    async def run_cycle(self) -> PortfolioDecision | None:
        """
        Execute a single enhanced decision cycle.

        Pipeline
        --------
        1. Refresh state from API
        2. Check kill switch / daily loss
        3. Run analyst team (parallel)
        4. Run bull/bear debate on analyst reports
        5. Run risk team assessment
        6. Portfolio manager makes final decision
        7. Validate against guardrails
        8. Execute if approved
        9. Record to memory and audit trail

        Returns
        -------
        PortfolioDecision | None

        """
        if not self._running:
            return None

        self._cycle_count += 1
        logger.info(f"=== Decision Cycle {self._cycle_count} ===")

        # 1. Refresh state
        await self._refresh_state()

        # 2. Check daily loss
        realized_pnl = self._state.get("realized_pnls", {})
        for currency, pnl in realized_pnl.items():
            if not self._guardrails.check_daily_loss(str(pnl)):
                logger.warning(f"Kill switch triggered: daily loss {pnl} {currency}")
                return None

        if self._guardrails.kill_switch.is_triggered:
            logger.warning("Kill switch active — skipping cycle")
            return None

        # 3. Analyst team
        analyst_reports: list[AnalystReport] = []
        if self._analyst_team:
            try:
                analyst_reports = await self._analyst_team.analyze(
                    self._state, self._event_buffer,
                )
                logger.info(
                    f"Analyst reports: "
                    + ", ".join(f"{r.analyst_name}={r.signal}({r.confidence:.0%})" for r in analyst_reports)
                )
            except Exception as e:
                logger.error(f"Analyst team failed: {e}")

        # 4. Bull/Bear debate
        debate_result: DebateResult | None = None
        if self._debate and self._config.enable_debate and analyst_reports:
            try:
                debate_result = await self._debate.debate(
                    analyst_reports=analyst_reports,
                    state=self._state,
                    max_rounds=self._config.max_debate_rounds,
                )
                logger.info(
                    f"Debate: {debate_result.recommended_action} "
                    f"(conviction: {debate_result.conviction:.0%}, "
                    f"rounds: {debate_result.rounds_completed})"
                )
            except Exception as e:
                logger.error(f"Debate failed: {e}")

        # If no debate, skip to no-action
        if debate_result is None or debate_result.recommended_action == "HOLD":
            decision = PortfolioDecision(
                action=None,
                approved=False,
                reasoning=debate_result.synthesis if debate_result else "No analyst data",
                risk_verdict=None,
                debate_result=debate_result,
            )
            self._record_decision(decision)
            self._event_buffer.clear()
            return decision

        # 5. Risk team
        risk_verdict: RiskVerdict | None = None
        if self._risk_team and self._config.enable_risk_team:
            try:
                risk_verdict = await self._risk_team.evaluate(
                    proposed_action={"action": debate_result.recommended_action},
                    debate_result=debate_result,
                    state=self._state,
                )
                logger.info(
                    f"Risk verdict: {'APPROVED' if risk_verdict.approved else 'REJECTED'} "
                    f"(score: {risk_verdict.consensus_score:.2f})"
                )
            except Exception as e:
                logger.error(f"Risk team failed: {e}")

        if risk_verdict and not risk_verdict.approved:
            decision = PortfolioDecision(
                action=None,
                approved=False,
                reasoning=f"Risk team rejected: {risk_verdict.summary}",
                risk_verdict=risk_verdict,
                debate_result=debate_result,
            )
            self._record_decision(decision)
            self._event_buffer.clear()
            return decision

        # 6. Portfolio manager decision
        decision: PortfolioDecision
        if self._portfolio_manager:
            try:
                memory_context = ""
                if self._memory:
                    memory_context = self._memory.to_context(count=5)

                decision = await self._portfolio_manager.decide(
                    debate_result=debate_result,
                    risk_verdict=risk_verdict,
                    state=self._state,
                    objectives=self._objectives,
                    memory_context=memory_context,
                )
                logger.info(
                    f"Portfolio manager: {'APPROVED' if decision.approved else 'REJECTED'} "
                    f"— {decision.reasoning[:100]}"
                )
            except Exception as e:
                logger.error(f"Portfolio manager failed: {e}")
                decision = PortfolioDecision(
                    action=None,
                    approved=False,
                    reasoning=f"Portfolio manager error: {e}",
                    risk_verdict=risk_verdict,
                    debate_result=debate_result,
                )
        else:
            decision = PortfolioDecision(
                action=None, approved=False, reasoning="No portfolio manager",
                risk_verdict=risk_verdict, debate_result=debate_result,
            )

        # 7. Execute if approved
        if decision.approved and decision.action:
            await self._execute_action(decision)

        # 8. Record
        self._record_decision(decision)
        self._event_buffer.clear()

        return decision

    async def run_loop(self) -> None:
        """Run the continuous decision loop."""
        logger.info("Starting enhanced agent loop")
        while self._running:
            try:
                await self.run_cycle()
            except Exception as e:
                logger.error(f"Error in agent loop: {e}")
            await asyncio.sleep(self._config.event_batch_interval_secs)

    def add_event(self, event: dict) -> None:
        """Add an event to the processing buffer."""
        self._event_buffer.append(event)
        max_events = self._config.max_context_events
        if len(self._event_buffer) > max_events:
            self._event_buffer = self._event_buffer[-max_events:]

    def add_objective(self, objective: dict) -> None:
        """Add an objective for the agent."""
        self._objectives.append(objective)
        self._objectives.sort(key=lambda o: o.get("priority", 99))

    def remove_objective(self, objective_id: str) -> None:
        self._objectives = [
            o for o in self._objectives if o.get("objective_id") != objective_id
        ]

    async def _refresh_state(self) -> None:
        """Refresh state from the API."""
        try:
            portfolio = await self._client.get("/api/v1/portfolio")
            self._state = portfolio.get("data", {})

            # Enrich with positions
            try:
                positions = await self._client.get("/api/v1/portfolio/positions")
                self._state["positions"] = positions.get("data", [])
            except Exception:
                pass

            # Enrich with orders
            try:
                orders = await self._client.get("/api/v1/orders", params={"status": "open"})
                self._state["open_orders"] = orders.get("data", [])
            except Exception:
                pass

        except NautilusApiError as e:
            logger.error(f"Failed to refresh state: {e}")
        except Exception as e:
            logger.error(f"Unexpected error refreshing state: {e}")

    async def _execute_action(self, decision: PortfolioDecision) -> None:
        """Execute the approved action."""
        action = decision.action
        if not action:
            return

        tool_name = action.get("tool", "")
        params = action.get("params", {})
        action_name = tool_name.replace("nautilus_", "")
        risk = classify_action(action_name)

        # Final guardrail check
        check = self._guardrails.validate_action(action_name, risk, params=params)
        if not check.passed:
            logger.warning(f"Guardrail blocked: {check.rejection_reason}")
            return

        if check.needs_approval:
            logger.info(f"Action needs human approval: {tool_name}")
            return

        # Dispatch
        try:
            result = await self._dispatch_tool(tool_name, params)
            logger.info(f"Executed {tool_name}: success")

            # Record to memory
            if self._memory and "order" in tool_name.lower():
                self._memory.remember_trade(TradeMemory(
                    trade_id=f"T-{self._cycle_count}",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    instrument_id=params.get("instrument_id", "unknown"),
                    side=params.get("side", "unknown"),
                    quantity=params.get("quantity", "0"),
                    entry_reasoning=decision.reasoning[:500],
                    market_conditions=self._state,
                ))

            if "order" in tool_name.lower() and "submit" in tool_name.lower():
                self._guardrails.rate_limiter.record()

        except NautilusApiError as e:
            logger.error(f"API error executing {tool_name}: {e}")
        except Exception as e:
            logger.error(f"Error executing {tool_name}: {e}")

    async def _dispatch_tool(self, tool_name: str, params: dict) -> dict:
        """Dispatch a tool call to the API."""
        dispatch_map = {
            "nautilus_node_status": ("GET", "/api/v1/node/status"),
            "nautilus_list_strategies": ("GET", "/api/v1/strategies"),
            "nautilus_list_orders": ("GET", "/api/v1/orders"),
            "nautilus_get_order": ("GET", "/api/v1/orders/{client_order_id}"),
            "nautilus_get_portfolio_summary": ("GET", "/api/v1/portfolio"),
            "nautilus_get_positions": ("GET", "/api/v1/portfolio/positions"),
            "nautilus_get_balances": ("GET", "/api/v1/portfolio/balances"),
            "nautilus_get_pnl": ("GET", "/api/v1/portfolio/pnl"),
            "nautilus_submit_order": ("POST", "/api/v1/orders"),
            "nautilus_cancel_order": ("DELETE", "/api/v1/orders/{client_order_id}"),
            "nautilus_cancel_all_orders": ("POST", "/api/v1/orders/cancel-all"),
            "nautilus_start_strategy": ("POST", "/api/v1/strategies/{strategy_id}/start"),
            "nautilus_stop_strategy": ("POST", "/api/v1/strategies/{strategy_id}/stop"),
        }

        if tool_name not in dispatch_map:
            raise ValueError(f"Unknown tool: {tool_name}")

        method, path_template = dispatch_map[tool_name]
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

    def _record_decision(self, decision: PortfolioDecision) -> None:
        """Record a decision to the audit trail."""
        record = {
            "cycle": self._cycle_count,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": self._guardrails.mode.value,
            "approved": decision.approved,
            "action": decision.action,
            "reasoning": decision.reasoning,
            "debate": {
                "recommendation": decision.debate_result.recommended_action,
                "conviction": decision.debate_result.conviction,
            } if decision.debate_result else None,
            "risk": {
                "approved": decision.risk_verdict.approved,
                "score": decision.risk_verdict.consensus_score,
            } if decision.risk_verdict else None,
        }
        self._decisions.append(record)

        if len(self._decisions) > 200:
            self._decisions = self._decisions[-200:]

        status = "APPROVED" if decision.approved else "REJECTED"
        action_name = decision.action.get("tool", "none") if decision.action else "none"
        logger.info(f"Decision #{self._cycle_count}: {status} | Action: {action_name}")
