"""Verify recurrence upgrades preserve legacy rows and reject lossy downgrades."""

import json
import os
import sqlite3
import subprocess
import sys


def migrate(path, direction, revision):
    return subprocess.run(
        [sys.executable, "-m", "alembic", direction, revision],
        env={**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{path}"},
        capture_output=True,
        text=True,
        check=False,
    )


def test_upgrade_preserves_candidate_and_investigation_link(tmp_path):
    path = tmp_path / "legacy.db"
    result = migrate(path, "upgrade", "0005")
    assert result.returncode == 0, result.stderr
    scope = json.dumps(
        {"services": ["checkout"], "start": "2026-01-01T00:00:00Z", "end": "2026-01-01T00:10:00Z"}
    )
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO investigations (id, question, system, scope, status, request_sha256, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("run", "owner question", "B", scope, "completed", "a" * 64, "2026-01-01"),
        )
        db.execute(
            "INSERT INTO investigation_candidates (id,service,level,message,template,reason,scope,status,occurred_at,created_at,investigation_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                "old",
                "checkout",
                "ERROR",
                "timeout",
                "timeout",
                "unseen-template",
                scope,
                "promoted",
                "2026-01-01",
                "2026-01-01",
                "run",
            ),
        )
    result = migrate(path, "upgrade", "0006")
    assert result.returncode == 0, result.stderr
    with sqlite3.connect(path) as db:
        row = db.execute(
            "SELECT id,status,scope,investigation_id,occurrence_count,last_seen_at,active_service FROM investigation_candidates"
        ).fetchone()
        assert row == ("old", "promoted", scope, "run", 1, "2026-01-01", None)
        db.execute(
            "INSERT INTO investigation_candidates (id,service,level,message,template,reason,scope,status,occurred_at,created_at) SELECT 'new',service,level,message,template,reason,scope,'new',occurred_at,created_at FROM investigation_candidates WHERE id='old'"
        )
    result = migrate(path, "downgrade", "0005")
    assert result.returncode != 0
    assert "recurring candidate history" in result.stderr
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT count(*) FROM investigation_candidates").fetchone()[0] == 2
        assert db.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0006"


def test_empty_database_can_upgrade_and_downgrade(tmp_path):
    path = tmp_path / "empty.db"
    result = migrate(path, "upgrade", "0006")
    assert result.returncode == 0, result.stderr
    result = migrate(path, "downgrade", "0005")
    assert result.returncode == 0, result.stderr
