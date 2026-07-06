import json
from pathlib import Path

from governance.audit_log import append_audit_event
from governance.claude_runs import DEFAULT_CLAUDE_MODEL, load_claude_runs, run_claude_comparison, split_runs_for_mapping


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


class SuccessfulClaude:
    def __init__(self, confidence: float = 0.93):
        self.confidence = confidence

    def propose_one(self, data_dir, source_field, source_value, destination_fields):
        return {
            "source_field": source_field,
            "source_value": source_value,
            "destination_fields": destination_fields,
            "transformation_logic": "link_down -> assignment_group=Network Operations",
            "confidence_score": self.confidence,
            "reasoning": "Claude found the same historical support.",
            "evidence_citations": ["TKT-1001"],
            "governance_status": "Pending Approval",
            "validation_flags": [],
        }


class MalformedClaude:
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


class FailingClaude:
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


def test_successful_claude_run_persists_without_modifying_mapping_status(tmp_path):
    source_mapping = mapping()

    entry = run_claude_comparison(tmp_path, DATA_DIR, "Assurance", source_mapping, SuccessfulClaude())

    assert source_mapping["governance_status"] == "Pending Approval"
    assert entry["engine"] == "claude"
    assert entry["model"] == DEFAULT_CLAUDE_MODEL
    assert entry["model_label"] == "Claude Sonnet 5"
    assert entry["run_succeeded"] is True
    assert entry["mock_confidence_score"] == 0.86
    assert entry["mock_governance_status"] == "Pending Approval"
    assert entry["claude_confidence_score"] == 0.93
    assert entry["claude_governance_status"] == "Pending Approval"
    assert entry["claude_citations"] == ["TKT-1001"]
    assert load_claude_runs(tmp_path) == [entry]


def test_malformed_claude_response_is_persisted_as_failed_run(tmp_path):
    entry = run_claude_comparison(tmp_path, DATA_DIR, "Assurance", mapping(), MalformedClaude())

    assert entry["run_succeeded"] is False
    assert entry["error"] == "malformed_json_response"
    assert load_claude_runs(tmp_path)[0]["error"]


def test_repeated_claude_runs_append_instead_of_overwriting(tmp_path):
    run_claude_comparison(tmp_path, DATA_DIR, "Assurance", mapping(), SuccessfulClaude(0.91))
    run_claude_comparison(tmp_path, DATA_DIR, "Assurance", mapping(), SuccessfulClaude(0.94))

    runs = load_claude_runs(tmp_path)

    assert len(runs) == 2
    assert [run["claude_confidence_score"] for run in runs] == [0.91, 0.94]


def test_selected_claude_model_is_persisted(tmp_path):
    entry = run_claude_comparison(
        tmp_path,
        DATA_DIR,
        "Assurance",
        mapping(),
        SuccessfulClaude(),
        model="claude-opus-4-8",
    )

    assert entry["model"] == "claude-opus-4-8"
    assert entry["model_label"] == "Claude Opus 4.8"
    assert load_claude_runs(tmp_path)[0]["model_label"] == "Claude Opus 4.8"


def test_invalid_claude_model_falls_back_to_default(tmp_path):
    entry = run_claude_comparison(
        tmp_path,
        DATA_DIR,
        "Assurance",
        mapping(),
        SuccessfulClaude(),
        model="claude-unlisted-model",
    )

    assert entry["model"] == DEFAULT_CLAUDE_MODEL
    assert entry["model_label"] == "Claude Sonnet 5"


def test_demo_reset_splits_old_claude_runs_into_historical_bucket(tmp_path):
    run_claude_comparison(tmp_path, DATA_DIR, "Assurance", mapping(), SuccessfulClaude(0.91))
    append_audit_event(tmp_path, "demo_state", "demo_reset", "tester", "reset", "All domains")
    run_claude_comparison(tmp_path, DATA_DIR, "Assurance", mapping(), SuccessfulClaude(0.94))

    runs = split_runs_for_mapping(tmp_path, "Assurance", mapping())

    assert [run["claude_confidence_score"] for run in runs["current"]] == [0.94]
    assert [run["claude_confidence_score"] for run in runs["historical"]] == [0.91]


def test_claude_run_data_never_includes_raw_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secret-value")

    entry = run_claude_comparison(
        tmp_path,
        DATA_DIR,
        "Assurance",
        mapping(),
        FailingClaude("authentication failed for sk-ant-secret-value"),
    )

    serialized_entry = json.dumps(entry)
    serialized_log = (tmp_path / "claude_engine_runs.jsonl").read_text(encoding="utf-8")
    assert "sk-ant-secret-value" not in serialized_entry
    assert "sk-ant-secret-value" not in serialized_log
    assert entry["error"] == "authentication failed - check ANTHROPIC_API_KEY"
