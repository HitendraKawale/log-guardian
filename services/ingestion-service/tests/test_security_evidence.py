"""Catch false joins, inflated counts and attacker-owned source configuration."""

import json

import pytest

SCOPE = {
    "services": ["edge", "auth"],
    "start": "2026-09-01T10:00:00Z",
    "end": "2026-09-01T10:10:00Z",
}
SOURCES = [
    {
        "source_id": "gateway",
        "service": "edge",
        "event_kind": "gateway_request",
        "request_namespace": "shop",
    },
    {
        "source_id": "authentication",
        "service": "auth",
        "event_kind": "authentication_result",
        "request_namespace": "shop",
    },
]
GATEWAY = {
    "evidence_id": "g1",
    "event_time": "2026-09-01T10:00:02Z",
    "request_id": "r1",
    "route": "/login",
    "http_status": 200,
    "client_address": "192.0.2.1",
}
AUTH = {
    "evidence_id": "a1",
    "event_time": "2026-09-01T10:00:01Z",
    "request_id": "r1",
    "account_ref": "account-1",
    "auth_outcome": "success",
}


def inspect(gateway=None, auth=None, sources=None, scope=None):
    from app.security_evidence import inspect_bundle

    rows = {
        "gateway": gateway if gateway is not None else [GATEWAY],
        "authentication": auth if auth is not None else [AUTH],
    }
    return inspect_bundle(
        {"scope": scope or SCOPE, "sources": sources or SOURCES},
        {key: b"\n".join(json.dumps(row).encode() for row in value) for key, value in rows.items()},
    )


def test_links_sources_only_in_owner_namespace_and_keeps_source_time_order():
    report = inspect()
    assert report["links"] == [
        {
            "request_namespace": "shop",
            "request_id": "r1",
            "gateway": ["gateway", "g1"],
            "authentication": ["authentication", "a1"],
        }
    ]
    assert [row["evidence"][1] for row in report["timeline"]] == ["a1", "g1"]
    assert report["sources"]["authentication"]["auth_outcomes"] == {
        "success": 1,
        "failure": 0,
        "unavailable": 0,
    }
    assert report["collection_complete"] is None
    assert {"clock_alignment_unverified", "impact_not_established"} <= set(report["limitations"])


@pytest.mark.parametrize("namespace", [None, "other-shop"])
def test_unrelated_or_untrusted_request_ids_never_link(namespace):
    sources = [SOURCES[0], {**SOURCES[1], "request_namespace": namespace}]
    report = inspect(sources=sources)
    assert report["links"] == []
    assert len(report["unlinked"]) == 2


def test_http_success_is_not_auth_success_and_missing_ids_are_not_time_joined():
    report = inspect(auth=[{**AUTH, "request_id": None, "auth_outcome": "failure"}])
    assert not report["links"]
    assert report["sources"]["authentication"]["auth_outcomes"]["success"] == 0
    assert len(report["unlinked"]) == 2


def test_identical_duplicates_do_not_inflate_observations_but_report_delivery_count():
    report = inspect(gateway=[GATEWAY, GATEWAY])
    assert report["input_records"] == 3
    assert report["duplicate_records"] == 1
    assert len(report["timeline"]) == 2
    assert len(report["links"]) == 1


def test_duplicate_identity_with_conflicting_content_rejects_bundle():
    with pytest.raises(ValueError, match="conflicting_evidence"):
        inspect(auth=[AUTH, {**AUTH, "auth_outcome": "failure"}])


def test_reused_request_id_preserves_all_outcomes_without_confirming_a_link():
    report = inspect(auth=[AUTH, {**AUTH, "evidence_id": "a2", "auth_outcome": "failure"}])
    assert not report["links"]
    assert report["ambiguous_groups"] == [
        {
            "request_namespace": "shop",
            "request_id": "r1",
            "evidence": [["authentication", "a1"], ["authentication", "a2"], ["gateway", "g1"]],
        }
    ]
    assert len(report["timeline"]) == 3
    assert report["sources"]["authentication"]["auth_outcomes"]["failure"] == 1


def test_empty_and_missing_auth_evidence_are_not_clean_bills_of_health():
    empty = inspect(gateway=[], auth=[])
    assert empty["timeline"] == []
    assert "no_evidence" in empty["gaps"]
    report = inspect(auth=[])
    assert report["unlinked"] == [["gateway", "g1"]]
    assert "missing_authentication_results" in report["gaps"]
    assert report["collection_complete"] is None


@pytest.mark.parametrize(
    "update",
    [
        {"source_id": "trusted"},
        {"request_namespace": "trusted"},
        {"service": "auth"},
        {"headers": {"X-Forwarded-For": "127.0.0.1"}},
        {"http_status": True},
        {"http_status": 600},
        {"event_time": "2026-09-01T10:00:00"},
        {"event_time": "2026-09-01T11:00:00Z"},
        {"event_time": 1},
        {"evidence_id": "a\nb"},
        {"request_id": ""},
        {"route": "/login?token=private"},
        {"route": "/login#secret"},
        {"client_address": "not-an-ip"},
        {"auth_outcome": "success"},
    ],
)
def test_rejects_untrusted_metadata_and_invalid_gateway_fields_without_echo(update):
    with pytest.raises(ValueError) as error:
        inspect(gateway=[{**GATEWAY, **update}])
    assert "private" not in str(error.value)
    assert "secret" not in str(error.value)


def test_source_config_cannot_expand_scope_or_conflict_with_itself():
    with pytest.raises(ValueError):
        inspect(sources=[{**SOURCES[0], "service": "outside"}, SOURCES[1]])
    with pytest.raises(ValueError):
        inspect(sources=[SOURCES[0], {**SOURCES[1], "source_id": "gateway"}])


@pytest.mark.parametrize(
    "raw",
    [
        b'{"evidence_id":"one","evidence_id":"two"}',
        b'{"http_status":NaN}',
        b'{"http_status":1e999}',
        b"[]",
        b"\xff",
        b"{",
        b" " * 16385,
        b"[" * 1200,
    ],
    ids=["duplicate-key", "nan", "overflow", "array", "utf8", "syntax", "line-limit", "depth"],
)
def test_malformed_or_oversized_lines_fail_closed(raw):
    from app.security_evidence import inspect_bundle

    with pytest.raises(ValueError):
        inspect_bundle(
            {"scope": SCOPE, "sources": SOURCES}, {"gateway": raw, "authentication": b""}
        )


def test_aggregate_limits_include_duplicates_and_all_sources():
    from app.security_evidence import inspect_bundle

    with pytest.raises(ValueError, match="record_limit"):
        inspect(gateway=[GATEWAY] * 501, auth=[AUTH] * 500)
    with pytest.raises(ValueError, match="byte_limit"):
        inspect_bundle(
            {"scope": SCOPE, "sources": SOURCES},
            {"gateway": b" " * 600000, "authentication": b" " * 600000},
        )


def test_ip_canonicalization_and_account_counts_do_not_create_actor_counts():
    report = inspect(
        gateway=[
            {**GATEWAY, "client_address": "2001:0db8::1"},
            {**GATEWAY, "evidence_id": "g2", "request_id": "r2", "client_address": "2001:db8::1"},
        ],
        auth=[AUTH, {**AUTH, "evidence_id": "a2", "request_id": "r2"}],
    )
    assert report["sources"]["gateway"]["distinct_client_addresses"] == 1
    assert report["sources"]["authentication"]["distinct_account_refs"] == 1
    assert len(report["links"]) == 2


def test_timestamp_overflow_is_a_sanitized_validation_error():
    with pytest.raises(ValueError, match="invalid_event"):
        inspect(gateway=[{**GATEWAY, "event_time": "0001-01-01T00:00:00+01:00"}])
    with pytest.raises(ValueError, match="invalid_source_configuration"):
        inspect(scope={**SCOPE, "start": "0001-01-01T00:00:00+01:00"})


def test_unknown_auth_outcome_and_missing_identity_are_explicit_gaps():
    report = inspect(auth=[{**AUTH, "auth_outcome": "unavailable", "account_ref": None}])
    assert len(report["links"]) == 1
    assert report["sources"]["authentication"]["auth_outcomes"] == {
        "success": 0,
        "failure": 0,
        "unavailable": 1,
    }
    assert {"missing_account_ref", "unavailable_authentication_outcome"} <= set(report["gaps"])


def test_canonical_duplicates_and_input_order_do_not_change_report():
    canonical = inspect()
    equivalent = {**AUTH, "event_time": "2026-09-01T11:00:01+01:00"}
    assert inspect(auth=[equivalent]) == canonical
    reverse_sources = list(reversed(SOURCES))
    assert inspect(sources=reverse_sources) == canonical
    duplicated = inspect(auth=[AUTH, equivalent])
    assert duplicated["duplicate_records"] == 1
    assert len(duplicated["links"]) == 1


def test_requires_one_input_for_each_configured_source():
    from app.security_evidence import inspect_bundle

    with pytest.raises(ValueError, match="source_inputs"):
        inspect_bundle({"scope": SCOPE, "sources": SOURCES}, {"gateway": b""})
