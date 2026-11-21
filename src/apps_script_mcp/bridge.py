"""HTTP client for the Apps Script web app bridge."""

from __future__ import annotations

from typing import Any

import httpx

# Apps Script allows 6 minutes per execution; leave a little headroom.
DEFAULT_TIMEOUT = 370.0


class BridgeError(Exception):
    pass


class BridgeClient:
    def __init__(
        self,
        url: str,
        key: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._url = url
        self._key = key
        self._transport = transport
        self._timeout = timeout

    async def call(self, action: str, **params: Any) -> Any:
        """Call one bridge action and return its data, or raise BridgeError."""
        payload = {
            "key": self._key,
            "action": action,
            "params": {k: v for k, v in params.items() if v is not None},
        }
        try:
            # The web app answers with a 302 to script.googleusercontent.com,
            # which must be followed with a GET.
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.post(self._url, json=payload)
        except httpx.TimeoutException as exc:
            raise BridgeError(
                "The bridge did not answer in time (Apps Script stops after 6 minutes)."
            ) from exc
        except httpx.HTTPError as exc:
            raise BridgeError(f"Could not reach the bridge: {exc}") from exc

        try:
            body = response.json()
        except ValueError:
            body = None
        if not isinstance(body, dict) or "ok" not in body:
            raise BridgeError(
                f"The bridge returned HTTP {response.status_code} without a JSON result. "
                "Check that the URL ends in /exec, that the web app is deployed with "
                "'Who has access: Anyone', and that the latest code is deployed as a new version."
            )
        if not body["ok"]:
            raise BridgeError(str(body.get("error") or "Unknown bridge error"))
        return body.get("data")
