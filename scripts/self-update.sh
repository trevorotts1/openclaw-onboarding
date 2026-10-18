#!/usr/bin/env bash
# self-update.sh — v1.0.0
#
# The box's own self-update runner. Starts itself in a detached session, then:
#
#   step 1  upgrade   OpenClaw to the version the TRIGGER passes in (Mac only;
#                     skipped on a Docker box — the host side already did it)
#   step 2  update    scripts/weekly-full-update.sh (the FULL path, no terminal)
#   step 3  999-setup the 999 installer, with NINE_API_DOCS pointing at a
#                     box-local mode-600 file and no terminal attached
#   step 4  9router   install-9router-guards.sh --upgrade <pinned target>
#
# It writes ONE status file in the persistent OpenClaw root and never messages
# the client or calls a messaging tool.
#
# Exit codes (the detached child's; the launcher returns 0 once it has started):
#   0   success
#   20  upgrade failure          (oc-atomic-upgrade.sh non-zero — 78 refused,
#                                 70 rollback failed, 3 undetermined)
#   21  update failure           (weekly-full-update.sh non-zero)
#   22  refusal                  (no root, no target version, no pin, missing tools)
#   23  999 setup failure        (prereqs, no checkout, api-docs, installer rc)
#   24  9Router upgrade failure
#
# Every step is recorded, so a failure names the step that failed and the last
# line of its output. No key value is ever printed, echoed, or written to the
# status file or the log.
#
# agent-pull-fix: R5
# agent-pull-fix: R10
#
# INTERPRETER: macOS bash 3.2. No associative arrays, no mapfile, no ${x^^},
# no heredoc nested inside $( ).
set -uo pipefail

VERSION="1.0.0"
REPO_RAW="https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main"

EX_OK=0
EX_UPGRADE=20
EX_UPDATE=21
EX_REFUSE=22
EX_999=23
EX_9ROUTER=24

SELF="$0"
MODE_DETACHED=0
ROLL_ID=""
TARGET_VERSION=""
NINE9ROUTER_TARGET="${NINEROUTER_TARGET:-}"
PASSTHRU=()

# The 999 installer's own required key names (its parse_api_docs contract) and
# the plan names it validates. Aliases are included so a box that stores a key
# under its family alias is still found. NEVER printed.
KEY_NAMES="OLLAMA_API_KEY OLLAMA_CLOUD_API_KEY DEEPSEEK_API_KEY AGNES_API_KEY AGNES_AI_API_KEY OPENROUTER_API_KEY"
PLAN_NAMES="OLLAMA_PLAN AGNES_PLAN"
API_DOCS_DIR="$HOME/.config/blackceo-999"
API_DOCS_FILE="$API_DOCS_DIR/api-docs.md"

GH_AUTH="PENDING"

usage() {
  sed -n '2,30p' "$SELF"
  echo ""
  echo "Usage: self-update.sh --roll-id ID --openclaw-target X.Y.Z [--ninerouter-target VERSION]"
  echo "       self-update.sh --roll-id ID --openclaw-target X.Y.Z --foreground   (no detach; for tests)"
  echo ""
  echo "  --openclaw-target   also accepted as --target-version"
  echo "  --ninerouter-target also accepted as --9router-target"
  exit "$1"
}

# ── status ───────────────────────────────────────────────────────────────────
# One file, rewritten atomically. Only these fields, and last_line is redacted:
# a child that misbehaves must not be able to put a key in here.

_redact() {
  sed -E \
    -e 's/([A-Za-z_][A-Za-z0-9_]*(KEY|TOKEN|SECRET|PASSWORD|PASSWD))[=:][^ ]*/\1=<redacted>/g' \
    -e 's/sk-[A-Za-z0-9_-]{12,}/sk-<redacted>/g' \
    -e 's/[A-Fa-f0-9]{32,}/<redacted>/g' 2>/dev/null | cut -c1-400
}

write_status() {  # step exit_code last_line
  local t
  t="$STATUS.tmp.$$"
  {
    printf 'step=%s\n' "$1"
    printf 'roll_id=%s\n' "${ROLL_ID:-}"
    printf 'pid=%s\n' "$$"
    printf 'started_utc=%s\n' "$STARTED"
    printf 'updated_utc=%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    printf 'exit_code=%s\n' "$2"
    printf 'last_line=%s\n' "$3"
    printf 'gh_auth=%s\n' "$GH_AUTH"
    printf 'runner_version=%s\n' "$VERSION"
  } > "$t" 2>/dev/null && chmod 600 "$t" 2>/dev/null && mv -f "$t" "$STATUS" 2>/dev/null
  return 0
}

log() { printf '[self-update %s] %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"; }

last_line() { tail -n 1 "$LOG" 2>/dev/null | _redact; }

finish() {  # exit_code step
  write_status "$2" "$1" "$(last_line)"
  log "END step=$2 exit=$1"
  exit "$1"
}

# ── arguments ────────────────────────────────────────────────────────────────

while [ "$#" -gt 0 ]; do
  case "$1" in
    --roll-id)
      [ "$#" -ge 2 ] || { echo "self-update.sh: --roll-id needs a value" >&2; exit "$EX_REFUSE"; }
      ROLL_ID="$2"; shift 2 ;;
    --openclaw-target|--target-version)
      [ "$#" -ge 2 ] || { echo "self-update.sh: $1 needs a value" >&2; exit "$EX_REFUSE"; }
      TARGET_VERSION="$2"; shift 2 ;;
    --ninerouter-target|--9router-target)
      [ "$#" -ge 2 ] || { echo "self-update.sh: $1 needs a value" >&2; exit "$EX_REFUSE"; }
      NINE9ROUTER_TARGET="$2"; shift 2 ;;
    --detached)    MODE_DETACHED=1; shift ;;
    --foreground)  MODE_DETACHED=1; shift ;;
    -h|--help)     usage 0 ;;
    *) echo "self-update.sh: unknown argument: $1 (try --help)" >&2; exit "$EX_REFUSE" ;;
  esac
done

# The roll id becomes a FILENAME, so it may not carry a path separator or a
# leading dot. Anything else is a refusal, never a sanitized guess.
case "${ROLL_ID:-}" in
  "") ;;
  *[!A-Za-z0-9._-]*|.*) echo "self-update.sh: REFUSED — --roll-id may contain only A-Z a-z 0-9 . _ - and may not start with '.'" >&2; exit "$EX_REFUSE" ;;
esac

# ── root, log, status ────────────────────────────────────────────────────────

if [ -n "${OPENCLAW_ROOT:-}" ] && [ -d "${OPENCLAW_ROOT}" ]; then
  ROOT="$OPENCLAW_ROOT"
elif [ -d /data/.openclaw ]; then
  ROOT=/data/.openclaw
elif [ -d "$HOME/.openclaw" ]; then
  ROOT="$HOME/.openclaw"
else
  echo "self-update.sh: REFUSED — no OpenClaw root (tried \$OPENCLAW_ROOT, /data/.openclaw, $HOME/.openclaw)" >&2
  exit "$EX_REFUSE"
fi

# One status file and one log per ROLL, so two rolls on one box can never
# overwrite each other's run. Without a roll id the legacy single-file names
# are kept.
if [ -n "$ROLL_ID" ]; then
  STATUS_DIR="$ROOT/self-update"
  ( umask 077; mkdir -p "$STATUS_DIR" ) 2>/dev/null || {
    echo "self-update.sh: REFUSED — cannot create $STATUS_DIR" >&2; exit "$EX_REFUSE"; }
  chmod 700 "$STATUS_DIR" 2>/dev/null || true
  LOG="$STATUS_DIR/$ROLL_ID.log"
  STATUS="$STATUS_DIR/$ROLL_ID.status"
else
  mkdir -p "$ROOT/logs" 2>/dev/null || true
  LOG="$ROOT/logs/self-update.log"
  STATUS="$ROOT/self-update.status"
fi
( umask 077; : >> "$LOG" ) 2>/dev/null || {
  echo "self-update.sh: REFUSED — cannot write $LOG" >&2; exit "$EX_REFUSE"; }
chmod 600 "$LOG" 2>/dev/null || true
STARTED="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

IS_DOCKER=0
[ -f /.dockerenv ] && IS_DOCKER=1
IS_MAC=0
[ "$(uname -s)" = "Darwin" ] && IS_MAC=1

# Validate BEFORE detaching: a refusal must be visible to the trigger as a
# non-zero exit, not swallowed by a 0 from a launcher that already backgrounded
# a child destined to refuse.
if [ -z "$TARGET_VERSION" ] && [ "$IS_DOCKER" = 0 ]; then
  log "REFUSED: no --openclaw-target (the trigger must pass the version; it is never discovered)"
  write_status "preflight" "$EX_REFUSE" "no --openclaw-target"
  exit "$EX_REFUSE"
fi
if ! command -v curl >/dev/null 2>&1; then
  log "REFUSED: curl missing — cannot fetch the update scripts from main"
  write_status "preflight" "$EX_REFUSE" "curl missing"
  exit "$EX_REFUSE"
fi

# ── detach ───────────────────────────────────────────────────────────────────
# A gateway restart must never kill this. `setsid` gives a fresh session where
# the platform has it; macOS has no setsid, so the fallback is `nohup` +
# background, which already ignores SIGHUP from a dying parent shell.
# ponytail: on a Mac without setsid the child shares the session but survives
# the parent; upgrade path is a launchd job if a true new session is ever needed.

if [ "$MODE_DETACHED" = 0 ]; then
  PASSTHRU=(--detached)
  [ -n "$ROLL_ID" ] && PASSTHRU=(--roll-id "$ROLL_ID" "${PASSTHRU[@]}")
  [ -n "$TARGET_VERSION" ] && PASSTHRU=(--openclaw-target "$TARGET_VERSION" "${PASSTHRU[@]}")
  [ -n "$NINE9ROUTER_TARGET" ] && PASSTHRU=(--ninerouter-target "$NINE9ROUTER_TARGET" "${PASSTHRU[@]}")

  if command -v setsid >/dev/null 2>&1; then
    setsid nohup bash "$SELF" "${PASSTHRU[@]}" </dev/null >>"$LOG" 2>&1 &
  else
    nohup bash "$SELF" "${PASSTHRU[@]}" </dev/null >>"$LOG" 2>&1 &
  fi
  CHILD=$!
  GH_AUTH="PENDING"
  write_status "launched" 0 "detached pid=$CHILD"
  log "START detached pid=$CHILD target=${TARGET_VERSION:-none}"
  exit "$EX_OK"
fi

# ── preflight (detached child) ───────────────────────────────────────────────

log "START runner v$VERSION pid=$$ root=$ROOT roll=${ROLL_ID:-none} openclaw=${TARGET_VERSION:-none} ninerouter=${NINE9ROUTER_TARGET:-none}"

if [ ! -d "$ROOT" ]; then
  log "REFUSED: OpenClaw root vanished ($ROOT)"
  finish "$EX_REFUSE" "preflight"
fi

WORK="$(mktemp -d "${TMPDIR:-/tmp}/self-update.XXXXXX")" || {
  log "REFUSED: could not create a temp dir"
  finish "$EX_REFUSE" "preflight"
}
trap 'rm -rf "$WORK"' EXIT

fetch() {  # url dest
  curl -fsSL --max-time 60 "$1" -o "$2" >>"$LOG" 2>&1
}

# ── step 1: OpenClaw upgrade (Mac only) ──────────────────────────────────────
# The target version is the one the trigger passed. Nothing here discovers a
# version — a self-update that guesses its own destination is the defect the
# atomic upgrade exists to prevent.

if [ "$IS_DOCKER" = 1 ]; then
  log "STEP upgrade: skipped (/.dockerenv — the host side performed it)"
  write_status "upgrade-skipped" 0 "docker box: host performed the upgrade"
else
  log "STEP upgrade: OpenClaw -> $TARGET_VERSION"
  write_status "upgrade" "" "running"
  if ! fetch "$REPO_RAW/scripts/oc-atomic-upgrade.sh" "$WORK/oc-atomic-upgrade.sh" \
     || ! fetch "$REPO_RAW/scripts/oc-schema-migrate.py" "$WORK/oc-schema-migrate.py"; then
    log "FAIL upgrade: could not fetch oc-atomic-upgrade.sh / oc-schema-migrate.py from main"
    finish "$EX_UPGRADE" "upgrade"
  fi
  chmod 700 "$WORK/oc-atomic-upgrade.sh" 2>/dev/null || true
  bash "$WORK/oc-atomic-upgrade.sh" --upgrade --target-version "$TARGET_VERSION" >>"$LOG" 2>&1 </dev/null
  RC=$?
  if [ "$RC" -ne 0 ]; then
    log "FAIL upgrade: oc-atomic-upgrade.sh exited $RC"
    finish "$EX_UPGRADE" "upgrade"
  fi
  log "OK upgrade: $TARGET_VERSION"
fi

# ── step 2: weekly full update ───────────────────────────────────────────────
# The same entry point the Sunday cron uses: fetched from main, so the box
# always runs the newest version of it. It never restarts the gateway and never
# messages a client.

log "STEP update: weekly-full-update.sh"
write_status "update" "" "running"
if ! fetch "$REPO_RAW/scripts/weekly-full-update.sh" "$WORK/weekly-full-update.sh"; then
  log "FAIL update: could not fetch scripts/weekly-full-update.sh from main"
  finish "$EX_UPDATE" "update"
fi
bash "$WORK/weekly-full-update.sh" >>"$LOG" 2>&1 </dev/null
RC=$?
if [ "$RC" -ne 0 ]; then
  log "FAIL update: weekly-full-update.sh exited $RC"
  finish "$EX_UPDATE" "update"
fi
log "OK update"

# ── the Mac steps: 999 + 9Router ─────────────────────────────────────────────
# Both are macOS-only and meaningless inside a container.

if [ "$IS_MAC" = 0 ] || [ "$IS_DOCKER" = 1 ]; then
  log "STEP 999-setup: skipped (not a macOS host)"
  log "STEP 9router: skipped (not a macOS host)"
  write_status "done" 0 "non-Mac: 999 and 9Router steps skipped"
  finish "$EX_OK" "done"
fi

# ── env stores: find the box's OWN keys and plan names BY NAME ───────────────
# Presence only. Values are read exactly once, and only when the api-docs file
# has to be built — never printed, never echoed, never logged.

ENV_STORES=""
_add_store() {
  [ -n "$1" ] && [ -f "$1" ] && [ -r "$1" ] || return 0
  case "$ENV_STORES" in *"
$1"*) return 0 ;; esac
  ENV_STORES="$ENV_STORES
$1"
}
_add_store "$ROOT/secrets/.env"
_add_store "$ROOT/.env"
_add_store "$HOME/.openclaw/secrets/.env"
_add_store "$HOME/.openclaw/.env"
_add_store "/data/.openclaw/secrets/.env"
_add_store "/data/.openclaw/.env"
for _f in "$ROOT"/secrets/*.env "$HOME/.openclaw"/secrets/*.env; do
  _add_store "$_f"
done

ENV_STORE_COUNT=0
while IFS= read -r _f; do [ -n "$_f" ] && ENV_STORE_COUNT=$((ENV_STORE_COUNT + 1)); done <<EOF
$ENV_STORES
EOF
log "env stores searched: $ENV_STORE_COUNT (names only; no value is printed)"

_name_in() {  # name -> 0 when present in any store; never prints the value
  local _n _s
  _n="$1"
  while IFS= read -r _s; do
    [ -n "$_s" ] || continue
    if grep -Eq "^[[:space:]]*(export[[:space:]]+)?$_n=" "$_s" 2>/dev/null; then return 0; fi
  done <<EOF
$ENV_STORES
EOF
  return 1
}

# key_value NAME — prints the value on stdout. Caller captures it into a local
# and hands it straight to the 600 file. Callers must never log the result.
key_value() {
  local _n _s _line
  _n="$1"
  while IFS= read -r _s; do
    [ -n "$_s" ] || continue
    _line="$(grep -E "^[[:space:]]*(export[[:space:]]+)?$_n=" "$_s" 2>/dev/null | head -1)"
    [ -n "$_line" ] || continue
    _line="${_line#*=}"
    _line="${_line%"${_line##*[! ]}"}"
    case "$_line" in
      \"*\") _line="${_line#\"}"; _line="${_line%\"}" ;;
      \'*\') _line="${_line#\'}"; _line="${_line%\'}" ;;
    esac
    printf '%s' "$_line"
    return 0
  done <<EOF
$ENV_STORES
EOF
  return 1
}

FOUND_KEYS=""
for _n in $KEY_NAMES; do
  _name_in "$_n" && FOUND_KEYS="$FOUND_KEYS $_n"
done
FOUND_KEYS="${FOUND_KEYS# }"
FOUND_KEY_COUNT=0
for _n in $FOUND_KEYS; do FOUND_KEY_COUNT=$((FOUND_KEY_COUNT + 1)); done

FOUND_PLANS=""
for _n in $PLAN_NAMES; do
  _name_in "$_n" && FOUND_PLANS="$FOUND_PLANS $_n"
done
FOUND_PLANS="${FOUND_PLANS# }"

log "keys found by name: ${FOUND_KEYS:-none}"
log "plan names found: ${FOUND_PLANS:-none}"

# ── step 3: 999 setup ────────────────────────────────────────────────────────

log "STEP 999-setup"
write_status "999-setup" "" "running"

find_999() {
  local _cand _link
  for _cand in "${NINE_SETUP_REPO:-}" "$ROOT/persist-home/999-setup" "$HOME/999-setup" \
               "$ROOT/persist-home/999-setup-clean" "$HOME/Documents/999-setup" "$HOME/.claude-nine"; do
    [ -n "$_cand" ] && [ -d "$_cand" ] || continue
    [ -f "$_cand/.claude/skills/nine-router-setup/scripts/setup-macos.sh" ] || continue
    printf '%s' "$_cand"; return 0
  done
  for _link in "$HOME/.claude/skills/nine-router-setup" "$HOME/.claude-nine/skills/nine-router-setup"; do
    [ -L "$_link" ] || continue
    _cand="$(cd "$_link" 2>/dev/null && cd ../../.. 2>/dev/null && pwd -P)" || continue
    [ -n "$_cand" ] && [ -f "$_cand/.claude/skills/nine-router-setup/scripts/setup-macos.sh" ] || continue
    printf '%s' "$_cand"; return 0
  done
  return 1
}

# The installer's requirements, PROVED by executing them — the same probes its
# own preflight runs, so a failure is named here instead of halfway through
# provisioning.
check_999_prereqs() {
  local _bad=""
  [ "$(uname -s)" = "Darwin" ] || _bad="$_bad os"
  [ "$(uname -m)" = "arm64" ] || _bad="$_bad arch"
  { command -v claude >/dev/null 2>&1 || [ -x "$HOME/.local/bin/claude" ]; } || _bad="$_bad claude"
  curl --version >/dev/null 2>&1 || _bad="$_bad curl"
  osascript -e '1+1' >/dev/null 2>&1 || _bad="$_bad osascript"
  shasum -a 256 /dev/null >/dev/null 2>&1 || _bad="$_bad shasum"
  tar --version >/dev/null 2>&1 || _bad="$_bad tar"
  security list-keychains >/dev/null 2>&1 || _bad="$_bad security"
  git --version >/dev/null 2>&1 || _bad="$_bad git"
  python3 --version >/dev/null 2>&1 || _bad="$_bad python3"
  xcode-select -p >/dev/null 2>&1 || _bad="$_bad command-line-tools"
  PREREQ_MISSING="${_bad# }"
  [ -z "$PREREQ_MISSING" ]
}

NINE_REPO="$(find_999)" || NINE_REPO=""
if [ -z "$NINE_REPO" ]; then
  log "FAIL 999-setup: no 999 checkout with .claude/skills/nine-router-setup/scripts/setup-macos.sh (searched \$NINE_SETUP_REPO, <root>/persist-home, \$HOME/999-setup, \$HOME/Documents/999-setup, \$HOME/.claude-nine, skill links)"
  finish "$EX_999" "999-setup"
fi
log "999 checkout: $NINE_REPO"

if ! check_999_prereqs; then
  log "FAIL 999-setup: installer requirements not met: $PREREQ_MISSING"
  finish "$EX_999" "999-setup"
fi

NINE_SCRIPT="$NINE_REPO/.claude/skills/nine-router-setup/scripts/setup-macos.sh"

# A box that already runs 9Router never takes the installer's full path — that
# replaces the skill link and can rewire the router (shared-utils/lib-frontdoor.sh
# and nine_router_guard.py both enforce this). Such a box gets --skills-only.
NINE_MODE="full"
if [ -d "$HOME/.9router" ] || [ -f "$HOME/.local/bin/claude-nine" ]; then
  NINE_MODE="skills-only"
  log "999-setup: 9Router detected — using --skills-only (never the full installer)"
fi

if [ "$NINE_MODE" = "full" ]; then
  if [ "$FOUND_KEY_COUNT" -eq 0 ]; then
    log "FAIL 999-setup: no known key name found in any of the $ENV_STORE_COUNT env stores"
    finish "$EX_999" "999-setup"
  fi

  # Build the installer's credential file OUTSIDE the client's Documents, mode
  # 600, from the box's own stores. Values go into this one file and nowhere
  # else: not stdout, not the log, not the status file.
  umask 077
  mkdir -p "$API_DOCS_DIR" 2>/dev/null || { log "FAIL 999-setup: cannot create $API_DOCS_DIR"; finish "$EX_999" "999-setup"; }
  chmod 700 "$API_DOCS_DIR" 2>/dev/null || true
  API_TMP="$API_DOCS_FILE.tmp.$$"
  : > "$API_TMP" 2>/dev/null || { log "FAIL 999-setup: cannot write $API_TMP"; finish "$EX_999" "999-setup"; }
  WROTE=0
  for _n in $KEY_NAMES; do
    _v="$(key_value "$_n")" || continue
    [ -n "$_v" ] || continue
    printf '%s=%s\n' "$_n" "$_v" >> "$API_TMP" 2>/dev/null || { log "FAIL 999-setup: write to $API_TMP failed"; finish "$EX_999" "999-setup"; }
    WROTE=$((WROTE + 1))
  done
  unset _v
  # Plan names are only written when they are one of the values the installer
  # validates; anything else would fail its own check later.
  _v="$(key_value OLLAMA_PLAN)"
  case "$_v" in
    free|pro|max) printf 'OLLAMA_PLAN=%s\n' "$_v" >> "$API_TMP" ;;
  esac
  _v="$(key_value AGNES_PLAN)"
  case "$_v" in
    starter|plus|pro) printf 'AGNES_PLAN=%s\n' "$_v" >> "$API_TMP" ;;
  esac
  unset _v

  if [ "$WROTE" -eq 0 ]; then
    rm -f "$API_TMP" 2>/dev/null
    log "FAIL 999-setup: no readable key values in the env stores"
    finish "$EX_999" "999-setup"
  fi
  chmod 600 "$API_TMP" 2>/dev/null && mv -f "$API_TMP" "$API_DOCS_FILE" 2>/dev/null || {
    rm -f "$API_TMP" 2>/dev/null
    log "FAIL 999-setup: could not install $API_DOCS_FILE mode 600"
    finish "$EX_999" "999-setup"
  }
  log "999-setup: wrote $API_DOCS_FILE (mode 600, $WROTE credential name(s); the client's Documents file was not touched)"
fi

# No terminal attached: </dev/null, and the GitHub sign-in prompts disabled.
# gh auth stays PENDING — an interactive login is never attempted from here.
GH_AUTH="PENDING"
if [ "$NINE_MODE" = "full" ]; then
  NINE_API_DOCS="$API_DOCS_FILE" GIT_TERMINAL_PROMPT=0 GH_PROMPT_DISABLED=1 \
    bash "$NINE_SCRIPT" >>"$LOG" 2>&1 </dev/null
else
  NINE_API_DOCS="$API_DOCS_FILE" GIT_TERMINAL_PROMPT=0 GH_PROMPT_DISABLED=1 \
    bash "$NINE_SCRIPT" --skills-only >>"$LOG" 2>&1 </dev/null
fi
RC=$?
if [ "$RC" -ne 0 ]; then
  log "FAIL 999-setup: setup-macos.sh ($NINE_MODE) exited $RC"
  finish "$EX_999" "999-setup"
fi
log "OK 999-setup ($NINE_MODE); gh_auth=PENDING"

# ── step 4: 9Router upgrade to the pinned target ─────────────────────────────

log "STEP 9router"
write_status "9router" "" "running"

GUARDS="$NINE_REPO/.claude/skills/nine-router-setup/scripts/macos/install-9router-guards.sh"
if [ ! -f "$GUARDS" ]; then
  log "FAIL 9router: install-9router-guards.sh not found at $GUARDS"
  finish "$EX_9ROUTER" "9router"
fi
if [ -z "$NINE9ROUTER_TARGET" ]; then
  log "REFUSED 9router: no pinned target (pass --9router-target VERSION or set NINEROUTER_TARGET); never upgrading to an unpinned latest"
  finish "$EX_REFUSE" "9router"
fi

bash "$GUARDS" --upgrade "$NINE9ROUTER_TARGET" >>"$LOG" 2>&1 </dev/null
RC=$?
if [ "$RC" -ne 0 ]; then
  log "FAIL 9router: install-9router-guards.sh --upgrade $NINE9ROUTER_TARGET exited $RC"
  finish "$EX_9ROUTER" "9router"
fi
log "OK 9router: $NINE9ROUTER_TARGET"

write_status "done" 0 "all steps complete"
finish "$EX_OK" "done"
