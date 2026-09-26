"""Upgrading adds security storage without rewriting existing operational evidence."""

import os
import sqlite3
import subprocess
import sys


def test_security_upgrade_preserves_existing_log(tmp_path):
    path = tmp_path / "upgrade.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{path}"}
    for revision in ("0006", "0007"):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", revision],
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        if revision == "0006":
            with sqlite3.connect(path) as db:
                assert not db.execute(
                    "SELECT name FROM sqlite_master WHERE name='security_cases'"
                ).fetchall()
                db.execute(
                    "INSERT INTO logs (service,level,message,timestamp,status,created_at) VALUES ('old','INFO','preserve me','2026-01-01','unscored','2026-01-01')"
                )
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT service,message FROM logs").fetchall() == [("old", "preserve me")]
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == ("0007",)
        db.execute("INSERT INTO security_evidence VALUES ('edge','r1','hash','{}')")
        db.execute(
            "INSERT INTO security_cases VALUES ('case','key','hash','{}','{}','{}','2026-01-01')"
        )
        assert db.execute("SELECT count(*) FROM security_cases").fetchone() == (1,)
