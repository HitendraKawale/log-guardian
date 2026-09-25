# Animated security preview

Standalone prototype: frontend/security-prototype.html. Open it directly in a browser;
no server, package installation or external asset request is required by the page.
The UI remains illustrative and does not execute tools or connect to the product API.

## Motion source

The owner requested SVG motion using www.ui-skills.com. The site's skill catalog
provides implementation guidance, not a drop-in animation asset library. This preview
uses original inline SVG and the browser's Web Animations API, following:

https://www.ui-skills.com/skills/raphaelsalaja/12-principles-of-animation

Applied rules: 280 ms ease-out travel, consistent duration, one animated packet at
a time and subtle 180 ms pressed feedback at scale 0.98. No bouncing, backdrop
animation or excessive staggering. A user-started sequence waits 1.8 seconds between
steps so captions can be read; individual packet travel is 280 ms. Pause cancels
motion and pending steps; restart and scenario changes cancel playback. A hidden tab
pauses playback. Reduced motion offers an immediate static walkthrough.

The SVG shows agent to journal request capture, tool to journal completion, and journal
evidence to policy review. Missing completions do not animate a return packet.
The horizontal diagram scrolls within its own region on narrow screens; the textual
timeline gives the same information without requiring motion or horizontal scrolling.

## Added example

A support agent may use search_docs but a retrieved document instructs it to use
send_email. This illustrative run attempts send_email and receives a tool-name
finding. The story does not imply that the recorder stored the retrieved document,
recipient, message body or tool arguments. It does not prove injection causation or
that an email was actually delivered. Shadow mode does not block the invocation.

## Executed verification

From any directory, using the repo's existing Playwright installation:

```bash
/Users/hitesh/log-guardian/.venv/bin/python docs/verification/security-preview/check-motion.py.txt --screenshots /tmp/lg47-motion-check
```

Run the relative script path from the preview worktree. It defaults to the local
HTML file URL; use --url to exercise a running server instead.

Output:

```text
PASS: SVG moves, pause/resume, scenario changes, four outcomes, reset, keyboard, reduced motion, mobile layout; no page errors.
```

Also exercised the email SVG sequence in Agent Browser at
http://127.0.0.1:8477/security-prototype.html. Desktop and mobile screenshots were
inspected. Screenshots are local verification artifacts in /tmp/lg47-motion-check,
not screenshots of a deployed production feature.

This preview is on feat/47-security-preview, separate from the product implementation
branch. The complete product API/UI and README animation remain future work.
