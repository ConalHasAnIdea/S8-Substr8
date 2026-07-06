from pathlib import Path
import secrets
import sys
import json
import os

from flask import Flask, redirect, render_template, request, session, url_for
import yaml

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from discovery.api_keys import ANTHROPIC, OPENAI, clear_api_key, get_api_key, key_source, set_api_key
from discovery.api_keys import clear_local_config, get_local_base_url, list_local_models, local_config_source, set_local_config
from discovery.mock_discovery_engine import run_discovery
from discovery.retrieval import EvidenceRetriever
from governance.approval_model import assign_mapping, is_decision_locked, load_proposals, mapping_label, record_decision, unassign_mapping
from governance.claude_runs import DEFAULT_CLAUDE_MODEL, run_claude_comparison, split_runs_for_mapping
from governance.demo_reset import reset_demo_state
from governance.mapping_display import destination_summary, source_summary
from governance.local_runs import LOCAL_ENGINE_LABEL, local_llm_configured, local_llm_status, run_local_comparison, split_local_runs_for_mapping
from governance.openai_runs import DEFAULT_OPENAI_MODEL, run_openai_comparison, split_openai_runs_for_mapping
from governance.reason_review import MIN_DECISION_REASON_LENGTH
from governance.reporting import decorate_events_with_reason_flags, flagged_reason_events, load_audit_events, mapping_audit_context, reviewer_activity_report, split_audit_events_at_latest_reset
from governance.substrate_versions import active_versions, cut_candidates, cut_substrate_version, load_substrate_versions, rollback_to_version
from governance.team import assignment_options, group_lookup, load_team_groups, load_team_roster, team_lookup

DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"
WIRED_SOURCE = "TMF642 Alarm Management"
WIRED_TARGET = "ServiceNow Incident"
def claude_configured() -> bool:
    """Availability is resolved per request: a key entered on the settings
    page (in-memory) or the ANTHROPIC_API_KEY environment variable."""
    return bool(get_api_key(ANTHROPIC))


def openai_configured() -> bool:
    return bool(get_api_key(OPENAI))
MOCK_ENGINE_LABEL = "Mock Discovery Engine (deterministic, evidence-derived)"
FRONTIER_ENGINE_LABEL = "FrontierLLM (per-mapping comparison)"
LOCAL_DISCOVERY_ENGINE_LABEL = f"{LOCAL_ENGINE_LABEL} (per-mapping comparison)"
DOMAINS = {
    "assurance": {
        "domain_label": "Assurance",
        "data_dir": DATA_DIR,
        "output_stem": "proposed_mapping",
        "proposal_file": "proposed_mapping.yaml",
        "route": "index",
        "mapping_route": "mapping_detail",
        "decision_route": "decision",
        "assign_route": "assign_decision",
        "unassign_route": "unassign_decision",
        "frontier_route": "run_assurance_frontier",
        "local_route": "run_assurance_local",
        "source": "TMF642 Alarm Management",
        "target": "ServiceNow Incident",
        "target_disabled": [
            "Jira Service Management - Not yet wired",
            "BMC Remedy - Not yet wired",
        ],
        "empty_text": "Select a source and target, then run discovery to generate a reviewable mapping specification from operator evidence.",
    },
    "order_management": {
        "domain_label": "Order Management & Fulfillment",
        "data_dir": DATA_DIR / "order_management",
        "output_stem": "proposed_mapping_order_management",
        "proposal_file": "proposed_mapping_order_management.yaml",
        "route": "order_management",
        "mapping_route": "order_mapping_detail",
        "decision_route": "order_decision",
        "assign_route": "order_assign_decision",
        "unassign_route": "order_unassign_decision",
        "frontier_route": "run_order_frontier",
        "local_route": "run_order_local",
        "source": "TMF622 Product Order",
        "target": "Oracle UIM (Inventory)",
        "target_disabled": ["Oracle ASAP (Provisioning) - Not yet wired"],
        "empty_text": "Select a source and target, then run discovery to generate a reviewable inventory mapping specification from operator evidence.",
    },
}

app = Flask(__name__)
# Session-signing key: from the environment if provided, otherwise random per
# process. Sessions (and the review-queue "discovery ran" flags they carry)
# reset on restart, consistent with the in-memory API key store.
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)


def status_class(status: str) -> str:
    return (
        status.lower()
        .replace(" - ", "-")
        .replace(" ", "-")
        .replace("/", "-")
    )


app.jinja_env.filters["status_class"] = status_class


GOVERNANCE_STATUS_HELP = {
    "Pending Approval": "The evidence supports this mapping and it has not yet been reviewed. A reviewer can approve, reject, or request clarification.",
    "Needs Clarification": "Confidence is below the review threshold, or the evidence includes real conflicts (contradicting tickets or legacy rules). A human should resolve the ambiguity before this can be approved.",
    "Insufficient Evidence - Human Required": "No historical evidence, operator notes, or legacy rules support this mapping at all. Rather than guess, this was routed to a human; new evidence is needed before it can be approved.",
    "Assigned / Awaiting Decision": "This mapping has been handed to a specific reviewer or group. Approve, Reject, and Needs Clarification are locked until it is unassigned.",
    "Approved": "A reviewer has approved this mapping. It is stamped with an individual version and is eligible for inclusion the next time a substrate version is cut.",
    "Rejected": "A reviewer has rejected this mapping. It will not be included in any substrate version.",
}


def status_help_text(status: str) -> str:
    return GOVERNANCE_STATUS_HELP.get(status, "")


app.jinja_env.filters["status_help_text"] = status_help_text


def ensure_proposals() -> None:
    if not (OUTPUT_DIR / "proposed_mapping.yaml").exists():
        run_discovery(DATA_DIR, OUTPUT_DIR)


def build_corpus_summary(domain: dict) -> list[dict]:
    retriever = EvidenceRetriever(domain["data_dir"])
    config = retriever.domain_config
    record_id_field = config.get("record_id_field", "ticket_id")
    fixture_label = "alarm fixtures" if config["domain_key"] == "assurance" else "order fixtures"
    record_label = "historical tickets" if config["domain_key"] == "assurance" else "historical records"

    return [
        {
            "label": record_label,
            "filename": config["historical_records"],
            "items": [
                {"id": record.get(record_id_field, "unknown"), "record": record}
                for record in reversed(retriever.records)
            ],
        },
        {
            "label": "operator notes",
            "filename": "operator_notes.md",
            "items": [
                {"id": note["id"], "record": note}
                for note in retriever.notes
            ],
        },
        {
            "label": "legacy mapping rules",
            "filename": "legacy_mapping.yaml",
            "items": [
                {"id": rule["id"], "record": rule}
                for rule in retriever.legacy_mapping.get("rules", [])
            ],
        },
        {
            "label": fixture_label,
            "filename": config["fixtures"],
            "items": [
                {"id": fixture.get("id", f"fixture-{index + 1}"), "record": fixture}
                for index, fixture in reversed(list(enumerate(retriever.fixtures)))
            ],
        },
    ]


def assignment_context() -> dict:
    return {
        "assignment_options": assignment_options(DATA_DIR),
        "team_lookup": team_lookup(DATA_DIR),
        "group_lookup": group_lookup(DATA_DIR),
    }


def assignee_label(assignee_id: str | None) -> str:
    if not assignee_id:
        return ""
    members = team_lookup(DATA_DIR)
    groups = group_lookup(DATA_DIR)
    if assignee_id in members:
        return members[assignee_id]["name"]
    if assignee_id in groups:
        return groups[assignee_id]["name"]
    return assignee_id


def selected_frontier_provider(domain_key: str) -> str:
    """Which provider is pre-selected in the merged FrontierLLM dropdown: the
    session's remembered choice if still configured, else whichever provider
    is actually configured, defaulting to Claude."""
    remembered = session.get(f"{domain_key}_frontier_provider")
    if remembered == "openai" and openai_configured():
        return "openai"
    if remembered == "claude" and claude_configured():
        return "claude"
    if claude_configured():
        return "claude"
    if openai_configured():
        return "openai"
    return "claude"


def frontier_engine_context(domain_key: str) -> dict:
    return {
        "claude_configured": claude_configured(),
        "openai_configured": openai_configured(),
        "selected_frontier_provider": selected_frontier_provider(domain_key),
    }


def frontier_runs_for_mapping(domain_label: str, mapping: dict) -> dict:
    """Claude's and OpenAI's runs merged into one chronological list, each
    entry tagged with which provider produced it, for the single merged
    FrontierLLM comparison panel."""
    claude = split_runs_for_mapping(OUTPUT_DIR, domain_label, mapping)
    openai = split_openai_runs_for_mapping(OUTPUT_DIR, domain_label, mapping)

    def tag(runs: list[dict], label: str) -> list[dict]:
        return [{**run, "frontier_provider_label": label} for run in runs]

    def merged(claude_runs: list[dict], openai_runs: list[dict]) -> list[dict]:
        combined = tag(claude_runs, "Claude") + tag(openai_runs, "ChatGPT")
        combined.sort(key=lambda run: run.get("timestamp") or "", reverse=True)
        return combined

    return {
        "current": merged(claude["current"], openai["current"]),
        "historical": merged(claude["historical"], openai["historical"]),
    }


def selected_local_model(domain_key: str, available_models: list[str]) -> str | None:
    """Resolve the model pre-selected in the live dropdown: the session's
    remembered choice if it's still on offer, else the first available model,
    else None (nothing to run against)."""
    remembered = session.get(f"{domain_key}_local_model")
    if remembered and remembered in available_models:
        return remembered
    if available_models:
        return available_models[0]
    return remembered


def local_engine_context(domain_key: str) -> dict:
    status = local_llm_status()
    return {
        "local_configured": local_llm_configured(),
        "local_reachable": status["reachable"],
        "local_status_message": status["message"],
        "local_base_url": status["base_url"],
        "local_models": status["models"],
        "selected_local_model": selected_local_model(domain_key, status["models"]),
    }


def resolve_local_run_model(domain_key: str, requested: str | None) -> str | None:
    """Per-run model resolution for a 'Run local model' click: honor the
    submitted choice if it's genuinely on offer right now, otherwise fall back
    to the first available model. Remembers the resolved choice in session so
    it pre-fills next time, without ever touching the settings store."""
    status = local_llm_status()
    available = status["models"]
    requested = (requested or "").strip()
    model = requested if requested in available else (available[0] if available else None)
    if model:
        session[f"{domain_key}_local_model"] = model
    return model


def mapping_history_context(mapping: dict, domain_label: str) -> dict:
    return mapping_audit_context(OUTPUT_DIR, mapping_label(mapping), domain_label)


def mapping_history(mapping: dict, domain_label: str) -> list[dict]:
    return mapping_history_context(mapping, domain_label)["current"]


def queue_items(mappings: list[dict], domain: dict) -> list[dict]:
    items = []
    for index, mapping in reversed(list(enumerate(mappings))):
        frontier_runs = frontier_runs_for_mapping(domain["domain_label"], mapping)
        local_runs = split_local_runs_for_mapping(OUTPUT_DIR, domain["domain_label"], mapping)
        history_groups = mapping_history_context(mapping, domain["domain_label"])
        items.append({
            "index": index,
            "mapping": mapping,
            "source_summary": source_summary(mapping),
            "destination_summary": destination_summary(mapping),
            "has_reason_flag": any(
                event.get("reason_flagged_for_review")
                for event in history_groups["current"]
            ),
            "frontier_runs": frontier_runs["current"],
            "historical_frontier_runs": frontier_runs["historical"],
            "local_runs": local_runs["current"],
            "historical_local_runs": local_runs["historical"],
        })
    return items


def discovery_engine_allowed(engine: str) -> bool:
    return (
        engine.startswith("Mock Discovery Engine")
        or (engine == FRONTIER_ENGINE_LABEL and (claude_configured() or openai_configured()))
        or (engine == LOCAL_DISCOVERY_ENGINE_LABEL and local_llm_configured())
    )


def discovery_engine_session_label(engine: str) -> str:
    if engine.startswith("Mock Discovery Engine"):
        return engine
    if engine == FRONTIER_ENGINE_LABEL:
        return "Mock baseline with FrontierLLM per-mapping comparison"
    if engine == LOCAL_DISCOVERY_ENGINE_LABEL:
        return "Mock baseline with Local (self hosted) per-mapping comparison"
    return MOCK_ENGINE_LABEL


def render_review_page(domain_key: str):
    domain = DOMAINS[domain_key]
    discovery_ran = bool(session.get(f"{domain_key}_discovery_ran"))
    mappings = load_proposals(OUTPUT_DIR, domain["proposal_file"]) if discovery_ran else []
    if discovery_ran and not mappings:
        discovery_ran = False
    return render_template(
        "index.html",
        mappings=mappings,
        queue_items=queue_items(mappings, domain),
        **frontier_engine_context(domain_key),
        **local_engine_context(domain_key),
        mock_engine_label=MOCK_ENGINE_LABEL,
        frontier_engine_label=FRONTIER_ENGINE_LABEL,
        local_engine_label=LOCAL_DISCOVERY_ENGINE_LABEL,
        discovery_ran=discovery_ran,
        discovery_source=session.get(f"{domain_key}_discovery_source", domain["source"]),
        discovery_target=session.get(f"{domain_key}_discovery_target", domain["target"]),
        discovery_engine=session.get(f"{domain_key}_discovery_engine", MOCK_ENGINE_LABEL),
        corpus_summary=build_corpus_summary(domain),
        **assignment_context(),
        domain_key=domain_key,
        domain=domain,
        active_domain=domain_key,
        active_nav="review",
        view_title="Review Queue",
    )


@app.route("/")
def index():
    return render_review_page("assurance")


@app.route("/order-management")
def order_management():
    return render_review_page("order_management")


@app.route("/run-discovery", methods=["POST"])
def run_assurance_discovery():
    domain_key = "assurance"
    domain = DOMAINS[domain_key]
    source = request.form.get("source_schema", WIRED_SOURCE)
    target = request.form.get("target_schema", WIRED_TARGET)
    engine = request.form.get("discovery_engine", MOCK_ENGINE_LABEL)
    if source == WIRED_SOURCE and target == WIRED_TARGET and discovery_engine_allowed(engine):
        run_discovery(DATA_DIR, OUTPUT_DIR)
        session[f"{domain_key}_discovery_ran"] = True
        session[f"{domain_key}_discovery_source"] = source
        session[f"{domain_key}_discovery_target"] = target
        session[f"{domain_key}_discovery_engine"] = discovery_engine_session_label(engine)
        if engine == LOCAL_DISCOVERY_ENGINE_LABEL:
            resolve_local_run_model(domain_key, request.form.get("local_model"))
    return redirect(url_for("index"))


@app.route("/order-management/run-discovery", methods=["POST"])
def run_order_management_discovery():
    domain_key = "order_management"
    domain = DOMAINS[domain_key]
    source = request.form.get("source_schema", domain["source"])
    target = request.form.get("target_schema", domain["target"])
    engine = request.form.get("discovery_engine", MOCK_ENGINE_LABEL)
    if source == domain["source"] and target == domain["target"] and discovery_engine_allowed(engine):
        run_discovery(domain["data_dir"], OUTPUT_DIR, domain["output_stem"])
        session[f"{domain_key}_discovery_ran"] = True
        session[f"{domain_key}_discovery_source"] = source
        session[f"{domain_key}_discovery_target"] = target
        session[f"{domain_key}_discovery_engine"] = discovery_engine_session_label(engine)
        if engine == LOCAL_DISCOVERY_ENGINE_LABEL:
            resolve_local_run_model(domain_key, request.form.get("local_model"))
    return redirect(url_for("order_management"))


@app.route("/mapping/<int:index>")
def mapping_detail(index: int):
    mappings = load_proposals(OUTPUT_DIR)
    if index < 0 or index >= len(mappings):
        return redirect(url_for("index"))
    retriever = EvidenceRetriever(DATA_DIR)
    evidence_lookup = retriever.evidence_by_citation()
    mapping = mappings[index]
    evidence = [
        {"id": citation, "record": evidence_lookup.get(citation)}
        for citation in mapping.get("evidence_citations", [])
    ]
    frontier_run_groups = frontier_runs_for_mapping(DOMAINS["assurance"]["domain_label"], mapping)
    local_run_groups = split_local_runs_for_mapping(OUTPUT_DIR, DOMAINS["assurance"]["domain_label"], mapping)
    history_groups = mapping_history_context(mapping, DOMAINS["assurance"]["domain_label"])
    return render_template(
        "mapping_detail.html",
        index=index,
        mapping=mapping,
        evidence=evidence,
        **assignment_context(),
        assignee_label=assignee_label(mapping.get("assigned_to")),
        decision_locked=is_decision_locked(mapping),
        history=history_groups["current"],
        historical_history=history_groups["historical"],
        **frontier_engine_context("assurance"),
        **local_engine_context("assurance"),
        frontier_runs=frontier_run_groups["current"],
        historical_frontier_runs=frontier_run_groups["historical"],
        local_runs=local_run_groups["current"],
        historical_local_runs=local_run_groups["historical"],
        min_decision_reason_length=MIN_DECISION_REASON_LENGTH,
        discovery_source=session.get("assurance_discovery_source", WIRED_SOURCE),
        discovery_target=session.get("assurance_discovery_target", WIRED_TARGET),
        domain_key="assurance",
        domain=DOMAINS["assurance"],
        active_nav="review",
        active_domain="assurance",
        view_title="Mapping Detail",
    )


@app.route("/order-management/mapping/<int:index>")
def order_mapping_detail(index: int):
    domain_key = "order_management"
    domain = DOMAINS[domain_key]
    mappings = load_proposals(OUTPUT_DIR, domain["proposal_file"])
    if index < 0 or index >= len(mappings):
        return redirect(url_for("order_management"))
    retriever = EvidenceRetriever(domain["data_dir"])
    evidence_lookup = retriever.evidence_by_citation()
    mapping = mappings[index]
    evidence = [
        {"id": citation, "record": evidence_lookup.get(citation)}
        for citation in mapping.get("evidence_citations", [])
    ]
    frontier_run_groups = frontier_runs_for_mapping(domain["domain_label"], mapping)
    local_run_groups = split_local_runs_for_mapping(OUTPUT_DIR, domain["domain_label"], mapping)
    history_groups = mapping_history_context(mapping, domain["domain_label"])
    return render_template(
        "mapping_detail.html",
        index=index,
        mapping=mapping,
        evidence=evidence,
        **assignment_context(),
        assignee_label=assignee_label(mapping.get("assigned_to")),
        decision_locked=is_decision_locked(mapping),
        history=history_groups["current"],
        historical_history=history_groups["historical"],
        **frontier_engine_context(domain_key),
        **local_engine_context(domain_key),
        frontier_runs=frontier_run_groups["current"],
        historical_frontier_runs=frontier_run_groups["historical"],
        local_runs=local_run_groups["current"],
        historical_local_runs=local_run_groups["historical"],
        min_decision_reason_length=MIN_DECISION_REASON_LENGTH,
        discovery_source=session.get(f"{domain_key}_discovery_source", domain["source"]),
        discovery_target=session.get(f"{domain_key}_discovery_target", domain["target"]),
        domain_key=domain_key,
        domain=domain,
        active_nav="review",
        active_domain=domain_key,
        view_title="Mapping Detail",
    )


@app.route("/mapping/<int:index>/decision", methods=["POST"])
def decision(index: int):
    action = request.form["action"]
    reason = request.form.get("reason", "")
    try:
        record_decision(OUTPUT_DIR, index, action, "local-reviewer", reason, advisory_async=True)
    except ValueError as exc:
        mappings = load_proposals(OUTPUT_DIR)
        frontier_run_groups = frontier_runs_for_mapping(DOMAINS["assurance"]["domain_label"], mappings[index])
        local_run_groups = split_local_runs_for_mapping(OUTPUT_DIR, DOMAINS["assurance"]["domain_label"], mappings[index])
        history_groups = mapping_history_context(mappings[index], DOMAINS["assurance"]["domain_label"])
        return render_template(
            "mapping_detail.html",
            index=index,
            mapping=mappings[index],
            evidence=[],
            error=str(exc),
            **assignment_context(),
            assignee_label="",
            decision_locked=False,
            history=history_groups["current"],
            historical_history=history_groups["historical"],
            **frontier_engine_context("assurance"),
            **local_engine_context("assurance"),
            frontier_runs=frontier_run_groups["current"],
            historical_frontier_runs=frontier_run_groups["historical"],
            local_runs=local_run_groups["current"],
            historical_local_runs=local_run_groups["historical"],
            min_decision_reason_length=MIN_DECISION_REASON_LENGTH,
            discovery_source=session.get("assurance_discovery_source", WIRED_SOURCE),
            discovery_target=session.get("assurance_discovery_target", WIRED_TARGET),
            domain_key="assurance",
            domain=DOMAINS["assurance"],
            active_nav="review",
            active_domain="assurance",
            view_title="Mapping Detail",
        ), 400
    return redirect(url_for("mapping_detail", index=index))


@app.route("/mapping/<int:index>/assign", methods=["POST"])
def assign_decision(index: int):
    assignee = request.form.get("assigned_to", "")
    reason = request.form.get("reason", "")
    try:
        assign_mapping(OUTPUT_DIR, index, assignee, "local-reviewer", reason)
    except ValueError:
        pass
    return redirect(url_for("mapping_detail", index=index))


@app.route("/mapping/<int:index>/unassign", methods=["POST"])
def unassign_decision(index: int):
    reason = request.form.get("reason", "")
    try:
        unassign_mapping(OUTPUT_DIR, index, "local-reviewer", reason)
    except ValueError:
        pass
    return redirect(url_for("mapping_detail", index=index))


@app.route("/mapping/<int:index>/frontier-run", methods=["POST"])
def run_assurance_frontier(index: int):
    provider = request.form.get("frontier_provider", "claude")
    if provider not in ("claude", "openai"):
        provider = "claude"
    session["assurance_frontier_provider"] = provider
    mappings = load_proposals(OUTPUT_DIR)
    if 0 <= index < len(mappings):
        if provider == "openai" and openai_configured():
            run_openai_comparison(
                OUTPUT_DIR,
                DATA_DIR,
                DOMAINS["assurance"]["domain_label"],
                mappings[index],
                model=DEFAULT_OPENAI_MODEL,
            )
        elif provider == "claude" and claude_configured():
            run_claude_comparison(
                OUTPUT_DIR,
                DATA_DIR,
                DOMAINS["assurance"]["domain_label"],
                mappings[index],
                model=DEFAULT_CLAUDE_MODEL,
            )
    return redirect(request.form.get("return_to") or url_for("index", _anchor=f"mapping-{index}"))


@app.route("/mapping/<int:index>/local-run", methods=["POST"])
def run_assurance_local(index: int):
    if local_llm_configured():
        model = resolve_local_run_model("assurance", request.form.get("local_model"))
        mappings = load_proposals(OUTPUT_DIR)
        if 0 <= index < len(mappings):
            run_local_comparison(
                OUTPUT_DIR,
                DATA_DIR,
                DOMAINS["assurance"]["domain_label"],
                mappings[index],
                model=model,
            )
    return redirect(request.form.get("return_to") or url_for("index", _anchor=f"mapping-{index}"))


@app.route("/order-management/mapping/<int:index>/decision", methods=["POST"])
def order_decision(index: int):
    domain_key = "order_management"
    domain = DOMAINS[domain_key]
    action = request.form["action"]
    reason = request.form.get("reason", "")
    try:
        record_decision(
            OUTPUT_DIR,
            index,
            action,
            "local-reviewer",
            reason,
            domain["proposal_file"],
            domain["domain_label"],
            advisory_async=True,
        )
    except ValueError as exc:
        mappings = load_proposals(OUTPUT_DIR, domain["proposal_file"])
        frontier_run_groups = frontier_runs_for_mapping(domain["domain_label"], mappings[index])
        local_run_groups = split_local_runs_for_mapping(OUTPUT_DIR, domain["domain_label"], mappings[index])
        history_groups = mapping_history_context(mappings[index], domain["domain_label"])
        return render_template(
            "mapping_detail.html",
            index=index,
            mapping=mappings[index],
            evidence=[],
            error=str(exc),
            **assignment_context(),
            assignee_label="",
            decision_locked=False,
            history=history_groups["current"],
            historical_history=history_groups["historical"],
            **frontier_engine_context(domain_key),
            **local_engine_context(domain_key),
            frontier_runs=frontier_run_groups["current"],
            historical_frontier_runs=frontier_run_groups["historical"],
            local_runs=local_run_groups["current"],
            historical_local_runs=local_run_groups["historical"],
            min_decision_reason_length=MIN_DECISION_REASON_LENGTH,
            discovery_source=session.get(f"{domain_key}_discovery_source", domain["source"]),
            discovery_target=session.get(f"{domain_key}_discovery_target", domain["target"]),
            domain_key=domain_key,
            domain=domain,
            active_nav="review",
            active_domain=domain_key,
            view_title="Mapping Detail",
        ), 400
    return redirect(url_for("order_mapping_detail", index=index))


@app.route("/order-management/mapping/<int:index>/assign", methods=["POST"])
def order_assign_decision(index: int):
    domain = DOMAINS["order_management"]
    assignee = request.form.get("assigned_to", "")
    reason = request.form.get("reason", "")
    try:
        assign_mapping(OUTPUT_DIR, index, assignee, "local-reviewer", reason, domain["proposal_file"], domain["domain_label"])
    except ValueError:
        pass
    return redirect(url_for("order_mapping_detail", index=index))


@app.route("/order-management/mapping/<int:index>/unassign", methods=["POST"])
def order_unassign_decision(index: int):
    domain = DOMAINS["order_management"]
    reason = request.form.get("reason", "")
    try:
        unassign_mapping(OUTPUT_DIR, index, "local-reviewer", reason, domain["proposal_file"], domain["domain_label"])
    except ValueError:
        pass
    return redirect(url_for("order_mapping_detail", index=index))


@app.route("/order-management/mapping/<int:index>/frontier-run", methods=["POST"])
def run_order_frontier(index: int):
    domain = DOMAINS["order_management"]
    provider = request.form.get("frontier_provider", "claude")
    if provider not in ("claude", "openai"):
        provider = "claude"
    session["order_management_frontier_provider"] = provider
    mappings = load_proposals(OUTPUT_DIR, domain["proposal_file"])
    if 0 <= index < len(mappings):
        if provider == "openai" and openai_configured():
            run_openai_comparison(
                OUTPUT_DIR,
                domain["data_dir"],
                domain["domain_label"],
                mappings[index],
                model=DEFAULT_OPENAI_MODEL,
            )
        elif provider == "claude" and claude_configured():
            run_claude_comparison(
                OUTPUT_DIR,
                domain["data_dir"],
                domain["domain_label"],
                mappings[index],
                model=DEFAULT_CLAUDE_MODEL,
            )
    return redirect(request.form.get("return_to") or url_for("order_management", _anchor=f"mapping-{index}"))


@app.route("/order-management/mapping/<int:index>/local-run", methods=["POST"])
def run_order_local(index: int):
    domain = DOMAINS["order_management"]
    if local_llm_configured():
        model = resolve_local_run_model("order_management", request.form.get("local_model"))
        mappings = load_proposals(OUTPUT_DIR, domain["proposal_file"])
        if 0 <= index < len(mappings):
            run_local_comparison(
                OUTPUT_DIR,
                domain["data_dir"],
                domain["domain_label"],
                mappings[index],
                model=model,
            )
    return redirect(request.form.get("return_to") or url_for("order_management", _anchor=f"mapping-{index}"))


@app.route("/approved-substrates")
def approved_substrates():
    path = OUTPUT_DIR / "approved_substrate.yaml"
    substrate = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {"versions": []}
    return render_template(
        "approved_substrates.html",
        substrate=substrate,
        active_domain=None,
        active_nav="approved",
        view_title="Approved Mappings",
    )


def render_substrate_versions_page(domain_key: str, error: str | None = None, status_code: int = 200):
    domain = DOMAINS[domain_key]
    body = render_template(
        "substrate_versions.html",
        domains=DOMAINS,
        domain_key=domain_key,
        cut_preview=cut_candidates(OUTPUT_DIR, domain["proposal_file"], domain["domain_label"]),
        versions=load_substrate_versions(OUTPUT_DIR, domain_key),
        active_version_id=active_versions(OUTPUT_DIR).get(domain_key),
        error=error,
        active_domain=None,
        active_nav="substrate_versions",
        view_title="Substrate Versions",
    )
    return body, status_code


@app.route("/substrate-versions")
def substrate_versions_page():
    domain_key = request.args.get("domain", "assurance")
    if domain_key not in DOMAINS:
        return redirect(url_for("substrate_versions_page"))
    return render_substrate_versions_page(domain_key)


@app.route("/substrate-versions/cut", methods=["POST"])
def cut_substrate_version_action():
    domain_key = request.form.get("domain_key", "assurance")
    if domain_key not in DOMAINS:
        return redirect(url_for("substrate_versions_page"))
    domain = DOMAINS[domain_key]
    try:
        cut_substrate_version(OUTPUT_DIR, domain_key, domain["domain_label"], domain["proposal_file"], "local-reviewer")
    except ValueError as exc:
        return render_substrate_versions_page(domain_key, error=str(exc), status_code=400)
    return redirect(url_for("substrate_versions_page", domain=domain_key))


@app.route("/substrate-versions/rollback", methods=["POST"])
def rollback_substrate_version_action():
    domain_key = request.form.get("domain_key", "assurance")
    if domain_key not in DOMAINS:
        return redirect(url_for("substrate_versions_page"))
    domain = DOMAINS[domain_key]
    try:
        rollback_to_version(OUTPUT_DIR, domain_key, domain["domain_label"], request.form.get("version_id", ""), "local-reviewer")
    except ValueError as exc:
        return render_substrate_versions_page(domain_key, error=str(exc), status_code=400)
    return redirect(url_for("substrate_versions_page", domain=domain_key))


@app.route("/audit-log")
def audit_log():
    all_events = load_audit_events(OUTPUT_DIR)
    event_groups = split_audit_events_at_latest_reset(all_events)
    current_flags = flagged_reason_events(event_groups["current"])
    historical_flags = flagged_reason_events(event_groups["historical"])
    return render_template(
        "audit_log.html",
        events=decorate_events_with_reason_flags(event_groups["current"]),
        historical_events=decorate_events_with_reason_flags(event_groups["historical"]),
        flagged_reasons=current_flags,
        historical_flagged_reasons=historical_flags,
        report=reviewer_activity_report(
            OUTPUT_DIR,
            DATA_DIR,
            [domain["proposal_file"] for domain in DOMAINS.values()],
        ),
        **assignment_context(),
        active_domain=None,
        active_nav="audit",
        view_title="Audit Log",
    )


@app.route("/team")
def team():
    return render_template(
        "team.html",
        members=load_team_roster(DATA_DIR),
        groups=load_team_groups(DATA_DIR),
        team_lookup=team_lookup(DATA_DIR),
        active_domain=None,
        active_nav="team",
        view_title="Team",
    )


def _redacted_error(exc: Exception, secret: str) -> str:
    message = str(exc) or exc.__class__.__name__
    if secret:
        message = message.replace(secret, "[redacted]")
    return message[:300]


def validate_anthropic_key(key: str) -> tuple[bool, str | None]:
    try:
        import anthropic
    except ImportError:
        return False, "The 'anthropic' package is not installed."
    try:
        anthropic.Anthropic(api_key=key).models.list(limit=1)
        return True, None
    except Exception as exc:
        return False, _redacted_error(exc, key)


def validate_openai_key(key: str) -> tuple[bool, str | None]:
    try:
        import openai
    except ImportError:
        return False, "The 'openai' package is not installed."
    try:
        openai.OpenAI(api_key=key).models.list()
        return True, None
    except Exception as exc:
        return False, _redacted_error(exc, key)


def validate_local_settings(base_url: str) -> tuple[bool, str | None]:
    """Settings only cares whether the endpoint itself is reachable - which
    model to use is a discovery-screen, per-run choice, not a settings one."""
    valid, error, _models = list_local_models(base_url)
    return valid, error


KEY_PROVIDERS = [
    {"provider": ANTHROPIC, "label": "Anthropic API key", "field": "anthropic_api_key", "env_var": "ANTHROPIC_API_KEY"},
    {"provider": OPENAI, "label": "OpenAI API key", "field": "openai_api_key", "env_var": "OPENAI_API_KEY"},
]


def settings_providers(results: dict) -> list[dict]:
    return [
        {**spec, "source": key_source(spec["provider"]), "result": results.get(spec["provider"])}
        for spec in KEY_PROVIDERS
    ]


def local_settings_context(result: dict | None = None) -> dict:
    return {
        "source": local_config_source(),
        "base_url": get_local_base_url() or "",
        "result": result,
    }


@app.route("/settings", methods=["GET", "POST"])
def settings():
    results = {}
    local_result = None
    if request.method == "POST":
        for spec in KEY_PROVIDERS:
            submitted = (request.form.get(spec["field"]) or "").strip()
            if not submitted:
                continue
            validator = validate_anthropic_key if spec["provider"] == ANTHROPIC else validate_openai_key
            valid, error = validator(submitted)
            if valid:
                set_api_key(spec["provider"], submitted)
                results[spec["provider"]] = {"state": "valid", "error": None}
            else:
                results[spec["provider"]] = {"state": "invalid", "error": error}
        local_base_url = (request.form.get("local_llm_base_url") or "").strip()
        if local_base_url:
            valid, error = validate_local_settings(local_base_url)
            if valid:
                set_local_config(local_base_url)
                local_result = {"state": "valid", "error": None}
            else:
                local_result = {"state": "invalid", "error": error}
    return render_template(
        "settings.html",
        providers=settings_providers(results),
        local_status=local_llm_status(),
        local_settings=local_settings_context(local_result),
        active_domain=None,
        active_nav="settings",
        view_title="Settings",
    )


@app.route("/settings/clear", methods=["POST"])
def settings_clear():
    try:
        clear_api_key(request.form.get("provider", ""))
    except ValueError:
        pass
    return redirect(url_for("settings"))


@app.route("/settings/local/clear", methods=["POST"])
def settings_local_clear():
    clear_local_config()
    return redirect(url_for("settings"))


@app.route("/demo-controls")
def demo_controls():
    return render_template(
        "demo_controls.html",
        active_domain=None,
        active_nav="demo",
        view_title="Demo Controls",
    )


@app.route("/demo-controls/reset", methods=["POST"])
def demo_reset():
    if request.form.get("confirm") == "yes":
        reset_demo_state(
            OUTPUT_DIR,
            list(DOMAINS.values()),
            "local-reviewer",
            "Reset all domain review state to pre-discovery demo baseline.",
        )
        for domain_key in DOMAINS:
            for key in ("discovery_ran", "discovery_source", "discovery_target", "discovery_engine"):
                session.pop(f"{domain_key}_{key}", None)
        return render_template("reset_transition.html")
    return redirect(url_for("demo_controls"))


if __name__ == "__main__":
    # Debug (interactive debugger + auto-reload) is opt-in: FLASK_DEBUG=1.
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1", port=int(os.environ.get("PORT", "5000")))
