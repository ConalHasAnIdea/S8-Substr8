from collections import Counter
from typing import Any


MIN_TICKETS_FOR_SPLIT = 4
SPLIT_BAND_LOW = 0.40
SPLIT_BAND_HIGH = 0.60
TOP_TWO_COVERAGE_MIN = 0.80
SPLIT_HINT_TEXT = (
    "Evidence is split roughly evenly between two destination values. "
    "This may represent a conditional rule (e.g. different vendors or "
    "severity levels routing differently) rather than a single uncertain "
    "mapping. Human review should determine whether two separate "
    "conditional mappings are more appropriate than one low-confidence "
    "mapping."
)


def derive_confidence(supporting: int, conflicting: int) -> float | None:
    """Transparent confidence score derived only from evidence counts."""
    total = supporting + conflicting
    if total == 0:
        return None
    agreement = supporting / total
    volume_factor = min(1.0, total / 10)
    dampened = agreement * (0.50 + (0.50 * volume_factor))
    return round(dampened, 2)


def apply_note_weighting(base_confidence: float | None, weighted_notes: list[tuple[str, float]]) -> tuple[float | None, str]:
    """
    Notes nudge existing evidence confidence toward their average authority by up
    to 0.05; they never create confidence when evidence produced none.
    """
    if base_confidence is None:
        return None, "Note authority weighting skipped because confidence is None."
    if not weighted_notes:
        return base_confidence, ""
    average_weight = sum(weight for _, weight in weighted_notes) / len(weighted_notes)
    adjustment = max(-0.05, min(0.05, (average_weight - 0.5) * 0.10))
    adjusted = round(max(0.0, min(1.0, base_confidence + adjustment)), 2)
    note_ids = ", ".join(note_id for note_id, _ in weighted_notes)
    explanation = (
        f"Authority weighting from {note_ids} averaged {average_weight:.2f}, "
        f"adjusting confidence from {base_confidence:.2f} to {adjusted:.2f}."
    )
    return adjusted, explanation


def detect_split(outcome_counts: Counter, total_correct: int) -> dict[str, Any] | None:
    """
    Return an advisory hint when correct evidence is roughly split between two
    destination outcomes. Phase 2 open item: a probabilistic engine is better
    positioned to detect whether the split correlates with attributes such as
    vendor, severity, service, or network domain.
    """
    if total_correct < MIN_TICKETS_FOR_SPLIT or len(outcome_counts) < 2:
        return None

    top_two = outcome_counts.most_common(2)
    top_two_total = sum(count for _, count in top_two)
    leader_count = top_two[0][1]
    leader_pct = leader_count / total_correct
    top_two_coverage = top_two_total / total_correct

    if top_two_coverage < TOP_TWO_COVERAGE_MIN:
        return None
    if not SPLIT_BAND_LOW <= leader_pct <= SPLIT_BAND_HIGH:
        return None

    return {
        "detected": True,
        "top_outcomes": [
            {
                "value": _format_outcome_value(value),
                "count": count,
                "pct": round((count / total_correct) * 100),
            }
            for value, count in top_two
        ],
        "hint": SPLIT_HINT_TEXT,
    }


def _format_outcome_value(value: Any) -> str:
    if isinstance(value, tuple):
        if len(value) == 1:
            return str(value[0])
        return ", ".join(str(item) for item in value)
    return str(value)
