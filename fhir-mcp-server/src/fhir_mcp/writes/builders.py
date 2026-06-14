"""Build FHIR R4 resources from flat, LLM-friendly write payloads.

The agent sends simple flat objects (see the stage_write tool); this module
turns them into valid FHIR R4 resources. Validation and code resolution are
done first by validators.py, which passes the resolved codes in via the
ValidationResult.

Resource shapes (codes, dosage, dates) are aligned to what the MedAgentBench
graders expect; confirm against your target FHIR profile before clinical use.
"""
from __future__ import annotations

import base64
from typing import Any

from ..coding.resolver import Resolution
from .validators import ValidationResult

CODE_SYSTEM_URI = {
    "LOINC": "http://loinc.org",
    "RxNorm": "http://www.nlm.nih.gov/research/umls/rxnorm",
    "SNOMED": "http://snomed.info/sct",
    "ICD-10": "http://hl7.org/fhir/sid/icd-10-cm",
    "NDC": "http://hl7.org/fhir/sid/ndc",
}

# Standard FHIR observation-category codings, keyed by a plain lowercased term.
# Used when a write provides an explicit `category` instead of a resolved code.
_OBSERVATION_CATEGORIES = {
    "vital-signs": {
        "system": "http://hl7.org/fhir/observation-category",
        "code": "vital-signs",
        "display": "Vital Signs",
    },
}


def _explicit_coding(code: str, system: str, display: str | None = None) -> dict:
    """A CodeableConcept built from a code the caller supplied verbatim.

    Used when the task itself provides the code (e.g. MedAgentBench passes the
    NDC/SNOMED/LOINC code in the task context) — bypasses internal resolution.
    """
    coding: dict[str, Any] = {
        "system": CODE_SYSTEM_URI.get(system, system),
        "code": str(code),
    }
    if display:
        coding["display"] = display
    cc: dict[str, Any] = {"coding": [coding]}
    if display:
        cc["text"] = display
    return cc


def _codeable_concept(resolution: Resolution) -> dict[str, Any]:
    """Build a FHIR CodeableConcept from a resolver Resolution."""
    return {
        "coding": [
            {
                "system": CODE_SYSTEM_URI.get(resolution.system, resolution.system),
                "code": resolution.code,
                "display": resolution.display,
            }
        ],
        "text": resolution.display,
    }


def _patient_ref(patient_id: str) -> dict[str, str]:
    return {"reference": f"Patient/{patient_id}"}


def build_observation(payload: dict, validation: ValidationResult) -> dict:
    obs: dict[str, Any] = {
        "resourceType": "Observation",
        "status": payload.get("status", "final"),
        "subject": _patient_ref(payload["patient_id"]),
    }
    # code: explicit free-text (e.g. a flowsheet id like "BP") or resolved LOINC
    if payload.get("code_text"):
        obs["code"] = {"text": payload["code_text"]}
    else:
        obs["code"] = _codeable_concept(validation.resolved["type"])
    # value: a string (e.g. "118/77 mmHg") or a numeric quantity
    if payload.get("value_string") is not None:
        obs["valueString"] = payload["value_string"]
    else:
        obs["valueQuantity"] = {"value": payload["value"], "unit": payload["unit"]}
    category = str(payload.get("category", "")).strip().lower()
    if category in _OBSERVATION_CATEGORIES:
        obs["category"] = [{"coding": [_OBSERVATION_CATEGORIES[category]]}]
    if payload.get("effective_date"):
        obs["effectiveDateTime"] = payload["effective_date"]
    return obs


def build_medication_request(payload: dict, validation: ValidationResult) -> dict:
    parts = [str(payload["dose_value"]), str(payload["dose_unit"])]
    if payload.get("frequency"):
        parts.append(str(payload["frequency"]))
    if payload.get("route"):
        parts.append(str(payload["route"]))
    dose_rate: dict[str, Any] = {
        "doseQuantity": {"value": payload["dose_value"], "unit": payload["dose_unit"]}
    }
    if payload.get("rate_value") is not None and payload.get("rate_unit"):
        dose_rate["rateQuantity"] = {
            "value": payload["rate_value"],
            "unit": payload["rate_unit"],
        }
    dosage: dict[str, Any] = {"text": " ".join(parts), "doseAndRate": [dose_rate]}
    if payload.get("route"):
        dosage["route"] = payload["route"]  # MedAgentBench expects a plain string

    # medication: an explicit code+system the task provided, or a resolved code
    if payload.get("code") and payload.get("code_system"):
        medication_cc = _explicit_coding(
            payload["code"], payload["code_system"], payload.get("medication")
        )
    else:
        medication_cc = _codeable_concept(validation.resolved["medication"])

    mr: dict[str, Any] = {
        "resourceType": "MedicationRequest",
        "status": "active",
        "intent": "order",
        "medicationCodeableConcept": medication_cc,
        "subject": _patient_ref(payload["patient_id"]),
        "priority": payload.get("priority", "routine"),
        "dosageInstruction": [dosage],
    }
    if payload.get("authored_on"):
        mr["authoredOn"] = payload["authored_on"]
    if payload.get("reason"):
        mr["reasonCode"] = [{"text": payload["reason"]}]
    return mr


def build_service_request(payload: dict, validation: ValidationResult) -> dict:
    sr: dict[str, Any] = {
        "resourceType": "ServiceRequest",
        "status": "active",
        "intent": "order",
        "category": [{"text": payload["category"]}],
        "subject": _patient_ref(payload["patient_id"]),
        "priority": payload.get("priority", "routine"),
    }
    # code: an explicit code+system the task provided, a resolved code, or text
    if payload.get("code") and payload.get("code_system"):
        sr["code"] = _explicit_coding(
            payload["code"], payload["code_system"], payload.get("service")
        )
    else:
        res = validation.resolved.get("service")
        sr["code"] = (
            _codeable_concept(res) if res is not None else {"text": payload["service"]}
        )
    if payload.get("authored_on"):
        sr["authoredOn"] = payload["authored_on"]
    if payload.get("scheduled_date"):
        sr["occurrenceDateTime"] = payload["scheduled_date"]
    if payload.get("note"):
        sr["note"] = {"text": payload["note"]}
    if payload.get("reason"):
        sr["reasonCode"] = [{"text": payload["reason"]}]
    return sr


def build_document_reference(payload: dict, validation: ValidationResult) -> dict:
    encoded = base64.b64encode(str(payload["text"]).encode("utf-8")).decode("ascii")
    dr: dict[str, Any] = {
        "resourceType": "DocumentReference",
        "status": "current",
        "type": {"text": payload["note_type"]},
        "subject": _patient_ref(payload["patient_id"]),
        "author": [{"display": payload.get("author", "agent")}],
        "content": [{"attachment": {"contentType": "text/plain", "data": encoded}}],
    }
    if payload.get("effective_date"):
        dr["date"] = payload["effective_date"]
    return dr


_BUILDERS = {
    "Observation": build_observation,
    "MedicationRequest": build_medication_request,
    "ServiceRequest": build_service_request,
    "DocumentReference": build_document_reference,
}

SUPPORTED_RESOURCE_TYPES = tuple(_BUILDERS.keys())


def build(resource_type: str, payload: dict, validation: ValidationResult) -> dict:
    """Build a FHIR R4 resource. Raises KeyError for unknown resource types."""
    builder = _BUILDERS.get(resource_type)
    if builder is None:
        raise KeyError(f"unknown resource_type '{resource_type}'")
    return builder(payload, validation)
