# Delivery tracker

The approved technical scope is in [the agentic Log Guardian plan](2026-09-11-agentic-log-guardian.md). This document maps that scope to GitHub delivery. Creating an issue does not complete its implementation steps.

## Workflow

- GitHub issues own scope, dependencies, acceptance criteria, and verification evidence.
- Use the existing `enhancement` and `documentation` labels. Add `ready-for-agent` only when prerequisites and approvals are satisfied.
- Milestones describe deliverables, not promised dates.
- One issue-linked branch per reviewable change: `feat/<issue>-<slug>`, with PRs targeting `main`, or the prerequisite branch for a clearly documented stacked PR. Retarget stacked PRs after their prerequisite merges. Split an issue into multiple PRs if that makes review smaller; do not combine unrelated issues.
- PR bodies name the issue, describe the observable change, list commands and relevant output, and state omissions. Screenshots and actual browser checks accompany UI changes.
- Keep commits focused. Commit, push, and PR publication still require the user's authorization; do not silently infer that permission from technical-plan approval.
- Do not enable branch protection, change repository permissions, or publish a hosted service without separate approval.
- Paid model evaluations require an explicit model and spend allowance. A scripted provider test is not a live evaluation.
- Close an issue only when every acceptance criterion has evidence. Update plan checkboxes only for completed work, never merely because tickets exist.

## Milestones and issues

| Ticket | Milestone | Deliverable | Blocked by | Plan steps |
| --- | --- | --- | --- | --- |
| T01 | Evaluated investigation core | Versioned incident cases with isolated labels and corpus validation | None | 1 |
| T02 | Evaluated investigation core | Three bounded evidence tools over replay and database sources | T01 | 2, 4 |
| T03 | Evaluated investigation core | Runnable one-shot and fixed-retrieval baselines with cited reports | T02; paid evaluation approval for live results | 3, 5, 6 |
| T04 | Evaluated investigation core | Bounded adaptive investigation with tested safety and failure behavior | T03 | 7, 8, 9 |
| T05 | Evaluated investigation core | Reproducible comparison of the baselines and adaptive agent | T04; paid evaluation approval | 10, 11 |
| T06 | Durable investigation workspace | Authenticated durable investigation submission and history | T05 | 12, 13 |
| T07 | Durable investigation workspace | Worker execution, progress, cancellation, and restart reconciliation | T06 | 14, 15, 16, 17 |
| T08 | Durable investigation workspace | Browser investigation workflow with evidence and failure states | T07 | 18, 19, 20, 21, 22, 23 |
| T09 | Reproducible portfolio release | Isolated live timeout scenario with observed recovery and minimal startup | T08 | 24, 25, 26, 27, 28, 29, 34 |
| T10 | Reproducible portfolio release | Read-only recorded demo, separate from owner-operated paid execution | T09; hosting approval for publication | 30, 35 |
| T11 | Reproducible portfolio release | Evaluation write-up, demonstration, and final release evidence | T10 | 31, 32, 33, 36, 37, 38 |

The approved execution order remains authoritative. Tool tests are written with the tool implementation using TDD, but step 4 is only marked complete when its full checks have run. Milestone dependencies keep later implementation from bypassing the evaluation gate.

## Verification expected on each PR

- Run the affected service suite from its own directory and run `make test` before claiming the change is ready.
- Run `make lint`, extending its coverage as new Python directories land.
- Preserve the scoring contract and the best-effort ingestion behavior.
- Run database and browser integration checks in task-owned environments when applicable. Inspect the actual migration revision, not just the presence of columns.
- Report skipped checks and their blockers explicitly. No invented accuracy, latency, reliability, or cost results.

## Publication record

Repository: `HitendraKawale/log-guardian`.

GitHub confirmed three milestones and eleven issues:

- [Evaluated investigation core](https://github.com/HitendraKawale/log-guardian/milestone/1): T01 [#3](https://github.com/HitendraKawale/log-guardian/issues/3), T02 [#4](https://github.com/HitendraKawale/log-guardian/issues/4), T03 [#5](https://github.com/HitendraKawale/log-guardian/issues/5), T04 [#6](https://github.com/HitendraKawale/log-guardian/issues/6), T05 [#7](https://github.com/HitendraKawale/log-guardian/issues/7).
- [Durable investigation workspace](https://github.com/HitendraKawale/log-guardian/milestone/2): T06 [#8](https://github.com/HitendraKawale/log-guardian/issues/8), T07 [#9](https://github.com/HitendraKawale/log-guardian/issues/9), T08 [#10](https://github.com/HitendraKawale/log-guardian/issues/10).
- [Reproducible portfolio release](https://github.com/HitendraKawale/log-guardian/milestone/3): T09 [#11](https://github.com/HitendraKawale/log-guardian/issues/11), T10 [#12](https://github.com/HitendraKawale/log-guardian/issues/12), T11 [#13](https://github.com/HitendraKawale/log-guardian/issues/13).

Each issue after #3 has a native GitHub blocked-by relationship to its predecessor, in addition to the body reference.

## Current implementation

Issue #3 is implemented locally on `feat/3-incident-evidence` in `.worktrees/3-incident-evidence`. The worktree reuses the root virtual environment through a locally ignored symlink. Application code on `main` is unchanged.

The change adds versioned evidence, isolated grading labels, a standard-library validator, 33 deterministic checks, documentation, and Makefile/CI integration. `make test` passed all 100 tests and `make lint` passed. The shared local environment still emits pytest-asyncio deprecation warnings. The new suite also passed with plugin autoload disabled, without relying on that plugin.

With explicit user approval, commit `957afe3` was pushed and [PR #14](https://github.com/HitendraKawale/log-guardian/pull/14) opened against `main`. The worktree is clean. Local verification passed all 100 tests, lint, and corpus validation; the PR reports its hosted CI status. Issue #3 remains open pending review and integration. No merge, model calls, or public deployment have been performed. All PR #14 CI checks subsequently passed.

Issue #4 is implemented locally on `feat/4-evidence-tools` in `.worktrees/4-evidence-tools`, based on issue #3's commit. This keeps the changes separate while the parent PR awaits review. Its three tools and five runbook sections passed 43 new checks; all 143 local tests and lint passed. A stored-timestamp UTC fix was necessary to make SQLite scope queries correct for new offset-aware inputs. Historical offset loss remains documented.

PostgreSQL and image execution are blocked by the unavailable Docker daemon. With user approval, issue #4 was committed as `133a5b9`, pushed, and published as [PR #15](https://github.com/HitendraKawale/log-guardian/pull/15) against `feat/3-incident-evidence`. Fresh verification passed all 143 tests and lint. All hosted CI checks passed. The worktree is clean and issue #4 remains open pending review and integration. Neither PR was merged. Retarget #15 to `main` after #14 merges.

Issue #5's offline implementation is on `feat/5-investigation-baselines` in `.worktrees/5-investigation-baselines`, based on `133a5b9`. Steps 3 and 4 are complete locally: A/B baselines, explicit SDK/model configuration, structured cited reports, provenance, guarded development CLI, and deterministic tool checks. With user approval, commit `e4edf8b` was pushed and draft [PR #16](https://github.com/HitendraKawale/log-guardian/pull/16) opened against `feat/4-evidence-tools`. The nine-file diff excludes prerequisite changes. Fresh verification again passed all 177 tests, lint, and dependency checks. The worktree is clean; no PR was merged.

Fresh verification: 177 tests passed, lint passed, and `pip check` reported no broken requirements. The evaluation suite passed 38 tests with plugin autoload disabled. A/B dry runs made zero provider requests and saved artifacts to `/tmp/log-guardian-baselines.Wdv3dv/`. OpenAI SDK 2.11.0 and snapshot `gpt-4.1-mini-2025-04-14` were checked against provider documentation; pricing is dated 2026-09-13. The subsequent authorized live smoke evaluation completed step 5: four requests on dev-01/dev-06, estimated total cost $0.00366960, all with known usage. The authorization is exhausted. Both baselines matched the supported case's core deadline mechanism but failed the required inconclusive case, inventing a causal link from unavailable log collection to request timeouts. Correct abstentions: 0 of 2.

Step 6 remains open; PR #16 stays draft. Original artifacts and review notes are saved under `evals/results/2026-09-13-baseline-smoke/` in the issue #5 worktree, not yet committed or pushed. An offline artifact check was added. Fresh verification passed 178 tests and lint. Do not treat the runner's completed status as semantic success or advance past the missing inconclusive example. Further paid requests need a new explicit allowance.

The issue #5 worktree now contains an offline correction candidate: stop-word filtering and section-ID matching for runbooks, plus a general missing-telemetry/causal-evidence prompt policy. The dev-06 dry run returns `runbook:timeouts` without a provider request. All 184 tests and lint passed, including unchanged archived report hashes. The user then authorized committing/pushing this update and a fresh four-request, $0.10 evaluation. Candidate and first-batch artifacts were published as `0a97c3f`. The second batch cost an estimated $0.00401200 and still produced 0 of 2 required abstentions. B's corrected retrieval returned the timeout runbook, but its unsupported causal claim persisted.

Second-batch artifacts and review notes are saved locally in `evals/results/2026-09-13-baseline-smoke-v2/`, not yet committed or pushed. Fresh verification passed 185 tests and lint, including both archived batches. Eight total requests have been made, estimated $0.00768160 across the two exhausted authorizations. Step 6 and issue #5 remain open; PR #16 stays draft. No additional prompt change, paid request, or merge was performed.

Offline SDK-boundary diagnosis verified that the client can accept an inconclusive report for the real dev-06 evidence. The evaluated schema emitted outcome before evidence/gaps, and the provider documents schema-key output ordering. A new uncommitted candidate changes only report field order, not prompt wording, model, retrieval, validators, or evidence. Its effect on abstention is unverified. See the worktree's `docs/baseline-abstention-diagnosis.md`. All 187 tests and lint passed; both archived batches remain intact. New paid calls required explicit approval.

The user approved the order-only candidate and another four-request, $0.10 trial. Candidate and second batch were committed/pushed as `8edf09e`. The third batch cost $0.00409200 with all usage known. A/dev-06 now provides a real inconclusive example without the invented request dependency. B's inconclusive label still hides an unsupported alternative, so only one of two required abstentions passes core semantic review. Both dev-01 reports retained the supported deadline explanation. Observation-level limitations remain documented.

Step 6 is complete. All four third-batch reports and the review/summary are published as `9d6a86d` under `evals/results/2026-09-13-baseline-smoke-v3/`. The representative pair is B/dev-01 and A/dev-06. Fresh verification: 188 tests and lint passed. All twelve originals remain preserved. All three allowances are exhausted: twelve requests, estimated $0.01177360. PR #16 is now ready for review, and all attached CI checks pass, including hosted integration tests. Issue #5's acceptance checkboxes are complete; the issue stays open pending integration. Local Docker/PostgreSQL evidence-tool verification and independent review remain unperformed. No PR was merged. Next: issue #6 / steps 7–9, bounded adaptive execution and offline tests. No additional paid evaluation or merge is authorized.

Steps 7–9 are complete locally on `feat/6-adaptive-investigator` (`.worktrees/6-adaptive-investigator`, based on `9d6a86d`). C uses native tool selection through the shared runner/CLI, with the planned six-request/eight-tool/120-second/evidence/output limits. No automatic retries; ambiguous usage stops execution. Twenty-six new scripted SDK tests and one C CLI test passed, including evidence-dependent next queries and adversarial/budget cases. Full verification: 215 tests passed; lint passed, 70 files formatted. An actual C dry run made zero model/tool requests with a $0.00525840 first-request reservation.

Changes are uncommitted; no paid C evaluation or PR yet. Step 10's full development comparison would be 24 runs (A/B/C on eight cases), at most 64 provider requests, using $0.025 per-run allowances for a $0.60 total allowance. This is a proposed allowance, not authorization. Held-out runs, commits/pushes for this slice and merges still need their respective approval.

## Final status (2026-09-14)

All 38 plan execution steps are complete. Delivery is an eight-PR stack, none merged:
#14 corpus -> #15 tools -> #16 baselines -> #17 adaptive -> #18 storage/API -> #19 UI -> #20 demo sandbox -> #21 portfolio docs/demo.

Evidence highlights: six live evaluation batches preserved (92 runs, 152 requests, est. $0.12803600 total; scorecard in docs/evaluation.md); real container fault/recovery run; PostgreSQL migration verified to revision 0003; 242 unit/contract/eval + 3 sandbox + 15 browser tests and lint green at `57b4350`.

Gates still requiring explicit owner approval: merging the PR chain (bottom-up, retargeting each successor after its base merges), public hosting of the static demo (issue #12 final criterion), any further paid model execution, and independent review.
