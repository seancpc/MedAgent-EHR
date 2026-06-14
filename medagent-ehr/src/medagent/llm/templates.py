"""Load and render the agent's Jinja2 prompt templates.

A template file has three marker-delimited sections:

    === SYSTEM ===   instructions
    === USER ===     the per-call input
    === EXAMPLE ===  a worked example

After Jinja rendering, render() returns (system, user); the EXAMPLE section is
appended to the system message as guidance.
"""
from __future__ import annotations

from pathlib import Path

from jinja2 import Template

_PROMPT_DIR = Path(__file__).parent / "prompts"
_SYSTEM_MARKER = "=== SYSTEM ==="
_USER_MARKER = "=== USER ==="
_EXAMPLE_MARKER = "=== EXAMPLE ==="


def render(template_name: str, **variables: object) -> tuple[str, str]:
    """Render a prompt template; return (system_message, user_message)."""
    raw = (_PROMPT_DIR / template_name).read_text(encoding="utf-8")
    text = Template(raw).render(**variables)

    if _SYSTEM_MARKER not in text or _USER_MARKER not in text:
        raise ValueError(f"template {template_name} missing SYSTEM/USER markers")

    after_system = text.split(_SYSTEM_MARKER, 1)[1]
    system_part, after_user = after_system.split(_USER_MARKER, 1)
    if _EXAMPLE_MARKER in after_user:
        user_part, example_part = after_user.split(_EXAMPLE_MARKER, 1)
    else:
        user_part, example_part = after_user, ""

    system = system_part.strip()
    if example_part.strip():
        system += f"\n\n{_EXAMPLE_MARKER}\n{example_part.strip()}"
    return system, user_part.strip()
