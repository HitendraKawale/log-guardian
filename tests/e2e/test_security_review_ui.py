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
def security_stack(tmp_path, request):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    log = (tmp_path / "server.log").open("w+")
    program = """
import os, sys, uvicorn, asyncio, contextlib, json
import httpx
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import async_sessionmaker
from app.main import app
from app.database import engine
from app.investigator import run_once
from fastapi.staticfiles import StaticFiles

async def scripted(request):
    body = json.loads(request.content)
    batch = json.loads(body['messages'][-1]['content'])
    ref = next(i['evidence_id'] for i in batch['items']
               if i['kind'] == 'security_event' and i['content'].get('auth_outcome') == 'failure')
    report = dict(observations=[dict(claim='Scripted check: one recorded authentication failure.', evidence_ids=[ref])],
                  missing_evidence=['Account compromise is not established.'], alternatives=[],
                  likely_cause=None, outcome='inconclusive', suggested_checks=[])
    return httpx.Response(200, json=dict(id='scripted-browser', object='chat.completion', created=1,
        model=body['model'], choices=[dict(index=0, finish_reason='stop', message=dict(role='assistant', content=json.dumps(report)))],
        usage=dict(prompt_tokens=100, completion_tokens=100, total_tokens=200, prompt_tokens_details=dict(cached_tokens=0))))

original = app.router.lifespan_context
@contextlib.asynccontextmanager
async def lifespan(app):
    async with original(app):
        async with AsyncOpenAI(api_key='scripted-placeholder', max_retries=0,
             http_client=httpx.AsyncClient(transport=httpx.MockTransport(scripted))) as provider:
            stop = asyncio.Event()
            async def worker():
                factory = async_sessionmaker(engine, expire_on_commit=False)
                while not stop.is_set():
                    await run_once(factory, provider, 'scripted-browser-worker')
                    await asyncio.sleep(0.05)
            task = asyncio.create_task(worker()) if sys.argv[2] == 'scripted' else None
            try:
                yield
            finally:
                stop.set()
                if task is not None:
                    await task
app.router.lifespan_context = lifespan
app.mount('/ui', StaticFiles(directory=os.environ['LG_TEST_FRONTEND'], html=True))
uvicorn.run(app, fd=int(sys.argv[1]), log_level='warning')
"""
    process = subprocess.Popen(
        [sys.executable, "-c", program, str(sock.fileno()), getattr(request, "param", "scripted")],
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
            "INVESTIGATION_API_KEY": "execution-test",
            "OPENAI_API_KEY": "",
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


def test_explicit_security_investigation_with_scripted_worker(page, security_stack, tmp_path):
    connect(page, security_stack)
    upload_example(page)
    execution = {"X-API-Key": "execution-test"}
    assert page.request.get(f"{security_stack}/investigations", headers=execution).json() == []
    page.get_by_label("Investigation API key", exact=True).fill("security-test")
    page.get_by_label("I authorize sharing this case with the model provider.", exact=True).check()
    page.get_by_role("button", name="Start or open investigation", exact=True).click()
    expect(page.locator("#security-run-message")).to_contain_text("401")
    assert page.request.get(f"{security_stack}/investigations", headers=execution).json() == []
    page.get_by_label("Investigation API key", exact=True).fill("execution-test")
    deliveries = []

    def lose_promotion_response(route):
        deliveries.append(route.request.url)
        if len(deliveries) == 1:
            accepted = route.fetch()
            assert accepted.status == 201
            route.abort()
        else:
            route.continue_()

    page.route(f"{security_stack}/investigations/from-security-case/*", lose_promotion_response)
    page.get_by_role("button", name="Start or open investigation", exact=True).click()
    expect(page.locator("#security-run-message")).to_contain_text("Retry this same case")
    page.get_by_role("button", name="Start or open investigation", exact=True).click()
    expect(page.locator("#security-run-status")).to_contain_text("completed", timeout=15000)
    assert len(deliveries) == 2 and len(set(deliveries)) == 1
    expect(page.locator("#security-run-report")).to_contain_text("Scripted check")
    page.locator("#security-run-report .citation").first.click()
    expect(page.locator("#security-run-evidence details[open] pre")).to_contain_text(
        '"auth_outcome": "failure"'
    )
    page.get_by_role("button", name="Start or open investigation", exact=True).click()
    expect(page.locator("#security-run-status")).to_contain_text("completed")
    assert len(page.request.get(f"{security_stack}/investigations", headers=execution).json()) == 1
    assert page.evaluate("JSON.stringify(localStorage) + JSON.stringify(sessionStorage)") == "{}{}"
    assert "execution-test" not in page.url
    page.screenshot(path=str(tmp_path / "security-investigation-desktop.png"), full_page=True)
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.screenshot(path=str(tmp_path / "security-investigation-mobile.png"), full_page=True)
    page.reload()
    expect(page.get_by_label("Investigation API key", exact=True)).to_have_value("")
    page.get_by_label("Security API key", exact=True).fill("security-test")
    page.get_by_role("button", name="Connect", exact=True).click()
    page.locator("#security-history button").click()
    page.get_by_label("Investigation API key", exact=True).fill("execution-test")
    page.get_by_label("I authorize sharing this case with the model provider.", exact=True).check()
    page.get_by_role("button", name="Start or open investigation", exact=True).click()
    expect(page.locator("#security-run-report")).to_contain_text("Scripted check")
    runs = page.request.get(f"{security_stack}/investigations", headers=execution).json()
    hostile = '<img src=x onerror="window.xss=1">'

    def hostile_draft(route):
        reply = route.fetch()
        run = reply.json()
        run["report"]["observations"][0]["claim"] = hostile
        route.fulfill(response=reply, json=run)

    page.route(f"{security_stack}/investigations/{runs[0]['id']}", hostile_draft)
    page.get_by_role("button", name="Start or open investigation", exact=True).click()
    expect(page.locator("#security-run-report")).to_contain_text(hostile)
    assert page.locator("#security-run-report img").count() == 0
    assert page.evaluate("window.xss") is None
    page.get_by_label("API endpoint", exact=True).fill("http://localhost:1")
    expect(page.get_by_label("Investigation API key", exact=True)).to_have_value("")
    expect(page.locator("#security-run-report")).to_be_empty()


@pytest.mark.parametrize("security_stack", ["idle"], indirect=True)
def test_cancelled_case_is_not_requeued(page, security_stack):
    connect(page, security_stack)
    upload_example(page)
    page.get_by_label("Investigation API key", exact=True).fill("execution-test")
    page.get_by_label("I authorize sharing this case with the model provider.", exact=True).check()
    page.get_by_role("button", name="Start or open investigation", exact=True).click()
    expect(page.locator("#security-run-status")).to_contain_text("queued")
    page.get_by_role("button", name="Cancel investigation", exact=True).click()
    expect(page.locator("#security-run-status")).to_contain_text("cancelled")
    page.get_by_role("button", name="Start or open investigation", exact=True).click()
    expect(page.locator("#security-run-status")).to_contain_text("cancelled")
    runs = page.request.get(
        f"{security_stack}/investigations", headers={"X-API-Key": "execution-test"}
    ).json()
    assert len(runs) == 1 and runs[0]["status"] == "cancelled"
