"""Paired local SQLite measurements of the real recorder, without model calls or user data."""

import argparse
import asyncio
import hashlib
import json
import math
import platform
import random
import statistics
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.investigation_schemas import InvestigationScope
from app.investigation_tools import EvidenceTools
from app.investigator import RecordingTools
from app.models import Base, Investigation, InvestigationEvent, Log
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def distribution(values):
    return {
        "median_ms": statistics.median(values),
        "p95_ms": sorted(values)[math.ceil(len(values) * 0.95) - 1],
    }


async def measure(rounds, pairs):
    samples, event_counts = [], []
    start = datetime(2026, 1, 1, 10, tzinfo=UTC)
    scope = InvestigationScope(
        services=["checkout"], start=start, end=start + timedelta(minutes=10)
    )
    arguments = scope.model_dump(mode="json")
    with tempfile.TemporaryDirectory(prefix="lg-recording-measurement-") as directory:
        engine = create_async_engine(f"sqlite+aiosqlite:///{directory}/events.db")
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            async with factory() as session:
                session.add_all(
                    [
                        Log(
                            service="checkout",
                            level="INFO",
                            message=f"Synthetic request {n}",
                            timestamp=start + timedelta(seconds=n),
                        )
                        for n in range(50)
                    ]
                )
                await session.commit()
            for round_number in range(rounds):
                async with factory() as session:
                    run = Investigation(
                        question="Local measurement",
                        system="C",
                        scope=arguments,
                        request_sha256="0" * 64,
                        status="running",
                    )
                    session.add(run)
                    await session.commit()
                    run_id = run.id
                async with factory() as evidence_session:
                    tools = {
                        "baseline": EvidenceTools(scope, session=evidence_session),
                        "recorded": RecordingTools(
                            scope, factory, run_id, session=evidence_session
                        ),
                    }
                    rng = random.Random(round_number)
                    for pair in range(-5, pairs):
                        order = list(tools)
                        rng.shuffle(order)
                        outputs, timings = {}, {}
                        for name in order:
                            before = time.perf_counter_ns()
                            batch = await tools[name].query_logs(**arguments)
                            timings[name] = (time.perf_counter_ns() - before) / 1_000_000
                            outputs[name] = batch.model_dump(mode="json")
                        assert outputs["baseline"] == outputs["recorded"]
                        assert len(outputs["recorded"]["items"]) == 50
                        if pair >= 0:
                            samples.append(
                                {
                                    "round": round_number + 1,
                                    "pair": pair + 1,
                                    "order": order,
                                    **timings,
                                }
                            )
                async with factory() as session:
                    count = await session.scalar(
                        select(func.count())
                        .select_from(InvestigationEvent)
                        .where(InvestigationEvent.investigation_id == run_id)
                    )
                    assert count == 2 * (pairs + 5)
                    completions = await session.scalar(
                        select(func.count())
                        .select_from(InvestigationEvent)
                        .where(
                            InvestigationEvent.investigation_id == run_id,
                            InvestigationEvent.kind == "tool_call",
                        )
                    )
                    assert completions == pairs + 5
                    event_counts.append(count)
        finally:
            await engine.dispose()
    root = Path(__file__).resolve().parent
    return {
        "mode": "local_synthetic_no_model",
        "backend": "file_backed_sqlite",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "rounds": rounds,
        "pairs_per_round": pairs,
        "warmup_pairs_per_round": 5,
        "rows_per_query": 50,
        "persisted_events_per_round": event_counts,
        "source_sha256": {
            name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in (
                "measure_recording.py",
                "app/investigator.py",
                "app/investigation_tools.py",
                "app/investigation_loop.py",
                "app/investigation_schemas.py",
                "app/models.py",
            )
        },
        "baseline": distribution([s["baseline"] for s in samples]),
        "recorded": distribution([s["recorded"] for s in samples]),
        "paired_added_latency": distribution([s["recorded"] - s["baseline"] for s in samples]),
        "samples": samples,
        "limits": "Sequential local queries only; no contention, model latency, real-user traffic or alert review. "
        "Recorded timing includes the cancellation check and committed request/completion writes. "
        "No application latency acceptance threshold has been agreed.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--pairs", type=int, default=100)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.rounds <= 10 or not 20 <= args.pairs <= 1000:
        parser.error("use 1–10 rounds and 20–1000 pairs")
    if args.output.exists():
        parser.error("output already exists; measurements are not overwritten")
    result = asyncio.run(measure(args.rounds, args.pairs))
    with args.output.open("x") as handle:
        json.dump(result, handle, indent=2)
        handle.write("\n")
    print(
        json.dumps(
            {
                name: result[name]
                for name in (
                    "baseline",
                    "recorded",
                    "paired_added_latency",
                    "persisted_events_per_round",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
