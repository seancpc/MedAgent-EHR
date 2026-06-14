"""Coding tools: resolve_code."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..coding.resolver import resolve
from ..envelope import err, ok
from ..services import Services


def register(mcp: FastMCP, services: Services) -> None:
    @mcp.tool()
    def resolve_code(term: str, system: str) -> dict:
        """Resolve a human medical term to a formal code.

        Args:
            term: Human term, e.g. "HbA1c" or "Metformin".
            system: One of LOINC, RxNorm, SNOMED, ICD-10.
        """
        table = services.code_tables.get(system)
        if table is None:
            return err(
                f"unknown code system '{system}'. "
                f"Available: {', '.join(sorted(services.code_tables))}"
            )
        res = resolve(term, table)
        if not res.resolved:
            return err(
                f"could not resolve '{term}' in {system}. "
                f"Try a more standard term, or check the system name."
            )
        return ok(
            {
                "term": res.term,
                "system": res.system,
                "code": res.code,
                "display": res.display,
                "match_method": res.match_method,
                "confidence": res.confidence,
            }
        )
