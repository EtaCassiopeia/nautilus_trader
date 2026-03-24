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
from unittest.mock import patch

import pytest

from nautilus_trader.cli.client import CliApiError
from nautilus_trader.cli.client import CliClient


class TestCliApiError:
    def test_attributes(self) -> None:
        error = CliApiError(404, "NOT_FOUND", "Order not found")

        assert error.status_code == 404
        assert error.code == "NOT_FOUND"
        assert error.message == "Order not found"

    def test_str(self) -> None:
        error = CliApiError(500, "INTERNAL", "Server error")

        assert "500" in str(error)
        assert "INTERNAL" in str(error)


class TestCliClient:
    def test_get_success(self) -> None:
        client = CliClient("http://localhost:8001")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok", "data": {}}

        client._client.request = MagicMock(return_value=mock_response)

        result = client.get("/health")

        assert result["status"] == "ok"
        client._client.request.assert_called_once_with(
            "GET",
            "/health",
            params=None,
            json=None,
        )

    def test_error_raises(self) -> None:
        client = CliClient("http://localhost:8001")

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.return_value = {
            "error": {"code": "NOT_FOUND", "message": "Not found"},
        }
        mock_response.text = "Not Found"

        client._client.request = MagicMock(return_value=mock_response)

        with pytest.raises(CliApiError) as exc_info:
            client.get("/api/v1/orders/O-999")

        assert exc_info.value.status_code == 404

    def test_post_with_json(self) -> None:
        client = CliClient("http://localhost:8001")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}

        client._client.request = MagicMock(return_value=mock_response)

        client.post("/api/v1/node/stop", json={"timeout": 30})

        client._client.request.assert_called_once_with(
            "POST",
            "/api/v1/node/stop",
            params=None,
            json={"timeout": 30},
        )

    def test_api_key_header(self) -> None:
        client = CliClient("http://localhost:8001", api_key="secret")

        assert client._client.headers.get("X-Api-Key") == "secret"
