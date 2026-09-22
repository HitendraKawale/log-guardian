# Initial-evidence live batch authorization

The owner explicitly approved this new batch in chat on 2026-09-22, then approved
a local preparation commit and execution after offline checks. No push, PR, merge,
production traffic or follow-on spending is authorized.

- Batch: investigator-initial-evidence-2026-09-22.
- Model: gpt-4.1-mini-2025-04-14, standard service tier, official OpenAI endpoint.
- Ten existing staging cases, stage-01 through stage-10, once each.
- Cases SHA-256: 5d720e4c8af1f7d634f700de5574a36a2d6ed10e6c42072c4cdeb999e0f1dcca.
- At most six model requests per case, sixty total, zero retries.
- Maximum USD 0.10 per case and USD 2 total. Native worker retains USD 0.025/run.
- Existing 1024-output-token, eight-tool, 64-KiB-evidence and 120-second limits remain.
- Production base: 7ea3ef2e5087a778ba49c91b3d0573850cfc111a, merged PR #43.
- Freeze: evals/investigator-security/initial-evidence-live-freeze.json.
- Ledger: the shared git directory's investigator-initial-evidence-2026-09-22 directory.

The existing runner reserves conservatively before every HTTP send, saves decoded
response witnesses before dispatch, refuses a changed candidate, and stops on
ambiguous usage or transport failure. No retry or reuse of unused allowance after
this batch is permitted. An interrupted or partially attempted batch stays closed.
The preceding investigator-security-pilot-2026-09-22 ledger remains untouched.

## Procedure and interpretation

- [ ] Change only batch identity, base and authorization source in the existing runner.
- [ ] Run offline tests, verify unchanged production code and original ledger hashes,
  generate a new candidate freeze, and commit preparation locally.
- [ ] Execute once with explicit digest and the new shared ledger.
- [ ] Preserve the original files and lossless databases, then derive exposure,
  model-proposal versus server-origin counts, policy and report findings separately.

All fixtures are synthetic and self-authored. Reviewer notes remain outside runtime
inputs. First-query exposure is checked against actual provider request bodies, not
fixture availability. Schema/citation validity is not semantic correctness. Content
harms, tool attempts, scope enforcement and capture completeness are separate outcomes.
Independent review is pending. No accuracy or detector-recall claim follows from zero
observed violations. Estimates and conservative reservations are not billing receipts.

Pricing was checked earlier on the same date and is preserved in
investigator-pilot-pricing.md. This batch changes no model, pricing or transport logic.
The freeze hashes the authorization, runner, dependencies and production source.
The freeze itself is excluded from its digest to avoid a circular hash.
