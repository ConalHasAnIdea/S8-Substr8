import json
from pathlib import Path

import pytest
import yaml

from discovery.mock_discovery_engine import run_discovery
from governance.approval_model import record_decision
from governance.reason_review import MIN_DECISION_REASON_LENGTH


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


class RelevantChecker:
    def check(self, mapping, action, reason):
        return {"verdict": "RELEVANT", "note": "Reason relates to this mapping."}


class NotRelevantChecker:
    def check(self, mapping, action, reason):
        return {"verdict": "NOT_RELEVANT", "note": "Reason appears unrelated to this mapping."}


class FailingChecker:
    def check(self, mapping, action, reason):
        raise TimeoutError("advisory timeout")


def reviewable_index(output_dir: Path) -> int:
    proposals = yaml.safe_load((output_dir / "proposed_mapping.yaml").read_text(encoding="utf-8"))["mappings"]
    return next(
        index for index, mapping in enumerate(proposals)
        if mapping["governance_status"] != "Insufficient Evidence - Human Required"
    )


def audit_actions(output_dir: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in (output_dir / "audit_log.jsonl").read_text(encoding="utf-8").splitlines()
    ]


def test_approval_versions_and_audits(tmp_path):
    run_discovery(DATA_DIR, tmp_path)
    approval_index = reviewable_index(tmp_path)

    record_decision(tmp_path, approval_index, "Approved", "tester", "unit test approval")

    approved = yaml.safe_load((tmp_path / "approved_substrate.yaml").read_text(encoding="utf-8"))
    assert approved["versions"][0]["version"] == "1.0.0"
    assert (tmp_path / "audit_log.jsonl").read_text(encoding="utf-8").strip()


def test_insufficient_evidence_cannot_be_approved(tmp_path):
    run_discovery(DATA_DIR, tmp_path)
    proposals = yaml.safe_load((tmp_path / "proposed_mapping.yaml").read_text(encoding="utf-8"))["mappings"]
    planted_index = next(
        index for index, mapping in enumerate(proposals)
        if mapping.get("source_value") == "solar_flare_noise"
    )

    with pytest.raises(ValueError):
        record_decision(tmp_path, planted_index, "Approved", "tester", "should fail")


def test_empty_decision_reason_is_blocked_and_not_audited(tmp_path):
    run_discovery(DATA_DIR, tmp_path)

    with pytest.raises(ValueError, match="required"):
        record_decision(tmp_path, reviewable_index(tmp_path), "Rejected", "tester", "   ")

    assert not (tmp_path / "audit_log.jsonl").exists()


def test_short_decision_reason_is_blocked(tmp_path):
    run_discovery(DATA_DIR, tmp_path)

    with pytest.raises(ValueError, match=str(MIN_DECISION_REASON_LENGTH)):
        record_decision(tmp_path, reviewable_index(tmp_path), "Rejected", "tester", "short")


def test_duplicate_previous_decision_reason_for_same_user_is_blocked(tmp_path):
    run_discovery(DATA_DIR, tmp_path)
    first_index = reviewable_index(tmp_path)
    record_decision(tmp_path, first_index, "Rejected", "tester", "duplicate manual decision reason")

    with pytest.raises(ValueError, match="differ"):
        record_decision(tmp_path, first_index + 1, "Rejected", "tester", "duplicate manual decision reason")


def test_terse_substantive_reason_records_without_flag_when_relevant(tmp_path):
    run_discovery(DATA_DIR, tmp_path)

    record_decision(
        tmp_path,
        reviewable_index(tmp_path),
        "Needs Clarification",
        "tester",
        "override, I know this network, the storm signature is wrong",
        relevance_checker=RelevantChecker(),
    )

    events = audit_actions(tmp_path)
    assert [event["action"] for event in events] == ["Needs Clarification"]


def test_not_relevant_reason_is_flagged_without_modifying_original_decision(tmp_path):
    run_discovery(DATA_DIR, tmp_path)

    record_decision(
        tmp_path,
        reviewable_index(tmp_path),
        "Rejected",
        "tester",
        "the sky is blue and lunch was excellent",
        relevance_checker=NotRelevantChecker(),
    )

    events = audit_actions(tmp_path)
    assert [event["action"] for event in events] == ["Rejected", "reason_flagged_for_review"]
    assert events[0]["reason"] == "the sky is blue and lunch was excellent"
    assert "flag_note" not in events[0]
    assert events[1]["decision_action"] == "Rejected"
    assert events[1]["flag_note"] == "Reason appears unrelated to this mapping."


def test_advisory_relevance_failure_records_decision_without_flag(tmp_path):
    run_discovery(DATA_DIR, tmp_path)

    record_decision(
        tmp_path,
        reviewable_index(tmp_path),
        "Rejected",
        "tester",
        "manual override due to known local transport exception",
        relevance_checker=FailingChecker(),
    )

    assert [event["action"] for event in audit_actions(tmp_path)] == ["Rejected"]
