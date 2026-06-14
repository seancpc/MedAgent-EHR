"""LLM client for medagent-ehr (talks to llama-server, OpenAI-compatible).

Calls llama.cpp's `llama-server` via its OpenAI-compatible
`/v1/chat/completions` endpoint. The class is still named `OllamaClient` and
the env vars still start with `OLLAMA_` (kept for code stability), but the
actual backend is llama-server — chosen because Ollama's Qwen3 template has
several open tool-calling and thinking-mode bugs that hurt agentic reliability.
Use Ollama only to `pull` the GGUF, then point llama-server at the blob.

Thinking-mode control: passed via `chat_template_kwargs.enable_thinking`, which
the Qwen Jinja chat template reads when llama-server is run with `--jinja`.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

import httpx

# strips a <think>...</think> block from content (Qwen Jinja with enable_thinking)
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


class OllamaError(Exception):
    """An LLM request or response-parsing step failed."""


@dataclass
class ChatResult:
    """One chat response."""

    content: str
    thinking: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0


def extract_json(text: str) -> dict:
    """Defensively parse the FIRST complete JSON object out of an LLM response.

    Tolerates a stray <think> block, surrounding prose, AND trailing extra
    content (e.g. a second concatenated JSON object — a common failure mode
    where the model emits a replan_request then a tool_call). Scans brace depth
    while respecting string literals and escapes to isolate the first balanced
    {...}. Raises OllamaError if no parseable object can be recovered.
    """
    cleaned = _THINK_BLOCK.sub("", text)
    start = cleaned.find("{")
    if start == -1:
        raise OllamaError("no JSON object found in model output")

    depth = 0
    in_string = False
    escaped = False
    end = -1
    for i in range(start, len(cleaned)):
        ch = cleaned[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end == -1:
        raise OllamaError("no complete JSON object found in model output")

    try:
        parsed = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise OllamaError(f"could not parse JSON from model output: {exc}")
    if not isinstance(parsed, dict):
        raise OllamaError("model output was valid JSON but not an object")
    return parsed


def _normalize_v1_base(base_url: str) -> str:
    """Accept '.../v1' or '...:port' and return the chat-completions URL."""
    url = base_url.rstrip("/")
    if not url.endswith("/v1"):
        url = url + "/v1"
    return url + "/chat/completions"


class OllamaClient:
    """Synchronous client for llama-server's OpenAI-compatible chat API."""

    def __init__(
        self, base_url: str, model: str, timeout_seconds: float = 600.0
    ) -> None:
        if not base_url or not model:
            raise OllamaError(
                "LLM is not configured. Set OLLAMA_BASE_URL (llama-server "
                "OpenAI-compatible /v1 base, e.g. http://localhost:11434/v1) "
                "and OLLAMA_MODEL in .env on the target machine."
            )
        self._url = _normalize_v1_base(base_url)
        self._model = model
        self._client = httpx.Client(timeout=timeout_seconds)

    def close(self) -> None:
        self._client.close()

    def chat(
        self,
        system: str,
        user: str,
        think: bool = False,
        json_mode: bool = True,
        max_tokens: int = 4096,
    ) -> ChatResult:
        """Send one chat request. `think` toggles Qwen reasoning per agent role.

        json_mode enforces strict-JSON output via response_format=json_object,
        but ONLY when think=False — when thinking is ON, the <think>...</think>
        prefix would conflict with the JSON grammar constraint. With think=True
        we rely on the prompt + defensive extract_json instead.

        max_tokens caps the response — important safety against thinking-mode
        runaway, which can otherwise generate tens of thousands of tokens.
        """
        payload: dict = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.0,
            "stream": False,
            "max_tokens": max_tokens,
            # Qwen Jinja template reads this to toggle <think> generation.
            "chat_template_kwargs": {"enable_thinking": think},
        }
        if json_mode and not think:
            payload["response_format"] = {"type": "json_object"}

        try:
            response = self._client.post(self._url, json=payload)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            raise OllamaError(f"llama-server request failed: {exc}") from exc

        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        content = message.get("content", "") or ""
        # Newer servers may surface reasoning in a separate field; otherwise
        # pull it from the content's <think> block.
        thinking = message.get("reasoning_content") or ""
        if not thinking:
            m = _THINK_BLOCK.search(content)
            if m:
                thinking = m.group(0)

        usage = data.get("usage") or {}
        return ChatResult(
            content=content,
            thinking=thinking,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
        )

    def chat_json(
        self, system: str, user: str, think: bool = False
    ) -> tuple[dict, ChatResult]:
        """chat() plus defensive JSON parsing, with one retry on parse failure.

        Returns (parsed_object, last ChatResult). Raises OllamaError if the
        model fails to produce valid JSON twice.
        """
        result = self.chat(system, user, think=think, json_mode=True)
        try:
            return extract_json(result.content), result
        except OllamaError:
            pass  # fall through to a single retry
        retry_user = (
            user + "\n\nIMPORTANT: your previous reply was not valid JSON. "
            "Reply with ONLY a single valid JSON object — no prose, no fences."
        )
        result = self.chat(system, retry_user, think=think, json_mode=True)
        return extract_json(result.content), result
