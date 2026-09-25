# Agent-security product plan

Issue #47. The owner selected security monitoring for AI agents, approved generic
Python first, and requested a commit for every verified step. Push relevant branches;
do not merge or start paid model execution. OpenAI Agents SDK and LangGraph follow later.

## Goal

The repository has security experiments and an investigator journal, but no reusable
agent integration or dedicated security review product. Build a local, single-owner,
shadow-mode monitor. Prove collection, policy findings and review with real captured
Python calls, without calling a model or claiming measured attack detection.

```text
[Owner policy] --------------------------> [Policy findings]
                                               ^
[Python tool wrappers] -> [Durable events] -> [Security API] -> [Review UI]
```

The monitor never derives policy from prompts, retrieved text or tool results. A
policy violation is not proof of malicious intent or prompt-injection causation.
A function returning does not prove a downstream side effect succeeded. A missing
completion remains unknown. Shadow mode does not block a tool for violating policy;
an audit-write failure before dispatch does prevent an unrecorded call.

## Milestones and commits

### 0. Preserve experimental work

- [x] Commit and push #46's completed offline verifier, archives and tests as 4d4bdf9.
- [x] Mark live-verifier preparation deferred. No live driver or paid batch was started.

### 1. Generic Python capture and a working investigator example

- [x] Create a Python package with no runtime dependencies under integrations/python/log_guardian_agent.
- [x] Add immutable owner Policy and Monitor.wrap for ordinary and async callables.
- [x] Journal a request durably before calling the wrapped function; link completion
  afterward. Store identifiers, tool names, origin, outcome and elapsed time only.
  Never store arguments, return values, exception messages, prompts or model keys.
- [x] Support explicit owner-selected agent versus host origin. Host bootstrap reads
  are not model tool proposals. The callable receives its original arguments unchanged.
- [x] Use exclusive per-run journals, serialized writes, bounded event count, 0600 file
  permissions and no resume/retry. Poison a recorder after an audit-write failure.
- [x] Implement strict bounded journal inspection against a separately supplied owner
  policy. Reject unknown fields, malformed records, duplicate IDs, invalid sequence,
  orphan/repeated completions and mismatched policy fingerprints.
- [x] Start with exact tool allowlists. Report disallowed agent-origin requests and
  observed returned/raised/unknown outcomes. Do not call this a universal injection detector.
- [x] Wrap the repository's actual EvidenceTools methods in a no-provider example.
  Exercise host bootstrap, an allowed query and a deliberately out-of-policy read.
- [x] Add tests, packaging, a Make target and a CI matrix entry. Verify installation
  in an isolated temporary environment and run the full affected suites before committing.

Milestone 1 evidence is in docs/verification/agent-capture/. Twenty-two SDK checks
passed, including process exit, concurrent calls, write failures and a network-forbidden
investigator example. Full verification passed 661 offline tests plus six demo tests.
The package installed and ran with isolated Python and no runtime dependencies.
Security ingestion/UI and the root README animation remain unimplemented milestones.

Public interface:

```python
policy = Policy(allowed_tools={"query_logs"})
with Monitor("run.jsonl", agent="investigator", policy=policy) as monitor:
    query = monitor.wrap("query_logs", tools.query_logs)
    batch = await query(**scope)
report = inspect_journal(Path("run.jsonl").read_bytes(), policy)
```

Run IDs, call IDs and sequence numbers belong to the recorder, never tool arguments.
A request without completion is unknown, including process termination. Capturing all
wrapped calls does not prove that the application routed every tool through the wrapper.
One recorder supports concurrent threads/tasks, but a journal has one writer and is
not a multi-process queue. The owner must join calls before closing its recorder.

### 2. Dedicated security ingestion and review

- [ ] Add a key-gated security API separate from operational log candidates and paid
  investigation routes. An empty security key disables the new API.
- [ ] Store security runs, ordered events and findings with a migration. Deduplicate
  reuploads by run/event identity and reject conflicting bytes, not overwrite them.
- [ ] Evaluate against server-owned policy, never a policy claimed inside uploaded
  events. Keep its snapshot/fingerprint with the run. Refuse mismatched policy rather
  than silently grading historical events against a different configuration.
- [ ] Add an explicit owner-run journal upload command, not hidden network calls from
  the tool wrapper. Failed uploads leave the local journal available for manual retry.
- [ ] Add a security-first dashboard queue and per-run timeline. Distinguish host reads,
  tool requests, returned calls, raised calls and unknown outcomes. Render text safely.
- [ ] Verify SQLite/PostgreSQL migration behavior and browser flows before committing.

This is authenticated collector telemetry, not proof against a compromised collector
process. The owner configures which tools are allowed. Recipient, resource-scope and
other argument-level rules require explicit safe projections and later policy versions;
they are not inferred from stored strings in this first generic integration.

### 3. Product documentation and recorded walkthrough

- [ ] Replace the README's incident-investigator positioning with the actual security
  alpha, an executable quick start and a short animation from the running product.
- [ ] Record the example flow: owner policy, captured tool calls, a policy mismatch,
  its observed outcome and the review timeline. Label scripted agent behavior and do
  not show a blocked action when shadow mode permitted it.
- [ ] Provide a static diagram/description alongside motion, and retain editable
  animation sources plus reproducible capture commands.
- [ ] Write integration, event/policy contract, threat model, privacy/storage,
  troubleshooting, architecture and development guides. State delivery and retention limits.
- [ ] Move historical ML/investigator research out of the headline while preserving
  recorded numbers and links. Keep the report verifier explicitly experimental.
- [ ] Check commands, links, packaging and rendered assets, then commit and push.

## File decisions

| Area | Today | After |
| --- | --- | --- |
| integrations/python/ | No generic integration | Standalone stdlib recorder, inspector, packaging, example and tests |
| Makefile and .github/workflows/ci.yml | No SDK suite | Run and lint the new suite explicitly |
| app/models.py, migrations, new security router | Operational incidents only | Dedicated security runs/events/findings with policy ownership and idempotent import |
| frontend/ | Incident-investigator dashboard | Security queue and execution timeline; operational views remain available |
| README.md and docs/ | Research-heavy entry point | Security alpha onboarding, integration and limits, plus recorded walkthrough |

No new frontend framework, model dependency, hosted service, billing, multi-tenancy,
automatic remediation, generic argument capture or policy blocking in this release.
No public package/image publication is implied by git push.

## Verification discipline

Write failing behavioral checks before implementation. Run every affected suite,
not only new tests. Preserve existing result archives and source freezes. Commit only
a passing milestone and report its hash; pushing a branch is not a merge or a release.
The first generic policy is deliberately limited to tool allowlists. Later adapters
must not imply coverage of destinations, permissions or effects they did not observe.
