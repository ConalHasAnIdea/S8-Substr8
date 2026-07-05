"""
In-memory API key and local inference config store shared by the settings UI
and the discovery engines.

Values set here live in this process's memory only: they are never written to
disk, logs, or session cookies, and they are gone when the app restarts.
Environment variables remain the fallback so existing workflows keep working;
values entered on the settings page override the environment for the session.
"""

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

ANTHROPIC = "anthropic"
OPENAI = "openai"

ENV_VARS = {
    ANTHROPIC: "ANTHROPIC_API_KEY",
    OPENAI: "OPENAI_API_KEY",
}

LOCAL_BASE_URL_ENV = "LOCAL_LLM_BASE_URL"
LOCAL_MODEL_ENV = "LOCAL_LLM_MODEL"
DEFAULT_LOCAL_MODEL = "llama3.1"

_STORE: dict[str, str] = {}
_LOCAL_STORE: dict[str, str] = {}


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


def set_local_config(base_url: str, model: str | None = None) -> None:
    base_url = base_url.strip().rstrip("/")
    if not base_url:
        raise ValueError("Local endpoint URL must be non-empty.")
    _LOCAL_STORE["base_url"] = base_url
    _LOCAL_STORE["model"] = (model or DEFAULT_LOCAL_MODEL).strip() or DEFAULT_LOCAL_MODEL


def clear_local_config() -> None:
    _LOCAL_STORE.clear()


def get_local_base_url() -> str | None:
    return _LOCAL_STORE.get("base_url") or (os.environ.get(LOCAL_BASE_URL_ENV) or "").strip().rstrip("/") or None


def get_local_model() -> str:
    return _LOCAL_STORE.get("model") or (os.environ.get(LOCAL_MODEL_ENV) or "").strip() or DEFAULT_LOCAL_MODEL


def local_config_source() -> str | None:
    if _LOCAL_STORE.get("base_url"):
        return "settings"
    if (os.environ.get(LOCAL_BASE_URL_ENV) or "").strip():
        return "environment"
    return None


def validate_local_config(
    base_url: str,
    model: str | None,
    timeout: float = 1.5,
    opener=urlopen,
) -> tuple[bool, str | None, list[str]]:
    base_url = base_url.strip().rstrip("/")
    model = (model or DEFAULT_LOCAL_MODEL).strip() or DEFAULT_LOCAL_MODEL
    if not base_url:
        return False, "LOCAL_LLM_BASE_URL is not set. Enter a local endpoint URL.", []

    tags_url = f"{base_url}/api/tags"
    try:
        with opener(tags_url, timeout=timeout) as response:
            status = getattr(response, "status", 200)
            if not 200 <= status < 300:
                return False, f"{tags_url} returned HTTP {status}.", []
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        return False, f"{tags_url} returned HTTP {exc.code}.", []
    except URLError as exc:
        return False, f"Could not reach {tags_url}: {exc.reason}", []
    except OSError as exc:
        return False, f"Could not reach {tags_url}: {exc}", []
    except json.JSONDecodeError as exc:
        return False, f"{tags_url} did not return valid JSON: {exc}", []

    models = sorted({
        item.get("name") or item.get("model")
        for item in payload.get("models", [])
        if isinstance(item, dict) and (item.get("name") or item.get("model"))
    })
    if model not in models:
        return (
            False,
            f"Model {model!r} was not found at {tags_url}. Available models: {', '.join(models) if models else 'none'}.",
            models,
        )
    return True, None, models
