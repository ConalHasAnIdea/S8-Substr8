from dataclasses import dataclass, field
from typing import Any


@dataclass
class EvidenceBundle:
    supporting: list[dict[str, Any]] = field(default_factory=list)
    conflicting: list[dict[str, Any]] = field(default_factory=list)
    notes: list[dict[str, str]] = field(default_factory=list)
    legacy_rules: list[dict[str, Any]] = field(default_factory=list)

    @property
    def citations(self) -> list[str]:
        ids: list[str] = []
        ids.extend(item["ticket_id"] for item in self.supporting)
        ids.extend(item["ticket_id"] for item in self.conflicting)
        ids.extend(item["id"] for item in self.notes)
        ids.extend(item["id"] for item in self.legacy_rules)
        return ids

    @property
    def supporting_count(self) -> int:
        return len(self.supporting)

    @property
    def conflicting_count(self) -> int:
        return len(self.conflicting)


@dataclass
class MappingProposal:
    source_field: str
    destination_fields: list[str]
    transformation_logic: str
    confidence_score: float | None
    reasoning: str
    evidence_citations: list[str]
    governance_status: str
    source_value: str | None = None
    evidence_summary: dict[str, int] = field(default_factory=dict)
    split_hint: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        data = {
            "source_field": self.source_field,
            "destination_fields": self.destination_fields,
            "transformation_logic": self.transformation_logic,
            "confidence_score": self.confidence_score,
            "reasoning": self.reasoning,
            "evidence_citations": self.evidence_citations,
            "governance_status": self.governance_status,
            "evidence_summary": self.evidence_summary,
        }
        if self.source_value is not None:
            data["source_value"] = self.source_value
        if self.split_hint is not None:
            data["split_hint"] = self.split_hint
        return data
