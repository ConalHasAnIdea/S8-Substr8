import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from .claude_runs import last_demo_reset_timestamp, mapping_run_key


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
    return normalized


def load_openai_runs(output_dir: Path) -> list[dict[str, Any]]:
    path = output_dir / RUN_LOG
    if not path.exists():
        return []
    return [
        normalize_openai_run(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def append_openai_run(output_dir: Path, entry: dict[str, Any]) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / RUN_LOG).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")
    return entry


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
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "engine": ENGINE_ID,
        "model": model,
        "model_label": openai_model_label(model),
        "domain": domain,
        "mapping_key": mapping_run_key(domain, mapping),
        "source_field": mapping.get("source_field"),
        "source_value": mapping.get("source_value"),
        "destination_fields": mapping.get("destination_fields", []),
        "mock_confidence_score": mapping.get("confidence_score"),
        "mock_governance_status": mapping.get("governance_status"),
        "engine_confidence_score": None,
        "engine_governance_status": None,
        "engine_citations": [],
        "engine_reasoning": "",
        "validation_flags": [],
        "run_succeeded": False,
        "error": None,
    }

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
        flags = result.get("validation_flags", [])
        entry.update({
            "engine_confidence_score": result.get("confidence_score"),
            "engine_governance_status": result.get("governance_status"),
            "engine_citations": result.get("evidence_citations", []),
            "engine_reasoning": redact_api_key(result.get("reasoning", "")),
            "validation_flags": flags,
            "run_succeeded": True,
        })
        if flags:
            fatal_flags = {"openai_call_failed", "malformed_json_response"}
            if any(flag in fatal_flags or "malformed" in flag for flag in flags):
                entry["run_succeeded"] = False
                if "openai_call_failed" in flags:
                    entry["error"] = entry["engine_reasoning"] or "OpenAI call failed."
                else:
                    entry["error"] = sanitize_error("; ".join(flags))
    except Exception as exc:
        entry["error"] = sanitize_error(exc)

    return append_openai_run(output_dir, entry)
