"""Build the static read-only portfolio demo into site/.

Packages the frontend with two real recorded investigations (one supported,
one inconclusive), both from preserved live artifacts. The result needs no
backend, provider key, or credentials, and contains no execution endpoint,
upload capability, or fault control. Everything is explicitly marked recorded.
"""

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
RUNS = [
    (
        "evals/results/2026-09-14-heldout/test-03-C.json",
        "recorded-supported",
        "Adaptive run C on a held-out case: migration lock contention, diagnosed with citations.",
    ),
    (
        "evals/results/2026-09-14-dev-c2/dev-06-C.json",
        "recorded-inconclusive",
        "Adaptive run C abstains: missing upstream evidence is reported, not replaced by a guess.",
    ),
]


def convert(artifact: dict, run_id: str, note: str) -> dict:
    """Reshape a preserved evaluation artifact into the UI's run+events form."""
    first = artifact["trace"][0]["arguments"]
    events = [
        {
            "sequence": index + 1,
            "kind": "tool_call",
            "created_at": artifact["started_at"],
            "payload": {
                "tool": event["tool"],
                "arguments": event["arguments"],
                "result": event["result"],
            },
        }
        for index, event in enumerate(artifact["trace"])
    ]
    events.append(
        {
            "sequence": 1_000_000,
            "kind": "status",
            "created_at": artifact["started_at"],
            "payload": {"status": "completed", "error": None, "note": note},
        }
    )
    return {
        "id": run_id,
        "question": artifact["question"],
        "system": artifact["system"],
        "scope": {
            "services": first["services"],
            "start": first["start"],
            "end": first["end"],
        },
        "status": "completed",
        "error": None,
        "report": artifact["report"],
        "model_requested": artifact["model_requested"],
        "prompt_sha256": artifact["prompt_sha256"],
        "code_revision": artifact["provenance"]["code_revision"],
        "usage": artifact["usage"],
        "estimated_cost_usd": artifact["estimated_cost_usd"],
        "elapsed_ms": artifact["elapsed_ms"],
        "created_at": artifact["started_at"],
        "started_at": artifact["started_at"],
        "finished_at": None,
        "recorded_note": note,
        "events": events,
    }


def main() -> None:
    if SITE.exists():
        shutil.rmtree(SITE)
    shutil.copytree(
        ROOT / "frontend",
        SITE,
        ignore=shutil.ignore_patterns(
            "Dockerfile", "*.conf", "security.html", "security.js", "security.css"
        ),
    )
    runs = []
    for path, run_id, note in RUNS:
        artifact = json.loads((ROOT / path).read_text())
        assert artifact["mode"] == "live" and artifact["status"] == "completed"
        runs.append(convert(artifact, run_id, note))
    blob = json.dumps({"note": "Recorded live artifacts; no current execution.", "runs": runs})
    for banned in ("api_key", "OPENAI", "sk-", "idempotency"):
        assert banned not in blob, banned
    (SITE / "recorded-runs.json").write_text(blob + "\n")
    index = (
        (SITE / "index.html")
        .read_text()
        .replace('      <a class="ghost" href="security.html">Security review</a>\n', "")
    )
    index = index.replace(
        '<script src="app.js"></script>',
        '<script>window.LG_RECORDED_URL = "recorded-runs.json";</script>\n'
        '  <script src="app.js"></script>',
    )
    (SITE / "index.html").write_text(index)
    print(f"wrote {SITE} with {len(runs)} recorded runs")


if __name__ == "__main__":
    main()
