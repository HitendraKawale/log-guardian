# C rerun after query_logs guidance fix

One change from the [first comparison](../2026-09-14-dev-abc/README.md): the `query_logs` tool description now says to start unfiltered and that `text` matches only the message field, literally. Prompt, schema, model and corpus are unchanged. A/B do not receive tool descriptions and were not rerun; their `2026-09-14-dev-abc` results remain the comparison.

Result: **5/8 core review passes** (was 4/8), 8/8 completed (was 6/8), 20 requests, estimated **$0.01367280** on clean `998ed13`.

- Fixed: dev-01 and dev-03 now query unfiltered first and produce grounded diagnoses; no model-budget or invalid-report failures.
- Still failing: dev-02, dev-05 filter first (`connection`, `ERROR`) and abstain unnecessarily. dev-04 regressed in kind: it previously gave an ungrounded supported diagnosis, now abstains after a filtered gateway query missed the NXDOMAIN/configuration records.
- dev-06 abstention remains correct.

C remains below A (7/8) and B (7/8) and costs about 2x A. The guidance reduced hard failures but did not fix filter-first behavior in half the failing cases. Unnecessary abstention replaced wrong answers, which is the preferable failure direction but still a failure.

Review is by the coding assistant, not independent or blind. Eight authored cases; no reliability claim. Rerunning C is not a paired comparison with A/B on identical dates, but all inputs A/B receive are byte-identical between the two batches.
