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

from typing import Any

from pydantic import BaseModel
from pydantic import Field


class CreateStrategyRequest(BaseModel):
    strategy_path: str = Field(
        ...,
        description="Fully qualified path to strategy class (e.g., 'my_module:MyStrategy')",
    )
    config_path: str = Field(
        ...,
        description="Fully qualified path to strategy config class (e.g., 'my_module:MyStrategyConfig')",
    )
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="Strategy configuration parameters",
    )
    start: bool = Field(
        default=True,
        description="Whether to start the strategy immediately after creation",
    )


class CreateActorRequest(BaseModel):
    actor_path: str = Field(
        ...,
        description="Fully qualified path to actor class (e.g., 'my_module:MyActor')",
    )
    config_path: str = Field(
        ...,
        description="Fully qualified path to actor config class (e.g., 'my_module:MyActorConfig')",
    )
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="Actor configuration parameters",
    )
    start: bool = Field(
        default=True,
        description="Whether to start the actor immediately after creation",
    )
