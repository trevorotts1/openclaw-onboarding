#!/usr/bin/env python3
# =============================================================================
# SKILL 54 — ANTHOLOGY WRITER :: PROMPT-FIDELITY GATE  (fail-closed, stdlib-only)
# -----------------------------------------------------------------------------
# The baked authoring prompt assets ARE the IP. This gate sha256-pins them so the
# IP can never silently drift: any byte change to assets/prompts/*.md flips the
# hash and the gate fails closed (PRD §4 — AF-AW-PROMPT-DRIFT). The pins live in
# ONE place: ANTHOLOGY-MANIFEST.json -> source_prompt_pins (relpath -> sha256).
#
#   AF-AW-PROMPT-DRIFT — a prompt asset's sha256 != its recorded manifest pin, an
#                        asset is missing, or an unpinned prompt file appeared.
#
# EXIT: 0 PASS · 2 AUTOFAIL · 3 USAGE/IO.
# USAGE: prove_aw_fidelity.py [--prompts-dir DIR] [--manifest FILE] [--json]
#        prove_aw_fidelity.py --self-test
# =============================================================================
"""Fail-closed prompt-fidelity (sha256) gate for the Anthology Writer."""

import argparse
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _aw_common as c  # noqa: E402

AF_PROMPT_DRIFT = "AF-AW-PROMPT-DRIFT"

_SKILL_DIR = Path(__file__).resolve().parent.parent
_DEFAULT_PROMPTS = _SKILL_DIR / "assets" / "prompts"
_DEFAULT_MANIFEST = _SKILL_DIR / "ANTHOLOGY-MANIFEST.json"
_FIX = _SKILL_DIR / "test-fixtures"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _load_pins(manifest_path: Path) -> dict:
    """Return {basename: sha256} from ANTHOLOGY-MANIFEST.json.source_prompt_pins.
    Keys in the manifest are repo-relative ('assets/prompts/09-write-chapter.md');
    we key on the basename so a --prompts-dir override works for the drift test."""
    obj = c.read_json(manifest_path)
    pins = obj.get("source_prompt_pins", {}) if isinstance(obj, dict) else {}
    return {Path(k).name: v for k, v in pins.items()}


def evaluate(prompts_dir: Path, manifest_path: Path) -> c.Result:
    r = c.Result("prove_aw_fidelity")
    if not manifest_path.is_file():
        r.fail(AF_PROMPT_DRIFT, "manifest not found: %s" % manifest_path)
        return r
    expected = _load_pins(manifest_path)
    if not expected:
        r.fail(AF_PROMPT_DRIFT, "no source_prompt_pins recorded in the manifest")
        return r
    if not prompts_dir.is_dir():
        r.fail(AF_PROMPT_DRIFT, "prompts dir not found: %s" % prompts_dir)
        return r
    present = {p.name for p in prompts_dir.glob("*.md")}
    for name, want in expected.items():
        p = prompts_dir / name
        if not p.is_file():
            r.fail(AF_PROMPT_DRIFT, "prompt asset missing: %s" % name)
            continue
        got = _sha256(p)
        if got != want:
            r.fail(AF_PROMPT_DRIFT, "%s sha256 drift: got %s… expected %s…"
                   % (name, got[:12], want[:12]))
        else:
            r.note("%s pinned OK (%s…)" % (name, want[:12]))
    for extra in sorted(present - set(expected)):
        r.fail(AF_PROMPT_DRIFT, "unexpected prompt file present (unpinned IP): %s" % extra)
    return r


def prove(prompts_dir, manifest_path, as_json=False) -> int:
    return evaluate(Path(prompts_dir), Path(manifest_path)).emit(as_json)


def self_test() -> int:
    checks = []
    g = evaluate(_DEFAULT_PROMPTS, _DEFAULT_MANIFEST)
    checks.append(("baked assets/prompts PASS the manifest pins", g.passed))
    a = evaluate(_FIX / "attack" / "drifted-prompts", _DEFAULT_MANIFEST)
    checks.append(("drifted prompt AUTOFAILs", not a.passed))
    checks.append(("...with AF-AW-PROMPT-DRIFT",
                   any(code == AF_PROMPT_DRIFT for code, _ in a.violations)))
    return c.selftest_report("prove_aw_fidelity", checks)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Anthology Writer prompt-fidelity gate (Skill 54).")
    ap.add_argument("--prompts-dir", default=str(_DEFAULT_PROMPTS),
                    help="directory of baked prompt assets (default: assets/prompts)")
    ap.add_argument("--manifest", default=str(_DEFAULT_MANIFEST),
                    help="manifest carrying source_prompt_pins")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    return prove(args.prompts_dir, args.manifest, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
