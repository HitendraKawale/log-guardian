"""Corpus checks must fail on leakage or broken evidence, not merely parse JSON."""

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
from validate import load_cases, validate_corpus

ROOT = Path(__file__).resolve().parents[1]


def case(case_id, message):
    return {
        "schema_version": 1,
        "dataset_version": "1.0.0",
        "case_id": case_id,
        "provenance": "authored",
        "question": "Why are checkout requests failing?",
        "scope": {
            "services": ["checkout", "inventory"],
            "start": "2026-01-01T10:00:00Z",
            "end": "2026-01-01T10:10:00Z",
        },
        "logs": [
            {
                "evidence_id": case_id + ":1",
                "service": "checkout",
                "level": "ERROR",
                "message": message,
                "timestamp": "2026-01-01T10:05:00Z",
            }
        ],
    }


def label(row, variant):
    return {
        "dataset_version": "1.0.0",
        "case_id": row["case_id"],
        "variant_id": variant,
        "family": "upstream_latency",
        "expected_outcome": "supported",
        "expected_cause": "The upstream request exceeded its deadline.",
        "acceptable_alternatives": [],
        "supporting_evidence_ids": [row["logs"][0]["evidence_id"]],
        "forbidden_claims": ["The database is down."],
        "required_missing_evidence": [],
        "tags": [],
    }


def save(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


@pytest.fixture
def corpus(tmp_path):
    dev = case("dev-01", "inventory request exceeded deadline after 5000ms")
    test = case("test-01", "dns resolver returned SERVFAIL; upstream connection not attempted")
    rows = {"dev": [dev], "test": [test], "labels": [label(dev, "delay"), label(test, "dns")]}
    return tmp_path, rows


def check(corpus):
    root, rows = corpus
    save(root / "cases/dev.jsonl", rows["dev"])
    save(root / "cases/test.jsonl", rows["test"])
    save(root / "labels.jsonl", rows["labels"])
    return validate_corpus(root)


def test_valid_corpus_reports_counts_and_content_hashes(corpus):
    result = check(corpus)
    assert (result["dev"], result["test"], result["labels"]) == (1, 1, 2)
    assert len(result["sha256"]["cases/dev.jsonl"]) == 64
    before = result["sha256"]
    corpus[1]["dev"][0]["logs"][0]["message"] += "; retry exhausted"
    assert check(corpus)["sha256"]["cases/dev.jsonl"] != before["cases/dev.jsonl"]


@pytest.mark.parametrize("field", ["expected_cause", "true_label", "variant_id"])
def test_rejects_evaluator_fields_in_runtime_case(corpus, field):
    corpus[1]["dev"][0][field] = "leaked answer"
    with pytest.raises(ValueError, match="fields"):
        check(corpus)


def test_rejects_evaluator_fields_inside_log(corpus):
    corpus[1]["dev"][0]["logs"][0]["label"] = True
    with pytest.raises(ValueError, match="fields"):
        check(corpus)


@pytest.mark.parametrize("timestamp", ["2026-01-01T10:05:00", "not-a-date", 123])
def test_rejects_invalid_or_naive_timestamps(corpus, timestamp):
    corpus[1]["dev"][0]["logs"][0]["timestamp"] = timestamp
    with pytest.raises(ValueError, match="timestamp"):
        check(corpus)


def test_accepts_offset_aware_timestamp_in_utc_scope(corpus):
    corpus[1]["dev"][0]["logs"][0]["timestamp"] = "2026-01-01T15:35:00+05:30"
    assert check(corpus)["dev"] == 1


@pytest.mark.parametrize("mutation", ["outside-time", "outside-service", "reversed", "too-wide"])
def test_rejects_evidence_outside_valid_scope(corpus, mutation):
    row = corpus[1]["dev"][0]
    if mutation == "outside-time":
        row["logs"][0]["timestamp"] = "2026-01-01T11:00:00Z"
    elif mutation == "outside-service":
        row["logs"][0]["service"] = "unselected-service"
    elif mutation == "reversed":
        row["scope"]["end"] = "2026-01-01T09:00:00Z"
    else:
        row["scope"]["end"] = "2026-01-01T12:00:00Z"
    with pytest.raises(ValueError, match="scope"):
        check(corpus)


@pytest.mark.parametrize("mutation", ["case", "evidence", "variant", "renamed-copy"])
def test_rejects_duplicates_and_split_leakage(corpus, mutation):
    rows = corpus[1]
    if mutation == "case":
        rows["test"][0]["case_id"] = rows["dev"][0]["case_id"]
    elif mutation == "evidence":
        rows["dev"][0]["logs"].append(copy.deepcopy(rows["dev"][0]["logs"][0]))
    elif mutation == "variant":
        rows["labels"][1]["variant_id"] = rows["labels"][0]["variant_id"]
    else:
        rows["test"][0]["logs"][0]["message"] = "inventory request exceeded deadline after 9000ms"
    with pytest.raises(ValueError, match="duplicate"):
        check(corpus)


@pytest.mark.parametrize("mutation", ["missing", "extra", "duplicate", "wrong-version", "bad-ref"])
def test_rejects_broken_label_mapping(corpus, mutation):
    labels = corpus[1]["labels"]
    if mutation == "missing":
        labels.pop()
    elif mutation == "extra":
        extra = copy.deepcopy(labels[0])
        extra["case_id"] = "not-a-case"
        labels.append(extra)
    elif mutation == "duplicate":
        labels.append(copy.deepcopy(labels[0]))
    elif mutation == "wrong-version":
        labels[0]["dataset_version"] = "2.0.0"
    else:
        labels[0]["supporting_evidence_ids"] = ["test-01:1"]
    with pytest.raises(ValueError):
        check(corpus)


@pytest.mark.parametrize("outcome", [[], {}, None, "unknown"])
def test_invalid_outcome_is_a_validation_error(corpus, outcome):
    corpus[1]["labels"][0]["expected_outcome"] = outcome
    with pytest.raises(ValueError, match="outcome"):
        check(corpus)


def test_renaming_services_cannot_hide_a_copied_incident(corpus):
    row = corpus[1]["test"][0]
    row["scope"]["services"] = ["gateway", "stock"]
    row["logs"][0]["service"] = "gateway"
    row["logs"][0]["message"] = "stock request exceeded deadline after 9000ms"
    with pytest.raises(ValueError, match="duplicate incident evidence"):
        check(corpus)


def test_inconclusive_label_requires_missing_evidence_and_no_cause(corpus):
    entry = corpus[1]["labels"][0]
    entry["expected_outcome"] = "inconclusive"
    with pytest.raises(ValueError, match="inconclusive"):
        check(corpus)
    entry["expected_cause"] = None
    entry["required_missing_evidence"] = ["Upstream logs for the same interval."]
    assert check(corpus)["labels"] == 2


def test_runtime_loader_never_reads_labels(corpus):
    root, rows = corpus
    path = root / "dev.jsonl"
    save(path, rows["dev"])
    (root / "labels.jsonl").write_text("not valid JSON")
    assert load_cases(path) == rows["dev"]


def test_duplicate_json_keys_are_not_silently_overwritten(tmp_path):
    path = tmp_path / "dev.jsonl"
    path.write_text('{"case_id":"one","case_id":"two"}\n')
    with pytest.raises(ValueError, match="duplicate JSON key"):
        load_cases(path)


def test_checked_in_corpus_and_cli():
    result = validate_corpus(ROOT)
    assert (result["dev"], result["test"], result["labels"]) == (8, 16, 24)
    process = subprocess.run(
        [sys.executable, str(ROOT / "validate.py")], capture_output=True, text=True
    )
    assert process.returncode == 0, process.stderr
    assert "8 development, 16 held-out, 24 labels" in process.stdout


def test_cli_json_mode_is_machine_readable():
    process = subprocess.run(
        [sys.executable, str(ROOT / "validate.py"), "--json"],
        capture_output=True,
        text=True,
    )
    assert process.returncode == 0, process.stderr
    result = json.loads(process.stdout)
    assert (result["dev"], result["test"], result["labels"]) == (8, 16, 24)
    assert process.stderr == ""


def test_cli_reports_bad_file_and_exits_nonzero(tmp_path):
    process = subprocess.run(
        [sys.executable, str(ROOT / "validate.py"), "--root", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert process.returncode == 1
    assert "dev.jsonl" in process.stderr
    assert "Traceback" not in process.stderr
