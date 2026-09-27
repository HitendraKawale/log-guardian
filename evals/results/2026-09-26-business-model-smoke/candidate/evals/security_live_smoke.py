"""One approved security-case batch reuses the tested reservation/capture transport."""

import argparse
import asyncio
import contextlib
import hashlib
import json
import os
import secrets
import subprocess
from decimal import Decimal
from importlib.metadata import version
from pathlib import Path

import httpx
import investigator_pilot as p
from app.database import get_session
from app.investigator import run_once
from app.main import app
from app.models import Base
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

BASE = "3841bf9548b2b76f906cbaa61d34378417a70bbc"
AUTHORIZATION = "security-business-smoke-2026-09-26-02"
INPUTS = p.ROOT / "evals/business-model-smoke/inputs.json"
CASE_IDS = [f"smoke-{n:02}" for n in range(1, 5)]


def manifest():
    subprocess.run(
        ["git", "diff", "--quiet", BASE, "--", "services", "frontend"], cwd=p.ROOT, check=True
    )
    files = [
        Path(__file__),
        INPUTS,
        p.ROOT / "evals/investigator_pilot.py",
        p.ROOT / "evals/run.py",
        p.ROOT / "evals/validate.py",
        p.ROOT / "evals/tests/test_security_live_smoke.py",
        p.ROOT / "examples/security-review/sources.json",
        p.ROOT / "docs/plans/business-model-smoke-authorization.md",
        p.ROOT / "evals/security-live-smoke/pricing.txt",
        p.ROOT / "services/ingestion-service/requirements.txt",
    ] + sorted((p.ROOT / "services/ingestion-service/app").rglob("*.py"))
    value = {
        "authorization": AUTHORIZATION,
        "production_revision": BASE,
        "model": p.MODEL,
        "case_ids": CASE_IDS,
        "per_case_usd": "0.025",
        "total_usd": "0.10",
        "max_requests": 24,
        "max_requests_per_case": 6,
        "max_output_tokens": 1024,
        "retries": 0,
        "files": {
            str(f.relative_to(p.ROOT)): hashlib.sha256(f.read_bytes()).hexdigest() for f in files
        },
        "dependencies": {
            name: version(name)
            for name in ("openai", "httpx", "pydantic", "sqlalchemy", "aiosqlite")
        },
    }
    return value, p.digest(value)


@contextlib.contextmanager
def configured():
    """Separate allowance and ledger; never invoke a historical batch's run_batch."""
    values = {
        "AUTHORIZATION": AUTHORIZATION,
        "CASE_IDS": CASE_IDS,
        "MAX_REQUESTS": 24,
        "PER_CASE": Decimal("0.025"),
        "TOTAL": Decimal("0.10"),
        "candidate": manifest,
    }
    old = {name: getattr(p, name) for name in values}
    try:
        for name, value in values.items():
            setattr(p, name, value)
        yield
    finally:
        for name, value in old.items():
            setattr(p, name, value)


def ledger():
    common = subprocess.check_output(
        ["git", "rev-parse", "--git-common-dir"], cwd=p.ROOT, text=True
    ).strip()
    return (p.ROOT / common).resolve() / AUTHORIZATION


async def execute_case(directory, case, provider):
    engine = create_async_engine(f"sqlite+aiosqlite:///{directory / (case['case_id'] + '.db')}")
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def sessions():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = sessions
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://smoke.local"
        ) as api:
            review = {"X-API-Key": p.settings.security_api_key, "Idempotency-Key": case["case_id"]}
            execution = {"X-API-Key": p.settings.investigation_api_key}
            response = await api.post("/security/cases", json=case["body"], headers=review)
            assert response.status_code == 201, response.status_code
            saved = response.json()
            assert (await api.get("/investigations", headers=execution)).json() == []
            route = f"/investigations/from-security-case/{saved['id']}"
            assert (await api.post(route, headers=review)).status_code == 401
            queued = await api.post(route, headers=execution)
            assert queued.status_code == 201
            run_id = queued.json()["id"]
            assert await run_once(factory, provider, AUTHORIZATION)
            run = (await api.get(f"/investigations/{run_id}", headers=execution)).json()
            events = (await api.get(f"/investigations/{run_id}/events", headers=execution)).json()
            retry = await api.post(route, headers=execution)
            assert retry.status_code == 200 and retry.json()["id"] == run_id
            assert len((await api.get("/investigations", headers=execution)).json()) == 1
            result = {"case_id": case["case_id"], "saved_case": saved, "run": run, "events": events}
            p.save(directory / f"{case['case_id']}.json", result)
            return result
    finally:
        app.dependency_overrides.pop(get_session, None)
        await engine.dispose()


async def run_batch(output, expected, *, transport=None, key=None, live=False):
    mocked = type(transport) is httpx.MockTransport
    if not mocked and (
        not live or transport is not None or output != ledger() or not p.clean_worktree()
    ):
        raise ValueError(
            "live run requires clean source, explicit approval and its exclusive ledger"
        )
    current, digest = manifest()
    if digest != expected:
        raise ValueError("frozen candidate mismatch")
    if not mocked and (not key or any(not 32 < ord(c) < 127 for c in key)):
        raise ValueError("missing or invalid credential")
    cases = json.loads(INPUTS.read_bytes())
    if [case["case_id"] for case in cases] != CASE_IDS:
        raise ValueError("case identity mismatch")
    output.mkdir(mode=0o700)
    p.sync_directory(output.parent)
    p.save(
        output / "manifest.json",
        {**current, "candidate_sha256": digest, "mode": "mock" if mocked else "live"},
    )
    for name, checksum in current["files"].items():
        raw = (p.ROOT / name).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == checksum
        target = output / "candidate" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    old = {
        name: getattr(p.settings, name)
        for name in (
            "security_api_key",
            "investigation_api_key",
            "security_sources_path",
            "prometheus_url",
        )
    }
    p.settings.security_api_key = secrets.token_urlsafe(32)
    p.settings.investigation_api_key = secrets.token_urlsafe(32)
    p.settings.security_sources_path = str(p.ROOT / "examples/security-review/sources.json")
    p.settings.prometheus_url = ""
    statuses = {case: "not_run" for case in CASE_IDS}
    with configured():
        recorder = p.RecordingTransport(
            output,
            transport if mocked else httpx.AsyncHTTPTransport(retries=0, trust_env=False),
            expected,
        )
        try:
            async with AsyncOpenAI(
                api_key="mock-only" if mocked else key,
                base_url="https://api.openai.com/v1",
                max_retries=0,
                http_client=httpx.AsyncClient(
                    transport=recorder, trust_env=False, follow_redirects=False, timeout=120
                ),
            ) as client:
                for case in cases:
                    recorder.case_id = case["case_id"]
                    try:
                        result = await execute_case(output, case, client)
                        run = result["run"]
                        statuses[case["case_id"]] = run["status"]
                        if (
                            run["error"]
                            in {"worker_error", "deadline_exceeded", "cancelled", "unknown_usage"}
                            or run["status"] == "cancelled"
                        ):
                            recorder.fatal = recorder.fatal or "worker_interruption"
                    except BaseException as exc:
                        recorder.fatal = type(exc).__name__
                        statuses[case["case_id"]] = "interrupted"
                    if recorder.fatal:
                        break
        finally:
            for name, value in old.items():
                setattr(p.settings, name, value)
            summary = {
                "mode": "mock" if mocked else "live",
                "cases": statuses,
                "fatal": recorder.fatal,
                "attempts": len(recorder.records),
                "reserved_usd": str(
                    sum((Decimal(r["reserved_usd"]) for r in recorder.records), Decimal(0))
                ),
                "known_cost_upper_usd": str(
                    sum(
                        (
                            Decimal(r["cost_upper_usd"])
                            for r in recorder.records
                            if r["cost_upper_usd"] is not None
                        ),
                        Decimal(0),
                    )
                ),
                "usage_complete": all(
                    r["response_saved"] and r["usage"] is not None for r in recorder.records
                ),
                "allowance_closed": True,
            }
            p.save(output / "summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--candidate-sha256")
    args = parser.parse_args()
    value, digest = manifest()
    if not args.live:
        print(json.dumps({"candidate_sha256": digest, **value}, indent=2))
        return
    result = asyncio.run(
        run_batch(ledger(), args.candidate_sha256, key=os.environ.get("OPENAI_API_KEY"), live=True)
    )
    print(json.dumps(result, indent=2))
    if result["fatal"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
