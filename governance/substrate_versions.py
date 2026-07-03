import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .approval_model import load_proposals, mapping_label
from .audit_log import append_audit_event
from .mapping_display import destination_summary, source_summary

VERSIONS_FILENAME = "substrate_versions.jsonl"
ACTIVE_POINTER_FILENAME = "active_substrate_version.yaml"


def load_substrate_versions(output_dir: Path, domain_key: str | None = None) -> list[dict[str, Any]]:
    path = output_dir / VERSIONS_FILENAME
    if not path.exists():
        return []
    versions = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if domain_key:
        versions = [version for version in versions if version["domain_key"] == domain_key]
    return versions


def next_version_id(output_dir: Path, domain_key: str) -> str:
    existing = load_substrate_versions(output_dir, domain_key)
    return f"{domain_key}-v{len(existing) + 1}"


def active_versions(output_dir: Path) -> dict[str, str]:
    path = output_dir / ACTIVE_POINTER_FILENAME
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    pointer = data.get("active_version")
    return pointer if isinstance(pointer, dict) else {}


def set_active_version(output_dir: Path, domain_key: str, version_id: str) -> None:
    pointer = active_versions(output_dir)
    pointer[domain_key] = version_id
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / ACTIVE_POINTER_FILENAME).write_text(
        yaml.safe_dump({"active_version": pointer}, sort_keys=False),
        encoding="utf-8",
    )


def cut_candidates(output_dir: Path, proposal_file: str, domain_label: str) -> dict[str, list[dict[str, Any]]]:
    included = []
    excluded = []
    for mapping in load_proposals(output_dir, proposal_file):
        entry = {
            "domain": domain_label,
            "label": mapping_label(mapping),
            "status": mapping.get("governance_status"),
        }
        if mapping.get("governance_status") == "Approved":
            included.append(entry)
        else:
            excluded.append(entry)
    return {"included": included, "excluded": excluded}


def _cut_summary(approved: list[dict[str, Any]]) -> str:
    counts = Counter(mapping["source_field"] for mapping in approved)
    breakdown = ", ".join(f"{count} from {field}" for field, count in counts.items())
    noun = "mapping" if len(approved) == 1 else "mappings"
    return f"{len(approved)} approved {noun}: {breakdown}"


def cut_substrate_version(
    output_dir: Path,
    domain_key: str,
    domain_label: str,
    proposal_file: str,
    user: str,
) -> dict[str, Any]:
    approved = [
        mapping
        for mapping in load_proposals(output_dir, proposal_file)
        if mapping.get("governance_status") == "Approved"
    ]
    if not approved:
        raise ValueError("No mappings are currently in Approved status for this domain; nothing to cut.")
    version_id = next_version_id(output_dir, domain_key)
    record = {
        "version_id": version_id,
        "domain": domain_label,
        "domain_key": domain_key,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": user,
        "mapping_ids": [mapping_label(mapping) for mapping in approved],
        "mappings": [
            {
                "mapping_id": mapping_label(mapping),
                "source_field": mapping.get("source_field"),
                "source_summary": source_summary(mapping),
                "destination_fields": mapping.get("destination_fields", []),
                "destination_summary": destination_summary(mapping),
                "confidence_at_cut": mapping.get("confidence_score"),
            }
            for mapping in approved
        ],
        "summary": _cut_summary(approved),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / VERSIONS_FILENAME).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
    set_active_version(output_dir, domain_key, version_id)
    append_audit_event(
        output_dir,
        version_id,
        "substrate_version_cut",
        user,
        record["summary"],
        domain_label,
        extra={"version_id": version_id, "mapping_ids": record["mapping_ids"]},
    )
    return record


def rollback_to_version(
    output_dir: Path,
    domain_key: str,
    domain_label: str,
    version_id: str,
    user: str,
) -> dict[str, Any]:
    versions = {version["version_id"]: version for version in load_substrate_versions(output_dir, domain_key)}
    if version_id not in versions:
        raise ValueError(f"Unknown substrate version for this domain: {version_id}")
    previous_active = active_versions(output_dir).get(domain_key)
    if previous_active == version_id:
        raise ValueError(f"{version_id} is already the active substrate version.")
    set_active_version(output_dir, domain_key, version_id)
    append_audit_event(
        output_dir,
        version_id,
        "substrate_rollback",
        user,
        f"Rolled back active substrate from {previous_active or 'none'} to {version_id}. "
        "Recorded for governance; no live runtime is affected in Phase 1.",
        domain_label,
        extra={"previous_active_version": previous_active, "rolled_back_to": version_id},
    )
    return versions[version_id]
