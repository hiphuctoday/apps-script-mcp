import asyncio

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from apps_script_mcp import server
from apps_script_mcp.bridge import BridgeError


class FakeBridge:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    async def call(self, action, **params):
        self.calls.append((action, params))
        response = self.responses[action]
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture
def bridge(monkeypatch):
    def install(responses):
        fake = FakeBridge(responses)
        monkeypatch.setattr(server, "_client", fake)
        return fake

    return install


def call_tool(name, args=None):
    async def run():
        async with Client(server.mcp) as client:
            return await client.call_tool(name, args or {})

    return asyncio.run(run())


def test_all_tools_are_registered():
    async def run():
        async with Client(server.mcp) as client:
            return {tool.name for tool in await client.list_tools()}

    assert asyncio.run(run()) == {
        "bridge_status",
        "run_code",
        "list_projects",
        "create_project",
        "get_project",
        "write_file",
        "delete_file",
        "run_function",
    }


def test_run_code_success(bridge):
    fake = bridge({"run_code": {"success": True, "result": 5, "logs": ["hi"]}})
    result = call_tool("run_code", {"code": "return 2+3"})
    assert result.data == {"result": 5, "logs": ["hi"]}
    assert fake.calls == [("run_code", {"code": "return 2+3"})]


def test_run_code_script_error_includes_logs(bridge):
    bridge(
        {
            "run_code": {
                "success": False,
                "error": "x is not defined",
                "stack": "ReferenceError: x is not defined",
                "logs": ["before"],
            }
        }
    )
    with pytest.raises(ToolError) as excinfo:
        call_tool("run_code", {"code": "x"})
    message = str(excinfo.value)
    assert "x is not defined" in message
    assert "before" in message


def test_bridge_error_becomes_tool_error(bridge):
    bridge({"get_project": BridgeError("Could not read script abc (HTTP 403).")})
    with pytest.raises(ToolError, match="403"):
        call_tool("get_project", {"script_id": "abc"})


def test_status_adds_hint_when_drive_service_is_off(bridge):
    bridge({"status": {"version": "1.1.0", "driveService": False}})
    assert "Drive API" in call_tool("bridge_status").data["hint"]


def test_status_has_no_hint_when_ready(bridge):
    bridge({"status": {"version": "1.1.0", "driveService": True}})
    assert "hint" not in call_tool("bridge_status").data


def test_run_function_passes_args(bridge):
    fake = bridge({"run_function": {"success": True, "result": 5, "logs": []}})
    result = call_tool(
        "run_function", {"script_id": "abc", "function_name": "add", "args": [2, 3]}
    )
    assert result.data["result"] == 5
    assert fake.calls == [
        ("run_function", {"script_id": "abc", "function_name": "add", "args": [2, 3]})
    ]
