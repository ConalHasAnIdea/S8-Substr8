"""
Regression tests for citation validation, including the substring-containment
bypass the original per-engine check was vulnerable to.
"""

from discovery.citation_validation import (
    build_id_extractor,
    validate_citation,
    validate_citations,
)

VALID_IDS = {
    "TKT-1011",
    "TKT-1024",
    "Operator Note 3",
    "Operator Note OM1",
    "Legacy Rule 3",
    "Legacy OM Rule 2",
}


def test_bare_real_id_is_accepted():
    verdict = validate_citation("TKT-1011", VALID_IDS)
    assert verdict.valid
    assert verdict.matched_ids == ["TKT-1011"]


def test_annotated_real_id_is_accepted():
    # The original false-positive case the old loose check existed to solve.
    # Models annotate real IDs with descriptive text; that must stay valid.
    verdict = validate_citation("TKT-1011 (mapping_correct=true, later_correction=false)", VALID_IDS)
    assert verdict.valid
    assert verdict.matched_ids == ["TKT-1011"]


def test_smuggled_fabricated_id_is_rejected_and_named():
    # THE bypass: a fabricated ID riding alongside a real one passed the old
    # substring check. It must fail now, and the verdict must say why.
    verdict = validate_citation("TKT-9999 (see TKT-1011)", VALID_IDS)
    assert not verdict.valid
    assert "TKT-9999" in verdict.unknown_ids
    assert verdict.matched_ids == ["TKT-1011"]
    assert "TKT-9999" in verdict.reason


def test_citation_with_no_id_shaped_token_is_rejected():
    verdict = validate_citation("as discussed with the operations team", VALID_IDS)
    assert not verdict.valid
    assert verdict.unknown_ids == []


def test_unknown_id_from_a_known_family_is_rejected():
    verdict = validate_citation("Legacy Rule 99", VALID_IDS)
    assert not verdict.valid
    assert verdict.unknown_ids == ["Legacy Rule 99"]


def test_om_and_plain_note_families_do_not_cross_match():
    # "Operator Note 3" and "Operator Note OM1" are distinct families;
    # generalisation must not let one validate the other's fabrications.
    assert validate_citation("Operator Note OM1", VALID_IDS).valid
    assert validate_citation("Operator Note 3", VALID_IDS).valid
    assert not validate_citation("Operator Note OM7", VALID_IDS).valid


def test_partial_numeric_match_is_not_accepted():
    # TKT-101 is not valid and must not match inside or as a prefix of
    # TKT-1011. Boundary handling, basically.
    verdict = validate_citation("TKT-101", VALID_IDS)
    assert not verdict.valid


def test_multiple_valid_ids_in_one_citation_all_normalize():
    verdict = validate_citation("TKT-1011 and TKT-1024 both support this", VALID_IDS)
    assert verdict.valid
    assert verdict.matched_ids == ["TKT-1011", "TKT-1024"]


def test_empty_valid_ids_rejects_everything():
    # No evidence shown means nothing legitimate to cite. An extractor can't
    # even be built.
    assert build_id_extractor(set()) is None
    verdict = validate_citation("TKT-1011", set())
    assert not verdict.valid


def test_batch_validation_splits_and_normalizes():
    result = validate_citations(
        [
            "TKT-1011 (supporting)",
            "TKT-9999 (see TKT-1011)",
            "Operator Note 3",
            "totally made up prose citation",
        ],
        VALID_IDS,
    )
    assert result["normalized"] == ["Operator Note 3", "TKT-1011"]
    assert result["fabricated"] == sorted(
        ["TKT-9999 (see TKT-1011)", "totally made up prose citation"]
    )
    rejected = [d for d in result["details"] if not d.valid]
    assert any("TKT-9999" in d.unknown_ids for d in rejected)
