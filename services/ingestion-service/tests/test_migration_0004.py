"""Alembic 0003 -> 0004 adds the candidate queue and holds its uniqueness rule.

The unique index is not cosmetic: de-duplication across process restarts and
replicas is delegated to the database, so if the constraint is missing the
queue fills with repeats of the same message family. It is asserted here
against a real migrated database rather than inferred from the model.
"""

import subprocess
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa

SERVICE = Path(__file__).resolve().parents[1]

CANDIDATE = (
    "INSERT INTO investigation_candidates"
    " (id, service, level, message, template, reason, scope, status, occurred_at, created_at)"
    " VALUES (:id, 'checkout', 'ERROR', :message, :template, 'unseen-template',"
    " '{{}}', 'new', '2026-01-01 10:00:00', '2026-01-01 10:00:00')"
)


def alembic(env, *arguments):
    return subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        cwd=SERVICE,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _env(tmp_path, database):
    return {
        "PATH": "/usr/bin:/bin",
        "DATABASE_URL": f"sqlite+aiosqlite:///{database}",
        "HOME": str(tmp_path),
    }


def test_upgrade_adds_candidates_and_preserves_investigations(tmp_path):
    database = tmp_path / "migrate.db"
    env = _env(tmp_path, database)

    assert alembic(env, "upgrade", "0003").returncode == 0
    engine = sa.create_engine(f"sqlite:///{database}")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO investigations"
                " (id, question, system, scope, status, request_sha256, created_at)"
                " VALUES ('run-1', 'why?', 'B', '{}', 'queued', 'abc', '2026-01-01 10:00:00')"
            )
        )

    result = alembic(env, "upgrade", "0004")
    assert result.returncode == 0, result.stderr

    with engine.connect() as connection:
        revision = connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar()
        assert revision == "0004"
        tables = {
            row[0]
            for row in connection.execute(
                sa.text("SELECT name FROM sqlite_master WHERE type='table'")
            )
        }
        assert "investigation_candidates" in tables
        # The existing investigation survives; candidates are a separate queue.
        assert connection.execute(sa.text("SELECT COUNT(*) FROM investigations")).scalar() == 1


def test_service_template_pair_is_unique(tmp_path):
    database = tmp_path / "unique.db"
    env = _env(tmp_path, database)
    assert alembic(env, "upgrade", "0004").returncode == 0

    engine = sa.create_engine(f"sqlite:///{database}")
    with engine.begin() as connection:
        connection.execute(
            sa.text(CANDIDATE),
            {"id": "c1", "message": "first sighting", "template": "disk error"},
        )
    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                sa.text(CANDIDATE),
                {"id": "c2", "message": "second sighting", "template": "disk error"},
            )


def test_same_template_in_a_different_service_is_allowed(tmp_path):
    """Two services failing the same way are two things worth investigating."""
    database = tmp_path / "per-service.db"
    env = _env(tmp_path, database)
    assert alembic(env, "upgrade", "0004").returncode == 0

    engine = sa.create_engine(f"sqlite:///{database}")
    with engine.begin() as connection:
        connection.execute(
            sa.text(CANDIDATE),
            {"id": "c1", "message": "m", "template": "disk error"},
        )
        connection.execute(
            sa.text(CANDIDATE.replace("'checkout'", "'inventory'")),
            {"id": "c2", "message": "m", "template": "disk error"},
        )
        count = connection.execute(
            sa.text("SELECT COUNT(*) FROM investigation_candidates")
        ).scalar()
    assert count == 2


def test_downgrade_removes_the_queue_and_keeps_investigations(tmp_path):
    database = tmp_path / "down.db"
    env = _env(tmp_path, database)
    assert alembic(env, "upgrade", "0004").returncode == 0
    result = alembic(env, "downgrade", "0003")
    assert result.returncode == 0, result.stderr

    engine = sa.create_engine(f"sqlite:///{database}")
    with engine.connect() as connection:
        tables = {
            row[0]
            for row in connection.execute(
                sa.text("SELECT name FROM sqlite_master WHERE type='table'")
            )
        }
        assert "investigation_candidates" not in tables
        assert "investigations" in tables
