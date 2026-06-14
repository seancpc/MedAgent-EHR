"""In-memory staging store for two-phase writes.

A write is never executed directly. It is first *staged* (validated, previewed,
no side effects), then *committed*. Each staged write carries an idempotency
hash so re-staging or re-committing the same draft does nothing.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


def idempotency_hash(resource_type: str, payload: dict[str, Any]) -> str:
    """Stable SHA-256 hash of a write, used to detect duplicate stage/commit."""
    blob = json.dumps(
        {"resource_type": resource_type, "payload": payload},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass
class StagedWrite:
    """A validated, not-yet-committed write."""

    staged_id: str
    resource_type: str
    payload: dict[str, Any]
    preview: str
    warnings: list[str]
    idem_hash: str
    created_at: float = field(default_factory=time.time)
    committed: bool = False
    committed_resource_id: str | None = None

    def summary(self) -> dict[str, Any]:
        """Compact dict describing this staged write (for tool output).

        Includes the built `fhir_resource` so the agent can see exactly what it
        staged, and so the Verifier can check actual content (note text,
        priority, codes) — the one-line `preview` alone hides those fields and
        caused the Verifier to reject content-rich writes it could not see.
        """
        return {
            "staged_id": self.staged_id,
            "resource_type": self.resource_type,
            "preview": self.preview,
            "fhir_resource": self.payload.get("_fhir"),
            "validation": "passed",
            "warnings": self.warnings,
            "idempotency_hash": self.idem_hash,
            "committed": self.committed,
        }


class StagingStore:
    """Holds staged writes for the lifetime of the server process."""

    def __init__(self) -> None:
        self._by_id: dict[str, StagedWrite] = {}
        self._by_hash: dict[str, str] = {}  # idem_hash -> staged_id

    def stage(
        self,
        resource_type: str,
        payload: dict[str, Any],
        preview: str,
        warnings: list[str] | None = None,
    ) -> StagedWrite:
        """Create — or return the existing — staged write for this payload."""
        idem = idempotency_hash(resource_type, payload)
        existing_id = self._by_hash.get(idem)
        if existing_id is not None:
            return self._by_id[existing_id]

        staged = StagedWrite(
            staged_id=f"stg_{uuid.uuid4().hex[:8]}",
            resource_type=resource_type,
            payload=payload,
            preview=preview,
            warnings=warnings or [],
            idem_hash=idem,
        )
        self._by_id[staged.staged_id] = staged
        self._by_hash[idem] = staged.staged_id
        return staged

    def get(self, staged_id: str) -> StagedWrite | None:
        return self._by_id.get(staged_id)

    def list_pending(self) -> list[StagedWrite]:
        """All staged writes not yet committed."""
        return [s for s in self._by_id.values() if not s.committed]

    def mark_committed(self, staged_id: str, resource_id: str) -> None:
        staged = self._by_id.get(staged_id)
        if staged is not None:
            staged.committed = True
            staged.committed_resource_id = resource_id

    def discard(self, staged_id: str) -> bool:
        """Remove a staged write. Returns True if it existed."""
        staged = self._by_id.pop(staged_id, None)
        if staged is None:
            return False
        self._by_hash.pop(staged.idem_hash, None)
        return True
