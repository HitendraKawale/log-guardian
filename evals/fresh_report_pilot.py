"""Configure one approved fresh-case batch while preserving the consumed runner defaults."""

import hashlib
import json
from contextlib import contextmanager

import investigator_pilot as p

CANDIDATE_SHA = "20e8e292e67b2cd7cc9968668fb63968446c56b17a52f6df06a89168fb905168"
CORPUS_SHA = "af896fc98e7929be8507de15a14a1387c1ead48bd4b0b3ddb19c71cd14da2ab5"
PRODUCTION_BASE = "1edd36aaf214935268f64da64b61a8ac249cf7b1"
CANDIDATE_FILE = "evals/semantic-review/2026-09-22-report-grounding/candidate.json"
CORPUS_FILE = "evals/freezes/fresh-report-grounding-af896fc98e79.json"
CASE_FILE = "evals/semantic-review/fresh-case-authoring/cases.jsonl"
CASE_SHA = "74fcfffbd4e862ef56c45784da7813b1f22a03fff7610939b589d18d93f058ca"


def frozen(path, key, expected):
    value = json.loads((p.ROOT / path).read_bytes())
    recorded = value.pop(key)
    actual = hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if recorded != expected or actual != expected:
        raise ValueError("frozen manifest changed")
    return value


@contextmanager
def configured():
    """CLI owns one batch; restore module settings for in-process offline tests."""
    original_candidate = p.candidate

    def candidate():
        production = frozen(CANDIDATE_FILE, "candidate_sha256", CANDIDATE_SHA)
        frozen(CORPUS_FILE, "corpus_freeze_sha256", CORPUS_SHA)
        for name, expected in production["files"].items():
            if (
                name.startswith("services/")
                and hashlib.sha256((p.ROOT / name).read_bytes()).hexdigest() != expected
            ):
                raise ValueError("frozen production source changed")
        manifest, _ = original_candidate()
        if manifest["dependencies"] != production["dependencies"]:
            raise ValueError("frozen dependency versions changed")
        if any("inventory" in c["scope"]["services"] for c in p.load_cases(p.ROOT / CASE_FILE)):
            raise ValueError("canary must remain outside every scope")
        manifest.update(
            frozen_production_candidate=CANDIDATE_SHA,
            frozen_corpus=CORPUS_SHA,
            review_status="separate_model_authored_declared_context_exposure",
        )
        manifest["pricing"]["checked_at"] = "2026-09-23"
        return manifest, p.digest(manifest)

    settings = {
        "AUTHORIZATION": "fresh-report-grounding-2026-09-23",
        "BASE": PRODUCTION_BASE,
        "CASE_FILE": CASE_FILE,
        "CASE_SHA": CASE_SHA,
        "CASE_IDS": [f"fresh-{n:02}" for n in range(1, 13)],
        "MAX_REQUESTS": 72,
        "FILES": (
            "evals/investigator_pilot.py",
            "evals/fresh_report_pilot.py",
            "evals/tests/test_investigator_pilot.py",
            "evals/tests/test_fresh_report_pilot.py",
            "evals/run.py",
            "evals/validate.py",
            CASE_FILE,
            CANDIDATE_FILE,
            CORPUS_FILE,
            "docs/plans/fresh-report-grounding-authorization.md",
            "docs/plans/fresh-report-grounding-pricing.md",
            "services/ingestion-service/requirements.txt",
            "services/ingestion-service/runbooks/operations.md",
        )
        + tuple(
            str(path.relative_to(p.ROOT))
            for path in sorted((p.ROOT / "services/ingestion-service/app").rglob("*.py"))
        ),
        "candidate": candidate,
    }
    old = {key: getattr(p, key) for key in settings}
    try:
        for key, value in settings.items():
            setattr(p, key, value)
        yield p
    finally:
        for key, value in old.items():
            setattr(p, key, value)


if __name__ == "__main__":
    with configured() as pilot:
        raise SystemExit(pilot.main())
