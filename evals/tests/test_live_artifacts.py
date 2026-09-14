"""Check archived live results offline, including the failed abstentions."""

import hashlib
import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/ingestion-service"))

from app.investigation_agent import validate_citations  # noqa: E402
from app.investigation_schemas import EvidenceBatch, InvestigationReport  # noqa: E402


@pytest.mark.parametrize(
    "name,revision,expected_cost,expected_labels,expected_reviewed",
    [
        (
            "2026-09-13-baseline-smoke",
            "e4edf8bdc33e5df6f666518ee146f74a46058e12",
            "0.00366960",
            0,
            0,
        ),
        (
            "2026-09-13-baseline-smoke-v2",
            "0a97c3f00acdfefe48329f1d0d89a60b3533b59f",
            "0.00401200",
            0,
            0,
        ),
        (
            "2026-09-13-baseline-smoke-v3",
            "8edf09ed34d896ea54e76fcc9ccc6632c8c1b9f7",
            "0.00409200",
            2,
            1,
        ),
    ],
)
def test_live_batches_preserve_provenance_failures_and_accounting(
    name, revision, expected_cost, expected_labels, expected_reviewed
):
    folder = ROOT / "evals/results" / name
    summary = json.loads((folder / "summary.json").read_text())
    assert summary["requests"] == len(summary["runs"]) == 4
    assert summary["authorization_exhausted"] is True
    total = Decimal(0)
    abstentions = 0
    reviewed = 0
    for entry in summary["runs"]:
        raw = (folder / entry["artifact"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == entry["sha256"]
        run = json.loads(raw)
        assert run["mode"] == "live" and run["status"] == "completed"
        assert run["model_requests"] == 1
        assert run["model_requested"] == run["model_returned"] == summary["model"]
        assert run["provenance"]["code_dirty"] is False
        assert run["provenance"]["code_revision"] == revision
        assert run["provenance"]["origin"] == "authored"
        batches = [EvidenceBatch.model_validate(event["result"]) for event in run["trace"]]
        report = InvestigationReport.model_validate(run["report"])
        validate_citations(report, batches)
        assert all(len(batch.model_dump_json().encode()) <= 16384 for batch in batches)
        assert sum(len(batch.model_dump_json().encode()) for batch in batches) <= 65536
        assert run["elapsed_ms"] <= 120000
        usage, prices = run["usage"], run["pricing"]
        assert usage == entry["usage"] and usage["output_tokens"] <= 1024
        assert usage["input_tokens"] <= run["input_token_reservation"]
        cached = usage["cached_input_tokens"]
        cost = (
            (usage["input_tokens"] - cached) * Decimal(prices["input_per_million_usd"])
            + cached * Decimal(prices["cached_input_per_million_usd"])
            + usage["output_tokens"] * Decimal(prices["output_per_million_usd"])
        ) / 1_000_000
        assert cost == Decimal(run["estimated_cost_usd"]) == Decimal(entry["estimated_cost_usd"])
        assert cost <= Decimal("0.025")
        total += cost
        assert report.outcome == entry["reported_outcome"]
        if entry["case_id"] == "dev-06":
            assert entry["expected_outcome"] == "inconclusive"
            abstentions += report.outcome == "inconclusive"
            if expected_reviewed:
                # Preserve the offline review, not an automated claim of semantic correctness.
                assert entry["abstention_review_pass"] is (entry["system"] == "A")
                reviewed += entry["abstention_review_pass"]
        if expected_reviewed:
            previous = json.loads(
                (
                    ROOT / "evals/results/2026-09-13-baseline-smoke-v2" / entry["artifact"]
                ).read_text()
            )
            for current_event, previous_event in zip(run["trace"], previous["trace"], strict=True):
                assert {k: v for k, v in current_event.items() if k != "elapsed_ms"} == {
                    k: v for k, v in previous_event.items() if k != "elapsed_ms"
                }
            assert usage["input_tokens"] == previous["usage"]["input_tokens"]
    assert total == Decimal(summary["estimated_total_cost_usd"]) == Decimal(expected_cost)
    assert total <= Decimal(summary["allowance_usd"])
    assert abstentions == summary.get("reported_abstentions", 0) == expected_labels
    assert reviewed == summary["correct_abstentions"] == expected_reviewed


def test_abc_development_batch_preserves_failures_and_accounting():
    folder = ROOT / "evals/results/2026-09-14-dev-abc"
    summary = json.loads((folder / "summary.json").read_text())
    assert len(summary["runs"]) == 24 and summary["requests"] == 46
    assert summary["authorization_exhausted"] is True
    total = Decimal(0)
    for entry in summary["runs"]:
        raw = (folder / entry["artifact"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == entry["sha256"]
        run = json.loads(raw)
        assert run["provenance"]["code_revision"] == "ad7f95f0ba86b2a9e0182680dccfb9c1161e51ef"
        assert run["provenance"]["code_dirty"] is False
        assert run["status"] == entry["execution_status"]
        if run["status"] == "completed":
            batches = [EvidenceBatch.model_validate(e["result"]) for e in run["trace"]]
            validate_citations(InvestigationReport.model_validate(run["report"]), batches)
        else:
            assert entry["core_review_pass"] is False and run["report"] is None
        assert run["usage"] is not None
        cost = Decimal(run["estimated_cost_usd"])
        assert cost <= Decimal("0.025")
        total += cost
    assert total == Decimal(summary["estimated_total_cost_usd"]) == Decimal("0.03470640")
    # Preserve the offline review verdicts, including C's failures.
    assert summary["by_system"]["A"]["core_pass"] == 7
    assert summary["by_system"]["B"]["core_pass"] == 7
    assert summary["by_system"]["C"]["core_pass"] == 4
