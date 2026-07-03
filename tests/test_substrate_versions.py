import json
from pathlib import Path

import pytest
import yaml

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from governance.substrate_versions import (
    active_versions,
    cut_candidates,
    cut_substrate_version,
    load_substrate_versions,
    rollback_to_version,
)


def write_proposals(output_dir: Path, statuses: list[str], filename: str = "proposed_mapping.yaml") -> None:
    mappings = [
        {
            "source_field": "perceivedSeverity" if index % 2 == 0 else "probableCause",
            "source_value": f"value-{index}",
            "destination_fields": ["impact", "urgency"],
            "transformation_logic": "critical -> impact=1-High, urgency=1-High",
            "confidence_score": 0.8,
            "governance_status": status,
        }
        for index, status in enumerate(statuses)
    ]
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / filename).write_text(yaml.safe_dump({"mappings": mappings}, sort_keys=False), encoding="utf-8")


def read_audit_events(output_dir: Path) -> list[dict]:
    path = output_dir / "audit_log.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_cut_includes_only_approved_mappings(tmp_path):
    write_proposals(
        tmp_path,
        ["Approved", "Pending Approval", "Approved", "Insufficient Evidence - Human Required", "Assigned / Awaiting Decision"],
    )

    preview = cut_candidates(tmp_path, "proposed_mapping.yaml", "Assurance")
    assert len(preview["included"]) == 2
    assert len(preview["excluded"]) == 3
    assert "Assigned / Awaiting Decision" in [item["status"] for item in preview["excluded"]]

    record = cut_substrate_version(tmp_path, "assurance", "Assurance", "proposed_mapping.yaml", "local-reviewer")
    assert record["version_id"] == "assurance-v1"
    assert len(record["mapping_ids"]) == 2
    assert all(mapping["confidence_at_cut"] == 0.8 for mapping in record["mappings"])
    assert "2 approved mappings" in record["summary"]

    stored = load_substrate_versions(tmp_path, "assurance")
    assert [version["version_id"] for version in stored] == ["assurance-v1"]


def test_version_ids_increment_per_domain(tmp_path):
    write_proposals(tmp_path, ["Approved"])
    write_proposals(tmp_path, ["Approved"], "proposed_mapping_order_management.yaml")

    first = cut_substrate_version(tmp_path, "assurance", "Assurance", "proposed_mapping.yaml", "local-reviewer")
    second = cut_substrate_version(tmp_path, "assurance", "Assurance", "proposed_mapping.yaml", "local-reviewer")
    other_domain = cut_substrate_version(
        tmp_path, "order_management", "Order Management & Fulfillment", "proposed_mapping_order_management.yaml", "local-reviewer"
    )

    assert first["version_id"] == "assurance-v1"
    assert second["version_id"] == "assurance-v2"
    assert other_domain["version_id"] == "order_management-v1"
    assert active_versions(tmp_path) == {"assurance": "assurance-v2", "order_management": "order_management-v1"}


def test_cut_writes_audit_entry(tmp_path):
    write_proposals(tmp_path, ["Approved"])
    record = cut_substrate_version(tmp_path, "assurance", "Assurance", "proposed_mapping.yaml", "local-reviewer")

    events = [event for event in read_audit_events(tmp_path) if event["action"] == "substrate_version_cut"]
    assert len(events) == 1
    assert events[0]["version_id"] == record["version_id"]
    assert events[0]["mapping_ids"] == record["mapping_ids"]
    assert events[0]["domain"] == "Assurance"


def test_cut_with_no_approved_mappings_is_rejected(tmp_path):
    write_proposals(tmp_path, ["Pending Approval", "Rejected"])
    with pytest.raises(ValueError):
        cut_substrate_version(tmp_path, "assurance", "Assurance", "proposed_mapping.yaml", "local-reviewer")
    assert load_substrate_versions(tmp_path) == []


def test_rollback_repoints_active_version_and_logs(tmp_path):
    write_proposals(tmp_path, ["Approved"])
    cut_substrate_version(tmp_path, "assurance", "Assurance", "proposed_mapping.yaml", "local-reviewer")
    cut_substrate_version(tmp_path, "assurance", "Assurance", "proposed_mapping.yaml", "local-reviewer")
    assert active_versions(tmp_path)["assurance"] == "assurance-v2"

    rollback_to_version(tmp_path, "assurance", "Assurance", "assurance-v1", "local-reviewer")
    assert active_versions(tmp_path)["assurance"] == "assurance-v1"

    events = [event for event in read_audit_events(tmp_path) if event["action"] == "substrate_rollback"]
    assert len(events) == 1
    assert events[0]["previous_active_version"] == "assurance-v2"
    assert events[0]["rolled_back_to"] == "assurance-v1"


def test_rollback_to_unknown_or_active_version_is_rejected(tmp_path):
    write_proposals(tmp_path, ["Approved"])
    cut_substrate_version(tmp_path, "assurance", "Assurance", "proposed_mapping.yaml", "local-reviewer")

    with pytest.raises(ValueError):
        rollback_to_version(tmp_path, "assurance", "Assurance", "assurance-v9", "local-reviewer")
    with pytest.raises(ValueError):
        rollback_to_version(tmp_path, "assurance", "Assurance", "assurance-v1", "local-reviewer")


def test_active_pointer_tolerates_demo_reset_shape(tmp_path):
    (tmp_path / "active_substrate_version.yaml").write_text(
        yaml.safe_dump({"active_version": None}, sort_keys=False), encoding="utf-8"
    )
    assert active_versions(tmp_path) == {}
