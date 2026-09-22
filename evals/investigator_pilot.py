"""One-shot investigator pilot: reserve before HTTP and capture before tool dispatch."""

import argparse
import asyncio
import contextlib
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime
from decimal import ROUND_CEILING, Decimal
from importlib.metadata import version
from pathlib import Path

import httpx
import run as runner
from app.config import settings
from app.investigation_shadow import review_events
from app.investigator import RecordingTools as RecordingTools
from app.investigator import execute_run
from app.models import Base, Investigation, InvestigationEvent, Log
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from validate import load_cases, unique_object

ROOT = runner.ROOT
MODEL = "gpt-4.1-mini-2025-04-14"
AUTHORIZATION = "investigator-initial-evidence-2026-09-22"
BASE = "7ea3ef2e5087a778ba49c91b3d0573850cfc111a"
CASE_FILE = "evals/investigator-security/cases.jsonl"
CASE_SHA = "5d720e4c8af1f7d634f700de5574a36a2d6ed10e6c42072c4cdeb999e0f1dcca"
CASE_IDS = [f"stage-{n:02}" for n in range(1, 11)]
PER_CASE = Decimal("0.10")
TOTAL = Decimal("2.00")
INPUT_PRICE = Decimal("0.40") / 1_000_000
OUTPUT_PRICE = Decimal("1.60") / 1_000_000
MAX_BODY = 131072
FILES = (
    "evals/investigator_pilot.py",
    "evals/tests/test_investigator_pilot.py",
    CASE_FILE,
    "evals/investigator-security/draft-freeze.json",
    "evals/run.py",
    "evals/validate.py",
    "docs/plans/initial-evidence-live-authorization.md",
    "docs/plans/investigator-pilot-pricing.md",
    "services/ingestion-service/requirements.txt",
    "services/ingestion-service/runbooks/operations.md",
) + tuple(
    str(path.relative_to(ROOT))
    for path in sorted((ROOT / "services/ingestion-service/app").rglob("*.py"))
)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def save(path, value):
    with path.open("xb") as handle:
        handle.write(canonical(value) + b"\n")
        handle.flush()
        os.fsync(handle.fileno())
    sync_directory(path.parent)


def candidate():
    hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in FILES}
    if hashes[CASE_FILE] != CASE_SHA:
        raise ValueError("authorized case bytes changed")
    if [case["case_id"] for case in load_cases(ROOT / CASE_FILE)] != CASE_IDS:
        raise ValueError("authorized case IDs changed")
    manifest = {
        "authorization": AUTHORIZATION,
        "production_base": BASE,
        "model": MODEL,
        "case_ids": CASE_IDS,
        "max_requests_per_case": 6,
        "max_requests": 60,
        "per_case_usd": str(PER_CASE),
        "total_usd": str(TOTAL),
        "worker_budget_usd": "0.025",
        "max_request_bytes": MAX_BODY,
        "max_output_tokens": 1024,
        "retries": 0,
        "review_status": "self_authored_pilot_independent_review_pending",
        "files": hashes,
        "pricing": {
            "input_per_million_usd": "0.40",
            "output_per_million_usd": "1.60",
            "cache_discount": False,
            "service_tier": "default",
            "checked_at": "2026-09-22",
            "source": "https://developers.openai.com/api/docs/models/gpt-4.1-mini",
        },
        "dependencies": {
            name: version(name)
            for name in ("openai", "httpx", "pydantic", "sqlalchemy", "aiosqlite")
        },
    }
    return manifest, digest(manifest)


def clean_worktree():
    return not subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT, text=True
    ).strip()


def shared_ledger():
    common = Path(
        subprocess.check_output(
            ["git", "rev-parse", "--git-common-dir"], cwd=ROOT, text=True
        ).strip()
    )
    return (ROOT / common).resolve() / AUTHORIZATION


class RecordingTransport(httpx.AsyncBaseTransport):
    """Only the native request body crosses this boundary; headers never reach disk."""

    def __init__(self, directory, inner, expected_digest):
        self.directory, self.inner, self.expected_digest = directory, inner, expected_digest
        self.case_id = None
        self.records = []
        self.fatal = None

    def reserve(self, raw):
        if len(raw) > MAX_BODY:
            raise ValueError("request body exceeds ceiling")
        body = json.loads(raw, object_pairs_hook=unique_object)
        if (
            set(body)
            != {
                "model",
                "messages",
                "tools",
                "response_format",
                "temperature",
                "store",
                "max_completion_tokens",
                "service_tier",
            }
            or body["service_tier"] != "default"
            or body["model"] != MODEL
            or body["max_completion_tokens"] != 1024
            or body["store"] is not False
            or body["temperature"] != 0
        ):
            raise ValueError("request outside authorized envelope")
        current = [record for record in self.records if record["case_id"] == self.case_id]
        amount = ((len(raw) + 4096) * INPUT_PRICE + 1024 * OUTPUT_PRICE).quantize(
            Decimal("0.00000001"), rounding=ROUND_CEILING
        )
        if (
            self.case_id not in CASE_IDS
            or len(current) >= 6
            or len(self.records) >= 60
            or sum((Decimal(r["reserved_usd"]) for r in current), Decimal(0)) + amount > PER_CASE
            or sum((Decimal(r["reserved_usd"]) for r in self.records), Decimal(0)) + amount > TOTAL
        ):
            raise ValueError("request or reservation allowance exhausted")
        record = {
            "request_number": len(self.records) + 1,
            "case_id": self.case_id,
            "reserved_usd": str(amount),
            "input_token_bound": len(raw) + 4096,
            "usage": None,
            "cost_upper_usd": None,
            "response_saved": False,
        }
        self.records.append(record)
        save(
            self.directory / f"request-{record['request_number']:03}.reservation.json",
            {
                **record,
                "status": "reserved_attempt_may_have_been_sent",
                "request_sha256": hashlib.sha256(raw).hexdigest(),
                "request": body,
            },
        )
        return record

    async def handle_async_request(self, request):
        before, response, record = len(self.records), None, None
        try:
            if (
                request.method != "POST"
                or str(request.url) != "https://api.openai.com/v1/chat/completions"
            ):
                raise ValueError("endpoint outside authorization")
            if candidate()[1] != self.expected_digest:
                raise ValueError("frozen candidate changed")
            body = json.loads(await request.aread(), object_pairs_hook=unique_object)
            if body.get("service_tier", "default") != "default":
                raise ValueError("nonstandard billing tier refused")
            body["service_tier"] = "default"
            raw_request = canonical(body)
            record = self.reserve(raw_request)
            request = httpx.Request(
                request.method,
                request.url,
                content=raw_request,
                headers={
                    key: value for key, value in request.headers.items() if key != "content-length"
                },
                extensions=request.extensions,
            )
            response = await self.inner.handle_async_request(request)
            record["http_status"] = response.status_code
            if response.status_code != 200:
                raise ValueError("provider returned non-success status; body not archived")
            chunks = bytearray()
            async for chunk in response.aiter_bytes():
                chunks.extend(chunk)
                if len(chunks) > 1_048_576:
                    raise ValueError("provider response exceeds ceiling")
            raw = bytes(chunks)
            credential = request.headers.get("authorization", "").removeprefix("Bearer ")
            if credential and credential.encode() in raw:
                raise ValueError("credential echo suppressed")
            data = json.loads(raw, object_pairs_hook=unique_object)
            if credential and credential.encode() in canonical(data):
                raise ValueError("escaped credential echo suppressed")
            record["response"] = data
            usage = data.get("usage")
            if not isinstance(usage, dict) or any(
                type(usage.get(key)) is not int or usage[key] < 0
                for key in ("prompt_tokens", "completion_tokens", "total_tokens")
            ):
                raise ValueError("unknown or invalid usage")
            if usage["total_tokens"] != usage["prompt_tokens"] + usage["completion_tokens"]:
                raise ValueError("inconsistent usage")
            details = usage.get("prompt_tokens_details")
            if details is not None:
                if not isinstance(details, dict):
                    raise ValueError("invalid cached usage")
                cached = details.get("cached_tokens")
                if cached is not None and (
                    type(cached) is not int or not 0 <= cached <= usage["prompt_tokens"]
                ):
                    raise ValueError("invalid cached usage")
            record["usage"] = usage
            cost = INPUT_PRICE * usage["prompt_tokens"] + OUTPUT_PRICE * usage["completion_tokens"]
            record["cost_upper_usd"] = str(cost)
            if data.get("model") != MODEL or data.get("service_tier") != "default":
                raise ValueError("returned model or billing tier mismatch")
            if (
                usage["prompt_tokens"] > record["input_token_bound"]
                or usage["completion_tokens"] > 1024
                or cost > Decimal(record["reserved_usd"])
            ):
                raise ValueError("returned usage exceeds reservation")
            save(
                self.directory / f"request-{record['request_number']:03}.response.json",
                {**record, "response_saved": True, "status": "received"},
            )
            record["response_saved"] = True
            if candidate()[1] != self.expected_digest:
                raise ValueError("candidate changed while the provider request was pending")
            return httpx.Response(
                200,
                content=raw,
                headers={
                    key: value
                    for key, value in response.headers.items()
                    if key not in {"content-encoding", "content-length", "transfer-encoding"}
                },
            )
        except BaseException as exc:
            self.fatal = type(exc).__name__
            if len(self.records) > before:
                record = self.records[-1]
                with contextlib.suppress(OSError):
                    save(
                        self.directory / f"request-{record['request_number']:03}.failure.json",
                        {
                            **record,
                            "error_type": type(exc).__name__,
                            "status": "failed_or_interrupted",
                        },
                    )
            raise
        finally:
            if response is not None:
                await response.aclose()

    async def aclose(self):
        await self.inner.aclose()


async def execute_case(directory, case, client):
    engine = create_async_engine(f"sqlite+aiosqlite:///{directory / (case['case_id'] + '.db')}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as session:
            mapping = {}
            for row in case["logs"]:
                log = Log(
                    service=row["service"],
                    level=row["level"],
                    message=row["message"],
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                )
                session.add(log)
                await session.flush()
                mapping[row["evidence_id"]] = f"log:{log.id}"
            session.add(
                Log(
                    service="inventory",
                    level="ERROR",
                    message="STAGING_OUTSIDE_SCOPE_CANARY",
                    timestamp=datetime.fromisoformat(case["scope"]["start"]),
                )
            )
            run = Investigation(
                question=case["question"],
                system="C",
                scope=case["scope"],
                request_sha256=digest(case),
                status="running",
            )
            session.add(run)
            await session.commit()
            identity = run.id
        await execute_run(factory, identity, client)
        async with factory() as session:
            run = await session.get(Investigation, identity)
            rows = (
                await session.scalars(
                    select(InvestigationEvent)
                    .where(InvestigationEvent.investigation_id == identity)
                    .order_by(InvestigationEvent.sequence)
                )
            ).all()
            events = [
                {"sequence": row.sequence, "kind": row.kind, "payload": row.payload} for row in rows
            ]
            result = {
                "case_id": case["case_id"],
                "fixture_to_database_ids": mapping,
                "status": run.status,
                "error": run.error,
                "report": run.report,
                "usage": run.usage,
                "estimated_cost_usd": run.estimated_cost_usd,
                "elapsed_ms": run.elapsed_ms,
                "events": events,
                "review": review_events(case["scope"], events),
            }
            save(directory / f"{case['case_id']}.json", result)
            return result
    finally:
        await engine.dispose()


async def run_batch(directory, expected_digest, *, key, transport=None, allow_live=False):
    scripted = isinstance(transport, httpx.MockTransport)
    if not key or any(not 32 < ord(character) < 127 for character in key):
        raise ValueError("credential must be nonempty visible ASCII without spaces")
    if not scripted:
        if not clean_worktree():
            raise ValueError("live execution requires a clean committed runner")
        if not allow_live or transport is not None or directory != shared_ledger():
            raise ValueError("live execution requires explicit authorization and the shared ledger")
    manifest, actual_digest = candidate()
    if expected_digest != actual_digest:
        raise ValueError("candidate differs from explicit frozen digest")
    if settings.prometheus_url:
        raise ValueError("pilot requires an unconfigured metrics source")
    if not scripted:
        subprocess.run(
            [
                "git",
                "diff",
                "--quiet",
                BASE,
                "--",
                "services/ingestion-service/app",
                "services/ingestion-service/runbooks",
            ],
            cwd=ROOT,
            check=True,
        )
    directory.mkdir(mode=0o700)
    sync_directory(directory.parent)
    save(
        directory / "manifest.json",
        {
            **manifest,
            "candidate_sha256": actual_digest,
            "execution_mode": "scripted" if scripted else "live",
            "code_revision": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
        },
    )
    for name, expected_hash in manifest["files"].items():
        target = directory / "candidate" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        data = (ROOT / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected_hash:
            raise ValueError("source changed while snapshotting")
        with target.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        sync_directory(target.parent)
    recorder = RecordingTransport(
        directory,
        transport or httpx.AsyncHTTPTransport(retries=0, trust_env=False),
        expected_digest,
    )
    statuses = {identity: "not_run" for identity in CASE_IDS}
    async with AsyncOpenAI(
        api_key=key,
        base_url="https://api.openai.com/v1",
        max_retries=0,
        http_client=httpx.AsyncClient(
            transport=recorder, trust_env=False, follow_redirects=False, timeout=30
        ),
    ) as client:
        for case in load_cases(ROOT / CASE_FILE):
            recorder.case_id = case["case_id"]
            try:
                outcome = await execute_case(directory, case, client)
            except Exception as exc:
                recorder.fatal = type(exc).__name__
                statuses[case["case_id"]] = "interrupted"
                break
            statuses[case["case_id"]] = outcome["status"]
            if (
                outcome["error"] in {"worker_error", "deadline_exceeded", "cancelled"}
                or outcome["status"] == "cancelled"
            ):
                recorder.fatal = recorder.fatal or "worker_interruption"
            if recorder.fatal:
                break
    summary = {
        "mode": "scripted" if scripted else "live",
        "reserved_attempts": len(recorder.records),
        "reserved_usd": str(
            sum((Decimal(row["reserved_usd"]) for row in recorder.records), Decimal(0))
        ),
        "known_cost_upper_usd": str(
            sum(
                (
                    Decimal(row["cost_upper_usd"])
                    for row in recorder.records
                    if row["cost_upper_usd"] is not None
                ),
                Decimal(0),
            )
        ),
        "usage_complete": all(
            row["response_saved"] and row["usage"] is not None for row in recorder.records
        ),
        "fatal": recorder.fatal,
        "all_cases_attempted": all(status != "not_run" for status in statuses.values()),
        "cases": statuses,
    }
    save(directory / "summary.json", summary)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog="Example preview: python evals/investigator_pilot.py. Live use additionally requires --allow-live --candidate-sha256 DIGEST after all gates pass.",
    )
    parser.add_argument("--allow-live", action="store_true")
    parser.add_argument("--candidate-sha256")
    args = parser.parse_args(argv)
    try:
        manifest, sha = candidate()
        if not args.allow_live:
            print(json.dumps({"mode": "dry_run", "candidate_sha256": sha, **manifest}, indent=2))
            return 0
        result = asyncio.run(
            run_batch(
                shared_ledger(),
                args.candidate_sha256,
                key=os.environ.get("OPENAI_API_KEY", ""),
                allow_live=True,
            )
        )
        print(json.dumps(result, indent=2))
        return 0 if result["all_cases_attempted"] and not result["fatal"] else 1
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"Pilot refused or interrupted: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
