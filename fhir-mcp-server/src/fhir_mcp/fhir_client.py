"""Low-level FHIR R4 REST client.

Wraps httpx with the things every tool needs:
  - automatic pagination (follows Bundle `next` links, returns a flat list)
  - retry with backoff on transient errors
  - normalized errors (FhirError) with messages an agent can act on

This module knows nothing about MCP or specific tools — it only speaks FHIR REST.
"""
from __future__ import annotations

import time
from typing import Any

import httpx

# HTTP statuses worth retrying (transient server-side / gateway issues).
_RETRYABLE_STATUS = {502, 503, 504}


class FhirError(Exception):
    """A FHIR request failed. The message is written to be actionable."""


class FhirClient:
    """Minimal FHIR R4 REST client."""

    def __init__(
        self,
        base_url: str,
        auth_token: str = "",
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        if not base_url:
            raise FhirError(
                "FHIR base URL is not configured. Set FHIR_BASE_URL in .env "
                "on the target machine."
            )
        self._base_url = base_url.rstrip("/")
        self._max_retries = max_retries
        headers = {"Accept": "application/fhir+json"}
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
        self._client = httpx.Client(
            base_url=self._base_url, headers=headers, timeout=timeout_seconds
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "FhirClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- core request with retry ------------------------------------------
    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                response = self._client.request(method, url, **kwargs)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
            else:
                if response.status_code in _RETRYABLE_STATUS:
                    last_error = FhirError(
                        f"FHIR server returned {response.status_code}"
                    )
                else:
                    return response
            if attempt < self._max_retries:
                time.sleep(0.5 * attempt)  # linear backoff
        raise FhirError(
            f"FHIR request {method} {url} failed after {self._max_retries} "
            f"attempts: {last_error}"
        )

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.is_success:
            return
        detail = response.text[:300]
        raise FhirError(f"FHIR request failed: HTTP {response.status_code}. {detail}")

    # -- public API -------------------------------------------------------
    def read(self, resource_type: str, resource_id: str) -> dict[str, Any]:
        """GET a single resource by id."""
        response = self._request("GET", f"/{resource_type}/{resource_id}")
        if response.status_code == 404:
            raise FhirError(f"{resource_type}/{resource_id} not found")
        self._raise_for_status(response)
        return response.json()

    def search(
        self,
        resource_type: str,
        params: dict[str, Any] | None = None,
        max_results: int = 200,
    ) -> list[dict[str, Any]]:
        """Search a resource type, following pagination, up to max_results.

        Returns a flat list of resource dicts (the `resource` field of each
        Bundle entry).
        """
        resources: list[dict[str, Any]] = []
        response = self._request("GET", f"/{resource_type}", params=params or {})
        self._raise_for_status(response)

        while True:
            bundle = response.json()
            for entry in bundle.get("entry", []):
                resource = entry.get("resource")
                if resource is not None:
                    resources.append(resource)
                    if len(resources) >= max_results:
                        return resources
            next_url = _next_link(bundle)
            if not next_url:
                return resources
            # `next` is an absolute URL; httpx uses it as-is even with base_url set
            response = self._request("GET", next_url)
            self._raise_for_status(response)

    def create(self, resource_type: str, resource: dict[str, Any]) -> dict[str, Any]:
        """POST a new resource. Returns the created resource (including its id)."""
        response = self._request(
            "POST",
            f"/{resource_type}",
            json=resource,
            headers={"Content-Type": "application/fhir+json"},
        )
        self._raise_for_status(response)
        # Most FHIR servers echo the created resource; some return an empty body
        # with a Location header instead.
        if response.content:
            return response.json()
        location = response.headers.get("Location", "")
        return {"resourceType": resource_type, "id": location.rsplit("/", 1)[-1]}

    def capability(self) -> dict[str, Any]:
        """GET /metadata — used by health_check."""
        response = self._request("GET", "/metadata")
        self._raise_for_status(response)
        return response.json()


def _next_link(bundle: dict[str, Any]) -> str | None:
    """Extract the `next` page URL from a FHIR Bundle, if any."""
    for link in bundle.get("link", []):
        if link.get("relation") == "next":
            return link.get("url")
    return None
