"""The exported static demo works in a real browser with no backend at all."""

from __future__ import annotations

import subprocess
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

ROOT = Path(__file__).resolve().parents[2]
SHOTS = Path(__file__).parent / "screenshots"


@pytest.fixture(scope="module")
def static_site():
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/export_static_demo.py")], check=True, timeout=60
    )
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(ROOT / "site"))
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture
def demo(static_site, page: Page):
    # No ?api= override and no backend anywhere: only static files are served.
    page.goto(static_site)
    expect(page.locator(".recorded-banner")).to_contain_text("Recorded demo")
    return page


def test_recorded_runs_render_without_backend_or_key(demo: Page):
    items = demo.locator(".inv-item-btn")
    expect(items).to_have_count(2)
    items.first.click()
    expect(demo.locator("#inv-status")).to_have_text("completed")
    expect(demo.locator("#inv-events")).to_contain_text("query_logs")
    expect(demo.locator("#inv-outcome")).to_have_text("Supported conclusion")
    expect(demo.locator("#inv-meta")).to_contain_text("gpt-4.1-mini-2025-04-14")


def test_citations_open_real_recorded_evidence(demo: Page):
    demo.locator(".inv-item-btn").first.click()
    demo.locator("#inv-report .citation").first.click()
    drawer = demo.locator("#citation-drawer")
    expect(drawer).to_be_visible()
    expect(demo.locator("#citation-body")).not_to_be_empty()


def test_inconclusive_recorded_example_shows_gaps(demo: Page):
    demo.locator(".inv-item-btn", has_text="search timeouts").click()
    expect(demo.locator("#inv-outcome")).to_have_text("Inconclusive")
    expect(demo.locator("#inv-report")).to_contain_text("does not establish a cause")
    expect(demo.locator("#inv-report")).to_contain_text("Missing evidence")


def test_live_execution_is_disabled_and_nothing_secret_ships(demo: Page, static_site):
    for control in demo.locator("#inv-form input, #inv-form button").all():
        assert control.is_disabled()
    expect(demo.locator("#inv-form-msg")).to_contain_text("disabled in the recorded demo")
    expect(demo.get_by_role("link", name="Security review", exact=True)).to_have_count(0)
    assert not list((ROOT / "site").glob("security.*"))
    import urllib.request

    blob = urllib.request.urlopen(f"{static_site}/recorded-runs.json").read().decode()
    for banned in ("sk-", "api_key", "OPENAI"):
        assert banned not in blob


def test_narrow_screen_layout_and_screenshot(demo: Page):
    demo.locator(".inv-item-btn").first.click()
    demo.set_viewport_size({"width": 390, "height": 844})
    assert demo.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    SHOTS.mkdir(exist_ok=True)
    demo.screenshot(path=str(SHOTS / "static-demo-mobile.png"))
    demo.set_viewport_size({"width": 1440, "height": 900})
    demo.screenshot(path=str(SHOTS / "static-demo.png"))
    assert (SHOTS / "static-demo.png").stat().st_size > 10_000
