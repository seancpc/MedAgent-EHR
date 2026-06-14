"""Smoke test for fhir-mcp-server dependencies.

Exercises the building blocks the MCP tools rely on — config, the code
resolver, the calculators, and FHIR connectivity — against a real (running)
FHIR server. This confirms the environment is wired correctly; full MCP-level
testing happens when the agent connects to the server.

Usage (on the target machine, with the FHIR server running and .env filled):
    python scripts/smoke_test.py
"""
from __future__ import annotations

import sys

from fhir_mcp.calc.formulas import compute
from fhir_mcp.coding.resolver import resolve
from fhir_mcp.fhir_client import FhirError
from fhir_mcp.services import build_services


def main() -> int:
    services = build_services()
    print(f"config.configured = {services.config.configured}")

    # 1. code resolver
    res = resolve("HbA1c", services.code_tables["LOINC"])
    print(f"resolve_code('HbA1c', LOINC) -> {res.code} ({res.match_method})")
    assert res.resolved, "resolver failed on a seed term"

    # 2. calculator
    bmi = compute("BMI", {"weight_kg": 68, "height_cm": 165})
    print(f"calculate BMI -> {bmi['result']} {bmi['unit']}")

    # 3. FHIR connectivity
    if not services.config.configured:
        print("FHIR not configured (FHIR_BASE_URL empty) — skipping FHIR checks.")
        return 0
    try:
        cap = services.fhir().capability()
        print(f"FHIR reachable: version {cap.get('fhirVersion', 'unknown')}")
        patients = services.fhir().search("Patient", {}, max_results=1)
        print(f"Patient search returned {len(patients)} record(s).")
    except FhirError as exc:
        print(f"FHIR check FAILED: {exc}", file=sys.stderr)
        return 1
    finally:
        services.close()

    print("smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
