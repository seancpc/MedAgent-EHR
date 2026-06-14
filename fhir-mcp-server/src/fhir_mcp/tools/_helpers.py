"""Shared helpers for turning verbose FHIR resources into compact dicts."""
from __future__ import annotations

from datetime import date
from typing import Any


def concept_text(concept: dict | None) -> str:
    """Extract a human label from a FHIR CodeableConcept."""
    if not concept:
        return "(unknown)"
    if concept.get("text"):
        return concept["text"]
    for coding in concept.get("coding", []):
        if coding.get("display"):
            return coding["display"]
    return "(unknown)"


def format_name(resource: dict) -> str:
    """Format the first HumanName of a FHIR resource as 'Family, Given'."""
    names = resource.get("name", [])
    if not names:
        return "(unknown)"
    n = names[0]
    if n.get("text"):
        return n["text"]
    family = n.get("family", "")
    given = " ".join(n.get("given", []))
    label = ", ".join(p for p in (family, given) if p)
    return label or "(unknown)"


def compute_age(birth_date: str | None) -> int | None:
    """Compute age in whole years from an ISO birth date (YYYY-MM-DD)."""
    if not birth_date:
        return None
    try:
        born = date.fromisoformat(str(birth_date)[:10])
    except ValueError:
        return None
    today = date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def patient_brief(resource: dict) -> dict[str, Any]:
    """Compact demographics dict for a FHIR Patient resource."""
    return {
        "patient_id": resource.get("id"),
        "name": format_name(resource),
        "birth_date": resource.get("birthDate"),
        "age": compute_age(resource.get("birthDate")),
        "gender": resource.get("gender"),
    }
