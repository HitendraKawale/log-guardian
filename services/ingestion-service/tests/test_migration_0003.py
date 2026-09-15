"""Alembic 0002 -> 0003 on an isolated database preserves existing log rows."""

import subprocess
import sys
from pathlib import Path

import sqlalchemy as sa

SERVICE = Path(__file__).resolve().parents[1]


def alembic(env, *arguments):
    return subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        cwd=SERVICE,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_upgrade_from_0002_preserves_logs_and_adds_tables(tmp_path):
    database = tmp_path / "migrate.db"
    env = {
        "PATH": "/usr/bin:/bin",
        "DATABASE_URL": f"sqlite+aiosqlite:///{database}",
        "HOME": str(tmp_path),
    }
    upgraded = alembic(env, "upgrade", "0002")
    assert upgraded.returncode == 0, upgraded.stderr
    engine = sa.create_engine(f"sqlite:///{database}")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO logs (service, level, message, timestamp, status, created_at)"
                " VALUES ('checkout', 'ERROR', 'boom', '2026-01-01 10:00:00', 'unscored',"
                " '2026-01-01 10:00:00')"
            )
        )
    # Pinned to 0003 rather than "head": this test is about what 0003 does, and
    # asserting the head revision would break every time a migration is added.
    final = alembic(env, "upgrade", "0003")
    assert final.returncode == 0, final.stderr
    with engine.connect() as connection:
        revision = connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar()
        assert revision == "0003"
        tables = {
            row[0]
            for row in connection.execute(
                sa.text("SELECT name FROM sqlite_master WHERE type='table'")
            )
        }
        assert {"investigations", "investigation_events"} <= tables
        preserved = connection.execute(
            sa.text("SELECT service, level, message, status FROM logs")
        ).all()
        assert preserved == [("checkout", "ERROR", "boom", "unscored")]
        indexes = {
            row[0]
            for row in connection.execute(
                sa.text("SELECT name FROM sqlite_master WHERE type='index'")
            )
        }
        assert {"ix_logs_service_timestamp", "ix_investigation_events_run_seq"} <= indexes
    downgraded = alembic(env, "downgrade", "0002")
    assert downgraded.returncode == 0, downgraded.stderr
    with engine.connect() as connection:
        remaining = connection.execute(
            sa.text("SELECT count(*) FROM sqlite_master WHERE name='investigations'")
        ).scalar()
        assert remaining == 0
        assert connection.execute(sa.text("SELECT count(*) FROM logs")).scalar() == 1
