#!/usr/bin/env python3
"""Fill a running stack with log traffic that looks like a real system.

Used for screenshots, demos, and having something on screen when someone else
is driving. The mix is deliberately boring: mostly INFO and DEBUG, a thin tail
of warnings and errors, and the occasional genuine incident, so the anomaly rate
lands somewhere believable instead of the 65% you get from hammering the API
with CRITICAL test rows.

    python scripts/seed_demo.py                 # 120 logs over the last 30 min
    python scripts/seed_demo.py --count 300
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta

SERVICES = [
    "payment-api",
    "auth-service",
    "api-gateway",
    "checkout-worker",
    "inventory-svc",
    "notification-worker",
]

# (level, weight, templates). Weights give a realistic pyramid: most traffic is
# uneventful, incidents are rare.
TRAFFIC: list[tuple[str, int, list[str]]] = [
    (
        "DEBUG",
        26,
        [
            "cache hit for session:{hex}",
            "connection pool: {small}/50 active",
            "span exported to collector in {ms}ms",
            "config reloaded, {small} keys",
        ],
    ),
    (
        "INFO",
        46,
        [
            "GET /v1/orders/{id} 200 in {ms}ms",
            "POST /v1/checkout 201 in {ms}ms",
            "user {id} authenticated via oauth",
            "published order.created to topic orders",
            "processed {small} events from queue",
            "scheduled reconciliation finished in {ms}ms",
            "health check ok",
        ],
    ),
    (
        "WARNING",
        14,
        [
            "retrying upstream call, attempt 2 of 3",
            "connection pool at 85% capacity",
            "slow query: SELECT on orders took {ms}ms",
            "rate limit approaching for client 10.0.{small}.{small}",
            "deprecated api version v1 called by mobile-ios/3.2.1",
        ],
    ),
    (
        "ERROR",
        10,
        [
            "failed to charge card: gateway returned 402",
            "upstream timeout calling inventory-svc after 5000ms",
            "could not acquire lock on order {id}",
            "webhook delivery failed, will retry in {small}s",
            "unhandled exception in request handler",
        ],
    ),
    (
        "CRITICAL",
        4,
        [
            "database connection refused, request failed",
            "out of memory: killed worker process {id}",
            "deadlock detected on table orders",
            "payment provider unreachable, circuit breaker open",
        ],
    ),
]


def _post(url: str, payload: dict) -> dict | None:
    request = urllib.request.Request(  # noqa: S310
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
            return json.loads(response.read())
    except (urllib.error.URLError, OSError) as exc:
        print(f"  request failed: {exc}", file=sys.stderr)
        return None


def _message(template: str, rng: random.Random) -> str:
    return template.format(
        id=rng.randint(1000, 99999),
        ms=rng.randint(3, 900),
        small=rng.randint(1, 48),
        hex=f"{rng.getrandbits(32):08x}",
    )


def seed(base: str, count: int, minutes: int, seed_value: int) -> None:
    rng = random.Random(seed_value)
    levels = [level for level, weight, _ in TRAFFIC for _ in range(weight)]
    templates = {level: msgs for level, _, msgs in TRAFFIC}

    now = datetime.now(UTC)
    created: list[dict] = []

    for index in range(count):
        level = rng.choice(levels)
        # Spread backwards from now so the time column reads like a live feed.
        offset = timedelta(seconds=(count - index) * (minutes * 60 / count))
        payload = {
            "service": rng.choice(SERVICES),
            "level": level,
            "message": _message(rng.choice(templates[level]), rng),
            "timestamp": (now - offset).isoformat(),
        }
        record = _post(f"{base}/logs", payload)
        if record:
            created.append(record)

    # A handful of human labels, so the feedback column shows real state rather
    # than a wall of untouched buttons.
    for record in rng.sample(created, min(6, len(created))):
        _post(f"{base}/logs/{record['id']}/feedback", {"is_anomaly": bool(record["is_anomaly"])})

    flagged = sum(1 for record in created if record.get("is_anomaly"))
    rate = flagged / len(created) * 100 if created else 0
    print(f"seeded {len(created)} logs, {flagged} flagged anomalous ({rate:.0f}%)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", nargs="?", default="http://localhost:8000")
    parser.add_argument("--count", type=int, default=120)
    parser.add_argument("--minutes", type=int, default=30, help="window to spread logs over")
    parser.add_argument("--seed", type=int, default=7, help="rng seed, for repeatable demos")
    args = parser.parse_args()

    seed(args.base_url.rstrip("/"), args.count, args.minutes, args.seed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
