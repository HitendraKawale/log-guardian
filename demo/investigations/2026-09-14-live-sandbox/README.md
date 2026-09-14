# Live sandbox investigation (adaptive C, real fault)

One authorized paid run against the demo sandbox's real logs, executed by the
queue worker after an actual injected inventory delay produced genuine 504s.

- Status: completed; estimated cost $0.00229760; usage {'input_tokens': 4872, 'output_tokens': 410, 'cached_input_tokens': 1024}.
- Model gpt-4.1-mini-2025-04-14; prompt/schema a009f3a84312f38d…; worker revision container build (revision unavailable in image).
- C queried all scoped logs unfiltered, then a summary, and stopped: two tool calls, one conclusion.

Review: the likely cause matches the injected mechanism (inventory ~3002ms vs
checkout's 1000ms deadline) and cites real rows; recovery is observed, and
metrics are requested rather than invented. Caveats: the scenario script's
request-ID prefixes ("fault-", "recovered-") appear in log messages and hint at
the incident window, though not the mechanism; the internal reason for the
inventory delay is (correctly) not asserted. "Consider adjusting deadline" is a
remediation suggestion, not a read-only check. Reviewer: coding assistant, not
independent. One case; no general reliability claim.

Artifacts: `run.json` (API detail), `events.json` (ordered events with the
exact redacted evidence sent to the model). SHA-256: run 5c0663077ca8756e…, events 8d38391a18360f84….
