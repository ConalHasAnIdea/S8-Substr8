from pathlib import Path
from typing import Any

import yaml


def load_team_roster(data_dir: Path) -> list[dict[str, Any]]:
    path = data_dir / "team_roster.yaml"
    if not path.exists():
        return []
    return yaml.safe_load(path.read_text(encoding="utf-8")).get("team", [])


def load_team_groups(data_dir: Path) -> list[dict[str, Any]]:
    path = data_dir / "team_groups.yaml"
    if not path.exists():
        return []
    return yaml.safe_load(path.read_text(encoding="utf-8")).get("groups", [])


def assignment_options(data_dir: Path) -> list[dict[str, str]]:
    members = [
        {
            "id": member["id"],
            "label": f"{member['name']} - {member['role']}",
            "kind": "member",
        }
        for member in load_team_roster(data_dir)
    ]
    groups = [
        {
            "id": group["id"],
            "label": f"{group['name']} - group",
            "kind": "group",
        }
        for group in load_team_groups(data_dir)
    ]
    return members + groups


def team_lookup(data_dir: Path) -> dict[str, dict[str, Any]]:
    return {member["id"]: member for member in load_team_roster(data_dir)}


def group_lookup(data_dir: Path) -> dict[str, dict[str, Any]]:
    return {group["id"]: group for group in load_team_groups(data_dir)}
