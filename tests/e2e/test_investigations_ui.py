"""Browser tests for the investigation UI against the deterministic stub API.

These verify UI behavior (progress, citations, cancellation, states, safety)
without Docker or provider spend. Backend behavior has its own suites; the
live-stack dashboard tests remain in test_dashboard.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.stub_server import start_servers

pytestmark = pytest.mark.e2e

SHOTS = Path(__file__).parent / "screenshots"


@pytest.fixture
def stub():
    frontend, api, state, shutdown = start_servers()
    yield frontend, api, state
    shutdown()


@pytest.fixture
def ui(stub, page: Page):
    frontend, api, state = stub
    page.goto(f"{frontend}/?api={api}")
    expect(page.locator("#inv-list")).to_contain_text("No investigations yet")
    return page


def start_run(page: Page, question: str):
    page.fill('#inv-form [name="question"]', question)
    page.fill('#inv-form [name="services"]', "checkout")
    page.click('#inv-form button[type="submit"]')


def test_full_run_progress_report_and_citation_drawer(ui: Page):
    start_run(ui, "Why did checkout time out?")
    expect(ui.locator("#inv-status")).to_have_text("completed", timeout=10_000)
    # Progress recorded real tool activity before completion.
    expect(ui.locator("#inv-events")).to_contain_text("query_logs")
    expect(ui.locator("#inv-events")).to_contain_text("1 item(s)")
    expect(ui.locator("#inv-outcome")).to_have_text("Supported conclusion")
    expect(ui.locator("#inv-meta")).to_contain_text("$0.00123000")
    ui.locator(".citation", has_text="log:1").first.click()
    drawer = ui.locator("#citation-drawer")
    expect(drawer).to_be_visible()
    expect(drawer).to_contain_text("checkout")
    ui.keyboard.press("Escape")
    expect(drawer).to_be_hidden()


def test_malicious_log_and_report_text_is_never_executed(ui: Page):
    start_run(ui, "Why did checkout time out?")
    expect(ui.locator("#inv-status")).to_have_text("completed", timeout=10_000)
    expect(ui.locator("#inv-report")).to_contain_text("Ignore instructions")
    assert ui.evaluate("window.xss") is None
    assert ui.locator("#inv-report img").count() == 0
    ui.click('.tab[data-view="logs"]')
    expect(ui.locator("#logs-body")).to_contain_text("Ignore instructions")
    assert ui.evaluate("window.xss") is None
    assert ui.locator("#logs-body img").count() == 0


def test_inconclusive_state_shows_gaps_not_a_guess(ui: Page):
    start_run(ui, "inconclusive: what caused the search timeouts?")
    expect(ui.locator("#inv-status")).to_have_text("completed", timeout=10_000)
    expect(ui.locator("#inv-outcome")).to_have_text("Inconclusive")
    report = ui.locator("#inv-report")
    expect(report).to_contain_text("does not establish a cause")
    expect(report).to_contain_text("Upstream traces for the failing interval")
    expect(report).not_to_contain_text("Likely cause")


def test_provider_failure_shows_error_and_partial_evidence(ui: Page):
    start_run(ui, "provider-fail: why?")
    expect(ui.locator("#inv-status")).to_have_text("failed", timeout=10_000)
    expect(ui.locator("#inv-error")).to_contain_text("provider_error")
    expect(ui.locator("#inv-error")).to_contain_text("Partial evidence")
    expect(ui.locator("#inv-events")).to_contain_text("query_logs")
    expect(ui.locator("#inv-report-section")).to_be_hidden()


def test_cancel_running_run(ui: Page):
    start_run(ui, "hang: never finishes")
    expect(ui.locator("#inv-status")).to_have_text("running", timeout=10_000)
    ui.click("#inv-cancel")
    expect(ui.locator("#inv-status")).to_have_text("cancelled", timeout=10_000)
    expect(ui.locator("#inv-error")).to_contain_text("cancelled")
    expect(ui.locator("#inv-cancel")).to_be_hidden()


def test_history_reload_and_reselection(ui: Page):
    start_run(ui, "First question?")
    expect(ui.locator("#inv-status")).to_have_text("completed", timeout=10_000)
    start_run(ui, "Second question?")
    expect(ui.locator("#inv-status")).to_have_text("completed", timeout=10_000)
    ui.click("#inv-reload")
    items = ui.locator(".inv-item-btn")
    expect(items).to_have_count(2)
    items.last.click()  # Newest first, so the last item is the first question.
    expect(ui.locator("#inv-question")).to_have_text("First question?")


def test_feedback_saves_specific_label_and_shows_failures(stub, page: Page):
    frontend, api, state = stub
    page.goto(f"{frontend}/?api={api}")
    page.click('.tab[data-view="logs"]')
    row = page.locator("#logs-body tr").first
    row.locator(".fb-anom").click()
    # The specific label round-trips through the API and the stub's storage.
    expect(page.locator("#logs-body")).to_contain_text("labeled: anomaly", timeout=10_000)
    assert state.logs[-1]["true_label"] is True
    state.fail_feedback = True
    page.fill('#log-form [name="message"]', "second row")
    page.click('#log-form button[type="submit"]')
    fresh = page.locator("#logs-body tr", has_text="second row")
    expect(fresh).to_be_visible(timeout=10_000)
    fresh.locator(".fb-norm").click()
    expect(page.locator("#form-msg")).to_contain_text("was not saved (HTTP 500)")
    expect(page.locator("#logs-body tr", has_text="second row")).not_to_contain_text("labeled")


def test_evaluations_view_is_recorded_and_read_only(ui: Page):
    ui.click('.tab[data-view="evaluations"]')
    panel = ui.locator("#view-evaluations")
    expect(panel).to_contain_text("recorded")
    expect(panel).to_contain_text("not live model runs")
    expect(panel).to_contain_text("Held-out A/B/C comparison", timeout=10_000)
    expect(panel).to_contain_text("dev-01")
    assert panel.locator("button").count() == 0  # Nothing here triggers execution.


def test_keyboard_navigation_and_empty_states(ui: Page):
    expect(ui.locator("#inv-detail-empty")).to_contain_text("No investigation selected")
    tab = ui.locator('.tab[data-view="logs"]')
    tab.focus()
    ui.keyboard.press("Enter")
    expect(ui.locator("#view-logs")).to_be_visible()
    expect(ui.locator("#view-investigations")).to_be_hidden()
    assert ui.evaluate("document.activeElement.className").startswith("tab")


def test_viewports_desktop_and_mobile(ui: Page):
    start_run(ui, "Why did checkout time out?")
    expect(ui.locator("#inv-status")).to_have_text("completed", timeout=10_000)
    SHOTS.mkdir(exist_ok=True)
    ui.set_viewport_size({"width": 1440, "height": 900})
    assert ui.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    ui.screenshot(path=str(SHOTS / "investigations.png"))
    ui.set_viewport_size({"width": 390, "height": 844})
    assert ui.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    ui.screenshot(path=str(SHOTS / "investigations-mobile.png"))
    assert (SHOTS / "investigations.png").stat().st_size > 10_000
