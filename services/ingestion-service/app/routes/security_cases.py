"""Save deterministic security reviews atomically; this router never queues model work."""

import hashlib
import json
import re
import secrets
from datetime import UTC
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from sqlalchemy import select, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_session
from ..models import SecurityCase, SecurityEvidence
from ..security_adapters import Registry, analyze_import
from ..security_evidence import MAX_BYTES, decode_json

MAX_WIRE_BYTES = 2 * MAX_BYTES


def fail(status, detail):
    raise HTTPException(status, detail, headers={"Cache-Control": "no-store"})


async def require_security_key(x_api_key: str | None = Header(default=None)):
    if not settings.security_api_key:
        fail(503, "Security review disabled; configure SECURITY_API_KEY")
    if not secrets.compare_digest((x_api_key or "").encode(), settings.security_api_key.encode()):
        fail(401, "Invalid or missing security key")


router = APIRouter(
    prefix="/security", tags=["security review"], dependencies=[Depends(require_security_key)]
)


def load_registry() -> Registry:
    try:
        path = Path(settings.security_sources_path)
        if not path.is_file():
            raise ValueError("not a file")
        with path.open("rb") as stream:
            raw = stream.read(16385)
        if len(raw) > 16384:
            raise ValueError("too large")
        return Registry.model_validate(decode_json(raw))
    except (OSError, ValueError):
        fail(503, "Security sources unavailable; configure SECURITY_SOURCES_PATH")


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def public(case):
    return {
        "id": case.id,
        "created_at": case.created_at.replace(tzinfo=UTC),
        "request_sha256": case.request_sha256,
        "source_snapshot": case.source_snapshot,
        "input_hashes": case.input_hashes,
        "report": case.report,
    }


@router.get("/sources")
async def sources(response: Response):
    response.headers["Cache-Control"] = "no-store"
    return {
        **load_registry().model_dump(mode="json"),
        "max_bytes": MAX_BYTES,
        "max_wire_bytes": MAX_WIRE_BYTES,
    }


async def save_case(session: AsyncSession, owner: dict, body: dict, key: str):
    """One transaction owns all evidence and the case; database uniqueness arbitrates races."""
    try:
        report = analyze_import(owner, body)
    except (ValueError, OverflowError):
        fail(422, "Invalid source records, scope or import limits")
    fingerprint = digest({"owner": owner, "body": body})
    existing = await session.scalar(select(SecurityCase).where(SecurityCase.idempotency_key == key))
    if existing is not None:
        if existing.request_sha256 != fingerprint:
            fail(409, "Idempotency key conflicts with content or source configuration")
        return existing, False
    source_map = {s["source_id"]: s for s in owner["sources"]}
    records = []
    for event in report["timeline"]:
        source_id, evidence_id = event["evidence"]
        content = {"source": source_map[source_id], "event": event}
        records.append(
            {
                "source_id": source_id,
                "evidence_id": evidence_id,
                "content_sha256": digest(content),
                "content": content,
            }
        )
    dialect = session.bind.dialect.name
    if dialect not in {"sqlite", "postgresql"}:
        fail(503, "Security persistence requires SQLite or PostgreSQL")
    insert = sqlite_insert if dialect == "sqlite" else pg_insert
    records.sort(key=lambda r: (r["source_id"], r["evidence_id"]))
    for offset in range(0, len(records), 200):
        batch = records[offset : offset + 200]
        await session.execute(
            insert(SecurityEvidence)
            .values(batch)
            .on_conflict_do_nothing(index_elements=["source_id", "evidence_id"])
        )
        expected = {(r["source_id"], r["evidence_id"]): r["content_sha256"] for r in batch}
        stored = await session.scalars(
            select(SecurityEvidence).where(
                tuple_(SecurityEvidence.source_id, SecurityEvidence.evidence_id).in_(list(expected))
            )
        )
        if any(
            record.content_sha256 != expected[record.source_id, record.evidence_id]
            for record in stored
        ):
            await session.rollback()
            fail(
                409, "Existing source/event identity has different evidence or source configuration"
            )
    case = SecurityCase(
        idempotency_key=key,
        request_sha256=fingerprint,
        source_snapshot=owner,
        input_hashes={
            name: hashlib.sha256(raw.encode()).hexdigest() for name, raw in body["logs"].items()
        },
        report=report,
    )
    session.add(case)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = await session.scalar(
            select(SecurityCase).where(SecurityCase.idempotency_key == key)
        )
        if existing is None or existing.request_sha256 != fingerprint:
            fail(409, "Idempotency key conflicts with content or source configuration")
        return existing, False
    await session.refresh(case)
    return case, True


@router.post("/cases")
async def import_case(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    idempotency_key: str | None = Header(default=None),
):
    if not idempotency_key or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", idempotency_key):
        fail(422, "Supply an Idempotency-Key of 1 to 128 ASCII token characters")
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > MAX_WIRE_BYTES:
            fail(413, "Security import exceeds 2 MiB wire limit")
        raw.extend(chunk)
    owner = load_registry().model_dump(mode="json")
    try:
        body = decode_json(bytes(raw))
    except (ValueError, OverflowError):
        fail(422, "Invalid source records, scope or import limits")
    case, created = await save_case(session, owner, body, idempotency_key)
    response.status_code = 201 if created else 200
    response.headers["Cache-Control"] = "no-store"
    return public(case)


@router.get("/cases")
async def list_cases(
    response: Response,
    session: AsyncSession = Depends(get_session),
    limit: int = 25,
    offset: int = 0,
):
    if not 1 <= limit <= 50 or offset < 0:
        fail(422, "Invalid pagination")
    response.headers["Cache-Control"] = "no-store"
    rows = await session.execute(
        select(
            SecurityCase.id,
            SecurityCase.created_at,
            SecurityCase.report["scope"].label("scope"),
            SecurityCase.report["input_records"].as_integer().label("input_records"),
        )
        .order_by(SecurityCase.created_at.desc(), SecurityCase.id)
        .limit(limit)
        .offset(offset)
    )
    return [{**row._mapping, "created_at": row.created_at.replace(tzinfo=UTC)} for row in rows]


@router.get("/cases/{case_id}")
async def get_case(case_id: str, response: Response, session: AsyncSession = Depends(get_session)):
    case = await session.get(SecurityCase, case_id)
    if case is None:
        fail(404, "Unknown security review")
    response.headers["Cache-Control"] = "no-store"
    return public(case)
