from pathlib import Path
from typing import Any, Protocol

from discovery.api_keys import get_local_base_url, get_local_model, list_local_models, local_config_source
from .run_log import append_run_log, build_run_record, last_demo_reset_timestamp, load_run_log, mapping_run_key


RUN_LOG = "local_engine_runs.jsonl"
ENGINE_ID = "local"
LOCAL_ENGINE_LABEL = "Local (self hosted)"


class LocalEngineLike(Protocol):
    def propose_one(
        self,
        data_dir: Path,
        source_field: str,
        source_value: str | None,
        destination_fields: list[str],
    ) -> dict[str, Any]:
        ...


def local_llm_configured() -> bool:
    return bool(get_local_base_url())


def local_model_label(model: str | None = None) -> str:
    return model or get_local_model()


def local_llm_status(timeout: float = 1.5) -> dict[str, Any]:
    """Endpoint reachability plus the live model list. Which model to actually
    use for a given run is a discovery-screen, per-run choice (see
    run_local_comparison's model parameter) - this status is about whether the
    endpoint itself is reachable, not any one model."""
    base_url = get_local_base_url()
    source = local_config_source()
    if not base_url:
        return {
            "configured": False,
            "reachable": False,
            "label": "Not configured",
            "message": "Set LOCAL_LLM_BASE_URL to enable the local engine.",
            "base_url": "",
            "models": [],
            "source": None,
        }

    reachable, error, models = list_local_models(base_url, timeout=timeout)
    return {
        "configured": True,
        "reachable": reachable,
        "label": "Connected" if reachable else "Not reachable",
        "message": f"Reached {base_url}/api/tags." if reachable else error,
        "base_url": base_url,
        "models": models,
        "source": source,
    }


def sanitize_error(error: Exception | str) -> str:
    message = str(error) or error.__class__.__name__ if isinstance(error, Exception) else str(error)
    base_url = get_local_base_url()
    if base_url:
        message = message.replace(base_url, "[redacted-local-endpoint]")
    if "LOCAL_LLM_BASE_URL" in message:
        return message
    return message


def normalize_local_run(entry: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(entry)
    normalized.setdefault("engine", ENGINE_ID)
    normalized.setdefault("model", local_model_label(normalized.get("model")))
    normalized.setdefault("model_label", normalized["model"])
    normalized.setdefault("engine_confidence_score", normalized.get("confidence_score"))
    normalized.setdefault("engine_governance_status", normalized.get("governance_status"))
    normalized.setdefault("engine_citations", normalized.get("citations", []))
    normalized.setdefault("engine_reasoning", normalized.get("reasoning", ""))
    return normalized


def load_local_runs(output_dir: Path) -> list[dict[str, Any]]:
    path = output_dir / RUN_LOG
    if not path.exists():
        return []
    return [
        normalize_local_run(run)
        for run in load_run_log(output_dir, RUN_LOG)
    ]


def append_local_run(output_dir: Path, entry: dict[str, Any]) -> dict[str, Any]:
    return normalize_local_run(append_run_log(output_dir, RUN_LOG, entry))


def runs_for_mapping(output_dir: Path, domain: str, mapping: dict[str, Any]) -> list[dict[str, Any]]:
    key = mapping_run_key(domain, mapping)
    return [
        run for run in reversed(load_local_runs(output_dir))
        if run.get("mapping_key") == key
    ]


def split_local_runs_for_mapping(output_dir: Path, domain: str, mapping: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    reset_timestamp = last_demo_reset_timestamp(output_dir)
    current = []
    historical = []
    for run in runs_for_mapping(output_dir, domain, mapping):
        if reset_timestamp and run.get("timestamp", "") <= reset_timestamp:
            historical.append(run)
        else:
            current.append(run)
    return {"current": current, "historical": historical}


def run_local_comparison(
    output_dir: Path,
    data_dir: Path,
    domain: str,
    mapping: dict[str, Any],
    engine: LocalEngineLike | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """model is a per-run parameter (picked from the live /api/tags dropdown
    on the discovery screen), same as choosing which mapping to run against.
    It is never required to come from settings or the environment - those are
    only the fallback when no explicit model is passed for this call."""
    model = local_model_label(model)
    proposal: dict[str, Any] | None = None
    run_succeeded = False
    error = None

    try:
        if engine is None:
            from discovery.local_discovery_engine import LocalDiscoveryEngine

            engine = LocalDiscoveryEngine(model=model)
        result = engine.propose_one(
            data_dir,
            mapping["source_field"],
            mapping.get("source_value"),
            mapping.get("destination_fields", []),
        )
        proposal = dict(result)
        proposal["reasoning"] = sanitize_error(proposal.get("reasoning", ""))
        flags = result.get("validation_flags", [])
        run_succeeded = True
        fatal_flags = {"local_call_failed", "malformed_json_response"}
        if any(flag in fatal_flags or "malformed" in flag for flag in flags):
            run_succeeded = False
            error = proposal.get("reasoning") or "; ".join(flags)
    except Exception as exc:
        error = sanitize_error(exc)

    entry = build_run_record(
        engine=ENGINE_ID,
        model=model,
        model_label=model,
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
    return append_local_run(output_dir, entry)
