#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prove_sp_media.py — fail-closed image-provenance + per-stage coverage gate for the
Sales Page Assets media ledger (Skill 56, FIX-IMG-02).

This clones PART B of Skill 49's prove_sf_no_pitch.py (image provenance: _BAD_TASK_IDS +
GHL_HOST_FINGERPRINTS + fail-closed on zero images) and adapts it to the Skill 56
media_ledger.json shape, then adds a per-STAGE COVERAGE check against image_plan.json.
Before this gate existed the media ledger was never validated (P2/P4 were existence-only and
prove_sp_bundle.py has zero image checks) even though SOP-SALESPAGE-01 claimed a GHL-host
provenance gate — a blank/off-host/placeholder image passed every gate.

TWO SACRED GUARANTEES (both fail-closed):

  A) IMAGE PROVENANCE — every media record must carry a real image-provider taskId (no
     native/placeholder value) AND resolve to the GHL media host (no off-host / placeholder
     URL). Mirrors delivery_gate.py _BAD_TASK_IDS + the assert_images_are_ghl_media host rule.
       AF-SP56-MEDIA-PROVENANCE — missing / placeholder / native taskId
       AF-SP56-MEDIA-HOST       — media URL does not resolve to a GHL media host

  B) STAGE COVERAGE — every stage declared in image_plan.json must have >= 1 media record in
     media_ledger.json (closes the "images for 2 of ~40 slots certify" hole).
       AF-SP56-MEDIA-COVERAGE   — an image-plan stage has zero media records

FAIL-CLOSED PRECONDITIONS (exit 3 — never a vacuous PASS):
  * media_ledger.json or image_plan.json is missing / unreadable JSON;
  * the media ledger carries zero image records (nothing to prove provenance on -> vacuous);
  * the image plan declares zero stages (cannot compute the required coverage set).

stdlib only. Exit 0 = pass, exit 2 = violation, exit 3 = usage/fail-closed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

EXIT_OK = 0
EXIT_VIOLATION = 2
EXIT_FAILCLOSED = 3

# GHL media host fingerprints — a media URL must resolve to one of these hosts
# (clone of prove_sf_no_pitch.GHL_HOST_FINGERPRINTS / assert_images_are_ghl_media).
GHL_HOST_FINGERPRINTS = (
    "gohighlevel", "leadconnector", "leadconnectorhq", "msgsndr",
    "highlevel", "storage.googleapis.com/highlevel",
)

# A taskId that is NOT a real image-provider bake (clone of delivery_gate.py _BAD_TASK_IDS).
_BAD_TASK_IDS = frozenset({"", "native", "placeholder", "none", "null", "n/a", "tbd", "todo"})


class ProverInputError(Exception):
    """Raised when a required input cannot be verified -> fail-closed (exit 3)."""


def _norm_stage(value: Any) -> str:
    return str(value).strip().lower() if value is not None else ""


def _host_ok(url: str) -> bool:
    if not isinstance(url, str) or not url.strip():
        return False
    try:
        parsed = urlparse(url.strip())
    except (ValueError, TypeError):
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    hay = (parsed.netloc + parsed.path).lower()
    return any(fp in hay for fp in GHL_HOST_FINGERPRINTS)


def _images(ledger: Dict[str, Any]) -> List[Any]:
    imgs = ledger.get("images")
    return imgs if isinstance(imgs, list) else []


def _plan_stages(plan: Dict[str, Any]) -> List[str]:
    """Distinct, order-preserving list of stages declared in the image plan."""
    prompts = plan.get("prompts")
    if not isinstance(prompts, list):
        return []
    out: List[str] = []
    seen = set()
    for pr in prompts:
        if not isinstance(pr, dict):
            continue
        st = _norm_stage(pr.get("stage"))
        if st and st not in seen:
            seen.add(st)
            out.append(st)
    return out


def evaluate(media_ledger: Dict[str, Any], image_plan: Dict[str, Any]) -> List[Tuple[str, str]]:
    fails: List[Tuple[str, str]] = []

    images = _images(media_ledger)
    if not images:
        raise ProverInputError(
            "AF-SP56-MEDIA-EMPTY: the media ledger carries no image records. taskId + GHL-host "
            "provenance cannot be proven on zero images -> fail-closed (a PASS would be vacuous).")

    plan_stages = _plan_stages(image_plan)
    if not plan_stages:
        raise ProverInputError(
            "AF-SP56-MEDIA-PLAN-EMPTY: the image plan declares no stages. The required per-stage "
            "coverage set cannot be computed -> fail-closed.")

    # --- A) IMAGE PROVENANCE (taskId + GHL host) ------------------------------
    media_stages = set()
    for img in images:
        who = (f"asset {img.get('asset_key', '?')!r} (stage {img.get('stage', '?')})"
               if isinstance(img, dict) else "an image record")
        if not isinstance(img, dict):
            fails.append(("AF-SP56-MEDIA-PROVENANCE", "an image record is not an object"))
            continue
        media_stages.add(_norm_stage(img.get("stage")))

        task_id = img.get("task_id", img.get("kie_task_id"))
        norm_task = str(task_id).strip().lower() if task_id is not None else ""
        if task_id is None or norm_task in _BAD_TASK_IDS:
            fails.append(("AF-SP56-MEDIA-PROVENANCE",
                          f"{who}: missing/placeholder image-provider taskId ({task_id!r}) — the "
                          "image was not proven provider-rendered"))

        url = img.get("ghl_media_url", img.get("media_url", img.get("url", "")))
        if not _host_ok(url):
            fails.append(("AF-SP56-MEDIA-HOST",
                          f"{who}: media URL {url!r} does not resolve to a GHL media host"))

    # --- B) STAGE COVERAGE (every plan stage has >= 1 media record) -----------
    missing = [st for st in plan_stages if st not in media_stages]
    if missing:
        fails.append(("AF-SP56-MEDIA-COVERAGE",
                      f"image-plan stage(s) {missing} have zero media records — every stage in "
                      "image_plan.json must carry at least one uploaded image"))

    return fails


def evaluate_media(media_ledger: Any, image_plan: Any) -> Tuple[int, List[Tuple[str, str]]]:
    if not isinstance(media_ledger, dict):
        return EXIT_FAILCLOSED, [("AF-SP56-MEDIA-INPUT", "media ledger is not a JSON object")]
    if not isinstance(image_plan, dict):
        return EXIT_FAILCLOSED, [("AF-SP56-MEDIA-INPUT", "image plan is not a JSON object")]
    try:
        fails = evaluate(media_ledger, image_plan)
    except ProverInputError as exc:
        return EXIT_FAILCLOSED, [("FAIL-CLOSED", str(exc))]
    if fails:
        return EXIT_VIOLATION, fails
    return EXIT_OK, []


# ---------------------------------------------------------------------------
# IO
# ---------------------------------------------------------------------------
def _load_json(path: str) -> Any:
    if path == "-":
        return json.loads(sys.stdin.read())
    return json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))


def _report(code: int, fails: List[Tuple[str, str]]) -> None:
    if code == EXIT_OK:
        print("PASS: every media record has a taskId + GHL-host provenance, and every image-plan "
              "stage is covered by >= 1 media record.")
        return
    label = "FAIL-CLOSED" if code == EXIT_FAILCLOSED else "VIOLATION"
    print(f"{label}: media provenance/coverage gate failed ({len(fails)} finding(s)):")
    for c, m in fails:
        print(f"  [{c}] {m}")


# ---------------------------------------------------------------------------
# Self-test fixtures.
# ---------------------------------------------------------------------------
def _valid_plan() -> Dict[str, Any]:
    stages = ["main", "main", "upsell-1", "downsell-1", "high-ticket"]
    return {
        "funnel_type": "sales_page_assets",
        "image_prompt_count": len(stages),
        "prompts": [{"index": i, "stage": s, "prompt_text": "x"} for i, s in enumerate(stages)],
    }


def _valid_media() -> Dict[str, Any]:
    return {
        "funnel_type": "sales_page_assets",
        "media_folder": "jane-doe__glow-method",
        "images": [
            {"asset_key": "jane-doe__glow-method__main__img-01__v01", "stage": "main",
             "task_id": "kie-01", "ghl_media_url": "https://storage.msgsndr.com/x/main-01.png"},
            {"asset_key": "jane-doe__glow-method__main__img-02__v01", "stage": "main",
             "task_id": "kie-02", "ghl_media_url": "https://storage.msgsndr.com/x/main-02.png"},
            {"asset_key": "jane-doe__glow-method__upsell-1__img-03__v01", "stage": "upsell-1",
             "task_id": "kie-03", "ghl_media_url": "https://msgsndr.com/media/up-03.png"},
            {"asset_key": "jane-doe__glow-method__downsell-1__img-04__v01", "stage": "downsell-1",
             "task_id": "kie-04", "ghl_media_url": "https://leadconnectorhq.com/media/dn-04.png"},
            {"asset_key": "jane-doe__glow-method__high-ticket__img-05__v01", "stage": "high-ticket",
             "task_id": "kie-05", "ghl_media_url": "https://gohighlevel.com/media/ht-05.png"},
        ],
    }


def _violation_cases():
    import copy as _c

    def bad_task(m):
        m["images"][0]["task_id"] = "placeholder"

    def missing_task(m):
        m["images"][1].pop("task_id", None)

    def off_host(m):
        m["images"][2]["ghl_media_url"] = "https://example.com/random/up-03.png"

    def drop_stage_coverage(m):
        # remove every high-ticket media record -> that plan stage is uncovered
        m["images"] = [im for im in m["images"] if im.get("stage") != "high-ticket"]

    def _mk(fn):
        m = _c.deepcopy(_valid_media())
        fn(m)
        return m

    return [
        ("bad_task_id", "AF-SP56-MEDIA-PROVENANCE", lambda: _mk(bad_task)),
        ("missing_task_id", "AF-SP56-MEDIA-PROVENANCE", lambda: _mk(missing_task)),
        ("off_host_url", "AF-SP56-MEDIA-HOST", lambda: _mk(off_host)),
        ("uncovered_stage", "AF-SP56-MEDIA-COVERAGE", lambda: _mk(drop_stage_coverage)),
    ]


def run_self_test() -> int:
    import copy as _c
    ok = True

    code, fails = evaluate_media(_valid_media(), _valid_plan())
    if code != EXIT_OK:
        ok = False
        print(f"SELF-TEST FAIL: valid fixture -> exit {code}: {fails}")
    else:
        print("SELF-TEST ok: valid fixture PASSES (exit 0).")

    caught = 0
    cases = _violation_cases()
    for name, expected, build in cases:
        code, fails = evaluate_media(build(), _valid_plan())
        codes = {c for c, _ in fails}
        if code != EXIT_VIOLATION:
            ok = False
            print(f"SELF-TEST FAIL: '{name}' -> exit {code} (expected 2): {fails}")
        elif expected not in codes:
            ok = False
            print(f"SELF-TEST FAIL: '{name}' -> {sorted(codes)} (expected {expected}).")
        else:
            caught += 1
            print(f"SELF-TEST ok: '{name}' -> exit 2, carries {expected}.")

    # fail-closed cases
    fc = 0
    m = _c.deepcopy(_valid_media()); m["images"] = []
    code, fails = evaluate_media(m, _valid_plan())
    if code == EXIT_FAILCLOSED and any("AF-SP56-MEDIA-EMPTY" in msg for _, msg in fails):
        fc += 1; print("SELF-TEST ok: zero images -> fail-closed (exit 3).")
    else:
        ok = False; print(f"SELF-TEST FAIL: zero images -> exit {code}: {fails}")

    p = _c.deepcopy(_valid_plan()); p["prompts"] = []
    code, fails = evaluate_media(_valid_media(), p)
    if code == EXIT_FAILCLOSED and any("AF-SP56-MEDIA-PLAN-EMPTY" in msg for _, msg in fails):
        fc += 1; print("SELF-TEST ok: empty image plan -> fail-closed (exit 3).")
    else:
        ok = False; print(f"SELF-TEST FAIL: empty image plan -> exit {code}: {fails}")

    code, fails = evaluate_media("not-a-dict", _valid_plan())
    if code == EXIT_FAILCLOSED:
        fc += 1; print("SELF-TEST ok: non-object media ledger -> fail-closed (exit 3).")
    else:
        ok = False; print(f"SELF-TEST FAIL: non-object media ledger -> exit {code}: {fails}")

    print(f"SELF-TEST FIXTURES: {caught}/{len(cases)} violation-catch, {fc}/3 fail-closed")
    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(
        description="Fail-closed image-provenance (taskId + GHL host) + per-stage coverage gate "
                    "for the Sales Page Assets media ledger. Exit 0 pass, 2 violation, 3 fail-closed.")
    ap.add_argument("--media", help="path to media_ledger.json ('-' reads stdin)")
    ap.add_argument("--plan", help="path to image_plan.json (for the per-stage coverage check)")
    ap.add_argument("--self-test", action="store_true",
                    help="construct VALID + VIOLATION + FAIL-CLOSED fixtures and assert")
    args = ap.parse_args(argv)

    if args.self_test:
        return run_self_test()

    if not args.media or not args.plan:
        print("USAGE ERROR: pass --media <media_ledger.json> AND --plan <image_plan.json> "
              "(or --self-test).")
        return EXIT_FAILCLOSED
    try:
        media_ledger = _load_json(args.media)
    except Exception as exc:  # noqa: BLE001
        print(f"USAGE/IO ERROR: cannot load media ledger {args.media!r}: {exc}")
        return EXIT_FAILCLOSED
    try:
        image_plan = _load_json(args.plan)
    except Exception as exc:  # noqa: BLE001
        print(f"USAGE/IO ERROR: cannot load image plan {args.plan!r}: {exc}")
        return EXIT_FAILCLOSED

    code, fails = evaluate_media(media_ledger, image_plan)
    _report(code, fails)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
