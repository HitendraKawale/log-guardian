// Investigations view. Polls ordered events with a cursor while a run is
// active; renders reports with clickable citations backed by recorded tool
// evidence. All log/model text is rendered as text, never as HTML.
(() => {
  const $ = (id) => document.getElementById(id);
  const API = window.LG.apiBase;
  const authHeaders = window.LG.authHeaders;
  const announce = window.LG.announce;

  const RECORDED_URL = window.LG_RECORDED_URL || null;
  let recordedRuns = new Map();

  let selected = null;
  let pollTimer = null;
  let eventCursor = 0;
  let evidenceIndex = new Map();

  // --- view switching -------------------------------------------------------
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((t) =>
        t.classList.toggle("active", t === tab)
      );
      for (const view of ["investigations", "logs", "evaluations"]) {
        $(`view-${view}`).hidden = view !== tab.dataset.view;
      }
      if (tab.dataset.view !== "investigations") stopPolling();
      announce(`${tab.textContent} view`);
    });
  });

  const text = (value) => document.createTextNode(String(value));

  function element(tag, className, content) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (content !== undefined) node.append(text(content));
    return node;
  }

  if (RECORDED_URL) {
    const banner = element(
      "p",
      "callout recorded-banner",
      "Recorded demo: these are preserved live investigation artifacts. " +
        "Nothing on this page executes a model or contacts a backend."
    );
    document.querySelector("#view-investigations").prepend(banner);
    const form = $("inv-form");
    for (const control of form.querySelectorAll("input, select, button")) {
      control.disabled = true;
    }
    $("inv-form-msg").textContent = "Live execution is disabled in the recorded demo.";
  }


  // --- history list ---------------------------------------------------------
  async function loadList() {
    const list = $("inv-list");
    let runs;
    if (RECORDED_URL) {
      try {
        const res = await fetch(RECORDED_URL);
        const manifest = await res.json();
        recordedRuns = new Map(manifest.runs.map((run) => [run.id, run]));
        runs = manifest.runs;
      } catch {
        list.replaceChildren(element("li", "empty", "Could not load recorded runs."));
        return;
      }
      renderList(runs, list);
      return;
    }
    try {
      const res = await fetch(`${API}/investigations`, { headers: authHeaders() });
      if (res.status === 503) {
        list.replaceChildren(
          element("li", "empty", "Investigations are disabled on this server (no key configured).")
        );
        return;
      }
      if (res.status === 401) {
        list.replaceChildren(element("li", "empty", "Unauthorized — set the API key above."));
        return;
      }
      if (!res.ok) throw new Error(res.status);
      runs = await res.json();
    } catch {
      list.replaceChildren(element("li", "empty", "Could not load investigations."));
      return;
    }
    renderList(runs, list);
  }

  function renderList(runs, list) {
    if (!runs.length) {
      list.replaceChildren(element("li", "empty", "No investigations yet."));
      return;
    }
    list.replaceChildren(
      ...runs.map((run) => {
        const item = element("li", `inv-item status-${run.status}`);
        const button = element("button", "inv-item-btn");
        button.append(
          element("span", "inv-item-q", run.question),
          element("span", `badge st-${run.status}`, run.status)
        );
        button.addEventListener("click", () => select(run.id));
        item.append(button);
        return item;
      })
    );
  }

  // --- detail + polling -----------------------------------------------------
  function stopPolling() {
    clearInterval(pollTimer);
    pollTimer = null;
  }

  async function select(id) {
    stopPolling();
    selected = id;
    eventCursor = 0;
    evidenceIndex = new Map();
    $("inv-events").replaceChildren();
    $("inv-detail-empty").hidden = true;
    $("inv-detail").hidden = false;
    $("inv-report-section").hidden = true;
    if (RECORDED_URL) {
      const run = recordedRuns.get(id);
      for (const event of run.events) appendEvent(event);
      renderRun(run);
      return;
    }
    await refreshDetail();
    pollTimer = setInterval(refreshDetail, 1000);
  }

  const TERMINAL = new Set(["completed", "failed", "cancelled"]);

  async function refreshDetail() {
    if (!selected) return;
    let run;
    try {
      const res = await fetch(`${API}/investigations/${selected}`, { headers: authHeaders() });
      if (!res.ok) throw new Error(res.status);
      run = await res.json();
    } catch {
      $("inv-error").hidden = false;
      $("inv-error").replaceChildren(text("Could not load this run."));
      stopPolling();
      return;
    }
    renderRun(run);
    await pollEvents();
    if (TERMINAL.has(run.status)) {
      stopPolling();
      loadList();
    }
  }

  function renderRun(run) {
    $("inv-question").replaceChildren(text(run.question));
    const status = $("inv-status");
    status.className = `badge st-${run.status}`;
    status.replaceChildren(text(run.status));
    $("inv-cancel").hidden = !["queued", "running"].includes(run.status);
    const meta = $("inv-meta");
    meta.replaceChildren();
    const pairs = [
      ["System", run.system],
      ["Scope", `${run.scope.services.join(", ")} · ${run.scope.start} → ${run.scope.end}`],
      ["Model", run.model_requested || "—"],
      ["Cost (est.)", run.estimated_cost_usd ? `$${run.estimated_cost_usd}` : "—"],
      ["Elapsed", run.elapsed_ms ? `${(run.elapsed_ms / 1000).toFixed(2)}s` : "—"],
    ];
    for (const [label, value] of pairs) {
      meta.append(element("dt", "", label), element("dd", "", value));
    }
    const error = $("inv-error");
    if (run.status === "failed") {
      error.hidden = false;
      error.replaceChildren(
        text(`This run failed: ${run.error}. Partial evidence below is preserved.`)
      );
    } else if (run.status === "cancelled") {
      error.hidden = false;
      error.replaceChildren(text("This run was cancelled. No conclusion was produced."));
    } else {
      error.hidden = true;
    }
    if (run.report) renderReport(run.report);
  }

  async function pollEvents() {
    try {
      const res = await fetch(
        `${API}/investigations/${selected}/events?after=${eventCursor}`,
        { headers: authHeaders() }
      );
      if (!res.ok) return;
      for (const event of await res.json()) {
        eventCursor = Math.max(eventCursor, event.sequence);
        appendEvent(event);
      }
    } catch {
      /* transient; next poll retries */
    }
  }

  function appendEvent(event) {
    const item = element("li", `event event-${event.kind}`);
    if (event.kind === "tool_call") {
      const { tool, arguments: args, result } = event.payload;
      item.append(element("span", "event-tool", tool));
      item.append(element("code", "event-args", JSON.stringify(args)));
      const items = result?.items || [];
      const summary = result?.error
        ? `error: ${result.error}`
        : `${items.length} item(s)${result?.truncated ? " (truncated)" : ""}`;
      item.append(element("span", "event-summary", summary));
      for (const evidence of items) {
        evidenceIndex.set(evidence.evidence_id, evidence);
      }
    } else {
      item.append(element("span", "event-status", JSON.stringify(event.payload)));
    }
    $("inv-events").append(item);
  }

  // --- report + citations ---------------------------------------------------
  function citationButton(id) {
    const known = evidenceIndex.has(id);
    const button = element("button", `citation${known ? "" : " unknown"}`, id);
    button.type = "button";
    button.addEventListener("click", () => openDrawer(id));
    return button;
  }

  function findingBlock(finding) {
    const block = element("div", "finding");
    block.append(element("p", "finding-claim", finding.claim));
    const row = element("p", "citations");
    for (const id of finding.evidence_ids) row.append(citationButton(id), text(" "));
    block.append(row);
    return block;
  }

  function renderReport(report) {
    $("inv-report-section").hidden = false;
    const outcome = $("inv-outcome");
    outcome.className = `outcome-${report.outcome}`;
    outcome.replaceChildren(
      text(report.outcome === "supported" ? "Supported conclusion" : "Inconclusive")
    );
    const container = $("inv-report");
    container.replaceChildren();
    if (report.outcome === "inconclusive") {
      container.append(
        element(
          "p",
          "callout",
          "The evidence does not establish a cause. Missing evidence is listed below rather than a guessed diagnosis."
        )
      );
    }
    const sections = [
      ["Likely cause", report.likely_cause ? [report.likely_cause] : []],
      ["Observations", report.observations],
      ["Alternatives", report.alternatives],
    ];
    for (const [title, findings] of sections) {
      if (!findings.length) continue;
      container.append(element("h4", "", title));
      for (const finding of findings) container.append(findingBlock(finding));
    }
    const lists = [
      ["Missing evidence", report.missing_evidence],
      ["Suggested checks", report.suggested_checks],
    ];
    for (const [title, entries] of lists) {
      if (!entries.length) continue;
      container.append(element("h4", "", title));
      const list = element("ul");
      for (const entry of entries) list.append(element("li", "", entry));
      container.append(list);
    }
  }

  function openDrawer(id) {
    const drawer = $("citation-drawer");
    $("citation-title").replaceChildren(text(id));
    const evidence = evidenceIndex.get(id);
    $("citation-body").replaceChildren(
      text(
        evidence
          ? JSON.stringify(evidence.content, null, 2)
          : "This citation does not match any recorded evidence for this run."
      )
    );
    drawer.hidden = false;
    $("citation-close").focus();
    announce(`Evidence ${id} opened`);
  }

  $("citation-close").addEventListener("click", () => {
    $("citation-drawer").hidden = true;
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") $("citation-drawer").hidden = true;
  });

  // --- create + cancel ------------------------------------------------------
  $("inv-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.target;
    const message = $("inv-form-msg");
    const services = form.services.value
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    const body = {
      question: form.question.value,
      system: form.system.value,
      scope: {
        services,
        start: new Date(form.start.value).toISOString(),
        end: new Date(form.end.value).toISOString(),
      },
    };
    try {
      const res = await fetch(`${API}/investigations`, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        message.textContent = `Could not start (${res.status}): ${
          typeof detail.detail === "string" ? detail.detail : "invalid request"
        }`;
        return;
      }
      const run = await res.json();
      message.textContent = "";
      announce("Investigation queued");
      await loadList();
      select(run.id);
    } catch {
      message.textContent = "Could not reach the API.";
    }
  });

  $("inv-cancel").addEventListener("click", async () => {
    if (!selected) return;
    try {
      const res = await fetch(`${API}/investigations/${selected}/cancel`, {
        method: "POST",
        headers: authHeaders(),
      });
      if (res.ok) {
        announce("Cancellation requested");
        refreshDetail();
      }
    } catch {
      /* next poll shows current state */
    }
  });

  $("inv-reload").addEventListener("click", loadList);

  // Default the time window to the last 15 minutes, in local time.
  const now = new Date();
  const earlier = new Date(now.getTime() - 15 * 60 * 1000);
  const local = (d) => new Date(d.getTime() - d.getTimezoneOffset() * 60000)
    .toISOString().slice(0, 19);
  document.querySelector('#inv-form [name="start"]').value = local(earlier);
  document.querySelector('#inv-form [name="end"]').value = local(now);

  loadList();
})();
