const form = document.getElementById("analyze-form");
const userIdInput = document.getElementById("user-id");
const inputText = document.getElementById("input-text");
const submitBtn = document.getElementById("submit-btn");
const taskIdEl = document.getElementById("task-id");
const statusChip = document.getElementById("status-chip");
const messageEl = document.getElementById("message");
const planOut = document.getElementById("plan-output");
const reportOut = document.getElementById("report-output");

let pollHandle = null;

function setStatus(status) {
  statusChip.textContent = status;
  statusChip.className = `chip chip-${status}`;
}

function setMessage(msg) {
  messageEl.textContent = msg;
}

async function getJson(url) {
  const res = await fetch(url);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return res.json();
}

async function refreshPlan(taskId) {
  try {
    const data = await getJson(`/plan/${taskId}`);
    renderPlan(data.plan);
  } catch (err) {
    setMessage(`Plan fetch error: ${err.message}`);
  }
}

async function refreshReport(taskId) {
  try {
    const data = await getJson(`/report/${taskId}`);
    renderReport(data.formal_report_text, data.formal_report, data.report);
  } catch (err) {
    setMessage(`Report fetch error: ${err.message}`);
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function renderPlan(plan) {
  if (!plan || !Array.isArray(plan.agents) || plan.agents.length === 0) {
    planOut.innerHTML = '<p class="empty">No plan yet.</p>';
    return;
  }

  const cards = plan.agents
    .map((agent) => {
      const name = escapeHtml(agent.name || "unknown");
      const objective = escapeHtml(agent.objective || "No objective provided.");
      const priority = escapeHtml(agent.priority ?? "-");
      return `
        <article class="item-card">
          <div class="item-top">
            <strong>${name}</strong>
            <span class="tag">P${priority}</span>
          </div>
          <p>${objective}</p>
        </article>
      `;
    })
    .join("");

  const notes = plan.notes ? `<p class="notes">${escapeHtml(plan.notes)}</p>` : "";
  planOut.innerHTML = `${cards}${notes}`;
}

function renderFormalTextBlock(text, fallbackFormal) {
  const source = typeof text === "string" && text.trim() ? text.trim() : "";
  if (!source) {
    return `
      <article class="formal-report">
        <header class="formal-head">
          <h3>${escapeHtml((fallbackFormal && fallbackFormal.title) || "Investment Analysis Report")}</h3>
          <p class="formal-subject">Subject: ${escapeHtml((fallbackFormal && fallbackFormal.subject) || "N/A")}</p>
        </header>
        <section><p>No narrative report generated.</p></section>
      </article>
    `;
  }

  const lines = source.split(/\r?\n/);
  let html = '<article class="formal-report">';
  let inList = false;

  function closeList() {
    if (inList) {
      html += "</ul>";
      inList = false;
    }
  }

  for (const raw of lines) {
    const line = raw.trim();
    if (!line) {
      closeList();
      continue;
    }

    if (line.toLowerCase().startsWith("title:")) {
      closeList();
      html += `<header class="formal-head"><h3>${escapeHtml(line.slice(6).trim())}</h3></header>`;
      continue;
    }

    if (/^\d+\.\s+/.test(line)) {
      closeList();
      html += `<section><h4>${escapeHtml(line)}</h4>`;
      continue;
    }

    if (line.startsWith("- ")) {
      if (!inList) {
        html += "<ul>";
        inList = true;
      }
      html += `<li>${escapeHtml(line.slice(2))}</li>`;
      continue;
    }

    closeList();
    html += `<p>${escapeHtml(line)}</p>`;
  }
  closeList();
  html += "</article>";
  return html;
}

function renderReport(formalText, formal, report) {
  if (!formalText && !formal && (!Array.isArray(report) || report.length === 0)) {
    reportOut.innerHTML = '<p class="empty">No report yet.</p>';
    return;
  }

  const formalReport = renderFormalTextBlock(formalText, formal);

  const cards = (Array.isArray(report) ? report : [])
    .map((entry) => {
      const name = escapeHtml(entry.agent_name || "agent");
      const confidence =
        typeof entry.confidence === "number" ? `${Math.round(entry.confidence * 100)}%` : "n/a";
      const payload = escapeHtml(JSON.stringify(entry.output_json ?? {}, null, 2));
      return `
        <article class="item-card">
          <div class="item-top">
            <strong>${name}</strong>
            <span class="tag">${confidence}</span>
          </div>
          <pre>${payload}</pre>
        </article>
      `;
    })
    .join("");

  const appendix = cards
    ? `
      <details class="appendix">
        <summary>Technical Appendix (Raw Agent Outputs)</summary>
        <div class="report-divider"></div>
        <div class="list-view">${cards}</div>
      </details>
    `
    : "";

  reportOut.innerHTML = `${formalReport}${appendix}`;
}

async function pollStatus(taskId) {
  try {
    const data = await getJson(`/status/${taskId}`);
    const status = String(data.status || "unknown").toLowerCase();
    setStatus(status);
    await refreshPlan(taskId);

    if (status === "completed") {
      clearInterval(pollHandle);
      pollHandle = null;
      await refreshReport(taskId);
      setMessage("Task completed.");
      submitBtn.disabled = false;
      return;
    }

    if (status === "failed") {
      clearInterval(pollHandle);
      pollHandle = null;
      setMessage("Task failed. Check backend logs.");
      submitBtn.disabled = false;
    }
  } catch (err) {
    setMessage(`Status polling error: ${err.message}`);
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  submitBtn.disabled = true;
  setMessage("Submitting task...");
  setStatus("queued");
  renderPlan(null);
  renderReport(null);

  if (pollHandle) {
    clearInterval(pollHandle);
    pollHandle = null;
  }

  try {
    const payload = {
      user_id: Number(userIdInput.value),
      input_text: inputText.value.trim(),
    };

    const res = await fetch("/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      throw new Error(await res.text());
    }

    const data = await res.json();
    const taskId = data.task_id;
    taskIdEl.textContent = String(taskId);
    setStatus(String(data.status || "queued").toLowerCase());
    setMessage("Task created. Polling status...");

    await pollStatus(taskId);
    pollHandle = setInterval(() => pollStatus(taskId), 2000);
  } catch (err) {
    setStatus("failed");
    setMessage(`Submit error: ${err.message}`);
    submitBtn.disabled = false;
  }
});
