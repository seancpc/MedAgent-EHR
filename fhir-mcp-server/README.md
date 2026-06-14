# fhir-mcp-server

An MCP ([Model Context Protocol](https://modelcontextprotocol.io)) server that
exposes a **FHIR R4** electronic health record as ~14 LLM-friendly tools.

This is the **infrastructure component** of the **MedAgent-MCP** project — an
open-source, local, agentic EHR copilot. See the project overview document
(`MedAgent-MCP_專案說明.md`) for the full picture.

> **Data policy:** All data used with this server is public/synthetic
> (Synthea + MedAgentBench). No real patient data (PHI) is involved.

## What it does

Raw FHIR REST APIs are verbose and hard for an LLM to use directly. This server
wraps FHIR into a small set of tools that:

- accept human terms (e.g. "HbA1c") and resolve medical codes internally,
- hide FHIR pagination and return compact, flat JSON,
- use a uniform `{ok, data, error}` response envelope,
- gate all writes behind a two-phase `stage -> commit` flow.

## Tools

| Group | Tools |
|-------|-------|
| Patient | `find_patient`, `get_patient_summary` |
| Clinical | `get_observations`, `get_conditions`, `get_medications`, `get_encounters`, `search_clinical_notes` |
| Coding / calc | `resolve_code`, `calculate_clinical_value` |
| Write (two-phase) | `stage_write`, `commit_write`, `list_staged_writes`, `discard_write` |
| System | `health_check` |

## Development

Requires Python 3.12+.

```bash
# 1. start the HAPI FHIR R4 server
docker compose up -d

# 2. install
python -m venv .venv
. .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# 3. copy env template (sensitive fields stay empty on dev machines by design)
cp .env.example .env

# 4. run the MCP server
python -m fhir_mcp.server
```

## Status

Work in progress. See the project overview document for the build roadmap.

## License

Apache-2.0
