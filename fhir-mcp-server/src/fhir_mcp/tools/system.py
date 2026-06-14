"""System tools: health_check."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..envelope import err, ok
from ..fhir_client import FhirError
from ..services import Services


def register(mcp: FastMCP, services: Services) -> None:
    @mcp.tool()
    def health_check() -> dict:
        """Check that the FHIR backend is reachable and report server status.

        Use this first to confirm the environment is configured before calling
        other tools.
        """
        if not services.config.configured:
            return err(
                "FHIR backend not configured: FHIR_BASE_URL is empty. "
                "Set it in .env on the target machine."
            )
        try:
            cap = services.fhir().capability()
        except FhirError as exc:
            return err(f"FHIR backend unreachable: {exc}")
        return ok(
            {
                "fhir_status": "reachable",
                "fhir_software": cap.get("software", {}).get("name", "unknown"),
                "fhir_version": cap.get("fhirVersion", "unknown"),
                "code_systems": sorted(services.code_tables),
                "staged_writes_pending": len(services.staging.list_pending()),
            }
        )
