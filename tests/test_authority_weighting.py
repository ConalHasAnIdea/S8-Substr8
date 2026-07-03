from pathlib import Path

from discovery.confidence import apply_note_weighting
from discovery.mock_discovery_engine import MockDiscoveryEngine


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def test_high_authority_note_confidence_is_not_lower_than_low_authority_note():
    high_confidence, _ = apply_note_weighting(0.70, [("Operator Note 2", 1.0)])
    low_confidence, _ = apply_note_weighting(0.70, [("Operator Note 6", 0.3)])

    assert high_confidence >= low_confidence


def test_reasoning_names_team_member_and_role_for_weighted_notes():
    mappings = MockDiscoveryEngine().discover(DATA_DIR)
    severity_mapping = next(mapping for mapping in mappings if mapping["source_field"] == "perceivedSeverity")

    assert "Jordan Reyes" in severity_mapping["reasoning"]
    assert "Client Operations Lead" in severity_mapping["reasoning"]
    assert "authority 1.0" in severity_mapping["reasoning"]


def test_weighting_clamps_confidence_and_preserves_none():
    high_clamped, _ = apply_note_weighting(0.99, [("Operator Note 2", 1.0)])
    low_clamped, _ = apply_note_weighting(0.01, [("Operator Note 6", 0.0)])
    none_confidence, _ = apply_note_weighting(None, [("Operator Note 2", 1.0)])

    assert high_clamped == 1.0
    assert low_clamped == 0.0
    assert none_confidence is None
