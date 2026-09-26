"""Historical pilot checks execute archived application bytes, not the evolving product."""

import hashlib
import importlib
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE_SHA = "089668b84ee0e4514e10054d5465b1818c750dbe228d0e28e6c7d4be52292af4"


@pytest.mark.parametrize(
    "check",
    [
        "test_fresh_batch_configuration_restores_consumed_batch",
        "test_fresh_batch_real_worker_and_input_separation",
        "test_seventy_two_reservations_then_stop",
        "test_frozen_production_drift_refuses_before_ledger[app/investigation_agent.py]",
        "test_frozen_production_drift_refuses_before_ledger[fresh-case-authoring/cases.jsonl]",
    ],
)
def test_frozen_pilot_against_archived_application(tmp_path, check):
    archive = ROOT / "evals/freezes/report-grounding-20e8e292e67b.tar.gz"
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == ARCHIVE_SHA
    stage = tmp_path / "frozen"
    stage.mkdir()
    pilot = importlib.import_module("fresh_report_pilot")
    with pilot.configured() as configured:
        supporting = [
            name
            for name in configured.FILES
            if not name.startswith("services/ingestion-service/app/")
        ]
    for name in supporting + ["evals/pytest.ini"]:
        target = stage / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    with tarfile.open(archive) as bundle:
        for member in bundle.getmembers():
            if not member.name.startswith("services/"):
                continue
            assert member.isfile() and ".." not in Path(member.name).parts
            target = stage / member.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(bundle.extractfile(member).read())
    # Keep the original five checks unchanged, but import the actual frozen worker in a child.
    shutil.copyfile(
        ROOT / "evals/tests/_fresh_pilot_checks.py",
        stage / "evals/tests/test_fresh_report_pilot.py",
    )
    env = {
        **os.environ,
        "OPENAI_API_KEY": "",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
    }
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        env.pop(name, None)
    commands = [
        ["git", "init", "-q"],
        ["git", "add", "."],
        [
            "git",
            "-c",
            "user.name=Offline fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "core.hooksPath=/dev/null",
            "commit",
            "-qm",
            "Frozen test fixture",
        ],
    ]
    for command in commands:
        subprocess.run(command, cwd=stage, env=env, capture_output=True, check=True)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", f"tests/test_fresh_report_pilot.py::{check}"],
        cwd=stage / "evals",
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_evolving_product_cannot_reuse_the_frozen_live_candidate():
    pilot = importlib.import_module("fresh_report_pilot")
    with pilot.configured() as configured:
        with pytest.raises(ValueError, match="frozen production source changed"):
            configured.candidate()
