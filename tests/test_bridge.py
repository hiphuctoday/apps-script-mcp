import asyncio
import json

import httpx
import pytest

from apps_script_mcp.bridge import BridgeClient, BridgeError
from apps_script_mcp.config import ConfigError, load_config

URL = "https://script.google.com/macros/s/abc/exec"
REDIRECT = "https://script.googleusercontent.com/macros/echo?user_content_key=x"


def make_client(handler):
    return BridgeClient(URL, "secret", transport=httpx.MockTransport(handler))


def test_call_follows_redirect_and_returns_data():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "script.google.com":
            seen["method"] = request.method
            seen["body"] = json.loads(request.content)
            return httpx.Response(302, headers={"location": REDIRECT})
        seen["redirect_method"] = request.method
        return httpx.Response(200, json={"ok": True, "data": {"version": "1.0.0"}})

    data = asyncio.run(make_client(handler).call("status", skipped=None, kept=1))

    assert data == {"version": "1.0.0"}
    assert seen["method"] == "POST"
    assert seen["redirect_method"] == "GET"
    assert seen["body"] == {"key": "secret", "action": "status", "params": {"kept": 1}}


def test_bridge_error_is_raised():
    def handler(request):
        return httpx.Response(200, json={"ok": False, "error": "Invalid bridge key."})

    with pytest.raises(BridgeError, match="Invalid bridge key"):
        asyncio.run(make_client(handler).call("status"))


def test_html_response_gives_setup_hint():
    def handler(request):
        return httpx.Response(200, text="<html>Sign in</html>")

    with pytest.raises(BridgeError, match="Who has access: Anyone"):
        asyncio.run(make_client(handler).call("status"))


def test_network_failure_is_wrapped():
    def handler(request):
        raise httpx.ConnectError("no route")

    with pytest.raises(BridgeError, match="Could not reach the bridge"):
        asyncio.run(make_client(handler).call("status"))


def test_load_config():
    env = {"APPS_SCRIPT_BRIDGE_URL": URL, "APPS_SCRIPT_BRIDGE_KEY": "k"}
    assert load_config(env).url == URL

    with pytest.raises(ConfigError, match="APPS_SCRIPT_BRIDGE_KEY"):
        load_config({"APPS_SCRIPT_BRIDGE_URL": URL})

    with pytest.raises(ConfigError, match="/exec"):
        load_config({**env, "APPS_SCRIPT_BRIDGE_URL": "https://script.google.com/macros/s/abc/dev"})
