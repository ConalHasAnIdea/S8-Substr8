import os
from pathlib import Path
from typing import Any, Protocol

from .run_log import append_run_log, build_run_record, last_demo_reset_timestamp, load_run_log, mapping_run_key


RUN_LOG = "claude_engine_runs.jsonl"
DEFAULT_CLAUDE_MODEL = "claude-sonnet-5"
CLAUDE_MODEL_OPTIONS = [
    {"value": "claude-sonnet-5", "label": "Claude Sonnet 5"},
    {"value": "claude-opus-4-8", "label": "Claude Opus 4.8"},
]


class ClaudeEngineLike(Protocol):
    def propose_one(
        self,
        data_dir: Path,
        source_field: str,
        source_value: str | None,
        destination_fields: list[str],
    ) -> dict[str, Any]:
        ...


def claude_model_label(model: str | None) -> str:
    model = model or DEFAULT_CLAUDE_MODEL
    for option in CLAUDE_MODEL_OPTIONS:
        if option["value"] == model:
            return option["label"]
    return model


def allowed_claude_model(model: str | None) -> str:
    allowed = {option["value"] for option in CLAUDE_MODEL_OPTIONS}
    return model if model in allowed else DEFAULT_CLAUDE_MODEL


def normalize_claude_run(entry: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(entry)
    normalized.setdefault("engine", "claude")
    normalized["model"] = allowed_claude_model(normalized.get("model"))
    normalized["model_label"] = claude_model_label(normalized["model"])
    normalized.setdefault("claude_confidence_score", normalized.get("confidence_score"))
    normalized.setdefault("claude_governance_status", normalized.get("governance_status"))
    normalized.setdefault("claude_citations", normalized.get("citations", []))
    normalized.setdefault("claude_reasoning", normalized.get("reasoning", ""))
    return normalized


def sanitize_error(error: Exception | str) -> str:
    message = str(error) or error.__class__.__name__ if isinstance(error, Exception) else str(error)
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        message = message.replace(api_key, "[redacted]")
    lowered = message.lower()
    if "auth" in lowered or "api key" in lowered or "x-api-key" in lowered:
        return "authentication failed - check ANTHROPIC_API_KEY"
    return message


def load_claude_runs(output_dir: Path) -> list[dict[str, Any]]:
    path = output_dir / RUN_LOG
    if not path.exists():
        return []
    return [
        normalize_claude_run(run)
        for run in load_run_log(output_dir, RUN_LOG)
    ]


def append_claude_run(output_dir: Path, entry: dict[str, Any]) -> dict[str, Any]:
    return normalize_claude_run(append_run_log(output_dir, RUN_LOG, entry))


def runs_for_mapping(output_dir: Path, domain: str, mapping: dict[str, Any]) -> list[dict[str, Any]]:
    key = mapping_run_key(domain, mapping)
    return [
        run for run in reversed(load_claude_runs(output_dir))
        if run.get("mapping_key") == key
    ]


def split_runs_for_mapping(output_dir: Path, domain: str, mapping: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    reset_timestamp = last_demo_reset_timestamp(output_dir)
    current = []
    historical = []
    for run in runs_for_mapping(output_dir, domain, mapping):
        if reset_timestamp and run.get("timestamp", "") <= reset_timestamp:
            historical.append(run)
        else:
            current.append(run)
    return {"current": current, "historical": historical}


def run_claude_comparison(
    output_dir: Path,
    data_dir: Path,
    domain: str,
    mapping: dict[str, Any],
    engine: ClaudeEngineLike | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    model = allowed_claude_model(model)
    proposal: dict[str, Any] | None = None
    run_succeeded = False
    error = None

    try:
        if engine is None:
            from discovery.claude_discovery_engine import ClaudeDiscoveryEngine

            engine = ClaudeDiscoveryEngine(model=model)
        result = engine.propose_one(
            data_dir,
            mapping["source_field"],
            mapping.get("source_value"),
            mapping.get("destination_fields", []),
        )
        proposal = result
        run_succeeded = True
        if any("malformed" in flag for flag in result.get("validation_flags", [])):
            run_succeeded = False
            error = "; ".join(result["validation_flags"])
    except Exception as exc:
        error = sanitize_error(exc)

    entry = build_run_record(
        engine="claude",
        model=model,
        model_label=claude_model_label(model),
        domain=domain,
        mapping=mapping,
        proposal=proposal,
        run_succeeded=run_succeeded,
        error=error,
        legacy_fields={
            "claude_confidence_score": proposal.get("confidence_score") if proposal else None,
            "claude_governance_status": proposal.get("governance_status") if proposal else None,
            "claude_citations": proposal.get("evidence_citations", []) if proposal else [],
            "claude_reasoning": proposal.get("reasoning", "") if proposal else "",
        },
    )
    return append_claude_run(output_dir, entry)
