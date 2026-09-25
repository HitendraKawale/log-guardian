# Verifier packet v2

Contract: `docs/plans/report-verifier-contract-v2.md`.

The first fourteen input and label rows are unchanged from `evals/report-verifier/`.
Four authored augmentations add direct verifier-targeting instructions and benign
quoted counterparts. There are eight expected acceptable reports, nine semantic
negatives and one local-invalid citation control. These are development judgments,
not human-validated labels or held-out measurements.

Only inputs.jsonl is eligible model input, one item per request with host-owned
policy. Keep labels.jsonl, manifest.json, this README and build_packet.py outside
model inputs. The manifest identifies synthetic additions that were never delivered
to the investigator. No runtime archive was edited to create them.

response.schema.json is generated from the offline boundary's Review model. Responses
use schema_version=2; existing inputs retain schema_version=1. Supported and contradicted
claims require at least one quoted reference. The host checks reference membership,
quote presence, supported references belonging to the original finding's citations,
exact coverage and hash binding. No model may choose the final acceptance flag.

From the repository root:

```bash
.venv/bin/python evals/report-verifier-v2/build_packet.py --output /tmp/new-verifier-v2
cd evals && ../.venv/bin/python -m pytest tests/test_report_verifier_boundary.py tests/test_report_verifier_packet.py
```

Use a new output directory. The builder refuses existing packet files. The tests
reproduce output bytes, preserve v1 rows, reject malformed/unbound responses, replay
the original empty-reference counterexample, and aggregate scripted verdicts for the
new probes. They do not execute a model or prove prompt-injection resistance.

A deliberate negative-limit check supplies a structurally valid but semantically
wrong passing verdict with genuine quotes; the boundary accepts it. This is the
remaining semantic problem, not a tested defense. Production use requires a separate
model experiment that measures missed defects and false rejections. No API client,
production integration, report repair or paid authorization exists here.
