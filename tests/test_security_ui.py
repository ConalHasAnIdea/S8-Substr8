import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ui.app as appmod
from discovery import api_keys


@pytest.fixture(autouse=True)
def clean_key_state(monkeypatch):
    api_keys._STORE.clear()
    api_keys._LOCAL_STORE.clear()
    api_keys.clear_local_config()
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LOCAL_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LOCAL_LLM_MODEL", raising=False)
    yield
    api_keys._STORE.clear()
    api_keys._LOCAL_STORE.clear()
    api_keys.clear_local_config()


@pytest.fixture
def client():
    return appmod.app.test_client()


def test_security_page_renders_with_only_mock_when_nothing_is_configured(client):
    response = client.get("/security")

    assert response.status_code == 200
    assert b">Mock<" in response.data
    assert b"Held 5/5" in response.data
    assert b"Not configured" in response.data


def test_security_page_shows_skipped_state_for_unconfigured_engines(client):
    response = client.get("/security")

    assert response.status_code == 200
    assert b"Not configured - add an Anthropic API key" in response.data
    assert b"Not configured - add an OpenAI API key" in response.data
    assert b"No local endpoint configured" in response.data


def test_security_page_never_500s_on_post_with_nothing_configured(client):
    response = client.post("/security")

    assert response.status_code == 200
    assert b">Mock<" in response.data


def test_security_nav_link_present_in_base_template():
    template = (Path(__file__).resolve().parents[1] / "ui" / "templates" / "base.html").read_text(encoding="utf-8")

    assert "url_for('security')" in template
