import json
from pathlib import Path
from typing import Any

import yaml


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_team_roster(data_dir: Path) -> dict[str, dict[str, Any]]:
    roster_path = data_dir / "team_roster.yaml"
    if not roster_path.exists() and data_dir.parent != data_dir:
        roster_path = data_dir.parent / "team_roster.yaml"
    if not roster_path.exists():
        return {}
    roster = load_yaml(roster_path)
    return {member["id"]: member for member in roster.get("team", [])}


def load_operator_notes(path: Path) -> list[dict[str, str]]:
    notes: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    body: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## Operator Note"):
            if current:
                current["text"] = "\n".join(body).strip()
                notes.append(current)
            title = line.replace("## ", "").strip()
            note_id = title.split(":", 1)[0]
            current = {"id": note_id, "title": title}
            body = []
        elif current:
            body.append(line)
    if current:
        current["text"] = "\n".join(body).strip()
        notes.append(current)
    return notes


class EvidenceRetriever:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        config_path = data_dir / "domain_config.json"
        self.domain_config = load_json(config_path) if config_path.exists() else {
            "domain_key": "assurance",
            "domain_label": "Assurance",
            "source_label": "TMF642 Alarm Management",
            "target_label": "ServiceNow Incident",
            "source_schema": "tmf642_alarm_schema.json",
            "target_schema": "servicenow_incident_schema.json",
            "historical_records": "historical_tickets.jsonl",
            "fixtures": "alarm_fixtures.jsonl",
            "record_id_field": "ticket_id",
        }
        self.alarm_schema = load_json(data_dir / self.domain_config["source_schema"])
        self.incident_schema = load_json(data_dir / self.domain_config["target_schema"])
        self.source_schema = self.alarm_schema
        self.target_schema = self.incident_schema
        self.legacy_mapping = load_yaml(data_dir / "legacy_mapping.yaml")
        self.tickets = load_jsonl(data_dir / self.domain_config["historical_records"])
        self.records = self.tickets
        self.fixtures = load_jsonl(data_dir / self.domain_config["fixtures"])
        self.notes = load_operator_notes(data_dir / "operator_notes.md")
        self.team_roster = load_team_roster(data_dir)
        self._attach_note_authors()

    def _attach_note_authors(self) -> None:
        meta_path = self.data_dir / "operator_notes_meta.yaml"
        if not meta_path.exists():
            return
        note_authors = load_yaml(meta_path).get("notes", {})
        for note in self.notes:
            author_id = note_authors.get(note["id"])
            if author_id:
                note["author_id"] = author_id
                note["author"] = self.team_roster.get(author_id)

    def weighted_notes(self, notes: list[dict[str, Any]]) -> list[tuple[str, float]]:
        weighted: list[tuple[str, float]] = []
        for note in notes:
            author = note.get("author")
            if author:
                weighted.append((note["id"], float(author["authority_weight"])))
        return weighted

    def note_author_fragments(self, notes: list[dict[str, Any]]) -> list[str]:
        fragments: list[str] = []
        for note in notes:
            author = note.get("author")
            if author:
                fragments.append(
                    f"{note['id']} ({author['name']}, {author['role']}, authority {author['authority_weight']})"
                )
        return fragments

    def tickets_by(self, field: str, value: str) -> list[dict[str, Any]]:
        ticket_key = {
            "perceivedSeverity": "perceived_severity",
            "probableCause": "probable_cause",
            "vendor": "vendor",
        }.get(field, field)
        return [ticket for ticket in self.tickets if ticket.get(ticket_key) == value]

    def records_by_source(self, field: str, value: str) -> list[dict[str, Any]]:
        if self.domain_config["domain_key"] == "assurance":
            return self.tickets_by(field, value)
        return [
            record for record in self.records
            if record.get("source", {}).get(field) == value
        ]

    def fixture_values_for(self, field: str) -> list[str]:
        values: set[str] = set()
        for fixture in self.fixtures:
            if field in fixture:
                values.add(fixture[field])
            if field in fixture.get("characteristic", {}):
                values.add(fixture["characteristic"][field])
        return sorted(values)

    def legacy_rules_for(self, field: str, value: str) -> list[dict[str, Any]]:
        return [
            rule
            for rule in self.legacy_mapping.get("rules", [])
            if rule.get("source_field") == field and rule.get("source_value") == value
        ]

    def notes_for(self, terms: list[str]) -> list[dict[str, str]]:
        matches: list[dict[str, str]] = []
        lowered_terms = [term.lower().replace("_", " ") for term in terms]
        for note in self.notes:
            haystack = f"{note['title']} {note['text']}".lower().replace("_", " ")
            if any(term in haystack for term in lowered_terms):
                matches.append(note)
        return matches

    def evidence_by_citation(self) -> dict[str, dict[str, Any]]:
        lookup: dict[str, dict[str, Any]] = {}
        record_id_field = self.domain_config.get("record_id_field", "ticket_id")
        lookup.update({record[record_id_field]: record for record in self.records})
        lookup.update({note["id"]: note for note in self.notes})
        lookup.update({rule["id"]: rule for rule in self.legacy_mapping.get("rules", [])})
        return lookup
