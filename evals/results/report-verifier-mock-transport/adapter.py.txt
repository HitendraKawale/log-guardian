"""Map verifier requests to provider wire format and rehearse transport with mocks only."""

import argparse
import asyncio
import base64
import json
import os
import time
from decimal import Decimal
from importlib.metadata import version
from pathlib import Path

import httpx
from investigator_pilot import save, sync_directory
from report_verifier_boundary import check_review
from report_verifier_eval import ROOT, encode, preparation, sha, write_new
from validate import unique_object

MODEL = "gpt-4.1-mini-2025-04-14"
ENDPOINT = "https://api.openai.com/v1/chat/completions"
MAX_BODY = 131072
MAX_OUTPUT = 4096
REQUEST_SECONDS = 60
BATCH_SECONDS = 1200
INPUT_PRICE = Decimal("0.40") / 1_000_000
OUTPUT_PRICE = Decimal("1.60") / 1_000_000


def wire_bundle():
    neutral, source = preparation()
    files = {}
    for ident in source["eligible"]:
        item = json.loads(neutral[f"requests/{ident}.json"])
        wire = {
            "model": MODEL,
            "messages": item["messages"],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "report_verifier",
                    "strict": True,
                    "schema": item["response_schema"],
                },
            },
            "store": False,
            "stream": False,
            "temperature": 0,
            "max_completion_tokens": MAX_OUTPUT,
            "service_tier": "default",
        }
        raw = encode(wire)
        reservation(raw, Decimal(0), 0)
        files[f"requests/{ident}.json"] = raw
    manifest = {
        "mode": "offline_wire_preparation",
        "live_enabled": False,
        "model": MODEL,
        "endpoint": ENDPOINT,
        "eligible": source["eligible"],
        "local_invalid": source["local_invalid"],
        "neutral_preparation_sha256": sha(neutral["manifest.json"]),
        "files": {name: sha(raw) for name, raw in files.items()},
        "implementation": {
            name: sha((ROOT / name).read_bytes())
            for name in ("evals/report_verifier_transport.py", "evals/investigator_pilot.py")
        },
        "httpx": version("httpx"),
        "input_usd_per_million": "0.40",
        "output_usd_per_million": "1.60",
    }
    files["manifest.json"] = encode(manifest)
    return files, manifest


def prepare(output: Path):
    files, manifest = wire_bundle()
    write_new(output, files)
    return manifest


def reservation(raw, prior, attempts):
    amount = (len(raw) + 4096) * INPUT_PRICE + MAX_OUTPUT * OUTPUT_PRICE
    if (
        len(raw) > MAX_BODY
        or attempts >= 17
        or amount > Decimal("0.10")
        or prior + amount > Decimal("2")
    ):
        raise ValueError("request or reservation ceiling exceeded")
    return amount


def usage(data, input_bound):
    if (
        not isinstance(data, dict)
        or data.get("model") != MODEL
        or data.get("service_tier") != "default"
    ):
        raise ValueError("provider model or tier mismatch")
    value = data.get("usage")
    fields = ("prompt_tokens", "completion_tokens", "total_tokens")
    if not isinstance(value, dict) or any(
        type(value.get(key)) is not int or value[key] < 0 for key in fields
    ):
        raise ValueError("unknown usage")
    if (
        value["total_tokens"] != value["prompt_tokens"] + value["completion_tokens"]
        or value["prompt_tokens"] > input_bound
        or value["completion_tokens"] > MAX_OUTPUT
    ):
        raise ValueError("usage exceeds reservation or is inconsistent")
    details = value.get("prompt_tokens_details")
    cached = 0
    if details is not None:
        if not isinstance(details, dict):
            raise ValueError("invalid cached usage")
        cached = details.get("cached_tokens", 0)
        if type(cached) is not int or not 0 <= cached <= value["prompt_tokens"]:
            raise ValueError("invalid cached usage")
    return {**{key: value[key] for key in fields}, "cached_tokens": cached}


def payload(data):
    choices = data.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        return None
    choice = choices[0]
    message = choice.get("message")
    if (
        type(choice.get("index")) is not int
        or choice["index"] != 0
        or choice.get("finish_reason") != "stop"
        or not isinstance(message, dict)
        or message.get("role") != "assistant"
        or message.get("refusal") is not None
        or message.get("tool_calls") not in (None, [])
        or message.get("function_call") is not None
        or not isinstance(message.get("content"), str)
    ):
        return None
    try:
        return message["content"].encode("utf-8")
    except UnicodeError:
        return None


def save_bytes(path, raw):
    with path.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    sync_directory(path.parent)


async def exchange(client, raw, deadline, output, ident):
    body, status, complete = bytearray(), None, False
    try:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("deadline expired")
        async with asyncio.timeout(remaining):
            async with client.stream(
                "POST",
                ENDPOINT,
                content=raw,
                headers={"Content-Type": "application/json"},
                timeout=remaining,
            ) as response:
                status = response.status_code
                async for chunk in response.aiter_bytes():
                    body.extend(chunk[: MAX_BODY + 1 - len(body)])
                    if len(body) > MAX_BODY:
                        raise ValueError("provider response exceeds ceiling")
                    if time.monotonic() >= deadline:
                        raise TimeoutError("deadline expired")
                complete = True
    finally:
        if status is not None:
            save(
                output / f"{ident}.http.json",
                {
                    "status": status,
                    "capture_complete": complete,
                    "decoded_body_base64": base64.b64encode(body).decode(),
                    "decoded_body_sha256": sha(body),
                },
            )
    if time.monotonic() >= deadline:
        raise TimeoutError("deadline expired")
    if status != 200:
        raise ValueError("provider HTTP failure")
    return bytes(body)


async def run_mock(bundle: Path, output: Path, transport):
    if type(transport) is not httpx.MockTransport:
        raise ValueError("offline preparation requires exactly httpx.MockTransport")
    expected, manifest = wire_bundle()
    for name, raw in expected.items():
        if (bundle / name).read_bytes() != raw:
            raise ValueError("wire preparation changed")
    neutral, _ = preparation()
    items = {json.loads(line)["item_id"]: line for line in neutral["inputs.jsonl"].splitlines()}
    cases = {
        ident: "local_invalid" if ident in manifest["local_invalid"] else "not_attempted"
        for ident in items
    }
    output.mkdir(parents=True, exist_ok=False)
    sync_directory(output.parent)
    (output / "responses").mkdir()
    save(
        output / "manifest.json",
        {
            "mode": "mock",
            "paid_requests": 0,
            "wire_manifest_sha256": sha(expected["manifest.json"]),
        },
    )
    records, reserved, fatal = [], Decimal(0), None
    batch_deadline = time.monotonic() + BATCH_SECONDS
    async with httpx.AsyncClient(
        transport=transport, trust_env=False, follow_redirects=False, timeout=REQUEST_SECONDS
    ) as client:
        for ident in manifest["eligible"]:
            if time.monotonic() >= batch_deadline:
                fatal = "batch_deadline"
                break
            raw = expected[f"requests/{ident}.json"]
            amount = reservation(raw, reserved, len(records))
            record = {
                "item_id": ident,
                "mode": "mock",
                "wire_sha256": sha(raw),
                "request": json.loads(raw),
                "simulated_reserved_usd": str(amount),
                "input_token_bound": len(raw) + 4096,
                "usage": None,
                "simulated_cost_upper_usd": None,
                "status": "reserved_attempt_may_have_been_sent",
            }
            save(output / f"{ident}.reservation.json", record)
            records.append(record)
            reserved += amount
            cases[ident] = "unknown"
            started = time.monotonic()
            try:
                body = await exchange(
                    client, raw, min(batch_deadline, started + REQUEST_SECONDS), output, ident
                )
                data = json.loads(body.decode("utf-8"), object_pairs_hook=unique_object)
                encode(data)  # Reject non-finite values before using provider metadata.
                record["usage"] = usage(data, record["input_token_bound"])
                cost = (
                    record["usage"]["prompt_tokens"] * INPUT_PRICE
                    + record["usage"]["completion_tokens"] * OUTPUT_PRICE
                )
                if cost > amount:
                    raise ValueError("cost exceeds reservation")
                record["simulated_cost_upper_usd"] = str(cost)
                content = payload(data)
                if content is not None:
                    save_bytes(output / "responses" / f"{ident}.json", content[:16385])
                record["review"] = check_review(items[ident], content)
                cases[ident] = (
                    "verifier_error"
                    if record["review"]["reason_codes"] == ["verifier_error"]
                    else record["review"]["disposition"]
                )
            except (httpx.HTTPError, TimeoutError, ValueError, TypeError, KeyError) as exc:
                fatal = type(exc).__name__
                record["error_type"] = fatal
                cases[ident] = "transport_failed"
            record["elapsed_seconds"] = time.monotonic() - started
            record["status"] = cases[ident]
            save(output / f"{ident}.result.json", record)
            if fatal:
                break
    summary = {
        "mode": "mock",
        "paid_requests": 0,
        "attempted": len(records),
        "cases": cases,
        "fatal": fatal,
        "usage_complete": all(r["usage"] is not None for r in records),
        "simulated_reserved_usd": str(reserved),
        "simulated_known_cost_upper_usd": str(
            sum(
                (
                    Decimal(r["simulated_cost_upper_usd"])
                    for r in records
                    if r["simulated_cost_upper_usd"] is not None
                ),
                Decimal(0),
            )
        ),
    }
    save(output / "summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog="Example: python evals/report_verifier_transport.py --output /tmp/verifier-wire",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="New directory for offline wire artifacts; no request is sent",
    )
    args = parser.parse_args()
    try:
        manifest = prepare(args.output)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(
        json.dumps(
            {
                "mode": "offline_wire_preparation",
                "requests": len(manifest["eligible"]),
                "live_enabled": False,
                "output": str(args.output),
            }
        )
    )


if __name__ == "__main__":
    main()
