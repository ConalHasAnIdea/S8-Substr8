from pathlib import Path

from discovery.retrieval import EvidenceRetriever


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def test_retrieval_loads_actual_cited_records():
    retriever = EvidenceRetriever(DATA_DIR)
    lookup = retriever.evidence_by_citation()

    assert "TKT-1001" in lookup
    assert "Operator Note 2" in lookup
    assert "Legacy Rule 1" in lookup


def test_planted_insufficient_case_has_no_evidence():
    retriever = EvidenceRetriever(DATA_DIR)

    assert retriever.tickets_by("probableCause", "solar_flare_noise") == []
    assert retriever.legacy_rules_for("probableCause", "solar_flare_noise") == []
    assert retriever.notes_for(["solar_flare_noise"]) == []
