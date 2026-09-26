# Log Guardian for Python agents

An alpha recorder for tools you explicitly wrap. It writes durable local metadata
and compares observed tool requests with your allowlist. It does not call a model,
send telemetry, capture argument/result bodies or block policy violations.

Targets Linux and macOS with Python 3.11+. Windows is not supported by this initial
directory-fsync implementation. Install from this checkout; no public package has
been published:

```bash
python -m pip install ./integrations/python
```

The installed package has no runtime dependencies. Setuptools is a build dependency.

## Wrap tools, then review

```python
from pathlib import Path
from log_guardian_agent import Monitor, Policy, inspect_journal

policy = Policy(allowed_tools={"read_logs"})
path = Path("new-run.jsonl")

with Monitor(path, agent="my-agent", policy=policy) as monitor:
    read_logs = monitor.wrap("read_logs", lambda: "private result")
    assert read_logs() == "private result"

report = inspect_journal(path.read_bytes(), policy)
assert report["findings"] == []
```

Register the wrapped callable with your agent instead of the original. Tool names,
origin, policy and output paths are owner configuration, not model tool arguments.
Arguments pass unchanged to the callable; results and exceptions pass back unchanged
when audit writes succeed. Never reuse an existing journal path.

Async functions use the same API:

```python
with Monitor("new-async-run.jsonl", agent="my-agent", policy=policy) as monitor:
    query = monitor.wrap("read_logs", my_async_query)
    result = await query(service="checkout")
```

Wrap an async function itself, not a synchronous factory returning an awaitable.
For a host bootstrap action rather than a model proposal, set origin="host" when
wrapping it. Tool kwargs cannot change the recorder's origin or event IDs.

An out-of-policy agent tool still executes in shadow mode. Inspection emits a
`disallowed_tool` finding with request/completion evidence IDs. Host-origin calls
are visible but excluded from this agent-tool allowlist rule.

## What outcomes mean

- returned: the Python callable returned. This does not prove a remote send, write
  or other downstream operation succeeded. A returned error object is still returned.
- raised: the callable raised, including cancellation. It may already have caused
  side effects. The recorder does not store the exception message.
- unknown: a recorded request has no completion. This is not evidence of blocking
  or success, and must never cause automatic replay.

The recorder stores only run/call/event IDs, sequence, UTC timestamp, agent/tool name,
origin, policy fingerprint, outcome and elapsed milliseconds. It never serializes
arguments, return values, prompts, exception messages or provider credentials.

## Audit failures and concurrency

A request is flushed and fsynced before invoking the tool. Completion is recorded
after the callable returns or raises. Journal creation is exclusive with 0600 file
permissions on supported POSIX filesystems. Threads and async tasks may share a
recorder; only journal writes are serialized, not tool execution.

If a request cannot be durably recorded, AuditWriteError has
action_may_have_executed=False and the tool is not called. A completion-write failure
raises AuditWriteError with action_may_have_executed=True. Do not automatically retry
that action. An I/O-failed recorder refuses later calls even if storage recovers.

Use one writer per journal and join all calls before closing the recorder. Calls
that attempt completion after close cannot produce a durable completion. No file
resume, rotation, multi-process writer, automatic retry or cleanup is implemented.
Journals are limited to 10,000 events and inspection to 8 MiB; start another run
before reaching the limit. No retention or deletion policy runs automatically.

## Existing investigator example

After `make install`, run from the repository root with a new output path:

```bash
PYTHONPATH=integrations/python .venv/bin/python integrations/python/examples/investigator.py --output /tmp/new-investigator-run.jsonl
```

This invokes the repository's actual EvidenceTools over a small in-memory replay:
a host initial read, an allowed query and a deliberately out-of-policy summary read.
It records three real tool invocations and one allowlist finding. Dispatch is scripted;
there is no model, attack-success measurement, real customer data or remote send.
It does not instrument the production investigator worker automatically.

## Trust and coverage limits

Pass the same owner Policy to inspection. Its fingerprint must match the journal;
never reconstruct trusted policy from agent text or silently swap policies afterward.
The fingerprint binds a policy version but is not a signature or proof of provenance.
A process or user with journal access can alter records. A compromised agent runtime
can bypass wrappers; this is not a sandbox or protection against arbitrary Python code.

Only explicitly wrapped calls are observed. capture_complete is null because a
journal cannot prove that the host instrumented every possible path. The first rule
checks tool names only, not recipients, resource scope, sensitive-data lineage or
intent. A violation can be benign policy misconfiguration. No prompt-injection
resistance, malicious-intent inference or production detection rate is claimed.

The dedicated security API, upload command, review UI and README animation are later
milestones in docs/plans/agent-security-product.md. OpenAI Agents SDK and LangGraph
adapters are not implemented yet.
