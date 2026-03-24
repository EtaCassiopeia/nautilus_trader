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

import httpx


class CliApiError(Exception):
    """
    Raised when the NautilusTrader API returns a non-2xx response.

    Parameters
    ----------
    status_code : int
        The HTTP status code.
    code : str
        The error code from the API.
    message : str
        The error message.

    """

    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(f"[{status_code}] {code}: {message}")


class CliClient:
    """
    Synchronous HTTP client for the CLI.

    Uses httpx for synchronous HTTP requests to the NautilusTrader API.

    Parameters
    ----------
    api_url : str
        Base URL of the NautilusTrader API.
    api_key : str, optional
        API key for ``X-Api-Key`` header authentication.
    timeout : float
        Request timeout in seconds.

    """

    def __init__(
        self,
        api_url: str,
        api_key: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        headers: dict[str, str] = {}
        if api_key:
            headers["X-Api-Key"] = api_key

        self._client = httpx.Client(
            base_url=api_url.rstrip("/"),
            headers=headers,
            timeout=timeout,
        )

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict:
        """
        Send a GET request.

        Parameters
        ----------
        path : str
            The API path.
        params : dict, optional
            Query parameters.

        Returns
        -------
        dict

        Raises
        ------
        CliApiError
            If the API returns a non-2xx response.

        """
        return self._request("GET", path, params=params)

    def post(self, path: str, json: dict[str, Any] | None = None) -> dict:
        """
        Send a POST request.

        Parameters
        ----------
        path : str
            The API path.
        json : dict, optional
            JSON body.

        Returns
        -------
        dict

        Raises
        ------
        CliApiError

        """
        return self._request("POST", path, json=json)

    def put(self, path: str, json: dict[str, Any] | None = None) -> dict:
        """Send a PUT request."""
        return self._request("PUT", path, json=json)

    def patch(self, path: str, json: dict[str, Any] | None = None) -> dict:
        """Send a PATCH request."""
        return self._request("PATCH", path, json=json)

    def delete(self, path: str) -> dict:
        """Send a DELETE request."""
        return self._request("DELETE", path)

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict:
        """Send an HTTP request and handle errors."""
        response = self._client.request(
            method,
            path,
            params=params,
            json=json,
        )

        if response.status_code >= 400:
            body = response.json()
            error = body.get("error", {})
            raise CliApiError(
                status_code=response.status_code,
                code=error.get("code", "UNKNOWN"),
                message=error.get("message", response.text),
            )

        return response.json()
