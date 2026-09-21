"""Verify source observation states separately from API reachability in Chromium."""

import json

import pytest
from playwright.sync_api import expect

from tests.e2e.stub_server import MALICIOUS, start_servers

pytestmark = pytest.mark.e2e


@pytest.fixture
def source():
    frontend, api, state, shutdown = start_servers()
    try:
        yield frontend, api, state
    finally:
        shutdown()


def open_logs(page, frontend, api):
    page.goto(f"{frontend}/?api={api}")
    page.get_by_role("button", name="Logs", exact=True).click()


def test_empty_source_is_not_claimed_connected(page, source):
    frontend, api, state = source
    state.logs.clear()
    open_logs(page, frontend, api)
    expect(page.locator("#status-text")).to_have_text("API connected")
    expect(page.locator("#latest-log")).to_contain_text("No logs received")


def test_latest_source_is_unfiltered_and_rendered_as_text(page, source):
    frontend, api, state = source
    state.logs[0]["service"] = MALICIOUS

    def logs(route):
        body = state.logs if route.request.url.endswith("?limit=1") else []
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    page.route(f"{api}/logs?*", logs)
    open_logs(page, frontend, api)
    page.locator("#f-service").fill("another-service")
    expect(page.locator("#logs-body")).to_contain_text("No logs match")
    expect(page.locator("#latest-log")).to_contain_text(MALICIOUS)
    expect(page.locator("#latest-log")).to_contain_text("event time")
    expect(page.locator("#latest-log")).to_contain_text("observed")
    assert page.locator("#latest-log img, #latest-log script").count() == 0
    assert page.evaluate("window.xss") is None


def test_sqlite_event_time_is_utc_in_a_non_utc_browser(browser, source):
    frontend, api, state = source
    state.logs[0]["timestamp"] = "2026-09-21T12:00:00"
    context = browser.new_context(timezone_id="Asia/Kolkata")
    try:
        page = context.new_page()
        open_logs(page, frontend, api)
        expect(page.locator("#latest-log")).to_contain_text("event time 2026-09-21T12:00:00.000Z")
    finally:
        context.close()


@pytest.mark.parametrize("failure", ["unauthorized", "offline"])
def test_source_observation_becomes_stale_on_failure(page, source, failure):
    frontend, api, _ = source
    open_logs(page, frontend, api)
    expect(page.locator("#latest-log")).to_contain_text("checkout")

    def fail(route):
        if failure == "unauthorized":
            route.fulfill(status=401, body='{"detail":"unauthorized"}')
        else:
            route.abort()

    page.route(f"{api}/logs?*", fail)
    page.locator("#f-service").fill("force-refresh")
    expect(page.locator("#status-text")).to_have_text("API offline or unauthorized")
    expect(page.locator("#latest-log")).to_contain_text("stale")
    expect(page.locator("#latest-log")).to_contain_text("checkout")
