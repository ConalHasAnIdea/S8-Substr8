import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CANONICAL_RUN_FIELDS = [
    "timestamp",
    "engine",
    "model",
    "model_label",
    "domain",
    "mapping_key",
    "mapping_identifier",
    "source_field",
    "source_value",
    "destination_fields",
    "mock_confidence_score",
    "mock_governance_status",
    "proposal",
    "confidence_score",
    "governance_status",
    "citations",
    "reasoning",
    "validation_flags",
    "run_succeeded",
    "error",
    "latency_ms",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
]


def mapping_run_key(domain: str, mapping: dict[str, Any]) -> str:
    source_value = mapping.get("source_value")
    destinations = ",".join(mapping.get("destination_fields", []))
    return f"{domain}|{mapping.get('source_field')}|{source_value or ''}|{destinations}"


def mapping_identifier(domain: str, mapping: dict[str, Any]) -> dict[str, Any]:
    return {
        "domain": domain,
        "source_field": mapping.get("source_field"),
        "source_value": mapping.get("source_value"),
        "destination_fields": mapping.get("destination_fields", []),
        "mapping_key": mapping_run_key(domain, mapping),
    }


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


def build_run_record(
    *,
    engine: str,
    model: str,
    model_label: str,
    domain: str,
    mapping: dict[str, Any],
    proposal: dict[str, Any] | None,
    run_succeeded: bool,
    error: str | None = None,
    validation_flags: list[str] | None = None,
    timestamp: str | None = None,
    latency_ms: int | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    legacy_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    proposal = proposal or {}
    citations = proposal.get("evidence_citations", [])
    flags = validation_flags if validation_flags is not None else proposal.get("validation_flags", [])
    record = {
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "engine": engine,
        "model": model,
        "model_label": model_label,
        "domain": domain,
        "mapping_key": mapping_run_key(domain, mapping),
        "mapping_identifier": mapping_identifier(domain, mapping),
        "source_field": mapping.get("source_field"),
        "source_value": mapping.get("source_value"),
        "destination_fields": mapping.get("destination_fields", []),
        "mock_confidence_score": mapping.get("confidence_score"),
        "mock_governance_status": mapping.get("governance_status"),
        "proposal": proposal or None,
        "confidence_score": proposal.get("confidence_score"),
        "governance_status": proposal.get("governance_status"),
        "citations": citations,
        "reasoning": proposal.get("reasoning", ""),
        "validation_flags": flags,
        "run_succeeded": run_succeeded,
        "error": error,
        "latency_ms": latency_ms if latency_ms is not None else proposal.get("latency_ms"),
        "prompt_tokens": prompt_tokens if prompt_tokens is not None else proposal.get("prompt_tokens"),
        "completion_tokens": completion_tokens if completion_tokens is not None else proposal.get("completion_tokens"),
        "total_tokens": total_tokens if total_tokens is not None else proposal.get("total_tokens"),
    }
    if legacy_fields:
        record.update(legacy_fields)
    return ensure_run_schema(record)


def ensure_run_schema(entry: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(entry)
    proposal = normalized.get("proposal") or {}
    normalized.setdefault("mapping_identifier", {
        "domain": normalized.get("domain"),
        "source_field": normalized.get("source_field"),
        "source_value": normalized.get("source_value"),
        "destination_fields": normalized.get("destination_fields", []),
        "mapping_key": normalized.get("mapping_key"),
    })
    normalized.setdefault("proposal", proposal or None)
    normalized.setdefault("confidence_score", proposal.get("confidence_score"))
    normalized.setdefault("governance_status", proposal.get("governance_status"))
    normalized.setdefault("citations", proposal.get("evidence_citations", []))
    normalized.setdefault("reasoning", proposal.get("reasoning", ""))
    normalized.setdefault("validation_flags", proposal.get("validation_flags", []))
    normalized.setdefault("run_succeeded", False)
    normalized.setdefault("error", None)
    normalized.setdefault("latency_ms", proposal.get("latency_ms"))
    normalized.setdefault("prompt_tokens", proposal.get("prompt_tokens"))
    normalized.setdefault("completion_tokens", proposal.get("completion_tokens"))
    normalized.setdefault("total_tokens", proposal.get("total_tokens"))
    for field in CANONICAL_RUN_FIELDS:
        normalized.setdefault(field, None)
    if normalized["destination_fields"] is None:
        normalized["destination_fields"] = []
    if normalized["validation_flags"] is None:
        normalized["validation_flags"] = []
    if normalized["citations"] is None:
        normalized["citations"] = []
    return normalized


def append_run_log(output_dir: Path, filename: str, entry: dict[str, Any]) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    normalized = ensure_run_schema(entry)
    with (output_dir / filename).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(normalized) + "\n")
    return normalized


def load_run_log(output_dir: Path, filename: str) -> list[dict[str, Any]]:
    path = output_dir / filename
    if not path.exists():
        return []
    return [
        ensure_run_schema(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def telemetry_from_response(response: Any, latency_ms: int | None = None) -> dict[str, int | None]:
    usage = getattr(response, "usage", None)
    prompt_tokens = _field(usage, "prompt_tokens")
    completion_tokens = _field(usage, "completion_tokens")
    total_tokens = _field(usage, "total_tokens")

    prompt_tokens = prompt_tokens if prompt_tokens is not None else _field(response, "prompt_eval_count")
    completion_tokens = completion_tokens if completion_tokens is not None else _field(response, "eval_count")
    total_tokens = total_tokens if total_tokens is not None else (
        prompt_tokens + completion_tokens
        if prompt_tokens is not None and completion_tokens is not None
        else None
    )

    duration_ns = _field(response, "total_duration")
    response_latency_ms = round(duration_ns / 1_000_000) if duration_ns is not None else None

    return {
        "latency_ms": latency_ms if latency_ms is not None else response_latency_ms,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


def _field(obj: Any, name: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(name)
    if hasattr(obj, name):
        return getattr(obj, name)
    if hasattr(obj, "model_dump"):
        return obj.model_dump().get(name)
    return None
