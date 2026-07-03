CONFIDENCE_THRESHOLD = 0.70


def apply_policy(mapping: dict) -> dict:
    if mapping["governance_status"].startswith("Insufficient Evidence"):
        return mapping
    if mapping.get("confidence_score") is None:
        mapping["governance_status"] = "Insufficient Evidence - Human Required"
    elif mapping["confidence_score"] < CONFIDENCE_THRESHOLD:
        mapping["governance_status"] = "Needs Clarification"
    elif mapping.get("evidence_summary", {}).get("conflicting", 0) > 0:
        mapping["governance_status"] = "Needs Clarification"
    else:
        mapping["governance_status"] = "Pending Approval"
    if "priority" in mapping.get("destination_fields", []):
        mapping["governance_status"] = "Rejected"
    return mapping
