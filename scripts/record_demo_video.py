"""Record the ~90-second portfolio demonstration from the static recorded demo.

The page itself carries the "Recorded demo" banner, so the video cannot pass
recorded artifacts off as current model execution. The flow shows an observed
failure, the adaptive investigation's tool activity, clickable evidence, the
honest supported conclusion, and the separate inconclusive example.
"""

import subprocess
import sys
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/media"


def pause(seconds: float) -> None:
    time.sleep(seconds)


def main() -> int:
    subprocess.run([sys.executable, str(ROOT / "scripts/export_static_demo.py")], check=True)
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(ROOT / "site"))
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            record_video_dir=str(OUTPUT),
            record_video_size={"width": 1280, "height": 720},
        )
        page = context.new_page()
        started = time.monotonic()
        page.goto(url)
        pause(6)  # Banner: recorded demo, no live execution.
        # Observed failure: the supported case's evidence begins with real errors.
        page.locator(".inv-item-btn").first.click()
        pause(8)
        events = page.locator("#inv-events li")
        for index in range(min(events.count(), 3)):
            events.nth(index).scroll_into_view_if_needed()
            pause(5)
        page.locator("#inv-report-section").scroll_into_view_if_needed()
        pause(8)  # Honest supported conclusion with citations.
        page.locator("#inv-report .citation").first.click()
        pause(8)  # Clickable evidence drawer showing the cited record.
        page.keyboard.press("Escape")
        pause(2)
        # Separate inconclusive example: gaps, not a fabricated cause.
        page.locator(".inv-item-btn", has_text="search timeouts").click()
        pause(6)
        page.locator("#inv-report-section").scroll_into_view_if_needed()
        pause(10)
        page.locator("#inv-report .citation").first.click()
        pause(6)
        page.keyboard.press("Escape")
        # Recorded scorecard for context.
        page.locator('.tab[data-view="evaluations"]').click()
        pause(10)
        page.mouse.wheel(0, 600)
        pause(8)
        elapsed = time.monotonic() - started
        video = page.video
        context.close()
        path = Path(video.path())
        browser.close()
    final = OUTPUT / "demo-90s.webm"
    path.rename(final)
    server.shutdown()
    print(f"recorded {elapsed:.1f}s -> {final} ({final.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
