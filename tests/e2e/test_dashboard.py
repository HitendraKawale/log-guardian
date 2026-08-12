"""Browser tests for the dashboard, driven against the live stack.

The frontend is plain JS with no build step and no unit tests, so a real browser
is the only thing that can tell you whether it works. These drive Chromium
against the nginx container and the ingestion API behind it.

Screenshots land in tests/e2e/screenshots/ and are committed, which is also how
the dashboard gets into the README without hand-cropping anything.

    make test-e2e
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from tests.integration.conftest import FRONTEND_URL, INGESTION_URL, service_is_up

pytestmark = pytest.mark.e2e

SHOTS = Path(__file__).parent / "screenshots"
DASHBOARD = f"{FRONTEND_URL}/?api={INGESTION_URL}"


@pytest.fixture(scope="session", autouse=True)
def require_stack_for_browser() -> None:
    if not service_is_up(f"{INGESTION_URL}/health"):
        pytest.skip(f"stack not reachable at {INGESTION_URL}; run `make up`")


@pytest.fixture(autouse=True)
def shots_dir() -> None:
    SHOTS.mkdir(parents=True, exist_ok=True)


@pytest.fixture
def dashboard(page: Page) -> Page:
    page.goto(DASHBOARD)
    # The page polls every 3s; wait for the first successful round trip rather
    # than sleeping and hoping.
    expect(page.locator("#status-text")).to_have_text("connected", timeout=15_000)
    return page


def test_dashboard_loads_and_connects(dashboard: Page):
    expect(dashboard.locator("h1")).to_contain_text("Log Guardian")
    expect(dashboard.locator("#status-dot")).to_have_class(re.compile(r"online"))


def test_stat_cards_show_numbers(dashboard: Page):
    # Populated from GET /logs, so a number here means the API answered.
    expect(dashboard.locator("#stat-total")).to_have_text(re.compile(r"^\d+$"), timeout=15_000)
    expect(dashboard.locator("#stat-anomalies")).to_have_text(re.compile(r"^\d+$"))


def test_model_badge_reports_the_active_analyzer(dashboard: Page):
    expect(dashboard.locator("#model-badge")).to_contain_text(
        re.compile(r"model|heuristic"), timeout=20_000
    )


def test_ingesting_from_the_form_puts_a_row_in_the_table(dashboard: Page):
    marker = f"browser test {uuid.uuid4()}"
    form = dashboard.locator("#log-form")
    form.locator('input[name="service"]').fill("browser-test")
    form.locator('select[name="level"]').select_option("CRITICAL")
    form.locator('input[name="message"]').fill(marker)
    form.locator('button[type="submit"]').click()

    # The row arrives via the next poll, not the submit response.
    expect(dashboard.locator("#logs-body")).to_contain_text(marker, timeout=15_000)


def test_level_filter_narrows_the_table(dashboard: Page):
    marker = f"debug row {uuid.uuid4()}"
    form = dashboard.locator("#log-form")
    form.locator('input[name="service"]').fill("browser-test")
    form.locator('select[name="level"]').select_option("DEBUG")
    form.locator('input[name="message"]').fill(marker)
    form.locator('button[type="submit"]').click()
    expect(dashboard.locator("#logs-body")).to_contain_text(marker, timeout=15_000)

    dashboard.locator("#f-level").select_option("CRITICAL")
    expect(dashboard.locator("#logs-body")).not_to_contain_text(marker, timeout=15_000)


def test_feedback_button_records_a_label(dashboard: Page):
    marker = f"feedback row {uuid.uuid4()}"
    form = dashboard.locator("#log-form")
    form.locator('input[name="service"]').fill("browser-test")
    form.locator('select[name="level"]').select_option("CRITICAL")
    form.locator('input[name="message"]').fill(marker)
    form.locator('button[type="submit"]').click()

    row = dashboard.locator("#logs-body tr", has_text=marker)
    expect(row).to_be_visible(timeout=15_000)
    row.locator(".fb-btn").first.click()

    # Re-rendered from the API, so the label came back from the database.
    expect(dashboard.locator("#logs-body tr", has_text=marker)).not_to_contain_text(
        "?", timeout=15_000
    )


def test_pause_button_stops_the_refresh(dashboard: Page):
    toggle = dashboard.locator("#toggle-refresh")
    toggle.click()
    expect(toggle).to_contain_text(re.compile(r"Resume|▶"), timeout=5_000)


def test_capture_screenshots(dashboard: Page):
    """Not an assertion so much as the artefact the README uses."""
    dashboard.set_viewport_size({"width": 1440, "height": 900})
    expect(dashboard.locator("#logs-body tr").first).to_be_visible(timeout=15_000)
    dashboard.screenshot(path=str(SHOTS / "dashboard.png"), full_page=False)

    dashboard.set_viewport_size({"width": 420, "height": 900})
    dashboard.screenshot(path=str(SHOTS / "dashboard-mobile.png"), full_page=False)

    assert (SHOTS / "dashboard.png").stat().st_size > 10_000
