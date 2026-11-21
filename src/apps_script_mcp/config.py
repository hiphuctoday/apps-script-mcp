"""Bridge connection settings, read from the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass

URL_VAR = "APPS_SCRIPT_BRIDGE_URL"
KEY_VAR = "APPS_SCRIPT_BRIDGE_KEY"


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    url: str
    key: str


def load_config(env: dict[str, str] | None = None) -> Config:
    env = os.environ if env is None else env
    url = (env.get(URL_VAR) or "").strip()
    key = (env.get(KEY_VAR) or "").strip()
    missing = [name for name, value in ((URL_VAR, url), (KEY_VAR, key)) if not value]
    if missing:
        raise ConfigError(
            f"Missing environment variable(s): {', '.join(missing)}. "
            "See README.md for the one-time bridge setup."
        )
    if not url.startswith("https://script.google.com/") or not url.endswith("/exec"):
        raise ConfigError(
            f"{URL_VAR} must be the web app URL, in the form "
            "https://script.google.com/macros/s/<id>/exec"
        )
    return Config(url=url, key=key)
