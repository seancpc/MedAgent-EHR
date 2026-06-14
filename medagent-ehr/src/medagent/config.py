"""Configuration loading for medagent-ehr.

Values come from environment variables (optionally via a .env file). On
development machines the sensitive fields (Ollama / MCP / Langfuse endpoints
and keys) are intentionally empty; they are filled only on the target machine.

This module contains NO secret values — only the loading logic. It is identical
across all environments and safe to deploy anywhere.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    """Resolved medagent-ehr configuration."""

    ollama_base_url: str
    ollama_model: str
    fhir_mcp_url: str
    langfuse_host: str
    langfuse_public_key: str
    langfuse_secret_key: str
    web_host: str
    web_port: int
    max_steps: int
    max_replans: int
    max_retries: int

    @property
    def llm_configured(self) -> bool:
        """True once the Ollama endpoint and model are set."""
        return bool(self.ollama_base_url and self.ollama_model)

    @property
    def mcp_configured(self) -> bool:
        """True once the fhir-mcp-server address is set."""
        return bool(self.fhir_mcp_url)

    @property
    def tracing_enabled(self) -> bool:
        """True only when all three Langfuse fields are set."""
        return bool(
            self.langfuse_host
            and self.langfuse_public_key
            and self.langfuse_secret_key
        )


def load_config() -> Config:
    """Load configuration from environment variables / .env file."""
    load_dotenv()
    return Config(
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "").strip(),
        ollama_model=os.getenv("OLLAMA_MODEL", "").strip(),
        fhir_mcp_url=os.getenv("FHIR_MCP_URL", "").strip(),
        langfuse_host=os.getenv("LANGFUSE_HOST", "").strip(),
        langfuse_public_key=os.getenv("LANGFUSE_PUBLIC_KEY", "").strip(),
        langfuse_secret_key=os.getenv("LANGFUSE_SECRET_KEY", "").strip(),
        web_host=os.getenv("WEB_HOST", "127.0.0.1").strip(),
        web_port=int(os.getenv("WEB_PORT", "9443")),
        max_steps=int(os.getenv("MAX_STEPS", "25")),
        max_replans=int(os.getenv("MAX_REPLANS", "3")),
        max_retries=int(os.getenv("MAX_RETRIES", "3")),
    )
