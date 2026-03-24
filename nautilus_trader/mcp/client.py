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


class NautilusApiError(Exception):
    """
    Raised when the NautilusTrader API returns a non-2xx response.

    Parameters
    ----------
    status_code : int
        The HTTP status code.
    code : str
        The error code from the API response.
    message : str
        The error message from the API response.

    """

    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(f"[{status_code}] {code}: {message}")


class NautilusClient:
    """
    HTTP client wrapper for the NautilusTrader REST API.

    Provides typed methods for all HTTP verbs with automatic error handling
    and API key authentication.

    Parameters
    ----------
    api_url : str
        Base URL of the NautilusTrader API (e.g., "http://localhost:8001").
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
        self._base_url = api_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._session: httpx.AsyncClient | None = None

    @property
    def base_url(self) -> str:
        """Return the base URL."""
        return self._base_url

    @property
    def is_connected(self) -> bool:
        """Return whether the client session is active."""
        return self._session is not None and not self._session.is_closed

    async def start(self) -> None:
        """Initialize the HTTP session."""
        headers: dict[str, str] = {}
        if self._api_key:
            headers["X-Api-Key"] = self._api_key

        self._session = httpx.AsyncClient(
            base_url=self._base_url,
            headers=headers,
            timeout=self._timeout,
        )

    async def stop(self) -> None:
        """Close the HTTP session."""
        if self._session is not None:
            await self._session.aclose()
            self._session = None

    async def get(self, path: str, params: dict[str, Any] | None = None) -> dict:
        """
        Send a GET request.

        Parameters
        ----------
        path : str
            The API path (e.g., "/api/v1/node/status").
        params : dict, optional
            Query parameters.

        Returns
        -------
        dict

        Raises
        ------
        NautilusApiError
            If the API returns a non-2xx response.

        """
        return await self._request("GET", path, params=params)

    async def post(self, path: str, json: dict[str, Any] | None = None) -> dict:
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
        NautilusApiError
            If the API returns a non-2xx response.

        """
        return await self._request("POST", path, json=json)

    async def put(self, path: str, json: dict[str, Any] | None = None) -> dict:
        """
        Send a PUT request.

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
        NautilusApiError
            If the API returns a non-2xx response.

        """
        return await self._request("PUT", path, json=json)

    async def patch(self, path: str, json: dict[str, Any] | None = None) -> dict:
        """
        Send a PATCH request.

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
        NautilusApiError
            If the API returns a non-2xx response.

        """
        return await self._request("PATCH", path, json=json)

    async def delete(self, path: str) -> dict:
        """
        Send a DELETE request.

        Parameters
        ----------
        path : str
            The API path.

        Returns
        -------
        dict

        Raises
        ------
        NautilusApiError
            If the API returns a non-2xx response.

        """
        return await self._request("DELETE", path)

    async def health_check(self) -> bool:
        """
        Check if the NautilusTrader API is reachable.

        Returns
        -------
        bool

        """
        try:
            await self.get("/health")
            return True
        except Exception:
            return False

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict:
        """Send an HTTP request and handle errors."""
        if self._session is None:
            raise RuntimeError(
                "Client session not initialized. Call start() first.",
            )

        response = await self._session.request(
            method,
            path,
            params=params,
            json=json,
        )

        if response.status_code >= 400:
            body = response.json()
            error = body.get("error", {})
            raise NautilusApiError(
                status_code=response.status_code,
                code=error.get("code", "UNKNOWN"),
                message=error.get("message", response.text),
            )

        return response.json()
