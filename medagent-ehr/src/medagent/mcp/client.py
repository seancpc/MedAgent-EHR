"""Synchronous client wrapper for fhir-mcp-server (MCP over streamable HTTP).

The MCP Python SDK client is async; this module wraps it in a synchronous
interface so the (synchronous) agent and Flask app can use it simply.

For v1 each call opens a fresh connection — simple and correct. The user
accepted that throughput is not a concern; a persistent-session optimization
can come later.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


class McpClientError(Exception):
    """An MCP client call failed."""


class FhirMcpClient:
    """Synchronous wrapper around the fhir-mcp-server MCP endpoint."""

    def __init__(self, base_url: str) -> None:
        if not base_url:
            raise McpClientError(
                "FHIR_MCP_URL is not configured. Set it in .env on the target machine."
            )
        url = base_url.rstrip("/")
        # streamable-http MCP endpoints are conventionally served under /mcp
        self._url = url if url.endswith("/mcp") else url + "/mcp"

    def list_tools(self) -> list[dict[str, Any]]:
        """Return available tools as {name, description, input_schema} dicts."""
        return asyncio.run(self._list_tools())

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call a tool; return its {ok, data, error} envelope."""
        return asyncio.run(self._call_tool(name, arguments))

    async def _list_tools(self) -> list[dict[str, Any]]:
        try:
            async with streamablehttp_client(self._url) as (read, write, _gid):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.list_tools()
        except Exception as exc:
            raise McpClientError(f"MCP list_tools failed: {exc}") from exc
        return [
            {
                "name": t.name,
                "description": t.description or "",
                "input_schema": getattr(t, "inputSchema", {}) or {},
            }
            for t in result.tools
        ]

    async def _call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            async with streamablehttp_client(self._url) as (read, write, _gid):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(name, arguments=arguments)
        except Exception as exc:
            raise McpClientError(f"MCP call '{name}' failed: {exc}") from exc
        return _extract_envelope(result)


def _extract_envelope(result: Any) -> dict[str, Any]:
    """Pull the tool's {ok,data,error} envelope out of an MCP CallToolResult.

    fhir-mcp-server tools return a dict; FastMCP exposes it as structured
    content. Falls back to parsing text content. Verify this shape against the
    installed SDK on first run.
    """
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        # FastMCP may wrap a value under a single "result" key
        if set(structured.keys()) == {"result"} and isinstance(
            structured["result"], dict
        ):
            return structured["result"]
        return structured
    for item in getattr(result, "content", None) or []:
        text = getattr(item, "text", None)
        if text:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"ok": False, "data": None, "error": text}
    return {"ok": False, "data": None, "error": "empty MCP tool result"}
