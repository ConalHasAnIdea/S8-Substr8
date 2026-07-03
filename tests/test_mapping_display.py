from governance.mapping_display import destination_summary, source_summary


def test_source_summary_includes_value_when_present():
    assert source_summary({"source_field": "probableCause", "source_value": "link_down"}) == "probableCause=link_down"


def test_destination_summary_extracts_proposed_values_from_transformation_logic():
    mapping = {
        "destination_fields": ["impact", "urgency"],
        "transformation_logic": "critical -> impact=1-High, urgency=1-High",
    }

    assert destination_summary(mapping) == "impact=1-High, urgency=1-High"


def test_destination_summary_falls_back_to_rhs_when_no_field_assignment():
    mapping = {
        "destination_fields": ["assignment_group"],
        "transformation_logic": "unknown_failure -> no proposed assignment_group",
    }

    assert destination_summary(mapping) == "no proposed assignment_group"
