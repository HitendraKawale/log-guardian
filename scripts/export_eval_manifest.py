"""Regenerate frontend/evaluations.json from published evaluation summaries.

Copies only summary rows (no raw evidence), so the static page stays small and
serves recorded results without a provider key.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BATCHES = [
    ("2026-09-14-dev-abc", "A/B/C development comparison"),
    ("2026-09-14-dev-c2", "C rerun after tool-guidance fix"),
    ("2026-09-14-heldout", "Held-out A/B/C comparison"),
]


def main() -> None:
    manifest = {"note": "Recorded evaluation artifacts; not live execution.", "batches": []}
    for folder, name in BATCHES:
        summary = json.loads((ROOT / "evals/results" / folder / "summary.json").read_text())
        manifest["batches"].append(
            {
                "name": name,
                "folder": folder,
                "evaluation": summary["evaluation"],
                "model": summary["model"],
                "estimated_total_cost_usd": summary["estimated_total_cost_usd"],
                "runs": [
                    {
                        key: run.get(key)
                        for key in (
                            "case_id",
                            "system",
                            "execution_status",
                            "error",
                            "reported_outcome",
                            "expected_outcome",
                            "core_review_pass",
                            "review",
                            "estimated_cost_usd",
                        )
                    }
                    for run in summary["runs"]
                ],
            }
        )
    output = ROOT / "frontend/evaluations.json"
    output.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"wrote {output} with {sum(len(b['runs']) for b in manifest['batches'])} runs")


if __name__ == "__main__":
    main()
