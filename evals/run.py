"""Run one development baseline. Live execution requires explicit opt-in and a budget."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/ingestion-service"))

from app.investigation_agent import BaselineConfig, canonical, run_baseline  # noqa: E402
from app.investigation_schemas import InvestigationScope  # noqa: E402
from app.investigation_tools import EvidenceTools  # noqa: E402
from openai import AsyncOpenAI  # noqa: E402
from validate import load_cases  # noqa: E402


def provenance(case, corpus):
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True))
    digest = hashlib.sha256()
    for name in (
        "evals/run.py",
        "evals/validate.py",
        "services/ingestion-service/requirements.txt",
        "services/ingestion-service/app/investigation_agent.py",
        "services/ingestion-service/app/investigation_schemas.py",
        "services/ingestion-service/app/investigation_tools.py",
    ):
        digest.update(name.encode() + b"\0" + (ROOT / name).read_bytes())
    return {
        "case_id": case["case_id"],
        "dataset_version": case["dataset_version"],
        "origin": case["provenance"],
        "case_sha256": hashlib.sha256(canonical(case).encode()).hexdigest(),
        "corpus_sha256": hashlib.sha256(corpus.read_bytes()).hexdigest(),
        "code_revision": revision,
        "code_dirty": dirty,
        "implementation_sha256": digest.hexdigest(),
    }


async def execute(args, case, config, key):
    tools = EvidenceTools(InvestigationScope(**case["scope"]), records=case["logs"])
    if args.dry_run:
        return await run_baseline(args.system, case["question"], tools, None, config, dry_run=True)
    async with AsyncOpenAI(
        api_key=key, base_url="https://api.openai.com/v1", max_retries=0
    ) as client:
        return await run_baseline(args.system, case["question"], tools, client, config)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=(
            "Example (no network): python evals/run.py --system B --case dev-01 "
            "--model gpt-4.1-mini-2025-04-14 --max-cost-usd 0.10 --dry-run"
        ),
    )
    parser.add_argument("--system", choices=["A", "B"], required=True)
    parser.add_argument(
        "--case", required=True, help="development case ID; no paths or held-out cases"
    )
    parser.add_argument(
        "--model", default=os.environ.get("LLM_MODEL"), help="explicit model snapshot, or LLM_MODEL"
    )
    parser.add_argument(
        "--max-cost-usd",
        required=True,
        help="positive per-run allowance for conservative preflight",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="collect evidence and estimate reservation; make no provider request",
    )
    parser.add_argument(
        "--allow-live", action="store_true", help="explicitly authorize one paid provider request"
    )
    parser.add_argument(
        "--output", type=Path, help="new JSON artifact; existing files are never overwritten"
    )
    args = parser.parse_args()
    if args.dry_run and args.allow_live:
        parser.error("choose --dry-run or --allow-live, not both")
    if not args.dry_run and not args.allow_live:
        parser.error(
            "live execution requires --allow-live; use --dry-run to inspect without spending"
        )
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not args.dry_run and not key:
        parser.error("OPENAI_API_KEY is required for live execution")
    try:
        config = BaselineConfig(model=args.model, max_cost_usd=args.max_cost_usd)
    except ValueError:
        parser.error("specify the supported model snapshot and a finite positive --max-cost-usd")
    corpus = ROOT / "evals/cases/dev.jsonl"
    try:
        cases = load_cases(corpus)
        case = next((case for case in cases if case["case_id"] == args.case), None)
        if case is None:
            parser.error("unknown development case ID")
        metadata = provenance(case, corpus)
        if not args.dry_run and metadata["code_dirty"]:
            parser.error(
                "live evaluation requires a clean committed worktree for reproducible provenance"
            )
        # Reserve an output path before spending; exclusive creation also rejects symlinks.
        output = args.output.open("x", encoding="utf-8") if args.output else None
    except FileExistsError:
        parser.error("output already exists; choose a new artifact path")
    except (OSError, ValueError, subprocess.SubprocessError):
        parser.error("cannot load development evidence, record code provenance, or create output")
    try:
        result = asyncio.run(execute(args, case, config, key))
        result["provenance"] = metadata
        serialized = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if output:
            output.write(serialized)
        else:
            print(serialized, end="")
        return 0 if result["status"] in {"completed", "dry_run"} else 1
    finally:
        if output:
            output.close()


if __name__ == "__main__":
    sys.exit(main())
