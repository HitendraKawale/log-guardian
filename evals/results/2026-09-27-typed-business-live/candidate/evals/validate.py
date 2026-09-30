"""Validate authored evidence separately from grading labels, without model calls.

Runtime tools may use load_cases; only the offline evaluator loads labels.
The duplicate fingerprint catches cosmetic copies, not semantic paraphrases.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

CASE_FIELDS = {
    "schema_version",
    "dataset_version",
    "case_id",
    "provenance",
    "question",
    "scope",
    "logs",
}
LOG_FIELDS = {"evidence_id", "service", "level", "message", "timestamp"}
LABEL_FIELDS = {
    "dataset_version",
    "case_id",
    "variant_id",
    "family",
    "expected_outcome",
    "expected_cause",
    "acceptable_alternatives",
    "supporting_evidence_ids",
    "forbidden_claims",
    "required_missing_evidence",
    "tags",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def fields(value, expected: set[str], context: str) -> None:
    require(isinstance(value, dict), f"{context}: expected object")
    require(set(value) == expected, f"{context}: unexpected or missing fields")


def nonempty(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def strings(value, context: str) -> None:
    require(
        isinstance(value, list) and all(nonempty(v) for v in value), f"{context}: expected strings"
    )
    require(len(value) == len(set(value)), f"{context}: duplicate value")


def timestamp(value) -> datetime:
    require(isinstance(value, str), "timestamp: expected ISO string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"timestamp: invalid ISO value {value!r}") from exc
    require(parsed.tzinfo is not None, "timestamp: timezone offset required")
    return parsed


def unique_object(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def read_rows(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            try:
                row = json.loads(line, object_pairs_hook=unique_object)
                require(isinstance(row, dict), "expected JSON object")
                rows.append(row)
            except ValueError as exc:
                raise ValueError(f"{path}:{number}: {exc}") from exc
    require(bool(rows), f"{path}: empty dataset")
    return rows


def load_cases(path: Path) -> list[dict]:
    """Load evidence only; unknown fields cannot smuggle in evaluator labels."""
    cases = read_rows(path)
    for case in cases:
        fields(case, CASE_FIELDS, str(path))
        for name in ("dataset_version", "case_id", "question"):
            require(nonempty(case[name]), f"{path}: invalid {name}")
        require(
            type(case["schema_version"]) is int and case["schema_version"] == 1,
            "unsupported schema_version",
        )
        require(case["provenance"] == "authored", "this corpus requires authored provenance")
        scope = case["scope"]
        fields(scope, {"services", "start", "end"}, "scope")
        strings(scope["services"], "scope services")
        require(1 <= len(scope["services"]) <= 4, "scope requires one to four services")
        start, end = timestamp(scope["start"]), timestamp(scope["end"])
        require(
            timedelta(0) < end - start <= timedelta(hours=1), "scope must span at most one hour"
        )
        require(isinstance(case["logs"], list) and bool(case["logs"]), "case requires log evidence")
        ids = set()
        for log in case["logs"]:
            fields(log, LOG_FIELDS, case["case_id"])
            require(all(nonempty(log[n]) for n in LOG_FIELDS), "invalid log field or timestamp")
            require(
                log["level"] in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}, "invalid level"
            )
            require(log["service"] in scope["services"], "log service outside scope")
            require(start <= timestamp(log["timestamp"]) <= end, "log timestamp outside scope")
            require(log["evidence_id"] not in ids, "duplicate evidence ID")
            ids.add(log["evidence_id"])
    return cases


def fingerprint(case: dict) -> tuple:
    # ponytail: cosmetic-copy check only; human review must catch paraphrased incidents.
    services = sorted(case["scope"]["services"], key=len, reverse=True)
    pattern = re.compile("|".join(re.escape(service) for service in services), re.IGNORECASE)
    messages = []
    for log in case["logs"]:
        message = pattern.sub("<service>", log["message"].lower())
        message = re.sub(r"\d+", "#", message)
        messages.append((log["level"], " ".join(message.split())))
    return tuple(sorted(messages))


def validate_corpus(root: Path) -> dict:
    """Cross-check splits and evaluator-only labels, returning content provenance."""
    splits = {name: load_cases(root / f"cases/{name}.jsonl") for name in ("dev", "test")}
    cases, evidence_ids, fingerprints = {}, set(), set()
    for split in splits.values():
        for case in split:
            require(case["case_id"] not in cases, "duplicate case ID across corpus")
            cases[case["case_id"]] = case
            ids = {log["evidence_id"] for log in case["logs"]}
            require(not ids & evidence_ids, "duplicate evidence ID across corpus")
            evidence_ids.update(ids)
            signature = fingerprint(case)
            require(
                signature not in fingerprints, "duplicate incident evidence after normalization"
            )
            fingerprints.add(signature)
    versions = {case["dataset_version"] for case in cases.values()}
    require(len(versions) == 1, "mixed dataset versions")
    version = next(iter(versions))
    labels = read_rows(root / "labels.jsonl")
    labeled, variants = set(), set()
    for label in labels:
        fields(label, LABEL_FIELDS, "label")
        for name in ("case_id", "variant_id", "family"):
            require(nonempty(label[name]), f"label: invalid {name}")
        case_id = label["case_id"]
        require(case_id in cases, f"label references unknown case {case_id}")
        require(case_id not in labeled, f"duplicate label for {case_id}")
        require(label["variant_id"] not in variants, "duplicate incident variant")
        labeled.add(case_id)
        variants.add(label["variant_id"])
        require(label["dataset_version"] == version, "label version differs from evidence")
        for name in (
            "acceptable_alternatives",
            "supporting_evidence_ids",
            "forbidden_claims",
            "required_missing_evidence",
            "tags",
        ):
            strings(label[name], f"label {name}")
        ids = {log["evidence_id"] for log in cases[case_id]["logs"]}
        refs = set(label["supporting_evidence_ids"])
        require(bool(refs) and refs <= ids, f"invalid evidence references for {case_id}")
        outcome = label["expected_outcome"]
        require(
            nonempty(outcome) and outcome in {"supported", "inconclusive"},
            "invalid expected outcome",
        )
        if outcome == "supported":
            require(nonempty(label["expected_cause"]), "supported label requires a cause")
        else:
            require(
                label["expected_cause"] is None and bool(label["required_missing_evidence"]),
                "inconclusive label needs missing evidence and no asserted cause",
            )
    require(labeled == set(cases), "missing evaluator labels")
    paths = ("cases/dev.jsonl", "cases/test.jsonl", "labels.jsonl")
    return {
        "dataset_version": version,
        "dev": len(splits["dev"]),
        "test": len(splits["test"]),
        "labels": len(labels),
        "sha256": {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in paths},
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog="Examples: python evals/validate.py; python evals/validate.py --root evals --json",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="corpus directory containing cases/ and labels.jsonl",
    )
    parser.add_argument("--json", action="store_true", help="emit only the JSON validation result")
    args = parser.parse_args()
    try:
        result = validate_corpus(args.root)
    except (OSError, ValueError) as exc:
        print(f"Corpus invalid: {exc}", file=sys.stderr)
        return 1
    if not args.json:
        print(
            f"Corpus {result['dataset_version']}: {result['dev']} development, "
            f"{result['test']} held-out, {result['labels']} labels"
        )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
