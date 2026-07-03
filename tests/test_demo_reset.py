import json
from pathlib import Path

import yaml

from governance.approval_model import load_proposals
from governance.demo_reset import reset_demo_state
from governance.substrate_versions import active_versions, cut_substrate_version, load_substrate_versions


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def test_reset_demo_state_clears_generated_review_state_and_preserves_audit(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    domains = [
        {"output_stem": "proposed_mapping"},
        {"output_stem": "proposed_mapping_order_management"},
    ]
    original_data = (DATA_DIR / "team_roster.yaml").read_text(encoding="utf-8")

    for domain in domains:
        (output_dir / f"{domain['output_stem']}.yaml").write_text(
            yaml.safe_dump({
                "mappings": [
                    {
                        "source_field": "probableCause",
                        "destination_fields": ["assignment_group"],
                        "governance_status": "Assigned / Awaiting Decision",
                        "assigned_to": "TM-01",
                    }
                ]
            }),
            encoding="utf-8",
        )
        (output_dir / f"{domain['output_stem']}.md").write_text("generated proposal", encoding="utf-8")

    (output_dir / "approved_substrate.yaml").write_text(
        yaml.safe_dump({"versions": [{"version": 1, "mappings": [{"source_field": "probableCause"}]}]}),
        encoding="utf-8",
    )
    (output_dir / "audit_log.jsonl").write_text(
        json.dumps({"timestamp": "2026-01-01T00:00:00Z", "mapping": "A", "action": "Approved"}) + "\n",
        encoding="utf-8",
    )

    reset_demo_state(output_dir, domains, "tester", "reset from test")

    assert load_proposals(output_dir, "proposed_mapping.yaml") == []
    assert load_proposals(output_dir, "proposed_mapping_order_management.yaml") == []
    assert not (output_dir / "proposed_mapping.md").exists()
    assert yaml.safe_load((output_dir / "approved_substrate.yaml").read_text(encoding="utf-8")) == {"versions": []}
    events = [
        json.loads(line)
        for line in (output_dir / "audit_log.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [event["action"] for event in events] == ["Approved", "demo_reset"]
    assert (DATA_DIR / "team_roster.yaml").read_text(encoding="utf-8") == original_data


def test_reset_demo_state_clears_substrate_versions_and_active_pointer(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    domains = [{"output_stem": "proposed_mapping"}]
    (output_dir / "proposed_mapping.yaml").write_text(
        yaml.safe_dump({
            "mappings": [
                {
                    "source_field": "perceivedSeverity",
                    "source_value": "critical",
                    "destination_fields": ["impact", "urgency"],
                    "transformation_logic": "critical -> impact=1-High, urgency=1-High",
                    "confidence_score": 0.86,
                    "governance_status": "Approved",
                }
            ]
        }),
        encoding="utf-8",
    )
    cut_substrate_version(output_dir, "assurance", "Assurance", "proposed_mapping.yaml", "tester")
    assert load_substrate_versions(output_dir) != []
    assert active_versions(output_dir) == {"assurance": "assurance-v1"}

    reset_demo_state(output_dir, domains, "tester", "reset from test")

    assert load_proposals(output_dir, "proposed_mapping.yaml") == []
    assert load_substrate_versions(output_dir) == []
    assert active_versions(output_dir) == {}
    events = [
        json.loads(line)
        for line in (output_dir / "audit_log.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [event["action"] for event in events] == ["substrate_version_cut", "demo_reset"]
