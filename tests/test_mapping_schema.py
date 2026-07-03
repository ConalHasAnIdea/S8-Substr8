from pathlib import Path

from discovery.mock_discovery_engine import MockDiscoveryEngine


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def test_mapping_output_never_targets_priority_directly():
    mappings = MockDiscoveryEngine().discover(DATA_DIR)

    assert mappings
    assert all("priority" not in mapping["destination_fields"] for mapping in mappings)


def test_insufficient_evidence_mapping_is_emitted():
    mappings = MockDiscoveryEngine().discover(DATA_DIR)
    planted = [
        mapping for mapping in mappings
        if mapping.get("source_value") == "solar_flare_noise"
    ][0]

    assert planted["confidence_score"] is None
    assert planted["evidence_citations"] == []
    assert planted["governance_status"] == "Insufficient Evidence - Human Required"
