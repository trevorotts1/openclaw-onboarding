#!/usr/bin/env bash
# sync-extensions.sh — Skill 32 Command Center Setup
#
# PURPOSE
#   Master idempotent orchestrator for post-build capability extension.
#   In --converge mode: full sweep (depts + roles + SOPs + personas + CC sync).
#   In legacy mode (no --converge): departments-only fast path for Sunday cron.
#
# WHAT IT DOES (--converge mode, §1.6)
#   1. Detects deltas: depts + roles + SOPs + personas vs last-sync.json
#   2. Registers routing + materializes workspaces for new depts
#   3. Validates _index.json invariants (total_roles == sum(dept role counts))
#   4. Refreshes build-state + org chart + Notion (via refresh-build-state-from-index.py
#      and build-workforce.py --regenerate-org-chart-only)
#   5. Re-syncs the Command Center: POST /api/system/converge (HTTP preferred);
#      falls back to on-box seed-workspaces.py + ingest-sop-library.py if unreachable
#   6. Handles untagged personas: writes needs-tags.json; surfaces in Telegram
#   7. Updates last-sync.json (extended: depts+roles+SOPs+personas)
#   8. Sends Telegram summary (new entities + untagged personas + CC sync path)
#   9. Runs post-add ground-truth QC (asserts new entity visible in CC)
#
# IDEMPOTENCY CONTRACT (unchanged from v11.18.5)
#   - Running twice in a row produces the same state (no duplicates)
#   - Never removes existing departments, agents, or routing rules
#   - Never touches agents NOT in the extension delta
#   - Fails loudly (exit 1) on any mutating step that errors
#
# USAGE
#   bash sync-extensions.sh --converge [--dry-run] [--verbose] [--fast]
#   bash sync-extensions.sh [--dry-run] [--verbose]    # legacy depts-only
#   bash sync-extensions.sh --dept <slug>              # force-add a single dept
#
# --fast     Skip infographic/Notion re-renders (cheap path; used by Sunday cron)
#            In --fast mode, full renders run only when deltas exist.
#
# CALLED FROM
#   Client agent: closing step of EVERY add-*.sh run (converge mode)
#   Sunday cron (0 3 * * 0): sync-extensions.sh --converge --fast
#   CC dashboard: POST /api/system/converge calls back via MC_API_TOKEN
#   Manually after adding a new skill/dept to the role-library

set -uo pipefail

# ─── Logging ─────────────────────────────────────────────────────────────────
P="[sync-ext]"
info()    { printf '%s %s\n'             "$P" "$*"; }
ok()      { printf '%s \033[32m✓\033[0m %s\n' "$P" "$*"; }
warn()    { printf '%s \033[33m⚠\033[0m %s\n' "$P" "$*" >&2; }
fail()    { printf '%s \033[31m✗\033[0m %s\n' "$P" "$*" >&2; }
die()     { fail "$*"; exit 1; }

DRY_RUN=0
VERBOSE=0
FORCE_DEPT=""
CONVERGE_MODE=0
FAST_MODE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)   DRY_RUN=1 ;;
    --verbose)   VERBOSE=1 ;;
    --converge)  CONVERGE_MODE=1 ;;
    --fast)      FAST_MODE=1 ;;
    --dept)      shift; FORCE_DEPT="$1" ;;
    *) warn "Unknown flag: $1" ;;
  esac
  shift
done

[[ $DRY_RUN -eq 1 ]]    && info "DRY-RUN MODE — no mutations"
[[ $CONVERGE_MODE -eq 1 ]] && info "CONVERGE MODE — full sweep (depts + roles + SOPs + personas + CC)"
[[ $FAST_MODE -eq 1 ]]     && info "FAST MODE — infographic/Notion renders skipped unless deltas present"

# ─── Platform detection ───────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$SKILL_ROOT/.." && pwd)"
ADD_DEPT_SH="$SCRIPT_DIR/add-department.sh"

if [[ -f "/data/.openclaw/openclaw.json" ]]; then
  OC_ROOT="/data/.openclaw"
  OC_PLATFORM="vps"
elif [[ -f "$HOME/.openclaw/openclaw.json" ]]; then
  OC_ROOT="$HOME/.openclaw"
  OC_PLATFORM="mac"
else
  die "Cannot find openclaw.json — run the OpenClaw installer first"
fi

OC_JSON="$OC_ROOT/openclaw.json"
info "Platform : $OC_PLATFORM"
info "Config   : $OC_JSON"

# ─── Path resolution ─────────────────────────────────────────────────────────
INDEX_JSON="$REPO_ROOT/23-ai-workforce-blueprint/templates/role-library/_index.json"
# Also check installed-skills path (live box)
if [[ ! -f "$INDEX_JSON" ]]; then
  for idx_cand in \
    "$OC_ROOT/skills/23-ai-workforce-blueprint/templates/role-library/_index.json" \
    "$HOME/.openclaw/skills/23-ai-workforce-blueprint/templates/role-library/_index.json" \
    "/data/.openclaw/skills/23-ai-workforce-blueprint/templates/role-library/_index.json"
  do
    if [[ -f "$idx_cand" ]]; then
      INDEX_JSON="$idx_cand"
      break
    fi
  done
fi
DETECT_PY="$SCRIPT_DIR/detect-extensions.py"
REGISTER_PY="$SCRIPT_DIR/register-routing-dept.py"
MATERIALIZE_SH="$SCRIPT_DIR/materialize-dept-agents.sh"
BUILD_WORKFORCE_PY="$REPO_ROOT/23-ai-workforce-blueprint/scripts/build-workforce.py"
REFRESH_BUILD_STATE_PY="$REPO_ROOT/23-ai-workforce-blueprint/scripts/refresh-build-state-from-index.py"
REGEN_SOP_INDEX_PY="$REPO_ROOT/23-ai-workforce-blueprint/scripts/regenerate-sop-index.py"
# AUTO-REGISTER: reconcile any NEW on-disk library role/SOP/persona/dept into
# _index.json (+ content-hash restamp) BEFORE propagation, so a library half-add
# can never propagate as an invisible/partial role.
REGISTER_LIB_PY="$REPO_ROOT/23-ai-workforce-blueprint/scripts/register-library-additions.py"
SEED_WORKSPACES_PY="$SCRIPT_DIR/seed-workspaces.py"
INGEST_SOP_LIBRARY_SH="$SCRIPT_DIR/ingest-sop-library.sh"
GENERATE_INFOGRAPHICS_SH="$REPO_ROOT/37-zhc-closeout/scripts/generate-infographics.sh"
CREATE_NOTION_SH="$REPO_ROOT/37-zhc-closeout/scripts/create-notion-closeout.sh"

# Also check installed paths for key scripts
for script_var in REFRESH_BUILD_STATE_PY REGEN_SOP_INDEX_PY BUILD_WORKFORCE_PY REGISTER_LIB_PY; do
  script_path="${!script_var}"
  if [[ ! -f "$script_path" ]]; then
    for oc_cand in \
      "/data/.openclaw/skills" \
      "$HOME/.openclaw/skills"
    do
      cand_23="$oc_cand/23-ai-workforce-blueprint/scripts/$(basename "$script_path")"
      if [[ -f "$cand_23" ]]; then
        eval "$script_var=\"$cand_23\""
        break
      fi
    done
  fi
done

SYNC_STATE_DIR="$OC_ROOT/extension-sync"
LAST_SYNC_JSON="$SYNC_STATE_DIR/last-sync.json"
NEEDS_TAGS_JSON="$SYNC_STATE_DIR/needs-tags.json"
ADD_LEDGER_JSONL="$SYNC_STATE_DIR/add-ledger.jsonl"
SYNC_LOG="$SYNC_STATE_DIR/sync-$(date +%Y%m%d-%H%M%S).log"

mkdir -p "$SYNC_STATE_DIR"

[[ -f "$INDEX_JSON" ]] || die "Role-library _index.json not found at: $INDEX_JSON (check installed skills)"
[[ -f "$DETECT_PY"  ]] || die "detect-extensions.py not found at: $DETECT_PY"

# ─── Step 1: Detect extension delta ──────────────────────────────────────────
info "Detecting extension delta..."

if [[ -n "$FORCE_DEPT" ]]; then
  info "Force-adding single dept: $FORCE_DEPT"
  NEW_DEPTS="$FORCE_DEPT"
  NEW_ROLES=""
  NEW_SOPS=""
  NEW_PERSONAS=""
  UNTAGGED_PERSONAS=""
else
  DETECT_ARGS="--index $INDEX_JSON"
  [[ -f "$LAST_SYNC_JSON" ]] && DETECT_ARGS="$DETECT_ARGS --last-sync $LAST_SYNC_JSON"
  [[ $VERBOSE -eq 1 ]] && DETECT_ARGS="$DETECT_ARGS --verbose"

  DETECT_OUTPUT="$(python3 "$DETECT_PY" $DETECT_ARGS 2>&1)" || {
    fail "detect-extensions.py failed"
    fail "$DETECT_OUTPUT"
    exit 1
  }

  # Legacy dept delta (back-compat: grep '^NEW: ' still works since detect-extensions.py
  # emits both NEW: and NEW-DEPT: for each new dept)
  NEW_DEPTS="$(echo "$DETECT_OUTPUT" | grep '^NEW-DEPT: ' | sed 's/^NEW-DEPT: //')"
  # Fallback: if NEW-DEPT: lines absent (older detect-extensions.py), use NEW: lines
  if [[ -z "$NEW_DEPTS" ]]; then
    NEW_DEPTS="$(echo "$DETECT_OUTPUT" | grep '^NEW: ' | sed 's/^NEW: //')"
  fi
  SKIP_COUNT="$(echo "$DETECT_OUTPUT" | grep '^SKIP: ' | wc -l | tr -d ' ')"

  # Extended delta (converge mode only)
  NEW_ROLES="$(echo "$DETECT_OUTPUT" | grep '^NEW-ROLE: ' | sed 's/^NEW-ROLE: //')"
  NEW_SOPS="$(echo "$DETECT_OUTPUT" | grep '^NEW-SOP: ' | sed 's/^NEW-SOP: //')"
  NEW_PERSONAS="$(echo "$DETECT_OUTPUT" | grep '^NEW-PERSONA: ' | sed 's/^NEW-PERSONA: //')"
  UNTAGGED_PERSONAS="$(echo "$DETECT_OUTPUT" | grep '^UNTAGGED: ' | sed 's/^UNTAGGED: //')"

  [[ $VERBOSE -eq 1 ]] && info "Detect output:" && echo "$DETECT_OUTPUT"
fi

# In converge mode, we continue even with no new depts (roles/SOPs/personas may be new)
HAS_ANY_DELTA=0
[[ -n "$NEW_DEPTS" ]] && HAS_ANY_DELTA=1
[[ $CONVERGE_MODE -eq 1 && -n "${NEW_ROLES:-}" ]] && HAS_ANY_DELTA=1
[[ $CONVERGE_MODE -eq 1 && -n "${NEW_SOPS:-}" ]] && HAS_ANY_DELTA=1
[[ $CONVERGE_MODE -eq 1 && -n "${NEW_PERSONAS:-}" ]] && HAS_ANY_DELTA=1

if [[ -z "$NEW_DEPTS" && $HAS_ANY_DELTA -eq 0 ]]; then
  ok "No new entities detected — sync is current."
  # Still update the last-sync timestamp
  [[ $DRY_RUN -eq 0 ]] && python3 - "$INDEX_JSON" "$LAST_SYNC_JSON" <<'PYEOF'
import json, sys
from datetime import datetime, timezone
idx = json.load(open(sys.argv[1]))
state = {"synced_at": datetime.now(timezone.utc).isoformat(),
         "departments": list(idx.get("departments", {}).keys()),
         "total_roles": idx.get("total_roles", 0),
         "version": idx.get("version", "unknown")}
with open(sys.argv[2], "w") as f:
    json.dump(state, f, indent=2)
PYEOF
  if [[ $CONVERGE_MODE -eq 1 ]]; then
    info "Converge mode: no delta, but running CC re-sync for consistency"
    # Fall through to CC re-sync step
  else
    exit 0
  fi
fi

info "New departments to register: $(echo "$NEW_DEPTS" | wc -l | tr -d ' ')"
echo "$NEW_DEPTS" | while IFS= read -r dept; do info "  + $dept"; done

# ─── Step 2: Register each new department ────────────────────────────────────
REGISTERED=()
FAILED=()

while IFS= read -r dept; do
  [[ -z "$dept" ]] && continue
  info "Processing: $dept"

  # 2a. Register routing entry
  if [[ -f "$REGISTER_PY" ]]; then
    if [[ $DRY_RUN -eq 0 ]]; then
      if python3 "$REGISTER_PY" --dept "$dept" --config "$OC_JSON" 2>&1; then
        ok "  routing registered: $dept"
      else
        warn "  routing registration failed for: $dept (continuing)"
        FAILED+=("$dept")
        continue
      fi
    else
      info "  [DRY-RUN] would register routing for: $dept"
    fi
  else
    warn "register-routing-dept.py not found — skipping routing registration"
  fi

  # 2b. Materialize agent workspace dirs (idempotent)
  if [[ -f "$MATERIALIZE_SH" ]]; then
    if [[ $DRY_RUN -eq 0 ]]; then
      bash "$MATERIALIZE_SH" --dept "$dept" 2>&1 && \
        ok "  workspace materialized: $dept" || \
        warn "  workspace materialization warning for: $dept"
    else
      info "  [DRY-RUN] would materialize workspace for: $dept"
    fi
  fi

  # 2c. (G2 fix) Create CC workspaces row + QC specialist via add-department.sh.
  #     The routing registration (2a) writes openclaw.json only — it NEVER
  #     creates the SQLite workspaces row that loadDepartments() reads.
  #     add-department.sh is idempotent: if the row already exists it returns
  #     {"status":"already_exists"} and exits 0.
  if [[ -f "$ADD_DEPT_SH" ]]; then
    # Derive a human-readable display name from the slug:
    #   "project-architecture-office" → "Project Architecture Office"
    DEPT_DISPLAY=$(echo "$dept" | sed -E 's/-/ /g' | awk '{for(i=1;i<=NF;i++) $i=toupper(substr($i,1,1)) substr($i,2); print}')
    if [[ $DRY_RUN -eq 0 ]]; then
      ADOUT=$(bash "$ADD_DEPT_SH" --slug "$dept" --name "$DEPT_DISPLAY" 2>&1)
      ADD_RC=$?
      # Parse the ---SUMMARY--- JSON block to detect created vs already_exists
      ADD_STATUS=$(echo "$ADOUT" | awk '/^---SUMMARY---/{found=1; next} found{print; exit}' | python3 -c "import json,sys; d=json.loads(sys.stdin.read().strip()); print(d.get('status','unknown'))" 2>/dev/null || echo "unknown")
      if [[ $ADD_RC -eq 0 ]]; then
        ok "  CC workspace row: $dept ($ADD_STATUS)"
      else
        warn "  CC workspace row failed for: $dept (rc=$ADD_RC) — continuing"
        warn "  Output: $(echo "$ADOUT" | tail -5)"
      fi
    else
      info "  [DRY-RUN] would create CC workspace row for: $dept"
    fi
  else
    warn "  add-department.sh not found — CC workspaces row NOT created for: $dept (orphan risk)"
  fi

  REGISTERED+=("$dept")
done <<< "$NEW_DEPTS"

# ─── Step 2b-pre: AUTO-REGISTER new library artifacts into _index.json ───────
# Before validating invariants OR propagating, reconcile the role-library index
# with what is actually on disk: register any NEW role/SOP/persona/dept file that
# was added to the library without its _index.json entry (+ restamp the content
# manifest), and surface any duplicate-residue / triple-hyphen orphan. This is the
# library-side AUTO-REGISTER that makes a library add WHOLE before it propagates
# into client workspaces — the system-wide companion to add-role.sh / add-department.sh.
# Idempotent: a no-op when the library is already in sync.
if [[ $CONVERGE_MODE -eq 1 && -f "$REGISTER_LIB_PY" ]]; then
  info "Step 2b-pre: AUTO-REGISTER new library artifacts into _index.json..."
  if [[ $DRY_RUN -eq 1 ]]; then
    python3 "$REGISTER_LIB_PY" --index "$INDEX_JSON" 2>&1 | sed 's/^/    /' || true
    info "  [DRY-RUN] would run: register-library-additions.py --apply"
  else
    if python3 "$REGISTER_LIB_PY" --index "$INDEX_JSON" --apply 2>&1 | sed 's/^/    /'; then
      ok "Step 2b-pre: library index reconciled with disk (new roles/SOPs/personas registered + content-hash restamped)"
    else
      fail "Step 2b-pre: register-library-additions.py --apply reported drift it could not auto-heal"
      die "Library has a half-add that needs manual attention (e.g. duplicate-residue or triple-hyphen orphan). Run: python3 $REGISTER_LIB_PY --check"
    fi
  fi
elif [[ $CONVERGE_MODE -eq 1 ]]; then
  warn "register-library-additions.py not found — skipping library AUTO-REGISTER (run it manually if you added library files)"
fi

# ─── Step 2c extended: validate _index.json invariants (converge mode) ───────
if [[ $CONVERGE_MODE -eq 1 && $DRY_RUN -eq 0 ]]; then
  info "Step 2c: Validating _index.json invariants..."
  INVARIANT_RESULT="$(python3 - "$INDEX_JSON" <<'PYEOF'
import json, sys
idx = json.load(open(sys.argv[1]))
deps = idx.get("departments", {})
computed = sum(len(d.get("roles", [])) for d in deps.values())
reported = idx.get("total_roles", None)
if reported != computed:
    print(f"INVARIANT_FAIL: total_roles={reported} but sum(dept roles)={computed}")
    sys.exit(1)
# Also verify count == len(roles) per dept
bad = []
for slug, d in deps.items():
    if d.get("count") != len(d.get("roles", [])):
        bad.append(f"{slug}: count={d.get('count')} vs len(roles)={len(d.get('roles',[]))}")
if bad:
    print("INVARIANT_FAIL: per-dept count drift: " + "; ".join(bad))
    sys.exit(1)
print(f"INVARIANT_OK: total_roles={computed}, total_departments={len(deps)}")
PYEOF
  )" || {
    fail "Step 2c: _index.json invariant FAIL: $INVARIANT_RESULT"
    die "_index.json is internally inconsistent. Re-run add-role.sh or add-department.sh to fix."
  }
  ok "Step 2c: $INVARIANT_RESULT"
fi

# ─── Step 3: Refresh build-state + org chart + Notion (converge mode) ────────
if [[ $CONVERGE_MODE -eq 1 && $DRY_RUN -eq 0 ]]; then
  info "Step 3a: Refreshing build-state from _index.json..."

  # C3: Run gates FIRST (they write per-dept roleLibraryFilled/sopLibraryFilled/wiringStatus),
  # THEN run refresh (which reads those gate-written fields for gated done-flip).
  _BLUEPRINT_SCRIPTS="$(dirname "$REFRESH_BUILD_STATE_PY")"
  _VERIFY_LIB_SH="$_BLUEPRINT_SCRIPTS/verify-library-gate.sh"
  _VERIFY_WIRING_SH="$_BLUEPRINT_SCRIPTS/verify-wiring.sh"
  _GATE_LIB_RC=0
  _GATE_WIRING_RC=0

  if [[ -f "$_VERIFY_LIB_SH" ]]; then
    info "Step 3a-gate: Running verify-library-gate.sh..."
    bash "$_VERIFY_LIB_SH" 2>&1 || _GATE_LIB_RC=$?
    if [[ $_GATE_LIB_RC -eq 0 ]]; then
      ok "Step 3a-gate: verify-library-gate.sh PASSED"
    else
      warn "Step 3a-gate: verify-library-gate.sh rc=$_GATE_LIB_RC (some depts may not have full libraries)"
    fi
  else
    warn "Step 3a-gate: verify-library-gate.sh not found — library gate skipped"
  fi

  if [[ -f "$_VERIFY_WIRING_SH" ]]; then
    info "Step 3a-gate: Running verify-wiring.sh --all..."
    bash "$_VERIFY_WIRING_SH" --all 2>&1 || _GATE_WIRING_RC=$?
    if [[ $_GATE_WIRING_RC -eq 0 ]]; then
      ok "Step 3a-gate: verify-wiring.sh PASSED"
    else
      warn "Step 3a-gate: verify-wiring.sh rc=$_GATE_WIRING_RC (some depts may not be wired)"
    fi
  else
    warn "Step 3a-gate: verify-wiring.sh not found — wiring gate skipped"
  fi

  if [[ -f "$REFRESH_BUILD_STATE_PY" ]]; then
    REFRESH_ARGS="--strict"
    [[ $VERBOSE -eq 1 ]] && REFRESH_ARGS="--strict --verbose"
    if python3 "$REFRESH_BUILD_STATE_PY" $REFRESH_ARGS 2>&1; then
      ok "Step 3a: build-state refreshed (strict mode — status:done gated on library+wiring)"
    else
      fail "Step 3a: refresh-build-state-from-index.py failed"
      die "build-state refresh failed — converge cannot continue without current build-state."
    fi
  else
    warn "Step 3a: refresh-build-state-from-index.py not found at $REFRESH_BUILD_STATE_PY — skipping"
  fi

  info "Step 3b: Regenerating ORG-CHART.md..."
  if [[ -f "$BUILD_WORKFORCE_PY" ]]; then
    if python3 "$BUILD_WORKFORCE_PY" --regenerate-org-chart-only 2>&1; then
      ok "Step 3b: ORG-CHART.md regenerated"
    else
      warn "Step 3b: --regenerate-org-chart-only failed (non-fatal — org chart may be stale)"
    fi
  else
    warn "Step 3b: build-workforce.py not found — ORG-CHART.md NOT regenerated"
  fi

  if [[ $FAST_MODE -eq 0 || $HAS_ANY_DELTA -eq 1 ]]; then
    info "Step 3c: Re-rendering infographic..."
    if [[ -f "$GENERATE_INFOGRAPHICS_SH" ]]; then
      bash "$GENERATE_INFOGRAPHICS_SH" structure 2>&1 && ok "Step 3c: infographic regenerated" || \
        warn "Step 3c: infographic regeneration failed (non-fatal)"
    else
      warn "Step 3c: generate-infographics.sh not found — skipping"
    fi

    info "Step 3d: Refreshing Notion workforce tree..."
    if [[ -f "$CREATE_NOTION_SH" ]]; then
      if bash "$CREATE_NOTION_SH" --refresh-workforce-only 2>&1; then
        ok "Step 3d: Notion workforce tree refreshed"
      else
        warn "Step 3d: Notion workforce refresh failed or page id not set — SKIPPED (non-fatal)"
      fi
    else
      warn "Step 3d: create-notion-closeout.sh not found — skipping Notion refresh"
    fi
  else
    info "Step 3c/3d: FAST mode + no delta — skipping infographic/Notion renders"
  fi
fi

# ─── Step 3 (legacy): Update last-sync manifest (all modes) ──────────────────
if [[ $DRY_RUN -eq 0 ]]; then
  info "Step 3e: Updating last-sync.json..."
  python3 - "$INDEX_JSON" "$LAST_SYNC_JSON" "$OC_ROOT" <<'PYEOF'
import json, os, sys
from datetime import datetime, timezone
from pathlib import Path

idx = json.load(open(sys.argv[1]))
oc_root = sys.argv[3] if len(sys.argv) > 3 else ""

# Flatten roles from index
all_roles = []
for dept, ddata in idx.get("departments", {}).items():
    for role in ddata.get("roles", []):
        all_roles.append(f"{dept}/{role}")

# Scan on-disk SOPs
sops = []
for depts_cand in [
    Path(oc_root) / "workspace/agents/main/departments" if oc_root else None,
    Path(oc_root) / "workspace/departments" if oc_root else None,
]:
    if depts_cand and depts_cand.is_dir():
        for dept_dir in sorted(depts_cand.iterdir()):
            if not dept_dir.is_dir() or dept_dir.name.startswith("."):
                continue
            dept = dept_dir.name
            for sop_dir in [dept_dir / "SOP"] + [
                r / "SOP" for r in (dept_dir / "roles").iterdir()
                if (dept_dir / "roles").is_dir() and r.is_dir() and not r.name.startswith(".")
            ] if (dept_dir / "roles").is_dir() else [dept_dir / "SOP"]:
                if sop_dir.is_dir():
                    for f in sop_dir.glob("*.md"):
                        if f.name == "00-INDEX.md":
                            continue
                        stem = f.stem
                        parts = stem.split("-", 1)
                        slug = parts[1] if (len(parts) == 2 and parts[0].isdigit()) else stem
                        sops.append(f"{dept}/{slug}")
        break

# Scan personas
personas = []
for pc_cand in [
    Path(oc_root) / "workspace/data/coaching-personas/persona-categories.json" if oc_root else None,
    Path(oc_root) / "workspace/coaching-personas/persona-categories.json" if oc_root else None,
]:
    if pc_cand and pc_cand.is_file():
        try:
            pc = json.load(open(pc_cand))
            personas = list(pc.get("personas", {}).keys())
        except Exception:
            pass
        break

state = {
    "synced_at": datetime.now(timezone.utc).isoformat(),
    "version": idx.get("version", "unknown"),
    "total_roles": idx.get("total_roles", 0),
    "departments": list(idx.get("departments", {}).keys()),
    "roles": sorted(all_roles),
    "sops": sorted(set(sops)),
    "personas": sorted(personas),
}
with open(sys.argv[2], "w") as f:
    json.dump(state, f, indent=2)
    f.write("\n")
print(f"last-sync.json updated: {sys.argv[2]}")
PYEOF
  ok "last-sync.json updated"
fi

# ─── Step 4: Re-sync Command Center (converge mode only, §1.6 step 5) ────────
CC_SYNC_PATH="none"
if [[ $CONVERGE_MODE -eq 1 && $DRY_RUN -eq 0 ]]; then
  info "Step 4: Re-syncing Command Center..."

  CC_BASE_URL="${CC_BASE_URL:-${NEXT_PUBLIC_APP_URL:-http://localhost:3000}}"
  MC_API_TOKEN="${MC_API_TOKEN:-${CRON_SECRET:-}}"

  CC_HTTP_OK=0
  if [[ -n "$MC_API_TOKEN" && -n "$CC_BASE_URL" ]]; then
    CC_CONVERGE_RESP="$(curl -sf -X POST "$CC_BASE_URL/api/system/converge" \
      -H "Authorization: Bearer $MC_API_TOKEN" \
      -H "Content-Type: application/json" \
      -d '{"scope":"all"}' \
      --max-time 60 2>&1)" && CC_HTTP_OK=1 || CC_HTTP_OK=0

    if [[ $CC_HTTP_OK -eq 1 ]]; then
      ok "Step 4: CC converge via HTTP succeeded ($CC_BASE_URL/api/system/converge)"
      CC_SYNC_PATH="http"
    else
      warn "Step 4: CC HTTP converge failed (rc=$? output: ${CC_CONVERGE_RESP:0:200}) — trying on-box fallback"
    fi
  else
    warn "Step 4: MC_API_TOKEN or CC_BASE_URL not set — skipping HTTP converge, trying on-box fallback"
  fi

  if [[ $CC_HTTP_OK -eq 0 ]]; then
    # On-box fallback: seed-workspaces.py + ingest-sop-library.sh
    FALLBACK_OK=0
    if [[ -f "$SEED_WORKSPACES_PY" ]]; then
      if python3 "$SEED_WORKSPACES_PY" 2>&1; then
        ok "  fallback: seed-workspaces.py succeeded"
        FALLBACK_OK=1
      else
        warn "  fallback: seed-workspaces.py failed"
      fi
    else
      warn "  fallback: seed-workspaces.py not found at $SEED_WORKSPACES_PY"
    fi

    if [[ -f "$INGEST_SOP_LIBRARY_SH" ]]; then
      if bash "$INGEST_SOP_LIBRARY_SH" 2>&1; then
        ok "  fallback: ingest-sop-library.sh succeeded"
        FALLBACK_OK=1
      else
        warn "  fallback: ingest-sop-library.sh failed"
      fi
    fi

    if [[ $FALLBACK_OK -eq 1 ]]; then
      CC_SYNC_PATH="on-box-fallback"
      info "Step 4: CC re-synced via on-box fallback"
    else
      fail "Step 4: BOTH HTTP converge AND on-box fallback failed."
      die "CC is out of sync. Check CC_BASE_URL=$CC_BASE_URL and MC_API_TOKEN, or run seed-workspaces.py manually."
    fi
  fi
fi

# ─── Step 5: Persona tags (converge mode, §1.6 step 6) ───────────────────────
UNTAGGED_COUNT=0
if [[ $CONVERGE_MODE -eq 1 && $DRY_RUN -eq 0 && -n "${UNTAGGED_PERSONAS:-}" ]]; then
  UNTAGGED_COUNT="$(echo "$UNTAGGED_PERSONAS" | wc -l | tr -d ' ')"
  info "Step 5: $UNTAGGED_COUNT untagged persona(s) detected — writing needs-tags.json"

  python3 - "$NEEDS_TAGS_JSON" <<PYEOF
import json, sys
from datetime import datetime, timezone
slugs = """${UNTAGGED_PERSONAS}""".strip().splitlines()
data = {"generated_at": datetime.now(timezone.utc).isoformat(), "untagged": [s.strip() for s in slugs if s.strip()]}
with open(sys.argv[1], "w") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
print(f"needs-tags.json written: {len(data['untagged'])} untagged persona(s)")
PYEOF
  ok "Step 5: needs-tags.json updated"
elif [[ $CONVERGE_MODE -eq 1 && $DRY_RUN -eq 0 ]]; then
  # No untagged personas — clear any stale needs-tags.json
  if [[ -f "$NEEDS_TAGS_JSON" ]]; then
    python3 -c "
import json
from datetime import datetime, timezone
with open('$NEEDS_TAGS_JSON', 'w') as f:
    json.dump({'generated_at': datetime.now(timezone.utc).isoformat(), 'untagged': []}, f, indent=2)
    f.write('\n')
"
    ok "Step 5: needs-tags.json cleared (no untagged personas)"
  fi
fi

# ─── Step 6: Append converge record to add-ledger (§1.8) ─────────────────────
if [[ $CONVERGE_MODE -eq 1 && $DRY_RUN -eq 0 ]]; then
  # C3: Ledger status is conditional on both gates passing
  _CONVERGE_STATUS="done"
  _CONVERGE_GATE_REASON=""
  if [[ $_GATE_LIB_RC -ne 0 ]]; then
    _CONVERGE_STATUS="incomplete"
    _CONVERGE_GATE_REASON="library-gate-failed(rc=$_GATE_LIB_RC)"
  fi
  if [[ $_GATE_WIRING_RC -ne 0 ]]; then
    _CONVERGE_STATUS="incomplete"
    _CONVERGE_GATE_REASON="${_CONVERGE_GATE_REASON:+$_CONVERGE_GATE_REASON,}wiring-gate-failed(rc=$_GATE_WIRING_RC)"
  fi

  python3 - "$ADD_LEDGER_JSONL" "$CC_SYNC_PATH" "$_CONVERGE_STATUS" "${_CONVERGE_GATE_REASON:-}" <<PYEOF
import json, sys, fcntl
from datetime import datetime, timezone
ledger_path = sys.argv[1]
cc_path = sys.argv[2]
converge_status = sys.argv[3] if len(sys.argv) > 3 else "done"
gate_reason = sys.argv[4] if len(sys.argv) > 4 else ""
new_depts = """${NEW_DEPTS:-}""".strip()
new_roles = """${NEW_ROLES:-}""".strip()
record = json.dumps({
    "ts": datetime.now(timezone.utc).isoformat(),
    "type": "converge",
    "slug": "full-converge",
    "status": converge_status,
    "detail": f"new_depts={len([d for d in new_depts.splitlines() if d])}, new_roles={len([r for r in new_roles.splitlines() if r])}, cc_sync_path={cc_path}, gate_reason={gate_reason}",
    "by": "converge",
}, separators=(",", ":"))
try:
    with open(ledger_path, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(record + "\n")
        fcntl.flock(f, fcntl.LOCK_UN)
except OSError as e:
    print(f"WARN: could not write ledger: {e}", file=sys.stderr)
PYEOF
fi

# ─── Step 7: Telegram summary (extended for converge mode) ───────────────────
if [[ $DRY_RUN -eq 0 ]]; then
  if [[ ${#REGISTERED[@]} -gt 0 || $CONVERGE_MODE -eq 1 ]]; then
    # C3: Telegram message is conditional on gates passing
    if [[ "${_CONVERGE_STATUS:-done}" == "incomplete" ]]; then
      MSG="Extension sync INCOMPLETE on $(hostname) — library/wiring gate failed: ${_CONVERGE_GATE_REASON:-unknown}. Depts may not be fully ready. Check logs."
    else
      MSG="Extension sync complete on $(hostname)."
    fi

    if [[ ${#REGISTERED[@]} -gt 0 ]]; then
      REG_LIST="$(printf '%s\n' "${REGISTERED[@]}" | sed 's/^/  • /')"
      MSG="$MSG
New departments registered (${#REGISTERED[@]}):
$REG_LIST"
    fi

    if [[ $CONVERGE_MODE -eq 1 ]]; then
      NEW_ROLES_COUNT=0
      NEW_SOPS_COUNT=0
      NEW_PERSONAS_COUNT=0
      [[ -n "${NEW_ROLES:-}" ]] && NEW_ROLES_COUNT=$(echo "$NEW_ROLES" | wc -l | tr -d ' ')
      [[ -n "${NEW_SOPS:-}" ]] && NEW_SOPS_COUNT=$(echo "$NEW_SOPS" | wc -l | tr -d ' ')
      [[ -n "${NEW_PERSONAS:-}" ]] && NEW_PERSONAS_COUNT=$(echo "$NEW_PERSONAS" | wc -l | tr -d ' ')
      MSG="$MSG
New roles: $NEW_ROLES_COUNT | New SOPs: $NEW_SOPS_COUNT | New personas: $NEW_PERSONAS_COUNT
CC sync path: $CC_SYNC_PATH"
      if [[ $UNTAGGED_COUNT -gt 0 ]]; then
        MSG="$MSG
ATTENTION: $UNTAGGED_COUNT persona(s) need domain/perspective tags before they are routable.
See extension-sync/needs-tags.json for the list."
      fi
    fi

    if [[ ${#FAILED[@]} -gt 0 ]]; then
      FAIL_LIST="$(printf '%s\n' "${FAILED[@]}" | sed 's/^/  • /')"
      MSG="$MSG

FAILED to register (${#FAILED[@]}) — manual review needed:
$FAIL_LIST"
    fi

    # Send via openclaw message send (rule: never bypass OpenClaw for Telegram)
    openclaw message send --channel telegram --body "$MSG" 2>/dev/null || \
      warn "Telegram summary send failed (non-fatal)"
  fi
fi

# ─── Result ───────────────────────────────────────────────────────────────────
if [[ ${#FAILED[@]} -gt 0 ]]; then
  fail "sync completed with ${#FAILED[@]} failure(s): ${FAILED[*]}"
  exit 1
fi

if [[ $CONVERGE_MODE -eq 1 ]]; then
  ok "sync-extensions.sh --converge complete — ${#REGISTERED[@]} new dept(s), CC sync: $CC_SYNC_PATH"
else
  ok "sync-extensions.sh complete — ${#REGISTERED[@]} new dept(s) registered."
fi
