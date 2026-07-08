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
def client(tmp_path, monkeypatch):
    # Route persists probe-run history to OUTPUT_DIR on every POST - redirect
    # it to a throwaway directory so tests never touch the real demo data.
    monkeypatch.setattr(appmod, "OUTPUT_DIR", tmp_path)
    return appmod.app.test_client()


def test_security_page_renders_with_only_mock_when_nothing_is_configured(client):
    response = client.get("/security")

    assert response.status_code == 200
    assert b">Substr8<" in response.data
    assert b"Held (mocked) 5/5" in response.data
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
    assert b">Substr8<" in response.data


def test_security_nav_link_present_in_base_template():
    template = (Path(__file__).resolve().parents[1] / "ui" / "templates" / "base.html").read_text(encoding="utf-8")

    assert "url_for('security')" in template


def test_security_page_title_and_subheader(client):
    response = client.get("/security")
    html = response.data.decode()

    assert "<h1>Security - Prompt Injection Test</h1>" in html
    assert "Payloads planted as traps in the evidence corpus, used to test prompt injection resistance" in html


def test_summary_table_shows_substr8_column_and_scenario_rows(client):
    response = client.get("/security")
    html = response.data.decode()

    assert "Current Run" in html
    assert "SubStr8_Logo.png" in html
    assert "anthropic-logo.png" in html
    assert "oai-logo.png" in html
    assert "commentary_fake_citation" in html
    assert "verdict-held" in html
    assert "held (mocked)" in html


def test_history_is_empty_before_any_probe_run(client):
    response = client.get("/security")

    assert b"No probe runs recorded yet" in response.data


def test_post_persists_a_history_entry_visible_on_next_get(client):
    post_response = client.post("/security")
    assert post_response.status_code == 200

    get_response = client.get("/security")
    html = get_response.data.decode()

    assert "No probe runs recorded yet" not in html
    assert "local-reviewer" in html


def test_history_survives_across_requests_not_just_the_posting_one(client, tmp_path):
    client.post("/security")

    from governance.security_probe_log import load_security_probe_runs

    records = load_security_probe_runs(tmp_path)
    assert len(records) == 1
    assert records[0]["engines"][0]["key"] == "Mock"
    assert records[0]["engines"][0]["held"] == 5


def test_local_engine_gets_one_column_per_available_model(client, monkeypatch):
    api_keys.set_local_config("http://fake-local-pod.example")
    monkeypatch.setattr(appmod, "local_llm_status", lambda: {
        "configured": True,
        "reachable": True,
        "label": "Connected",
        "message": "Reached http://fake-local-pod.example/api/tags.",
        "base_url": "http://fake-local-pod.example",
        "models": ["llama3.1", "nemotron-3-nano:4b"],
        "source": "settings",
    })

    class FakeEngine:
        def __init__(self, model=None, base_url=None, client=None):
            self.model = model

        def propose_one(self, data_dir, source_field, source_value, destination_fields):
            return {
                "source_field": source_field,
                "source_value": source_value,
                "destination_fields": destination_fields,
                "transformation_logic": "link_down -> assignment_group=Transport NOC",
                "confidence_score": 0.86,
                "reasoning": "ok",
                "evidence_citations": ["TKT-1001"],
                "governance_status": "Pending Approval",
                "validation_flags": [],
            }

    import discovery.local_discovery_engine as lde
    monkeypatch.setattr(lde, "LocalDiscoveryEngine", FakeEngine)

    response = client.post("/security")
    html = response.data.decode()

    assert response.status_code == 200
    assert "Local (llama3.1)" in html
    assert "Local (nemotron-3-nano:4b)" in html
    assert "llamalogo.png" in html
    assert "Nemotronlogo.png" in html


def test_security_summary_table_uses_logo_headers():
    columns = [
        {"key": "Mock", "label": "Substr8", "status": "skipped", "logo_filename": "SubStr8_Logo.png", "logo_alt": "Substr8 logo"},
        {"key": "Claude", "label": "Claude", "status": "skipped", "logo_filename": "anthropic-logo.png", "logo_alt": "Anthropic logo"},
    ]

    summary = appmod.build_security_summary_table(columns)

    assert summary["engine_headers"] == [
        {"label": "Substr8", "logo_filename": "SubStr8_Logo.png", "logo_alt": "Substr8 logo"},
        {"label": "Claude", "logo_filename": "anthropic-logo.png", "logo_alt": "Anthropic logo"},
    ]
