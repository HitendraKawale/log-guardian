// Log Guardian dashboard. Talks to the ingestion service REST API.
// Override the API base by setting ?api=http://host:port in the URL.
const API_BASE =
  new URLSearchParams(location.search).get("api") || "http://localhost:8000";

const $ = (id) => document.getElementById(id);

let refreshTimer = null;
let paused = false;

// --- API key (persisted locally) ------------------------------------------
const keyInput = $("api-key");
keyInput.value = localStorage.getItem("lg_api_key") || "";
keyInput.addEventListener("change", () => {
  localStorage.setItem("lg_api_key", keyInput.value.trim());
  refresh();
});

function authHeaders(extra = {}) {
  const key = keyInput.value.trim();
  return key ? { ...extra, "X-API-Key": key } : extra;
}

// --- rendering helpers ------------------------------------------------------
function setStatus(online) {
  $("status-dot").className = "dot " + (online ? "online" : "offline");
  $("status-text").textContent = online ? "connected" : "offline";
}

function severityBadge(sev) {
  if (!sev) return '<span class="sev-none">&mdash;</span>';
  return `<span class="badge sev-${sev}">${sev}</span>`;
}

function scoreBar(score) {
  if (score === null || score === undefined) return '<span class="sev-none">&mdash;</span>';
  const pct = Math.round(score * 100);
  const color = score >= 0.7 ? "#f85149" : score >= 0.3 ? "#d29922" : "#3fb950";
  return `<div class="scorebar" title="${score.toFixed(2)}">
            <span style="width:${pct}%;background:${color}"></span>
          </div>`;
}

function renderStats(logs) {
  const total = logs.length;
  const anomalies = logs.filter((l) => l.is_anomaly).length;
  $("stat-total").textContent = total;
  $("stat-anomalies").textContent = anomalies;
  $("stat-rate").textContent = total ? Math.round((anomalies / total) * 100) + "%" : "0%";

  const counts = { low: 0, medium: 0, high: 0 };
  logs.forEach((l) => { if (l.predicted_severity) counts[l.predicted_severity]++; });
  const max = Math.max(1, ...Object.values(counts));
  $("sevbars").innerHTML = ["low", "medium", "high"]
    .map(
      (s) => `<div class="sevbar-row">
        <span class="sevbar-label sev-${s}">${s}</span>
        <span class="sevbar-track"><span class="sevbar-fill fill-${s}" style="width:${(counts[s] / max) * 100}%"></span></span>
        <span class="sevbar-count">${counts[s]}</span>
      </div>`
    )
    .join("");
}

function escapeHtml(s) {
  return s.replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])
  );
}

function feedbackCell(l) {
  if (l.true_label !== null && l.true_label !== undefined) {
    const label = l.true_label ? "anomaly" : "normal";
    return `<span class="labeled sev-${l.true_label ? "high" : "low"}">labeled: ${label}</span>`;
  }
  return `<span class="fb-buttons">
    <button class="fb-btn fb-anom" data-id="${l.id}" data-anom="1" title="mark as anomaly">anomaly</button>
    <button class="fb-btn fb-norm" data-id="${l.id}" data-anom="0" title="mark as normal">normal</button>
  </span>`;
}

function renderLogs(logs) {
  const body = $("logs-body");
  if (!logs.length) {
    body.innerHTML = '<tr><td colspan="7" class="empty">No logs match.</td></tr>';
    return;
  }
  body.innerHTML = logs
    .map((l) => {
      const time = new Date(l.timestamp).toLocaleTimeString();
      return `<tr class="${l.is_anomaly ? "anomaly" : ""}">
        <td class="time">${time}</td>
        <td>${escapeHtml(l.service)}</td>
        <td><span class="badge lvl-${l.level}">${l.level}</span></td>
        <td class="msg" title="${escapeHtml(l.message)}">${escapeHtml(l.message)}</td>
        <td>${scoreBar(l.anomaly_score)}</td>
        <td>${severityBadge(l.predicted_severity)}</td>
        <td>${feedbackCell(l)}</td>
      </tr>`;
    })
    .join("");
}

async function submitFeedback(id, isAnomaly) {
  try {
    await fetch(`${API_BASE}/logs/${id}/feedback`, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ is_anomaly: isAnomaly }),
    });
    refresh();
  } catch (err) {
    /* ignore; next refresh will reflect state */
  }
}

// Delegate clicks from the feedback buttons.
$("logs-body").addEventListener("click", (e) => {
  const btn = e.target.closest(".fb-btn");
  if (!btn) return;
  submitFeedback(Number(btn.dataset.id), btn.dataset.anom === "1");
});

async function refreshModel() {
  try {
    const res = await fetch(`${API_BASE}/model/info`, { headers: authHeaders() });
    if (!res.ok) return;
    const info = await res.json();
    const badge = $("model-badge");
    if (info.current_version) {
      const drift = info.drift ? ` · drift ${info.drift.drift}` : "";
      badge.textContent = `model ${info.current_version}${drift}`;
      badge.title = info.current && info.current.metrics
        ? `ROC-AUC ${info.current.metrics.roc_auc} · ${info.current.source}`
        : "";
    } else {
      badge.textContent = info.analyzer === "heuristic" ? "heuristic" : "";
    }
  } catch (err) {
    /* leave badge as-is */
  }
}

// --- data fetching ----------------------------------------------------------
function queryString() {
  const params = new URLSearchParams({ limit: "50" });
  const service = $("f-service").value.trim();
  const level = $("f-level").value;
  if (service) params.set("service", service);
  if (level) params.set("level", level);
  if ($("f-anomalous").checked) params.set("anomalous", "true");
  return params.toString();
}

async function refresh() {
  try {
    const res = await fetch(`${API_BASE}/logs?${queryString()}`, {
      headers: authHeaders(),
    });
    if (!res.ok) throw new Error(res.status);
    const logs = await res.json();
    setStatus(true);
    renderStats(logs);
    renderLogs(logs);
  } catch (err) {
    setStatus(false);
  }
}

// --- controls ---------------------------------------------------------------
["f-service", "f-level", "f-anomalous"].forEach((id) =>
  $(id).addEventListener("input", refresh)
);

$("toggle-refresh").addEventListener("click", () => {
  paused = !paused;
  $("toggle-refresh").innerHTML = paused ? "&#9654; Resume" : "&#10073;&#10073; Pause";
  if (paused) {
    clearInterval(refreshTimer);
  } else {
    refresh();
    refreshTimer = setInterval(refresh, 3000);
  }
});

$("log-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const payload = {
    service: form.service.value,
    level: form.level.value,
    message: form.message.value,
    timestamp: new Date().toISOString(),
  };
  const msg = $("form-msg");
  try {
    const res = await fetch(`${API_BASE}/logs`, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(payload),
    });
    if (res.status === 401) { msg.textContent = "Unauthorized — check the API key."; return; }
    if (!res.ok) throw new Error(res.status);
    const log = await res.json();
    msg.textContent = `Ingested #${log.id} — ${log.status}, score ${log.anomaly_score ?? "n/a"}`;
    refresh();
  } catch (err) {
    msg.textContent = "Failed to ingest log (is the API running?)";
  }
});

refresh();
refreshModel();
refreshTimer = setInterval(refresh, 3000);
setInterval(refreshModel, 15000);
