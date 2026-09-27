"""Exercise the archived false inference through the new, selection-only contract."""

import json
from pathlib import Path

import pytest
from app.investigation_schemas import EvidenceBatch

ARCHIVE = Path(__file__).resolve().parents[3] / "evals/results/2026-09-26-report-guidance-live"


def archived(number=3):
    data = json.loads((ARCHIVE / f"smoke-{number:02}.json").read_text())
    return data, EvidenceBatch.model_validate(data["events"][1]["payload"]["result"])


def selection(ids=(), hypotheses=(), checks=()):
    from app.security_assessment import SecuritySelection

    return SecuritySelection(
        focus_evidence_ids=list(ids), hypothesis_codes=list(hypotheses), check_codes=list(checks)
    )


def assemble(batch, ids=(), hypotheses=(), checks=()):
    from app.security_assessment import assemble_security_assessment

    return assemble_security_assessment(selection(ids, hypotheses, checks), [batch])


def test_archived_false_login_prose_is_not_a_security_selection():
    from app.security_assessment import SecuritySelection

    data, _ = archived()
    assert (
        "successful login attempt (HTTP 200)" in data["run"]["report"]["observations"][2]["claim"]
    )
    with pytest.raises(ValueError):
        SecuritySelection.model_validate(data["run"]["report"])


def test_archived_gateway_success_cannot_become_authentication_success():
    _, batch = archived()
    gateway = batch.items[3]
    report = assemble(batch, [gateway.evidence_id])
    assert report["schema_version"] == 2 and report["outcome"] == "inconclusive"
    assert report["facts"] == [
        {
            "claim": 'Gateway recorded HTTP 200 for route "/api/auth/login" at 2026-09-26T12:00:20Z from address "192.0.2.44".',
            "evidence_ids": [gateway.evidence_id],
        }
    ]
    assert (
        "Authentication outcome is unknown; no authentication results were supplied."
        in report["unknowns"]
    )
    assert report["hypotheses"] == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("focus_evidence_ids", ["x"] * 4),
        ("focus_evidence_ids", [True]),
        ("focus_evidence_ids", [""]),
        ("focus_evidence_ids", ["x" * 129]),
        ("focus_evidence_ids", ["x", "x"]),
        ("hypothesis_codes", ["compromised"]),
        ("hypothesis_codes", ["retry_possible"] * 2),
        ("check_codes", ["execute_command"]),
        ("check_codes", ["read_auth_results"] * 2),
        ("claim", "Login succeeded"),
    ],
)
def test_selection_rejects_unbounded_or_untrusted_output(field, value):
    from app.security_assessment import SecuritySelection

    body = {"focus_evidence_ids": [], "hypothesis_codes": [], "check_codes": [], field: value}
    with pytest.raises(ValueError):
        SecuritySelection.model_validate(body)


@pytest.mark.parametrize(
    "code,case,allowed",
    [
        ("repeated_login_attempts", 1, True),
        ("repeated_login_attempts", 3, False),
        ("retry_possible", 2, True),
        ("retry_possible", 3, False),
        ("read_auth_results", 3, True),
        ("read_rejection_reasons", 2, True),
        ("read_rejection_reasons", 3, False),
        ("read_session_audit", 4, True),
    ],
)
def test_code_prerequisites(code, case, allowed):
    _, batch = archived(case)
    kwargs = {"checks" if code.startswith("read_") else "hypotheses": [code]}
    if not allowed:
        with pytest.raises(ValueError):
            assemble(batch, **kwargs)
    else:
        result = assemble(batch, **kwargs)
        assert len(result["checks" if code.startswith("read_") else "hypotheses"]) == 1
        for finding in result["hypotheses"]:
            assert set(finding["evidence_ids"]) <= {i.evidence_id for i in batch.items}
        if code == "retry_possible":
            refs = result["hypotheses"][0]["evidence_ids"]
            cited = [i for i in batch.items if i.evidence_id in refs]
            assert len(cited) == 2
            assert {i.content["auth_outcome"] for i in cited} == {"failure", "success"}
            assert "recorded order" in result["hypotheses"][0]["claim"]


@pytest.mark.parametrize(
    "change", ["redacted", "missing", "different-source", "ambiguous", "equal-time", "reversed"]
)
def test_retry_needs_known_same_source_account_and_recorded_order(change):
    _, batch = archived(2)
    auth = [i for i in batch.items if i.content.get("event_kind") == "authentication_result"]
    for item in auth:
        if change == "redacted":
            item.content["account_ref"] = "[REDACTED]"
        if change == "missing":
            item.content["account_ref"] = None
        if change == "ambiguous":
            item.content["correlation"] = "ambiguous"
        if change == "equal-time":
            item.content["event_time"] = "2026-09-26T12:00:00Z"
    if change == "different-source":
        auth[-1].content["evidence"][0] = "other-auth"
    if change == "reversed":
        auth[-1].content["event_time"] = "2026-09-26T12:00:00Z"
    with pytest.raises(ValueError):
        assemble(batch, hypotheses=["retry_possible"])


@pytest.mark.parametrize(
    "status,outcome", [(200, "failure"), (401, "success"), (200, "unavailable")]
)
def test_http_and_auth_are_rendered_independently(status, outcome):
    _, batch = archived(2)
    gateway = next(i for i in batch.items if i.content.get("event_kind") == "gateway_request")
    auth = next(i for i in batch.items if i.content.get("event_kind") == "authentication_result")
    gateway.content["http_status"] = status
    auth.content["auth_outcome"] = outcome
    facts = assemble(batch, [gateway.evidence_id, auth.evidence_id])["facts"]
    assert f"HTTP {status}" in facts[0]["claim"]
    assert f"Authentication service recorded {outcome}" in facts[1]["claim"]
    assert "customer-2042" in facts[1]["claim"] and "192.0.2.44" not in facts[1]["claim"]
    assert [f["evidence_ids"] for f in facts] == [[gateway.evidence_id], [auth.evidence_id]]


def test_absence_comes_from_summary_not_partial_pages_or_errors():
    _, batch = archived(2)
    batch.items = batch.items[:2]
    batch.truncated = True
    report = assemble(batch)
    assert not any("no authentication results were supplied" in s for s in report["unknowns"])
    failed = EvidenceBatch(source="security_case", error="source_unavailable", truncated=True)
    report = assemble(failed, checks=["read_auth_results"])
    assert any("unavailable" in s for s in report["unknowns"])
    assert not any("no authentication results were supplied" in s for s in report["unknowns"])


def test_summary_is_counts_not_account_identity():
    _, batch = archived(2)
    fact = assemble(batch, [batch.items[0].evidence_id])["facts"][0]
    assert "8 supplied records" in fact["claim"]
    assert "2 failure" in fact["claim"] and "1 success" in fact["claim"]
    assert "customer-2042" not in fact["claim"]


def test_repeated_pages_deduplicate_and_other_cases_or_conflicts_fail():
    from app.security_assessment import assemble_security_assessment

    _, batch = archived(2)
    chosen = selection(hypotheses=["retry_possible"])
    assert assemble_security_assessment(chosen, [batch, batch]) == assemble_security_assessment(
        chosen, [batch]
    )
    _, other = archived(3)
    changed = batch.model_copy(deep=True)
    changed.items[0].content["total"] = 999
    for extra in (other, changed):
        with pytest.raises(ValueError):
            assemble_security_assessment(chosen, [batch, extra])
    for ref in (batch.items[1].evidence_id, other.items[2].evidence_id, "unknown"):
        with pytest.raises(ValueError):
            assemble(batch, [ref])


def test_checks_reject_absent_prerequisites_and_unknown_fields_fail_closed():
    _, batch = archived(1)
    batch.items[0].content["unlinked_records"] = 0
    for code in ("read_auth_results", "read_session_audit"):
        with pytest.raises(ValueError):
            assemble(batch, checks=[code])
    event = next(i for i in batch.items if i.kind == "security_event")
    for key in ("event_time", "event_kind"):
        changed = batch.model_copy(deep=True)
        row = next(i for i in changed.items if i.evidence_id == event.evidence_id)
        del row.content[key]
        with pytest.raises(ValueError):
            assemble(changed, [event.evidence_id])


def test_report_limit_fails_without_truncating(monkeypatch):
    from app import security_assessment

    _, batch = archived(3)
    monkeypatch.setattr(security_assessment, "MAX_RESULT_BYTES", 10)
    with pytest.raises(ValueError):
        assemble(batch)
