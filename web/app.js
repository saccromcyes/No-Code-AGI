"use strict";
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// ---------- Session: your agents and runs are tied to it ----------
function sessionId() {
  let id = null;
  try { id = localStorage.getItem("agent-builder-session"); } catch (_) { /* storage blocked */ }
  if (!id || !/^[A-Za-z0-9-]{8,64}$/.test(id)) {
    id = crypto.randomUUID ? crypto.randomUUID() : `s-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    try { localStorage.setItem("agent-builder-session", id); } catch (_) { /* lasts this page view */ }
  }
  return id;
}
const SESSION = sessionId();
const api = async (path, opts = {}) => {
  const res = await fetch(path, { ...opts, headers: { "X-Session-Id": SESSION, ...(opts.body ? { "Content-Type": "application/json" } : {}), ...(opts.headers || {}) } });
  if (res.status === 204) return null;
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(Array.isArray(body.detail) ? body.detail.map((d) => d.msg).join("; ") : body.detail || `Request failed (${res.status}).`);
  return body;
};

let TOOLS = [];
let AGENTS = [];
let current = null; // agent being viewed
let dirty = false;
let CONFIG = {};

// ---------- Views ----------
document.querySelectorAll(".views button").forEach((b) => b.addEventListener("click", () => {
  document.querySelectorAll(".views button").forEach((x) => x.setAttribute("aria-pressed", x === b));
  $("#view-build").hidden = b.dataset.view !== "build";
  $("#view-eval").hidden = b.dataset.view !== "eval";
  if (b.dataset.view === "eval") loadEval();
}));

// ---------- Agent list ----------
function renderList() {
  const item = (a) => `<li><button type="button" data-id="${esc(a.id)}" aria-current="${current && current.id === a.id}"><strong>${esc(a.name)}</strong><span>${esc(a.description || a.tools.map((t) => TOOLS.find((x) => x.name === t)?.label || t).join(", ") || "No tools")}</span></button></li>`;
  const mine = AGENTS.filter((a) => !a.template);
  $("#mine").innerHTML = mine.length ? mine.map(item).join("") : `<li class="empty">None yet. Start one, or copy a starter.</li>`;
  $("#starters").innerHTML = AGENTS.filter((a) => a.template).map(item).join("");
}
document.querySelector(".rail").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-id]");
  if (!b) return;
  if (dirty && !confirmDiscard()) return;
  select(AGENTS.find((a) => a.id === b.dataset.id));
});
function confirmDiscard() {
  // A visible inline prompt instead of a blocking dialog
  const s = $("#save-status");
  if (s.dataset.confirm === "1") { s.dataset.confirm = ""; return true; }
  s.dataset.confirm = "1";
  s.className = "save-status error";
  s.textContent = "You have unsaved changes. Click again to discard them, or save first.";
  return false;
}

// ---------- Builder ----------
function renderTools(selected, readonly) {
  $("#f-tools").innerHTML = TOOLS.map((t) => `<label class="tool"><input type="checkbox" value="${esc(t.name)}" ${selected.includes(t.name) ? "checked" : ""} ${readonly ? "disabled" : ""}><strong>${esc(t.label)}</strong><span>${esc(t.summary)}</span></label>`).join("");
  syncNotesField();
}
// The notes box only matters when the agent can search notes.
function syncNotesField() {
  $("#notes-field").hidden = !$('#f-tools input[value="search_notes"]')?.checked;
}
function select(agent, fresh = false) {
  current = agent;
  dirty = false;
  const ro = !!agent.template;
  $("#agent-title").textContent = fresh ? "New agent" : agent.name;
  $("#f-name").value = agent.name;
  $("#f-description").value = agent.description || "";
  $("#f-instructions").value = agent.instructions || "";
  $("#f-notes").value = agent.notes || "";
  renderTools(agent.tools || [], ro);
  for (const id of ["#f-name", "#f-description", "#f-instructions", "#f-notes"]) $(id).disabled = ro;
  $("#readonly-note").hidden = !ro;
  $("#copy-agent").hidden = !ro;
  $("#save-agent").hidden = ro;
  $("#delete-agent").hidden = ro || fresh;
  $("#save-status").textContent = "";
  $("#save-status").dataset.confirm = "";
  $("#unsaved").hidden = true;
  $("#examples").innerHTML = (agent.examples || []).map((x) => `<button type="button">${esc(x)}</button>`).join("");
  $("#run-btn").disabled = fresh || !CONFIG.llm_ready;
  $("#run-input").placeholder = fresh ? "Save the agent to run it." : "Give the agent a task…";
  $("#trace-wrap").hidden = true;
  renderList();
  loadHistory();
}
function formData() {
  return {
    name: $("#f-name").value.trim() || "Untitled agent",
    description: $("#f-description").value.trim(),
    instructions: $("#f-instructions").value,
    tools: [...document.querySelectorAll("#f-tools input:checked")].map((i) => i.value),
    notes: $("#f-notes").value,
    examples: current?.examples || [],
  };
}
$("#agent-form").addEventListener("input", () => {
  if (current?.template) return;
  syncNotesField();
  dirty = true;
  $("#unsaved").hidden = !current?.id;
  $("#save-status").textContent = "";
});
$("#new-agent").addEventListener("click", () => {
  if (dirty && !confirmDiscard()) return;
  select({ id: null, name: "My agent", description: "", instructions: "", tools: ["calculator"], notes: "", examples: [] }, true);
  $("#f-name").focus();
  $("#f-name").select();
});
$("#copy-agent").addEventListener("click", async () => {
  try {
    const copy = await api("/api/agents", { method: "POST", body: JSON.stringify({ ...formData(), name: `${current.name} (copy)`, examples: current.examples }) });
    await refresh(copy.id);
    $("#save-status").className = "save-status";
    $("#save-status").textContent = "Copied. This version is yours to edit.";
  } catch (e) { showStatus(e.message, true); }
});
$("#save-agent").addEventListener("click", async () => {
  try {
    const saved = current.id
      ? await api(`/api/agents/${current.id}`, { method: "PUT", body: JSON.stringify(formData()) })
      : await api("/api/agents", { method: "POST", body: JSON.stringify(formData()) });
    await refresh(saved.id);
    showStatus("Saved.");
  } catch (e) { showStatus(e.message, true); }
});
$("#delete-agent").addEventListener("click", async (e) => {
  const btn = e.currentTarget;
  if (btn.dataset.confirm !== "1") { btn.dataset.confirm = "1"; btn.textContent = "Click again to delete"; return; }
  btn.dataset.confirm = ""; btn.textContent = "Delete";
  try { await api(`/api/agents/${current.id}`, { method: "DELETE" }); await refresh("research-assistant"); } catch (err) { showStatus(err.message, true); }
});
function showStatus(text, error = false) { const s = $("#save-status"); s.className = `save-status${error ? " error" : ""}`; s.textContent = text; }

async function refresh(selectId) {
  AGENTS = await api("/api/agents");
  const target = AGENTS.find((a) => a.id === selectId) || AGENTS.find((a) => a.template);
  select(target);
}

// ---------- Run ----------
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
const fmtMs = (ms) => (ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${ms} ms`);
function pretty(value) {
  if (typeof value === "string") return value;
  const keys = Object.keys(value || {});
  if (keys.length === 1) return String(value[keys[0]]);
  return JSON.stringify(value, null, 1).replace(/^\{\n|\n\}$/g, "").replace(/^ /gm, "");
}
function stepHTML(ev) {
  const t = `<time>${fmtMs(ev.t_ms)}</time>`;
  switch (ev.type) {
    case "start":
      return `<li class="k-model"><span class="node"></span><div class="step-head"><b>Started ${esc(ev.agent)}</b>${t}</div><p class="muted">Model ${esc(ev.model)}. Tools: ${ev.tools.length ? ev.tools.map((x) => esc(TOOLS.find((y) => y.name === x)?.label || x)).join(", ") : "none"}.</p></li>`;
    case "model":
      return ev.n_calls
        ? `<li class="k-model"><span class="node"></span><div class="step-head"><b>Turn ${ev.turn}: decided to use ${ev.n_calls} tool${ev.n_calls > 1 ? "s" : ""}</b>${t}</div>${ev.thought ? `<p class="thought">${esc(ev.thought)}</p>` : ""}</li>`
        : `<li class="k-model"><span class="node"></span><div class="step-head"><b>Turn ${ev.turn}: writing the answer</b>${t}</div></li>`;
    case "tool_call":
      return `<li class="k-call"><span class="node"></span><div class="step-head"><b>${esc(ev.label)}</b>${t}</div><pre class="code">${esc(pretty(ev.args))}</pre></li>`;
    case "tool_result":
      return `<li class="k-result${ev.ok ? "" : " fail"}"><span class="node"></span><div class="step-head"><b>${ev.ok ? "Result" : "Tool error"}</b><time>${fmtMs(ev.ms)}</time></div><pre class="code">${esc(ev.output)}</pre></li>`;
    case "answer":
      return `<li class="k-answer"><span class="node"></span><div class="step-head"><b>Answer</b>${t}</div><div class="answer">${esc(ev.text)}</div></li>`;
    case "error":
      return `<li class="k-error"><span class="node"></span><div class="step-head"><b>${esc(ev.message)}</b>${t}</div></li>`;
    default:
      return "";
  }
}
function renderStats(done) {
  const s = done.stats;
  const status = { completed: "Finished", max_steps: "Stopped at the step limit", error: "Failed" }[done.status] || done.status;
  $("#stats").innerHTML = `<span><b>${status}</b></span><span>${plural(s.model_turns, "model turn")}</span><span>${plural(s.tool_calls, "tool call")}${s.tool_errors ? `, ${s.tool_errors} failed` : ""}</span><span>${(s.prompt_tokens + s.completion_tokens).toLocaleString()} tokens</span><span>${fmtMs(s.latency_ms)}</span>`;
}

let running = false;
async function run(text) {
  if (running || !current?.id || !text.trim()) return;
  running = true;
  $("#run-btn").disabled = true;
  $("#trace-wrap").hidden = false;
  $("#trace").innerHTML = "";
  $("#stats").innerHTML = "";
  try {
    const res = await fetch(`/api/agents/${current.id}/run`, { method: "POST", headers: { "X-Session-Id": SESSION, "Content-Type": "application/json" }, body: JSON.stringify({ input: text }) });
    if (!res.ok) { const b = await res.json().catch(() => ({})); throw new Error(b.detail || `Run failed (${res.status}).`); }
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const parts = buf.split("\n\n");
      buf = parts.pop();
      for (const p of parts) {
        if (!p.startsWith("data: ")) continue;
        const ev = JSON.parse(p.slice(6));
        if (ev.type === "done") { renderStats(ev); loadHistory(); continue; }
        $("#trace").insertAdjacentHTML("beforeend", stepHTML(ev));
      }
    }
  } catch (e) {
    $("#trace").insertAdjacentHTML("beforeend", stepHTML({ type: "error", message: e.message, t_ms: 0 }));
  } finally {
    running = false;
    $("#run-btn").disabled = !CONFIG.llm_ready;
  }
}
$("#run-form").addEventListener("submit", (e) => { e.preventDefault(); run($("#run-input").value); });
$("#run-input").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#run-form").requestSubmit(); } });
$("#examples").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) { $("#run-input").value = b.textContent; run(b.textContent); } });

async function loadHistory() {
  if (!current?.id) { $("#history").hidden = true; return; }
  try {
    const runs = await api(`/api/agents/${current.id}/runs`);
    $("#history").hidden = !runs.length;
    $("#history-list").innerHTML = runs.map((r) => `<li><button type="button" data-run="${esc(r.id)}"><span>${esc(r.input.slice(0, 70))}</span><span class="st">${{ completed: "finished", max_steps: "step limit", error: "failed" }[r.status] || r.status}, ${fmtMs(r.stats.latency_ms || 0)}</span></button></li>`).join("");
  } catch (_) { $("#history").hidden = true; }
}
$("#history-list").addEventListener("click", async (e) => {
  const b = e.target.closest("button[data-run]");
  if (!b) return;
  const r = await api(`/api/runs/${b.dataset.run}`);
  $("#trace-wrap").hidden = false;
  $("#run-input").value = r.input;
  $("#trace").innerHTML = r.steps.map(stepHTML).join("");
  renderStats(r);
});

// ---------- Evaluation ----------
let evalLoaded = false;
async function loadEval() {
  if (evalLoaded) return;
  const el = $("#eval-body");
  const d = await fetch("/api/eval").then((r) => r.json()).catch(() => ({ available: false }));
  if (!d.available) { el.innerHTML = `<p class="muted">Results appear here after the first automated evaluation run.</p>`; return; }
  evalLoaded = true;
  const s = d.summary;
  const pct = (x) => `${Math.round(x * 100)}%`;
  el.innerHTML = `<div class="cards">
      <div class="card"><b>${pct(s.success)}</b><span>of ${s.tasks} tasks solved</span></div>
      <div class="card"><b>${pct(s.used_needed_tools)}</b><span>used the tools the task needed</span></div>
      <div class="card"><b>${s.avg_model_turns}</b><span>model turns per task</span></div>
      <div class="card"><b>${(s.latency_p50_ms / 1000).toFixed(1)} s</b><span>median time per task</span></div>
    </div>
    <p class="muted">Run ${new Date(d.run_at).toLocaleDateString(undefined, { dateStyle: "medium" })} with ${esc(d.model)}, commit ${esc(d.commit)}.</p>
    <div style="overflow-x:auto"><table><thead><tr><th>Task</th><th>Result</th><th>Tools used</th><th>Answer</th></tr></thead><tbody>${
      d.tasks.map((t) => `<tr><td><span class="muted">${esc(t.group)}</span><br>${esc(t.input)}</td><td class="${t.passed ? "pass" : "fail-t"}">${t.passed ? "Pass" : "Fail"}</td><td>${t.tools_used.map((x) => esc(TOOLS.find((y) => y.name === x)?.label || x)).join(", ") || "none"}</td><td>${esc(t.answer.slice(0, 220))}${t.answer.length > 220 ? "…" : ""}</td></tr>`).join("")
    }</tbody></table></div>`;
}

// ---------- Boot ----------
(async () => {
  [CONFIG, TOOLS] = await Promise.all([api("/api/config"), api("/api/tools")]);
  $("#no-llm").hidden = CONFIG.llm_ready;
  await refresh("research-assistant");
})();
