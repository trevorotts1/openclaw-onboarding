#!/usr/bin/env python3
# =============================================================================
# 50-email-engine/index/gemini-indexer.py
# -----------------------------------------------------------------------------
# THIN wrapper / stub over shared-utils/embedding_engine.py for the SEPARATE
# email-superlibrary index (NOT the persona index). Embeds the email-library
# entry bodies ONCE on the operator box; client boxes NEVER call this — they
# download the sha256-verified vectors via provision-email-index.sh.
#
# It resolves shared-utils/embedding_engine.py from the usual candidate roots
# (mirrors 23-.../scripts/gemini-indexer.py) and hands off to its indexer main
# with the email corpus (email-library/**/*.md) as the source. Honors the
# client's own provider config (qc-static.yml / the client key chain) — this
# script pins NO Anthropic id and holds NO operator key.
#
# USAGE (operator box only, needs a client-supplied Gemini/Google key for the DELTA):
#   python3 gemini-indexer.py --reindex-all
#   python3 gemini-indexer.py --entry-id framework-pas
# =============================================================================
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_CANDIDATES = [os.path.join(_HERE, r) for r in (
    "../../shared-utils", "../shared-utils", "../../../shared-utils",
)] + [
    os.path.expanduser("~/.openclaw/skills/shared-utils"),
    "/data/.openclaw/skills/shared-utils",
    os.path.expanduser("~/.openclaw/onboarding/shared-utils"),
]
_ENGINE_ROOT = next(
    (os.path.realpath(p) for p in _CANDIDATES
     if os.path.isfile(os.path.join(p, "embedding_engine.py"))),
    None,
)

# The email corpus this index is built from (SEPARATE from the persona corpus).
EMAIL_CORPUS_GLOB = os.path.join(os.path.dirname(_HERE), "email-library", "**", "*.md")
EMAIL_INDEX_MANIFEST = os.path.join(_HERE, "EMAIL-INDEX-MANIFEST.json")


def main():
    if _ENGINE_ROOT is None:
        sys.stderr.write(
            "[email-gemini-indexer] FATAL: shared-utils/embedding_engine.py not found in %r\n"
            % _CANDIDATES)
        return 2
    sys.path.insert(0, _ENGINE_ROOT)
    os.environ.setdefault("OC_EMAIL_INDEX_CORPUS", EMAIL_CORPUS_GLOB)
    os.environ.setdefault("OC_EMAIL_INDEX_MANIFEST", EMAIL_INDEX_MANIFEST)
    # STUB HANDOFF: the shared embedding engine owns the actual embed + sqlite
    # write. When its email-corpus entrypoint lands it is invoked here; until
    # then this stub fails loud rather than silently re-embedding per box.
    try:
        import embedding_engine  # noqa: F401
    except Exception as exc:  # pragma: no cover - environment dependent
        sys.stderr.write("[email-gemini-indexer] FATAL: cannot import embedding_engine: %s\n" % exc)
        return 2
    entry = getattr(embedding_engine, "_email_indexer_main", None) \
        or getattr(embedding_engine, "_indexer_main", None)
    if entry is None:
        sys.stderr.write(
            "[email-gemini-indexer] embedding_engine has no email indexer entrypoint yet; "
            "the email index asset is built by index/build-and-publish.sh on the operator box.\n")
        return 2
    return entry() or 0


if __name__ == "__main__":
    sys.exit(main())
