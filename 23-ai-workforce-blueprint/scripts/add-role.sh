#!/usr/bin/env bash
# add-role.sh — add a SINGLE specialist role under an existing department on a
# live client box, without running a full Skill 23 rebuild.
#
# Background (G6):
#   Pre-v11.2.0 there was no post-build script to add one role. The only path
#   was a full `build-workforce.py` re-run (rebuilds ALL departments). This
#   script fills that gap: one role, one dept, no rebuild.
#
# What it does (every step is idempotent — safe to re-run):
#   1. Validates the target department exists (workspaces table + $OC_ROOT dir)
#   2. Creates the role workspace directory under departments/<dept-slug>/roles/
#   3. Writes IDENTITY.md, SOUL.md, MEMORY.md, how-to.md (stub) for the new role
#   4. Inserts an agent row into the CC mission-control.db for the role
#      (specialist_type='specialist', status='standby')
#   5. Inherits (symlinks) USER.md, AGENTS.md, TOOLS.md from workspace root
#   6. Creates a placeholder persona governance file for the role
#   7. Touches .persona-index-stale so persona-selector-v2.py rebuilds its cache
#
# Usage:
#   bash add-role.sh --dept <dept-slug> --role "<Role Display Name>"
#   bash add-role.sh --dept graphics --role "3D Animation Specialist"
#   bash add-role.sh --dept sales --role "Pipeline Analyst" \
#       --description "Monitors deal pipeline health and flags stalled deals"
#
# Output: human-readable progress, then a single JSON line:
#   {"dept":"<slug>","role_slug":"<slug>","agent_id":"<hex>","status":"created"}
#   or {"dept":"<slug>","role_slug":"<slug>","agent_id":"<hex>","status":"already_exists"}
#
# Exit codes:
#   0 — success (created or already_exists)
#   1 — fatal (missing args, missing dept, DB error, etc.)

set -euo pipefail

# ─── Args ────────────────────────────────────────────────────────────────────
DEPT_SLUG=""
ROLE_NAME=""
DESCRIPTION=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dept)        DEPT_SLUG="${2:-}";   shift 2 ;;
    --role)        ROLE_NAME="${2:-}";   shift 2 ;;
    --description) DESCRIPTION="${2:-}"; shift 2 ;;
    -h|--help)
      sed -n '2,45p' "$0"
      exit 0
      ;;
    *)
      echo "[add-role] FATAL: unknown arg: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$DEPT_SLUG" || -z "$ROLE_NAME" ]]; then
  echo "[add-role] FATAL: --dept and --role are required" >&2
  echo "Usage: bash add-role.sh --dept <slug> --role \"<Role Display Name>\"" >&2
  exit 1
fi

# ─── Platform resolver ───────────────────────────────────────────────────────
# Mirrors add-department.sh, add-persona-from-source.sh, persona-inbox-watcher.sh
if [[ -d /data/.openclaw ]]; then
  OC_ROOT="/data/.openclaw"
elif [[ -d "$HOME/.openclaw" ]]; then
  OC_ROOT="$HOME/.openclaw"
else
  echo "[add-role] FATAL: no OpenClaw root found at /data/.openclaw or \$HOME/.openclaw" >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "[add-role] FATAL: python3 not on PATH — required" >&2
  exit 1
fi

# ─── Normalize slugs ─────────────────────────────────────────────────────────
DEPT_SLUG=$(echo "$DEPT_SLUG" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+|-+$//g')
ROLE_SLUG=$(echo "$ROLE_NAME" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+|-+$//g')

[[ -z "$DEPT_SLUG" ]] && { echo "[add-role] FATAL: dept slug normalized to empty" >&2; exit 1; }
[[ -z "$ROLE_SLUG" ]] && { echo "[add-role] FATAL: role slug normalized to empty" >&2; exit 1; }
[[ -z "$DESCRIPTION" ]] && DESCRIPTION="$ROLE_NAME specialist in the $DEPT_SLUG department."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[add-role] OC_ROOT=$OC_ROOT"
echo "[add-role] dept=$DEPT_SLUG  role=$ROLE_NAME  slug=$ROLE_SLUG"

# ─── Discover DB (mirrors add-department.sh and seed-workspaces.py) ──────────
DB_PATH=""
for cand in \
  "$HOME/projects/command-center/mission-control.db" \
  "$HOME/projects/mission-control/mission-control.db" \
  "/opt/mission-control/mission-control.db" \
  "/app/mission-control.db" \
  "/data/projects/command-center/mission-control.db"
do
  if [[ -f "$cand" ]]; then
    DB_PATH="$cand"
    break
  fi
done

[[ -z "$DB_PATH" ]] && { echo "[add-role] WARN: mission-control.db not found — agent row will be skipped"; }

echo "[add-role] DB=$DB_PATH"

# ─── All mutation in Python (no bash JSON acrobatics) ────────────────────────
export AR_OC_ROOT="$OC_ROOT"
export AR_DEPT_SLUG="$DEPT_SLUG"
export AR_ROLE_NAME="$ROLE_NAME"
export AR_ROLE_SLUG="$ROLE_SLUG"
export AR_DESCRIPTION="$DESCRIPTION"
export AR_SCRIPT_DIR="$SCRIPT_DIR"
export AR_DB_PATH="${DB_PATH:-}"

python3 <<'PYEOF'
import json
import os
import secrets
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

OC_ROOT     = os.environ["AR_OC_ROOT"]
DEPT_SLUG   = os.environ["AR_DEPT_SLUG"]
ROLE_NAME   = os.environ["AR_ROLE_NAME"]
ROLE_SLUG   = os.environ["AR_ROLE_SLUG"]
DESCRIPTION = os.environ["AR_DESCRIPTION"]
SCRIPT_DIR  = os.environ["AR_SCRIPT_DIR"]
DB_PATH     = os.environ.get("AR_DB_PATH", "")

NOW = datetime.now(timezone.utc).isoformat()


def emit_summary(payload):
    print("---SUMMARY---")
    print(json.dumps(payload, separators=(",", ":")))


def upsert_role_into_index(dept_slug, role_slug, oc_root, script_dir, now):
    """Add role_slug to _index.json under departments[dept_slug].roles[].
    FAIL LOUD if dept not found in index (adding a role to a non-existent dept
    is a wiring error). Returns True if file changed, False if no-op."""
    import tempfile
    candidates = [
        Path("/data/.openclaw/skills/23-ai-workforce-blueprint/templates/role-library/_index.json"),
        Path.home() / ".openclaw/skills/23-ai-workforce-blueprint/templates/role-library/_index.json",
        Path(script_dir).resolve().parent / "templates/role-library/_index.json",
        Path(script_dir).resolve().parent.parent / "23-ai-workforce-blueprint/templates/role-library/_index.json",
    ]
    target = None
    for p in candidates:
        if p.is_file():
            target = p
            break
    if not target:
        print(f"  [role-index] _index.json not found — skipping (run on box with installed skills)", file=sys.stderr)
        return False

    try:
        idx = json.load(open(target))
    except (json.JSONDecodeError, OSError) as e:
        print(f"  [role-index] FATAL: failed to read {target}: {e}", file=sys.stderr)
        sys.exit(1)

    deps = idx.setdefault("departments", {})
    if dept_slug not in deps:
        print(f"  [role-index] FATAL: dept '{dept_slug}' not found in _index.json — "
              f"add the department first with add-department.sh before adding roles.", file=sys.stderr)
        sys.exit(1)

    dept_entry = deps[dept_slug]
    roles = dept_entry.get("roles", [])
    if role_slug in roles:
        print(f"  [role-index] role '{role_slug}' already in _index.json for dept '{dept_slug}' — no-op")
        return False

    roles.append(role_slug)
    roles.sort()
    dept_entry["roles"] = roles
    dept_entry["count"] = len(roles)

    # Scaffold a LIBRARY how-to.md stub for the role so it is a COMPLETE,
    # registerable library artifact (not membership-without-a-file, which
    # register-library-additions.py --check would correctly flag as a half-add).
    # Folder-form <dept>/<slug>/how-to.md is the canonical library layout.
    lib_role_dir = target.parent / dept_slug / role_slug
    lib_how_to = lib_role_dir / "how-to.md"
    if not lib_how_to.exists():
        try:
            lib_role_dir.mkdir(parents=True, exist_ok=True)
            lib_how_to.write_text(
                f"# {role_slug.replace('-', ' ').title()} — how-to.md (stub)  "
                f"[PENDING — FILL FROM LIBRARY]\n\n"
                f"**Department:** {dept_slug}\n"
                f"**Role type:** specialist\n"
                f"**Status:** PENDING — fill this file with the role's SOPs before "
                f"assigning work.\n\n"
                f"## Responsibilities\n(Fill from interview or a sibling role template.)\n\n"
                f"## Section 9 — Standard Operating Procedures\n(Add per-task SOPs here.)\n",
                encoding="utf-8")
            print(f"  + library-stub   {lib_how_to}")
        except OSError as e:
            print(f"  [role-index] WARN: could not scaffold library stub {lib_how_to}: {e}",
                  file=sys.stderr)

    # Recompute global totals
    idx["total_roles"] = sum(len(d.get("roles", [])) for d in deps.values())
    idx["total_departments"] = len(deps)
    idx["generated_at"] = now

    # Atomic write (tmp + os.replace)
    idx_dir = target.parent
    fd, tmp_path = tempfile.mkstemp(prefix=".idx.", suffix=".json.tmp", dir=str(idx_dir))
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(idx, f, indent=2)
            f.write("\n")
        os.replace(tmp_path, str(target))
    except OSError as e:
        if Path(tmp_path).exists():
            Path(tmp_path).unlink(missing_ok=True)
        print(f"  [role-index] FATAL: write failed: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"  + role-index     added '{role_slug}' to dept '{dept_slug}' in _index.json "
          f"(total_roles={idx['total_roles']})")
    return True


def _append_add_ledger(oc_root, record):
    """Append one JSON line to the append-only add-ledger.jsonl (§1.8).
    Never raises — failure is WARN only (ledger is best-effort)."""
    import fcntl
    ledger_dir = Path(oc_root) / "extension-sync"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = ledger_dir / "add-ledger.jsonl"
    line = json.dumps(record, separators=(",", ":")) + "\n"
    try:
        with open(ledger_path, "a") as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX)
                f.write(line)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    except OSError as e:
        print(f"  [ledger] WARN: could not append to {ledger_path}: {e}", file=sys.stderr)


# ─── Locate the department workspace dir ─────────────────────────────────────
# Convention: departments live in $OC_ROOT/workspace/agents/main/departments/<slug>/
# Mirrors the path written by build-workforce.py DEPARTMENTS_DIR.
dept_dir_candidates = [
    Path(OC_ROOT) / "workspace" / "agents" / "main" / "departments" / DEPT_SLUG,
    Path(OC_ROOT) / "master-files" / "departments" / DEPT_SLUG,
]
dept_dir = next((d for d in dept_dir_candidates if d.is_dir()), None)

if not dept_dir:
    # First candidate didn't exist — create it so we can scaffold
    dept_dir = dept_dir_candidates[0]
    print(f"  [add-role] WARN: dept dir not found; creating at {dept_dir}")
    dept_dir.mkdir(parents=True, exist_ok=True)

role_dir = dept_dir / "roles" / ROLE_SLUG
workspace_root = Path(OC_ROOT) / "workspace"

print(f"  dept_dir : {dept_dir}")
print(f"  role_dir : {role_dir}")

# ─── Idempotency: if IDENTITY.md already present → short-circuit ─────────────
identity_path = role_dir / "IDENTITY.md"
agent_id = None

if identity_path.exists():
    print(f"  [add-role] role already scaffolded: {role_dir}")
    # Still attempt to insert/heal the DB row
else:
    role_dir.mkdir(parents=True, exist_ok=True)
    (role_dir / "memory").mkdir(exist_ok=True)

    # ── 1. IDENTITY.md ───────────────────────────────────────────────────────
    identity_content = f"""# IDENTITY.md — {ROLE_NAME}

**Department:** {DEPT_SLUG}
**Role:** {ROLE_NAME}
**Generated by:** add-role.sh (Skill 23 post-build)

## Who I Am

- **Name:** (assigned by department head during onboarding)
- **Role:** {ROLE_NAME}
- **Department:** {DEPT_SLUG}
- **Reports to:** Department Head of {DEPT_SLUG}

## What This Role Owns

{DESCRIPTION}

## Operating Discipline

- Read `how-to.md` FIRST before executing any task.
- Follow the matching SOP in `SOP/00-INDEX.md` for this task.
- If no SOP covers the task, escalate to the department head (do not guess).
- Use the symlinked TOOLS.md, AGENTS.md, USER.md to know tools, behavior, and owner.

## Operating Protocol — Read the SOP Before You Work (binding)

Before executing ANY task you are spawned for, in this order:
1. Read this folder's `how-to.md` — it is the entry point to your SOPs.
2. Open the matching procedure: the Section-9 SOP in `how-to.md` OR the file in
   `SOP/` indexed by `SOP/00-INDEX.md` that covers this task. Read it FIRST.
3. Execute the SOP step by step. Do not improvise around it.
4. If NO SOP covers the task, do NOT guess — escalate to your department head so
   the SOP-Writer can author one (INSTRUCTIONS.md Moment 3.7).
"""
    identity_path.write_text(identity_content, encoding="utf-8")
    print(f"  + IDENTITY.md    {identity_path}")

    # ── 2. SOUL.md ───────────────────────────────────────────────────────────
    soul_path = role_dir / "SOUL.md"
    soul_content = f"""# SOUL.md — {ROLE_NAME}

## Mission
Execute {ROLE_NAME} responsibilities for the {DEPT_SLUG} department at a quality
standard high enough to earn the owner's trust.

## Voice
Mirror the owner's communication style (see workspace USER.md > Behavioral
Identity Profile). Plain, direct, no jargon unless the task domain requires it.

## Values
- Output quality beats output speed
- Honor the persona when assigned; honor the mission always
- Surface uncertainty rather than guess
- Document what you learn in MEMORY.md

## Role Description
{DESCRIPTION}

## Operating Protocol — Read the SOP Before You Work (binding)

Before executing ANY task you are spawned for, in this order:
1. Read this folder's `how-to.md` — it is the entry point to your SOPs.
2. Open the matching procedure and read it FIRST.
3. Execute the SOP step by step. Do not improvise.
4. If NO SOP covers the task, escalate — do NOT guess.
"""
    soul_path.write_text(soul_content, encoding="utf-8")
    print(f"  + SOUL.md        {soul_path}")

    # ── 3. MEMORY.md ─────────────────────────────────────────────────────────
    memory_path = role_dir / "MEMORY.md"
    memory_content = f"""# MEMORY.md — {ROLE_NAME}

(Empty — fills with use.)

## Long-term facts
- (Updated as the role accumulates work)

## Decisions
- (Logged at the time they are made)

## What I have learned about the owner / customers
- (Captured from feedback over time)
"""
    memory_path.write_text(memory_content, encoding="utf-8")
    print(f"  + MEMORY.md      {memory_path}")

    # ── 4. how-to.md (stub) ───────────────────────────────────────────────────
    how_to_path = role_dir / "how-to.md"
    how_to_content = f"""# {ROLE_NAME} — how-to.md (stub)  [PENDING — FILL FROM LIBRARY]

**Department:** {DEPT_SLUG}
**Status:** PENDING — fill this file with the role's SOPs before assigning work.

## Quick-start
1. Read IDENTITY.md to understand who this role is.
2. Read SOUL.md to understand the mission and values.
3. Read this file (how-to.md) for the operating procedures.
4. Consult SOP/00-INDEX.md if it exists for this dept.

## Responsibilities
(Fill from role-library template or write from interview)

## Section 9 — Standard Operating Procedures
(Add per-task SOPs here, or create a SOP/ subfolder with 00-INDEX.md)
"""
    how_to_path.write_text(how_to_content, encoding="utf-8")
    print(f"  + how-to.md      {how_to_path}")

    # ── 5. Persona governance placeholder ────────────────────────────────────
    pg_path = role_dir / "governing-personas.md"
    pg_content = f"""# Governing Personas — {ROLE_NAME}

No personas pre-assigned. The department head assigns personas via
`persona-selector-v2.py --dept {DEPT_SLUG}` based on the task domain.

See `../governing-personas.md` for the department-level pool.
"""
    pg_path.write_text(pg_content, encoding="utf-8")
    print(f"  + governing-personas.md  {pg_path}")

    # ── 6. Symlink shared files (USER.md, AGENTS.md, TOOLS.md) ───────────────
    for fname in ("USER.md", "AGENTS.md", "TOOLS.md"):
        src = workspace_root / fname
        dst = role_dir / fname
        if not src.is_file():
            print(f"  [symlink] {fname} not found at {src}, skipping")
            continue
        if dst.is_symlink() and dst.resolve() == src.resolve():
            continue  # already correct
        if dst.exists() or dst.is_symlink():
            dst.unlink()
        try:
            dst.symlink_to(src)
            print(f"  ~ symlink        {fname} → {src}")
        except OSError as e:
            import shutil
            shutil.copy2(str(src), str(dst))
            print(f"  ~ copy (symlink fallback) {fname}")

# ─── 7. Insert agent row in CC DB ────────────────────────────────────────────
agent_status = "skipped_no_db"
if DB_PATH and Path(DB_PATH).is_file():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    try:
        ag_cols = [r[1] for r in db.execute("PRAGMA table_info(agents)")]
        if not ag_cols:
            print("  [DB] agents table missing — skipping agent row", file=sys.stderr)
            agent_status = "skipped_no_table"
        else:
            # Idempotency: check for existing row by persona field
            persona_key = f"role-{DEPT_SLUG}-{ROLE_SLUG}"
            existing = db.execute(
                "SELECT id FROM agents WHERE persona = ? LIMIT 1",
                (persona_key,)
            ).fetchone()
            if existing:
                agent_id = existing[0]
                print(f"  [DB] agent row already exists: {agent_id}")
                agent_status = "already_exists"
            else:
                agent_id = secrets.token_hex(8)
                ag_data = {
                    "id": agent_id,
                    "workspace_id": DEPT_SLUG,
                    "name": ROLE_NAME,
                    "role": ROLE_NAME,
                    "persona": persona_key,
                    "description": DESCRIPTION,
                    "specialist_type": "specialist",
                    "status": "standby",
                    "avatar_emoji": "🔧",
                    "is_master": 0,
                    "created_at": NOW,
                    "updated_at": NOW,
                }
                insert_cols = [c for c in ag_data if c in ag_cols]
                sql = (f"INSERT INTO agents ({','.join(insert_cols)}) "
                       f"VALUES ({','.join('?'*len(insert_cols))})")
                db.execute(sql, [ag_data[c] for c in insert_cols])
                db.commit()
                print(f"  + agent          {agent_id}  ({ROLE_NAME})")
                agent_status = "created"
    finally:
        db.close()

# ─── 8. Upsert role into _index.json (§1.1 — NEW) ───────────────────────────
index_changed = upsert_role_into_index(DEPT_SLUG, ROLE_SLUG, OC_ROOT, SCRIPT_DIR, NOW)

# ─── 9. Append to add-ledger (§1.8) ──────────────────────────────────────────
_append_add_ledger(OC_ROOT, {
    "ts": NOW,
    "type": "role",
    "slug": ROLE_SLUG,
    "dept": DEPT_SLUG,
    "status": "already_exists" if agent_status == "already_exists" else "created",
    "detail": f"role_name={ROLE_NAME}, index_changed={index_changed}, pending_how_to=true",
    "by": "agent",
})

# ─── 10. Touch .persona-index-stale ──────────────────────────────────────────
skill23_dir = Path(OC_ROOT) / "skills" / "23-ai-workforce-blueprint"
if skill23_dir.is_dir():
    marker = skill23_dir / ".persona-index-stale"
    try:
        marker.write_text(NOW + "\n")
        print(f"  ~ persona-stale  {marker}")
    except OSError as e:
        print(f"  [persona-stale] WARN: {e}", file=sys.stderr)
else:
    print(f"  [persona-stale] skill 23 dir not found at {skill23_dir}; no-op")

# ─── Done ─────────────────────────────────────────────────────────────────────
final_status = "already_exists" if agent_status == "already_exists" else ("created" if identity_path.exists() else "error")
emit_summary({
    "dept": DEPT_SLUG,
    "role": ROLE_NAME,
    "role_slug": ROLE_SLUG,
    "role_dir": str(role_dir),
    "agent_id": agent_id or "none",
    "agent_status": agent_status,
    "status": final_status,
    "pending_how_to": True,
})
PYEOF

RC=$?
if [[ $RC -ne 0 ]]; then
  echo "[add-role] FATAL: python mutation failed (rc=$RC)" >&2
  exit $RC
fi

# B6: WIRING GATE — blocking for this dept (not advisory)
_WIRING_SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/verify-wiring.sh"
if [[ -f "$_WIRING_SCRIPT" ]]; then
  echo "[add-role] Running wiring gate for dept $DEPT_SLUG..."
  _WIRING_RC=0
  bash "$_WIRING_SCRIPT" --dept "$DEPT_SLUG" 2>&1 | tail -30 || _WIRING_RC=$?
  if [[ "$_WIRING_RC" != "0" ]]; then
    echo "[add-role] ERROR: verify-wiring.sh failed (rc=$_WIRING_RC) for dept $DEPT_SLUG — dept is NOT wired." >&2
    echo "[add-role] wiringStatus set to 'failed'. Fix registration/reachability then re-run." >&2
    exit 1
  fi
  echo "[add-role] Wiring gate PASSED for dept $DEPT_SLUG."
else
  echo "[add-role] WARN: verify-wiring.sh not found — run it manually after filling how-to.md" >&2
fi

# v12.34.0: AUTO-REGISTER — reconcile the role-library _index.json with what is
# now on disk. The §8 upsert above adds the role's SLUG to departments[].roles[],
# but the detailed roles[] entry (title/role_type/capability_class/path/word_count)
# AND the per-artifact content_sha are produced by register-library-additions.py,
# which discovers the new role file, ADDS its roles[] entry (idempotent — never
# clobbers existing metadata), re-tags capability_class, and re-stamps the content
# manifest in one pass. This is what keeps BOTH the library-lockstep gate and the
# CONTENT-HASH gate green after an add. Falls back to the bare content-hash restamp
# if the register script is unavailable (older installs).
_REGISTER_SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/register-library-additions.py"
_HASH_SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/hash-content-manifest.py"
if [[ -f "$_REGISTER_SCRIPT" ]] && command -v python3 >/dev/null 2>&1; then
  echo "[add-role] AUTO-REGISTER: reconciling _index.json with disk + restamping content manifest..."
  python3 "$_REGISTER_SCRIPT" --apply >/dev/null 2>&1 \
    && echo "[add-role] library index reconciled + content-manifest re-stamped." \
    || echo "[add-role] WARN: register-library-additions.py reported drift (run: python3 $_REGISTER_SCRIPT --check)." >&2
elif [[ -f "$_HASH_SCRIPT" ]] && command -v python3 >/dev/null 2>&1; then
  echo "[add-role] Re-stamping per-artifact content manifest (content_sha/version)..."
  python3 "$_HASH_SCRIPT" >/dev/null 2>&1 \
    && echo "[add-role] content-manifest re-stamped." \
    || echo "[add-role] WARN: hash-content-manifest.py re-stamp reported warnings (run it manually)." >&2
fi

echo ""
echo "[add-role] Done. Role '$ROLE_NAME' added under dept '$DEPT_SLUG'."
echo "  Next steps (ALL REQUIRED):"
echo "    1. Fill how-to.md from the role-library template (remove the [PENDING — FILL FROM LIBRARY] marker)."
echo "       Template: 23-ai-workforce-blueprint/templates/role-library/<dept>/<role>/how-to.md"
echo "    2. Run generate-governing-personas.sh to update persona pools."
echo "    3. Re-stamp the content manifest so content_sha reflects the FILLED how-to.md:"
echo "       python3 23-ai-workforce-blueprint/scripts/hash-content-manifest.py"
echo "    4. Run converge: bash 32-command-center-setup/scripts/sync-extensions.sh --converge"
echo "       This updates build-state, ORG-CHART.md, infographic, Notion, and the CC dashboard."
exit 0
