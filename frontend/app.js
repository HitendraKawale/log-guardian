// Log Guardian dashboard. Talks to the ingestion service REST API.
// Override the API base by setting ?api=http://host:port in the URL.
const API_BASE =
  new URLSearchParams(location.search).get("api") || "http://localhost:8000";

const $ = (id) => document.getElementById(id);

function setStatus(online) {
  const dot = $("status-dot");
  dot.className = "dot " + (online ? "online" : "offline");
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
  const scored = logs.filter((l) => l.anomaly_score !== null);
  const avg = scored.length
    ? scored.reduce((s, l) => s + l.anomaly_score, 0) / scored.length
    : 0;
  $("stat-total").textContent = total;
  $("stat-anomalies").textContent = anomalies;
  $("stat-rate").textContent = total ? Math.round((anomalies / total) * 100) + "%" : "0%";
  $("stat-score").textContent = avg.toFixed(2);
}

function renderLogs(logs) {
  const body = $("logs-body");
  if (!logs.length) {
    body.innerHTML = '<tr><td colspan="6" class="empty">No logs yet.</td></tr>';
    return;
  }
  body.innerHTML = logs
    .map((l) => {
      const time = new Date(l.timestamp).toLocaleTimeString();
      return `<tr class="${l.is_anomaly ? "anomaly" : ""}">
        <td class="time">${time}</td>
        <td>${l.service}</td>
        <td><span class="badge lvl-${l.level}">${l.level}</span></td>
        <td class="msg" title="${escapeHtml(l.message)}">${escapeHtml(l.message)}</td>
        <td>${scoreBar(l.anomaly_score)}</td>
        <td>${severityBadge(l.predicted_severity)}</td>
      </tr>`;
    })
    .join("");
}

function escapeHtml(s) {
  return s.replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])
  );
}

async function refresh() {
  try {
    const res = await fetch(`${API_BASE}/logs?limit=50`);
    if (!res.ok) throw new Error(res.status);
    const logs = await res.json();
    setStatus(true);
    renderStats(logs);
    renderLogs(logs);
  } catch (err) {
    setStatus(false);
  }
}

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
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(res.status);
    const log = await res.json();
    msg.textContent = `Ingested #${log.id} — ${log.status}, score ${
      log.anomaly_score ?? "n/a"
    }`;
    refresh();
  } catch (err) {
    msg.textContent = "Failed to ingest log (is the API running?)";
  }
});

refresh();
setInterval(refresh, 3000);
