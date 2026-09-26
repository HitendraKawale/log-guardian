"""Inspect normalized security logs offline; owner configuration is separate from events."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/ingestion-service"))

from app.security_evidence import MAX_BYTES, decode_json, inspect_bundle  # noqa: E402


def read_bounded(path: Path, limit: int) -> bytes:
    if not path.is_file():
        raise ValueError("input_read_failed")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("byte_limit")
    return raw


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog="Example: python evals/security_evidence.py --config owner.json "
        "--source gateway=gateway.jsonl --source authentication=auth.jsonl\n"
        "JSON report on stdout; errors on stderr, exit 2. No network, model, or file writes. "
        "Inputs are normalized JSONL, not raw gateway logs. Use an empty file for a source "
        "with no supplied events; this never proves collection completeness.",
    )
    parser.add_argument(
        "--config", type=Path, required=True, help="Owner scope and source settings JSON"
    )
    parser.add_argument(
        "--source",
        action="append",
        required=True,
        metavar="ID=PATH",
        help="One JSONL file per configured source; repeat up to four times",
    )
    args = parser.parse_args(argv)
    try:
        if len(args.source) > 4:
            raise ValueError("source_limit")
        paths = {}
        for argument in args.source:
            name, separator, path = argument.partition("=")
            if not separator or not name or not path or name in paths:
                raise ValueError("invalid_source_arguments")
            paths[name] = Path(path)
        config = decode_json(read_bounded(args.config, 16 * 1024))
        remaining, inputs = MAX_BYTES, {}
        for name, path in paths.items():
            inputs[name] = read_bounded(path, remaining)
            remaining -= len(inputs[name])
        report = inspect_bundle(config, inputs)
    except OSError:
        print("error: input_read_failed", file=sys.stderr)
        return 2
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
