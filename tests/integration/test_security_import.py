"""Verify PostgreSQL migration and concurrent imports in a new task-owned database."""

import asyncio
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "services/ingestion-service"


@pytest.fixture(scope="session", autouse=True)
def require_stack():
    if not os.environ.get("LG_TEST_POSTGRES_URL"):
        pytest.skip("set LG_TEST_POSTGRES_URL to a task-owned PostgreSQL server")


def test_postgres_atomic_overlap_and_concurrent_imports():
    async def exercise():
        import asyncpg

        admin_url = os.environ["LG_TEST_POSTGRES_URL"].replace("postgresql+asyncpg:", "postgresql:")
        name = "lg_security_" + uuid.uuid4().hex
        admin = await asyncpg.connect(admin_url)
        try:
            await admin.execute(f'CREATE DATABASE "{name}"')
        finally:
            await admin.close()
        # Keep the fresh database for inspection; never drop a pre-existing database.
        url = admin_url.rsplit("/", 1)[0] + "/" + name
        database_url = url.replace("postgresql:", "postgresql+asyncpg:")
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=SERVICE,
            env={**os.environ, "DATABASE_URL": database_url},
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        sys.path.insert(0, str(SERVICE))
        from app.models import Investigation, SecurityCase, SecurityEvidence
        from app.routes.security_cases import list_cases, save_case
        from fastapi import HTTPException, Response
        from sqlalchemy import func, select
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        engine = create_async_engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        owner = json.loads((ROOT / "examples/security-review/sources.json").read_text())
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

        async def save(key, value=body):
            async with factory() as session:
                case, created = await save_case(session, owner, value, key)
                return case.id, created

        try:
            a, b = await asyncio.gather(save("same"), save("same"))
            assert a[0] == b[0] and sorted([a[1], b[1]]) == [False, True]
            c, d = await asyncio.gather(save("overlap-1"), save("overlap-2"))
            assert c[0] != d[0]
            changed = {
                **body,
                "logs": {
                    **body["logs"],
                    "auth": body["logs"]["auth"].replace('"failure"', '"success"'),
                },
            }
            with pytest.raises(HTTPException) as error:
                await save("conflict", changed)
            assert error.value.status_code == 409
            async with factory() as session:
                assert await session.scalar(select(func.count()).select_from(SecurityCase)) == 3
                assert await session.scalar(select(func.count()).select_from(SecurityEvidence)) == 6
                assert await session.scalar(select(func.count()).select_from(Investigation)) == 0
                history = await list_cases(Response(), session=session, limit=25, offset=0)
                assert len(history) == 3
                assert all(row["input_records"] == 6 and "report" not in row for row in history)
            print(f"PostgreSQL security evidence verified in fresh database {name}")
        finally:
            await engine.dispose()

    asyncio.run(exercise())
