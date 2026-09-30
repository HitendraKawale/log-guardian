"""Drive the real security import API and static page without provider or Docker services."""

import hashlib
import json
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
    if sys.argv[2] == 'provider-error':
        return httpx.Response(503, json={'error': {'message': 'scripted provider unavailable'}})
    body = json.loads(request.content)
    batch = json.loads(body['messages'][-1]['content'])
    events = [i for i in batch['items'] if i['kind'] == 'security_event']
    chosen = next((i for i in events if i['content'].get('auth_outcome') == 'failure'), events[0])
    identity = chosen['content']['evidence_id'] if sys.argv[2] == 'invalid' else chosen['evidence_id']
    report = dict(focus_evidence_ids=[identity], hypothesis_codes=[], check_codes=[])
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
            task = asyncio.create_task(worker()) if sys.argv[2] in {'scripted', 'invalid', 'provider-error'} else None
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
            "OTEL_CONSOLE": "",
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

    identity = page.request.get(
        f"{security_stack}/security/cases", headers={"X-API-Key": "security-test"}
    ).json()[0]["id"]
    page.route(f"{security_stack}/security/cases/{identity}", untrusted_report)
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
    expect(page.locator("#security-run-report")).to_contain_text(
        "Authentication service recorded failure"
    )
    expect(
        page.locator("#security-run-report").get_by_role(
            "heading", name="Recorded facts", exact=True
        )
    ).to_be_visible()
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
    expect(page.locator("#security-run-report")).to_contain_text(
        "Authentication service recorded failure"
    )
    runs = page.request.get(f"{security_stack}/investigations", headers=execution).json()
    hostile = '<img src=x onerror="window.xss=1">'

    def hostile_draft(route):
        reply = route.fetch()
        run = reply.json()
        run["report"]["facts"][0]["claim"] = hostile
        route.fulfill(response=reply, json=run)

    page.route(f"{security_stack}/investigations/{runs[0]['id']}", hostile_draft)
    page.get_by_role("button", name="Start or open investigation", exact=True).click()
    expect(page.locator("#security-run-report")).to_contain_text(hostile)
    assert page.locator("#security-run-report img").count() == 0
    assert page.evaluate("window.xss") is None
    page.get_by_label("API endpoint", exact=True).fill("http://localhost:1")
    expect(page.get_by_label("Investigation API key", exact=True)).to_have_value("")
    expect(page.locator("#security-run-report")).to_be_empty()


def test_security_walkthrough(browser, security_stack, tmp_path):
    """Record real browser actions; pauses only pace an explicitly requested recording."""
    recording = os.environ.get("LG_RECORD_DEMO") == "1"
    context = browser.new_context(
        viewport={"width": 1280, "height": 900},
        **(
            {"record_video_dir": str(tmp_path), "record_video_size": {"width": 1280, "height": 900}}
            if recording
            else {}
        ),
    )
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    steps = []

    def hold(caption):
        if recording:
            page.evaluate(
                "text => document.getElementById('recording-caption').textContent = text", caption
            )
            # Presentation timing, never a substitute for an assertion or readiness wait.
            page.wait_for_timeout(4000)
        steps.append(caption)

    try:
        page.goto(f"{security_stack}/ui/security.html?api={security_stack}")
        if recording:
            page.evaluate("""() => {
                const banner = document.createElement('aside');
                banner.style = 'position:fixed;top:0;left:0;right:0;z-index:100;background:#10263c;color:white;padding:12px 24px;font:16px system-ui;border-bottom:2px solid #4f9dff';
                const label = document.createElement('strong');
                label.textContent = 'SYNTHETIC LOGS / SCRIPTED PROVIDER / NO PAID CALLS';
                const caption = document.createElement('div'); caption.id = 'recording-caption';
                banner.append(label, caption); document.body.prepend(banner);
                document.body.style.paddingTop = '82px';
            }""")
            page.add_style_tag(content="* { scroll-margin-top: 105px; }")
        hold("Connect to the owner's evidence store. Only test credentials are used here.")
        page.get_by_label("Security API key", exact=True).fill("security-test")
        page.get_by_role("button", name="Connect", exact=True).click()
        expect(page.get_by_label("edge log file")).to_be_visible()
        hold(
            "The server selects source identity and request namespaces, not the uploaded log text."
        )
        upload_example(page)
        expect(page.locator("#security-outcomes")).to_have_text(
            "2 failures, 1 success, 0 unavailable."
        )
        execution = {"X-API-Key": "execution-test"}
        assert page.request.get(f"{security_stack}/investigations", headers=execution).json() == []
        page.locator("#security-title").scroll_into_view_if_needed()
        hold(
            "Six authored records produce three links. Saving evidence has not queued any model work."
        )
        page.screenshot(path=str(tmp_path / "security-review-poster.png"))
        page.get_by_role("button", name='["edge","r1"]', exact=True).click()
        expect(page.locator("#security-timeline details[open] pre")).to_contain_text(
            '"http_status": 200'
        )
        hold(
            "Inspect the saved gateway record. HTTP 200 does not establish successful authentication."
        )
        page.get_by_role("button", name='["auth","a1"]', exact=True).click()
        expect(
            page.locator("#security-timeline details[open]").filter(has_text="auth / a1")
        ).to_contain_text('"auth_outcome": "failure"')
        hold(
            "Its linked authentication record explicitly reports failure. Timing alone is not a link."
        )
        page.get_by_label("Investigation API key", exact=True).fill("execution-test")
        page.get_by_label(
            "I authorize sharing this case with the model provider.", exact=True
        ).check()
        hold(
            "A separate key and explicit consent are required. This recording uses only a scripted provider."
        )
        page.get_by_role("button", name="Start or open investigation", exact=True).click()
        expect(page.locator("#security-run-status")).to_contain_text("completed", timeout=15000)
        expect(page.locator("#security-run-report")).to_contain_text(
            "Authentication service recorded failure"
        )
        page.locator("#security-run-report").scroll_into_view_if_needed()
        hold(
            "The host renders facts from typed records. Model selections and displayed usage are scripted, not paid."
        )
        page.locator("#security-run-report .citation").first.click()
        expect(page.locator("#security-run-evidence details[open] pre")).to_contain_text(
            '"auth_outcome": "failure"'
        )
        hold(
            "The citation opens supplied evidence. Its completeness and correspondence to reality remain unverified."
        )
        page.locator("#security-limits").scroll_into_view_if_needed()
        hold(
            "One success is visible. Compromise, data access, actor identity and AI involvement remain unestablished."
        )
        runs = page.request.get(f"{security_stack}/investigations", headers=execution).json()
        assert len(runs) == 1 and runs[0]["status"] == "completed"
        events = page.request.get(
            f"{security_stack}/investigations/{runs[0]['id']}/events", headers=execution
        ).json()
        assert any(event["kind"] == "tool_request" for event in events)
        assert not errors
        (tmp_path / "walkthrough.json").write_text(
            json.dumps(
                {
                    "runtime_revision": subprocess.check_output(
                        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
                    ).strip(),
                    "real_model_requests": 0,
                    "provider": "httpx.MockTransport in security_stack test fixture",
                    "steps": steps,
                    "run": runs[0],
                    "events": events,
                    "sha256": {
                        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                        for name in [
                            "frontend/security.html",
                            "frontend/security.js",
                            "frontend/security.css",
                            "examples/security-review/nginx.jsonl",
                            "examples/security-review/auth.jsonl",
                            "examples/security-review/sources.json",
                        ]
                    },
                },
                indent=2,
            )
            + "\n"
        )
    finally:
        context.close()
    if recording:
        page.video.save_as(str(tmp_path / "security-review.webm"))


def test_missing_auth_v2_and_preserved_legacy_claim(page, security_stack, tmp_path):
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    connect(page, security_stack)
    page.get_by_label("From (UTC)", exact=True).fill("2026-09-01T10:00:00Z")
    page.get_by_label("To (UTC)", exact=True).fill("2026-09-01T10:10:00Z")
    page.get_by_label("edge log file").set_input_files(
        ROOT / "examples/security-review/nginx.jsonl"
    )
    page.get_by_label("auth log file").set_input_files(
        {"name": "empty.jsonl", "mimeType": "application/json", "buffer": b""}
    )
    page.get_by_role("button", name="Save review", exact=True).click()
    expect(page.get_by_role("heading", name="0 linked requests", exact=True)).to_be_visible()
    page.get_by_label("Investigation API key", exact=True).fill("execution-test")
    page.get_by_label("I authorize sharing this case with the model provider.", exact=True).check()
    page.get_by_role("button", name="Start or open investigation", exact=True).click()
    expect(page.locator("#security-run-status")).to_contain_text("completed", timeout=15000)
    report = page.locator("#security-run-report")
    expect(report).to_contain_text("Gateway recorded HTTP 200")
    expect(report).to_contain_text(
        "Authentication outcome is unknown; no authentication results were supplied."
    )
    expect(report).not_to_contain_text("Authentication service recorded success")
    button = report.locator(".citation").first
    button.focus()
    page.keyboard.press("Enter")
    expect(page.locator("#security-run-evidence details[open] pre")).to_contain_text(
        '"http_status": 200'
    )
    for width, name in [(1280, "desktop"), (390, "mobile")]:
        page.set_viewport_size({"width": width, "height": 900})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=str(tmp_path / f"typed-missing-auth-{name}.png"), full_page=True)
    archive = json.loads(
        (ROOT / "evals/results/2026-09-26-report-guidance-live/smoke-03.json").read_text()
    )
    run_id = page.request.get(
        f"{security_stack}/investigations", headers={"X-API-Key": "execution-test"}
    ).json()[0]["id"]
    replacement = archive["run"]["report"]
    invalidate_during_read = False

    def old_report(route):
        response = route.fetch()
        data = response.json()
        data["report"] = replacement
        if invalidate_during_read:
            page.get_by_label("Investigation API key", exact=True).fill("")
        route.fulfill(response=response, json=data)

    page.route(f"{security_stack}/investigations/{run_id}", old_report)
    page.get_by_role("button", name="Start or open investigation", exact=True).click()
    expect(report).to_contain_text("Legacy model draft")
    expect(report).to_contain_text("successful login attempt (HTTP 200)")
    expect(report.get_by_role("heading", name="Recorded facts", exact=True)).to_have_count(0)
    expect(page.locator("#security-assessment-report")).to_contain_text(
        "Authentication outcome is unknown"
    )
    for width, name in [(1280, "desktop"), (390, "mobile")]:
        page.set_viewport_size({"width": width, "height": 900})
        page.screenshot(path=str(tmp_path / f"legacy-false-claim-{name}.png"), full_page=True)
    replacement = {"schema_version": 99, "facts": [{"claim": "HIDDEN_UNKNOWN_VERSION"}]}
    page.get_by_role("button", name="Start or open investigation", exact=True).click()
    expect(report).to_contain_text("Unsupported report version")
    expect(report).not_to_contain_text("HIDDEN_UNKNOWN_VERSION")
    invalidate_during_read = True
    with page.expect_response(f"{security_stack}/investigations/{run_id}") as pending:
        page.get_by_role("button", name="Start or open investigation", exact=True).click()
    pending.value.finished()
    expect(page.get_by_label("Investigation API key", exact=True)).to_have_value("")
    expect(report).to_be_empty()
    expect(page.locator("#security-run-status")).to_contain_text("A linked investigation exists")
    assert page.evaluate("JSON.stringify(localStorage) + JSON.stringify(sessionStorage)") == "{}{}"
    assert errors == []


def test_v2_security_report_in_shared_investigation_history(page, security_stack, tmp_path):
    connect(page, security_stack)
    upload_example(page)
    page.get_by_label("Investigation API key", exact=True).fill("execution-test")
    page.get_by_label("I authorize sharing this case with the model provider.", exact=True).check()
    page.get_by_role("button", name="Start or open investigation", exact=True).click()
    expect(page.locator("#security-run-status")).to_contain_text("completed", timeout=15000)
    dashboard = page.context.new_page()
    errors = []
    dashboard.on("pageerror", lambda error: errors.append(str(error)))
    try:
        dashboard.set_extra_http_headers({"X-API-Key": "execution-test"})
        dashboard.goto(f"{security_stack}/ui/index.html?api={security_stack}")
        dashboard.get_by_role("button", name="Investigations", exact=True).click()
        dashboard.locator("#inv-list .inv-item-btn").first.click()
        expect(dashboard.locator("#inv-question")).to_contain_text("saved gateway")
        expect(dashboard.locator("#inv-report")).to_contain_text(
            "Authentication service recorded failure"
        )
        expect(dashboard.get_by_role("heading", name="Recorded facts", exact=True)).to_be_visible()
        expect(dashboard.locator("#inv-report")).to_contain_text(
            "business impact are not established"
        )
        expect(dashboard.locator("#inv-events .event-tool")).to_have_count(1)
        dashboard.locator("#inv-report .citation").first.click()
        expect(dashboard.locator("#citation-body")).to_contain_text('"auth_outcome": "failure"')
        dashboard.get_by_role("button", name="Close", exact=True).click()
        dashboard.screenshot(path=str(tmp_path / "shared-history-v2.png"), full_page=True)
        run = page.request.get(
            f"{security_stack}/investigations", headers={"X-API-Key": "execution-test"}
        ).json()[0]

        def unsupported(route):
            response = route.fetch()
            data = response.json()
            data["report"] = {
                "schema_version": 99,
                "outcome": "inconclusive",
                "facts": [{"claim": "HIDDEN_UNKNOWN_VERSION"}],
            }
            route.fulfill(response=response, json=data)

        dashboard.route(f"{security_stack}/investigations/{run['id']}", unsupported)
        dashboard.locator("#inv-list .inv-item-btn").first.click()
        expect(dashboard.locator("#inv-outcome")).to_have_text("Unsupported report version")
        expect(dashboard.locator("#inv-report")).not_to_contain_text("HIDDEN_UNKNOWN_VERSION")
        assert errors == []
    finally:
        print("Shared history browser errors:", errors)
        dashboard.close()


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


@pytest.mark.parametrize("security_stack", ["idle"], indirect=True)
def test_baseline_before_ai_consent(page, security_stack, tmp_path):
    connect(page, security_stack)
    upload_example(page)
    expect(page.locator("#security-assessment-status")).to_contain_text("No model call")
    expect(page.locator("#security-assessment-report")).to_contain_text(
        "Authentication service recorded failure"
    )
    expect(page.get_by_label("Investigation API key", exact=True)).to_have_value("")
    runs = page.request.get(
        f"{security_stack}/investigations", headers={"X-API-Key": "execution-test"}
    ).json()
    assert runs == []
    button = (
        page.locator("#security-assessment-report .citation")
        .filter(has_text="security-event:")
        .first
    )
    button.focus()
    page.keyboard.press("Enter")
    expect(page.locator("#security-assessment-evidence details[open] pre")).to_be_visible()
    assert page.evaluate("JSON.stringify(localStorage) + JSON.stringify(sessionStorage)") == "{}{}"
    page.screenshot(path=str(tmp_path / "baseline-no-model-desktop.png"), full_page=True)
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.screenshot(path=str(tmp_path / "baseline-no-model-mobile.png"), full_page=True)
    page.reload()
    expect(page.get_by_label("Security API key", exact=True)).to_have_value("")
    page.get_by_label("Security API key", exact=True).fill("security-test")
    page.get_by_role("button", name="Connect", exact=True).click()
    page.locator("#security-history button").first.click()
    expect(page.locator("#security-assessment-status")).to_contain_text("No model call")


@pytest.mark.parametrize("security_stack", ["invalid", "provider-error"], indirect=True)
def test_baseline_survives_ai_failure(page, security_stack, tmp_path):
    connect(page, security_stack)
    upload_example(page)
    expect(page.locator("#security-assessment-status")).to_contain_text("No model call")
    baseline = page.locator("#security-assessment-report").text_content()
    page.get_by_label("Investigation API key", exact=True).fill("execution-test")
    expect(page.locator("#security-assessment-report")).to_have_text(baseline)
    page.get_by_label("I authorize sharing this case with the model provider.", exact=True).check()
    page.get_by_role("button", name="Start or open investigation", exact=True).click()
    expect(page.locator("#security-run-status")).to_contain_text("failed", timeout=15000)
    expect(page.locator("#security-run-status")).to_contain_text(
        "factual assessment is independent"
    )
    expect(page.locator("#security-run-report")).to_be_empty()
    expect(page.locator("#security-assessment-report")).to_have_text(baseline)
    run = page.request.get(
        f"{security_stack}/investigations", headers={"X-API-Key": "execution-test"}
    ).json()[0]
    assert run["status"] == "failed" and run["report"] is None
    assert run["error"] in {"invalid_report", "provider_error"}
    page.screenshot(path=str(tmp_path / f"baseline-{run['error']}.png"), full_page=True)


@pytest.mark.parametrize("security_stack", ["idle"], indirect=True)
def test_baseline_untrusted_text_versions_and_fetch_failure(page, security_stack):
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    connect(page, security_stack)
    upload_example(page)
    expect(page.locator("#security-assessment-status")).to_contain_text("No model call")
    hostile = '<img src=x onerror="window.xss=1"><script>window.xss=2</script>'
    mode = "hostile"

    def intercept(route):
        response = route.fetch()
        data = response.json()
        if mode == "hostile":
            data["report"]["facts"][0]["claim"] = hostile * 8
        elif mode == "version":
            data["policy_version"] = 99
            data["report"]["facts"][0]["claim"] = "HIDDEN_UNKNOWN_VERSION"
        elif mode == "failure":
            route.fulfill(
                status=422, json={"detail": "Saved evidence cannot produce a bounded assessment"}
            )
            return
        route.fulfill(response=response, json=data)

    page.route(f"{security_stack}/security/cases/*/assessment", intercept)
    page.locator("#security-history button").click()
    expect(page.locator("#security-assessment-report")).to_contain_text(hostile)
    assert (
        page.locator("#security-assessment-report img, #security-assessment-report script").count()
        == 0
    )
    assert page.evaluate("window.xss") is None
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    mode = "version"
    page.locator("#security-history button").click()
    expect(page.locator("#security-assessment-status")).to_contain_text(
        "Unsupported factual assessment version"
    )
    expect(page.locator("#security-assessment-report")).to_be_empty()
    mode = "failure"
    page.locator("#security-history button").click()
    expect(page.locator("#security-assessment-status")).to_contain_text(
        "Saved evidence remains available"
    )
    expect(page.locator("#security-timeline details")).to_have_count(6)
    assert (
        page.request.get(
            f"{security_stack}/investigations", headers={"X-API-Key": "execution-test"}
        ).json()
        == []
    )
    assert errors == []


@pytest.mark.parametrize("security_stack", ["idle"], indirect=True)
@pytest.mark.parametrize(
    "field,value", [("Security API key", "changed"), ("API endpoint", "http://localhost:1")]
)
def test_baseline_response_after_connection_change_is_discarded(page, security_stack, field, value):
    connect(page, security_stack)
    upload_example(page)
    expect(page.locator("#security-assessment-status")).to_contain_text("No model call")

    def delayed(route):
        response = route.fetch()
        page.get_by_label(field, exact=True).fill(value)
        route.fulfill(response=response)

    page.route(f"{security_stack}/security/cases/*/assessment", delayed)
    with page.expect_event(
        "requestfailed", predicate=lambda request: request.url.endswith("/assessment")
    ) as pending:
        page.locator("#security-history button").click()
    assert pending.value.failure
    expect(page.locator("#security-detail")).to_be_hidden()
    expect(page.locator("#security-assessment-report")).to_be_empty()
    expect(page.locator("#security-assessment-evidence")).to_be_empty()


@pytest.mark.parametrize("security_stack", ["idle"], indirect=True)
def test_baseline_response_cannot_replace_another_case(page, security_stack):
    connect(page, security_stack)
    upload_example(page)
    expect(page.locator("#security-assessment-status")).to_contain_text("No model call")
    headers = {"X-API-Key": "security-test"}
    first = page.request.get(f"{security_stack}/security/cases", headers=headers).json()[0]["id"]
    body = json.loads((ROOT / "evals/typed-business-live/inputs.json").read_text())[2]["body"]
    second = page.request.post(
        f"{security_stack}/security/cases",
        headers={**headers, "Idempotency-Key": "other-case"},
        data=body,
    ).json()["id"]
    page.get_by_role("button", name="Reload", exact=True).click()
    expect(page.locator("#security-history button")).to_have_count(2)

    def delayed(route):
        response = route.fetch()
        page.locator("#security-history button").filter(has_text=second[:8]).click()
        expect(page.locator("#security-title")).to_have_text("0 linked requests")
        route.fulfill(response=response)

    url = f"{security_stack}/security/cases/{first}/assessment"
    page.route(url, delayed)
    with page.expect_response(url) as pending:
        page.locator("#security-history button").filter(has_text=first[:8]).click()
    pending.value.finished()
    expect(page.locator("#security-assessment-status")).to_contain_text("Reviewed 6 of 6")
    expect(page.locator("#security-assessment-report")).to_contain_text(
        "no authentication results were supplied"
    )
    expect(page.locator("#security-assessment-report")).not_to_contain_text(
        "Authentication service recorded success"
    )


@pytest.mark.parametrize("security_stack", ["invalid"], indirect=True)
def test_shared_history_links_to_baseline_outside_first_page_without_source_registry(
    page, security_stack
):
    connect(page, security_stack)
    upload_example(page)
    page.get_by_label("Investigation API key", exact=True).fill("execution-test")
    page.get_by_label("I authorize sharing this case with the model provider.", exact=True).check()
    page.get_by_role("button", name="Start or open investigation", exact=True).click()
    expect(page.locator("#security-run-status")).to_contain_text(
        "failed: invalid_report", timeout=15000
    )
    headers = {"X-API-Key": "security-test"}
    case_id = page.request.get(f"{security_stack}/security/cases", headers=headers).json()[0]["id"]
    body = {
        "scope": {
            "services": ["gateway", "authentication"],
            "start": "2026-09-01T10:00:00Z",
            "end": "2026-09-01T10:10:00Z",
        },
        "logs": {
            "edge": (ROOT / "examples/security-review/nginx.jsonl").read_text(),
            "auth": (ROOT / "examples/security-review/auth.jsonl").read_text(),
        },
    }
    for i in range(26):
        response = page.request.post(
            f"{security_stack}/security/cases",
            headers={**headers, "Idempotency-Key": f"later-{i}"},
            data=body,
        )
        assert response.status == 201
    assert case_id not in {
        row["id"]
        for row in page.request.get(f"{security_stack}/security/cases", headers=headers).json()
    }
    page.route(
        f"{security_stack}/investigations**",
        lambda route: route.continue_(
            headers={**route.request.headers, "X-API-Key": "execution-test"}
        ),
    )
    page.goto(f"{security_stack}/ui/index.html?api={security_stack}")
    page.get_by_role("button", name="Investigations", exact=True).click()
    page.locator("#inv-list .inv-item-btn").first.click()
    link = page.get_by_role("link", name="Open factual assessment", exact=True)
    expect(link).to_be_visible()
    assert "execution-test" not in link.get_attribute("href")
    assert "security-test" not in link.get_attribute("href")
    reads = []
    page.on(
        "request",
        lambda request: reads.append((request.url, request.headers.get("x-api-key")))
        if "/security/" in request.url
        else None,
    )
    link.click()
    expect(page.get_by_label("Security API key", exact=True)).to_have_value("")
    assert reads == []
    page.route(
        f"{security_stack}/security/sources",
        lambda route: route.fulfill(
            status=503, json={"detail": "Current source registry unavailable"}
        ),
    )
    page.get_by_label("Security API key", exact=True).fill("security-test")
    page.get_by_role("button", name="Connect", exact=True).click()
    expect(page.locator("#security-assessment-status")).to_contain_text("No model call")
    expect(page.locator("#security-provenance")).to_contain_text(case_id)
    expect(page.locator("#security-message")).to_contain_text("Saved reviews remain available")
    expect(page.locator("#security-import")).to_be_hidden()
    assert reads and all(key == "security-test" for _, key in reads)
    assert "execution-test" not in page.url and "security-test" not in page.url
