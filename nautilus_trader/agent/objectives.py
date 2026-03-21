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

from dataclasses import dataclass
from dataclasses import field
from enum import Enum
from enum import unique


@unique
class ObjectiveStatus(Enum):
    """
    Status of a trading objective.

    ``ACTIVE``
        The objective is currently being pursued.

    ``PAUSED``
        The objective is temporarily suspended.

    ``COMPLETED``
        The objective has been achieved.

    ``FAILED``
        The objective has failed and will not be retried.
    """

    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class Objective:
    """
    A high-level trading objective for the agent.

    Objectives describe what the agent should try to achieve in natural
    language, along with structured constraints and progress tracking.

    Parameters
    ----------
    objective_id : str
        Unique identifier for this objective.
    description : str
        Natural language description of the goal.
    priority : int
        Priority level (lower number = higher priority).
    status : ObjectiveStatus
        Current status of the objective.
    constraints : dict[str, str]
        Key-value constraints that bound the objective (e.g. max_drawdown, time_horizon).
    progress : dict[str, str]
        Key-value progress indicators (e.g. pnl_realized, trades_executed).
    created_at : float
        Unix timestamp when the objective was created.
    updated_at : float
        Unix timestamp when the objective was last updated.

    """

    objective_id: str
    description: str
    priority: int = 1
    status: ObjectiveStatus = ObjectiveStatus.ACTIVE
    constraints: dict[str, str] = field(default_factory=dict)
    progress: dict[str, str] = field(default_factory=dict)
    created_at: float = 0.0
    updated_at: float = 0.0


class ObjectiveManager:
    """
    Manages a collection of trading objectives.

    Provides CRUD operations and context serialization for the
    reasoning engine.
    """

    def __init__(self) -> None:
        self._objectives: dict[str, Objective] = {}

    def add(self, objective: Objective) -> None:
        """
        Add an objective.

        Parameters
        ----------
        objective : Objective
            The objective to add.

        Raises
        ------
        ValueError
            If an objective with the same ID already exists.

        """
        if objective.objective_id in self._objectives:
            raise ValueError(
                f"Objective '{objective.objective_id}' already exists. "
                "Remove it first or use a different ID.",
            )
        self._objectives[objective.objective_id] = objective

    def remove(self, objective_id: str) -> None:
        """
        Remove an objective by ID.

        Parameters
        ----------
        objective_id : str
            The objective ID to remove.

        Raises
        ------
        KeyError
            If the objective does not exist.

        """
        if objective_id not in self._objectives:
            raise KeyError(f"Objective '{objective_id}' not found.")
        del self._objectives[objective_id]

    def get(self, objective_id: str) -> Objective | None:
        """
        Get an objective by ID.

        Parameters
        ----------
        objective_id : str
            The objective ID.

        Returns
        -------
        Objective or None

        """
        return self._objectives.get(objective_id)

    def get_active(self) -> list[Objective]:
        """
        Get all active objectives sorted by priority (ascending).

        Returns
        -------
        list[Objective]

        """
        active = [
            obj for obj in self._objectives.values()
            if obj.status == ObjectiveStatus.ACTIVE
        ]
        return sorted(active, key=lambda o: o.priority)

    def update_status(self, objective_id: str, status: ObjectiveStatus) -> None:
        """
        Update the status of an objective.

        Parameters
        ----------
        objective_id : str
            The objective ID.
        status : ObjectiveStatus
            The new status.

        Raises
        ------
        KeyError
            If the objective does not exist.

        """
        objective = self._objectives.get(objective_id)
        if objective is None:
            raise KeyError(f"Objective '{objective_id}' not found.")
        objective.status = status

    def update_progress(self, objective_id: str, progress: dict[str, str]) -> None:
        """
        Update the progress of an objective.

        Parameters
        ----------
        objective_id : str
            The objective ID.
        progress : dict[str, str]
            Progress key-value pairs to merge into existing progress.

        Raises
        ------
        KeyError
            If the objective does not exist.

        """
        objective = self._objectives.get(objective_id)
        if objective is None:
            raise KeyError(f"Objective '{objective_id}' not found.")
        objective.progress.update(progress)

    def to_context(self) -> list[dict]:
        """
        Serialize all objectives for the reasoning engine context.

        Returns
        -------
        list[dict]
            Each objective as a dictionary, sorted by priority.

        """
        all_objectives = sorted(self._objectives.values(), key=lambda o: o.priority)
        return [
            {
                "objective_id": obj.objective_id,
                "description": obj.description,
                "priority": obj.priority,
                "status": obj.status.value,
                "constraints": obj.constraints,
                "progress": obj.progress,
                "created_at": obj.created_at,
                "updated_at": obj.updated_at,
            }
            for obj in all_objectives
        ]
