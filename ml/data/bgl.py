"""Parser for the BGL log dataset.

Each line is nine space-separated fields followed by free-text content:

    Label Timestamp Date Node Time NodeRepeat Type Component Level Content

    - 1117838570 2005.06.03 R02-M1-N0-C:J12-U11 2005-06-03-15.42.50.363779
      R02-M1-N0-C:J12-U11 RAS KERNEL INFO instruction cache parity error corrected

``Label`` is "-" on a normal line and an alert category (KERNDTLB, APPREAD, ...)
on an anomalous one. Those tags were assigned by LLNL operators, so unlike the
synthetic generator this module replaces, the labels are not a function of the
features we later extract.

Records are emitted in the platform's own log shape (service / level / message /
timestamp) so one featurizer covers both training and the live scoring path.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

# Number of fixed fields before the free-text content.
_PREFIX_FIELDS = 9

# BGL's severity vocabulary mapped onto the platform's LogLevel enum. FATAL and
# FAILURE both collapse to CRITICAL — the enum draws no finer distinction, and
# every labelled alert in BGL carries one of those two anyway.
LEVEL_MAP: dict[str, str] = {
    "INFO": "INFO",
    "WARNING": "WARNING",
    "ERROR": "ERROR",
    "SEVERE": "ERROR",
    "FATAL": "CRITICAL",
    "FAILURE": "CRITICAL",
}


@dataclass
class ParseStats:
    """Counts of what the parser accepted and rejected, so drops stay visible."""

    total: int = 0
    parsed: int = 0
    malformed: int = 0
    unknown_level: int = 0

    @property
    def dropped(self) -> int:
        return self.malformed + self.unknown_level

    def __str__(self) -> str:
        return (
            f"{self.parsed:,} parsed / {self.total:,} lines "
            f"({self.malformed:,} malformed, {self.unknown_level:,} unknown level)"
        )


def parse_line(line: str) -> dict | None:
    """Parse one raw BGL line, or return None if it does not fit the format."""
    parts = line.split(maxsplit=_PREFIX_FIELDS)
    if len(parts) <= _PREFIX_FIELDS:
        return None

    label, epoch, _date, _node, _time, _repeat, _type, component, level, content = parts

    mapped = LEVEL_MAP.get(level.upper())
    if mapped is None:
        return None

    try:
        timestamp = datetime.fromtimestamp(int(epoch), UTC)
    except ValueError:
        return None

    return {
        # The epoch field is UTC; BGL's other time field is Livermore local
        # (UTC-7/-8), so anything hour-of-day derived from this is a UTC hour.
        "timestamp": timestamp,
        "service": component.lower(),
        "level": mapped,
        "message": content.strip(),
        "label": 0 if label == "-" else 1,
        "category": None if label == "-" else label,
    }


def load(
    path: str | Path, limit: int | None = None, stats: ParseStats | None = None
) -> Iterator[dict]:
    """Stream parsed records from a BGL log file.

    The file is 709 MB, so this yields rather than building a list. Pass a
    ``ParseStats`` to find out how many lines were skipped and why.
    """
    stats = stats if stats is not None else ParseStats()
    emitted = 0

    with Path(path).open(errors="replace") as handle:
        for line in handle:
            stats.total += 1
            parts = line.split(maxsplit=_PREFIX_FIELDS)

            if len(parts) <= _PREFIX_FIELDS:
                stats.malformed += 1
                continue
            if parts[8].upper() not in LEVEL_MAP:
                stats.unknown_level += 1
                continue

            record = parse_line(line)
            if record is None:
                stats.malformed += 1
                continue

            stats.parsed += 1
            yield record

            emitted += 1
            if limit is not None and emitted >= limit:
                return
