"""
A real, working discovery engine backed by the Claude API, implementing the
SAME interface as MockDiscoveryEngine. This is Phase 2: deliberately built to
be run against real evidence, with real model calls, specifically to observe
where and how a probabilistic engine behaves differently from the
deterministic mock, not to replace it permanently.

This engine validates the model's response against the actual evidence it was
given: any cited ticket/note/rule ID that does NOT appear in the retrieved
evidence is flagged as a fabricated citation rather than silently trusted.
That check is the single most important thing this file does.
"""

import json
from time import perf_counter
from pathlib import Path
from typing import Any

from .api_keys import ANTHROPIC, get_api_key
from .citation_validation import validate_citations
from .discovery_engine import DiscoveryEngine
from .prompt_builder import build_prompt
from .retrieval import EvidenceRetriever
from governance.reason_review import strip_json_fences
from governance.run_log import telemetry_from_response

try:
    import anthropic
except ImportError:
    anthropic = None


class FabricatedCitationError(Exception):
    """Raised when the model cites an evidence ID that was never given to it."""


class ClaudeDiscoveryEngine(DiscoveryEngine):
    def __init__(self, model: str = "claude-sonnet-5", api_key: str | None = None):
        if anthropic is None:
            raise RuntimeError(
                "The 'anthropic' package is not installed. Run: "
                "pip install anthropic"
            )
        self.client = anthropic.Anthropic(api_key=api_key or get_api_key(ANTHROPIC))
        self.model = model

    def discover(self, data_dir: Path) -> list[dict[str, Any]]:
        """Full interface compatibility with MockDiscoveryEngine is out of
        scope for this Phase 2 probe — see propose_one() for the actual
        single-case mechanism this file exists to exercise."""
        raise NotImplementedError(
            "ClaudeDiscoveryEngine.discover() is not implemented in this "
            "Phase 2 probe. Use propose_one() for a single mapping case."
        )

    def propose_one(
        self,
        data_dir: Path,
        source_field: str,
        source_value: str | None,
        destination_fields: list[str],
    ) -> dict[str, Any]:
        """Run discovery for exactly one mapping case, validate the response
        against the real evidence it was given, and return a dict in the same
        shape MockDiscoveryEngine produces."""

        retriever = EvidenceRetriever(data_dir)
        prompt = build_prompt(retriever, source_field, source_value, destination_fields)

        # Collect the set of evidence IDs actually given to the model, so we
        # can catch fabricated citations rather than trust them blindly.
        # Uses the same domain-aware lookups prompt_builder.py uses, so the
        # validation set exactly matches what the model was shown.
        record_id_field = retriever.domain_config.get("record_id_field", "ticket_id")
        if source_value:
            records = retriever.records_by_source(source_field, source_value)
            rules = retriever.legacy_rules_for(source_field, source_value)
            notes = retriever.notes_for([source_value])
        else:
            records = retriever.records
            rules = retriever.legacy_mapping.get("rules", [])
            notes = retriever.notes

        valid_ids = (
            {r[record_id_field] for r in records if record_id_field in r}
            | {n["id"] for n in notes}
            | {r["id"] for r in rules}
        )

        started = perf_counter()
        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=prompt["system"],
            messages=[{"role": "user", "content": prompt["user"]}],
        )
        telemetry = telemetry_from_response(
            response,
            latency_ms=round((perf_counter() - started) * 1000),
        )

        raw_text = "".join(
            block.text for block in response.content if block.type == "text"
        ).strip()

        # The model sometimes wraps its JSON in markdown code fences despite
        # being told not to (a real, observed instance of imperfect
        # instruction-following, not a hypothetical). Strip fences
        # defensively rather than fail on them — this is parsing leniency
        # for formatting only; it does not relax the citation-fabrication
        # validation below, which still runs against the cleaned JSON.
        try:
            parsed = json.loads(strip_json_fences(raw_text))
        except json.JSONDecodeError as e:
            return {
                "source_field": source_field,
                "source_value": source_value,
                "destination_fields": destination_fields,
                "transformation_logic": None,
                "confidence_score": None,
                "reasoning": f"ENGINE ERROR: model response was not valid JSON: {e}",
                "evidence_citations": [],
                "governance_status": "Needs Clarification",
                "raw_response": raw_text,
                "validation_flags": ["malformed_json_response"],
            }

        cited = set(parsed.get("evidence_citations", []))
        validation = validate_citations(cited, valid_ids)
        normalized_citations = validation["normalized"]
        fabricated = validation["fabricated"]

        flags = []
        if fabricated:
            smuggled = sorted({
                uid
                for verdict in validation["details"]
                for uid in verdict.unknown_ids
            })
            flags.append(
                f"fabricated_citations: {fabricated}"
                + (f" (unknown IDs: {smuggled})" if smuggled else "")
            )
            # Do not silently trust fabricated citations — strip them and
            # downgrade governance status rather than let them pass through.
            parsed["evidence_citations"] = sorted(set(normalized_citations))
            parsed["governance_status"] = "Needs Clarification"
            parsed["reasoning"] = (
                parsed.get("reasoning", "")
                + f" [VALIDATION WARNING: model cited {sorted(fabricated)} "
                "which were not present in the evidence it was given. "
                "These citations were removed and this mapping was "
                "downgraded to Needs Clarification.]"
            )
        else:
            parsed["evidence_citations"] = sorted(set(normalized_citations))

        # If confidence is null, the model itself is saying there's no
        # support for a mapping — force the correct status regardless of
        # what status string the model happened to choose. This closes a
        # real observed gap: the model correctly reasoned "no evidence
        # exists" but sometimes returns governance_status="Pending Approval"
        # anyway, which doesn't match the mock's stricter status taxonomy
        # for this exact situation. Don't trust the model's status label
        # when confidence_score is null — derive it deterministically here.
        if parsed.get("confidence_score") is None:
            parsed["governance_status"] = "Insufficient Evidence - Human Required"
        else:
            parsed.setdefault("governance_status", "Pending Approval")

        parsed["validation_flags"] = flags
        parsed["raw_response"] = raw_text
        parsed.update(telemetry)
        return parsed
