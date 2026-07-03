import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from discovery.injection_suite import (
    CONFIDENCE_TARGET,
    FAKE_CITATION,
    OUTCOME_FLIP,
    SCENARIOS,
    score_engines,
)
from discovery.mock_discovery_engine import MockDiscoveryEngine


ENGINE_NAME = "MockDiscoveryEngine"


def mock_scorecard():
    return score_engines({ENGINE_NAME: MockDiscoveryEngine()})


def test_suite_has_at_least_four_scenarios_across_required_field_kinds():
    assert len(SCENARIOS) >= 4
    covered = {scenario.target_field for scenario in SCENARIOS}
    assert "operator_commentary" in covered
    assert "operator_note_body" in covered
    assert "legacy_rule_note" in covered


def test_every_scenario_has_a_recognised_intent_signal():
    known = {FAKE_CITATION, OUTCOME_FLIP, CONFIDENCE_TARGET}
    for scenario in SCENARIOS:
        assert scenario.intent["kind"] in known
        assert scenario.intent.get("value") not in (None, "")


def test_scorecard_structure_is_well_formed():
    scorecard = mock_scorecard()

    assert set(scorecard) == {ENGINE_NAME}
    result = scorecard[ENGINE_NAME]
    assert result["total"] == len(SCENARIOS)
    assert result["held"] + result["followed"] == result["total"]
    assert len(result["scenarios"]) == len(SCENARIOS)

    scenario_names = {row["scenario"] for row in result["scenarios"]}
    assert scenario_names == {scenario.name for scenario in SCENARIOS}

    for row in result["scenarios"]:
        assert isinstance(row["followed"], bool)
        assert row["target_field"]
        assert row["intent_kind"]
        assert "intent_value" in row


def test_deterministic_engine_holds_every_scenario():
    result = mock_scorecard()[ENGINE_NAME]

    assert result["followed"] == 0
    assert result["held"] == result["total"]
    assert all(row["followed"] is False for row in result["scenarios"])
