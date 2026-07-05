import os
from pathlib import Path
from typing import Any, Protocol

from .run_log import append_run_log, build_run_record, last_demo_reset_timestamp, load_run_log, mapping_run_key


RUN_LOG = "openai_engine_runs.jsonl"
ENGINE_ID = "openai"
DEFAULT_OPENAI_MODEL = "gpt-5.5"
OPENAI_MODEL_OPTIONS = [
    {"value": "gpt-5.5", "label": "ChatGPT-5.5"},
    {"value": "gpt-5.4", "label": "ChatGPT-5.4"},
]


class OpenAIEngineLike(Protocol):
    def propose_one(
        self,
        data_dir: Path,
        source_field: str,
        source_value: str | None,
        destination_fields: list[str],
    ) -> dict[str, Any]:
        ...


def sanitize_error(error: Exception | str) -> str:
    message = redact_api_key(str(error) or error.__class__.__name__ if isinstance(error, Exception) else str(error))
    lowered = message.lower()
    if "auth" in lowered or "api key" in lowered or "bearer" in lowered:
        return "authentication failed - check OPENAI_API_KEY"
    return message


def redact_api_key(message: str) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if api_key:
        message = message.replace(api_key, "[redacted]")
    return message


def openai_model_label(model: str | None) -> str:
    model = model or DEFAULT_OPENAI_MODEL
    for option in OPENAI_MODEL_OPTIONS:
        if option["value"] == model:
            return option["label"]
    return model


def allowed_openai_model(model: str | None) -> str:
    allowed = {option["value"] for option in OPENAI_MODEL_OPTIONS}
    return model if model in allowed else DEFAULT_OPENAI_MODEL


def normalize_openai_run(entry: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(entry)
    if normalized.get("engine") == "gpt-5.5":
        normalized["engine"] = ENGINE_ID
        normalized.setdefault("model", "gpt-5.5")
    else:
        normalized.setdefault("engine", ENGINE_ID)
    normalized["model"] = allowed_openai_model(normalized.get("model"))
    normalized["model_label"] = openai_model_label(normalized["model"])
    normalized.setdefault("engine_confidence_score", normalized.get("confidence_score"))
    normalized.setdefault("engine_governance_status", normalized.get("governance_status"))
    normalized.setdefault("engine_citations", normalized.get("citations", []))
    normalized.setdefault("engine_reasoning", normalized.get("reasoning", ""))
    return normalized


def load_openai_runs(output_dir: Path) -> list[dict[str, Any]]:
    path = output_dir / RUN_LOG
    if not path.exists():
        return []
    return [
        normalize_openai_run(run)
        for run in load_run_log(output_dir, RUN_LOG)
    ]


def append_openai_run(output_dir: Path, entry: dict[str, Any]) -> dict[str, Any]:
    return normalize_openai_run(append_run_log(output_dir, RUN_LOG, entry))


def runs_for_mapping(output_dir: Path, domain: str, mapping: dict[str, Any]) -> list[dict[str, Any]]:
    key = mapping_run_key(domain, mapping)
    return [
        run for run in reversed(load_openai_runs(output_dir))
        if run.get("mapping_key") == key
    ]


def split_openai_runs_for_mapping(output_dir: Path, domain: str, mapping: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    reset_timestamp = last_demo_reset_timestamp(output_dir)
    current = []
    historical = []
    for run in runs_for_mapping(output_dir, domain, mapping):
        if reset_timestamp and run.get("timestamp", "") <= reset_timestamp:
            historical.append(run)
        else:
            current.append(run)
    return {"current": current, "historical": historical}


def run_openai_comparison(
    output_dir: Path,
    data_dir: Path,
    domain: str,
    mapping: dict[str, Any],
    engine: OpenAIEngineLike | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    model = allowed_openai_model(model)
    proposal: dict[str, Any] | None = None
    run_succeeded = False
    error = None

    try:
        if engine is None:
            from discovery.openai_discovery_engine import OpenAIDiscoveryEngine

            engine = OpenAIDiscoveryEngine(model=model)
        result = engine.propose_one(
            data_dir,
            mapping["source_field"],
            mapping.get("source_value"),
            mapping.get("destination_fields", []),
        )
        proposal = dict(result)
        proposal["reasoning"] = redact_api_key(proposal.get("reasoning", ""))
        flags = result.get("validation_flags", [])
        run_succeeded = True
        if flags:
            fatal_flags = {"openai_call_failed", "malformed_json_response"}
            if any(flag in fatal_flags or "malformed" in flag for flag in flags):
                run_succeeded = False
                if "openai_call_failed" in flags:
                    error = proposal.get("reasoning") or "OpenAI call failed."
                else:
                    error = sanitize_error("; ".join(flags))
    except Exception as exc:
        error = sanitize_error(exc)

    entry = build_run_record(
        engine=ENGINE_ID,
        model=model,
        model_label=openai_model_label(model),
        domain=domain,
        mapping=mapping,
        proposal=proposal,
        run_succeeded=run_succeeded,
        error=error,
        legacy_fields={
            "engine_confidence_score": proposal.get("confidence_score") if proposal else None,
            "engine_governance_status": proposal.get("governance_status") if proposal else None,
            "engine_citations": proposal.get("evidence_citations", []) if proposal else [],
            "engine_reasoning": proposal.get("reasoning", "") if proposal else "",
        },
    )
    return append_openai_run(output_dir, entry)
