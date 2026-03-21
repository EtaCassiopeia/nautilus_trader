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

import pytest

from nautilus_trader.agent.objectives import Objective
from nautilus_trader.agent.objectives import ObjectiveManager
from nautilus_trader.agent.objectives import ObjectiveStatus


class TestObjectiveStatus:
    def test_values(self) -> None:
        assert ObjectiveStatus.ACTIVE.value == "ACTIVE"
        assert ObjectiveStatus.PAUSED.value == "PAUSED"
        assert ObjectiveStatus.COMPLETED.value == "COMPLETED"
        assert ObjectiveStatus.FAILED.value == "FAILED"


class TestObjective:
    def test_defaults(self) -> None:
        obj = Objective(objective_id="obj-1", description="Test goal")

        assert obj.objective_id == "obj-1"
        assert obj.description == "Test goal"
        assert obj.priority == 1
        assert obj.status == ObjectiveStatus.ACTIVE
        assert obj.constraints == {}
        assert obj.progress == {}
        assert obj.created_at == 0.0
        assert obj.updated_at == 0.0

    def test_custom_values(self) -> None:
        obj = Objective(
            objective_id="obj-2",
            description="Accumulate BTC",
            priority=3,
            status=ObjectiveStatus.PAUSED,
            constraints={"max_drawdown": "5%"},
            progress={"btc_accumulated": "0.5"},
            created_at=1000.0,
            updated_at=2000.0,
        )

        assert obj.priority == 3
        assert obj.status == ObjectiveStatus.PAUSED
        assert obj.constraints == {"max_drawdown": "5%"}
        assert obj.progress == {"btc_accumulated": "0.5"}
        assert obj.created_at == 1000.0
        assert obj.updated_at == 2000.0


class TestObjectiveManager:
    def test_add_and_get(self) -> None:
        manager = ObjectiveManager()
        obj = Objective(objective_id="obj-1", description="Test")

        manager.add(obj)

        assert manager.get("obj-1") is obj

    def test_get_nonexistent_returns_none(self) -> None:
        manager = ObjectiveManager()

        assert manager.get("nonexistent") is None

    def test_add_duplicate_raises_value_error(self) -> None:
        manager = ObjectiveManager()
        obj = Objective(objective_id="obj-1", description="Test")
        manager.add(obj)

        with pytest.raises(ValueError, match="already exists"):
            manager.add(Objective(objective_id="obj-1", description="Duplicate"))

    def test_remove(self) -> None:
        manager = ObjectiveManager()
        obj = Objective(objective_id="obj-1", description="Test")
        manager.add(obj)

        manager.remove("obj-1")

        assert manager.get("obj-1") is None

    def test_remove_nonexistent_raises_key_error(self) -> None:
        manager = ObjectiveManager()

        with pytest.raises(KeyError, match="not found"):
            manager.remove("nonexistent")

    def test_get_active_sorted_by_priority(self) -> None:
        manager = ObjectiveManager()
        manager.add(Objective(objective_id="low", description="Low priority", priority=10))
        manager.add(Objective(objective_id="high", description="High priority", priority=1))
        manager.add(Objective(objective_id="mid", description="Mid priority", priority=5))
        manager.add(Objective(
            objective_id="done",
            description="Done",
            status=ObjectiveStatus.COMPLETED,
        ))

        active = manager.get_active()

        assert len(active) == 3
        assert active[0].objective_id == "high"
        assert active[1].objective_id == "mid"
        assert active[2].objective_id == "low"

    def test_get_active_excludes_non_active(self) -> None:
        manager = ObjectiveManager()
        manager.add(Objective(
            objective_id="paused",
            description="Paused",
            status=ObjectiveStatus.PAUSED,
        ))
        manager.add(Objective(
            objective_id="failed",
            description="Failed",
            status=ObjectiveStatus.FAILED,
        ))
        manager.add(Objective(
            objective_id="completed",
            description="Completed",
            status=ObjectiveStatus.COMPLETED,
        ))

        assert manager.get_active() == []

    def test_update_status(self) -> None:
        manager = ObjectiveManager()
        manager.add(Objective(objective_id="obj-1", description="Test"))

        manager.update_status("obj-1", ObjectiveStatus.COMPLETED)

        assert manager.get("obj-1").status == ObjectiveStatus.COMPLETED

    def test_update_status_nonexistent_raises_key_error(self) -> None:
        manager = ObjectiveManager()

        with pytest.raises(KeyError, match="not found"):
            manager.update_status("nonexistent", ObjectiveStatus.PAUSED)

    def test_update_progress(self) -> None:
        manager = ObjectiveManager()
        manager.add(Objective(
            objective_id="obj-1",
            description="Test",
            progress={"trades": "0"},
        ))

        manager.update_progress("obj-1", {"trades": "5", "pnl": "100.0"})

        obj = manager.get("obj-1")
        assert obj.progress == {"trades": "5", "pnl": "100.0"}

    def test_update_progress_nonexistent_raises_key_error(self) -> None:
        manager = ObjectiveManager()

        with pytest.raises(KeyError, match="not found"):
            manager.update_progress("nonexistent", {"key": "value"})

    def test_to_context(self) -> None:
        manager = ObjectiveManager()
        manager.add(Objective(
            objective_id="obj-2",
            description="Second",
            priority=2,
        ))
        manager.add(Objective(
            objective_id="obj-1",
            description="First",
            priority=1,
            constraints={"max_loss": "1000"},
        ))

        context = manager.to_context()

        assert len(context) == 2
        assert context[0]["objective_id"] == "obj-1"
        assert context[0]["status"] == "ACTIVE"
        assert context[0]["constraints"] == {"max_loss": "1000"}
        assert context[1]["objective_id"] == "obj-2"

    def test_to_context_empty(self) -> None:
        manager = ObjectiveManager()

        assert manager.to_context() == []
