// Explicit uploads only. Credentials stay in memory; all evidence renders as text.
(() => {
  const $ = (id) => document.getElementById(id);
  const element = (tag, value) => {
    const node = document.createElement(tag);
    if (value !== undefined) node.textContent = String(value);
    return node;
  };
  let sources = [], maxBytes = 0, offset = 0, generation = 0, detailVersion = 0;
  let pending = null;
  const controllers = new Set();
  const message = (value) => { $("security-message").textContent = value; };
  $("security-api").value = new URLSearchParams(location.search).get("api") || "http://localhost:8000";

  function destination() {
    const url = new URL($("security-api").value);
    const loopback = ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname) || url.hostname.endsWith(".localhost");
    if (url.username || url.password || url.search || url.hash || url.pathname !== "/" ||
        !(url.protocol === "https:" || (url.protocol === "http:" && loopback))) {
      throw new Error("Use an HTTPS API origin, or HTTP on localhost, without a path or credentials.");
    }
    return url.origin;
  }

  async function request(path, options = {}) {
    const epoch = generation;
    const controller = new AbortController();
    controllers.add(controller);
    const timer = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(destination() + path, {
        ...options, credentials: "omit", redirect: "error", cache: "no-store",
        signal: controller.signal,
        headers: { "X-API-Key": $("security-key").value, ...options.headers },
      });
      if (epoch !== generation) throw new Error("Connection changed; reconnect to review this server.");
      const data = await response.json();
      if (!response.ok) throw new Error(`HTTP ${response.status}: ${typeof data.detail === "string" ? data.detail : "Invalid request"}`);
      return { data, status: response.status };
    } finally {
      clearTimeout(timer);
      controllers.delete(controller);
    }
  }

  function invalidate() {
    generation++;
    for (const controller of controllers) controller.abort();
    sources = [];
    pending = null;
    $("security-import").hidden = true;
    $("security-detail").hidden = true;
    $("security-empty").hidden = false;
    $("security-history").replaceChildren(element("li", "Reconnect to load history."));
    for (const id of ["security-reload", "security-previous", "security-next"]) $(id).disabled = true;
    message("Connection settings changed. Reconnect before importing.");
  }
  $("security-api").addEventListener("input", invalidate);
  $("security-key").addEventListener("input", invalidate);

  async function history() {
    const { data } = await request(`/security/cases?limit=25&offset=${offset}`);
    $("security-history").replaceChildren(...data.map((item) => {
      const li = element("li");
      const button = element("button", `${item.scope.services.join(", ")} / ${item.input_records} input records / ${item.id.slice(0, 8)}`);
      button.className = "inv-item-btn";
      button.type = "button";
      button.addEventListener("click", async () => {
        const version = ++detailVersion;
        try {
          const result = await request(`/security/cases/${encodeURIComponent(item.id)}`);
          if (version === detailVersion) render(result.data);
        } catch (error) { message(error.message || "Could not load review."); }
      });
      li.append(button);
      return li;
    }));
    if (!data.length) $("security-history").append(element("li", "No saved reviews in this page."));
    $("security-previous").disabled = offset === 0;
    $("security-next").disabled = data.length < 25;
  }

  $("security-connect").addEventListener("submit", async (event) => {
    event.preventDefault();
    const epoch = generation;
    const button = event.target.querySelector("button");
    button.disabled = true;
    message("Loading owner-configured sources...");
    try {
      const { data } = await request("/security/sources");
      if (epoch !== generation) return;
      sources = data.sources;
      maxBytes = data.max_bytes;
      $("security-source-files").replaceChildren(...sources.map((source, index) => {
        const block = element("div");
        const label = element("label", `${source.source_id} log file`);
        const input = element("input");
        input.type = "file";
        input.required = true;
        input.id = `security-file-${index}`;
        label.append(input);
        block.append(label, element("small", `${source.service}: ${source.format}. Request namespace: ${source.request_namespace || "not configured"}.`));
        return block;
      }));
      $("security-import").hidden = false;
      $("security-reload").disabled = false;
      offset = 0;
      await history();
      message("Sources loaded. Files are sent only when you choose Save review.");
    } catch (error) {
      $("security-import").hidden = true;
      message(error.message || "Connection failed.");
    } finally { button.disabled = false; }
  });

  $("security-import").addEventListener("submit", async (event) => {
    event.preventDefault();
    const epoch = generation;
    const button = event.target.querySelector("button[type=submit]");
    button.disabled = true;
    let dispatched = false;
    try {
      const selected = sources.map((source, index) => [source.source_id, $(`security-file-${index}`).files[0]]);
      if (selected.some(([, file]) => !file) || selected.reduce((n, [, file]) => n + file.size, 0) > maxBytes) {
        throw new Error("Select every source file with at most 1 MiB combined.");
      }
      const logs = {};
      for (const [name, file] of selected) logs[name] = new TextDecoder("utf-8", { fatal: true }).decode(await file.arrayBuffer());
      if (epoch !== generation) return;
      const body = JSON.stringify({ scope: {
        services: [...new Set(sources.map((source) => source.service))],
        start: $("security-start").value, end: $("security-end").value,
      }, logs });
      if (!pending || pending.body !== body) pending = { body, key: crypto.randomUUID() };
      dispatched = true;
      message("Validating and saving evidence...");
      const result = await request("/security/cases", { method: "POST", body,
        headers: { "Content-Type": "application/json", "Idempotency-Key": pending.key } });
      if (epoch !== generation) return;
      detailVersion++;
      render(result.data);
      offset = 0;
      await history();
      message(result.status === 200 ? "Existing review loaded. No duplicate import created." : "Review saved. No model called.");
    } catch (error) {
      message(`${error.message || "Upload failed."}${dispatched ? " If delivery is uncertain, retry unchanged files on this page to reuse the import key." : ""}`);
    } finally { button.disabled = false; }
  });

  function render(saved) {
    const report = saved.report;
    $("security-empty").hidden = true;
    $("security-detail").hidden = false;
    $("security-title").textContent = `${report.links.length} linked requests`;
    const outcomes = Object.values(report.sources).reduce((total, source) => {
      for (const key of Object.keys(total)) total[key] += source.auth_outcomes[key];
      return total;
    }, { success: 0, failure: 0, unavailable: 0 });
    $("security-outcomes").textContent = `${outcomes.failure} failures, ${outcomes.success} success, ${outcomes.unavailable} unavailable.`;
    $("security-scope").textContent = `${report.scope.services.join(", ")}: ${report.scope.start} to ${report.scope.end}. ${report.input_records} input records; ${report.duplicate_records} duplicate deliveries.`;
    $("security-gaps").replaceChildren(...(report.gaps.length ? report.gaps.map((gap) => gap.replaceAll("_", " ")) : ["No structural gaps found in supplied records. Collection completeness remains unknown."]).map((gap) => element("li", gap)));
    $("security-counts").replaceChildren(...Object.entries(report.sources).map(([name, counts]) => element("li", `${name}: ${counts.records} unique records, ${counts.distinct_client_addresses} observed addresses, ${counts.distinct_account_refs} account references. These are not actor counts.`)));
    const evidence = new Map();
    $("security-timeline").replaceChildren(...report.timeline.map((row) => {
      const details = element("details");
      const summary = element("summary", `${row.event_time} / ${row.evidence.join(" / ")} / ${row.auth_outcome || `HTTP ${row.http_status ?? "unknown"}`}`);
      const pre = element("pre", JSON.stringify(row, null, 2));
      pre.className = "citation-body";
      details.append(summary, pre);
      evidence.set(JSON.stringify(row.evidence), details);
      return details;
    }));
    const citation = (ref) => {
      const button = element("button", JSON.stringify(ref));
      button.type = "button";
      button.className = "citation";
      button.addEventListener("click", () => {
        const details = evidence.get(JSON.stringify(ref));
        if (!details) { message("Evidence reference is absent from the saved timeline."); return; }
        details.open = true;
        details.querySelector("summary").focus();
        details.scrollIntoView({ block: "nearest" });
      });
      return button;
    };
    $("security-links").replaceChildren(...report.links.map((link) => {
      const li = element("li", `${link.request_namespace} / ${link.request_id}: `);
      li.append(citation(link.gateway), citation(link.authentication));
      return li;
    }));
    $("security-unlinked").replaceChildren(...report.ambiguous_groups.map((group) => {
      const li = element("li", `Ambiguous request ${group.request_namespace} / ${group.request_id}: `);
      li.append(...group.evidence.map(citation));
      return li;
    }));
    for (const ref of report.unlinked) {
      const li = element("li", "Unlinked: ");
      li.append(citation(ref));
      $("security-unlinked").append(li);
    }
    if (!report.unlinked.length) $("security-unlinked").append(element("li", "Every supplied record belongs to a confirmed pair."));
    $("security-provenance").textContent = JSON.stringify({ id: saved.id, created_at: saved.created_at,
      request_sha256: saved.request_sha256, input_hashes: saved.input_hashes,
      source_snapshot: saved.source_snapshot }, null, 2);
  }
  for (const [id, step] of [["security-reload", 0], ["security-previous", -25], ["security-next", 25]]) {
    $(id).addEventListener("click", async () => {
      offset = Math.max(0, offset + step);
      try { await history(); } catch (error) { message(error.message || "Could not load history."); }
    });
  }
})();
