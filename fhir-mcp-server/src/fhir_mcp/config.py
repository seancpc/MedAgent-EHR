"""Configuration loading for fhir-mcp-server.

Values come from environment variables (optionally via a .env file). On
development machines the sensitive fields (FHIR_BASE_URL, FHIR_AUTH_TOKEN) are
intentionally empty; they are filled only on the target machine.

This module contains NO secret values — only the loading logic. It is identical
across all environments and safe to deploy anywhere.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    """Resolved fhir-mcp-server configuration."""

    fhir_base_url: str
    fhir_auth_token: str
    mcp_host: str
    mcp_port: int
    fhir_timeout_seconds: float

    @property
    def configured(self) -> bool:
        """True once the FHIR endpoint is set (i.e. running on a target machine)."""
        return bool(self.fhir_base_url)


def load_config() -> Config:
    """Load configuration from environment variables / .env file."""
    load_dotenv()  # no-op if there is no .env file
    return Config(
        fhir_base_url=os.getenv("FHIR_BASE_URL", "").strip(),
        fhir_auth_token=os.getenv("FHIR_AUTH_TOKEN", "").strip(),
        mcp_host=os.getenv("MCP_HOST", "127.0.0.1").strip(),
        mcp_port=int(os.getenv("MCP_PORT", "9765")),
        fhir_timeout_seconds=float(os.getenv("FHIR_TIMEOUT_SECONDS", "30")),
    )
