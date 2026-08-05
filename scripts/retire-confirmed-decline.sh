#!/usr/bin/env bash
# retire-confirmed-decline.sh — the CONFIRMED-DECLINE UN-BUILD path of the AI
# Workforce standard-first redesign (master plan 2026-08-04, PHASE 3 item 4 +
# section 2.3).
#
# Under standard-first the interview EDITS an already-prebuilt company, so a
# confirmed decline must UN-BUILD, not just skip-at-creation. For each
# PROVENANCED decline this script performs the four steps of the master plan:
#
#   1. Deregister the agents.list row (dept-<slug>) from openclaw.json — only
#      when one was lazily registered (backup first; config safety protocol).
#   2. ARCHIVE the department tree: departments/<slug> ->
#      company_dir/.retired/<slug>-<ts>/  (the master plan's rename-to-archive
#      step; NEVER delete — APFS snapshot doctrine; `mv` keeps the APFS
#      snapshots pinning the history).
#   3. Remove the board lane + Command Center workspaces row via the Command
#      Center's EXISTING DELETE surface — src/lib/workspaces/department-optout.ts
#      archiveDepartment() (PHASE 6): a SOFT archive (workspaces.archived_at +
#      archived_reason='retired'; the row is PRESERVED, never deleted). This
#      step mirrors that function's exact SQL in sqlite3 against the EXPLICIT
#      database only (--db / $DASHBOARD_DB_PATH / $DATABASE_PATH — the same
#      explicit-signal-only discipline seed-workspaces.py + the prebuild driver
#      use; never ambient discovery). Absent db or absent archived_at column
#      (migration 095 not applied) -> step SKIPPED + recorded, never faked.
#   4. Append the removed-with-provenance record to the chosen artifact
#      (company_dir/departments.json): the entry is dropped from the chosen
#      list and the full provenanced decline is appended to a
#      `retiredDepartments` audit array.
#
# GATE (binding): this script must NEVER run without a provenanced decline
# object. The provenance reader is the SAME shared module every other decline
# consumer uses — 23-ai-workforce-blueprint/scripts/canonical_decline.py
# (build-workforce.py's _shared_canonical_decline_set, master plan PHASE 3
# item 4) — so a bare decline (no decision/source/decidedAt/decidedBy, no
# ownerDeclineConfirmed, incomplete dict triple) is REJECTED here exactly as
# it is rejected at build time (fail-safe to the LARGER floor: nothing is
# retired and the script exits 2 without ANY mutation).
#
# ARCHIVE ONLY — this script NEVER deletes anything. Trees are moved into
# .retired/, CC rows are soft-stamped, the chosen artifact is rewritten
# atomically (tmp + rename) with a .bak copy first. A wrong decline is always
# recoverable from the archive + the provenance record.
#
# EXEMPT (never retired): the orchestrator column ceo / dept-ceo /
# master-orchestrator — mirrored from the Command Center retire path's own
# orchestrator exemption.
#
# USAGE
#   bash retire-confirmed-decline.sh --dept <slug> [...] [options]
#
#   --dept <slug>            department to retire; may repeat. The sentinel
#                            __declined__ retires EVERY provenanced decline in
#                            the shared build-state (the apply-diff build's
#                            invocation form). REQUIRED.
#   --build-state-file <f>   explicit build-state JSON (scratch isolation;
#                            default: ~/.openclaw/workspace/ or
#                            /data/.openclaw/workspace/ live state)
#   --company-dir <dir>      ZHC company dir holding departments/ (default:
#                            resolved from the live companySlug / clientSlug)
#   --oc-config <path>       explicit openclaw.json for the agents.list
#                            deregistration (default: the box's own live
#                            config — but with a SCRATCH --build-state-file the
#                            step is SKIPPED unless this is passed explicitly;
#                            scratch runs must never touch a live config)
#   --db <mission-control.db>  explicit Command Center database for the lane
#                            archive (or $DASHBOARD_DB_PATH / $DATABASE_PATH)
#   --skip-cc                skip the Command Center lane archive entirely
#   --dry-run                report only; mutate nothing
#
# EXIT CODES
#   0  all requested retirements complete (or nothing to retire)
#   1  a retirement step failed (archive failed / chosen-artifact write failed)
#   2  gate refusal: no provenanced decline for the requested dept(s)
#   3  usage error
#
# NO-CO-MINGLING (binding — SKILL.md:41-43, NO-COMINGLING-RULE.md): this
# script operates ONLY on the target box's own tree + state; it never reads
# or writes another client's tree and never sources content from anywhere but
# what is already on this box.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# The retire script lives at the REPO ROOT's scripts/ dir; Skill 23 is one
# level up (23-ai-workforce-blueprint/scripts/).
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SKILL23_CANDIDATES=(
  "$REPO_ROOT/23-ai-workforce-blueprint/scripts"
  "$HOME/.openclaw/skills/23-ai-workforce-blueprint/scripts"
  "/data/.openclaw/skills/23-ai-workforce-blueprint/scripts"
)
SKILL23_SCRIPTS=""
for _c in "${SKILL23_CANDIDATES[@]}"; do
  if [[ -f "$_c/canonical_decline.py" && -f "$_c/build-workforce.py" ]]; then
    SKILL23_SCRIPTS="$_c"
    break
  fi
done
if [[ -z "$SKILL23_SCRIPTS" ]]; then
  echo "[retire-confirmed-decline] FATAL: Skill 23 scripts dir (canonical_decline.py) not found; checked: ${SKILL23_CANDIDATES[*]}" >&2
  exit 3
fi

DEPTS=()
STATE_FILE=""
COMPANY_DIR=""
OC_CONFIG_OVERRIDE=""
DB_PATH="${DASHBOARD_DB_PATH:-${DATABASE_PATH:-}}"
SKIP_CC=0
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dept)              DEPTS+=("$2"); shift 2 ;;
    --build-state-file)  STATE_FILE="$2"; shift 2 ;;
    --company-dir)       COMPANY_DIR="$2"; shift 2 ;;
    --oc-config)         OC_CONFIG_OVERRIDE="$2"; shift 2 ;;
    --db)                DB_PATH="$2"; shift 2 ;;
    --skip-cc)           SKIP_CC=1; shift ;;
    --dry-run)           DRY_RUN=1; shift ;;
    -h|--help)           grep '^#' "$0" | head -60; exit 0 ;;
    *) echo "[retire-confirmed-decline] unknown argument: $1" >&2; exit 3 ;;
  esac
done

if [[ ${#DEPTS[@]} -eq 0 ]]; then
  echo "[retire-confirmed-decline] FATAL: at least one --dept <slug> (or --dept __declined__) is REQUIRED" >&2
  exit 3
fi

# ── resolve the build-state file (explicit scratch file wins; never guess) ──
if [[ -z "$STATE_FILE" ]]; then
  if [[ -f "/data/.openclaw/workspace/.workforce-build-state.json" ]]; then
    STATE_FILE="/data/.openclaw/workspace/.workforce-build-state.json"
  elif [[ -f "$HOME/.openclaw/workspace/.workforce-build-state.json" ]]; then
    STATE_FILE="$HOME/.openclaw/workspace/.workforce-build-state.json"
  else
    echo "[retire-confirmed-decline] FATAL: no live build-state found and no --build-state-file given (refusing to guess)" >&2
    exit 3
  fi
fi
if [[ ! -f "$STATE_FILE" ]]; then
  echo "[retire-confirmed-decline] FATAL: build-state file not found: $STATE_FILE" >&2
  exit 2
fi

# ── resolve the company dir (explicit wins; else live state companySlug) ────
if [[ -z "$COMPANY_DIR" ]]; then
  _SLUG="$(python3 -c "
import json, sys
try:
    d = json.load(open('$STATE_FILE'))
except (OSError, ValueError):
    sys.exit(0)
sys.stdout.write((d.get('companySlug') or d.get('clientSlug') or '').strip())
" 2>/dev/null || true)"
  if [[ -n "$_SLUG" ]]; then
    for _root in "$HOME/Downloads/openclaw-master-files/zero-human-company" \
                 "/data/openclaw-master-files/zero-human-company" \
                 "$HOME/clawd/zero-human-company"; do
      if [[ -d "$_root/$_SLUG" ]]; then COMPANY_DIR="$_root/$_SLUG"; break; fi
    done
  fi
fi

MODE="DRY-RUN"
[[ "$DRY_RUN" -eq 0 ]] && MODE="APPLY"
echo "[retire-confirmed-decline] $MODE: state=$STATE_FILE company=${COMPANY_DIR:-<unresolved>} db=${DB_PATH:-<none>} depts=${DEPTS[*]}" >&2

# ══ THE GATE: canonical_decline.py's shared reader must classify every ══
# requested department PROVENANCED before ANY mutation. Exits 2 (fail-closed,
# nothing touched) when a requested dept has no honored decline.
python3 - "$SKILL23_SCRIPTS" "$STATE_FILE" "${DEPTS[@]}" <<'PY' >/dev/null || exit 2
import json, sys
sys.path.insert(0, sys.argv[1])
import canonical_decline as cd  # the ONE shared reader (master plan PHASE 3 gate)
state_path, requested = sys.argv[2], sys.argv[3:]
try:
    state = json.load(open(state_path, encoding="utf-8"))
except (OSError, ValueError) as exc:
    print(f"[retire-gate] REFUSED: cannot read build-state: {exc}", file=sys.stderr)
    sys.exit(2)
view = cd.analyze(state, quiet=False)
declined, rejections = view["declined"], view["rejections"]
if "__declined__" in requested:
    targets = sorted(declined)
else:
    targets = sorted({cd.norm(d) for d in requested if d and d != "__declined__"})
unprovenanced = [t for t in targets if t not in declined]
if not targets:
    print("[retire-gate] no provenanced declines to retire — nothing to do", file=sys.stderr)
    sys.exit(0)
if unprovenanced or rejections:
    for u in unprovenanced:
        print(f"[retire-gate] REFUSED: '{u}' has NO provenanced decline record "
              f"(canonical_decline.py did not honor it) — nothing retired (fail-safe "
              f"to the larger floor).", file=sys.stderr)
    for r in rejections:
        print(f"[retire-gate] rejected decline on record: {r.get('id')} [{r.get('reason')}]",
              file=sys.stderr)
    sys.exit(2)
sys.exit(0)
PY
GATE_RC=$?
if [[ $GATE_RC -eq 0 ]]; then :; elif [[ $GATE_RC -eq 2 ]]; then exit 2; else exit 1; fi

TARGETS_JSON="$(python3 - "$SKILL23_SCRIPTS" "$STATE_FILE" "${DEPTS[@]}" <<'PY'
import json, sys
sys.path.insert(0, sys.argv[1])
import canonical_decline as cd
state = json.load(open(sys.argv[2], encoding="utf-8"))
view = cd.analyze(state, quiet=True)
declined = view["declined"]
requested = sys.argv[3:]
targets = sorted(declined) if "__declined__" in requested else \
    sorted({cd.norm(d) for d in requested if d and d != "__declined__"})
prebuilt = (state.get("standardPrebuild") or {}).get("prebuiltDepartments") or []
raws, known = [], set()
for slug in prebuilt:
    if cd.norm(slug) in targets and slug not in raws:
        raws.append(slug); known.add(cd.norm(slug))
for t in targets:
    if t not in known:
        raws.append(t)
print(json.dumps(raws))
PY
)"
if [[ "$TARGETS_JSON" == "[]" ]]; then
  echo "[retire-confirmed-decline] no provenanced declines to retire — nothing to do" >&2
  exit 0
fi

echo "[retire-confirmed-decline] provenance gate PASSED — retiring: $TARGETS_JSON" >&2

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "[retire-confirmed-decline] DRY-RUN complete: would retire $TARGETS_JSON (no mutation performed)" >&2
  exit 0
fi

FAILURES=0

# ── STEP 2: ARCHIVE each department tree to company_dir/.retired/<slug>-<ts>/ ──
# NEVER delete. Runs FIRST so a declined tree can never linger on the board's
# provisioned layer after the lane is dropped.
TS="$(date +%Y%m%d-%H%M%S)"
if [[ -n "$COMPANY_DIR" && -d "$COMPANY_DIR/departments" ]]; then
  while IFS= read -r SLUG; do
    [[ -z "$SLUG" ]] && continue
    SRC="$COMPANY_DIR/departments/$SLUG"
    if [[ ! -d "$SRC" ]]; then
      echo "[retire-confirmed-decline] step 2: '$SLUG' — no tree at $SRC (nothing to archive; continuing)" >&2
      continue
    fi
    DEST="$COMPANY_DIR/.retired/$SLUG-$TS"
    mkdir -p "$COMPANY_DIR/.retired"
    if mv "$SRC" "$DEST"; then
      echo "[retire-confirmed-decline] step 2: archived $SRC -> $DEST (NEVER deleted)" >&2
    else
      echo "[retire-confirmed-decline] step 2 FAILED for '$SLUG': could not move $SRC -> $DEST" >&2
      FAILURES=$((FAILURES + 1))
    fi
  done < <(echo "$TARGETS_JSON" | python3 -c "import json,sys; [print(s) for s in json.load(sys.stdin)]")
else
  echo "[retire-confirmed-decline] step 2 SKIPPED: no company dir with departments/ resolvable ($COMPANY_DIR)" >&2
fi

# ── STEP 1: deregister agents.list rows (only if lazily registered) ─────────
# SCRATCH ISOLATION (explicit-signal-only, same doctrine as the prebuild
# driver): when the build-state file is NOT one of the box's two live
# locations, the agents.list deregistration is SKIPPED unless an explicit
# --oc-config was passed — a scratch run must never touch the live config
# (a scratch test once deregistered a live box's dept row for exactly this
# reason; the guard is the fix).
OC_CONFIG=""
_SCRATCH_STATE=1
if [[ "$STATE_FILE" == "/data/.openclaw/workspace/.workforce-build-state.json" \
   || "$STATE_FILE" == "$HOME/.openclaw/workspace/.workforce-build-state.json" ]]; then
  _SCRATCH_STATE=0
fi
if [[ -n "$OC_CONFIG_OVERRIDE" ]]; then
  OC_CONFIG="$OC_CONFIG_OVERRIDE"
elif [[ "$_SCRATCH_STATE" -eq 0 ]]; then
  for _c in "/data/.openclaw/openclaw.json" "$HOME/.openclaw/openclaw.json"; do
    [[ -f "$_c" ]] && OC_CONFIG="$_c" && break
  done
fi
if [[ -z "$OC_CONFIG" && "$_SCRATCH_STATE" -eq 1 ]]; then
  echo "[retire-confirmed-decline] step 1 SKIPPED: scratch build-state without an explicit --oc-config (live config never touched by a scratch run)" >&2
elif [[ -n "$OC_CONFIG" && -f "$OC_CONFIG" ]]; then
  if ! python3 - "$OC_CONFIG" "$TARGETS_JSON" <<'PY'
import json, os, shutil, sys, datetime
config_path, targets = sys.argv[1], json.loads(sys.argv[2])
norm = lambda s: "".join(c for c in str(s).lower() if c.isalnum())
keys = {norm(f"dept-{t}") for t in targets} | {norm(t) for t in targets}
try:
    cfg = json.load(open(config_path, encoding="utf-8"))
except (OSError, ValueError) as exc:
    print(f"[retire-confirmed-decline] step 1 SKIPPED: cannot read openclaw.json: {exc}", file=sys.stderr)
    sys.exit(0)
agents = (cfg.get("agents") or {}).get("list") or []
keep, removed = [], []
for row in agents:
    if isinstance(row, dict) and norm(row.get("id", "")) in keys:
        removed.append(row.get("id"))
    else:
        keep.append(row)
if not removed:
    print("[retire-confirmed-decline] step 1: no agents.list rows were lazily registered — nothing to deregister", file=sys.stderr)
    sys.exit(0)
# Backup FIRST (config safety protocol; mirrors the build's backup discipline).
bak_dir = os.path.join(os.path.dirname(config_path), "backups")
os.makedirs(bak_dir, exist_ok=True)
bak = os.path.join(bak_dir, f"openclaw-backup-{datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}-pre-retire.json")
shutil.copy2(config_path, bak)
cfg["agents"]["list"] = keep
tmp = config_path + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(cfg, f, indent=2)
os.replace(tmp, config_path)
print(f"[retire-confirmed-decline] step 1: deregistered {removed} from agents.list (backup: {bak})", file=sys.stderr)
PY
  then
    echo "[retire-confirmed-decline] step 1 FAILED (agents.list deregistration)" >&2
    FAILURES=$((FAILURES + 1))
  fi
else
  echo "[retire-confirmed-decline] step 1 SKIPPED: no openclaw.json found (nothing registered)" >&2
fi

# ── STEP 3: Command Center lane removal via the existing delete surface ──────
# Mirrors src/lib/workspaces/department-optout.ts archiveDepartment() (PHASE 6
# of the master plan): soft archive (archived_at + archived_reason='retired'),
# NEVER a hard delete; idempotent; orchestrator column exempt. Explicit db only.
if [[ "$SKIP_CC" -eq 1 ]]; then
  echo "[retire-confirmed-decline] step 3 SKIPPED (--skip-cc)" >&2
elif [[ -z "$DB_PATH" || ! -f "$DB_PATH" ]]; then
  echo "[retire-confirmed-decline] step 3 NOT-APPLICABLE: no explicit Command Center database (--db / DASHBOARD_DB_PATH / DATABASE_PATH) — recorded as skipped, never faked" >&2
else
  if ! python3 - "$DB_PATH" "$TARGETS_JSON" <<'PY'
import json, sqlite3, sys
db_path, targets = sys.argv[1], json.loads(sys.argv[2])
norm = lambda s: "".join(c for c in str(s).lower() if c.isalnum())
EXEMPT = {"ceo", "deptceo", "masterorchestrator"}  # orchestrator column exempt
conn = sqlite3.connect(db_path)
cols = {r[1] for r in conn.execute("PRAGMA table_info(workspaces)")}
if "workspaces" not in {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}:
    print("[retire-confirmed-decline] step 3: no workspaces table — SKIPPED", file=sys.stderr)
    sys.exit(0)
if "archived_at" not in cols:
    print("[retire-confirmed-decline] step 3: workspaces.archived_at absent (migration 095 not applied) — SKIPPED, lane archive deferred to the Command Center web surface", file=sys.stderr)
    sys.exit(0)
rows = conn.execute("SELECT id, slug FROM workspaces").fetchall()
archived, already, refused = [], [], []
for t in targets:
    key = norm(t)
    if key in EXEMPT or norm(t) == norm("master-orchestrator"):
        refused.append(t)
        continue
    for wid, wslug in rows:
        if norm(wid) != key and norm(wslug or "") != key:
            continue
        cur = conn.execute(
            "UPDATE workspaces SET archived_at = COALESCE(archived_at, datetime('now')), "
            "archived_reason = COALESCE(archived_reason, 'retired'), "
            "updated_at = datetime('now') WHERE id = ? AND archived_at IS NULL", (wid,))
        (archived if cur.rowcount else already).append(wid)
conn.commit()
conn.close()
print(f"[retire-confirmed-decline] step 3: archived lanes {archived} (already archived: {already}; orchestrator-exempt refused: {refused}) — soft archive, rows PRESERVED", file=sys.stderr)
PY
  then
    echo "[retire-confirmed-decline] step 3 FAILED (Command Center lane archive)" >&2
    FAILURES=$((FAILURES + 1))
  fi
fi

# ── STEP 4: chosen artifact — removed-with-provenance append ─────────────────
if [[ -n "$COMPANY_DIR" ]]; then
  if ! python3 - "$COMPANY_DIR" "$TARGETS_JSON" "$STATE_FILE" <<'PY'
import json, os, sys, datetime
company_dir, targets, state_path = sys.argv[1], json.loads(sys.argv[2]), sys.argv[3]
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(state_path))))
artifact = os.path.join(company_dir, "departments.json")
try:
    state = json.load(open(state_path, encoding="utf-8"))
except (OSError, ValueError):
    state = {}
try:
    entries = json.load(open(artifact, encoding="utf-8"))
    if not isinstance(entries, list):
        entries = []
except (OSError, ValueError):
    entries = []
norm = lambda s: "".join(c for c in str(s).lower() if c.isalnum())
keys = {norm(t) for t in targets}
kept_entries, removed_slugs = [], []
for e in entries:
    slug = e.get("slug") or e.get("id") if isinstance(e, dict) else e
    if norm(slug or "") in keys:
        removed_slugs.append(slug)
    else:
        kept_entries.append(e)
# Reconstruct the provenance records for exactly the retired slugs.
records = []
try:
    recon = state.get("canonicalReconciliation") or {}
    decisions = recon.get("decisions") or {}
    for did, dec in decisions.items():
        if norm(did) in keys:
            rec = {"slug": did, "retiredAt": datetime.datetime.now().isoformat(),
                   "source": "retire-confirmed-decline.sh"}
            rec.update(dec if isinstance(dec, dict) else {"decision": str(dec)})
            records.append(rec)
    for entry in (recon.get("declinedDepartments") or []) + (state.get("declinedDepartments") or []):
        if isinstance(entry, dict) and norm(entry.get("id", "")) in keys:
            rec = {"retiredAt": datetime.datetime.now().isoformat(),
                   "source": "retire-confirmed-decline.sh"}
            rec.update(entry)
            if rec.get("slug") is None:
                rec["slug"] = entry.get("id")
            records.append(rec)
except Exception:
    pass
payload = {"removedWithProvenance": records, "departments": kept_entries}
# .bak first, then atomic tmp+rename (a crash mid-write never truncates the artifact).
if os.path.isfile(artifact):
    import shutil
    shutil.copy2(artifact, artifact + ".bak")
tmp = artifact + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(payload, f, indent=2)
os.replace(tmp, artifact)
print(f"[retire-confirmed-decline] step 4: chosen artifact rewritten — removed {removed_slugs}, "
      f"appended {len(records)} removed-with-provenance record(s) to retiredDepartments", file=sys.stderr)
PY
  then
    echo "[retire-confirmed-decline] step 4 FAILED (chosen-artifact rewrite)" >&2
    FAILURES=$((FAILURES + 1))
  fi
else
  echo "[retire-confirmed-decline] step 4 SKIPPED: no company dir resolvable" >&2
fi

echo "[retire-confirmed-decline] DONE: $TARGETS_JSON retired (archive-only; failures=$FAILURES)" >&2
[[ "$FAILURES" -eq 0 ]] && exit 0 || exit 1
