"""FastMCP server exposing Google Apps Script through the web app bridge."""

from __future__ import annotations

import json
from typing import Any, Literal

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from .bridge import BridgeClient, BridgeError
from .config import ConfigError, load_config

mcp = FastMCP(
    "apps-script",
    instructions=(
        "Edit and run Google Apps Script as the signed-in Google user through a "
        "personal web app bridge. Use run_code for one-off snippets (Sheets, Docs, "
        "Drive, Gmail, Calendar), and the project tools to read, write and run "
        "standalone script projects. Call bridge_status first if anything fails."
    ),
)

_client: BridgeClient | None = None


def get_client() -> BridgeClient:
    global _client
    if _client is None:
        config = load_config()
        _client = BridgeClient(config.url, config.key)
    return _client


async def _call(action: str, **params: Any) -> Any:
    try:
        return await get_client().call(action, **params)
    except (BridgeError, ConfigError) as exc:
        raise ToolError(str(exc)) from exc


def _run_result(data: dict[str, Any]) -> dict[str, Any]:
    """Turn a bridge execution result into a tool result or a tool error."""
    if data.get("success"):
        return {"result": data.get("result"), "logs": data.get("logs", [])}
    parts = [f"Script error: {data.get('error')}"]
    if data.get("stack"):
        parts.append(f"Stack:\n{data['stack']}")
    if data.get("logs"):
        parts.append("Logs before the error:\n" + "\n".join(data["logs"]))
    raise ToolError("\n\n".join(parts))


@mcp.tool
async def bridge_status() -> dict[str, Any]:
    """Check the bridge: its version, the Google account it runs as, and whether
    the Drive service is enabled (needed to create and edit projects)."""
    status = await _call("status")
    if not status.get("driveService"):
        status["hint"] = (
            "create_project, write_file and delete_file will fail. In the bridge "
            "editor click Services > + > Drive API > Add, then Deploy > Manage "
            "deployments > Edit > Version: New version."
        )
    return status


@mcp.tool
async def run_code(code: str) -> dict[str, Any]:
    """Run Apps Script (JavaScript, V8) as the user and return the result and logs.

    `code` is a function body: use `return` to send back a JSON-serializable
    value. All built-in services are available (SpreadsheetApp, DocumentApp,
    DriveApp, GmailApp, CalendarApp, UrlFetchApp, ...). console.log and
    Logger.log output is returned in `logs`. There is no active document, so
    open files by ID or URL. Executions stop after 6 minutes.
    """
    return _run_result(await _call("run_code", code=code))


@mcp.tool
async def list_projects(query: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """List standalone Apps Script projects in the user's Drive, optionally
    filtered by a title substring. Scripts bound to a Sheet/Doc/Form are not
    listed, but work with the other tools when you pass their script ID."""
    return await _call("list_projects", query=query, limit=limit)


@mcp.tool
async def create_project(title: str) -> dict[str, Any]:
    """Create a standalone Apps Script project with an empty Code file."""
    return await _call("create_project", title=title)


@mcp.tool
async def get_project(script_id: str) -> dict[str, Any]:
    """Get a standalone project's title and every file with its full source.
    `script_id` is the ID in the editor URL (script.google.com/d/<id>/edit)."""
    return await _call("get_project", script_id=script_id)


@mcp.tool
async def write_file(
    script_id: str,
    name: str,
    source: str,
    type: Literal["SERVER_JS", "HTML", "JSON"] | None = None,
) -> dict[str, Any]:
    """Create or fully replace one file in a project; other files are kept.

    `name` has no extension ("Code", not "Code.gs"). `type` defaults to
    SERVER_JS, or JSON for the "appsscript" manifest; use HTML for HtmlService
    templates.
    """
    return await _call("write_file", script_id=script_id, name=name, source=source, type=type)


@mcp.tool
async def delete_file(script_id: str, name: str) -> dict[str, Any]:
    """Delete one file from a project (the appsscript manifest cannot be deleted)."""
    return await _call("delete_file", script_id=script_id, name=name)


@mcp.tool
async def run_function(
    script_id: str, function_name: str, args: list[Any] | None = None
) -> dict[str, Any]:
    """Run a top-level function from a project's saved code and return its
    result and logs.

    The project's .gs files are loaded into the bridge and executed there, so
    it runs as the user but outside the real project: there is no active
    document (getActiveSpreadsheet() returns null), and the project's own
    libraries, advanced services, script properties and triggers are not
    available. Only standalone projects can be loaded. `args` must be JSON-serializable.
    """
    try:
        json.dumps(args)
    except (TypeError, ValueError) as exc:
        raise ToolError(f"args must be JSON-serializable: {exc}") from exc
    data = await _call(
        "run_function", script_id=script_id, function_name=function_name, args=args or []
    )
    return _run_result(data)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
