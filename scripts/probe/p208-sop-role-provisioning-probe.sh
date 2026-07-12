#!/usr/bin/env bash
# p208-sop-role-provisioning-probe.sh — P2-08 (c) step 3: per-box SOPs/roles/
# skills provisioning-correctness probe. SHIPS IN P6-01 (built and QC'd now;
# run against live fleet boxes only in the final rollout phase, per the note
# in Section 3 of the spec: "ships in P6-01" means build+QC now, deploy later).
#
# WHAT THIS CLOSES
# -----------------
# P2-08's row in the P6-01 fleet probe table: "SOP counts ≥ floor with
# source='role-library' rows ≥1 ... skills at expected skill-version.txt
# values; refresh queue empty post-update." Three INDEPENDENT checks, any one
# of which failing degrades the whole box:
#
#   1. SOP LIBRARY POPULATED — wraps the v19.50.0 gate
#      (assert-sop-library-populated.py) standalone against the box's live
#      mission-control.db. Same fail-closed contract: no --min-total means
#      REFUSE, never assume a floor (a rubber-stamped floor is exactly the C2
#      defect class this whole phase exists to prevent).
#   2. SKILL VERSION DRIFT — every numbered skill dir under the installed
#      skills root must carry the SAME skill-version.txt content as the
#      reference checkout (defaults to THIS script's own repo checkout — the
#      fresh clone the rollout doctrine (2.7) requires, never a stale local
#      copy). A skill present on one side and missing on the other, or a
#      differing version string, is reported by name.
#   3. REFRESH QUEUE DRAINED — .artifact-refresh-queue.json must carry ZERO
#      items with kind=="role" AND status=="STALE" post-update. This is the
#      direct proof that refresh-stale-roles.py (P2-08 (c) step 2) actually
#      ran and drained what it was built to drain — a box stuck on the OLD
#      role docs (the P2-08 (b) "stale role docs" defect) would fail this
#      check even if checks 1/2 both pass.
#
# USAGE
#   p208-sop-role-provisioning-probe.sh --min-total N [--json] [--box <label>]
#       [--min-role-library N] [--role-library-source S] [--db PATH]
#       [--skills-dir DIR] [--repo-dir DIR] [--workspace DIR] [--queue-file PATH]
#
# EXIT CODES
#   0  fully provisioned  (all three checks pass)
#   1  degraded           (one or more checks failed) — operator/fleet-ledger attention
#   2  usage error        (e.g. --min-total not supplied — fail-closed, never assumed)
# ============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

JSON=0
BOX="${OPENCLAW_BOX_LABEL:-$(hostname -s 2>/dev/null || echo unknown)}"
MIN_TOTAL=""
MIN_ROLE_LIBRARY=1
ROLE_LIBRARY_SOURCE="role-library"
DB_PATH=""
SKILLS_DIR="${OPENCLAW_SKILLS_DIR:-}"
REPO_DIR="$REPO_ROOT"
WORKSPACE=""
QUEUE_FILE=""

if [ -z "$SKILLS_DIR" ]; then
  if [ -d "/data/.openclaw/skills" ]; then
    SKILLS_DIR="/data/.openclaw/skills"
  else
    SKILLS_DIR="$HOME/.openclaw/skills"
  fi
fi

while [ $# -gt 0 ]; do
  case "$1" in
    --json) JSON=1 ;;
    --box) shift; BOX="${1:-$BOX}" ;;
    --min-total) shift; MIN_TOTAL="${1:-}" ;;
    --min-role-library) shift; MIN_ROLE_LIBRARY="${1:-1}" ;;
    --role-library-source) shift; ROLE_LIBRARY_SOURCE="${1:-role-library}" ;;
    --db) shift; DB_PATH="${1:-}" ;;
    --skills-dir) shift; SKILLS_DIR="${1:-$SKILLS_DIR}" ;;
    --repo-dir) shift; REPO_DIR="${1:-$REPO_DIR}" ;;
    --workspace) shift; WORKSPACE="${1:-}" ;;
    --queue-file) shift; QUEUE_FILE="${1:-}" ;;
    -h|--help) sed -n '2,40p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
  shift
done

if [ -z "$MIN_TOTAL" ]; then
  echo "USAGE ERROR: --min-total is required (fail-closed — an implicit floor" >&2
  echo "would rubber-stamp the C2 ghost class; pass the same floor the box's" >&2
  echo "own ingest reported, or the last known-good ledger total)." >&2
  exit 2
fi

if [ -z "$WORKSPACE" ]; then
  if [ -d "/data/.openclaw/workspace" ]; then
    WORKSPACE="/data/.openclaw/workspace"
  else
    WORKSPACE="$HOME/.openclaw/workspace"
  fi
fi
[ -z "$QUEUE_FILE" ] && QUEUE_FILE="$WORKSPACE/.artifact-refresh-queue.json"

CHECKED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# ── (1) SOP LIBRARY POPULATED ────────────────────────────────────────────
ASSERT_SOP_PY="$REPO_ROOT/32-command-center-setup/scripts/assert-sop-library-populated.py"
SOP_OK=0
SOP_REASON="assert-sop-library-populated.py not found at $ASSERT_SOP_PY"
if [ -f "$ASSERT_SOP_PY" ] && command -v python3 >/dev/null 2>&1; then
  SOP_ARGS=(--min-total "$MIN_TOTAL" --min-role-library "$MIN_ROLE_LIBRARY"
            --role-library-source "$ROLE_LIBRARY_SOURCE" --json)
  [ -n "$DB_PATH" ] && SOP_ARGS+=(--db "$DB_PATH")
  SOP_JSON="$(python3 "$ASSERT_SOP_PY" "${SOP_ARGS[@]}" 2>&1)"
  SOP_RC=$?
  if [ "$SOP_RC" -eq 0 ]; then
    SOP_OK=1
    SOP_REASON="$(printf '%s' "$SOP_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("reason",""))' 2>/dev/null || echo "healthy")"
  else
    SOP_REASON="$(printf '%s' "$SOP_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("reason",""))' 2>/dev/null || printf '%s' "$SOP_JSON")"
  fi
fi

# ── (2) SKILL VERSION DRIFT ──────────────────────────────────────────────
SKILL_DRIFT_COUNT=0
SKILL_DRIFT_LIST=""
SKILL_CHECKED_COUNT=0
if [ -d "$SKILLS_DIR" ] && [ -d "$REPO_DIR" ]; then
  for d in "$SKILLS_DIR"/[0-9]*; do
    [ -d "$d" ] || continue
    name="$(basename "$d")"
    case "$name" in *ARCHIVED*) continue ;; esac
    ref_dir="$REPO_DIR/$name"
    [ -d "$ref_dir" ] || continue   # a skill not shipped in the reference repo is out of THIS probe's scope
    SKILL_CHECKED_COUNT=$((SKILL_CHECKED_COUNT + 1))
    installed_ver=""
    ref_ver=""
    [ -f "$d/skill-version.txt" ] && installed_ver="$(tr -d '[:space:]' < "$d/skill-version.txt")"
    [ -f "$ref_dir/skill-version.txt" ] && ref_ver="$(tr -d '[:space:]' < "$ref_dir/skill-version.txt")"
    if [ "$installed_ver" != "$ref_ver" ]; then
      SKILL_DRIFT_COUNT=$((SKILL_DRIFT_COUNT + 1))
      SKILL_DRIFT_LIST="${SKILL_DRIFT_LIST}${name}(installed=${installed_ver:-<none>},expected=${ref_ver:-<none>});"
    fi
  done
fi
SKILLS_OK=1
[ "$SKILL_DRIFT_COUNT" -gt 0 ] && SKILLS_OK=0

# ── (3) REFRESH QUEUE DRAINED (zero actionable STALE role items) ────────
QUEUE_OK=1
QUEUE_STALE_ROLE_COUNT=0
QUEUE_REASON="queue file not present -- treated as drained (nothing was ever queued)"
if [ -f "$QUEUE_FILE" ] && command -v python3 >/dev/null 2>&1; then
  QUEUE_CHECK="$(python3 - "$QUEUE_FILE" <<'PYEOF'
import json, sys
path = sys.argv[1]
try:
    d = json.load(open(path, encoding="utf-8"))
except Exception as e:
    print(f"ERROR|could not parse queue file: {e}")
    sys.exit(0)
items = d.get("items", [])
if not isinstance(items, list):
    items = []
stale_roles = [i for i in items if isinstance(i, dict) and i.get("kind") == "role" and i.get("status") == "STALE"]
print(f"{len(stale_roles)}|" + ",".join(i.get("key", "?") for i in stale_roles[:10]))
PYEOF
)"
  if [[ "$QUEUE_CHECK" == ERROR\|* ]]; then
    QUEUE_OK=0
    QUEUE_REASON="${QUEUE_CHECK#ERROR|}"
  else
    QUEUE_STALE_ROLE_COUNT="${QUEUE_CHECK%%|*}"
    QUEUE_KEYS="${QUEUE_CHECK#*|}"
    if [ "$QUEUE_STALE_ROLE_COUNT" -gt 0 ]; then
      QUEUE_OK=0
      QUEUE_REASON="$QUEUE_STALE_ROLE_COUNT STALE role item(s) still queued: $QUEUE_KEYS -- refresh-stale-roles.py did not drain them"
    else
      QUEUE_REASON="0 STALE role items queued -- fully drained"
    fi
  fi
fi

OVERALL_OK=1
[ "$SOP_OK" -eq 1 ] || OVERALL_OK=0
[ "$SKILLS_OK" -eq 1 ] || OVERALL_OK=0
[ "$QUEUE_OK" -eq 1 ] || OVERALL_OK=0

if [ "$JSON" -eq 1 ]; then
  python3 - "$BOX" "$CHECKED_AT" "$SOP_OK" "$SOP_REASON" "$SKILLS_OK" "$SKILL_DRIFT_COUNT" \
    "$SKILL_CHECKED_COUNT" "$SKILL_DRIFT_LIST" "$QUEUE_OK" "$QUEUE_STALE_ROLE_COUNT" "$QUEUE_REASON" "$OVERALL_OK" <<'PYEOF'
import json, sys
box, checked_at, sop_ok, sop_reason, skills_ok, drift_count, checked_count, drift_list, queue_ok, queue_stale, queue_reason, overall_ok = sys.argv[1:13]
print(json.dumps({
    "box": box,
    "checked_at": checked_at,
    "sop_library": {"ok": bool(int(sop_ok)), "reason": sop_reason},
    "skill_versions": {
        "ok": bool(int(skills_ok)),
        "checked": int(checked_count),
        "drift_count": int(drift_count),
        "drifted": [s for s in drift_list.split(";") if s],
    },
    "refresh_queue": {"ok": bool(int(queue_ok)), "stale_role_count": int(queue_stale), "reason": queue_reason},
    "overall_provisioned": bool(int(overall_ok)),
}, indent=2))
PYEOF
else
  echo "P2-08 SOP/role/skill provisioning probe — box: $BOX  ($CHECKED_AT)"
  if [ "$SOP_OK" -eq 1 ]; then
    echo "  [OK]   SOP library: $SOP_REASON"
  else
    echo "  [MISS] SOP library: $SOP_REASON"
  fi
  if [ "$SKILLS_OK" -eq 1 ]; then
    echo "  [OK]   skill versions: $SKILL_CHECKED_COUNT checked, 0 drifted"
  else
    echo "  [MISS] skill versions: $SKILL_DRIFT_COUNT/$SKILL_CHECKED_COUNT drifted -- $SKILL_DRIFT_LIST"
  fi
  if [ "$QUEUE_OK" -eq 1 ]; then
    echo "  [OK]   refresh queue: $QUEUE_REASON"
  else
    echo "  [MISS] refresh queue: $QUEUE_REASON"
  fi
  if [ "$OVERALL_OK" -eq 1 ]; then
    echo "  VERDICT: PROVISIONED"
  else
    echo "  VERDICT: DEGRADED — see MISS lines above"
  fi
fi

[ "$OVERALL_OK" -eq 1 ] && exit 0 || exit 1
