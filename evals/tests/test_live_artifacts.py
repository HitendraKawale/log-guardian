"""Check archived live results offline, including the failed abstentions."""

import hashlib
import json
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/ingestion-service"))

from app.investigation_agent import validate_citations  # noqa: E402
from app.investigation_schemas import EvidenceBatch, InvestigationReport  # noqa: E402


def test_first_live_batch_preserves_provenance_failures_and_accounting():
    folder = ROOT / "evals/results/2026-09-13-baseline-smoke"
    summary = json.loads((folder / "summary.json").read_text())
    assert summary["requests"] == len(summary["runs"]) == 4
    assert summary["authorization_exhausted"] is True
    total = Decimal(0)
    abstentions = 0
    for entry in summary["runs"]:
        raw = (folder / entry["artifact"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == entry["sha256"]
        run = json.loads(raw)
        assert run["mode"] == "live" and run["status"] == "completed"
        assert run["model_requests"] == 1
        assert run["model_requested"] == run["model_returned"] == summary["model"]
        assert run["provenance"]["code_dirty"] is False
        assert run["provenance"]["code_revision"] == "e4edf8bdc33e5df6f666518ee146f74a46058e12"
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
    assert total == Decimal(summary["estimated_total_cost_usd"]) == Decimal("0.00366960")
    assert total <= Decimal(summary["allowance_usd"])
    assert abstentions == summary["correct_abstentions"] == 0
