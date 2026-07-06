import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from discovery import local_discovery_engine
from discovery.api_keys import (
    DEFAULT_LOCAL_MODEL,
    LOCAL_BASE_URL_ENV,
    LOCAL_MODEL_ENV,
    clear_local_config,
    get_local_base_url,
    list_local_models,
    normalize_local_base_url,
    set_local_config,
    validate_local_config,
)
from discovery.local_discovery_engine import (
    LocalDiscoveryEngine,
    local_base_url,
    local_model_name,
)
from governance import local_runs


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture(autouse=True)
def clean_local_config(monkeypatch):
    clear_local_config()
    monkeypatch.delenv(LOCAL_BASE_URL_ENV, raising=False)
    monkeypatch.delenv(LOCAL_MODEL_ENV, raising=False)
    yield
    clear_local_config()


class FakeChatCompletions:
    def __init__(self, content: str):
        self.content = content
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=self.content)
                )
            ]
        )


class FakeClient:
    def __init__(self, content: str):
        self.completions = FakeChatCompletions(content)
        self.chat = SimpleNamespace(completions=self.completions)


class FakeOpenAIClientFactory:
    def __init__(self):
        self.kwargs = None

    def OpenAI(self, **kwargs):
        self.kwargs = kwargs
        return FakeClient(json.dumps({
            "source_field": "probableCause",
            "source_value": "link_down",
            "destination_fields": ["assignment_group"],
            "transformation_logic": "link_down -> assignment_group=Transport NOC",
            "confidence_score": 0.86,
            "reasoning": "Evidence supports Transport NOC.",
            "evidence_citations": ["TKT-1001"],
        }))


def successful_payload(citations=None) -> str:
    return json.dumps({
        "source_field": "probableCause",
        "source_value": "link_down",
        "destination_fields": ["assignment_group"],
        "transformation_logic": "link_down -> assignment_group=Transport NOC",
        "confidence_score": 0.86,
        "reasoning": "Evidence supports Transport NOC.",
        "evidence_citations": citations or ["TKT-1001"],
    })


def test_missing_base_url_fails_with_clear_message(monkeypatch):
    monkeypatch.delenv(LOCAL_BASE_URL_ENV, raising=False)

    with pytest.raises(RuntimeError) as exc:
        LocalDiscoveryEngine()

    assert "LOCAL_LLM_BASE_URL is not set" in str(exc.value)
    assert "Set LOCAL_LLM_BASE_URL" in str(exc.value)


def test_env_vars_control_base_url_and_model(monkeypatch):
    fake_openai = FakeOpenAIClientFactory()
    monkeypatch.setattr(local_discovery_engine, "openai", fake_openai)
    monkeypatch.setenv(LOCAL_BASE_URL_ENV, "http://local-pod.example")
    monkeypatch.setenv(LOCAL_MODEL_ENV, "mistral-local")

    engine = LocalDiscoveryEngine()

    assert engine.model == "mistral-local"
    assert fake_openai.kwargs["base_url"] == "http://local-pod.example/v1"
    assert fake_openai.kwargs["api_key"] == "ollama"


def test_model_defaults_to_llama31_when_unset(monkeypatch):
    monkeypatch.delenv(LOCAL_MODEL_ENV, raising=False)

    assert local_model_name() == DEFAULT_LOCAL_MODEL


def test_base_url_has_no_hardcoded_default(monkeypatch):
    monkeypatch.delenv(LOCAL_BASE_URL_ENV, raising=False)

    with pytest.raises(RuntimeError):
        local_base_url()


def test_successful_response_uses_shared_prompt_and_citation_validation():
    client = FakeClient(successful_payload(["TKT-1001", "TKT-9999"]))
    engine = LocalDiscoveryEngine(client=client)

    result = engine.propose_one(
        DATA_DIR,
        "probableCause",
        "link_down",
        ["assignment_group"],
    )

    call = client.completions.calls[0]
    assert call["model"] == DEFAULT_LOCAL_MODEL
    assert call["messages"][0]["role"] == "system"
    assert "Do not invent ticket IDs" in call["messages"][0]["content"]
    assert call["messages"][1]["role"] == "user"
    assert "TKT-1001" in call["messages"][1]["content"]

    assert result["source_field"] == "probableCause"
    assert result["source_value"] == "link_down"
    assert result["destination_fields"] == ["assignment_group"]
    assert result["confidence_score"] == 0.86
    assert result["governance_status"] == "Needs Clarification"
    assert result["evidence_citations"] == ["TKT-1001"]
    assert "fabricated_citations" in result["validation_flags"][0]
    assert "TKT-9999" in result["validation_flags"][0]


def test_local_status_pings_api_tags_without_real_network(monkeypatch):
    calls = []

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"models": [{"name": "mistral-local"}]}'

    def fake_urlopen(url, timeout):
        calls.append((url, timeout))
        return FakeResponse()

    valid, error, models = validate_local_config(
        "http://local-pod.example",
        "mistral-local",
        timeout=0.25,
        opener=fake_urlopen,
    )

    assert valid is True
    assert error is None
    assert models == ["mistral-local"]
    assert calls == [("http://local-pod.example/api/tags", 0.25)]

    set_local_config("http://local-pod.example")
    monkeypatch.setattr(local_runs, "list_local_models", lambda base_url, timeout=1.5: (True, None, ["mistral-local"]))
    status = local_runs.local_llm_status(timeout=0.25)
    assert status["configured"] is True
    assert status["reachable"] is True
    assert status["label"] == "Connected"
    assert status["models"] == ["mistral-local"]
    assert status["source"] == "settings"


def test_local_status_reports_missing_endpoint_without_network(monkeypatch):
    monkeypatch.delenv(LOCAL_BASE_URL_ENV, raising=False)

    status = local_runs.local_llm_status()

    assert status["configured"] is False
    assert status["reachable"] is False
    assert "Set LOCAL_LLM_BASE_URL" in status["message"]


def test_list_local_models_returns_available_models_without_requiring_a_match():
    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"models": [{"name": "llama3.1"}, {"name": "mistral-local"}]}'

    def fake_urlopen(url, timeout):
        return FakeResponse()

    reachable, error, models = list_local_models(
        "http://local-pod.example",
        timeout=0.25,
        opener=fake_urlopen,
    )

    assert reachable is True
    assert error is None
    assert models == ["llama3.1", "mistral-local"]


def test_list_local_models_reports_unreachable_state_distinctly_from_missing_model():
    import urllib.error

    def fake_urlopen(url, timeout):
        raise urllib.error.URLError(ConnectionRefusedError("Connection refused"))

    reachable, error, models = list_local_models(
        "http://local-pod.example",
        timeout=0.25,
        opener=fake_urlopen,
    )

    assert reachable is False
    assert "Could not reach" in error
    assert models == []


def test_run_local_comparison_uses_explicit_model_parameter_over_env_and_default(monkeypatch, tmp_path):
    monkeypatch.setenv(LOCAL_MODEL_ENV, "env-model")

    class FakeEngine:
        def __init__(self):
            self.received_model = None

        def propose_one(self, data_dir, source_field, source_value, destination_fields):
            return {
                "source_field": source_field,
                "source_value": source_value,
                "destination_fields": destination_fields,
                "transformation_logic": "link_down -> assignment_group=Transport NOC",
                "confidence_score": 0.86,
                "reasoning": "Evidence supports Transport NOC.",
                "evidence_citations": ["TKT-1001"],
                "governance_status": "Pending Approval",
                "validation_flags": [],
            }

    mapping = {
        "source_field": "probableCause",
        "source_value": "link_down",
        "destination_fields": ["assignment_group"],
        "confidence_score": 0.86,
        "governance_status": "Pending Approval",
    }

    entry = local_runs.run_local_comparison(
        tmp_path,
        DATA_DIR,
        "Assurance",
        mapping,
        engine=FakeEngine(),
        model="picked-from-dropdown",
    )

    assert entry["model"] == "picked-from-dropdown"
    assert entry["model_label"] == "picked-from-dropdown"


def test_run_local_comparison_falls_back_to_env_when_no_model_given(monkeypatch, tmp_path):
    monkeypatch.setenv(LOCAL_MODEL_ENV, "env-model")

    class FakeEngine:
        def propose_one(self, data_dir, source_field, source_value, destination_fields):
            return {
                "source_field": source_field,
                "source_value": source_value,
                "destination_fields": destination_fields,
                "transformation_logic": "link_down -> assignment_group=Transport NOC",
                "confidence_score": 0.86,
                "reasoning": "Evidence supports Transport NOC.",
                "evidence_citations": ["TKT-1001"],
                "governance_status": "Pending Approval",
                "validation_flags": [],
            }

    mapping = {
        "source_field": "probableCause",
        "source_value": "link_down",
        "destination_fields": ["assignment_group"],
        "confidence_score": 0.86,
        "governance_status": "Pending Approval",
    }

    entry = local_runs.run_local_comparison(
        tmp_path,
        DATA_DIR,
        "Assurance",
        mapping,
        engine=FakeEngine(),
    )

    assert entry["model"] == "env-model"


def test_normalize_strips_pasted_generate_endpoint_down_to_base_url():
    assert (
        normalize_local_base_url("https://9fs2yfo9dv05wz-11434.proxy.runpod.net/api/generate")
        == "https://9fs2yfo9dv05wz-11434.proxy.runpod.net"
    )


def test_normalize_strips_other_known_ollama_api_verbs():
    assert normalize_local_base_url("http://localhost:11434/api/chat") == "http://localhost:11434"
    assert normalize_local_base_url("http://localhost:11434/api/tags") == "http://localhost:11434"
    assert normalize_local_base_url("http://localhost:11434/api/tags/") == "http://localhost:11434"


def test_normalize_strips_bare_trailing_api_segment():
    assert normalize_local_base_url("http://localhost:11434/api") == "http://localhost:11434"


def test_normalize_leaves_a_clean_base_url_untouched():
    assert normalize_local_base_url("http://localhost:11434") == "http://localhost:11434"


def test_normalize_does_not_mistake_an_api_subdomain_for_the_suffix():
    assert normalize_local_base_url("https://api.example.com") == "https://api.example.com"


def test_set_local_config_normalizes_a_pasted_generate_endpoint(monkeypatch):
    set_local_config("https://9fs2yfo9dv05wz-11434.proxy.runpod.net/api/generate")

    assert get_local_base_url() == "https://9fs2yfo9dv05wz-11434.proxy.runpod.net"


def test_list_local_models_succeeds_against_a_pasted_generate_endpoint():
    calls = []

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"models": [{"name": "llama3.1"}]}'

    def fake_urlopen(url, timeout):
        calls.append(url)
        return FakeResponse()

    reachable, error, models = list_local_models(
        "https://9fs2yfo9dv05wz-11434.proxy.runpod.net/api/generate",
        timeout=0.25,
        opener=fake_urlopen,
    )

    assert reachable is True
    assert error is None
    assert models == ["llama3.1"]
    assert calls == ["https://9fs2yfo9dv05wz-11434.proxy.runpod.net/api/tags"]
