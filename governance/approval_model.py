from pathlib import Path
from threading import Thread
from typing import Any

import yaml

from .audit_log import append_audit_event
from .reason_review import ReasonRelevanceChecker, record_reason_relevance_flag, validate_decision_reason
from .versioning import add_approved_version

VALID_STATES = {
    "Pending Approval",
    "Approved",
    "Rejected",
    "Needs Clarification",
    "Insufficient Evidence - Human Required",
    "Assigned / Awaiting Decision",
}

ASSIGNED_STATUS = "Assigned / Awaiting Decision"


def load_proposals(output_dir: Path, filename: str = "proposed_mapping.yaml") -> list[dict[str, Any]]:
    path = output_dir / filename
    if not path.exists():
        return []
    return yaml.safe_load(path.read_text(encoding="utf-8")).get("mappings", [])


def save_proposals(output_dir: Path, proposals: list[dict[str, Any]], filename: str = "proposed_mapping.yaml") -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / filename).write_text(
        yaml.safe_dump({"mappings": proposals}, sort_keys=False),
        encoding="utf-8",
    )


def mapping_label(mapping: dict[str, Any]) -> str:
    label = mapping["source_field"]
    if mapping.get("source_value"):
        label += f"={mapping['source_value']}"
    return label


def is_decision_locked(mapping: dict[str, Any]) -> bool:
    return mapping.get("governance_status") == ASSIGNED_STATUS and bool(mapping.get("assigned_to"))


def assign_mapping(
    output_dir: Path,
    index: int,
    assigned_to: str,
    user: str,
    reason: str,
    filename: str = "proposed_mapping.yaml",
    domain: str = "Assurance",
) -> dict[str, Any]:
    if not assigned_to:
        raise ValueError("Select an assignee before assigning this mapping.")
    proposals = load_proposals(output_dir, filename)
    mapping = proposals[index]
    if is_decision_locked(mapping):
        raise ValueError("Mapping is already assigned.")
    if mapping.get("governance_status") in {"Approved", "Rejected"}:
        raise ValueError("Finalized mappings cannot be assigned.")
    mapping["previous_governance_status"] = mapping.get("governance_status", "Pending Approval")
    mapping["governance_status"] = ASSIGNED_STATUS
    mapping["assigned_to"] = assigned_to
    save_proposals(output_dir, proposals, filename)
    append_audit_event(output_dir, mapping_label(mapping), "assigned", user, reason, domain, assigned_to)
    return mapping


def unassign_mapping(
    output_dir: Path,
    index: int,
    user: str,
    reason: str,
    filename: str = "proposed_mapping.yaml",
    domain: str = "Assurance",
) -> dict[str, Any]:
    proposals = load_proposals(output_dir, filename)
    mapping = proposals[index]
    if not is_decision_locked(mapping):
        raise ValueError("Mapping is not currently assigned.")
    prior_assignee = mapping.get("assigned_to")
    mapping["governance_status"] = mapping.get("previous_governance_status", "Pending Approval")
    mapping.pop("assigned_to", None)
    mapping.pop("previous_governance_status", None)
    save_proposals(output_dir, proposals, filename)
    append_audit_event(output_dir, mapping_label(mapping), "unassigned", user, reason, domain, prior_assignee)
    return mapping


def record_decision(
    output_dir: Path,
    index: int,
    action: str,
    user: str,
    reason: str,
    filename: str = "proposed_mapping.yaml",
    domain: str = "Assurance",
    assigned_to: str | None = None,
    relevance_checker: ReasonRelevanceChecker | None = None,
    advisory_async: bool = False,
) -> dict[str, Any]:
    if action not in VALID_STATES:
        raise ValueError(f"Unsupported governance action: {action}")
    reason = validate_decision_reason(output_dir, user, reason)
    proposals = load_proposals(output_dir, filename)
    mapping = proposals[index]
    if is_decision_locked(mapping):
        raise ValueError("Assigned mappings must be unassigned before a decision can be recorded.")
    if mapping["governance_status"].startswith("Insufficient Evidence") and action == "Approved":
        raise ValueError("Insufficient-evidence mappings cannot be approved without new evidence.")
    mapping["governance_status"] = action
    mapping.pop("assigned_to", None)
    mapping.pop("previous_governance_status", None)
    save_proposals(output_dir, proposals, filename)
    audit_extra = None
    if action in {"Approved", "Rejected"} and mapping.get("split_hint"):
        audit_extra = {"split_hint_present": True}
    append_audit_event(output_dir, mapping_label(mapping), action, user, reason, domain, assigned_to, audit_extra)
    if advisory_async and relevance_checker is None:
        Thread(
            target=record_reason_relevance_flag,
            args=(output_dir, dict(mapping), action, user, reason, domain, None),
            daemon=True,
        ).start()
    else:
        record_reason_relevance_flag(output_dir, mapping, action, user, reason, domain, relevance_checker)
    if action == "Approved":
        approved = [item for item in proposals if item["governance_status"] == "Approved"]
        add_approved_version(output_dir, approved, user, f"Approved {mapping_label(mapping)}")
    return mapping
