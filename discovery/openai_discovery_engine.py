"""
Standalone OpenAI (GPT-5.5) discovery engine for the cross-model probe.

This is deliberately separate from the app and from claude_discovery_engine.py.
It implements the same propose_one() shape so the probe harness can compare
mock vs Claude vs GPT-5.5 on identical evidence. It carries the same
governance hardening the Claude engine earned the hard way:
  - markdown fence stripping (models wrap JSON in fences despite instructions)
  - shared citation validation (discovery.citation_validation) against real
    evidence, rejecting citations that smuggle unknown IDs alongside real ones
  - null-confidence forces the strict insufficient-evidence status
  - graceful handling of malformed / failed responses

OpenAI-specific notes baked in below:
  - GPT-5.5 is a reasoning model; it uses `max_completion_tokens`, not
    `max_tokens`, and reasoning tokens are consumed from that budget. Set it
    generously so the visible answer isn't starved by reasoning tokens.
  - The system instruction goes in a message with role "system" (or
    "developer"); we use "system" for portability.
"""

import json
from pathlib import Path
from typing import Any

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from discovery.api_keys import OPENAI, get_api_key
from discovery.citation_validation import validate_citations
from discovery.prompt_builder import build_prompt
from discovery.retrieval import EvidenceRetriever

try:
    import openai
except ImportError:
    openai = None


class OpenAIDiscoveryEngine:
    def __init__(self, model: str = "gpt-5.5", api_key: str | None = None):
        if openai is None:
            raise RuntimeError(
                "The 'openai' package is not installed. Run: pip install openai"
            )
        self.client = openai.OpenAI(api_key=api_key or get_api_key(OPENAI))
        self.model = model

    def propose_one(
        self,
        data_dir: Path,
        source_field: str,
        source_value: str | None,
        destination_fields: list[str],
    ) -> dict[str, Any]:
        retriever = EvidenceRetriever(data_dir)
        prompt = build_prompt(retriever, source_field, source_value, destination_fields)

        # Build the valid-evidence-ID set exactly as the Claude engine does,
        # so citation validation is identical across engines.
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

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                max_completion_tokens=8192,  # generous: reasoning tokens count against this
                messages=[
                    {"role": "system", "content": prompt["system"]},
                    {"role": "user", "content": prompt["user"]},
                ],
            )
            raw_text = (response.choices[0].message.content or "").strip()
        except Exception as e:  # network, auth, rate limit, etc.
            return {
                "source_field": source_field,
                "source_value": source_value,
                "destination_fields": destination_fields,
                "transformation_logic": None,
                "confidence_score": None,
                "reasoning": f"ENGINE ERROR: OpenAI call failed: {e}",
                "evidence_citations": [],
                "governance_status": "Needs Clarification",
                "raw_response": "",
                "validation_flags": ["openai_call_failed"],
            }

        # Strip markdown code fences (same defensive handling as Claude engine).
        fence_stripped = raw_text
        if fence_stripped.startswith("```"):
            lines = fence_stripped.split("\n")
            if lines[0].strip() in ("```json", "```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            fence_stripped = "\n".join(lines).strip()

        try:
            parsed = json.loads(fence_stripped)
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

        # Citation validation via the shared validator (same as Claude engine).
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

        # Null confidence forces the strict insufficient-evidence status,
        # regardless of what status string the model chose.
        if parsed.get("confidence_score") is None:
            parsed["governance_status"] = "Insufficient Evidence - Human Required"
        else:
            parsed.setdefault("governance_status", "Pending Approval")

        parsed["validation_flags"] = flags
        parsed["raw_response"] = raw_text
        return parsed
