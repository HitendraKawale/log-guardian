# Juice Shop business test

Five final browser-driven cases passed through Log Guardian's real import API and no-model
assessment. The records came from a running nginx gateway and instrumented Juice Shop
password-login decisions, not from a script inventing authentication outcomes.

This establishes a bounded integration result. It does not establish attack detection accuracy,
production capacity or usefulness to an independent business. The shop is intentionally
vulnerable and all accounts, products and activity are synthetic.

## Versions and changes

- Log Guardian: `d150fac52414cf0ede06bc20443dc199dd094df6`, merged PR #53. No product code changed.
- Juice Shop: `v20.2.0`, `5658473cf8814459bf89000ce373b20ed0b4eb37`, MIT. See `juice-shop-LICENSE.txt`.
- Four added lines in `routes/login.ts` import/call a new opt-in recorder. Its seven unit tests
  and one real-API test are preserved with the patch and test source.
- The recorder emits explicit success, failure or unavailable at the corresponding decision.
  Success follows session registration. Account references are HMAC pseudonyms. Source events
  contain no password, token, plaintext email or recovery answer.
- This first hook covers password login, including its MFA-required branch. It does not cover
  MFA completion, OAuth, account recovery, orders or payments.
- The source release has no root lockfile. The first `npm ci` attempt was a setup error.
  Documented `npm install` then exposed a build incompatibility: resolved Angular 22.2.0 emits
  `browser-stats.json`, while the release's SBOM command expects `stats.json`. The owner
  authorized fixing the lab build. `Dockerfile.baseline` adjusts that input path without
  disabling SBOM generation. The generated CycloneDX BOM contains 672 components.
- Resolved lockfiles, image identifiers and source hashes are preserved. Dependencies were
  resolved at build time; this is not a claim of deterministic dependency resolution.

## What ran

A real browser registered a new account, logged in, added a product to its authenticated basket,
submitted incorrect passwords, retried successfully, and used the guest basket. It then uploaded
captured files using Log Guardian's browser. No application responses were mocked. Credentials
and authentication response bodies were not archived.

| Final case | Gateway records | Auth failures | Auth successes | Confirmed links | Records reviewed |
| --- | ---: | ---: | ---: | ---: | ---: |
| Normal customer | 28 | 0 | 1 | 1 | 29/29 |
| Wrong password | 32 | 1 | 0 | 1 | 33/33 |
| Retry | 43 | 2 | 1 | 3 | 46/46 |
| Guest browsing | 46 | 0 | 0 | 0 | 46/46 |
| Missing auth export | 28 | 0 | 0 | 0 | 28/28 |

That is 182 records across five reviews, but only 154 unique source records. The missing-auth
case deliberately reuses the normal customer's gateway window and omits its actual auth event.
It is an evidence-omission test, not a second independently observed incident.

The baseline reviewed every saved record and displayed 12 facts per case: one summary and
11 event facts. It disclosed the omitted event facts. All reports remained inconclusive.
Gateway success with omitted auth evidence did not become a successful-login claim.

The guest basket is client-side state in this shop. Its UI changed, but that is not evidence of a
server-side cart mutation or a purchase. The authenticated basket operation returned HTTP 200
with a saved item and quantity 1; the visible basket count also became 1.

A separate benign request supplied its own request ID. nginx replaced it, and the emitted
application failure and gateway record shared the new ID. This check was not imported as a
sixth final case.

## Verification output

The local Log Guardian suites ran with provider and telemetry variables empty:

```text
make test: 840 passed across its seven suites
make test-demo: 6 passed
make lint: All checks passed! / 556 files already formatted
Security browser suite: 17 passed in 41.38s
LG_VERIFY_EXIT=0
```

Upstream checks are not all green. The complete API suite has the same 21 failing test names
before and after instrumentation, including required internet-resource checks blocked by the
isolated network. Additional failures concern upstream challenge behavior and an IP expectation.
They were not fixed, suppressed or attributed to the logging hook.

| Check | Baseline | Instrumented |
| --- | --- | --- |
| Server suite | 393 passed, 2 skipped | 420 passed, 2 skipped |
| API suite | 509 passed, 21 failed, 7 skipped | 510 passed, 21 failed, 7 skipped |
| TypeScript build | Passed | Passed |
| Full lint | Passed | Passed |
| Refactoring Safety Net | Passed | Passed |

The differing server totals are the runner's recorded output, not an assertion that 27 new
tests were written. Seven recorder tests were added. The dedicated recorder run reports seven
passed, 100% line/function coverage and 95.65% branch coverage. The new real-API test verifies
unchanged login responses with auditing disabled and explicit failure/success/unavailable
records when enabled. Both tests were first run against missing functionality and failed.

Final business output:

```text
PASS: five real-business log reviews; no model calls or invented authentication records.
BUSINESS_EXIT=0
PASS: nginx replaced the caller-selected request ID; gateway and actual auth decision share the generated ID.
```

The standalone verifier uses only the standard library, not Log Guardian's report builder:

```bash
python3 verify.py.txt
shasum -a 256 -c SHA256SUMS
```

It compares input hashes, exact-ID links, source outcomes and timestamps, displayed claim
fields, citation membership, mandatory unknowns and coverage counts. It does not perform a
general semantic entailment evaluation.

The independent database check found six saved cases and 183 unique stored records. One case
with 29 records belongs to the preserved partial attempt before the final five-case run.
There are zero Investigation rows and zero InvestigationEvent rows. History reload retained
the retry counts and required re-entering the review key. Browser storage remained empty in
Log Guardian. Desktop/mobile checks and keyboard citations passed.

## Failures and limits retained

`business-results-failed-01` through `-04` preserve the earlier attempts:

1. The driver waited for network idle, which Socket.IO long polling prevents. A separate probe
   identified the pending `/socket.io/` request. The driver now waits for visible controls.
2. Juice Shop's Security Question label intercepts clicks on its dropdown. Keyboard selection
   worked in a real browser and is used by the driver. Mouse interaction was not repaired.
3. The driver incorrectly expected HTTP 201 from the basket handler. The actual handler saves
   the item and returns HTTP 200. The assertion now checks its documented source behavior,
   saved quantity and visible basket state.
4. A broad Login text locator matched both the menu and heading. The driver now selects the
   heading. This attempt had already saved one valid normal-customer review; that case remains.

The independent verifier also initially treated plain-string checklist entries as cited
findings. Its failure is preserved. Citation checks now apply to facts and hypotheses, while
checklist entries are separately required to be nonempty strings.

The minimal nginx configuration does not support the shop's WebSocket upgrade. A follow-up
browser probe recorded a `/socket.io/` handshake 400 and one console error. Gateway windows
also contain HTTP 499 records around browser closure. These records remain in the imports.
The REST/browser workflows completed despite that error, but the test does not establish a
clean WebSocket integration. No JavaScript page errors were observed.

No paid model calls, real business data, production deployment, attacks against external
systems, real payments or automatic remediation occurred. Upstream regression tests include
the shop's own local challenge tests inside network-isolated containers; the five business
scenarios use ordinary customer actions, not exploit challenges.

## Local inspection and containment

- Shop: http://127.0.0.1:8490/
- Review: http://127.0.0.1:8492/security.html?api=http://127.0.0.1:8491
- API: http://127.0.0.1:8491/health

Commands used: `docker compose -f /tmp/lg-juice-business/compose.yml up -d` and the shared
venv's Python running `/tmp/lg-juice-business/start_lg.py`. Portless had no active routes;
these pinned loopback URLs avoid changing the shared proxy.

The shop runs as UID 65532, with all capabilities dropped, no host/home mounts, no published
port and only an internal Docker network. An external TCP probe returned ENETUNREACH. nginx
has a second host-facing network because Docker Desktop did not expose its loopback port on
an internal-only network. Only nginx publishes port 8490, bound to 127.0.0.1.

Log Guardian uses a separate SQLite database, a private review key, empty execution/provider
keys and no worker. The owner-only `/tmp/lg-juice-business/runtime.json` contains local runtime
credentials and API/frontend PIDs. It is intentionally absent here. The shop's `shop.env`,
SQLite databases, browser storage and authentication response bodies are also excluded.
Do not paste the runtime file into a review or commit it. Test sources contain synthetic/public
fixture values, not the live lab credentials.

The source logs and completed reports are archived without rewriting. Credential scans found
no runtime key, generated account email, password, recovery answer or JWT in the copied
artifacts. Screenshots mask shop login fields and show no plaintext review key.

## Repeating the experiment

These are local experiment scripts with the recorded paths, not a supported installer.
Use a fresh isolated worktree/database and fresh private runtime values for another run.
Do not rerun the registration driver against an existing account and call it a fresh experiment.

1. Check out the recorded Juice Shop revision. Create `baseline.tar` with `git archive HEAD`
   before applying `juice-shop-audit.patch`.
2. Copy the preserved Dockerfiles/configuration and `.py.txt` scripts into a new temporary lab,
   restoring the `.py` suffix. Adjust their lab/repository paths if different.
3. To reuse the recorded dependency resolutions, add these instructions to the baseline
   Dockerfile before `RUN npm install`: `COPY server-resolved-lock.json /juice-shop/package-lock.json`
   and `COPY frontend-resolved-lock.json /juice-shop/frontend/package-lock.json`. Keep the recorded
   Node image digest and SBOM path compatibility edit. Confirm build, SBOM, tests and RSN again.
4. Apply the audit patch to the source checkout. Populate `overlay/` with the changed login
   route, recorder and unit test. Copy the real-API test to the build context. Build baseline,
   instrumented and runtime images in that order.
5. Run the restored `create-runtime.py` to generate fresh private inputs. It refuses to overwrite
   an existing runtime manifest and checks that the ports are free. Never use customer credentials
   or configure a provider for this test.
6. Launch the task-named stack and local API/frontend, verify isolation/readiness, then run
   `run.py`, `request-id-check.py`, `verify.py` and `postchecks.py` in that order. The retained
   partial-run case makes the recorded postcheck expect six cases; a fresh lab must instead
   expect five, unless its own earlier attempts created additional cases. Read the retained
   failures before interpreting a failed new run.

Cleanup is owner-operated and applies only to this lab. Stop the two PIDs named in its runtime
manifest after verifying their command lines; use `docker compose -f /tmp/lg-juice-business/compose.yml down`
for this stack. Keep the data and evidence until the owner chooses retention. Do not stop older
viewers or remove other worktrees, containers or shared Docker resources.
