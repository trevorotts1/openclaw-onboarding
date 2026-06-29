#!/usr/bin/env bash
# materialize-dept-agents.sh — turn workspace department folders into REAL agents.
#
# The bug this fixes (introduced and lived in for weeks):
#   Skill 23 "AI Workforce Blueprint" wrote role-definition.md files into
#   $OC_ROOT/workspace/departments/<slug>/ and flipped the dept's
#   .workforce-build-state.json status to "done" purely based on file
#   presence. The OpenClaw runtime never knew about any of these
#   "departments" — the gateway, dashboard, and Telegram bots all saw a
#   single agent (the default "main").
#
#   Skill 32 INSTALL.md Phase 4 documented "the agent adds an entry to
#   agents.list[]" — but no script in 32-command-center-setup/scripts/
#   actually performed that mutation. It was prose, not code. So every
#   client onboarded under v10.14.12–v10.14.18 ended up with a Telegram
#   celebration claiming N-department, M-role workforce LIVE while the
#   runtime saw exactly one agent.
#
# What this script does:
#   - Auto-detects the OpenClaw root ($OC_ROOT — VPS: /data/.openclaw, Mac: $HOME/.openclaw)
#   - Scans workspace/departments/ AND workspaces/command-center/ for dept folders
#   - For each dept, adds (or updates) an entry in openclaw.json's agents.list[]
#     following the schema in 32-command-center-setup/INSTALL.md Phase 4
#   - Atomic write (tmp file + rename); timestamped backup before mutation
#   - Idempotent — re-running adds zero duplicates; updates existing entries
#     in-place if workspace path or pretty name changes
#   - Hard-fails loud if anything goes wrong
#
# All JSON mutation happens in a Python heredoc (Python is on every VPS/Mac).
# Bash quoting on nested JSON was the previous trap — we deliberately avoid jq.
#
# Usage:
#   bash 32-command-center-setup/scripts/materialize-dept-agents.sh
#   bash 32-command-center-setup/scripts/materialize-dept-agents.sh --dry-run
#
# Exit codes:
#   0 — success (zero or more agents added/updated)
#   1 — fatal error (missing openclaw.json, malformed JSON, python missing, etc.)

set -euo pipefail

# ─── Platform detection ──────────────────────────────────────────────────────
if [[ -d /data/.openclaw ]]; then
  OC_ROOT="/data/.openclaw"
elif [[ -d "$HOME/.openclaw" ]]; then
  OC_ROOT="$HOME/.openclaw"
else
  echo "[materialize-dept-agents] FATAL: no OpenClaw root found at /data/.openclaw or \$HOME/.openclaw" >&2
  exit 1
fi

CONFIG_FILE="$OC_ROOT/openclaw.json"
BACKUP_DIR="$OC_ROOT/backups"

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
fi

if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "[materialize-dept-agents] FATAL: openclaw.json not found at $CONFIG_FILE" >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "[materialize-dept-agents] FATAL: python3 not on PATH — required for JSON mutation" >&2
  exit 1
fi

# ─── PRE-INTERVIEW REFUSAL (FIX H — defense in depth; report-don't-build) ─────
# Independently refuse to scaffold department agents before the AI Workforce
# interview is complete, so a NULL-model / default-floor company can never
# materialize pre-interview. Defense-in-depth alongside the Skill-32
# run-full-install precondition and the build-workforce.py exit-87 genuine-signal
# fail-close. --dry-run is exempt (it is read-only and makes no mutation). We only
# refuse when a state file is present AND shows interviewComplete != true (no state
# file => proceed; the other layers cover that path). Exit 0 CLEAN, never a crash.
if [[ $DRY_RUN -eq 0 ]]; then
  _STATE_FILE="$OC_ROOT/workspace/.workforce-build-state.json"
  if [[ -f "$_STATE_FILE" ]]; then
    _ic="$(python3 -c "import json; print('true' if json.load(open('$_STATE_FILE')).get('interviewComplete') is True else 'false')" 2>/dev/null || echo "unknown")"
    if [[ "$_ic" != "true" ]]; then
      echo "[materialize-dept-agents] Interview not completed yet (interviewComplete=$_ic) — REFUSING to materialize dept agents. No mutation made. Complete the AI Workforce interview first, then re-run. Exiting 0 (clean, not a failure)."
      exit 0
    fi
  fi
fi

# ─── Backup the config first (mirror Skill 32 INSTALL.md Phase 4.1) ──────────
if [[ $DRY_RUN -eq 0 ]]; then
  mkdir -p "$BACKUP_DIR"
  BACKUP_FILE="$BACKUP_DIR/openclaw-backup-$(date -u +%Y%m%dT%H%M%SZ)-pre-materialize.json"
  cp "$CONFIG_FILE" "$BACKUP_FILE"
  echo "[materialize-dept-agents] backed up config → $BACKUP_FILE"
fi

# ─── Discover dept folders ───────────────────────────────────────────────────
# Priority order (highest last, so later discoveries win in discovered{}):
#
#   1. $OC_ROOT/workspace/departments/<dept-slug>/
#      Legacy Skill 23 path (pre-v9.6.0). Still used by some installs.
#
#   2. $OC_ROOT/workspaces/command-center/<dept-slug>/
#      Skill 32 alt path (per INSTALL.md Phase 3). Takes priority over (1)
#      when both contain the same slug.
#
#   3. <openclaw-master-files>/zero-human-company/<company>/departments/<dept-slug>/
#      Canonical Skill 23 output path (v9.6.0+, PRD 1.9). build-workforce.py
#      (resolve_company_paths) writes ALL new departments here, NOT into
#      $OC_ROOT. Glob-expanded for every company slug found on disk.
#      Mac: ~/Downloads/openclaw-master-files/zero-human-company/
#      VPS: /data/openclaw-master-files/zero-human-company/
#
# PATH-MISMATCH FIX (v14.22.3): the previous version only scanned roots (1)
# and (2), which live under $OC_ROOT. build-workforce.py writes to root (3),
# a completely separate tree. This caused materialize-dept-agents.sh to find
# ZERO department folders and register ZERO agents even after a successful
# build — every client onboarded under v9.6.0–v14.22.2 was silently broken.
DEPT_SCAN_ROOTS=(
  "$OC_ROOT/workspace/departments"
  "$OC_ROOT/workspaces/command-center"
)

# Expand the canonical master-files ZHC tree (root 3). We iterate every
# company directory and push its departments/ subdir into DEPT_SCAN_ROOTS
# so the Python scanner sees it as a direct list of dept-slug children.
for _mf_root in \
    "$HOME/Downloads/openclaw-master-files/zero-human-company" \
    "/data/openclaw-master-files/zero-human-company"; do
  [[ -d "$_mf_root" ]] || continue
  for _company_dir in "$_mf_root"/*/; do
    [[ -d "$_company_dir" ]] || continue
    _dept_d="${_company_dir%/}/departments"
    if [[ -d "$_dept_d" ]]; then
      DEPT_SCAN_ROOTS+=("$_dept_d")
      echo "[materialize-dept-agents] including ZHC dept path: $_dept_d"
    fi
  done
done

# ─── Run the mutation in Python (no bash JSON acrobatics) ────────────────────
export OC_CONFIG_FILE="$CONFIG_FILE"
export OC_ROOT_PATH="$OC_ROOT"
export OC_DRY_RUN="$DRY_RUN"
export OC_DEPT_ROOTS="${DEPT_SCAN_ROOTS[*]}"

python3 <<'PYEOF'
import json
import os
import sys
import tempfile
from pathlib import Path

CONFIG_FILE = os.environ["OC_CONFIG_FILE"]
OC_ROOT = os.environ["OC_ROOT_PATH"]
DRY_RUN = os.environ.get("OC_DRY_RUN", "0") == "1"
DEPT_ROOTS = os.environ["OC_DEPT_ROOTS"].split()

# Pretty-name map: dept slug → friendly C-suite-style role title.
# For any slug not listed, we titlecase the slug ('-' → ' ').
PRETTY_NAMES = {
    "marketing":            "Chief Marketing Officer",
    "sales":                "Chief Revenue Officer",
    "billing-finance":      "Chief Financial Officer",
    "customer-support":     "Director of Customer Success",
    "web-development":      "Head of Web Development",
    "app-development":      "Head of App Development",
    "graphics":             "Creative Director — Graphics",
    "video":                "Creative Director — Video",
    "audio":                "Creative Director — Audio",
    "research":             "Director of Research",
    "communications":       "Director of Communications",
    "crm":                  "Head of CRM",
    "openclaw-maintenance": "OpenClaw Maintenance Lead",
    "legal-compliance":     "General Counsel",
    "social-media":         "Head of Social Media",
    "paid-advertisement":   "Head of Paid Advertising",
    "master-orchestrator":  "Master Orchestrator (CEO Agent)",
    "engineering":          "Head of Software Development / Engineering",
}

# Slugs we deliberately skip — these aren't agent-worthy folders.
SKIP_SLUGS = {
    ".git", ".cache", ".workforce-build-state.json",
    "templates", "shared", "_archive", "node_modules",
}

def pretty_name(slug: str) -> str:
    if slug in PRETTY_NAMES:
        return PRETTY_NAMES[slug]
    # Default: title-case the slug (e.g. "vertical-pack" → "Vertical Pack")
    return slug.replace("-", " ").title()

def is_valid_dept_dir(p: Path) -> bool:
    if not p.is_dir():
        return False
    name = p.name
    if name.startswith(".") or name.startswith("_"):
        return False
    if name in SKIP_SLUGS:
        return False
    return True

# ─── Discover dept slugs (dedup, alt path wins) ─────────────────────────────
discovered = {}  # slug → absolute workspace path
for root in DEPT_ROOTS:
    rp = Path(root)
    if not rp.is_dir():
        continue
    for child in sorted(rp.iterdir()):
        if not is_valid_dept_dir(child):
            continue
        # Skill 32 path wins over Skill 23 path if both have same slug —
        # because we iterate DEPT_ROOTS in priority order (cc first).
        discovered.setdefault(child.name, str(child.resolve()))

if not discovered:
    print(f"[materialize-dept-agents] WARN: no department folders found under {DEPT_ROOTS} — nothing to materialize")
    print("added 0 agents, updated 0 agents, total in agents.list: <unchanged>")
    sys.exit(0)

# ─── Load openclaw.json ─────────────────────────────────────────────────────
try:
    with open(CONFIG_FILE, "r") as f:
        cfg = json.load(f)
except json.JSONDecodeError as e:
    print(f"[materialize-dept-agents] FATAL: openclaw.json is malformed JSON: {e}", file=sys.stderr)
    sys.exit(1)

if "agents" not in cfg or not isinstance(cfg["agents"], dict):
    cfg["agents"] = {"list": []}
if "list" not in cfg["agents"] or not isinstance(cfg["agents"]["list"], list):
    cfg["agents"]["list"] = []

agent_list = cfg["agents"]["list"]
by_id = {a.get("id"): a for a in agent_list if isinstance(a, dict) and a.get("id")}

added = 0
updated = 0

for slug, workspace_path in discovered.items():
    agent_id = f"dept-{slug}"
    name = pretty_name(slug)
    # FIX (v12.9.12): derive agentDir from OC_ROOT/agents/<agent-id> so the
    # routing agent can resolve this dept agent at runtime. Without agentDir
    # the gateway cannot locate the agent's state directory and the routing
    # handoff silently fails.
    agent_dir = os.path.join(OC_ROOT, "agents", agent_id)

    # BUG FIX (v12.9.4): multimodal.enabled MUST be false when the configured
    # embedding provider is text-only (openai-compatible / text-embedding-3-small).
    # Enabling it caused memory-core to throw "memorySearch.multimodal requires a
    # provider adapter that supports multimodal embeddings" on EVERY message, and
    # fallback:"none" silently dropped all memory access.  Safe defaults: multimodal
    # disabled, fallback "openai" (matches the text embedding provider).
    desired_entry = {
        "id": agent_id,
        "name": name,
        "workspace": workspace_path,
        "agentDir": agent_dir,
        "memorySearch": {
            "extraPaths": [],
            "multimodal": {"enabled": False, "modalities": []},
            "fallback": "openai",
        },
        # NOTE: "wiki" is NOT a valid agents.list[] key in the strict OpenClaw
        # config schema (agents.list entries are z.core.$strict).  It was here
        # previously and caused "Unrecognized key: wiki" on every dept agent,
        # breaking openclaw gateway status / openclaw agents list.  Removed.
        # Per-agent doc/wiki-search capability is expressed via memorySearch.
    }

    existing = by_id.get(agent_id)
    if existing is None:
        agent_list.append(desired_entry)
        by_id[agent_id] = desired_entry
        # Ensure agentDir exists on disk so the gateway can resolve it at startup.
        os.makedirs(agent_dir, exist_ok=True)
        added += 1
        print(f"  + added   {agent_id:40s} → {workspace_path}")
    else:
        # Preserve any operator-curated fields on the existing entry that we
        # don't override (e.g. custom memorySearch.extraPaths, telegram bot
        # binding). Only update fields where we're authoritative.
        changed = False
        if existing.get("name") != name:
            existing["name"] = name
            changed = True
        if existing.get("workspace") != workspace_path:
            existing["workspace"] = workspace_path
            changed = True
        # Ensure memorySearch block exists (don't overwrite curated extras).
        # NOTE: "wiki" backfill deliberately removed -- "wiki" is not a valid
        # agents.list[] key in the strict OpenClaw schema and causes
        # "Unrecognized key: wiki" / Invalid input on every dept agent.
        # Also strip any stale "wiki" key left by earlier runs so existing
        # boxes become schema-valid after the next materialize run.
        existing.setdefault("memorySearch", desired_entry["memorySearch"])
        # IDEMPOTENT MIGRATION (v12.9.4): force multimodal.enabled=false on any
        # existing agent where it was previously set to true -- that was the broken
        # default that caused fleet-wide memory failures.  Re-running materialize
        # corrects all existing boxes without a separate migration step.
        existing_mm = existing.get("memorySearch", {}).get("multimodal", {})
        if existing_mm.get("enabled") is True:
            existing["memorySearch"]["multimodal"] = {"enabled": False, "modalities": []}
            changed = True
        elif "multimodal" not in existing.get("memorySearch", {}):
            existing["memorySearch"]["multimodal"] = desired_entry["memorySearch"]["multimodal"]
            changed = True
        # IDEMPOTENT MIGRATION (v12.9.4): force fallback to "openai" if currently
        # "none" or absent -- "none" silently drops all memory access on search errors.
        existing_fb = existing.get("memorySearch", {}).get("fallback")
        if existing_fb in (None, "none"):
            existing["memorySearch"]["fallback"] = "openai"
            changed = True
        if "extraPaths" not in existing.get("memorySearch", {}):
            existing["memorySearch"]["extraPaths"] = []
            changed = True
        if "wiki" in existing:
            del existing["wiki"]
            changed = True
        # IDEMPOTENT MIGRATION (v12.9.12): back-fill agentDir on entries written
        # before this version so existing boxes self-heal on the next materialize run.
        if not existing.get("agentDir"):
            existing["agentDir"] = agent_dir
            os.makedirs(agent_dir, exist_ok=True)
            changed = True
        if changed:
            updated += 1
            print(f"  ~ updated {agent_id:40s} → {workspace_path}")
        else:
            print(f"  = no-op   {agent_id:40s} (already in sync)")

total = len(agent_list)

if DRY_RUN:
    print(f"[materialize-dept-agents] DRY RUN — no write performed")
    print(f"added {added} agents, updated {updated} agents, total in agents.list: {total}")
    sys.exit(0)

# ─── Atomic write (tmp + rename) ────────────────────────────────────────────
try:
    cfg_dir = os.path.dirname(CONFIG_FILE)
    fd, tmp_path = tempfile.mkstemp(prefix=".openclaw.", suffix=".json.tmp", dir=cfg_dir)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(cfg, f, indent=2)
            f.write("\n")
        os.replace(tmp_path, CONFIG_FILE)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise
except Exception as e:
    print(f"[materialize-dept-agents] FATAL: atomic write failed: {e}", file=sys.stderr)
    sys.exit(1)

print(f"added {added} agents, updated {updated} agents, total in agents.list: {total}")

# ─── Emit a machine-readable manifest of discovered agents so the bash
#     wrapper can call scaffold-agent-files.sh for each one. ────────────────
manifest_path = os.path.join(os.path.dirname(CONFIG_FILE), ".materialize-dept-agents.manifest")
try:
    with open(manifest_path, "w") as f:
        for slug, workspace_path in discovered.items():
            agent_id = f"dept-{slug}"
            name = pretty_name(slug)
            # Tab-separated: agent_id<TAB>name<TAB>workspace_path<TAB>dept_slug
            f.write(f"{agent_id}\t{name}\t{workspace_path}\t{slug}\n")
    print(f"[materialize-dept-agents] wrote scaffolder manifest → {manifest_path}")
except OSError as e:
    print(f"[materialize-dept-agents] WARN: could not write scaffolder manifest: {e}", file=sys.stderr)
PYEOF

RC=$?
if [[ $RC -ne 0 ]]; then
  echo "[materialize-dept-agents] FATAL: python mutation failed (rc=$RC)" >&2
  exit $RC
fi

# ─── Phase 2: scaffold per-agent IDENTITY/SOUL/MEMORY/HEARTBEAT + symlinks ───
# Trevor's agent-file architecture (v10.14.29):
#   - SHARED across all agents: USER.md, AGENTS.md, TOOLS.md (one copy at
#     $OC_ROOT/workspace/, each dept-head agent symlinks to them)
#   - PER-AGENT (each agent has its own): IDENTITY.md, SOUL.md, MEMORY.md,
#     HEARTBEAT.md (in the agent's workspace folder)
#   - Sub-agents (role folders inside a dept) are EXCLUDED — they have their
#     own scaffolder in 23-ai-workforce-blueprint/scripts/post-build-role-workspaces.py
#
# This script delegates the actual file writes to scaffold-agent-files.sh so
# the same code-path also runs from add-department.sh and from inside
# build-workforce.py.
SCAFFOLDER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/scaffold-agent-files.sh"
MANIFEST="$OC_ROOT/.materialize-dept-agents.manifest"

if [[ $DRY_RUN -eq 0 && -f "$MANIFEST" && -x "$SCAFFOLDER" ]]; then
  echo "[materialize-dept-agents] scaffolding per-agent files for each dept…"
  scaffold_ok=0
  scaffold_fail=0
  while IFS=$'\t' read -r agent_id agent_name workspace_path dept_slug; do
    [[ -z "$agent_id" ]] && continue
    # Strip "dept-" prefix from agent_id to get the slug for --agent-slug
    agent_slug="${agent_id#dept-}"
    if bash "$SCAFFOLDER" \
        --agent-slug "$agent_slug" \
        --agent-name "$agent_name" \
        --department "$dept_slug" \
        --workspace-dir "$workspace_path" \
        --shared-root "$OC_ROOT/workspace" >/dev/null 2>&1; then
      scaffold_ok=$((scaffold_ok+1))
    else
      scaffold_fail=$((scaffold_fail+1))
      echo "  ! scaffold-agent-files failed for $agent_id (continuing)" >&2
    fi
  done < "$MANIFEST"
  echo "[materialize-dept-agents] scaffolded $scaffold_ok agents ($scaffold_fail failures)"
  rm -f "$MANIFEST"
elif [[ ! -x "$SCAFFOLDER" ]]; then
  echo "[materialize-dept-agents] WARN: scaffold-agent-files.sh not executable at $SCAFFOLDER -- skipping per-agent file scaffolding" >&2
fi

# ---- Phase 3: trio/quad DB-row pass (idempotent, skip on dry-run) -----------
# Inserts QC / Deep-Research / Devil's Advocate / Healer rows for each dept
# that is missing them. Delegates to lib-trio-quad-rows.py for the same logic
# that add-department.sh uses (single source of truth).
# Safe to re-run: every insert is WHERE NOT EXISTS for that workspace+role_type.
# If no mission-control.db is found, logs a WARN and continues (some boxes
# legitimately have no CC DB yet during the initial install pass).
if [[ $DRY_RUN -eq 0 ]]; then
  SCRIPTS_DIR_PHASE3="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  export OC_SCRIPTS_DIR="$SCRIPTS_DIR_PHASE3"
  python3 <<'PHASE3EOF'
import os, sys, sqlite3, json
from pathlib import Path

OC_ROOT = os.environ.get("OC_ROOT_PATH", "")
SCRIPTS_DIR = os.environ.get("OC_SCRIPTS_DIR", "")
DRY_RUN = os.environ.get("OC_DRY_RUN", "0") == "1"

# Import lib-trio-quad-rows
try:
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "lib_trio_quad_rows",
        os.path.join(SCRIPTS_DIR, "lib-trio-quad-rows.py")
    )
    lib = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lib)
    ensure_trio_quad_rows = lib.ensure_trio_quad_rows
except Exception as e:
    print(f"[materialize] WARN: could not load lib-trio-quad-rows.py: {e}", file=sys.stderr)
    sys.exit(0)

# Resolve mission-control.db (mirror add-department.sh candidate list)
db_candidates = [
    os.path.join(OC_ROOT, "workspaces", "command-center", "mission-control.db"),
    os.path.join(OC_ROOT, "workspace", "mission-control.db"),
    os.path.join(OC_ROOT, "data", "mission-control.db"),
]
db_path = None
for c in db_candidates:
    if os.path.isfile(c):
        db_path = c
        break

if not db_path:
    print("[materialize] WARN: mission-control.db not found - skipping trio/quad row pass")
    sys.exit(0)

# Read manifest written by Phase 1
manifest_path = os.path.join(OC_ROOT, ".materialize-dept-agents.manifest")
if not os.path.isfile(manifest_path):
    # Manifest was already consumed by Phase 2 scaffolder -- try workspaces table
    try:
        db = sqlite3.connect(db_path)
        cur = db.execute(
            "SELECT id, name, slug FROM workspaces WHERE type != 'main' AND type != 'system'"
        )
        rows = cur.fetchall()
        db.close()
        entries = [(ws_id, name, slug or name.lower().replace(" ", "-")) for ws_id, name, slug in rows]
    except Exception as e:
        print(f"[materialize] WARN: could not read workspaces table: {e}", file=sys.stderr)
        sys.exit(0)
else:
    entries = []
    with open(manifest_path) as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 4:
                # agent_id, name, workspace_path, dept_slug
                entries.append((None, parts[1], parts[3]))

db = sqlite3.connect(db_path)
total_healer = 0
total_qc = 0
total_research = 0
total_da = 0

for ws_id_or_none, dept_name, dept_slug in entries:
    if not dept_name:
        continue
    # Resolve ws_id if not directly available
    if not ws_id_or_none:
        cur = db.execute(
            "SELECT id FROM workspaces WHERE slug=? LIMIT 1", (dept_slug,)
        )
        row = cur.fetchone()
        if not row:
            print(f"  [materialize] SKIP {dept_slug}: no workspace row found")
            continue
        ws_id = row[0]
    else:
        ws_id = ws_id_or_none

    try:
        counts = ensure_trio_quad_rows(db, ws_id, dept_name, dept_slug, "")
        total_healer += counts.get("healer", 0)
        total_qc += counts.get("qc", 0)
        total_research += counts.get("deep-research", 0)
        total_da += counts.get("devils-advocate", 0)
    except Exception as e:
        print(f"  [materialize] WARN: trio/quad insert failed for {dept_slug}: {e}", file=sys.stderr)

db.commit()
db.close()

print(
    f"[materialize] trio/quad rows:"
    f" +{total_healer} healer,"
    f" +{total_qc} qc,"
    f" +{total_research} research,"
    f" +{total_da} da"
    f" (idempotent)"
)
PHASE3EOF
fi

# ---- Phase 4: role-file materialization (write healer-<dept>.md if missing) -
# Ensures the per-dept Healer role FILE exists in the box's installed role library.
# Source: <skills>/23-ai-workforce-blueprint/templates/role-library/healer/dept-healer-template.md
# Target: <role-library>/<dept>/healer-<dept>.md
# Write only if missing; fills {{DEPARTMENT_NAME}} with the pretty dept name.
# Other {{TOKENS}} are filled by the WS-2 instantiation path.
if [[ $DRY_RUN -eq 0 ]]; then
  python3 <<'PHASE4EOF'
import os, sys

OC_ROOT = os.environ.get("OC_ROOT_PATH", "")
SCRIPTS_DIR = os.environ.get("OC_SCRIPTS_DIR", "")

# Find skills dir
SKILLS_CANDIDATES = [
    os.path.join(OC_ROOT, "workspace", ".openclaw-skills"),
    os.path.join(OC_ROOT, ".openclaw-skills"),
    os.path.join(os.path.expanduser("~"), ".openclaw", "workspace", ".openclaw-skills"),
    "/data/skills",
    os.path.join(os.path.expanduser("~"), "skills"),
]
skills_dir = ""
for c in SKILLS_CANDIDATES:
    if os.path.isdir(c):
        skills_dir = c
        break

if not skills_dir:
    print("[materialize] Phase 4: skills dir not found -- skipping role-file materialization")
    sys.exit(0)

healer_template = os.path.join(
    skills_dir,
    "23-ai-workforce-blueprint",
    "templates",
    "role-library",
    "healer",
    "dept-healer-template.md",
)
if not os.path.isfile(healer_template):
    print(f"[materialize] Phase 4: healer template not found at {healer_template} -- skipping")
    sys.exit(0)

role_lib = os.path.join(
    skills_dir,
    "23-ai-workforce-blueprint",
    "templates",
    "role-library",
)

written = 0
skipped = 0

if not os.path.isdir(role_lib):
    print(f"[materialize] Phase 4: role-library not found at {role_lib} -- skipping")
    sys.exit(0)

with open(healer_template) as f:
    template_content = f.read()

for dept_slug in sorted(os.listdir(role_lib)):
    dept_dir = os.path.join(role_lib, dept_slug)
    if not os.path.isdir(dept_dir) or dept_slug.startswith("_") or dept_slug == "healer":
        continue
    target = os.path.join(dept_dir, f"healer-{dept_slug}.md")
    if os.path.isfile(target):
        skipped += 1
        continue
    dept_name = dept_slug.replace("-", " ").title()
    content = template_content.replace("{{DEPARTMENT_NAME}}", dept_name)
    try:
        with open(target, "w") as f:
            f.write(content)
        written += 1
    except Exception as e:
        print(f"  [materialize] WARN: could not write {target}: {e}", file=sys.stderr)

print(f"[materialize] Phase 4: role files written={written} already_present={skipped}")
PHASE4EOF
fi

exit 0
