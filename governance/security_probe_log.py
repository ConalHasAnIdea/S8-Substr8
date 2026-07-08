"""
Append-only history of /security "Run Probes" clicks, so the injection
scorecard survives a page reload instead of vanishing the instant you
navigate away. Only a deliberate live run is logged here - the Mock-only
scoring that happens passively on every page GET is not, since that isn't a
security check anyone consciously triggered.

Records are condensed: per-engine held/followed/errored counts and a
followed/error verdict per scenario by name. The static scenario metadata
(payload text, description, intent) lives in discovery/injection_suite.py
and is looked up fresh at render time, so it is never duplicated per run.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RUN_LOG = "security_probe_runs.jsonl"


def _condense_column(column: dict[str, Any]) -> dict[str, Any]:
    result = column.get("result")
    return {
        "key": column["key"],
        "label": column["label"],
        "status": column["status"],
        "held": result["held"] if result else None,
        "followed": result["followed"] if result else None,
        "errored": result["errored"] if result else None,
        "total": result["total"] if result else None,
        "scenarios": [
            {
                "scenario": row["scenario"],
                "followed": row["followed"],
                "error": row.get("error"),
            }
            for row in (result["scenarios"] if result else [])
        ],
    }


def append_security_probe_run(
    output_dir: Path,
    columns: list[dict[str, Any]],
    user: str = "local-reviewer",
) -> dict[str, Any]:
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user": user,
        "engines": [_condense_column(column) for column in columns],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / RUN_LOG).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
    return record


def load_security_probe_runs(output_dir: Path) -> list[dict[str, Any]]:
    """Newest first, matching every other history view in this app."""
    path = output_dir / RUN_LOG
    if not path.exists():
        return []
    records = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return list(reversed(records))
