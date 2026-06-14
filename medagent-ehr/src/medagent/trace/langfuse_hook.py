"""Langfuse tracing wrapper for medagent-ehr.

A thin, DEFENSIVE wrapper over the Langfuse v3 Python SDK. Tracing must never
break the agent: when Langfuse is not configured, or if any Langfuse call
raises, the wrapper silently falls back to no-ops.

The Langfuse v3 SDK is OpenTelemetry-based, so spans/generations created within
a `span()`/`generation()` context nest automatically under the active context.

NOTE: verify the exact Langfuse v3 method names against the installed SDK on
first run — the tracing API has shifted across Langfuse versions. Because every
call here is wrapped in try/except, a signature mismatch degrades to "no trace"
rather than crashing the agent.
"""
from __future__ import annotations

import contextlib
import logging
from typing import Any, Iterator

from ..config import Config

logger = logging.getLogger("medagent.trace")


class _NullSpan:
    """Stand-in observation handle used when tracing is off or a call fails."""

    def update(self, **kwargs: Any) -> None:  # noqa: D102
        pass


class Tracer:
    """Defensive Langfuse v3 wrapper. Every method degrades to a no-op on failure."""

    def __init__(self, config: Config) -> None:
        self._client: Any = None
        if not config.tracing_enabled:
            logger.info("Langfuse tracing disabled (no credentials).")
            return
        try:
            from langfuse import Langfuse

            self._client = Langfuse(
                host=config.langfuse_host,
                public_key=config.langfuse_public_key,
                secret_key=config.langfuse_secret_key,
            )
            logger.info("Langfuse tracing enabled.")
        except Exception as exc:  # pragma: no cover - depends on environment
            logger.warning("Langfuse init failed; tracing disabled: %s", exc)
            self._client = None

    @property
    def enabled(self) -> bool:
        return self._client is not None

    @contextlib.contextmanager
    def span(self, name: str, **kwargs: Any) -> Iterator[Any]:
        """Context manager for a generic span (non-LLM work, e.g. a tool call)."""
        if self._client is None:
            yield _NullSpan()
            return
        try:
            with self._client.start_as_current_span(name=name, **kwargs) as span:
                yield span
        except Exception as exc:  # pragma: no cover
            logger.debug("trace span '%s' failed: %s", name, exc)
            yield _NullSpan()

    @contextlib.contextmanager
    def generation(self, name: str, **kwargs: Any) -> Iterator[Any]:
        """Context manager for an LLM generation observation."""
        if self._client is None:
            yield _NullSpan()
            return
        try:
            with self._client.start_as_current_generation(name=name, **kwargs) as gen:
                yield gen
        except Exception as exc:  # pragma: no cover
            logger.debug("trace generation '%s' failed: %s", name, exc)
            yield _NullSpan()

    def event(self, name: str, **kwargs: Any) -> None:
        """Record a point-in-time event under the current trace."""
        if self._client is None:
            return
        try:
            self._client.create_event(name=name, **kwargs)
        except Exception as exc:  # pragma: no cover
            logger.debug("trace event '%s' failed: %s", name, exc)

    def score(self, name: str, value: float, **kwargs: Any) -> None:
        """Attach a score to the current trace (used after benchmark grading)."""
        if self._client is None:
            return
        try:
            self._client.score_current_trace(name=name, value=value, **kwargs)
        except Exception as exc:  # pragma: no cover
            logger.debug("trace score '%s' failed: %s", name, exc)

    def flush(self) -> None:
        """Flush buffered traces. Call once at process shutdown."""
        if self._client is None:
            return
        try:
            self._client.flush()
        except Exception as exc:  # pragma: no cover
            logger.debug("langfuse flush failed: %s", exc)
