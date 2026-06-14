"""Multi-stage medical code resolver.

Given a human term (e.g. "HbA1c") and a target code system, resolve it to a
formal code by trying progressively looser matching:

    1. exact   — normalized term equals a code's display
    2. alias   — normalized term equals one of a code's aliases
    3. fuzzy   — rapidfuzz similarity at or above FUZZY_THRESHOLD

The actual code data lives in coding/tables/ (seed tables built in a later
phase) and is passed in as a CodeTable; this module is pure matching logic.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from rapidfuzz import fuzz, process

FUZZY_THRESHOLD = 85.0  # 0-100; matches at or above this are accepted


def _norm(text: str) -> str:
    """Normalize a term for matching: lowercase, collapse whitespace."""
    return " ".join(str(text).lower().split())


@dataclass(frozen=True)
class CodeEntry:
    """One code in a code system."""

    code: str
    display: str
    aliases: tuple[str, ...] = ()

    def all_terms(self) -> list[str]:
        """Display plus aliases — every string that should match this code."""
        return [self.display, *self.aliases]


@dataclass
class CodeTable:
    """A set of codes for one system (e.g. LOINC)."""

    system: str
    entries: list[CodeEntry] = field(default_factory=list)

    # built in __post_init__: normalized term -> (CodeEntry, is_display)
    _index: dict[str, tuple[CodeEntry, bool]] = field(
        default_factory=dict, init=False, repr=False
    )

    def __post_init__(self) -> None:
        for entry in self.entries:
            self._index.setdefault(_norm(entry.display), (entry, True))
            for alias in entry.aliases:
                self._index.setdefault(_norm(alias), (entry, False))

    def exact(self, term: str) -> tuple[CodeEntry, bool] | None:
        """Return (entry, is_display) for an exact display/alias match, else None."""
        return self._index.get(_norm(term))

    def fuzzy(self, term: str) -> tuple[CodeEntry | None, float]:
        """Best fuzzy match and its score (0-100)."""
        if not self._index:
            return None, 0.0
        match = process.extractOne(
            _norm(term), list(self._index.keys()), scorer=fuzz.WRatio
        )
        if match is None:
            return None, 0.0
        matched_term, score, _ = match
        entry, _is_display = self._index[matched_term]
        return entry, float(score)


@dataclass
class Resolution:
    """The outcome of resolving a term."""

    term: str
    system: str
    code: str | None
    display: str | None
    match_method: str  # "exact" | "alias" | "fuzzy" | "unresolved"
    confidence: float  # 0.0 - 1.0

    @property
    def resolved(self) -> bool:
        return self.code is not None


def resolve(term: str, table: CodeTable) -> Resolution:
    """Resolve `term` against `table` using exact -> alias -> fuzzy matching."""
    hit = table.exact(term)
    if hit is not None:
        entry, is_display = hit
        method = "exact" if is_display else "alias"
        return Resolution(term, table.system, entry.code, entry.display, method, 1.0)

    entry, score = table.fuzzy(term)
    if entry is not None and score >= FUZZY_THRESHOLD:
        return Resolution(
            term, table.system, entry.code, entry.display, "fuzzy", round(score / 100.0, 3)
        )

    return Resolution(term, table.system, None, None, "unresolved", 0.0)
