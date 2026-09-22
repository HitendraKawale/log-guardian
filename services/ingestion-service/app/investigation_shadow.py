"""Review existing events without changing execution or mistaking denials for attacks."""

from pydantic import ValidationError

from .investigation_loop import TOOL_SCHEMAS
from .investigation_schemas import EvidenceBatch, InvestigationScope, MetricQuery


def baseline(scope, name, arguments):
    if not isinstance(name, str) or name not in TOOL_SCHEMAS:
        return "unknown_tool"
    try:
        query = TOOL_SCHEMAS[name].model_validate(arguments)
    except ValidationError:
        return "invalid_arguments"
    if isinstance(query, InvestigationScope):
        services = set(query.services)
    elif isinstance(query, MetricQuery):
        services = {query.service}
    else:
        return "authorized"
    if not services <= set(scope.services) or query.start < scope.start or query.end > scope.end:
        return "scope_violation"
    return "authorized"


def review_events(scope, events):
    """Caller supplies one run's ordered events and owner scope; never emit raw payloads."""
    scope = InvestigationScope.model_validate(scope)
    if len(events) > 10000:
        raise ValueError("event review exceeds 10000 rows")
    rows, last = [], 0
    requests, pending = {}, {}
    legacy_completions = 0
    for event in events:
        sequence = event.get("sequence") if isinstance(event, dict) else None
        row = {"sequence": sequence if type(sequence) is int else None, "observed": "invalid_event"}
        rows.append(row)
        if type(sequence) is not int or sequence <= last:
            continue
        last = sequence
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        if event.get("kind") == "status":
            error = payload.get("error")
            if error in ("unknown_tool", "invalid_arguments", "worker_error", "deadline_exceeded"):
                row["observed"] = error
            elif error is not None:
                row["observed"] = "other_run_failure"
            elif payload.get("status") in ("completed", "failed", "cancelled"):
                row["observed"] = payload["status"]
            continue
        if event.get("kind") == "tool_request":
            name, arguments = payload.get("tool"), payload.get("arguments")
            if (
                not isinstance(name, str)
                or name not in TOOL_SCHEMAS
                or not isinstance(arguments, dict)
            ):
                continue
            changed = payload.get("arguments_redacted", False)
            requests[sequence] = pending[sequence] = (name, arguments, changed)
            row.update(
                tool=name,
                observed="requested",
                baseline=(
                    "indeterminate_redacted" if changed else baseline(scope, name, arguments)
                ),
            )
            continue
        if event.get("kind") != "tool_call":
            continue
        try:
            batch = EvidenceBatch.model_validate(payload.get("result"))
        except ValidationError:
            continue
        name = payload.get("tool")
        if "request_sequence" in payload:
            request_sequence = payload["request_sequence"]
            if (
                type(request_sequence) is not int
                or request_sequence not in pending
                or pending[request_sequence]
                != (name, payload.get("arguments"), payload.get("arguments_redacted", False))
            ):
                continue
            del pending[request_sequence]
            row["request_sequence"] = request_sequence
        else:
            legacy_completions += 1
        expected = (
            "indeterminate_redacted"
            if payload.get("arguments_redacted")
            else baseline(scope, name, payload.get("arguments"))
        )
        observed = batch.error or "succeeded"
        row.update(
            tool=name if isinstance(name, str) and name in TOOL_SCHEMAS else None,
            baseline=expected,
            observed=observed,
            agrees=None
            if expected == "indeterminate_redacted"
            else (
                observed in ("succeeded", "source_unavailable")
                if expected == "authorized"
                else observed == expected
            ),
        )
    calls = [row for row in rows if "agrees" in row]
    return {
        "captured_requests": len(requests),
        "unresolved_requests": [
            {"request_sequence": sequence, "tool": data[0], "outcome": "unknown"}
            for sequence, data in pending.items()
        ],
        "legacy_completions": legacy_completions,
        "captured_calls": len(calls),
        "scope_denials": sum(row["observed"] == "scope_violation" for row in calls),
        "baseline_scope_violations": sum(row["baseline"] == "scope_violation" for row in calls),
        "disagreements": sum(row["agrees"] is False for row in calls),
        "invalid_events": sum(row["observed"] == "invalid_event" for row in rows),
        "capture_complete": None,
        "events": rows,
        "limits": "Events alone cannot establish attempted-call coverage or malicious intent. "
        "This is a basic scope-policy comparison, not measured detection accuracy.",
    }
