#!/usr/bin/env python3
"""Verify a running Log Guardian deployment from the outside.

Point it at whatever you just deployed. Standard library only, so it runs on a
bare box, in a CI step, or as a container healthcheck without installing
anything.

    python scripts/smoke.py                         # local compose
    python scripts/smoke.py https://api.example.com # anywhere else
    python scripts/smoke.py --api-key "$API_KEY"

Exits non-zero on the first hard failure, so it works as a deploy gate.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime

GREEN, YELLOW, RED, RESET = "\033[32m", "\033[33m", "\033[31m", "\033[0m"

failures = 0
warnings = 0


def _print(status: str, colour: str, label: str, detail: str = "") -> None:
    print(f"  {colour}{status:<5}{RESET} {label}" + (f"  {detail}" if detail else ""))


def ok(label: str, detail: str = "") -> None:
    _print("ok", GREEN, label, detail)


def warn(label: str, detail: str = "") -> None:
    global warnings
    warnings += 1
    _print("warn", YELLOW, label, detail)


def fail(label: str, detail: str = "") -> None:
    global failures
    failures += 1
    _print("FAIL", RED, label, detail)


def request(
    url: str, method: str = "GET", body: dict | None = None, api_key: str = ""
) -> tuple[int, str]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)  # noqa: S310
    if data:
        req.add_header("Content-Type", "application/json")
    if api_key:
        req.add_header("X-API-Key", api_key)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:  # noqa: S310
            return response.status, response.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()
    except (urllib.error.URLError, OSError) as exc:
        return 0, str(exc)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", nargs="?", default="http://localhost:8000")
    parser.add_argument("--api-key", default="", help="sent as X-API-Key when the API is locked")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    print(f"\nSmoke test: {base}\n")

    status, body = request(f"{base}/health", api_key=args.api_key)
    if status == 200:
        ok("liveness", "/health")
    else:
        fail("liveness", f"/health -> {status} {body[:80]}")
        print("\nNothing is answering; stopping here.\n")
        return 1

    status, body = request(f"{base}/readiness", api_key=args.api_key)
    ok("readiness", "database reachable") if status == 200 else fail(
        "readiness", f"-> {status} {body[:80]}"
    )

    payload = {
        "service": "smoke-test",
        "level": "CRITICAL",
        "message": "smoke test: database connection refused",
        "timestamp": datetime.now(UTC).isoformat(),
    }
    status, body = request(f"{base}/logs", "POST", payload, args.api_key)
    log_id = None
    if status == 201:
        record = json.loads(body)
        log_id = record["id"]
        if record["status"] == "scored":
            ok("ingest", f"id={log_id} score={record['anomaly_score']}")
        else:
            # Not fatal by design: ingestion is meant to outlive the scorer.
            warn("ingest", f"id={log_id} stored unscored - is the AI service up?")
    elif status == 401:
        fail("ingest", "401 - the API needs a key; pass --api-key")
    else:
        fail("ingest", f"-> {status} {body[:120]}")

    if log_id is not None:
        status, body = request(f"{base}/logs/{log_id}", api_key=args.api_key)
        ok("read back", f"/logs/{log_id}") if status == 200 else fail("read back", f"-> {status}")

    status, body = request(f"{base}/metrics", api_key=args.api_key)
    if status == 200 and "ingestion_logs_total" in body:
        ok("metrics", "ingestion_logs_total present")
    else:
        fail("metrics", f"-> {status}")

    status, body = request(f"{base}/model/info", api_key=args.api_key)
    if status == 200:
        info = json.loads(body)
        ok("model", f"analyzer={info.get('analyzer')} version={info.get('current_version')}")
    else:
        warn("model", f"/model/info -> {status} (AI service unreachable?)")

    print()
    if failures:
        print(f"{RED}{failures} failed{RESET}, {warnings} warning(s)\n")
        return 1
    print(
        f"{GREEN}all checks passed{RESET}" + (f", {warnings} warning(s)" if warnings else "") + "\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
