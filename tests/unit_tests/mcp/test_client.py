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

from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from nautilus_trader.mcp.client import NautilusApiError
from nautilus_trader.mcp.client import NautilusClient


class TestNautilusApiError:
    def test_attributes(self) -> None:
        error = NautilusApiError(404, "NOT_FOUND", "Order not found")

        assert error.status_code == 404
        assert error.code == "NOT_FOUND"
        assert error.message == "Order not found"
        assert "404" in str(error)
        assert "NOT_FOUND" in str(error)

    def test_is_exception(self) -> None:
        error = NautilusApiError(500, "INTERNAL", "Server error")
        assert isinstance(error, Exception)


class TestNautilusClient:
    def test_init(self) -> None:
        client = NautilusClient("http://localhost:8001", api_key="secret")

        assert client.base_url == "http://localhost:8001"
        assert client.is_connected is False

    def test_init_strips_trailing_slash(self) -> None:
        client = NautilusClient("http://localhost:8001/")

        assert client.base_url == "http://localhost:8001"

    @pytest.mark.asyncio
    async def test_start_creates_session(self) -> None:
        client = NautilusClient("http://localhost:8001")

        await client.start()

        assert client.is_connected is True
        await client.stop()

    @pytest.mark.asyncio
    async def test_stop_closes_session(self) -> None:
        client = NautilusClient("http://localhost:8001")
        await client.start()

        await client.stop()

        assert client.is_connected is False

    @pytest.mark.asyncio
    async def test_request_without_start_raises(self) -> None:
        client = NautilusClient("http://localhost:8001")

        with pytest.raises(RuntimeError, match="not initialized"):
            await client.get("/health")

    @pytest.mark.asyncio
    async def test_get_success(self) -> None:
        client = NautilusClient("http://localhost:8001")
        await client.start()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok", "data": {"trader_id": "TRADER-001"}}

        client._session.request = AsyncMock(return_value=mock_response)  # type: ignore[union-attr]

        result = await client.get("/health")

        assert result["status"] == "ok"
        client._session.request.assert_called_once_with(  # type: ignore[union-attr]
            "GET",
            "/health",
            params=None,
            json=None,
        )
        await client.stop()

    @pytest.mark.asyncio
    async def test_get_with_params(self) -> None:
        client = NautilusClient("http://localhost:8001")
        await client.start()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok", "data": []}

        client._session.request = AsyncMock(return_value=mock_response)  # type: ignore[union-attr]

        await client.get("/api/v1/orders", params={"status": "open"})

        client._session.request.assert_called_once_with(  # type: ignore[union-attr]
            "GET",
            "/api/v1/orders",
            params={"status": "open"},
            json=None,
        )
        await client.stop()

    @pytest.mark.asyncio
    async def test_post_success(self) -> None:
        client = NautilusClient("http://localhost:8001")
        await client.start()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}

        client._session.request = AsyncMock(return_value=mock_response)  # type: ignore[union-attr]

        result = await client.post("/api/v1/node/stop", json={"timeout": 30})

        assert result["status"] == "ok"
        client._session.request.assert_called_once_with(  # type: ignore[union-attr]
            "POST",
            "/api/v1/node/stop",
            params=None,
            json={"timeout": 30},
        )
        await client.stop()

    @pytest.mark.asyncio
    async def test_error_response_raises(self) -> None:
        client = NautilusClient("http://localhost:8001")
        await client.start()

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.return_value = {
            "error": {
                "code": "ORDER_NOT_FOUND",
                "message": "Order 'O-999' not found",
            },
        }
        mock_response.text = "Not Found"

        client._session.request = AsyncMock(return_value=mock_response)  # type: ignore[union-attr]

        with pytest.raises(NautilusApiError) as exc_info:
            await client.get("/api/v1/orders/O-999")

        assert exc_info.value.status_code == 404
        assert exc_info.value.code == "ORDER_NOT_FOUND"
        assert exc_info.value.message == "Order 'O-999' not found"
        await client.stop()

    @pytest.mark.asyncio
    async def test_delete_success(self) -> None:
        client = NautilusClient("http://localhost:8001")
        await client.start()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}

        client._session.request = AsyncMock(return_value=mock_response)  # type: ignore[union-attr]

        result = await client.delete("/api/v1/orders/O-001")

        assert result["status"] == "ok"
        await client.stop()

    @pytest.mark.asyncio
    async def test_put_success(self) -> None:
        client = NautilusClient("http://localhost:8001")
        await client.start()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}

        client._session.request = AsyncMock(return_value=mock_response)  # type: ignore[union-attr]

        result = await client.put("/api/v1/risk/limits", json={"max_rate": "10"})

        assert result["status"] == "ok"
        await client.stop()

    @pytest.mark.asyncio
    async def test_patch_success(self) -> None:
        client = NautilusClient("http://localhost:8001")
        await client.start()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}

        client._session.request = AsyncMock(return_value=mock_response)  # type: ignore[union-attr]

        result = await client.patch("/api/v1/orders/O-001", json={"quantity": "0.5"})

        assert result["status"] == "ok"
        await client.stop()

    @pytest.mark.asyncio
    async def test_health_check_success(self) -> None:
        client = NautilusClient("http://localhost:8001")
        await client.start()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}

        client._session.request = AsyncMock(return_value=mock_response)  # type: ignore[union-attr]

        assert await client.health_check() is True
        await client.stop()

    @pytest.mark.asyncio
    async def test_health_check_failure(self) -> None:
        client = NautilusClient("http://localhost:8001")
        await client.start()

        client._session.request = AsyncMock(  # type: ignore[union-attr]
            side_effect=Exception("Connection refused"),
        )

        assert await client.health_check() is False
        await client.stop()

    @pytest.mark.asyncio
    async def test_api_key_header(self) -> None:
        client = NautilusClient("http://localhost:8001", api_key="my-secret")
        await client.start()

        assert client._session.headers.get("X-Api-Key") == "my-secret"  # type: ignore[union-attr]
        await client.stop()

    @pytest.mark.asyncio
    async def test_no_api_key_header(self) -> None:
        client = NautilusClient("http://localhost:8001")
        await client.start()

        assert "X-Api-Key" not in client._session.headers  # type: ignore[union-attr]
        await client.stop()
