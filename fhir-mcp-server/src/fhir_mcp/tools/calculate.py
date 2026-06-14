"""Calculation tools: calculate_clinical_value."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..calc.formulas import FormulaError, available_formulas, compute
from ..envelope import err, ok
from ..services import Services


def register(mcp: FastMCP, services: Services) -> None:
    @mcp.tool()
    def calculate_clinical_value(formula: str, inputs: dict) -> dict:
        """Compute a clinical value with a deterministic formula (no LLM involved).

        Args:
            formula: One of BMI, BSA, CrCl_Cockcroft-Gault, eGFR_CKD-EPI.
            inputs: Formula-specific inputs, e.g.
                {"weight_kg": 68, "height_cm": 165} for BMI.
        """
        try:
            result = compute(formula, inputs)
        except FormulaError as exc:
            return err(
                f"calculation failed: {exc}. "
                f"Available formulas: {', '.join(available_formulas())}"
            )
        return ok({"formula": formula, **result, "inputs_used": inputs})
