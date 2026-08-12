#!/usr/bin/env python3
"""Produce the dashboard screenshot and demo recording used in the README.

Separate from tests/e2e on purpose: those capture whatever state the test run
happened to leave behind, which is the right thing for evidence and the wrong
thing for a README. This drives a scripted walkthrough at human pace against
seeded data.

    python scripts/seed_demo.py       # realistic traffic first
    python scripts/capture_demo.py    # -> docs/images/

Needs ffmpeg on PATH for the GIF; without it the .webm is still written.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parents[1]
IMAGES = REPO_ROOT / "docs" / "images"
VIDEO_TMP = REPO_ROOT / "docs" / "images" / ".video"

VIEWPORT = {"width": 1440, "height": 900}
INCIDENT = "payment provider unreachable, circuit breaker open"


def _gif(webm: Path, gif: Path, width: int = 960, fps: int = 12) -> bool:
    """Convert with a generated palette; the default 256-colour quantisation
    turns the dark UI into mud."""
    if not shutil.which("ffmpeg"):
        print("  ffmpeg not found, keeping .webm only")
        return False
    palette = webm.with_suffix(".png")
    scale = f"fps={fps},scale={width}:-1:flags=lanczos"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(webm),
            "-vf",
            f"{scale},palettegen=stats_mode=diff",
            str(palette),
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(webm),
            "-i",
            str(palette),
            "-lavfi",
            f"{scale}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=3",
            str(gif),
        ],
        check=True,
        capture_output=True,
    )
    palette.unlink(missing_ok=True)
    return True


def capture(dashboard_url: str) -> None:
    IMAGES.mkdir(parents=True, exist_ok=True)
    VIDEO_TMP.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()

        # --- stills, at 2x so they stay sharp on a retina display -----------
        context = browser.new_context(viewport=VIEWPORT, device_scale_factor=2)
        page = context.new_page()
        page.goto(dashboard_url)
        page.wait_for_selector("#logs-body tr", timeout=20_000)
        page.wait_for_timeout(1500)

        page.screenshot(path=str(IMAGES / "dashboard.png"))
        print(f"  wrote {IMAGES / 'dashboard.png'}")

        page.set_viewport_size({"width": 430, "height": 932})
        page.wait_for_timeout(1000)
        page.screenshot(path=str(IMAGES / "dashboard-mobile.png"))
        print(f"  wrote {IMAGES / 'dashboard-mobile.png'}")
        context.close()

        # --- the walkthrough ------------------------------------------------
        context = browser.new_context(
            viewport=VIEWPORT,
            record_video_dir=str(VIDEO_TMP),
            record_video_size=VIEWPORT,
        )
        page = context.new_page()
        page.goto(dashboard_url)
        page.wait_for_selector("#logs-body tr", timeout=20_000)
        page.wait_for_timeout(2500)  # let the viewer read the stat cards

        form = page.locator("#log-form")
        form.locator('input[name="service"]').fill("payment-api")
        page.wait_for_timeout(400)
        form.locator('select[name="level"]').select_option("CRITICAL")
        page.wait_for_timeout(400)
        # type() rather than fill(), so the recording shows it being written
        form.locator('input[name="message"]').fill("")
        form.locator('input[name="message"]').type(INCIDENT, delay=28)
        page.wait_for_timeout(700)
        form.locator('button[type="submit"]').click()

        row = page.locator("#logs-body tr", has_text=INCIDENT).first
        row.wait_for(timeout=15_000)
        page.wait_for_timeout(2200)  # the new row, scored and flagged high

        row.locator(".fb-btn").first.click()  # a reviewer confirms the anomaly
        page.wait_for_timeout(2600)

        page.locator("#f-anomalous").check()  # filter down to anomalies
        page.wait_for_timeout(3000)
        page.locator("#f-anomalous").uncheck()
        page.wait_for_timeout(1500)

        context.close()  # video is only flushed on close
        browser.close()

    videos = sorted(VIDEO_TMP.glob("*.webm"), key=lambda f: f.stat().st_mtime)
    if not videos:
        sys.exit("playwright wrote no video")

    webm = IMAGES / "demo.webm"
    shutil.move(str(videos[-1]), webm)
    shutil.rmtree(VIDEO_TMP, ignore_errors=True)
    print(f"  wrote {webm} ({webm.stat().st_size / 1e6:.1f} MB)")

    gif = IMAGES / "demo.gif"
    if _gif(webm, gif):
        print(f"  wrote {gif} ({gif.stat().st_size / 1e6:.1f} MB)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frontend", default="http://localhost:8080")
    parser.add_argument("--api", default="http://localhost:8000")
    args = parser.parse_args()

    capture(f"{args.frontend}/?api={args.api}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
