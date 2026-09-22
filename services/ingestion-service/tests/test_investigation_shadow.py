"""Check policy comparisons independently of tool-reported errors and preserve capture gaps."""

import json

import pytest

SCOPE = {"services": ["checkout"], "start": "2026-01-01T10:00:00Z", "end": "2026-01-01T10:10:00Z"}


def event(arguments, error=None):
    return {
        "sequence": 1,
        "kind": "tool_call",
        "payload": {
            "tool": "query_logs",
            "arguments": arguments,
            "result": {"source": "database", "error": error, "items": []},
        },
    }


def test_baseline_catches_a_false_success_without_echoing_arguments():
    from app.investigation_shadow import review_events

    result = review_events(
        SCOPE, [event({**SCOPE, "services": ["inventory"], "text": "PRIVATE_CANARY"})]
    )
    row = result["events"][0]
    assert row["baseline"] == "scope_violation" and row["observed"] == "succeeded"
    assert row["agrees"] is False and result["disagreements"] == 1
    assert "PRIVATE_CANARY" not in json.dumps(result)
    assert result["capture_complete"] is None


@pytest.mark.parametrize(
    "arguments,error,baseline",
    [
        (SCOPE, None, "authorized"),
        ({**SCOPE, "services": ["inventory"]}, "scope_violation", "scope_violation"),
        ({**SCOPE, "start": "2026-01-01T09:59:00Z"}, "scope_violation", "scope_violation"),
        ({**SCOPE, "unexpected": "value"}, "invalid_arguments", "invalid_arguments"),
        (SCOPE, "source_unavailable", "authorized"),
    ],
)
def test_distinguishes_denials_validation_and_source_failure(arguments, error, baseline):
    from app.investigation_shadow import review_events

    result = review_events(SCOPE, [event(arguments, error)])
    assert result["events"][0]["baseline"] == baseline
    assert result["events"][0]["agrees"] is True
    assert result["scope_denials"] == (error == "scope_violation")


@pytest.mark.parametrize("completion_kind", ["none", "matching", "mismatched", "duplicate"])
def test_journal_pairs_only_valid_completions(completion_kind):
    from app.investigation_shadow import review_events

    request = {
        "sequence": 1,
        "kind": "tool_request",
        "payload": {"tool": "query_logs", "arguments": SCOPE},
    }
    completion = event(SCOPE)
    completion["sequence"] = 2
    completion["payload"]["request_sequence"] = 1
    if completion_kind == "mismatched":
        completion["payload"]["arguments"] = {**SCOPE, "services": ["inventory"]}
    events = [request] if completion_kind == "none" else [request, completion]
    if completion_kind == "duplicate":
        events.append({**completion, "sequence": 3})
    result = review_events(SCOPE, events)
    assert result["captured_requests"] == 1
    assert len(result["unresolved_requests"]) == (completion_kind in {"none", "mismatched"})
    assert result["invalid_events"] == (completion_kind in {"mismatched", "duplicate"})
    assert result["capture_complete"] is None


def test_redacted_arguments_are_not_scored_as_original_request():
    from app.investigation_shadow import review_events

    completion = event({**SCOPE, "text": "[REDACTED]" * 100})
    completion["payload"]["arguments_redacted"] = True
    result = review_events(SCOPE, [completion])
    assert result["events"][0]["baseline"] == "indeterminate_redacted"
    assert result["events"][0]["agrees"] is None
    assert result["disagreements"] == 0


def test_run_rejections_do_not_invent_missing_tool_details():
    from app.investigation_shadow import review_events

    result = review_events(
        SCOPE,
        [
            {
                "sequence": 1000000,
                "kind": "status",
                "payload": {"status": "failed", "error": "unknown_tool"},
            }
        ],
    )
    assert result["captured_calls"] == 0 and result["capture_complete"] is None
    assert result["events"][0]["observed"] == "unknown_tool"
    assert "tool" not in result["events"][0]


def test_malformed_event_fails_visibly_without_leaking_content():
    from app.investigation_shadow import review_events

    result = review_events(
        SCOPE, [{"sequence": 1, "kind": "tool_call", "payload": "PRIVATE_CANARY"}]
    )
    assert result["events"][0]["observed"] == "invalid_event"
    assert "PRIVATE_CANARY" not in json.dumps(result)


async def test_rehearsal_runs_real_worker_and_exposes_post_execution_recording_gap():
    from rehearse_shadow import rehearse

    result = await rehearse()
    cases = {case["case_id"]: case for case in result["cases"]}
    assert len(cases) == 10 and result["mode"] == "scripted_provider_real_tools"
    assert cases["service-denial"]["review"]["scope_denials"] == 1
    assert cases["time-denial"]["review"]["scope_denials"] == 1
    assert cases["metric-denial"]["review"]["scope_denials"] == 1
    assert cases["quoted-text"]["review"]["scope_denials"] == 0
    assert cases["unknown-tool"]["status"] == "failed"
    assert cases["unknown-tool"]["error"] == "unknown_tool"
    assert cases["malformed-call"]["error"] == "invalid_arguments"
    gap = cases["recording-outage"]
    assert gap["executed_calls_oracle"] == 1 and gap["review"]["captured_calls"] == 0
    assert gap["status"] == "failed" and gap["error"] == "worker_error"
    assert gap["review"]["unresolved_requests"] == [
        {"request_sequence": 1, "tool": "query_logs", "outcome": "unknown"}
    ]
    before = cases["request-recording-outage"]
    assert before["executed_calls_oracle"] == 0 and before["review"]["captured_requests"] == 0
    assert all(case["review"]["disagreements"] == 0 for case in result["cases"])
