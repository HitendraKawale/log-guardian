"""Pin reviewed failures without pretending citation membership proves semantic support."""

import hashlib
import json
from pathlib import Path

import investigator_pilot  # noqa: F401
import pytest
from app.investigation_agent import validate_citations
from app.investigation_schemas import EvidenceBatch, InvestigationReport

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "semantic-review/2026-09-22-initial-evidence"
ARCHIVE = ROOT / "results/2026-09-22-initial-evidence-live"


def test_review_sources_are_pinned():
    assert (REVIEW / "SHA256SUMS").exists(), "review packet has not been preserved"
    for line in (REVIEW / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split("  ", 1)
        assert hashlib.sha256((REVIEW / name).read_bytes()).hexdigest() == digest


@pytest.mark.parametrize(
    "case_id", ["stage-02", "stage-05", "stage-06", "stage-07", "stage-08", "stage-09"]
)
def test_reviewed_report_reproduces_membership_boundary(case_id):
    assert (REVIEW / "regressions.json").exists(), "review cases have not been pinned"
    cases = json.loads((REVIEW / "regressions.json").read_bytes())
    assert len(cases) == 6
    case = next(row for row in cases if row["case_id"] == case_id)
    witness = json.loads((ARCHIVE / case["response_file"]).read_bytes())
    assert witness["case_id"] == case_id
    report = InvestigationReport.model_validate_json(
        witness["response"]["choices"][0]["message"]["content"]
    )
    assert case["disputed_quote"] in json.dumps(report.model_dump())
    assert case["expected_behavior"] and case["status"] == "open_manual_semantic_regression"
    saved = json.loads((ARCHIVE / f"{case_id}.json").read_bytes())
    batches = [
        EvidenceBatch.model_validate(event["payload"]["result"])
        for event in saved["events"]
        if event["kind"] == "tool_call"
    ]
    if case_id == "stage-05":
        assert saved["report"] is None and saved["error"] == "invalid_report"
        with pytest.raises(ValueError, match="Unknown citation"):
            validate_citations(report, batches)
    else:
        assert saved["report"] == report.model_dump(mode="json")
        validate_citations(report, batches)
        # Known semantic problems pass this validator; this check is not a semantic grader.
