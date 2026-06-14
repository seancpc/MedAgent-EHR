"""Clinical data tools: get_observations, get_conditions, get_medications,
get_encounters."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..coding.resolver import resolve
from ..envelope import err, ok
from ..fhir_client import FhirError
from ..services import Services
from ._helpers import concept_text


def _observation_brief(obs: dict) -> dict:
    vq = obs.get("valueQuantity", {})
    return {
        "date": obs.get("effectiveDateTime") or obs.get("issued"),
        "value": vq.get("value"),
        "unit": vq.get("unit"),
    }


def _dosage_text(mr: dict) -> str:
    instructions = mr.get("dosageInstruction", [])
    if instructions and instructions[0].get("text"):
        return instructions[0]["text"]
    return ""


def _date_range(date_from: str | None, date_to: str | None) -> list[str]:
    dates: list[str] = []
    if date_from:
        dates.append(f"ge{date_from}")
    if date_to:
        dates.append(f"le{date_to}")
    return dates


def register(mcp: FastMCP, services: Services) -> None:
    @mcp.tool()
    def get_observations(
        patient_id: str,
        type: str | None = None,
        code: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        latest_only: bool = False,
        max_results: int = 50,
    ) -> dict:
        """Get a patient's observations (labs / vitals).

        PREFER `code`. This EHR stores observations under LOCAL flowsheet codes
        (e.g. "A1C", "GLU", "MG", "K"). When the task gives you a code — e.g.
        "the code for HbA1C is A1C" — you MUST pass it as `code` to find the
        data. Do NOT pass the term as `type` in that case: `type` resolves to a
        LOINC code that usually does NOT match this EHR's local codes and
        returns 0 results (which looks like "no data" but is a wrong query).

        Args:
            patient_id: FHIR patient id.
            code: The observation code to query VERBATIM (skips resolution) —
                use the code the task gives you. This is the reliable path.
            type: Fallback ONLY when no code is given — a human term resolved
                to a LOINC code (may not match this EHR's local data).
            date_from / date_to: optional YYYY-MM-DD range.
            latest_only: if true, return only the most recent result.
            max_results: cap on results (default 50).
        """
        if code:
            query_code = str(code)
            label = type or str(code)
        else:
            if not type:
                return err("provide either 'type' (a term to resolve) or 'code'")
            loinc = services.code_tables.get("LOINC")
            res = resolve(type, loinc) if loinc else None
            if res is None or not res.resolved:
                return err(
                    f"could not resolve observation type '{type}' to a LOINC code"
                )
            query_code = res.code
            label = type
        params: dict = {"patient": patient_id, "code": query_code}
        dates = _date_range(date_from, date_to)
        if dates:
            params["date"] = dates
        try:
            resources = services.fhir().search(
                "Observation", params, max_results=max_results
            )
        except FhirError as exc:
            return err(str(exc))
        results = [_observation_brief(o) for o in resources]
        results.sort(key=lambda r: r.get("date") or "", reverse=True)
        if latest_only:
            results = results[:1]
        return ok(
            {"type": label, "code": query_code, "results": results,
             "count": len(results)}
        )

    @mcp.tool()
    def get_conditions(patient_id: str, status: str = "active") -> dict:
        """Get a patient's conditions / problems.

        Args:
            patient_id: FHIR patient id.
            status: "active", "resolved", or "all" (default "active").
        """
        params: dict = {"patient": patient_id}
        if status != "all":
            params["clinical-status"] = status
        try:
            resources = services.fhir().search("Condition", params, max_results=100)
        except FhirError as exc:
            return err(str(exc))
        items = [
            {
                "condition": concept_text(c.get("code")),
                "clinical_status": concept_text(c.get("clinicalStatus")),
                "onset": c.get("onsetDateTime"),
            }
            for c in resources
        ]
        return ok({"conditions": items, "count": len(items)})

    @mcp.tool()
    def get_medications(patient_id: str, active_only: bool = True) -> dict:
        """Get a patient's medication requests.

        Args:
            patient_id: FHIR patient id.
            active_only: if true (default), return only active medications.
        """
        params: dict = {"patient": patient_id}
        if active_only:
            params["status"] = "active"
        try:
            resources = services.fhir().search(
                "MedicationRequest", params, max_results=100
            )
        except FhirError as exc:
            return err(str(exc))
        items = [
            {
                "medication": concept_text(m.get("medicationCodeableConcept")),
                "status": m.get("status"),
                "dosage": _dosage_text(m),
                "authored_on": m.get("authoredOn"),
            }
            for m in resources
        ]
        return ok({"medications": items, "count": len(items)})

    @mcp.tool()
    def get_encounters(
        patient_id: str,
        date_from: str | None = None,
        date_to: str | None = None,
        max_results: int = 50,
    ) -> dict:
        """Get a patient's encounters (visits).

        Args:
            patient_id: FHIR patient id.
            date_from / date_to: optional YYYY-MM-DD range.
            max_results: cap on results (default 50).
        """
        params: dict = {"patient": patient_id}
        dates = _date_range(date_from, date_to)
        if dates:
            params["date"] = dates
        try:
            resources = services.fhir().search(
                "Encounter", params, max_results=max_results
            )
        except FhirError as exc:
            return err(str(exc))
        items = []
        for e in resources:
            period = e.get("period") or {}
            types = e.get("type") or []
            items.append(
                {
                    "start": period.get("start"),
                    "end": period.get("end"),
                    "type": concept_text(types[0]) if types else "(unknown)",
                    "status": e.get("status"),
                }
            )
        items.sort(key=lambda r: r.get("start") or "", reverse=True)
        return ok({"encounters": items, "count": len(items)})
