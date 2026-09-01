#!/usr/bin/env python3
# =============================================================================
# SKILL 53 — BOOK WRITER :: AVATAR DOSSIER GATE (fail-closed)
# -----------------------------------------------------------------------------
# P1-AVATAR (stages 01-avatar-questions-1-30 / 02-avatar-questions-31-32 /
# 03-rewrite-avatar) produces run/artifacts/01-avatar.md — the reader dossier the
# whole book is written against. It must EXIST and be a substantial document:
# >= 500 STRIPPED words (consistent with the other provers' stripped-word
# approach — whitespace padding cannot fake it, and the model's self-reported
# count is never trusted).
#
#   AF-BK-AVATAR-MISSING — the avatar dossier is missing, empty, or below the
#   500 stripped-word floor.
#
# EXIT: 0 PASS · 2 AUTOFAIL · 3 USAGE/IO.
# USAGE: prove_bw_avatar.py --run-dir DIR [--json]
#        prove_bw_avatar.py <path-to-01-avatar.md> [--json] | --self-test
# =============================================================================
"""Fail-closed avatar-dossier gate (Skill 53)."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bw_common as c  # noqa: E402

AF_AVATAR_MISSING = "AF-BK-AVATAR-MISSING"

# P1-AVATAR's produced artifact (manifest produces_artifact). The golden run's
# avatar dossier lives at this path — NOT 03-rewrite-avatar.md (a stage id, not
# an artifact; that path does not exist).
ARTIFACT_REL = "artifacts/01-avatar.md"

# the minimum stripped-word floor for the avatar dossier (stated constant)
AVATAR_WORD_FLOOR = 500


def evaluate(text: str) -> c.Result:
    r = c.Result("prove_bw_avatar")
    words = c.word_count(text)
    if words < AVATAR_WORD_FLOOR:
        r.fail(AF_AVATAR_MISSING, "avatar dossier measured %d stripped words, below the %d floor "
               "(self-reported counts ignored)" % (words, AVATAR_WORD_FLOOR))
    else:
        r.note("avatar dossier measured %d stripped words (>= %d)" % (words, AVATAR_WORD_FLOOR))
    return r


def prove_path(path, as_json=False) -> int:
    p = Path(path)
    if not p.is_file():
        r = c.Result("prove_bw_avatar")
        r.fail(AF_AVATAR_MISSING, "avatar dossier missing: %s" % p)
        return r.emit(as_json)
    return evaluate(c.read_text(path)).emit(as_json)


def prove_run_dir(run_dir, as_json=False) -> int:
    """Resolve the avatar artifact under a run dir: DIR/<ARTIFACT_REL>."""
    return prove_path(Path(run_dir) / ARTIFACT_REL, as_json=as_json)


def self_test() -> int:
    checks = []
    long_avatar = "# Avatar Dossier\n" + ("reader " * 600)
    checks.append(("600-word avatar PASSES", evaluate(long_avatar).passed))
    checks.append(("empty avatar AUTOFAILs AF-BK-AVATAR-MISSING",
                   any(cd == AF_AVATAR_MISSING for cd, _ in evaluate("").violations)))
    under = "# Avatar Dossier\n" + ("reader " * 400)
    checks.append(("under-floor avatar AUTOFAILs AF-BK-AVATAR-MISSING",
                   any(cd == AF_AVATAR_MISSING for cd, _ in evaluate(under).violations)))
    padded = "# Avatar Dossier\n" + ("reader " * 400) + ("\n" * 40000)
    checks.append(("whitespace-padded short avatar STILL AUTOFAILs AF-BK-AVATAR-MISSING",
                   any(cd == AF_AVATAR_MISSING for cd, _ in evaluate(padded).violations)))
    return c.selftest_report("prove_bw_avatar", checks)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Book Writer avatar-dossier gate (Skill 53).")
    ap.add_argument("path", nargs="?", help="01-avatar.md path (run/artifacts/01-avatar.md)")
    ap.add_argument("--run-dir", help="run dir to resolve %s under" % ARTIFACT_REL)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if args.run_dir:
        return prove_run_dir(args.run_dir, as_json=args.json)
    if args.path:
        return prove_path(args.path, as_json=args.json)
    ap.error("a path or --run-dir is required (or use --self-test)")


if __name__ == "__main__":
    sys.exit(main())
