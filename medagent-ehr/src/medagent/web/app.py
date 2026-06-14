"""Flask web demo for medagent-ehr.

Serves a single page where a clinician types a task; the agent runs and the
page shows the answer plus a step-by-step timeline of what the agent did.

Runs over HTTPS (self-signed) for the laptop-to-desktop LAN demo.

Run with:  python -m medagent.web.app
"""
from __future__ import annotations

import logging
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from ..agent.orchestrator import Orchestrator, build_orchestrator
from ..config import load_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("medagent.web")

app = Flask(__name__)
_config = load_config()
_orchestrator: Orchestrator | None = None


def _get_orchestrator() -> Orchestrator:
    """Build the orchestrator lazily so importing this module never fails."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = build_orchestrator(_config)
    return _orchestrator


@app.get("/")
def index() -> str:
    return render_template("index.html")


@app.post("/api/run")
def run_task():
    data = request.get_json(silent=True) or {}
    task = (data.get("task") or "").strip()
    if not task:
        return jsonify({"error": "task is required"}), 400
    try:
        result = _get_orchestrator().run(task)
    except Exception as exc:  # noqa: BLE001 - surface setup errors to the UI
        logger.exception("agent run error")
        return jsonify({"error": str(exc)}), 500
    return jsonify(
        {
            "task": result.task,
            "status": result.status,
            "final_answer": result.final_answer,
            "abort_reason": result.abort_reason,
            "steps_used": result.steps_used,
            "plan": result.plan,
            "scratchpad": result.scratchpad,
        }
    )


def _ssl_context():
    """Use cert.pem/key.pem at the repo root if present, else a self-signed cert.

    The 'adhoc' option needs the 'cryptography' package; it is fine for a LAN
    demo. To avoid the browser warning, drop real cert.pem/key.pem at the root.
    """
    root = Path(__file__).resolve().parents[3]
    cert, key = root / "cert.pem", root / "key.pem"
    if cert.exists() and key.exists():
        return (str(cert), str(key))
    return "adhoc"


def main() -> None:
    logger.info(
        "medagent-ehr web demo on https://%s:%s", _config.web_host, _config.web_port
    )
    app.run(host=_config.web_host, port=_config.web_port, ssl_context=_ssl_context())


if __name__ == "__main__":
    main()
