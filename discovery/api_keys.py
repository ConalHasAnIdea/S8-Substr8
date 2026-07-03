"""
In-memory API key store shared by the settings UI and the discovery engines.

Keys set here live in this process's memory only: they are never written to
disk, logs, or session cookies, and they are gone when the app restarts.
Environment variables remain the fallback so existing workflows keep working;
a key entered on the settings page overrides the environment for the session.
"""

import os

ANTHROPIC = "anthropic"
OPENAI = "openai"

ENV_VARS = {
    ANTHROPIC: "ANTHROPIC_API_KEY",
    OPENAI: "OPENAI_API_KEY",
}

_STORE: dict[str, str] = {}


def _require_known(provider: str) -> None:
    if provider not in ENV_VARS:
        raise ValueError(f"Unknown API key provider: {provider}")


def set_api_key(provider: str, value: str) -> None:
    _require_known(provider)
    if not value:
        raise ValueError("API key value must be non-empty.")
    _STORE[provider] = value


def clear_api_key(provider: str) -> None:
    _require_known(provider)
    _STORE.pop(provider, None)


def get_api_key(provider: str) -> str | None:
    """Resolve a key: in-memory store first, environment variable fallback."""
    _require_known(provider)
    return _STORE.get(provider) or os.environ.get(ENV_VARS[provider])


def key_source(provider: str) -> str | None:
    """Where the effective key comes from: 'settings', 'environment', or None."""
    _require_known(provider)
    if _STORE.get(provider):
        return "settings"
    if os.environ.get(ENV_VARS[provider]):
        return "environment"
    return None
