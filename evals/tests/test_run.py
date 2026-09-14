"""The owner CLI defaults to refusing live execution and never loads labels."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
COMMAND = [
    sys.executable,
    str(ROOT / "evals/run.py"),
    "--case",
    "dev-01",
    "--model",
    "gpt-4.1-mini-2025-04-14",
    "--max-cost-usd",
    "0.10",
]


def invoke(*arguments):
    env = {k: v for k, v in os.environ.items() if k not in {"OPENAI_API_KEY", "LLM_MODEL"}}
    return subprocess.run(
        COMMAND + list(arguments), capture_output=True, text=True, env=env, timeout=15
    )


@pytest.mark.parametrize("system,count", [("A", 1), ("B", 3)])
def test_dry_run_has_provenance_evidence_and_zero_requests(system, count):
    completed = invoke("--system", system, "--dry-run")
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["status"] == "dry_run" and result["model_requests"] == 0
    assert len(result["trace"]) == count
    assert result["provenance"]["case_id"] == "dev-01"
    assert result["provenance"]["origin"] == "authored"
    assert len(result["provenance"]["case_sha256"]) == 64
    assert len(result["provenance"]["implementation_sha256"]) == 64
    assert "expected_cause" not in completed.stdout and "true_label" not in completed.stdout
    assert result["report"] is None


def test_live_requires_opt_in_and_credentials():
    denied = invoke("--system", "A")
    assert denied.returncode == 2 and "--allow-live" in denied.stderr
    missing = invoke("--system", "A", "--allow-live")
    assert missing.returncode == 2 and "OPENAI_API_KEY" in missing.stderr


def test_case_selection_does_not_accept_paths_or_held_out_ids():
    for case in ("../../labels.jsonl", "test-01"):
        denied = invoke("--system", "A", "--dry-run", "--case", case)
        assert denied.returncode == 2
        assert "development case" in denied.stderr


def test_existing_output_is_never_overwritten(tmp_path):
    output = tmp_path / "run.json"
    saved = invoke("--system", "A", "--dry-run", "--output", str(output))
    assert saved.returncode == 0 and saved.stdout == ""
    previous = output.read_text()
    assert json.loads(previous)["status"] == "dry_run"
    denied = invoke("--system", "A", "--dry-run", "--output", str(output))
    assert denied.returncode == 2 and "already exists" in denied.stderr
    assert output.read_text() == previous
