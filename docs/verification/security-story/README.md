# Business-security explanation and recording

Issue #48. The user approved this documentation/demo milestone with "just do it".
The README now leads with the gateway/authentication workflow. The optional agent
recorder, older SVG prototype and operational research remain separate and intact.
No paid model calls, customer traffic, public deployment or merge occurred.

## What was recorded

`frontend/media/security-review.webm` is a 38-second, 1280 x 900 VP8 recording of actual
browser actions against the real API, SQLite database and worker. The six records come
from `examples/security-review/`. They yield three exact-ID links, two auth failures and
one success. That is not enough to establish credential stuffing or compromise.

The existing security_stack test fixture supplies an httpx.MockTransport provider.
Its response uses a citation from evidence actually delivered to the worker. Token
counts are synthetic. The displayed USD 0.00020000 is an estimate calculated from those
invented counts, not money spent. There is no real provider fallback or product fake mode.

The capture adds a persistent test-only banner and explanatory text above the real UI.
It does not replace application data or mock browser API responses. Four-second holds
make each stage readable; assertions, not those holds, wait for application state.
The recording is silent and has an adjacent text transcript. Native controls provide
play, pause, seeking and fullscreen; there is no autoplay, loop or custom animation.

Reproduce from the repository's tests directory, with Chromium installed:

```bash
LG_RECORD_DEMO=1 ../.venv/bin/python -m pytest \
  e2e/test_security_review_ui.py::test_security_walkthrough -q --tb=short \
  --basetemp=/tmp/lg48-walkthrough-recording
```

```text
1 passed in 40.32s
```

The test normally runs without presentation delays or video capture. Recording output
lands in pytest's temporary directory, never overwriting committed media automatically.
`recording-verification.txt` preserves this execution's output. `walkthrough.json`
contains the run, tool events, source/UI hashes, stage captions and runtime revision
020ee00. The recording test itself was added in this milestone; this is not a model
execution freeze. `security-review-poster.png` captures the saved case before execution.

## Browser and static-export verification

The new preview check first failed with a 404 and missing heading. After implementation,
the security-review and static-export suites reported:

```text
13 passed in 16.12s
```

The full browser suite ran from tests/ against the existing task-owned services:

```bash
INGESTION_URL=http://127.0.0.1:8480 \
AI_URL=http://127.0.0.1:8482 \
FRONTEND_URL=http://127.0.0.1:8480/ui \
../.venv/bin/python -m pytest e2e -q --tb=short \
  --basetemp=/tmp/lg48-story-e2e-final
```

```text
42 passed in 44.29s
```

`browser-verification.txt` records the full result. The new static-page check verifies
that the video loads, reports a finite duration, plays and pauses, makes no off-origin
requests, contains no form or script, and fits a 390px viewport. Reduced-motion mode
does not trigger playback. The transcript remains readable independently of the video.
Desktop and mobile screenshots were inspected and saved here.

The static exporter copies the native-video preview but still excludes the real
security uploader, its JavaScript/CSS and its operational navigation link. Existing
recorded operational runs remain available at the export's index. No public site was
redeployed.

Agent Browser separately opened the preview on the existing local server, inspected
native controls, played the video and observed currentTime advance to 16.05796 seconds
with duration 38 and error null. It reported no page errors or console messages.
The task session was closed. No new server, proxy configuration or provider worker
was started. Local inspection URL:

`http://127.0.0.1:8480/ui/security-preview.html`

## Documentation checks and limits

`make lint` reported:

```text
All checks passed!
398 files already formatted
```

README local file links were checked. The historical scoring-study body and research
archives were not changed. The new wording distinguishes operational evaluation figures
from security-case accuracy and qualifies old spending totals as historical.

The external `~/log-guardian-interview-qa.md` was corrected in place. It retains all
48 numbered questions and preserves the recorder/verifier experiments as optional or
historical work. It is not copied into this repository. The answers explicitly separate
case evidence, scripted-provider integration and unmeasured live-model judgment.

This milestone changes documentation, a read-only page, media and browser tests, not
production API or worker behavior. Service/ML/offline and container integration suites
were not rerun locally for this change. The prior checkpoint's CI run 36229166454 passed.
The existing pytest-asyncio configuration warning remains.

During recording-test development, an assertion incorrectly selected the last open
record, which was the gateway entry rather than auth/a1. Selecting the named auth record
fixed the check; application behavior did not change. The successful recording is from
the corrected test, not a splice of failed runs.

There was no independent review, live model evaluation or customer-capacity measurement.
The recording demonstrates the workflow, not the quality of security judgments. Future
paid evaluation still requires a fresh corpus, frozen candidate and current per-batch
authorization. Old spending allowances remain closed.
