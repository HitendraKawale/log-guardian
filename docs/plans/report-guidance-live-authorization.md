# Report-guidance live authorization

The owner approved a new live test and then approved local freeze commits with "ues"
in response to the explicit proposal: the same four synthetic e-commerce cases,
gpt-4.1-mini-2025-04-14, maximum 24 requests, USD 0.025 estimated allowance per case
and USD 0.10 total, no retries, no push and no deployment.

New one-shot ledger: security-report-guidance-2026-09-26-03, in the shared git directory.
Both earlier allowances remain closed. An existing ledger refuses execution, including
an interrupted attempt. Unused request slots or reservations do not authorize a rerun.

## Candidate and inputs

The application candidate is 147444fdada01becc86415d5a5ab58ee30eba4de. Relative to the
preceding live candidate, only security report guidance changed in application code.
It clarifies outcome/cause consistency, asks for shorter reports and properly supported
citations, and retains uncertainty about actors, sessions and business effects.
Report validators, citation IDs, 1024 output tokens, model and retry limits are unchanged.

Use byte-identical evals/business-model-smoke/inputs.json and the same owner source registry.
These four development cases were already inspected and used to revise the guidance.
This is not independent, held-out or customer-traffic evaluation. Evaluator notes stay
outside provider inputs. No passwords, customer identities, tokens or cookies are present.

Freeze runner, application, input and dependency hashes before sending. Commit the
snapshot locally, verify a clean tree and the candidate's application bytes, and use
isolated databases with actual import/promotion routes and the existing run_once worker.
No continuous provider worker may run. A mock rehearsal must verify all 35 rows arrive
and capture preserves native schema order. Offline tests do not establish model quality.

## Paid boundary

Keep the fixed OpenAI endpoint, default billing tier, six requests per case and 24 total,
USD 0.025 per case and USD 0.10 total conservative reservation ceilings. Reserve and fsync
before sending. Preserve exact request JSON and its hash; save responses before dispatch.
SDK and HTTP retries stay disabled. No automatic repair, continuation or report retry.
Stop on ambiguous usage, provider/transport/capture failure or worker interruption.
Known-usage invalid or truncated reports remain failures; remaining approved cases may run.

Pricing uses the preserved official reference in evals/security-live-smoke/pricing.txt:
USD 0.40 input, USD 0.10 cached input, USD 1.60 output per million tokens. Reservations
use uncached input pricing. This is an estimate, not a provider billing guarantee.

Preserve every response and failure, close the allowance, and review claims separately
from schema acceptance. Compare to the prior batch without claiming causality from a
single repeat. No independent review, production readiness, detection accuracy,
automatic remediation, further live calls, push or production deployment is authorized.
