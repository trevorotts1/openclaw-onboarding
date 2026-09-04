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
#   - Scans the canonical master-files ZHC departments/ tree, workspaces/command-center/,
#     and legacy workspace/departments/ for dept folders — canonical wins on slug collision
#     (see the "ONE TRUE RULE" comment above DEPT_SCAN_ROOTS for the full priority order)
#   - For each dept, adds (or updates) an entry in openclaw.json's CANONICAL
#     agents.entries{} roster (keyed by agent id), falling back to the legacy
#     agents.list[] array ONLY on a genuinely pre-migration config that already
#     carries it. It NEVER creates agents.list on a config that lacks it: the
#     modern schema is strict and that one key invalidates the whole config
#     ("agents: Unrecognized key: \"list\"").
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

# ─── Root guard (config writes as the node user, NEVER root) ─────────────────
# This script mutates openclaw.json (agents.list[]). Root writes to that file
# freeze the gateway / leave a root-owned config the node user can no longer
# write (EACCES on client boxes thereafter). Mirrors add-department.sh:87-90 and
# check_root_guard() in 59-anthology-engine/scripts/provision-anthology-client.sh.
if [[ "$(id -u)" == "0" ]]; then
  echo "[materialize-dept-agents] FATAL: refusing to run as root -- config writes must be the node user (root writes freeze the gateway / EACCES on client boxes). Re-run as the node user, e.g. sudo -u node bash materialize-dept-agents.sh ..." >&2
  exit 1
fi

# ─── Platform detection — via the shared resolver (false-negative #3 fix) ─────
# Centralized /data-else-HOME .openclaw detection; identical inline fallback if
# the shared file is absent. See shared-utils/resolve-oc-root.sh.
_OC_ROOT_RESOLVER="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)/../../shared-utils/resolve-oc-root.sh"
# shellcheck source=/dev/null
[[ -f "$_OC_ROOT_RESOLVER" ]] && source "$_OC_ROOT_RESOLVER"
if declare -F resolve_oc_root >/dev/null 2>&1; then
  if _oc_root_resolved="$(resolve_oc_root)"; then
    OC_ROOT="$_oc_root_resolved"
  else
    echo "[materialize-dept-agents] FATAL: no OpenClaw root found at /data/.openclaw or \$HOME/.openclaw" >&2
    exit 1
  fi
elif [[ -d /data/.openclaw ]]; then
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

# ─── INTERVIEW-COMPLETE PRECONDITION (binding) ────────────────────────────────
# Do NOT materialize department agents into agents.list[] before the owner's AI
# Workforce interview is COMPLETE. Materializing a default/empty department floor
# pre-interview is exactly the "rogue/default board" failure. REPORT and exit 0
# (not an error) so callers/crons see "interview not completed yet", not a crash.
# --dry-run is exempt (it mutates nothing and is used for inspection).
_MATERIALIZE_STATE_FILE="$OC_ROOT/workspace/.workforce-build-state.json"
if [[ $DRY_RUN -eq 0 ]]; then
  if [[ ! -f "$_MATERIALIZE_STATE_FILE" ]] || \
     [[ "$(python3 -c "import json,sys; sys.stdout.write('true' if json.load(open('$_MATERIALIZE_STATE_FILE')).get('interviewComplete') is True else 'false')" 2>/dev/null || echo false)" != "true" ]]; then
    echo "[materialize-dept-agents] INTERVIEW_NOT_COMPLETE: AI Workforce interview not completed yet (interviewComplete != true in $_MATERIALIZE_STATE_FILE) — refusing to materialize department agents. No config mutation performed." >&2
    exit 0
  fi
fi

# ─── Resolve THIS box's own company slug (multi-company glob hazard fix) ─────
# Root 1 below (the canonical master-files ZHC tree) used to glob EVERY
# company subdirectory under zero-human-company/ — "for _company_dir in
# "$_mf_root"/*/" — with no scoping at all. On an operator/demo box that hosts
# more than one client's ZHC build side by side, that registered ALL of their
# departments into THIS box's single openclaw.json agents.list[], not just the
# box's own. Resolve the box's own company slug the SAME way
# run-full-install.sh / seed-workspaces.py / sync-departments-from-build-state.py
# already do — an explicit $COMPANY_SLUG override, else
# .workforce-build-state.json's companySlug (falling back to the legacy
# clientSlug alias) — and scope root 1 to ONLY that company's directory. When
# no slug can be resolved (older build-state, or a genuinely un-branded box),
# fall back to the old glob-all behavior with a loud warning so a real
# multi-company leak is at least visible in the log, not silent.
_MATERIALIZE_COMPANY_SLUG="${COMPANY_SLUG:-}"
if [[ -z "$_MATERIALIZE_COMPANY_SLUG" && -f "$_MATERIALIZE_STATE_FILE" ]]; then
  _MATERIALIZE_COMPANY_SLUG="$(python3 -c "
import json, sys
try:
    d = json.load(open('$_MATERIALIZE_STATE_FILE'))
except (OSError, json.JSONDecodeError):
    sys.exit(0)
slug = (d.get('companySlug') or d.get('clientSlug') or '').strip()
sys.stdout.write(slug)
" 2>/dev/null || true)"
fi
if [[ -n "$_MATERIALIZE_COMPANY_SLUG" ]]; then
  echo "[materialize-dept-agents] scoping the canonical ZHC dept scan to this box's own company: $_MATERIALIZE_COMPANY_SLUG"
else
  echo "[materialize-dept-agents] WARN: could not resolve this box's own company slug (no \$COMPANY_SLUG, no companySlug/clientSlug in $_MATERIALIZE_STATE_FILE) — falling back to scanning EVERY company directory under the canonical ZHC roots. On a box that hosts more than one client's build, this can register a FOREIGN client's departments into this box's agents.list[]. Set COMPANY_SLUG to fix." >&2
fi

# ─── Backup the config first (mirror Skill 32 INSTALL.md Phase 4.1) ──────────
if [[ $DRY_RUN -eq 0 ]]; then
  mkdir -p "$BACKUP_DIR"
  BACKUP_FILE="$BACKUP_DIR/openclaw-backup-$(date -u +%Y%m%dT%H%M%SZ)-pre-materialize.json"
  cp "$CONFIG_FILE" "$BACKUP_FILE"
  echo "[materialize-dept-agents] backed up config → $BACKUP_FILE"
fi

# ─── Discover dept folders ───────────────────────────────────────────────────
# ONE TRUE RULE: DEPT_SCAN_ROOTS is ordered MOST-AUTHORITATIVE FIRST. The
# Python scanner below dedups with discovered.setdefault(slug, path) — i.e.
# FIRST DISCOVERY WINS — so whichever root is listed first for a given slug
# is the one that "shadows" every later root that happens to produce the
# same slug. Keep this list ordered from most-authoritative (canonical build
# output) down to least (legacy/deprecated paths), or a stale legacy folder
# will silently shadow the real one.
#
#   1. <openclaw-master-files>/zero-human-company/<company>/departments/<dept-slug>/
#      Canonical Skill 23 output path (v9.6.0+, PRD 1.9) — MOST AUTHORITATIVE.
#      build-workforce.py (resolve_company_paths) writes ALL new departments
#      here, NOT into $OC_ROOT. Glob-expanded for every company slug found on
#      disk. Scanned FIRST so it wins any slug collision.
#      Mac: ~/Downloads/openclaw-master-files/zero-human-company/
#      VPS: /data/openclaw-master-files/zero-human-company/
#
#   2. $OC_ROOT/workspaces/command-center/<dept-slug>/
#      Skill 32 alt path (per INSTALL.md Phase 3). Wins over (3) when both
#      contain the same slug; loses to (1).
#
#   3. $OC_ROOT/workspace/departments/<dept-slug>/
#      Legacy Skill 23 path (pre-v9.6.0). Still present on some installs but
#      DEPRECATED — scanned LAST so it never shadows (1) or (2) for the same
#      slug.
#
# PATH-MISMATCH FIX (v14.22.3): an earlier version only scanned roots (2) and
# (3), which live under $OC_ROOT. build-workforce.py writes to root (1), a
# completely separate tree. This caused materialize-dept-agents.sh to find
# ZERO department folders and register ZERO agents even after a successful
# build — every client onboarded under v9.6.0–v14.22.2 was silently broken.
#
# DEDUP-PRIORITY FIX (P2-4): an earlier version scanned the legacy root (3)
# FIRST and the canonical root (1) LAST while using first-wins setdefault()
# semantics in the Python scanner. That meant a stale leftover folder under
# the legacy path could silently shadow the current, correct build output
# for the same slug — exactly backwards from the intent. Roots are now
# built most-authoritative-first so first-wins setdefault() actually picks
# the canonical copy.
DEPT_SCAN_ROOTS=()

# Expand the canonical master-files ZHC tree (root 1) FIRST — it is the most
# authoritative source and must win any slug collision under setdefault().
# Scoped to THIS BOX'S OWN company (_MATERIALIZE_COMPANY_SLUG, resolved
# above) when known — pushing only that company's departments/ subdir into
# DEPT_SCAN_ROOTS. Falls back to iterating every company directory ONLY when
# the box's own slug could not be resolved (already warned above).
for _mf_root in \
    "$HOME/Downloads/openclaw-master-files/zero-human-company" \
    "/data/openclaw-master-files/zero-human-company"; do
  [[ -d "$_mf_root" ]] || continue
  if [[ -n "$_MATERIALIZE_COMPANY_SLUG" ]]; then
    _dept_d="$_mf_root/$_MATERIALIZE_COMPANY_SLUG/departments"
    if [[ -d "$_dept_d" ]]; then
      DEPT_SCAN_ROOTS+=("$_dept_d")
      echo "[materialize-dept-agents] including ZHC dept path: $_dept_d"
    fi
    continue
  fi
  for _company_dir in "$_mf_root"/*/; do
    [[ -d "$_company_dir" ]] || continue
    _dept_d="${_company_dir%/}/departments"
    if [[ -d "$_dept_d" ]]; then
      DEPT_SCAN_ROOTS+=("$_dept_d")
      echo "[materialize-dept-agents] including ZHC dept path: $_dept_d"
    fi
  done
done

# Then the Skill 32 alt path (root 2), then the legacy Skill 23 path (root 3)
# LAST — least authoritative, scanned last so it can never shadow (1) or (2).
DEPT_SCAN_ROOTS+=(
  "$OC_ROOT/workspaces/command-center"
  "$OC_ROOT/workspace/departments"
)

# ─── Run the mutation in Python (no bash JSON acrobatics) ────────────────────
export OC_CONFIG_FILE="$CONFIG_FILE"
export OC_ROOT_PATH="$OC_ROOT"
export OC_DRY_RUN="$DRY_RUN"
export OC_DEPT_ROOTS="${DEPT_SCAN_ROOTS[*]}"

python3 <<'PYEOF'
import json
import os
import re
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

# ─── Discover dept slugs (dedup, most-authoritative root wins) ─────────────
# ONE TRUE RULE: DEPT_ROOTS (built in bash above) is ordered
# most-authoritative first. setdefault() below is FIRST-WINS, so for any
# slug that shows up under more than one root, whichever root we reach
# first — canonical master-files ZHC build output, then the command-center
# workspace root, then the legacy workspace/departments root last — is the
# one that sticks. Do not reorder DEPT_ROOTS without keeping this rule true.
discovered = {}  # slug → absolute workspace path
for root in DEPT_ROOTS:
    rp = Path(root)
    if not rp.is_dir():
        continue
    for child in sorted(rp.iterdir()):
        if not is_valid_dept_dir(child):
            continue
        discovered.setdefault(child.name, str(child.resolve()))

if not discovered:
    print(f"[materialize-dept-agents] WARN: no department folders found under {DEPT_ROOTS} — nothing to materialize")
    print("added 0 agents, updated 0 agents, total in roster: <unchanged>")
    sys.exit(0)

# ─── Load openclaw.json ─────────────────────────────────────────────────────
try:
    with open(CONFIG_FILE, "r") as f:
        cfg = json.load(f)
except json.JSONDecodeError as e:
    print(f"[materialize-dept-agents] FATAL: openclaw.json is malformed JSON: {e}", file=sys.stderr)
    sys.exit(1)

# ─── Resolve the roster shape: agents.entries (canonical) vs agents.list ────
# THE BUG THIS FIXES (2026-09-04): this block used to create
# cfg["agents"]["list"] UNCONDITIONALLY. A schema-valid modern OpenClaw config
# CANNOT CONTAIN agents.list -- AgentsSchema is .strict() with exactly
# {ownership, defaults, entries} -- so that single key invalidates the whole
# config:
#     x openclaw.json:2 - agents: Unrecognized key: "list"
# On a migrated box (agents.entries) every routine `update-skills.sh` run
# therefore INVALIDATED the client's config: the gateway could no longer reload,
# and the remedy the validator prints (`openclaw doctor --fix`) has been
# observed on this fleet to restore an older last-known-good and silently DROP
# departments. Reproduced end-to-end on 2026-09-04: a modern fixture validated
# rc=0 before this script and rc=1 (`Unrecognized key: "list"`) after it.
#
# The rules below were each verified against openclaw 2026.9.1's own zod schema
# (dist/zod-schema-*.js) AND with `openclaw config validate` on fixtures:
#   * entries WINS when both shapes are present -- the same precedence the
#     gateway applies at boot ("Removed agents.list because canonical
#     agents.entries is already set").
#   * legacy agents.list is written ONLY when the config ALREADY carries it and
#     has NO entries. We NEVER create agents.list on a config that lacks it.
#   * in entries mode the agent id is the KEY. An "id" key INSIDE an entry is
#     rejected -- AgentEntryConfigSchema is AgentEntrySchema.omit({id}).strict():
#       x agents.entries.main: Unrecognized key: "id"
#   * in entries mode the memory-search block lives at entry.memory.search.
#     A top-level "memorySearch" key is rejected the same way:
#       x agents.entries.main: Unrecognized key: "memorySearch"
#   * entries KEYS must match ^[a-z0-9_][a-z0-9_-]{0,63}$ (case-INSENSITIVE),
#     and any two keys that normalize to the same agent id are a hard schema
#     error ("resolve to the same agent id ...; rename one key"). This is not
#     theoretical: the fleet's Presentations department folder is capitalized
#     ("departments/Presentations") while its migrated entries key is lowercase
#     ("dept-presentations"), so a naive f"dept-{slug}" key would collide.
ENTRIES_KEY_RE = re.compile(r"^[a-z0-9_][a-z0-9_-]{0,63}$", re.IGNORECASE)
_RUNTIME_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$", re.IGNORECASE)
_INVALID_ID_CHARS_RE = re.compile(r"[^a-z0-9_-]+")


def normalize_agent_id(value: str) -> str:
    """Mirror of OpenClaw's normalizeAgentIdStrict()
    (packages/normalization-core/src/agent-id.ts): trim, lowercase, replace runs
    of invalid characters with '-', strip leading/trailing '-', cap at 64 chars.
    Returns "" when the id is unrepresentable. Writing THIS as the entries key
    means the key we write is exactly the id the gateway resolves at runtime.
    """
    trimmed = (value or "").strip()
    lowered = trimmed.lower()
    if _RUNTIME_ID_RE.match(trimmed):
        return lowered
    return _INVALID_ID_CHARS_RE.sub("-", lowered).lstrip("-").rstrip("-")[:64]


agents_cfg = cfg.get("agents")
if not isinstance(agents_cfg, dict):
    agents_cfg = {}
    cfg["agents"] = agents_cfg

_cfg_entries = agents_cfg.get("entries")
_cfg_list = agents_cfg.get("list")

if isinstance(_cfg_entries, dict) and _cfg_entries:
    ROSTER_MODE = "entries"
elif isinstance(_cfg_list, list):
    ROSTER_MODE = "list"
else:
    # Neither shape present (or entries is an empty dict, which is itself
    # schema-invalid: "agents.entries must contain at least one configured
    # agent"). Modern is the default -- we never invent agents.list.
    ROSTER_MODE = "entries"

if ROSTER_MODE == "entries":
    if not isinstance(agents_cfg.get("entries"), dict):
        agents_cfg["entries"] = {}
    roster = agents_cfg["entries"]  # LIVE dict inside cfg -- never a copy
    ROSTER_LABEL = "agents.entries"
    if isinstance(_cfg_list, list):
        print(
            "[materialize-dept-agents] WARN: this config carries BOTH agents.entries "
            f"({len(roster)} entries) and a legacy agents.list ({len(_cfg_list)} items). "
            "Registering into agents.entries (the canonical roster the gateway keeps). "
            "The stale agents.list is left EXACTLY as found -- this script never deletes "
            "a key it did not create -- but that key makes the config fail "
            '`openclaw config validate` (agents: Unrecognized key: "list"). '
            "Clear it with the atomic migration: update-skills.sh --agents-list-migrate",
            file=sys.stderr,
        )
else:
    roster = agents_cfg["list"]  # LIVE list inside cfg -- never a copy
    ROSTER_LABEL = "agents.list"
    print(
        "[materialize-dept-agents] legacy pre-migration config detected "
        "(agents.list present, no agents.entries) -- registering into agents.list[] "
        "and NOT creating agents.entries."
    )

# by_id maps ROSTER KEY -> the LIVE entry dict inside cfg (mutating one of these
# mutates cfg, which is what gets written back). key_by_norm lets a
# differently-cased existing key be UPDATED instead of colliding with a new one.
if ROSTER_MODE == "entries":
    by_id = {k: v for k, v in roster.items() if isinstance(v, dict)}
    key_by_norm = {}
    for _k in by_id:
        key_by_norm.setdefault(normalize_agent_id(_k), _k)
else:
    by_id = {a.get("id"): a for a in roster if isinstance(a, dict) and a.get("id")}
    key_by_norm = {}

claimed_norms = {}  # entries mode: normalized id -> dept slug that claimed it


def default_memory_search():
    """A fresh (never shared) default memory-search block."""
    return {
        "extraPaths": [],
        "multimodal": {"enabled": False, "modalities": []},
        "fallback": "openai",
    }


def memory_search_of(entry):
    """The entry's LIVE memory-search dict, or None. Never returns a copy --
    a copy here would make every migration below mutate a throwaway and still
    print success."""
    if ROSTER_MODE == "entries":
        mem = entry.get("memory")
        if isinstance(mem, dict) and isinstance(mem.get("search"), dict):
            return mem["search"]
        return None
    ms = entry.get("memorySearch")
    return ms if isinstance(ms, dict) else None


def install_memory_search(entry, block):
    """Attach a memory-search block where THIS roster shape expects it:
    entry.memory.search for agents.entries, entry.memorySearch for agents.list."""
    if ROSTER_MODE == "entries":
        mem = entry.get("memory")
        if not isinstance(mem, dict):
            mem = {}
            entry["memory"] = mem
        mem["search"] = block
    else:
        entry["memorySearch"] = block

added = 0
updated = 0

manifest_rows = []  # (roster_key, pretty name, workspace path, dept slug)

for slug, workspace_path in discovered.items():
    agent_id = f"dept-{slug}"
    name = pretty_name(slug)

    # ── Roster key ──────────────────────────────────────────────────────────
    # list mode: the id lives INSIDE the record, unchanged from before.
    # entries mode: the KEY is the id, and it must satisfy the schema pattern.
    #   * reuse an existing key that normalizes to the same agent id (e.g. an
    #     already-migrated lowercase "dept-presentations" for the capitalized
    #     "Presentations" folder) so we UPDATE it instead of adding a second key
    #     that the schema rejects as a duplicate agent id;
    #   * a slug that cannot be represented at all is FATAL, never a silent drop.
    if ROSTER_MODE == "entries":
        norm_id = normalize_agent_id(agent_id)
        if not norm_id or not ENTRIES_KEY_RE.match(norm_id):
            print(
                f"[materialize-dept-agents] FATAL: department folder '{slug}' yields agent id "
                f"'{agent_id}', which cannot be represented as an agents.entries key "
                f"(schema pattern ^[a-z0-9_][a-z0-9_-]{{0,63}}$). Rename the department folder "
                f"to a slug made of letters, digits, '_' and '-'. REFUSING to continue -- a "
                f"department is never silently dropped from the roster.",
                file=sys.stderr,
            )
            sys.exit(1)
        prior_slug = claimed_norms.get(norm_id)
        if prior_slug is not None and prior_slug != slug:
            print(
                f"[materialize-dept-agents] FATAL: department folders '{prior_slug}' and "
                f"'{slug}' both normalize to the agent id '{norm_id}'. OpenClaw rejects two "
                f"agents.entries keys that resolve to the same agent id. Rename one of the "
                f"department folders. REFUSING to continue -- a department is never silently "
                f"dropped from the roster.",
                file=sys.stderr,
            )
            sys.exit(1)
        claimed_norms[norm_id] = slug
        roster_key = key_by_norm.get(norm_id, norm_id)
    else:
        roster_key = agent_id
    # FIX (v12.9.12): derive agentDir from OC_ROOT/agents/<agent-id> so the
    # routing agent can resolve this dept agent at runtime. Without agentDir
    # the gateway cannot locate the agent's state directory and the routing
    # handoff silently fails.
    # It is keyed on roster_key, NOT on the raw f"dept-{slug}": in entries mode
    # those differ for a capitalized dept folder, and an agentDir naming a
    # different id than the roster key is incoherent on a case-sensitive
    # filesystem (the scaffolder, the manifest and agentDir must all follow the
    # one id the gateway actually resolves). In legacy list mode roster_key IS
    # agent_id, so this is a no-op there.
    agent_dir = os.path.join(OC_ROOT, "agents", roster_key)

    # BUG FIX (v12.9.4): multimodal.enabled MUST be false when the configured
    # embedding provider is text-only (openai-compatible / text-embedding-3-small).
    # Enabling it caused memory-core to throw "memorySearch.multimodal requires a
    # provider adapter that supports multimodal embeddings" on EVERY message, and
    # fallback:"none" silently dropped all memory access.  Safe defaults: multimodal
    # disabled, fallback "openai" (matches the text embedding provider).
    # NOTE: "wiki" is NOT a valid agent-entry key in the strict OpenClaw config
    # schema (both agents.list entries and agents.entries values are strict). It
    # was here previously and caused "Unrecognized key: wiki" on every dept
    # agent, breaking openclaw gateway status / openclaw agents list. Removed.
    # Per-agent doc/wiki-search capability is expressed via the memory-search
    # block instead.
    #
    # In entries mode the id is DELIBERATELY absent from the record: the key IS
    # the id, and an "id" key inside an entry fails validation with
    # `agents.entries.<id>: Unrecognized key: "id"`. The memory-search block
    # likewise moves to entry.memory.search, because a top-level "memorySearch"
    # key fails the same way.
    if ROSTER_MODE == "entries":
        desired_entry = {
            "name": name,
            "workspace": workspace_path,
            "agentDir": agent_dir,
            "memory": {"search": default_memory_search()},
        }
    else:
        desired_entry = {
            "id": agent_id,
            "name": name,
            "workspace": workspace_path,
            "agentDir": agent_dir,
            "memorySearch": default_memory_search(),
        }

    manifest_rows.append((roster_key, name, workspace_path, slug))

    existing = by_id.get(roster_key)
    if existing is None:
        if ROSTER_MODE == "entries":
            roster[roster_key] = desired_entry
            key_by_norm.setdefault(norm_id, roster_key)
        else:
            roster.append(desired_entry)
        by_id[roster_key] = desired_entry
        # Ensure agentDir exists on disk so the gateway can resolve it at startup.
        os.makedirs(agent_dir, exist_ok=True)
        added += 1
        print(f"  + added   {roster_key:40s} → {workspace_path}")
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
        # IDEMPOTENT MIGRATION (2026-09-04): in entries mode a top-level
        # "memorySearch" key is a HARD schema error
        # (`agents.entries.<id>: Unrecognized key: "memorySearch"`). Earlier
        # versions of THIS script wrote exactly that key, so move it to its
        # canonical home at entry.memory.search rather than leaving the entry
        # invalid. Existing memory.search fields win; nothing is discarded.
        if ROSTER_MODE == "entries" and isinstance(existing.get("memorySearch"), dict):
            legacy_ms = existing.pop("memorySearch")
            mem = existing.get("memory")
            if not isinstance(mem, dict):
                mem = {}
                existing["memory"] = mem
            if isinstance(mem.get("search"), dict):
                for _lk, _lv in legacy_ms.items():
                    mem["search"].setdefault(_lk, _lv)
            else:
                mem["search"] = legacy_ms
            changed = True
        # Ensure the memory-search block exists (don't overwrite curated extras).
        # NOTE: "wiki" backfill deliberately removed -- "wiki" is not a valid
        # agent-entry key in the strict OpenClaw schema and causes
        # "Unrecognized key: wiki" / Invalid input on every dept agent.
        # Also strip any stale "wiki" key left by earlier runs so existing
        # boxes become schema-valid after the next materialize run.
        #
        # memory_search_of() hands back the LIVE dict inside `existing` (which is
        # itself the LIVE record inside cfg), so every migration below mutates
        # the object that actually gets written. Returning copies here is the
        # classic silent no-op: the migrations "succeed", the file is rewritten
        # unchanged, and the run still reports success.
        existing_ms = memory_search_of(existing)
        if existing_ms is None:
            existing_ms = default_memory_search()
            install_memory_search(existing, existing_ms)
            changed = True
        # IDEMPOTENT MIGRATION (v12.9.4): force multimodal.enabled=false on any
        # existing agent where it was previously set to true -- that was the broken
        # default that caused fleet-wide memory failures.  Re-running materialize
        # corrects all existing boxes without a separate migration step.
        existing_mm = existing_ms.get("multimodal")
        if isinstance(existing_mm, dict) and existing_mm.get("enabled") is True:
            existing_ms["multimodal"] = {"enabled": False, "modalities": []}
            changed = True
        elif "multimodal" not in existing_ms:
            existing_ms["multimodal"] = {"enabled": False, "modalities": []}
            changed = True
        # IDEMPOTENT MIGRATION (v12.9.4): force fallback to "openai" if currently
        # "none" or absent -- "none" silently drops all memory access on search errors.
        if existing_ms.get("fallback") in (None, "none"):
            existing_ms["fallback"] = "openai"
            changed = True
        if "extraPaths" not in existing_ms:
            existing_ms["extraPaths"] = []
            changed = True
        if "wiki" in existing:
            del existing["wiki"]
            changed = True
        # entries mode: the key IS the id, so an "id" key inside the record is a
        # hard schema error (`agents.entries.<id>: Unrecognized key: "id"`).
        # Strip one left by an older version of this script.
        if ROSTER_MODE == "entries" and "id" in existing:
            del existing["id"]
            changed = True
        # IDEMPOTENT MIGRATION (v12.9.12): back-fill agentDir on entries written
        # before this version so existing boxes self-heal on the next materialize run.
        if not existing.get("agentDir"):
            existing["agentDir"] = agent_dir
            os.makedirs(agent_dir, exist_ok=True)
            changed = True
        if changed:
            updated += 1
            print(f"  ~ updated {roster_key:40s} → {workspace_path}")
        else:
            print(f"  = no-op   {roster_key:40s} (already in sync)")

# agents.ownership: the schema rejects a multi-agent roster that has neither
# ownership="explicit" nor exactly one legacy default=true marker ("multi-agent
# rosters require agents.ownership=\"explicit\" or one legacy default=true
# marker"). Registering department agents is precisely what turns a single-agent
# config into a multi-agent one, so set the key when -- and ONLY when -- our own
# write would otherwise leave the config invalid. An ownership value that is
# already present is never overwritten.
if ROSTER_MODE == "entries" and len(roster) > 1 and "ownership" not in agents_cfg:
    _marked = [k for k, v in roster.items() if isinstance(v, dict) and v.get("default") is True]
    if not _marked:
        agents_cfg["ownership"] = "explicit"
        print(
            '[materialize-dept-agents] set agents.ownership="explicit" -- the schema requires '
            "it for a multi-agent roster and this run made the roster multi-agent. No existing "
            "ownership value was overwritten."
        )

total = len(roster)

if DRY_RUN:
    print(f"[materialize-dept-agents] DRY RUN — no write performed")
    print(f"added {added} agents, updated {updated} agents, total in {ROSTER_LABEL}: {total}")
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

print(f"added {added} agents, updated {updated} agents, total in {ROSTER_LABEL}: {total}")

# ─── Emit a machine-readable manifest of discovered agents so the bash
#     wrapper can call scaffold-agent-files.sh for each one. ────────────────
manifest_path = os.path.join(os.path.dirname(CONFIG_FILE), ".materialize-dept-agents.manifest")
try:
    with open(manifest_path, "w") as f:
        # manifest_rows carries the roster key ACTUALLY registered above -- not a
        # recomputed f"dept-{slug}". In entries mode those differ whenever the
        # dept folder is capitalized (departments/Presentations -> the migrated
        # key dept-presentations), and the scaffolder + agentDir must follow the
        # key that is really in the config, not a second, phantom id.
        for roster_key, name, workspace_path, slug in manifest_rows:
            # Tab-separated: agent_id<TAB>name<TAB>workspace_path<TAB>dept_slug
            f.write(f"{roster_key}\t{name}\t{workspace_path}\t{slug}\n")
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

# Resolve mission-control.db via the single shared resolver (PRD 1.3) so the
# trio/quad rows land in the SAME db the dashboard + add-department.sh write to
# (Mac ~/projects/command-center first, then VPS /data/projects/command-center).
# The previous $OC_ROOT/workspaces/command-center candidate list was WRONG: the
# dashboard never creates the DB there, so install-time DA/QC/Healer rows were
# silently skipped. Falls back to add-department.sh's actual candidate list if
# the shared resolver cannot be imported.
db_path = None
try:
    _shared = os.path.join(SCRIPTS_DIR, "..", "..", "shared-utils")
    if _shared not in sys.path:
        sys.path.insert(0, _shared)
    from resolve_db import find_dashboard_db, is_db_found  # type: ignore
    _p = find_dashboard_db()
    if is_db_found(_p):
        db_path = str(_p)
except Exception as e:
    print(f"[materialize] WARN: shared resolve_db import failed ({e}); using fallback list", file=sys.stderr)

if not db_path:
    # Fallback mirrors add-department.sh:115-126 (Mac first), the db this skill writes to.
    for c in [
        os.path.join(os.path.expanduser("~"), "projects", "command-center", "mission-control.db"),
        os.path.join(os.path.expanduser("~"), "projects", "mission-control", "mission-control.db"),
        "/opt/mission-control/mission-control.db",
        "/app/mission-control.db",
        "/data/projects/command-center/mission-control.db",
    ]:
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

# A3-SAFETY GUARD (v16.2.11, blast-radius item 2): NEVER materialize generated
# healer-<dept>.md files into the A3-gated CANONICAL skill tree
# (~/.openclaw/skills or /data/.openclaw/skills). Those healer files are shipped,
# content-manifest-tracked TEMPLATE content; writing generated copies (or new
# custom-dept healer files) there would diverge Skill 23's installed (DEST) digest
# from the pristine-source (SRC) digest and block the fleet update-skills A3 gate.
# By design this script targets the workspace ".openclaw-skills" mirror only (its
# SKILLS_CANDIDATES never include the canonical hashed dir), so this guard is pure
# defense-in-depth: it does not change current behaviour, it only makes the "never
# write into the hashed skill dir" invariant explicit and enforced.
_canon_roots = [
    os.path.realpath(os.path.join(os.path.expanduser("~"), ".openclaw", "skills")),
    os.path.realpath(os.path.join("/data", ".openclaw", "skills")),
]
_role_lib_real = os.path.realpath(role_lib)
if any(_role_lib_real == r or _role_lib_real.startswith(r + os.sep) for r in _canon_roots):
    print("[materialize] Phase 4: role-library resolves under the A3-gated canonical "
          "skills tree -- skipping healer materialization (A3 safety; use the "
          "workspace .openclaw-skills mirror instead)")
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
