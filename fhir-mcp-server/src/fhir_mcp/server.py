"""fhir-mcp-server entry point.

Builds the FastMCP server, registers all 14 tools, and runs it over streamable
HTTP so the agent can connect via a URL.

Run with:  python -m fhir_mcp.server
"""
from __future__ import annotations

import logging
import sys

from mcp.server.fastmcp import FastMCP

from .services import build_services
from .tools import calculate, clinical, coding, notes, patient, system, write

# STDIO MCP servers must not write to stdout; log to stderr.
logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger("fhir-mcp-server")

# Tool modules in registration order. Together they register all 14 tools:
# system(1) + patient(2) + clinical(4) + notes(1) + coding(1) + calculate(1)
# + write(4) = 14.
_TOOL_MODULES = (system, patient, clinical, notes, coding, calculate, write)


def build_server() -> FastMCP:
    """Construct the FastMCP server with all tools registered."""
    services = build_services()
    # NOTE: host/port are passed as FastMCP settings. If a future SDK version
    # changes this, adjust here when first running on the desktop.
    mcp = FastMCP(
        "fhir-mcp-server",
        host=services.config.mcp_host,
        port=services.config.mcp_port,
    )
    for module in _TOOL_MODULES:
        module.register(mcp, services)
    logger.info(
        "fhir-mcp-server ready on %s:%s (FHIR configured: %s)",
        services.config.mcp_host,
        services.config.mcp_port,
        services.config.configured,
    )
    return mcp


def main() -> None:
    build_server().run(transport="streamable-http")


if __name__ == "__main__":
    main()
