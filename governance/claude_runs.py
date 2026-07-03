import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol


RUN_LOG = "claude_engine_runs.jsonl"
DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-6"
CLAUDE_MODEL_OPTIONS = [
    {"value": "claude-sonnet-4-6", "label": "Claude Sonnet 4.6"},
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


def mapping_run_key(domain: str, mapping: dict[str, Any]) -> str:
    source_value = mapping.get("source_value")
    destinations = ",".join(mapping.get("destination_fields", []))
    return f"{domain}|{mapping.get('source_field')}|{source_value or ''}|{destinations}"


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
        normalize_claude_run(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def last_demo_reset_timestamp(output_dir: Path) -> str | None:
    path = output_dir / "audit_log.jsonl"
    if not path.exists():
        return None
    reset_timestamps = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        if event.get("action") == "demo_reset":
            reset_timestamps.append(event.get("timestamp"))
    return max(reset_timestamps) if reset_timestamps else None


def append_claude_run(output_dir: Path, entry: dict[str, Any]) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / RUN_LOG).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")
    return entry


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
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "engine": "claude",
        "model": model,
        "model_label": claude_model_label(model),
        "domain": domain,
        "mapping_key": mapping_run_key(domain, mapping),
        "source_field": mapping.get("source_field"),
        "source_value": mapping.get("source_value"),
        "destination_fields": mapping.get("destination_fields", []),
        "mock_confidence_score": mapping.get("confidence_score"),
        "mock_governance_status": mapping.get("governance_status"),
        "claude_confidence_score": None,
        "claude_governance_status": None,
        "claude_citations": [],
        "claude_reasoning": "",
        "validation_flags": [],
        "run_succeeded": False,
        "error": None,
    }

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
        entry.update({
            "claude_confidence_score": result.get("confidence_score"),
            "claude_governance_status": result.get("governance_status"),
            "claude_citations": result.get("evidence_citations", []),
            "claude_reasoning": result.get("reasoning", ""),
            "validation_flags": result.get("validation_flags", []),
            "run_succeeded": True,
        })
        if any("malformed" in flag for flag in result.get("validation_flags", [])):
            entry["run_succeeded"] = False
            entry["error"] = "; ".join(result["validation_flags"])
    except Exception as exc:
        entry["error"] = sanitize_error(exc)

    return append_claude_run(output_dir, entry)
