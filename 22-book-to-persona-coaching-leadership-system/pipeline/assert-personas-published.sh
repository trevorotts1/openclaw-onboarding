#!/usr/bin/env bash
# 22-book-to-persona-coaching-leadership-system/pipeline/assert-personas-published.sh
# ─────────────────────────────────────────────────────────────────────────────
# THE DIVERGENCE GUARD — fails LOUD and EARLY (not just at CI / roll time) when
# the persona subsystem is out of lockstep. It is the standalone + pre-commit +
# pre-roll enforcement of the same N38 invariant CI enforces at the PR boundary.
#
# Two layers:
#   1. REPO TRIAD (always, hermetic — no workspace needed):
#        blueprint dirs == categories keys == manifest.persona_count == canonical
#      This is what pre-commit and the pre-roll verifier run: a repo/manifest
#      that disagrees is refused before it can ship.
#   2. WORKSPACE vs REPO (when a workspace is resolvable / --workspace given):
#        every publishable workspace persona is present in the repo library, and
#        no pending-publish marker (.fleet-publish-pending.json) is set.
#      This catches "added to the workspace but the repo was never caught up"
#      the moment it happens, with the exact remediation command.
#
# USAGE
#   assert-personas-published.sh [--repo ROOT] [--workspace DIR] [--repo-only]
#
#   --repo ROOT     repo root to check (default: this checkout)
#   --workspace DIR workspace coaching-personas dir (default: live-resolve, if any)
#   --repo-only     ONLY the repo triad (skip the workspace comparison). Used by
#                   the pre-commit hook, the update-skills pre-roll verifier, and
#                   CI, where no live workspace exists.
#
# EXIT CODES
#   0  in lockstep
#   3  workspace persona(s) not in the repo library, OR a pending marker is set
#   5  repo triad disagrees (blueprint dirs / categories / manifest counts)
#   2  environment error
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PF="$SELF_DIR/persona_fleet.py"
STATUS_HELPER="$SELF_DIR/fleet-publish-status.sh"
REPO_ROOT="$(cd "$SELF_DIR/../.." && pwd)"
WORKSPACE="${PUBLISH_PERSONAS_WORKSPACE:-}"
REPO_ONLY=0

while [ $# -gt 0 ]; do
    case "$1" in
        --repo)      REPO_ROOT="$2"; shift 2 ;;
        --workspace) WORKSPACE="$2"; shift 2 ;;
        --repo-only) REPO_ONLY=1; shift ;;
        -h|--help)   sed -n '2,34p' "${BASH_SOURCE[0]}"; exit 0 ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

command -v python3 >/dev/null 2>&1 || { echo "python3 required" >&2; exit 2; }
[ -f "$PF" ] || { echo "core helper not found: $PF" >&2; exit 2; }
REPO_ROOT="$(cd "$REPO_ROOT" 2>/dev/null && pwd)" || { echo "bad --repo" >&2; exit 2; }
PUBLISH_CMD="22-book-to-persona-coaching-leadership-system/pipeline/publish-personas-to-fleet.sh"

# ── Layer 1: repo triad (hermetic) ───────────────────────────────────────────
if ! python3 "$PF" triad --repo-root "$REPO_ROOT" >/dev/null 2>&1; then
    echo "✗ PERSONA REPO TRIAD DISAGREES:" >&2
    python3 "$PF" triad --repo-root "$REPO_ROOT" >&2 || true
    echo "" >&2
    echo "  The repo blueprint dirs, persona-categories.json keys, and the" >&2
    echo "  INDEX-MANIFEST.json persona_count/canonical_persona_count are NOT all" >&2
    echo "  equal. A persona shipped to one half without the others. Fix with the" >&2
    echo "  ONE command (brings all four into lockstep atomically):" >&2
    echo "    $PUBLISH_CMD" >&2
    exit 5
fi

if [ "$REPO_ONLY" = "1" ]; then
    echo "✓ persona repo triad agrees (blueprint dirs == categories keys == manifest counts)"
    exit 0
fi

# ── Resolve workspace (live) if not given ────────────────────────────────────
if [ -z "$WORKSPACE" ]; then
    for c in "/data/.openclaw/workspace/data/coaching-personas" \
             "/data/.openclaw/master-files/coaching-personas" \
             "$HOME/.openclaw/workspace/data/coaching-personas"; do
        if [ -d "$c" ]; then WORKSPACE="$c"; break; fi
    done
fi

if [ -z "$WORKSPACE" ] || [ ! -d "$WORKSPACE" ]; then
    echo "✓ persona repo triad agrees; no live workspace to compare (repo-only check)"
    exit 0
fi

# ── Layer 2: workspace vs repo ───────────────────────────────────────────────
rc=0
MISSING=(); while IFS= read -r _l; do [ -n "$_l" ] && MISSING+=("$_l"); done \
    < <(python3 "$PF" diff-slugs --workspace "$WORKSPACE" --repo-root "$REPO_ROOT")
if [ "${#MISSING[@]}" -gt 0 ]; then
    echo "✗ WORKSPACE ↔ REPO DIVERGENCE: ${#MISSING[@]} workspace persona(s) are NOT in the repo library:" >&2
    printf '    - %s\n' "${MISSING[@]}" >&2
    echo "  The workspace/index advanced but the repo library lagged. Catch up with:" >&2
    echo "    $PUBLISH_CMD" >&2
    rc=3
fi

# Pending-publish marker set by the pipeline's terminal phase?
if [ -f "$STATUS_HELPER" ]; then
    if ! bash "$STATUS_HELPER" check "$WORKSPACE" >/dev/null 2>&1; then
        echo "✗ a fleet-publish PENDING marker is set (.fleet-publish-pending.json):" >&2
        bash "$STATUS_HELPER" check "$WORKSPACE" >&2 || true
        rc=3
    fi
fi

if [ "$rc" = "0" ]; then
    echo "✓ persona subsystem in lockstep: repo triad agrees AND every workspace persona is published"
fi
exit "$rc"
