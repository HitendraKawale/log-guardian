"""A factual review must remain useful without a model selection or provider."""

import hashlib
import json
from pathlib import Path

import pytest
from app.security_adapters import analyze_import

from tests.security_case_helpers import AUTH, NGINX, OWNER, payload


def saved_case(body=None, owner=OWNER):
    body = payload() if body is None else body
    return {
        "case_id": "baseline-test",
        "report": analyze_import(owner, body),
        "source_snapshot": owner,
        "input_hashes": {
            name: hashlib.sha256(raw.encode()).hexdigest() for name, raw in body["logs"].items()
        },
    }


def test_same_snapshot_same_baseline_and_no_input_mutation():
    from app.security_assessment import build_security_baseline

    saved = saved_case()
    before = json.dumps(saved, sort_keys=True)
    first = build_security_baseline(saved)
    assert first == build_security_baseline(saved)
    assert before == json.dumps(saved, sort_keys=True)
    assert first["method"] == "deterministic"
    assert first["coverage"] == {
        "saved_records": 2,
        "reviewed_records": 2,
        "displayed_event_facts": 2,
        "omitted_event_facts": 0,
        "fact_limit": 12,
        "display_limited": False,
    }
    claims = [fact["claim"] for fact in first["report"]["facts"]]
    assert len(claims) == 3
    assert any("Gateway recorded HTTP 200" in claim for claim in claims)
    assert any("Authentication service recorded failure" in claim for claim in claims)
    assert not any("Authentication service recorded success" in claim for claim in claims)
    evidence = {item["evidence_id"] for item in first["evidence"]}
    assert all(set(f["evidence_ids"]) <= evidence for f in first["report"]["facts"])


@pytest.mark.parametrize("number,count,hypotheses", [(1, 19, 1), (2, 8, 2), (3, 6, 0), (4, 8, 1)])
def test_frozen_business_cases_need_no_model_selection(number, count, hypotheses):
    from app.security_assessment import build_security_baseline

    root = Path(__file__).resolve().parents[3]
    owner = json.loads((root / "examples/security-review/sources.json").read_text())
    cases = json.loads((root / "evals/typed-business-live/inputs.json").read_text())
    result = build_security_baseline(saved_case(cases[number - 1]["body"], owner))
    report = result["report"]
    assert result["coverage"]["reviewed_records"] == count
    assert result["coverage"]["omitted_event_facts"] == max(0, count - 11)
    assert len(report["hypotheses"]) == hypotheses
    evidence = {item["evidence_id"]: item for item in result["evidence"]}
    cited = {ref for f in report["facts"] + report["hypotheses"] for ref in f["evidence_ids"]}
    assert cited == evidence.keys()
    assert all(ref.startswith(("security-event:", "security-summary:")) for ref in cited)
    assert report["outcome"] == "inconclusive"
    if number == 3:
        assert any("Authentication outcome is unknown" in s for s in report["unknowns"])
        assert any("HTTP 200" in f["claim"] for f in report["facts"])
        assert not any(
            "Authentication service recorded success" in f["claim"] for f in report["facts"]
        )
        assert len(report["checks"]) == 2  # Auth-results and session-policy context, not a verdict.
    else:
        assert not any("Obtain authentication-result" in check for check in report["checks"])
    if number == 4:
        assert "recorded order" in report["hypotheses"][0]["claim"]
        assert not any(
            "More than one authentication failure" in f["claim"] for f in report["hypotheses"]
        )


def gateway_case(count):
    body = payload()
    body["logs"] = {
        "edge": "\n".join(json.dumps({**NGINX, "request_id": f"r-{i:04}"}) for i in range(count)),
        "auth": "",
    }
    return saved_case(body)


@pytest.mark.parametrize("count", [0, 49, 1000])
def test_scan_exhausts_pages_but_discloses_display_limit(count):
    from app.security_assessment import build_security_baseline

    saved = gateway_case(count)
    result = build_security_baseline(saved)
    assert result["coverage"]["saved_records"] == count
    assert result["coverage"]["reviewed_records"] == count
    assert result["coverage"]["displayed_event_facts"] == min(count, 11)
    assert result["coverage"]["omitted_event_facts"] == max(0, count - 11)
    assert result["coverage"]["display_limited"] == (count > 11)
    assert len(result["report"]["facts"]) == min(count, 11) + 1
    assert not any("page was truncated" in text for text in result["report"]["unknowns"])
    assert any(
        "Collection completeness is unknown" in text for text in result["report"]["unknowns"]
    )
    records = [
        i["content"]["evidence"][1] for i in result["evidence"] if i["kind"] == "security_event"
    ]
    assert records == [f"r-{i:04}" for i in range(min(count, 11))]


def test_representatives_precede_fill_and_source_time_breaks_ties():
    from app.security_assessment import build_security_baseline

    body = payload()
    body["logs"] = {
        "edge": "\n".join(
            json.dumps({**NGINX, "request_id": name, "status": str(status)})
            for name, status in [("z", 200), ("b", 503), ("a", 503), ("c", 401), ("d", 201)]
        ),
        "auth": "\n".join(
            json.dumps({**AUTH, "event_id": name, "request_id": None, "outcome": outcome})
            for name, outcome in [
                ("auth-s", "success"),
                ("auth-f", "failure"),
                ("auth-u", "unavailable"),
            ]
        ),
    }
    result = build_security_baseline(saved_case(body))
    rows = {i["evidence_id"]: i["content"] for i in result["evidence"]}
    order = [rows[f["evidence_ids"][0]]["evidence"][1] for f in result["report"]["facts"][1:]]
    assert order == ["auth-f", "auth-s", "auth-u", "a", "c", "z", "d", "b"]
    assert not any("recorded order" in h["claim"] for h in result["report"]["hypotheses"])


@pytest.mark.parametrize("change", ["redacted", "same-time", "reversed", "ambiguous"])
def test_baseline_does_not_invent_retry_from_uncertain_records(change):
    from app.security_assessment import build_security_baseline

    first = {**AUTH, "request_id": "r1"}
    second = {
        **AUTH,
        "event_id": "auth-2",
        "request_id": "r2",
        "outcome": "success",
        "timestamp": "2026-09-01T10:00:03Z",
    }
    if change == "redacted":
        first["account_ref"] = second["account_ref"] = "redacted-account"
    if change == "same-time":
        second["timestamp"] = first["timestamp"]
    if change == "reversed":
        second["timestamp"] = "2026-09-01T10:00:00Z"
    if change == "ambiguous":
        second["request_id"] = first["request_id"]
    body = payload()
    body["logs"]["auth"] = "\n".join(map(json.dumps, [first, second]))
    result = build_security_baseline(saved_case(body))
    assert result["report"]["hypotheses"] == []
    if change == "redacted":
        assert any(
            "account reference unavailable or redacted" in f["claim"]
            for f in result["report"]["facts"]
        )


@pytest.mark.parametrize(
    "fault",
    [
        "error",
        "version",
        "offset",
        "count",
        "next",
        "records",
        "summary",
        "duplicate",
        "unknown-id",
    ],
)
def test_page_errors_cannot_be_reported_as_complete(monkeypatch, fault):
    from app import security_assessment as module

    original = module.security_page

    def broken(saved, query):
        batch = original(saved, query)
        if fault == "error":
            batch.error = "source_unavailable"
        if fault == "version":
            batch.version = "another-case"
        if fault == "offset":
            batch.items[1].content["offset"] = True
        if fault == "count":
            batch.items[1].content["returned_records"] = 0
        if fault == "next":
            batch.items[1].content["next_offset"] = query.offset
        if fault == "records":
            batch.items.pop()
        if fault == "summary" and query.offset:
            batch.items[0].content["sources"]["edge"]["records"] = 40
        if fault == "duplicate":
            batch.items[-1] = batch.items[-2]
        if fault == "unknown-id":
            batch.items[-1].evidence_id = "security-event:unknown"
        return batch

    monkeypatch.setattr(module, "security_page", broken)
    with pytest.raises(ValueError):
        module.build_security_baseline(gateway_case(80))


@pytest.mark.parametrize("fault", ["too-many", "duplicate", "missing-field", "bad-auth-count"])
def test_bad_snapshot_fails_instead_of_becoming_an_assessment(fault):
    from app.security_assessment import build_security_baseline

    saved = saved_case()
    if fault == "too-many":
        saved["report"]["timeline"] *= 501
    if fault == "duplicate":
        saved["report"]["timeline"].append(saved["report"]["timeline"][0])
    if fault == "missing-field":
        del saved["report"]["timeline"][0]["event_time"]
    if fault == "bad-auth-count":
        saved["report"]["sources"]["auth"]["auth_outcomes"]["failure"] = 2
    with pytest.raises(ValueError):
        build_security_baseline(saved)


@pytest.mark.parametrize("limit,value", [("MAX_RESULT_BYTES", 1400), ("MAX_BASELINE_BYTES", 5000)])
def test_byte_limits_reduce_fact_prefix_without_losing_citations(monkeypatch, limit, value):
    from app import security_assessment as module

    saved = gateway_case(30)
    full = module.build_security_baseline(saved)
    monkeypatch.setattr(module, limit, value)
    result = module.build_security_baseline(saved)
    assert 1 <= len(result["report"]["facts"]) < len(full["report"]["facts"])
    assert result["report"]["facts"] == full["report"]["facts"][: len(result["report"]["facts"])]
    assert result["coverage"]["display_limited"]
    assert result["coverage"]["omitted_event_facts"] == 31 - len(result["report"]["facts"])
    target = result["report"] if limit == "MAX_RESULT_BYTES" else result
    assert len(json.dumps(target, ensure_ascii=False, separators=(",", ":")).encode()) <= value
    evidence = {i["evidence_id"] for i in result["evidence"]}
    assert evidence == {
        ref
        for f in result["report"]["facts"] + result["report"]["hypotheses"]
        for ref in f["evidence_ids"]
    }


def test_mandatory_content_cannot_be_silently_discarded(monkeypatch):
    from app import security_assessment as module

    monkeypatch.setattr(module, "MAX_BASELINE_BYTES", 10)
    with pytest.raises(ValueError, match="Mandatory baseline"):
        module.build_security_baseline(saved_case())


def test_unicode_evidence_uses_utf8_size_and_stays_within_response_limit(monkeypatch):
    from app import security_assessment as module

    saved = gateway_case(30)
    # Exercise a stored descriptive field, not an invented Unicode event identifier.
    saved["report"]["limitations"].append("é" * 2000)
    monkeypatch.setattr(module, "MAX_BASELINE_BYTES", 8000)
    result = module.build_security_baseline(saved)
    raw = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode()
    assert len(raw) <= 8000
    assert result["coverage"]["reviewed_records"] == 30
    assert "é" * 2000 in result["evidence"][0]["content"]["limitations"]
    assert result["coverage"]["display_limited"]
