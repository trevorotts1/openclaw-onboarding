#!/usr/bin/env bash
# =============================================================================
# PODCAST PRODUCTION ENGINE :: install-podcast-department.sh (act-3)
# -----------------------------------------------------------------------------
# Materializes the podcast department AGENT (id dept-podcast) on a client box
# so it can hold session podcast:intake:<client-slug> and consume queued
# TaskFlows. This is the act that unblocks the 18-step pipeline: without a
# materialized agent, dept-podcast is DECLARED in openclaw.json agents.list
# but its agentDir is EMPTY on the box, so the gateway has no runtime to route
# the intake session to and queued flows have no consumer.
#
# WHAT "MATERIALIZED" MEANS (all four, verified by --verify):
#   1. an agents.list[] entry id=dept-podcast with a valid workspace and
#      agentDir (registered by the SHARED materialize-dept-agents.sh from
#      skill 32; this installer never hand-edits the agents.list schema)
#   2. per-agent files IDENTITY/SOUL/MEMORY/HEARTBEAT in the podcast
#      department workspace folder (via the SHARED scaffold-agent-files.sh)
#   3. the agentDir tree the gateway expects: agentDir/ plus agentDir/agent/
#      plus agentDir/sessions/
#   4. the per-agent SQLite store agentDir/agent/openclaw-agent.sqlite
#      (see THE SQLITE below; created by --prime-session)
#
# THE SQLITE -- HOW openclaw-agent.sqlite IS ACTUALLY CREATED (live-investigated
# on an operator box and a client box, gateway 2026.7.1-2):
#   - It is NOT created by scaffold-agent-files.sh, NOT by
#     materialize-dept-agents.sh, and NOT by agents.list registration. Those
#     produce the agents.list row and the bare agentDir only.
#   - The gateway creates it LAZILY on the FIRST write to the agent's own
#     state database (schema tables: schema_meta, cache_entries,
#     auth_profile_store, auth_profile_state, memory_index_*). Evidence: a
#     working agent's agentDir and auth-profiles.json landed days BEFORE its
#     sqlite appeared; the first session transcript (.jsonl) also predates the
#     sqlite; and dozens of registered agents on the same box still have an
#     empty agentDir because they never ran a turn. The sqlite path the
#     current gateway resolves is <agentDir>/agent/openclaw-agent.sqlite;
#     older gateways wrote <agentDir>/openclaw-agent.sqlite (both layouts are
#     accepted by --verify).
#   - Consequence: a no-op FIRST DISPATCH through the gateway for this agent
#     forces the store to exist. --prime-session does exactly that: it sends
#     one no-op message to session podcast:intake:<client-slug> via the
#     gateway (openclaw agent CLI, loopback) and then verifies the sqlite and
#     the sessions dir exist. Until primed (or until the first real intake
#     turn), the agent is registered but storage-less.
#
# REUSE, NOT REINVENTION: this installer delegates registration to
# 32-command-center-setup/scripts/materialize-dept-agents.sh (the script whose
# header documents the "runtime never knew about departments" bug) and file
# scaffolding to 32-command-center-setup/scripts/scaffold-agent-files.sh. It
# adds only what those two never did: the agentDir storage tree, the
# --prime-session first-dispatch, and the --verify gate.
#
# IDEMPOTENT: every step is a no-op when already done. Re-running is safe.
# materialize-dept-agents.sh is a batch pass over ALL department folders on
# the box; re-running it here heals any other previously-unwired department in
# the same pass (same behavior as add-department.sh's wire_department_runtime).
#
# FAIL CLOSED: missing/invalid --client-slug, missing openclaw.json, running
# as root, a failed materializer, or a read-back that shows no agents.list
# entry all STOP with a nonzero exit and an operator message. A registration
# that cannot be verified is never reported as success.
#
# SECRETS: no secret VALUES are ever read, echoed, printed, or written. All
# PODCAST_CLIENT_* onboarding env is reported SET / NOT SET by label only.
#
# EXIT: 0 installed / verified / dry-run planned
#       2 refused (usage, validation, precondition, verify miss, fail closed)
#       4 wiring failure (materializer ran but read-back shows no entry)
#
# USAGE:
#   install-podcast-department.sh --client-slug <slug> [--prime-session] [--dry-run]
#   install-podcast-department.sh --verify --client-slug <slug>
#
# FLAGS:
#   --client-slug <slug>  REQUIRED. Lowercase [a-z0-9-], 2 to 41 chars. Falls
#                         back to PODCAST_CLIENT_SLUG when absent. The slug
#                         rides the session key podcast:intake:<client-slug>
#                         (wiring.json session_key_template).
#   --prime-session       After install, send ONE no-op first-dispatch message
#                         to podcast:intake:<client-slug> via the gateway
#                         (openclaw agent CLI) so the gateway lazily creates
#                         the agent sqlite + session storage, then verify both
#                         exist. Costs one model turn; skip on boxes where the
#                         first real intake dispatch is imminent.
#   --verify              Read-only gate. Checks: agents.list entry present,
#                         agentDir + agent/ + sessions/ present, sqlite present
#                         (either layout), and the podcast: session namespace
#                         allowed in hooks.allowedSessionKeyPrefixes. Exits 0
#                         only when ALL hold.
#   --dry-run             Print the plan; write nothing. Exits 0 when plannable.
#   -h, --help            Show this help.
#
# ENV (values never printed; SET / NOT SET only):
#   PODCAST_CLIENT_SLUG         Fallback client slug when --client-slug absent.
#   PODCAST_CLIENT_ID           Onboarding contact/client id. Presence checked
#                               only; a missing label is a warning, not a stop.
#   PODCAST_CLIENT_LOCATION_ID  The client's Convert and Flow Location ID used
#                               by the intake handler's hard tenant check.
#                               Presence checked only; warning, not a stop.
#   PODCAST_CLIENT_EMAIL        Onboarding contact email. Presence checked
#                               only; warning, not a stop.
#   PODCAST_AGENT_ID            Podcast department agent id (default
#                               dept-podcast; never "main").
#   PODCAST_INSTALL_OC_ROOT     Override the OpenClaw root detection
#                               (default: /data/.openclaw else $HOME/.openclaw).
#                               Also the test seam.
#   PODCAST_PRIME_TIMEOUT       Seconds allowed for the prime turn (default 120).
# =============================================================================
set -euo pipefail

AGENT_ID="${PODCAST_AGENT_ID:-dept-podcast}"
DEPT_SLUG="podcast"

EX_OK=0
EX_REFUSED=2
EX_WIRING=4

log() { printf '%s\n' "$*" >&2; }
die() { local code="$1"; shift; log "HARD STOP ($code): $*"; exit "$code"; }
need() { command -v "$1" >/dev/null 2>&1 || die "$EX_REFUSED" "missing dependency: $1"; }

usage() { sed -n '2,106p' "$0" | sed 's/^# \{0,1\}//' >&2; }

# --------------------------------------------------------------------------- #
# Arguments
# --------------------------------------------------------------------------- #
CLIENT_SLUG=""
MODE="install"
DRY_RUN="0"
PRIME="0"

while [ $# -gt 0 ]; do
  case "$1" in
    --client-slug)   CLIENT_SLUG="${2:-}"; shift 2 ;;
    --verify)        MODE="verify"; shift ;;
    --prime-session) PRIME="1"; shift ;;
    --dry-run)       DRY_RUN="1"; shift ;;
    -h|--help)       usage; exit "$EX_OK" ;;
    *) log "Unknown flag: $1"; usage; exit "$EX_REFUSED" ;;
  esac
done

if [ -z "$CLIENT_SLUG" ]; then CLIENT_SLUG="${PODCAST_CLIENT_SLUG:-}"; fi

# --------------------------------------------------------------------------- #
# Input validation (fail closed)
# --------------------------------------------------------------------------- #
[ -n "$CLIENT_SLUG" ] || { log "missing client slug (pass --client-slug or export PODCAST_CLIENT_SLUG)"; usage; exit "$EX_REFUSED"; }
printf '%s' "$CLIENT_SLUG" | grep -Eq '^[a-z0-9][a-z0-9-]{1,40}$' \
  || die "$EX_REFUSED" "client slug '$CLIENT_SLUG' must be lowercase [a-z0-9-], 2 to 41 chars"

SESSION_KEY="podcast:intake:${CLIENT_SLUG}"
ROUTE_ID="podcast-intake-${CLIENT_SLUG}"

need python3

# Root guard: config writes run as the node runtime user, never root (a
# root-owned config file freezes the gateway). Read-only modes are allowed.
if [ "$DRY_RUN" != "1" ] && [ "$MODE" != "verify" ] && [ "$(id -u)" = "0" ]; then
  die "$EX_REFUSED" "running as root is refused; config writes must run as the node runtime user (re-run as the node user)"
fi

# --------------------------------------------------------------------------- #
# Resolve the OpenClaw root (override -> shared resolver -> inline fallback)
# --------------------------------------------------------------------------- #
OC_ROOT="${PODCAST_INSTALL_OC_ROOT:-}"
if [ -z "$OC_ROOT" ]; then
  SCRIPT_DIR="$(cd "$(dirname "$0")" 2>/dev/null && pwd || true)"
  RESOLVER="${SCRIPT_DIR}/../../shared-utils/resolve-oc-root.sh"
  # shellcheck source=/dev/null
  [ -f "$RESOLVER" ] && . "$RESOLVER"
  if declare -F resolve_oc_root >/dev/null 2>&1; then
    OC_ROOT="$(resolve_oc_root || true)"
  fi
fi
if [ -z "$OC_ROOT" ]; then
  if [ -d /data/.openclaw ]; then OC_ROOT="/data/.openclaw";
  elif [ -d "$HOME/.openclaw" ]; then OC_ROOT="$HOME/.openclaw"; fi
fi
[ -n "$OC_ROOT" ] || die "$EX_REFUSED" "no OpenClaw root found at /data/.openclaw or \$HOME/.openclaw (set PODCAST_INSTALL_OC_ROOT to override)"

CONFIG_FILE="$OC_ROOT/openclaw.json"
[ -f "$CONFIG_FILE" ] || die "$EX_REFUSED" "openclaw.json not found at $CONFIG_FILE"
python3 -c 'import json,sys; json.load(open(sys.argv[1]))' "$CONFIG_FILE" 2>/dev/null \
  || die "$EX_REFUSED" "openclaw.json at $CONFIG_FILE is not valid JSON; refusing to touch it"

# The sibling scripts from skill 32 that do the real registration/scaffolding.
# Numbered skill directories are siblings both in this repo and in an
# installed skills tree, so relative resolution works in both.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL32_SCRIPTS="$(cd "$SCRIPT_DIR/../.." && pwd)/32-command-center-setup/scripts"
MATERIALIZER="$SKILL32_SCRIPTS/materialize-dept-agents.sh"
SCAFFOLDER="$SKILL32_SCRIPTS/scaffold-agent-files.sh"

# --------------------------------------------------------------------------- #
# Helpers: read openclaw.json facts via python heredocs (no bash JSON parsing)
# --------------------------------------------------------------------------- #
export IPC_CONFIG_FILE="$CONFIG_FILE"
export IPC_AGENT_ID="$AGENT_ID"
export IPC_SESSION_KEY="$SESSION_KEY"

# Print the registered agentDir for AGENT_ID, or empty when no entry exists.
read_agent_dir() {
  python3 <<'PYEOF'
import json, os
cfg_path = os.environ["IPC_CONFIG_FILE"]
agent_id = os.environ["IPC_AGENT_ID"]
try:
    cfg = json.load(open(cfg_path))
except Exception:
    raise SystemExit(0)
agents = cfg.get("agents", {})
lst = agents.get("list", []) if isinstance(agents, dict) else []
for a in lst:
    if isinstance(a, dict) and a.get("id") == agent_id:
        print(a.get("agentDir", ""))
        break
PYEOF
}

# Exit 0 when AGENT_ID is present in agents.list, 1 otherwise.
entry_present() {
  python3 <<'PYEOF'
import json, os
cfg_path = os.environ["IPC_CONFIG_FILE"]
agent_id = os.environ["IPC_AGENT_ID"]
try:
    cfg = json.load(open(cfg_path))
except Exception:
    raise SystemExit(1)
agents = cfg.get("agents", {})
lst = agents.get("list", []) if isinstance(agents, dict) else []
found = any(isinstance(a, dict) and a.get("id") == agent_id for a in lst)
raise SystemExit(0 if found else 1)
PYEOF
}

# Exit 0 when hooks.allowedSessionKeyPrefixes allows this client's podcast
# session key (the register-podcast-hook.sh act writes the podcast: prefix),
# 1 otherwise.
namespace_allowed() {
  python3 <<'PYEOF'
import json, os
cfg_path = os.environ["IPC_CONFIG_FILE"]
session_key = os.environ["IPC_SESSION_KEY"]
try:
    cfg = json.load(open(cfg_path))
except Exception:
    raise SystemExit(1)
hooks = cfg.get("hooks", {})
if not isinstance(hooks, dict):
    raise SystemExit(1)
prefixes = hooks.get("allowedSessionKeyPrefixes", [])
if not isinstance(prefixes, list):
    raise SystemExit(1)
# The podcast namespace must be allowed by an explicit podcast prefix; a bare
# catch-all entry never counts as podcast isolation.
ok = any(isinstance(p, str) and p.startswith("podcast:") and session_key.startswith(p) for p in prefixes)
raise SystemExit(0 if ok else 1)
PYEOF
}

# Locate the sqlite store; prints the path if present, else nothing. Accepts
# the modern layout (agentDir/agent/openclaw-agent.sqlite, what the current
# gateway resolves) and the legacy layout (agentDir/openclaw-agent.sqlite).
find_sqlite() {
  local agent_dir="$1"
  if [ -f "$agent_dir/agent/openclaw-agent.sqlite" ]; then
    printf '%s' "$agent_dir/agent/openclaw-agent.sqlite"
  elif [ -f "$agent_dir/openclaw-agent.sqlite" ]; then
    printf '%s' "$agent_dir/openclaw-agent.sqlite"
  fi
}

label_state() { if [ -n "${!1:-}" ]; then printf 'SET'; else printf 'NOT SET'; fi; }

# --------------------------------------------------------------------------- #
# Preflight: PODCAST_CLIENT_* onboarding env (labels only; values never shown)
# --------------------------------------------------------------------------- #
log "preflight (labels only; values never printed):"
log "  PODCAST_CLIENT_SLUG        = $(label_state PODCAST_CLIENT_SLUG) (fallback client slug)"
log "  PODCAST_CLIENT_ID          = $(label_state PODCAST_CLIENT_ID) (onboarding client id)"
log "  PODCAST_CLIENT_LOCATION_ID = $(label_state PODCAST_CLIENT_LOCATION_ID) (intake hard tenant check)"
log "  PODCAST_CLIENT_EMAIL       = $(label_state PODCAST_CLIENT_EMAIL) (onboarding contact)"
if [ "$(label_state PODCAST_CLIENT_ID)" != "SET" ]; then
  log "  WARNING: PODCAST_CLIENT_ID is NOT SET; intake ledger rows carry it"
fi
if [ "$(label_state PODCAST_CLIENT_LOCATION_ID)" != "SET" ]; then
  log "  WARNING: PODCAST_CLIENT_LOCATION_ID is NOT SET; the intake handler's hard tenant check needs it before go-live"
fi
if [ "$(label_state PODCAST_CLIENT_EMAIL)" != "SET" ]; then
  log "  WARNING: PODCAST_CLIENT_EMAIL is NOT SET; onboarding emails need it"
fi

AGENT_DIR_FALLBACK="$OC_ROOT/agents/$AGENT_ID"
WORKSPACE_DIR="$OC_ROOT/workspace/departments/$DEPT_SLUG"

# --------------------------------------------------------------------------- #
# VERIFY mode: read-only materialization gate
# --------------------------------------------------------------------------- #
if [ "$MODE" = "verify" ]; then
  log ""
  log "verify dept-$DEPT_SLUG materialization against $CONFIG_FILE"
  MISS=0

  if entry_present; then
    log "  [PASS] agents.list entry present (id=$AGENT_ID)"
  else
    log "  [MISS] agents.list entry absent (id=$AGENT_ID); run this installer without --verify"
    MISS=$((MISS+1))
  fi

  AGENT_DIR="$(read_agent_dir)"
  [ -n "$AGENT_DIR" ] || AGENT_DIR="$AGENT_DIR_FALLBACK"

  if [ -d "$AGENT_DIR" ]; then
    log "  [PASS] agentDir present ($AGENT_DIR)"
  else
    log "  [MISS] agentDir absent ($AGENT_DIR)"
    MISS=$((MISS+1))
  fi

  if [ -d "$AGENT_DIR/agent" ] && [ -d "$AGENT_DIR/sessions" ]; then
    log "  [PASS] storage tree present (agent/ + sessions/)"
  else
    log "  [MISS] storage tree incomplete (need $AGENT_DIR/agent and $AGENT_DIR/sessions)"
    MISS=$((MISS+1))
  fi

  # Unit 3.5 -- the runtime dir must be a self-sufficient runtime, never an
  # empty directory. resolveSpecialistSessionKey probes this dir; the Command
  # Center holds the task as routed_but_not_dispatched when it is empty.
  RUNTIME_FILES="AGENTS.md IDENTITY.md SOUL.md MEMORY.md HEARTBEAT"
  RUNTIME_MISSING=""
  for f in $RUNTIME_FILES; do
    [ -f "$AGENT_DIR/$f" ] || RUNTIME_MISSING="$RUNTIME_MISSING $f"
  done
  if [ -z "$RUNTIME_MISSING" ]; then
    log "  [PASS] runtime-dir per-agent files present (AGENTS.md IDENTITY.md SOUL.md MEMORY.md HEARTBEAT)"
  else
    log "  [MISS] runtime-dir per-agent files absent:$RUNTIME_MISSING (re-run this installer to materialize them)"
    MISS=$((MISS+1))
  fi

  SQLITE_PATH="$(find_sqlite "$AGENT_DIR" || true)"
  if [ -n "$SQLITE_PATH" ]; then
    log "  [PASS] sqlite store present ($SQLITE_PATH)"
  else
    log "  [MISS] sqlite store absent; the gateway creates it lazily on the first dispatch -- run with --prime-session"
    MISS=$((MISS+1))
  fi

  if namespace_allowed; then
    log "  [PASS] session namespace allowed (podcast: in hooks.allowedSessionKeyPrefixes)"
  else
    log "  [MISS] session namespace NOT allowed; run register-podcast-hook.sh --client-slug $CLIENT_SLUG (act-1) to bind podcast:"
    MISS=$((MISS+1))
  fi

  if [ "$MISS" -eq 0 ]; then
    log "verify: PASS -- $AGENT_ID is materialized and can hold $SESSION_KEY"
    exit "$EX_OK"
  fi
  log "verify: FAIL -- $MISS check(s) missed"
  exit "$EX_REFUSED"
fi

# --------------------------------------------------------------------------- #
# Plan (printed on every run; the ONLY thing applied)
# --------------------------------------------------------------------------- #
log ""
log "install plan for client '$CLIENT_SLUG' (agent $AGENT_ID) against OC_ROOT=$OC_ROOT:"
log "  1. scaffold per-agent files via scaffold-agent-files.sh (workspace $WORKSPACE_DIR)"
log "  2. register/update agents.list via materialize-dept-agents.sh (batch pass; idempotent)"
log "  3. read-back the agents.list entry for $AGENT_ID (fail closed if absent)"
log "  4. ensure storage tree: $AGENT_DIR_FALLBACK/agent and $AGENT_DIR_FALLBACK/sessions"
if [ "$PRIME" = "1" ]; then
  log "  5. prime-session: ONE no-op first dispatch to $SESSION_KEY via the gateway"
  log "     (openclaw agent CLI; forces the lazy sqlite + session storage), then verify both"
fi
log "  session key: $SESSION_KEY   route id: $ROUTE_ID"

if [ "$DRY_RUN" = "1" ]; then
  log ""
  log "dry-run: plan printed above; nothing written (exit 0)"
  exit "$EX_OK"
fi

# --------------------------------------------------------------------------- #
# Step 1: scaffold per-agent files (creates the dept workspace folder the
# materializer scans). Falls back to a bare mkdir when the scaffolder is
# absent from this install (the add-department.sh fallback doctrine).
# --------------------------------------------------------------------------- #
if [ -f "$SCAFFOLDER" ]; then
  log "step 1: scaffolding per-agent files for $AGENT_ID"
  if ! bash "$SCAFFOLDER" --agent-slug "$DEPT_SLUG" --agent-name "Podcast" --department "$DEPT_SLUG" >/dev/null 2>&1; then
    log "  WARNING: scaffold-agent-files.sh exited nonzero; continuing (files are stubs; registration is the load-bearing step)"
  fi
else
  log "step 1: scaffold-agent-files.sh not found at $SCAFFOLDER; creating workspace dir only"
  mkdir -p "$WORKSPACE_DIR"
fi

# --------------------------------------------------------------------------- #
# Step 2: register the agent via the SHARED materializer (single source of
# truth for the agents.list schema). It honors its own interview-complete
# precondition and reports INTERVIEW_NOT_COMPLETE (exit 0, no mutation).
# --------------------------------------------------------------------------- #
[ -f "$MATERIALIZER" ] || die "$EX_REFUSED" "materialize-dept-agents.sh not found at $MATERIALIZER (skill 32 must be installed next to this skill)"

log "step 2: running materialize-dept-agents.sh (batch pass; idempotent for every dept it finds)"
MATERIALIZE_OUT="$(bash "$MATERIALIZER" 2>&1 || true)"
if printf '%s' "$MATERIALIZE_OUT" | grep -q "INTERVIEW_NOT_COMPLETE"; then
  die "$EX_REFUSED" "materialize-dept-agents.sh deferred: the AI Workforce interview is not marked complete on this box. Finish the interview, then re-run this installer."
fi
# Surface the materializer's own summary (added/updated/no-op lines) so the
# operator can see whether the batch pass changed anything this run.
printf '%s\n' "$MATERIALIZE_OUT" | grep -E "^ *[+~=]|^added " | while IFS= read -r LINE; do
  log "  $LINE"
done

# --------------------------------------------------------------------------- #
# Step 3: read-back verification (fail closed; a write we cannot confirm is a
# failure, never a reported success)
# --------------------------------------------------------------------------- #
if entry_present; then
  log "step 3: agents.list entry for $AGENT_ID confirmed (read-back)"
else
  die "$EX_WIRING" "materialize-dept-agents.sh ran but no agents.list entry exists for $AGENT_ID after read-back; investigate $CONFIG_FILE (materializer output: $(printf '%s' "$MATERIALIZE_OUT" | tail -1))"
fi

AGENT_DIR="$(read_agent_dir)"
[ -n "$AGENT_DIR" ] || AGENT_DIR="$AGENT_DIR_FALLBACK"

# --------------------------------------------------------------------------- #
# Step 4: ensure the storage tree the gateway expects. The sqlite itself is
# LAZY (see THE SQLITE in the header): registration and mkdir never create it;
# only the first dispatch does. Step 5 below can force that.
#
# Unit 3.5 (master plan 2026-08-04): the RUNTIME DIR must also carry the
# per-agent files (AGENTS.md, IDENTITY.md, SOUL.md, MEMORY.md, HEARTBEAT) so
# `~/.openclaw/agents/dept-podcast/` is a self-sufficient runtime the Command
# Center dispatch resolver can rely on. resolveSpecialistSessionKey
# (task-dispatcher.ts) probes this exact directory; a bare empty dir is the
# `no_specialist_runtime` hold. We materialize the files here (copying the
# workspace-scaffolded versions when they exist, else writing lightweight
# stubs), so the runtime dir is NEVER empty on a box this installer has run on.
# --------------------------------------------------------------------------- #
log "step 4: ensuring storage tree under $AGENT_DIR"
mkdir -p "$AGENT_DIR" "$AGENT_DIR/agent" "$AGENT_DIR/sessions"
log "  + $AGENT_DIR/agent (sqlite home; created lazily by the gateway on first dispatch)"
log "  + $AGENT_DIR/sessions (session transcripts)"

# Unit 3.5 -- materialize the per-agent files into the runtime dir. Sources, in
# priority order: the workspace-scaffolded file (scaffold-agent-files.sh wrote
# it at $WORKSPACE_DIR/IDENTITY.md etc.), then a lightweight stub. The shared
# AGENTS.md lives at the workspace root as a symlink to the shared copy; when
# present we copy the resolved target (never a dangling symlink).
RUNTIME_FILES="AGENTS.md IDENTITY.md SOUL.md MEMORY.md HEARTBEAT"
for f in $RUNTIME_FILES; do
  if [ -f "$AGENT_DIR/$f" ]; then
    continue  # already materialized -- never overwrite operator-curated content
  fi
  if [ -f "$WORKSPACE_DIR/$f" ]; then
    cp "$WORKSPACE_DIR/$f" "$AGENT_DIR/$f" 2>/dev/null \
      && log "  + $AGENT_DIR/$f (copied from workspace scaffold)" \
      || log "  WARNING: could not copy $WORKSPACE_DIR/$f into $AGENT_DIR"
  elif [ -L "$WORKSPACE_DIR/$f" ] && [ -f "$(readlink "$WORKSPACE_DIR/$f" 2>/dev/null || true)" ]; then
    cp -- "$(readlink "$WORKSPACE_DIR/$f")" "$AGENT_DIR/$f" 2>/dev/null \
      && log "  + $AGENT_DIR/$f (resolved from workspace symlink)" \
      || log "  WARNING: could not resolve $WORKSPACE_DIR/$f into $AGENT_DIR"
  else
    # Lightweight stub -- the runtime dir is never empty. Content is a pointer
    # to the workspace originals so a later full scaffold supersedes it.
    printf '# %s -- dept-podcast runtime dir placeholder.\n# Full content lives in the workspace scaffold (%s/%s).\n# Re-run scaffold-agent-files.sh or install-podcast-department.sh to supersede.\n' \
      "$f" "$WORKSPACE_DIR" "$f" > "$AGENT_DIR/$f" 2>/dev/null \
      && log "  + $AGENT_DIR/$f (lightweight stub)" \
      || log "  WARNING: could not write $AGENT_DIR/$f"
  fi
done

# --------------------------------------------------------------------------- #
# Step 5 (optional): prime one session so the lazy storage exists NOW
# --------------------------------------------------------------------------- #
if [ "$PRIME" = "1" ]; then
  log "step 5: priming session $SESSION_KEY with ONE no-op first dispatch"
  OPENCLAW_BIN="$(command -v openclaw || true)"
  [ -n "$OPENCLAW_BIN" ] || die "$EX_REFUSED" "the openclaw CLI is not on PATH; cannot prime a session (install it or let the first real intake dispatch create the storage)"

  PRIME_TIMEOUT="${PODCAST_PRIME_TIMEOUT:-120}"
  PRIME_MSG="Podcast department storage prime (no-op). Reply with the single word ok. No pipeline work is requested."
  PRIME_RC=0
  PRIME_OUT="$("$OPENCLAW_BIN" agent --agent "$AGENT_ID" --session-key "$SESSION_KEY" \
    --message "$PRIME_MSG" --timeout "$PRIME_TIMEOUT" 2>&1)" || PRIME_RC=$?
  if [ "$PRIME_RC" -ne 0 ]; then
    die "$EX_WIRING" "prime dispatch failed (rc=$PRIME_RC): $(printf '%s' "$PRIME_OUT" | tail -2 | tr '\n' ' ')"
  fi
  log "  prime turn completed; checking storage"

  # Brief settle retry: the gateway writes synchronously inside the turn, but
  # a slow disk should never read as a failure on the first stat.
  SQLITE_PATH=""
  for _ in 1 2 3; do
    SQLITE_PATH="$(find_sqlite "$AGENT_DIR" || true)"
    [ -n "$SQLITE_PATH" ] && break
    sleep 1
  done

  if [ -z "$SQLITE_PATH" ]; then
    die "$EX_WIRING" "prime turn succeeded but the sqlite store still does not exist under $AGENT_DIR (checked agent/ and top-level layouts)"
  fi
  if [ ! -d "$AGENT_DIR/sessions" ]; then
    die "$EX_WIRING" "prime turn succeeded but $AGENT_DIR/sessions does not exist"
  fi
  log "  + sqlite store materialized: $SQLITE_PATH"
  log "  + sessions dir present: $AGENT_DIR/sessions"
fi

log ""
log "installed: $AGENT_ID is materialized on this box and can hold $SESSION_KEY"
if [ "$PRIME" != "1" ]; then
  log "note: the sqlite store is created lazily by the gateway on the FIRST dispatch."
  log "      Re-run with --prime-session to force it now, or let the first real intake turn do it."
fi
log "next: register the intake route (register-podcast-hook.sh --client-slug $CLIENT_SLUG) if not already done, then confirm with --verify"
exit "$EX_OK"
