from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


def next_version(existing: dict[str, Any] | None) -> str:
    if not existing or not existing.get("versions"):
        return "1.0.0"
    major, minor, patch = existing["versions"][-1]["version"].split(".")
    return f"{major}.{minor}.{int(patch) + 1}"


def add_approved_version(output_dir: Path, approved_mappings: list[dict[str, Any]], approver: str, summary: str) -> dict[str, Any]:
    path = output_dir / "approved_substrate.yaml"
    existing = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {"versions": []}
    version_record = {
        "version": next_version(existing),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "approver": approver,
        "summary": summary,
        "mappings": approved_mappings,
    }
    existing.setdefault("versions", []).append(version_record)
    path.write_text(yaml.safe_dump(existing, sort_keys=False), encoding="utf-8")
    return version_record
