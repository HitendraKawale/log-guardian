# Log Guardian product release scope

Status: product scope approved through Plannotator. Each milestone still requires its own implementation plan.

## Goal

Today the repository demonstrates investigation, but lacks a complete onboarding and recurring detection workflow for ordinary application logs.
The first release lets the owner connect a Docker Compose project, review suspicious events, and request a bounded AI investigation.
Prove the flow locally, then measure usefulness on real development logs before offering a paid pilot. Revenue is not established by shipping software.

## Product decision

Start with a single-owner, localhost-bound installation using the owner's model key. Keep detection free of model calls. AI explains selected events using bounded evidence; it does not classify every incoming line.

```text
Today: [Demo/API logs] -> [One-time novelty candidates] -> [Manual API promotion]
After: [User project logs] -> [Recurring incident queue] -> [Budgeted investigation + review]
```

A hosted multi-tenant service adds data isolation, account security, operational support, and billing before we have evidence of demand. Reject it for the first release. A dashboard-only redesign leaves onboarding and detector behavior unresolved. Reject that too.

## Findings from source inspection

- `app/trigger.py` tracks template novelty in process memory, with a global 500-log warmup. It has no frequency detector.
- `app/models.py` makes `(service, template)` unique in the candidate queue. A familiar error cannot create a later incident through that path.
- `app/service.py` commits logs before best-effort candidate selection. Preserve this failure separation.
- `frontend/candidates.js` lists and dismisses candidates. It intentionally has no investigation action because the log key cannot authorize spending.
- `infrastructure/docker/demo-compose.yml` supplies a fault sandbox, not an onboarding path for another project. Its worker is opt-in and the stack is localhost-bound.
- The README explicitly warns that the worker has no account-wide allowance ledger. Per-run limits do not bound cumulative spend.
- The BGL classifier is domain-specific. Its reported accuracy is not application-log detection evidence.

## Delivery sequence

Each milestone gets its own source-traced implementation plan and review. Do not implement this whole roadmap as one change.

- [x] **1. Connect the selected development project.** Verified locally with the owner-selected checkout/inventory sandbox, not an external customer's application. Add a local startup profile and a documented log-forwarding path for a selected Compose service. Start with Docker CLI output forwarded by an owner-run command rather than granting a container the Docker socket. Support structured logs and explicitly defined plain-text fallback behavior. Show connection status and last received log. Keep paid execution disabled by default. Test malformed input, disconnects, backpressure, and shutdown; document delivery and duplicate guarantees rather than claiming exactly-once ingestion.
- [ ] **2. Detect recurring incidents.** Keep severity plus template novelty; add per-service error-frequency windows and explicit learning state. Persist the state needed across restart. Replace lifetime candidate suppression with incident-window grouping so repetition updates an active incident and recurrence can open a new one. Define window lengths, minimum traffic, cooldown, late-event handling, and retention in this milestone's plan. Test ordinary traffic, novel errors, familiar-error bursts, recovery, recurrence, restart, and concurrent ingestion. These are test cases, not measured production accuracy.
- [ ] **3. Investigate from the product safely.** Add an explicitly authorized candidate-to-report action without granting the log key execution rights. Keep provider keys server-side. Reserve cumulative budget durably before model calls; reconcile known usage and retain reservations for ambiguous failures. Reuse existing evidence tools, citation checks, idempotency, and worker cancellation. Start with fixed retrieval B because preserved evaluation does not support making adaptive C the default. Test provider failures, duplicate clicks, concurrent budget claims, restart, and exhausted allowances using scripted providers. Live checks need a new per-batch authorization.
- [ ] **4. Make the queue useful daily.** Put incidents and their evidence ahead of benchmark displays. Add useful/noise feedback and one opt-in notification integration with deduplication and delivery failure visibility. Provide log retention and deletion behavior that accounts for stored report evidence. Test the complete browser flow, keyboard access, empty/learning/error states, and untrusted log rendering.
- [ ] **5. Run a pilot and prepare a release.** Use it on the owner's projects, record onboarding time, reviewed findings, noise, missed known faults, investigation cost, and resource use. Recruit an external pilot before adding billing. Package reproducible images, document upgrades and backup/restore, check secrets and dependencies, and test recovery on a clean install. Public deployment, image publication, commits, pushes, and paid runs require their respective authorizations.

## File ownership for the planned work

Paths are relative to the repository root. New paths are proposals, not files created by this draft.

| File or area | Today | Planned responsibility |
| --- | --- | --- |
| `infrastructure/docker/local-compose.yml` and `scripts/forward_compose_logs.py`, new | No general local-product profile or selected-project forwarder | Local installation and explicit owner-run collection without a mounted Docker socket |
| `Makefile`, `README.md` | Research/demo entry points | Local startup, connection instructions, limits, and troubleshooting |
| `services/ingestion-service/app/trigger.py`, `app/service.py`, `app/config.py` | In-memory novelty and best-effort persistence | Per-service recurring detection with visible learning state; preserve stored logs on detector failure |
| `services/ingestion-service/app/models.py`, `migrations/versions/`, candidate routes and schemas | Lifetime candidate uniqueness | Durable incident windows, recurrence, and review state through migrations |
| `services/ingestion-service/app/investigator.py`, investigation routes and schemas | Key-gated execution with per-run bounds | Durable cumulative reservations and explicit user-authorized execution |
| `frontend/` | Logs, candidates, investigations, evaluation displays | Connection-to-incident-to-report workflow with separate execution authorization |
| `services/ingestion-service/tests/`, `tests/e2e/`, new forwarder checks | Existing service and browser checks | Regression coverage for collection, recurring detection, spend controls, and daily use |
| `.github/workflows/ci.yml`, `Makefile` | Existing test and lint coverage | Include every new Python directory and new suite explicitly |

## Decisions expressed as behavior changes

```diff
- A service/template pair produces at most one candidate for its lifetime.
+ Repeat observations update an active incident; a later recurrence can open another.

- A familiar template never qualifies, regardless of its frequency.
+ A familiar error burst can qualify against a per-service baseline.

- A configured worker has per-run limits but no cumulative allowance ledger.
+ Every paid request requires a durable reservation within an explicit allowance.

- Candidate review requires a separate manual API call to investigate.
+ The product offers explicit execution authorization without widening the log key.

- BGL model scores are displayed alongside application logs.
+ Application incident detection explains its own signal; BGL remains a separate experiment.
```

## Verification gates

- [x] Before implementation, capture a baseline with `make test`, `make test-demo`, and `make lint`; retain failures as baseline evidence. On 2026-09-20: 301 tests plus 3 demo tests passed; lint passed, 92 files already formatted. Raw logs: `/tmp/log-guardian-baseline.EIsuKJ/`.
- [ ] For each milestone, write failing contract checks before behavior changes and run the whole affected suite from its configured directory.
- [ ] Validate migrations on SQLite and PostgreSQL whenever persistent schema changes.
- [ ] Run a task-owned local stack and verify visible changes in Chromium. Capture screenshots and exact URLs.
- [ ] Exercise checkout/inventory fault, recovery, and recurrence through the real ingestion path. Do not treat this controlled sandbox as customer validation.
- [ ] Confirm offline tests and ordinary ingestion make no paid requests.
- [ ] Preserve existing evaluation archives unchanged. New prompt tuning uses development cases, not the consumed held-out split.

## Deliberately excluded

No multi-tenancy, billing, Kubernetes onboarding, automatic remediation, model retraining on unlabeled customer logs, or public hosted execution in the first local milestone. Automatic investigation waits for budget enforcement and separate approval. No new frontend framework is required by this scope.

## Review and current evidence

Plannotator approved the product direction and milestone order. Each milestone requires its own detailed implementation plan before code changes. Milestone 1's completed local implementation record is [local project onboarding](local-project-onboarding.md).

Issue #31 is implemented, uncommitted, in `/Users/hitesh/log-guardian-worktrees/31-local-onboarding` on `feat/31-local-onboarding`. Verification passed 345 offline tests, 5 demo tests, 31 Chromium tests, and lint. Two real Docker fault/recovery cycles stored 83 application records with zero fault-control diagnostics; native Docker collection replaced Compose log collection after the latter merged stderr into stdout. API outage and SIGINT cleanup were exercised. SQLite data survived restart; no schema change required a migration.

The local dashboard is at `http://localhost:8080/?api=http://localhost:8000`; verification collectors and the separate browser-test stack are stopped. Local ingestion/dashboard and source-only checkout/inventory remain running. Evidence and outstanding code-review/publication gates are recorded in the milestone plan. No paid calls, commits, pushes, hosted CI run, or public deployment occurred. Existing evidence archives are unchanged. Recurring detection is the next unimplemented milestone.
