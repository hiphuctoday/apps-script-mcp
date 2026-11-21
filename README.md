# apps-script-mcp

An MCP server that lets Claude write and run Google Apps Script in your Google account, with no Google Cloud Console setup.

It works through a small "bridge" script that you deploy once as a web app in your own account. The local server calls it with a secret key, and the bridge runs as you.

## Setup

Requires [uv](https://docs.astral.sh/uv/).

1. Create a new project at <https://script.google.com> and paste in [bridge/Code.gs](bridge/Code.gs).
2. Click **+** next to **Services** and add **Drive API**.
3. In **Project Settings**, tick **Show "appsscript.json" manifest file in editor**, then paste in [bridge/appsscript.json](bridge/appsscript.json).
4. Run the `setup` function, approve all permissions, and copy the key from the execution log.
5. Click **Deploy > New deployment > Web app**, with **Execute as: Me** and **Who has access: Anyone**. Copy the `/exec` URL.
6. Add the server to your MCP client:

```json
{
  "mcpServers": {
    "apps-script": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/apps-script-mcp", "apps-script-mcp"],
      "env": {
        "APPS_SCRIPT_BRIDGE_URL": "https://script.google.com/macros/s/.../exec",
        "APPS_SCRIPT_BRIDGE_KEY": "your key"
      }
    }
  }
}
```

Ask Claude to call `bridge_status` to check that it works.

## Tools

| Tool | What it does |
|---|---|
| `bridge_status` | Checks the bridge and the account it runs as |
| `run_code` | Runs a snippet as you and returns its result and logs |
| `list_projects` | Lists standalone script projects in your Drive |
| `create_project` | Creates a standalone project |
| `get_project` | Reads all files of a project |
| `write_file` | Creates or replaces one file |
| `delete_file` | Deletes one file |
| `run_function` | Runs a function from a project's saved code |

## Security

Anyone with both the URL and the key can do everything the manifest scopes allow, including reading your mail and files. Treat the key like a password.

- Remove scopes you do not need from `appsscript.json`.
- Run `rotateKey` in the bridge editor to replace the key.
- Archive the deployment to turn the bridge off.

## Limits

- Only standalone projects can be edited, not scripts bound to a Sheet, Doc or Form.
- `run_function` runs inside the bridge, so there is no active document and the project's own libraries, properties and triggers are unavailable.
- There is no deploy tool; publish from the Apps Script editor.
- Each call stops after 6 minutes.

## Development

```sh
uv sync
uv run pytest
```

## License

[MIT](LICENSE)
