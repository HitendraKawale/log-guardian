# Offline workspace security replay

This experiment checks authored workspace traces against an owner-controlled policy.
It does not run an AI agent, execute tools, or call a provider. It tests policy-rule
mechanics, not prompt-injection detection accuracy or protection of a live application.

## Provenance

Tool contracts come from MIT-licensed [AgentDojo](https://github.com/ethz-spylab/agentdojo)
revision `089ed468cf3ed0322acc66b0211f26d9d90dbf60`. The unchanged email contract,
workspace tool registration and full license are in `reference/agentdojo/` with
source URLs and SHA-256 hashes in `manifest.json`. Those files are reference artifacts,
not imported code, and are excluded from project formatting and linting.

The development traces are authored examples informed by those contracts. They are
not captured AgentDojo executions, customer telemetry or a reproduction of its benchmark.
Expected findings belong only in `dev-labels.jsonl`, with draft review status.

## Run

From the repository root:

```sh
env -u OPENAI_API_KEY -u ANTHROPIC_API_KEY -u TYPESAFE_API_KEY \
  .venv/bin/python evals/agent_security.py \
  --input evals/agent-security/dev.jsonl \
  --policy evals/agent-security/policy.json
make test-evals
```

The CLI emits deterministic JSON on stdout and never opens labels or writes output
files. Exit 0 means valid input, including cases with findings; 1 means invalid data
or inaccessible files; 2 means invalid CLI arguments. Input and policy files each
have a 1 MiB limit. Every trace has at most 1,000 events. An invalid later trace
prevents partial output for earlier traces.

The explicit policy allows `get_unread_emails`, `send_email`, and two synthetic
recipient addresses. `disallowed_tool` flags calls outside that tool list.
`unapproved_recipient` checks primary recipients, CC and BCC against exact allowed
addresses. Domain case is normalized; local-part case is preserved. This adapter
accepts simple ASCII mailboxes, not display names or the full RFC mailbox grammar.

## Executed verification

On the issue #36 worktree based on merged `main` at `107ca66`:

```text
make test:       430 passed
make test-demo:    6 passed, 2 existing deprecation warnings
make lint:      All checks passed; 111 files already formatted
new replay tests: 60 passed, included in the 430 above
CLI:              8 authored traces, 4 findings
repeat CLI:       byte-identical output
```

The evaluation suite also prints its existing pytest-asyncio unset-loop-scope
warning. No hosted CI, live agent, UI or paid-provider verification was performed.
No production code, wire contract or operational detector changed.

| Development trace | Recorded finding | Recorded tool outcome |
| --- | --- | --- |
| workspace-dev-01 through workspace-dev-04 | None | Approved read/send behavior |
| workspace-dev-05 | Unapproved primary recipient | Succeeded |
| workspace-dev-06 | Unapproved BCC recipient | Succeeded |
| workspace-dev-07 | Disallowed deletion tool | Denied |
| workspace-dev-08 | Unapproved recipient | Unknown, no result event |

Findings cite their actual request and result event IDs. The result of a denied
operation is not successful execution. A successful unapproved email is a policy
violation, not proven sensitive-data exfiltration. Prior hostile text does not
establish causation and does not generate an alert on its own.

`offline-replay.json` preserves the CLI output with hashes of the input, policy,
implementation, reused validation module and pinned-source manifest. It was created
without overwriting an earlier artifact. Local test evidence lives in
`/tmp/lg36-validation-red.log`, `/tmp/lg36-rules-red.log`, `/tmp/lg36-cli-red.log`
and `/tmp/lg36-final-checks.log`.

Tests cover strict schemas, cross-trace correlation, interleaved call IDs, invalid
and oversized input, exact-address lookalikes, all recipient fields, denied/failed/
unknown outcomes, label isolation, source hashes and real CLI process execution.
In-process CLI replay tests prohibit socket connections, DNS lookup and datagram
sends. Removing provider keys alone is not the evidence for no-network behavior.

## Pre-publication review

The same implementation agent reviewed the work against issue #36, the approved
plan and repository standards. No independent reviewer was available.

Standards review found no remaining blocker. Source provenance and MIT attribution
are preserved; runtime and evaluator inputs stay separate; production services and
existing evaluation archives remain unchanged.

Spec review found one parser defect: `str.splitlines()` split valid JSON strings
at Unicode separators U+0085, U+2028 and U+2029. Three regression cases reproduced
the failure. The shared loader now iterates UTF-8 text with `io.StringIO`, preserving
those characters within records and accepting CRLF record endings. No rule or
fixture labels changed.

Fresh verification after the fix:

```text
make test:        433 passed
make test-demo:     6 passed, 2 existing deprecation warnings
make lint:       All checks passed; 111 files already formatted
new replay tests: 63 passed, included in the 433 above
CLI:               8 authored traces, 4 findings, byte-identical rerun
```

The failure and verification logs are `/tmp/lg36-review-red.log` and
`/tmp/lg36-review-verified.log`. `offline-replay-reviewed.json` records the new
implementation hash; its findings match the earlier `offline-replay.json`, which
remains unchanged as a pre-review checkpoint. The earlier artifact's implementation
hash does not describe the final source. Hosted CI results are not included in this
local verification record.

## Limits and next review

All outcomes above are authored contract checks, not precision/recall, jailbreak
resistance or a live-agent benchmark. Labels remain drafts awaiting owner review.
Telemetry is assumed to come from the owner; forged events can falsify outcomes.
No sensitive-data lineage, hidden payload channel, URL-based exfiltration, arbitrary
tool argument analysis or runtime permission enforcement is implemented.

No new held-out split was authored or inspected. Freeze these rules and development
fixtures before the owner or an independent reviewer supplies evaluation scenarios.
Do not claim independence merely because an upstream case is public. Existing
operational evaluation archives and consumed held-out cases were not revised or
used to tune these rules.

Production integration needs a trusted application adapter and a separate security
incident path. The operational severity/warmup/burst detector must not suppress a
security-policy finding. This experiment does not provide that integration.
