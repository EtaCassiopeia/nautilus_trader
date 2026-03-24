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

from datetime import datetime
from datetime import timezone
from typing import TYPE_CHECKING

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from nautilus_trader.api.config import ApiServerConfig
from nautilus_trader.api.middleware import ApiKeyMiddleware
from nautilus_trader.api.middleware import RequestLoggingMiddleware


if TYPE_CHECKING:
    from nautilus_trader.system.kernel import NautilusKernel


def create_app(kernel: NautilusKernel, config: ApiServerConfig) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="NautilusTrader API",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Store kernel reference for dependency injection
    app.state.kernel = kernel
    app.state.config = config

    # Middleware (order matters — last added runs first)
    if config.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=config.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.add_middleware(RequestLoggingMiddleware)

    if config.api_key is not None:
        app.add_middleware(ApiKeyMiddleware, api_key=config.api_key)

    # Health endpoint (always public, no auth)
    @app.get("/health")
    async def health():
        return JSONResponse(
            content={
                "status": "ok",
                "data": {
                    "trader_id": str(kernel.trader_id),
                    "is_running": kernel.is_running(),
                },
                "ts": datetime.now(timezone.utc).isoformat(),
            },
        )

    # Register route modules
    from nautilus_trader.api.routes.actors import router as actors_router
    from nautilus_trader.api.routes.cache import router as cache_router
    from nautilus_trader.api.routes.market_data import router as market_data_router
    from nautilus_trader.api.routes.node import router as node_router
    from nautilus_trader.api.routes.orders import router as orders_router
    from nautilus_trader.api.routes.portfolio import router as portfolio_router
    from nautilus_trader.api.routes.risk import router as risk_router
    from nautilus_trader.api.routes.strategies import router as strategies_router

    app.include_router(actors_router)
    app.include_router(cache_router)
    app.include_router(market_data_router)
    app.include_router(node_router)
    app.include_router(orders_router)
    app.include_router(portfolio_router)
    app.include_router(risk_router)
    app.include_router(strategies_router)

    return app


class ApiServer:
    """
    Manages the lifecycle of the embedded API server.

    The server runs on the same asyncio event loop as the ``TradingNode``,
    ensuring thread-safe access to all kernel subsystems.

    Parameters
    ----------
    kernel : NautilusKernel
        The kernel instance to expose via the API.
    config : ApiServerConfig
        The server configuration.

    """

    def __init__(self, kernel: NautilusKernel, config: ApiServerConfig) -> None:
        self._kernel = kernel
        self._config = config
        self._app = create_app(kernel, config)
        self._server: uvicorn.Server | None = None

    @property
    def app(self) -> FastAPI:
        """Return the FastAPI application instance."""
        return self._app

    async def start(self) -> None:
        """Start the API server (runs until cancelled or stopped)."""
        uvi_config = uvicorn.Config(
            app=self._app,
            host=self._config.host,
            port=self._config.port,
            loop="none",  # Use the existing event loop
            log_level="warning",  # We do our own logging via middleware
        )
        self._server = uvicorn.Server(uvi_config)
        self._kernel.logger.info(
            f"Starting API server on {self._config.host}:{self._config.port}",
        )
        await self._server.serve()

    async def stop(self) -> None:
        """Signal the API server to stop gracefully."""
        if self._server is not None:
            self._kernel.logger.info("Stopping API server")
            self._server.should_exit = True
