# Initial evidence coverage

Issue #42. The owner approved one bounded, unfiltered, server-initiated read before
C's first model request. No paid calls, commits or pushes are authorized here.

Cause: C starts without evidence and delegates its first query to the model. Eight
of ten live first queries filtered by question words, hiding available observations
and four attack messages. An empty-result fallback would not fix partial matches.

```text
[Owner scope] -> [Journaled unfiltered read] -> [First model request]
                                                 |
                                      [Optional bounded follow-ups]
```

| File | Decision |
| --- | --- |
| `app/investigation_loop.py` | Collect initial evidence inside the deadline; count it against existing tool/byte budgets; reuse result retention for initial/follow-up reads; seed duplicate detection |
| `app/investigation_tools.py` | Add an owner-only initial-read dispatch hook, not a model tool |
| `app/investigator.py` | Label initial request/completion events origin=server_initial; preserve cancellation and commit ordering |
| Loop, worker and eval tests | Verify first-request content, authority position, limits, source errors, cancellation, missing-provider and recording failures |
| `evals/investigator_pilot.py` and its tests | Keep historical git-base checks for live use only. Scripted tests need neither the historical commit nor the old runtime behavior |

Missing-provider runs still fail before tool execution. Dry runs collect the initial
bounded evidence and preview its actual reservation without calling a provider.
Keep the 50-row/16-KiB per-result cap, 64-KiB aggregate evidence budget, eight tool
executions, six model requests and 120-second deadline. A/B stay unchanged.
The initial sample is not exhaustive; truncation and source errors remain explicit.

The hosted #40 eval failure is a shallow-checkout failure: its scripted runner
unnecessarily runs git diff against an unavailable historical commit. Move that
live-only provenance gate out of scripted execution, without weakening live checks.

- [x] Add failing first-request exposure and journal-origin checks.
- [x] Implement the initial read and shared retention within existing budgets.
- [x] Update scripted flows to distinguish initial reads from model proposals.
- [x] Verify all ten existing fixtures and all five payloads in first HTTP requests.
- [x] Run relevant full suites, reproduce shallow-checkout behavior and preserve
  fresh offline evidence. Do not rewrite prior archives or refresh their freezes.

The prior paid batch and its candidate stay closed. Any later live comparison
requires a new frozen candidate and authorization. Exposure is not detector recall.

## Result

530 offline tests and six demo tests passed; all 170 eval tests passed in a real
shallow local clone without the historical base object. Ten exposure tests failed
before implementation; six initial-limit tests failed against the old implementation.

The preserved scripted run delivered all 35 fixture observations, including all
five injected messages, in the first HTTP requests. An independent database
connection verified initial request/completion commits before those sends.
No real provider call was made and no detection/semantic accuracy claim follows.

Evidence: `evals/results/2026-09-22-initial-evidence/README.md`.
The fix and evidence remain uncommitted. Hosted CI is not revalidated until an
authorized publication; the earlier #40 branch still has its recorded failure.
