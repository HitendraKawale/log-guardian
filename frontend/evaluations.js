// Read-only view over published evaluation artifacts. Everything here is
// recorded data shipped with the frontend; nothing triggers live execution.
(() => {
  const container = document.getElementById("eval-batches");
  const text = (value) => document.createTextNode(String(value));

  function element(tag, className, content) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (content !== undefined) node.append(text(content));
    return node;
  }

  function batchSection(batch) {
    const section = element("section", "eval-batch");
    section.append(element("h3", "", batch.name));
    section.append(element("p", "eval-desc", batch.evaluation));
    const facts = element("p", "eval-facts",
      `model ${batch.model} · ${batch.runs.length} runs · ` +
      `estimated $${batch.estimated_total_cost_usd} · recorded`);
    section.append(facts);
    const table = element("table", "logs");
    const head = element("thead");
    const headRow = element("tr");
    for (const title of ["Case", "System", "Status", "Reported", "Expected", "Review"]) {
      headRow.append(element("th", "", title));
    }
    head.append(headRow);
    const body = element("tbody");
    for (const run of batch.runs) {
      const row = element("tr", run.core_review_pass === false ? "anomaly" : "");
      row.append(
        element("td", "", run.case_id),
        element("td", "", run.system),
        element("td", "", run.execution_status + (run.error ? ` (${run.error})` : "")),
        element("td", "", run.reported_outcome || "—"),
        element("td", "", run.expected_outcome),
        element("td", "msg", run.review || "")
      );
      body.append(row);
    }
    table.append(head, body);
    section.append(table);
    return section;
  }

  fetch("evaluations.json")
    .then((res) => (res.ok ? res.json() : Promise.reject(res.status)))
    .then((manifest) => {
      container.replaceChildren(...manifest.batches.map(batchSection));
    })
    .catch(() => {
      container.replaceChildren(
        element("p", "empty", "No published evaluation manifest is available.")
      );
    });
})();
