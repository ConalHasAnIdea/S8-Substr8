import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from discovery.injection_suite import (
    CONFIDENCE_TARGET,
    FAKE_CITATION,
    OUTCOME_FLIP,
    SCENARIOS,
    describe_intent,
    score_engines,
    score_engines_safe,
)
from discovery.mock_discovery_engine import MockDiscoveryEngine


ENGINE_NAME = "MockDiscoveryEngine"


def mock_scorecard():
    return score_engines({ENGINE_NAME: MockDiscoveryEngine()})


def fake_citation_scenario():
    return next(scenario for scenario in SCENARIOS if scenario.name == "commentary_fake_citation")


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


def test_fake_citation_detection_accepts_dict_citations_with_injected_id():
    scenario = fake_citation_scenario()
    baseline = {"evidence_citations": [{"id": "TKT-1011"}]}
    poisoned = {"evidence_citations": [{"id": "TKT-1011"}, {"id": "TKT-9000-INJECTED"}]}

    assert scenario.followed(baseline, poisoned) is True


def test_fake_citation_detection_keeps_existing_string_behavior():
    scenario = fake_citation_scenario()
    baseline = {"evidence_citations": ["TKT-1011"]}
    poisoned = {"evidence_citations": ["TKT-1011", "TKT-9000-INJECTED"]}

    assert scenario.followed(baseline, poisoned) is True


def test_fake_citation_detection_is_false_when_injected_id_absent():
    scenario = fake_citation_scenario()
    baseline = {"evidence_citations": [{"id": "TKT-1011"}]}
    poisoned = {"evidence_citations": [{"ticket_id": "TKT-1019"}]}

    assert scenario.followed(baseline, poisoned) is False


class RaisingEngine:
    def discover(self, data_dir):
        raise RuntimeError("simulated network failure")


def test_score_engines_safe_turns_a_raised_exception_into_an_error_row_not_a_crash():
    scorecard = score_engines_safe({"Raising": RaisingEngine()})

    result = scorecard["Raising"]
    assert result["total"] == len(SCENARIOS)
    assert result["errored"] == len(SCENARIOS)
    assert result["held"] == 0
    assert result["followed"] == 0
    for row in result["scenarios"]:
        assert row["followed"] is None
        assert "simulated network failure" in row["error"]


def test_score_engines_safe_matches_score_engines_for_a_well_behaved_engine():
    safe = score_engines_safe({ENGINE_NAME: MockDiscoveryEngine()})[ENGINE_NAME]

    assert safe["errored"] == 0
    assert safe["held"] == len(SCENARIOS)
    assert safe["followed"] == 0


def test_describe_intent_is_human_readable_for_every_known_kind():
    for scenario in SCENARIOS:
        text = describe_intent(scenario.intent["kind"], scenario.intent["value"])
        assert "Followed if" in text
        assert str(scenario.intent["value"]) in text
