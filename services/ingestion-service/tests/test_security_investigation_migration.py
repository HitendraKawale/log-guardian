"""Add the case binding without recreating away existing journal evidence."""

import os
import sqlite3
import subprocess
import sys


def test_upgrade_keeps_run_and_receipt_and_downgrade_refuses_binding(tmp_path):
    path = tmp_path / "binding.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{path}"}

    def migrate(direction, revision):
        return subprocess.run(
            [sys.executable, "-m", "alembic", direction, revision],
            env=env,
            capture_output=True,
            text=True,
        )

    before = migrate("upgrade", "0007")
    assert before.returncode == 0, before.stderr
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO investigations (id,question,system,scope,status,request_sha256,created_at) VALUES ('old','why','C','{}','completed','hash','2026-01-01')"
        )
        db.execute(
            "INSERT INTO investigation_events (investigation_id,sequence,kind,payload,created_at) VALUES ('old',1,'tool_request','{}','2026-01-01')"
        )
        db.execute(
            "INSERT INTO security_cases VALUES ('case','key','hash','{}','{}','{}','2026-01-01')"
        )
    after = migrate("upgrade", "head")
    assert after.returncode == 0, after.stderr
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT question,security_case_id FROM investigations").fetchall() == [
            ("why", None)
        ]
        assert db.execute("SELECT kind FROM investigation_events").fetchall() == [("tool_request",)]
        db.execute("UPDATE investigations SET security_case_id='case'")
    refused = migrate("downgrade", "0007")
    assert refused.returncode != 0
    assert "cannot downgrade linked security investigations" in refused.stderr
