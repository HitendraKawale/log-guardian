"""Check draft fixtures and runtime separation, without grading model behavior."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import run as runner
from validate import load_cases, read_rows

PACKET = Path(__file__).resolve().parents[1] / "investigator-security"


def test_pairs_change_only_one_untrusted_log():
    cases = load_cases(PACKET / "cases.jsonl")
    by_id = {case["case_id"]: case for case in cases}
    notes = read_rows(PACKET / "reviewer-notes.jsonl")
    assert len(cases) == len(by_id) == 10 and len(notes) == 5
    covered = []
    for note in notes:
        assert note["review_status"] == "draft" and note["reviewer"] is None
        assert note["author"] == "assistant"
        assert note["objective"] and note["acceptable_conclusions"] and note["grading_checks"]
        control, attack = by_id[note["control"]], by_id[note["attack"]]
        covered.extend((note["control"], note["attack"]))
        assert control["scope"] == attack["scope"] and control["question"] == attack["question"]
        assert len(attack["logs"]) == len(control["logs"]) + 1
        assert note["attack_evidence_id"] == attack["logs"][-1]["evidence_id"]

        def without_id(row):
            return {key: value for key, value in row.items() if key != "evidence_id"}

        assert [without_id(row) for row in control["logs"]] == [
            without_id(row) for row in attack["logs"][:-1]
        ]
    assert sorted(covered) == sorted(by_id)


@pytest.mark.parametrize("index", range(10))
def test_packet_delivery_and_owner_scope(index):
    asyncio.run(check_delivery(index))


async def check_delivery(index):
    case = load_cases(PACKET / "cases.jsonl")[index]
    scope = runner.InvestigationScope(**case["scope"])
    tools = runner.EvidenceTools(scope, records=case["logs"])
    arguments = scope.model_dump(mode="json")
    full = await tools.query_logs(**arguments)
    assert full.error is None and not full.truncated
    assert {item.evidence_id: item.content["message"] for item in full.items} == {
        row["evidence_id"]: row["message"] for row in case["logs"]
    }
    narrowed = await tools.query_logs(
        **{**arguments, "start": "2026-01-01T10:05:00Z", "end": "2026-01-01T10:06:00Z"}
    )
    assert narrowed.error is None and 0 < len(narrowed.items) < len(full.items)
    service = await tools.query_logs(**{**arguments, "services": ["inventory"]})
    window = await tools.query_logs(**{**arguments, "start": "2026-01-01T09:55:00Z"})
    assert service.error == window.error == "scope_violation"
    assert service.items == window.items == []
    metric = await tools.read_metric_series(
        service="checkout", metric_name="error_rate", start=arguments["start"], end=arguments["end"]
    )
    assert metric.error == "source_unavailable"


@pytest.mark.parametrize("index", range(10))
def test_dry_run_does_not_read_reviewer_notes_or_call_model(index, monkeypatch):
    original_open = Path.open

    def guarded_open(path, *args, **kwargs):
        assert (
            path.resolve() != (PACKET / "reviewer-notes.jsonl").resolve()
        ), "runtime read reviewer notes"
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)
    case = load_cases(PACKET / "cases.jsonl")[index]
    result = asyncio.run(
        runner.execute(
            SimpleNamespace(system="C", dry_run=True),
            case,
            runner.BaselineConfig(model="gpt-4.1-mini-2025-04-14", max_cost_usd="0.025"),
            None,
        )
    )
    assert result["status"] == "dry_run" and result["model_requests"] == 0
    assert result["report"] is None and result["trace"] == []
    assert "review_status" not in json.dumps(result)
