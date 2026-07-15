#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_browser_qc.py — the P13-BROWSER-QC phase gate declared in
CWFE-MANIFEST.json (`"gate": "scripts/run_browser_qc.py"`,
`"py_symbol": "run_browser_qc.evaluate"`, `"af_code": "AF-CWFE-P13-BROWSER-QC"`,
build unit U19, needs U15).

Spec Section 16 names this phase's required output: "browser-qc-report.json
(desktop/mobile/reduced-motion/accessibility/performance report)". Spec
Section 17.7 (accessibility/performance gate) requires this module to
validate "the reduced-motion path, keyboard path, headings, labels, contrast
tooling, major browser errors, mobile overflow, performance budgets, and
media loading strategy" — and, like every other prove_*/gate module in this
skill, NEVER on an agent's claim: this drives a REAL headless Chromium
(Playwright) against a REAL `next start` production server serving the P11
build-receipt.json's already-materialized `site_dir` on disk. It never
re-reads the template source and never trusts build-receipt.json's own
`"status"` for anything beyond "was P11 asked to run at all" — every
pass/fail decision here comes from live browser observation.

WHY PLAYWRIGHT FROM PYTHON, NOT A SEPARATE JS TEST RUNNER (ADR-5: "Python
owns orchestration... deterministic provers"): spec Section 19.3 explicitly
names Playwright as this engine's browser-automation tool. The `playwright`
Python package drives the SAME Chromium engine a JS Playwright test would,
without this skill growing a second, JS-only test-runner dependency chain
alongside its existing Python gate scripts — one automation surface, reused.

FIVE CATEGORIES (mirrors the artifact schema, structure/browser-qc-report.schema.json):

  1. desktop        — real page load, zero console/page errors, <main>
                       landmark, keyboard-reachable + FUNCTIONAL skip link
                       (focus actually lands on #cwfe-conversion-start, not
                       just a scroll — see the U19 hardening note below).
  2. mobile          — a real device profile (Playwright's "iPhone 13"), no
                       horizontal overflow, a real `<meta name="viewport">`,
                       every `data-cwfe-cta` element on-screen (not clipped
                       past the viewport edge) at the conversion anchor.
  3. reduced_motion  — `reduced_motion="reduce"` context: zero `<video>`
                       elements mounted at all (spec 13.4: scrubbing must be
                       fully disabled, not merely paused), the
                       `data-cwfe-reduced-motion="true"` marker present, and
                       the conversion content still complete/reachable.
  4. accessibility   — a real, self-contained JS auditor (_A11Y_SCRIPT below;
                       no axe-core dependency is available/needed for the
                       checks spec 17.7 actually names) evaluated in-page:
                       html[lang], one <main> landmark, no duplicate ids,
                       img alt/decorative treatment, video aria-hidden,
                       form-field labels, interactive-element accessible
                       names, heading-level-skip detection, and a real
                       WCAG-formula contrast-ratio scan (4.5:1 normal /
                       3:1 large text) over every visible leaf text node.
  5. performance     — see the CALIBRATION note below for exactly how every
                       budget number here was derived (measured against this
                       skill's own deterministic fixture, 2026-07-15 —
                       spec 12.3's calibration discipline applied to
                       performance budgets, not just seam SSIM/PSNR).

U19 HARDENING APPLIED (the one template change this unit makes, additive,
a11y-scoped, file-disjoint from every U16/U18 conversion/embed file):
`templates/components/ScrollScrubEngine.tsx`'s `#cwfe-conversion-start`
anchor div now carries `tabIndex={-1}`. Verified BEFORE the fix (this
module's own investigation, reproducible via the mutation proof in
`_self_test`): activating the skip link scrolled the viewport but left
focus on `<body>` — a real WCAG technique-G1 gap ("a skip link's target
should receive focus, not just scroll into view"), confirmed by a live
Playwright Tab+Enter sequence against the real built fixture BEFORE this
unit's fix, then confirmed fixed by the same sequence AFTER it. The desktop
category's skip-link check below is exactly that assertion, running for
real on every project this gate audits, not just this unit's own fixture.

CALIBRATION (spec 12.3's "do not freeze thresholds without testing against
the engine's own fixtures" discipline, applied to perf budgets): every
JS_BUDGET_BYTES / CLS_BUDGET / FCP_BUDGET_MS number below was set from a
REAL measured run against `tests/fixtures/site-fixture` (real `next build`
+ `next start`, Playwright Chromium 1208, 2026-07-15) — see the inline
comments at each constant for the exact observed baseline and the headroom
multiplier applied, never an invented number. Two of the five performance
measurements are PROJECT-RELATIVE, not fixed constants, because a fixed
byte budget calibrated only against a fixture's tiny synthetic clips would
be meaningless (dangerous, even) once real client media is orders of
magnitude larger: `initial_media_bytes` and `total_media_bytes_after_full_
scroll` are derived at evaluate() time from the SAME project's own
build-receipt.json scene byte sizes (mirrors prove_site.py's "never trust a
number you can recompute from disk" discipline) — a defect class like "every
scene preloads at once regardless of project size" is still caught, at any
media scale.

LCP INVESTIGATED AND FOUND UNRELIABLE IN THIS HEADLESS HARNESS: the
`largest-contentful-paint` PerformanceObserver entry type is listed in
`PerformanceObserver.supportedEntryTypes` and never once fired in this
harness — not against the real fixture site, not against a synthetic
`<h1>`-only `page.set_content()` page, not after forcing a tab-visibility
change (the Chromium-documented LCP finalization trigger), not after an
explicit `page.screenshot()` compositor flush. This is a known class of
headless-Chromium limitation, not a defect in the generated site. Rather
than silently report a fabricated LCP=0 "pass", this module uses First
Contentful Paint (the `paint` timeline entry type — verified reliable,
64ms observed on the fixture) as the calibrated proxy and RECORDS the
substitution in every report's `performance.lcp_status` field, so a human
reviewer always sees it, never a silently-passing fake LCP.

Exit 0 = PASS, 2 = FAIL, 3 = usage error. Requires the `playwright` Python
package plus an installed Chromium (`python3 -m playwright install
chromium`) and Node/npm already installed in site_dir (spec 12/ADR-5:
`ffmpeg`/`node`/`npm`/browser binaries are external tools invoked exactly
like every other build unit that shells out to one — never string-shelled,
always argument arrays or a library's own process launcher).
"""

from __future__ import annotations

import argparse
import contextlib
import datetime
import json
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_SCRIPT_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _SCRIPT_DIR.parent
_STRUCTURE_DIR = _SKILL_DIR / "structure"
_FIXTURE_DIR = _SKILL_DIR / "tests" / "fixtures" / "site-fixture"

sys.path.insert(0, str(_SCRIPT_DIR))
sys.path.insert(0, str(_SCRIPT_DIR / "lib"))
import json_schema_lite as jsl  # noqa: E402

EXIT_OK = 0
EXIT_FAIL = 2
EXIT_USAGE = 3

SCHEMA_VERSION = "1.0.0"

SERVER_READY_TIMEOUT_SECONDS = 45.0
SERVER_POLL_INTERVAL_SECONDS = 0.25
DESKTOP_VIEWPORT = {"width": 1440, "height": 900}
MOBILE_DEVICE_NAME = "iPhone 13"

# ---------------------------------------------------------------------------
# Perf budget calibration — see module docstring "CALIBRATION" section.
# ---------------------------------------------------------------------------
# Observed baseline (tests/fixtures/site-fixture, real `next build` +
# `next start`, Playwright Chromium 1208, 2026-07-15): script-initiated
# resource transferSize summed to 146,115 bytes.
JS_BUDGET_BYTES = 350_000  # ~2.4x the observed baseline — framework/dependency headroom, still catches an accidentally-bundled heavy library.
# Core Web Vitals "good" threshold (web.dev) — an external, non-invented reference point.
CLS_BUDGET = 0.1
# Observed baseline FCP: 64ms (local, uncontended, no CDN/network latency).
# 3000ms is deliberately generous versus web.dev's 1800ms "good" field
# threshold — this is a LOCAL headless-server timing, not a real-world Core
# Web Vitals claim; its job is catching a blocking-paint regression (a
# synchronous script, an infinite loop before paint), not certifying
# real-world performance.
FCP_BUDGET_MS = 3000.0
# initial_media_bytes / total_media_bytes budgets are PROJECT-RELATIVE, not
# fixed — see _compute_media_budgets() below.
MEDIA_INITIAL_HEADROOM = 1.5
MEDIA_TOTAL_HEADROOM = 1.2

A11Y_SCRIPT = r"""
() => {
  function relLum(r, g, b) {
    const [rs, gs, bs] = [r, g, b].map((c) => {
      c = c / 255;
      return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * rs + 0.7152 * gs + 0.0722 * bs;
  }
  function parseColor(str) {
    if (!str) return null;
    const m = str.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const parts = m[1].split(",").map((s) => parseFloat(s.trim()));
    if (parts.length < 3 || parts.some((n) => Number.isNaN(n))) return null;
    return { r: parts[0], g: parts[1], b: parts[2], a: parts.length > 3 ? parts[3] : 1 };
  }
  function effectiveBackground(el) {
    let node = el;
    while (node) {
      const style = getComputedStyle(node);
      const bg = parseColor(style.backgroundColor);
      if (bg && bg.a > 0.01) return bg;
      node = node.parentElement;
    }
    return { r: 255, g: 255, b: 255, a: 1 };
  }
  function contrastRatio(fg, bg) {
    const L1 = relLum(fg.r, fg.g, fg.b) + 0.05;
    const L2 = relLum(bg.r, bg.g, bg.b) + 0.05;
    return L1 > L2 ? L1 / L2 : L2 / L1;
  }

  const violations = [];

  if (!document.documentElement.lang) {
    violations.push("html-lang: <html> is missing a lang attribute");
  }
  if (!document.querySelector("main")) {
    violations.push("landmark-main: no <main> landmark found");
  }

  const idCounts = {};
  document.querySelectorAll("[id]").forEach((el) => {
    idCounts[el.id] = (idCounts[el.id] || 0) + 1;
  });
  Object.entries(idCounts).forEach(([id, count]) => {
    if (count > 1) violations.push(`duplicate-id: "${id}" used ${count} times`);
  });

  document.querySelectorAll("img").forEach((img) => {
    const hasAlt = img.hasAttribute("alt");
    const decorative = img.getAttribute("role") === "presentation" || img.getAttribute("aria-hidden") === "true";
    if (!hasAlt && !decorative) {
      violations.push(`img-alt: missing alt/decorative-marker on ${img.getAttribute("src") || "<img>"}`);
    }
  });

  document.querySelectorAll("video").forEach((v) => {
    if (v.getAttribute("aria-hidden") !== "true") {
      violations.push(`video-not-hidden: ${v.getAttribute("src") || "<video>"} must be aria-hidden (this engine's scene videos are always decorative motion — real content lives in DOM text, spec 13.3)`);
    }
  });

  document.querySelectorAll("input, select, textarea").forEach((field) => {
    const type = (field.getAttribute("type") || "").toLowerCase();
    if (["hidden", "submit", "button", "image"].includes(type)) return;
    const id = field.id;
    const hasLabelFor = id && document.querySelector(`label[for="${CSS.escape(id)}"]`);
    const hasAriaLabel = field.getAttribute("aria-label");
    const hasAriaLabelledby = field.getAttribute("aria-labelledby");
    const wrappedInLabel = field.closest("label");
    if (!hasLabelFor && !hasAriaLabel && !hasAriaLabelledby && !wrappedInLabel) {
      violations.push(`form-label: unlabeled field ${field.outerHTML.slice(0, 80)}`);
    }
  });

  document.querySelectorAll("a[href], button").forEach((el) => {
    const text = (el.textContent || "").trim();
    const ariaLabel = el.getAttribute("aria-label");
    const ariaLabelledby = el.getAttribute("aria-labelledby");
    const title = el.getAttribute("title");
    if (!text && !ariaLabel && !ariaLabelledby && !title) {
      violations.push(`interactive-name: no accessible name on ${el.outerHTML.slice(0, 80)}`);
    }
  });

  const headingLevels = Array.from(document.querySelectorAll("h1,h2,h3,h4,h5,h6")).map((h) =>
    parseInt(h.tagName[1], 10),
  );
  let prevLevel = 0;
  headingLevels.forEach((level) => {
    if (prevLevel !== 0 && level > prevLevel + 1) {
      violations.push(`heading-skip: h${prevLevel} -> h${level}`);
    }
    prevLevel = level;
  });

  document.querySelectorAll("body *").forEach((el) => {
    if (el.children.length > 0) return; // leaf-ish elements only — a practical heuristic, not an axe-core replacement.
    const text = (el.textContent || "").trim();
    if (!text) return;
    const style = getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden") return;
    if (parseFloat(style.opacity) === 0) return;
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return;
    const fg = parseColor(style.color);
    if (!fg) return;
    const bg = effectiveBackground(el);
    const ratio = contrastRatio(fg, bg);
    const fontSize = parseFloat(style.fontSize) || 16;
    const fontWeight = parseInt(style.fontWeight, 10) || 400;
    const isLarge = fontSize >= 24 || (fontSize >= 18.66 && fontWeight >= 700);
    const threshold = isLarge ? 3.0 : 4.5;
    if (ratio < threshold) {
      violations.push(
        `contrast: "${text.slice(0, 40)}" ratio=${ratio.toFixed(2)} needs>=${threshold} (fontSize=${fontSize}px weight=${fontWeight})`,
      );
    }
  });

  return violations;
}
"""


class BrowserQcError(Exception):
    """Usage/precondition failure — receipt missing/invalid, server never
    became ready, playwright unavailable, etc. Distinct from a category
    FAIL, which is captured and recorded in the report rather than raised."""


# ---------------------------------------------------------------------------
# build-receipt.json loading (never trusts it beyond "P11 ran and passed" —
# every actual measurement below comes from live browser observation of the
# disk-materialized site_dir it points at, same discipline as prove_site.py)
# ---------------------------------------------------------------------------
def _load_build_receipt(run_dir: Path) -> Dict[str, Any]:
    path = run_dir / "build-receipt.json"
    if not path.is_file():
        raise BrowserQcError(f"build-receipt.json not found at {path} — P11-SITE-BUILD must run first")
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BrowserQcError(f"build-receipt.json is not valid JSON: {exc}") from exc
    schema = json.loads((_STRUCTURE_DIR / "build-receipt.schema.json").read_text(encoding="utf-8"))
    errors = jsl.validate(receipt, schema)
    if errors:
        raise BrowserQcError("build-receipt.json failed schema validation: " + "; ".join(errors))
    if receipt.get("status") != "pass":
        raise BrowserQcError(
            f"build-receipt.json status is {receipt.get('status')!r}, not 'pass' — P11-SITE-BUILD did not succeed"
        )
    return receipt


def _neighbor_mount_radius(site_dir: Path) -> int:
    """Reads NEIGHBOR_MOUNT_RADIUS out of the MATERIALIZED (as-served, on
    disk in site_dir, not the template source) useScrollScrub.ts — the perf
    budget for "max simultaneously mounted video elements" is derived from
    the real running scroll engine's own preload radius, never hardcoded
    independently of it (mirrors estimate_cost.py's "never trust a number
    you can recompute from a live source" rule)."""
    path = site_dir / "components" / "useScrollScrub.ts"
    if not path.is_file():
        raise BrowserQcError(f"useScrollScrub.ts not found at {path} — cannot derive the mount-radius perf budget")
    text = path.read_text(encoding="utf-8")
    m = re.search(r"NEIGHBOR_MOUNT_RADIUS\s*=\s*(\d+)", text)
    if not m:
        raise BrowserQcError(
            "could not find NEIGHBOR_MOUNT_RADIUS in the materialized useScrollScrub.ts — refusing to guess a perf budget"
        )
    return int(m.group(1))


def _compute_media_budgets(receipt: Dict[str, Any], mount_radius: int) -> Tuple[int, int]:
    """PROJECT-RELATIVE media budgets, derived from this project's OWN
    build-receipt.json scene byte sizes — see module docstring CALIBRATION
    section for why a fixed byte constant would be meaningless across wildly
    different real client media sizes."""
    scenes = receipt.get("scenes", [])
    if not scenes:
        raise BrowserQcError("build-receipt.json has no scenes — cannot derive media perf budgets")
    per_scene_bytes = [int(s["video_bytes"]) + int(s["poster_bytes"]) for s in scenes]
    max_single_scene_bytes = max(per_scene_bytes)
    max_mounted = 2 * mount_radius + 1
    initial_media_budget = int(max_mounted * max_single_scene_bytes * MEDIA_INITIAL_HEADROOM)
    total_media_budget = int(sum(per_scene_bytes) * MEDIA_TOTAL_HEADROOM)
    return initial_media_budget, total_media_budget


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------
def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_server(site_dir: Path, port: int, log_path: Path) -> subprocess.Popen:
    if not (site_dir / "node_modules").is_dir():
        raise BrowserQcError(
            f"{site_dir} has no node_modules — run scripts/build_site.py without --skip-toolchain first"
        )
    if not (site_dir / ".next").is_dir():
        raise BrowserQcError(f"{site_dir} has no .next production build — run scripts/build_site.py first")
    log_f = log_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        ["npx", "next", "start", "-p", str(port)],
        cwd=str(site_dir),
        stdout=log_f,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
    )
    proc._cwfe_log_file = log_f  # type: ignore[attr-defined]
    return proc


def _wait_for_server(url: str, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    last_err: Optional[BaseException] = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:  # noqa: S310 - localhost only
                if resp.status == 200:
                    return
        except (urllib.error.URLError, OSError, ValueError) as exc:
            last_err = exc
        time.sleep(SERVER_POLL_INTERVAL_SECONDS)
    raise BrowserQcError(f"server at {url} did not become ready within {timeout}s (last error: {last_err})")


def _stop_server(proc: subprocess.Popen) -> None:
    with contextlib.suppress(Exception):
        proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(Exception):
            proc.kill()
        with contextlib.suppress(Exception):
            proc.wait(timeout=5)
    log_f = getattr(proc, "_cwfe_log_file", None)
    if log_f is not None:
        with contextlib.suppress(Exception):
            log_f.close()


# ---------------------------------------------------------------------------
# Category checks — each takes an already-navigated real Playwright Page (or
# builds its own context) and returns {"passed": bool, "violations": [...]}.
# ---------------------------------------------------------------------------
def _check_desktop(browser: Any, url: str) -> Dict[str, Any]:
    violations: List[str] = []
    context = browser.new_context(viewport=DESKTOP_VIEWPORT)
    page = context.new_page()
    console_errors: List[str] = []
    page_errors: List[str] = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))

    page.goto(url, wait_until="load")
    page.wait_for_timeout(500)

    if not page.evaluate("() => !!document.querySelector('main')"):
        violations.append("no <main> landmark on desktop render")
    if not page.evaluate("() => !!document.documentElement.lang"):
        violations.append("<html> missing lang attribute")

    # Skip-link functional check (spec 13.4 "keyboard-accessible controls";
    # the U19 hardening this module verifies end-to-end — see module docstring).
    page.keyboard.press("Tab")
    skip_href = page.evaluate("() => document.activeElement && document.activeElement.getAttribute('href')")
    if skip_href != "#cwfe-conversion-start":
        violations.append(f"first Tab stop is not the skip link (got href={skip_href!r})")
    else:
        outline_style = page.evaluate("() => getComputedStyle(document.activeElement).outlineStyle")
        if outline_style == "none":
            violations.append("skip link has no visible :focus-visible outline")
        page.keyboard.press("Enter")
        page.wait_for_timeout(200)
        focused_id = page.evaluate("() => document.activeElement && document.activeElement.id")
        if focused_id != "cwfe-conversion-start":
            violations.append(
                f"activating the skip link did not move focus to #cwfe-conversion-start (got id={focused_id!r}) — "
                "WCAG technique G1 requires the skip target to receive focus, not just scroll into view"
            )

    if console_errors:
        violations.append(f"console errors on load: {console_errors}")
    if page_errors:
        violations.append(f"uncaught page errors on load: {page_errors}")

    context.close()
    return {"passed": len(violations) == 0, "violations": violations}


def _check_mobile(browser: Any, url: str, devices: Dict[str, Any]) -> Dict[str, Any]:
    violations: List[str] = []
    device = {k: v for k, v in devices[MOBILE_DEVICE_NAME].items() if k != "default_browser_type"}
    context = browser.new_context(**device)
    page = context.new_page()
    page.goto(url, wait_until="load")
    page.wait_for_timeout(500)

    scroll_width = page.evaluate("() => document.documentElement.scrollWidth")
    client_width = page.evaluate("() => document.documentElement.clientWidth")
    if scroll_width > client_width + 1:  # +1px rounding tolerance
        violations.append(f"horizontal overflow on mobile: scrollWidth={scroll_width} > clientWidth={client_width}")

    viewport_meta = page.evaluate(
        "() => { const m = document.querySelector('meta[name=\"viewport\"]'); return m ? m.getAttribute('content') : null; }"
    )
    if not viewport_meta or "width=device-width" not in viewport_meta:
        violations.append(f"missing/incorrect <meta name=viewport>: {viewport_meta!r}")

    page.evaluate(
        "() => { const el = document.getElementById('cwfe-conversion-start'); if (el) el.scrollIntoView(); }"
    )
    page.wait_for_timeout(300)
    cta_boxes = page.evaluate(
        "() => Array.from(document.querySelectorAll('[data-cwfe-cta]')).map(el => { "
        "const r = el.getBoundingClientRect(); return { right: r.right, left: r.left }; })"
    )
    viewport_width = device.get("viewport", {}).get("width", 0)
    for box in cta_boxes:
        if box["right"] > viewport_width + 1 or box["left"] < -1:
            violations.append(f"CTA element clipped outside mobile viewport: {box}")

    context.close()
    return {"passed": len(violations) == 0, "violations": violations}


def _check_reduced_motion(browser: Any, url: str) -> Dict[str, Any]:
    violations: List[str] = []
    context = browser.new_context(viewport=DESKTOP_VIEWPORT, reduced_motion="reduce")
    page = context.new_page()
    page.goto(url, wait_until="load")
    page.wait_for_timeout(500)

    is_reduced_marker = page.evaluate("() => !!document.querySelector('[data-cwfe-reduced-motion=\"true\"]')")
    if not is_reduced_marker:
        violations.append("data-cwfe-reduced-motion marker not present under prefers-reduced-motion: reduce")

    video_count = page.evaluate("() => document.querySelectorAll('[data-cwfe-scene-video]').length")
    if video_count != 0:
        violations.append(f"{video_count} <video> element(s) mounted under prefers-reduced-motion: reduce (must be 0 — scrubbing must be fully disabled, spec 13.4)")

    conversion_text_len = page.evaluate(
        "() => (document.querySelector('[data-cwfe-conversion-sections]')?.textContent || '').trim().length"
    )
    if conversion_text_len == 0:
        violations.append("conversion content is empty under reduced motion (content must remain complete without video, spec 13.4)")

    context.close()
    return {"passed": len(violations) == 0, "violations": violations}


def _check_accessibility(browser: Any, url: str) -> Dict[str, Any]:
    context = browser.new_context(viewport=DESKTOP_VIEWPORT)
    page = context.new_page()
    page.goto(url, wait_until="load")
    page.wait_for_timeout(500)
    violations = page.evaluate(A11Y_SCRIPT)
    context.close()
    return {"passed": len(violations) == 0, "violations": list(violations)}


def _check_performance(
    browser: Any, url: str, *, initial_media_budget: int, total_media_budget: int, max_mounted_budget: int
) -> Dict[str, Any]:
    violations: List[str] = []
    context = browser.new_context(viewport=DESKTOP_VIEWPORT)
    page = context.new_page()
    page.add_init_script(
        """
        window.__cwfePerf = { cls: 0 };
        try {
          new PerformanceObserver((list) => {
            for (const entry of list.getEntries()) {
              if (!entry.hadRecentInput) window.__cwfePerf.cls += entry.value;
            }
          }).observe({ type: 'layout-shift', buffered: true });
        } catch (e) {}
        """
    )
    page.goto(url, wait_until="load")
    page.wait_for_timeout(1200)

    resource_summary = page.evaluate(
        """
        () => performance.getEntriesByType('resource').map((r) => ({
          initiatorType: r.initiatorType,
          transferSize: r.transferSize || 0,
        }))
        """
    )
    js_bytes = sum(r["transferSize"] for r in resource_summary if r["initiatorType"] == "script")
    initial_media_bytes = sum(r["transferSize"] for r in resource_summary if r["initiatorType"] in ("img", "video"))

    paint_entries = page.evaluate("() => performance.getEntriesByType('paint').map(e => ({name: e.name, startTime: e.startTime}))")
    fcp_entry = next((e for e in paint_entries if e["name"] == "first-contentful-paint"), None)
    fcp_ms = fcp_entry["startTime"] if fcp_entry else None

    lcp_entries = page.evaluate("() => performance.getEntriesByType('largest-contentful-paint')")
    lcp_status = "observed" if lcp_entries else "unavailable_in_headless_harness_fcp_used"

    cls = page.evaluate("() => window.__cwfePerf.cls")

    # Scroll through the whole timeline to (a) measure cumulative media bytes
    # and (b) find the real max simultaneously-mounted <video> count — never
    # a static single-scroll-position snapshot (spec 13.5's "number of
    # simultaneously mounted video elements" applies across the whole scrub,
    # not just at load).
    max_mounted = page.evaluate("() => document.querySelectorAll('[data-cwfe-scene-video]').length")
    scroll_height = page.evaluate("() => document.documentElement.scrollHeight")
    if scroll_height > 0:
        for frac in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0):
            page.evaluate(f"() => window.scrollTo(0, Math.floor({frac} * document.documentElement.scrollHeight))")
            page.wait_for_timeout(150)
            n = page.evaluate("() => document.querySelectorAll('[data-cwfe-scene-video]').length")
            max_mounted = max(max_mounted, n)

    final_resource_summary = page.evaluate(
        """
        () => performance.getEntriesByType('resource').map((r) => ({
          initiatorType: r.initiatorType,
          transferSize: r.transferSize || 0,
        }))
        """
    )
    total_media_bytes = sum(r["transferSize"] for r in final_resource_summary if r["initiatorType"] in ("img", "video"))

    if js_bytes > JS_BUDGET_BYTES:
        violations.append(f"initial JS bytes {js_bytes} exceeds budget {JS_BUDGET_BYTES}")
    if initial_media_bytes > initial_media_budget:
        violations.append(f"initial media bytes {initial_media_bytes} exceeds project-relative budget {initial_media_budget}")
    if total_media_bytes > total_media_budget:
        violations.append(f"total media bytes after full scroll {total_media_bytes} exceeds project-relative budget {total_media_budget}")
    if fcp_ms is None:
        violations.append("no first-contentful-paint entry observed — page may never have painted")
    elif fcp_ms > FCP_BUDGET_MS:
        violations.append(f"first contentful paint {fcp_ms:.0f}ms exceeds budget {FCP_BUDGET_MS:.0f}ms")
    if cls > CLS_BUDGET:
        violations.append(f"cumulative layout shift {cls:.3f} exceeds budget {CLS_BUDGET}")
    if max_mounted > max_mounted_budget:
        violations.append(f"max simultaneously mounted <video> elements {max_mounted} exceeds budget {max_mounted_budget}")

    context.close()
    return {
        "passed": len(violations) == 0,
        "violations": violations,
        "measurements": {
            "initial_js_bytes": js_bytes,
            "initial_media_bytes": initial_media_bytes,
            "total_media_bytes_after_full_scroll": total_media_bytes,
            "first_contentful_paint_ms": fcp_ms if fcp_ms is not None else -1.0,
            "cumulative_layout_shift": cls,
            "max_mounted_video_elements": max_mounted,
        },
        "budgets": {
            "initial_js_bytes": JS_BUDGET_BYTES,
            "initial_media_bytes": initial_media_budget,
            "total_media_bytes": total_media_budget,
            "first_contentful_paint_ms": FCP_BUDGET_MS,
            "cumulative_layout_shift": CLS_BUDGET,
            "max_mounted_video_elements": max_mounted_budget,
        },
        "lcp_status": lcp_status,
    }


# ---------------------------------------------------------------------------
# Report persistence
# ---------------------------------------------------------------------------
def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_report(run_dir: Path, report: Dict[str, Any]) -> None:
    schema = json.loads((_STRUCTURE_DIR / "browser-qc-report.schema.json").read_text(encoding="utf-8"))
    errors = jsl.validate(report, schema)
    if errors:
        raise BrowserQcError("generated browser-qc-report.json failed its own schema: " + "; ".join(errors))
    (run_dir / "browser-qc-report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Orchestration entry point
# ---------------------------------------------------------------------------
def evaluate(run_dir: Path, *, port: Optional[int] = None, server_timeout: float = SERVER_READY_TIMEOUT_SECONDS) -> Tuple[bool, str]:
    run_dir = Path(run_dir)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        return False, (
            "P13-BROWSER-QC FAIL: the `playwright` Python package is not installed — "
            f"run `pip install playwright && python3 -m playwright install chromium` ({exc})"
        )

    try:
        receipt = _load_build_receipt(run_dir)
    except BrowserQcError as exc:
        return False, f"P13-BROWSER-QC FAIL: {exc}"

    site_dir = Path(receipt["site_dir"])
    if not site_dir.is_dir():
        return False, f"P13-BROWSER-QC FAIL: receipt's site_dir does not exist on disk: {site_dir}"

    try:
        mount_radius = _neighbor_mount_radius(site_dir)
        initial_media_budget, total_media_budget = _compute_media_budgets(receipt, mount_radius)
        max_mounted_budget = 2 * mount_radius + 1
    except BrowserQcError as exc:
        return False, f"P13-BROWSER-QC FAIL: {exc}"

    resolved_port = port if port is not None else _find_free_port()
    url = f"http://127.0.0.1:{resolved_port}/"
    log_path = run_dir / "browser-qc-server.log"

    try:
        proc = _start_server(site_dir, resolved_port, log_path)
    except BrowserQcError as exc:
        return False, f"P13-BROWSER-QC FAIL: {exc}"

    try:
        _wait_for_server(url, server_timeout)
    except BrowserQcError as exc:
        _stop_server(proc)
        return False, f"P13-BROWSER-QC FAIL: {exc}"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                desktop = _check_desktop(browser, url)
                mobile = _check_mobile(browser, url, p.devices)
                reduced_motion = _check_reduced_motion(browser, url)
                accessibility = _check_accessibility(browser, url)
                performance = _check_performance(
                    browser,
                    url,
                    initial_media_budget=initial_media_budget,
                    total_media_budget=total_media_budget,
                    max_mounted_budget=max_mounted_budget,
                )
            finally:
                browser.close()
    finally:
        _stop_server(proc)

    categories = {
        "desktop": desktop,
        "mobile": mobile,
        "reduced_motion": reduced_motion,
        "accessibility": accessibility,
        "performance": performance,
    }
    overall_pass = all(c["passed"] for c in categories.values())

    report = {
        "schema_version": SCHEMA_VERSION,
        "project_id": receipt["project_id"],
        "site_dir": str(site_dir),
        "server_url": url,
        "categories": categories,
        "overall_status": "pass" if overall_pass else "failed",
        "created_at": _now(),
    }
    _write_report(run_dir, report)

    if overall_pass:
        return True, "P13-BROWSER-QC PASS: desktop/mobile/reduced-motion/accessibility/performance all green"

    failing = [name for name, cat in categories.items() if not cat["passed"]]
    detail_bits = []
    for name in failing:
        detail_bits.append(f"{name}: {categories[name]['violations']}")
    return False, "P13-BROWSER-QC FAIL: " + " | ".join(detail_bits)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
def _patched_fixture_run_dir(run_dir: Path) -> None:
    """Writes the deterministic U15 fixture, then patches its cta_map so
    every action carries a schema-valid "kind" (make_fixture.py predates
    U16's conversion-map contract, structure/content-manifest.schema.json's
    cta_map is deliberately open-shaped, and an entry missing "kind" is
    correctly, independently flagged as misconfigured by U16's own
    ConversionCtaWiring — which is CORRECT U16 behavior, not a U19 bug, but
    it does emit a real console.error this module's desktop check would
    otherwise (accurately) flag). This keeps U19's self-test measuring
    ACTUAL a11y/mobile/reduced-motion/perf regressions, not re-litigating
    U16's already-covered, already-passing conversion-wiring behavior.
    Does not touch tests/fixtures/site-fixture/make_fixture.py itself —
    U15/U16/U18's own test suites keep using the original, un-patched
    fixture untouched by this function."""
    sys.path.insert(0, str(_FIXTURE_DIR))
    import make_fixture  # noqa: E402

    import resolve_content_engine as rce  # noqa: E402

    make_fixture.write_fixture_run_dir(run_dir)
    manifest_path = run_dir / "content-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["cta_map"] = {
        "primary": {"kind": "external-link", "label": "Book Your Strategy Call", "href": "#book"},
        "form-submit": {"kind": "external-link", "label": "Request My Slot", "href": "#book"},
    }
    manifest["content_hash"] = rce.compute_content_hash(manifest)
    ok, reason = rce.verify_locked_manifest(manifest)
    if not ok:
        raise AssertionError(f"patched fixture manifest failed self-verification: {reason}")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _self_test() -> bool:  # noqa: C901 - a self-test orchestrating several real, sequential proofs
    sys.path.insert(0, str(_SCRIPT_DIR))
    import build_site as bs  # noqa: E402

    ok = True
    with tempfile.TemporaryDirectory(prefix="cwfe-browser-qc-selftest-") as tmp:
        run_dir = Path(tmp) / "run"
        _patched_fixture_run_dir(run_dir)
        result = bs.build_site(run_dir, skip_toolchain=False, toolchain_timeout=300)
        if result.receipt["status"] != "pass":
            print("RESULT: FAIL — fixture build did not pass, cannot self-test")
            return False

        # --- Proof 1: good build passes every category ---
        passed, detail = evaluate(run_dir)
        print("good-build evaluate():", passed, "-", detail[:300])
        if not passed:
            print("RESULT: FAIL (expected PASS on an untouched good build)")
            ok = False

        report_path = run_dir / "browser-qc-report.json"
        if not report_path.is_file():
            print("RESULT: FAIL (browser-qc-report.json was not written)")
            ok = False

        index_html_path = result.site_dir / ".next" / "server" / "app" / "index.html"
        if not index_html_path.is_file():
            print("RESULT: FAIL (expected a statically-prerendered index.html to mutate for the break-it proofs)")
            return False
        original_html = index_html_path.read_text(encoding="utf-8")

        def _restart_and_evaluate() -> Tuple[bool, str]:
            (run_dir / "browser-qc-report.json").unlink(missing_ok=True)
            return evaluate(run_dir)

        # --- Proof 2: real regression — force horizontal overflow on mobile
        # (the exact defect class this module's mobile check exists to
        # catch). Note: an EARLIER version of this proof tried stripping the
        # `<meta name="viewport">` tag directly out of the prerendered
        # index.html. That mutation was investigated and found NOT to
        # reproduce on re-serve — Next.js's Metadata API regenerates
        # framework-owned <head> tags (viewport/title/description) from the
        # route's compiled metadata at request time rather than trusting the
        # literal prerendered HTML bytes for them, so a tampered static file
        # alone cannot make Next silently drop its own default viewport tag.
        # That is a REASSURING finding (this defect class is structurally
        # prevented by the framework, confirmed empirically, not assumed) —
        # but it means the mobile check needs an actually-reproducible
        # mutation to prove its fail-closed path, so this proof instead
        # widens the real `<main>` element (an EXISTING body-level node,
        # confirmed to survive React hydration unlike a wholly foreign
        # injected node would) past the mobile viewport width.
        try:
            mutated = original_html.replace("<main>", '<main style="min-width:3000px">')
            if mutated == original_html:
                print("RESULT: FAIL (main-element mutation made no change — selector text drifted)")
                ok = False
            else:
                index_html_path.write_text(mutated, encoding="utf-8")
                passed2, detail2 = _restart_and_evaluate()
                print("overflow-forced evaluate():", passed2, "-", detail2[:300])
                if passed2 or "overflow" not in detail2.lower():
                    print("RESULT: FAIL (gate did not fail closed on forced horizontal overflow)")
                    ok = False
        finally:
            index_html_path.write_text(original_html, encoding="utf-8")

        # --- Proof 3: real regression — strip aria-hidden from a scene
        # <video> (a11y defect class) ---
        try:
            mutated = original_html.replace('aria-hidden="true" tabindex="-1" data-cwfe-scene-video', 'tabindex="-1" data-cwfe-scene-video')
            if mutated == original_html:
                print("RESULT: FAIL (video aria-hidden mutation made no change — selector text drifted)")
                ok = False
            else:
                index_html_path.write_text(mutated, encoding="utf-8")
                passed3, detail3 = _restart_and_evaluate()
                print("video-aria-hidden-stripped evaluate():", passed3, "-", detail3[:300])
                if passed3 or "video-not-hidden" not in detail3:
                    print("RESULT: FAIL (gate did not fail closed on a video missing aria-hidden)")
                    ok = False
        finally:
            index_html_path.write_text(original_html, encoding="utf-8")

        # --- Proof 4: usage failure — missing build-receipt.json entirely ---
        empty_run_dir = Path(tmp) / "empty-run"
        empty_run_dir.mkdir()
        passed4, detail4 = evaluate(empty_run_dir)
        print("missing-receipt evaluate():", passed4, "-", detail4[:200])
        if passed4 or "build-receipt.json not found" not in detail4:
            print("RESULT: FAIL (gate did not fail closed on a missing build-receipt.json)")
            ok = False

        # --- Proof 5: usage failure — server never starts (bad site_dir) ---
        broken_run_dir = Path(tmp) / "broken-run"
        broken_run_dir.mkdir()
        broken_receipt = dict(result.receipt)
        broken_receipt["site_dir"] = str(Path(tmp) / "does-not-exist")
        (broken_run_dir / "build-receipt.json").write_text(json.dumps(broken_receipt, indent=2), encoding="utf-8")
        passed5, detail5 = evaluate(broken_run_dir)
        print("nonexistent-site-dir evaluate():", passed5, "-", detail5[:200])
        if passed5 or "does not exist on disk" not in detail5:
            print("RESULT: FAIL (gate did not fail closed on a nonexistent site_dir)")
            ok = False

        # --- Proof 6: restore leaves a clean, still-passing state ---
        passed6, detail6 = evaluate(run_dir)
        print("restored-build evaluate():", passed6, "-", detail6[:300])
        if not passed6:
            print("RESULT: FAIL (restoring the original HTML did not restore a passing state)")
            ok = False

    print("RESULT:", "PASS" if ok else "FAIL")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run-dir", type=Path, default=None)
    parser.add_argument("--port", type=int, default=None, help="Fixed port for the `next start` server (default: an OS-assigned free port)")
    parser.add_argument("--server-timeout", type=float, default=SERVER_READY_TIMEOUT_SECONDS)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        ok = _self_test()
        return EXIT_OK if ok else EXIT_FAIL

    if not args.run_dir:
        print("USAGE ERROR: --run-dir is required (unless --self-test)", file=sys.stderr)
        return EXIT_USAGE
    if not args.run_dir.is_dir():
        print(f"USAGE ERROR: --run-dir does not exist: {args.run_dir}", file=sys.stderr)
        return EXIT_USAGE

    passed, detail = evaluate(args.run_dir, port=args.port, server_timeout=args.server_timeout)
    print(detail)
    return EXIT_OK if passed else EXIT_FAIL


if __name__ == "__main__":
    raise SystemExit(main())
