"""Unit tests for error-recovery classification."""
from medagent.agent.recovery import classify_error, recovery_hint


def test_classify_code_resolution():
    assert classify_error("could not resolve 'X' to a LOINC code") == "code_resolution"


def test_classify_validation():
    assert classify_error("dose exceeds the plausible maximum") == "validation"


def test_classify_transient():
    assert classify_error("FHIR request failed after 3 attempts") == "transient"


def test_classify_empty_result():
    assert classify_error("Patient/X not found") == "empty_result"


def test_classify_unknown():
    assert classify_error("some unexpected wording") == "unknown"


def test_recovery_hint_is_non_empty():
    assert recovery_hint("could not resolve foo") != ""
