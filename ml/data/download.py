"""Fetch raw log datasets from Loghub's Zenodo archive.

Loghub (https://github.com/logpai/loghub) publishes the standard public log
datasets used in the anomaly-detection literature. We use BGL: 4.7M lines from
a BlueGene/L supercomputer, where each line is tagged with an alert category or
"-" for normal. Those tags are real operator-assigned labels, which is the whole
reason to prefer it over anything we could generate ourselves.

Usage:
    python ml/data/download.py           # ~55 MB zipped, 709 MB extracted
"""

from __future__ import annotations

import sys
import urllib.request
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = REPO_ROOT / "ml" / "datasets"

BGL_URL = "https://zenodo.org/api/records/8196385/files/BGL.zip/content"
BGL_ARCHIVE = DATASET_DIR / "BGL.zip"
BGL_LOG = DATASET_DIR / "BGL.log"


def _report(read: int, total: int) -> None:
    if total <= 0:
        return
    pct = read / total * 100
    sys.stderr.write(f"\r  {pct:5.1f}%  ({read / 1e6:.0f}/{total / 1e6:.0f} MB)")
    sys.stderr.flush()


def _download(url: str, dest: Path) -> None:
    with urllib.request.urlopen(url) as response:  # noqa: S310 - fixed https URL
        total = int(response.headers.get("Content-Length", 0))
        read = 0
        with dest.open("wb") as handle:
            while chunk := response.read(1 << 20):
                handle.write(chunk)
                read += len(chunk)
                _report(read, total)
    sys.stderr.write("\n")


def fetch_bgl(force: bool = False) -> Path:
    """Download and extract BGL.log, skipping work that is already done."""
    DATASET_DIR.mkdir(parents=True, exist_ok=True)

    if BGL_LOG.exists() and not force:
        print(f"Already present: {BGL_LOG} ({BGL_LOG.stat().st_size / 1e6:.0f} MB)")
        return BGL_LOG

    if not BGL_ARCHIVE.exists() or force:
        print(f"Downloading BGL from Zenodo -> {BGL_ARCHIVE}")
        _download(BGL_URL, BGL_ARCHIVE)

    print(f"Extracting -> {BGL_LOG}")
    with zipfile.ZipFile(BGL_ARCHIVE) as archive:
        archive.extract("BGL.log", DATASET_DIR)

    print(f"Ready: {BGL_LOG} ({BGL_LOG.stat().st_size / 1e6:.0f} MB)")
    return BGL_LOG


if __name__ == "__main__":
    fetch_bgl(force="--force" in sys.argv)
