"""Drive the real security import API and static page without provider or Docker services."""

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from playwright.sync_api import expect

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.e2e


@pytest.fixture
def security_stack(tmp_path):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    log = (tmp_path / "server.log").open("w+")
    program = """
import os, sys, uvicorn
from app.main import app
from fastapi.staticfiles import StaticFiles
app.mount('/ui', StaticFiles(directory=os.environ['LG_TEST_FRONTEND'], html=True))
uvicorn.run(app, fd=int(sys.argv[1]), log_level='warning')
"""
    process = subprocess.Popen(
        [sys.executable, "-c", program, str(sock.fileno())],
        cwd=ROOT / "services/ingestion-service",
        pass_fds=(sock.fileno(),),
        stdout=log,
        stderr=log,
        env={
            **os.environ,
            "DATABASE_URL": f"sqlite+aiosqlite:///{tmp_path / 'ui.db'}",
            "SECURITY_API_KEY": "security-test",
            "SECURITY_SOURCES_PATH": str(ROOT / "examples/security-review/sources.json"),
            "LG_TEST_FRONTEND": str(ROOT / "frontend"),
            "KAFKA_ENABLED": "false",
            "INVESTIGATION_API_KEY": "",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "",
            "OTEL_CONSOLE": "0",
        },
    )
    sock.close()
    url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and process.poll() is None:
            try:
                with urllib.request.urlopen(f"{url}/health", timeout=1) as response:
                    if response.status == 200:
                        break
            except (urllib.error.URLError, TimeoutError):
                time.sleep(0.1)
        else:
            log.seek(0)
            pytest.fail(log.read())
        yield url
    finally:
        process.terminate()
        process.wait(timeout=10)
        log.close()


def connect(page, url):
    page.goto(f"{url}/ui/security.html?api={url}")
    page.get_by_label("Security API key", exact=True).fill("security-test")
    page.get_by_role("button", name="Connect", exact=True).click()
    expect(page.get_by_label("edge log file")).to_be_visible()


def upload_example(page, *, expect_saved=True):
    page.get_by_label("From (UTC)", exact=True).fill("2026-09-01T10:00:00Z")
    page.get_by_label("To (UTC)", exact=True).fill("2026-09-01T10:10:00Z")
    page.get_by_label("edge log file").set_input_files(
        ROOT / "examples/security-review/nginx.jsonl"
    )
    page.get_by_label("auth log file").set_input_files(ROOT / "examples/security-review/auth.jsonl")
    page.get_by_role("button", name="Save review", exact=True).click()
    if expect_saved:
        expect(page.get_by_role("heading", name="3 linked requests", exact=True)).to_be_visible()


def test_real_upload_replay_reload_citations_and_mobile(page, security_stack, tmp_path):
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(f"{security_stack}/ui/?api={security_stack}")
    page.get_by_role("link", name="Security review", exact=True).click()
    expect(page.get_by_label("API endpoint", exact=True)).to_have_value(security_stack)
    connect(page, security_stack)
    upload_example(page)
    expect(page.locator("#security-outcomes")).to_have_text("2 failures, 1 success, 0 unavailable.")
    expect(page.locator("#security-limits")).to_contain_text("not established")
    expect(page.locator("#security-history button")).to_have_count(1)
    page.get_by_role("button", name='["edge","r1"]', exact=True).click()
    expect(page.locator("details[open] pre")).to_contain_text('"route": "/login"')
    page.get_by_role("button", name="Save review", exact=True).click()
    expect(page.locator("#security-message")).to_contain_text("Existing review")
    expect(page.locator("#security-history button")).to_have_count(1)
    assert page.evaluate("JSON.stringify(localStorage) + JSON.stringify(sessionStorage)") == "{}{}"
    page.reload()
    expect(page.get_by_label("Security API key", exact=True)).to_have_value("")
    page.get_by_label("Security API key", exact=True).fill("security-test")
    page.get_by_role("button", name="Connect", exact=True).click()
    page.locator("#security-history button").click()
    expect(page.get_by_role("heading", name="3 linked requests", exact=True)).to_be_visible()
    page.screenshot(path=str(tmp_path / "security-desktop.png"), full_page=True)
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.screenshot(path=str(tmp_path / "security-mobile.png"), full_page=True)
    assert errors == []


def test_wrong_key_and_rejected_file_never_show_a_saved_success(page, security_stack):
    connect(page, security_stack)
    page.get_by_label("Security API key", exact=True).fill("wrong")
    page.get_by_role("button", name="Connect", exact=True).click()
    expect(page.locator("#security-message")).to_contain_text("401")
    page.get_by_label("Security API key", exact=True).fill("security-test")
    page.get_by_role("button", name="Connect", exact=True).click()
    expect(page.get_by_label("edge log file")).to_be_visible()
    page.get_by_label("From (UTC)", exact=True).fill("2026-09-01T10:00:00Z")
    page.get_by_label("To (UTC)", exact=True).fill("2026-09-01T10:10:00Z")
    page.get_by_label("edge log file").set_input_files(
        {"name": "bad.jsonl", "mimeType": "application/json", "buffer": b'{"password":"PRIVATE"}'}
    )
    page.get_by_label("auth log file").set_input_files(ROOT / "examples/security-review/auth.jsonl")
    page.get_by_role("button", name="Save review", exact=True).click()
    expect(page.locator("#security-message")).to_contain_text("422")
    expect(page.locator("#security-history button")).to_have_count(0)
    expect(page.locator("#security-message")).not_to_contain_text("PRIVATE")


def test_unknown_delivery_retries_the_same_key_after_server_commit(page, security_stack):
    connect(page, security_stack)
    keys = []

    def lose_first_response(route):
        if route.request.method != "POST":
            route.continue_()
            return
        keys.append(route.request.headers["idempotency-key"])
        if len(keys) == 1:
            response = route.fetch()
            assert response.status == 201
            route.abort()
        else:
            route.continue_()

    page.route(f"{security_stack}/security/cases", lose_first_response)
    upload_example(page, expect_saved=False)
    expect(page.locator("#security-message")).to_contain_text("retry unchanged files")
    page.get_by_role("button", name="Save review", exact=True).click()
    expect(page.locator("#security-message")).to_contain_text("Existing review")
    expect(page.locator("#security-history button")).to_have_count(1)
    assert len(keys) == 2 and keys[0] == keys[1]


def test_untrusted_saved_text_cannot_create_markup(page, security_stack):
    connect(page, security_stack)
    upload_example(page)
    hostile = '<img src=x onerror="window.xss=1"><script>window.xss=2</script>'

    def untrusted_report(route):
        response = route.fetch()
        saved = response.json()
        saved["report"]["timeline"][0]["auth_outcome"] = hostile
        route.fulfill(response=response, json=saved)

    page.route(f"{security_stack}/security/cases/*", untrusted_report)
    page.locator("#security-history button").click()
    expect(page.locator("#security-timeline")).to_contain_text(hostile)
    assert page.locator("#security-timeline img, #security-timeline script").count() == 0
    assert page.evaluate("window.xss") is None
