#!/usr/bin/env python3
"""
bundle_gate.py — MASTER Part 8 FIX 1: the bundle-completeness gate as its OWN
terminal phase (P-BUNDLE-GATE), taken OUT of the render phase.

WHY THIS EXISTS (FIX 1):
Before this script, the ONLY way run_postflight_gate() (the AF-BUNDLE-COMPLETE
completeness gate in build_deck.py) ever ran was as the tail of build_deck.py's
render main(). That made the RENDER phase structurally unable to exit zero on a
fresh run: the render genuinely succeeds (12 verified PNGs, a real .pptx) but the
gate then demands the guide PDF, speech, audio, infographic, teleprompter and deck
PDF — artifacts produced by LATER phases — and exits 5. Twelve baked slides were
still "blocked" a day later.

FIX 1 splits the phases:
  * build_deck.py (render) gates only on RENDER outputs. (The --bundle-gate flag
    on build_deck.py re-arms the old inline behavior; default is OFF — that half
    of the fix lives in build_deck.py / the W01 lane.)
  * THIS script is the bundle-completeness terminal phase. It resolves the same
    bundle dir, deliverables ledger and deck slug the render main() used, then
    calls build_deck.run_postflight_gate() DIRECTLY — the exact, unchanged
    postflight body (every AF-* sub-check, the deliverables.json ledger, exit 5
    on any missing/under-threshold artifact, "COMPLETE" printed only when the
    read-back ledger is all-verified). No copy of the gate lives here: one gate,
    one body, two callers.

CLI:
  python3 bundle_gate.py --run-dir <run> [--bundle-dir DIR] [--deck-slug SLUG]
                         [--skip-teleprompter-gate] [--adhoc] [--slides PATH]

  --run-dir               governed run dir (contains working/). Required unless
                          --bundle-dir is given for a bare-dir invocation.
  --bundle-dir            explicit bundle dir override (else resolved exactly
                          like the render main: the process manifest's
                          recorded bundleDir, else ~/Downloads/<deck-slug>).
  --deck-slug             slug for {deck_slug}-templated filenames (else
                          derived from intake/config like fix_bundle_complete,
                          else the run dir name).
  --skip-teleprompter-gate  explicit per-run bypass of the teleprompter-publish
                          sub-check (same M7 contract as build_deck's flag).
  --adhoc                 ad-hoc invocation: implies the teleprompter-gate
                          bypass for THIS run only (render main's --adhoc
                          semantics) and skips slides-path-dependent sub-checks
                          that need a slides.json.
  --slides                optional slides.json path; when supplied it is
                          threaded into run_postflight_gate so the run-dir
                          sub-checks (visual variety, image QC, canonical
                          render path, ...) count the exact rendered file.

EXIT CODES (identical to the gate it wraps):
  0 — every required bundle deliverable verified ("=== COMPLETE ===").
  5 — AF-BUNDLE-COMPLETE failed: missing / under-threshold / wrong-type /
      unpublished artifacts, listed on stderr.
  2 — could not run (bad args, unresolvable bundle dir).

Zero third-party deps. The heavy import (build_deck, ~13k lines) happens lazily
inside main() AFTER the scripts dir is put on sys.path, so `--help` and argument
errors never pay for it and a bare invocation off-tree still resolves the
package the same way build_deck's own sibling imports do.
"""

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent


def _ensure_import_path() -> None:
    """Put this script's dir on sys.path so `import build_deck` resolves the
    sibling module (and build_deck's own `presentation_job` package imports)
    regardless of the caller's cwd."""
    if str(_SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS_DIR))


def _deck_slug(run_dir: Path) -> str:
    """Deck slug mirror of fix_bundle_complete._deck_slug: intake/config first,
    else the run dir name, slugified to [a-z0-9-] like build_deck._slugify."""
    import re as _re
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
        except Exception:  # noqa: BLE001 — absent/unreadable intake -> next candidate
            pass
    return _re.sub(r"[^a-z0-9]+", "-", run_dir.name.lower()).strip("-") or run_dir.name


def _resolve_bundle_dir(run_dir: Path, explicit: str | None) -> Path:
    """Resolve the bundle dir exactly like build_deck's render main:
    explicit --bundle-dir wins; else the bundleDir recorded in
    working/checkpoints/process_manifest.json (written by write_process_manifest
    at render time); else ~/Downloads/<deck-slug> (BUNDLE_DIR_DEFAULT
    convention). A directory is NOT required — the gate must be runnable on a
    dir that has not been created yet (fail-closed ABSENT entries, never a
    crash)."""
    if explicit:
        return Path(explicit).expanduser().resolve()
    pm = run_dir / "working" / "checkpoints" / "process_manifest.json"
    try:
        obj = json.loads(pm.read_text())
        rec = obj.get("bundleDir") or obj.get("bundle_dir") if isinstance(obj, dict) else None
        if rec and str(rec).strip():
            return Path(str(rec).strip()).expanduser().resolve()
    except Exception:  # noqa: BLE001 — no manifest / unreadable -> fall through
        pass
    return Path.home() / "Downloads" / _deck_slug(run_dir)


def _existing_ledger_or_none(bundle_dir: Path) -> Path | None:
    """Return the bundle's deliverables.json when a render main() (or an earlier
    bundle-gate run) has already written one; None otherwise."""
    lp = bundle_dir / "deliverables.json"
    return lp if lp.exists() else None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="FIX 1 bundle-completeness terminal phase: wraps "
                    "build_deck.run_postflight_gate (AF-BUNDLE-COMPLETE).")
    ap.add_argument("--run-dir", dest="run_dir", default=None,
                    help="governed run dir (contains working/)")
    ap.add_argument("--bundle-dir", dest="bundle_dir", default=None,
                    help="explicit bundle dir override")
    ap.add_argument("--deck-slug", dest="deck_slug", default=None,
                    help="deck slug for {deck_slug}-templated filenames")
    ap.add_argument("--skip-teleprompter-gate", action="store_true",
                    help="explicit per-run bypass of the teleprompter-publish sub-check")
    ap.add_argument("--adhoc", action="store_true",
                    help="ad-hoc invocation: implies the teleprompter-gate bypass")
    ap.add_argument("--slides", dest="slides", default=None,
                    help="slides.json path threaded into the run-dir sub-checks")
    args = ap.parse_args(argv)

    if not args.run_dir and not args.bundle_dir:
        ap.error("--run-dir is required (or pass --bundle-dir for a bare-dir gate)")

    run_dir = Path(args.run_dir).expanduser().resolve() if args.run_dir else None
    if run_dir is not None and not (run_dir / "working").is_dir():
        print(f"bundle_gate: --run-dir {run_dir} has no working/ subtree — "
              f"not a governed run dir.", file=sys.stderr)
        return 2

    deck_slug = args.deck_slug
    if not deck_slug:
        if run_dir is not None:
            deck_slug = _deck_slug(run_dir)
        else:
            deck_slug = "deck"

    bundle_dir = (
        _resolve_bundle_dir(run_dir, args.bundle_dir)
        if run_dir is not None
        else Path(args.bundle_dir).expanduser().resolve()
    )

    ledger_path = _existing_ledger_or_none(bundle_dir)
    if ledger_path is None:
        # No render has written the ledger yet: create it in the same shape the
        # render main does (init_deliverables_ledger) so run_postflight_gate
        # can update + read it back. Imported lazily — see module docstring.
        # The gate must run on a bundle dir that has never been created (a fresh
        # run resolves ~/Downloads/<slug> before any render touches it), so make
        # the directory first: init_deliverables_ledger writes deliverables.json
        # directly into it and fails closed (FileNotFoundError -> exit 1) on an
        # absent parent. Fail-closed ABSENT entries, never a crash.
        bundle_dir.mkdir(parents=True, exist_ok=True)
        _ensure_import_path()
        import build_deck as _bd  # noqa: PLC0415
        ledger_path = _bd.init_deliverables_ledger(bundle_dir, deck_slug)

    slides_path = Path(args.slides).expanduser().resolve() if args.slides else None

    print(f"=== BUNDLE GATE (P-BUNDLE-GATE / FIX 1): bundle={bundle_dir} "
          f"slug={deck_slug} ===", flush=True)

    _ensure_import_path()
    import build_deck as _bd  # noqa: PLC0415
    # The postflight body owns the outcome: prints COMPLETE and returns on an
    # all-verified read-back; prints the loud AF-BUNDLE-COMPLETE report and
    # sys.exit(5) otherwise. Thread the run_dir through so every run-dir
    # sub-check (KIE-baked re-prove, visual variety, image QC, canonical render
    # path, owner-skip disclosure...) runs exactly as it does in the render main.
    _bd.run_postflight_gate(
        bundle_dir, ledger_path, deck_slug,
        skip_teleprompter_gate=bool(args.skip_teleprompter_gate or args.adhoc),
        run_dir=run_dir,
        slides_path=slides_path,
    )
    # run_postflight_gate returning normally == the gate passed.
    return 0


if __name__ == "__main__":
    sys.exit(main())
