"""The adapter must not turn client metadata or HTTP status into trusted auth evidence."""

import json

import pytest

from tests.security_case_helpers import AUTH, NGINX, OWNER, SCOPE, payload


def test_prescribed_formats_link_without_treating_http_200_as_auth_success():
    from app.security_adapters import analyze_import

    report = analyze_import(OWNER, payload())
    assert len(report["links"]) == 1
    assert report["sources"]["auth"]["auth_outcomes"] == {
        "success": 0,
        "failure": 1,
        "unavailable": 0,
    }
    assert report["links"][0]["gateway"] == ["edge", "request-1"]
    assert report["links"][0]["authentication"] == ["auth", "auth-1"]


@pytest.mark.parametrize(
    "change",
    [
        {"X-Forwarded-For": "127.0.0.1"},
        {"source_id": "owner"},
        {"request_namespace": "owner"},
        {"route": "/login?password=PRIVATE"},
        {"status": True},
        {"status": "200.0"},
        {"remote_addr": "invalid"},
        {"request_id": None},
        {"time": "2026-09-01"},
    ],
)
def test_nginx_adapter_rejects_unknown_or_unsafe_fields_without_echo(change):
    from app.security_adapters import analyze_import

    with pytest.raises(ValueError) as error:
        analyze_import(OWNER, payload(nginx={**NGINX, **change}))
    assert "PRIVATE" not in str(error.value)


def test_owner_controls_format_source_and_scope():
    from app.security_adapters import analyze_import

    for body in (
        {**payload(), "sources": OWNER["sources"]},
        {"scope": SCOPE, "logs": {"unknown": ""}},
        {**payload(), "scope": {**SCOPE, "services": ["elsewhere"]}},
        {**payload(), "scope": {**SCOPE, "services": [*SCOPE["services"], "elsewhere"]}},
    ):
        with pytest.raises(ValueError):
            analyze_import(OWNER, body)
    owner = {
        "sources": [{**OWNER["sources"][0], "format": "application_auth_json"}, OWNER["sources"][1]]
    }
    with pytest.raises(ValueError):
        analyze_import(owner, payload())


def test_auth_adapter_rejects_credentials_and_retains_unknown_results():
    from app.security_adapters import analyze_import

    with pytest.raises(ValueError):
        analyze_import(OWNER, payload(auth={**AUTH, "password": "PRIVATE"}))
    report = analyze_import(OWNER, payload(auth={**AUTH, "outcome": "unavailable"}))
    assert report["sources"]["auth"]["auth_outcomes"]["unavailable"] == 1


def test_raw_limits_and_duplicate_json_are_checked_before_normalizing():
    from app.security_adapters import analyze_import

    for raw in (
        '{"status":"200","status":"401"}',
        "x" * 1048577,
        "\n".join([json.dumps(NGINX)] * 1001),
    ):
        with pytest.raises(ValueError):
            analyze_import(OWNER, {"scope": SCOPE, "logs": {"edge": raw, "auth": ""}})
