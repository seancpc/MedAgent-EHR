"""Patient tools: find_patient, get_patient_summary."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..envelope import err, ok
from ..fhir_client import FhirError
from ..services import Services
from ._helpers import concept_text, patient_brief


def register(mcp: FastMCP, services: Services) -> None:
    @mcp.tool()
    def find_patient(
        identifier: str | None = None,
        name: str | None = None,
        family: str | None = None,
        given: str | None = None,
        birth_date: str | None = None,
    ) -> dict:
        """Find patients by identifier, name parts, and/or birth date.

        Provide at least one argument. For a multi-word name like
        "Darrell400 Ondricka197" prefer the precise `family` (surname) and
        `given` (first name) parameters — FHIR's `name` parameter matches a
        single starts-with token across all name fields and will MISS a
        "Given Family" two-word query.

        birth_date format: YYYY-MM-DD.
        """
        params: dict = {}
        if identifier:
            params["identifier"] = identifier
        if name:
            params["name"] = name
        if family:
            params["family"] = family
        if given:
            params["given"] = given
        if birth_date:
            params["birthdate"] = birth_date
        if not params:
            return err(
                "provide at least one of: identifier, name, family, given, birth_date"
            )
        try:
            resources = services.fhir().search("Patient", params, max_results=20)
        except FhirError as exc:
            return err(str(exc))
        matches = [patient_brief(r) for r in resources]
        return ok({"matches": matches, "match_count": len(matches)})

    @mcp.tool()
    def get_patient_summary(patient_id: str) -> dict:
        """Get a compact snapshot of one patient.

        Returns demographics plus active problems and active medications.
        """
        try:
            fhir = services.fhir()
            patient = fhir.read("Patient", patient_id)
            conditions = fhir.search(
                "Condition",
                {"patient": patient_id, "clinical-status": "active"},
                max_results=50,
            )
            meds = fhir.search(
                "MedicationRequest",
                {"patient": patient_id, "status": "active"},
                max_results=50,
            )
        except FhirError as exc:
            return err(str(exc))
        summary = patient_brief(patient)
        summary["active_conditions"] = [concept_text(c.get("code")) for c in conditions]
        summary["active_medications"] = [
            concept_text(m.get("medicationCodeableConcept")) for m in meds
        ]
        return ok(summary)
