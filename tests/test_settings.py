import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ui.app as appmod
from discovery import api_keys


@pytest.fixture(autouse=True)
def clean_key_state(monkeypatch):
    api_keys._STORE.clear()
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    yield
    api_keys._STORE.clear()


@pytest.fixture
def client():
    return appmod.app.test_client()


def test_settings_page_renders(client):
    response = client.get("/settings")

    assert response.status_code == 200
    assert b"Not configured." in response.data
    assert b"held in memory" in response.data
    assert b'type="password"' in response.data


def test_invalid_key_is_marked_invalid_and_not_stored(client, monkeypatch):
    monkeypatch.setattr(appmod, "validate_anthropic_key", lambda key: (False, "authentication failed"))

    response = client.post("/settings", data={"anthropic_api_key": "sk-ant-bad-key"})

    assert response.status_code == 200
    assert b"Invalid" in response.data
    assert b"authentication failed" in response.data
    assert api_keys.key_source(api_keys.ANTHROPIC) is None
    assert api_keys.get_api_key(api_keys.ANTHROPIC) is None


def test_valid_key_is_marked_valid_and_stored(client, monkeypatch):
    monkeypatch.setattr(appmod, "validate_openai_key", lambda key: (True, None))

    response = client.post("/settings", data={"openai_api_key": "sk-openai-good-key"})

    assert response.status_code == 200
    assert b"Valid" in response.data
    assert api_keys.get_api_key(api_keys.OPENAI) == "sk-openai-good-key"
    assert api_keys.key_source(api_keys.OPENAI) == "settings"


def test_key_value_is_never_rendered_back(client, monkeypatch):
    monkeypatch.setattr(appmod, "validate_anthropic_key", lambda key: (True, None))

    response = client.post("/settings", data={"anthropic_api_key": "sk-ant-supersecret-value"})

    assert b"sk-ant-supersecret-value" not in response.data
    follow_up = client.get("/settings")
    assert b"sk-ant-supersecret-value" not in follow_up.data


def test_clearing_a_key_removes_it_from_the_store(client):
    api_keys.set_api_key(api_keys.ANTHROPIC, "sk-ant-session-key")

    response = client.post("/settings/clear", data={"provider": "anthropic"})

    assert response.status_code == 302
    assert api_keys.key_source(api_keys.ANTHROPIC) is None
    assert api_keys.get_api_key(api_keys.ANTHROPIC) is None


def test_environment_fallback_when_store_is_empty(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-only-key")

    assert api_keys.get_api_key(api_keys.ANTHROPIC) == "env-only-key"
    assert api_keys.key_source(api_keys.ANTHROPIC) == "environment"


def test_saving_a_key_enables_the_engine_options_in_the_ui(client, monkeypatch):
    before = client.get("/")
    assert b"Claude - Not configured" in before.data
    assert b"OpenAI GPT-5.5 - Not configured" in before.data

    monkeypatch.setattr(appmod, "validate_anthropic_key", lambda key: (True, None))
    monkeypatch.setattr(appmod, "validate_openai_key", lambda key: (True, None))
    client.post("/settings", data={"anthropic_api_key": "sk-ant-live", "openai_api_key": "sk-openai-live"})

    after = client.get("/")
    assert b"Claude - Not configured" not in after.data
    assert b"OpenAI GPT-5.5 - Not configured" not in after.data
    assert b"Run with Claude" in after.data or b"Claude (per-mapping comparison)" in after.data


def test_engines_prefer_in_memory_key_over_environment(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-anthropic-key")
    monkeypatch.setenv("OPENAI_API_KEY", "env-openai-key")
    api_keys.set_api_key(api_keys.ANTHROPIC, "settings-anthropic-key")
    api_keys.set_api_key(api_keys.OPENAI, "settings-openai-key")

    assert api_keys.get_api_key(api_keys.ANTHROPIC) == "settings-anthropic-key"
    assert api_keys.get_api_key(api_keys.OPENAI) == "settings-openai-key"

    pytest.importorskip("anthropic")
    from discovery.claude_discovery_engine import ClaudeDiscoveryEngine

    assert ClaudeDiscoveryEngine().client.api_key == "settings-anthropic-key"

    pytest.importorskip("openai")
    from discovery.openai_discovery_engine import OpenAIDiscoveryEngine

    assert OpenAIDiscoveryEngine().client.api_key == "settings-openai-key"
