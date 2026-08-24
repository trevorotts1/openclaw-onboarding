#!/usr/bin/env python3
"""
fix_bundle_complete.py — FIX-8: the full deliverable bundle gate.

WHY THIS EXISTS (Gauntlet Loop FIX-8 / T-09 / M2-M9):
The department's delivery contract is a ten-piece operator build bundle
(deck_pptx, deck_pdf, guide_pdf, speech_md, speech_pdf, speech_fish_md,
audio_mp3, infographic_png, teleprompter_html, webinar_mp4). In the live E2E run (task
e738cff0) only the deck PPTX was produced; the other eight were never built.
The engine had NO dedicated, mechanically-enforced `bundle_complete.json`
gate after assembly — the bundle was "complete" only in the eye of whatever
agent happened to be driving the run.

THIS FILE closes that gap with a FAIL-CLOSED gate:

  * it requires ALL deliverables to exist in the bundle dir AND be
    non-empty (a zero-byte / placeholder file does NOT count as "done");
  * on ANY missing/empty deliverable it FAILS with the code
    AF-BUNDLE-INCOMPLETE and enumerates EXACTLY which keys are missing —
    a partial bundle can never be reported "done";
  * on PASS it writes `bundle_complete.json` into the bundle dir (the
    named gate artifact) — a durable, on-disk proof the full bundle is
    present, plus a JSON `--json` report mode for machines.

SOURCE OF TRUTH — DELIVERABLE_AUDIT_SPEC (+ DELIVERABLES_REQUIRED / REQUIRED_KEYS derived views):
The ten keys + canonical filenames come from build_deck.py's
DELIVERABLES_REQUIRED (deck_slug-templated) and the PIPELINE-MANIFEST
build_bundle_files list. To avoid importing the 10,000-line build_deck.py
(and to keep this gate stdlib-only + runnable on a deployed box without
python-pptx), the canonical set is pinned in presentation_job/deliverables.py
(U05 — the single source of truth every consumer imports from) AND asserted
against the PIPELINE-MANIFEST by the self-test (they must never drift apart).

WHERE IT RUNS:
  * standalone:   python3 fix_bundle_complete.py <bundle_dir>
  * in-pipeline: run_signature_deck.py P9-DELIVER pre-delivery guard
                  (fix_bundle_complete(bundle_dir) — see the P9 wiring).
  * self-test:    python3 fix_bundle_complete.py --selftest

EXIT CODES:
  0 — all ten deliverables present and non-empty (gate clean).
  1 — one or more deliverables missing or empty (AF-BUNDLE-INCOMPLETE).
  2 — could not run (bad args / bundle dir unreadable).

PUBLIC API:
  REQUIRED_DELIVERABLES : list[dict] — the {key, filename, label} specs (derived from DELIVERABLE_AUDIT_SPEC).
  check_bundle_complete(bundle_dir, deck_slug="deck") -> list[str]
      Returns a list of MISSING-or-empty keys ([] == complete). Never raises.
  run_bundle_gate(bundle_dir, deck_slug="deck") -> tuple[bool, list[str], Path|None]
      Runs the gate, writes bundle_complete.json on pass, returns
      (ok, missing_keys, gate_path).
  fix_bundle_complete(bundle_dir, deck_slug="deck") -> bool
      Thin wrapper for in-pipeline callers — True iff the full bundle is
      complete (writes bundle_complete.json on pass).

Zero third-party deps (stdlib json/os/pathlib/argparse only), matching the
delivery_gate.py rule so it runs identically in the repo and on a deployed
client box.
"""

import argparse
import json
import os
import sys
from pathlib import Path

# SINGLE SOURCE OF TRUTH (U05) — the deliverable whitelist and its derived views
# now live in presentation_job/deliverables.py. curate.py, phase_verifiers.py,
# and self_audit.py import the same constants from that one module. No file
# (including this one) may hardcode a deliverable list of its own.
try:
    from presentation_job.deliverables import (
        DELIVERABLE_AUDIT_SPEC,
        REQUIRED_DELIVERABLES,
        REQUIRED_KEYS,
        DELIVERABLE_COUNT,
        BUNDLE_COMPLETE_FILENAME,
        AF_BUNDLE_INCOMPLETE,
        _expand_filename,
    )
except ImportError:
    _SCRIPTS = Path(__file__).resolve().parent
    if str(_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS))
    from presentation_job.deliverables import (
        DELIVERABLE_AUDIT_SPEC,
        REQUIRED_DELIVERABLES,
        REQUIRED_KEYS,
        DELIVERABLE_COUNT,
        BUNDLE_COMPLETE_FILENAME,
        AF_BUNDLE_INCOMPLETE,
        _expand_filename,
    )

# sync_check.py LOCKSTEP — C1 emission registry (same pattern as delivery_gate.py
# _EMITTED_AF_CODES). sync_check scans every script named in an autofails[]
# check_script for `"code": "AF-..."` dicts and FAILS (exit 4) if any emitted
# code is not registered in PIPELINE-MANIFEST.autofails. This literal makes the
# EXACT code this gate can emit machine-discoverable. It MUST stay registered.
_EMITTED_AF_CODES = (
    {"code": "AF-BUNDLE-INCOMPLETE"},  # one+ of deliverables missing/empty
)


def check_bundle_complete(bundle_dir, deck_slug="deck") -> list:
    """Return a list of missing-or-undersized deliverable KEYS in bundle_dir.
    [] means the full bundle is present at real substance.
    Never raises: an unreadable bundle_dir is reported as 'all missing'
    (fail-closed). A REAL regular file must clear its DELIVERABLE_AUDIT_SPEC
    min_bytes floor — F27: before this, only size==0 was rejected, so a
    1-byte stub (e.g. audio_mp3 with a 512 KB floor) passed FIX-8 as "done".
    A zero-byte placeholder or a symlink-to-nowhere is still NOT done."""
    bundle_dir = Path(bundle_dir)
    min_bytes_by_key = {d["key"]: d.get("min_bytes", 1) for d in DELIVERABLE_AUDIT_SPEC}
    missing = []
    for spec in REQUIRED_DELIVERABLES:
        key = spec["key"]
        fname = _expand_filename(spec["filename"], deck_slug)
        path = bundle_dir / fname
        # lexists: a broken/dangling symlink is seen as present-but-rejected,
        # never silently "absent" (mirrors build_deck's postflight gate).
        if not os.path.lexists(str(path)):
            missing.append(key)
            continue
        if path.is_symlink():
            # A symlink is not a deliverable file — it can point at a decoy.
            missing.append(key)
            continue
        try:
            size = path.stat().st_size
            if not path.is_file() or size < max(1, int(min_bytes_by_key.get(key, 1))):
                missing.append(key)
        except OSError:
            missing.append(key)
    return missing


def run_bundle_gate(bundle_dir, deck_slug="deck"):
    """Run the full FIX-8 gate over bundle_dir. Returns
    (ok: bool, missing_keys: list[str], gate_path: Path|None).

    Fail-closed: any missing/empty key -> ok=False and NO bundle_complete.json
    is written (a stale one is removed so a previous pass cannot mask a
    regression). On pass, writes bundle_complete.json and returns its path.
    """
    bundle_dir = Path(bundle_dir)
    gate_path = bundle_dir / BUNDLE_COMPLETE_FILENAME
    missing = check_bundle_complete(bundle_dir, deck_slug=deck_slug)

    if missing:
        # Remove a stale pass marker so a partial bundle is NEVER reported done.
        try:
            if gate_path.exists():
                gate_path.unlink()
        except OSError:
            pass
        return False, missing, None

    # All present and non-empty -> write the durable pass marker.
    bundle_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "gate": BUNDLE_COMPLETE_FILENAME,
        "complete": True,
        "deck_slug": deck_slug,
        "deliverable_count": len(DELIVERABLE_AUDIT_SPEC),
        "deliverables": {
            spec["key"]: _expand_filename(spec["filename"], deck_slug)
            for spec in REQUIRED_DELIVERABLES
        },
        "checked_at": _now_utc(),
    }
    try:
        gate_path.write_text(json.dumps(record, indent=2))
    except OSError as exc:  # cannot write the gate artifact -> fail closed
        return False, [f"cannot write {BUNDLE_COMPLETE_FILENAME}: {exc!r}"], None
    return True, [], gate_path


def fix_bundle_complete(bundle_dir, deck_slug="deck") -> bool:
    """Thin in-pipeline wrapper: True iff the full bundle is
    complete (writes bundle_complete.json on pass). Fail-closed otherwise."""
    ok, _missing, _gate = run_bundle_gate(bundle_dir, deck_slug=deck_slug)
    return ok


def resolve_bundle_dir(run_dir, explicit_bundle_dir=None):
    """Resolve the operator build bundle dir (where the deliverables live)
    for a governed run dir, matching build_deck.py's convention:
      1. an explicit bundle dir (--out override / --bundle-dir arg);
      2. the `bundleDir` recorded in working/checkpoints/process_manifest.json;
      3. ~/Downloads/<deck-slug>/ (build_deck's BUNDLE_DIR_DEFAULT convention,
         deck-slug from the run dir's intake/config or the run dir name);
      4. the run dir itself (some flows keep the bundle in the run dir).

    Returns a Path (never None) — callers must still treat a partial/missing
    bundle as fail-closed regardless of which candidate was chosen."""
    run_dir = Path(run_dir)
    if explicit_bundle_dir:
        return Path(explicit_bundle_dir)
    # 2. recorded bundleDir in the process manifest
    pm = run_dir / "working" / "checkpoints" / "process_manifest.json"
    try:
        obj = json.loads(pm.read_text())
        rec = obj.get("bundleDir") or obj.get("bundle_dir")
        if rec and str(rec).strip():
            return Path(str(rec).strip())
    except Exception:  # noqa: BLE001
        pass
    # 3. ~/Downloads/<deck-slug>/
    slug = _deck_slug(run_dir)
    dl = Path.home() / "Downloads" / slug
    return dl


def _deck_slug(run_dir) -> str:
    """Mirror run_signature_deck._deck_slug: deck slug from intake/config, else
    the run dir base name. Slugified to [a-z0-9-] like build_deck._slugify."""
    import re as _re
    run_dir = Path(run_dir)
    for cand in [run_dir / "working" / "copy" / "intake.json",
                 run_dir / "working" / "config.json"]:
        try:
            obj = json.loads(cand.read_text())
            if isinstance(obj, dict):
                for k in ("deck_slug", "slug", "title"):
                    v = (obj.get(k) or "").strip()
                    if v:
                        s = _re.sub(r"[^a-z0-9]+", "-", str(v).lower()).strip("-")
                        return s or str(v)
        except Exception:  # noqa: BLE001
            pass
    return run_dir.name


def _now_utc() -> str:
    try:
        import datetime
        return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    except Exception:  # noqa: BLE001 — never let a timestamp fail the gate
        return ""


# ---------------------------------------------------------------------------
# SELF-TEST — built-in pass + fail fixtures (no external deps, no network).
# ---------------------------------------------------------------------------
def _selftest() -> int:
    import tempfile

    fails = []

    # CASE A — deck-only bundle (the live E2E failure) -> FAILS, missing 8.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        # A real deck pptx at full floor size, nothing else.
        _a_floor = max(int(next(d for d in DELIVERABLE_AUDIT_SPEC
                                if d["key"] == "deck_pptx").get("min_bytes", 1)), 1)
        (base / "deck-FINAL.pptx").write_bytes(b"x" * _a_floor)
        missing = check_bundle_complete(base, deck_slug="deck")
        expect = set(REQUIRED_KEYS) - {"deck_pptx"}
        if set(missing) != expect:
            fails.append(f"A deck-only: expected missing={sorted(expect)}, got {sorted(missing)}")
        ok, miss, gate = run_bundle_gate(base, deck_slug="deck")
        if ok:
            fails.append("A deck-only: gate must FAIL on a deck-only bundle")
        if gate is not None:
            fails.append(f"A deck-only: no bundle_complete.json must be written, got {gate}")
        if (base / BUNDLE_COMPLETE_FILENAME).exists():
            fails.append("A deck-only: a stale bundle_complete.json must be removed on failure")

    # CASE B — zero-byte placeholder treated as missing (not 'done').
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        (base / "deck-FINAL.pptx").write_bytes(b"")
        (base / "PRESENTERS-SPEECH.md").write_text("real speech text" * 400)
        missing = check_bundle_complete(base, deck_slug="deck")
        if "deck_pptx" not in missing:
            fails.append("B zero-byte: a zero-byte deck_pptx must count as missing")
        if "speech_md" in missing:
            fails.append("B zero-byte: a real speech_md must NOT be missing")

    # CASE F27 — a NON-empty but undersized stub counts as missing: audio_mp3
    # has a 512 KB floor; a 1-byte 'audio.mp3' previously passed FIX-8.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        min_by_key = {d["key"]: d.get("min_bytes", 1) for d in DELIVERABLE_AUDIT_SPEC}
        for spec in REQUIRED_DELIVERABLES:
            fname = _expand_filename(spec["filename"], "deck")
            floor = int(min_by_key.get(spec["key"], 1))
            if spec["key"] == "audio_mp3":
                (base / fname).write_bytes(b"ID3stub")  # 8 bytes << 512 KB floor
            else:
                (base / fname).write_bytes(b"x" * max(floor, 1))
        missing = check_bundle_complete(base, deck_slug="deck")
        if missing != ["audio_mp3"]:
            fails.append(f"F27 stub: expected ['audio_mp3'] undersized, got {sorted(missing)}")

    def _write_full_bundle(base: Path, slug: str) -> None:
        min_by_key = {d["key"]: d.get("min_bytes", 1) for d in DELIVERABLE_AUDIT_SPEC}
        for spec in REQUIRED_DELIVERABLES:
            fname = _expand_filename(spec["filename"], slug)
            (base / fname).write_bytes(b"x" * max(int(min_by_key.get(spec["key"], 1)), 1))

    # CASE C — full bundle -> PASSES, bundle_complete.json written.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        _write_full_bundle(base, "deck")
        missing = check_bundle_complete(base, deck_slug="deck")
        if missing:
            fails.append(f"C full: expected no missing, got {sorted(missing)}")
        ok, miss, gate = run_bundle_gate(base, deck_slug="deck")
        if not ok:
            fails.append(f"C full: full bundle must PASS, got ok=False miss={miss}")
        if gate is None or not gate.is_file():
            fails.append("C full: bundle_complete.json must be written on pass")
        else:
            rec = json.loads(gate.read_text())
            if rec.get("complete") is not True:
                fails.append("C full: bundle_complete.json record.complete must be true")
            if rec.get("deliverable_count") != len(DELIVERABLE_AUDIT_SPEC):
                fails.append("C full: bundle_complete.json must record all deliverables")

    # CASE D — deck_slug templating.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        _write_full_bundle(base, "acme-q1")
        missing = check_bundle_complete(base, deck_slug="acme-q1")
        if missing:
            fails.append(f"D slug: expected no missing, got {sorted(missing)}")
        ok, _m, gate = run_bundle_gate(base, deck_slug="acme-q1")
        if not ok:
            fails.append("D slug: slugged full bundle must PASS")

    # CASE E — manifest cross-check: the keys must match the
    # PIPELINE-MANIFEST build_bundle_files list (they must never drift).
    try:
        # Walk up from this script until the PIPELINE-MANIFEST is found (the
        # repo layout can nest at different depths across worktrees/deploys).
        manifest_path = None
        cur = Path(__file__).resolve().parent
        for _ in range(8):
            cand = cur / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
            if cand.is_file():
                manifest_path = cand
                break
            cur = cur.parent
        if manifest_path is None:
            raise FileNotFoundError("PIPELINE-MANIFEST.json not found by walking up")
        man = json.loads(manifest_path.read_text())
        manifest_keys = man.get("build_bundle_files", [])
        if sorted(manifest_keys) != sorted(REQUIRED_KEYS):
            fails.append(
                f"E manifest: PIPELINE-MANIFEST.build_bundle_files {sorted(manifest_keys)} "
                f"!= fix_bundle_complete.REQUIRED_KEYS {sorted(REQUIRED_KEYS)} — they drifted")
    except Exception as exc:  # noqa: BLE001
        fails.append(f"E manifest: could not cross-check PIPELINE-MANIFEST: {exc!r}")

    if fails:
        print("fix_bundle_complete selftest -> FAIL")
        for f in fails:
            print("  -", f)
        return 1
    print("fix_bundle_complete selftest -> PASS "
          "(deck-only-fails/nonempty-floor/full-passes/slug-templating/manifest-lockstep)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="FIX-8 full deliverable bundle gate (AF-BUNDLE-INCOMPLETE).")
    ap.add_argument("bundle_dir", nargs="?",
                    help="the operator build bundle directory (or use --run-dir)")
    ap.add_argument("--run-dir", dest="run_dir", help="governed run dir; the bundle dir "
                    "is resolved from process_manifest/Downloads/run dir")
    ap.add_argument("--bundle-dir", dest="bundle_dir_opt",
                    help="explicit bundle dir override (with --run-dir)")
    ap.add_argument("--deck-slug", default=None,
                    help="deck slug for {deck_slug}-templated filenames")
    ap.add_argument("--json", action="store_true", help="emit JSON result")
    ap.add_argument("--selftest", action="store_true", help="run built-in fixtures")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()

    if args.run_dir:
        bundle_dir = resolve_bundle_dir(args.run_dir, args.bundle_dir_opt)
        slug = args.deck_slug or _deck_slug(args.run_dir)
        if not bundle_dir.is_dir():
            print(f"fix_bundle_complete: resolved bundle dir not a directory: "
                  f"{bundle_dir} (run-dir mode; nothing to gate — fail-closed)",
                  file=sys.stderr)
            return 2
    elif args.bundle_dir:
        bundle_dir = Path(args.bundle_dir)
        slug = args.deck_slug or "deck"
    else:
        ap.error("bundle_dir or --run-dir is required (or use --selftest)")

    if not bundle_dir.is_dir():
        print(f"fix_bundle_complete: bundle_dir not a directory: {bundle_dir}",
              file=sys.stderr)
        return 2

    ok, missing, gate = run_bundle_gate(bundle_dir, deck_slug=slug)
    if args.json:
        print(json.dumps({
            "ok": ok,
            "gate": BUNDLE_COMPLETE_FILENAME,
            "required": REQUIRED_KEYS,
            "missing": sorted(missing),
            "bundle_complete_path": str(gate) if gate else None,
        }, indent=2))
        return 0 if ok else 1

    if ok:
        print(f"BUNDLE COMPLETE: all {len(REQUIRED_DELIVERABLES)} deliverables "
              f"present and non-empty. Gate artifact: {gate}")
        return 0
    print(f"FATAL [{AF_BUNDLE_INCOMPLETE}]: the full 9-deliverable bundle is "
          f"INCOMPLETE. Missing/empty:", file=sys.stderr)
    for key in sorted(missing):
        label = next((d["label"] for d in REQUIRED_DELIVERABLES if d["key"] == key), key)
        print(f"  - {key} ({label})", file=sys.stderr)
    print("The run may NOT be reported as 'done'. Re-run the upstream producer "
          "roles until all deliverables exist and are non-empty.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
