# Fresh-case pricing check

Checked 2026-09-23 through Context7's indexed official OpenAI model documentation:
https://developers.openai.com/api/docs/models/gpt-4.1-mini

The retrieved pricing is USD 0.40 input, USD 0.10 cached input and USD 1.60 output
per million tokens. The batch retains gpt-4.1-mini-2025-04-14 and requests standard
service tier. Reservations and usage upper bounds ignore cache discounts.

The runner reserves serialized request bytes plus 4096 overhead tokens and the
1024-output-token maximum at noncached rates before sending. Returned usage must
fit this reservation, and the returned model/tier must match. This is conservative
accounting, not a billing receipt or guarantee against an upstream billing change.

The frozen production pricing table remains unchanged. This check supplies dated
execution provenance without changing the candidate or raising any allowance.
