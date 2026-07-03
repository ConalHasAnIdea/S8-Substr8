from pathlib import Path
from typing import Any

import yaml

from .audit_log import append_audit_event


def reset_demo_state(output_dir: Path, domains: list[dict[str, Any]], user: str, reason: str = "Demo state reset") -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    for domain in domains:
        for suffix in (".yaml", ".md"):
            path = output_dir / f"{domain['output_stem']}{suffix}"
            if path.exists():
                path.unlink()

    approved_path = output_dir / "approved_substrate.yaml"
    approved_path.write_text(yaml.safe_dump({"versions": []}, sort_keys=False), encoding="utf-8")

    versions_log = output_dir / "substrate_versions.jsonl"
    if versions_log.exists():
        versions_log.write_text("", encoding="utf-8")

    active_pointer = output_dir / "active_substrate_version.yaml"
    if active_pointer.exists():
        active_pointer.write_text(yaml.safe_dump({"active_version": None}, sort_keys=False), encoding="utf-8")

    append_audit_event(
        output_dir,
        "demo_state",
        "demo_reset",
        user,
        reason,
        "All domains",
    )
