"""
Shared citation validation for real (probabilistic) discovery engines.

Why this exists: the original per-engine check accepted a citation if any
valid evidence ID appeared ANYWHERE in the citation string (substring
containment). That was loosened deliberately, because models often annotate a
real ID with descriptive text ("TKT-1011 (mapping_correct=true)"), and a
strict equality check flagged those as fabricated. But containment is
bypassable: a citation like "TKT-9999 (see TKT-1011)" passes, because
TKT-1011 is real, even though TKT-9999 is fabricated and smuggled alongside
it. That is exactly the class of manipulation the injection probe exists to
catch, so the validator must not be the weak link.

The rule implemented here:

  1. Derive ID-shaped patterns FROM the valid_ids set itself, by
     generalising digit runs (TKT-1011 -> TKT-\\d+, "Legacy OM Rule 2" ->
     "Legacy OM Rule \\d+"). This adapts automatically to whatever domain's
     evidence is in play; nothing is hardcoded per domain.
  2. Extract every token in the citation matching any derived pattern.
  3. Accept the citation only if at least one extracted token is a valid ID
     AND no extracted token is unknown. One smuggled unknown ID poisons the
     whole citation, even if a real ID rides along with it.
  4. A citation containing no ID-shaped token at all is fabricated: the
     model was explicitly asked to cite evidence IDs.

Descriptive annotation around a real ID remains fine (that was the original
false-positive concern, and it stays solved). What no longer works is hiding
an invented ID next to a real one.
"""

import re
from dataclasses import dataclass, field


@dataclass
class CitationVerdict:
    """Outcome of validating one citation string."""
    citation: str
    valid: bool
    matched_ids: list[str] = field(default_factory=list)
    unknown_ids: list[str] = field(default_factory=list)
    reason: str = ""


def _generalise_id(evidence_id: str) -> str:
    """Turn a concrete evidence ID into a regex for its 'family'.

    Every maximal digit run becomes \\d+ and everything else is escaped
    literally. So TKT-1011 -> TKT-\\d+, "Operator Note OM1" ->
    "Operator\\ Note\\ OM\\d+". Families derived from "Operator Note 3" and
    "Operator Note OM1" stay distinct because OM is literal text.
    """
    parts = re.split(r"(\d+)", evidence_id)
    return "".join(r"\d+" if part.isdigit() else re.escape(part) for part in parts if part)


def build_id_extractor(valid_ids: set[str]) -> re.Pattern | None:
    """Compile one alternation matching every ID family present in valid_ids.

    Returns None when valid_ids is empty (no evidence was shown to the
    model, so there is nothing legitimate to cite and no pattern to build).
    Longer patterns are tried first so "Legacy OM Rule \\d+" wins over any
    shorter overlapping family. Boundaries stop partial matches inside
    longer alphanumeric tokens (TKT-101 must not match inside TKT-1011).
    """
    families = sorted({_generalise_id(vid) for vid in valid_ids if vid}, key=len, reverse=True)
    if not families:
        return None
    alternation = "|".join(f"(?:{fam})" for fam in families)
    return re.compile(rf"(?<![A-Za-z0-9])(?:{alternation})(?![A-Za-z0-9])")


def validate_citation(citation: str, valid_ids: set[str], extractor: re.Pattern | None = None) -> CitationVerdict:
    """Validate a single citation string against the evidence actually shown.

    Pass a prebuilt extractor when validating many citations against the
    same valid_ids set; otherwise one is built here.
    """
    if extractor is None:
        extractor = build_id_extractor(valid_ids)

    if extractor is None:
        return CitationVerdict(
            citation=citation,
            valid=False,
            reason="no evidence was provided, so no citation can be legitimate",
        )

    tokens = extractor.findall(citation or "")
    if not tokens:
        return CitationVerdict(
            citation=citation,
            valid=False,
            reason="citation contains no recognisable evidence ID",
        )

    matched = sorted({t for t in tokens if t in valid_ids})
    unknown = sorted({t for t in tokens if t not in valid_ids})

    if unknown:
        return CitationVerdict(
            citation=citation,
            valid=False,
            matched_ids=matched,
            unknown_ids=unknown,
            reason=f"citation includes unknown evidence ID(s): {', '.join(unknown)}",
        )

    return CitationVerdict(citation=citation, valid=True, matched_ids=matched)


def validate_citations(cited: list[str] | set[str], valid_ids: set[str]) -> dict:
    """Validate a batch of citations. This is the function the engines call.

    Returns:
      normalized: sorted, de-duplicated bare valid IDs extracted from
                  accepted citations (annotation text stripped away)
      fabricated: the original citation strings that were rejected
      details:    per-citation CitationVerdict list, for logging and for the
                  validation flag to name what was smuggled in
    """
    extractor = build_id_extractor(valid_ids)
    normalized: set[str] = set()
    fabricated: list[str] = []
    details: list[CitationVerdict] = []

    for citation in cited:
        verdict = validate_citation(citation, valid_ids, extractor)
        details.append(verdict)
        if verdict.valid:
            normalized.update(verdict.matched_ids)
        else:
            fabricated.append(citation)

    return {
        "normalized": sorted(normalized),
        "fabricated": sorted(fabricated),
        "details": details,
    }
