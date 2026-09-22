"""Candidate UI contracts use scripted state without paid providers."""

import pytest
from playwright.sync_api import expect

from tests.e2e.stub_server import MALICIOUS, start_servers


@pytest.fixture
def detector_ui(page):
    frontend, api, state, shutdown = start_servers()
    state.detectors = [
        {"service": "checkout", "observed": 20, "novelty_ready": False, "baseline_ready": False}
    ]
    state.candidates = [
        {
            "id": "one",
            "service": "checkout",
            "level": "ERROR",
            "message": MALICIOUS,
            "occurred_at": "2026-09-22T10:00:00Z",
            "last_seen_at": "2026-09-22T10:01:00Z",
            "occurrence_count": 2,
            "reason": "error-burst",
            "activity": "active",
            "status": "new",
            "scope": {},
            "signal_details": {
                "count": 6,
                "baseline_mean": 2,
                "threshold": 6,
                "learning": False,
                "reasons": ["error-burst"],
            },
        }
    ]
    page.goto(f"{frontend}/?api={api}")
    page.get_by_role("button", name="Candidates", exact=True).click()
    yield page, state
    shutdown()


def test_readiness_counts_reasons_and_untrusted_message(detector_ui):
    page, state = detector_ui
    expect(page.locator("#detector-status")).to_contain_text(
        "checkout: novelty learning; baseline learning; 20 timely logs"
    )
    row = page.locator("#candidates-body tr").first
    expect(row).to_contain_text("2 observations")
    expect(row).to_contain_text("6 errors this minute")
    expect(row).to_contain_text("threshold 6")
    expect(row).to_contain_text("active")
    expect(row).to_contain_text(MALICIOUS)
    assert row.locator("img").count() == 0 and page.evaluate("window.xss") is None
    state.detectors[0].update(novelty_ready=True, baseline_ready=True)
    state.candidates[0].update(activity="quiet", occurrence_count=4)
    page.get_by_role("button", name="Refresh", exact=True).click()
    expect(row).to_contain_text("quiet")
    expect(row).to_contain_text("4 observations")
    expect(page.locator("#detector-status")).to_contain_text("baseline ready")


def test_keyboard_dismissal_keeps_review_and_activity_separate(detector_ui):
    page, state = detector_ui
    dismiss = page.get_by_role("button", name="Dismiss", exact=True)
    dismiss.focus()
    page.keyboard.press("Enter")
    expect(page.locator("#candidates-body")).to_contain_text("No candidates match")
    page.locator("#c-status").select_option("dismissed")
    expect(page.locator("#candidates-body")).to_contain_text("dismissed")
    expect(page.locator("#candidates-body")).to_contain_text("active")


def test_detector_failure_does_not_hide_queue_and_promoted_link_survives(detector_ui):
    page, state = detector_ui
    state.fail_detectors = True
    state.candidates[0].update(status="promoted", investigation_id="run-existing")
    page.locator("#c-status").select_option("promoted")
    expect(page.locator("#detector-status")).to_contain_text("Could not load detector state (503)")
    expect(page.locator("#candidates-body")).to_contain_text("promoted")
    expect(page.locator("#candidates-body .badge")).to_have_attribute(
        "title", "investigation run-existing"
    )
    expect(page.locator("#candidates-body button")).to_have_count(0)
    assert not state.runs
