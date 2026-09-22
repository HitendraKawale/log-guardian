# Scripted pilot runner verification

This is not a live model evaluation. HTTP mock transport supplied 20 scripted
responses while the unchanged investigator worker executed against ten separate
SQLite databases. All ten cases completed with one linked tool request/completion
pair each. Provider decisions and reported token counts here are fabricated test
inputs. The cost/reservation fields exercise accounting and are not real charges.

The authorized packet contains ten cases. Each database contains only that case's
observations plus one synthetic inventory canary outside the owner scope. The
scripted full-scope queries did not expose the canary. Every case artifact includes
its fixture-to-database evidence-ID map, journal, report and scope review.

The transport saved each request reservation before HTTP and each response witness
before tool dispatch. Separate tests cover unknown tool proposals, which remain in
response witnesses even when the worker rejects them without a tool-request event.
They also cover one-shot ledger refusal, HTTP/timeout failures, invalid usage/model/
tier, candidate drift, pre/post-send storage failure, compression and credential echoes.

24 runner tests passed. All 506 offline tests and six demo tests passed; lint passed.
Logs: `/tmp/lg40-pilot-final-verified.log`, with earlier red logs under
`/tmp/lg40-pilot-*.log`. No real provider request, commit or publication occurred.
The shared live authorization ledger remains unclaimed.

Candidate digest:
`57bddee278208dac2c489b050649cfca44126cfc47784840b01f379043ec9502`.
`candidate/` preserves source bytes. `*.db.gz` are lossless copies of the closed
SQLite files, compressed with a fixed timestamp. JSON request/response witnesses,
case results and summary were copied without modification. Original scripted
files remain at:
`/var/folders/qz/ycfy4hxs01321rg_7tdl5kqr0000gn/T/lg40-investigator-pilot-scripted-rbn_zz0p/ledger`.

Verify from this directory with `shasum -a 256 -c SHA256SUMS`.
The checksum list covers the preserved artifacts, excluding this later README.
Independent review remains pending. No security effectiveness claim follows from
these scripted responses or from the passing infrastructure tests.
