"""Integration-style tests for the orchestrator, using fake LLM and MCP clients.

These exercise the real control loop (plan -> execute -> verify -> terminate)
without needing a live Ollama or MCP server.
"""
from medagent.agent.orchestrator import Orchestrator
from medagent.config import Config
from medagent.llm.ollama_client import ChatResult


def _config() -> Config:
    return Config(
        ollama_base_url="x", ollama_model="m", fhir_mcp_url="x",
        langfuse_host="", langfuse_public_key="", langfuse_secret_key="",
        web_host="127.0.0.1", web_port=8443,
        max_steps=10, max_replans=2, max_retries=2,
    )


class FakeOllama:
    """Returns scripted JSON responses for successive chat_json() calls."""

    def __init__(self, responses):
        self._responses = list(responses)

    def chat_json(self, system, user, think=False):
        return self._responses.pop(0), ChatResult(content="{}")


class FakeMcp:
    """A stand-in fhir-mcp-server returning canned tool results."""

    def __init__(self, tools=None, results=None):
        self._tools = tools or []
        self._results = results or {}

    def list_tools(self):
        return self._tools

    def call_tool(self, name, arguments):
        return self._results.get(name, {"ok": True, "data": {}, "error": None})


def test_task_done_immediately():
    ollama = FakeOllama([
        {"task": "t", "steps": [{"step_id": 1, "intent": "answer"}]},
        {"type": "task_done", "final_answer": "the answer"},
    ])
    result = Orchestrator(_config(), ollama, FakeMcp()).run("t")
    assert result.status == "completed"
    assert result.final_answer == "the answer"


def test_tool_call_then_done():
    ollama = FakeOllama([
        {"task": "t", "steps": [{"step_id": 1, "intent": "find"}]},
        {"type": "tool_call", "step_id": 1, "tool": "find_patient", "args": {}},
        {"type": "task_done", "final_answer": "found"},
    ])
    mcp = FakeMcp(
        tools=[{"name": "find_patient", "description": "d", "input_schema": {}}],
        results={"find_patient": {"ok": True, "data": {"matches": []}, "error": None}},
    )
    result = Orchestrator(_config(), ollama, mcp).run("t")
    assert result.status == "completed"
    assert len(result.scratchpad) == 1


def test_max_steps_abort():
    responses = [{"task": "t", "steps": []}]
    responses += [
        {"type": "tool_call", "step_id": 1, "tool": "find_patient", "args": {}}
    ] * 20
    mcp = FakeMcp(
        tools=[{"name": "find_patient", "description": "d", "input_schema": {}}]
    )
    result = Orchestrator(_config(), FakeOllama(responses), mcp).run("t")
    assert result.status == "aborted"
    assert "max_steps" in result.abort_reason
