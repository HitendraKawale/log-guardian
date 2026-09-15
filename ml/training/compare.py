"""Compare the shipped scorer against established log-anomaly methods.

Everything here runs on one task and one split, because that is the only way the
numbers mean anything: per-line binary classification of BGL's CRITICAL subset,
trained on rows before 2005-09-01 and scored on the five months after.

    python ml/training/compare.py            # add --quick to subsample

**These numbers are not comparable to published BGL results.** The literature
(loglizer, Deeplog, LogRobust and the papers that follow them) groups lines into
sessions or sliding windows and classifies the *window*, usually over the full
4.7M-line corpus. A window containing one alert among a hundred lines is far
easier to flag than the line itself, and the severity gate here has already
removed the 82% of the corpus where an `if` statement suffices. Published F1
figures above 0.95 on BGL describe a different, easier problem. The comparison
that means something is the one below, where every method sees identical rows.

Two axes vary:

*Parser* -- how a raw line becomes a comparable token sequence. ``none`` is the
lowercased message, which is what the service ships; ``regex`` is the template
variant in ``templates.py``, measured and rejected; ``drain3`` is the
Drain algorithm (He et al. 2017), the standard log parser, fitted on the
training window only and then frozen so test lines are matched, never learned.

*Classifier* -- ``lookup`` memorises each template's majority label, the classic
template-frequency baseline. ``logreg``, ``tree`` and ``svm`` are loglizer's
supervised trio. ``rf`` is what this repo ships.

Every supervised method gets its decision threshold fitted the same way, on a
chronological holdout inside the training window, so none of them is handicapped
by an arbitrary 0.50 and none of them sees the test window while tuning.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AI_SERVICE = REPO_ROOT / "services" / "ai-service"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(AI_SERVICE))

from app.analyzer import HeuristicAnalyzer  # noqa: E402
from app.schemas import AnalyzeRequest  # noqa: E402

from ml.data.prepare import TEST_PATH, TRAIN_PATH, read_jsonl  # noqa: E402
from ml.training.pipeline import chronological_split  # noqa: E402
from ml.training.templates import normalize_message  # noqa: E402


def drain_parser(train_messages: list[str]):
    """Fit Drain on the training window, then freeze it.

    Drain is an online parser: ``add_log_message`` grows the cluster tree. Test
    lines go through ``match`` instead, which assigns an existing cluster or
    returns None, so the parser cannot adapt to the window it is being scored
    on -- the same discipline the model itself is held to.
    """
    from drain3 import TemplateMiner
    from drain3.masking import MaskingInstruction
    from drain3.template_miner_config import TemplateMinerConfig

    config = TemplateMinerConfig()
    config.profiling_enabled = False
    # Drain's documented masking set: without it the parameter tokens explode
    # the cluster count and the comparison would be unfair to Drain.
    config.masking_instructions = [
        MaskingInstruction(r"((?<=[^A-Za-z0-9])|^)(\d{1,3}\.){3}\d{1,3}(?=[^A-Za-z0-9]|$)", "IP"),
        MaskingInstruction(r"((?<=[^A-Za-z0-9])|^)0x[a-fA-F0-9]+(?=[^A-Za-z0-9]|$)", "HEX"),
        MaskingInstruction(r"((?<=[^A-Za-z0-9])|^)[\-\+]?\d+(?=[^A-Za-z0-9]|$)", "NUM"),
        MaskingInstruction(r"(?<=executed cmd )(\".+?\")", "CMD"),
    ]
    miner = TemplateMiner(config=config)
    for message in train_messages:
        miner.add_log_message(message)

    def parse(message: str) -> str:
        cluster = miner.match(message)
        return cluster.get_template() if cluster is not None else "<unmatched>"

    return parse, miner


def score_at(y_true, scores, threshold):
    from sklearn.metrics import precision_recall_fscore_support

    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true, (scores >= threshold).astype(int), average="binary", zero_division=0
    )
    return float(precision), float(recall), float(f1)


def fit_threshold(y_true, scores):
    """Pick the threshold maximising F1, over quantiles of the score range.

    Quantiles rather than a fixed 0..1 grid so methods without a probabilistic
    output (SVM decision values) are treated on equal terms.
    """
    import numpy as np
    from sklearn.metrics import f1_score

    grid = np.unique(np.quantile(scores, np.linspace(0.001, 0.999, 200)))
    if grid.size == 0:
        return 0.5
    f1s = [f1_score(y_true, (scores >= t).astype(int), zero_division=0) for t in grid]
    return float(grid[int(np.argmax(f1s))])


def model_scores(estimator, features):
    if hasattr(estimator, "predict_proba"):
        return estimator.predict_proba(features)[:, 1]
    return estimator.decision_function(features)


def run_supervised(name, classifier, parse, inner_fit, inner_val, train, test, results):
    """Fit, choose a threshold on the inner holdout, then score the test window."""
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics import roc_auc_score

    started = time.time()
    vectorizer = TfidfVectorizer(
        analyzer="word", token_pattern=r"\S+", ngram_range=(1, 2), min_df=2, sublinear_tf=True
    )
    x_inner = vectorizer.fit_transform([parse(r["message"]) for r in inner_fit])
    y_inner = np.array([r["label"] for r in inner_fit])
    classifier.fit(x_inner, y_inner)

    val_scores = model_scores(
        classifier, vectorizer.transform([parse(r["message"]) for r in inner_val])
    )
    threshold = fit_threshold(np.array([r["label"] for r in inner_val]), val_scores)

    # Refit on the full training window now that the threshold is settled.
    vectorizer_full = TfidfVectorizer(
        analyzer="word", token_pattern=r"\S+", ngram_range=(1, 2), min_df=2, sublinear_tf=True
    )
    x_train = vectorizer_full.fit_transform([parse(r["message"]) for r in train])
    classifier.fit(x_train, np.array([r["label"] for r in train]))

    y_test = np.array([r["label"] for r in test])
    scores = model_scores(
        classifier, vectorizer_full.transform([parse(r["message"]) for r in test])
    )
    precision, recall, f1 = score_at(y_test, scores, threshold)
    results.append(
        (name, precision, recall, f1, float(roc_auc_score(y_test, scores)), time.time() - started)
    )


def run_lookup(name, parse, train, test, results):
    """Classic template-frequency baseline: memorise each template's majority label."""
    import numpy as np
    from sklearn.metrics import roc_auc_score

    started = time.time()
    counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for record in train:
        counts[parse(record["message"])][record["label"]] += 1
    prior = sum(r["label"] for r in train) / len(train)

    scores = np.array(
        [
            (lambda c: c[1] / (c[0] + c[1]) if c[0] + c[1] else prior)(
                counts.get(parse(r["message"]), [0, 0])
            )
            for r in test
        ]
    )
    y_test = np.array([r["label"] for r in test])
    precision, recall, f1 = score_at(y_test, scores, 0.5)
    results.append(
        (name, precision, recall, f1, float(roc_auc_score(y_test, scores)), time.time() - started)
    )


def run_novelty(name, parse, train, test, results):
    """Unsupervised: flag any line whose template was never seen in training."""
    import numpy as np
    from sklearn.metrics import roc_auc_score

    started = time.time()
    seen = {parse(r["message"]) for r in train}
    scores = np.array([0.0 if parse(r["message"]) in seen else 1.0 for r in test])
    y_test = np.array([r["label"] for r in test])
    precision, recall, f1 = score_at(y_test, scores, 0.5)
    auc = float(roc_auc_score(y_test, scores)) if len(set(scores.tolist())) > 1 else float("nan")
    results.append((name, precision, recall, f1, auc, time.time() - started))


def run_trivial(train, test, results):
    import numpy as np
    from sklearn.metrics import roc_auc_score

    y_test = np.array([r["label"] for r in test])
    ones = np.ones(len(test))
    precision, recall, f1 = score_at(y_test, ones, 0.5)
    results.append(("always alert", precision, recall, f1, float("nan"), 0.0))

    started = time.time()
    analyzer = HeuristicAnalyzer()
    scores = np.array(
        [
            analyzer.analyze(
                AnalyzeRequest(
                    service=r["service"],
                    level=r["level"],
                    message=r["message"],
                    timestamp=r["timestamp"],
                )
            ).anomaly_score
            for r in test
        ]
    )
    precision, recall, f1 = score_at(y_test, scores, HeuristicAnalyzer.threshold)
    results.append(
        (
            "shipped heuristic (old)",
            precision,
            recall,
            f1,
            float(roc_auc_score(y_test, scores)),
            time.time() - started,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--quick", type=int, default=0, help="subsample to N training rows for a fast smoke run"
    )
    args = parser.parse_args()

    for path in (TRAIN_PATH, TEST_PATH):
        if not path.exists():
            raise SystemExit(f"{path} not found - run: python ml/data/prepare.py")

    from sklearn.ensemble import RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.svm import LinearSVC
    from sklearn.tree import DecisionTreeClassifier

    train = read_jsonl(TRAIN_PATH)
    test = read_jsonl(TEST_PATH)
    if args.quick:
        train = sorted(train, key=lambda r: r["timestamp"])[:: max(1, len(train) // args.quick)]
        test = test[:: max(1, len(test) // args.quick)]
    inner_fit, inner_val = chronological_split(train)

    print(f"train {len(train):,} | inner holdout {len(inner_val):,} | test {len(test):,}")
    print("fitting Drain on the training window ...", flush=True)
    started = time.time()
    drain_parse, miner = drain_parser([r["message"] for r in train])
    print(
        f"  {len(miner.drain.clusters):,} Drain clusters in {time.time() - started:.0f}s; "
        f"{len({normalize_message(r['message']) for r in train}):,} regex templates"
    )

    parsers = {
        "none": lambda m: m.lower(),
        "regex": normalize_message,
        "drain3": drain_parse,
    }

    results: list[tuple] = []
    run_trivial(train, test, results)
    for parser_name in ("regex", "drain3"):
        run_novelty(
            f"novelty: unseen {parser_name} template", parsers[parser_name], train, test, results
        )
        run_lookup(
            f"lookup: {parser_name} majority label", parsers[parser_name], train, test, results
        )

    supervised = [
        ("logreg", lambda: LogisticRegression(max_iter=2000)),
        ("tree", lambda: DecisionTreeClassifier(min_samples_leaf=5, random_state=42)),
        ("svm", lambda: LinearSVC(C=1.0, dual="auto", max_iter=5000)),
        (
            "rf (shipped)",
            lambda: RandomForestClassifier(
                n_estimators=200, min_samples_leaf=5, n_jobs=-1, random_state=42
            ),
        ),
    ]
    for parser_name in ("none", "regex", "drain3"):
        for clf_name, make in supervised:
            label = f"{parser_name} + {clf_name}"
            print(f"  running {label} ...", flush=True)
            run_supervised(
                label, make(), parsers[parser_name], inner_fit, inner_val, train, test, results
            )

    print(f"\n  {'method':<34s}{'prec':>7s}{'recall':>8s}{'f1':>8s}{'roc-auc':>9s}{'fit':>8s}")
    for name, precision, recall, f1, auc, elapsed in results:
        auc_text = "      -" if auc != auc else f"{auc:9.3f}"
        print(f"  {name:<34s}{precision:7.3f}{recall:8.3f}{f1:8.3f}{auc_text}{elapsed:7.0f}s")


if __name__ == "__main__":
    main()
