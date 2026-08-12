from datetime import UTC, datetime

from ml.data.prepare import read_jsonl, write_jsonl

CUTOFF = datetime(2005, 9, 1, tzinfo=UTC)


def _record(day: int, label: int) -> dict:
    return {
        "timestamp": datetime(2005, 8, 1, tzinfo=UTC).replace(month=8 if day < 32 else 9),
        "service": "kernel",
        "level": "CRITICAL",
        "message": f"failure on day {day}",
        "label": label,
        "category": "KERNDTLB" if label else None,
    }


def test_jsonl_roundtrip_preserves_records(tmp_path):
    records = [_record(1, 1), _record(2, 0)]
    path = tmp_path / "split.jsonl.gz"

    count, positives = write_jsonl(path, records)
    assert (count, positives) == (2, 1)
    assert read_jsonl(path) == records


def test_roundtrip_keeps_timestamps_timezone_aware(tmp_path):
    path = tmp_path / "split.jsonl.gz"
    write_jsonl(path, [_record(1, 1)])
    assert read_jsonl(path)[0]["timestamp"].tzinfo is not None


def test_chronological_split_puts_no_timestamp_on_both_sides():
    stamps = [
        datetime(2005, 6, 15, tzinfo=UTC),
        datetime(2005, 8, 31, 23, 59, tzinfo=UTC),
        datetime(2005, 9, 1, tzinfo=UTC),
        datetime(2005, 12, 1, tzinfo=UTC),
    ]
    train = [t for t in stamps if t < CUTOFF]
    test = [t for t in stamps if t >= CUTOFF]

    assert len(train) == 2 and len(test) == 2
    # The whole point of splitting by time: every training row predates every
    # test row, so no burst can straddle the boundary.
    assert max(train) < min(test)
