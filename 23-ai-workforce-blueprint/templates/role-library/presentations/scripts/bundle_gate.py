#!/usr/bin/env python3
"""
bundle_gate.py — the bundle-completeness gate for P-BUNDLE-GATE.

WHY THIS EXISTS (FIX 1): before this script the completeness gate
(run_postflight_gate in build_deck.py) ran only as the tail of build_deck.py's
render main(), so the RENDER phase could never exit zero on a fresh run.

PD-063 (Critical) fixed three defects in the first version of this script:

  * it resolved the bundle dir to ``~/Downloads/<deck-slug>`` — the client's
    home folder, on every governed run, and CREATED it when absent;
  * it templated the deck filenames from the INTERVIEW name (``_deck_slug``
    reads intake ``deck_slug``/``slug``/``title``), so a deck assembled as
    ``acme-q1-FINAL.pptx`` was hunted as ``quarterly-review-FINAL.pptx``;
  * neither it nor run_postflight_gate wrote ``working/checkpoints/
    bundle_gate.json``, which ``phase_verifiers._verify_bundle_gate`` requires —
    the phase could pass and still be unverifiable.

WHAT IT DOES NOW (governed run: ``--run-dir`` and no ``--bundle-dir``):

  1. Each deliverable is taken from its DECLARED path inside the run folder,
     using ``presentation_job.deliverable_paths.CANONICAL_PATHS`` — one table,
     no second copy — plus that module's documented ``ALIAS_PATHS``.
  2. The deck and deck PDF are matched by the ``*-FINAL`` pattern, never by the
     interview name.
  3. ``infographic_png`` is skipped ONLY when the engine's own state records
     the infographic step as ``routed_around`` (a legitimately skipped
     infographic, PD-TEST-168b). Nothing else excuses it.
  4. ``working/checkpoints/bundle_gate.json`` is ALWAYS written (atomic) before
     exiting 0 or 5:
         {"ok": true|false, "missing": [...], "checked_at": "<utc iso8601>"}
  5. Nothing outside the run folder is created or read. The home folder is
     never consulted on a governed run.

Per-file substance mirrors the postflight body: symlinks and non-regular files
are rejected, the per-key ``min_bytes`` floor from
``build_deck.DELIVERABLES_REQUIRED`` applies (with ``deliverable_floors``
scaling for the deck and guide PDFs), and the magic-byte content-type check
runs for every typed key. Run-dir QUALITY sub-checks (KIE-baked, visual
variety, image QC, brand consistency, speech length) stay with the phases that
own them — this phase attests the BUNDLE.

LEGACY BARE-DIR MODE (``--bundle-dir DIR``): an explicit flat bundle dir still
runs the original ``build_deck.run_postflight_gate`` body unchanged, for the
operator/bare-dir invocation that predates the run-folder model. It writes the
same verdict file when ``--run-dir`` is also given. There is no longer any
implicit bundle-dir resolution: a caller that wants the flat gate names the
folder.

CLI:
  python3 bundle_gate.py --run-dir <run> [--deck-slug SLUG] [--slides PATH]
  python3 bundle_gate.py --bundle-dir <dir> [--run-dir <run>] [--deck-slug SLUG]
                         [--skip-teleprompter-gate] [--adhoc] [--slides PATH]

EXIT CODES:
  0 — every required bundle deliverable verified.
  5 — AF-BUNDLE-COMPLETE failed: absent / under-threshold / wrong-type /
      rejected artifacts, listed on stderr; the verdict file records them.
  2 — could not run (bad args, not a governed run dir).

Zero third-party deps. The heavy import (build_deck) happens lazily, after the
scripts dir is put on sys.path, so ``--help`` and argument errors never pay for
it.
"""

import argparse
import json
import os
import stat as _stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

_SCRIPTS_DIR = Path(__file__).resolve().parent

# The gate's own verdict record. phase_verifiers._verify_bundle_gate requires
# exactly this path (the manifest's P-BUNDLE-GATE produces_artifact).
VERDICT_REL = "working/checkpoints/bundle_gate.json"

# The infographic step whose `routed_around` state exempts infographic_png.
INFOGRAPHIC_PHASE = "P8.3-INFOGRAPHIC"

# Keys whose filename is resolved by the *-FINAL pattern rather than the
# interview-derived deck slug (PD-063 requirement 2).
_FINAL_PATTERN_KEYS = ("deck_pptx", "deck_pdf")


def _ensure_import_path() -> None:
    """Put this script's dir on sys.path so sibling/package imports resolve
    regardless of the caller's cwd."""
    if str(_SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS_DIR))


# ---------------------------------------------------------------------------
# small IO helpers
# ---------------------------------------------------------------------------

def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:  # noqa: BLE001 — absent/unreadable is a normal outcome here
        return None


def _routed_around_phases(run_dir: Path) -> set:
    """Phase ids the engine recorded as `routed_around: true` in state.json.

    An absent or unreadable state file returns the empty set — fail closed: an
    unproven skip never exempts a required deliverable."""
    state = _read_json(run_dir / "state.json")
    if not isinstance(state, dict):
        return set()
    out = set()
    for row in state.get("phases") or []:
        if isinstance(row, dict) and row.get("routed_around") is True:
            pid = row.get("id")
            if isinstance(pid, str) and pid:
                out.add(pid)
    return out


def _deck_slug(run_dir: Path) -> str:
    """Deck slug for {deck_slug}-templated filenames (legacy mode's flat gate
    and the webinar/video key). The deck ITSELF is never resolved by this name
    — see _candidates()."""
    import re as _re
    for cand in [run_dir / "working" / "copy" / "intake.json",
                 run_dir / "working" / "config.json"]:
        obj = _read_json(cand)
        if isinstance(obj, dict):
            for k in ("deck_slug", "slug", "title"):
                v = (obj.get(k) or "").strip()
                if v:
                    s = _re.sub(r"[^a-z0-9]+", "-", str(v).lower()).strip("-")
                    return s or str(v)
    return _re.sub(r"[^a-z0-9]+", "-", run_dir.name.lower()).strip("-") or run_dir.name


def _write_verdict(run_dir: Path, ok: bool, missing: List[str],
                   reasons: Optional[List[str]] = None) -> Path:
    """Atomically write working/checkpoints/bundle_gate.json inside the run dir."""
    path = run_dir / VERDICT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ok": bool(ok),
        "missing": list(missing),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    if reasons:
        payload["reasons"] = list(reasons)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path


# ---------------------------------------------------------------------------
# governed run-folder resolution
# ---------------------------------------------------------------------------

def _path_table():
    """The ONE canonical path table (presentation_job.deliverable_paths)."""
    _ensure_import_path()
    from presentation_job import deliverable_paths  # noqa: PLC0415
    return deliverable_paths


def _candidates(key: str, deck_slug: str, dp) -> List[str]:
    """Run-dir-relative patterns for one key: the canonical path first, then the
    module's documented aliases.

    The deck pair is templated with `*` so it is found by the *-FINAL pattern
    whatever the assembled name is (PD-063 requirement 2). Other templated keys
    try the resolve deck slug, then the same wildcard as a fallback."""
    rels = []
    canon = dp.CANONICAL_PATHS.get(key)
    if canon:
        rels.append(canon)
    rels.extend(dp.ALIAS_PATHS.get(key, []))
    out: List[str] = []
    for rel in rels:
        if not rel or rel in out:
            continue
        if "{deck_slug}" in rel:
            if key in _FINAL_PATTERN_KEYS:
                rel = rel.replace("{deck_slug}", "*")
            else:
                with_slug = rel.replace("{deck_slug}", deck_slug)
                if with_slug not in out:
                    out.append(with_slug)
                rel = rel.replace("{deck_slug}", "*")
        if rel not in out:
            out.append(rel)
    return out


def _find(run_dir: Path, rel: str) -> Optional[Path]:
    """Resolve one run-dir-relative pattern. lexists so a dangling symlink is
    SEEN (and then rejected by _check_file) instead of looking absent."""
    if "*" in rel or "?" in rel:
        try:
            hits = sorted(p for p in run_dir.glob(rel) if os.path.lexists(str(p)))
        except Exception:  # noqa: BLE001 — malformed pattern -> absent
            return None
        return hits[0] if hits else None
    p = run_dir / rel
    return p if os.path.lexists(str(p)) else None


def _deliverable_specs() -> dict:
    """key -> build_deck.DELIVERABLES_REQUIRED row (min_bytes/label/magic).
    An import failure degrades to presence-only; it never crashes the gate."""
    try:
        _ensure_import_path()
        import build_deck as _bd  # noqa: PLC0415
        return {spec["key"]: spec for spec in _bd.DELIVERABLES_REQUIRED}
    except Exception:  # noqa: BLE001
        return {}


def _check_file(key: str, path: Path, spec: Optional[dict], run_dir: Path) -> Optional[str]:
    """Per-file substance: symlink, non-regular, byte floor, magic bytes.
    Returns a reason string, or None when the file is acceptable."""
    if path.is_symlink():
        return "path is a symlink (rejected: a symlink can point at a decoy)"
    st = os.lstat(str(path))
    if not _stat.S_ISREG(st.st_mode):
        return "path is not a regular file (rejected)"
    if spec is None:
        return None
    if spec.get("produced_later"):
        return None
    min_bytes = spec["min_bytes"]
    if key in ("guide_pdf", "deck_pdf"):
        try:
            _ensure_import_path()
            from presentation_job import deliverable_floors as _floors  # noqa: PLC0415
            n = _floors.slide_count(run_dir)
            if n:
                min_bytes = (_floors.guide_floor(n) if key == "guide_pdf"
                             else _floors.pdf_floor(n))
        except Exception:  # noqa: BLE001 — keep the static floor
            pass
    if st.st_size < min_bytes:
        return f"file too small: {st.st_size} bytes (min {min_bytes})"
    try:
        _ensure_import_path()
        import build_deck as _bd  # noqa: PLC0415
        sigs = _bd.DELIVERABLE_MAGIC.get(key)
        if sigs is not None and not _bd._magic_ok(path, sigs):
            return ("wrong content type: leading bytes do not match the expected "
                    f"magic for {key}")
    except Exception:  # noqa: BLE001 — magic check unavailable -> skip, not crash
        pass
    return None


def _governed_check(run_dir: Path, deck_slug: str) -> Tuple[bool, List[str], List[str]]:
    """Resolve every declared deliverable from the run's own files.

    Returns (ok, missing, reasons). `missing` names the canonical run-dir path
    the run did not carry; `reasons` carries the per-key detail."""
    dp = _path_table()
    routed = _routed_around_phases(run_dir)
    specs = _deliverable_specs()
    missing: List[str] = []
    reasons: List[str] = []

    for key in dp.CANONICAL_PATHS:
        if key == "infographic_png" and INFOGRAPHIC_PHASE in routed:
            # PD-063: the ONLY legitimate skip — the engine's own state says the
            # infographic step was routed around.
            continue
        cands = _candidates(key, deck_slug, dp)
        found = None
        for rel in cands:
            found = _find(run_dir, rel)
            if found is not None:
                break
        display = dp.CANONICAL_PATHS[key].replace("{deck_slug}", deck_slug)
        if found is None:
            missing.append(display)
            reasons.append(f"{display}: absent ({key}; looked in: "
                           f"{', '.join(cands)})")
            continue
        why = _check_file(key, found, specs.get(key), run_dir)
        if why:
            try:
                shown = str(found.relative_to(run_dir))
            except ValueError:
                shown = str(found)
            missing.append(shown)
            reasons.append(f"{shown}: {why} ({key})")

    return (not missing), missing, reasons


# ---------------------------------------------------------------------------
# legacy bare-dir mode (explicit --bundle-dir)
# ---------------------------------------------------------------------------

def _flat_missing(bundle_dir: Path, deck_slug: str, specs: dict) -> List[str]:
    """The names a flat bundle dir is missing (legacy mode's verdict detail)."""
    out = []
    for key, spec in specs.items():
        if spec.get("produced_later"):
            continue
        fname = str(spec["filename"]).replace("{deck_slug}", deck_slug)
        if not os.path.lexists(str(bundle_dir / fname)):
            out.append(fname)
    return out


def _legacy_main(args, run_dir: Optional[Path], bundle_dir: Path, deck_slug: str) -> int:
    _ensure_import_path()
    import build_deck as _bd  # noqa: PLC0415

    ledger_path = bundle_dir / "deliverables.json"
    if not ledger_path.exists():
        bundle_dir.mkdir(parents=True, exist_ok=True)
        ledger_path = _bd.init_deliverables_ledger(bundle_dir, deck_slug)

    print(f"=== BUNDLE GATE (P-BUNDLE-GATE, legacy flat dir): bundle={bundle_dir} "
          f"slug={deck_slug} ===", flush=True)
    try:
        _bd.run_postflight_gate(
            bundle_dir, ledger_path, deck_slug,
            skip_teleprompter_gate=bool(args.skip_teleprompter_gate or args.adhoc),
            run_dir=run_dir,
            slides_path=(Path(args.slides).expanduser().resolve()
                         if args.slides else None),
        )
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
        if run_dir is not None and code != 0:
            specs = {s["key"]: s for s in _bd.DELIVERABLES_REQUIRED}
            _write_verdict(run_dir, False, _flat_missing(bundle_dir, deck_slug, specs),
                           ["run_postflight_gate exited "
                            f"{code}; see its report on stderr"])
        raise
    if run_dir is not None:
        _write_verdict(run_dir, True, [])
    return 0


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="P-BUNDLE-GATE: resolve every declared bundle deliverable "
                    "from the run's own files and record working/checkpoints/"
                    "bundle_gate.json.")
    ap.add_argument("--run-dir", dest="run_dir", default=None,
                    help="governed run dir (contains working/)")
    ap.add_argument("--bundle-dir", dest="bundle_dir", default=None,
                    help="explicit flat bundle dir (legacy bare-dir gate)")
    ap.add_argument("--deck-slug", dest="deck_slug", default=None,
                    help="deck slug for {deck_slug}-templated filenames")
    ap.add_argument("--skip-teleprompter-gate", action="store_true",
                    help="legacy mode only: bypass the teleprompter-publish sub-check")
    ap.add_argument("--adhoc", action="store_true",
                    help="legacy mode only: implies the teleprompter-gate bypass")
    ap.add_argument("--slides", dest="slides", default=None,
                    help="legacy mode only: slides.json path threaded into the "
                         "run-dir sub-checks")
    args = ap.parse_args(argv)

    if not args.run_dir and not args.bundle_dir:
        ap.error("--run-dir is required (or pass --bundle-dir for a bare-dir gate)")

    run_dir = Path(args.run_dir).expanduser().resolve() if args.run_dir else None
    if run_dir is not None and not (run_dir / "working").is_dir():
        print(f"bundle_gate: --run-dir {run_dir} has no working/ subtree — "
              f"not a governed run dir.", file=sys.stderr)
        return 2

    deck_slug = args.deck_slug or (_deck_slug(run_dir) if run_dir is not None else "deck")

    if args.bundle_dir:
        return _legacy_main(args, run_dir, Path(args.bundle_dir).expanduser().resolve(),
                            deck_slug)

    # Governed run-folder mode: every deliverable comes from its declared path
    # inside the run; the home folder is never read or written.
    print(f"=== BUNDLE GATE (P-BUNDLE-GATE): run={run_dir} slug={deck_slug} ===",
          flush=True)
    ok, missing, reasons = _governed_check(run_dir, deck_slug)
    verdict_path = _write_verdict(run_dir, ok, missing, reasons)
    print(f"bundle_gate: verdict -> {verdict_path}", flush=True)
    if ok:
        print("=== COMPLETE ===", flush=True)
        return 0
    print(f"AF-BUNDLE-COMPLETE: {len(missing)} bundle deliverable(s) missing or "
          f"unacceptable:", file=sys.stderr)
    for reason in reasons or missing:
        print(f"  - {reason}", file=sys.stderr)
    return 5


if __name__ == "__main__":
    sys.exit(main())
