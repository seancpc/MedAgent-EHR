"""Unit tests for clinical calculation formulas."""
import pytest

from fhir_mcp.calc.formulas import FormulaError, compute


def test_bmi():
    result = compute("BMI", {"weight_kg": 68, "height_cm": 165})
    assert result["unit"] == "kg/m2"
    assert result["result"] == 25.0


def test_egfr_ckd_epi_runs():
    result = compute(
        "eGFR_CKD-EPI", {"creatinine": 1.1, "age": 68, "gender": "female"}
    )
    assert result["unit"] == "mL/min/1.73m2"
    assert 0 < result["result"] < 200


def test_crcl():
    result = compute(
        "CrCl_Cockcroft-Gault",
        {"age": 68, "weight_kg": 68, "creatinine": 1.1, "gender": "female"},
    )
    assert result["unit"] == "mL/min"
    assert result["result"] > 0


def test_missing_input_raises():
    with pytest.raises(FormulaError):
        compute("BMI", {"weight_kg": 68})


def test_unknown_formula_raises():
    with pytest.raises(FormulaError):
        compute("NOPE", {})
