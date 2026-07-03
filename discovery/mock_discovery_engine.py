from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .confidence import apply_note_weighting, derive_confidence, detect_split
from .discovery_engine import DiscoveryEngine
from .evidence_model import MappingProposal
from .retrieval import EvidenceRetriever
from governance.policy_rules import apply_policy


class MockDiscoveryEngine(DiscoveryEngine):
    def discover(self, data_dir: Path) -> list[dict[str, Any]]:
        retriever = EvidenceRetriever(data_dir)
        if retriever.domain_config["domain_key"] != "assurance":
            return self._discover_configured_domain(retriever)

        proposals: list[MappingProposal] = []
        proposals.append(self._severity_to_impact_urgency(retriever))

        probable_causes = sorted(
            {fixture["probableCause"] for fixture in retriever.fixtures}
            | {ticket["probable_cause"] for ticket in retriever.tickets}
        )
        for cause in probable_causes:
            proposals.append(self._probable_cause_assignment(cause, retriever))

        return [apply_policy(proposal.to_dict()) for proposal in proposals]

    def _discover_configured_domain(self, retriever: EvidenceRetriever) -> list[dict[str, Any]]:
        proposals: list[MappingProposal] = []
        for mapping_config in retriever.domain_config.get("candidate_mappings", []):
            field = mapping_config["source_field"]
            values = set(retriever.fixture_values_for(field))
            for record in retriever.records:
                if field in record.get("source", {}):
                    values.add(record["source"][field])
            for value in sorted(values):
                proposals.append(self._configured_field_value_mapping(value, mapping_config, retriever))
        return [apply_policy(proposal.to_dict()) for proposal in proposals]

    def _configured_field_value_mapping(
        self,
        value: str,
        mapping_config: dict[str, Any],
        retriever: EvidenceRetriever,
    ) -> MappingProposal:
        source_field = mapping_config["source_field"]
        destination_fields = mapping_config["destination_fields"]
        records = retriever.records_by_source(source_field, value)
        rules = retriever.legacy_rules_for(source_field, value)
        notes = retriever.notes_for([value, source_field] + mapping_config.get("note_terms", []))
        if not records and not rules and not notes:
            return MappingProposal(
                source_field=source_field,
                source_value=value,
                destination_fields=destination_fields,
                transformation_logic=f"{value} -> no proposed {', '.join(destination_fields)}",
                confidence_score=None,
                reasoning=(
                    f"No historical records, operator notes, or legacy rules mention {source_field}={value}. "
                    "The mock engine refuses to fabricate a mapping and routes this value to a human."
                ),
                evidence_citations=[],
                governance_status="Insufficient Evidence - Human Required",
                evidence_summary={"supporting": 0, "conflicting": 0},
            )

        correct = [record for record in records if record["mapping_correct"] and not record["later_correction"]]
        outcome_counts = Counter(
            tuple(record.get("outcome", {}).get(destination) for destination in destination_fields)
            for record in correct
        )
        if outcome_counts:
            selected_outcome, support_count = outcome_counts.most_common(1)[0]
            selected = dict(zip(destination_fields, selected_outcome))
            split_hint = detect_split(outcome_counts, len(correct))
        elif rules:
            selected = {field: rules[0].get("outcome", {}).get(field) for field in destination_fields}
            support_count = 0
            split_hint = None
        else:
            selected = {field: "Human Review" for field in destination_fields}
            support_count = 0
            split_hint = None

        supporting = [
            record for record in correct
            if all(record.get("outcome", {}).get(destination) == selected[destination] for destination in destination_fields)
        ]
        conflicting = [
            record for record in records
            if record not in supporting
        ]

        legacy_outcomes = {
            tuple(rule.get("outcome", {}).get(destination) for destination in destination_fields)
            for rule in rules
        }
        if len(legacy_outcomes) > 1:
            conflicting.append({
                retriever.domain_config["record_id_field"]: ", ".join(rule["id"] for rule in rules),
                "outcome": "legacy conflict",
            })

        base_confidence = derive_confidence(len(supporting), len(conflicting))
        confidence, weighting_explanation = apply_note_weighting(base_confidence, retriever.weighted_notes(notes))
        record_id_field = retriever.domain_config["record_id_field"]
        citations = [record[record_id_field] for record in supporting + conflicting if record_id_field in record]
        citations += [note["id"] for note in notes] + [rule["id"] for rule in rules]
        selected_text = ", ".join(f"{field}={selected[field]}" for field in destination_fields)
        conflict_ids = [record[record_id_field] for record in conflicting if record_id_field in record]
        reasoning = (
            f"Derived from {len(records)} historical {source_field}={value} records: "
            f"{len(supporting)} support {selected_text} and {len(conflicting)} conflict or were corrected."
        )
        if support_count:
            reasoning += f" The leading outcome appeared in {support_count} correct records."
        if conflict_ids:
            reasoning += f" Conflicting citations: {', '.join(conflict_ids)}."
        if notes:
            reasoning += f" Operator context included {', '.join(note['id'] for note in notes)}."
            author_fragments = retriever.note_author_fragments(notes)
            if author_fragments:
                reasoning += f" Note authority: {'; '.join(author_fragments)}."
        if weighting_explanation:
            reasoning += f" {weighting_explanation}"
        if len(legacy_outcomes) > 1:
            reasoning += " Legacy rules disagree with each other, so policy should require review."

        return MappingProposal(
            source_field=source_field,
            source_value=value,
            destination_fields=destination_fields,
            transformation_logic=f"{value} -> {selected_text}",
            confidence_score=confidence,
            reasoning=reasoning,
            evidence_citations=citations,
            governance_status="Pending Approval",
            evidence_summary={"supporting": len(supporting), "conflicting": len(conflicting)},
            split_hint=split_hint,
        )

    def _severity_to_impact_urgency(self, retriever: EvidenceRetriever) -> MappingProposal:
        tickets_by_severity: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for ticket in retriever.tickets:
            tickets_by_severity[ticket["perceived_severity"]].append(ticket)

        lines: list[str] = []
        supporting: list[dict[str, Any]] = []
        conflicting: list[dict[str, Any]] = []
        for severity in retriever.alarm_schema["fields"]["perceivedSeverity"]["enum"]:
            tickets = tickets_by_severity.get(severity, [])
            if not tickets:
                lines.append(f"{severity} -> insufficient evidence")
                continue
            correct = [ticket for ticket in tickets if ticket["mapping_correct"] and not ticket["later_correction"]]
            outcomes = Counter((ticket["resulting_impact"], ticket["resulting_urgency"]) for ticket in correct)
            if not outcomes:
                lines.append(f"{severity} -> insufficient evidence")
                conflicting.extend(tickets)
                continue
            (impact, urgency), support_count = outcomes.most_common(1)[0]
            severity_support = [
                ticket for ticket in correct
                if (ticket["resulting_impact"], ticket["resulting_urgency"]) == (impact, urgency)
            ]
            severity_conflicts = [
                ticket for ticket in tickets
                if ticket not in severity_support
            ]
            supporting.extend(severity_support)
            conflicting.extend(severity_conflicts)
            lines.append(
                f"{severity} -> impact={impact}, urgency={urgency} "
                f"({support_count} of {len(tickets)} historical tickets)"
            )

        notes = retriever.notes_for(["critical", "unknown customer impact"])
        rules = retriever.legacy_rules_for("perceivedSeverity", "critical") + retriever.legacy_rules_for("perceivedSeverity", "major")
        base_confidence = derive_confidence(len(supporting), len(conflicting))
        confidence, weighting_explanation = apply_note_weighting(base_confidence, retriever.weighted_notes(notes))
        citations = [ticket["ticket_id"] for ticket in supporting + conflicting] + [note["id"] for note in notes] + [rule["id"] for rule in rules]
        conflicts = [ticket["ticket_id"] for ticket in conflicting]
        reasoning = (
            f"Derived from {len(supporting) + len(conflicting)} historical severity examples: "
            f"{len(supporting)} support the selected impact/urgency outcomes and "
            f"{len(conflicting)} conflict or were later corrected."
        )
        if conflicts:
            reasoning += f" Conflicting cases ({', '.join(conflicts)}) reduced confidence."
        if notes:
            reasoning += f" {notes[0]['id']} reinforces the critical alarm handling policy."
            author_fragments = retriever.note_author_fragments(notes)
            if author_fragments:
                reasoning += f" Note authority: {'; '.join(author_fragments)}."
        if weighting_explanation:
            reasoning += f" {weighting_explanation}"
        reasoning += " ServiceNow priority is derived downstream from the operator impact x urgency matrix."
        return MappingProposal(
            source_field="perceivedSeverity",
            destination_fields=["impact", "urgency"],
            transformation_logic="\n".join(lines) + "\npriority is derived by ServiceNow Priority Data Lookup",
            confidence_score=confidence,
            reasoning=reasoning,
            evidence_citations=citations,
            governance_status="Pending Approval",
            evidence_summary={"supporting": len(supporting), "conflicting": len(conflicting)},
        )

    def _probable_cause_assignment(self, cause: str, retriever: EvidenceRetriever) -> MappingProposal:
        tickets = retriever.tickets_by("probableCause", cause)
        rules = retriever.legacy_rules_for("probableCause", cause)
        notes = retriever.notes_for([cause])
        if not tickets and not rules and not notes:
            return MappingProposal(
                source_field="probableCause",
                source_value=cause,
                destination_fields=["assignment_group"],
                transformation_logic=f"{cause} -> no proposed assignment_group",
                confidence_score=None,
                reasoning=(
                    f"No historical tickets, operator notes, or legacy rules mention probableCause={cause}. "
                    "The mock engine refuses to fabricate a mapping and routes this value to a human."
                ),
                evidence_citations=[],
                governance_status="Insufficient Evidence - Human Required",
                evidence_summary={"supporting": 0, "conflicting": 0},
            )

        correct = [ticket for ticket in tickets if ticket["mapping_correct"] and not ticket["later_correction"]]
        outcomes = Counter(ticket["assignment_group"] for ticket in correct)
        if outcomes:
            assignment_group, support_count = outcomes.most_common(1)[0]
            split_hint = detect_split(outcomes, len(correct))
        elif rules:
            assignment_group = rules[0]["outcome"]["assignment_group"]
            support_count = 0
            split_hint = None
        else:
            assignment_group = "Human Review"
            support_count = 0
            split_hint = None

        supporting = [ticket for ticket in correct if ticket["assignment_group"] == assignment_group]
        conflicting = [
            ticket for ticket in tickets
            if ticket["assignment_group"] != assignment_group or not ticket["mapping_correct"] or ticket["later_correction"]
        ]

        legacy_outcomes = {
            rule.get("outcome", {}).get("assignment_group")
            for rule in rules
            if "assignment_group" in rule.get("outcome", {})
        }
        if len(legacy_outcomes) > 1:
            synthetic_conflict = {
                "ticket_id": ", ".join(rule["id"] for rule in rules),
                "assignment_group": "legacy conflict",
            }
            conflicting.append(synthetic_conflict)

        base_confidence = derive_confidence(len(supporting), len(conflicting))
        confidence, weighting_explanation = apply_note_weighting(base_confidence, retriever.weighted_notes(notes))
        citations = [ticket["ticket_id"] for ticket in supporting + conflicting if "ticket_id" in ticket]
        citations += [note["id"] for note in notes] + [rule["id"] for rule in rules]
        conflict_ids = [ticket["ticket_id"] for ticket in conflicting if "ticket_id" in ticket]
        reasoning = (
            f"Derived from {len(tickets)} historical {cause} tickets: {len(supporting)} support "
            f"assignment_group={assignment_group} and {len(conflicting)} conflict or were corrected."
        )
        if support_count:
            reasoning += f" The leading outcome appeared in {support_count} correct tickets."
        if conflict_ids:
            reasoning += f" Conflicting citations: {', '.join(conflict_ids)}."
        if notes:
            reasoning += f" Operator context included {', '.join(note['id'] for note in notes)}."
            author_fragments = retriever.note_author_fragments(notes)
            if author_fragments:
                reasoning += f" Note authority: {'; '.join(author_fragments)}."
        if weighting_explanation:
            reasoning += f" {weighting_explanation}"
        if len(legacy_outcomes) > 1:
            reasoning += " Legacy rules disagree with each other, so policy should require review."

        return MappingProposal(
            source_field="probableCause",
            source_value=cause,
            destination_fields=["assignment_group"],
            transformation_logic=f"{cause} -> assignment_group={assignment_group}",
            confidence_score=confidence,
            reasoning=reasoning,
            evidence_citations=citations,
            governance_status="Pending Approval",
            evidence_summary={"supporting": len(supporting), "conflicting": len(conflicting)},
            split_hint=split_hint,
        )


def run_discovery(data_dir: Path, output_dir: Path, output_stem: str = "proposed_mapping") -> list[dict[str, Any]]:
    import yaml

    output_dir.mkdir(parents=True, exist_ok=True)
    proposals = MockDiscoveryEngine().discover(data_dir)
    (output_dir / f"{output_stem}.yaml").write_text(yaml.safe_dump({"mappings": proposals}, sort_keys=False), encoding="utf-8")
    lines = ["# Proposed Substr8 Mapping", ""]
    for item in proposals:
        label = item["source_field"]
        if item.get("source_value"):
            label += f"={item['source_value']}"
        lines.extend([
            f"## {label}",
            f"- Destinations: {', '.join(item['destination_fields'])}",
            f"- Confidence: {item['confidence_score']}",
            f"- Status: {item['governance_status']}",
            f"- Citations: {', '.join(item['evidence_citations']) or 'none'}",
            "",
            item["reasoning"],
            "",
        ])
    (output_dir / f"{output_stem}.md").write_text("\n".join(lines), encoding="utf-8")
    return proposals
