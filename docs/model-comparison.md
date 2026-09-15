# Model comparison

Reproduce with `make compare` (`ml/training/compare.py`, ~5 minutes).

## What is being compared, and what is not

One task, one split, every method seeing identical rows: per-line binary
classification of BGL's CRITICAL subset, fitted on rows before 2005-09-01 and
scored on the 222,395 rows in the five months after.

**These numbers are not comparable to published BGL results.** The literature
groups lines into sessions or sliding windows and classifies the *window*,
usually over the full 4.7M-line corpus. A window holding one alert among a
hundred lines is far easier to flag than the line itself, and the severity gate
here has already removed the 82% of the corpus where an `if` statement suffices
— every remaining row is CRITICAL, and 41.6% of them are real alerts. Published
F1 figures above 0.95 on BGL describe a different and easier problem. Compare
methods within this table, not against papers.

Two axes vary. **Parser**: `none` is the lowercased message, which is what the
service ships; `regex` is the template variant in `ml/training/templates.py`;
`drain3` is Drain (He et al. 2017) via `drain3==0.9.11`, fitted on the training
window and then frozen, so test lines are matched rather than learned.
**Classifier**: `lookup` memorises each template's majority label — the classic
template-frequency baseline; `logreg`, `tree` and `svm` are loglizer's supervised
trio; `rf` is what this repo ships.

Every supervised method gets its threshold fitted the same way, on a
chronological holdout inside the training window, so none is handicapped by an
arbitrary 0.50 and none sees the test window while tuning.

## Results

| method | precision | recall | f1 | roc-auc |
| --- | ---: | ---: | ---: | ---: |
| always alert | 0.416 | 1.000 | 0.588 | – |
| shipped heuristic (previous) | 0.416 | 1.000 | 0.588 | 0.407 |
| novelty: unseen regex template | 0.792 | 0.715 | 0.752 | 0.791 |
| novelty: unseen drain3 template | 0.847 | 0.695 | 0.764 | 0.803 |
| lookup: regex majority label | 1.000 | 0.285 | 0.444 | 0.952 |
| lookup: drain3 majority label | 1.000 | 0.303 | 0.465 | 0.969 |
| drain3 + tree | 0.416 | 1.000 | 0.588 | 0.651 |
| drain3 + svm | 0.996 | 0.303 | 0.465 | 0.950 |
| drain3 + rf | 0.994 | 0.304 | 0.465 | 0.966 |
| drain3 + logreg | 0.838 | 1.000 | 0.912 | 0.957 |
| none + tree | 0.416 | 1.000 | 0.588 | 0.961 |
| none + svm | 0.883 | 0.934 | 0.908 | 0.992 |
| none + logreg | 0.847 | 1.000 | 0.917 | 0.997 |
| regex + rf | 0.903 | 0.934 | 0.918 | 0.992 |
| regex + logreg | 0.908 | 0.991 | 0.948 | 0.995 |
| regex + tree | 0.977 | 0.924 | 0.949 | 0.954 |
| regex + svm | 0.980 | 0.934 | 0.956 | 0.979 |
| **none + rf (shipped)** | **0.914** | **1.000** | **0.955** | **0.999** |

The shipped artifact is `none + rf`. `ml/training/evaluate.py` reports it at
precision 0.947 / recall 1.000 / **f1 0.973** / **roc-auc 0.999**, slightly above
the row above because `pipeline.py` picks its threshold on a fixed grid while
`compare.py` uses score quantiles so that SVM decision values are treated on
equal terms. Same model, same split, different threshold-selection procedure.

## The finding: templating the message makes it worse

Abstracting variable parts away — replacing paths, addresses and numbers with
placeholders — is the standard first step for log data and the entire purpose of
Drain. Here it loses, consistently, at every level of abstraction and under
every classifier. By threshold-free ROC-AUC:

| parser | logreg | tree | svm | rf |
| --- | ---: | ---: | ---: | ---: |
| none (lowercase only) | 0.997 | 0.961 | 0.992 | **0.999** |
| regex templates | 0.995 | 0.954 | 0.979 | 0.992 |
| drain3 | 0.957 | 0.651 | 0.950 | 0.966 |

Abstracting *less* beat abstracting *more*, monotonically. An intermediate
variant that masked only numbers and hex words, keeping paths, landed between
them (ROC-AUC 0.987), which is the same ordering.

The reason is visible when the held-out rows are split by whether their template
family was seen during training:

| held-out stratum | rows | raw text | templated |
| --- | ---: | ---: | ---: |
| familiar template | 138,864 (62.4%) | 1.0000 | 1.0000 |
| **novel template** | **83,531 (37.6%)** | **0.9891** | **0.9320** |

Templating was supposed to earn its keep precisely on novel families, by mapping
an unseen line onto a known template. It does the opposite: on familiar families
both are perfect, and on novel ones raw text is clearly better.

BGL's "variable" parts are not noise. `ciod: Error loading
/bgl/apps/SWL/performance/MINIBEN/...: invalid or missing program image` is a
user's own broken job and carries no alert, while `ciod: Error reading message
prefix on CioStream socket to 172.16.96.116:33399, Link has been severed` is a
real failure. The path segments and the socket address are the evidence for
which is which, and `<path>` deletes it. Only 9.7% of held-out rows repeat a raw
line seen in training, so this is not whole-line memorisation — it is shared
vocabulary below the template level.

## Other observations

- **Template lookup is high-precision and low-recall** (1.000 / 0.285). Memorising
  a template's majority label is right whenever it fires, and it fires on 62% of
  rows; it simply has nothing to say about the rest. Its respectable ROC-AUC
  (0.952–0.969) alongside a 0.444 F1 is the clearest case in this table of why a
  threshold-free ranking metric and an operating-point metric must both be read.
- **Novelty detection is a weak signal, not a null one.** "Flag any line whose
  template is new" reaches 0.75–0.76 F1 — well above the 0.588 bar — which says
  unseen message families really are enriched for alerts (79.2% of novel-template
  rows are alerts). It is not competitive with a supervised model, but it needs
  no labels.
- **Decision trees collapse to "always alert"** under two of three parsers
  (0.416 / 1.000 / 0.588, exactly the trivial baseline). The threshold fitted on
  the inner holdout lands below every leaf probability.
- **Drain3 + svm/rf lose most of their recall** (0.303) despite healthy ROC-AUC
  (0.950/0.966). The threshold chosen on the inner holdout did not transfer to the
  test window; the ranking is fine and the operating point is not.
- **Drain is fast and aggressive**: 313 clusters from 633,977 lines in 5 seconds,
  against 884 distinct regex templates. It collapses more than the hand-written
  rules do, and on this task that is the wrong direction.

## Limits

- One dataset, one split, one seed. `random_state=42` throughout; no
  repeated-run variance is reported.
- Drain is run with its documented masking set. A practitioner tuning
  `sim_th`/`depth` per dataset would likely do better, and no such tuning was done
  for any method beyond the shared threshold fit.
- The severity gate does the heavy lifting before any of this: on the full
  corpus, alerting on CRITICAL alone gives 100% recall at 41% precision. Every
  number here describes the residual problem inside that class.
- BGL is supercomputer RAS logging. Nothing here shows any of it transfers to
  application logs.
