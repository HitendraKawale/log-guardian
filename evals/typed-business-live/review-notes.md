# Synthetic business cases: author expectations

Written before model execution. These notes are evaluator-only, not provider input.
The same assistant authored and reviews these cases; there is no independent adjudicator.
The scenarios resemble e-commerce logging but were not sampled from production systems.
All records use the existing strict nginx and application-auth formats.

| Case | Supplied records | Material evidence | Limits and useful follow-up |
| --- | --- | --- | --- |
| smoke-01 | 11 gateway, 8 auth | Eight failures across four account references; two gateway HTTP 200s accompany failures; unpaired login 429 | Possible mistakes or unauthorized guessing, not confirmed attack. Inspect redacted rejection reasons. No recorded auth success. |
| smoke-02 | 5 gateway, 3 auth | Same source/account has failure, failure, success in timestamp order. All login HTTP responses are 200. | A retry is possible; account ownership and actor identity remain unknown. Inspect rejection reasons and session/activity context. |
| smoke-03 | 6 gateway, 0 auth | Login HTTP 200, 200, 401 and 503; catalog/cart traffic | No authentication outcome can be established. Obtain scoped auth-result records. No recording defect or outage is proven by an empty supplied file. |
| smoke-04 | 6 gateway, 2 auth | One auth failure then success for an account, with two login addresses. Later orders 201 and checkout/status 200 are unlinked. | Success is a recorded auth outcome, not compromise. No shared session, order creation, payment completion or authorized access is established. Inspect session policy and redacted activity audit. |

Row totals are 19/8/6/8, or 41 overall. Each fits the initial 25-record page by count;
verify byte bounds and actual delivered records in rehearsal and after the live run.

Assess the model's focus selections for relevance, not just validity. Counts summarize
patterns, auth events establish recorded outcomes, and gateway events establish HTTP
responses only. The allowed two hypothesis codes are broad possibilities and not an
exhaustive causal analysis. Choosing both does not prove malicious intent or a legitimate
retry. Empty selections are valid but may be unhelpful. A materially useful assessment
should prioritize the scenario's authentication evidence or its absence over catalog
traffic alone.

The application assembles factual text, mandatory unknowns and the inconclusive outcome.
Those outputs must not be credited as independent model reasoning or detection accuracy.
Preserve rejected selections rather than silently correcting them or changing labels.
