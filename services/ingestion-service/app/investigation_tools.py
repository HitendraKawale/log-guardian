"""Read-only evidence tools with one contract for replay and database sources.

Paths and database sessions are owner-supplied construction parameters, never
model tool arguments. Results contain redacted snapshots, not grading labels.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import UTC
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from .investigation_schemas import (
    EvidenceBatch,
    EvidenceItem,
    InvestigationScope,
    LogQuery,
    ReplayLog,
    RunbookQuery,
)
from .models import Log

MAX_RESULT_BYTES = 16_384
RUNBOOK_PATH = Path(__file__).resolve().parents[1] / "runbooks" / "operations.md"
_BEARER = re.compile(r"\bBearer\s+[^\s,\"'<>]+", re.IGNORECASE)
_CREDENTIAL = re.compile(
    r"""(["']?\b(?:password|api[_-]?key|token|secret|authorization)\b["']?\s*[:=]\s*)"""
    r"""(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[^\s,;{}]+)""",
    re.IGNORECASE,
)
_USERINFO = re.compile(r"([a-z][a-z0-9+.-]*://)[^/\s:@]+:[^/@\s]+@", re.IGNORECASE)


def redact(value):
    """Remove known credential forms; this is not general-purpose PII detection."""
    if isinstance(value, str):
        value = _BEARER.sub("Bearer [REDACTED]", value)
        value = _CREDENTIAL.sub(lambda m: m[1] + '"[REDACTED]"', value)
        return _USERINFO.sub(r"\1[REDACTED]@", value)
    if isinstance(value, dict):
        return {key: redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def bounded_batch(source, items, *, scope=None, truncated=False, version=None):
    items = [item.model_copy(update={"content": redact(item.content)}) for item in items]
    if version is None:
        snapshot = json.dumps([i.model_dump(mode="json") for i in items], sort_keys=True)
        version = hashlib.sha256(snapshot.encode()).hexdigest()
    batch = EvidenceBatch(
        source=source,
        version=version,
        truncated=truncated,
        start=scope.start if scope else None,
        end=scope.end if scope else None,
    )
    # ponytail: reserialize at most 50 items; use incremental byte counts if that bound grows.
    for item in items:
        batch.items.append(item)
        if len(batch.model_dump_json().encode("utf-8")) > MAX_RESULT_BYTES:
            batch.items.pop()
            batch.truncated = True
    return batch


class EvidenceTools:
    def __init__(
        self,
        scope: InvestigationScope,
        *,
        records=None,
        session: AsyncSession | None = None,
        runbook_path: Path = RUNBOOK_PATH,
    ):
        if (records is None) == (session is None):
            raise ValueError("Provide exactly one replay or database source")
        self.scope = scope
        self.session = session
        self.records = (
            tuple(ReplayLog.model_validate(row) for row in records) if records is not None else None
        )
        if self.records is not None and len({r.evidence_id for r in self.records}) != len(
            self.records
        ):
            raise ValueError("Duplicate replay evidence IDs")
        self.source = "replay" if self.records is not None else "database"
        self.runbook_path = runbook_path

    def _request(self, schema, arguments, source):
        try:
            query = schema.model_validate(arguments)
        except ValidationError:
            return EvidenceBatch(source=source, error="invalid_arguments")
        if isinstance(query, InvestigationScope) and (
            not set(query.services) <= set(self.scope.services)
            or query.start < self.scope.start
            or query.end > self.scope.end
        ):
            return EvidenceBatch(source=source, error="scope_violation")
        return query

    def _where(self, query):
        return (
            Log.service.in_(query.services),
            Log.timestamp >= query.start,
            Log.timestamp <= query.end,
        )

    def _replay_matches(self, query):
        return [
            row
            for row in self.records
            if row.service in query.services and query.start <= row.timestamp <= query.end
        ]

    async def query_logs(self, **arguments) -> EvidenceBatch:
        query = self._request(LogQuery, arguments, self.source)
        if isinstance(query, EvidenceBatch):
            return query
        try:
            if self.records is not None:
                records = self._replay_matches(query)
                if query.text is not None:
                    records = [row for row in records if query.text in row.message]
                records.sort(key=lambda r: (r.timestamp, r.evidence_id), reverse=True)
                items = [
                    EvidenceItem(
                        evidence_id=row.evidence_id,
                        kind="log",
                        content=row.model_dump(mode="json", exclude={"evidence_id"}),
                    )
                    for row in records[: query.limit + 1]
                ]
            else:
                stmt = select(Log).where(*self._where(query))
                if query.text is not None:
                    # Native substring functions keep '%' and '_' literal and preserve case.
                    position = (
                        func.instr if self.session.bind.dialect.name == "sqlite" else func.strpos
                    )
                    stmt = stmt.where(position(Log.message, query.text) > 0)
                result = await self.session.execute(
                    stmt.order_by(Log.timestamp.desc(), Log.id.desc()).limit(query.limit + 1)
                )
                items = []
                for row in result.scalars():
                    # SQLite returns naive UTC values; ingestion normalizes before storage.
                    stamp = (
                        row.timestamp.replace(tzinfo=UTC)
                        if row.timestamp.tzinfo is None
                        else row.timestamp.astimezone(UTC)
                    )
                    items.append(
                        EvidenceItem(
                            evidence_id=f"log:{row.id}",
                            kind="log",
                            content={
                                "service": row.service,
                                "level": row.level,
                                "message": row.message,
                                "timestamp": stamp.isoformat().replace("+00:00", "Z"),
                            },
                        )
                    )
        except SQLAlchemyError:
            return EvidenceBatch(source=self.source, error="source_unavailable")
        return bounded_batch(
            self.source, items[: query.limit], scope=query, truncated=len(items) > query.limit
        )

    async def summarize_logs(self, **arguments) -> EvidenceBatch:
        query = self._request(InvestigationScope, arguments, self.source)
        if isinstance(query, EvidenceBatch):
            return query
        try:
            if self.records is not None:
                counts = Counter(
                    (row.service, row.level.value) for row in self._replay_matches(query)
                )
            else:
                result = await self.session.execute(
                    select(Log.service, Log.level, func.count())
                    .where(*self._where(query))
                    .group_by(Log.service, Log.level)
                )
                counts = {(service, level): count for service, level, count in result}
        except SQLAlchemyError:
            return EvidenceBatch(source=self.source, error="source_unavailable")
        content = {
            "total": sum(counts.values()),
            "groups": [
                {"service": service, "level": level, "count": count}
                for (service, level), count in sorted(counts.items())
            ],
        }
        snapshot = json.dumps(redact(content), sort_keys=True) + query.model_dump_json()
        identity = hashlib.sha256(snapshot.encode()).hexdigest()
        item = EvidenceItem(evidence_id=f"summary:{identity}", kind="summary", content=content)
        return bounded_batch(self.source, [item], scope=query)

    async def search_runbooks(self, **arguments) -> EvidenceBatch:
        query = self._request(RunbookQuery, arguments, "runbooks")
        if isinstance(query, EvidenceBatch):
            return query
        try:
            document = redact(self.runbook_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError):
            return EvidenceBatch(source="runbooks", error="source_unavailable")
        version = hashlib.sha256(document.encode()).hexdigest()
        sections = re.split(r"^## ([a-z0-9-]+): (.+)$", document, flags=re.MULTILINE)
        if len(sections) == 1:
            return EvidenceBatch(source="runbooks", error="source_unavailable")
        words = set(re.findall(r"\w+", query.query.lower()))
        ranked = []
        seen = set()
        for index in range(1, len(sections), 3):
            section_id, title, body = sections[index : index + 3]
            if section_id in seen:
                return EvidenceBatch(source="runbooks", error="source_unavailable")
            seen.add(section_id)
            score = len(words & set(re.findall(r"\w+", (title + " " + body).lower())))
            if score:
                item = EvidenceItem(
                    evidence_id=f"runbook:{section_id}",
                    kind="runbook",
                    content={"title": title, "body": body.strip()},
                )
                ranked.append((score, section_id, item))
        ranked.sort(key=lambda row: (-row[0], row[1]))
        return bounded_batch(
            "runbooks",
            [r[2] for r in ranked[: query.limit]],
            truncated=len(ranked) > query.limit,
            version=version,
        )
