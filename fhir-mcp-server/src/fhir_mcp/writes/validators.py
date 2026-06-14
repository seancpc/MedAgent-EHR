"""Validation for staged writes.

Each resource type has a validator that checks required fields, resolves medical
codes, and applies sanity ranges. Validators never touch the FHIR server — they
are pure functions over the payload and the code tables, which makes them easy
to unit-test.

The dose / value sanity tables below are a PROVISIONAL v1 seed set and must be
verified and expanded against public clinical references before real use.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..coding.resolver import Resolution, resolve

# --- provisional sanity tables (verify before real use) ------------------
# Observation plausible value ranges, keyed by lowercased type term.
_VALUE_RANGES: dict[str, tuple[float, float]] = {
    "body weight": (0.5, 500.0),
    "body height": (10.0, 280.0),
    "heart rate": (10.0, 300.0),
    "systolic blood pressure": (40.0, 300.0),
    "diastolic blood pressure": (20.0, 200.0),
    "body temperature": (25.0, 45.0),
    "oxygen saturation": (10.0, 100.0),
}
# Max plausible total daily dose in mg, keyed by lowercased drug display name.
_MAX_DAILY_DOSE_MG: dict[str, float] = {
    "metformin": 2550.0,
    "lisinopril": 80.0,
    "atorvastatin": 80.0,
    "amlodipine": 10.0,
    "metoprolol": 400.0,
    "furosemide": 600.0,
    "losartan": 100.0,
    "hydrochlorothiazide": 50.0,
}
_FREQUENCY_PER_DAY: dict[str, int] = {
    "qd": 1, "daily": 1, "once daily": 1, "od": 1,
    "bid": 2, "twice daily": 2,
    "tid": 3, "three times daily": 3,
    "qid": 4, "four times daily": 4,
}
_SERVICE_CATEGORIES = {"laboratory", "imaging", "referral"}


@dataclass
class ValidationResult:
    """Outcome of validating a write payload."""

    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    resolved: dict[str, Resolution] = field(default_factory=dict)
    preview: str = ""


def _as_number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _missing(payload: dict, *keys: str) -> list[str]:
    return [k for k in keys if payload.get(k) in (None, "")]


def _norm(text: Any) -> str:
    return " ".join(str(text).lower().split())


def validate_observation(payload: dict, code_tables: dict) -> ValidationResult:
    if _missing(payload, "patient_id"):
        return ValidationResult(False, ["missing required field(s): patient_id"])

    result = ValidationResult(ok=True)

    # code: an explicit flowsheet/free-text code (code_text) bypasses LOINC
    # resolution; otherwise resolve the plain `type` term to a LOINC code.
    if not payload.get("code_text"):
        if _missing(payload, "type"):
            return ValidationResult(
                False, ["missing required field(s): type (or code_text)"]
            )
        loinc = code_tables.get("LOINC")
        res = resolve(payload["type"], loinc) if loinc else None
        if res is None or not res.resolved:
            return ValidationResult(
                False,
                [f"could not resolve observation type '{payload['type']}' to a "
                 f"LOINC code"],
            )
        result.resolved["type"] = res

    label = payload.get("code_text") or payload.get("type")

    # value: a string (e.g. "118/77 mmHg") OR a numeric quantity + unit
    if payload.get("value_string") not in (None, ""):
        result.preview = (
            f"Record {label} = {payload['value_string']} "
            f"for patient {payload['patient_id']}"
        )
        return result

    miss = _missing(payload, "value", "unit")
    if miss:
        return ValidationResult(False, [f"missing required field(s): {', '.join(miss)}"])
    number = _as_number(payload["value"])
    if number is None:
        return ValidationResult(False, [f"value '{payload['value']}' is not numeric"])

    rng = _VALUE_RANGES.get(_norm(payload["type"])) if payload.get("type") else None
    if rng and not (rng[0] <= number <= rng[1]):
        return ValidationResult(
            False,
            [f"value {number} {payload['unit']} is outside the plausible range "
             f"{rng[0]}-{rng[1]} for {payload['type']}"],
        )

    result.preview = (
        f"Record {label} = {payload['value']} {payload['unit']} "
        f"for patient {payload['patient_id']}"
    )
    return result


def validate_medication_request(payload: dict, code_tables: dict) -> ValidationResult:
    miss = _missing(payload, "patient_id", "dose_value", "dose_unit")
    if miss:
        return ValidationResult(False, [f"missing required field(s): {', '.join(miss)}"])

    has_explicit = bool(payload.get("code") and payload.get("code_system"))
    if not has_explicit and _missing(payload, "medication"):
        return ValidationResult(
            False, ["missing required field(s): medication (or code + code_system)"]
        )

    result = ValidationResult(ok=True)
    # An explicit drug code (e.g. an NDC given by the task) is used verbatim.
    if not has_explicit:
        rxnorm = code_tables.get("RxNorm")
        res = resolve(payload["medication"], rxnorm) if rxnorm else None
        if res is None or not res.resolved:
            return ValidationResult(
                False,
                [f"could not resolve medication '{payload['medication']}' to an "
                 f"RxNorm code"],
            )
        result.resolved["medication"] = res

    dose = _as_number(payload["dose_value"])
    if dose is None or dose <= 0:
        return ValidationResult(
            False, [f"dose_value '{payload['dose_value']}' must be a positive number"]
        )

    # Daily-dose sanity only applies to a resolved known drug dosed in mg with a
    # parseable frequency; skip for explicit codes / infusions without one.
    freq = payload.get("frequency")
    if not has_explicit and freq and str(payload["dose_unit"]).lower() == "mg":
        per_day = _FREQUENCY_PER_DAY.get(_norm(freq))
        if per_day is not None:
            max_mg = _MAX_DAILY_DOSE_MG.get(_norm(result.resolved["medication"].display))
            if max_mg is not None and dose * per_day > max_mg:
                return ValidationResult(
                    False,
                    [f"total daily dose {dose * per_day:g} mg exceeds the plausible "
                     f"maximum {max_mg:g} mg/day. Re-check dose or frequency."],
                )

    label = payload.get("medication") or payload.get("code")
    result.preview = (
        f"Prescribe {label} {payload['dose_value']}{payload['dose_unit']} "
        f"for patient {payload['patient_id']}"
    )
    return result


def validate_service_request(payload: dict, code_tables: dict) -> ValidationResult:
    miss = _missing(payload, "patient_id", "category")
    if miss:
        return ValidationResult(False, [f"missing required field(s): {', '.join(miss)}"])

    has_explicit = bool(payload.get("code") and payload.get("code_system"))
    if not has_explicit and _missing(payload, "service"):
        return ValidationResult(
            False, ["missing required field(s): service (or code + code_system)"]
        )

    if _norm(payload["category"]) not in _SERVICE_CATEGORIES:
        return ValidationResult(
            False,
            [f"category '{payload['category']}' is invalid; expected one of: "
             f"{', '.join(sorted(_SERVICE_CATEGORIES))}"],
        )

    result = ValidationResult(ok=True)
    # An explicit code+system (e.g. provided in the task) is used verbatim and
    # needs no resolution. Otherwise try LOINC (labs) then SNOMED (procedures).
    if not has_explicit:
        for system in ("LOINC", "SNOMED"):
            table = code_tables.get(system)
            if table:
                candidate = resolve(payload["service"], table)
                if candidate.resolved:
                    result.resolved["service"] = candidate
                    break
        if "service" not in result.resolved:
            result.warnings.append(
                f"could not resolve service '{payload['service']}' to a code; "
                f"the order will use free text"
            )

    label = payload.get("service") or payload.get("code")
    result.preview = (
        f"Order {label} ({payload['category']}) for patient "
        f"{payload['patient_id']}, priority {payload.get('priority', 'routine')}"
    )
    return result


def validate_document_reference(payload: dict, code_tables: dict) -> ValidationResult:
    miss = _missing(payload, "patient_id", "note_type", "text")
    if miss:
        return ValidationResult(False, [f"missing required field(s): {', '.join(miss)}"])

    result = ValidationResult(ok=True)
    result.preview = (
        f"Add {payload['note_type']} ({len(str(payload['text']))} chars) "
        f"for patient {payload['patient_id']}"
    )
    return result


_VALIDATORS = {
    "Observation": validate_observation,
    "MedicationRequest": validate_medication_request,
    "ServiceRequest": validate_service_request,
    "DocumentReference": validate_document_reference,
}

SUPPORTED_RESOURCE_TYPES = tuple(_VALIDATORS.keys())


def validate(resource_type: str, payload: dict, code_tables: dict) -> ValidationResult:
    """Validate a write payload for the given FHIR resource type."""
    fn = _VALIDATORS.get(resource_type)
    if fn is None:
        return ValidationResult(
            False,
            [f"unknown resource_type '{resource_type}'. "
             f"Supported: {', '.join(_VALIDATORS)}"],
        )
    return fn(payload, code_tables)
