from datetime import UTC, datetime
from pathlib import Path

from ml.data.bgl import LEVEL_MAP, ParseStats, load, parse_line

FIXTURE = Path(__file__).parent / "fixtures" / "bgl_sample.log"

# 16 real lines lifted out of BGL.log: 5 normal, 5 alerts, 4 with a severity
# field the format does not define, 2 truncated before the message.
EXPECTED_PARSED = 10
EXPECTED_UNKNOWN_LEVEL = 4
EXPECTED_MALFORMED = 2

NORMAL = (
    "- 1117838570 2005.06.03 R02-M1-N0-C:J12-U11 2005-06-03-15.42.50.363779 "
    "R02-M1-N0-C:J12-U11 RAS KERNEL INFO instruction cache parity error corrected\n"
)
ALERT = (
    "APPREAD 1117869872 2005.06.04 R23-M1-N8-I:J18-U11 2005-06-04-00.24.32.398284 "
    "R23-M1-N8-I:J18-U11 RAS APP FATAL ciod: failed to read message prefix\n"
)


def test_parses_a_normal_line():
    record = parse_line(NORMAL)
    assert record == {
        "timestamp": datetime(2005, 6, 3, 22, 42, 50, tzinfo=UTC),
        "service": "kernel",
        "level": "INFO",
        "message": "instruction cache parity error corrected",
        "label": 0,
        "category": None,
    }


def test_alert_line_keeps_its_category():
    record = parse_line(ALERT)
    assert record["label"] == 1
    assert record["category"] == "APPREAD"
    assert record["level"] == "CRITICAL"
    assert record["service"] == "app"


def test_timestamp_comes_from_the_utc_epoch_not_the_local_string():
    # The line's other time field reads 15.42.50 (Livermore local); the epoch
    # is 22:42:50 UTC. Using the wrong one would shift hour-of-day by 7.
    assert parse_line(NORMAL)["timestamp"].hour == 22


def test_truncated_line_is_rejected():
    truncated = "- 1120866514 2005.07.08 R02-M1 2005-07-08-16.48.34 R02-M1 RAS KERNEL FATAL\n"
    assert parse_line(truncated) is None


def test_undefined_severity_is_rejected():
    assert parse_line(NORMAL.replace(" INFO ", " Kill ")) is None


def test_severity_mapping_collapses_onto_the_platform_enum():
    assert LEVEL_MAP["FATAL"] == "CRITICAL"
    assert LEVEL_MAP["FAILURE"] == "CRITICAL"
    assert LEVEL_MAP["SEVERE"] == "ERROR"
    assert set(LEVEL_MAP.values()) <= {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def test_load_counts_every_line_it_skips():
    stats = ParseStats()
    records = list(load(FIXTURE, stats=stats))

    assert len(records) == EXPECTED_PARSED
    assert stats.parsed == EXPECTED_PARSED
    assert stats.unknown_level == EXPECTED_UNKNOWN_LEVEL
    assert stats.malformed == EXPECTED_MALFORMED
    # Nothing disappears without being accounted for.
    assert stats.total == stats.parsed + stats.dropped


def test_load_respects_limit():
    assert len(list(load(FIXTURE, limit=3))) == 3


def test_fixture_has_both_classes():
    labels = {record["label"] for record in load(FIXTURE)}
    assert labels == {0, 1}
