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
from urllib.request import Request, urlopen

ANTHROPIC = "anthropic"
OPENAI = "openai"

ENV_VARS = {
    ANTHROPIC: "ANTHROPIC_API_KEY",
    OPENAI: "OPENAI_API_KEY",
}

LOCAL_BASE_URL_ENV = "LOCAL_LLM_BASE_URL"
LOCAL_MODEL_ENV = "LOCAL_LLM_MODEL"
DEFAULT_LOCAL_MODEL = "llama3.1"

# Ollama's native REST verbs. If someone pastes the full endpoint they'd use
# to actually call the model (e.g. https://host/api/generate, copied straight
# from a RunPod/Ollama quickstart) instead of just the base URL, strip it back
# down rather than silently building a broken doubled-up path like
# https://host/api/generate/api/tags.
_KNOWN_OLLAMA_API_VERBS = {
    "generate", "chat", "tags", "show", "create", "copy", "delete",
    "pull", "push", "ps", "embed", "embeddings",
}


def normalize_local_base_url(base_url: str) -> str:
    base_url = (base_url or "").strip().rstrip("/")
    if not base_url:
        return ""
    segments = base_url.split("/")
    if len(segments) >= 2 and segments[-2] == "api" and segments[-1] in _KNOWN_OLLAMA_API_VERBS:
        segments = segments[:-2]
    elif segments[-1] == "api":
        segments = segments[:-1]
    return "/".join(segments).rstrip("/")


def _local_endpoint_opener(url: str, timeout: float):
    """Default opener for local-endpoint checks. Some reverse proxies in
    front of self-hosted models (observed with a RunPod proxy) return 403 for
    Python's default urllib User-Agent while a browser-like one works fine, so
    send a real one rather than let a working endpoint look unreachable."""
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 (Substr8 local-engine health check)"})
    return urlopen(request, timeout=timeout)


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


def set_local_config(base_url: str) -> None:
    """Local settings hold only the endpoint URL. Which model to use is a
    discovery-screen, per-run choice, not something saved here."""
    base_url = normalize_local_base_url(base_url)
    if not base_url:
        raise ValueError("Local endpoint URL must be non-empty.")
    _LOCAL_STORE["base_url"] = base_url


def clear_local_config() -> None:
    _LOCAL_STORE.clear()


def get_local_base_url() -> str | None:
    raw = _LOCAL_STORE.get("base_url") or os.environ.get(LOCAL_BASE_URL_ENV) or ""
    return normalize_local_base_url(raw) or None


def get_local_model() -> str:
    """Env var / default fallback only, for callers with no explicit per-run
    model (e.g. the CLI probes). The settings page never sets this."""
    return (os.environ.get(LOCAL_MODEL_ENV) or "").strip() or DEFAULT_LOCAL_MODEL


def local_config_source() -> str | None:
    if _LOCAL_STORE.get("base_url"):
        return "settings"
    if (os.environ.get(LOCAL_BASE_URL_ENV) or "").strip():
        return "environment"
    return None


def _query_local_tags(
    base_url: str,
    timeout: float,
    opener,
) -> tuple[bool, str | None, list[str]]:
    base_url = normalize_local_base_url(base_url)
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
    return True, None, models


def list_local_models(
    base_url: str | None = None,
    timeout: float = 1.5,
    opener=_local_endpoint_opener,
) -> tuple[bool, str | None, list[str]]:
    """Reachability plus the live model list, with no specific model required.
    Used to populate the discovery screen's model dropdown live from
    /api/tags, and to validate the endpoint URL on the settings page (which
    only ever cares whether the endpoint itself is reachable)."""
    resolved = base_url if base_url is not None else (get_local_base_url() or "")
    return _query_local_tags(resolved, timeout, opener)


def validate_local_config(
    base_url: str,
    model: str | None,
    timeout: float = 1.5,
    opener=_local_endpoint_opener,
) -> tuple[bool, str | None, list[str]]:
    """Reachability AND a specific model's presence at that endpoint."""
    model = (model or DEFAULT_LOCAL_MODEL).strip() or DEFAULT_LOCAL_MODEL
    reachable, error, models = _query_local_tags(base_url, timeout, opener)
    if not reachable:
        return False, error, []
    if model not in models:
        tags_url = f"{normalize_local_base_url(base_url)}/api/tags"
        return (
            False,
            f"Model {model!r} was not found at {tags_url}. Available models: {', '.join(models) if models else 'none'}.",
            models,
        )
    return True, None, models
