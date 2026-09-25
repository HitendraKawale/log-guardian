"""Capture real read-only investigator tools with scripted dispatch and no model calls."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from log_guardian_agent import Monitor, Policy, inspect_journal

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services/ingestion-service"))
from app.investigation_schemas import InvestigationScope  # noqa: E402
from app.investigation_tools import EvidenceTools  # noqa: E402


async def capture(output):
    scope = {
        "services": ["checkout"],
        "start": "2026-01-01T12:00:00+00:00",
        "end": "2026-01-01T12:02:00+00:00",
    }
    tools = EvidenceTools(
        InvestigationScope.model_validate(scope),
        records=[
            {
                "evidence_id": "demo:1",
                "service": "checkout",
                "level": "ERROR",
                "timestamp": "2026-01-01T12:01:00+00:00",
                "message": "Inventory request exceeded caller deadline.",
            }
        ],
    )
    policy = Policy(allowed_tools={"query_logs"})
    with Monitor(output, agent="investigator", policy=policy) as monitor:
        initial = monitor.wrap("initial_logs", tools._initial_logs, origin="host")
        query = monitor.wrap("query_logs", tools.query_logs)
        summary = monitor.wrap("summarize_logs", tools.summarize_logs)
        assert (await initial(scope)).error is None
        assert (await query(**scope)).error is None
        assert (await summary(**scope)).error is None
    return {
        "mode": "scripted_tool_capture",
        "provider_requests": 0,
        **inspect_journal(output.read_bytes(), policy),
    }


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog="Example from repo root: PYTHONPATH=integrations/python .venv/bin/python integrations/python/examples/investigator.py --output /tmp/new-agent-run.jsonl",
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="New JSONL file; parent directory must exist"
    )
    args = parser.parse_args()
    try:
        report = asyncio.run(capture(args.output))
    except (OSError, ValueError) as exc:
        parser.exit(
            1,
            f"Capture failed ({type(exc).__name__}); use a new output path and valid local permissions.\n",
        )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
