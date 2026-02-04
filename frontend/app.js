const apiBaseUrl =
  window.APP_CONFIG?.apiBaseUrl && window.APP_CONFIG.apiBaseUrl !== "__API_BASE_URL__"
    ? window.APP_CONFIG.apiBaseUrl
    : "http://localhost:8000";

const elements = {
  userCount: document.getElementById("user-count"),
  workflowCount: document.getElementById("workflow-count"),
  healthStatus: document.getElementById("health-status"),
  uptime: document.getElementById("uptime"),
  workflowLive: document.getElementById("workflow-live"),
  workflowDraft: document.getElementById("workflow-draft"),
  workflowRuns: document.getElementById("workflow-runs"),
  apiEndpoint: document.getElementById("api-endpoint"),
  userList: document.getElementById("user-list"),
  workflowList: document.getElementById("workflow-list"),
  activityList: document.getElementById("activity-list"),
  runList: document.getElementById("run-list"),
  seedDemo: document.getElementById("seed-demo"),
  refresh: document.getElementById("refresh"),
  userForm: document.getElementById("user-form"),
  workflowForm: document.getElementById("workflow-form"),
  workflowTemplate: document.getElementById("workflow-template"),
  runForm: document.getElementById("run-form"),
  runWorkflow: document.getElementById("run-workflow"),
};

elements.apiEndpoint.textContent = apiBaseUrl;

async function fetchJson(path, options) {
  const response = await fetch(`${apiBaseUrl}${path}`, options);
  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(detail.detail || "Request failed");
  }
  if (response.status === 204) {
    return null;
  }
  return response.json();
}

function renderUsers(users) {
  elements.userCount.textContent = users.length.toString();
  elements.userList.innerHTML = users
    .map(
      (user) => `
      <div class="card">
        <h4>${user.username}</h4>
        <p>${user.email}</p>
        <p>${user.role}</p>
      </div>
    `,
    )
    .join("");
}

function renderWorkflows(workflows) {
  elements.workflowCount.textContent = workflows.length.toString();
  elements.workflowList.innerHTML = workflows
    .map(
      (workflow) => `
      <div class="card">
        <h4>${workflow.name}</h4>
        <p>${workflow.description || "No description yet"}</p>
        <p>Status: ${workflow.status}</p>
      </div>
    `,
    )
    .join("");
}

function renderActivity(activity) {
  elements.activityList.innerHTML = activity
    .map(
      (entry) => `
      <div class="card">
        <h4>${entry.action.toUpperCase()} · ${entry.entity_type}</h4>
        <p>${entry.detail || "Activity recorded."}</p>
        <p>${new Date(entry.created_at).toLocaleString()}</p>
      </div>
    `,
    )
    .join("");
}

function renderMetrics(metrics) {
  elements.uptime.textContent = Math.floor(metrics.uptime_seconds).toString();
  elements.workflowLive.textContent = metrics.workflows_live.toString();
  elements.workflowDraft.textContent = metrics.workflows_draft.toString();
  elements.workflowRuns.textContent = metrics.runs.toString();
}

function renderTemplates(templates) {
  elements.workflowTemplate.innerHTML = [
    "<option value=\"\">Custom workflow</option>",
    ...templates.map(
      (template, index) =>
        `<option value="${index}">${template.name}</option>`,
    ),
  ].join("");
  elements.workflowTemplate.dataset.templates = JSON.stringify(templates);
}

function renderRuns(runs) {
  elements.runList.innerHTML = runs
    .map(
      (run) => `
      <div class="card">
        <h4>Run #${run.id} · ${run.status}</h4>
        <p>Workflow ID: ${run.workflow_id}</p>
        <p>${run.summary || "Execution queued."}</p>
      </div>
    `,
    )
    .join("");
}

function renderRunWorkflowOptions(workflows) {
  elements.runWorkflow.innerHTML = workflows
    .map((workflow) => `<option value="${workflow.id}">${workflow.name}</option>`)
    .join("");
}

async function loadDashboard() {
  const [health, users, workflows, metrics, activity, templates, runs] = await Promise.all([
    fetchJson("/health"),
    fetchJson("/users"),
    fetchJson("/workflows"),
    fetchJson("/metrics"),
    fetchJson("/activity"),
    fetchJson("/templates"),
    fetchJson("/runs"),
  ]);
  elements.healthStatus.textContent = health.status;
  renderUsers(users);
  renderWorkflows(workflows);
  renderMetrics(metrics);
  renderActivity(activity);
  renderTemplates(templates);
  renderRuns(runs);
  renderRunWorkflowOptions(workflows);
}

async function seedDemoData() {
  await fetchJson("/users", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username: `builder_${Math.floor(Math.random() * 1000)}`,
      email: `builder_${Date.now()}@openagi.ai`,
      role: "strategist",
      bio: "Specializes in multi-agent workflow optimization.",
    }),
  });

  await fetchJson("/workflows", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: "Support Concierge",
      description: "Triages inbound support, enriches context, and drafts answers.",
      status: "live",
      components: [
        { type: "connector", name: "Zendesk", config: { queue: "priority" } },
        { type: "tool", name: "Answer Draft", config: { tone: "friendly" } },
        { type: "memory", name: "Customer Profile", config: { ttl: "30d" } },
      ],
    }),
  });
}

elements.seedDemo.addEventListener("click", async () => {
  elements.seedDemo.disabled = true;
  try {
    await seedDemoData();
    await loadDashboard();
  } catch (error) {
    alert(error.message);
  } finally {
    elements.seedDemo.disabled = false;
  }
});

elements.refresh.addEventListener("click", async () => {
  try {
    await loadDashboard();
  } catch (error) {
    alert(error.message);
  }
});

elements.userForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(event.target);
  const payload = Object.fromEntries(formData.entries());
  try {
    await fetchJson("/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    event.target.reset();
    await loadDashboard();
  } catch (error) {
    alert(error.message);
  }
});

elements.workflowForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(event.target);
  const payload = Object.fromEntries(formData.entries());
  try {
    payload.components = payload.components
      ? JSON.parse(payload.components)
      : [];
  } catch (error) {
    alert("Components must be valid JSON.");
    return;
  }
  try {
    await fetchJson("/workflows", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    event.target.reset();
    await loadDashboard();
  } catch (error) {
    alert(error.message);
  }
});

elements.workflowTemplate.addEventListener("change", (event) => {
  const templates = JSON.parse(elements.workflowTemplate.dataset.templates || "[]");
  const selected = templates[Number(event.target.value)];
  if (!selected) {
    return;
  }
  elements.workflowForm.querySelector("input[name=\"name\"]").value = selected.name;
  elements.workflowForm.querySelector("textarea[name=\"description\"]").value =
    selected.description || "";
  elements.workflowForm.querySelector("select[name=\"status\"]").value =
    selected.status || "draft";
  elements.workflowForm.querySelector("textarea[name=\"components\"]").value = JSON.stringify(
    selected.components ?? [],
    null,
    2,
  );
});

elements.runForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(event.target);
  const payload = Object.fromEntries(formData.entries());
  try {
    await fetchJson(`/workflows/${payload.workflow_id}/runs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        workflow_id: Number(payload.workflow_id),
        status: payload.status,
        summary: payload.summary,
      }),
    });
    event.target.reset();
    await loadDashboard();
  } catch (error) {
    alert(error.message);
  }
});

loadDashboard().catch((error) => {
  elements.healthStatus.textContent = "offline";
  console.error(error);
});
