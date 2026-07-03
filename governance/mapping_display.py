import re
from typing import Any


def source_summary(mapping: dict[str, Any]) -> str:
    source = str(mapping.get("source_field", "unknown"))
    value = mapping.get("source_value")
    if value is None or value == "":
        return source
    return f"{source}={value}"


def destination_summary(mapping: dict[str, Any]) -> str:
    fields = [str(field) for field in mapping.get("destination_fields", [])]
    transformation = str(mapping.get("transformation_logic", "") or "")
    rhs = _first_transformation_rhs(transformation)
    proposed_values = _field_values_from_rhs(fields, rhs)

    if proposed_values:
        return ", ".join(proposed_values)
    if rhs:
        return rhs
    return ", ".join(fields) if fields else "No destination proposed"


def _first_transformation_rhs(transformation: str) -> str:
    for line in transformation.splitlines():
        if "->" not in line:
            continue
        _, rhs = line.split("->", 1)
        rhs = rhs.strip()
        if rhs:
            return rhs
    return ""


def _field_values_from_rhs(fields: list[str], rhs: str) -> list[str]:
    proposed_values: list[str] = []
    for field in fields:
        match = re.search(rf"(?<![\w.]){re.escape(field)}\s*=\s*([^,\n]+)", rhs)
        if match:
            proposed_values.append(f"{field}={match.group(1).strip()}")
    return proposed_values
