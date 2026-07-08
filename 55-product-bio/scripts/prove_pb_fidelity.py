#!/usr/bin/env python3
# =============================================================================
# SKILL 55 — PRODUCT BIO :: PROMPT-FIDELITY GATE  (fail-closed, stdlib-only)
# -----------------------------------------------------------------------------
# The two baked prompt assets ARE the IP. This gate sha256-pins them so the IP
# can never silently drift: any byte change to assets/prompts/*.md flips the
# hash and the gate fails closed (PRD §4 AF-PB-PROMPT-DRIFT, G3). The expected
# hashes below were recorded from the byte-identical copies of the verified
# source prompts P1 / P2 at bake time; they equal the source-file sha256.
#
#   AF-PB-PROMPT-DRIFT — a prompt asset's sha256 != its recorded pin, an asset
#                        is missing, or an unexpected prompt file appeared.
#
# EXIT: 0 PASS · 2 AUTOFAIL · 3 USAGE/IO.
# USAGE: prove_pb_fidelity.py [--prompts-dir DIR] [--json]
#        prove_pb_fidelity.py --self-test
# =============================================================================
"""Fail-closed prompt-fidelity (sha256) gate for the Product Bio engine."""

import argparse
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _pb_common as c  # noqa: E402

AF_PROMPT_DRIFT = "AF-PB-PROMPT-DRIFT"

_SKILL_DIR = Path(__file__).resolve().parent.parent
_DEFAULT_PROMPTS = _SKILL_DIR / "assets" / "prompts"
_FIX = _SKILL_DIR / "test-fixtures"

# Recorded pins — the sha256 of the byte-identical baked copies of P1 / P2.
EXPECTED_HASHES = {
    "01-product-bio-writer.md":
        "67ead6929555dff09e1d2ed88d75b6a8325d31260eaa6caa9dd495cb2a245527",
    "02-google-doc-html-writer.md":
        "5cd1b2833c4da6bf2e2de153f359edecd1c34a5462cfa10a5a670103f6fa2d39",
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def evaluate(prompts_dir: Path) -> c.Result:
    r = c.Result("prove_pb_fidelity")
    if not prompts_dir.is_dir():
        r.fail(AF_PROMPT_DRIFT, "prompts dir not found: %s" % prompts_dir)
        return r
    present = {p.name for p in prompts_dir.glob("*.md")}
    for name, want in EXPECTED_HASHES.items():
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
    for extra in sorted(present - set(EXPECTED_HASHES)):
        r.fail(AF_PROMPT_DRIFT, "unexpected prompt file present (unpinned IP): %s" % extra)
    return r


def prove(prompts_dir, as_json=False) -> int:
    return evaluate(Path(prompts_dir)).emit(as_json)


def self_test() -> int:
    checks = []
    g = evaluate(_DEFAULT_PROMPTS)
    checks.append(("baked assets/prompts PASS the pin", g.passed))
    a = evaluate(_FIX / "attack" / "drifted-prompts")
    checks.append(("drifted prompt AUTOFAILs", not a.passed))
    checks.append(("...with AF-PB-PROMPT-DRIFT",
                   any(code == AF_PROMPT_DRIFT for code, _ in a.violations)))
    return c.selftest_report("prove_pb_fidelity", checks)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Product Bio prompt-fidelity gate (Skill 55).")
    ap.add_argument("--prompts-dir", default=str(_DEFAULT_PROMPTS),
                    help="directory of baked prompt assets (default: assets/prompts)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    return prove(args.prompts_dir, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
