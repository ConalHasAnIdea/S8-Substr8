import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def append_audit_event(
    output_dir: Path,
    mapping: str,
    action: str,
    user: str,
    reason: str,
    domain: str = "Assurance",
    assigned_to: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "domain": domain,
        "mapping": mapping,
        "action": action,
        "user": user,
        "reason": reason,
    }
    if assigned_to:
        event["assigned_to"] = assigned_to
    if extra:
        event.update(extra)
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "audit_log.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event) + "\n")
    return event
