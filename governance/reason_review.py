import json
import os
from pathlib import Path
from typing import Any, Protocol

from .audit_log import append_audit_event
from .reporting import load_audit_events

MIN_DECISION_REASON_LENGTH = 10
DECISION_ACTIONS = {"Approved", "Rejected", "Needs Clarification"}


class ReasonRelevanceChecker(Protocol):
    def check(self, mapping: dict[str, Any], action: str, reason: str) -> dict[str, str]:
        ...


def strip_json_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].strip() in {"```", "```json"}:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return stripped


def validate_decision_reason(output_dir: Path, user: str, reason: str) -> str:
    cleaned = reason.strip()
    if not cleaned:
        raise ValueError("Decision reason is required.")
    if len(cleaned) < MIN_DECISION_REASON_LENGTH:
        raise ValueError(f"Decision reason must be at least {MIN_DECISION_REASON_LENGTH} characters.")

    for event in reversed(load_audit_events(output_dir)):
        if event.get("user") == user and event.get("action") in DECISION_ACTIONS:
            if event.get("reason", "").strip() == cleaned:
                raise ValueError("Decision reason must differ from your previous decision reason.")
            break

    return cleaned


class ClaudeReasonRelevanceChecker:
    def __init__(self, model: str = "claude-sonnet-4-6"):
        self.model = model

    def check(self, mapping: dict[str, Any], action: str, reason: str) -> dict[str, str]:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return {"verdict": "RELEVANT", "note": "Claude relevance check is not configured."}

        try:
            import anthropic
        except ImportError:
            return {"verdict": "RELEVANT", "note": "Claude relevance check is unavailable."}

        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        prompt = (
            "Does this decision reason plausibly relate to THIS mapping decision? "
            "Answer RELEVANT unless the text is clearly nonsensical, clearly about a different mapping, "
            "or clearly placeholder/gibberish. Bias strongly toward RELEVANT - terse, blunt, or "
            "expert-shorthand reasons are RELEVANT. Only return NOT_RELEVANT when you are confident "
            "the text does not pertain to this decision at all. Respond with a JSON object: "
            '{"verdict":"RELEVANT"|"NOT_RELEVANT","note":"<one short sentence>"}.\n\n'
            f"Decision: {action}\n"
            f"Reason: {reason}\n"
            f"Mapping source_field: {mapping.get('source_field')}\n"
            f"Mapping source_value: {mapping.get('source_value')}\n"
            f"Destination fields: {mapping.get('destination_fields', [])}\n"
            f"Confidence: {mapping.get('confidence_score')}\n"
            f"Evidence/reasoning summary: {mapping.get('reasoning', '')[:1000]}"
        )
        response = client.messages.create(
            model=self.model,
            max_tokens=512,
            system="You are a conservative advisory reviewer. You never block decisions.",
            messages=[{"role": "user", "content": prompt}],
        )
        raw_text = "".join(block.text for block in response.content if block.type == "text").strip()
        parsed = json.loads(strip_json_fences(raw_text))
        verdict = parsed.get("verdict")
        if verdict not in {"RELEVANT", "NOT_RELEVANT"}:
            return {"verdict": "RELEVANT", "note": "Malformed advisory verdict treated as relevant."}
        return {"verdict": verdict, "note": parsed.get("note", "")[:240]}


def record_reason_relevance_flag(
    output_dir: Path,
    mapping: dict[str, Any],
    action: str,
    user: str,
    reason: str,
    domain: str,
    checker: ReasonRelevanceChecker | None = None,
) -> None:
    try:
        checker = checker or ClaudeReasonRelevanceChecker()
        verdict = checker.check(mapping, action, reason)
    except Exception:
        return

    if verdict.get("verdict") != "NOT_RELEVANT":
        return

    append_audit_event(
        output_dir,
        mapping.get("source_field", "unknown") + (f"={mapping['source_value']}" if mapping.get("source_value") else ""),
        "reason_flagged_for_review",
        user,
        reason,
        domain,
        extra={
            "decision_action": action,
            "flag_note": verdict.get("note", "Reason may not relate to this mapping."),
        },
    )
