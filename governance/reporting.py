import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

from .team import load_team_roster

REPORT_ACTIONS = {"Approved", "Rejected", "Needs Clarification"}
PRE_DECISION_STATES = {
    "Pending Approval",
    "Needs Clarification",
    "Insufficient Evidence",
    "Insufficient Evidence - Manual Review Required",
}


def load_audit_events(output_dir: Path) -> list[dict[str, Any]]:
    path = output_dir / "audit_log.jsonl"
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def split_audit_events_at_latest_reset(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    reset_index = None
    for index, event in enumerate(events):
        if event.get("action") == "demo_reset":
            reset_index = index
    if reset_index is None:
        return {"current": list(reversed(events)), "historical": []}
    return {
        "current": list(reversed(events[reset_index:])),
        "historical": list(reversed(events[:reset_index])),
    }


def flagged_reason_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        event for event in events
        if event.get("action") == "reason_flagged_for_review"
    ]


def decorate_events_with_reason_flags(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flags = flagged_reason_events(events)
    flag_lookup = {
        (
            flag.get("mapping"),
            flag.get("domain", "Assurance"),
            flag.get("decision_action"),
            flag.get("user"),
            flag.get("reason"),
        ): flag
        for flag in flags
    }
    decorated = []
    for event in events:
        if event.get("action") == "reason_flagged_for_review":
            continue
        entry = dict(event)
        flag = flag_lookup.get((
            entry.get("mapping"),
            entry.get("domain", "Assurance"),
            entry.get("action"),
            entry.get("user"),
            entry.get("reason"),
        ))
        if flag:
            entry["reason_flagged_for_review"] = True
            entry["flag_note"] = flag.get("flag_note", "Reason flagged for governance review.")
        decorated.append(entry)
    return decorated


def mapping_audit_context(output_dir: Path, mapping_label: str, domain_label: str) -> dict[str, list[dict[str, Any]]]:
    event_groups = split_audit_events_at_latest_reset(load_audit_events(output_dir))

    def matches_mapping(event: dict) -> bool:
        return event.get("mapping") == mapping_label and event.get("domain", "Assurance") == domain_label

    def decorated_history(events: list[dict]) -> list[dict]:
        return [
            event for event in decorate_events_with_reason_flags(events)
            if matches_mapping(event)
        ]

    return {
        "current": decorated_history(event_groups["current"]),
        "historical": decorated_history(event_groups["historical"]),
    }


def current_unassigned_count(output_dir: Path, proposal_files: list[str]) -> int:
    count = 0
    for filename in proposal_files:
        path = output_dir / filename
        if not path.exists():
            continue
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for mapping in payload.get("mappings", []):
            status = mapping.get("governance_status", "Pending Approval")
            if status in PRE_DECISION_STATES and not mapping.get("assigned_to"):
                count += 1
    return count


def reviewer_activity_report(output_dir: Path, data_dir: Path, proposal_files: list[str] | None = None) -> list[dict[str, Any]]:
    events = list(reversed(split_audit_events_at_latest_reset(load_audit_events(output_dir))["current"]))
    roster = load_team_roster(data_dir)
    stats = {
        member["id"]: {
            "id": member["id"],
            "name": member["name"],
            "role": member["role"],
            "Assigned": 0,
            "Approved": 0,
            "Rejected": 0,
            "Needs Clarification": 0,
            "total_actions": 0,
            "revision_rate": 0.0,
        }
        for member in roster
    }

    approvals_by_member: dict[str, list[tuple[int, str]]] = defaultdict(list)
    revised_approvals: dict[str, set[tuple[int, str]]] = defaultdict(set)

    for index, event in enumerate(events):
        assigned_to = event.get("assigned_to")
        action = event.get("action")
        if assigned_to not in stats:
            continue
        if action == "assigned":
            stats[assigned_to]["Assigned"] += 1
        elif action in REPORT_ACTIONS:
            stats[assigned_to][action] += 1
        else:
            continue
        stats[assigned_to]["total_actions"] += 1
        if action == "Approved":
            approvals_by_member[assigned_to].append((index, event.get("mapping", "")))

    for member_id, approvals in approvals_by_member.items():
        for approval_index, mapping in approvals:
            for later_event in events[approval_index + 1:]:
                if later_event.get("mapping") == mapping and later_event.get("action") in REPORT_ACTIONS:
                    revised_approvals[member_id].add((approval_index, mapping))
                    break

    for member_id, approvals in approvals_by_member.items():
        if approvals:
            stats[member_id]["revision_rate"] = round((len(revised_approvals[member_id]) / len(approvals)) * 100, 1)

    report = list(stats.values())
    if proposal_files is not None:
        report.append({
            "id": "UNASSIGNED",
            "name": "Unassigned",
            "role": "Current pre-decision mappings",
            "Assigned": current_unassigned_count(output_dir, proposal_files),
            "Approved": 0,
            "Rejected": 0,
            "Needs Clarification": 0,
            "total_actions": 0,
            "revision_rate": 0.0,
            "is_unassigned": True,
        })

    return report
