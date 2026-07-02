#!/usr/bin/env python3
# PRD 1.8 wrapper (impl in shared-utils/embedding_engine.py); a71f6bbd: multi-candidate sys.path resolve + fail-loud
#
# P12-1 (FINAL-REVIEW-2026-07-01 Point 12 fix 1): refuse a FULL rebuild
# (--rebuild, which DROPS every existing embedding — see embedding_engine.
# cmd_index()) when the prebuilt-index sentinel (.prebuilt-index-version,
# written by shared-utils/provision-persona-index.sh on a canonical install)
# is present. A full rebuild on a box that already carries the sha256-verified,
# ship-don't-re-embed prebuilt index would discard those canonical vectors and
# pay the full per-box re-embed cost this pipeline exists to avoid. Incremental
# indexing (no flag — embedding_engine's own default skip-unchanged-by-hash
# behavior) is ALWAYS allowed; this guard ONLY blocks --rebuild. An OPERATOR
# can still force a genuine full rebuild (e.g. after a real embedding-model
# migration) by passing --force-full-rebuild alongside --rebuild; that flag is
# OPERATOR-ONLY — never surface it in any client-facing doc/reflex — and is
# stripped from argv before delegating to embedding_engine's own argparse,
# which does not know about it.
import sys, os; _h=os.path.dirname(os.path.abspath(__file__)); _c=[os.path.join(_h,r) for r in ("shared-utils","../skills/shared-utils","../../shared-utils","../../../shared-utils","../shared-utils")]+[os.path.expanduser("~/.openclaw/skills/shared-utils"),"/data/.openclaw/skills/shared-utils",os.path.expanduser("~/.openclaw/onboarding/shared-utils")]
_r=next((os.path.realpath(p) for p in _c if os.path.isfile(os.path.join(p,"embedding_engine.py"))),None)
sys.exit(sys.stderr.write("[gemini-indexer] FATAL: embedding_engine.py not found in %r\n" % _c) or 2) if _r is None else sys.path.insert(0,_r)

_FORCE_FULL_REBUILD = "--force-full-rebuild" in sys.argv
if _FORCE_FULL_REBUILD:
    sys.argv = [a for a in sys.argv if a != "--force-full-rebuild"]

# Only --rebuild (a FULL rebuild) is gated. --status short-circuits before
# cmd_index() in embedding_engine._indexer_main() regardless of --rebuild, so
# skip the guard when --status is also present (mirrors that precedence
# exactly -- no false-positive refusal on a --status call).
if "--rebuild" in sys.argv and "--status" not in sys.argv and not _FORCE_FULL_REBUILD:
    _sentinel = None
    try:
        from detect_platform import get_openclaw_paths  # type: ignore
        _sentinel = get_openclaw_paths()["coaching_personas"] / ".prebuilt-index-version"
    except Exception:
        _sentinel = None
    if _sentinel is not None and _sentinel.exists():
        sys.stderr.write(
            "[gemini-indexer] REFUSED: --rebuild (FULL rebuild) requested but "
            "the prebuilt-index sentinel is present (%s) -- this box carries "
            "the canonical, sha256-verified ship-don't-re-embed index. A full "
            "rebuild would discard it and pay the full re-embed cost. "
            "Incremental indexing (no flag) runs normally. If you are an "
            "OPERATOR performing a genuine embedding-model migration, pass "
            "--force-full-rebuild alongside --rebuild to override "
            "(operator-only -- never surface this to a client box).\n"
            % _sentinel
        )
        sys.exit(3)

from embedding_engine import _indexer_main as main; main()
