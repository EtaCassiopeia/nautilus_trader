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

from typing import TYPE_CHECKING

from fastapi import Request


if TYPE_CHECKING:
    from nautilus_trader.cache.base import CacheFacade
    from nautilus_trader.common.component import MessageBus
    from nautilus_trader.data.engine import DataEngine
    from nautilus_trader.portfolio.base import PortfolioFacade
    from nautilus_trader.risk.engine import RiskEngine
    from nautilus_trader.system.kernel import NautilusKernel
    from nautilus_trader.trading.trader import Trader


def get_kernel(request: Request) -> NautilusKernel:
    return request.app.state.kernel


def get_trader(request: Request) -> Trader:
    return request.app.state.kernel.trader


def get_cache(request: Request) -> CacheFacade:
    return request.app.state.kernel.cache


def get_portfolio(request: Request) -> PortfolioFacade:
    return request.app.state.kernel.portfolio


def get_msgbus(request: Request) -> MessageBus:
    return request.app.state.kernel.msgbus


def get_data_engine(request: Request) -> DataEngine:
    return request.app.state.kernel.data_engine


def get_risk_engine(request: Request) -> RiskEngine:
    return request.app.state.kernel.risk_engine
