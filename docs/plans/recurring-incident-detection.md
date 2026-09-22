# Recurring incident detection

Status: implementation and local verification complete on issue #33, branch `feat/33-recurring-incidents`, based on onboarding commit `4abd403`. Changes remain uncommitted. See [verification evidence](../recurring-detection-verification.md).

## Execution checkpoint

The initial baseline exposed a demo fixture shutdown bug. `make test` completed
with 345 tests passed. `make test-demo` printed `5 passed, 2 warnings` but Python
then exited with segmentation fault 11 (exit 139). The fault reproduced with
`PYTHONFAULTHANDLER=1`; the macOS native stack shows a uvloop timer calling
`PyGILState_Ensure` during interpreter shutdown. The fixture signaled daemon
servers to exit without joining their threads.

A real-fixture regression failed because server threads remained alive after
teardown. `demo/test_scenario.py` now retains thread handles and signals/joins
all servers in `finally`. Three full demo-suite executions each returned exit 0
with `6 passed, 2 warnings`. Lint passed with 99 files already formatted;
`git diff --check` passed. Evidence: `/tmp/lg33-demo-repro.log`,
`/tmp/lg33-demo-red.log`, `/tmp/lg33-demo-fixed-{1,2,3}.log`.
The deprecation warnings remain; no dependency upgrades were made.

Issue: https://github.com/HitendraKawale/log-guardian/issues/33
Worktree: `/Users/hitesh/log-guardian-worktrees/33-recurring-incidents`.
All six steps are complete. Pure transitions live in `app/trigger.py`;
`app/incident_detection.py` coordinates a separate bounded database transaction;
models and migration 0006 add durable state and recurring candidate metadata.
`persist_log` now uses the durable detector. API and dashboard expose signal
counts, readiness and activity. This completes operational recurring detection,
not the remaining product milestones.

Fresh checkpoint verification: 365 offline tests, 6 demo tests, lint passed
(104 files formatted), and `git diff --check` passed. Evidence:
`/tmp/lg33-backend-checkpoint.log`. The 20 new detector tests cover rules,
SQLite persistence/concurrency, rollback/lock deadline and migration safety.
They failed before their corresponding implementation was added.

Test coverage was split into `test_incident_detection.py`,
`test_incident_persistence.py` and `test_incident_migration.py` so pure timelines,
real database coordination and Alembic subprocess checks remain separate.
Final verification supersedes that checkpoint: 370 offline tests, 6 demo tests,
34 Chromium tests, PostgreSQL integration, lint and diff checks passed. The actual
ten-minute fault/quiet/recurrence flow created two IDs and retained learning over
restart. No model calls, commits or pushes.

Final review added two protections with failing regression checks: promotion
locks the candidate before copying scope/creating a run; the detector keeps its
connection until SQLite timeout restoration and includes pool acquisition in its
deadline. The PostgreSQL test reproduced duplicate concurrent promotions before
the lock fix. CI now supplies a disposable PostgreSQL URL and dependencies, so
that test is not silently skipped; Makefile/CI lint includes the new tests.
Detailed commands, remaining limits, latency observations and the live harness
checkpoint race are recorded in the verification report.

## Goal

Familiar errors currently stop qualifying after their first appearance, and candidate uniqueness suppresses later recurrence forever.
Detect error bursts without a model call, group repetition, and preserve learning across restarts.
Prove fault, quiet gap, recurrence and restart behavior on SQLite/PostgreSQL and in the browser. These checks do not measure production accuracy.

## Context

The owner chose higher recall, accepting noisy review candidates but no automatic spending. This is milestone 2 of `product-release-scope.md`, not the remaining product roadmap.

Source findings:
- `app/service.py::persist_log` is shared by REST and Kafka. It commits logs before best-effort candidate selection.
- `app/trigger.py::InvestigationTrigger` uses process-local template memory and global warmup. `ml/training/measure_trigger.py` also consumes it for historical BGL measurement.
- `InvestigationCandidate` uniquely indexes `(service, template)`. Candidate review state and investigation linkage must remain intact.
- Promotion copies candidate scope and uses novelty-specific default wording. Investigation scopes cannot exceed one hour.
- `frontend/candidates.js` safely renders untrusted content using text nodes. It displays reasons but no counts or detector readiness.
- `init_db` uses `create_all`, which cannot upgrade existing SQLite tables. Existing databases need an explicit Alembic upgrade.

Implementation starts from onboarding commit `4abd403` in a new issue-linked worktree, not main and not the Jev experiment branch. Jev artifacts and all existing evaluation archives stay untouched. Create/reuse the detector issue when execution begins; commit, push and publication need separate authorization for this milestone.

## Approach

```text
[REST or Kafka log] -> [Committed log] -> [Persisted per-service detector]
                                                  |
[Review queue + learning state] <- [Grouped incident, no model call]
```

Use the existing database, not Redis, a scheduler or a new worker. Detection stays best-effort after log persistence. A detector transaction updates bounded service state and its incident together; rollback cannot lose the stored log. Count and log detection failures separately. There is no automatic catch-up after a detector failure in this milestone, and collection retries may count duplicate stored logs. State these limits rather than claiming exactly-once detection.

### Signal policy

Defaults are initial product choices, not calibrated thresholds:

| Decision | Rule |
| --- | --- |
| Candidate severities | Existing `TRIGGER_CANDIDATE_LEVELS`, default ERROR/CRITICAL |
| Novelty learning | Existing `TRIGGER_WARMUP_LOGS`, default 500, now per service; zero disables novelty warmup |
| Burst window | Current UTC-aligned 60-second bucket, evaluated after each eligible log |
| Baseline | Mean eligible count across preceding 15 complete buckets, including empty buckets after observation starts |
| Baseline readiness | At least five complete minutes and 100 total observed logs; independent of novelty readiness |
| Warm burst | Current eligible count >= 5 and >= 3 × max(1, baseline mean) |
| Learning burst | Current eligible count >= 5, even before the baseline is ready |
| Grouping | One active incident per service, merging novelty and burst signals; not one row per individual message |
| Recurrence | After >= 10 minutes with no eligible error received, close grouping. A later qualifying novelty/burst opens a new ID |
| Cold start after long silence | After >= 15 minutes without logs, discard bucket history and relearn baseline; preserve template history and lifetime observation count |

Baseline count measures logs, not failed requests. Increased traffic or verbose error logging can flag a candidate. A fixed-minute boundary can split a short burst; this initial implementation does not claim a true rolling-window detector. Store the observed count, baseline mean, threshold, bucket interval and learning flag with each trigger so the reviewer can see exactly why it fired.

Use server receipt time for bucket membership and quiet-gap grouping, never the caller's timestamp. Logs older than five minutes or more than one minute in the future are stored but excluded from detector learning/counts and counted as excluded. This prevents replayed backlogs or skewed clocks from creating current incidents. The UI must say the detector covers timely received logs, not all stored history. Use event timestamps only for evidence scope; normalize SQLite naive values as UTC.

During an active incident, each eligible log updates count and last-seen time even if it no longer meets the burst threshold. INFO logs do not keep the incident active. After ten quiet minutes, the API reports the incident as quiet based on its timestamps; no timer job or claim of verified recovery is needed. On the next ingestion, clear the expired active pointer under the same database lock.

Dismissed/promoted candidates remain terminal in review status. Repeated errors update their occurrence metadata without reopening or paying; only a new incident after the quiet gap is reviewable again. Display ongoing activity for dismissed/promoted rows when those rows are shown. Grouping unrelated failures within one service is a deliberate limitation; do not imply common root cause.

### State, bounds and concurrency

Add one `DetectorState` row per service: observed count, last received time, first bucket time, bounded minute buckets, bounded template history, active candidate ID, and last eligible-error time. JSON collections are assigned as new values so SQLAlchemy tracks updates. Retain at most 16 minute buckets and 2,000 normalized template hashes per service. Store template hashes rather than message content in state; insertion/eviction is deterministic. Evicted templates can later appear novel, which must be documented. Lifetime service cardinality remains proportional to ingested service names, as with existing log storage; no unbounded per-log state.

Use a dialect-specific upsert followed by a database write lock before reading state: PostgreSQL row lock; SQLite writer transaction. Keep both paths explicit and small. Concurrent first observations must create one state row. Set a bounded detector transaction/lock deadline of 250 ms; on lock timeout or other failure roll back detection, increment a failure counter, and return the stored log. No retry loop on the ingestion path. SQLite serializes writers across services; this is a known throughput ceiling, not hidden behind a process mutex. Verify cancellation leaves the session usable.

Add `last_seen_at`, `occurrence_count`, `signal_details`, and nullable `active_service` to candidates. A unique index on `active_service` enforces at most one active grouping per service. Clear it when an incident expires, regardless of review status. Replace lifetime `(service, template)` uniqueness with a nonunique lookup index. Representative message/template remains the first triggering log; details retain the finite set of triggered signal names and latest numerical trigger observation. Count starts at one for the triggering observation; do not imply it counts pre-trigger evidence.

Scope follows the most recent eligible event while an incident is active, using a trailing ten-minute window ending one second after that event, never >1 hour. Once promoted, freeze the candidate scope and investigation link; the investigation's copied scope is never changed. Occurrence counts and last seen can still advance, visibly distinct from the investigated evidence window.

Migration `0006` preserves every existing candidate ID, status, scope and investigation link. Backfill count=1, last_seen=occurred_at, signal details identifying legacy novelty; set active_service null. New detector state begins learning from newly ingested logs without replaying historical data. A downgrade refuses when duplicate `(service, template)` rows would make the old unique index invalid; never delete incident history to force downgrade.

### Interfaces and decisions

```diff
- investigation_trigger.consider(...)  # global in-memory runtime state
- _record_candidate(...)              # insert once per lifetime template
+ await observe_log(session, record)  # durable state + grouped candidate transaction

- A message pattern not seen before appeared in {service} ...
+ Operational log evidence was selected for {service} at {time}. What is going on?
```

Put database orchestration in `app/incident_detection.py`, and pure bucket/signal transitions in `app/trigger.py`. Keep the old `InvestigationTrigger` explicitly as the historical novelty-only baseline used by `ml/training/measure_trigger.py`; runtime no longer uses it. Do not rewrite recorded baseline results or run the BGL held-out measurement while tuning.

Extend `CandidateOut` additively with count, last seen, signal details and derived `activity` (`active`, `quiet`, `legacy`). Add authenticated, paginated `GET /candidates/detectors` before `/{candidate_id}` for per-service novelty/baseline readiness, timely-log counts and last received time. Reuse the log API key, never the investigation key. List ordering changes to last-seen descending with ID as tie-breaker.

Keep the current seven-column table: add last seen/count beneath the time cell and readable numerical signal evidence beneath reason. Add a small readiness region in the candidates view, with loading/empty/failure states and text-only rendering. No redesign, auto-investigate button or new frontend dependency.

## Files to modify

Paths below are relative to the new onboarding-based worktree. Unlisted files remain unchanged unless source tracing proves another direct caller needs migration; record that discovery before expanding scope.

| Path | Today | After |
| --- | --- | --- |
| `services/ingestion-service/app/trigger.py` | Process-local novelty selector | Keep historical selector; add deterministic burst/state transition functions |
| `services/ingestion-service/app/incident_detection.py`, new | No durable detector | Per-service locked state update and incident grouping |
| `services/ingestion-service/app/service.py` | Global trigger, lifetime insert | Call shared durable detector after log commit; expose failures/exclusions |
| `services/ingestion-service/app/models.py` | Lifetime candidate identity | Detector state and candidate activity/count/details fields |
| `services/ingestion-service/migrations/versions/0006_recurring_incidents.py`, new | No upgrade for recurrence | Preserve old rows and links; replace uniqueness safely |
| `services/ingestion-service/app/config.py` | Global novelty warmup | Document per-service meaning; validate detector policy settings and bounds |
| `services/ingestion-service/app/routes/candidates.py` | Basic candidate read/dismiss | Add activity/details and detector readiness endpoint |
| `services/ingestion-service/app/routes/investigations.py` | Novelty-specific promotion question | Neutral owner-supplied question, no log-message interpolation |
| `frontend/candidates.js`, `frontend/index.html` | Basic review table | Show count, numerical reason, activity and readiness |
| `services/ingestion-service/tests/test_incident_detection.py`, new | No burst contracts | Deterministic timeline, durability, concurrency, limits and failure checks |
| `services/ingestion-service/tests/test_candidates_api.py`, `test_logs.py`, `test_candidate_promotion.py` | Old runtime injection assumptions | Shared detector seam, additive response and promotion regressions |
| `tests/integration/test_incident_detection.py`, new | No PostgreSQL detector coverage | Real two-session coordination, migrations and recurrence |
| `tests/e2e/test_candidates_ui.py`, `tests/e2e/stub_server.py` | Novelty-only candidate fixtures | Counts/readiness/activity, escaped messages and review interactions |
| `docs/local-development.md`, `README.md` | Onboarding and old trigger limits | Upgrade commands, detector defaults and stated limits |

## Reuse

- `app/templates.py::normalize_message`: shared message normalization, no new parser.
- Existing SQLAlchemy session and Alembic infrastructure: no new service or dependency.
- `InvestigationScope`: validate every generated bounded evidence window.
- Existing candidate IDs, review statuses, dismissal, and separate execution authorization.
- `frontend/candidates.js` text-node rendering and existing auth helpers.
- Existing demo fault controls and Playwright tests. Never expose fault controls as tools or evidence.

## Steps

- [x] Establish the detector issue and isolated onboarding-based branch. Copy this approved plan there; capture `make test`, `make test-demo`, `make lint` baseline. Read each touched file in full before editing, including existing test fixtures and Compose migration startup.
- [x] Add deterministic failing timeline tests, then implement pure transitions. Required examples: four learning errors do not fire, fifth does; mature baseline of two errors/minute fires at six, not five; ordinary steady traffic does not fire; per-service readiness differs; a familiar template bursts; late/future logs do not learn; exact minute boundary and quiet-gap boundary are explicit; bucket/template caps hold. Pin clock values, do not sleep or call models.
- [x] Add failing migration and persistence tests, then implement models, migration and `observe_log`. Verify state survives session/process recreation; ten concurrent first/error observations produce exact counts and one candidate; lock timeout preserves stored logs and leaves a usable session; state and candidate updates roll back together. Verify expired dismissed/promoted incidents can recur under a new ID without changing old links. Preserve legacy novelty tests and do not run held-out BGL evaluation.
- [x] Replace the runtime call in `persist_log`, update API contracts and promotion wording. Run the full ingestion suite including direct/streaming callers, authentication and promotion regression tests. Prove candidate selection still creates zero Investigation rows and provider calls. Verify migrations from populated revision 0005 on SQLite and PostgreSQL, and guard the lossy downgrade case.
- [x] Update the existing candidate UI and browser fixtures. Exercise learning, burst, ongoing count, quiet gap, recurrence, dismissal, promotion-link preservation, detector-fetch failure, keyboard controls and malicious message rendering in Chromium. Keep the table usable without provider credentials.
- [x] Run all offline suites, demo, lint, PostgreSQL integration and browser tests. Start only task-owned named servers/Compose resources. Exercise real fault, recovery quiet gap and repeated fault through the collector; restart ingestion between bursts and verify no lost learning or duplicate active grouping. Capture exact URLs, screenshots, counts and logs. Record upgrade instructions and limits. Leave commits/pushes/PRs for explicit authorization.

## Verification and acceptance

The acceptance result is two incident IDs for two qualifying episodes of the same familiar error separated by ten quiet minutes, one row per service during each episode, persisted learning across restart, and zero paid calls. Quiet means no eligible error observed, not that the application is healthy.

Both SQLite and PostgreSQL concurrency tests are required, not optional substitutes. Existing APIs must keep storing logs during detector failures. Quantify added ingestion latency in the controlled sandbox, reporting any detections dropped by the deadline rather than hiding them. Browser screenshots verify visible state, while assertions verify incident counts and links.

If Docker/PostgreSQL or browser tooling is unavailable, report that blocker and leave the matching acceptance boxes open. A passing unit suite does not complete this milestone.

## Not doing

No Jev runtime integration, automatic execution, cumulative paid budget, feedback loop, notifications, general log deletion, hosted service, billing, anomaly-model retraining, latency metric detection or statistical significance claims. No cross-service causal grouping. No catch-up worker, exactly-once collector, arbitrary historical replay, or baseline calibration from the eight development fixtures.

## Review

The owner approved this plan in Plannotator and subsequently requested completion. Implementation is complete with the verification and limits above. No external publication has been made for this milestone. Wide events and security signals remain separate work.
