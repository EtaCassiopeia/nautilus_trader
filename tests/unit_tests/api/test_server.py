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

from unittest.mock import MagicMock
from unittest.mock import PropertyMock

import pytest
from httpx import ASGITransport
from httpx import AsyncClient

from nautilus_trader.api.config import ApiServerConfig
from nautilus_trader.api.server import ApiServer
from nautilus_trader.api.server import create_app


def _mock_kernel(trader_id: str = "TRADER-001", is_running: bool = True):
    """Create a mock NautilusKernel for testing."""
    kernel = MagicMock()
    type(kernel).trader_id = PropertyMock(return_value=trader_id)
    kernel.is_running.return_value = is_running
    kernel.logger = MagicMock()
    return kernel


class TestCreateApp:
    def test_creates_fastapi_app(self) -> None:
        kernel = _mock_kernel()
        config = ApiServerConfig()
        app = create_app(kernel, config)

        assert app.title == "NautilusTrader API"
        assert app.state.kernel is kernel
        assert app.state.config is config

    def test_app_has_health_endpoint(self) -> None:
        kernel = _mock_kernel()
        config = ApiServerConfig()
        app = create_app(kernel, config)

        routes = {route.path for route in app.routes}
        assert "/health" in routes


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_returns_ok(self) -> None:
        kernel = _mock_kernel()
        config = ApiServerConfig()
        app = create_app(kernel, config)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["data"]["trader_id"] == "TRADER-001"
        assert data["data"]["is_running"] is True
        assert "ts" in data

    @pytest.mark.asyncio
    async def test_health_reflects_not_running(self) -> None:
        kernel = _mock_kernel(is_running=False)
        config = ApiServerConfig()
        app = create_app(kernel, config)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/health")

        data = response.json()
        assert data["data"]["is_running"] is False


class TestApiKeyMiddleware:
    @pytest.mark.asyncio
    async def test_no_auth_when_api_key_not_configured(self) -> None:
        kernel = _mock_kernel()
        config = ApiServerConfig(api_key=None)
        app = create_app(kernel, config)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/health")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_health_bypasses_auth(self) -> None:
        kernel = _mock_kernel()
        config = ApiServerConfig(api_key="secret-key")
        app = create_app(kernel, config)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # Health should be accessible without API key
            response = await client.get("/health")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_docs_bypasses_auth(self) -> None:
        kernel = _mock_kernel()
        config = ApiServerConfig(api_key="secret-key")
        app = create_app(kernel, config)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/openapi.json")

        assert response.status_code == 200


class TestApiServer:
    def test_creates_with_kernel_and_config(self) -> None:
        kernel = _mock_kernel()
        config = ApiServerConfig(enabled=True, port=9999)
        server = ApiServer(kernel, config)

        assert server.app is not None
        assert server.app.state.kernel is kernel
