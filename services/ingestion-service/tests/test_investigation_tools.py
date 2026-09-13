"""Replay and database tools must expose the same bounded, read-only evidence."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from app.investigation_schemas import InvestigationScope
from app.investigation_tools import EvidenceTools
from app.models import Log
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

START = datetime(2026, 1, 1, 10, tzinfo=UTC)
SCOPE = {"services": ["checkout", "inventory"], "start": START, "end": START + timedelta(hours=1)}


def rows(count=60):
    return [
        {
            "evidence_id": f"fixture:{index:03d}",
            "service": "checkout" if index % 2 == 0 else "inventory",
            "level": "ERROR" if index % 2 == 0 else "INFO",
            "message": f"request {index} completed",
            "timestamp": START + timedelta(seconds=index),
        }
        for index in range(count)
    ]


@pytest.fixture(params=["replay", "database"])
async def tools(request, engine):
    records = rows()
    records[0]["message"] = 'Authorization: Bearer fixture-token password="two words"'
    records[1]["message"] = "literal 50%_done; API_KEY=fixture-key"
    records[2]["message"] = "postgresql://user:fixture-password@db.local/test"
    records[3]["message"] = "Unicode: 東京; request safe"
    records += [{**records[-1], "evidence_id": "outside:1", "service": "other"}]
    records += [
        {**records[-2], "evidence_id": "outside:2", "timestamp": START - timedelta(seconds=1)}
    ]
    scope = InvestigationScope(**SCOPE)
    if request.param == "replay":
        yield EvidenceTools(scope, records=records)
    else:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            session.add_all(
                [Log(**{k: v for k, v in r.items() if k != "evidence_id"}) for r in records]
            )
            await session.commit()
            yield EvidenceTools(scope, session=session)
            assert await session.scalar(select(func.count()).select_from(Log)) == 62


async def test_query_is_scoped_ordered_bounded_and_repeatable(tools):
    first = await tools.query_logs(**SCOPE)
    second = await tools.query_logs(**SCOPE)
    assert first == second
    assert first.error is None and first.truncated
    assert len(first.items) == 50
    assert first.items[0].content["message"] == "request 59 completed"
    assert first.items[-1].content["message"] == "request 10 completed"
    assert len(first.model_dump_json().encode()) <= 16_384


async def test_summary_counts_full_scope_not_first_page(tools):
    result = await tools.summarize_logs(**SCOPE)
    assert result.error is None and not result.truncated
    content = result.items[0].content
    assert content["total"] == 60
    assert content["groups"] == [
        {"service": "checkout", "level": "ERROR", "count": 30},
        {"service": "inventory", "level": "INFO", "count": 30},
    ]


@pytest.mark.parametrize(
    "patch",
    [
        {"services": ["other"]},
        {"start": START - timedelta(seconds=1)},
        {"end": START + timedelta(hours=2)},
        {"services": []},
        {"services": ["checkout", "checkout"]},
        {"start": "2026-01-01T10:00:00"},
        {"start": str(int(START.timestamp()))},
        {"end": START - timedelta(seconds=1)},
        {"path": "../../evals/labels.jsonl"},
    ],
)
async def test_rejects_invalid_or_expanded_scope(tools, patch):
    for method in (tools.query_logs, tools.summarize_logs):
        result = await method(**{**SCOPE, **patch})
        assert result.error in {"invalid_arguments", "scope_violation"}
        assert result.items == []


@pytest.mark.parametrize("limit", [0, 51, True, "5"])
async def test_rejects_invalid_limits(tools, limit):
    result = await tools.query_logs(**SCOPE, limit=limit)
    assert result.error == "invalid_arguments"


async def test_literal_search_does_not_interpret_wildcards_or_sql(tools):
    result = await tools.query_logs(**SCOPE, text="50%_done")
    assert len(result.items) == 1
    assert "fixture-key" not in result.model_dump_json()
    empty = await tools.query_logs(**SCOPE, text="' OR 1=1 --")
    assert empty.error is None and empty.items == [] and not empty.truncated
    unicode_result = await tools.query_logs(**SCOPE, text="東京")
    assert len(unicode_result.items) == 1


async def test_credentials_are_redacted_before_serialization(tools):
    result = await tools.query_logs(**{**SCOPE, "end": START + timedelta(seconds=3)})
    serialized = result.model_dump_json()
    for secret in ("fixture-token", "two words", "fixture-key", "fixture-password"):
        assert secret not in serialized
    assert "[REDACTED]" in serialized


async def test_offsets_normalize_and_endpoints_are_inclusive(tools):
    result = await tools.query_logs(
        services=["checkout"],
        start="2026-01-01T15:30:00+05:30",
        end="2026-01-01T15:30:02+05:30",
    )
    assert len(result.items) == 2
    assert result.start == START
    assert result.end == START + timedelta(seconds=2)


async def test_large_multibyte_log_is_omitted_not_partially_quoted():
    records = rows(2)
    records[1]["message"] = "🔥" * 20_000
    tool = EvidenceTools(InvestigationScope(**SCOPE), records=records)
    result = await tool.query_logs(**SCOPE)
    assert result.truncated
    assert len(result.model_dump_json().encode()) <= 16_384
    assert [i.content["message"] for i in result.items] == ["request 0 completed"]


async def test_replay_takes_a_snapshot_and_refuses_label_fields():
    records = rows(1)
    tool = EvidenceTools(InvestigationScope(**SCOPE), records=records)
    records[0]["message"] = "changed after construction"
    assert (await tool.query_logs(**SCOPE)).items[0].content["message"] == "request 0 completed"
    records[0]["true_label"] = True
    with pytest.raises(ValueError):
        EvidenceTools(InvestigationScope(**SCOPE), records=records)


@pytest.mark.parametrize("query", ["What caused the search timeouts?", "timeouts"])
async def test_runbook_section_ids_match_without_common_word_noise(tools, query):
    result = await tools.search_runbooks(query=query, limit=1)
    assert result.items[0].evidence_id == "runbook:timeouts"
    empty = await tools.search_runbooks(query="what is the")
    assert empty.items == [] and empty.error is None


async def test_runbooks_are_ranked_versioned_and_do_not_accept_paths(tools):
    first = await tools.search_runbooks(query="connection pool exhaustion", limit=1)
    assert first.error is None
    assert first.items[0].evidence_id == "runbook:connection-pools"
    assert "pool" in first.items[0].content["body"].lower()
    assert first == await tools.search_runbooks(query="connection pool exhaustion", limit=1)
    rejected = await tools.search_runbooks(query="pool", path="../../evals/labels.jsonl")
    assert rejected.error == "invalid_arguments" and rejected.items == []
    missing = await tools.search_runbooks(query="zzzznotaword")
    assert missing.items == [] and missing.error is None


async def test_json_credentials_and_runbook_versions(tmp_path):
    path = tmp_path / "operations.md"
    path.write_text('## example: Connection diagnostics\n{"api_key":"fixture-json-key"}\n')
    tool = EvidenceTools(InvestigationScope(**SCOPE), records=[], runbook_path=path)
    first = await tool.search_runbooks(query="connection")
    assert first.error is None
    assert "fixture-json-key" not in first.model_dump_json()
    assert json.loads(first.items[0].content["body"])["api_key"] == "[REDACTED]"
    path.write_text("## example: Connection diagnostics\nCompare connection limits.\n")
    second = await tool.search_runbooks(query="connection")
    assert first.version != second.version
    assert "api_key" in first.items[0].content["body"]


async def test_runbook_failure_is_not_an_empty_success(tmp_path):
    tool = EvidenceTools(
        InvestigationScope(**SCOPE), records=[], runbook_path=tmp_path / "missing.md"
    )
    result = await tool.search_runbooks(query="pool")
    assert result.error == "source_unavailable" and result.items == []


async def test_database_failure_does_not_expose_sql_or_credentials(engine):
    async with async_sessionmaker(engine)() as session:
        tool = EvidenceTools(InvestigationScope(**SCOPE), session=session)
        async with engine.begin() as connection:
            await connection.run_sync(Log.__table__.drop)
        for method in (tool.query_logs, tool.summarize_logs):
            result = await method(**SCOPE)
            assert result.error == "source_unavailable"
            assert "SELECT" not in result.model_dump_json()


@pytest.mark.parametrize("stamp", ["2026-01-01T15:30:01+05:30", "2026-01-01T10:00:01"])
async def test_offset_ingestion_is_queryable_by_utc_scope(client, engine, stamp):
    await client.post(
        "/logs",
        json={
            "service": "checkout",
            "level": "INFO",
            "message": "offset ingestion",
            "timestamp": stamp,
        },
    )
    async with async_sessionmaker(engine)() as session:
        tool = EvidenceTools(InvestigationScope(**SCOPE), session=session)
        result = await tool.query_logs(**SCOPE)
        assert [item.content["message"] for item in result.items] == ["offset ingestion"]
