#!/usr/bin/env bash
# backfill-per-dept-healer.sh -- One-shot idempotent backfill for already-built boxes.
#
# Ensures every materialized department on this box has:
#   (a) a per-dept Healer DB row in mission-control.db  (role_type = "healer")
#   (b) a healer-<dept>.md role FILE in the role library
#
# Design constraints (from spec section B):
#   - Heartbeat OFF for Healer: never adds healer to agents.defaults.heartbeat.agentsOnly
#   - NEVER touches IDENTITY / SOUL / MEMORY of existing agents (write_if_missing contract)
#   - Interview-complete gated: exits 0 with SKIP message if interviewComplete != true
#   - Backs up openclaw.json and mission-control.db before any write
#   - Writes per-box receipt to /tmp/v12-healer-backfill/<box-slug>.json
#   - Hard fails if openclaw config validate returns non-zero; restores backup
#   - Re-runnable: every insert is WHERE NOT EXISTS; every file write is write-if-missing
#
# Usage:
#   bash 32-command-center-setup/scripts/backfill-per-dept-healer.sh
#   bash 32-command-center-setup/scripts/backfill-per-dept-healer.sh --dry-run
#
# Exit codes:
#   0 -- success OR interview incomplete (skip is a pass, not a failure)
#   1 -- fatal error (backup failed, python error, config validate failed)

set -euo pipefail

# ---- Platform detection — via the shared resolver (false-negative #3 fix) ---
# Centralized /data-else-HOME .openclaw detection; identical inline fallback if
# the shared file is absent. See shared-utils/resolve-oc-root.sh.
_OC_ROOT_RESOLVER="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)/../../shared-utils/resolve-oc-root.sh"
# shellcheck source=/dev/null
[[ -f "$_OC_ROOT_RESOLVER" ]] && source "$_OC_ROOT_RESOLVER"
if declare -F resolve_oc_root >/dev/null 2>&1; then
  if _oc_root_resolved="$(resolve_oc_root)"; then
    OC_ROOT="$_oc_root_resolved"
  else
    echo "[backfill-healer] FATAL: no OpenClaw root found at /data/.openclaw or \$HOME/.openclaw" >&2
    exit 1
  fi
elif [[ -d /data/.openclaw ]]; then
  OC_ROOT="/data/.openclaw"
elif [[ -d "$HOME/.openclaw" ]]; then
  OC_ROOT="$HOME/.openclaw"
else
  echo "[backfill-healer] FATAL: no OpenClaw root found at /data/.openclaw or \$HOME/.openclaw" >&2
  exit 1
fi

CONFIG_FILE="$OC_ROOT/openclaw.json"
BACKUP_DIR="$OC_ROOT/backups"
DRY_RUN=0

if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
  echo "[backfill-healer] DRY RUN mode -- no writes will be made"
fi

if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "[backfill-healer] FATAL: openclaw.json not found at $CONFIG_FILE" >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "[backfill-healer] FATAL: python3 not on PATH -- required for DB mutation" >&2
  exit 1
fi

# ---- Interview-complete gate (B.2.1) ---------------------------------------
WF_STATE="$OC_ROOT/workspace/.workforce-build-state.json"

interview_complete=false
if [[ -f "$WF_STATE" ]]; then
  if python3 -c "import json,sys; d=json.load(open('$WF_STATE')); sys.exit(0 if d.get('interviewComplete') == True else 1)" 2>/dev/null; then
    interview_complete=true
  fi
fi

BOX_SLUG=$(hostname -s 2>/dev/null || echo "unknown-box")

if [[ "$interview_complete" != "true" ]]; then
  echo "[backfill-healer] SKIP $BOX_SLUG: interview incomplete (interviewComplete != true) - templates on disk, departments not materialized"
  exit 0
fi

# ---- Check buildCompletedAt (corroborating signal, not the gate) -----------
build_completed=false
if [[ -f "$WF_STATE" ]]; then
  if python3 -c "import json,sys; d=json.load(open('$WF_STATE')); sys.exit(0 if d.get('buildCompletedAt') else 1)" 2>/dev/null; then
    build_completed=true
  fi
fi

if [[ "$build_completed" != "true" ]]; then
  echo "[backfill-healer] INFO: interviewComplete=true but buildCompletedAt is null -- interview done, build still pending. Skipping department materialization."
  exit 0
fi

# ---- Discover skills dir ---------------------------------------------------
# The healer template lives in the skills install
SKILLS_CANDIDATES=(
  "/data/.openclaw/workspace/.openclaw-skills"
  "$HOME/.openclaw/workspace/.openclaw-skills"
  "/data/skills"
  "$HOME/skills"
)
SKILLS_DIR=""
for c in "${SKILLS_CANDIDATES[@]}"; do
  if [[ -d "$c" ]]; then
    SKILLS_DIR="$c"
    break
  fi
done

HEALER_TEMPLATE=""
if [[ -n "$SKILLS_DIR" ]]; then
  CANDIDATE="$SKILLS_DIR/23-ai-workforce-blueprint/templates/role-library/healer/dept-healer-template.md"
  if [[ -f "$CANDIDATE" ]]; then
    HEALER_TEMPLATE="$CANDIDATE"
  fi
fi

if [[ -z "$HEALER_TEMPLATE" ]]; then
  echo "[backfill-healer] WARN: dept-healer-template.md not found in skills dir -- role files will not be written (DB rows will still be inserted)" >&2
fi

# ---- Backup before any write -----------------------------------------------
if [[ $DRY_RUN -eq 0 ]]; then
  mkdir -p "$BACKUP_DIR"
  TS=$(date -u +%Y%m%dT%H%M%SZ)
  BACKUP_CONFIG="$BACKUP_DIR/openclaw-backup-${TS}-pre-backfill-healer.json"
  cp "$CONFIG_FILE" "$BACKUP_CONFIG"
  echo "[backfill-healer] backed up openclaw.json -> $BACKUP_CONFIG"

  # Backup mission-control.db if found
  DB_BACKUP=""
  for db_candidate in \
      "$OC_ROOT/workspaces/command-center/mission-control.db" \
      "$OC_ROOT/workspace/mission-control.db" \
      "$OC_ROOT/data/mission-control.db"; do
    if [[ -f "$db_candidate" ]]; then
      DB_BACKUP="$BACKUP_DIR/mission-control-backup-${TS}-pre-backfill-healer.db"
      cp "$db_candidate" "$DB_BACKUP"
      echo "[backfill-healer] backed up mission-control.db -> $DB_BACKUP"
      break
    fi
  done
fi

# ---- Run the backfill in Python --------------------------------------------
export OC_ROOT_PATH="$OC_ROOT"
export OC_DRY_RUN="$DRY_RUN"
export OC_HEALER_TEMPLATE="${HEALER_TEMPLATE:-}"
export OC_SKILLS_DIR="${SKILLS_DIR:-}"
export OC_BOX_SLUG="$BOX_SLUG"

RECEIPT_DIR="/tmp/v12-healer-backfill"
mkdir -p "$RECEIPT_DIR" 2>/dev/null || true

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

python3 <<'PYEOF'
import json
import os
import sys
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

OC_ROOT = os.environ["OC_ROOT_PATH"]
DRY_RUN = os.environ["OC_DRY_RUN"] == "1"
HEALER_TEMPLATE = os.environ.get("OC_HEALER_TEMPLATE", "")
SKILLS_DIR = os.environ.get("OC_SKILLS_DIR", "")
BOX_SLUG = os.environ.get("OC_BOX_SLUG", "unknown-box")
RECEIPT_DIR = "/tmp/v12-healer-backfill"
SCRIPTS_DIR = os.environ.get("OC_SCRIPTS_DIR", "")

# Add scripts dir to path so we can import lib-trio-quad-rows
if SCRIPTS_DIR:
    sys.path.insert(0, SCRIPTS_DIR)

try:
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "lib_trio_quad_rows",
        os.path.join(SCRIPTS_DIR, "lib-trio-quad-rows.py") if SCRIPTS_DIR else ""
    )
    if spec and spec.loader:
        lib = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(lib)
        ensure_trio_quad_rows = lib.ensure_trio_quad_rows
    else:
        raise ImportError("spec not found")
except Exception as e:
    print(f"[backfill-healer] WARN: could not load lib-trio-quad-rows.py: {e}", file=sys.stderr)
    ensure_trio_quad_rows = None


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def find_db():
    candidates = [
        os.path.join(OC_ROOT, "workspaces", "command-center", "mission-control.db"),
        os.path.join(OC_ROOT, "workspace", "mission-control.db"),
        os.path.join(OC_ROOT, "data", "mission-control.db"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def discover_departments():
    """Return list of (slug, name, workspace_id) tuples from the workspaces table."""
    db_path = find_db()
    if not db_path:
        return []
    try:
        db = sqlite3.connect(db_path)
        cur = db.execute(
            "SELECT id, name, slug FROM workspaces WHERE type != 'main' AND type != 'system' ORDER BY name"
        )
        rows = cur.fetchall()
        db.close()
        result = []
        for ws_id, name, slug in rows:
            if ws_id and name:
                result.append((ws_id, name, slug or name.lower().replace(" ", "-")))
        return result
    except Exception as e:
        print(f"[backfill-healer] WARN: could not query workspaces: {e}", file=sys.stderr)
        return []


def pretty_name(slug):
    return slug.replace("-", " ").title()


def write_healer_role_file(dept_slug, dept_name, skills_role_lib):
    """Write healer-<dept>.md to the role library if missing."""
    if not HEALER_TEMPLATE or not os.path.isfile(HEALER_TEMPLATE):
        return False
    target_dir = os.path.join(skills_role_lib, dept_slug)
    if not os.path.isdir(target_dir):
        return False
    target_file = os.path.join(target_dir, f"healer-{dept_slug}.md")
    if os.path.isfile(target_file):
        return False  # already exists, write-if-missing
    if DRY_RUN:
        print(f"  [DRY RUN] would write {target_file}")
        return True
    with open(HEALER_TEMPLATE, "r") as f:
        content = f.read()
    # Fill only DEPARTMENT_NAME; other tokens filled by WS-2 instantiation path
    content = content.replace("{{DEPARTMENT_NAME}}", dept_name)
    with open(target_file, "w") as f:
        f.write(content)
    return True


# ---- Discover departments and role-library path ----------------------------
departments = discover_departments()
if not departments:
    # Fallback: scan workspace/departments/ folders
    for base in [
        os.path.join(OC_ROOT, "workspaces", "command-center"),
        os.path.join(OC_ROOT, "workspace", "departments"),
    ]:
        if os.path.isdir(base):
            for entry in sorted(os.scandir(base), key=lambda e: e.name):
                if entry.is_dir():
                    slug = entry.name
                    departments.append(("", pretty_name(slug), slug))

skills_role_lib = ""
if SKILLS_DIR:
    candidate = os.path.join(SKILLS_DIR, "23-ai-workforce-blueprint", "templates", "role-library")
    if os.path.isdir(candidate):
        skills_role_lib = candidate

db_path = find_db()

# ---- Tally ----------------------------------------------------------------
total_depts = len(departments)
healers_added = 0
healers_already = 0
role_files_written = 0
qc_added = 0
research_added = 0
da_added = 0

db = None
if db_path and not DRY_RUN and ensure_trio_quad_rows:
    db = sqlite3.connect(db_path)
elif db_path and DRY_RUN:
    print(f"[backfill-healer] [DRY RUN] would mutate {db_path}")

for ws_id, dept_name, dept_slug in departments:
    print(f"[backfill-healer] processing dept: {dept_name} ({dept_slug})")

    # DB rows
    if db and ws_id and ensure_trio_quad_rows:
        try:
            counts = ensure_trio_quad_rows(db, ws_id, dept_name, dept_slug, "")
            if counts.get("healer", 0):
                healers_added += 1
            else:
                healers_already += 1
            qc_added += counts.get("qc", 0)
            research_added += counts.get("deep-research", 0)
            da_added += counts.get("devils-advocate", 0)
        except Exception as e:
            print(f"  WARN: DB insert failed for {dept_slug}: {e}", file=sys.stderr)
            healers_already += 1
    elif not ws_id or not ensure_trio_quad_rows:
        print(f"  SKIP DB rows for {dept_slug}: no workspace_id or lib unavailable")
        healers_already += 1

    # Role file
    if skills_role_lib:
        if write_healer_role_file(dept_slug, dept_name, skills_role_lib):
            role_files_written += 1

if db:
    db.commit()
    db.close()

# ---- Write per-box receipt -------------------------------------------------
receipt = {
    "box": BOX_SLUG,
    "interviewComplete": True,
    "departments": total_depts,
    "healers_added": healers_added,
    "healers_already": healers_already,
    "role_files_written": role_files_written,
    "qc_added": qc_added,
    "research_added": research_added,
    "da_added": da_added,
    "validated": False,  # updated after config validate below
    "dry_run": DRY_RUN,
    "ts": now_iso(),
}

receipt_path = os.path.join(RECEIPT_DIR, f"{BOX_SLUG}.json")
try:
    with open(receipt_path, "w") as f:
        json.dump(receipt, f, indent=2)
    print(f"[backfill-healer] wrote receipt -> {receipt_path}")
except Exception as e:
    print(f"[backfill-healer] WARN: could not write receipt: {e}", file=sys.stderr)

print(
    f"[backfill-healer] PRE-VALIDATE SUMMARY"
    f" box={BOX_SLUG}"
    f" departments={total_depts}"
    f" healers_added={healers_added}"
    f" healers_already={healers_already}"
    f" role_files={role_files_written}"
)
PYEOF

RC=$?
if [[ $RC -ne 0 ]]; then
  echo "[backfill-healer] FATAL: python DB mutation failed (rc=$RC)" >&2
  exit $RC
fi

# ---- Config validate -------------------------------------------------------
if [[ $DRY_RUN -eq 0 ]]; then
  if command -v openclaw >/dev/null 2>&1; then
    echo "[backfill-healer] running openclaw config validate..."
    if ! openclaw config validate 2>&1; then
      echo "[backfill-healer] FATAL: config validate failed -- restoring backup" >&2
      cp "$BACKUP_CONFIG" "$CONFIG_FILE"
      echo "[backfill-healer] restored openclaw.json from $BACKUP_CONFIG" >&2
      exit 1
    fi
    echo "[backfill-healer] config validate PASSED"

    # Update receipt: validated = true
    python3 - <<'PYEOF2'
import json, os
BOX_SLUG = os.environ.get("OC_BOX_SLUG", "unknown-box")
path = f"/tmp/v12-healer-backfill/{BOX_SLUG}.json"
if os.path.isfile(path):
    with open(path) as f:
        r = json.load(f)
    r["validated"] = True
    with open(path, "w") as f:
        json.dump(r, f, indent=2)
PYEOF2
  else
    echo "[backfill-healer] WARN: openclaw CLI not found -- skipping config validate" >&2
  fi
fi

# ---- Final machine-readable line -------------------------------------------
export OC_SCRIPTS_DIR="$SCRIPTS_DIR"
python3 - <<'PYEOF3'
import json, os
BOX_SLUG = os.environ.get("OC_BOX_SLUG", "unknown-box")
path = f"/tmp/v12-healer-backfill/{BOX_SLUG}.json"
if os.path.isfile(path):
    with open(path) as f:
        r = json.load(f)
    print(
        f"[backfill-healer] DONE"
        f" box={r['box']}"
        f" departments={r['departments']}"
        f" healers_added={r['healers_added']}"
        f" role_files={r['role_files_written']}"
        f" validated={r['validated']}"
    )
PYEOF3

exit 0
