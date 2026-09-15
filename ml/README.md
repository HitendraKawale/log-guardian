# ML

Data and training for Log Guardian's anomaly scorer.

## The dataset

[BGL](https://github.com/logpai/loghub), from Loghub: 4,747,963 lines logged by
a BlueGene/L supercomputer at Lawrence Livermore between June 2005 and January
2006. The first field of each line is `-` for a normal line, or an alert
category (`KERNDTLB`, `APPREAD`, `KERNSTOR`, …) assigned by the operators who
ran the machine. 41 categories, 348,460 alerts, 7.39% of the corpus.

That provenance is the point. The labels were written by people with no idea
what features anyone would later extract, so a model that scores well has found
something rather than inverted a formula.

```bash
python ml/data/download.py     # 55 MB zipped, 709 MB extracted, into ml/datasets/
```

Raw files are gitignored.

## Parsing

Ten fields, nine fixed and then free text:

```
Label Timestamp Date Node Time NodeRepeat Type Component Level Content

- 1117838570 2005.06.03 R02-M1-N0-C:J12-U11 2005-06-03-15.42.50.363779
  R02-M1-N0-C:J12-U11 RAS KERNEL INFO instruction cache parity error corrected
```

`ml/data/bgl.py` maps that onto the platform's own log shape (`service`,
`level`, `message`, `timestamp`) so the same featurizer serves training and the
live API. Three things about it are worth knowing before you trust its output.

**There are two timestamps and they disagree by seven hours.** Field 1 is a UTC
epoch, field 4 is Livermore local time. The parser uses the epoch, so anything
hour-of-day derived from it is a UTC hour. Pick the other one by accident and
every time feature shifts by seven.

**Severity collapses onto a smaller enum.** BGL has INFO, WARNING, ERROR,
SEVERE, FATAL and FAILURE; the platform has DEBUG through CRITICAL. SEVERE folds
into ERROR, and FATAL and FAILURE both become CRITICAL. That last merge is
lossy, and it's tolerable only because every labelled alert is FATAL or FAILURE
anyway.

**34,786 lines are dropped and the parser says so.** 34,470 are truncated before
the message; 316 have a severity field that isn't a severity, from rows where
the fixed-width prefix is misaligned. `ParseStats` counts both, because a
dataset that quietly loses 0.7% of its rows is a bad way to spend an afternoon.

## What the labels look like against our features

```bash
python ml/data/profile_bgl.py
```

Read the output before changing the model. The short version: severity alone
gives 100% recall at 40.7% precision, the `RISK_KEYWORDS` features are slightly
anti-correlated with real alerts, and component carries a 4× spread that nothing
currently uses. The [root README](../README.md#what-the-real-data-changed) has
the tables.

## Splitting

```bash
python ml/data/prepare.py      # -> ml/datasets/bgl_{train,test}.jsonl.gz
```

Two choices are baked in.

*Only CRITICAL lines.* Since every alert is CRITICAL, scoring all 4.7M rows
teaches a model the severity rule and nothing else. The candidate pool is the
856,372 CRITICAL lines, of which 40.7% are alerts — a nearly balanced problem
where the answer has to come from the message.

*Chronological, never shuffled.* BGL fails in bursts. 2005-06-12 is 152,183
lines that are all alerts, 2005-06-14 contributes exactly 65,536 (a saturated
counter, not a coincidence), and those two days are 62% of every alert in the
dataset. Shuffle and near-identical lines from one event land on both sides of
the split, so the model memorises the event and the score is a lie.

The cutoff is 2005-09-01: 633,977 training rows, 222,395 held out across five
months and four different alert regimes, with the two priors 1.3 points apart.
`--cutoff` moves it. Later dates shrink the test set and widen the prior gap;
2005-11-01 opens a 9-point gap.

## Baselines

```bash
python ml/training/baseline.py
```

| baseline | precision | recall | f1 | roc-auc |
| --- | --- | --- | --- | --- |
| always alert | 0.416 | 1.000 | 0.588 | – |
| never alert | 0.000 | 0.000 | 0.000 | – |
| shipped heuristic | 0.416 | 1.000 | 0.588 | 0.407 |
| component rule | 0.107 | 0.002 | 0.004 | – |

The heuristic in `analyzer.py` matches "alert on everything" exactly, and ranks
below random. The component rule is derived from the training window only —
letting it see test would flatter it — and it fails because the alert-prone
components it finds are rare afterwards.

**0.588 F1 and 0.5 AUC is the bar.** A model that doesn't clear both is
strictly worse than an `if` statement.

## The shipped model

`train_bgl.py` fits the artifact the service loads, on the real split.
`evaluate.py` scores it once on the held-out five months (222,395 rows the model
never saw, in a window starting after every row it was fitted on):

| | precision | recall | f1 | roc-auc |
| --- | --- | --- | --- | --- |
| shipped heuristic (previous) | 0.416 | 1.000 | 0.588 | 0.407 |
| **TF-IDF + random forest** | **0.947** | **1.000** | **0.973** | **0.999** |

Three things got it there, and two of them were bugs rather than modelling.

**The holdout was random.** `train_and_register` used
`train_test_split(shuffle=True, stratify=y)`. Given bursts where one day is
152,183 lines that are 100% alerts, that scatters near-identical lines across
both sides and scores memorisation as skill. It now cuts at a timestamp
boundary, and refits on the whole window once the threshold is settled.

**The threshold was assumed.** 0.50 is only meaningful for a calibrated model on
a balanced problem. It is now fitted on a chronological holdout *inside* the
training window and stored on the registry entry, so serving uses the operating
point the metrics describe.

**The features were the wrong ones.** The five numeric features carried almost
no signal on the CRITICAL subset: level is constant there by construction, and
the hand-written keywords are anti-correlated with real alerts. The message text
replaced them.

### What did not work: templating

The obvious move for log data is to template the message first — replace paths,
addresses and numbers with placeholders so one family collapses to one string.
That is what Drain exists to do and what this project planned to do. Measured,
it makes the model worse, and worst where it was supposed to help:

| held-out stratum | rows | raw text | templated |
| --- | ---: | ---: | ---: |
| familiar template | 138,864 (62.4%) | 1.0000 | 1.0000 |
| novel template | 83,531 (37.6%) | 0.9891 | 0.9320 |

BGL's variable parts are not noise: `ciod: Error loading /bgl/apps/SWL/...` is a
user's broken job and benign, and the path is the evidence for that.
`ml/training/templates.py` keeps the rejected variant, and
[`docs/model-comparison.md`](../docs/model-comparison.md) has the full table
against Drain3 and the loglizer classifiers.

### What the numeric features did

Each was added to the message text and measured on the inner validation split.
Every one made the model worse, so `features.py` no longer exports them:

| features | roc-auc | best f1 |
| --- | --- | --- |
| text only | **0.984** | **0.915** |
| \+ level ordinal | 0.974 | 0.910 |
| \+ message length | 0.960 | 0.863 |
| \+ hour of day | 0.955 | 0.860 |
| \+ digit count | 0.930 | 0.664 |
| \+ all four | 0.944 | 0.824 |

`hour_of_day` is the instructive one: it lets the model learn *when* the June
bursts happened instead of what they said. `level_ordinal` is constant on this
subset, so it can only add noise — the severity gate lives outside the model, as
an explicit rule, which is all the data supports. The registry records
`candidate_levels`, and the serving path scores 0.0 outside that pool rather
than extrapolating into severities it has no evidence about.

## Still synthetic

`generate_data.py`, `train.py` and `retrain.py` still fit on generated data via
`pipeline.train_and_register`. They work, and `make train` will produce a model,
but the metrics that lands in `registry.json` are measured against labels drawn
from a sigmoid over the same variables the featurizer reads. Treat them as a
smoke test that the pipeline runs, not a result. `make train-bgl` is what
produces the committed artifact.

## Layout

```
ml/
  data/
    download.py      fetch BGL from Zenodo
    bgl.py           parse it into the platform's log schema
    profile_bgl.py   label distribution vs. the current features
    prepare.py       critical subset -> chronological train/test split
  training/
    baseline.py      trivial baselines on the held-out window
    compare.py       shipped model vs. Drain3 and the loglizer classifiers
    evaluate.py      score the registered model on the held-out window
    generate_data.py synthetic generator (superseded, still wired to train.py)
    pipeline.py      train -> evaluate -> version -> register
    train.py         train on synthetic data (smoke test)
    train_bgl.py     train the shipped model on the real split
    retrain.py       train on synthetic + human feedback
  tests/             parser and split tests, fixture cut from real BGL lines
  datasets/          raw and prepared data (gitignored)
```

## Model registry

`services/ai-service/app/model/registry.json` tracks every trained version:
created time, source, sample count, metrics, and a `train_mean_score` baseline
the AI service uses for drift detection. Versioned `.joblib` artifacts sit next
to it but are gitignored; only the current model and the registry are committed.
