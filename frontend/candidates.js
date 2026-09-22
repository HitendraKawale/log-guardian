// Candidates view. Lists what the label-free trigger selected and lets a
// reviewer dismiss it.
//
// There is no promote button, and that is deliberate rather than unfinished:
// starting an investigation spends provider money, and this page holds only the
// log API key. Promotion needs INVESTIGATION_API_KEY, so it stays an API call
// made by someone who has that key. Putting the spend capability in a browser
// tab would undo the separation the two keys exist to create.
//
// All candidate text is log content and therefore untrusted: every value is
// written with textContent or createTextNode, never innerHTML.
(() => {
  const $ = (id) => document.getElementById(id);
  const API = window.LG.apiBase;
  const authHeaders = window.LG.authHeaders;
  const announce = window.LG.announce;

  // The published recorded demo has no backend. Say so, rather than showing a
  // connection error for a queue that cannot exist there.
  const RECORDED = Boolean(window.LG_RECORDED_URL);

  const text = (value) => document.createTextNode(String(value));

  function cell(content, className) {
    const node = document.createElement("td");
    if (className) node.className = className;
    if (content !== undefined && content !== null) node.append(text(content));
    return node;
  }

  function emptyRow(message) {
    const row = document.createElement("tr");
    const td = cell(message, "empty");
    td.colSpan = 7;
    row.append(td);
    return row;
  }

  function statusBadge(candidate) {
    const span = document.createElement("span");
    span.className = `badge status-${candidate.status}`;
    span.append(text(candidate.status));
    if (candidate.status === "promoted" && candidate.investigation_id) {
      span.title = `investigation ${candidate.investigation_id}`;
    }
    return span;
  }

  function dismissButton(candidate, onDone) {
    const button = document.createElement("button");
    button.className = "ghost";
    button.type = "button";
    button.append(text("Dismiss"));
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        const res = await fetch(`${API}/candidates/${candidate.id}/dismiss`, {
          method: "POST",
          headers: authHeaders(),
        });
        if (!res.ok) {
          announce(`Could not dismiss (${res.status})`);
          button.disabled = false;
          return;
        }
        announce(`Dismissed candidate for ${candidate.service}`);
        onDone();
      } catch {
        announce("Could not reach the API.");
        button.disabled = false;
      }
    });
    return button;
  }

  function scopeTitle(candidate) {
    const scope = candidate.scope || {};
    if (!scope.start || !scope.end) return "";
    return `investigation scope: ${scope.start} to ${scope.end}`;
  }

  function date(value) {
    // SQLite returns naive timestamps; the API contract interprets them as UTC.
    if (!value) return "unknown";
    return new Date(/(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`).toLocaleString();
  }

  function row(candidate, onDone) {
    const tr = document.createElement("tr");
    const time = cell(date(candidate.occurred_at));
    const recent = document.createElement("p");
    recent.append(text(`Last seen: ${date(candidate.last_seen_at || candidate.occurred_at)}; ${candidate.occurrence_count || 1} observations since selection`));
    time.append(recent);
    tr.append(time);
    tr.append(cell(candidate.service));
    tr.append(cell(candidate.level));

    const message = cell(candidate.message, "msg");
    message.title = scopeTitle(candidate);
    tr.append(message);

    const why = cell((candidate.signal_details?.reasons || [candidate.reason]).join(", "));
    const details = candidate.signal_details;
    if (details && Number.isFinite(details.count)) {
      const explanation = document.createElement("p");
      explanation.append(text(`${details.count} errors this minute; baseline ${Number(details.baseline_mean).toFixed(2)}/minute; threshold ${details.threshold}${details.learning ? "; learning baseline" : ""}.`));
      why.append(explanation);
    }
    tr.append(why);

    const status = document.createElement("td");
    status.append(statusBadge(candidate));
    const activity = document.createElement("p");
    activity.append(text(candidate.activity || "legacy"));
    status.append(activity);
    tr.append(status);

    const action = document.createElement("td");
    // Only a "new" candidate can be dismissed; a promoted one keeps its link to
    // the run it started, and hiding that would lose the trail.
    if (candidate.status === "new") {
      action.append(dismissButton(candidate, onDone));
    } else {
      action.append(text("—"));
    }
    tr.append(action);
    return tr;
  }

  function query() {
    const params = new URLSearchParams();
    const status = $("c-status").value;
    const service = $("c-service").value.trim();
    if (status) params.set("status", status);
    if (service) params.set("service", service);
    params.set("limit", "100");
    return params.toString();
  }

  let refreshVersion = 0;

  async function refreshDetectors(version) {
    const node = $("detector-status");
    node.textContent = "Loading detector state.";
    const params = new URLSearchParams({ limit: "100" });
    const service = $("c-service").value.trim();
    if (service) params.set("service", service);
    try {
      const res = await fetch(`${API}/candidates/detectors?${params}`, { headers: authHeaders() });
      if (version !== refreshVersion) return;
      if (!res.ok) {
        node.textContent = `Could not load detector state (${res.status}).`;
        return;
      }
      const payload = await res.json();
      if (version !== refreshVersion) return;
      const lines = (payload.items || []).map((state) =>
        `${state.service}: novelty ${state.novelty_ready ? "ready" : "learning"}; baseline ${state.baseline_ready ? "ready" : "learning"}; ${state.observed} timely logs`
      );
      node.textContent = lines.length ? lines.join(". ") : "No timely logs observed yet.";
      if (payload.total > lines.length) node.append(text(`. Showing ${lines.length} of ${payload.total} services; filter by service to narrow.`));
    } catch {
      if (version === refreshVersion) node.textContent = "Could not reach detector state.";
    }
  }

  async function refresh() {
    const version = ++refreshVersion;
    const body = $("candidates-body");
    if (RECORDED) {
      $("detector-status").textContent = "Detector state is live-only.";
      body.replaceChildren(
        emptyRow("The candidate queue is live-only; this recorded demo has no backend.")
      );
      return;
    }
    refreshDetectors(version);
    try {
      const res = await fetch(`${API}/candidates?${query()}`, { headers: authHeaders() });
      if (version !== refreshVersion) return;
      if (!res.ok) {
        body.replaceChildren(emptyRow(`Could not load candidates (${res.status}).`));
        return;
      }
      const payload = await res.json();
      if (version !== refreshVersion) return;
      const items = payload.items || [];
      if (!items.length) {
        body.replaceChildren(emptyRow("No candidates match this filter."));
        return;
      }
      body.replaceChildren(...items.map((candidate) => row(candidate, refresh)));
    } catch {
      if (version === refreshVersion) body.replaceChildren(emptyRow("Could not reach the API."));
    }
  }

  $("c-refresh").addEventListener("click", refresh);
  $("c-status").addEventListener("change", refresh);
  $("c-service").addEventListener("change", refresh);

  // Load when the tab is opened rather than polling: a review queue changes at
  // human speed, and the logs view already polls.
  document.querySelectorAll('.tab[data-view="candidates"]').forEach((tab) => {
    tab.addEventListener("click", refresh);
  });
})();
