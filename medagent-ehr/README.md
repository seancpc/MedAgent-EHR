# medagent-ehr

An **open-source, local, agentic EHR copilot** — an AI agent that takes
natural-language clinical tasks, autonomously plans, queries an electronic
health record over FHIR, and **drafts write actions (orders, prescriptions)
that pass an independent clinical-safety check before they are committed**.

This is the **main project** of **MedAgent-MCP**. See the project overview
document (`MedAgent-MCP_專案說明.md`) for the full picture.

> **Data policy:** All data is public/synthetic (Synthea + MedAgentBench).
> No real patient data (PHI) is involved.

## Why it is different

By 2026, FHIR MCP servers and local-LLM agents are common. This project's
distinctive contribution is the **Verifier safety layer**: before any drafted
order or prescription is written, a separate agent role checks dosage, intent
match, and clinical safety. The whole system runs on a single consumer GPU with
a local open-weight model — no cloud API — which fits in-hospital privacy
constraints.

## Architecture

A three-layer agent:

- **Planner** — decomposes the task into ordered steps.
- **Executor** — runs a ReAct loop, calling FHIR tools, recovering from errors.
- **Verifier** — the safety gate before any write is committed.

Tools are provided by `fhir-mcp-server` (separate repo) over MCP.
Evaluated on Stanford's **MedAgentBench**.

## Development

Requires Python 3.12+, a running `fhir-mcp-server`, and an Ollama instance
serving the agent model.

```bash
python -m venv .venv
. .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# copy env template (sensitive fields stay empty on dev machines by design)
cp .env.example .env

# start the demo web server
python -m medagent.web.app
```

## Status

Work in progress. See the project overview document for the build roadmap.

## License

Apache-2.0
