#!/usr/bin/env bash
# =============================================================================
# regenerate-gateway-env.sh — FIX-14: wire MC_API_TOKEN + MISSION_CONTROL_URL
# into the gateway service-env regeneration list.
# -----------------------------------------------------------------------------
# Error 8 / D-8 (2026-08-06 audit): MC_API_TOKEN was NOT in the gateway env, so
# every Command Center board write / deliverable registration silently 401'd for
# ~15 days. FIX-14's durable fix has two halves:
#
#   1. REGRESSION GUARD (check_agent_env.py): the probe that FAILS LOUD whenever
#      the presentation agent's runtime env lacks the token or the token is not
#      in the managed-keys regeneration list.
#   2. THIS HELPER (regenerate-gateway-env.sh): the one script that APPENDS the
#      two labels to OPENCLAW_SERVICE_MANAGED_ENV_KEYS in the gateway service-env
#      file, and (when a value is available from the live process env or the box
#      secrets store) ensures MC_API_TOKEN + MISSION_CONTROL_URL are exported in
#      that file too — the ONLY env the launchd gateway process sees on a Mac.
#
# On a Mac the launchd gateway (~/Library/LaunchAgents/ai.openclaw.gateway.plist)
# does NOT inherit the GUI session env; its ProgramArguments exec an env-wrapper
# whose first job is to source a service-env file (fleet default
# ~/.openclaw/service-env/ai.openclaw.gateway.env), and that file is the ONLY env
# the gateway process sees. A label absent there can never resolve in the agent
# runtime. OPENCLAW_SERVICE_MANAGED_ENV_KEYS is the regeneration allow-list that
# file is rebuilt from: a token present in a store but missing from that list is
# dropped on the next regeneration (the exact regression shape). So this helper
# edits the managed list in place, keeping every pre-existing member.
#
# BEHAVIOR (idempotent, fail-closed on the file, best-effort on values):
#   - Resolves the gateway service-env file: $SVC_ENV override, else the *.env
#     entry of the launchd plist ProgramArguments, else the fleet default.
#   - Backs up the file (0600) before any mutation.
#   - Appends MC_API_TOKEN and MISSION_CONTROL_URL to the
#     OPENCLAW_SERVICE_MANAGED_ENV_KEYS value if absent (preserving all others).
#   - When MC_API_TOKEN / MISSION_CONTROL_URL are SET in the live process env, and
#     the label is absent from the env file, appends `export LABEL=value` (value
#     never printed). When only the secrets store carries them, prints the manual
#     add instruction instead of reading a store value into the file (the secrets
#     store is the box's own store — the operator exports it before a regenerate).
#   - After writing, verifies by read-back: both labels in the managed list and
#     (when exported) both labels present as `export LABEL=` lines.
#
# SECURITY: values are NEVER printed, echoed, or logged. Only label names and
# SET/NOT-SET presence. The backup is written 0600 under the same directory.
#
# GATEWAY RESTART: this script writes and verifies the env file; it does NOT
# restart the gateway. Apply the box's restart doctrine (Mac kickstart-then-stop:
# `openclaw daemon restart`) after a first-time run so the new labels activate.
#
#   bash regenerate-gateway-env.sh --docker   # FIX-73: same wire on the docker
#                    VPS layout — resolves the container secrets store
#                    /data/.openclaw/secrets/.env (SVC_ENV still overrides for
#                    tests), wires the managed list there, and prints the
#                    `docker compose up -d --force-recreate` instruction (a
#                    plain `docker compose restart` does NOT reload env changes).
#
# USAGE:
#   bash regenerate-gateway-env.sh            # wire the two MC labels in
#   bash regenerate-gateway-env.sh --check    # read-only: report current state
#   bash regenerate-gateway-env.sh --dry-run  # print planned mutations, write nothing
#   bash regenerate-gateway-env.sh --docker   # FIX-73: wire on the docker VPS layout
#
# ENV:
#   SVC_ENV          override the gateway service-env file path (test seam).
#   MC_API_TOKEN     when SET in the live process env, also exported into the file.
#   MISSION_CONTROL_URL  same.
#   OPENCLAW_GATEWAY_PLIST  override the launchd plist path inspected to find the
#                    service-env file (test seam).
#   OPENCLAW_SECRETS  override the docker secrets store path (test seam; the
#                    live container path is /data/.openclaw/secrets/.env).
#
# EXIT:
#   0  wired (or already wired / dry-run planned / read-only check)
#   2  fail-closed: cannot resolve or read the env file, or read-back verification
#      failed after a write
# =============================================================================
set -u

PROG="$(basename "$0")"
MANAGED="OPENCLAW_SERVICE_MANAGED_ENV_KEYS"
MC_LABELS="MC_API_TOKEN MISSION_CONTROL_URL"
EX_OK=0
EX_REFUSED=2

log() { printf '%s\n' "$*" >&2; }
die() { local code="$1"; shift; log "HARD STOP ($code): $*"; exit "$code"; }

MODE="wire"
DRY_RUN=0
PLATFORM_MODE="mac"
for a in "$@"; do
  case "$a" in
    --check)  MODE="check" ;;
    --dry-run) DRY_RUN=1 ;;
    --docker) PLATFORM_MODE="docker" ;;
    -h|--help) sed -n '2,92p' "$0" | sed 's/^# \{0,1\}//' >&2; exit "$EX_OK" ;;
    *) die "$EX_REFUSED" "unknown argument: $a" ;;
  esac
done

# --------------------------------------------------------------------------- #
# Resolve the gateway service-env file (same resolution the podcast hook uses):
# SVC_ENV override -> the last existing *.env entry of the launchd plist
# ProgramArguments -> the fleet default. Prints the path, or nothing when
# unresolvable (the caller then fails closed).
# --------------------------------------------------------------------------- #
gateway_plist_program_args() {
  local plist="$1"
  PLIST_PATH="$plist" python3 - <<'PY' 2>/dev/null || true
import os, plistlib
try:
    with open(os.environ["PLIST_PATH"], "rb") as fh:
        pl = plistlib.load(fh)
except Exception:
    raise SystemExit(0)
args = pl.get("ProgramArguments") if isinstance(pl, dict) else None
if isinstance(args, list):
    for a in args:
        if isinstance(a, str) and a.startswith("/"):
            print(a)
PY
}

resolve_gateway_service_env_file() {
  local plist candidate
  if [ -n "${SVC_ENV:-}" ]; then
    if [ -f "${SVC_ENV}" ]; then
      printf '%s\n' "${SVC_ENV}"
    fi
    return 0
  fi
  plist="${OPENCLAW_GATEWAY_PLIST:-$HOME/Library/LaunchAgents/ai.openclaw.gateway.plist}"
  if [ -f "$plist" ]; then
    local args last_env
    args="$(gateway_plist_program_args "$plist")"
    last_env=""
    if [ -n "$args" ]; then
      while IFS= read -r candidate; do
        case "$candidate" in
          *.env) [ -f "$candidate" ] && last_env="$candidate" ;;
        esac
      done <<<"$args"
    fi
    if [ -n "$last_env" ]; then
      printf '%s\n' "$last_env"
      return 0
    fi
  fi
  local fallback="$HOME/.openclaw/service-env/ai.openclaw.gateway.env"
  if [ -f "$fallback" ]; then
    printf '%s\n' "$fallback"
  fi
  return 0
}

# --------------------------------------------------------------------------- #
# FIX-73: docker/VPS resolution. The container has no launchd plist and no
# ~/Library LaunchAgents tree; the gateway env the engine reads lives in the
# container secrets store /data/.openclaw/secrets/.env (the path
# presentation_job/oc_paths.py lists FIRST for the vps layout, and the path the
# 2026-08-30 fleet envsync proved the docker gateway and every reader consume).
# SVC_ENV still overrides (the test seam), then $OPENCLAW_SECRETS, then the
# canonical container path. Prints the path, or nothing when unresolvable.
# --------------------------------------------------------------------------- #
resolve_docker_secrets_env_file() {
  if [ -n "${SVC_ENV:-}" ]; then
    if [ -f "${SVC_ENV}" ]; then
      printf '%s\n' "${SVC_ENV}"
    fi
    return 0
  fi
  if [ -n "${OPENCLAW_SECRETS:-}" ]; then
    if [ -f "${OPENCLAW_SECRETS}" ]; then
      printf '%s\n' "${OPENCLAW_SECRETS}"
    fi
    return 0
  fi
  local candidate="/data/.openclaw/secrets/.env"
  if [ -f "$candidate" ]; then
    printf '%s\n' "$candidate"
  fi
  return 0
}

print_docker_next_steps() {
  log "NEXT (docker): a plain 'docker compose restart' does NOT reload env changes — the container"
  log "      must be RECREATED to pick the keys up: cd <compose project dir> && docker compose up -d --force-recreate"
  log "      Then prove the runtime carries the token (value never printed):"
  log "      docker exec openclaw printenv MC_API_TOKEN | wc -c   # must be > 1"
  log "      and re-run check_agent_env.py — it must exit 0."
}

# --------------------------------------------------------------------------- #
# Read helpers (all label-only; never a value).
# --------------------------------------------------------------------------- #
# Current value of a label in the env file ("" when absent). Parses both the
# bare KEY= and export KEY= forms the service-env file uses.
env_file_value() {
  local env_file="$1" label="$2"
  ENV_FILE="$env_file" ENV_LABEL="$label" python3 - <<'PY'
import os, re
p = os.environ["ENV_FILE"]; label = os.environ["ENV_LABEL"]
try:
    text = open(p, encoding="utf-8", errors="replace").read()
except OSError:
    raise SystemExit(0)
for line in text.splitlines():
    m = re.match(r'^\s*(?:export\s+)?' + re.escape(label) + r'\s*=\s*(.*)$', line)
    if m:
        v = m.group(1).strip().strip('"').strip("'")
        print(v)
        raise SystemExit(0)
raise SystemExit(0)
PY
}

# True (0) when the label is defined in the env file.
env_file_has_label() {
  local env_file="$1" label="$2" v
  v="$(env_file_value "$env_file" "$label")"
  [ -n "$v" ]
}

# True (0) when the label is set in the live process env.
proc_has() { [ -n "${!1:-}" ]; }

managed_list_has() {
  local env_file="$1" label="$2" list
  list="$(env_file_value "$env_file" "$MANAGED")"
  case ",${list}," in
    *,${label},*) return 0 ;;
    *) return 1 ;;
  esac
}

# --------------------------------------------------------------------------- #
# State report (label-only).
# --------------------------------------------------------------------------- #
report_state() {
  local env_file="$1" list
  list="$(env_file_value "$env_file" "$MANAGED")"
  log "gateway service-env: $env_file"
  log "  $MANAGED present: $(env_file_has_label "$env_file" "$MANAGED" && echo yes || echo NO)"
  for lbl in MC_API_TOKEN MISSION_CONTROL_URL; do
    local in_list="NO" in_file="NO" in_proc="NO"
    [ -n "$list" ] && case ",${list}," in *,${lbl},*) in_list="YES" ;; esac
    env_file_has_label "$env_file" "$lbl" && in_file="YES"
    proc_has "$lbl" && in_proc="YES"
    log "  ${lbl}: managed_list=${in_list} env_file=${in_file} live_process=${in_proc}"
  done
}

# --------------------------------------------------------------------------- #
# The mutation: append the two labels to the managed list and (when the value is
# available in the live process env) export each label into the file. python3
# stdlib does the edit with a 0600 backup; values never touch the terminal.
# --------------------------------------------------------------------------- #
apply_wire() {
  local env_file="$1"
  ENV_FILE="$env_file" python3 - <<'PY'
import datetime, os, re, shutil, sys, tempfile

path = os.environ["ENV_FILE"]
managed_label = "OPENCLAW_SERVICE_MANAGED_ENV_KEYS"
want = ["MC_API_TOKEN", "MISSION_CONTROL_URL"]

def env_file_value_of(env_path, label):
    try:
        t = open(env_path, encoding="utf-8", errors="replace").read()
    except OSError:
        return ""
    for ln in t.splitlines():
        m = re.match(r'^\s*(?:export\s+)?' + re.escape(label) + r'\s*=\s*(.*)$', ln)
        if m:
            return m.group(1).strip().strip('"').strip("'")
    return ""

try:
    text = open(path, encoding="utf-8", errors="replace").read()
except OSError as exc:
    sys.stderr.write("cannot read %s: %s\n" % (path, exc)); sys.exit(2)

lines = text.split("\n")
# Extract the managed-list value (bare KEY= or export KEY=), if present.
managed_value = None
managed_idx = None
for i, ln in enumerate(lines):
    m = re.match(r"^\s*(?:export\s+)?" + re.escape(managed_label) + r"\s*=\s*(.*)$", ln)
    if m:
        managed_value = m.group(1).strip().strip('"').strip("'")
        managed_idx = i
        break

new_managed = []
if managed_value:
    for x in managed_value.split(","):
        x = x.strip()
        if x and x not in new_managed:
            new_managed.append(x)
else:
    # No managed-list label yet: seed it from the two MC labels only (the file's
    # other labels may already be exported explicitly; the managed list is an
    # allow-list that grows, never shrinks on a regenerate).
    pass

added = []
for lbl in want:
    if lbl not in new_managed:
        new_managed.append(lbl); added.append(lbl)

changed = False
# Rewrite the managed-list line.
managed_line = "export %s=%s" % (managed_label, ",".join(new_managed))
if managed_idx is not None:
    if lines[managed_idx] != managed_line:
        lines[managed_idx] = managed_line; changed = True
else:
    lines.append(managed_line); changed = True

# Export each wanted label into the file when the live process env carries it
# and the label is not already defined (never overwrite an existing value).
already = set()
for ln in lines:
    m = re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", ln)
    if m:
        already.add(m.group(1))

docker_mode = os.environ.get("FIX73_DOCKER_MODE", "") == "1"
store_val = {}
if docker_mode:
    for lbl in want:
        store_val[lbl] = env_file_value_of(env_path=path, label=lbl)

for lbl in want:
    val = os.environ.get(lbl, "")
    if not val and docker_mode:
        val = store_val.get(lbl, "")
    if val and lbl not in already:
        lines.append("export %s=%s" % (lbl, val)); changed = True

new_text = "\n".join(lines)
if not new_text.endswith("\n"):
    new_text += "\n"

if not changed:
    print("UNCHANGED")
    sys.exit(0)

ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
backup = path + ".bak-fix14." + ts
try:
    shutil.copy2(path, backup); os.chmod(backup, 0o600)
except OSError:
    backup = ""
st_mode = os.stat(path).st_mode & 0o777
d = os.path.dirname(path) or "."
fd, tmp = tempfile.mkstemp(prefix=".gateway-env.", suffix=".tmp", dir=d)
try:
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(new_text)
    os.chmod(tmp, st_mode)
    os.replace(tmp, path)
except Exception:
    try: os.unlink(tmp)
    except OSError: pass
    raise
print("WRITTEN %s" % backup)
PY
}

# --------------------------------------------------------------------------- #
# Read-back verification: both labels in the managed list; each exported label
# present as a definition. Never a value.
# --------------------------------------------------------------------------- #
verify_wire() {
  local env_file="$1" list ok=0
  list="$(env_file_value "$env_file" "$MANAGED")"
  for lbl in MC_API_TOKEN MISSION_CONTROL_URL; do
    case ",${list}," in
      *,${lbl},*) ;;
      *) log "VERIFY FAIL: ${lbl} NOT in ${MANAGED}"; ok=1 ;;
    esac
    # FIX-73 (docker): on the docker layout the secrets file IS the runtime env
    # source the gateway is recreated from, so a label missing from the file
    # itself is a fail even when the live process env does not carry it (on a
    # Mac the label is injected at regeneration time, so only the
    # live-process-carries-it case can be proven here).
    if [ "$PLATFORM_MODE" = "docker" ]; then
      if ! env_file_has_label "$env_file" "$lbl"; then
        log "VERIFY FAIL: ${lbl} missing from ${env_file} (docker secrets store is the runtime env source)"
        ok=1
      fi
    elif proc_has "$lbl"; then
      if ! env_file_has_label "$env_file" "$lbl"; then
        log "VERIFY FAIL: ${lbl} missing from ${env_file} (live process env carries it)"
        ok=1
      fi
    fi
  done
  return "$ok"
}

# --------------------------------------------------------------------------- #
# Main.
# --------------------------------------------------------------------------- #
if [ "$PLATFORM_MODE" = "docker" ]; then
  ENV_FILE="$(resolve_docker_secrets_env_file)"
  if [ -z "$ENV_FILE" ]; then
    die "$EX_REFUSED" "cannot resolve the docker secrets env file (no /data/.openclaw/secrets/.env, no \$OPENCLAW_SECRETS pointer, and no SVC_ENV override). Run this inside the openclaw container, or set SVC_ENV to the host-side bind-mount path (/docker/<project>/data/.openclaw/secrets/.env)."
  fi
else
  ENV_FILE="$(resolve_gateway_service_env_file)"
  if [ -z "$ENV_FILE" ]; then
    die "$EX_REFUSED" "cannot resolve the gateway service-env file (launchd plist not found at $HOME/Library/LaunchAgents/ai.openclaw.gateway.plist, or it carries no *.env argument, and no $HOME/.openclaw/service-env/ai.openclaw.gateway.env). Set SVC_ENV to point at it."
  fi
fi
[ -f "$ENV_FILE" ] || die "$EX_REFUSED" "gateway env file not found at $ENV_FILE"
[ -r "$ENV_FILE" ] || die "$EX_REFUSED" "gateway env file not readable at $ENV_FILE"

if [ "$MODE" = "check" ]; then
  report_state "$ENV_FILE"
  if [ "$PLATFORM_MODE" = "docker" ]; then
    print_docker_next_steps
  fi
  exit "$EX_OK"
fi

report_state "$ENV_FILE"

if [ "$DRY_RUN" = "1" ]; then
  log "dry-run: planned wire of MC_API_TOKEN + MISSION_CONTROL_URL into $MANAGED (and export each when the live process env carries it); nothing written (exit 0)"
  if [ "$PLATFORM_MODE" = "docker" ]; then
    print_docker_next_steps
  fi
  exit "$EX_OK"
fi

# Root guard: env-file writes must run as the gateway runtime user, never root.
if [ "$(id -u)" = "0" ]; then
  die "$EX_REFUSED" "running as root is refused; env-file writes must run as the gateway runtime user (re-run as the node user)"
fi

FIX73_DOCKER_MODE=$([ "$PLATFORM_MODE" = "docker" ] && echo 1 || echo 0) \
  OUT="$(apply_wire "$ENV_FILE")" || die "$EX_REFUSED" "wire failed for $ENV_FILE (see message above)"
if [ "$OUT" = "UNCHANGED" ]; then
  log "RESULT: no-op. MC_API_TOKEN + MISSION_CONTROL_URL already in $MANAGED (nothing rewritten)."
else
  BACKUP="${OUT#WRITTEN }"
  [ -n "$BACKUP" ] && log "backup written: $BACKUP"
  log "RESULT: wired MC_API_TOKEN + MISSION_CONTROL_URL into $MANAGED in $ENV_FILE"
fi

verify_wire "$ENV_FILE" || die "$EX_REFUSED" "read-back verification FAILED after the write; restoring requires the operator to re-run against the backup ($ENV_FILE.bak-fix14.*)"

if [ "$PLATFORM_MODE" = "docker" ]; then
  print_docker_next_steps
else
  log "NEXT: apply the box's gateway restart doctrine (Mac: openclaw daemon restart), then re-run check_agent_env.py — it must exit 0."
fi
log "      Then prove a board write authenticates: run the dept verify or dispatch a test presentation task."
exit "$EX_OK"
