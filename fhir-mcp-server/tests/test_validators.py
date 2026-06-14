"""Unit tests for write validators."""
from fhir_mcp.coding.tables.seed import load_seed_tables
from fhir_mcp.writes.validators import validate

TABLES = load_seed_tables()


def test_observation_valid():
    result = validate(
        "Observation",
        {"patient_id": "P1", "type": "body weight", "value": 68.5, "unit": "kg"},
        TABLES,
    )
    assert result.ok
    assert "type" in result.resolved


def test_observation_missing_field():
    result = validate(
        "Observation", {"patient_id": "P1", "type": "body weight"}, TABLES
    )
    assert not result.ok


def test_observation_out_of_range():
    result = validate(
        "Observation",
        {"patient_id": "P1", "type": "body weight", "value": 9000, "unit": "kg"},
        TABLES,
    )
    assert not result.ok


def test_medication_dose_exceeds_max():
    result = validate(
        "MedicationRequest",
        {
            "patient_id": "P1",
            "medication": "Metformin",
            "dose_value": 5000,
            "dose_unit": "mg",
            "frequency": "BID",
        },
        TABLES,
    )
    assert not result.ok
    assert "exceeds" in result.errors[0]


def test_medication_valid():
    result = validate(
        "MedicationRequest",
        {
            "patient_id": "P1",
            "medication": "Metformin",
            "dose_value": 500,
            "dose_unit": "mg",
            "frequency": "BID",
        },
        TABLES,
    )
    assert result.ok


def test_service_request_bad_category():
    result = validate(
        "ServiceRequest",
        {"patient_id": "P1", "service": "HbA1c", "category": "banana"},
        TABLES,
    )
    assert not result.ok


def test_unknown_resource_type():
    result = validate("Foo", {}, TABLES)
    assert not result.ok
