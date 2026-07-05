import json
from pathlib import Path
from time import perf_counter
from typing import Any

from discovery.citation_validation import validate_citations
from discovery.api_keys import DEFAULT_LOCAL_MODEL, get_local_base_url, get_local_model
from discovery.prompt_builder import build_prompt
from discovery.retrieval import EvidenceRetriever
from governance.reason_review import strip_json_fences
from governance.run_log import telemetry_from_response

try:
    import openai
except ImportError:
    openai = None


def local_model_name() -> str:
    return get_local_model()


def local_base_url() -> str:
    base_url = get_local_base_url()
    if not base_url:
        raise RuntimeError(
            "LOCAL_LLM_BASE_URL is not set. Set LOCAL_LLM_BASE_URL to the "
            "root URL of your Ollama-compatible local inference endpoint."
        )
    return base_url


def openai_compatible_base_url(base_url: str) -> str:
    base_url = base_url.rstrip("/")
    if base_url.endswith("/v1"):
        return base_url
    return f"{base_url}/v1"


class LocalDiscoveryEngine:
    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        client: Any | None = None,
    ):
        if client is not None:
            self.client = client
        else:
            resolved_base_url = base_url.rstrip("/") if base_url else local_base_url()
            if openai is None:
                raise RuntimeError(
                    "The 'openai' package is not installed. Run: pip install openai"
                )
            self.client = openai.OpenAI(
                base_url=openai_compatible_base_url(resolved_base_url),
                api_key="ollama",
            )
        self.model = model or local_model_name()

    def propose_one(
        self,
        data_dir: Path,
        source_field: str,
        source_value: str | None,
        destination_fields: list[str],
    ) -> dict[str, Any]:
        retriever = EvidenceRetriever(data_dir)
        prompt = build_prompt(retriever, source_field, source_value, destination_fields)
        valid_ids = evidence_ids_for(retriever, source_field, source_value)

        try:
            started = perf_counter()
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": prompt["system"]},
                    {"role": "user", "content": prompt["user"]},
                ],
            )
            telemetry = telemetry_from_response(
                response,
                latency_ms=round((perf_counter() - started) * 1000),
            )
            raw_text = (response.choices[0].message.content or "").strip()
        except Exception as exc:
            return {
                "source_field": source_field,
                "source_value": source_value,
                "destination_fields": destination_fields,
                "transformation_logic": None,
                "confidence_score": None,
                "reasoning": f"ENGINE ERROR: local model call failed: {exc}",
                "evidence_citations": [],
                "governance_status": "Needs Clarification",
                "raw_response": "",
                "validation_flags": ["local_call_failed"],
            }

        try:
            parsed = json.loads(strip_json_fences(raw_text))
        except json.JSONDecodeError as exc:
            return {
                "source_field": source_field,
                "source_value": source_value,
                "destination_fields": destination_fields,
                "transformation_logic": None,
                "confidence_score": None,
                "reasoning": f"ENGINE ERROR: model response was not valid JSON: {exc}",
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

        if parsed.get("confidence_score") is None:
            parsed["governance_status"] = "Insufficient Evidence - Human Required"
        else:
            parsed.setdefault("governance_status", "Pending Approval")

        parsed["validation_flags"] = flags
        parsed["raw_response"] = raw_text
        parsed.update(telemetry)
        return parsed


def evidence_ids_for(
    retriever: EvidenceRetriever,
    source_field: str,
    source_value: str | None,
) -> set[str]:
    record_id_field = retriever.domain_config.get("record_id_field", "ticket_id")
    if source_value:
        records = retriever.records_by_source(source_field, source_value)
        rules = retriever.legacy_rules_for(source_field, source_value)
        notes = retriever.notes_for([source_value])
    else:
        records = retriever.records
        rules = retriever.legacy_mapping.get("rules", [])
        notes = retriever.notes

    return (
        {r[record_id_field] for r in records if record_id_field in r}
        | {n["id"] for n in notes}
        | {r["id"] for r in rules}
    )
