"""Write tools: stage_write, commit_write, list_staged_writes, discard_write.

Writes are two-phase: stage_write validates and previews with NO side effects;
commit_write performs the actual FHIR POST. This split lets a verifier review
the staged draft before it is committed.
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..envelope import err, ok
from ..fhir_client import FhirError
from ..services import Services
from ..writes import builders, validators


def register(mcp: FastMCP, services: Services) -> None:
    @mcp.tool()
    def stage_write(resource_type: str, payload: dict) -> dict:
        """Validate and stage a write. NO side effects — does not commit.

        The `payload` is a FLAT object with plain string/number fields — NOT a
        nested FHIR resource. Do NOT wrap codes in {"coding":[...]}. Medical
        terms like "HbA1c" or "Metformin" are resolved to LOINC/RxNorm codes
        internally; just pass the plain term. `category` is a plain string.

        IMPORTANT: if the task already gives you a specific code, time, or value,
        use it VERBATIM (do not re-derive it):
          - a given code  -> pass `code` + `code_system` (e.g. "NDC", "SNOMED",
            "LOINC"); this is used as-is and skips internal resolution.
          - a given "current time" -> pass it as effective_date / authored_on
            with the FULL timestamp exactly as written (e.g.
            "2023-11-13T10:15:00+00:00").
          - a non-numeric value (e.g. a blood pressure "118/77 mmHg") -> pass
            `value_string`; a flowsheet id (e.g. "BP") -> pass `code_text`.

        Required + optional fields and one example payload per resource_type:

        Observation — record one measurement / vital / lab value:
          Required: patient_id; AND (type + value + unit) OR
                    (code_text/type + value_string)
          Optional: value_string (non-numeric value), code_text (free-text/
                    flowsheet code, skips LOINC resolution), category (e.g.
                    "vital-signs"), effective_date (full timestamp ok),
                    status (default "final")
          Example (numeric): {"patient_id": "7601", "type": "HbA1c",
            "value": 7.2, "unit": "%"}
          Example (BP string): {"patient_id": "S2380121", "code_text": "BP",
            "value_string": "118/77 mmHg", "category": "vital-signs",
            "effective_date": "2023-11-13T10:15:00+00:00"}

        MedicationRequest — prescribe or order a medication:
          Required: patient_id, dose_value, dose_unit, AND
                    (medication OR code + code_system)
          Optional: code + code_system (use a given drug code verbatim, e.g.
                    NDC), route (plain string, e.g. "IV" / "oral"),
                    rate_value + rate_unit (infusion rate, e.g. 2 + "h"),
                    frequency, authored_on, reason, priority (default "routine")
          Example (oral): {"patient_id": "7601", "medication": "Metformin",
            "dose_value": 500, "dose_unit": "mg", "frequency": "BID"}
          Example (IV infusion, given NDC): {"patient_id": "S6315806",
            "medication": "magnesium sulfate", "code": "0338-1715-40",
            "code_system": "NDC", "dose_value": 2, "dose_unit": "g",
            "route": "IV", "rate_value": 2, "rate_unit": "h",
            "authored_on": "2023-11-13T10:15:00+00:00"}

        ServiceRequest — order a lab test / imaging / referral:
          Required: patient_id, category, AND (service OR code + code_system)
          Optional: code + code_system (use a given code verbatim),
                    authored_on, note (free-text), reason, scheduled_date,
                    priority — when placing an order/referral to fulfil a
                    task, use "stat" UNLESS the task explicitly says routine /
                    non-urgent (bare default is "routine")
          `category` MUST be one of: "laboratory" | "imaging" | "referral" —
          as a plain string, NOT a coding object.
          Example (given code): {"patient_id": "S2016972",
            "category": "referral", "code": "306181000000106",
            "code_system": "SNOMED", "priority": "stat",
            "authored_on": "2023-11-13T10:15:00+00:00",
            "note": "Situation: ... Recommendation: ..."}

        DocumentReference — add a free-text clinical note:
          Required: patient_id, note_type, text
          Optional: author (default "agent"), effective_date (default today)
          Example payload:
            {"patient_id": "7601", "note_type": "progress note",
             "text": "Patient reports improved glucose control."}

        Returns a staged_id; the system commits automatically via commit_write
        after the Verifier approves.
        """
        result = validators.validate(resource_type, payload, services.code_tables)
        if not result.ok:
            return err("stage_write rejected: " + "; ".join(result.errors))
        try:
            fhir_resource = builders.build(resource_type, payload, result)
        except KeyError as exc:
            return err(f"stage_write failed: {exc}")
        staged = services.staging.stage(
            resource_type=resource_type,
            payload={"_fhir": fhir_resource, "_input": payload},
            preview=result.preview,
            warnings=result.warnings,
        )
        return ok(staged.summary())

    @mcp.tool()
    def commit_write(staged_id: str) -> dict:
        """Commit a previously staged write to the FHIR server.

        Idempotent: committing the same staged_id twice does not create a
        duplicate resource.
        """
        staged = services.staging.get(staged_id)
        if staged is None:
            return err(f"no staged write with id '{staged_id}'")
        if staged.committed:
            return ok(
                {
                    "staged_id": staged_id,
                    "committed": True,
                    "fhir_resource_id": staged.committed_resource_id,
                    "fhir_resource": staged.payload["_fhir"],
                    "note": "already committed (idempotent no-op)",
                }
            )
        try:
            created = services.fhir().create(
                staged.resource_type, staged.payload["_fhir"]
            )
        except FhirError as exc:
            return err(str(exc))
        resource_id = f"{staged.resource_type}/{created.get('id')}"
        services.staging.mark_committed(staged_id, resource_id)
        return ok(
            {
                "staged_id": staged_id,
                "committed": True,
                "fhir_resource_id": resource_id,
                "fhir_resource": staged.payload["_fhir"],
            }
        )

    @mcp.tool()
    def list_staged_writes(patient_id: str | None = None) -> dict:
        """List staged writes not yet committed, optionally filtered by patient."""
        pending = services.staging.list_pending()
        if patient_id:
            pending = [
                s
                for s in pending
                if s.payload.get("_input", {}).get("patient_id") == patient_id
            ]
        return ok(
            {"staged_writes": [s.summary() for s in pending], "count": len(pending)}
        )

    @mcp.tool()
    def discard_write(staged_id: str) -> dict:
        """Discard a staged write without committing it."""
        if services.staging.discard(staged_id):
            return ok({"staged_id": staged_id, "discarded": True})
        return err(f"no staged write with id '{staged_id}'")
