"""Browser tests for the candidate review tab, driven against the live stack.

The frontend has no build step and no unit tests, so a real browser is the only
thing that can say whether this works. The important assertion here is a
negative one: the dashboard must offer no way to start a paid investigation,
because it holds only the log API key.

    make test-e2e
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
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


@pytest.fixture
def candidates(page: Page) -> Page:
    SHOTS.mkdir(parents=True, exist_ok=True)
    page.goto(DASHBOARD)
    page.click('.tab[data-view="candidates"]')
    return page


def test_candidates_tab_opens_and_queries_the_api(candidates: Page) -> None:
    expect(candidates.locator("#view-candidates")).to_be_visible()
    # Either rows or a stated empty reason, never a stuck placeholder.
    expect(candidates.locator("#candidates-body")).not_to_be_empty()
    candidates.screenshot(path=str(SHOTS / "candidates.png"), full_page=True)


def test_the_dashboard_offers_no_way_to_spend(candidates: Page) -> None:
    """The spend boundary, asserted in the browser.

    Reviewing holds the log key; promoting needs the investigation key. If a
    promote control ever appears here, that separation is gone.
    """
    view = candidates.locator("#view-candidates")
    for label in ("Promote", "Investigate", "Run investigation"):
        expect(view.get_by_role("button", name=label)).to_have_count(0)
    expect(view).to_contain_text("spends money")


def test_a_familiar_error_burst_appears_and_can_be_dismissed(candidates: Page) -> None:
    """Cold-start error bursts qualify without bypassing per-service learning."""
    marker = uuid.uuid4().hex[:8]
    for _ in range(5):
        response = candidates.request.post(
            f"{INGESTION_URL}/logs",
            data={
                "service": f"svc-{marker}",
                "level": "ERROR",
                "message": "inventory timeout",
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )
        assert response.status == 201
    candidates.click("#c-refresh")
    row = candidates.locator("#candidates-body tr", has_text=f"svc-{marker}")
    expect(row.first).to_contain_text("error-burst")
    expect(row.first).to_contain_text("5 errors this minute")
    row.first.get_by_role("button", name="Dismiss").click()

    candidates.select_option("#c-status", "dismissed")
    expect(
        candidates.locator("#candidates-body tr", has_text=f"svc-{marker}").first
    ).to_contain_text("dismissed")
