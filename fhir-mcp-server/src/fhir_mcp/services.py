"""Shared services container passed to every tool group.

`Services` bundles the config, the FHIR client, the staging store and the code
tables so that tool functions have a single object to depend on.
"""
from __future__ import annotations

from dataclasses import dataclass

from .coding.resolver import CodeTable
from .coding.tables.seed import load_seed_tables
from .config import Config, load_config
from .fhir_client import FhirClient
from .writes.staging import StagingStore


@dataclass
class Services:
    """Everything the tools need: config, FHIR client, staging, code tables."""

    config: Config
    staging: StagingStore
    code_tables: dict[str, CodeTable]
    _fhir: FhirClient | None = None

    def fhir(self) -> FhirClient:
        """Return the FHIR client, creating it on first use.

        Raises FhirError (from FhirClient) if FHIR_BASE_URL is not configured —
        callers should catch it and turn it into an error envelope.
        """
        if self._fhir is None:
            self._fhir = FhirClient(
                base_url=self.config.fhir_base_url,
                auth_token=self.config.fhir_auth_token,
                timeout_seconds=self.config.fhir_timeout_seconds,
            )
        return self._fhir

    def close(self) -> None:
        if self._fhir is not None:
            self._fhir.close()
            self._fhir = None


def build_services() -> Services:
    """Construct Services from environment configuration."""
    return Services(
        config=load_config(),
        staging=StagingStore(),
        code_tables=load_seed_tables(),
    )
