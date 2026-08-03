#!/usr/bin/env bash
# =============================================================================
# PODCAST PRODUCTION ENGINE :: register-podcast-hook.sh
# webhook-design.md Sections 2, 7, 8; wiring.json session_binding
# -----------------------------------------------------------------------------
# Registers the podcast intake webhook ROUTE plus its session binding on a
# client box, one route per client, exactly one:
#
#   route id     podcast-intake-<client-slug>
#   sessionKey   podcast:intake:<client-slug>
#   endpoint     POST /plugins/webhooks/podcast-intake-<client-slug>
#
# THE REGISTRATION SURFACE (live-verified schema, see scripts/webhook/README.md):
# the OpenClaw Webhooks plugin exposes NO route-registration action over the
# gateway (its actions are flow operations only: create_flow, run_task,
# get_flow, find_latest_flow, resolve_flow, get_task_summary, set_waiting,
# resume_flow, finish_flow, fail_flow, request_cancel, cancel_flow). Route
# configuration therefore happens where the plugin reads it: the box's
# openclaw.json at
#
#   plugins.entries.webhooks.config.routes.<routeId>
#
# a MAP keyed by routeId (NOT plugins.webhooks.routes). The route object is
# .strict() and accepts EXACTLY: enabled?, path?, sessionKey (required),
# secret (required), controllerId?, description?. It does NOT accept
# allowedAgentIds or allowedSessionKeyPrefixes: those are gateway-core hooks
# fields, so this script ALSO binds the podcast agent id to
# hooks.allowedAgentIds and the podcast: session namespace to
# hooks.allowedSessionKeyPrefixes (wiring.json isolation clause), preserving
# every pre-existing entry and the hooks.defaultSessionKey's own value (the
# U88-GK-26 crash-loop guard: a defaultSessionKey that stops matching the
# prefix allowlist makes the gateway refuse to start).
#
# This is the box-side helper provision-podcast-client.sh delegates the
# "hook-mapping" step to, and the helper revoke-podcast-client.sh calls with
# --remove. All three CLI shapes below are honored:
#
#   register-podcast-hook.sh --client-slug acme-media
#   register-podcast-hook.sh acme-media                       (provision caller)
#   register-podcast-hook.sh acme-media podcast-intake-acme-media
#   register-podcast-hook.sh --remove acme-media [mapping-id] (revoke caller)
#
# IDEMPOTENT: a re-run against an already-registered route is a no-op (the
# config file is not rewritten); a drift in any field is healed by a safe
# update. --remove of an absent route is a no-op. A pre-existing backup file
# (<config>.bak-podcast-hook.<utc>) is written before every real mutation.
#
# FAIL CLOSED: no config file, an unparseable config file, an explicitly
# disabled webhooks plugin, a missing route secret, running as root, or a
# failed gateway config validation all STOP the script with a nonzero exit and
# an operator message. A registration that cannot be verified is never
# reported as success.
#
# SECRETS: PODCAST_INTAKE_HOOK_SECRET is referenced by env LABEL only
# (SecretRef {source: env, provider: default, id: PODCAST_INTAKE_HOOK_SECRET},
# re-resolved by the runtime on every request). The value is never read,
# echoed, printed, or written into openclaw.json; this script only checks that
# the label is SET in the live process environment. Never print a secret.
#
# GATEWAY RELOAD: this script writes and verifies config; it does NOT restart
# the gateway (the restart doctrine is box-type-specific and operator-owned:
# Mac kickstart-then-stop, Virtual Private Server compose recreate). Apply the
# box's restart doctrine after a first-time registration, then confirm the
# gateway is healthy and a signed test POST returns 200 while an unsigned one
# returns 401.
#
# CONFIG RESOLUTION: PODCAST_OPENCLAW_CONFIG override, else `openclaw config
# file` when the CLI is present, else $HOME/.openclaw/openclaw.json, else
# /data/.openclaw/openclaw.json.
#
# EXIT: 0 registered / no-op / dry-run planned
#       2 validation or usage refusal (fail closed)
#       4 gateway config write or validation failure
#
# USAGE:
#   register-podcast-hook.sh --client-slug <slug> [flags]
#   register-podcast-hook.sh <slug> [<route-id>] [flags]
#
# FLAGS:
#   --client-slug <slug>  REQUIRED. Lowercase [a-z0-9-], 2 to 41 chars, stable
#                         for the life of the client (same as --slug on
#                         provision-podcast-client.sh).
#   --remove              Unregister: delete the route entry, drop the podcast
#                         agent id from hooks.allowedAgentIds and the podcast:
#                         prefix from hooks.allowedSessionKeyPrefixes once no
#                         podcast:* route remains. Every other route and key is
#                         preserved.
#   --dry-run             Resolve + print the planned registration; write
#                         nothing. Exits 0 when plannable.
#   -h, --help            Show this help.
#
# ENV (values never printed; SET / NOT SET only):
#   PODCAST_INTAKE_HOOK_SECRET    REQUIRED for a real registration (the route
#                                 secret; SecretRef id). The script verifies the
#                                 label is SET and never touches the value.
#   PODCAST_CLIENT_LOCATION_ID    The client's Convert and Flow Location ID for
#                                 the intake handler's hard tenant check. Read
#                                 for presence only (SET / NOT SET); a missing
#                                 label is a warning, not a stop, because the
#                                 route can be registered before onboarding
#                                 records the location.
#   PODCAST_CLIENT_SLUG           Fallback client slug when --client-slug and a
#                                 positional slug are both absent.
#   PODCAST_AGENT_ID              Podcast department agent id bound to
#                                 hooks.allowedAgentIds (default dept-podcast,
#                                 the client's podcast department agent that
#                                 embodies director-of-podcast; never "main").
#   PODCAST_OPENCLAW_CONFIG       Override the openclaw.json path.
# =============================================================================
set -euo pipefail

PROG="$(basename "$0")"
WEBHOOK_DIR="$(cd "$(dirname "$0")/webhook" 2>/dev/null && pwd || true)"
SECRET_LABEL="PODCAST_INTAKE_HOOK_SECRET"
SESSION_PREFIX="podcast:"

EX_OK=0
EX_REFUSED=2
EX_GATEWAY=4

log() { printf '%s\n' "$*" >&2; }
die() { local code="$1"; shift; log "HARD STOP ($code): $*"; exit "$code"; }
need() { command -v "$1" >/dev/null 2>&1 || die "$EX_REFUSED" "missing dependency: $1"; }

usage() { sed -n '2,109p' "$0" | sed 's/^# \{0,1\}//' >&2; }

# --------------------------------------------------------------------------- #
# Arguments
# --------------------------------------------------------------------------- #
CLIENT_SLUG=""
MODE="add"
DRY_RUN="0"
POSITIONAL=()

while [ $# -gt 0 ]; do
  case "$1" in
    --client-slug) CLIENT_SLUG="${2:-}"; shift 2 ;;
    --remove)      MODE="remove"; shift ;;
    --dry-run)     DRY_RUN="1"; shift ;;
    -h|--help)     usage; exit "$EX_OK" ;;
    --) shift; while [ $# -gt 0 ]; do POSITIONAL+=("$1"); shift; done ;;
    -*) log "Unknown flag: $1"; usage; exit "$EX_REFUSED" ;;
    *)  POSITIONAL+=("$1"); shift ;;
  esac
done

# Positional compatibility with the sibling callers:
#   provision-podcast-client.sh -> register-podcast-hook.sh <slug> <mapping-id>
#   revoke-podcast-client.sh    -> register-podcast-hook.sh --remove <slug> <mapping-id>
POSITIONAL_MAPPING="${POSITIONAL[1]:-}"
if [ -z "$CLIENT_SLUG" ]; then CLIENT_SLUG="${POSITIONAL[0]:-}"; fi
if [ -z "$CLIENT_SLUG" ]; then CLIENT_SLUG="${PODCAST_CLIENT_SLUG:-}"; fi

# --------------------------------------------------------------------------- #
# Input validation (fail closed)
# --------------------------------------------------------------------------- #
[ -n "$CLIENT_SLUG" ] || { log "missing client slug"; usage; exit "$EX_REFUSED"; }
printf '%s' "$CLIENT_SLUG" | grep -Eq '^[a-z0-9][a-z0-9-]{1,40}$' \
  || die "$EX_REFUSED" "client slug '$CLIENT_SLUG' must be lowercase [a-z0-9-], 2 to 41 chars"

ROUTE_ID="podcast-intake-${CLIENT_SLUG}"
SESSION_KEY="podcast:intake:${CLIENT_SLUG}"
AGENT_ID="${PODCAST_AGENT_ID:-dept-podcast}"
CONTROLLER_ID="webhooks/${ROUTE_ID}"
DESCRIPTION="Podcast Production Engine intake for ${CLIENT_SLUG} (deterministic ingest, durable TaskFlow)."

# A caller-supplied mapping id (provision/revoke contract) must agree with the
# wiring.json route_id_template; a mismatch means we were pointed at the wrong
# client and we refuse rather than register a cross-boundary route.
if [ -n "$POSITIONAL_MAPPING" ] && [ "$POSITIONAL_MAPPING" != "$ROUTE_ID" ]; then
  die "$EX_REFUSED" "supplied route id '$POSITIONAL_MAPPING' does not match the wiring.json route_id_template '$ROUTE_ID'"
fi

need jq
need python3

# Resolve the gateway config file (fail closed: no file, no registration).
CONFIG_FILE="${PODCAST_OPENCLAW_CONFIG:-}"
if [ -z "$CONFIG_FILE" ] && command -v openclaw >/dev/null 2>&1; then
  CONFIG_FILE="$(openclaw config file 2>/dev/null || true)"
fi
if [ -z "$CONFIG_FILE" ]; then
  if [ -f "$HOME/.openclaw/openclaw.json" ]; then
    CONFIG_FILE="$HOME/.openclaw/openclaw.json"
  elif [ -f "/data/.openclaw/openclaw.json" ]; then
    CONFIG_FILE="/data/.openclaw/openclaw.json"
  fi
fi
[ -n "$CONFIG_FILE" ] || die "$EX_REFUSED" "openclaw.json not found (set PODCAST_OPENCLAW_CONFIG or install the gateway config)"
[ -f "$CONFIG_FILE" ] || die "$EX_REFUSED" "openclaw.json not found at $CONFIG_FILE"
jq empty "$CONFIG_FILE" 2>/dev/null || die "$EX_REFUSED" "openclaw.json at $CONFIG_FILE is not valid JSON; refusing to touch it"

# Root guard: config writes run as the node runtime user, never root (a
# root-owned config file freezes the gateway). Dry-run is read-only and allowed.
if [ "$DRY_RUN" != "1" ] && [ "$(id -u)" = "0" ]; then
  die "$EX_REFUSED" "running as root is refused; config writes must run as the node runtime user (re-run as the node user)"
fi

# Preflight: the PODCAST_CLIENT_* onboarding env plus the route secret label.
# Every credential is reported SET / NOT SET by label only; never a value.
label_state() { if [ -n "${!1:-}" ]; then printf 'SET'; else printf 'NOT SET'; fi; }

log "preflight (labels only; values never printed):"
log "  ${SECRET_LABEL} = $(label_state "$SECRET_LABEL") (route secret; SecretRef env id)"
log "  PODCAST_CLIENT_LOCATION_ID = $(label_state PODCAST_CLIENT_LOCATION_ID) (intake tenant check)"
if [ "$MODE" = "add" ] && [ "$(label_state "$SECRET_LABEL")" != "SET" ]; then
  if [ "$DRY_RUN" = "1" ]; then
    log "  WARNING: ${SECRET_LABEL} is NOT SET; a real registration will refuse until onboarding generates it (openssl rand -hex 32 into the client env store)"
  else
    die "$EX_REFUSED" "${SECRET_LABEL} is NOT SET in the live process environment; generate it at onboarding (openssl rand -hex 32) and export it before registering (fail closed)"
  fi
fi
if [ "$(label_state PODCAST_CLIENT_LOCATION_ID)" != "SET" ]; then
  log "  WARNING: PODCAST_CLIENT_LOCATION_ID is NOT SET; the intake handler's hard tenant check needs it before go-live"
fi

# --------------------------------------------------------------------------- #
# The planned registration (printed on every run; the ONLY thing applied)
# --------------------------------------------------------------------------- #
ROUTE_JSON="$(jq -n \
  --arg rid "$ROUTE_ID" \
  --arg path "/plugins/webhooks/${ROUTE_ID}" \
  --arg sk "$SESSION_KEY" \
  --arg label "$SECRET_LABEL" \
  --arg cid "$CONTROLLER_ID" \
  --arg desc "$DESCRIPTION" \
  '{
    enabled: true,
    path: $path,
    sessionKey: $sk,
    secret: { source: "env", provider: "default", id: $label },
    controllerId: $cid,
    description: $desc
  }')"

log ""
log "planned ${MODE} registration for client '$CLIENT_SLUG' against $CONFIG_FILE:"
log "  route id                 : $ROUTE_ID"
log "  endpoint                 : POST /plugins/webhooks/${ROUTE_ID}"
log "  sessionKey               : $SESSION_KEY"
log "  secret                   : SecretRef env label ${SECRET_LABEL} (value never written)"
log "  controllerId             : $CONTROLLER_ID"
log "  hooks.allowedAgentIds    + $AGENT_ID (podcast dept agent only)"
log "  hooks.allowedSessionKeyPrefixes + ${SESSION_PREFIX} (podcast namespace only; pre-existing entries and defaultSessionKey preserved)"
if [ "$MODE" = "remove" ]; then
  log "  action                   : delete route $ROUTE_ID; drop $AGENT_ID and ${SESSION_PREFIX} once no podcast:* route remains; preserve everything else"
fi

if [ "$DRY_RUN" = "1" ]; then
  log ""
  log "dry-run: planned registration printed above; nothing written (exit 0)"
  exit "$EX_OK"
fi

# Baseline validation: when the openclaw CLI is present, capture whether the
# config validates BEFORE we touch it, so a pre-existing validation failure is
# never blamed on this registration (and a fresh failure we cause IS blamed).
BASELINE_RC=""
if command -v openclaw >/dev/null 2>&1; then
  BASELINE_RC=0
  OPENCLAW_CONFIG_PATH="$CONFIG_FILE" openclaw config validate >/dev/null 2>&1 || BASELINE_RC=$?
fi

# Refuse to register against an explicitly disabled webhooks plugin (fail
# closed; a merge here would silently enable a surface the box turned off).
if [ "$MODE" = "add" ] && jq -e '.plugins.entries.webhooks.enabled == false' "$CONFIG_FILE" >/dev/null 2>&1; then
  die "$EX_REFUSED" "the webhooks plugin is explicitly disabled on this box; enable it before registering the podcast intake route"
fi

# --------------------------------------------------------------------------- #
# Apply the merge (python3 stdlib: read, mutate, backup, atomic write). The
# route secret is a SecretRef by label; no secret value can land in the file.
# Prints UNCHANGED (idempotent no-op) or WRITTEN <backup-path>.
# --------------------------------------------------------------------------- #
MERGE_OUT="$(REG_CONFIG="$CONFIG_FILE" REG_ROUTE_ID="$ROUTE_ID" REG_SESSION_KEY="$SESSION_KEY" \
  REG_AGENT_ID="$AGENT_ID" REG_CONTROLLER_ID="$CONTROLLER_ID" REG_DESCRIPTION="$DESCRIPTION" \
  REG_MODE="$MODE" REG_ROUTE_JSON="$ROUTE_JSON" python3 - <<'PY'
import datetime, json, os, shutil, sys, tempfile

cfg_path = os.environ["REG_CONFIG"]
route_id = os.environ["REG_ROUTE_ID"]
agent_id = os.environ["REG_AGENT_ID"]
mode = os.environ["REG_MODE"]

try:
    with open(cfg_path, encoding="utf-8") as fh:
        cfg = json.load(fh)
except Exception as exc:
    sys.stderr.write("cannot parse %s: %s\n" % (cfg_path, exc))
    sys.exit(2)
if not isinstance(cfg, dict):
    sys.stderr.write("top-level openclaw.json value is not an object\n")
    sys.exit(2)

before = json.dumps(cfg, sort_keys=True)

plugins = cfg.get("plugins")
if plugins is None:
    plugins = cfg["plugins"] = {}
if not isinstance(plugins, dict):
    sys.stderr.write("plugins is not an object; refusing to clobber it\n")
    sys.exit(2)
entries = plugins.get("entries")
if entries is None:
    entries = plugins["entries"] = {}
if not isinstance(entries, dict):
    sys.stderr.write("plugins.entries is not an object; refusing to clobber it\n")
    sys.exit(2)
webhooks = entries.get("webhooks")
if webhooks is None:
    webhooks = entries["webhooks"] = {}
if not isinstance(webhooks, dict):
    sys.stderr.write("plugins.entries.webhooks is not an object; refusing to clobber it\n")
    sys.exit(2)
config = webhooks.get("config")
if config is None:
    config = webhooks["config"] = {}
if not isinstance(config, dict):
    sys.stderr.write("plugins.entries.webhooks.config is not an object; refusing to clobber it\n")
    sys.exit(2)
routes = config.get("routes")
if routes is None:
    routes = config["routes"] = {}
if not isinstance(routes, dict):
    sys.stderr.write("plugins.entries.webhooks.config.routes is not a map; refusing to clobber it\n")
    sys.exit(2)

if mode == "add":
    if webhooks.get("enabled") is False:
        sys.stderr.write("the webhooks plugin is explicitly disabled on this box; enable it before registering the podcast intake route\n")
        sys.exit(2)
    webhooks["enabled"] = True
    routes[route_id] = json.loads(os.environ["REG_ROUTE_JSON"])
    hooks = cfg.get("hooks")
    if hooks is None:
        hooks = cfg["hooks"] = {}
    if not isinstance(hooks, dict):
        sys.stderr.write("hooks is not an object; refusing to clobber it\n")
        sys.exit(2)
    allowed_agents = hooks.get("allowedAgentIds")
    if not isinstance(allowed_agents, list):
        allowed_agents = []
    if agent_id not in allowed_agents:
        allowed_agents.append(agent_id)
    hooks["allowedAgentIds"] = allowed_agents
    prefixes = hooks.get("allowedSessionKeyPrefixes")
    if not isinstance(prefixes, list):
        prefixes = []
    if "podcast:" not in prefixes:
        prefixes.append("podcast:")
    default_sk = hooks.get("defaultSessionKey")
    if isinstance(default_sk, str) and default_sk and default_sk not in prefixes:
        # Crash-loop guard (U88-GK-26): hooks.defaultSessionKey must keep
        # matching hooks.allowedSessionKeyPrefixes or the gateway refuses to
        # start. Preserve the pre-existing default's own value.
        prefixes.append(default_sk)
    hooks["allowedSessionKeyPrefixes"] = prefixes
else:
    if route_id in routes:
        del routes[route_id]
    remaining_podcast = [
        rid for rid, r in routes.items()
        if isinstance(r, dict) and str(r.get("sessionKey") or "").startswith("podcast:")
    ]
    if not remaining_podcast:
        hooks = cfg.get("hooks")
        if isinstance(hooks, dict):
            aa = hooks.get("allowedAgentIds")
            if isinstance(aa, list) and agent_id in aa:
                hooks["allowedAgentIds"] = [a for a in aa if a != agent_id]
            pk = hooks.get("allowedSessionKeyPrefixes")
            if isinstance(pk, list) and "podcast:" in pk:
                hooks["allowedSessionKeyPrefixes"] = [p for p in pk if p != "podcast:"]

after = json.dumps(cfg, sort_keys=True)
if after == before:
    print("UNCHANGED")
    sys.exit(0)

ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
backup = cfg_path + ".bak-podcast-hook." + ts
try:
    shutil.copy2(cfg_path, backup)
except OSError:
    backup = ""
st_mode = os.stat(cfg_path).st_mode & 0o777
d = os.path.dirname(cfg_path) or "."
fd, tmp = tempfile.mkstemp(prefix=".podcast-hook.", suffix=".json.tmp", dir=d)
try:
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)
        fh.write("\n")
    os.chmod(tmp, st_mode)
    os.replace(tmp, cfg_path)
except Exception:
    try:
        os.unlink(tmp)
    except OSError:
        pass
    raise
print("WRITTEN %s" % backup)
PY
)" || die "$EX_GATEWAY" "config merge failed for $CONFIG_FILE (see message above)"

if [ "$MERGE_OUT" = "UNCHANGED" ]; then
  if [ "$MODE" = "add" ]; then
    log "RESULT: no-op. route $ROUTE_ID already registered exactly as specified (idempotent; nothing rewritten)."
  else
    log "RESULT: no-op. route $ROUTE_ID is not registered (nothing to remove; nothing rewritten)."
  fi
  exit "$EX_OK"
fi
BACKUP_FILE="${MERGE_OUT#WRITTEN }"
[ -n "$BACKUP_FILE" ] && log "backup written: $BACKUP_FILE"

# --------------------------------------------------------------------------- #
# Read-back verification (never a bare claim). In ADD mode the written file
# must carry the route exactly once with the binding fields, the allow-lists
# must be merged, and the secret must be a SecretRef by label. In REMOVE mode
# the route must be gone and, once no podcast:* route remains, the podcast
# agent id and podcast: prefix must be dropped from the allow-lists.
# --------------------------------------------------------------------------- #
VERIFY_RC=0
if [ "$MODE" = "add" ]; then
  jq -e --arg rid "$ROUTE_ID" --arg sk "$SESSION_KEY" --arg label "$SECRET_LABEL" --arg agent "$AGENT_ID" '
    .plugins.entries.webhooks.config.routes[$rid] as $r
    | ($r != null)
      and ($r.sessionKey == $sk)
      and ($r.secret.source == "env")
      and ($r.secret.provider == "default")
      and ($r.secret.id == $label)
      and (($r | keys) - ["enabled","path","sessionKey","secret","controllerId","description"] | length == 0)
      and ((.hooks.allowedAgentIds // []) | index($agent) != null)
      and ((.hooks.allowedSessionKeyPrefixes // []) | index("podcast:") != null)
  ' "$CONFIG_FILE" >/dev/null 2>&1 || VERIFY_RC=1
else
  jq -e --arg rid "$ROUTE_ID" --arg agent "$AGENT_ID" '
    (.plugins.entries.webhooks.config.routes[$rid] == null)
    and (
      ([(.plugins.entries.webhooks.config.routes // {})[]
         | select(type=="object" and ((.sessionKey // "") | startswith("podcast:")))] | length) as $n
      | ($n > 0)
        or (((.hooks.allowedAgentIds // []) | index($agent) == null)
            and ((.hooks.allowedSessionKeyPrefixes // []) | index("podcast:") == null))
    )
  ' "$CONFIG_FILE" >/dev/null 2>&1 || VERIFY_RC=1
fi

if [ "$VERIFY_RC" != "0" ]; then
  if [ -n "$BACKUP_FILE" ] && [ -f "$BACKUP_FILE" ]; then
    cp "$BACKUP_FILE" "$CONFIG_FILE"
    log "restored $CONFIG_FILE from $BACKUP_FILE"
  fi
  if [ "$MODE" = "add" ]; then
    die "$EX_GATEWAY" "read-back verification FAILED: route $ROUTE_ID not present exactly as specified in $CONFIG_FILE"
  else
    die "$EX_GATEWAY" "read-back verification FAILED: route $ROUTE_ID still present (or podcast allow-list entries not dropped) in $CONFIG_FILE"
  fi
fi
if [ "$MODE" = "add" ]; then
  log "read-back verified: route $ROUTE_ID present exactly once; sessionKey $SESSION_KEY; secret SecretRef by label; allow-lists merged"
else
  log "read-back verified: route $ROUTE_ID removed; podcast agent id and podcast: prefix dropped from the allow-lists"
fi

# Gateway config validation: gate only when the baseline validated (a box whose
# config was already invalid keeps its pre-existing condition, reported, not blamed).
if command -v openclaw >/dev/null 2>&1; then
  if [ "${BASELINE_RC:-1}" = "0" ]; then
    if OPENCLAW_CONFIG_PATH="$CONFIG_FILE" openclaw config validate >/dev/null 2>&1; then
      log "openclaw config validate: PASS"
    else
      if [ -n "$BACKUP_FILE" ] && [ -f "$BACKUP_FILE" ]; then
        cp "$BACKUP_FILE" "$CONFIG_FILE"
        log "restored $CONFIG_FILE from $BACKUP_FILE"
      fi
      die "$EX_GATEWAY" "openclaw config validate rejected the merged config; restored the backup (fail closed)"
    fi
  else
    log "openclaw config validate: SKIPPED (the box config did not validate before this registration; pre-existing condition, not caused here)"
  fi
else
  log "openclaw CLI not on PATH; skipped 'openclaw config validate' (structure was verified by the read-back above)"
fi

if [ "$MODE" = "remove" ]; then
  log "RESULT: removed route $ROUTE_ID from $CONFIG_FILE (pre-existing entries and every sibling route preserved)."
else
  log "RESULT: registered route $ROUTE_ID in $CONFIG_FILE."
fi
log "NEXT: apply the box's gateway restart doctrine (Mac kickstart-then-stop; Virtual Private Server compose recreate), confirm the gateway is healthy, then prove a signed test POST returns 200 and an unsigned one returns 401."
exit "$EX_OK"
