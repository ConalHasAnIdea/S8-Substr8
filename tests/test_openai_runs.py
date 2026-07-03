import json
from pathlib import Path

from governance.openai_runs import DEFAULT_OPENAI_MODEL, load_openai_runs, run_openai_comparison


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


class SuccessfulOpenAI:
    def __init__(self, confidence: float = 0.92, reasoning: str = "GPT-5.5 found the same historical support."):
        self.confidence = confidence
        self.reasoning = reasoning

    def propose_one(self, data_dir, source_field, source_value, destination_fields):
        return {
            "source_field": source_field,
            "source_value": source_value,
            "destination_fields": destination_fields,
            "transformation_logic": "link_down -> assignment_group=Network Operations",
            "confidence_score": self.confidence,
            "reasoning": self.reasoning,
            "evidence_citations": ["TKT-1001"],
            "governance_status": "Pending Approval",
            "validation_flags": [],
        }


class MalformedOpenAI:
    def propose_one(self, data_dir, source_field, source_value, destination_fields):
        return {
            "source_field": source_field,
            "source_value": source_value,
            "destination_fields": destination_fields,
            "transformation_logic": None,
            "confidence_score": None,
            "reasoning": "ENGINE ERROR: model response was not valid JSON",
            "evidence_citations": [],
            "governance_status": "Needs Clarification",
            "validation_flags": ["malformed_json_response"],
        }


class FailingOpenAI:
    def __init__(self, message: str):
        self.message = message

    def propose_one(self, data_dir, source_field, source_value, destination_fields):
        raise RuntimeError(self.message)


def mapping() -> dict:
    return {
        "source_field": "probableCause",
        "source_value": "link_down",
        "destination_fields": ["assignment_group"],
        "confidence_score": 0.86,
        "governance_status": "Pending Approval",
    }


def test_successful_openai_run_persists_without_modifying_mapping_status(tmp_path):
    source_mapping = mapping()

    entry = run_openai_comparison(tmp_path, DATA_DIR, "Assurance", source_mapping, SuccessfulOpenAI())

    assert source_mapping["governance_status"] == "Pending Approval"
    assert entry["engine"] == "openai"
    assert entry["model"] == DEFAULT_OPENAI_MODEL
    assert entry["model_label"] == "ChatGPT-5.5"
    assert entry["run_succeeded"] is True
    assert entry["mock_confidence_score"] == 0.86
    assert entry["mock_governance_status"] == "Pending Approval"
    assert entry["engine_confidence_score"] == 0.92
    assert entry["engine_governance_status"] == "Pending Approval"
    assert entry["engine_citations"] == ["TKT-1001"]
    assert load_openai_runs(tmp_path) == [entry]


def test_malformed_openai_response_is_persisted_as_failed_run(tmp_path):
    entry = run_openai_comparison(tmp_path, DATA_DIR, "Assurance", mapping(), MalformedOpenAI())

    assert entry["run_succeeded"] is False
    assert entry["error"] == "malformed_json_response"
    assert load_openai_runs(tmp_path)[0]["error"]


def test_repeated_openai_runs_append_instead_of_overwriting(tmp_path):
    run_openai_comparison(tmp_path, DATA_DIR, "Assurance", mapping(), SuccessfulOpenAI(0.91))
    run_openai_comparison(tmp_path, DATA_DIR, "Assurance", mapping(), SuccessfulOpenAI(0.94))

    runs = load_openai_runs(tmp_path)

    assert len(runs) == 2
    assert [run["engine_confidence_score"] for run in runs] == [0.91, 0.94]


def test_selected_openai_model_is_persisted(tmp_path):
    entry = run_openai_comparison(
        tmp_path,
        DATA_DIR,
        "Assurance",
        mapping(),
        SuccessfulOpenAI(),
        model="gpt-5.4",
    )

    assert entry["engine"] == "openai"
    assert entry["model"] == "gpt-5.4"
    assert entry["model_label"] == "ChatGPT-5.4"
    assert load_openai_runs(tmp_path)[0]["model_label"] == "ChatGPT-5.4"


def test_invalid_openai_model_falls_back_to_default(tmp_path):
    entry = run_openai_comparison(
        tmp_path,
        DATA_DIR,
        "Assurance",
        mapping(),
        SuccessfulOpenAI(),
        model="gpt-unlisted-model",
    )

    assert entry["model"] == DEFAULT_OPENAI_MODEL
    assert entry["model_label"] == "ChatGPT-5.5"


def test_openai_run_data_never_includes_raw_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-secret-value")

    entry = run_openai_comparison(
        tmp_path,
        DATA_DIR,
        "Assurance",
        mapping(),
        FailingOpenAI("authentication failed for sk-openai-secret-value"),
    )

    serialized_entry = json.dumps(entry)
    serialized_log = (tmp_path / "openai_engine_runs.jsonl").read_text(encoding="utf-8")
    assert "sk-openai-secret-value" not in serialized_entry
    assert "sk-openai-secret-value" not in serialized_log
    assert entry["error"] == "authentication failed - check OPENAI_API_KEY"


def test_successful_openai_reasoning_is_redacted_without_being_reclassified_as_auth_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-secret-value")

    entry = run_openai_comparison(
        tmp_path,
        DATA_DIR,
        "Assurance",
        mapping(),
        SuccessfulOpenAI(reasoning="This mapping is valid; do not expose sk-openai-secret-value in reasoning."),
    )

    assert entry["run_succeeded"] is True
    assert entry["engine_reasoning"] == "This mapping is valid; do not expose [redacted] in reasoning."
    assert entry["error"] is None
