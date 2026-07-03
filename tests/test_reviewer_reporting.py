import json
from pathlib import Path

import yaml

import pytest

from governance.approval_model import assign_mapping, is_decision_locked, load_proposals, record_decision, unassign_mapping
from governance.reporting import decorate_events_with_reason_flags, reviewer_activity_report, split_audit_events_at_latest_reset
from governance.versioning import add_approved_version


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def write_proposals(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "proposed_mapping.yaml").write_text(
        yaml.safe_dump({
            "mappings": [
                {
                    "source_field": "probableCause",
                    "source_value": "link_down",
                    "destination_fields": ["assignment_group"],
                    "governance_status": "Pending Approval",
                }
            ]
        }),
        encoding="utf-8",
    )


def write_audit(output_dir: Path, events: list[dict]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "audit_log.jsonl").write_text(
        "\n".join(json.dumps(event) for event in events) + "\n",
        encoding="utf-8",
    )


def test_assignment_sets_lock_status_and_persists_assignee(tmp_path):
    write_proposals(tmp_path)

    assign_mapping(tmp_path, 0, "TM-01", "tester", "route it")

    mapping = load_proposals(tmp_path)[0]
    event = json.loads((tmp_path / "audit_log.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert mapping["governance_status"] == "Assigned / Awaiting Decision"
    assert mapping["assigned_to"] == "TM-01"
    assert is_decision_locked(mapping) is True
    assert event["action"] == "assigned"
    assert event["assigned_to"] == "TM-01"


def test_assignment_unassignment_and_decision_are_distinct_audit_events(tmp_path):
    write_proposals(tmp_path)

    assign_mapping(tmp_path, 0, "TM-01", "sam", "please review")
    unassign_mapping(tmp_path, 0, "sam", "review complete")
    record_decision(tmp_path, 0, "Approved", "jordan", "approved after review")

    events = [
        json.loads(line)
        for line in (tmp_path / "audit_log.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [event["action"] for event in events] == ["assigned", "unassigned", "Approved"]
    assert events[0]["assigned_to"] == "TM-01"
    assert events[1]["assigned_to"] == "TM-01"
    assert "assigned_to" not in events[2]


def test_decision_is_blocked_while_assigned(tmp_path):
    write_proposals(tmp_path)
    assign_mapping(tmp_path, 0, "TM-01", "tester", "route it")

    with pytest.raises(ValueError):
        record_decision(tmp_path, 0, "Approved", "tester", "should be blocked")


def test_assigned_mapping_excluded_from_version_cut(tmp_path):
    write_proposals(tmp_path)
    assign_mapping(tmp_path, 0, "TM-01", "tester", "route it")

    approved = [
        mapping for mapping in load_proposals(tmp_path)
        if mapping["governance_status"] == "Approved"
    ]
    version = add_approved_version(tmp_path, approved, "tester", "cut preview test")

    assert version["mappings"] == []


def test_reviewer_report_counts_actions(tmp_path):
    write_audit(tmp_path, [
        {"timestamp": "2026-01-01T00:00:00Z", "mapping": "A", "action": "assigned", "assigned_to": "TM-01"},
        {"timestamp": "2026-01-01T00:01:00Z", "mapping": "A", "action": "Approved", "assigned_to": "TM-01"},
        {"timestamp": "2026-01-01T00:02:00Z", "mapping": "B", "action": "Rejected", "assigned_to": "TM-01"},
        {"timestamp": "2026-01-01T00:03:00Z", "mapping": "C", "action": "Needs Clarification", "assigned_to": "TM-02"},
    ])

    report = {row["id"]: row for row in reviewer_activity_report(tmp_path, DATA_DIR)}

    assert report["TM-01"]["Assigned"] == 1
    assert report["TM-01"]["Approved"] == 1
    assert report["TM-01"]["Rejected"] == 1
    assert report["TM-01"]["total_actions"] == 3
    assert report["TM-02"]["Needs Clarification"] == 1
    assert report["TM-02"]["total_actions"] == 1


def test_audit_events_before_latest_reset_are_historical():
    events = [
        {"timestamp": "2026-01-01T00:00:00Z", "action": "Approved", "mapping": "A"},
        {"timestamp": "2026-01-01T00:01:00Z", "action": "demo_reset", "mapping": "demo_state"},
        {"timestamp": "2026-01-01T00:02:00Z", "action": "Rejected", "mapping": "B"},
    ]

    split = split_audit_events_at_latest_reset(events)

    assert [event["action"] for event in split["current"]] == ["Rejected", "demo_reset"]
    assert [event["action"] for event in split["historical"]] == ["Approved"]


def test_decorate_events_with_reason_flags_marks_matching_decision():
    events = [
        {
            "timestamp": "2026-01-01T00:00:00Z",
            "domain": "Assurance",
            "mapping": "probableCause=link_down",
            "action": "Approved",
            "user": "tester",
            "reason": "the grass is blue today",
        },
        {
            "timestamp": "2026-01-01T00:01:00Z",
            "domain": "Assurance",
            "mapping": "probableCause=link_down",
            "action": "reason_flagged_for_review",
            "decision_action": "Approved",
            "user": "tester",
            "reason": "the grass is blue today",
            "flag_note": "Reason appears unrelated.",
        },
    ]

    decorated = decorate_events_with_reason_flags(events)

    assert len(decorated) == 1
    assert decorated[0]["reason_flagged_for_review"] is True
    assert decorated[0]["flag_note"] == "Reason appears unrelated."


def test_reviewer_report_counts_only_current_events_after_reset(tmp_path):
    write_audit(tmp_path, [
        {"timestamp": "2026-01-01T00:00:00Z", "mapping": "A", "action": "assigned", "assigned_to": "TM-01"},
        {"timestamp": "2026-01-01T00:01:00Z", "mapping": "A", "action": "Approved", "assigned_to": "TM-01"},
        {"timestamp": "2026-01-01T00:02:00Z", "mapping": "demo_state", "action": "demo_reset"},
        {"timestamp": "2026-01-01T00:03:00Z", "mapping": "B", "action": "Rejected", "assigned_to": "TM-02"},
    ])

    report = {row["id"]: row for row in reviewer_activity_report(tmp_path, DATA_DIR)}

    assert report["TM-01"]["Assigned"] == 0
    assert report["TM-01"]["Approved"] == 0
    assert report["TM-01"]["total_actions"] == 0
    assert report["TM-02"]["Rejected"] == 1
    assert report["TM-02"]["total_actions"] == 1


def test_reviewer_report_includes_current_unassigned_pre_decision_count(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "proposed_mapping.yaml").write_text(
        yaml.safe_dump({
            "mappings": [
                {"source_field": "a", "destination_fields": ["x"], "governance_status": "Pending Approval"},
                {"source_field": "b", "destination_fields": ["y"], "governance_status": "Needs Clarification"},
                {"source_field": "c", "destination_fields": ["z"], "governance_status": "Approved"},
                {
                    "source_field": "d",
                    "destination_fields": ["w"],
                    "governance_status": "Assigned / Awaiting Decision",
                    "assigned_to": "TM-01",
                },
            ]
        }),
        encoding="utf-8",
    )

    report = {row["id"]: row for row in reviewer_activity_report(tmp_path, DATA_DIR, ["proposed_mapping.yaml"])}

    assert report["UNASSIGNED"]["Assigned"] == 2
    assert report["UNASSIGNED"]["is_unassigned"] is True


def test_revision_rate_detects_reversed_and_stable_approvals(tmp_path):
    write_audit(tmp_path, [
        {"timestamp": "2026-01-01T00:00:00Z", "mapping": "stable", "action": "Approved", "assigned_to": "TM-01"},
        {"timestamp": "2026-01-01T00:01:00Z", "mapping": "revised", "action": "Approved", "assigned_to": "TM-02"},
        {"timestamp": "2026-01-01T00:02:00Z", "mapping": "revised", "action": "Needs Clarification", "assigned_to": "TM-04"},
    ])

    report = {row["id"]: row for row in reviewer_activity_report(tmp_path, DATA_DIR)}

    assert report["TM-01"]["revision_rate"] == 0.0
    assert report["TM-02"]["revision_rate"] == 100.0
