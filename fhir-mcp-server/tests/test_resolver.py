"""Unit tests for the multi-stage code resolver."""
from fhir_mcp.coding.resolver import CodeEntry, CodeTable, resolve


def _table() -> CodeTable:
    return CodeTable(
        system="LOINC",
        entries=[
            CodeEntry(code="4548-4", display="Hemoglobin A1c", aliases=("hba1c", "a1c")),
            CodeEntry(code="2160-0", display="Creatinine"),
        ],
    )


def test_exact_match():
    res = resolve("Hemoglobin A1c", _table())
    assert res.code == "4548-4"
    assert res.match_method == "exact"
    assert res.confidence == 1.0
    assert res.resolved


def test_alias_match():
    res = resolve("HbA1c", _table())
    assert res.code == "4548-4"
    assert res.match_method == "alias"


def test_case_and_whitespace_insensitive():
    res = resolve("  hemoglobin   a1c ", _table())
    assert res.code == "4548-4"


def test_fuzzy_match():
    res = resolve("Creatnine", _table())  # deliberate typo
    assert res.code == "2160-0"
    assert res.match_method == "fuzzy"
    assert 0.0 < res.confidence < 1.0


def test_unresolved():
    res = resolve("completely unrelated term xyz", _table())
    assert not res.resolved
    assert res.match_method == "unresolved"
    assert res.code is None
