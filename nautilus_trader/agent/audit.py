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
from collections import deque
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path


@dataclass
class Decision:
    """
    A recorded agent decision for the audit trail.

    Parameters
    ----------
    decision_id : str
        Unique identifier for this decision.
    timestamp : str
        ISO 8601 formatted timestamp.
    mode : str
        Operating mode when the decision was made (e.g. MONITOR, AUTONOMOUS).
    trigger : dict
        Events and objective that triggered the decision.
    reasoning : str
        The agent's reasoning text for this decision.
    action : dict or None
        Tool call details if an action was taken, None otherwise.
    guardrail_check : dict
        Guardrail validation result (pass/fail with check details).
    outcome : dict
        Result of the decision (status, order_id, error, etc.).

    """

    decision_id: str
    timestamp: str
    mode: str
    trigger: dict = field(default_factory=dict)
    reasoning: str = ""
    action: dict | None = None
    guardrail_check: dict = field(default_factory=dict)
    outcome: dict = field(default_factory=dict)


class AuditLog:
    """
    Records and persists agent decisions for audit and compliance.

    Maintains an in-memory ring buffer of recent decisions and optionally
    appends each decision to a JSONL file on disk.

    Parameters
    ----------
    log_path : str, optional
        Path to the JSONL file for persistent logging. If None, decisions
        are only stored in memory.
    max_in_memory : int
        Maximum number of decisions to keep in the in-memory buffer.

    """

    def __init__(
        self,
        log_path: str | None = None,
        max_in_memory: int = 1000,
    ) -> None:
        self._log_path = Path(log_path) if log_path else None
        self._decisions: deque[Decision] = deque(maxlen=max_in_memory)

        if self._log_path is not None:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, decision: Decision) -> None:
        """
        Record a decision to the audit log.

        The decision is appended to the in-memory buffer and, if a log
        path is configured, written to disk as a JSONL line.

        Parameters
        ----------
        decision : Decision
            The decision to record.

        """
        self._decisions.append(decision)

        if self._log_path is not None:
            with self._log_path.open("a") as f:
                f.write(json.dumps(asdict(decision)) + "\n")

    def get_recent(self, count: int = 10) -> list[Decision]:
        """
        Get the most recent decisions.

        Parameters
        ----------
        count : int
            Number of recent decisions to return.

        Returns
        -------
        list[Decision]
            Most recent decisions, newest last.

        """
        items = list(self._decisions)
        return items[-count:] if len(items) > count else items

    def to_context(self, count: int = 5) -> list[dict]:
        """
        Serialize recent decisions for the reasoning engine context.

        Parameters
        ----------
        count : int
            Number of recent decisions to include.

        Returns
        -------
        list[dict]
            Each decision as a dictionary.

        """
        recent = self.get_recent(count)
        return [asdict(d) for d in recent]
