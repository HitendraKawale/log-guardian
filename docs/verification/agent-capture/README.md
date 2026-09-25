# Generic Python capture verification

Milestone 1 of issue #47. This verifies a local recorder, not a completed security
monitoring service or measured prompt-injection defense.

## Executed checks

`make test`, `make test-demo`, `make lint` and `git diff --check` passed:

```text
661 offline tests passed
6 demo tests passed, 2 existing warnings
All checks passed!
375 files already formatted
```

The 22 new recorder checks cover sync/async calls, exceptions and cancellation,
concurrent calls, exclusive files, policy fingerprints, invalid journals, write
failures, capacity, process exit and a network-forbidden investigator example.

The actual example ran as:

```bash
PYTHONPATH=integrations/python .venv/bin/python integrations/python/examples/investigator.py --output docs/verification/agent-capture/investigator.jsonl
```

The preserved journal and report show three actual EvidenceTools invocations over
in-memory fixture logs: host initial_logs, allowed query_logs, and summarize_logs
outside the owner's allowlist. All returned. The summary action was observed, not
blocked. Tool dispatch was scripted and no model was called.

## Package check

Built the wheel with pip wheel --no-deps --no-build-isolation. Installed it with
--no-index --no-deps into a temporary isolated environment. Python -I imported the
installed package from site-packages, wrapped a call, inspected the journal and
verified that private argument/result text was absent. Package metadata declared
zero runtime dependencies.

The first temporary-venv attempt failed because a copied uv-managed Python could
not resolve libpython3.11.dylib. Using symlinks=True fixed the environment creation;
the package code did not change. The package targets Linux/macOS, not Windows.

## Limits and remaining work

Tool-name policy only. No argument-level checks, automatic blocking, complete
instrumentation guarantee or proof of downstream effects. A callable returning an
error object is still recorded as returned. Unresolved calls remain unknown.

No security ingestion API, upload command, review UI or root README animation is
implemented in this milestone. Those remain the next product steps. No package was
published to a registry and no paid verifier batch was started.
