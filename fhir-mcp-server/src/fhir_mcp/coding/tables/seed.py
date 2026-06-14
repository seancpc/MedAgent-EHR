"""Seed medical code tables (LOINC / RxNorm / SNOMED CT / ICD-10-CM).

================================  WARNING  ================================
 PROVISIONAL DATA — HAND-BUILT v1 SEED SET.
 These are a few dozen common codes, transcribed from public references so the
 resolver can run end-to-end. They MUST be verified against official sources
 (loinc.org, RxNav/RxNorm, the SNOMED CT browser, ICD-10-CM) and expanded
 before any real use. Codes are NOT guaranteed correct.
===========================================================================

Each row: (code, display, *aliases). Matching is case-insensitive and
whitespace-normalized by the resolver, so aliases can be written plainly.
"""
from __future__ import annotations

from ..resolver import CodeEntry, CodeTable

_LOINC: list[tuple] = [
    ("4548-4", "Hemoglobin A1c", "hba1c", "a1c", "glycated hemoglobin"),
    ("2339-0", "Glucose", "blood glucose", "glucose level"),
    ("2160-0", "Creatinine", "serum creatinine", "creatinine level"),
    ("29463-7", "Body weight", "weight"),
    ("8302-2", "Body height", "height"),
    ("39156-5", "Body mass index", "bmi"),
    ("8480-6", "Systolic blood pressure", "systolic bp", "sbp"),
    ("8462-4", "Diastolic blood pressure", "diastolic bp", "dbp"),
    ("8867-4", "Heart rate", "pulse", "pulse rate"),
    ("8310-5", "Body temperature", "temperature"),
    ("9279-1", "Respiratory rate", "resp rate"),
    ("2708-6", "Oxygen saturation", "o2 sat", "spo2"),
    ("2823-3", "Potassium", "serum potassium"),
    ("2951-2", "Sodium", "serum sodium"),
    ("718-7", "Hemoglobin", "hgb", "hb"),
    ("2093-3", "Total cholesterol", "cholesterol"),
    ("13457-7", "LDL cholesterol", "ldl"),
    ("1742-6", "Alanine aminotransferase", "alt"),
    ("1920-8", "Aspartate aminotransferase", "ast"),
    ("3016-3", "Thyroid stimulating hormone", "tsh"),
]

_RXNORM: list[tuple] = [
    ("6809", "Metformin", "metformin hcl"),
    ("29046", "Lisinopril"),
    ("83367", "Atorvastatin"),
    ("1191", "Aspirin", "asa"),
    ("17767", "Amlodipine"),
    ("6918", "Metoprolol"),
    ("11289", "Warfarin"),
    ("4603", "Furosemide"),
    ("10582", "Levothyroxine"),
    ("7646", "Omeprazole"),
    ("5487", "Hydrochlorothiazide", "hctz"),
    ("52175", "Losartan"),
    ("25480", "Gabapentin"),
    ("435", "Albuterol", "salbutamol"),
    ("274783", "Insulin glargine"),
]

_SNOMED: list[tuple] = [
    ("44054006", "Type 2 diabetes mellitus", "t2dm", "diabetes type 2"),
    ("59621000", "Essential hypertension", "hypertension", "high blood pressure"),
    ("55822004", "Hyperlipidemia", "high cholesterol"),
    ("195967001", "Asthma"),
    ("49436004", "Atrial fibrillation", "afib"),
    ("709044004", "Chronic kidney disease", "ckd"),
    ("84114007", "Heart failure", "congestive heart failure"),
    ("13645005", "Chronic obstructive pulmonary disease", "copd"),
]

_ICD10: list[tuple] = [
    ("E11.9", "Type 2 diabetes mellitus without complications", "type 2 diabetes"),
    ("I10", "Essential (primary) hypertension", "hypertension"),
    ("E78.5", "Hyperlipidemia, unspecified", "hyperlipidemia"),
    ("J45.909", "Unspecified asthma, uncomplicated", "asthma"),
    ("I48.91", "Unspecified atrial fibrillation", "atrial fibrillation"),
    ("N18.30", "Chronic kidney disease, stage 3 unspecified", "ckd stage 3"),
    ("I50.9", "Heart failure, unspecified", "heart failure"),
    ("J44.9", "Chronic obstructive pulmonary disease, unspecified", "copd"),
]


def _table(system: str, rows: list[tuple]) -> CodeTable:
    entries = [CodeEntry(code=r[0], display=r[1], aliases=tuple(r[2:])) for r in rows]
    return CodeTable(system=system, entries=entries)


def load_seed_tables() -> dict[str, CodeTable]:
    """Return {system_name: CodeTable} for all seed code systems."""
    return {
        "LOINC": _table("LOINC", _LOINC),
        "RxNorm": _table("RxNorm", _RXNORM),
        "SNOMED": _table("SNOMED", _SNOMED),
        "ICD-10": _table("ICD-10", _ICD10),
    }
