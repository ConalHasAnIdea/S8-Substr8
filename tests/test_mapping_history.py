import json

from governance.reporting import mapping_audit_context


def write_audit(output_dir, events):
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "audit_log.jsonl").write_text(
        "\n".join(json.dumps(event) for event in events) + "\n",
        encoding="utf-8",
    )


def test_mapping_history_splits_historical_logs_and_marks_flagged_reason(tmp_path):
    write_audit(tmp_path, [
        {
            "timestamp": "2026-01-01T00:00:00Z",
            "domain": "Assurance",
            "mapping": "probableCause=link_down",
            "action": "Approved",
            "user": "tester",
            "reason": "old approved reason",
        },
        {
            "timestamp": "2026-01-01T00:01:00Z",
            "domain": "All domains",
            "mapping": "demo_state",
            "action": "demo_reset",
            "user": "tester",
            "reason": "reset",
        },
        {
            "timestamp": "2026-01-01T00:02:00Z",
            "domain": "Assurance",
            "mapping": "probableCause=link_down",
            "action": "Rejected",
            "user": "tester",
            "reason": "the sky is blue and lunch was excellent",
        },
        {
            "timestamp": "2026-01-01T00:03:00Z",
            "domain": "Assurance",
            "mapping": "probableCause=link_down",
            "action": "reason_flagged_for_review",
            "decision_action": "Rejected",
            "user": "tester",
            "reason": "the sky is blue and lunch was excellent",
            "flag_note": "Reason appears unrelated.",
        },
    ])
    history = mapping_audit_context(tmp_path, "probableCause=link_down", "Assurance")

    assert [event["action"] for event in history["current"]] == ["Rejected"]
    assert history["current"][0]["reason_flagged_for_review"] is True
    assert history["current"][0]["flag_note"] == "Reason appears unrelated."
    assert [event["action"] for event in history["historical"]] == ["Approved"]
