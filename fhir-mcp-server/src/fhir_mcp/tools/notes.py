"""Clinical notes tool: search_clinical_notes (BM25 lexical ranking)."""
from __future__ import annotations

import base64

from mcp.server.fastmcp import FastMCP
from rank_bm25 import BM25Okapi

from ..envelope import err, ok
from ..fhir_client import FhirError
from ..services import Services


def _tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric tokenization for BM25."""
    return "".join(c.lower() if c.isalnum() else " " for c in text).split()


def _note_text(doc: dict) -> str:
    """Decode the text body of a FHIR DocumentReference, if present."""
    for content in doc.get("content", []):
        data = content.get("attachment", {}).get("data")
        if data:
            try:
                return base64.b64decode(data).decode("utf-8", errors="replace")
            except (ValueError, UnicodeDecodeError):
                continue
    return ""


def register(mcp: FastMCP, services: Services) -> None:
    @mcp.tool()
    def search_clinical_notes(
        patient_id: str, query: str, max_results: int = 5
    ) -> dict:
        """Search a patient's free-text clinical notes for the most relevant ones.

        Uses BM25 lexical ranking over the patient's DocumentReference notes.

        Args:
            patient_id: FHIR patient id.
            query: what to look for, in natural language.
            max_results: number of notes to return (default 5).
        """
        try:
            docs = services.fhir().search(
                "DocumentReference", {"patient": patient_id}, max_results=500
            )
        except FhirError as exc:
            return err(str(exc))

        notes = [(doc, text) for doc in docs if (text := _note_text(doc)).strip()]
        if not notes:
            return ok({"query": query, "results": [], "count": 0})

        bm25 = BM25Okapi([_tokenize(text) for _doc, text in notes])
        scores = bm25.get_scores(_tokenize(query))
        ranked = sorted(zip(notes, scores), key=lambda x: x[1], reverse=True)

        results = [
            {
                "document_id": doc.get("id"),
                "date": doc.get("date"),
                "score": round(float(score), 3),
                "excerpt": text[:500],
            }
            for (doc, text), score in ranked[:max_results]
        ]
        return ok({"query": query, "results": results, "count": len(results)})
