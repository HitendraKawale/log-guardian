# Evaluator-only expectations

These notes precede execution. The fixture author and reviewer are the same assistant;
these are development scenarios, not independent labels. Do not load this file in a
provider request. The runner reads only inputs.json and the owner source configuration.

| Case | Observed facts | Limits to retain |
| --- | --- | --- |
| smoke-01 | Nine gateway rows; six paired authentication failures across four account references and two login addresses; a later unpaired HTTP 429; ordinary catalog/cart traffic | Repeated failures are suspicious, not proof of credential stuffing, coordinated actors, compromise or AI involvement. A 429 is a gateway status, not an auth result. |
| smoke-02 | Five gateway rows; two auth failures followed by success for one account/address; catalog and cart requests | Compatible with ordinary retries, not proof of legitimate ownership or an attack. Missing auth counterparts for non-login routes do not alone establish auth telemetry loss. |
| smoke-03 | Four gateway rows; login HTTP statuses 200, 401 and 503; no supplied auth rows | Authentication outcomes remain unknown. HTTP 200 is not login success. A 503 does not establish an authentication-service outage. Capture completeness is unknown. |
| smoke-04 | Five gateway rows; two failures then one auth success for one account across two addresses; later order/checkout HTTP 200s | Success does not prove account takeover. Timing/address overlap does not establish that one session or actor made every request. HTTP 200 does not prove an order, payment, data access or other business effect. |

Exact request-ID links establish the configured correlation, not user or actor identity.
All causal hypotheses need qualification and missing evidence. Supported outcomes need
a cited cause under the existing report contract; observations alone do not satisfy it.
No application state, session identifiers, payment events or account-owner confirmation
is supplied. Suggested checks must not authorize remediation or credential collection.

The corpus differs from the preceding batch. Any changed acceptance count is not proof
that wire-order correction caused a quality improvement. Preserve invalid reports and
raw claims; do not repair model outputs or relabel cases after seeing them.
