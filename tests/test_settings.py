import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ui.app as appmod
from discovery import api_keys



@pytest.fixture(autouse=True)
def clean_key_state(monkeypatch):
    api_keys._STORE.clear(); api_keys._LOCAL_STORE.clear()
    api_keys.clear_local_config()
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LOCAL_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LOCAL_LLM_MODEL", raising=False)
    yield
    api_keys._STORE.clear(); api_keys._LOCAL_STORE.clear()
    api_keys.clear_local_config()


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
    assert b'value="FrontierLLM (per-mapping comparison)" disabled' in before.data

    monkeypatch.setattr(appmod, "validate_anthropic_key", lambda key: (True, None))
    monkeypatch.setattr(appmod, "validate_openai_key", lambda key: (True, None))
    client.post("/settings", data={"anthropic_api_key": "sk-ant-live", "openai_api_key": "sk-openai-live"})

    after = client.get("/")
    assert b'value="FrontierLLM (per-mapping comparison)" disabled' not in after.data
    assert b"Claude Sonnet 5" in after.data
    assert b"ChatGPT-5.5" in after.data


def local_status_stub():
    return {
        "configured": True,
        "reachable": True,
        "label": "Connected",
        "message": "Reached http://local-pod.example/api/tags.",
        "base_url": api_keys.get_local_base_url() or "",
        "models": ["llama3.1"],
        "source": api_keys.local_config_source(),
    }


def test_valid_local_config_is_marked_valid_and_stored(client, monkeypatch):
    monkeypatch.setattr(appmod, "validate_local_settings", lambda base_url: (True, None))
    monkeypatch.setattr(appmod, "local_llm_status", local_status_stub)

    response = client.post("/settings", data={"local_llm_base_url": "http://local-pod.example"})

    assert response.status_code == 200
    assert b"Valid" in response.data
    assert b"Stored in memory for this session." in response.data
    assert api_keys.get_local_base_url() == "http://local-pod.example"
    assert api_keys.local_config_source() == "settings"


def test_unreachable_local_config_is_marked_invalid_with_error(client, monkeypatch):
    monkeypatch.setattr(
        appmod,
        "validate_local_settings",
        lambda base_url: (False, "Could not reach http://local-pod.example/api/tags: connection refused"),
    )
    monkeypatch.setattr(appmod, "local_llm_status", lambda: {
        "configured": False,
        "reachable": False,
        "label": "Not configured",
        "message": "Set LOCAL_LLM_BASE_URL to enable the local engine.",
        "base_url": "",
        "models": [],
        "source": None,
    })

    response = client.post("/settings", data={"local_llm_base_url": "http://local-pod.example"})

    assert response.status_code == 200
    assert b"Invalid" in response.data
    assert b"connection refused" in response.data
    assert api_keys.get_local_base_url() is None


def test_clearing_local_config_removes_settings_override(client, monkeypatch):
    api_keys.set_local_config("http://settings-pod.example")

    response = client.post("/settings/local/clear")

    assert response.status_code == 302
    assert api_keys.local_config_source() is None
    assert api_keys.get_local_base_url() is None


def test_local_status_shows_environment_source_and_url(client, monkeypatch):
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", "http://env-pod.example")
    monkeypatch.setattr(appmod, "local_llm_status", lambda: {
        "configured": True,
        "reachable": True,
        "label": "Connected",
        "message": "Reached http://env-pod.example/api/tags.",
        "base_url": "http://env-pod.example",
        "models": ["llama3.1"],
        "source": "environment",
    })

    response = client.get("/settings")

    assert b"Loaded from environment: http://env-pod.example" in response.data
    assert b"Endpoint: http://env-pod.example" in response.data


def test_settings_page_no_longer_collects_a_model_field(client):
    response = client.get("/settings")

    assert b'name="local_llm_model"' not in response.data
    assert b"which model to use" in response.data.lower()


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


def test_local_engine_prefers_in_memory_base_url_over_environment(monkeypatch):
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", "http://env-pod.example")
    api_keys.set_local_config("http://settings-pod.example")

    class FakeOpenAIClientFactory:
        def __init__(self):
            self.kwargs = None

        def OpenAI(self, **kwargs):
            self.kwargs = kwargs
            return object()

    fake_openai = FakeOpenAIClientFactory()
    from discovery import local_discovery_engine

    monkeypatch.setattr(local_discovery_engine, "openai", fake_openai)

    engine = local_discovery_engine.LocalDiscoveryEngine(model="llama3.1")

    assert fake_openai.kwargs["base_url"] == "http://settings-pod.example/v1"
