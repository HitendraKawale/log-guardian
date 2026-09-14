"""Owner-operated fault scenario: healthy traffic, real timeout, recovery.

Only this script touches the fault endpoints; they are never agent tools.
The fault is always reset in ``finally``. Recovery is proven by successful
requests, never by a screenshot.

    python demo/run_scenario.py            # against the demo Compose stack
    python demo/run_scenario.py --capture demo/bundles/incident.jsonl
"""

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

CHECKOUT = "http://127.0.0.1:9001"
FAULTS = "http://127.0.0.1:9101"
INGESTION = "http://127.0.0.1:8000"


def drive_traffic(client, count, prefix):
    statuses = []
    for n in range(count):
        try:
            response = client.get(f"{CHECKOUT}/checkout/{prefix}-{n}", timeout=5.0)
            statuses.append(response.status_code)
        except httpx.HTTPError:
            statuses.append(0)
        time.sleep(0.2)
    return statuses


def capture_bundle(client, start, end, path):
    """Model-visible evidence only: logs by service/level/message/timestamp.

    No fault-control metadata, no expected answer, no scenario name.
    """
    rows = client.get(f"{INGESTION}/logs", params={"limit": 200}, timeout=10.0).json()
    kept = []
    for row in rows:
        stamp = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
        if stamp.tzinfo is None:  # Legacy SQLite rows are naive UTC.
            stamp = stamp.replace(tzinfo=UTC)
        if start <= stamp <= end and row["service"] in {"checkout", "inventory"}:
            kept.append(
                {
                    "service": row["service"],
                    "level": row["level"],
                    "message": row["message"],
                    "timestamp": row["timestamp"],
                }
            )
    kept.sort(key=lambda r: r["timestamp"])
    bundle = {
        "captured_at": datetime.now(UTC).isoformat(),
        "origin": "live-demo",
        "scope": {
            "services": ["checkout", "inventory"],
            "start": start.isoformat(),
            "end": end.isoformat(),
        },
        "question": "Why did checkout requests start failing?",
        "logs": kept,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bundle, indent=2) + "\n")
    return len(kept)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, help="write a model-visible evidence bundle")
    parser.add_argument("--delay-seconds", type=float, default=3.0)
    args = parser.parse_args()
    started = datetime.now(UTC)
    with httpx.Client() as client:
        for url in (f"{CHECKOUT}/health", f"{INGESTION}/health", f"{FAULTS}/fault"):
            client.get(url, timeout=5.0).raise_for_status()
        print("[1/5] services healthy")
        healthy = drive_traffic(client, 5, "ok")
        assert all(s == 200 for s in healthy), f"baseline unhealthy: {healthy}"
        print(f"[2/5] healthy traffic confirmed: {healthy}")
        try:
            client.post(
                f"{FAULTS}/fault/delay", json={"seconds": args.delay_seconds}, timeout=5.0
            ).raise_for_status()
            print(f"[3/5] inventory delay {args.delay_seconds}s applied")
            deadline = time.monotonic() + 60
            observed = []
            while time.monotonic() < deadline and observed.count(504) < 3:
                observed += drive_traffic(client, 1, "fault")
            assert observed.count(504) >= 3, f"no observed timeouts: {observed}"
            print(f"[4/5] real upstream timeouts observed: {observed}")
        finally:
            client.post(f"{FAULTS}/fault/reset", timeout=5.0).raise_for_status()
            print("      fault reset (finally)")
        recovered = drive_traffic(client, 5, "recovered")
        assert all(s == 200 for s in recovered), f"did not recover: {recovered}"
        print(f"[5/5] recovery verified by successful requests: {recovered}")
        if args.capture:
            count = capture_bundle(client, started, datetime.now(UTC), args.capture)
            print(f"      captured {count} model-visible log rows to {args.capture}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
