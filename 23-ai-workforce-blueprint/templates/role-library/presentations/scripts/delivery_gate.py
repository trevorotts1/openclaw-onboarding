#!/usr/bin/env python3
"""
delivery_gate.py — MECHANICAL last-mile delivery enforcer (R9-F9 fix).

Until now the client-facing last mile (AF-DH1 five-file whitelist, the GHL upload
record, and the SOP 9.4 ground-truth destination check) was DOCTRINE-ONLY: the codes
AF-DELIVER / AF-DH1 / AF-DELIVERY-COMPLETE are enforced_by "closeout_gate" with a
null py_symbol, and gate_integrity_check.py (Guard A) exempts non-build_deck codes.
So the only mechanical bundle gate was build_deck.py's AF-BUNDLE-COMPLETE over the
NINE-file operator build bundle in ~/Downloads — the actual client package
(delivery/[DECK_SLUG]-FINAL/, the FIVE whitelisted files) had no coded enforcer and
relied on the Concierge agent obeying the SOPs. This script closes that gap.

It mechanically enforces, over a run dir:
  1. AF-DH1 — delivery/[DECK_SLUG]-FINAL/ contains EXACTLY the five whitelisted,
     correctly-named client files and NOTHING else (no extras, no working/ dirs,
     no .md guide/speech, pptx/pdf carry the -FINAL suffix).
  2. GHL upload record — when the resolved delivery_plan.json carries a `ghl`
     destination, working/checkpoints/media_library.json must carry a non-null
     `pptx_ghl_media_id` (the upload actually happened, not just planned).
  3. SOP 9.4 ground-truth — every destination in delivery_plan.json is verified:
     a `mac_downloads` destination's `verify_anchor` file exists on disk; a `ghl`
     destination has its upload id; a `drive` destination has its file ids.

DEFER (pass, "not at delivery stage") when neither the delivery package dir nor a
delivery_plan.json exists — a pre-delivery render must not be blocked. A delivery
that was ATTEMPTED (plan present) but is missing/partial FAILS.

ZERO third-party deps (stdlib json / re / sys / pathlib / argparse / tempfile only)
so it runs identically in the repo and on a deployed client box.

PUBLIC API (imported by test_preflight.py):
    delivery_gate(run_dir: Path) -> tuple[bool, list[str]]
        (ok, reasons). ok is False on any AF-DH1 / upload-record / destination
        failure; reasons is the list of human-readable failure strings (empty on
        pass/defer).
    check_af_dh1(package_dir: Path) -> str   # "" on pass, reason on fail
    find_client_package(run_dir: Path) -> Path | None

EXIT CODES (CLI):
    0 — delivery complete (or deferred: pre-delivery), gate clean.
    1 — one or more last-mile failures (AF-DH1 / upload record / destination).
    2 — could not run (bad args / unreadable run dir).

USAGE:
    python3 delivery_gate.py <run_dir>
    python3 delivery_gate.py --selftest      # built-in pass + fail fixtures
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path

# The FIVE client-package files (AF-DH1 whitelist), kept in lockstep with
# sops/delivery-concierge-sops.md SOP 9.0 step 3a and PIPELINE-MANIFEST.json
# client_package_files. PRESENTERS-SPEECH is PLURAL (the canonical producer name).
EXACT_NAME_WHITELIST = frozenset({
    "PRESENTER-GUIDE.pdf",
    "PRESENTERS-SPEECH.pdf",
    "PRESENTER-AUDIO.mp3",
})
# Blocklist substrings/suffixes (belt-and-suspenders mirror of SOP 9.0 step 3b).
BLOCKLIST_SUFFIXES = (
    ".py", ".log", ".txt", "_manifest.json", "_qc_log.json", "_run.log",
    "QC-FINAL.md",
)
FORBIDDEN_SUBDIRS = frozenset({
    "working", "prompts", "images", "renders", "qc", "scripts", "checkpoints",
})


def _categorize(name: str) -> str:
    """Return the client-package category for a filename, or '' if not whitelisted."""
    if name == "PRESENTER-GUIDE.pdf":
        return "guide_pdf"
    if name == "PRESENTERS-SPEECH.pdf":
        return "speech_pdf"
    if name == "PRESENTER-AUDIO.mp3":
        return "audio_mp3"
    if name.endswith("-FINAL.pptx"):
        return "deck_pptx"
    if name.endswith("-FINAL.pdf"):
        return "deck_pdf"
    return ""


def check_af_dh1(package_dir: Path) -> str:
    """AF-DH1 hygiene gate over the resolved client package dir. Returns '' on PASS,
    or a specific failure reason. Enforces: exactly the five whitelisted client files,
    correctly named; no extra/wrongly-named file; no forbidden subdir; pptx/pdf carry
    the -FINAL suffix; no .md guide/speech."""
    if not package_dir.is_dir():
        return f"AF-DH1: client package dir {package_dir} does not exist"
    found = {}
    for child in sorted(package_dir.iterdir()):
        nm = child.name
        if child.is_dir():
            if nm in FORBIDDEN_SUBDIRS:
                return f"AF-DH1: forbidden dev directory in client package: {nm}/"
            return f"AF-DH1: unexpected subdirectory in client package: {nm}/"
        # Format check: a .md guide/speech is an explicit fail (must be .pdf).
        low = nm.lower()
        if low.endswith(".md") and ("presenter-guide" in low or "presenters-speech" in low
                                    or "presenter-speech" in low):
            return f"AF-DH1: guide/speech present as .md (must be .pdf): {nm}"
        for bad in BLOCKLIST_SUFFIXES:
            if nm.endswith(bad):
                return f"AF-DH1: blocklisted dev artifact in client package: {nm}"
        cat = _categorize(nm)
        if not cat:
            return f"AF-DH1: file not on the five-item whitelist: {nm}"
        if cat in found:
            return (f"AF-DH1: two files map to the same client slot {cat!r}: "
                    f"{found[cat]} + {nm}")
        found[cat] = nm
    required = {"deck_pptx", "deck_pdf", "guide_pdf", "speech_pdf", "audio_mp3"}
    missing = required - set(found)
    if missing:
        return (f"AF-DH1: client package is incomplete — missing "
                f"{', '.join(sorted(missing))} (have: {', '.join(sorted(found.values())) or 'nothing'})")
    return ""


def find_client_package(run_dir: Path):
    """Locate the single delivery/[DECK_SLUG]-FINAL/ client package dir, or None."""
    delivery = run_dir / "delivery"
    if not delivery.is_dir():
        return None
    candidates = [p for p in delivery.iterdir() if p.is_dir() and p.name.endswith("-FINAL")]
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        return None
    # Ambiguous: more than one -FINAL package. Caller treats None-with-many as a fail.
    return candidates  # type: ignore[return-value]


def _load_json(path: Path):
    try:
        return json.loads(path.read_text())
    except Exception:  # noqa: BLE001
        return None


def _check_destinations(run_dir: Path, plan: dict) -> list:
    """SOP 9.4 ground-truth: every resolved destination must be verifiable."""
    reasons = []
    dests = plan.get("destinations") or []
    if not isinstance(dests, list) or not dests:
        reasons.append("SOP-9.4: delivery_plan.json has no resolved destinations")
        return reasons
    media = _load_json(run_dir / "working" / "checkpoints" / "media_library.json") or {}
    for d in dests:
        if not isinstance(d, dict):
            reasons.append(f"SOP-9.4: malformed destination entry: {d!r}")
            continue
        dtype = d.get("type")
        if dtype == "mac_downloads":
            anchor = d.get("verify_anchor") or ""
            ap = Path(anchor.replace("~", str(Path.home()), 1)) if anchor.startswith("~") else Path(anchor)
            if not anchor:
                reasons.append("SOP-9.4: mac_downloads destination has no verify_anchor")
            elif not ap.is_file():
                reasons.append(f"SOP-9.4: mac_downloads verify_anchor missing on disk: {anchor}")
        elif dtype == "ghl":
            if not media.get("pptx_ghl_media_id"):
                reasons.append("AF-DELIVER/GHL: ghl destination resolved but "
                               "media_library.json has no pptx_ghl_media_id (upload record absent)")
        elif dtype == "drive":
            ids = plan.get("drive_file_ids") or media.get("drive_file_ids")
            if not ids:
                reasons.append("SOP-9.4: drive destination resolved but no drive_file_ids recorded")
        else:
            reasons.append(f"SOP-9.4: unknown/unimplemented destination type: {dtype!r}")
    return reasons


def delivery_gate(run_dir: Path):
    """Mechanical last-mile gate. Returns (ok, reasons). Defers (ok=True, []) when no
    delivery has been attempted yet (no package dir AND no delivery_plan.json)."""
    run_dir = Path(run_dir)
    plan_path = run_dir / "working" / "checkpoints" / "delivery_plan.json"
    pkg = find_client_package(run_dir)
    plan_exists = plan_path.is_file()

    if pkg is None and not plan_exists:
        return True, []  # pre-delivery render — defer.

    if isinstance(pkg, list):
        return False, [f"AF-DH1: more than one *-FINAL client package under delivery/: "
                       f"{', '.join(p.name for p in pkg)}"]

    reasons = []
    if pkg is None:
        reasons.append("AF-DH1: a delivery_plan.json exists but no delivery/[DECK_SLUG]-FINAL/ "
                       "client package was assembled")
    else:
        dh1 = check_af_dh1(pkg)
        if dh1:
            reasons.append(dh1)

    if plan_exists:
        plan = _load_json(plan_path)
        if plan is None:
            reasons.append("SOP-9.4: working/checkpoints/delivery_plan.json is unreadable / not JSON")
        else:
            if plan.get("af_dh1_triggered"):
                reasons.append(f"AF-DH1: delivery_plan records af_dh1_triggered: "
                               f"{plan.get('af_dh1_details', 'unspecified')}")
            reasons.extend(_check_destinations(run_dir, plan))
    else:
        reasons.append("SOP-9.4: client package exists but no delivery_plan.json "
                       "(destination resolution never ran)")

    return (len(reasons) == 0), reasons


# ---------------------------------------------------------------------------
# SELF-TEST — built-in pass + fail fixtures (no external deps, no network).
# ---------------------------------------------------------------------------
def _mk_pkg(base: Path, files):
    d = base / "delivery" / "demo-deck-FINAL"
    d.mkdir(parents=True, exist_ok=True)
    for nm in files:
        (d / nm).write_text("x")
    return d


def _write_plan(base: Path, plan):
    p = base / "working" / "checkpoints"
    p.mkdir(parents=True, exist_ok=True)
    (p / "delivery_plan.json").write_text(json.dumps(plan))


def _write_media(base: Path, media):
    p = base / "working" / "checkpoints"
    p.mkdir(parents=True, exist_ok=True)
    (p / "media_library.json").write_text(json.dumps(media))


FIVE = ["demo-deck-FINAL.pptx", "demo-deck-FINAL.pdf", "PRESENTER-GUIDE.pdf",
        "PRESENTERS-SPEECH.pdf", "PRESENTER-AUDIO.mp3"]


def _selftest() -> int:
    fails = []

    # CASE A — pre-delivery render (nothing) -> DEFER (ok, no reasons).
    with tempfile.TemporaryDirectory() as t:
        ok, reasons = delivery_gate(Path(t))
        if not ok or reasons:
            fails.append(f"A defer: expected ok/empty, got ok={ok} reasons={reasons}")

    # CASE B — clean 5-file package + verified GHL + mac anchor -> PASS.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        pkg = _mk_pkg(base, FIVE)
        _write_media(base, {"pptx_ghl_media_id": "abc123"})
        _write_plan(base, {"destinations": [
            {"type": "ghl", "ghl_folder_id": "root", "status": "uploaded"},
            {"type": "mac_downloads", "verify_anchor": str(pkg / "demo-deck-FINAL.pptx")},
        ]})
        ok, reasons = delivery_gate(base)
        if not ok:
            fails.append(f"B pass: expected PASS, got reasons={reasons}")

    # CASE C — extra .md draft in the package -> AF-DH1 FAIL.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        pkg = _mk_pkg(base, FIVE + ["notes-draft.md"])
        _write_media(base, {"pptx_ghl_media_id": "abc"})
        _write_plan(base, {"destinations": [{"type": "ghl"}]})
        ok, reasons = delivery_gate(base)
        if ok or not any("AF-DH1" in r for r in reasons):
            fails.append(f"C extra-md: expected AF-DH1 FAIL, got ok={ok} reasons={reasons}")

    # CASE D — singular legacy speech name in client package -> AF-DH1 FAIL (whitelist plural).
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        bad_five = ["demo-deck-FINAL.pptx", "demo-deck-FINAL.pdf", "PRESENTER-GUIDE.pdf",
                    "PRESENTER-SPEECH.pdf", "PRESENTER-AUDIO.mp3"]
        _mk_pkg(base, bad_five)
        _write_media(base, {"pptx_ghl_media_id": "abc"})
        _write_plan(base, {"destinations": [{"type": "ghl"}]})
        ok, reasons = delivery_gate(base)
        if ok or not any("AF-DH1" in r for r in reasons):
            fails.append(f"D singular-speech: expected AF-DH1 FAIL, got ok={ok} reasons={reasons}")

    # CASE E — ghl destination but NO upload record -> FAIL.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        _mk_pkg(base, FIVE)
        _write_media(base, {})  # no pptx_ghl_media_id
        _write_plan(base, {"destinations": [{"type": "ghl", "status": "pending"}]})
        ok, reasons = delivery_gate(base)
        if ok or not any("pptx_ghl_media_id" in r for r in reasons):
            fails.append(f"E no-upload-record: expected GHL FAIL, got ok={ok} reasons={reasons}")

    # CASE F — mac_downloads verify_anchor missing on disk -> FAIL.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        _mk_pkg(base, FIVE)
        _write_plan(base, {"destinations": [
            {"type": "mac_downloads", "verify_anchor": str(base / "delivery" / "nope.pptx")},
        ]})
        ok, reasons = delivery_gate(base)
        if ok or not any("verify_anchor missing" in r for r in reasons):
            fails.append(f"F missing-anchor: expected SOP-9.4 FAIL, got ok={ok} reasons={reasons}")

    # CASE G — package incomplete (missing audio) -> AF-DH1 FAIL.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        _mk_pkg(base, FIVE[:-1])  # no audio
        _write_plan(base, {"destinations": [{"type": "ghl"}]})
        _write_media(base, {"pptx_ghl_media_id": "abc"})
        ok, reasons = delivery_gate(base)
        if ok or not any("AF-DH1" in r and "missing" in r for r in reasons):
            fails.append(f"G incomplete: expected AF-DH1 missing FAIL, got ok={ok} reasons={reasons}")

    if fails:
        print("delivery_gate selftest -> FAIL")
        for f in fails:
            print("  -", f)
        return 1
    print("delivery_gate selftest -> PASS (7 cases: defer/pass/extra-md/singular/"
          "no-upload/missing-anchor/incomplete)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Mechanical last-mile delivery gate (R9-F9).")
    ap.add_argument("run_dir", nargs="?", help="presentation run directory")
    ap.add_argument("--selftest", action="store_true", help="run built-in fixtures")
    ap.add_argument("--json", action="store_true", help="emit JSON result")
    args = ap.parse_args()

    if args.selftest:
        return _selftest()
    if not args.run_dir:
        ap.error("run_dir is required (or use --selftest)")
    rd = Path(args.run_dir)
    if not rd.is_dir():
        print(f"delivery_gate: run_dir not a directory: {rd}", file=sys.stderr)
        return 2
    ok, reasons = delivery_gate(rd)
    if args.json:
        print(json.dumps({"ok": ok, "reasons": reasons}, indent=2))
    else:
        if ok:
            print("DELIVERY GATE: PASS (last mile complete or pre-delivery defer)")
        else:
            print("DELIVERY GATE: FAIL")
            for r in reasons:
                print("  -", r)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
