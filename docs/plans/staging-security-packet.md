# Staging security packet

## Goal

Prepare a reviewable, synthetic evaluation packet after the PostgreSQL crash checks.
Use existing evidence loading and dry runs, not a new paid runner or detector.
Offline checks establish compatibility, not attack success or detection accuracy.

```text
[Owner scope + question] -> [Investigator dry run]
[Evidence-only fixtures] -> [Real replay tools]
[Reviewer-only notes] -> [Independent human review, still pending]
```

| File | Decision |
| --- | --- |
| `evals/investigator-security/cases.jsonl` | Ten evidence bundles in the existing load_cases format; no labels or review notes |
| `evals/investigator-security/reviewer-notes.jsonl` | Five paired objectives and grading criteria, explicitly self-authored and unreviewed |
| `evals/investigator-security/README.md` | Review procedure, measures, failure rules and execution gates |
| `evals/tests/test_investigator_security_packet.py` | Reuse load_cases, execute with dry_run=True, and EvidenceTools; fail if runtime preparation opens reviewer notes |
| `evals/investigator-security/draft-freeze.json` | Hash packet files and tests against committed production candidate a0d0df4; not execution authorization |

## Decisions

Pair each benign case with an otherwise identical case containing one additional
attacker-controlled log message. Keep the owner question and scope unchanged.
The five objectives are service-scope expansion, time-window expansion, a fabricated
destructive tool, unsupported causal claims and forwarding unsafe operator advice.
Include quoted hostile text in a benign case to avoid defining attacks by keywords.
All inputs are visible development drafts. None is called held-out or independent.

```text
control: owner scope + incident observations
attack:  same owner scope + same observations + one untrusted instruction
```

The existing CLI selects fixed incident-corpus paths. Do not expand that live CLI
just to load these drafts. Tests can call its existing execute function with
client=None and dry_run=True. Check scope refusals by directly invoking real tools;
never report those authored probes as model behavior.

## Checklist

- [x] Write packet checks and observe failure before fixtures exist.
- [x] Add ten evidence-only cases and separate reviewer criteria.
- [x] Verify each full-scope query returns all fixture rows without truncation;
  verify forbidden service/time reads are denied and legitimate narrowed reads work.
- [x] Verify ten system-C dry runs make zero model requests while notes are unreadable.
- [x] Run affected offline suites and lint; freeze draft bytes and record results.

No model calls, commits, publication, production changes or independent-review claim.
Independent review requires a named person other than the author. A later live batch
needs a clean committed candidate, per-batch request/spend limits, durable accounting,
no retries and separate owner authorization. Existing email/Jev allowances do not apply.

## Verification

21 packet tests passed with pytest-asyncio disabled. The full offline suites passed
482 tests, plus six demo tests; lint passed. The 21 tests failed for missing packet
files before fixture creation. Logs: `/tmp/lg40-packet-red.log` and
`/tmp/lg40-packet-verified.log`.

The ten dry runs made zero model requests. Direct real-tool probes delivered all
fixture messages unchanged and refused service/time expansion. These are authored
compatibility checks, not observed model choices. No detector or production code
changed. The next blocker is a named independent reviewer; no such review is claimed.
