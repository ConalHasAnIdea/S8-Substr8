import json
from collections import Counter

import yaml

from discovery.confidence import detect_split
from discovery.evidence_model import MappingProposal
from governance.approval_model import record_decision


class RelevantChecker:
    def check(self, mapping, action, reason):
        return {"verdict": "RELEVANT", "note": "Reason relates to this mapping."}


def write_split_proposal(output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "proposed_mapping.yaml").write_text(
        yaml.safe_dump({
            "mappings": [
                {
                    "source_field": "probableCause",
                    "source_value": "optical_noise",
                    "destination_fields": ["assignment_group"],
                    "transformation_logic": "optical_noise -> assignment_group=Optical Assurance",
                    "confidence_score": 0.52,
                    "reasoning": "Split evidence fixture.",
                    "evidence_citations": ["TKT-1"],
                    "governance_status": "Needs Clarification",
                    "evidence_summary": {"supporting": 8, "conflicting": 7},
                    "split_hint": {
                        "detected": True,
                        "top_outcomes": [
                            {"value": "Optical Assurance", "count": 8, "pct": 53},
                            {"value": "Transport NOC", "count": 7, "pct": 47},
                        ],
                        "hint": "Evidence is split roughly evenly between two destination values.",
                    },
                }
            ]
        }),
        encoding="utf-8",
    )


def test_even_eight_seven_distribution_triggers_split_hint():
    hint = detect_split(Counter({"Optical Assurance": 8, "Transport NOC": 7}), 15)

    assert hint is not None
    assert hint["detected"] is True
    assert hint["top_outcomes"] == [
        {"value": "Optical Assurance", "count": 8, "pct": 53},
        {"value": "Transport NOC", "count": 7, "pct": 47},
    ]


def test_clear_fifteen_two_distribution_does_not_trigger_split_hint():
    assert detect_split(Counter({"Transport NOC": 15, "Access NOC": 2}), 17) is None


def test_low_volume_distribution_does_not_trigger_split_hint():
    assert detect_split(Counter({"Transport NOC": 2, "Access NOC": 1}), 3) is None


def test_one_winner_with_two_minorities_does_not_trigger_split_hint():
    assert detect_split(Counter({"Transport NOC": 6, "Access NOC": 1, "Optical Assurance": 1}), 8) is None


def test_split_hint_flows_through_mapping_proposal_to_dict():
    split_hint = detect_split(Counter({"Optical Assurance": 8, "Transport NOC": 7}), 15)
    proposal = MappingProposal(
        source_field="probableCause",
        source_value="optical_noise",
        destination_fields=["assignment_group"],
        transformation_logic="optical_noise -> assignment_group=Optical Assurance",
        confidence_score=0.52,
        reasoning="Split evidence fixture.",
        evidence_citations=["TKT-1"],
        governance_status="Needs Clarification",
        evidence_summary={"supporting": 8, "conflicting": 7},
        split_hint=split_hint,
    )

    assert proposal.to_dict()["split_hint"] == split_hint


def test_approving_split_hint_mapping_records_audit_metadata(tmp_path):
    write_split_proposal(tmp_path)

    record_decision(
        tmp_path,
        0,
        "Approved",
        "tester",
        "approved after reviewing the split evidence",
        relevance_checker=RelevantChecker(),
    )

    event = json.loads((tmp_path / "audit_log.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert event["action"] == "Approved"
    assert event["split_hint_present"] is True
