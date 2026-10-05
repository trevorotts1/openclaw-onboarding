#!/usr/bin/env python3
"""Render a page HTML at multiple viewport widths with Playwright (Chromium).

render_page.py <html> --out <dir> [--widths 320,390,768,1440]

Before every screenshot the page is forced fully loaded:
  1. every <img> is set to loading="eager";
  2. the page is scrolled to the bottom in 400px steps (triggers lazy content);
  3. wait until every img.complete && img.naturalWidth > 0 -- 30s timeout,
     exit 1 naming the images that never loaded;
  4. wait for document.fonts.ready.

Outputs per width W:
  <out>/W.png         full-page screenshot at width W
  <out>/part-NN.png   vertical pieces of at most 4000px height (part-01, ...)

With a single width the part files sit flat in <out> (the stage layout:
one render call per output folder). With several widths in one call they
would overwrite each other, so they go to <out>/<W>/part-NN.png instead.

Exit codes: 0 ok; 1 page failures (images that never loaded);
2 unreadable input or unusable environment (missing HTML, bad --widths,
Playwright/Chromium unavailable).
"""
import argparse
import sys
import time
from pathlib import Path

IMG_WAIT_SECONDS = 30
POLL_SECONDS = 0.25
SCROLL_STEP = 400
SCROLL_SETTLE_SECONDS = 0.05
MAX_PART_HEIGHT = 4000
VIEWPORT_HEIGHT = 1000

EAGER_JS = (
    "() => { document.querySelectorAll('img').forEach(i => { i.loading = 'eager'; }); }"
)
SCROLL_JS = "y => window.scrollTo(0, y)"
HEIGHT_JS = (
    "() => (document.scrollingElement || document.body).scrollHeight"
)
UNLOADED_JS = (
    "() => Array.from(document.images)"
    ".filter(i => !(i.complete && i.naturalWidth > 0))"
    ".map(i => ({src: i.getAttribute('src') || i.currentSrc || '<no src>',"
    " alt: i.getAttribute('alt') || ''}))"
)
FONTS_READY_JS = "() => document.fonts.ready.then(() => true)"


def eager_scroll_wait(page, timeout_seconds=IMG_WAIT_SECONDS):
    """Force-load images; return a list of image dicts that never loaded."""
    page.evaluate(EAGER_JS)
    height = page.evaluate(HEIGHT_JS)
    y = 0
    while y < height:
        page.evaluate(SCROLL_JS, y)
        time.sleep(SCROLL_SETTLE_SECONDS)
        y += SCROLL_STEP
    page.evaluate(SCROLL_JS, height)
    deadline = time.monotonic() + timeout_seconds
    failures = page.evaluate(UNLOADED_JS)
    while failures and time.monotonic() < deadline:
        time.sleep(POLL_SECONDS)
        failures = page.evaluate(UNLOADED_JS)
    return failures or []


def split_parts(png_path, out_dir, max_height=MAX_PART_HEIGHT):
    """Split a full-page screenshot into part-NN.png pieces of <= max_height."""
    from PIL import Image

    out_dir.mkdir(parents=True, exist_ok=True)
    im = Image.open(png_path)
    im.load()
    width, height = im.size
    number = 0
    top = 0
    paths = []
    while top < height:
        number += 1
        piece_h = min(max_height, height - top)
        piece = im.crop((0, top, width, top + piece_h))
        piece_path = out_dir / f"part-{number:02d}.png"
        piece.save(piece_path)
        paths.append(piece_path)
        top += piece_h
    return paths


def parse_widths(raw):
    widths = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            value = int(token)
        except ValueError:
            raise ValueError(f"width '{token}' is not an integer")
        if value <= 0:
            raise ValueError(f"width '{token}' must be positive")
        if value not in widths:
            widths.append(value)
    if not widths:
        raise ValueError("at least one width is required")
    return widths


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("html", help="path to the HTML file to render")
    parser.add_argument("--out", required=True, help="output directory")
    parser.add_argument(
        "--widths",
        default="320,390,768,1440",
        help="comma-separated viewport widths (default 320,390,768,1440)",
    )
    args = parser.parse_args(argv)

    html_path = Path(args.html)
    if not html_path.is_file():
        print(f"ERROR: HTML file not found: {html_path}", file=sys.stderr)
        return 2
    try:
        widths = parse_widths(args.widths)
    except ValueError as exc:
        print(f"ERROR: --widths: {exc}", file=sys.stderr)
        return 2
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        print(f"ERROR: Playwright unavailable: {exc}", file=sys.stderr)
        return 2

    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)
            except Exception as exc:
                print(f"ERROR: Chromium launch failed: {exc}", file=sys.stderr)
                return 2
            try:
                context = browser.new_context(
                    viewport={"width": widths[0], "height": VIEWPORT_HEIGHT},
                    device_scale_factor=1,
                )
                page = context.new_page()
                page.goto(html_path.resolve().as_uri(), wait_until="load")
                for width in widths:
                    page.set_viewport_size(
                        {"width": width, "height": VIEWPORT_HEIGHT}
                    )
                    page.reload(wait_until="load")
                    failures = eager_scroll_wait(page)
                    if failures:
                        for img in failures:
                            print(
                                f"IMG NEVER LOADED: {img['src']}"
                                + (f" (alt: {img['alt']})" if img["alt"] else "")
                            )
                        return 1
                    page.evaluate(FONTS_READY_JS)
                    full_path = out_dir / f"{width}.png"
                    page.screenshot(path=str(full_path), full_page=True)
                    parts_dir = out_dir if len(widths) == 1 else out_dir / str(width)
                    parts = split_parts(full_path, parts_dir)
                    print(
                        f"RENDER OK: {width}px -> {full_path}"
                        f" + {len(parts)} part file(s) in {parts_dir}"
                    )
            finally:
                browser.close()
    except Exception as exc:
        print(f"ERROR: render failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())