#!/usr/bin/env bash
# 22-book-to-persona-coaching-leadership-system/pipeline/fleet-publish-status.sh
# ─────────────────────────────────────────────────────────────────────────────
# The pipeline's FLEET-PUBLISH STATUS MARKER.
#
# The Skill-22 book pipeline registers a new persona in the WORKSPACE only. Its
# terminal phase calls `mark-pending` here so a persona can NEVER be silently
# left un-published to the fleet: it writes a durable marker
#   <coaching-dir>/.fleet-publish-pending.json  { "pending": [<slug>...], ... }
# and prints a LOUD banner telling the operator to run publish-personas-to-fleet.sh.
#
# publish-personas-to-fleet.sh calls `clear` on success. The divergence guard
# (assert-personas-published.sh) treats a present marker as a hard failure, so a
# forgotten publish blocks a commit / a roll.
#
# USAGE
#   fleet-publish-status.sh mark-pending <coaching-dir> <slug> [<slug>...]
#   fleet-publish-status.sh check        <coaching-dir>     # exit 3 if pending
#   fleet-publish-status.sh clear        <coaching-dir>
#   fleet-publish-status.sh path         <coaching-dir>     # print marker path
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

cmd="${1:-}"; shift || true
DIR="${1:-}"; shift || true
[ -n "$cmd" ] && [ -n "$DIR" ] || { sed -n '2,26p' "${BASH_SOURCE[0]}"; exit 2; }
MARKER="$DIR/.fleet-publish-pending.json"

case "$cmd" in
    path)
        echo "$MARKER" ;;
    mark-pending)
        [ -d "$DIR" ] || { echo "coaching dir not found: $DIR" >&2; exit 2; }
        MARKER="$MARKER" python3 - "$@" <<'PY'
import json, os, sys, datetime
marker = os.environ["MARKER"]
new = [s for s in sys.argv[1:] if s]
pending = set(new)
try:
    with open(marker) as f:
        pending |= set(json.load(f).get("pending", []))
except Exception:
    pass
data = {
    "pending": sorted(pending),
    "note": ("Personas were added to the WORKSPACE but NOT yet published to the "
             "fleet. Run 22-book-to-persona-coaching-leadership-system/pipeline/"
             "publish-personas-to-fleet.sh to bring the repo library + index "
             "manifest + release asset into lockstep, then commit."),
    "updatedAt": datetime.datetime.now(datetime.timezone.utc)
        .strftime("%Y-%m-%dT%H:%M:%SZ"),
}
with open(marker, "w") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
print(",".join(data["pending"]))
PY
        n_pending="$(python3 -c 'import json,sys;print(len(json.load(open(sys.argv[1]))["pending"]))' "$MARKER" 2>/dev/null || echo '?')"
        echo "" >&2
        echo "  ╔══════════════════════════════════════════════════════════════════╗" >&2
        echo "  ║  PERSONA(S) ADDED TO WORKSPACE — NOT YET PUBLISHED TO THE FLEET     ║" >&2
        echo "  ║  $n_pending persona(s) pending. The repo library + index manifest +      " >&2
        echo "  ║  release asset are NOT caught up. Run the ONE command:              ║" >&2
        echo "  ║    pipeline/publish-personas-to-fleet.sh                            ║" >&2
        echo "  ╚══════════════════════════════════════════════════════════════════╝" >&2
        echo "" >&2
        ;;
    check)
        [ -f "$MARKER" ] || { echo "no pending fleet publish"; exit 0; }
        pend="$(python3 -c 'import json,sys;print(",".join(json.load(open(sys.argv[1])).get("pending",[])))' "$MARKER" 2>/dev/null || echo '')"
        if [ -n "$pend" ]; then
            echo "PENDING fleet publish: $pend" >&2
            echo "  run pipeline/publish-personas-to-fleet.sh, then commit + roll." >&2
            exit 3
        fi
        echo "no pending fleet publish"; exit 0 ;;
    clear)
        rm -f "$MARKER"; echo "cleared: $MARKER" ;;
    *)
        echo "unknown command: $cmd" >&2; exit 2 ;;
esac
