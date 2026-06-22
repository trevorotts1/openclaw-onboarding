#!/usr/bin/env python3
"""ghl_verify.py — the ONE canonical build-verifier (Skill 06, T4 / R7 fix).

WHY THIS EXISTS
---------------
The Goal-2 V1 run shipped TWO independent verification writers with two
different truths, and that contradiction is exactly what the R7 judge flagged:

  * ``scorecard/verify-summary.json`` was written by ``v1_build.stage_s8_verify``
    — it checked only that LOCAL HTML files existed on disk and contained their
    marker (``marker in open(path).read()``). It NEVER fetched a URL. It reported
    ``overall_pass=True, 30/30``.
  * ``logs/final-preview-verify.json`` was written by a SEPARATE later step that
    did the real ``verify_url`` (HTTP 200 AND marker-in-body). It reported the
    true ``1/6``.

A reader therefore saw "30/30 PASS" next to "1/6 actually verified live" — an
optimistic summary that was not derived from the raw evidence. That is the lie.

THE FIX (the canonical-verify CONTRACT — enforced here, not merely described)
-----------------------------------------------------------------------------
ONE function (`verify_all`) makes ONE pass:

  1. For every built page it calls the SAME real check exactly once
     (``ghl_builder.verify_url(preview_url, marker)`` — HTTP 200 AND marker)
     and appends the raw per-page result to ``raw`` (written verbatim to
     ``logs/final-preview-verify.json``). This is the SINGLE SOURCE OF TRUTH.
  2. It then DERIVES the summary (``scorecard/verify-summary.json``) strictly by
     REDUCING ``raw`` — ``passed = sum(1 for r in raw if r["PASS"])`` — never
     from in-memory optimism, never from local-file existence.
  3. A hard guard assertion (`assert_consistent`) re-derives the counts from the
     written raw log and raises ``VerifyContradiction`` if the summary is EVER
     more optimistic than the raw log (``summary.passed > raw_passed`` or the
     verdicts disagree). A summary can never claim more than its evidence.

So the two files can never again disagree: the summary is a pure function of the
raw array, and the guard fails LOUD on any drift. The CLI exits non-zero on FAIL
(`overall=False`) and on any contradiction, so a partial/failed build can never
be massaged into a green report.

NETWORK NOTE
------------
The only real I/O here is the HTTP GET of the PUBLIC ``/preview/<pageId>`` URL,
done through ``ghl_builder.verify_url`` (the same HTTP-200-AND-marker check the
solver doc §2.4 blesses). The preview origin is the public preview host and is
NOT the Cloudflare-1010-gated funnels-builder origin, so this check runs from
bare Python (no browser needed) — the screenshot/DOM-capture step (which DOES
need the browser) is emitted as agent-browser commands, not executed here.
A ``fetcher`` parameter is injected in tests so NO live call ever happens in CI.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Callable

# Reuse the single source of truth for the real check + the D6 headless prefix.
_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import ghl_builder  # noqa: E402  (verify_url, browser_cmd, may_publish)


# The two canonical output paths (relative to a run dir). NOTHING else writes
# these — they are owned by this module so there is exactly one writer each.
RAW_REL = os.path.join("logs", "final-preview-verify.json")
SUMMARY_REL = os.path.join("scorecard", "verify-summary.json")

# The two standard screenshot viewports (desktop + mobile) the agent captures as
# REAL PNGs (replacing the V1 SVG placeholders).
VIEWPORTS = (
    {"name": "desktop", "width": 1440, "height": 900},
    {"name": "mobile", "width": 390, "height": 844},
)


class VerifyContradiction(AssertionError):
    """Raised when the derived summary is more optimistic than the raw log, or
    the two verdicts disagree. This is the guard that makes the 6/6-vs-1/6
    contradiction structurally impossible — it FAILS LOUD instead of letting a
    rosy summary ship next to a failing raw log."""


# ── The single real check (one page → one raw record) ────────────────────────

def verify_page(page: dict, *, fetcher: Callable[[str, str], dict] | None = None) -> dict:
    """Run the SINGLE real check for one built page and return its raw record.

    ``page`` carries at least ``{step|name, page_id, preview_url, marker}``. The
    check is ``ghl_builder.verify_url(preview_url, marker)`` (HTTP 200 AND marker
    in body) — the exact, only check; no local-file existence is consulted.

    Args:
        page: A built-page descriptor (from the funnel/website ledgers).
        fetcher: Optional injected ``(url, marker) -> verify_url-shaped dict``
            so tests never hit the network. Defaults to ``ghl_builder.verify_url``.

    Returns:
        A raw record: ``{step, page_id, preview_url, marker, http_code,
        marker_in_preview, PASS, error?}`` — the SAME shape the prior
        ``final-preview-verify.json`` used, so it is a drop-in replacement.
    """
    check = fetcher if fetcher is not None else ghl_builder.verify_url
    step = page.get("step") or page.get("name") or page.get("slug") or "?"
    preview_url = page.get("preview_url") or ""
    marker = page.get("marker") or ""

    if not preview_url or not marker:
        # A page with no preview URL or no marker cannot be verified live — that
        # is a FAIL, recorded honestly (never a silent pass).
        return {
            "step": step,
            "page_id": page.get("page_id"),
            "preview_url": preview_url,
            "marker": marker,
            "http_code": None,
            "marker_in_preview": False,
            "PASS": False,
            "error": "missing preview_url or marker — cannot verify live (FAIL)",
        }

    res = check(preview_url, marker)
    rec = {
        "step": step,
        "page_id": page.get("page_id"),
        "preview_url": preview_url,
        "marker": marker,
        "http_code": res.get("http"),
        "marker_in_preview": bool(res.get("marker_found")),
        "PASS": bool(res.get("ok")),
    }
    if "error" in res:
        rec["error"] = res["error"]
    return rec


# ── The reduction (summary is a PURE function of the raw array) ───────────────

def derive_summary(raw: list[dict], *, run_id: str = "", version: str = "",
                   brand: str = "", extra: dict | None = None) -> dict:
    """Derive the verify summary STRICTLY by reducing ``raw``.

    ``passed`` is ``sum(1 for r in raw if r["PASS"])`` and the overall verdict is
    "every page passed AND there is at least one page". Nothing here looks at
    local files, in-memory build state, or anything other than ``raw`` — so the
    summary can never be more optimistic than the evidence it reduces.

    Args:
        raw: The list of per-page raw records (from ``verify_page``).
        run_id / version / brand: Provenance labels (carried through, not scored).
        extra: Optional extra provenance fields merged into the summary.

    Returns:
        The summary dict (the ``scorecard/verify-summary.json`` content).
    """
    total = len(raw)
    passed = sum(1 for r in raw if r.get("PASS") is True)
    failed = total - passed
    # Overall PASS requires at least one verified page AND zero failures — an
    # empty raw list is NOT a pass (nothing was proven).
    overall = total > 0 and failed == 0
    summary = {
        "run_id": run_id,
        "version": version,
        "brand": brand,
        "verified_at": _ts(),
        "source_of_truth": RAW_REL,
        "verifier": "ghl_verify.verify_all (single canonical pass)",
        "total": total,
        "passed": passed,
        "failed": failed,
        "overall_pass": overall,
        "pages": [
            {"step": r.get("step"), "PASS": bool(r.get("PASS")),
             "http_code": r.get("http_code"),
             "marker_in_preview": bool(r.get("marker_in_preview"))}
            for r in raw
        ],
        "_contract": (
            "passed/failed/overall_pass are a pure reduction of "
            f"{RAW_REL}; the consistency guard rejects any summary more "
            "optimistic than that raw log."
        ),
    }
    if extra:
        summary.update(extra)
    return summary


# ── The hard guard (summary can NEVER be more optimistic than the raw log) ────

def assert_consistent(summary: dict, raw: list[dict]) -> None:
    """Raise ``VerifyContradiction`` unless ``summary`` is exactly consistent
    with ``raw``. This is the structural defense against the 6/6-vs-1/6 lie.

    Checks, all from re-deriving off ``raw`` (never trusting the summary's own
    numbers):
      * ``summary.passed`` == the recomputed pass count, and is NOT greater
        (a summary may never over-count passes).
      * ``summary.total`` / ``summary.failed`` match the raw array.
      * ``summary.overall_pass`` matches "every page passed AND total > 0";
        in particular it can never be True while any raw record is a FAIL.
    """
    raw_total = len(raw)
    raw_passed = sum(1 for r in raw if r.get("PASS") is True)
    raw_failed = raw_total - raw_passed
    raw_overall = raw_total > 0 and raw_failed == 0

    s_total = summary.get("total")
    s_passed = summary.get("passed")
    s_failed = summary.get("failed")
    s_overall = summary.get("overall_pass")

    if s_passed is None or s_total is None:
        raise VerifyContradiction(
            "summary is missing total/passed — cannot prove it was derived from "
            f"{RAW_REL}"
        )

    # The load-bearing inequality: a summary may NEVER claim more passes than the
    # raw log proves. (This is the exact failure mode that produced 30/30 next to
    # 1/6 — the summary counted things the raw log did not verify.)
    if s_passed > raw_passed:
        raise VerifyContradiction(
            f"summary.passed={s_passed} is MORE OPTIMISTIC than the raw log "
            f"({raw_passed} pages actually passed). A summary can never claim "
            f"more than its evidence ({RAW_REL})."
        )
    if s_passed != raw_passed or s_total != raw_total or s_failed != raw_failed:
        raise VerifyContradiction(
            f"summary counts (total={s_total}, passed={s_passed}, failed={s_failed}) "
            f"disagree with the raw log (total={raw_total}, passed={raw_passed}, "
            f"failed={raw_failed})."
        )
    if bool(s_overall) != raw_overall:
        raise VerifyContradiction(
            f"summary.overall_pass={s_overall} disagrees with the raw log verdict "
            f"({raw_overall}; every-page-passed AND total>0)."
        )
    if s_overall and raw_failed > 0:
        # Belt-and-braces: overall PASS while any page failed is the cardinal sin.
        raise VerifyContradiction(
            "summary.overall_pass is True while the raw log has "
            f"{raw_failed} failing page(s) — refusing the contradiction."
        )


# ── The single canonical pass (writes BOTH files from one source of truth) ────

def verify_all(run_dir: str, pages: list[dict], *,
               run_id: str = "", version: str = "", brand: str = "",
               fetcher: Callable[[str, str], dict] | None = None,
               extra: dict | None = None) -> dict:
    """THE canonical verify step. One pass, one source of truth, both files.

    Steps (in order):
      1. Run ``verify_page`` once per page → ``raw``.
      2. Write ``raw`` verbatim to ``logs/final-preview-verify.json``.
      3. Derive the summary by reducing ``raw`` (``derive_summary``).
      4. ``assert_consistent(summary, raw)`` — FAIL LOUD on any drift.
      5. Write the summary to ``scorecard/verify-summary.json``.

    Returns ``{raw, summary, raw_path, summary_path}``. Raises
    ``VerifyContradiction`` (step 4) if the summary could ever be more optimistic
    than the raw log — which is structurally impossible here, the assertion is
    the proof, not a hope.

    Args:
        run_dir: The run evidence root (never /tmp).
        pages: Built-page descriptors (funnel steps + website pages).
        run_id / version / brand: Provenance.
        fetcher: Injected verify_url for tests (no network in CI).
        extra: Extra provenance merged into the summary.
    """
    raw = [verify_page(p, fetcher=fetcher) for p in pages]

    raw_path = os.path.join(run_dir, RAW_REL)
    summary_path = os.path.join(run_dir, SUMMARY_REL)
    os.makedirs(os.path.dirname(raw_path), exist_ok=True)
    os.makedirs(os.path.dirname(summary_path), exist_ok=True)

    # Write the RAW source of truth FIRST, then derive everything else from it.
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2)

    summary = derive_summary(raw, run_id=run_id, version=version, brand=brand,
                             extra=extra)

    # The guard: re-derive from the JUST-WRITTEN raw file (not from memory) so the
    # check covers exactly what landed on disk, and FAIL LOUD on contradiction.
    with open(raw_path, encoding="utf-8") as f:
        raw_on_disk = json.load(f)
    assert_consistent(summary, raw_on_disk)

    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    return {"raw": raw, "summary": summary,
            "raw_path": raw_path, "summary_path": summary_path}


# ── Real-PNG screenshot + fetched-DOM capture (emit agent-browser commands) ───

def screenshot_plan(run_dir: str, pages: list[dict]) -> list[dict]:
    """Emit the agent-browser commands that capture REAL PNG screenshots +
    REAL fetched preview DOM for each page (replacing the V1 SVG placeholders
    and the synthetic-stub HTML writer).

    This module does NOT drive the browser (same glue-not-clicker boundary as
    ``ghl_builder``); it returns the headless-forced ``agent-browser`` argv lines
    the agent executes. For each page and each viewport it emits a
    ``screenshot`` of the PUBLIC ``/preview/<pageId>`` URL to
    ``screenshots/<step>-<viewport>.png``; once per page it also emits the
    ``html`` capture of the fetched preview DOM to ``<step>-preview.html``.

    Returns a list of ``{step, viewport?, kind, out, argv}`` step descriptors.
    The agent runs each ``argv`` (D6 headless-forced) and the output file lands
    under ``run_dir``. The verify guard does not depend on these — they are the
    R4 visual confirmation, captured as real artifacts, not asserted.
    """
    steps: list[dict] = []
    shots_dir = os.path.join(run_dir, "screenshots")
    for p in pages:
        step = p.get("step") or p.get("name") or p.get("slug") or "page"
        url = p.get("preview_url") or ""
        if not url:
            continue
        # Real fetched-DOM capture (NOT a synthetic stub): the agent navigates to
        # the public preview and dumps the rendered HTML it actually received.
        dom_out = os.path.join(run_dir, f"{step}-preview.html")
        steps.append({
            "step": step,
            "kind": "dom",
            "out": dom_out,
            "argv": ghl_builder.browser_cmd("open", url).split() +
                    ["&&"] + ghl_builder.browser_cmd("html", "--output", dom_out).split(),
            "note": "fetched preview DOM (real capture, replaces synthetic stub)",
        })
        for vp in VIEWPORTS:
            png_out = os.path.join(shots_dir, f"{step}-{vp['name']}.png")
            steps.append({
                "step": step,
                "viewport": vp["name"],
                "kind": "screenshot",
                "out": png_out,
                "argv": ghl_builder.browser_cmd(
                    "--viewport", f"{vp['width']}x{vp['height']}",
                    "open", url, "screenshot", png_out,
                ).split(),
                "note": f"REAL PNG at {vp['width']}x{vp['height']} (replaces SVG placeholder)",
            })
    return steps


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ── CLI: `ghl_verify verify-all <run_dir> <pages.json>` ───────────────────────

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="The ONE canonical Skill-06 build verifier (R7 fix).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser(
        "verify-all",
        help="single pass: write logs/final-preview-verify.json (raw) then "
             "derive scorecard/verify-summary.json from it, guarded.")
    p.add_argument("run_dir")
    p.add_argument("pages_json",
                   help="JSON file: a list of {step,page_id,preview_url,marker} "
                        "(or {pages:[...]}). REAL preview URLs are fetched.")
    p.add_argument("--run-id", default="")
    p.add_argument("--version", default="")
    p.add_argument("--brand", default="")

    p2 = sub.add_parser(
        "screenshot-plan",
        help="emit the headless agent-browser argv to capture REAL PNG "
             "screenshots + fetched preview DOM (no SVG placeholders).")
    p2.add_argument("run_dir")
    p2.add_argument("pages_json")

    args = ap.parse_args(argv)

    with open(args.pages_json, encoding="utf-8") as f:
        loaded = json.load(f)
    pages = loaded["pages"] if isinstance(loaded, dict) and "pages" in loaded else loaded
    if not isinstance(pages, list):
        sys.stderr.write("pages_json must be a list (or {pages:[...]})\n")
        return 2

    if args.cmd == "verify-all":
        try:
            out = verify_all(args.run_dir, pages, run_id=args.run_id,
                             version=args.version, brand=args.brand)
        except VerifyContradiction as e:
            sys.stderr.write(f"VERIFY CONTRADICTION (FAIL-LOUD): {e}\n")
            return 3
        s = out["summary"]
        print(json.dumps(
            {"overall_pass": s["overall_pass"], "passed": s["passed"],
             "total": s["total"], "raw": out["raw_path"],
             "summary": out["summary_path"]}, indent=2))
        # Exit non-zero on FAIL so a failing build can never read as success.
        return 0 if s["overall_pass"] else 1

    if args.cmd == "screenshot-plan":
        print(json.dumps(screenshot_plan(args.run_dir, pages), indent=2))
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
