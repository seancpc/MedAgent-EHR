"use strict";

const $ = (id) => document.getElementById(id);

async function runAgent() {
  const task = $("task").value.trim();
  if (!task) return;
  setRunning(true);
  try {
    const resp = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      showError(data.error || "request failed");
      return;
    }
    render(data);
  } catch (err) {
    showError(String(err));
  } finally {
    setRunning(false);
  }
}

function setRunning(on) {
  $("run").disabled = on;
  $("run").textContent = on ? "Running…" : "Run agent";
}

function showError(msg) {
  const s = $("status");
  s.className = "status aborted";
  s.textContent = "Error: " + msg;
  s.classList.remove("hidden");
}

function render(data) {
  const s = $("status");
  s.className = "status " + data.status;
  s.textContent =
    "Status: " + data.status + " (" + data.steps_used + " steps)" +
    (data.abort_reason ? " — " + data.abort_reason : "");
  s.classList.remove("hidden");

  const a = $("answer");
  a.classList.remove("hidden");
  a.innerHTML =
    "<h2>Answer</h2><p>" + escapeHtml(data.final_answer || "(no answer)") + "</p>";

  const p = $("plan");
  p.classList.remove("hidden");
  const steps = (data.plan && data.plan.steps) || [];
  p.innerHTML =
    "<h2>Plan</h2><ol>" +
    steps.map((st) => "<li>" + escapeHtml(st.intent) + "</li>").join("") +
    "</ol>";

  const t = $("timeline");
  t.classList.remove("hidden");
  t.innerHTML =
    "<h2>Step timeline</h2>" + (data.scratchpad || []).map(renderEntry).join("");
}

function renderEntry(entry) {
  const action = entry.action || {};
  const obs = entry.observation || {};
  const tool = action.tool ? action.tool : action.type;
  const args =
    action.args && Object.keys(action.args).length
      ? JSON.stringify(action.args)
      : "";
  let html = "<div class='entry " + (obs.ok ? "ok" : "err") + "'>";
  html +=
    "<div class='entry-head'>" + escapeHtml(tool) +
    (args ? " <code>" + escapeHtml(args) + "</code>" : "") + "</div>";
  if (action.thought) {
    html += "<div class='thought'>" + escapeHtml(action.thought) + "</div>";
  }
  html += "<div class='obs'>" + escapeHtml(summarize(obs)) + "</div>";
  if (obs.recovery_hint) {
    html += "<div class='hint'>hint: " + escapeHtml(obs.recovery_hint) + "</div>";
  }
  return html + "</div>";
}

function summarize(obs) {
  if (obs.error) return "error: " + obs.error;
  if (obs.result_summary) return obs.result_summary;
  if (obs.data !== undefined) return JSON.stringify(obs.data).slice(0, 400);
  return JSON.stringify(obs).slice(0, 400);
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

$("run").addEventListener("click", runAgent);
