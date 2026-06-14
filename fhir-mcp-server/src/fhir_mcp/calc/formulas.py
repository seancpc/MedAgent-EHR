"""Deterministic clinical calculation formulas.

These are pure functions — no LLM is involved — so numerical answers are exact
and reproducible. `calculate_clinical_value` (tools/calculate.py) dispatches to
the FORMULAS registry below.

Implementations are written from scratch from standard, publicly documented
clinical equations.
"""
from __future__ import annotations

from typing import Any, Callable


class FormulaError(ValueError):
    """Raised when inputs to a formula are missing or out of range."""


def _require(inputs: dict[str, Any], *keys: str) -> list[Any]:
    """Return the listed input values, raising FormulaError if any is missing."""
    missing = [k for k in keys if inputs.get(k) is None]
    if missing:
        raise FormulaError(f"missing required input(s): {', '.join(missing)}")
    return [inputs[k] for k in keys]


def bmi(inputs: dict[str, Any]) -> dict[str, Any]:
    """Body Mass Index. Inputs: weight_kg, height_cm."""
    weight_kg, height_cm = _require(inputs, "weight_kg", "height_cm")
    if height_cm <= 0:
        raise FormulaError("height_cm must be positive")
    height_m = height_cm / 100.0
    return {"result": round(weight_kg / (height_m ** 2), 1), "unit": "kg/m2"}


def bsa(inputs: dict[str, Any]) -> dict[str, Any]:
    """Body Surface Area (Mosteller). Inputs: weight_kg, height_cm."""
    weight_kg, height_cm = _require(inputs, "weight_kg", "height_cm")
    if weight_kg <= 0 or height_cm <= 0:
        raise FormulaError("weight_kg and height_cm must be positive")
    return {"result": round(((height_cm * weight_kg) / 3600.0) ** 0.5, 2), "unit": "m2"}


def crcl_cockcroft_gault(inputs: dict[str, Any]) -> dict[str, Any]:
    """Creatinine Clearance (Cockcroft-Gault).

    Inputs: age (years), weight_kg, creatinine (mg/dL), gender ('male'/'female').
    """
    age, weight_kg, creatinine, gender = _require(
        inputs, "age", "weight_kg", "creatinine", "gender"
    )
    if creatinine <= 0:
        raise FormulaError("creatinine must be positive")
    sex_factor = 0.85 if str(gender).lower().startswith("f") else 1.0
    value = ((140 - age) * weight_kg * sex_factor) / (72 * creatinine)
    return {"result": round(value, 1), "unit": "mL/min"}


def egfr_ckd_epi(inputs: dict[str, Any]) -> dict[str, Any]:
    """eGFR — 2021 CKD-EPI creatinine equation (race-free).

    Inputs: creatinine (mg/dL), age (years), gender ('male'/'female').
    """
    creatinine, age, gender = _require(inputs, "creatinine", "age", "gender")
    if creatinine <= 0:
        raise FormulaError("creatinine must be positive")
    is_female = str(gender).lower().startswith("f")
    kappa = 0.7 if is_female else 0.9
    alpha = -0.241 if is_female else -0.302
    ratio = creatinine / kappa
    value = (
        142
        * (min(ratio, 1.0) ** alpha)
        * (max(ratio, 1.0) ** -1.200)
        * (0.9938 ** age)
        * (1.012 if is_female else 1.0)
    )
    return {"result": round(value, 1), "unit": "mL/min/1.73m2"}


# Registry: formula name -> (function, human description).
FORMULAS: dict[str, tuple[Callable[[dict[str, Any]], dict[str, Any]], str]] = {
    "BMI": (bmi, "Body Mass Index from weight_kg and height_cm"),
    "BSA": (bsa, "Body Surface Area (Mosteller) from weight_kg and height_cm"),
    "CrCl_Cockcroft-Gault": (
        crcl_cockcroft_gault,
        "Creatinine clearance from age, weight_kg, creatinine, gender",
    ),
    "eGFR_CKD-EPI": (
        egfr_ckd_epi,
        "eGFR (2021 race-free CKD-EPI) from creatinine, age, gender",
    ),
}


def available_formulas() -> dict[str, str]:
    """Return {formula_name: description} for all supported formulas."""
    return {name: desc for name, (_fn, desc) in FORMULAS.items()}


def compute(formula: str, inputs: dict[str, Any]) -> dict[str, Any]:
    """Dispatch to a formula by name. Raises FormulaError for unknown names."""
    entry = FORMULAS.get(formula)
    if entry is None:
        raise FormulaError(
            f"unknown formula '{formula}'. Available: {', '.join(FORMULAS)}"
        )
    fn, _desc = entry
    return fn(inputs)
