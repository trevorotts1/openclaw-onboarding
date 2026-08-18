#!/usr/bin/env bash
#  PRD 2.1 -- unified repo (trevorotts1/openclaw-onboarding)
#
#  NOTE: this script REQUIRES bash (uses process substitution `< <(...)`, `[[ ]]`,
#  and bash arrays). Without the shebang above `./update-skills.sh` was executed by
#  the caller's login shell (sh/zsh on some boxes), where `< <(...)` is a syntax
#  error, forcing agents to fall back to `bash update-skills.sh`. The shebang makes
#  a direct `./update-skills.sh` invocation always run under bash. (v16.2.12)
#
#  Platform auto-detected via OPENCLAW_PLATFORM env var or presence of /data/.openclaw.
#  VPS: sources platform/vps/bootstrap.sh for container re-exec + path setup.
#  Mac: sources platform/mac/bootstrap.sh for Homebrew prereqs + path setup.
# ============================================================

# Platform detection + bootstrap (MUST run before set -euo pipefail -- VPS container
# re-exec uses conditional commands that may fail intentionally).
_DETECT_PLATFORM="${OPENCLAW_PLATFORM:-}"
if [ -z "$_DETECT_PLATFORM" ]; then
    [ -d "/data/.openclaw" ] && _DETECT_PLATFORM="vps" || _DETECT_PLATFORM="mac"
fi
export OPENCLAW_PLATFORM="$_DETECT_PLATFORM"

_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || pwd)"

# ----------------------------------------------------------
# PRE-BOOTSTRAP SELF-SYNC GUARD
# ----------------------------------------------------------
# This must stay above the platform bootstrap. The Mac bootstrap owns the
# power-resilience check; an old checkout used to reach that check (and exit
# 78) before it had any chance to fetch the update that made routine updates
# advisory. Keeping self-sync bootstrap-independent lets an auto-syncing stale
# checkout refresh and re-exec first. No platform variables or prerequisites
# beyond git are used here.
self_sync_guard() {
  [ "${OPENCLAW_UPDATE_SKIP_SELF_SYNC:-0}" = "1" ] && { echo "  [self-sync] skipped (OPENCLAW_UPDATE_SKIP_SELF_SYNC=1)"; return 0; }
  [ "${OPENCLAW_UPDATE_SELF_SYNCED:-0}" = "1" ] && { echo "  [self-sync] already re-exec'd from origin/main — proceeding"; return 0; }

  local src="${BASH_SOURCE[0]:-}"
  case "$src" in
    ""|bash|sh|-bash|-sh) echo "  [self-sync] running via pipe (no local checkout) — fresh by definition, skipping"; return 0 ;;
  esac
  [ -f "$src" ] || { echo "  [self-sync] script path not a regular file — skipping"; return 0; }
  command -v git >/dev/null 2>&1 || { echo "  [self-sync] git not available — skipping (cannot verify checkout currency)"; return 0; }

  local repo_root origin dirty="" behind="" local_sha remote_sha
  repo_root="$(cd "$_SCRIPT_DIR" && git rev-parse --show-toplevel 2>/dev/null || true)"
  [ -n "$repo_root" ] || { echo "  [self-sync] not a git checkout — skipping (likely a copied script)"; return 0; }
  origin="$(git -C "$repo_root" remote get-url origin 2>/dev/null || true)"
  case "$origin" in
    *trevorotts1/openclaw-onboarding*) : ;;
    *) echo "  [self-sync] checkout origin is not the onboarding repo — skipping self-sync"; return 0 ;;
  esac

  [ -n "$(git -C "$repo_root" status --porcelain 2>/dev/null)" ] && dirty=1
  git -C "$repo_root" fetch --quiet origin main 2>/dev/null || echo "  [self-sync] WARN: git fetch failed — currency check may be stale"
  local_sha="$(git -C "$repo_root" rev-parse HEAD 2>/dev/null || true)"
  remote_sha="$(git -C "$repo_root" rev-parse origin/main 2>/dev/null || true)"
  [ -n "$remote_sha" ] && [ "$local_sha" != "$remote_sha" ] && behind=1

  if [ -z "$dirty" ] && [ -z "$behind" ]; then
    echo "  [self-sync] local checkout is clean and current with origin/main — proceeding"
    return 0
  fi

  if [ "${OPENCLAW_UPDATE_AUTO_SYNC:-0}" = "1" ]; then
    echo "  [self-sync] checkout is $( [ -n "$dirty" ] && printf 'DIRTY ' )$( [ -n "$behind" ] && printf 'BEHIND ' )— OPENCLAW_UPDATE_AUTO_SYNC=1: hard-syncing to origin/main"
    git -C "$repo_root" fetch origin main
    git -C "$repo_root" reset --hard origin/main
    echo "  [self-sync] re-syncing complete — re-exec'ing the intended version before platform bootstrap"
    OPENCLAW_UPDATE_SELF_SYNCED=1 exec bash "$src" "${SELF_SYNC_ARGS[@]+"${SELF_SYNC_ARGS[@]}"}"
  fi

  echo "" >&2
  echo "ERROR (self-sync): refusing to wire from a $( [ -n "$dirty" ] && printf 'DIRTY ' )$( [ -n "$behind" ] && printf 'STALE/BEHIND ' )local checkout." >&2
  echo "  Checkout: $repo_root" >&2
  echo "  Local HEAD:  ${local_sha:-unknown}" >&2
  echo "  origin/main: ${remote_sha:-unknown}" >&2
  echo "" >&2
  echo "  Wiring from a stale checkout installs the OLD version. Resolve, then re-run:" >&2
  echo "    git -C \"$repo_root\" fetch origin main && git -C \"$repo_root\" reset --hard origin/main" >&2
  echo "  OR run the curl path (always fresh):" >&2
  echo "    curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/update-skills.sh | bash" >&2
  echo "  OR re-run with auto-sync (destructive — discards local changes):" >&2
  echo "    OPENCLAW_UPDATE_AUTO_SYNC=1 bash \"$src\"" >&2
  exit 1
}

# Capture argv before anything capable of aborting, then self-sync before the
# platform bootstrap (including the FileVault/power-resilience check).
SELF_SYNC_ARGS=("$@")
self_sync_guard

# DEFECT 3 (v13.1.3) — PLATFORM unbound-variable guard.
# A stale/dirty checkout of this script (pre-fix) referenced a bare $PLATFORM in
# the stale-artifact detection block (~line 1431 of that version) that was never
# assigned; under `set -euo pipefail` (active below) the first reference aborted
# with "PLATFORM: unbound variable" and the .onboarding-version stamp never wrote.
# Initialize PLATFORM here (aliased to the canonical OPENCLAW_PLATFORM) BEFORE any
# possible use so the script is robust even if any code path references the bare
# name. The canonical variable remains OPENCLAW_PLATFORM.
PLATFORM="${PLATFORM:-$OPENCLAW_PLATFORM}"
export PLATFORM

# This is the ROUTINE-UPDATE entrypoint, not first-time provisioning. Tell the
# platform bootstrap so its power-outage pre-flight only ADVISES (never aborts)
# on a FileVault-on / no-auto-login box: a live update over an existing
# connection does not require the box to survive a power cut, so that physical-
# security posture must not block the update. install.sh (provisioning) leaves
# this unset and keeps the hard gate. Exported so it survives the self-sync
# re-exec below. (Mac power-resilience gate scoping.)
export OPENCLAW_BOOTSTRAP_MODE=update

_PLATFORM_BOOTSTRAP="${_SCRIPT_DIR}/platform/${OPENCLAW_PLATFORM}/bootstrap.sh"
if [ -f "$_PLATFORM_BOOTSTRAP" ]; then
    # shellcheck source=/dev/null
    source "$_PLATFORM_BOOTSTRAP"
else
    # Inline minimal fallback when running via curl (no local clone yet).
    if [ "$OPENCLAW_PLATFORM" = "vps" ]; then
        OC_PLATFORM="vps"; OC_CONFIG="/data/.openclaw"; OC_JSON="/data/.openclaw/openclaw.json"
        OC_SKILLS_DIR="/data/.openclaw/skills"; OC_WORKSPACE_DEFAULT="/data/.openclaw/workspace"
    else
        OC_PLATFORM="mac"; OC_CONFIG="$HOME/.openclaw"; OC_JSON="$HOME/.openclaw/openclaw.json"
        OC_SKILLS_DIR="$HOME/.openclaw/skills"; OC_WORKSPACE_DEFAULT="$HOME/.openclaw/workspace"
    fi
fi

set -euo pipefail

ONBOARDING_VERSION="v22.0.40"

LOG_FILE="/tmp/openclaw-update-$(date +%Y%m%d-%H%M%S).log"

#=== BEGIN FLEET-STANDING-GATE-V1 ===
# ============================================================
#  FLEET STANDING GATE -- the single chokepoint for entitlement.
#
#  WHY HERE: a client box can be updated three different ways --
#    1. the Sunday `openclaw cron` job (client-facing, cron-prompt.txt)
#    2. the legacy silent shell cron (.update-restart-if-needed)
#    3. the operator's fleet-roll SSH push
#  ALL THREE ultimately execute THIS script. Gating each caller
#  separately means three patches and three chances to miss one; a
#  single early exit here covers every path at once.
#
#  FAIL OPEN -- READ THIS BEFORE CHANGING ANYTHING:
#  Only an EXPLICIT `blocked` verdict stops an update. Unreachable
#  gate, HTTP error, malformed reply, missing config, unknown box --
#  every one of those PROCEEDS with the update. The reason is
#  asymmetric blast radius: wrongly blocking freezes updates across
#  the entire fleet the moment n8n hiccups, while wrongly allowing
#  costs one update cycle for one delinquent box. Never "harden"
#  this into fail-closed.
#
#  A box that has never been provisioned with the gate env vars is
#  therefore unaffected -- this change is backward compatible and
#  inert until FLEET_STANDING_GATE_URL is seeded.
#
#  Escape hatches:
#    FLEET_STANDING_GATE_BYPASS=1   skip the gate entirely (operator)
#    FLEET_STANDING_GATE_SHADOW=1   report the verdict, never block
#
#  NEVER prints the header secret.
# ============================================================

fleet_standing_resolve_slug() {
    # 1. explicit env  2. openclaw.json env.vars  3. hostname
    if [ -n "${FLEET_STANDING_BOX_SLUG:-}" ]; then
        printf '%s' "$FLEET_STANDING_BOX_SLUG"; return 0
    fi
    local json="${OC_JSON:-}"
    if [ -n "$json" ] && [ -f "$json" ] && command -v python3 >/dev/null 2>&1; then
        local from_json
        from_json="$(python3 -c "
import json,sys
try:
    d=json.load(open(sys.argv[1]))
    print(((d.get('env') or {}).get('vars') or {}).get('FLEET_STANDING_BOX_SLUG','') or '')
except Exception:
    print('')
" "$json" 2>/dev/null || printf '')"
        if [ -n "$from_json" ]; then printf '%s' "$from_json"; return 0; fi
    fi
    hostname -s 2>/dev/null || printf ''
}

# Remove the "## Update held -- account not current" notice this gate appends on a
# `blocked` verdict, once the account is current again. Fenced by
# <!-- OPENCLAW_UPDATE_HELD_BILLING:<ts> --> … <!-- OPENCLAW_UPDATE_HELD_BILLING_END -->
# so ONLY that block is removed; every other line of AGENTS.md is preserved
# byte-for-byte, and a file with no notice is left completely untouched (no
# rewrite, no backup). Never fails the run.
fleet_standing_clear_held_notice() {
    local agents_md="${OC_CONFIG:-$HOME/.openclaw}/AGENTS.md"
    [ -f "$agents_md" ] || return 0
    grep -qF "OPENCLAW_UPDATE_HELD_BILLING" "$agents_md" 2>/dev/null || return 0
    command -v python3 >/dev/null 2>&1 || return 0
    AGENTS_MD="$agents_md" python3 - <<'PYEOF' 2>/dev/null || true
import os, re, time

p = os.environ["AGENTS_MD"]
try:
    with open(p, encoding="utf-8", errors="surrogateescape") as fh:
        original = fh.read()
except Exception:
    raise SystemExit(0)

pattern = re.compile(
    r'\n*<!--\s*OPENCLAW_UPDATE_HELD_BILLING:[^\n]*-->\n'
    r'(?:(?!<!--\s*OPENCLAW_UPDATE_HELD_BILLING_END\s*-->).*\n?)*'
    r'<!--\s*OPENCLAW_UPDATE_HELD_BILLING_END\s*-->\n?'
)
new = pattern.sub("\n", original)
if new == original:
    raise SystemExit(0)
# Only the fenced block may disappear. Anything larger is a bug -- refuse.
if len(original) - len(new) > 2000:
    raise SystemExit(0)
backup = os.path.realpath(p) + ".bak-standing-" + time.strftime("%Y%m%d-%H%M%S")
try:
    with open(backup, "w", encoding="utf-8", errors="surrogateescape") as fh:
        fh.write(original)
    with open(p, "w", encoding="utf-8", errors="surrogateescape") as fh:
        fh.write(new)
except Exception:
    raise SystemExit(0)
print("  [standing-gate] removed the stale 'update held -- account not current' notice from " + p)
PYEOF
    return 0
}

fleet_standing_gate() {
    if [ "${FLEET_STANDING_GATE_BYPASS:-0}" = "1" ]; then
        echo "  [standing-gate] bypassed (FLEET_STANDING_GATE_BYPASS=1)"
        return 0
    fi

    local url="${FLEET_STANDING_GATE_URL:-}"
    local hdr_name="${FLEET_STANDING_GATE_HEADER:-X-Fleet-Standing-Secret}"
    local hdr_val="${FLEET_STANDING_GATE_SECRET:-}"

    if [ -z "$url" ] || [ -z "$hdr_val" ]; then
        echo "  [standing-gate] not configured on this box -- proceeding (fail open)"
        return 0
    fi

    local slug; slug="$(fleet_standing_resolve_slug)"
    if [ -z "$slug" ]; then
        echo "  [standing-gate] could not resolve box slug -- proceeding (fail open)"
        return 0
    fi

    local body resp code
    body="{\"boxName\":\"${slug}\",\"action\":\"update\",\"source\":\"update-skills.sh\"}"

    # Two attempts, short timeouts. Never let curl's exit code trip set -e.
    local attempt
    for attempt in 1 2; do
        resp="$(curl -s -m 15 --connect-timeout 8 \
                 -w $'\n%{http_code}' \
                 -X POST "$url" \
                 -H "Content-Type: application/json" \
                 -H "${hdr_name}: ${hdr_val}" \
                 -d "$body" 2>/dev/null || printf '\n000')"
        code="$(printf '%s' "$resp" | tail -n1)"
        [ "$code" = "200" ] && break
        [ "$attempt" = "1" ] && sleep 3
    done

    if [ "$code" != "200" ]; then
        echo "  [standing-gate] gate unreachable (HTTP ${code:-000}) -- proceeding (fail open)"
        return 0
    fi

    local payload verdict
    payload="$(printf '%s' "$resp" | sed '$d')"
    # NOTE the `|| printf ''`: under `set -euo pipefail` a non-matching grep
    # exits 1, which would kill this command substitution and abort the whole
    # update -- i.e. a malformed gate reply would silently fail CLOSED across
    # the fleet. Swallowing the failure is what keeps the "unrecognised reply
    # -> proceed" branch below reachable. tests/unit/fleet-standing-gate.test.sh
    # covers this exact regression.
    verdict="$(printf '%s' "$payload" \
                | grep -o '"verdict"[[:space:]]*:[[:space:]]*"[a-z_]*"' \
                | head -n1 | sed 's/.*"\([a-z_]*\)"$/\1/' 2>/dev/null || printf '')"

    case "$verdict" in
        blocked) : ;;                                   # the only stop condition
        allowed)
            echo "  [standing-gate] account current -- proceeding"
            # A previously-blocked box carries an "## Update held -- account not
            # current" notice appended below. NOTHING ever removed it, so once the
            # account was brought current the box kept telling its agent (on every
            # single turn, AGENTS.md is re-billed) that its updates were frozen.
            # A writer owns removing what it wrote: clear it now that the gate says
            # allowed. Marker-fenced, so only this block is touched.
            fleet_standing_clear_held_notice
            return 0 ;;
        unmatched|held)
            echo "  [standing-gate] verdict '${verdict}' (box not on roster or lookup failed) -- proceeding (fail open)"
            return 0 ;;
        *)
            echo "  [standing-gate] unrecognised reply -- proceeding (fail open)"
            return 0 ;;
    esac

    if [ "${FLEET_STANDING_GATE_SHADOW:-0}" = "1" ]; then
        echo "  [standing-gate] SHADOW MODE: would have BLOCKED this update (${slug}) -- proceeding anyway"
        return 0
    fi

    # ---- blocked ----
    local agents_md="${OC_CONFIG:-$HOME/.openclaw}/AGENTS.md"
    local stamp; stamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    if [ -f "$agents_md" ] && ! grep -qF "OPENCLAW_UPDATE_HELD_BILLING" "$agents_md" 2>/dev/null; then
        {
            echo ""
            echo "<!-- OPENCLAW_UPDATE_HELD_BILLING:${stamp} -->"
            echo "## Update held -- account not current"
            echo "An update was available on ${stamp} but was not applied because this"
            echo "account is not current on payments. Nothing on this system was changed;"
            echo "everything continues running as it is. The update will apply automatically"
            echo "once the account is brought up to date."
            echo "<!-- OPENCLAW_UPDATE_HELD_BILLING_END -->"
        } >> "$agents_md" 2>/dev/null || true
    fi

    echo ""
    echo "============================================================"
    echo "  Update held -- account not current on payments."
    echo ""
    echo "  Nothing on this system has been changed and everything"
    echo "  keeps running as it is. As soon as the account is up to"
    echo "  date the latest version will install on the next check."
    echo "============================================================"
    echo ""
    exit 0
}

fleet_standing_gate
#=== END FLEET-STANDING-GATE-V1 ===

#=== BEGIN OPENCLAW-BACKUP-RETENTION-V1 ===
# ============================================================
#  Backup retention + disk pre-check -- ONE policy, every site.
#
#  WHY: every update/fix path on every box took a backup and NOTHING
#  ever removed one. Boxes accumulated GB-scale piles. Because a FAILED
#  backup now correctly aborts that box, a box that is tight on disk
#  fails the roll -- turning a storage problem into a roll failure.
#  These helpers close that permanently:
#    oc_backup_precheck_disk  fails LOUD and EARLY, before a byte is
#                             copied, when free space cannot hold it
#    oc_backup_prune          keeps the newest N, deletes older ones,
#                             and is only ever called AFTER a new
#                             backup has already succeeded
#
#  POLICY: keep the newest N. Default 3 = the backup this run just
#  wrote, the previous run's, and one older as safety margin. Two is
#  enough to undo one bad update; the third covers a bad update that
#  was only noticed one run later. Override per run with
#  OPENCLAW_BACKUP_KEEP (integer >= 1; anything else falls back to 3).
#
#  SAFETY RULES -- do not relax:
#    1. Prune runs AFTER a successful new backup, never before. The
#       only good backup is never deleted to make room for one that
#       then fails.
#    2. The current run's backup is never deleted, even when the keep
#       count would otherwise reach it.
#    3. Matching is against the tool's OWN literal name prefix followed
#       by a 4-digit year, one directory deep, and nothing else. A
#       prefix that is empty, shorter than 4 characters, contains a path
#       separator, or contains a glob metacharacter is REFUSED, and a
#       sibling that shares the prefix but is not timestamped is never
#       matched at all. A retention bug that deletes the wrong thing is
#       far worse than the disk it reclaims.
#    4. Every kept and every pruned entry is printed. Never silent.
#
#  This block is duplicated BYTE-FOR-BYTE into update-skills.sh, which
#  is curl-piped and so cannot source this file.
#  tests/unit/backup-retention.test.sh FAILS if the copies drift.
# ============================================================

# How many backups to keep. Never returns less than 1.
oc_backup_keep() {
  local n="${OPENCLAW_BACKUP_KEEP:-3}"
  case "$n" in
    ''|*[!0-9]*) n=3 ;;
  esac
  [ "$n" -lt 1 ] && n=1
  printf '%s' "$n"
}

# Size of a file or directory in KB. Prints 0 when it cannot be read.
oc_backup_size_kb() {
  local p="$1" kb=""
  [ -e "$p" ] || { printf '0'; return 0; }
  kb="$(du -sk "$p" 2>/dev/null | awk 'NR==1 {print $1}')"
  case "$kb" in
    ''|*[!0-9]*) kb=0 ;;
  esac
  printf '%s' "$kb"
}

# oc_backup_precheck_disk <dest_path> <needed_kb> [label]
#
# Verifies the filesystem holding <dest_path> can hold a backup of
# <needed_kb>, plus 20% headroom, plus a 10 MB floor. Walks up to the
# nearest existing parent so it works before mkdir.
#
# Returns 0 when there is room (or when free space genuinely cannot be
# read -- an unreadable df is not evidence of a full disk, so it warns
# and proceeds). Returns 1 LOUDLY, naming the path and the exact
# shortfall, when there is not.
oc_backup_precheck_disk() {
  local dest="$1" need_kb="$2" label="${3:-backup}"
  case "$need_kb" in
    ''|*[!0-9]*) need_kb=0 ;;
  esac

  local probe="$dest"
  while [ -n "$probe" ] && [ "$probe" != "/" ] && [ ! -d "$probe" ]; do
    probe="$(dirname "$probe")"
  done
  [ -d "$probe" ] || probe="/"

  local free_kb
  free_kb="$(df -Pk "$probe" 2>/dev/null | awk 'NR==2 {print $4}')"
  case "$free_kb" in
    ''|*[!0-9]*)
      echo "  [backup-precheck] WARN: cannot read free space for $probe -- proceeding with $label"
      return 0
      ;;
  esac

  # 20% headroom over the measured size, and never less than 10 MB free.
  local want_kb=$(( need_kb + need_kb / 5 + 10240 ))
  if [ "$free_kb" -lt "$want_kb" ]; then
    local short_kb=$(( want_kb - free_kb ))
    echo "" >&2
    echo "  ############################################################" >&2
    echo "  ## BACKUP ABORTED -- NOT ENOUGH FREE DISK" >&2
    echo "  ##   what      : $label" >&2
    echo "  ##   target    : $dest" >&2
    echo "  ##   filesystem: $probe" >&2
    echo "  ##   need      : ${want_kb} KB (${need_kb} KB of data + 20% headroom + 10 MB floor)" >&2
    echo "  ##   free      : ${free_kb} KB" >&2
    echo "  ##   short by  : ${short_kb} KB" >&2
    echo "  ## Refusing to start a backup that would die halfway and" >&2
    echo "  ## leave a corrupt archive. Free space on $probe, then re-run." >&2
    echo "  ############################################################" >&2
    echo "" >&2
    return 1
  fi

  echo "  [backup-precheck] OK: $label needs ~${want_kb} KB, ${free_kb} KB free on $probe"
  return 0
}

# oc_backup_prune <parent_dir> <literal_name_prefix> [current_backup_path]
#
# Keeps the newest N entries in <parent_dir> whose basename is
# <literal_name_prefix> followed immediately by a 4-digit year, deletes
# the rest, and prints every decision. Newest is decided by reverse
# lexical sort of the name, which is exactly newest-first for the
# YYYYmmdd-HHMMSS / YYYY-mm-dd-HHMMSS / YYYYmmddTHHMMSSZ stamps every
# caller here embeds. Requiring the year means an untimestamped sibling
# that happens to share the prefix is never matched and never counted.
#
# CALL THIS ONLY AFTER THE NEW BACKUP SUCCEEDED.
#
# Returns 1 without deleting anything if the prefix is not safely specific.
oc_backup_prune() {
  local parent="$1" prefix="$2" current="${3:-}"

  [ -d "$parent" ] || return 0

  case "$prefix" in
    ''|.|..)          echo "  [backup-prune] REFUSING: empty or dot prefix" >&2; return 1 ;;
    */*)              echo "  [backup-prune] REFUSING: prefix contains a path separator: $prefix" >&2; return 1 ;;
    *'*'*|*'?'*|*'['*|*']'*)
                      echo "  [backup-prune] REFUSING: prefix contains a glob metacharacter: $prefix" >&2; return 1 ;;
  esac
  if [ "${#prefix}" -lt 4 ]; then
    echo "  [backup-prune] REFUSING: prefix too short to be specific: $prefix" >&2
    return 1
  fi

  local keep_n current_base=""
  keep_n="$(oc_backup_keep)"
  [ -n "$current" ] && current_base="$(basename "$current")"

  local seen=0 pruned=0 entry base
  while IFS= read -r entry; do
    [ -n "$entry" ] || continue
    base="$(basename "$entry")"
    seen=$(( seen + 1 ))

    if [ "$seen" -le "$keep_n" ]; then
      echo "  [backup-prune] KEEP  ($seen/$keep_n): $entry"
      continue
    fi
    if [ -n "$current_base" ] && [ "$base" = "$current_base" ]; then
      echo "  [backup-prune] KEEP  (current run -- never pruned): $entry"
      continue
    fi
    if rm -rf -- "$entry" 2>/dev/null; then
      pruned=$(( pruned + 1 ))
      echo "  [backup-prune] PRUNE: $entry"
    else
      echo "  [backup-prune] WARN: could not remove $entry" >&2
    fi
  done <<EOF
$(find "$parent" -mindepth 1 -maxdepth 1 -name "${prefix}[0-9][0-9][0-9][0-9]*" 2>/dev/null | LC_ALL=C sort -r)
EOF

  echo "  [backup-prune] $parent/${prefix}<timestamp>* -- kept $(( seen - pruned )), pruned $pruned (keep=$keep_n)"
  return 0
}
#=== END OPENCLAW-BACKUP-RETENTION-V1 ===

# ----------------------------------------------------------
# Update-result notification — OPERATOR-ROUTED, NEVER the client chat.
# ----------------------------------------------------------
# SILENT-OPERATOR-CRON RULE (chore/silent-operator-crons): a skill-UPDATE result
# is INTERNAL maintenance traffic. The agent-facing push is the UPDATE PENDING
# flag written into AGENTS.md (write_update_pending_flag) — the agent picks it
# up on its next session and surfaces an owner-facing summary itself, on its own
# terms. The Terminal backup block (printed unconditionally below) covers the
# human running the updater by hand.
#
# The OLD form sent the raw "update applied / partial" result via
# `message send --target allowFrom[0]`, which on most boxes is the CLIENT's own
# chat (and on operator-first boxes, blindly the operator). Either way it
# AUTO-PUSHED internal update chatter to a chat. Per OPERATOR-MAINTENANCE.md
# (FIX 2 / v12.4.0): maintenance notifications use the OPERATOR session key /
# operator escalation chat — NEVER the client default — and NO-OP when no
# operator escalation chat is configured (no hardcoded default chat).
#
# Resolution: env.vars.OPERATOR_ESCALATION_CHAT_ID (written by
# configure-operator-telegram.sh) → operator account/session. If unset, we
# LOG-ONLY (no send) rather than fall back to any owner/allowFrom chat.
TELEGRAM_LAST_RESULT=""
send_telegram_progress() {
  local message="$1"
  local OCJSON="$HOME/.openclaw/openclaw.json"
  [ -d "/data/.openclaw" ] && OCJSON="/data/.openclaw/openclaw.json"
  local OPERATOR_CHAT=""
  TELEGRAM_LAST_RESULT="skipped"

  if ! command -v openclaw >/dev/null 2>&1; then
    TELEGRAM_LAST_RESULT="no-openclaw-cli"
    return 0
  fi

  # Resolve the OPERATOR escalation chat only — never the client default chat.
  if [ -f "$OCJSON" ] && command -v python3 >/dev/null 2>&1; then
    OPERATOR_CHAT=$(OC_JSON="$OCJSON" python3 - <<'PYEOF' 2>/dev/null
import json, os
try:
    cfg = json.load(open(os.environ["OC_JSON"]))
except Exception:
    cfg = {}
env = (cfg.get("env", {}) or {}).get("vars", {}) or {}
for k in ("OPERATOR_ESCALATION_CHAT_ID", "OPERATOR_HELP_CHAT_ID"):
    v = str(env.get(k, "") or "").strip()
    if v:
        print(v); raise SystemExit(0)
print("")
PYEOF
)
  fi

  if [ -z "$OPERATOR_CHAT" ]; then
    # No operator escalation chat configured → LOG-ONLY (the AGENTS.md UPDATE
    # PENDING flag + the Terminal backup block already cover the agent + human).
    # We deliberately do NOT fall back to allowFrom[0] / the client chat.
    {
      echo "[$(date '+%Y-%m-%d %H:%M:%S')] update-result notification (operator escalation chat not configured — LOG-ONLY, NOT sent to any client chat):"
      printf '%s\n' "$message"
    } >> "$LOG_FILE" 2>&1
    TELEGRAM_LAST_RESULT="logged-no-operator-chat"
    return 0
  fi

  # Send on the OPERATOR session key, reply out the operator account — mirrors
  # the OPERATOR-MAINTENANCE.md operator-drive contract.
  if openclaw message send \
      --channel telegram \
      --account operator \
      --session-key agent:main:operator \
      --target "$OPERATOR_CHAT" \
      --message "$message" >> "$LOG_FILE" 2>&1; then
    TELEGRAM_LAST_RESULT="sent-operator:$OPERATOR_CHAT"
  else
    # Operator send failed (e.g. operator account has no token yet). Do NOT fall
    # back to the client chat — LOG-ONLY.
    {
      echo "[$(date '+%Y-%m-%d %H:%M:%S')] update-result operator send FAILED (operator account likely missing token) — LOG-ONLY, NOT routed to any client chat:"
      printf '%s\n' "$message"
    } >> "$LOG_FILE" 2>&1
    TELEGRAM_LAST_RESULT="failed-operator:see-$LOG_FILE"
  fi
}

# ----------------------------------------------------------
# WORKSPACE RESOLVER -- ONE implementation, LOUD, never guesses (v21.3.1)
# ----------------------------------------------------------
# WHY THIS EXISTS (a live AGENTS.md was clobbered by the old shape):
# three call sites each resolved the agent workspace as
#     command -v obs_resolve_workspace >/dev/null && ws="$(obs_resolve_workspace)"
#     [ -z "$ws" ] && ws=<HARDCODED GUESS>
# obs_resolve_workspace is only defined if scripts/onboarding-state.sh was
# present in the pulled bundle and got SOURCED (it is sourced CONDITIONALLY).
# When that file was absent the call produced an empty string and each site
# SILENTLY substituted a DIFFERENT hardcoded path -- one site chose
# <oc-root>/workspace, another preferred $HOME/clawd. On a box whose
# openclaw.json names a workspace, BOTH guesses can be wrong, and the write
# lands on a file nobody intended. Guessing a path IS the defect.
#
# CONTRACT:
#   * Sets OC_WS_RESOLVED (path) and OC_WS_SOURCE (how it was resolved).
#   * ANNOUNCES the chosen path AND the reason it was chosen on EVERY call,
#     BEFORE the caller writes anything.
#   * Returns 1 -- with an exact statement of what could not be resolved -- when
#     the workspace cannot be determined by the intended means. There is NO
#     hardcoded last-resort guess. Callers MUST treat a non-zero return as
#     fatal and write NOTHING.
#
# RESOLUTION ORDER (identical to obs_resolve_workspace / install.sh Step 10):
#   1. obs_resolve_workspace, when the shim really did define it
#   2. THIS box's openclaw.json -> agents.entries.main.workspace   (NEW schema)
#   3. THIS box's openclaw.json -> agents.list[id=main].workspace  (LEGACY schema)
#   4. THIS box's openclaw.json -> agents.defaults.workspace
#   5. the canonical <oc-root>/workspace default -- ONLY when a readable,
#      parseable openclaw.json exists and simply declares no workspace at all
#      (that is the documented default, not a guess) -- still announced, with
#      its reason, on every run.
#
# ⚠️ WHY STEP 2 EXISTS AND WHY IT COMES FIRST. The schema migration renames
# `agents.list` (array) to `agents.entries` (object keyed by agent id). Before
# this resolver understood `entries`, a migrated box fell straight through to
# `agents.defaults.workspace` — so on any box that declared its workspace ONLY
# inside the legacy array, the migration silently RELOCATED the resolved
# workspace. That path is CANON_DIR, the symlink TARGET for the box's shared
# AGENTS.md / TOOLS.md / USER.md, so the effect would have been to re-point
# those files: a loud crash-loop traded for a silent outage. Reading the new
# shape FIRST makes this function return the SAME answer either side of a
# migration, which is exactly the invariant scripts/oc-atomic-upgrade.sh
# asserts before it will commit one. Keep the two reads in this order.
# ----------------------------------------------------------
oc_resolve_workspace_announced() {
  local _ctx="${1:-workspace}"
  OC_WS_RESOLVED=""
  OC_WS_SOURCE=""

  local _ws_ocroot="$HOME/.openclaw"
  [ -d "/data/.openclaw" ] && _ws_ocroot="/data/.openclaw"
  local _ws_ocjson="$_ws_ocroot/openclaw.json"

  # (1) the intended resolver, when the conditionally-sourced shim defined it.
  local _ws_have_resolver="no"
  if command -v obs_resolve_workspace >/dev/null 2>&1; then
    _ws_have_resolver="yes"
    # Guarded: a non-zero must not abort the updater under `set -euo pipefail`.
    OC_WS_RESOLVED="$(obs_resolve_workspace 2>/dev/null || true)"
    [ -n "$OC_WS_RESOLVED" ] && OC_WS_SOURCE="obs_resolve_workspace() from the onboarding-state.sh shim"
  fi

  # (2)+(3)+(4) read THIS box's own config directly. This is the SAME intended
  # means (the config), not a guess -- so it is a legitimate fallback, and it is
  # announced below with the reason the primary resolver was unavailable.
  # Reads BOTH schema shapes, new one first, so the answer is invariant across a
  # migration (see the RESOLUTION ORDER note above).
  if [ -z "$OC_WS_RESOLVED" ] && [ -f "$_ws_ocjson" ] && command -v python3 >/dev/null 2>&1; then
    OC_WS_RESOLVED="$(OC_JSON="$_ws_ocjson" python3 - <<'PYEOF' 2>/dev/null || true
import json, os
try:
    cfg = json.load(open(os.environ["OC_JSON"]))
    agents = cfg.get("agents") or {}
    if not isinstance(agents, dict):
        agents = {}
    ws = None
    # (2) NEW schema: agents.entries is a dict keyed by agent id.
    entries = agents.get("entries")
    if isinstance(entries, dict):
        main = entries.get("main")
        if isinstance(main, dict) and main.get("workspace"):
            ws = main["workspace"]
    # (3) LEGACY schema: agents.list is an array whose entries carry their own id.
    if not ws:
        for ag in (agents.get("list") or []):
            if isinstance(ag, dict) and ag.get("id") == "main" and ag.get("workspace"):
                ws = ag["workspace"]
                break
    # (4) the shared default.
    if not ws:
        defaults = agents.get("defaults") or {}
        if isinstance(defaults, dict):
            ws = defaults.get("workspace")
    if ws:
        print(os.path.expanduser(ws))
except Exception:
    pass
PYEOF
)"
    if [ -n "$OC_WS_RESOLVED" ]; then
      OC_WS_SOURCE="this box's own openclaw.json ($_ws_ocjson) -- FALLBACK USED because obs_resolve_workspace() is NOT defined (scripts/onboarding-state.sh was not sourced: absent from this bundle)"
    fi
  fi

  # (5) config is readable+parseable but declares no workspace anywhere.
  if [ -z "$OC_WS_RESOLVED" ] && [ -f "$_ws_ocjson" ] && [ -r "$_ws_ocjson" ] \
     && command -v python3 >/dev/null 2>&1 \
     && OC_JSON="$_ws_ocjson" python3 -c 'import json,os; json.load(open(os.environ["OC_JSON"]))' 2>/dev/null; then
    OC_WS_RESOLVED="$_ws_ocroot/workspace"
    OC_WS_SOURCE="canonical default -- FALLBACK USED because $_ws_ocjson parses but declares NO agents.entries.main.workspace, NO agents.list[id=main].workspace and NO agents.defaults.workspace"
  fi

  if [ -z "$OC_WS_RESOLVED" ]; then
    local _ws_why_resolver _ws_why_json _ws_why_py
    if [ "$_ws_have_resolver" = "yes" ]; then
      _ws_why_resolver="DEFINED but returned an empty path"
    else
      _ws_why_resolver="NOT DEFINED -- scripts/onboarding-state.sh was not sourced (missing from the pulled bundle)"
    fi
    if [ ! -f "$_ws_ocjson" ]; then
      _ws_why_json="ABSENT"
    elif [ ! -r "$_ws_ocjson" ]; then
      _ws_why_json="present but NOT READABLE"
    else
      _ws_why_json="present but did NOT parse as JSON"
    fi
    if command -v python3 >/dev/null 2>&1; then _ws_why_py="present"; else _ws_why_py="ABSENT"; fi
    {
      echo "  ✗ WORKSPACE UNRESOLVED -- refusing to write ($_ctx)."
      echo "    Could not determine the agent workspace by ANY intended means:"
      echo "      - obs_resolve_workspace(): $_ws_why_resolver"
      echo "      - config file $_ws_ocjson: $_ws_why_json"
      echo "      - python3: $_ws_why_py"
      echo "    NOT falling back to a hardcoded path. A silent guess is exactly what"
      echo "    overwrote a live AGENTS.md. Restore the bundle/config and re-run."
    } >&2
    return 1
  fi

  echo "  [workspace] $_ctx -> $OC_WS_RESOLVED"
  echo "  [workspace] resolved via: $OC_WS_SOURCE"
  return 0
}

# ----------------------------------------------------------
# Size of a file in BYTES, without reading it. (v21.3.2)
# ----------------------------------------------------------
# WHY NOT `wc -c < "$f"`: that redirect needs READ permission. On a file the
# updater may write but may not read, the redirect fails, and under
# `set -euo pipefail` the failure aborted the whole run at the size probe --
# BEFORE the AGENTS.md guards below could report anything. The file survived by
# luck rather than by design, and the operator saw a bare "Permission denied"
# with no explanation. `stat` needs only the directory entry, so an unreadable
# file still reports its true size and the shrink guard keeps working.
# Prints 0 when the file is absent or the size cannot be read. Never fails.
# Handles both stat flavours: -f is the Mac form, -c the VPS form.
oc_file_size_bytes() {
  local _p="${1:-}" _sz=""
  [ -n "$_p" ] && [ -e "$_p" ] || { echo 0; return 0; }
  # -L FOLLOWS the link. Without it stat reports the size of the link itself
  # (the length of the path it stores), so on the shared-AGENTS.md setup every
  # size would come back as a constant ~100 bytes and the shrink check below
  # could never fire -- dead exactly where the file matters most.
  #
  # The VPS form is tried FIRST and every answer is checked to be a plain
  # integer. Both details matter. The Mac form given to the VPS stat prints a
  # whole FILE SYSTEM report on stdout and THEN exits non-zero, so a chain that
  # trusted exit status alone glued that report onto the real number and the
  # result parsed as 0 -- a size guard that silently read zero on every VPS box.
  # The VPS form given to the Mac stat is rejected outright with nothing usable
  # on stdout, so this order falls through cleanly in the other direction.
  _sz="$(stat -L -c '%s' "$_p" 2>/dev/null | head -1 || true)"
  case "$_sz" in '' | *[!0-9]*) _sz="" ;; esac
  if [ -z "$_sz" ]; then
    _sz="$(stat -L -f '%z' "$_p" 2>/dev/null | head -1 || true)"
    case "$_sz" in '' | *[!0-9]*) _sz="" ;; esac
  fi
  [ -n "$_sz" ] || _sz=0
  echo "$_sz"
  return 0
}

# ----------------------------------------------------------
# _strip_update_pending_sections <AGENTS_FILE>
#
# Removes EVERY "## … UPDATE PENDING …" / "## … ONBOARDING PENDING …" section
# (header through the next top-level "## " heading, or EOF) from AGENTS.md, in
# place, behind five guards. Shared by BOTH callers so the sweep and the rewrite
# can never drift apart:
#   * write_update_pending_flag() — strip the old flag, then append a fresh one
#   * clear_update_pending_flag() — strip and append NOTHING (the gate passed)
#
# Returns 0 when the file now carries no PENDING section (written, or already
# clean). Returns non-zero when the rewrite was REFUSED — in which case the file
# is byte-for-byte untouched and the caller must NOT append anything, because the
# previous flag could not be removed and appending would stack a duplicate.
# ----------------------------------------------------------
_strip_update_pending_sections() {
  local AGENTS_FILE="$1"
  local rc=0
  # NOTE the command form: no `2>/dev/null`, no `|| true`. The real error has to
  # reach the operator, and a refusal has to be detectable by the caller.
  AGENTS_FILE="$AGENTS_FILE" python3 - <<'PYEOF' || rc=$?
import os, re, sys, time

p = os.environ["AGENTS_FILE"]


def die(msg):
    """Refuse to write. The file is left exactly as it was."""
    sys.stderr.write("  REFUSING to rewrite " + p + "\n")
    for line in msg.splitlines():
        sys.stderr.write("    " + line + "\n")
    raise SystemExit(1)


# --- guard 4: symlink transparency. Writing through the link is intended;
# --- say so out loud, and name the file that actually receives the bytes.
was_link = os.path.islink(p)
real = os.path.realpath(p)
if was_link:
    print("  [agents-flag] " + p)
    print("  [agents-flag]   is a SYMLINK -> " + real)
    print("  [agents-flag]   writing THROUGH the link, in place, onto that shared file.")
    print("  [agents-flag]   (intended: many agents share one AGENTS.md. The link is preserved.)")
else:
    print("  [agents-flag] target is a regular file: " + real)

# A file that does not exist yet is a known, safe state -- there is nothing to
# preserve, so we create it. A file that EXISTS but cannot be read is an ERROR
# and must never be treated as empty. That distinction is the whole fix.
exists = os.path.exists(p)
disk_before = os.path.getsize(p) if exists else 0

if not exists:
    if was_link:
        print("  [agents-flag] link target does not exist yet -- creating it through the link.")
    else:
        print("  [agents-flag] no existing AGENTS.md -- creating a fresh one (nothing to preserve).")
    original = ""
else:
    # --- guard 1: a read failure ABORTS, loudly, with the real error.
    # surrogateescape (not "replace") round-trips bytes that are not valid
    # UTF-8 exactly as they were, so a rewrite can never mangle them.
    try:
        with open(p, encoding="utf-8", errors="surrogateescape") as fh:
            original = fh.read()
    except Exception as exc:
        die("could not READ the existing file: " + repr(exc) + "\n"
            "This file is " + str(disk_before) + " bytes on disk and its contents are\n"
            "therefore UNKNOWN to this script. Rewriting it now would destroy it.\n"
            "Nothing was written. Fix the read error and re-run the updater.")

# Remove any "## ... UPDATE PENDING ..." or "## ... ONBOARDING PENDING ..."
# section: from its "## " header up to (but not including) the next top-level
# "## " heading, or EOF. Non-greedy, multiline. This sweeps EVERY such section,
# including stale ones left by earlier waves, not just the newest.
pattern = re.compile(
    r'(?m)^##[^\n]*(?:UPDATE PENDING|ONBOARDING PENDING)[^\n]*\n'   # the header
    r'(?:(?!^##\s).*\n?)*',                                         # body until next "## "
)
# Measured in BYTES, because it is compared against byte sizes below. Counting
# CHARACTERS here under-counted every non-ASCII character in a removed section
# (the flag text contains a few), so on a file carrying several stacked old
# flags the guard saw a bigger shrink than it could explain and REFUSED a
# perfectly good rewrite -- and, because the stale sections then stayed put, it
# refused again on every later run too.
removed_len = sum(len(m.group(0).encode("utf-8", "surrogateescape"))
                  for m in pattern.finditer(original))

if exists and removed_len == 0:
    # Already clean. Do NOT rewrite, do NOT take a backup -- a no-op run must be
    # byte-identical and must not leave another .bak- file behind on every roll.
    print("  [agents-flag] no UPDATE PENDING / ONBOARDING PENDING section present -- nothing to strip")
    raise SystemExit(0)

# --- guard 2: back up first, then READ THE BACKUP BACK and compare.
# A backup nobody has read is not a backup.
backup = ""
if original != "":
    backup = real + ".bak-" + time.strftime("%Y%m%d-%H%M%S")
    try:
        with open(backup, "w", encoding="utf-8", errors="surrogateescape") as fh:
            fh.write(original)
    except Exception as exc:
        die("could not WRITE the backup " + backup + ": " + repr(exc) + "\n"
            "Refusing to rewrite the file with no backup in hand. Nothing was written.")
    try:
        with open(backup, encoding="utf-8", errors="surrogateescape") as fh:
            readback = fh.read()
    except Exception as exc:
        die("could not READ BACK the backup " + backup + ": " + repr(exc) + "\n"
            "An unverified backup is not a backup. Nothing was written.")
    if readback != original:
        die("the backup " + backup + " does not match what was read from the file.\n"
            "Nothing was written.")
    print("  [agents-flag] backup verified: " + backup)
    print("  [agents-flag]   " + str(len(original.encode("utf-8", "surrogateescape")))
          + " bytes written, read back, and compared byte for byte.")

stripped = pattern.sub("", original)
new = stripped
# Collapse >2 blank lines left behind.
new = re.sub(r'\n{3,}', '\n\n', new)

# The collapse above is allowed to touch blank lines and nothing else.
if "".join(new.split()) != "".join(stripped.split()):
    die("internal check failed: collapsing blank lines changed real content.\n"
        "Nothing was written.")

# --- guard 3: SIZE SANITY. Stripping the previous flag section is the ONLY
# legitimate way this can shrink. Compare against the size ON DISK rather than
# against the text we read, so this still fires even if guard 1 were somehow
# defeated and `original` came back empty on a file full of content.
new_bytes = len(new.encode("utf-8", "surrogateescape"))
allowed_shrink = removed_len + 64   # +64 covers collapsed blank lines
if new_bytes < disk_before - allowed_shrink:
    die("the result would SHRINK this file by far more than removing the old\n"
        "flag can explain, so something has gone wrong:\n"
        "  on disk now      : " + str(disk_before) + " bytes\n"
        "  would be written : " + str(new_bytes) + " bytes\n"
        "  old flag sections: " + str(removed_len) + " bytes (the only allowed shrink)\n"
        "Nothing was written." + (("\nThe verified backup is at " + backup) if backup else ""))

# In place, through the link. NOT a temp file and a rename -- see the long
# comment in write_update_pending_flag. This truncates the target and keeps the
# link itself.
try:
    with open(p, "w", encoding="utf-8", errors="surrogateescape") as fh:
        fh.write(new)
except Exception as exc:
    die("the write itself FAILED: " + repr(exc)
        + (("\nThe verified backup is at " + backup) if backup else ""))

# --- guard 5: the link must have survived the write.
if was_link and not os.path.islink(p):
    die("after writing, " + p + " is NO LONGER A SYMLINK.\n"
        "The shared-file design has been broken -- restore from " + backup)

print("  [agents-flag] rewrote " + real + ": " + str(disk_before) + " -> "
      + str(new_bytes) + " bytes (removed " + str(removed_len)
      + " bytes of previous flag)")
PYEOF
  return "$rc"
}

# ----------------------------------------------------------
# clear_update_pending_flag
#
# THE ZOMBIE THIS KILLS. write_update_pending_flag() appended a section that
# literally instructed the reader: "Remove this entire UPDATE PENDING section from
# AGENTS.md when the gate passes." NOTHING executed that instruction. The updater
# wrote the flag on EVERY run — including runs where the verification gate had
# already passed and there was nothing pending — and never removed it afterwards,
# so a stale "UPDATE PENDING -- Skill Update to vX" block sat in a box's AGENTS.md
# indefinitely (measured: two weeks), re-billed to the model on every turn and
# telling the agent to activate skills that were already qc-passed.
#
# A script that writes a block owns removing it. This is the remover, and it also
# SWEEPS any stale section left by an earlier wave (the shared strip above matches
# every UPDATE PENDING / ONBOARDING PENDING section, not just the newest).
# ----------------------------------------------------------
clear_update_pending_flag() {
  if ! oc_resolve_workspace_announced "UPDATE PENDING flag removal target"; then
    echo "  ⚠ Could not resolve the workspace to clear the UPDATE PENDING flag (see above) — leaving AGENTS.md untouched." >&2
    return 0
  fi
  local AGENTS_FILE="$OC_WS_RESOLVED/AGENTS.md"
  if [ ! -f "$AGENTS_FILE" ]; then
    echo "  ℹ No AGENTS.md at $AGENTS_FILE — nothing to clear."
    return 0
  fi
  local SIZE_BEFORE SIZE_AFTER rc=0
  SIZE_BEFORE="$(oc_file_size_bytes "$AGENTS_FILE")"
  _strip_update_pending_sections "$AGENTS_FILE" || rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "  ⚠ UPDATE PENDING removal was REFUSED (see the error above) — AGENTS.md is UNCHANGED. Re-run the updater after fixing it." >&2
    return 0
  fi
  SIZE_AFTER="$(oc_file_size_bytes "$AGENTS_FILE")"
  if [ "$SIZE_AFTER" -lt "$SIZE_BEFORE" ]; then
    echo "  ✓ UPDATE PENDING section REMOVED from $AGENTS_FILE (${SIZE_BEFORE} -> ${SIZE_AFTER} bytes) — the gate passed and nothing is pending."
  else
    echo "  ✓ No UPDATE PENDING section to remove — $AGENTS_FILE is already clean."
  fi
  return 0
}

# ----------------------------------------------------------
# Write UPDATE PENDING flag to AGENTS.md
# ----------------------------------------------------------
write_update_pending_flag() {
  local version="$1"
  local new_skills="$2"

  # v10.15.48: resolve the canonical workspace the agent ACTUALLY reads from
  # (per-agent override -> defaults -> canonical default).
  # v21.3.1: the old code here was
  #     [ -z "$WORKSPACE_DIR" ] && WORKSPACE_DIR="$HOME/.openclaw/workspace"
  # i.e. when obs_resolve_workspace was undefined (its shim is sourced
  # CONDITIONALLY) this SILENTLY wrote the flag into a hardcoded path that the
  # box's own openclaw.json may not name at all. That is how a live AGENTS.md
  # got clobbered. Now: one announced resolver, and an unresolvable workspace is
  # a LOUD REFUSAL -- we never guess a target for a write.
  local WORKSPACE_DIR=""
  if ! oc_resolve_workspace_announced "UPDATE PENDING flag target"; then
    echo "  ✗ Refusing to write the UPDATE PENDING flag -- workspace unresolved (see above)." >&2
    return 1
  fi
  WORKSPACE_DIR="$OC_WS_RESOLVED"
  mkdir -p "$WORKSPACE_DIR"
  local AGENTS_FILE="$WORKSPACE_DIR/AGENTS.md"
  # Report the exact write target BEFORE touching it.
  echo "  [workspace] about to write: $AGENTS_FILE"

  # ------------------------------------------------------------------
  # SAFE IN-PLACE REWRITE of AGENTS.md.
  #
  # WHAT WENT WRONG BEFORE (this is a repaired wipe, not a hypothetical):
  # the old block read the file as
  #     try:    text = open(p).read()
  #     except Exception: text = ""
  # and then wrote it back with a TRUNCATING open(p, "w"). So ANY read
  # failure -- a permission problem, an I/O error, a link that could not be
  # followed -- silently turned the existing content into an empty string,
  # and the truncating write then destroyed the file. The only survivor was
  # the flag appended just below, which is why a live AGENTS.md came back as
  # a short stub containing nothing but an UPDATE PENDING notice. The read
  # error was invisible on top of that, because the old command ended in
  # `2>/dev/null || true` -- stderr thrown away, exit status ignored.
  #
  # WHY THIS STILL WRITES IN PLACE, and must NEVER become
  # write-a-temp-file-then-rename: agents deliberately share ONE AGENTS.md
  # through symlinks. A rename REPLACES the link with a regular file, so the
  # shared file silently becomes an unshared private copy and every other
  # agent stops seeing updates. `open(p, "w")` truncates the TARGET the link
  # points at and leaves the link itself in place, which is what we want.
  # Writing through the link is INTENDED -- the guards below only make it
  # visible, they never refuse it.
  #
  # THE GUARDS, in order:
  #   1. a read failure ABORTS with the real error -- never an empty string
  #   2. a timestamped backup is written AND read back and compared first
  #   3. the result is size-checked against the file ON DISK, so an
  #      unexpected shrink is refused even if guard 1 were ever defeated
  #   4. a symlink is detected and the real path being written is reported
  #   5. the link must still be a link afterwards -- asserted below
  # ------------------------------------------------------------------
  # Pre-write facts recorded in the SHELL so they outlive the python step and
  # can be asserted again after the flag is appended.
  local AGENTS_WAS_LINK=0
  if [ -L "$AGENTS_FILE" ]; then
    AGENTS_WAS_LINK=1
  fi
  # Size probe that does NOT need read permission and can never abort the run
  # (see oc_file_size_bytes above -- the old `wc -c <` form did both).
  local AGENTS_SIZE_BEFORE
  AGENTS_SIZE_BEFORE="$(oc_file_size_bytes "$AGENTS_FILE")"

  # FULLY strip ALL prior UPDATE PENDING / ONBOARDING PENDING SECTIONS
  # (header -> next "## " heading or EOF) before appending a fresh one. The old
  # `grep -v "UPDATE PENDING"` only removed the single header LINE, leaving the
  # multi-line body behind and STACKING a fresh full flag on every run.
  # The strip itself now lives in _strip_update_pending_sections() so the REMOVER
  # (clear_update_pending_flag) runs byte-identical logic behind the same guards.
  local FLAG_STRIP_RC=0
  _strip_update_pending_sections "$AGENTS_FILE" || FLAG_STRIP_RC=$?

  if [ "$FLAG_STRIP_RC" -ne 0 ]; then
    # The rewrite was REFUSED. The file is untouched. Do not append the flag
    # either: the previous flag could not be stripped, so appending would
    # stack a duplicate on top of it. Say so as loudly as possible, in the
    # Terminal and in the log, and leave the file alone.
    {
      echo ""
      echo "  =============================================================="
      echo "  AGENTS.md WAS NOT MODIFIED -- the rewrite was refused above."
      echo "  The file was NOT truncated and NOT emptied. No flag appended."
      echo "  The rest of this update already completed; only the agent's"
      echo "  UPDATE PENDING notice is missing. Fix the error printed above"
      echo "  and re-run the updater to write it."
      echo "  =============================================================="
      echo ""
    } 2>&1 | tee -a "${LOG_FILE:-/dev/null}" >&2
    return 0
  fi

  # Size AFTER the dedupe rewrite but BEFORE the append below. The rewrite is
  # ALLOWED to shrink the file -- removing stale flag sections is exactly what
  # it is for, and it has already size-checked itself against what it read.
  # The APPEND is the step that can only ever grow the file, so that is what
  # the assertion further down compares against. Comparing the final size to
  # the size before the dedupe instead cried wolf on every box carrying more
  # than one stale flag: a correct run printed "this file lost content,
  # restore it from backup". A wipe alarm that fires on good runs is an alarm
  # the operator learns to ignore.
  local AGENTS_SIZE_STRIPPED
  AGENTS_SIZE_STRIPPED="$(oc_file_size_bytes "$AGENTS_FILE")"

  local DATE_STAMP
  DATE_STAMP=$(date +%Y-%m-%d)

  cat >> "$AGENTS_FILE" <<FLAGCONTENT

## UPDATE PENDING -- Skill Update to ${version}

A skill update was applied via update-skills.sh on ${DATE_STAMP}. Activate each new skill below
and run the verification gate.

**You do NOT need to delete this section.** update-skills.sh owns it: the next run REMOVES it
automatically once the verification gate passes and no new skills are outstanding, and it sweeps
any stale copy left by an earlier wave. (Earlier versions told the reader to remove it by hand
and nothing ever did, so a stale flag sat in AGENTS.md for weeks.)

### 🔴 THE GATE IS THE TRUTH -- NOT THIS PROSE, NOT YOUR OWN "done"
This update is **NOT complete** until the VERIFICATION GATE passes. Files on disk = DOWNLOADED, not installed. Source the gate and check state:
- State file: \`~/.openclaw/workspace/.onboarding-state.json\` (per-skill: pending → downloaded → wired → qc-passed | qc-failed)
- Gate library: \`~/.openclaw/scripts/onboarding-state.sh\` (or the onboarding repo's \`scripts/\`)
- Run: source the library, then \`obs_gate_summary\`. A skill counts INSTALLED only when (a) \`openclaw skills info <name>\` shows it, (b) its CORE_UPDATES sentinel is present (if it ships CORE_UPDATES.md), and (c) its \`qc-*.sh\` exits 0 (if it ships one).
- **NEVER tell the owner "installed / done / onboarded" for any skill that is not \`qc-passed\` (or an explicit INTERVIEW_PENDING park).**

### What changed in this update
- Onboarding version: ${version}
- New skills installed (require ACTIVATION + GATE): ${new_skills:-none -- updates only}

### How to process each skill that is NOT yet qc-passed
For each such skill folder under \`~/.openclaw/skills/\`:
1. READ all files (Teach Yourself Protocol): SKILL.md, INSTALL.md, CORE_UPDATES.md, QC.md, plus any \`references/*.md\` files
2. CHECK prerequisites and search ALL standard credential locations (canonical: \`~/.openclaw/secrets/.env\` on Mac, \`/data/.openclaw/secrets/.env\` on VPS, plus \`openclaw.json\` env.vars). Skip asking the owner if values already exist.
3. EXECUTE the activation steps in INSTALL.md (read ≠ execute)
4. APPLY CORE_UPDATES.md surgically -- add to AGENTS.md / TOOLS.md / MEMORY.md / SOUL.md only the sections explicitly labeled in that file
5. RUN the gate (\`obs_verify_skill <folder>\`); loop activate→verify until it returns \`qc-passed\`. Skills that legitimately await owner input may be parked \`interview-pending\` (re-ping the owner; do NOT treat as terminal "done").
6. REPORT to owner ONLY what is verified-installed, plus what remains gated.

### Discipline (binding)
- Skills 22-23: MAIN ORCHESTRATOR ONLY, never delegate
- Tier order in any tiered skill (e.g. skill 36 GHL MCP): try Tier N before Tier N+1, no skipping
- Disclosure headers (e.g. \`[GHL tier used: N -- tool_name]\`) required per any skill's SOUL-level rules
- No destructive shortcuts: no \`--force\`, no \`--no-verify\`, no \`--break-system-packages\` unless explicitly instructed

### When the GATE passes
- This section is removed AUTOMATICALLY by the next update-skills.sh run. Leave it alone.
- Optional: add one line to MEMORY.md under "## System Updates":
  "${version} update applied on ${DATE_STAMP}. Verification gate PASSED. Skills activated: ${new_skills:-none}."

FLAGCONTENT

  # ------------------------------------------------------------------
  # POST-WRITE ASSERTIONS. Appending a flag can only make the file BIGGER,
  # and a shared file must still be shared afterwards. Both are checked
  # against the facts recorded before the write, and both are loud.
  # ------------------------------------------------------------------
  local AGENTS_SIZE_AFTER
  AGENTS_SIZE_AFTER="$(oc_file_size_bytes "$AGENTS_FILE")"
  if [ "$AGENTS_WAS_LINK" = "1" ] && [ ! -L "$AGENTS_FILE" ]; then
    echo "  ✗ ERROR: $AGENTS_FILE was a SYMLINK before this write and is a regular file now." >&2
    echo "    The shared core-file design has been broken -- other agents no longer see this file." >&2
    echo "    Restore the link from the timestamped backup reported above." >&2
  fi
  if [ "$AGENTS_SIZE_AFTER" -lt "$AGENTS_SIZE_STRIPPED" ]; then
    echo "  ✗ ERROR: $AGENTS_FILE SHRANK across the append: ${AGENTS_SIZE_STRIPPED} -> ${AGENTS_SIZE_AFTER} bytes." >&2
    echo "    Appending a flag can only grow a file, so this file lost content." >&2
    echo "    Restore it from the timestamped backup reported above." >&2
  fi
  echo "  ✓ UPDATE PENDING flag written (deduped) to $AGENTS_FILE"
  echo "    ${AGENTS_SIZE_BEFORE} bytes -> ${AGENTS_SIZE_STRIPPED} after removing stale flag sections -> ${AGENTS_SIZE_AFTER} with the new flag"
  if [ "$AGENTS_WAS_LINK" = "1" ]; then
    echo "    (written through a symlink onto the shared file; the link is intact)"
  fi

  # Seed Core.md terminology into MEMORY.md (idempotent)
  local MEMORY_FILE="$WORKSPACE_DIR/MEMORY.md"
  touch "$MEMORY_FILE"
  if ! grep -q "## Terminology -- Core.md Files" "$MEMORY_FILE" 2>/dev/null; then
    cat >> "$MEMORY_FILE" << 'COREMDEOF'

## Terminology -- Core.md Files

When the owner says **"Core.md files"** they mean the OpenClaw bootstrap files loaded every session -- not a literal file called `core.md`. The Core.md files are:

- **IDENTITY.md** -- the role the agent is playing. It contains the **experiences and the skills they need to embody** that role. Not just surface metadata (name / vibe / emoji) -- the lived background and capability set of the character being played.
- **SOUL.md** -- the **personality** of the agent, its **true mission**, its **beliefs**, its **rules**, its **goals**, its **belief systems**, its **principles**. Who the agent IS, not who they are playing. First file injected each session.
- **AGENTS.md** -- operating procedures, protocols, workflows, memory rules. *What the agent does and how*
- **USER.md** -- the human being helped (name, timezone, preferences, communication style)
- **TOOLS.md** -- local tool notes and conventions (camera names, SSH aliases, environment-specific specifics) -- NOT a permissions registry
- **MEMORY.md** -- curated long-term durable facts, decisions, preferences. Loaded in main private sessions; paired with daily logs at `memory/YYYY-MM-DD.md`

When the owner says "update the Core.md files" or "this needs to live in the Core.md files," choose the right one of these six based on its purpose:
- Personality / principle → SOUL.md
- Procedure / workflow → AGENTS.md
- Tool note → TOOLS.md
- Durable fact / decision → MEMORY.md
- User info → USER.md
- Identity metadata → IDENTITY.md

Never interpret "Core.md" as a literal filename.

COREMDEOF
    echo "  ✓ Core.md terminology seeded into MEMORY.md"
  fi
}

# ----------------------------------------------------------
# SKILLS DIRECTORY SECTION -- Active-dir-first detection
# ----------------------------------------------------------
# Platform detection:
#   VPS  (Hostinger Docker) → active dir is /data/.openclaw/skills
#   Mac                     → active dir is ~/.openclaw/skills
# We ALWAYS prefer the directory the running agent actually loads,
# falling back to ~/Downloads/openclaw-master-files only when the
# active dir doesn't exist.  Updating a stale Downloads copy while
# the active dir is untouched is a silent no-op (the classic bug).
# ----------------------------------------------------------

# ----------------------------------------------------------
# Discover skills directory -- active dir first
# ----------------------------------------------------------
discover_skills_dir() {
  # Detect platform: VPS has /data, Mac does not
  if [ -d /data ]; then
    # VPS (Hostinger Docker) -- active path is /data/.openclaw/skills
    local ACTIVE_DIR="/data/.openclaw/skills"
  else
    # Mac -- active path is ~/.openclaw/skills
    local ACTIVE_DIR="$HOME/.openclaw/skills"
  fi

  # Use the active dir whenever it exists and is non-empty
  if [ -d "$ACTIVE_DIR" ]; then
    local SKILL_COUNT=$(ls -d "$ACTIVE_DIR"/[0-9]*/ 2>/dev/null | wc -l | tr -d ' ')
    if [ "$SKILL_COUNT" -gt "0" ]; then
      echo "$ACTIVE_DIR"
      return
    fi
  fi

  # Active dir exists but is empty (first-install into it) -- still prefer it
  if [ -d "$ACTIVE_DIR" ]; then
    echo "$ACTIVE_DIR"
    return
  fi

  # Fallback: check Downloads copy (legacy / pre-active-dir installs)
  local LEGACY_DIR="$HOME/Downloads/openclaw-master-files"
  if [ -d "$LEGACY_DIR" ]; then
    local SKILL_COUNT=$(ls -d "$LEGACY_DIR"/[0-9]*/ 2>/dev/null | wc -l | tr -d ' ')
    if [ "$SKILL_COUNT" -gt "0" ]; then
      echo "$LEGACY_DIR"
      return
    fi
  fi

  # Fuzzy search for folders with "openclaw" and "master" in name (case-insensitive)
  local FUZZY_DIR=$(find "$HOME" -maxdepth 2 -type d -iname "*openclaw*" 2>/dev/null | grep -i "master" | head -1 || true)
  if [ -n "$FUZZY_DIR" ] && [ -d "$FUZZY_DIR" ]; then
    local SKILL_COUNT=$(ls -d "$FUZZY_DIR"/[0-9]*/ 2>/dev/null | wc -l | tr -d ' ')
    if [ "$SKILL_COUNT" -gt "0" ]; then
      echo "$FUZZY_DIR"
      return
    fi
  fi

  # Last resort: create and target the active dir (fresh install)
  echo "$ACTIVE_DIR"
}

# ----------------------------------------------------------
# UPDATE PENDING flag handling -- search correct locations
# ----------------------------------------------------------
check_update_pending() {
  # Search Mac primary location first, then secondary
  local PENDING_PATHS=(
    "$HOME/Downloads/openclaw-master-files/.pending-setup.md"
    "$HOME/.openclaw/skills/.pending-setup.md"
    "$HOME/.openclaw/onboarding/.pending-setup.md"
  )

  for PENDING in "${PENDING_PATHS[@]}"; do
    if [ -f "$PENDING" ]; then
      echo "$PENDING"
      return
    fi
  done

  # Return empty if not found
  echo ""
}

# ----------------------------------------------------------
# Check .onboarding-version -- search multiple paths
# Priority MUST match discover_skills_dir() (active dir first, legacy second)
# so the version we READ is the same location we WRITE to. If the legacy
# Downloads path is checked first the script sees the old stale marker even
# after a successful update → perpetual "needs update" false-positive (Bug B).
# ----------------------------------------------------------
get_current_version() {
  # Active dir first (mirrors discover_skills_dir priority). SKILLS_DIR is
  # resolved by discover_skills_dir() (VPS/Contabo -> /data/.openclaw/skills,
  # Mac -> $HOME/.openclaw/skills) and is already set by the time this is
  # called (main() sets it before the version gate). Bug A: this list used to
  # check only $HOME paths, so on every VPS/Contabo box the active version
  # file at /data/.openclaw/skills/.onboarding-version was never checked --
  # get_current_version() returned empty even on a fully up-to-date box.
  local VERSION_PATHS=(
    "${SKILLS_DIR:+$SKILLS_DIR/.onboarding-version}"
    "$HOME/.openclaw/skills/.onboarding-version"
    "$HOME/Downloads/openclaw-master-files/.onboarding-version"
    "$HOME/.openclaw/onboarding/.onboarding-version"
  )

  for VERSION_FILE in "${VERSION_PATHS[@]}"; do
    [ -n "$VERSION_FILE" ] || continue
    if [ -f "$VERSION_FILE" ]; then
      cat "$VERSION_FILE" 2>/dev/null | tr -d '[:space:]'
      return
    fi
  done

  # Return empty if not found
  echo ""
}

# --- BEGIN REAP-DEAD-SKILL-MANIFEST ---
# ----------------------------------------------------------
# reap_dead_skill_manifest  (v20.0.74)
#
# WHAT: deletes ~/.openclaw/skills/.skill-manifest.json and the orphaned
# regenerator ~/.openclaw/scripts/generate-manifest.sh from this box.
#
# WHY: .skill-manifest.json is a VERSION-STRING inventory written exactly
# once -- by install.sh Step 11, during a FULL install -- and regenerated
# by nothing. No updater has ever rewritten it. It therefore freezes at
# the version of the last full install while the skills underneath keep
# moving, and reports that stale version forever. Observed on the
# operator box: manifest onboardingVersion=v20.0.10 against a
# .onboarding-version stamp of v20.0.68. It manufactures phantom
# "stale skill" findings that have already burned two audits.
#
# NOTHING READS IT. `git grep skill-manifest` over openclaw-onboarding
# returns 4 hits: its two writers (install.sh:5414,
# scripts/generate-manifest.sh:6) and two documentation lines
# (VERSION-ARCHITECTURE.md:26,33). blackceo-command-center returns zero.
# The live drift gate reads a DIFFERENT, content-hashed file --
# .onboarding-content-manifest.json, written at the end of this script
# and consumed by check-updates.sh (A4). So deletion has no functional
# blast radius; its job is already done correctly, by content, elsewhere.
#
# WHY DELETE AND NOT RESTAMP: restamping preserves a version-string
# oracle, and version strings are precisely what lied -- trees carry a
# version identical to canonical while their contents differ. A
# perfectly restamped .skill-manifest.json would have reported every one
# of those drifted trees as healthy. Restamping costs the same effort as
# deleting, adds a maintenance obligation on every update path, and
# converts a noisy-but-noticed red light into a silent green one.
#
# WHY HERE: deleting from the repo alone leaves the lying copy armed on
# every already-provisioned box. The reap runs from main() BEFORE every
# exit path -- including the "already up to date" non-interactive no-op
# -- so a box is cleaned even on a run that syncs nothing.
#
# SAFETY: idempotent, never fails the run, and matches only these two
# exact basenames. .onboarding-version and
# .onboarding-content-manifest.json live in the same directory, are
# load-bearing, and are never touched.
# ----------------------------------------------------------
reap_dead_skill_manifest() {
  local _rdsm_count=0
  local _rdsm_path

  for _rdsm_path in \
      "${SKILLS_DIR:-$HOME/.openclaw/skills}/.skill-manifest.json" \
      "$HOME/.openclaw/skills/.skill-manifest.json" \
      "/data/.openclaw/skills/.skill-manifest.json" \
      "$HOME/Downloads/openclaw-master-files/.skill-manifest.json" \
      "$HOME/.openclaw/onboarding/.skill-manifest.json" \
      "$HOME/.openclaw/scripts/generate-manifest.sh" \
      "/data/.openclaw/scripts/generate-manifest.sh"; do
    if [ -f "$_rdsm_path" ] && rm -f "$_rdsm_path" 2>/dev/null; then
      _rdsm_count=$((_rdsm_count + 1))
    fi
  done

  if [ "$_rdsm_count" -gt 0 ]; then
    echo "  🧹 Reaped $_rdsm_count dead .skill-manifest.json artifact(s)"
    echo "      (superseded by .onboarding-content-manifest.json -- content-hashed, not version-string)"
  fi

  return 0
}
# --- END REAP-DEAD-SKILL-MANIFEST ---

# ----------------------------------------------------------
# v22.0.40 - safe_json_edit
# Harden any direct write to openclaw.json: back up, apply the
# python3 transform, validate with `openclaw config validate`,
# and ROLL BACK from the backup on failure so one bad key can
# never abort the updater under set -euo pipefail.
#
# The root-cause bug that aborted a multi-client update was
# skills.path written into openclaw.json on VPS (2026.5.x rejects
# the key with "skills Unrecognized key path / skills Invalid input").
# This helper ensures any future json edits are validated before they
# can corrupt the config and kill the run.
#
# Usage:
#   safe_json_edit OCJSON_PATH DESCRIPTION python3_transform_func
# where python3_transform_func is a bash function that:
#   - receives OCJSON_PATH as $1
#   - edits the file in-place
#   - exits 0 on success, non-zero on failure
#
# Note: the Mac updater has NO direct json.dump writes today --
# GHL MCP wiring uses `openclaw mcp set` which validates its own
# input. This helper is provided here as a forward-defense guard
# so future changes are forced to go through validation + rollback.
# ----------------------------------------------------------
safe_json_edit() {
  local OCJSON="$1"
  local DESCRIPTION="${2:-openclaw.json edit}"
  local EDIT_FUNC="$3"

  if [ ! -f "$OCJSON" ]; then
    echo "  [safe_json_edit] $OCJSON not found -- skipping $DESCRIPTION"
    return 0
  fi

  local BACKUP="${OCJSON}.bak-$(date +%Y%m%d-%H%M%S)"
  cp -f "$OCJSON" "$BACKUP" 2>/dev/null || {
    echo "  [safe_json_edit] WARN: could not create backup -- skipping $DESCRIPTION"
    return 0
  }

  # Run the edit function
  if ! "$EDIT_FUNC" "$OCJSON"; then
    echo "  [safe_json_edit] WARN: edit function failed -- rolling back $DESCRIPTION"
    cp -f "$BACKUP" "$OCJSON" 2>/dev/null || true
    rm -f "$BACKUP" 2>/dev/null || true
    return 0
  fi

  # Validate with the CLI if available
  if command -v openclaw >/dev/null 2>&1; then
    if ! openclaw config validate >> "$LOG_FILE" 2>&1; then
      echo "  [safe_json_edit] WARN: openclaw config validate FAILED after $DESCRIPTION -- rolling back"
      cp -f "$BACKUP" "$OCJSON" 2>/dev/null || true
      rm -f "$BACKUP" 2>/dev/null || true
      return 0
    fi
  fi

  rm -f "$BACKUP" 2>/dev/null || true
  echo "  [safe_json_edit] $DESCRIPTION applied and validated OK"
}

# ----------------------------------------------------------
# v10.15.51 -- link_shared_core_files
# AMENDED (N29, authorized by Trevor 2026-07-31): copy-on-run, not symlink.
# ----------------------------------------------------------
# Zero-Human-Workforce file model: on EVERY box, ALL of that account's agents
# + sub-agents SHARE the box's ONE canonical AGENTS.md / TOOLS.md / USER.md
# CONTENT, via a real file copy. Per-agent files (IDENTITY.md, SOUL.md,
# MEMORY.md, HEARTBEAT.md) stay each agent's OWN real files -- never touched
# here (except additive content preservation into IDENTITY.md, see below).
#
# WHY A COPY AND NOT A SYMLINK (this function used to symlink -- do not
# "restore" that): the OpenClaw runtime enforces a workspace-root boundary
# guard (applyResolvedSymlinkHop, reached via readWorkspaceFileWithGuards) that
# REJECTS any symlink whose realpath resolves outside the reading agent's own
# workspace. A rejected symlink is reported missing:true and a ~107-char
# [MISSING] stub is injected in its place -- the agent then runs with
# essentially no instructions, silently, with no error anywhere. Proven live:
# a client's dept-master-orchestrator reported rawChars:0 / injectedChars:107 /
# missing:true while its 335KB AGENTS.md sat intact on disk, and answered that
# it had no defined CEO routing/escalation procedure. No config key, env var,
# or flag reaches that call site, and the guard is unchanged between OpenClaw
# 2026.6.11 and 2026.7.1-2 (newer is stricter). A real file copy is invisible
# to that guard, so it is now the ONLY correct mechanism here.
#
# CANON_DIR = the box's DEFAULT AGENT WORKSPACE (agents.defaults.workspace, with
# the same resolver as obs_resolve_workspace / install.sh Step 10). The canonical
# AGENTS.md/TOOLS.md/USER.md live there. The copy source is ALWAYS this LOCAL
# box's own canonical -- NEVER a hardcoded path and NEVER a cross-box/cross-account
# path. The client is the USER; a client box copies from the CLIENT's own files
# only. This is the co-mingling guard (N0): we read THIS box's openclaw.json and
# resolve THIS box's workspace -- we never write a foreign path's content into a
# client's copy.
#
# NESTED WORKFLOW AGENT EXEMPTION: any workspace path matching */workflows/*/agents/*
# is an internal workflow micro-agent and is NEVER touched.
#
# Idempotent: if an agent's copy already byte-matches canonical, it is a no-op
# -- no rewrite, no backup churn. A pre-existing SYMLINK (relic of the
# pre-amendment behavior) is MIGRATED to a real copy, unconditionally -- the
# runtime guard rejects it regardless of what it points to. A real file that
# DIFFERS from canonical is backed up (never deleted), its unique content
# preserved additively into IDENTITY.md, then overwritten with canonical
# content. An absent file is left absent.
#
# FAIL-OPEN (regression guard for 5e181ceb, which once emptied a shared
# AGENTS.md when the updater could not read it): if the canonical source
# itself is unreadable or empty, EVERY agent's existing copy of that file is
# left EXACTLY as-is and a loud warning is printed to stderr. This function
# must never write an empty or truncated core file. Every write is verified by
# content hash (read back + compare) before being counted as a success; a
# verify failure is logged loudly and the pre-existing file/backup is left
# intact. File mode/ownership are preserved across the rewrite. Every action
# is logged with the [link-shared] prefix.
# ----------------------------------------------------------
link_shared_core_files() {
  local CANON_DIR="${1:-}"

  # OC_ROOT resolver (false-negative #3 fix): reuse the SHARED /data-else-HOME
  # .openclaw detector so this orchestrator resolves the SAME root as the ZHC/
  # dept scripts. Located from the freshly-extracted / installed tree; every use
  # below keeps its identical inline fallback if the shared file is unavailable
  # in this context (so behavior is unchanged either way).
  local _cand _OC_ROOT_RESOLVER=""
  for _cand in \
    "${EXTRACTED_DIR:-}/shared-utils/resolve-oc-root.sh" \
    "${SKILLS_DIR:-}/shared-utils/resolve-oc-root.sh"; do
    if [ -n "$_cand" ] && [ -f "$_cand" ]; then _OC_ROOT_RESOLVER="$_cand"; break; fi
  done
  # shellcheck source=/dev/null
  [ -n "$_OC_ROOT_RESOLVER" ] && source "$_OC_ROOT_RESOLVER"

  # --- Resolve CANON_DIR (box's own default agent workspace) ---------------
  # Precedence mirrors obs_resolve_workspace / install.sh Step 10:
  #   per-agent main override -> agents.defaults.workspace -> ~/.openclaw/workspace.
  # We ALWAYS read THIS box's openclaw.json -- never a foreign/hardcoded path.
  local OCJSON="$HOME/.openclaw/openclaw.json"
  [ -f "/data/.openclaw/openclaw.json" ] && OCJSON="/data/.openclaw/openclaw.json"
  # v21.3.1: this used to (a) call obs_resolve_workspace UNGUARDED -- a non-zero
  # aborts the whole updater under `set -euo pipefail` -- and (b) fall through to
  # a SILENT hardcoded <oc-root>/workspace when nothing resolved. CANON_DIR is
  # the symlink TARGET for the box's shared AGENTS.md/TOOLS.md/USER.md, so a
  # wrong guess here re-points real files at a path nobody named. Now: the one
  # announced resolver, and an unresolvable workspace REFUSES the whole
  # link-shared step (the caller already reports a warning + trips the step gate)
  # instead of linking into a guessed directory.
  if [ -z "$CANON_DIR" ]; then
    if ! oc_resolve_workspace_announced "link-shared CANON_DIR (symlink target for shared core files)"; then
      echo "  ✗ [link-shared] REFUSING to unify core files -- workspace unresolved (see above). No symlink was created or re-pointed." >&2
      return 1
    fi
    CANON_DIR="$OC_WS_RESOLVED"
  else
    echo "  [link-shared] CANON_DIR supplied by caller (explicit argument): $CANON_DIR"
  fi

  echo "  [link-shared] Zero-Human-Workforce file unification"
  echo "  [link-shared] CANON_DIR (this box's own canonical) = $CANON_DIR"
  mkdir -p "$CANON_DIR" 2>/dev/null || true

  # The canonical files must exist before we can link to them. touch ensures a
  # symlink target is always present (empty is fine; later wiring fills them).
  local f
  for f in AGENTS.md TOOLS.md USER.md; do
    [ -e "$CANON_DIR/$f" ] || { touch "$CANON_DIR/$f" 2>/dev/null || true; }
  done

  # Resolve CANON_DIR to an absolute, symlink-free real path so comparisons and
  # link targets are stable + correct.
  local CANON_REAL
  CANON_REAL="$(cd "$CANON_DIR" 2>/dev/null && pwd -P || echo "$CANON_DIR")"

  local TS
  TS="$(date +%Y%m%d-%H%M%S)"

  # ---- content-hash + stat helpers (N29 amendment: copy semantics) --------
  # _lsc_sha256 PATH -> sha256 hex digest on stdout, or empty if PATH is
  # missing/unreadable. PATH travels via an env var (never interpolated into
  # the python source) so paths with spaces/quotes are safe.
  _lsc_sha256() {
    LSC_HASH_PATH="$1" python3 -c '
import hashlib, os, sys
p = os.environ.get("LSC_HASH_PATH", "")
try:
    with open(p, "rb") as fh:
        data = fh.read()
    sys.stdout.write(hashlib.sha256(data).hexdigest())
except Exception:
    pass
' 2>/dev/null
  }

  # _lsc_mode_owner PATH -> "<mode>|<uid>:<gid>" for an existing file, or ""
  # if PATH doesn't exist. Tries BSD stat(1) syntax (Mac) then GNU stat(1)
  # syntax (Linux/VPS/Docker) -- the same fallback pattern already used
  # elsewhere in this file (see the INSTALL_FLAG age check above).
  _lsc_mode_owner() {
    local _p="$1" _m="" _o=""
    [ -e "$_p" ] || return 0
    _m="$(stat -f '%OLp' "$_p" 2>/dev/null || stat -c '%a' "$_p" 2>/dev/null || echo '')"
    _o="$(stat -f '%u:%g' "$_p" 2>/dev/null || stat -c '%u:%g' "$_p" 2>/dev/null || echo '')"
    printf '%s|%s' "$_m" "$_o"
  }

  # _lsc_write_copy SRC DEST MODE OWNER -> atomically copy SRC's bytes to DEST
  # (same-directory temp file + rename, so a mid-write crash can never leave
  # DEST truncated), apply MODE/OWNER if given, then verify by hash. Prints
  # "OK" on a verified match, "FAIL" otherwise. Every step is guarded so this
  # never raises under `set -euo pipefail`.
  _lsc_write_copy() {
    local _src="$1" _dest="$2" _mode="$3" _owner="$4"
    local _tmp="$_dest.tmp-unify-$$"
    if ! cp -f "$_src" "$_tmp" 2>/dev/null; then
      echo "FAIL"; return 0
    fi
    [ -n "$_mode" ] && chmod "$_mode" "$_tmp" 2>/dev/null
    [ -n "$_owner" ] && chown "$_owner" "$_tmp" 2>/dev/null
    if ! mv -f "$_tmp" "$_dest" 2>/dev/null; then
      rm -f "$_tmp" 2>/dev/null
      echo "FAIL"; return 0
    fi
    local _srchash _desthash
    _srchash="$(_lsc_sha256 "$_src")"
    _desthash="$(_lsc_sha256 "$_dest")"
    if [ -n "$_srchash" ] && [ "$_srchash" = "$_desthash" ]; then
      echo "OK"
    else
      echo "FAIL"
    fi
  }

  # Precompute each canonical file's hash ONCE (not per-workspace; this repo
  # targets bash 3.2 on Mac, so no associative arrays -- three scalars).
  # FAIL-OPEN: a canonical file that is missing/unreadable/EMPTY skips every
  # workspace for that filename entirely. Nothing is ever overwritten with
  # emptiness.
  local CANON_HASH_AGENTS="" CANON_HASH_TOOLS="" CANON_HASH_USER=""
  for f in AGENTS.md TOOLS.md USER.md; do
    local _ch=""
    if [ -s "$CANON_REAL/$f" ]; then
      _ch="$(_lsc_sha256 "$CANON_REAL/$f")"
    fi
    if [ -z "$_ch" ]; then
      echo "  ⛔ [link-shared] WARN: canonical $f is empty or unreadable at $CANON_REAL/$f -- leaving EVERY agent's existing copy of $f untouched (fail-open, no overwrite, no truncation)" >&2
    fi
    case "$f" in
      AGENTS.md) CANON_HASH_AGENTS="$_ch" ;;
      TOOLS.md)  CANON_HASH_TOOLS="$_ch" ;;
      USER.md)   CANON_HASH_USER="$_ch" ;;
    esac
  done

  # --- Enumerate agent workspaces ------------------------------------------
  # Sources: (a) every agents[].workspace declared in THIS box's openclaw.json,
  # (b) a scan of the workspaces/ dir (immediate children + agents/* role dirs).
  # We only ever operate on dirs under this box. Dedup; skip CANON; skip nested workflow agents.
  local WS_LIST_FILE
  WS_LIST_FILE="$(mktemp 2>/dev/null || echo "/tmp/link-shared-ws-$$.txt")"
  : > "$WS_LIST_FILE"

  if [ -f "$OCJSON" ] && command -v python3 >/dev/null 2>&1; then
    OC_JSON="$OCJSON" python3 - >> "$WS_LIST_FILE" 2>/dev/null <<'PYEOF' || true
import json, os
try:
    cfg = json.load(open(os.environ["OC_JSON"]))
    for ag in cfg.get("agents", {}).get("list", []) or []:
        if isinstance(ag, dict):
            ws = ag.get("workspace")
            if ws:
                print(os.path.expanduser(ws))
except Exception:
    pass
PYEOF
  fi

  # Scan the workspaces dir tree for agent-shaped dirs. The canonical default
  # parent is .openclaw/ (or /data/.openclaw); also scan the workspace's own
  # departments/ + agents/ trees where role workspaces live.
  local OC_ROOT
  if declare -F resolve_oc_root >/dev/null 2>&1 && OC_ROOT="$(resolve_oc_root)"; then
    :
  else
    OC_ROOT="$HOME/.openclaw"
    [ -d "/data/.openclaw" ] && OC_ROOT="/data/.openclaw"
  fi
  local _scan
  for _scan in \
      "$OC_ROOT/workspaces" \
      "$CANON_REAL/agents" \
      "$CANON_REAL/departments"; do
    [ -d "$_scan" ] || continue
    # Any dir that already carries one of the shared files (real or link) is an
    # agent workspace candidate. find -type d then filter in the loop below.
    find "$_scan" -type d \( -name 'AGENTS.md' -prune \) -o -type d -print 2>/dev/null \
      | while IFS= read -r d; do
          if [ -e "$d/AGENTS.md" ] || [ -e "$d/IDENTITY.md" ] || [ -e "$d/SOUL.md" ]; then
            echo "$d"
          fi
        done >> "$WS_LIST_FILE" 2>/dev/null || true
  done

  local COPIED=0 MIGRATED=0 BACKED_UP=0 PRESERVED=0 SKIPPED_ANT=0 NOOP=0 FAILED=0

  # Dedup workspace list, then process each.
  local W
  while IFS= read -r W; do
    [ -n "$W" ] || continue
    W="$(printf '%s' "$W" | sed 's:/*$::')"   # strip trailing slashes
    [ -d "$W" ] || continue

    # Resolve to absolute real path for a correct CANON comparison.
    local W_REAL
    W_REAL="$(cd "$W" 2>/dev/null && pwd -P || echo "$W")"

    # Skip the canonical workspace itself -- it OWNS the real files.
    if [ "$W_REAL" = "$CANON_REAL" ]; then
      continue
    fi

    # NESTED WORKFLOW AGENT EXEMPTION: never touch */workflows/*/agents/* micro-agents.
    case "$W_REAL/" in
      */workflows/*/agents/*)
        echo "  [link-shared] SKIP (nested workflow agent exempt): $W_REAL"
        SKIPPED_ANT=$((SKIPPED_ANT + 1))
        continue
        ;;
    esac

    for f in AGENTS.md TOOLS.md USER.md; do
      local TARGET="$CANON_REAL/$f"
      local LINKPATH="$W_REAL/$f"

      # Resolve this file's precomputed canonical hash (no associative arrays
      # -- see the bash-3.2 note above). Empty means canonical was bad; the
      # fail-open warning already fired once above, so skip silently here.
      local TARGET_HASH=""
      case "$f" in
        AGENTS.md) TARGET_HASH="$CANON_HASH_AGENTS" ;;
        TOOLS.md)  TARGET_HASH="$CANON_HASH_TOOLS" ;;
        USER.md)   TARGET_HASH="$CANON_HASH_USER" ;;
      esac
      if [ -z "$TARGET_HASH" ]; then
        continue
      fi

      if [ -L "$LINKPATH" ]; then
        # MIGRATION: a symlink is a relic of the pre-amendment behavior, and
        # the runtime boundary guard rejects it at read time regardless of
        # what it points to. Replace with a verified real copy, always.
        local CUR
        CUR="$(readlink "$LINKPATH" 2>/dev/null || echo '')"
        local MODE_OWNER
        MODE_OWNER="$(_lsc_mode_owner "$TARGET")"   # no real prior file to inherit mode from -- mirror canonical's own
        local M_MODE="${MODE_OWNER%%|*}" M_OWNER="${MODE_OWNER#*|}"
        rm -f "$LINKPATH" 2>/dev/null
        if [ "$(_lsc_write_copy "$TARGET" "$LINKPATH" "$M_MODE" "$M_OWNER")" = "OK" ]; then
          echo "  [link-shared] MIGRATE (symlink -> copy) $LINKPATH (was -> $CUR)"
          MIGRATED=$((MIGRATED + 1))
        else
          echo "  ✗ [link-shared] WARN: verified copy FAILED for $LINKPATH (was a symlink -> $CUR) -- see above" >&2
          FAILED=$((FAILED + 1))
        fi

      elif [ -f "$LINKPATH" ]; then
        # A REAL file. Idempotent fast path: already byte-identical to
        # canonical -> no-op. No rewrite, no backup churn.
        local CUR_HASH
        CUR_HASH="$(_lsc_sha256 "$LINKPATH")"
        if [ -n "$CUR_HASH" ] && [ "$CUR_HASH" = "$TARGET_HASH" ]; then
          NOOP=$((NOOP + 1))
          continue
        fi

        # DIVERGENT: back it up (NEVER delete), preserve unique content into
        # this agent's OWN IDENTITY.md (additive only), then overwrite with
        # canonical content -- as a real file, not a symlink.
        local BAK="$LINKPATH.bak-unify-$TS"
        cp -p "$LINKPATH" "$BAK" 2>/dev/null \
          && { echo "  [link-shared] BACKUP $LINKPATH -> $BAK"; BACKED_UP=$((BACKED_UP + 1)); } \
          || { echo "  [link-shared] WARN: backup failed for $LINKPATH -- leaving file untouched"; continue; }

        # Best-effort PRESERVE: append any content NOT already in CANON/<f> to
        # this agent's OWN IDENTITY.md under a guarded marker (only ADD; create
        # IDENTITY.md if absent). Guard prevents duplicate preservation on re-run.
        local AGENT_NAME
        AGENT_NAME="$(basename "$W_REAL")"
        local IDFILE="$W_REAL/IDENTITY.md"
        local PMARK="<!-- PRESERVED FROM ${AGENT_NAME} ${f} (unification ${TS}) -->"
        # Marker prefix (sans timestamp) used to detect prior preservation of the
        # same agent+file so re-runs never re-append.
        local PMARK_PREFIX="<!-- PRESERVED FROM ${AGENT_NAME} ${f} (unification "
        if ! grep -qF "$PMARK_PREFIX" "$IDFILE" 2>/dev/null; then
          AGENT_F="$LINKPATH" CANON_F="$TARGET" ID_F="$IDFILE" PMARK="$PMARK" \
            python3 - <<'PYEOF' 2>/dev/null || true
import os
src   = os.environ["AGENT_F"]
canon = os.environ["CANON_F"]
idf   = os.environ["ID_F"]
mark  = os.environ["PMARK"]
try:
    src_text = open(src, encoding="utf-8", errors="replace").read()
except Exception:
    src_text = ""
try:
    canon_text = open(canon, encoding="utf-8", errors="replace").read()
except Exception:
    canon_text = ""
# Split the agent's file into blank-line-delimited blocks; keep only blocks
# whose stripped text is non-empty AND not already present in the canonical file.
blocks, cur = [], []
for line in src_text.splitlines():
    if line.strip() == "":
        if cur:
            blocks.append("\n".join(cur)); cur = []
    else:
        cur.append(line)
if cur:
    blocks.append("\n".join(cur))
unique = [b for b in blocks if b.strip() and b.strip() not in canon_text]
if unique:
    with open(idf, "a", encoding="utf-8") as fh:
        fh.write("\n\n" + mark + "\n")
        fh.write("\n\n".join(unique))
        fh.write("\n")
    print("PRESERVED")
PYEOF
          if grep -qF "$PMARK" "$IDFILE" 2>/dev/null; then
            echo "  [link-shared] PRESERVE unique $f content -> $IDFILE"
            PRESERVED=$((PRESERVED + 1))
          fi
        fi

        # Overwrite with a verified real copy of canonical content, preserving
        # this agent's existing mode/ownership (captured BEFORE the rewrite).
        local MODE_OWNER
        MODE_OWNER="$(_lsc_mode_owner "$LINKPATH")"
        local M_MODE="${MODE_OWNER%%|*}" M_OWNER="${MODE_OWNER#*|}"
        if [ "$(_lsc_write_copy "$TARGET" "$LINKPATH" "$M_MODE" "$M_OWNER")" = "OK" ]; then
          echo "  [link-shared] COPY $LINKPATH <- $TARGET (canonical)"
          COPIED=$((COPIED + 1))
        else
          echo "  ✗ [link-shared] WARN: verified copy FAILED for $LINKPATH -- original is safe in $BAK" >&2
          FAILED=$((FAILED + 1))
        fi

      else
        # Absent → leave absent. (No churn.)
        :
      fi
    done
  done < <(sort -u "$WS_LIST_FILE")

  rm -f "$WS_LIST_FILE" 2>/dev/null || true

  echo "  [link-shared] done: copied=$COPIED migrated=$MIGRATED backed-up=$BACKED_UP preserved=$PRESERVED workflow-agent-skipped=$SKIPPED_ANT already-ok=$NOOP failed=$FAILED"
  echo "  [link-shared] IDENTITY/SOUL/MEMORY/HEARTBEAT left as each agent's OWN files (per-agent, not shared)."

  if [ "$FAILED" -gt 0 ]; then
    echo "  ✗ [link-shared] WARN: $FAILED verified-write failure(s) -- see WARN lines above; every original is preserved (backup or left untouched)" >&2
    return 1
  fi
  return 0
}

# >>> TRAP1-PRECLEAR-BEGIN  (extracted verbatim by scripts/test-updater-traps-1-and-3.sh)
# ----------------------------------------------------------
# TRAP 1 (canary 2026-07-19) -- SAFE .clawdbot relic pre-clear
# ----------------------------------------------------------
# BACKGROUND. OpenClaw 2026.7.1 tightened its startup-migration gate: it fatally
# refuses to start the gateway when a box carries a stale
# <ocroot>/plugins/installs.json or a leftover ~/.clawdbot directory. The
# documented remedy was a hand-typed pre-clear -- literally
#   mv ~/.clawdbot ~/.clawdbot.bak-pre-2026.7.1
# run on every box "before any fleet-wide roll", on the ASSUMPTION that
# ~/.clawdbot is always a dead relic of the clawdbot->OpenClaw rename.
#
# THAT ASSUMPTION IS FALSE ON AT LEAST ONE REAL BOX. A live canary run found a
# box where ~/.openclaw/workspace is a SYMLINK pointing INTO ~/.clawdbot/workspace,
# making ~/.clawdbot the box's LIVE workspace root (agent workspaces declared in
# openclaw.json, the departments tree, heartbeat state, files written the same
# day). Running the documented `mv` there would have dangled the symlink and
# taken the box down. The pre-clear must therefore NEVER be a blind move.
#
# TWO CHANGES ARE MADE HERE:
#
#  1) DETECT BEFORE MOVING, AND FAIL CLOSED. Nothing is renamed until this box
#     has been proven NOT to depend on .clawdbot. Any live signal -- a symlink
#     resolving into it, an openclaw.json path referencing it, a non-empty
#     workspace/ inside it, a file written in the last 30 days, or simply an
#     inability to check -- refuses the pre-clear loudly and exits non-zero.
#     Ambiguity counts as LIVE. We would rather halt a roll than dangle a box.
#
#  2) IT DOES NOT RUN BY DEFAULT. The pre-clear exists to survive an OpenClaw
#     BINARY version bump to 2026.7.1. This updater performs no such bump: it
#     contains no `npm install -g openclaw`, no `openclaw@<version>`, no
#     `openclaw update/upgrade`, no docker pull, and neither platform bootstrap
#     (platform/mac/bootstrap.sh, platform/vps/bootstrap.sh) installs the binary
#     either. A normal `update-skills.sh` run therefore cannot trigger the
#     2026.7.1 gate, so running a destructive pre-clear on every update would be
#     pure downside. It is opt-in only:
#         bash update-skills.sh --preclear-check        # report only, never moves
#         bash update-skills.sh --preclear-2026-7-1     # move, only if provably safe
#         OPENCLAW_PRECLEAR_2026_7_1=1 bash update-skills.sh   # same as above
#
# Exit codes for the pre-clear modes: 0 = clean (or nothing to do), 3 = REFUSED
# (a live signal was found, or liveness could not be determined). 3 is distinct
# so a fleet driver can tell "this box is fine" from "this box needs a human".
#
# Both layouts are covered: Mac ($HOME/.openclaw) and VPS/Docker, where the
# OpenClaw home may be /data/.openclaw or /home/node/.openclaw. No single path
# is assumed -- every candidate root that exists is inspected.
# ----------------------------------------------------------

# Absolute, symlink-resolved path. Portable: macOS has no `readlink -f` and may
# have no `realpath`, so python3 first, then a cd/pwd -P fallback.
_pc_realpath() {
  local p="${1:-}" out="" d b
  [ -n "$p" ] || return 0
  if command -v python3 >/dev/null 2>&1; then
    out="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$p" 2>/dev/null || true)"
  fi
  if [ -z "$out" ] && [ -d "$p" ]; then
    out="$( cd "$p" 2>/dev/null && pwd -P || true )"
  fi
  if [ -z "$out" ]; then
    d="$(dirname "$p")"; b="$(basename "$p")"
    if [ -d "$d" ]; then
      out="$( cd "$d" 2>/dev/null && pwd -P || true )"
      [ -n "$out" ] && out="$out/$b"
    fi
  fi
  printf '%s\n' "$out"
}

# Every OpenClaw home this box could be using, deduped, existing dirs only.
# Mac: $HOME/.openclaw. VPS/Docker: /data/.openclaw or /home/node/.openclaw
# (container images differ) -- we never assume which.
_pc_openclaw_homes() {
  local h seen=""
  for h in "${OC_CONFIG:-}" "$HOME/.openclaw" /data/.openclaw /home/node/.openclaw /root/.openclaw; do
    [ -n "$h" ] || continue
    [ -d "$h" ] || continue
    case " $seen " in *" $h "*) continue ;; esac
    seen="$seen $h"
    printf '%s\n' "$h"
  done
}

# Every .clawdbot root this box could be carrying: the sibling of each OpenClaw
# home, plus $HOME/.clawdbot. Existing paths only.
_pc_clawdbot_roots() {
  local h c seen=""
  { _pc_openclaw_homes | while IFS= read -r h; do dirname "$h"; done; printf '%s\n' "$HOME"; } 2>/dev/null \
  | while IFS= read -r c; do
      [ -n "$c" ] || continue
      printf '%s/.clawdbot\n' "$c"
    done \
  | while IFS= read -r c; do
      [ -e "$c" ] || continue
      case " $seen " in *" $c "*) continue ;; esac
      seen="$seen $c"
      printf '%s\n' "$c"
    done
}

# Liveness verdict for ONE .clawdbot root.
#   prints one "  - <reason>" line per live signal found
#   returns 0 = LIVE (do not touch), 1 = no live signal found
# Fails CLOSED: if a check cannot be performed, that is itself a live signal.
_pc_clawdbot_is_live() {
  local root="${1:-}" live=1 root_real="" home ocjson link target n

  [ -n "$root" ] || { echo "  - empty path passed to liveness check (cannot verify)"; return 0; }

  # F. The root is itself a symlink -> renaming it moves a link, not the data,
  # and the data it points at may be live. Never guess.
  if [ -L "$root" ]; then
    echo "  - $root is itself a SYMLINK (target not inspected) -- refusing to move a link"
    live=0
  fi

  root_real="$(_pc_realpath "$root")"
  if [ -z "$root_real" ]; then
    echo "  - could not resolve a real path for $root (cannot verify it is dead)"
    return 0
  fi

  # E. Unreadable -> cannot verify -> treat as live.
  if [ ! -r "$root" ]; then
    echo "  - $root is not readable by this user (cannot verify it is dead)"
    live=0
  fi

  # A. Any symlink under any OpenClaw home that resolves INTO .clawdbot.
  #    This is exactly the operator-Mac case: ~/.openclaw/workspace -> ~/.clawdbot/workspace.
  while IFS= read -r home; do
    [ -n "$home" ] || continue
    while IFS= read -r link; do
      [ -n "$link" ] || continue
      target="$(_pc_realpath "$link")"
      [ -n "$target" ] || continue
      case "$target" in
        "$root_real"|"$root_real"/*)
          echo "  - $link is a symlink resolving into $root_real (moving it would DANGLE this link)"
          live=0
          ;;
      esac
    done < <(find "$home" -maxdepth 2 -type l -print 2>/dev/null || true)
  done < <(_pc_openclaw_homes)

  # B. openclaw.json referencing paths under .clawdbot (declared agent
  #    workspaces, skills.path, scripts, secrets...). COUNT ONLY is printed --
  #    openclaw.json holds credentials under env.vars and is never dumped.
  while IFS= read -r home; do
    ocjson="$home/openclaw.json"
    [ -f "$ocjson" ] || continue
    n=""
    if command -v python3 >/dev/null 2>&1; then
      n="$(OCJ="$ocjson" ROOTR="$root_real" python3 - <<'PYEOF' 2>/dev/null || true
import json, os
hits = 0
root = os.environ["ROOTR"]
def walk(node):
    global hits
    if isinstance(node, str):
        if "/.clawdbot" in node or node == root or node.startswith(root + "/"):
            hits += 1
    elif isinstance(node, dict):
        for v in node.values():
            walk(v)
    elif isinstance(node, list):
        for v in node:
            walk(v)
try:
    walk(json.load(open(os.environ["OCJ"])))
    print(hits)
except Exception:
    print("ERR")
PYEOF
)"
    else
      # No python3: count matching LINES only. Never print the matched text.
      n="$(grep -c -F -- '.clawdbot' "$ocjson" 2>/dev/null || echo 0)"
    fi
    if [ "$n" = "ERR" ] || [ -z "$n" ]; then
      echo "  - could not parse $ocjson to check for .clawdbot references (cannot verify it is dead)"
      live=0
    elif [ "$n" -gt 0 ] 2>/dev/null; then
      echo "  - $ocjson contains $n path reference(s) under .clawdbot (values withheld)"
      live=0
    fi
  done < <(_pc_openclaw_homes)

  # C. A non-empty workspace/ inside .clawdbot -- structural evidence this root
  #    is being used as a workspace root, not a config relic.
  if [ -d "$root/workspace" ]; then
    n="$(find "$root/workspace" -maxdepth 1 -mindepth 1 -print 2>/dev/null | head -n 20 | wc -l | tr -d ' ' || true)"
    if [ -n "$n" ] && [ "$n" -gt 0 ] 2>/dev/null; then
      echo "  - $root/workspace exists and is NOT empty ($n+ entries) -- this looks like a live workspace root"
      live=0
    fi
  fi

  # D. Anything written in the last 30 days. A true relic is cold.
  #    maxdepth caps runtime on trees with dozens of agent workspaces; live
  #    boxes write near the top (heartbeat state, session files) well inside it.
  n="$(find "$root" -maxdepth 6 -type f -mtime -30 -print 2>/dev/null | head -n 1 || true)"
  if [ -n "$n" ]; then
    echo "  - $root contains file(s) modified in the last 30 days (e.g. $n) -- not a cold relic"
    live=0
  fi

  return $live
}

# mode: "check" (report only, never mutates) | "apply" (rename, only if proven safe)
preclear_2026_7_1() {
  local mode="${1:-check}"
  local refused=0 found=0 root home reasons ts is_live
  ts="$(date +%Y%m%d-%H%M%S)"

  echo ""
  echo "============================================"
  echo "   OpenClaw 2026.7.1 relic pre-clear (${mode})"
  echo "============================================"
  echo "  NOTE: this updater performs NO OpenClaw binary upgrade, so a normal"
  echo "        update run never trips the 2026.7.1 startup gate. This step is"
  echo "        opt-in and is only needed immediately before a version roll."
  echo ""

  # ---- PASS 1: detect only. Nothing is mutated until every root is cleared. ----
  while IFS= read -r root; do
    [ -n "$root" ] || continue
    found=1
    echo "  [preclear] inspecting $root"
    # ONE call: capture the evidence lines and the verdict together.
    # _pc_clawdbot_is_live returns 0 = LIVE, 1 = no live signal.
    is_live=0
    reasons="$(_pc_clawdbot_is_live "$root")" || is_live=1
    if [ "$is_live" = "0" ]; then
      refused=1
      echo ""
      echo "  ################################################################"
      echo "  ##  PRE-CLEAR REFUSED -- .clawdbot IS LIVE ON THIS BOX         ##"
      echo "  ################################################################"
      echo "  ##  Path : $root"
      echo "  ##  This box uses .clawdbot as a LIVE workspace/state root."
      echo "  ##  The documented 'mv ~/.clawdbot ~/.clawdbot.bak' pre-clear"
      echo "  ##  WAS NOT RUN. Running it would dangle live symlinks and/or"
      echo "  ##  orphan declared agent workspaces and take this box down."
      echo "  ##"
      echo "  ##  Evidence:"
      printf '%s\n' "$reasons" | sed 's/^/  ##  /'
      echo "  ##"
      echo "  ##  DO NOT roll this box to OpenClaw 2026.7.1 yet. A human must"
      echo "  ##  first migrate the live data OFF .clawdbot (relocate the"
      echo "  ##  workspace and repoint openclaw.json + symlinks at the real"
      echo "  ##  OpenClaw home), then re-run --preclear-check."
      echo "  ################################################################"
      echo ""
    else
      echo "  [preclear] no live signal found for $root"
    fi
  done < <(_pc_clawdbot_roots)

  # A stale plugins/installs.json is the OTHER half of the 2026.7.1 gate. It is
  # only ever renamed (never deleted) and only when the .clawdbot half cleared,
  # so a refused run leaves the box in exactly the state it started in.
  while IFS= read -r home; do
    [ -f "$home/plugins/installs.json" ] && { found=1; echo "  [preclear] found stale relic: $home/plugins/installs.json"; }
  done < <(_pc_openclaw_homes)

  if [ "$found" = "0" ]; then
    echo "  [preclear] no 2026.7.1 relics on this box -- nothing to do."
    return 0
  fi

  if [ "$refused" = "1" ]; then
    echo "  [preclear] RESULT: REFUSED (exit 3). Nothing was moved."
    return 3
  fi

  if [ "$mode" != "apply" ]; then
    echo "  [preclear] RESULT: SAFE to pre-clear. Re-run with --preclear-2026-7-1 to apply."
    return 0
  fi

  # ---- PASS 2: apply. Only reached when every root cleared detection. ----
  while IFS= read -r root; do
    [ -n "$root" ] || continue
    if mv "$root" "${root}.bak-pre-2026.7.1-${ts}" 2>/dev/null; then
      echo "  [preclear] renamed $root -> ${root}.bak-pre-2026.7.1-${ts}"
    else
      echo "  [preclear] ERROR: failed to rename $root -- leaving it in place" >&2
      refused=1
    fi
  done < <(_pc_clawdbot_roots)

  while IFS= read -r home; do
    [ -f "$home/plugins/installs.json" ] || continue
    if mv "$home/plugins/installs.json" "$home/plugins/installs.json.bak-pre-2026.7.1-${ts}" 2>/dev/null; then
      echo "  [preclear] renamed $home/plugins/installs.json -> installs.json.bak-pre-2026.7.1-${ts}"
    else
      echo "  [preclear] ERROR: failed to rename $home/plugins/installs.json" >&2
      refused=1
    fi
  done < <(_pc_openclaw_homes)

  if [ "$refused" = "1" ]; then
    echo "  [preclear] RESULT: INCOMPLETE (exit 3). Do not roll this box." >&2
    return 3
  fi
  echo "  [preclear] RESULT: pre-clear complete. Relics renamed, not deleted."
  return 0
}
# <<< TRAP1-PRECLEAR-END

# ----------------------------------------------------------
# LEGACY `agents.list` SCHEMA DETECTOR  (v22.0.8)
# ----------------------------------------------------------
# WHAT: reports whether this box's openclaw.json still carries the legacy
# `agents.list` array, and routes a migration request to the one procedure that
# can actually perform it (scripts/oc-atomic-upgrade.sh). It is a DETECTOR and a
# DISPATCHER — it never migrates a config itself, and on the roll path it never
# blocks. Both of those are deliberate; see the two numbered points below.
#
# THE LANDMINE. The 2026.7.2-beta line REJECTS that key outright:
#
#     Gateway failed to start: Invalid config at ~/.openclaw/openclaw.json:
#     agents: Unrecognized key: "list"
#
# The gateway exits 78 (EX_CONFIG) about 0.4s after launch. The shipped
# LaunchAgent sets KeepAlive with ThrottleInterval=10, so launchd respawns it
# every ~11s, forever. One affected box booted 701 times in 10 days before the
# crash-loop breaker latched channel auto-start OFF — at which point the box was
# COMPLETELY DARK: nothing in, nothing out, and 24 queued deliveries permanently
# lost.
#
# AND IT WAS SILENT. That LaunchAgent wrote StandardErrorPath = /dev/null, so
# the startup exception was DISCARDED — it survived only in
# /tmp/openclaw/openclaw-<date>.log. Ten days of investigation walked straight
# past the actual error for exactly that reason. (The plist defect is fixed
# separately, but a box provisioned before that fix still throws its startup
# errors away, so this gate must never depend on reading a gateway log.)
#
# WHY A *PRE*-UPGRADE GATE AND NOT A HEALTH CHECK. The key is harmless on
# 2026.7.1-2 — a box carrying it runs fine and looks completely healthy right up
# to the moment a version change moves it onto the beta line. By the time a
# health check could see the crash-loop, the client is already dark. The only
# useful place to look is BEFORE the box moves. At least one live box still
# carries this key today, safe only because of the line it happens to be on.
#
# WHY HERE (placement is load-bearing, same reason as heal_weekly_cron_updater
# and reap_dead_skill_manifest above): every exit path below the UPDATE-PENDING
# prompt and the version gate is an `exit 0`. A box carrying `agents.list` is
# precisely an ALREADY-POISONED box, i.e. exactly the box that reaches those
# early exits and would otherwise never be inspected. This call must stay above
# both of them.
#
# ⚠️ THIS GATE DOES NOT MIGRATE, AND IT NO LONGER BLOCKS THE ROLL. Both of
# those are corrections of a defect this gate shipped with, and the reasons are
# the whole point of this comment.
#
# (a) `openclaw doctor --fix` CANNOT PERFORM THIS MIGRATION. The first version
#     of this gate called it, because the gateway's own error text prescribes
#     it. Measured on 12 boxes: the config's SHA-256 was BYTE-IDENTICAL before
#     and after. `openclaw config schema` on 2026.7.1 / 2026.7.1-2 reports the
#     `agents` properties as exactly ["defaults","list"] — there is no `entries`
#     for it to migrate TO. It also has a measured SIDE EFFECT: on one box it
#     silently rewrote `agents.defaults.models` pins. So the old migrate path
#     could only ever fail its own re-validation, and it risked model pins to do
#     it. It is gone.
#
# (b) A SKILL ROLL IS NOT A VERSION CHANGE, SO REFUSING ONE PROTECTS NOTHING.
#     This updater installs no binary: it contains no `npm install -g openclaw`,
#     no `openclaw@<version>`, no `openclaw update/upgrade`, no docker pull (see
#     the note above preclear_2026_7_1, which says the same thing for the same
#     reason). The legacy key is harmless on the line these boxes are on. But
#     the earlier gate exited 78 on detection — which froze the roll on 35 of 38
#     boxes, AND the roll is the very thing that delivers scripts/ to a box
#     (deliver_canonical_scripts_tree, below this call). The gate was therefore
#     blocking the only delivery vehicle for its own fix: a deadlock in which
#     the tool that repairs the fleet can never reach the fleet.
#
#     So on a legacy box this gate now WARNS LOUDLY, records a marker, and lets
#     the roll proceed. Blocking is reserved for the paths that actually change
#     the version — the weekly `npm update -g openclaw` cron and the F1
#     remediations — which fail closed unless the atomic procedure runs.
#
# THE REAL MIGRATION lives in scripts/oc-atomic-upgrade.sh and is only valid
# INSIDE an upgrade window: gateway stopped and PROVEN stopped, new binary
# installed, config rewritten to `agents.entries`, verified lossless against the
# NEW schema, gateway started and proven to STAY up. It cannot be done earlier,
# because `additionalProperties:false` is set on `agents` in BOTH versions (no
# config is valid on both), the deployed runtime has NO `entries` reader (an
# early migration enumerates ZERO agents — a silent total outage), and a live
# gateway re-serializes openclaw.json about once a minute from an in-memory
# model that only knows `agents.list`, silently reverting anything written while
# it runs.
#
# THE WORKSPACE TRAP IS HANDLED UPSTREAM NOW. oc_resolve_workspace_announced()
# above reads `agents.entries.main.workspace` BEFORE the legacy array, so the
# resolved workspace — CANON_DIR, the symlink target for this box's shared
# AGENTS.md/TOOLS.md/USER.md — is invariant across the migration by
# construction. oc-atomic-upgrade.sh asserts that invariant before committing.
#
# WHY WE NEVER HAND-DELETE THE KEY. The legacy array holds agent definitions.
# Deleting it is not a migration; it is agent loss. The transform is `list` ->
# `entries` keyed by each agent's `id`, and nothing here improvises it.
#
# MODES (OPENCLAW_AGENTS_LIST_MODE, or the mode argument):
#   report   (default, used by the roll) detect and report. Never mutates.
#            Returns 0 even on a legacy box — see (b) — after writing the
#            marker file and printing the banner.
#   check    detect and report only, and RETURN 3 when the legacy key is
#            present. This is the pre-flight a fleet driver runs before it moves
#            any box onto a new build. Never mutates anything.
#   migrate  delegates to scripts/oc-atomic-upgrade.sh --upgrade if that tool is
#            on this box, and REFUSES if it is not. This gate never migrates by
#            itself: outside an upgrade window there is no correct migration.
#
# RETURNS: 0 = clear, or legacy-but-reported (report mode). 3 = REFUSED /
# needs a human, matching preclear_2026_7_1's contract.
#
# SELF-CONTAINED ON PURPOSE: this runs on the `curl ... | bash` path, BEFORE the
# repo is cloned, so it cannot source scripts/qc-assert-legacy-agents-list.sh.
# That script is the standalone/CI counterpart and asserts the same invariant.
# ----------------------------------------------------------
agents_list_gate() {
  # DEFAULT IS 'report', NOT 'migrate'. The roll changes no binary version, so
  # it has nothing to migrate for and everything to lose by refusing -- see (b)
  # in the block comment above.
  local mode="${1:-${OPENCLAW_AGENTS_LIST_MODE:-report}}"
  local ocjson verdict detail box marker atomic _al_rc

  box="$(hostname 2>/dev/null || uname -n 2>/dev/null || echo 'unknown-box')"
  ocjson="$HOME/.openclaw/openclaw.json"
  [ -f "/data/.openclaw/openclaw.json" ] && ocjson="/data/.openclaw/openclaw.json"

  if [ ! -f "$ocjson" ]; then
    echo "  [agents-list] no config at $ocjson (fresh box) -- nothing to inspect."
    return 0
  fi

  if ! command -v python3 >/dev/null 2>&1; then
    # We cannot READ the config, so we cannot prove the key is absent. An
    # unprovable absence is not an absence (see the negative-result contract in
    # this repo's other gates): refuse rather than assume clean.
    _agents_list_refuse_banner "$box" "$ocjson" \
      "python3 is NOT AVAILABLE on this box, so the config could not be parsed at all." \
      "The legacy \`agents.list\` key was NOT ruled out -- it was never looked for."
    return 3
  fi

  verdict="$(_agents_list_detect "$ocjson")"
  detail="${verdict#*|}"
  verdict="${verdict%%|*}"

  case "$verdict" in
    ABSENT)
      echo "  [agents-list] $ocjson carries no legacy \`agents.list\` key -- safe to proceed. ($detail)"
      return 0
      ;;
    UNDETERMINED)
      _agents_list_refuse_banner "$box" "$ocjson" \
        "The config could not be inspected: $detail" \
        "An unreadable config is NOT a clean config. Nothing was changed."
      return 3
      ;;
    PRESENT)
      : # fall through to the refuse/migrate decision below
      ;;
    *)
      _agents_list_refuse_banner "$box" "$ocjson" \
        "The detector returned an unrecognised verdict (${verdict:-<empty>})." \
        "Refusing to treat an unrecognised verdict as clean. Nothing was changed."
      return 3
      ;;
  esac

  echo ""
  echo "  [agents-list] LEGACY SCHEMA DETECTED on $box: $detail"

  # Record it where a human and the next sweep will both trip over it. A line in
  # a log nobody reads is how this fault stayed invisible for ten days.
  marker="$(dirname "$ocjson")/.openclaw-agents-list-legacy"
  {
    printf 'detected=%s\n' "$(date '+%Y-%m-%dT%H:%M:%S')"
    printf 'config=%s\n' "$ocjson"
    printf 'detail=%s\n' "$detail"
    printf 'remedy=bash %s/scripts/oc-atomic-upgrade.sh --upgrade\n' "$(dirname "$ocjson")"
  } > "$marker" 2>/dev/null || true

  # The atomic procedure, if this box has taken a roll that delivered it.
  atomic="$(dirname "$ocjson")/scripts/oc-atomic-upgrade.sh"

  if [ "$mode" = "check" ]; then
    # Pre-flight mode: a fleet driver asking "is this box safe to move?". The
    # answer is no, and it must be a non-zero one.
    _agents_list_refuse_banner "$box" "$ocjson" \
      "The legacy \`agents.list\` key IS PRESENT ($detail). This box MUST NOT be moved onto a new OpenClaw build as-is." \
      "Mode is 'check' -- detection only. Nothing was changed. Migrate it with: bash $atomic --upgrade"
    return 3
  fi

  if [ "$mode" = "migrate" ]; then
    # Delegate. This gate performs no migration itself, because outside an
    # upgrade window there is no correct one: the deployed runtime has no
    # `entries` reader, so writing the new shape here would enumerate ZERO
    # agents, and a live gateway would re-serialize the old shape back within
    # about a minute anyway.
    if [ ! -f "$atomic" ]; then
      _agents_list_refuse_banner "$box" "$ocjson" \
        "The legacy \`agents.list\` key IS PRESENT ($detail), and the atomic upgrade tool is NOT on this box (looked for $atomic)." \
        "Nothing was changed. Run a normal update-skills.sh roll first -- it delivers scripts/ to this box -- then re-run with --agents-list-migrate."
      return 3
    fi
    echo "  [agents-list] delegating to the atomic upgrade procedure: $atomic --upgrade"
    _al_rc=0
    bash "$atomic" --upgrade || _al_rc=$?
    if [ "$_al_rc" -eq 0 ]; then
      echo "  [agents-list] atomic upgrade COMPLETED -- this box is migrated and running."
      rm -f "$marker" 2>/dev/null || true
      return 0
    fi
    _agents_list_refuse_banner "$box" "$ocjson" \
      "The atomic upgrade procedure exited $_al_rc (78 = refused and rolled back, 70 = ROLLBACK FAILED and this box needs a human NOW, 3 = undetermined)." \
      "See its output above for the exact step that failed."
    return 3
  fi

  # ── DEFAULT ('report'): warn loudly, then LET THE ROLL PROCEED. ─────────────
  # This updater changes no OpenClaw binary, so it cannot trigger the landmine;
  # and it is the mechanism that delivers scripts/oc-atomic-upgrade.sh to this
  # box. Refusing here would block the only delivery vehicle for the fix on
  # every affected box -- a deadlock. Blocking belongs on the paths that DO
  # change the version: the weekly `npm update -g openclaw` cron and the F1
  # remediations, both of which fail closed without the atomic procedure.
  echo "  ################################################################"
  echo "  ##  LEGACY \`agents.list\` SCHEMA ON THIS BOX  --  NOT YET FATAL  ##"
  echo "  ################################################################"
  echo "  ##  Box    : $box"
  echo "  ##  Config : $ocjson"
  echo "  ##  Detail : $detail"
  echo "  ##"
  echo "  ##  This roll is CONTINUING on purpose: it installs no OpenClaw"
  echo "  ##  binary, so it cannot move this box onto the line that rejects"
  echo "  ##  the key -- and it is what delivers the fix below to this box."
  echo "  ##"
  echo "  ##  BUT THIS BOX IS NOT SAFE TO UPGRADE. The 2026.7.2-beta line"
  echo "  ##  rejects \`agents.list\` outright, the gateway exits 78 ~0.4s"
  echo "  ##  after start, launchd respawns it every ~11s, and the crash-loop"
  echo "  ##  breaker latches channels OFF until the box is COMPLETELY DARK."
  echo "  ##"
  echo "  ##  MIGRATE IT (stops the gateway, installs the new build, rewrites"
  echo "  ##  the config, verifies, restarts -- rolling back on any failure):"
  echo "  ##    bash $atomic --upgrade"
  echo "  ##  Inspect first, changing nothing:"
  echo "  ##    bash $atomic --detect"
  echo "  ##"
  echo "  ##  ⚠️  \`openclaw doctor --fix\` DOES NOT DO THIS. Measured on 12"
  echo "  ##  boxes: config SHA-256 identical before and after. It also"
  echo "  ##  silently rewrote agents.defaults.models pins on one box."
  echo "  ##"
  echo "  ##  Marker written: $marker"
  echo "  ################################################################"
  echo ""
  return 0
}

# Detect the legacy key in a config. Prints "<VERDICT>|<detail>" where VERDICT is
# ABSENT, PRESENT or UNDETERMINED. Never fails, never writes.
_agents_list_detect() {
  local cfg="$1" py out rc
  # The python source goes to a temp FILE and is then run as a plain
  # `python3 "$file"` command substitution -- never a heredoc directly inside
  # `$(...)`. bash 3.2.57 (stock macOS /bin/bash, which is what the fleet's Macs
  # run) has a parser bug where a multi-line `(` inside a heredoc BODY nested in
  # `$(...)` breaks its paren matching for the OUTER command substitution and
  # aborts at PARSE time. Dev boxes running Homebrew bash 5.x never see it, so
  # the heredoc form can look perfectly fine while being dead on every client
  # box. Same two-step, same reason, as scripts/qc-assert-config-write-chown.sh.
  # R0 (2026-08-11): NO literal suffix after the X's. BSD/macOS `mktemp` (every
  # Mac in the fleet) only substitutes a TRAILING run of X's -- a template
  # with anything after them (".py" here) is treated as a literal filename,
  # not a pattern: the first call "succeeds" by creating that exact
  # unrandomized file, and every call after it (or any concurrent run) fails
  # with "mkstemp failed ...: File exists" until that stale file is removed.
  # Proven via mutation test: `mktemp .../foo.XXXXXX.py` called twice in a row
  # fails the second time on this exact bash 3.2.57 / macOS mktemp; dropping
  # the suffix (`mktemp .../foo.XXXXXX`) succeeds every time. `python3 "$file"`
  # runs a script with no extension identically to one with `.py` -- the
  # suffix was cosmetic, never functional.
  py="$(mktemp "${TMPDIR:-/tmp}/agents-list-detect.XXXXXX")" || {
    printf 'UNDETERMINED|could not create a temp file to run the detector\n'; return 0; }
  cat > "$py" <<'PYEOF'
import json
import sys

try:
    with open(sys.argv[1], encoding='utf-8') as fh:
        cfg = json.load(fh)
except Exception as e:
    print('UNDETERMINED|cannot parse as JSON: %s' % e)
    raise SystemExit(0)

if not isinstance(cfg, dict):
    print('UNDETERMINED|top level is not a JSON object')
    raise SystemExit(0)

agents = cfg.get('agents')
if agents is None:
    print('ABSENT|no `agents` block at all')
    raise SystemExit(0)
if not isinstance(agents, dict):
    print('UNDETERMINED|`agents` is a %s, not an object' % type(agents).__name__)
    raise SystemExit(0)
if 'list' not in agents:
    print('ABSENT|`agents` block has %d key(s), none of them `list`' % len(agents))
    raise SystemExit(0)

val = agents['list']
if isinstance(val, list):
    shape = '%d entr(y/ies)' % len(val)
elif val is None:
    shape = 'null'
else:
    shape = 'a %s' % type(val).__name__
print('PRESENT|legacy `agents.list` key holds %s' % shape)
PYEOF
  rc=0
  out="$(python3 "$py" "$cfg" 2>&1)" || rc=$?
  rm -f "$py"
  if [ "$rc" -ne 0 ]; then
    printf 'UNDETERMINED|detector exited %s: %s\n' "$rc" "${out:-<no output>}"
    return 0
  fi
  if [ -z "$out" ]; then
    printf 'UNDETERMINED|detector produced no output\n'
    return 0
  fi
  printf '%s\n' "$out"
  return 0
}

# Print the workspace this config resolves to, using the SAME precedence as
# oc_resolve_workspace_announced(): agents.list[id=main].workspace first, then
# agents.defaults.workspace. Prints empty when neither is declared. Never fails,
# never writes. Used to prove a migration did not move the workspace.
_agents_list_workspace() {
  local cfg="$1" py out
  # R0 (2026-08-11): no literal suffix after the X's -- see the mktemp note in
  # _agents_list_detect() above (BSD/macOS mktemp does not randomize a
  # template with a trailing ".py"; the second call ever made to this exact
  # template fails "File exists" on every Mac in the fleet).
  py="$(mktemp "${TMPDIR:-/tmp}/agents-list-workspace.XXXXXX")" || { printf ''; return 0; }
  cat > "$py" <<'PYEOF'
import json
import os
import sys

try:
    with open(sys.argv[1], encoding='utf-8') as fh:
        cfg = json.load(fh)
    agents = cfg.get('agents') or {}
    if not isinstance(agents, dict):
        agents = {}
    for ag in (agents.get('list') or []):
        if isinstance(ag, dict) and ag.get('id') == 'main' and ag.get('workspace'):
            print(os.path.expanduser(ag['workspace']))
            raise SystemExit(0)
    defaults = agents.get('defaults') or {}
    ws = defaults.get('workspace') if isinstance(defaults, dict) else None
    if ws:
        print(os.path.expanduser(ws))
except SystemExit:
    raise
except Exception:
    pass
PYEOF
  out="$(python3 "$py" "$cfg" 2>/dev/null || true)"
  rm -f "$py"
  printf '%s' "$out"
  return 0
}

# Roll a config back from its backup. Uses `cat >` rather than `cp`/`mv` so the
# ORIGINAL inode, owner and mode survive: on a root-run updater a `cp` would
# leave openclaw.json owned root:root, the gateway (a non-root uid) would get
# EACCES on reload, and every config-touching feature would go dark while the
# gateway still reported healthy -- the exact fault
# scripts/qc-assert-config-write-chown.sh exists to catch.
_agents_list_restore() {
  local cfg="$1" backup="$2"
  # QC-ALLOW-NO-CHOWN: `cat >` writes THROUGH the existing inode, so the file's
  # owner, group and mode are unchanged by construction -- there is no ownership
  # to restore. A cp/mv here is what would need a chown; that is exactly why
  # this is a redirect.
  if cat "$backup" > "$cfg" 2>/dev/null; then
    echo "  [agents-list] config RESTORED from $backup (original inode/owner/mode preserved)" >&2
  else
    echo "  [agents-list] ✗ RESTORE FAILED -- the backup is still at $backup; restore it by hand before starting the gateway." >&2
  fi
}

# The one loud refusal banner, so every refusal path names the box, the config,
# the reason and the fix in the same shape. Matches preclear_2026_7_1's banner.
_agents_list_refuse_banner() {
  local box="$1" cfg="$2" reason="$3" state="$4"
  echo ""
  echo "  ################################################################"
  echo "  ##  ROLL REFUSED -- LEGACY \`agents.list\` SCHEMA GATE           ##"
  echo "  ################################################################"
  echo "  ##  Box    : $box"
  echo "  ##  Config : $cfg"
  echo "  ##"
  echo "  ##  $reason"
  echo "  ##  $state"
  echo "  ##"
  echo "  ##  WHY THIS BLOCKS THE ROLL:"
  echo "  ##    The 2026.7.2-beta line rejects that key outright --"
  echo "  ##      agents: Unrecognized key: \"list\""
  echo "  ##    -- and exits 78 (EX_CONFIG) ~0.4s after start. launchd's"
  echo "  ##    KeepAlive + ThrottleInterval=10 then respawns it every ~11s"
  echo "  ##    (701 boots in 10 days on the box this was measured on) until"
  echo "  ##    the crash-loop breaker latches channel auto-start OFF and the"
  echo "  ##    box goes COMPLETELY DARK. 24 queued deliveries were lost."
  echo "  ##"
  echo "  ##  IT IS SILENT: LaunchAgents provisioned before the plist fix set"
  echo "  ##  StandardErrorPath = /dev/null, so the startup exception is"
  echo "  ##  DISCARDED. Look in /tmp/openclaw/openclaw-<date>.log, NOT in the"
  echo "  ##  LaunchAgent's stderr -- there is none."
  echo "  ##"
  echo "  ##  THE FIX (run on the box, then re-run this):"
  echo "  ##    bash <oc-root>/scripts/oc-atomic-upgrade.sh --upgrade"
  echo "  ##"
  echo "  ##  ⚠️  NOT \`openclaw doctor --fix\`. It CANNOT do this: measured on"
  echo "  ##  12 boxes, the config SHA-256 was IDENTICAL before and after, and"
  echo "  ##  \`openclaw config schema\` on this line lists the agents keys as"
  echo "  ##  exactly [defaults, list] -- there is no \`entries\` to migrate to."
  echo "  ##  It also silently rewrote agents.defaults.models pins on one box."
  echo "  ##"
  echo "  ##  Verify it took (exit 0 = clean, 1 = still legacy, 3 = unreadable):"
  echo "  ##    bash scripts/qc-assert-legacy-agents-list.sh"
  echo "  ##"
  echo "  ##  DO NOT hand-delete the key, and DO NOT write \`entries\` early."
  echo "  ##  The array holds agent definitions, and the CURRENTLY INSTALLED"
  echo "  ##  runtime has no \`entries\` reader -- migrating before the binary"
  echo "  ##  changes enumerates ZERO agents: a silent total outage, worse"
  echo "  ##  than the crash-loop. The migration belongs INSIDE the upgrade"
  echo "  ##  window, which is what oc-atomic-upgrade.sh exists to provide."
  echo "  ##"
  echo "  ##  ⚠️  AFTER ANY plist CHANGE: \`launchctl kickstart -k\` does NOT"
  echo "  ##  reload a plist -- it only restarts the running process, and the"
  echo "  ##  OLD plist stays loaded. Activation needs bootout + bootstrap:"
  echo "  ##    launchctl bootout gui/\$(id -u)/<label> 2>/dev/null || true"
  echo "  ##    launchctl bootstrap gui/\$(id -u) <plist-path>"
  echo "  ################################################################"
  echo ""
}

# ----------------------------------------------------------
# R0 REGISTRY-PARITY GATE  (2026-08-11, post registry-strip incident)
# ----------------------------------------------------------
# WHAT HAPPENED THAT THIS GATE EXISTS TO CATCH: on 2026-08-11, 16 boxes had
# their `agents` registry reduced to `main`-only (every department
# de-registered) while a raw writer (source UNDETERMINED) raced a fleet roll.
# `config validate` returned valid (rc=0) on every one of them -- a config
# with zero departments is a perfectly valid config, so VALIDITY IS NOT
# HEALTH. Worse: THIS updater's own agents_list_gate() read the resulting
# near-empty/ABSENT registry as "safe to proceed" on every box it reached,
# because that gate checks SCHEMA SHAPE (does the legacy key exist), never
# COUNT. A roll that walks past a just-emptied registry calling it clean is
# exactly the failure this gate exists to close.
#
# ⚠️ NEVER TRUST `openclaw config validate` (or the ABSENT verdict from
# agents_list_gate) as a substitute for this check. This gate never calls
# validate and never treats ABSENT as automatically safe.
#
# TWO INDEPENDENT CHECKS. Either one alone REFUSES the run (exit 78):
#
#   (1) ABSOLUTE FLOOR (runs on 'pre' AND 'post'): the registry declares <= 1
#       agent while this box's own `<oc-root>/agents/` directory tree still
#       holds > 2 per-agent subdirectories. Those directories are created and
#       gate-tested elsewhere in this repo as a 1:1 mapping to
#       `agents.list[].id` / `agents.entries` keys (see
#       23-ai-workforce-blueprint/scripts/verify-wiring.sh, which already
#       fails loud when that pairing breaks) -- so a registry that has
#       collapsed while the directories it is supposed to describe are still
#       there is exactly the strip signature, not a coincidence. This check
#       alone would have refused every one of the 15 reached boxes in the
#       2026-08-11 incident.
#   (2) REGRESSION (runs on 'post' only, against the 'pre' snapshot captured
#       earlier in THIS SAME RUN): the registry's entry COUNT dropped, or any
#       agent id present at 'pre' is MISSING at 'post' -- even if the total
#       count happens to match (a drop-one/add-one swap can hide a real loss
#       behind a matching total; identity is checked, not just count). This
#       catches partial loss below the absolute floor, and loss with no
#       surviving directory evidence at all.
#
# NEVER AUTO-RESTORES. A parity violation could be an intentional, human-
# driven roster change (a real department retirement) -- indistinguishable
# from damage by this gate alone. On violation it writes a marker, prints a
# banner designed to be impossible to miss, best-effort escalates to Rescue
# Rangers (a documented no-op when the webhook env vars are not set -- most
# boxes today -- in which case the marker + banner ARE the escalation
# record), and REFUSES. A human, or the box's own standing sentinel, makes
# the call on whether the change was intended.
#
# PLACEMENT IS LOAD-BEARING, same reason as agents_list_gate's placement
# above it: 'pre' must run before ANY write this updater makes; 'post' must
# run after EVERY write this updater makes, immediately before the final
# return -- see the two call sites (search REGISTRY-PARITY-CALL).
#
# SCHEMA-AGNOSTIC ON PURPOSE. Reads BOTH `agents.list` (array, current fleet
# schema -- confirmed zero `agents.entries` readers anywhere in this repo as
# of this commit) and `agents.entries` (object, the post-migration schema),
# taking the union of ids if a config somehow briefly carries both. A box
# migrated by the atomic upgrade procedure is measured the same way as one
# still on the legacy schema.
# ----------------------------------------------------------
_REGISTRY_PARITY_PRE_VERDICT=""
_REGISTRY_PARITY_PRE_COUNT=""
_REGISTRY_PARITY_PRE_IDS=""
_REGISTRY_PARITY_PRE_DIRCOUNT=""

_registry_parity_ocjson() {
  local p="$HOME/.openclaw/openclaw.json"
  [ -f "/data/.openclaw/openclaw.json" ] && p="/data/.openclaw/openclaw.json"
  printf '%s' "$p"
}

_registry_parity_agentsdir() {
  local p="$HOME/.openclaw/agents"
  [ -d "/data/.openclaw/agents" ] && p="/data/.openclaw/agents"
  printf '%s' "$p"
}

# Prints "<verdict>|<count>|<comma-separated-sorted-ids>" for the agents
# registry in $1 (an openclaw.json path). verdict is OK, ABSENT or
# UNDETERMINED. Never fails, never writes to $1.
_registry_snapshot() {
  local cfg="$1" py out rc
  if [ ! -f "$cfg" ]; then
    printf 'NO-CONFIG|0|\n'
    return 0
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    printf 'UNDETERMINED|0|python3 not on PATH\n'
    return 0
  fi
  # Same bash-3.2.57-heredoc-in-$()-parser workaround as _agents_list_detect
  # above: write the python source to a temp FILE and run it as a plain
  # command substitution, never a heredoc directly inside $(...). No literal
  # suffix after the X's -- see the mktemp note in _agents_list_detect():
  # BSD/macOS mktemp does not randomize ".XXXXXX.py"; found by this gate's
  # OWN test suite failing "File exists" on the second call.
  py="$(mktemp "${TMPDIR:-/tmp}/registry-snapshot.XXXXXX")" || {
    printf 'UNDETERMINED|0|could not create a temp file to run the detector\n'; return 0; }
  cat > "$py" <<'PYEOF'
import json
import sys

try:
    with open(sys.argv[1], encoding='utf-8') as fh:
        cfg = json.load(fh)
except Exception as e:
    print('UNDETERMINED|0|cannot parse as JSON: %s' % e)
    raise SystemExit(0)

if not isinstance(cfg, dict):
    print('UNDETERMINED|0|top level is not a JSON object')
    raise SystemExit(0)

agents = cfg.get('agents')
if agents is None:
    print('ABSENT|0|no `agents` block at all')
    raise SystemExit(0)
if not isinstance(agents, dict):
    print('UNDETERMINED|0|`agents` is not an object')
    raise SystemExit(0)

has_entries = isinstance(agents.get('entries'), dict)
has_list = isinstance(agents.get('list'), list)

if not has_entries and not has_list:
    print('ABSENT|0|no `agents.list` or `agents.entries` key present')
    raise SystemExit(0)

ids = set()
if has_entries:
    for k in agents['entries'].keys():
        ids.add(str(k))
if has_list:
    for item in agents['list']:
        if isinstance(item, dict) and item.get('id'):
            ids.add(str(item['id']))

ids_sorted = sorted(ids)
print('OK|%d|%s' % (len(ids_sorted), ','.join(ids_sorted)))
PYEOF
  rc=0
  out="$(python3 "$py" "$cfg" 2>&1)" || rc=$?
  rm -f "$py"
  if [ "$rc" -ne 0 ]; then
    printf 'UNDETERMINED|0|detector exited %s: %s\n' "$rc" "${out:-<no output>}"
    return 0
  fi
  if [ -z "$out" ]; then
    printf 'UNDETERMINED|0|detector produced no output\n'
    return 0
  fi
  printf '%s\n' "$out"
  return 0
}

# Prints "<count>|<sorted-comma-list>" of subdirectories under $1. "0|" when
# the directory does not exist (fresh/unprovisioned box -- not a fault, just
# no baseline to compare against).
_registry_agent_dirs() {
  local dir="$1" n=0 f b names=""
  if [ ! -d "$dir" ]; then
    printf '0|\n'
    return 0
  fi
  for f in "$dir"/*/; do
    [ -d "$f" ] || continue
    b="$(basename "$f")"
    n=$((n + 1))
    if [ -z "$names" ]; then names="$b"; else names="$names,$b"; fi
  done
  if [ "$n" -gt 0 ]; then
    names="$(printf '%s' "$names" | tr ',' '\n' | sort | tr '\n' ',' | sed 's/,$//')"
  fi
  printf '%s|%s\n' "$n" "$names"
  return 0
}

# The one loud refusal banner for a parity violation, plus the marker file
# and the best-effort RR escalation. Matches the shape of
# _agents_list_refuse_banner above so every gate in this file refuses the
# same way.
_registry_parity_refuse() {
  local box="$1" cfg="$2" phase="$3" reason="$4" detail="$5" marker
  marker="$(dirname "$cfg")/.openclaw-registry-parity-refused"
  {
    printf 'refused_at=%s\n' "$(date '+%Y-%m-%dT%H:%M:%S')"
    printf 'phase=%s\n' "$phase"
    printf 'box=%s\n' "$box"
    printf 'config=%s\n' "$cfg"
    printf 'reason=%s\n' "$reason"
    printf 'detail=%s\n' "$detail"
  } > "$marker" 2>/dev/null || true

  echo ""
  echo "  ################################################################"
  echo "  ##  ROLL REFUSED -- REGISTRY-PARITY GATE ($phase)"
  echo "  ################################################################"
  echo "  ##  Box    : $box"
  echo "  ##  Config : $cfg"
  echo "  ##"
  echo "  ##  $reason"
  echo "  ##  $detail"
  echo "  ##"
  echo "  ##  \`openclaw config validate\` WOULD PASS on this box right now --"
  echo "  ##  a config with zero (or fewer) departments is a perfectly valid"
  echo "  ##  config. Validity is not health. Do not use it to override this."
  echo "  ##"
  echo "  ##  THIS GATE NEVER AUTO-RESTORES. A parity violation could be an"
  echo "  ##  intended roster change; only a human (or this box's own"
  echo "  ##  standing sentinel) can tell the difference. Marker written:"
  echo "  ##    $marker"
  echo "  ##"
  echo "  ##  RECOVERY: look for a pre-incident backup BEFORE restoring"
  echo "  ##  anything -- verify its agent count first:"
  echo "  ##    ${cfg}.bak-pre-agents-list-migration-*"
  echo "  ##    ${cfg}.last-good  (⚠ can be poisoned by the same writer that"
  echo "  ##                       caused the loss -- verify its count too)"
  echo "  ##  Copy whichever backup verifies clean to a path no updater or"
  echo "  ##  migration touches BEFORE restoring it."
  echo "  ################################################################"
  echo ""

  _registry_parity_escalate "$box" "$cfg" "$phase" "$reason" "$detail"
}

# Best-effort Rescue Rangers escalation. NEVER fails the gate: on most boxes
# today RESCUE_RANGERS_WEBHOOK_URL is not set, and that is a documented,
# silent no-op -- the marker file and banner above are the escalation record
# in that case. When it IS set, POSTs the same nine-field payload shape the
# agent-side escalation template uses (rescue-escalation-section.md.tpl).
_registry_parity_escalate() {
  local box="$1" cfg="$2" phase="$3" reason="$4" detail="$5" payload rc
  if [ -z "${RESCUE_RANGERS_WEBHOOK_URL:-}" ]; then
    echo "  [registry-parity] RESCUE_RANGERS_WEBHOOK_URL not set on this box -- skipping the live escalation POST. The marker file and banner above ARE the escalation record." >&2
    return 0
  fi
  if ! command -v curl >/dev/null 2>&1 || ! command -v python3 >/dev/null 2>&1; then
    echo "  [registry-parity] curl or python3 not on PATH -- skipping the live escalation POST." >&2
    return 0
  fi
  # No literal suffix after the X's -- see the mktemp note in
  # _agents_list_detect() above.
  payload="$(mktemp "${TMPDIR:-/tmp}/registry-parity-escalation.XXXXXX")" || return 0
  RPG_BOX="${FLEET_STANDING_BOX_SLUG:-$box}" RPG_PHASE="$phase" RPG_REASON="$reason" RPG_DETAIL="$detail" RPG_CFG="$cfg" \
    python3 -c '
import json, os
print(json.dumps({
    "action": "escalate",
    "person": "update-skills.sh registry-parity gate (automated)",
    "clientName": "a box",
    "agentName": "registry-parity-gate",
    "boxName": os.environ.get("RPG_BOX", "unknown-box"),
    "boxType": "unknown",
    "openclawVersion": "unknown",
    "problem": "REGISTRY-STRIP (%s): %s" % (os.environ.get("RPG_PHASE", ""), os.environ.get("RPG_REASON", "")),
    "alreadyTried": "registry-parity gate refused the roll (exit 78) and wrote a marker next to %s; no restore attempted. %s" % (os.environ.get("RPG_CFG", ""), os.environ.get("RPG_DETAIL", "")),
    "returnTo": "repo-gate",
}))
' > "$payload" 2>/dev/null

  # NOT a bash array here on purpose. `"${arr[@]}"` on a ZERO-LENGTH array
  # under `set -u` (this script runs `set -euo pipefail`) throws "unbound
  # variable" on stock bash 3.2.57 and would ABORT the whole updater at
  # exactly the moment it is trying to report a registry-parity refusal --
  # the CLAUDE.md negative-result contract names this exact trap ("bash 3.2
  # `set -u` on an empty array"). Two explicit curl invocations instead of
  # one array-built one: more lines, zero cleverness, nothing to trip on.
  rc=0
  if [ -n "${RESCUE_RANGERS_WEBHOOK_SECRET:-}" ]; then
    curl -s -m 10 -X POST "$RESCUE_RANGERS_WEBHOOK_URL" \
      -H "Content-Type: application/json" \
      -H "X-Rescue-Secret: ${RESCUE_RANGERS_WEBHOOK_SECRET}" \
      --data-binary "@$payload" >/dev/null 2>&1 || rc=$?
  else
    curl -s -m 10 -X POST "$RESCUE_RANGERS_WEBHOOK_URL" \
      -H "Content-Type: application/json" \
      --data-binary "@$payload" >/dev/null 2>&1 || rc=$?
  fi
  rm -f "$payload" 2>/dev/null || true
  if [ "$rc" -ne 0 ]; then
    echo "  [registry-parity] escalation POST failed/unavailable (rc=$rc, non-fatal) -- marker + banner remain the record." >&2
  else
    echo "  [registry-parity] escalation POSTed to Rescue Rangers." >&2
  fi
  return 0
}

# The gate itself. $1 = "pre" or "post". Returns 0 = clear, 78 = REFUSED (a
# parity violation was found -- the caller must exit 78 immediately, matching
# the same EX_CONFIG contract agents_list_gate uses).
registry_parity_gate() {
  local phase="$1" ocjson agentsdir box
  local snap sverdict scount sids dirsnap dircount dirnames

  box="$(hostname 2>/dev/null || uname -n 2>/dev/null || echo 'unknown-box')"
  ocjson="$(_registry_parity_ocjson)"
  agentsdir="$(_registry_parity_agentsdir)"

  if [ ! -f "$ocjson" ]; then
    echo "  [registry-parity:$phase] no config at $ocjson (fresh box) -- nothing to check."
    [ "$phase" = "pre" ] && _REGISTRY_PARITY_PRE_VERDICT="NO-CONFIG"
    return 0
  fi

  snap="$(_registry_snapshot "$ocjson")"
  sverdict="${snap%%|*}"
  scount="$(printf '%s' "$snap" | cut -d'|' -f2)"
  sids="$(printf '%s' "$snap" | cut -d'|' -f3-)"

  dirsnap="$(_registry_agent_dirs "$agentsdir")"
  dircount="${dirsnap%%|*}"
  dirnames="${dirsnap#*|}"

  echo "  [registry-parity:$phase] registry=$sverdict count=$scount ids=[${sids:-<none>}] | agents-dir($agentsdir) count=$dircount"

  if [ "$sverdict" = "UNDETERMINED" ]; then
    echo "  [registry-parity:$phase] ⚠ config could not be read/parsed -- an unreadable config is NOT proof of a healthy registry. Count checks SKIPPED this phase (not silently passed)."
    [ "$phase" = "pre" ] && _REGISTRY_PARITY_PRE_VERDICT="UNDETERMINED"
    return 0
  fi

  # Normalize ABSENT/NO-CONFIG to a zero count for the arithmetic below.
  case "$sverdict" in ABSENT|NO-CONFIG) scount=0 ;; esac

  # ---- CHECK 1: ABSOLUTE FLOOR (every phase) ----
  if [ "$scount" -le 1 ] && [ "$dircount" -gt 2 ]; then
    _registry_parity_refuse "$box" "$ocjson" "$phase" \
      "ABSOLUTE FLOOR: the registry declares only $scount agent(s) (ids=[${sids:-<none>}]) while $agentsdir holds $dircount agent subdirectories (names=[${dirnames:-<none>}])." \
      "This is the exact signature of the 2026-08-11 registry-strip incident: the on-disk agent identities survived; only the registry pointing to them was emptied."
    return 78
  fi

  if [ "$phase" = "pre" ]; then
    _REGISTRY_PARITY_PRE_VERDICT="$sverdict"
    _REGISTRY_PARITY_PRE_COUNT="$scount"
    _REGISTRY_PARITY_PRE_IDS="$sids"
    _REGISTRY_PARITY_PRE_DIRCOUNT="$dircount"
    return 0
  fi

  # ---- CHECK 2: REGRESSION (post only, vs this run's own pre snapshot) ----
  if [ -z "$_REGISTRY_PARITY_PRE_VERDICT" ] || [ "$_REGISTRY_PARITY_PRE_VERDICT" = "UNDETERMINED" ] || [ "$_REGISTRY_PARITY_PRE_VERDICT" = "NO-CONFIG" ]; then
    echo "  [registry-parity:post] no usable 'pre' snapshot from this run (was: ${_REGISTRY_PARITY_PRE_VERDICT:-<never captured>}) -- regression check skipped; the absolute-floor check above still ran."
    return 0
  fi

  if [ "$scount" -lt "$_REGISTRY_PARITY_PRE_COUNT" ]; then
    _registry_parity_refuse "$box" "$ocjson" "post" \
      "REGRESSION: the registry held $_REGISTRY_PARITY_PRE_COUNT agent(s) at the START of this run and holds only $scount now." \
      "pre ids=[${_REGISTRY_PARITY_PRE_IDS:-<none>}]  post ids=[${sids:-<none>}]. This run's own writes are not trusted; nothing after this point in the run proceeds."
    return 78
  fi

  # Identity check: every id present at 'pre' must still be present at
  # 'post', even if the count happens to match -- a drop-one/add-one swap is
  # not a loss by count, but it IS a loss of that specific agent.
  local missing="" id_pre save_ifs
  save_ifs="$IFS"
  IFS=','
  for id_pre in $_REGISTRY_PARITY_PRE_IDS; do
    IFS="$save_ifs"
    [ -z "$id_pre" ] && continue
    case ",${sids}," in
      *",${id_pre},"*) : ;;
      *)
        if [ -z "$missing" ]; then missing="$id_pre"; else missing="$missing,$id_pre"; fi
        ;;
    esac
    IFS=','
  done
  IFS="$save_ifs"

  if [ -n "$missing" ]; then
    _registry_parity_refuse "$box" "$ocjson" "post" \
      "IDENTITY LOSS: agent id(s) present at the START of this run are GONE from the registry now: [$missing]." \
      "pre ids=[${_REGISTRY_PARITY_PRE_IDS:-<none>}]  post ids=[${sids:-<none>}]. Count alone did not catch this -- a swap can hide a real loss behind a matching total."
    return 78
  fi

  echo "  [registry-parity:post] ✓ no loss: pre=$_REGISTRY_PARITY_PRE_COUNT post=$scount, all pre ids still present."
  return 0
}

# ----------------------------------------------------------
# SELF-HEAL: weekly-cron updater URL
# ----------------------------------------------------------
# THE BUG THIS REPAIRS
# Two updaters used to live in this repo under the same filename. THIS one
# (repo root update-skills.sh) is the canonical one: it carries the wiring,
# state-machine, A3 content-gate and manifest/stamp pipeline.
# scripts/update-skills.sh was a much smaller, independently-maintained
# script that only copied skills and never received any of the fixes below
# it -- a real 3-box pilot ran it (via a stale cron/doc reference) and
# produced a byte-identical AGENTS.md every week while its own version stamp
# climbed: a hollow update reported as a success. It is now RETIRED to a
# loud-failing shim (see scripts/update-skills.sh's own header) that exits
# non-zero unconditionally, so a wrong invocation can never again silently
# "succeed". This self-heal still exists to repoint any box whose weekly
# cron script still names that path -- pointing at the shim is loudly wrong
# in its own right now, but repointing it to the real URL is strictly better
# than leaving a box's cron broken.
#
# Every box runs $HOME/.openclaw/skills/.update-restart-if-needed from a Sunday
# 03:00 cron. scripts/setup-weekly-update.sh was corrected on 2026-06-27
# (6a881c8a) to install the ROOT url, but NOTHING rewrote the copy already on
# disk -- so every box provisioned BEFORE that date runs the LEGACY path
# every week, forever (and now gets a loud failure instead of a hollow
# success). This function repoints those boxes.
#
# HISTORY -- READ THIS BEFORE DELETING THE SELF-HEAL (updated at the PR #670 /
# PR #671 merge, so the comment does not outlive the facts it describes)
# When #670 was written, scripts/update-skills.sh was VERSION-GATED: a skill
# whose local skill-version.txt matched the staged string was SKIPPED without
# its contents ever being examined, shared-utils/ and universal-sops/ were not
# referenced anywhere in the file, and the version stamp was written ANYWAY.
# It therefore stamped boxes as current that were not, and that poisoned stamp
# then made THIS script's "Already up to date" gate exit 0 without copying
# anything -- a fleet roll read a matching stamp and silently no-oped while
# reporting success.
#
# BOTH halves of that were fixed in the same merge as this comment originally
# landed:
#   * scripts/update-skills.sh (at the time) started deciding per skill on
#     CONTENT, delivering shared-utils/ and universal-sops/, and WITHHOLDING
#     the stamp (exit 1) when a source file was still absent after the copy.
#   * this script's same-version non-interactive branch no longer blind-exits;
#     it runs a CONTENT RECHECK before deciding (see _SAME_VERSION_RECHECK).
# So a poisoned stamp is no longer produced, and an existing one no longer
# blinds this script. scripts/update-skills.sh has since been retired
# entirely (see above) -- the fleet-wide fix is no longer "make the legacy
# script safer", it is "there is only one updater, and the other name fails
# loudly". The self-heal below is still correct and still wanted -- it
# repoints a box's weekly cron to the URL that is actually canonical. Boxes
# still on the legacy URL re-fetch that file from main on every run, so they
# hit the loud shim failure immediately regardless of whether this heal fires
# -- the heal just gets them back to a WORKING weekly update sooner.
#
# PLACEMENT IS LOAD-BEARING
# The call site sits BEFORE the UPDATE-PENDING prompt and BEFORE the version
# gate -- both of which `exit 0`. A self-heal placed after either one would
# never execute on precisely the boxes that are already poisoned, i.e. the only
# boxes it exists to rescue. Do not move this call below the version gate.
#
# SAFETY
# The edit is surgical (the URL line only), always takes a timestamped backup
# first, and rewrites through a temp file + `cat >` so the original inode and
# its 0700 permissions are preserved. It never CREATES the cron script and
# never touches crontab -- installing a cron remains setup-weekly-update.sh's
# job. On a box that is already correct it is a silent no-op.
#
# PATH NOTE: this targets $HOME/.openclaw/skills explicitly rather than
# $SKILLS_DIR. discover_skills_dir() resolves to /data/.openclaw/skills on VPS
# platforms, but setup-weekly-update.sh hardcodes the $HOME path when it writes
# the cron script -- so $HOME is where the file to repair actually lives. Both
# are checked anyway (deduplicated) in case a box differs.
# ----------------------------------------------------------
CANONICAL_UPDATER_URL="https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/update-skills.sh"
LEGACY_UPDATER_PATH_FRAGMENT="main/scripts/update-skills.sh"

heal_one_weekly_cron_updater() {
  local cron_script="$1"

  # Never CREATE the cron script here -- only repair one already on disk.
  [ -f "$cron_script" ] || return 0

  if ! grep -q "$LEGACY_UPDATER_PATH_FRAGMENT" "$cron_script" 2>/dev/null; then
    echo "  [cron-heal] OK -- already points at the root updater: $cron_script"
    return 0
  fi

  echo "  [cron-heal] LEGACY updater URL detected in $cron_script"

  local backup="${cron_script}.bak.$(date +%Y%m%d-%H%M%S)"
  # Disk pre-check before the copy: a cron script is tiny, but a box with no
  # room left must say so here rather than write a truncated backup and then
  # edit the original against it.
  if ! oc_backup_precheck_disk "$backup" "$(oc_backup_size_kb "$cron_script")" "cron-heal backup of $cron_script"; then
    echo "  [cron-heal] WARN: no disk headroom for a backup -- refusing to edit $cron_script"
    return 0
  fi
  if ! cp -p "$cron_script" "$backup" 2>/dev/null; then
    echo "  [cron-heal] WARN: could not write a backup -- refusing to edit $cron_script"
    return 0
  fi
  # RETENTION: prune sibling .bak.<ts> copies of THIS cron script only, and
  # only now that this run's backup is on disk. Every self-heal run used to
  # leave another .bak.<ts> behind forever.
  oc_backup_prune "$(dirname "$cron_script")" "$(basename "$cron_script").bak." "$backup"

  local tmp
  tmp="$(mktemp "${TMPDIR:-/tmp}/cron-heal-XXXXXX" 2>/dev/null)" || {
    echo "  [cron-heal] WARN: mktemp failed -- leaving $cron_script untouched"
    return 0
  }

  # Portable in-place edit: BSD sed (-i '') and GNU sed (-i) disagree on the
  # backup-suffix argument, so write to a temp file and copy it back instead of
  # using sed -i at all. `cat > "$cron_script"` (not mv) preserves the original
  # inode, owner and 0700 mode -- an mv would install the temp file's 0600.
  if sed "s|${LEGACY_UPDATER_PATH_FRAGMENT}|main/update-skills.sh|g" "$cron_script" > "$tmp" 2>/dev/null \
     && [ -s "$tmp" ] \
     && grep -q "$CANONICAL_UPDATER_URL" "$tmp" \
     && ! grep -q "$LEGACY_UPDATER_PATH_FRAGMENT" "$tmp"; then
    cat "$tmp" > "$cron_script"
    rm -f "$tmp"
    echo "  [cron-heal] REPOINTED legacy -> root updater"
    echo "               script: $cron_script"
    echo "               backup: $backup"
  else
    rm -f "$tmp"
    echo "  [cron-heal] WARN: rewrite produced unexpected content -- original left untouched"
  fi
}

heal_weekly_cron_updater() {
  local seen=""
  local candidate
  for candidate in "$HOME/.openclaw/skills/.update-restart-if-needed" \
                   "${SKILLS_DIR:-}/.update-restart-if-needed"; do
    case "$candidate" in
      /.update-restart-if-needed|"") continue ;;   # empty SKILLS_DIR guard
    esac
    case " $seen " in
      *" $candidate "*) continue ;;               # already healed this path
    esac
    seen="$seen $candidate"
    heal_one_weekly_cron_updater "$candidate"
  done
}

# >>> CANONICAL-SCRIPTS-DELIVERY-BEGIN
# Deliver the complete canonical scripts/ tree additively. Canonical paths are
# authoritative for their own content and modes, while box-local paths absent
# from the repo are deliberately retained. This matches install.sh's existing
# merge/add behavior and avoids deleting legitimate local operator tooling.
# $3 (optional) is a display label only — the delivery logic is identical for
# scripts/ and for config/ (v21.6.0 reuses it verbatim for config/ so the pin
# file gets the SAME completeness receipt: byte-compare + exec-bit + symlink
# verification, not a bare `cp` exit code).
deliver_canonical_scripts_tree() {
  local src_root="$1" dest_root="$2" label="${3:-scripts/}"
  local src_path rel dest_path failures=0 files=0

  if [ ! -d "$src_root" ]; then
    # A MISSING SOURCE is a real content failure (nothing to deliver): fatal.
    echo "FATAL: canonical $label tree is missing: $src_root" >&2
    return 1
  fi

  # A ROOT-OWNED / otherwise-unwritable destination is an OWNERSHIP quirk (≈6 VPS
  # boxes carry $OC_ROOT/scripts owned root:root, so the node-user cp fails
  # "Permission denied"), NOT a content mismatch. Pre-fix this returned 1 and the
  # caller exited BEFORE the content/version-stamp write — the "optional/env step
  # aborts the updater before the stamp" bug class. It must instead: try to
  # self-heal the perms, and if it genuinely cannot write, DEGRADE with a LOUD,
  # ACTIONABLE chown instruction (return 2) so the run proceeds to the stamp.
  # A cp failure on a WRITABLE dest stays fatal (return 1) — that is a real
  # delivery failure, not an ownership quirk.
  local _owner_hint
  _owner_hint="$(id -un 2>/dev/null || printf '%s' "${USER:-node}")"
  _scripts_perms_degrade() {
    echo "WARN: canonical $label could not be written to: $dest_root" >&2
    echo "WARN: this is an OWNERSHIP quirk (destination not writable by $_owner_hint — likely owned root:root), NOT a content failure." >&2
    echo "WARN: the updater will PROCEED so an ownership quirk cannot block skills content + the version stamp; $label delivery is DEFERRED." >&2
    echo "WARN: ACTION REQUIRED on this box:  sudo chown -R $_owner_hint \"$dest_root\"   then re-run the updater to complete $label delivery." >&2
  }

  if ! mkdir -p "$dest_root" 2>/dev/null; then
    # Best-effort self-heal of the parent, then retry once.
    chmod u+rwx "$(dirname "$dest_root")" 2>/dev/null || true
    if ! mkdir -p "$dest_root" 2>/dev/null; then
      _scripts_perms_degrade
      return 2
    fi
  fi
  if ! cp -Rp "$src_root/." "$dest_root/" 2>/dev/null; then
    # Best-effort self-heal (only succeeds if we own the tree), then retry.
    chmod -R u+rwx "$dest_root" 2>/dev/null || true
    if ! cp -Rp "$src_root/." "$dest_root/" 2>/dev/null; then
      if [ ! -w "$dest_root" ]; then
        _scripts_perms_degrade
        return 2
      fi
      echo "FATAL: recursive canonical $label delivery failed: $src_root -> $dest_root" >&2
      return 1
    fi
  fi

  # A successful cp exit alone is not a completeness receipt. Re-read every
  # canonical entry and prove structure, bytes/symlink targets, and executable
  # status at the destination before the updater can reach its success stamp.
  while IFS= read -r -d '' src_path; do
    rel="${src_path#"$src_root"/}"
    dest_path="$dest_root/$rel"
    if [ -L "$src_path" ]; then
      if [ ! -L "$dest_path" ] || [ "$(readlink "$src_path" 2>/dev/null || true)" != "$(readlink "$dest_path" 2>/dev/null || true)" ]; then
        echo "FATAL: $label delivery symlink mismatch: $rel" >&2
        failures=$((failures + 1))
      fi
    elif [ -d "$src_path" ]; then
      if [ ! -d "$dest_path" ]; then
        echo "FATAL: $label delivery directory missing: $rel" >&2
        failures=$((failures + 1))
      fi
    elif [ -f "$src_path" ]; then
      files=$((files + 1))
      if [ ! -f "$dest_path" ] || ! cmp -s "$src_path" "$dest_path"; then
        echo "FATAL: $label delivery file missing or changed: $rel" >&2
        failures=$((failures + 1))
      elif { [ -x "$src_path" ] && [ ! -x "$dest_path" ]; } \
        || { [ ! -x "$src_path" ] && [ -x "$dest_path" ]; }; then
        echo "FATAL: $label delivery executable-bit mismatch: $rel" >&2
        failures=$((failures + 1))
      fi
    else
      echo "FATAL: unsupported canonical $label entry type: $rel" >&2
      failures=$((failures + 1))
    fi
  done < <(find "$src_root" -mindepth 1 -print0)

  if [ "$failures" -ne 0 ]; then
    echo "FATAL: canonical $label delivery incomplete ($failures mismatch(es)); success stamp withheld" >&2
    return 1
  fi
  echo "  ✓ Full canonical $label tree delivered and verified ($files files; additive, local-only files retained)"
}
# <<< CANONICAL-SCRIPTS-DELIVERY-END
# ----------------------------------------------------------
# U006 — Co-locate the canonical presentation entry script + its guard
# into the materialized Presentations department scripts/ directory.
# ----------------------------------------------------------
colocate_presentation_entry() {
  if ! oc_resolve_workspace_announced "presentation entry co-location"; then
    echo "  [U006] presentation entry co-location SKIPPED (workspace not resolvable)" >&2
    return 0
  fi
  WORKSPACE_DIR="$OC_WS_RESOLVED"
  local dept_scripts="$WORKSPACE_DIR/departments/Presentations/scripts"
  if [ ! -d "$dept_scripts" ]; then
    echo "  [U006] presentation entry co-location SKIPPED (department not materialized at $dept_scripts)" >&2
    return 0
  fi
  local src_dir="$SKILLS_DIR/23-ai-workforce-blueprint/scripts"
  local copied=0
  for f in presentation-canonical-entry.sh deck-build-guard.sh; do
    if [ -f "$src_dir/$f" ]; then
      cp "$src_dir/$f" "$dept_scripts/$f" && chmod +x "$dept_scripts/$f" && copied=$((copied + 1))
    fi
  done
  if [ "$copied" -eq 2 ]; then
    echo "  [U006] co-located presentation-canonical-entry.sh + deck-build-guard.sh -> $dept_scripts/"
  else
    echo "  [U006] presentation entry co-location partial (copied $copied of 2 files -> $dept_scripts/)" >&2
  fi
}
# <<< U006-COLOCATE-PRESENTATION-ENTRY-END

# ----------------------------------------------------------
# U001 — Dual Sunday cron mutex + legacy crontab retirement
#
# Two Sunday update mechanisms can fire at the same instant on
# Eastern-timezone boxes: the OpenClaw cron `weekly-onboarding-update`
# (0 3 * * 0 America/New_York) and a legacy Unix crontab entry
# (0 3 * * 0, system-local timezone). With no mutual exclusion, two
# concurrent update-skills.sh processes race. acquire_update_lock is
# the FIRST action in main(): a second concurrent invocation exits
# immediately with a distinct "LOCK HELD" result instead of running
# the update. retire_legacy_sunday_crontab removes the colliding
# crontab entry (with backup + owner notification) so both mechanisms
# cannot stay silently active.
# ----------------------------------------------------------
UPDATE_LOCK_PATH="/tmp/openclaw-update.lock"
UPDATE_LOCK_FD=""
UPDATE_LOCK_PID_FILE=""

# Acquire the global update lock; MUST be the first call in main().
# Prefers flock(1) where available; on hosts without it (e.g. macOS)
# falls back to an atomic O_EXCL lock file holding the owner PID, with
# stale-lock recovery when the recorded PID is no longer running.
# Returns 0 with the lock held; exits 1 if another live instance
# holds it (distinct "LOCK HELD" message, never a double-execute).
acquire_update_lock() {
  if command -v flock >/dev/null 2>&1; then
    exec {UPDATE_LOCK_FD}>"$UPDATE_LOCK_PATH" || {
      echo "FATAL: cannot open lock file $UPDATE_LOCK_PATH" >&2
      exit 1
    }
    if ! flock -n "$UPDATE_LOCK_FD"; then
      echo "LOCK HELD: another update-skills.sh instance is already running (lock: $UPDATE_LOCK_PATH)" >&2
      exit 1
    fi
    echo "  [lock] acquired $UPDATE_LOCK_PATH (flock)"
    return 0
  fi

  # Portable fallback: atomic mkdir (O_EXCL semantics) + PID liveness.
  UPDATE_LOCK_PID_FILE="$UPDATE_LOCK_PATH/pid"
  if mkdir "$UPDATE_LOCK_PATH" 2>/dev/null; then
    echo "$$" > "$UPDATE_LOCK_PID_FILE"
    echo "  [lock] acquired $UPDATE_LOCK_PATH (pid $$)"
    return 0
  fi
  local holder
  holder="$(cat "$UPDATE_LOCK_PID_FILE" 2>/dev/null || true)"
  if [ -n "$holder" ] && kill -0 "$holder" 2>/dev/null; then
    echo "LOCK HELD: another update-skills.sh instance is already running (pid $holder, lock: $UPDATE_LOCK_PATH)" >&2
    exit 1
  fi
  # Stale lock: recorded owner is dead — take over.
  rm -rf "$UPDATE_LOCK_PATH" 2>/dev/null || true
  if mkdir "$UPDATE_LOCK_PATH" 2>/dev/null; then
    echo "$$" > "$UPDATE_LOCK_PID_FILE"
    echo "  [lock] cleared stale lock (dead pid ${holder:-unknown}); acquired $UPDATE_LOCK_PATH (pid $$)"
    return 0
  fi
  echo "FATAL: cannot create lock directory $UPDATE_LOCK_PATH (permissions or path error)" >&2
  exit 1
}

# Release the update lock on exit (wired via trap in main).
release_update_lock() {
  if [ -n "$UPDATE_LOCK_FD" ]; then
    flock -u "$UPDATE_LOCK_FD" 2>/dev/null || true
    return 0
  fi
  if [ -n "$UPDATE_LOCK_PID_FILE" ] && [ "$(cat "$UPDATE_LOCK_PID_FILE" 2>/dev/null || true)" = "$$" ]; then
    rm -rf "$UPDATE_LOCK_PATH" 2>/dev/null || true
  fi
}

# Detect a legacy Unix crontab entry `0 3 * * 0` (system-local timezone)
# that collides with the OpenClaw cron weekly-onboarding-update
# (0 3 * * 0 America/New_York). Returns 0 when at least one such entry
# exists, 1 otherwise.
detect_legacy_sunday_crontab() {
  crontab -l 2>/dev/null | grep -Eq '^[[:space:]]*0[[:space:]]+3[[:space:]]+\*[[:space:]]+\*[[:space:]]+(0|7|0,6)([[:space:]]|$)'
}

# Retire the legacy Sunday crontab entry that collides with the OpenClaw
# weekly-onboarding-update cron: backs up the current crontab, removes
# every `0 3 * * 0` line, reinstalls the filtered crontab, and prints an
# owner notification. The OpenClaw cron (America/New_York) remains the
# sole Sunday update mechanism.
retire_legacy_sunday_crontab() {
  if ! command -v crontab >/dev/null 2>&1; then
    return 0
  fi
  if ! detect_legacy_sunday_crontab; then
    echo "  [crontab] no legacy Sunday '0 3 * * 0' crontab entry found — nothing to retire"
    return 0
  fi
  local backup tmp
  backup="${HOME}/.crontab.bak-dual-sunday-$(date +%Y%m%d-%H%M%S)"
  tmp="$(mktemp "${TMPDIR:-/tmp}/crontab-u001.XXXXXX" 2>/dev/null)" || {
    echo "  [crontab] WARNING: mktemp failed — legacy Sunday crontab entry NOT retired; both update mechanisms may fire at 3:00 AM" >&2
    return 0
  }
  if ! crontab -l > "$backup" 2>/dev/null; then
    echo "  [crontab] WARNING: could not back up crontab to $backup — legacy entry NOT retired" >&2
    rm -f "$tmp" 2>/dev/null || true
    return 0
  fi
  grep -Ev '^[[:space:]]*0[[:space:]]+3[[:space:]]+\*[[:space:]]+\*[[:space:]]+(0|7|0,6)([[:space:]]|$)' "$backup" > "$tmp" || true
  if crontab "$tmp" 2>/dev/null; then
    echo "  [crontab] RETIRED legacy Sunday '0 3 * * 0' crontab entry (backup: $backup)"
    echo "  [crontab] OWNER NOTICE: the system crontab Sunday update was removed to prevent a"
    echo "  [crontab] double-run with the OpenClaw weekly-onboarding-update cron (0 3 * * 0 America/New_York)."
    echo "  [crontab] The OpenClaw cron is now the sole Sunday update mechanism. Restore from the"
    echo "  [crontab] backup with 'crontab $backup' if you intentionally ran both."
  else
    echo "  [crontab] WARNING: failed to reinstall filtered crontab — original left intact (backup: $backup)" >&2
  fi
  rm -f "$tmp" 2>/dev/null || true
}

# ----------------------------------------------------------
# Main update logic
# ----------------------------------------------------------
main() {
  # ----------------------------------------------------------
  # U001 — MUTEX (MUST stay the first action in main): take the global
  # update lock before anything else runs, then retire any legacy
  # Sunday crontab entry that would double-fire with the OpenClaw cron.
  # ----------------------------------------------------------
  acquire_update_lock
  trap release_update_lock EXIT
  retire_legacy_sunday_crontab

  # ----------------------------------------------------------
  # SECURITY/PRIVACY (v20.0.9) — MAINTENANCE-SILENT for the WHOLE roll. A fleet
  # ----------------------------------------------------------
  # SECURITY/PRIVACY (v20.0.9) — MAINTENANCE-SILENT for the WHOLE roll. A fleet
  # roll / skill update is inherently MAINTENANCE: no step may push an internal
  # notification to a client chat. Export OPENCLAW_MAINTENANCE_SILENT=1 for the
  # entire duration of this run so EVERY subprocess it spawns inherits it —
  # migrate-existing-workforce.sh (which runs qc-completeness.sh at its Step 5)
  # AND the embedded qc-completeness.sh call later in this function.
  # qc-completeness.sh treats this as a HARD send-suppression gate that is
  # INDEPENDENT of any box's chat/account config, so a box whose operator-
  # escalation chat is mis-pointed at the client still cannot leak the QC gap
  # table during a roll. It gates NOTIFICATION only, never what QC computes.
  # ----------------------------------------------------------
  export OPENCLAW_MAINTENANCE_SILENT=1

  # ----------------------------------------------------------
  # Parse CLI args: --only "05,06,35" installs only those skill folders
  # (number prefix matches skill folder name prefix)
  # ----------------------------------------------------------
  ONLY_SKILLS=""
  # TRAP 1: the 2026.7.1 relic pre-clear is OPT-IN ONLY (see preclear_2026_7_1
  # above for why: this updater performs no OpenClaw binary upgrade).
  PRECLEAR_MODE=""
  if [ "${OPENCLAW_PRECLEAR_2026_7_1:-0}" = "1" ]; then
    PRECLEAR_MODE="apply"
  fi
  # Standalone legacy-`agents.list` run (--agents-list-check/--agents-list-migrate).
  # Empty = not standalone; the gate still runs automatically inside the roll.
  AGENTS_LIST_STANDALONE=""
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --only)
        shift
        ONLY_SKILLS="${1:-}"
        ;;
      --only=*)
        ONLY_SKILLS="${1#--only=}"
        ;;
      --preclear-check)
        PRECLEAR_MODE="check"
        ;;
      --preclear-2026-7-1)
        PRECLEAR_MODE="apply"
        ;;
      # Legacy `agents.list` gate, run standalone. The gate ALSO runs
      # automatically on every roll (see the call in main() below) -- these
      # flags exist to inspect or migrate a box on its own, before a version
      # change, without performing a skill update.
      --agents-list-check)
        AGENTS_LIST_STANDALONE="check"
        ;;
      --agents-list-migrate)
        AGENTS_LIST_STANDALONE="migrate"
        ;;
      --help|-h)
        echo "Usage: update-skills.sh [--only \"05,06,35\"] [--preclear-check | --preclear-2026-7-1]"
        echo "                        [--agents-list-check | --agents-list-migrate]"
        echo "  --only LIST   Install only skill folders whose number prefix matches LIST (comma-separated)"
        echo "                Example: --only \"05,06,36\" installs only skills 05-ghl-setup, 06-ghl-install-pages, 36-ghl-mcp-setup"
        echo "  (no flag)     Install/update all skills"
        echo ""
        echo "  --preclear-check       Report whether this box carries OpenClaw 2026.7.1 startup-gate"
        echo "                         relics (~/.clawdbot, plugins/installs.json) and whether they are"
        echo "                         SAFE to move. Never moves anything. Exit 3 = live, needs a human."
        echo ""
        echo "  --agents-list-check    Report whether this box's openclaw.json still carries the LEGACY"
        echo "                         \`agents.list\` array. Never changes anything. Exit 3 = present."
        echo "                         This is the pre-flight to run against every box BEFORE moving any"
        echo "                         of them onto a new OpenClaw build."
        echo "  --agents-list-migrate  Delegates to scripts/oc-atomic-upgrade.sh --upgrade, which is the"
        echo "                         only procedure that can do this safely: it STOPS the gateway (and"
        echo "                         proves it stopped), installs the new build, rewrites the config"
        echo "                         from \`agents.list\` to \`agents.entries\`, verifies the rewrite is"
        echo "                         lossless against the NEW schema, restarts, and proves the gateway"
        echo "                         STAYS up -- rolling back binary AND config on any failure."
        echo "                         NOTE: \`openclaw doctor --fix\` does NOT perform this migration."
        echo "                         Measured on 12 boxes: config SHA-256 identical before and after."
        echo "                         (The detector also runs automatically on every normal update run,"
        echo "                         where it reports and does not block.)"
        echo ""
        echo "  --preclear-2026-7-1    Same detection, then rename the relics (never deletes) -- but ONLY"
        echo "                         if nothing on this box still depends on .clawdbot. Exit 3 = refused."
        echo "                         Needed only immediately before an OpenClaw binary roll to 2026.7.1;"
        echo "                         a normal update run performs no binary upgrade and does not need it."
        exit 0
        ;;
    esac
    shift || true
  done

  # TRAP 1: pre-clear runs standalone and exits -- it is a pre-roll maintenance
  # action, not part of a skill update. Exit 3 propagates "REFUSED / needs a
  # human" to whatever fleet driver invoked it, so a roll halts loudly instead
  # of proceeding to a version bump that would down the box.
  if [ -n "$PRECLEAR_MODE" ]; then
    local _pc_rc=0
    preclear_2026_7_1 "$PRECLEAR_MODE" || _pc_rc=$?
    exit "$_pc_rc"
  fi

  # Standalone legacy-`agents.list` run: inspect (or migrate) this box and exit
  # WITHOUT performing a skill update. This is the pre-flight a fleet driver runs
  # against every box BEFORE it moves any of them onto a new OpenClaw build.
  # Exit 3 = REFUSED / needs a human (same contract as the pre-clear above).
  if [ -n "$AGENTS_LIST_STANDALONE" ]; then
    local _al_rc=0
    agents_list_gate "$AGENTS_LIST_STANDALONE" || _al_rc=$?
    exit "$_al_rc"
  fi

  echo "============================================"
  echo "   OpenClaw Skills Updater (Mac)"
  echo "   Version: ${ONBOARDING_VERSION}"
  if [ -n "$ONLY_SKILLS" ]; then
    echo "   Mode: SELECTIVE -- only [$ONLY_SKILLS]"
  fi
  echo "============================================"
  echo ""

  # Discover skills directory
  SKILLS_DIR=$(discover_skills_dir)
  export SKILLS_DIR
  echo "  📂 Skills directory: $SKILLS_DIR"

  # MERGE NOTE (PR #670 + PR #671): both of these landed at this exact spot,
  # independently, and for the SAME structural reason — every exit path below
  # this line is an `exit 0`, so anything that must reach an already-poisoned
  # or already-stamped box has to run here. Both are kept. Neither may be moved
  # below the UPDATE-PENDING prompt or the version gate.

  # SELF-HEAL the weekly cron's updater URL. See heal_weekly_cron_updater above
  # for the full rationale. This MUST stay above the UPDATE-PENDING prompt and
  # the version gate below -- both of them `exit 0`, and a box already poisoned
  # by the legacy updater is exactly the box that hits those early exits.
  heal_weekly_cron_updater

  # Reap the dead version-string manifest BEFORE any exit path below (the
  # pending-flag decline at "Update cancelled" and the already-up-to-date
  # no-op both exit 0 without reaching the sync). A box must be cleaned even
  # on a run that copies nothing. See reap_dead_skill_manifest() for why this
  # file is deleted rather than restamped.
  reap_dead_skill_manifest

  # LEGACY `agents.list` SCHEMA DETECTOR. See agents_list_gate() above for the
  # full rationale. Placement is load-bearing for the SAME reason as the two
  # calls immediately above: every exit path below this line is an `exit 0`, and
  # a box carrying `agents.list` is exactly an already-poisoned box that would
  # otherwise reach one of those early exits and never be inspected.
  #
  # ⚠️ A LEGACY CONFIG NO LONGER BLOCKS THIS ROLL, AND THAT IS THE FIX, NOT A
  # RELAXATION. The previous version exited 78 here on detection. Because this
  # updater installs no OpenClaw binary, that refusal prevented no crash — while
  # freezing the roll on 35 of 38 boxes, including the roll that delivers
  # scripts/oc-atomic-upgrade.sh (deliver_canonical_scripts_tree, below). The
  # gate was blocking the only delivery vehicle for its own remedy. In 'report'
  # mode the detector now warns loudly, writes a marker, and returns 0.
  #
  # WHAT STILL BLOCKS: a return of 3, which the detector reserves for the
  # genuinely UNKNOWN — an unparseable config, or no python3 to read it with. An
  # absence that cannot be proven is not an absence, and a box whose config does
  # not parse is not a box to keep writing to. That population is disjoint from
  # the 35: their configs parse fine, they simply carry the old key.
  #
  # The version-changing paths are where the real block lives now, and they fail
  # closed without the atomic procedure: the weekly `npm update -g openclaw`
  # cron (scripts/setup-weekly-update.sh) and the F1 remediations
  # (scripts/fleet-audit-remediate.sh, scripts/u126-remediate.sh).
  _AGENTS_LIST_RC=0
  agents_list_gate || _AGENTS_LIST_RC=$?
  if [ "$_AGENTS_LIST_RC" -ne 0 ]; then
    echo "FATAL: the \`agents.list\` schema detector could NOT READ this box's config (exit 78 / EX_CONFIG)." >&2
    echo "       This is the fail-closed path for an UNKNOWN, not for a known-legacy box." >&2
    echo "       Nothing was installed and no version stamp was written." >&2
    exit 78
  fi

  # REGISTRY-PARITY-CALL (pre). See registry_parity_gate() above for the full
  # rationale. Placement is load-bearing for the SAME reason as
  # agents_list_gate immediately above: this must run before ANY write this
  # updater makes, so the baseline snapshot reflects the box exactly as it
  # was found, not as this run has already started changing it. It ALSO
  # catches a box that arrives here ALREADY stripped (the absolute-floor
  # check does not need a 'post' phase to fire) -- a state the schema gate
  # above cannot see, because ABSENT is exactly what that gate calls "safe to
  # proceed."
  _REGISTRY_PARITY_RC=0
  registry_parity_gate pre || _REGISTRY_PARITY_RC=$?
  if [ "$_REGISTRY_PARITY_RC" -ne 0 ]; then
    echo "FATAL: registry-parity gate REFUSED this roll (exit 78 / EX_CONFIG) -- see the banner above." >&2
    echo "       Nothing was installed and no version stamp was written." >&2
    exit 78
  fi

  # ----------------------------------------------------------
  # Catchup check: if last weekly cron check is older than 7 days,
  # surface a note so the user knows the Sunday cron may have missed.
  # ----------------------------------------------------------
  if [ -f "$SKILLS_DIR/.last-update-check" ]; then
    LAST_CHECK_TS=$(date -j -f "%Y-%m-%dT%H:%M:%SZ" "$(cat "$SKILLS_DIR/.last-update-check")" +%s 2>/dev/null || \
                    date -d "$(cat "$SKILLS_DIR/.last-update-check")" +%s 2>/dev/null || echo 0)
    NOW_TS=$(date +%s)
    if [ "$LAST_CHECK_TS" -gt 0 ]; then
      DAYS_SINCE=$(( (NOW_TS - LAST_CHECK_TS) / 86400 ))
      if [ "$DAYS_SINCE" -gt 7 ]; then
        echo "  ℹ️  Weekly Sunday check last ran ${DAYS_SINCE} days ago -- your machine may have been asleep."
        echo "      This manual run will catch up."
      fi
    fi
  fi

  # Check for UPDATE PENDING flag
  PENDING_FILE=$(check_update_pending)
  if [ -n "$PENDING_FILE" ]; then
    echo "  ⚠️  UPDATE PENDING flag found at: $PENDING_FILE"
    echo "      Review this file before updating: cat $PENDING_FILE"
    echo ""
    # TTY GUARD (v17.0.18): only prompt when stdin is an interactive terminal.
    # Non-interactive (cron / curl|bash / SSH pipe): auto-decline so the updater
    # can never hang on stdin during a re-roll. Interactive behaviour is unchanged.
    if [ -t 0 ]; then
      read -p "Continue with update? (y/N) " -n 1 -r
      echo
    else
      echo "  (non-interactive: no TTY — auto-declining the pending-flag prompt)"
      REPLY="N"
    fi
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
      echo "  Update cancelled."
      exit 0
    fi
  fi

  # Check current version
  CURRENT_VERSION=$(get_current_version)
  if [ -n "$CURRENT_VERSION" ]; then
    echo "  Current version: $CURRENT_VERSION"
    echo "  Latest version:  $ONBOARDING_VERSION"
    if [ "$CURRENT_VERSION" = "$ONBOARDING_VERSION" ]; then
      echo ""
      # TTY GUARD (v17.0.18): a re-roll at the SAME version always reaches this
      # prompt. Only prompt on an interactive terminal; non-interactively
      # auto-decline the force-reinstall and exit 0 (already up to date — a clean,
      # idempotent no-op) instead of hanging on stdin.
      if [ -t 0 ]; then
        read -p "Already up to date. Force re-install? (y/N) " -n 1 -r
        echo
      else
        # CONTENT-AWARE EXIT (fleet fix). A matching stamp is NOT evidence that
        # the installed content matches canonical. ONE string governs 62 skill
        # trees plus shared-utils/ and universal-sops/ — and neither of those two
        # carries a version file at all. Exiting here meant an arbitrarily
        # drifted box was never compared, never repaired, and still reported
        # success: the fleet-wide false-success path. We now continue far enough
        # to PULL the source and diff it against the box (see CONTENT RECHECK
        # below). If the content genuinely matches we exit 0 seconds later,
        # BEFORE anything is copied, wired, or restarted — the same clean
        # idempotent no-op as before, only now it is earned rather than assumed.
        echo "  (non-interactive: no TTY — stamp is current; verifying CONTENT before deciding)"
        _SAME_VERSION_RECHECK=1
        REPLY="Y"
      fi
      if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "  Update cancelled."
        exit 0
      fi
    fi
  else
    echo "  No previous version found -- fresh install"
  fi

  echo ""
  echo "  Downloading latest skills from GitHub..."

  # v10.15.18: clone instead of curl|unzip. Info-ZIP's `unzip` MANGLES UTF-8
  # filenames (the role-library has em-dash filenames like
  # `qc-specialist----sales.md` and `deep-research-role----openclaw-maintenance.md`)
  # and silently partial-writes them, so a zip-based update would drop or
  # corrupt those role docs. `git clone` preserves every filename byte-for-byte.
  TEMP_ZIP="/tmp/openclaw-onboarding-update.zip"
  TEMP_EXTRACT="/tmp/openclaw-onboarding-update"
  rm -rf "$TEMP_EXTRACT" "$TEMP_ZIP"
  EXTRACTED_DIR=""

  if command -v git >/dev/null 2>&1; then
    if git clone --depth 1 "https://github.com/trevorotts1/openclaw-onboarding.git" "$TEMP_EXTRACT" 2>/dev/null; then
      # HARD verify the remote is exactly the intended repo (no leftover-clone mix-up)
      _origin="$(git -C "$TEMP_EXTRACT" remote get-url origin 2>/dev/null)"
      case "$_origin" in
        https://github.com/trevorotts1/openclaw-onboarding.git|https://github.com/trevorotts1/openclaw-onboarding)
          EXTRACTED_DIR="$TEMP_EXTRACT"
          # A2: capture source git SHA for content-manifest
          SRC_GIT_SHA="$(git -C "$TEMP_EXTRACT" rev-parse HEAD 2>/dev/null || echo "")"
          SRC_FROM_ZIP=0 ;;
        *)
          echo "ERROR: cloned remote ($_origin) is NOT trevorotts1/openclaw-onboarding -- refusing to use it."
          rm -rf "$TEMP_EXTRACT"; EXTRACTED_DIR="" ;;
      esac
    fi
  fi

  # Fallback ONLY if git is unavailable or the clone failed: zip + Mac-native
  # `ditto` (NOT Info-ZIP unzip) which handles UTF-8 filenames correctly.
  if [ -z "$EXTRACTED_DIR" ]; then
    echo "  (git clone unavailable/failed -- falling back to zip + ditto)"
    curl -fSL --progress-bar "https://github.com/trevorotts1/openclaw-onboarding/archive/refs/heads/main.zip" -o "$TEMP_ZIP"
    rm -rf "$TEMP_EXTRACT"; mkdir -p "$TEMP_EXTRACT"
    if command -v ditto >/dev/null 2>&1; then
      ditto -x -k "$TEMP_ZIP" "$TEMP_EXTRACT" 2>/dev/null || true
    else
      unzip -qo "$TEMP_ZIP" -d "$TEMP_EXTRACT" 2>/dev/null || true
    fi
    if [ -d "$TEMP_EXTRACT/openclaw-onboarding-main" ]; then
      EXTRACTED_DIR="$TEMP_EXTRACT/openclaw-onboarding-main"
    else
      # v16.2.13: `| head -1` closes the pipe early → `find` can die with SIGPIPE
      # (rc 141) which `pipefail` promotes to the pipeline status; `|| true` keeps
      # the plain assignment from aborting the updater under `set -e` (the first
      # dir is still captured before the SIGPIPE).
      EXTRACTED_DIR=$(find "$TEMP_EXTRACT" -maxdepth 1 -mindepth 1 -type d | head -1 || true)
    fi
    # A2: zip fallback — no git SHA available; content-set hash still works
    SRC_GIT_SHA="zip-fallback-$(date -u +%Y%m%dT%H%M%SZ)"
    SRC_FROM_ZIP=1
  fi

  if [ -z "$EXTRACTED_DIR" ] || [ ! -d "$EXTRACTED_DIR" ]; then
    echo "ERROR: Could not obtain the latest skills (git clone + zip fallback both failed)"
    rm -rf "$TEMP_EXTRACT" "$TEMP_ZIP"
    exit 1
  fi

  # v10.15.48: canonical onboarding dir for the freshly-pulled repo. Root-level
  # scripts/ (apply-fleet-standards.sh, ghl-mcp-autostart.sh, the new
  # resume-onboarding wiring) live here. Previously $ONBOARDING_DIR was
  # referenced (fleet-standards call) but never set under `set -u` -- a latent
  # bug. Define it once here so every downstream script reference resolves.
  ONBOARDING_DIR="$EXTRACTED_DIR"
  export ONBOARDING_DIR

  # scripts/ is outside SKILLS_DIR and therefore outside the numbered-skill
  # content manifest below. Deliver and verify it BEFORE the same-version
  # content-clean early exit; otherwise a box with current skills but a legacy
  # 22-file scripts allowlist would incorrectly no-op forever.
  _OC_SCRIPTS_DEST="$HOME/.openclaw/scripts"
  [ -d "/data/.openclaw" ] && _OC_SCRIPTS_DEST="/data/.openclaw/scripts"
  # rc 0 = delivered+verified; rc 1 = real fatal (missing source / genuine
  # delivery failure on a writable dest); rc 2 = OWNERSHIP quirk (dest not
  # writable). Only rc 1 withholds the stamp. rc 2 DEGRADES: a root-owned
  # scripts dir must not fatal-abort the whole run one step before content +
  # stamp — the chown is surfaced loudly and applied box-side in the Reroll.
  _SCRIPTS_RC=0
  deliver_canonical_scripts_tree "$ONBOARDING_DIR/scripts" "$_OC_SCRIPTS_DEST" || _SCRIPTS_RC=$?
  if [ "$_SCRIPTS_RC" -eq 1 ]; then
    echo "FATAL: updater cannot continue with a partial scripts directory; success stamp withheld" >&2
    rm -rf "$TEMP_EXTRACT" "$TEMP_ZIP"
    exit 1
  elif [ "$_SCRIPTS_RC" -eq 2 ]; then
    export OC_SCRIPTS_DELIVERY_DEFERRED=1
    echo "  ⚠ scripts/ delivery DEFERRED (destination not writable — see the chown ACTION above). Continuing so an ownership quirk does not block skills content or the version stamp." >&2
  fi
  export OC_PERSISTENT_SCRIPTS_DIR="$_OC_SCRIPTS_DEST"

  # >>> CANONICAL-CONFIG-DELIVERY-BEGIN  (v21.6.0 / R1)
  # config/ is a SIBLING of scripts/ and, until now, was delivered by NOTHING on
  # this path. update-skills.sh cloned the repo to a temp dir, copied scripts/
  # out of it, and DELETED the clone — so config/ghl-mcp-pin.env, the file
  # v21.5.0 called "the single source of truth for every launch surface", never
  # reached a single box. Every weekly-updated box fell through to the hardcoded
  # fallback constants inside ghl-mcp-autostart.sh, a pin bump propagated
  # nowhere, and the box-side QC gate hard-failed (proven: box layout rc=1, repo
  # layout rc=0 — CI was green only because CI runs in the one layout where the
  # file exists).
  #
  # The destination is the SIBLING of scripts/, so the consumers' first resolver
  # candidate ("$SELF_DIR/../config/…") hits it directly.
  OC_CANONICAL_CONFIG_DEST="$(dirname "$_OC_SCRIPTS_DEST")/config"
  _CONFIG_RC=0
  deliver_canonical_scripts_tree "$ONBOARDING_DIR/config" "$OC_CANONICAL_CONFIG_DEST" "config/" || _CONFIG_RC=$?
  # DEGRADE, never abort. scripts/ is fatal on rc=1 because every skill depends
  # on it; config/ currently carries the GHL Tier 2 pin and cron.d, so aborting
  # a whole fleet update over it would be disproportionate — and unnecessary,
  # because the consequence is already fail-closed and self-announcing: every
  # launch surface reports PIN_UNVERIFIED and refuses to build or start rather
  # than falling back to a stale constant. Loud, not fatal.
  if [ "$_CONFIG_RC" -ne 0 ]; then
    export OC_CONFIG_DELIVERY_DEFERRED=1
    echo "  ⚠ config/ delivery DEGRADED (rc=$_CONFIG_RC) — continuing so a config/ problem cannot block skills content or the version stamp." >&2
  fi

  # ASSERT-ON-LAND. A cp that exited 0 is not a receipt. This is the exact
  # invariant whose absence made v21.5.0 a repo-only release, so it is checked
  # explicitly and LOUDLY rather than inferred from the delivery function's rc.
  # It is deliberately NOT fatal: a box that fails here still gets its skills
  # and its version stamp, and every launch surface now refuses fail-closed
  # (STATUS: PIN_UNVERIFIED) rather than silently building an unvetted tree —
  # so the failure is impossible to miss and impossible to act on unsafely.
  if [ -r "$OC_CANONICAL_CONFIG_DEST/ghl-mcp-pin.env" ]; then
    echo "  ✓ config/ghl-mcp-pin.env delivered and readable at $OC_CANONICAL_CONFIG_DEST/ghl-mcp-pin.env"
  else
    echo "  ✗ config/ghl-mcp-pin.env is NOT readable at $OC_CANONICAL_CONFIG_DEST/ghl-mcp-pin.env after delivery." >&2
    echo "    CONSEQUENCE: scripts/ghl-mcp-autostart.sh will report STATUS: ghl-mcp-autostart=PIN_UNVERIFIED and will NOT build or start the Tier 2 GHL MCP on this box." >&2
    echo "    ACTION: check ownership/permissions on $OC_CANONICAL_CONFIG_DEST, then re-run this updater." >&2
    export OC_PIN_DELIVERY_FAILED=1
  fi
  export OC_PERSISTENT_CONFIG_DIR="$OC_CANONICAL_CONFIG_DEST"
  # <<< CANONICAL-CONFIG-DELIVERY-END

  # A2: Compute SOURCE manifest from the pulled tree BEFORE the copy loop.
  # This is what the destination must match after install (A3 gate).
  _CONTENT_HASH_SCRIPT="$EXTRACTED_DIR/scripts/skill-content-hash.sh"
  SRC_MANIFEST=""
  if [ -f "$_CONTENT_HASH_SCRIPT" ]; then
    SRC_MANIFEST=$(bash "$_CONTENT_HASH_SCRIPT" "$EXTRACTED_DIR" 2>/dev/null || true)
    printf '%s\n' "$SRC_MANIFEST" > /tmp/openclaw-update-src-manifest.txt
    echo "  [A2] Source content manifest computed ($(echo "$SRC_MANIFEST" | wc -l | tr -d ' ') lines)"
  else
    echo "  [A2] skill-content-hash.sh not found in source — content verification unavailable (non-fatal for this install)"
    SRC_MANIFEST=""
  fi

# ────────────────────────────────────────────────────────────────────────────
# CONTENT COMPARISON — the sync signal. Version strings are NOT.
#
# WHY: canonical routinely edits a skill tree's contents WITHOUT bumping that
# tree's skill-version.txt (23 of 62 versioned trees were in that state at
# origin/main 2d7bb304). A sync that decides on version-string equality
# therefore reports "unchanged" for trees whose bytes differ, and shared-utils/
# and universal-sops/ carry no version file at all, so a version gate has
# nothing to evaluate for them. Decisions below are made on CONTENT.
#
# DIRECTIONAL ON PURPOSE: `_OC_TREE_MISSING` = a SOURCE file that is absent on
# the box (or an entire absent tree). `_OC_TREE_DIFFERS` = a source file present
# on the box with different bytes. Destination-only extras (__pycache__, *.bak,
# runtime logs, per-box resolved artifacts) are NOT drift and must never force a
# re-copy or fail a gate — the copy semantics are an additive merge, so
# "source ⊆ dest, byte-for-byte" is the correct and complete health assertion.
#
# FAIL-CLOSED: if `diff` is unavailable we report drift, so the caller re-syncs
# rather than silently skipping.
#
# NOTE: the `case` patterns below interpolate directory paths. Glob metacharacters
# in a skills-dir path would widen the match; all real paths are $HOME/... or
# /tmp/... so this is safe in practice, and a widened match can only cause an
# extra (harmless) re-sync, never a skipped one.
# ────────────────────────────────────────────────────────────────────────────
_OC_TREE_MISSING=""
_OC_TREE_DIFFERS=""
_ocs_tree_compare() {
  local _src="${1%/}" _dst="${2%/}" _out _line
  _OC_TREE_MISSING=""
  _OC_TREE_DIFFERS=""
  [ -d "$_src" ] || return 0
  if ! command -v diff >/dev/null 2>&1; then
    _OC_TREE_MISSING=" (diff unavailable — assuming drift)"
    return 0
  fi
  if [ ! -d "$_dst" ]; then
    _OC_TREE_MISSING=" (entire tree absent: $_dst)"
    return 0
  fi
  _out="$(diff -rq \
            -x '.git' -x '__pycache__' -x '*.pyc' -x '*.pyo' -x '.DS_Store' \
            -x '*.bak' -x '*.bak-*' -x '.wired-*' \
            "$_src" "$_dst" 2>/dev/null || true)"
  [ -n "$_out" ] || return 0
  while IFS= read -r _line; do
    case "$_line" in
      "Only in $_src"*)   _OC_TREE_MISSING="${_OC_TREE_MISSING} ${_line#Only in }" ;;
      "Files "*" differ") _OC_TREE_DIFFERS="${_OC_TREE_DIFFERS} ${_line}" ;;
    esac
  done < <(printf '%s\n' "$_out")
  return 0
}

# _ocs_tree_in_sync <src> <dst>
#   rc 0 = every source file is present on the box with identical bytes
#   rc 1 = at least one source file is absent OR differs
_ocs_tree_in_sync() {
  _ocs_tree_compare "$1" "$2"
  [ -z "$_OC_TREE_MISSING" ] && [ -z "$_OC_TREE_DIFFERS" ]
}

# U007: u007_missing_departments_warning <workspace-dir>
#   Emit an explicit warning when <workspace>/departments is ABSENT but
#   <workspace>/.workforce-build-state.json has interviewComplete=true. The
#   role-staleness drain checks role docs against the departments/ tree; with no
#   departments/ it silently skips, so a completed-interview box that lost its
#   departments/ directory (usually an accidental deletion) would be invisible.
#   This makes the anomaly loud. Advisory only — never fails, never returns
#   non-zero, never withholds the stamp. When departments/ IS present (or the
#   interview is not complete, or there is no state file) this is a silent no-op,
#   so the staleness result and exit code are unchanged (AC#3).
u007_missing_departments_warning() {
  local _ws="${1:-$HOME/.openclaw/workspace}"
  local _depts="$_ws/departments"
  local _state="$_ws/.workforce-build-state.json"
  local _iv_done
  [ -d "$_depts" ] && return 0          # departments present -> nothing to warn about
  [ -f "$_state" ] || return 0          # no build state -> interview never ran here
  _iv_done="$(jq -r '.interviewComplete // false' "$_state" 2>/dev/null || echo false)"
  [ "$_iv_done" = "true" ] || return 0  # interview not complete -> absence is expected
  echo ""
  echo "  ! WARNING (U007): departments/ directory is MISSING at $_depts"
  echo "    but .workforce-build-state.json has interviewComplete=true. Role"
  echo "    staleness could NOT be checked (no departments to check against) — the"
  echo "    drain above skipped silently. This usually means departments/ was"
  echo "    accidentally deleted on a box whose interview is already complete."
  echo "    Restore the departments/ tree (re-run onboarding/wiring) so role"
  echo "    staleness can be verified. Advisory only — does not withhold the stamp."
}

# U008: u008_preflight_spend_check
#   Pre-flight budget guard run BEFORE the paid-API steps (persona embedding,
#   QC gates, floor-fill). The updater previously never checked whether the
#   operator's org had enough spend budget left, so a fleet-wide roll could
#   burn through a depleted budget mid-run with no warning.
#
#   Configuration (env vars):
#     OPENCLAW_ORG_SPEND_LIMIT      the minimum budget (USD) the org should have
#                                   before running paid steps. Default 100.
#     OPENCLAW_ORG_SPEND_REMAINING  the org's current remaining budget (USD), if
#                                   known. When unset/empty the check is a no-op
#                                   (a box with no budget tracking is not falsely
#                                   flagged — the updater cannot query the org's
#                                   balance itself).
#     OPENCLAW_SPEND_GATE           "1" to GATE (return 1 so the caller can abort
#                                   the paid steps) when below the limit; any
#                                   other value (default) only WARNS and returns 0
#                                   so a low budget never bricks an update.
#
#   Return: 0 = proceed (budget ok, unknown, or warn-only); 1 = below limit AND
#   OPENCLAW_SPEND_GATE=1 (caller should skip the paid steps). Never crashes.
u008_preflight_spend_check() {
  local _limit="${OPENCLAW_ORG_SPEND_LIMIT:-100}"
  local _remaining="${OPENCLAW_ORG_SPEND_REMAINING:-}"
  local _gate="${OPENCLAW_SPEND_GATE:-0}"

  # No budget figure to check against -> nothing to guard (not a failure).
  [ -n "$_remaining" ] || return 0

  # Both values must be numeric (optionally fractional) to compare. A
  # non-numeric value is treated as "unknown" -> no-op, never a crash and never a
  # false warning (awk would coerce "abc" to 0 and falsely fire).
  case "$_remaining" in *[!0-9.]*|"") return 0 ;; esac
  case "$_limit" in *[!0-9.]*|"") return 0 ;; esac

  # Compare remaining < limit numerically (bc for fractional USD; fall back to
  # awk if bc is absent).
  local _below=""
  if command -v bc >/dev/null 2>&1; then
    _below="$(printf '%s < %s\n' "$_remaining" "$_limit" 2>/dev/null | bc 2>/dev/null || echo "")"
  fi
  if [ -z "$_below" ]; then
    _below="$(awk -v r="$_remaining" -v l="$_limit" 'BEGIN{print (r<l)?1:0}' 2>/dev/null || echo "")"
  fi
  [ "$_below" = "1" ] || return 0   # budget is at/above the limit -> proceed silently

  echo ""
  echo "  ⚠️  PRE-FLIGHT SPEND CHECK (U008): remaining org budget \$${_remaining} is BELOW"
  echo "    the configured threshold \$${_limit} (OPENCLAW_ORG_SPEND_LIMIT). Paid steps"
  echo "    (persona embedding, QC gates, floor-fill) may trigger API spend."
  if [ "$_gate" = "1" ]; then
    echo "    OPENCLAW_SPEND_GATE=1 — GATING: paid-API steps will be SKIPPED this run."
    echo "    Raise OPENCLAW_ORG_SPEND_LIMIT or top up the budget, then re-run."
    return 1
  fi
  echo "    Advisory only (set OPENCLAW_SPEND_GATE=1 to gate). Proceeding — especially"
  echo "    review before any fleet-wide roll."
  return 0
}

# U004: u004_assert_doctrine_provenance
#   Run assert-dept-doctrine-provenance.py (warn-mode) against the materialized
#   Presentations department. Reports four disjoint buckets (identical, fork,
#   orphan, broken-symlink) into the log file.  Guarded on the department
#   existing; non-fatal; resolves the workspace through the same helper the
#   surrounding blocks use (oc_resolve_workspace_announced, fallback
#   $HOME/.openclaw/workspace).  Never prints file contents.  Never dumps an
#   environment.  Exits 0 always (warn-mode -- Rule 3.5).
u004_assert_doctrine_provenance() {
  if ! oc_resolve_workspace_announced "U004 doctrine-provenance assertion" 2>/dev/null; then
    echo "  [U004] doctrine-provenance assertion SKIPPED (workspace not resolvable)" >&2
    return 0
  fi
  local _dept_dir="$OC_WS_RESOLVED/departments/Presentations"
  if [ ! -d "$_dept_dir" ]; then
    echo "  [U004] doctrine-provenance assertion SKIPPED (department not materialized at $_dept_dir)" >&2
    return 0
  fi
  local _assert="$SKILLS_DIR/23-ai-workforce-blueprint/scripts/assert-dept-doctrine-provenance.py"
  if [ ! -f "$_assert" ]; then
    echo "  [U004] assert-dept-doctrine-provenance.py not found at $_assert - skipping (older onboarding bundle?)" >&2
    return 0
  fi
  # SIBLING-AUDIT FIX (found while investigating the U6c set -e abort above):
  # this block is documented "warn-mode" -- meant to log and never abort -- but
  # the bare `python3 "$_assert" ... 2>&1` below is a plain mid-sequence
  # statement, not the tested condition of an if/&&/||. Under `set -euo
  # pipefail` (active at L128; this function is called UNGUARDED at L5753 --
  # `u004_assert_doctrine_provenance` with no `if`/`||` around it) a non-zero
  # exit from assert-dept-doctrine-provenance.py (it can and does `sys.exit(3)`
  # on a real provenance problem) would abort the ENTIRE updater right here,
  # never reaching the "assertion completed" line, "warn-mode" or not -- the
  # exact set -e disease class as the U6c bug just above, just without a
  # command-substitution assignment. `|| true` on the tested command keeps this
  # step genuinely non-fatal, matching what "warn-mode" already claimed.
  local _u004_assert_rc=0
  {
    echo "  [U004] doctrine-provenance assertion (warn-mode) - dept at $_dept_dir"
    _u004_assert_rc=0
    python3 "$_assert" --dept-dir "$_dept_dir" --source-root "$SKILLS_DIR" 2>&1 || _u004_assert_rc=$?
    echo "  [U004] assertion completed (exit $_u004_assert_rc)"
  } >> "${LOG_FILE:-/dev/null}" 2>&1
  echo "  [U004] doctrine-provenance assertion logged (warn-mode)"
}

  # ── CC CURRENCY PROBE ────────────────────────────────────────────────────
  # WHY THIS EXISTS. The CONTENT RECHECK below `exit 0`s whenever the skills
  # stamp AND skills content are current -- roughly 3,100 lines BEFORE the
  # Command Center refresh (`run-full-install.sh --update-only`). But CC
  # currency is INDEPENDENT of skills-content currency, so every box with
  # current skills silently never converged its Command Center checkout.
  # Observed in the field: a client box sat 97 commits behind origin/main on
  # Command Center while every post-roll check reported green -- because
  # verification reads the .onboarding-version stamp, and that stamp was
  # legitimately current. A stamp is not a CC signal.
  #
  # Deliberately SELF-CONTAINED: cc_is_valid_checkout() and U6d's candidate
  # list are both defined LATER in this file and are not callable from here.
  # The list below is the union of the vps and mac candidates so the probe
  # does not depend on OPENCLAW_PLATFORM being set this early.
  #
  # CONTRACT: returns 1 ONLY when a full pass would actually repair something
  # -- i.e. the checkout is CLEAN but behind origin. Returns 0 for absent,
  # dirty, unknown, or already-current, because a full sync cannot fix those
  # and forcing one would burn a rebuild for no repair. NEVER mutates the
  # checkout: no stash, no reset, no checkout, no clean. Emits a greppable
  # `[CC CURRENCY] state=...` line and writes a marker file so post-roll
  # verification can check CC currency directly instead of trusting the stamp.
  _cc_write_marker() {
    local _f="$1" _mstate="$2" _mdir="$3" _mhead="$4" _mbranch="$5" _ts
    _ts="$(date -u '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || echo unknown)"
    mkdir -p "$(dirname "$_f")" 2>/dev/null || return 0
    {
      printf 'state=%s\n'       "$_mstate"
      printf 'dir=%s\n'         "$_mdir"
      printf 'head=%s\n'        "$_mhead"
      printf 'branch=%s\n'      "$_mbranch"
      printf 'checked_utc=%s\n' "$_ts"
    } > "$_f" 2>/dev/null || true
    return 0
  }

  _cc_currency_probe() {
    local _p _d="" _remote="" _dirty="" _def="" _head="" _marker _fetch_rc
    # Bug A: this used to hardcode ${HOME}/.openclaw/skills, which does not
    # exist on VPS/Contabo (active skills dir is /data/.openclaw/skills there
    # -- see discover_skills_dir()). Verification reads the SKILLS_DIR-resolved
    # path, so the marker was written to a location nothing ever checks on
    # those boxes -- reported MISSING on all of them. SKILLS_DIR is exported
    # by main() before this function can be reached.
    _marker="${SKILLS_DIR}/.command-center-state"

    for _p in "${CC_APP_DIR:-}" "${BLACKCEO_COMMAND_CENTER_ROOT:-}" \
              "$HOME/projects/command-center" "/data/projects/command-center" \
              "$HOME/projects/blackceo-command-center" \
              "/data/projects/blackceo-command-center" \
              "$HOME/projects/mission-control" "$HOME/blackceo-command-center" \
              "/opt/mission-control" "/app"; do
      [ -n "$_p" ] || continue
      if [ -d "$_p/.git" ]; then _d="$_p"; break; fi
    done

    if [ -z "$_d" ]; then
      echo "  — [CC CURRENCY] state=absent — no Command Center checkout on this box (informational, not a failure)."
      _cc_write_marker "$_marker" "absent" "" "" ""
      return 0
    fi

    if _remote="$(git -C "$_d" remote get-url origin 2>/dev/null)"; then :; else _remote=""; fi
    case "$_remote" in
      *command-center*) : ;;
      *)
        echo "  — [CC CURRENCY] state=absent — $_d is not a Command Center checkout (remote mismatch) — SKIP."
        _cc_write_marker "$_marker" "absent" "$_d" "" ""
        return 0
        ;;
    esac

    if _head="$(git -C "$_d" rev-parse --short HEAD 2>/dev/null)"; then :; else _head=""; fi
    if _dirty="$(git -C "$_d" status --porcelain 2>/dev/null)"; then :; else _dirty=""; fi

    if [ -n "$_dirty" ]; then
      echo "  ✗ [CC CURRENCY] state=dirty head=${_head:-unknown} dir=$_d"
      echo "    Command Center has UNCOMMITTED changes, so it cannot fast-forward and will NOT be refreshed."
      echo "    Nothing is stashed, reset, or discarded here — uncommitted work on a client box is load-bearing."
      printf '%s\n' "$_dirty" | head -n 10 | sed 's/^/      /'
      _cc_write_marker "$_marker" "dirty" "$_d" "$_head" ""
      return 0
    fi

    # Bug C: `git fetch ... || true` swallowed a fetch failure (offline box,
    # DNS hiccup, transient GitHub outage) and fell straight through to the
    # ancestor check below against the last-known-good, possibly-stale local
    # origin/<default> ref -- which can report state=current for a box that is
    # genuinely behind. Capture the real exit code (safe idiom under
    # set -euo pipefail: `if ! cmd; then rc=$?; fi`, never `cmd; rc=$?`) and
    # bail to state=unknown -- same as an unresolvable ref below -- which
    # already returns 0 and does not force a pass.
    _fetch_rc=0
    if ! git -C "$_d" fetch --quiet origin 2>/dev/null; then
      _fetch_rc=$?
    fi
    if [ "$_fetch_rc" -ne 0 ]; then
      echo "  — [CC CURRENCY] state=unknown head=${_head:-unknown} — git fetch failed (rc=$_fetch_rc, offline?) — not forcing a pass."
      _cc_write_marker "$_marker" "unknown" "$_d" "$_head" ""
      return 0
    fi

    if _def="$(git -C "$_d" symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null)"; then
      _def="${_def#origin/}"
    else
      _def=""
    fi
    [ -n "$_def" ] || _def="main"

    if git -C "$_d" rev-parse --verify --quiet "origin/$_def" >/dev/null 2>&1; then
      if git -C "$_d" merge-base --is-ancestor "origin/$_def" HEAD 2>/dev/null; then
        echo "  ✓ [CC CURRENCY] state=current head=${_head:-unknown} branch=$_def"
        _cc_write_marker "$_marker" "current" "$_d" "$_head" "$_def"
        return 0
      fi
      echo "  ✗ [CC CURRENCY] state=behind head=${_head:-unknown} branch=$_def — Command Center is NOT current with origin/$_def."
      _cc_write_marker "$_marker" "behind" "$_d" "$_head" "$_def"
      return 1
    fi

    echo "  — [CC CURRENCY] state=unknown head=${_head:-unknown} — could not resolve origin/$_def (offline?) — not forcing a pass."
    _cc_write_marker "$_marker" "unknown" "$_d" "$_head" "$_def"
    return 0
  }

  # >>> CONTENT-RECHECK-CONVERGENCE-PROBES-BEGIN (extracted verbatim by
  #     tests/unit/content-recheck-convergence-probes.test.sh)
  # ── FLEET-ROLL COVERAGE AUDIT GAP #8: RUNTIME/DB CONVERGENCE PROBES ──────
  # WHY THIS EXISTS. _cc_currency_probe above (audit gap fix, v21.4.38) closed
  # ONE of several convergence steps that live BELOW the CONTENT RECHECK
  # `exit 0` and are therefore never reached on a content-current re-roll:
  # U6b (persona-index provisioning), U6c/U6c2 (SOP library + SOP-embeddings
  # row-count ingest), weekly-onboarding-update cron registration, and
  # apply-fleet-standards.sh's AGENTS.md dedup / orphan-END repair. A box
  # whose skills content and version stamp are both current can sit forever
  # behind on ALL FOUR of these -- exactly the same "stamp is not a signal
  # for this" defect _cc_currency_probe fixed for Command Center, just not
  # yet extended to the rest of the list. These four probes extend that same
  # proven pattern to every remaining convergence step named in that audit.
  #
  # Each probe below mirrors _cc_currency_probe's contract EXACTLY (see its
  # header comment above): read-only, returns 1 ONLY when a full pass would
  # ACTUALLY repair something on THIS box, 0 for absent / unknown / already-
  # current / any read error. None of them ever writes, deletes, or invokes
  # a mutating CLI subcommand (no `cron create/edit/delete`, no SQL INSERT/
  # UPDATE/DELETE, no file write) -- every read is a plain query, a read-only
  # sqlite `?mode=ro` connection, a `cat`, or a `cron list`.
  #
  # SELF-CONTAINED BY DESIGN, same reason _cc_currency_probe gives for not
  # calling cc_is_valid_checkout()/U6d's candidate list: the real U6b/U6c/
  # U6c2 logic and shared-utils/cron-lib.sh's oc_cron_present/oc_cron_tombstoned
  # are inline code or functions that either do not exist as callable units or
  # live thousands of lines BELOW this point (and, for cron-lib.sh, carry a
  # DIFFERENT error-handling contract than a probe is allowed -- see the cron
  # probe's own header). Each probe below instead calls the SAME underlying
  # resolvers those steps call (resolve_db.find_dashboard_db(), the identical
  # manifest JSON reads) rather than reimplementing DB/manifest discovery, so
  # a probe and the real step it stands in for can never disagree about which
  # DB or manifest is the one that matters.

  # ── SOP LIBRARY / SOP-EMBEDDINGS CURRENCY PROBE ─────────────────────────
  # WHY THIS EXISTS. U6c (SOP V2 library ingest -- `sops` row count vs
  # SOP-LIBRARY-MANIFEST.json's canonical_sop_count) and U6c2 (SOP-embeddings
  # -- `sop_embeddings` row count vs SOP-EMBEDDINGS-MANIFEST.json's sop_count)
  # both live ~600 lines BELOW this exit and are gated on non-overlapping
  # under-population signals of their own. A content-current box can sit
  # under-populated on either forever. This probe reads both SAME signals via
  # the SAME DB resolution U6c/U6c2 use -- resolve_db.find_dashboard_db(),
  # called directly, not reimplemented -- so it can never disagree with them
  # about which mission-control.db is the one that matters.
  #
  # CONTRACT: returns 1 ONLY when a mission-control.db resolves AND is
  # genuinely under either canonical count. No DB on this box, no manifest,
  # missing python3/sqlite3, or any read error -> 0 (advisory, never forces a
  # pass). READ-ONLY: every query opens the DB `?mode=ro` -- this probe can
  # never write to mission-control.db.
  _sop_library_currency_probe() {
    if ! command -v python3 >/dev/null 2>&1 || ! command -v sqlite3 >/dev/null 2>&1; then
      echo "  — [SOP LIBRARY] state=unknown — python3 or sqlite3 missing — not forcing a pass."
      return 0
    fi

    local _slp_db=""
    _slp_db="$(python3 -c '
import sys
from pathlib import Path
su = Path(sys.argv[1])
sys.path.insert(0, str(su))
try:
    from resolve_db import find_dashboard_db, is_db_found
    p = find_dashboard_db()
    print(str(p) if is_db_found(p) else "")
except Exception:
    print("")' "$SKILLS_DIR/shared-utils" 2>/dev/null || true)"

    if [ -z "$_slp_db" ] || [ ! -f "$_slp_db" ]; then
      echo "  — [SOP LIBRARY] state=absent — no mission-control.db resolved on this box — not forcing a pass."
      return 0
    fi

    local _slp_lib_manifest="$SKILLS_DIR/shared-utils/sop-library/SOP-LIBRARY-MANIFEST.json"
    [ -f "$_slp_lib_manifest" ] || _slp_lib_manifest="$EXTRACTED_DIR/shared-utils/sop-library/SOP-LIBRARY-MANIFEST.json"
    local _slp_canon=2555
    if [ -f "$_slp_lib_manifest" ]; then
      _slp_canon="$(python3 -c 'import json,sys
try:
    print(int(json.load(open(sys.argv[1])).get("canonical_sop_count") or 2555))
except Exception:
    print(2555)' "$_slp_lib_manifest" 2>/dev/null || echo 2555)"
    fi

    local _slp_rows=0
    _slp_rows="$(sqlite3 "file:${_slp_db}?mode=ro" "SELECT COUNT(*) FROM sops;" 2>/dev/null || echo 0)"
    if [ "${_slp_rows:-0}" -lt "${_slp_canon:-2555}" ] 2>/dev/null; then
      echo "  ✗ [SOP LIBRARY] state=under-populated rows=$_slp_rows canonical=$_slp_canon db=$_slp_db"
      return 1
    fi

    local _slp_emb_manifest="$SKILLS_DIR/shared-utils/sop-embed-once/SOP-EMBEDDINGS-MANIFEST.json"
    [ -f "$_slp_emb_manifest" ] || _slp_emb_manifest="$EXTRACTED_DIR/shared-utils/sop-embed-once/SOP-EMBEDDINGS-MANIFEST.json"
    if [ -f "$_slp_emb_manifest" ]; then
      local _slp_emb_count=0
      _slp_emb_count="$(python3 -c 'import json,sys
try:
    print(int(json.load(open(sys.argv[1])).get("sop_count") or 0))
except Exception:
    print(0)' "$_slp_emb_manifest" 2>/dev/null || echo 0)"
      if [ "${_slp_emb_count:-0}" -gt 0 ] 2>/dev/null; then
        local _slp_emb_table=0 _slp_emb_rows=0
        _slp_emb_table="$(sqlite3 "file:${_slp_db}?mode=ro" "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='sop_embeddings';" 2>/dev/null || echo 0)"
        if [ "${_slp_emb_table:-0}" = "1" ]; then
          _slp_emb_rows="$(sqlite3 "file:${_slp_db}?mode=ro" "SELECT COUNT(*) FROM sop_embeddings;" 2>/dev/null || echo 0)"
        fi
        if [ "${_slp_emb_rows:-0}" -lt "${_slp_emb_count:-0}" ] 2>/dev/null; then
          echo "  ✗ [SOP LIBRARY] state=embeddings-under-populated rows=$_slp_emb_rows manifest_count=$_slp_emb_count db=$_slp_db"
          return 1
        fi
      fi
    fi

    echo "  ✓ [SOP LIBRARY] state=current sops=${_slp_rows}/${_slp_canon} db=$_slp_db"
    return 0
  }

  # ── PERSONA-INDEX CURRENCY PROBE ────────────────────────────────────────
  # WHY THIS EXISTS. U6b's own D3 completion re-assertion (which this probe
  # mirrors) compares the on-disk `.prebuilt-index-version` sentinel against
  # the PULLED manifest's release_tag; a mismatch (or a missing sentinel --
  # never provisioned) means U6b has real work to do. U6b lives ~500 lines
  # BELOW this exit, so that comparison cannot be CALLED from here -- it runs
  # inline, after sourcing provision-persona-index.sh, both far below this
  # point. This probe re-reads the SAME two files with the SAME comparison.
  #
  # CONTRACT: returns 1 ONLY when the manifest resolves (so a real release_tag
  # exists to compare against) AND the sentinel is missing or stale. Manifest
  # unreadable/absent, or python3 missing -> 0 (advisory). READ-ONLY: reads
  # two files, writes nothing.
  _persona_index_currency_probe() {
    if ! command -v python3 >/dev/null 2>&1; then
      echo "  — [PERSONA INDEX] state=unknown — python3 missing — not forcing a pass."
      return 0
    fi

    local _pip_manifest="$SKILLS_DIR/shared-utils/prebuilt-index/INDEX-MANIFEST.json"
    [ -f "$_pip_manifest" ] || _pip_manifest="$EXTRACTED_DIR/shared-utils/prebuilt-index/INDEX-MANIFEST.json"
    if [ ! -f "$_pip_manifest" ]; then
      echo "  — [PERSONA INDEX] state=absent — no INDEX-MANIFEST.json resolved — not forcing a pass."
      return 0
    fi

    local _pip_release_tag=""
    _pip_release_tag="$(python3 -c 'import json,sys
try:
    print(json.load(open(sys.argv[1])).get("release_tag",""))
except Exception:
    print("")' "$_pip_manifest" 2>/dev/null || true)"
    if [ -z "$_pip_release_tag" ]; then
      echo "  — [PERSONA INDEX] state=unknown — manifest has no release_tag — not forcing a pass."
      return 0
    fi

    local _pip_db_dir="$HOME/.openclaw/workspace/data/coaching-personas"
    [ -d "/data/.openclaw" ] && _pip_db_dir="/data/.openclaw/workspace/data/coaching-personas"
    local _pip_sentinel=""
    _pip_sentinel="$(cat "$_pip_db_dir/.prebuilt-index-version" 2>/dev/null | tr -d '[:space:]' || true)"

    if [ "$_pip_sentinel" = "$_pip_release_tag" ]; then
      echo "  ✓ [PERSONA INDEX] state=current sentinel==release_tag ($_pip_release_tag)"
      return 0
    fi

    echo "  ✗ [PERSONA INDEX] state=stale sentinel=${_pip_sentinel:-<missing>} release_tag=$_pip_release_tag"
    return 1
  }

  # ── WEEKLY-CRON REGISTRATION PROBE ──────────────────────────────────────
  # WHY THIS EXISTS. weekly-onboarding-update registration lives ~2,400 lines
  # BELOW this exit and is SKIPPED ENTIRELY on a content-current box -- a box
  # that never got the cron (pre-v9.2.0, or one where it was removed
  # out-of-band without a tombstone) never gets it from a same-version
  # re-roll.
  #
  # SELF-CONTAINED BY DESIGN -- NOT a call into shared-utils/cron-lib.sh's
  # oc_cron_present/oc_cron_tombstoned:
  #   * oc_cron_present deliberately FAILS OPEN (treats an unreadable
  #     `cron list --json` as "absent") because ITS caller's asymmetry favors
  #     attempting a redundant, idempotent registration over silently never
  #     registering. THIS probe's asymmetry is the opposite: forcing a full
  #     pass on a transient CLI hiccup means a full pass on every one of 38
  #     boxes on a bad network day. So a genuine parse failure here is
  #     advisory (return 0), never "treat as absent".
  #   * the tombstone check below is a pure file-existence READ. It
  #     deliberately does NOT source cron-lib.sh's oc_cron_tombstone_dir(),
  #     which mkdir -p's its marker directory as a side effect -- a probe
  #     must never write anything, even a directory. It mirrors that
  #     function's OWN path formula (the job name has no characters
  #     oc_cron_tombstone_path's sanitizer would change) as a plain
  #     `[ -f ... ]` instead.
  #
  # CONTRACT: returns 1 ONLY when `openclaw cron list --json` returns a
  # PARSEABLE answer AND that answer definitively shows the job absent AND it
  # is not tombstoned. openclaw missing, the call failing, or unparseable
  # output -> 0 (advisory, never forces a pass on a CLI/gateway hiccup).
  # READ-ONLY: only ever runs `cron list`, never `cron create`/`edit`/`delete`.
  _weekly_cron_currency_probe() {
    if ! command -v openclaw >/dev/null 2>&1; then
      echo "  — [WEEKLY CRON] state=unknown — openclaw CLI not found — not forcing a pass."
      return 0
    fi

    local _wcp_root="$HOME/.openclaw"
    [ -d "/data/.openclaw" ] && _wcp_root="/data/.openclaw"
    local _wcp_tomb="$_wcp_root/workspace/.cron-tombstones/weekly-onboarding-update"
    if [ -f "$_wcp_tomb" ]; then
      echo "  ✓ [WEEKLY CRON] state=tombstoned — deliberately removed; not treated as outstanding work."
      return 0
    fi

    local _wcp_raw="" _wcp_rc=0
    if ! _wcp_raw="$(openclaw cron list --json 2>/dev/null)"; then
      _wcp_rc=$?
    fi
    if [ -z "$_wcp_raw" ]; then
      echo "  — [WEEKLY CRON] state=unknown — 'openclaw cron list --json' returned nothing (rc=$_wcp_rc) — not forcing a pass."
      return 0
    fi

    local _wcp_present=""
    if command -v jq >/dev/null 2>&1; then
      local _wcp_jq_rc=0
      if printf '%s' "$_wcp_raw" | jq -e '
          ( if type=="array" then . else .jobs // [] end)
          | map(select(.name=="weekly-onboarding-update"))
          | length > 0
        ' >/dev/null 2>&1; then
        _wcp_jq_rc=0
      else
        _wcp_jq_rc=$?
      fi
      case "$_wcp_jq_rc" in
        0) _wcp_present=1 ;;
        1) _wcp_present=0 ;;
        *) echo "  — [WEEKLY CRON] state=unknown — jq could not parse cron list JSON (rc=$_wcp_jq_rc) — not forcing a pass."; return 0 ;;
      esac
    elif command -v python3 >/dev/null 2>&1; then
      local _wcp_py_rc=0
      if OC_CRON_RAW="$_wcp_raw" python3 -c '
import json, os, sys
try:
    data = json.loads(os.environ.get("OC_CRON_RAW", ""))
except Exception:
    sys.exit(2)
jobs = data if isinstance(data, list) else data.get("jobs", [])
sys.exit(0 if any(j.get("name") == "weekly-onboarding-update" for j in jobs) else 1)
' 2>/dev/null; then
        _wcp_py_rc=0
      else
        _wcp_py_rc=$?
      fi
      case "$_wcp_py_rc" in
        0) _wcp_present=1 ;;
        1) _wcp_present=0 ;;
        *) echo "  — [WEEKLY CRON] state=unknown — could not parse cron list JSON (rc=$_wcp_py_rc) — not forcing a pass."; return 0 ;;
      esac
    else
      echo "  — [WEEKLY CRON] state=unknown — jq and python3 both unavailable — not forcing a pass."
      return 0
    fi

    if [ "$_wcp_present" = "1" ]; then
      echo "  ✓ [WEEKLY CRON] state=registered"
      return 0
    fi
    echo "  ✗ [WEEKLY CRON] state=absent — weekly-onboarding-update is NOT registered and NOT tombstoned."
    return 1
  }

  # ── AGENTS.md HYGIENE PROBE ─────────────────────────────────────────────
  # WHY THIS EXISTS. apply-fleet-standards.sh's AGENTS.md dedup (5a-DEDUP,
  # scripts/dedup-agents-md.py) and update-skills.sh's own orphan-END
  # self-heal (CORE_UPDATES merge, ~1,700 lines BELOW this exit) both only
  # run as part of a full pass. A box already carrying duplicate marker-
  # guarded blocks or an orphan BEGIN/END pair (measured on the fleet: 3 of 4
  # sampled boxes carried the same orphan) keeps carrying them forever once
  # content is current.
  #
  # SIGNAL CHOSEN (deliberately CHEAP, not a dedup dry-run). Even
  # dedup-agents-md.py's own default dry-run mode means fully parsing the
  # file into heading-delimited blocks on every one of 38 boxes, every roll.
  # Just as reliable for what a full pass would actually DO differently here:
  #   (a) any single-token `<!-- MARKER -->` stamp line repeated more than
  #       once -- these are exactly the tokens apply-fleet-standards.sh's own
  #       idempotency guards stamp ONCE each (e.g. <!-- ROLE_DISCIPLINE_V1 -->),
  #       so a second copy of the SAME token is the exact re-append defect
  #       dedup exists to clean up. Near-zero false-positive rate, unlike a
  #       bare heading-count: two different blocks can legitimately share a
  #       heading like "## Notes"; they cannot legitimately share the same
  #       singleton marker token.
  #   (b) any `<!-- BEGIN skill:X:Y -->` / `<!-- END skill:X:Y -->` pair that
  #       is not 1:1 -- the orphan the CORE_UPDATES merge self-heals.
  # Both are a single regex pass over one file already capped at ~400,000
  # chars by the size guard elsewhere in this pipeline -- negligible cost.
  #
  # CONTRACT: returns 1 ONLY when the workspace resolves, AGENTS.md exists,
  # AND at least one of the two signals above is found. Unresolvable
  # workspace, missing file, or any read/parse error -> 0 (advisory).
  # READ-ONLY: opens AGENTS.md for reading only.
  _agents_md_hygiene_probe() {
    if ! command -v python3 >/dev/null 2>&1; then
      echo "  — [AGENTS.MD HYGIENE] state=unknown — python3 missing — not forcing a pass."
      return 0
    fi
    if ! oc_resolve_workspace_announced "AGENTS.md hygiene probe" 2>/dev/null; then
      echo "  — [AGENTS.MD HYGIENE] state=unknown — workspace not resolvable — not forcing a pass."
      return 0
    fi
    local _amh_file="$OC_WS_RESOLVED/AGENTS.md"
    if [ ! -f "$_amh_file" ]; then
      echo "  — [AGENTS.MD HYGIENE] state=absent — no AGENTS.md at $_amh_file — not forcing a pass."
      return 0
    fi

    local _amh_report="" _amh_rc=0
    if _amh_report="$(python3 -c '
import re, sys
path = sys.argv[1]
try:
    text = open(path, encoding="utf-8", errors="replace").read()
except Exception:
    print("error")
    sys.exit(0)
marker_re = re.compile(r"^<!--\s*(\S+)\s*-->\s*$")
begin_re  = re.compile(r"^<!--\s*BEGIN\s+skill:(.+?):(.+?)\s*-->\s*$")
end_re    = re.compile(r"^<!--\s*END\s+skill:(.+?):(.+?)\s*-->\s*$")
markers = {}
begins = {}
ends = {}
for ln in text.splitlines():
    m = marker_re.match(ln)
    if m:
        markers[m.group(1)] = markers.get(m.group(1), 0) + 1
        continue
    m = begin_re.match(ln)
    if m:
        k = (m.group(1), m.group(2))
        begins[k] = begins.get(k, 0) + 1
        continue
    m = end_re.match(ln)
    if m:
        k = (m.group(1), m.group(2))
        ends[k] = ends.get(k, 0) + 1
dup_markers = sum(1 for v in markers.values() if v > 1)
orphan_pairs = sum(1 for k in set(begins) | set(ends) if begins.get(k, 0) != ends.get(k, 0))
print(f"{dup_markers} {orphan_pairs}")
' "$_amh_file" 2>/dev/null)"; then
      :
    else
      _amh_rc=$?
    fi

    if [ "$_amh_rc" -ne 0 ] || [ -z "$_amh_report" ] || [ "$_amh_report" = "error" ]; then
      echo "  — [AGENTS.MD HYGIENE] state=unknown — could not parse $_amh_file — not forcing a pass."
      return 0
    fi

    local _amh_dup _amh_orphan
    _amh_dup="$(printf '%s' "$_amh_report" | awk '{print $1}')"
    _amh_orphan="$(printf '%s' "$_amh_report" | awk '{print $2}')"

    if [ "${_amh_dup:-0}" -gt 0 ] 2>/dev/null || [ "${_amh_orphan:-0}" -gt 0 ] 2>/dev/null; then
      echo "  ✗ [AGENTS.MD HYGIENE] state=dirty duplicate-marker-tokens=${_amh_dup:-0} orphan-BEGIN/END-pairs=${_amh_orphan:-0} file=$_amh_file"
      return 1
    fi
    echo "  ✓ [AGENTS.MD HYGIENE] state=clean file=$_amh_file"
    return 0
  }

  # ── UPDATE PENDING FLAG CURRENCY PROBE ──────────────────────────────────
  # WHY THIS EXISTS. write_update_pending_flag() / clear_update_pending_flag()
  # (defined far above, the shared PENDING-lifecycle pair) are dispatched from
  # the Post-update "UPDATE PENDING flag LIFECYCLE" step near the end of this
  # function, gated on _RESUME_NEEDED -- which was computed SOLELY from
  # ONBOARDING_GATE_OK (the per-skill qc gate) and NEW_SKILLS_CSV (brand-new
  # skill FOLDERS). Neither signal knows whether a "## UPDATE PENDING --
  # Skill Update to vX" section from a PRIOR run is still sitting in
  # AGENTS.md: an EXISTING skill can receive a genuine CONTENT update (a
  # script rewrite inside its own folder, not a new folder) while its qc
  # sentinel stays stamped from the PREVIOUS pass, so the gate reads "yes",
  # NEW_SKILLS_CSV stays empty, and clear_update_pending_flag() runs instead
  # of write_update_pending_flag() -- sweeping the stale block (if it even
  # matches) without ever re-announcing the work or arming the resume cron
  # that would drive an agent to re-process it. A live 3-box pilot reproduced
  # this on 3 of 3 boxes: exit 0, stamp advanced, skills genuinely updated on
  # disk, and AGENTS.md/MEMORY.md came out byte-identical -- the pointer/
  # self-heal pass the fresh flag exists to trigger never ran.
  #
  # THE FIX: a PENDING block's mere PRESENCE proves nothing about whether it
  # was handled -- only its VERSION does. This reads every "## ... UPDATE
  # PENDING ..." / "## ... ONBOARDING PENDING ..." header line currently in
  # AGENTS.md and extracts the version each one names ("Skill Update to
  # ${version}"). If ANY of them names a version other than the CURRENT
  # ONBOARDING_VERSION -- or a version this cannot parse at all (covers the
  # older "ONBOARDING PENDING" / "UPDATE PENDING - EXECUTE IMMEDIATELY"
  # wordings predating this lifecycle, per Start Here.md) -- the block is
  # STALE: outstanding work exists that the standard qc gate cannot see,
  # because that gate tracks per-skill activation state, not "did THIS
  # specific flag's work happen". Multiple stacked stale copies (measured on
  # a real box: three) all count as ONE outstanding finding here;
  # _strip_update_pending_sections (the shared remover both
  # write_update_pending_flag and clear_update_pending_flag already call, and
  # the ONLY mechanism that ever mutates the file) sweeps every one of them in
  # a single pass regardless of how many this probe reports.
  #
  # CONTRACT, identical to every sibling probe above: returns 1 ONLY when a
  # full pass would ACTUALLY repair something (a stale/unparsable block is
  # present). Absent workspace, absent AGENTS.md, absent python3, or a block
  # whose EVERY header already names the current version -> 0 (advisory,
  # never forces a pass on a box that genuinely has nothing to do). READ-ONLY:
  # opens AGENTS.md for reading only; never writes and never calls
  # write_update_pending_flag/clear_update_pending_flag itself -- it only
  # REPORTS, the existing lifecycle functions still own every write.
  _pending_flag_currency_probe() {
    if ! command -v python3 >/dev/null 2>&1; then
      echo "  — [UPDATE PENDING FLAG] state=unknown — python3 missing — not forcing a pass."
      return 0
    fi
    if ! oc_resolve_workspace_announced "UPDATE PENDING flag currency probe" >/dev/null 2>&1; then
      echo "  — [UPDATE PENDING FLAG] state=unknown — workspace not resolvable — not forcing a pass."
      return 0
    fi
    local _pfc_file="$OC_WS_RESOLVED/AGENTS.md"
    if [ ! -f "$_pfc_file" ]; then
      echo "  — [UPDATE PENDING FLAG] state=absent — no AGENTS.md at $_pfc_file — not forcing a pass."
      return 0
    fi

    local _pfc_report="" _pfc_rc=0
    if _pfc_report="$(python3 -c '
import re, sys
path, current = sys.argv[1], sys.argv[2]
try:
    text = open(path, encoding="utf-8", errors="replace").read()
except Exception:
    print("error")
    sys.exit(0)
header_re = re.compile(r"(?m)^##[^\n]*(?:UPDATE PENDING|ONBOARDING PENDING)[^\n]*$")
version_re = re.compile(r"Skill Update to\s+(\S+)")
headers = header_re.findall(text)
if not headers:
    print("clean 0")
    sys.exit(0)
stale = 0
for h in headers:
    m = version_re.search(h)
    if not m or not current or m.group(1).rstrip(".,:;)") != current:
        stale += 1
state = "stale" if stale else "current"
print(state + " " + str(len(headers)))
' "$_pfc_file" "${ONBOARDING_VERSION:-}" 2>/dev/null)"; then
      :
    else
      _pfc_rc=$?
    fi

    if [ "$_pfc_rc" -ne 0 ] || [ -z "$_pfc_report" ] || [ "$_pfc_report" = "error" ]; then
      echo "  — [UPDATE PENDING FLAG] state=unknown — could not parse $_pfc_file — not forcing a pass."
      return 0
    fi

    local _pfc_state _pfc_count
    _pfc_state="$(printf '%s' "$_pfc_report" | awk '{print $1}')"
    _pfc_count="$(printf '%s' "$_pfc_report" | awk '{print $2}')"

    if [ "$_pfc_state" = "stale" ]; then
      echo "  ✗ [UPDATE PENDING FLAG] state=stale sections=${_pfc_count} current-version=${ONBOARDING_VERSION:-<unset>} file=$_pfc_file — a PRIOR-VERSION (or unparsable) UPDATE PENDING section is still sitting in AGENTS.md; its presence is not proof the work was done."
      return 1
    fi
    echo "  ✓ [UPDATE PENDING FLAG] state=${_pfc_state} sections=${_pfc_count} file=$_pfc_file"
    return 0
  }
  # <<< CONTENT-RECHECK-CONVERGENCE-PROBES-END

  # ── CONTENT RECHECK (stamp already current, non-interactive run) ─────────
  # Reached only via the same-version branch above. Decide on CONTENT:
  #   (1) every numbered skill, via the A3 digest manifest (SRC vs the box);
  #   (2) shared-utils/ and universal-sops/, which skill-content-hash.sh does
  #       NOT enumerate (it globs '[0-9]*' only) and which have no version file.
  # Only a genuine match exits 0. Any drift falls through to the normal full
  # sync, which is unconditional (rm -rf + cp -r per skill), so it repairs
  # absent files, silently-edited files, and unbumped content alike. The cost
  # of a false "drift" verdict is one extra sync; the cost of a false "clean"
  # verdict is a broken box reporting success — so this errs toward syncing.
  if [ "${_SAME_VERSION_RECHECK:-0}" -eq 1 ]; then
    _RECHECK_DRIFT=""
    if [ -n "$SRC_MANIFEST" ] && [ -f "$_CONTENT_HASH_SCRIPT" ]; then
      _RC_DEST_MANIFEST="$(bash "$_CONTENT_HASH_SCRIPT" "$SKILLS_DIR" 2>/dev/null || true)"
      while IFS='|' read -r _rc_name _rc_src_digest; do
        [ -n "$_rc_name" ] || continue
        case "$_rc_name" in __TREE_SHA__) continue ;; esac
        _rc_dest_digest="$(printf '%s\n' "$_RC_DEST_MANIFEST" \
                           | awk -F'|' -v n="$_rc_name" '$1==n {print $2; exit}')"
        if [ "$_rc_dest_digest" != "$_rc_src_digest" ]; then
          _RECHECK_DRIFT="${_RECHECK_DRIFT} ${_rc_name}"
        fi
      done < <(printf '%s\n' "$SRC_MANIFEST")
    else
      # No manifest = no proof of health. Fail toward syncing, never toward exit 0.
      _RECHECK_DRIFT="${_RECHECK_DRIFT} (content-manifest-unavailable)"
    fi
    for _rc_tree in shared-utils universal-sops; do
      [ -d "$EXTRACTED_DIR/$_rc_tree" ] || continue
      if ! _ocs_tree_in_sync "$EXTRACTED_DIR/$_rc_tree" "$SKILLS_DIR/$_rc_tree"; then
        _RECHECK_DRIFT="${_RECHECK_DRIFT} ${_rc_tree}"
      fi
    done
    if [ -z "$_RECHECK_DRIFT" ]; then
      # Skills content is current. But CONTENT currency and RUNTIME/DB
      # convergence are SEPARATE questions that must be answered BEFORE we
      # are allowed to exit -- a clean-but-behind Command Center, an
      # under-populated SOP library/embeddings table, a stale persona-index
      # sentinel, a never-registered weekly cron, or a duplicated/orphaned
      # AGENTS.md are each a case where falling through actually repairs
      # something, because the full pass reaches every one of those steps
      # further below (see CONTENT-RECHECK-CONVERGENCE-PROBES above for why
      # each probe is self-contained and what signal it reads). Every probe
      # runs regardless of what an earlier one found, so the log always shows
      # the FULL set of outstanding items, not just the first.
      # >>> CONTENT-RECHECK-CONVERGENCE-GATE-BEGIN (extracted verbatim by
      #     tests/unit/content-recheck-convergence-probes.test.sh)
      _CONVERGENCE_TRIGGERS=""
      _cc_currency_probe || _CONVERGENCE_TRIGGERS="${_CONVERGENCE_TRIGGERS}${_CONVERGENCE_TRIGGERS:+; }Command Center currency"
      _sop_library_currency_probe || _CONVERGENCE_TRIGGERS="${_CONVERGENCE_TRIGGERS}${_CONVERGENCE_TRIGGERS:+; }SOP library/embeddings population"
      _persona_index_currency_probe || _CONVERGENCE_TRIGGERS="${_CONVERGENCE_TRIGGERS}${_CONVERGENCE_TRIGGERS:+; }persona-index sentinel"
      _weekly_cron_currency_probe || _CONVERGENCE_TRIGGERS="${_CONVERGENCE_TRIGGERS}${_CONVERGENCE_TRIGGERS:+; }weekly-onboarding-update cron registration"
      _agents_md_hygiene_probe || _CONVERGENCE_TRIGGERS="${_CONVERGENCE_TRIGGERS}${_CONVERGENCE_TRIGGERS:+; }AGENTS.md dedup/orphan hygiene"
      _pending_flag_currency_probe || _CONVERGENCE_TRIGGERS="${_CONVERGENCE_TRIGGERS}${_CONVERGENCE_TRIGGERS:+; }UPDATE PENDING flag currency"

      if [ -z "$_CONVERGENCE_TRIGGERS" ]; then
        echo "  ✓ [CONTENT RECHECK] stamp current AND installed content matches source — nothing to do."
        rm -rf "$TEMP_EXTRACT" "$TEMP_ZIP"
        exit 0
      fi
      echo "  ✗ [CONTENT RECHECK] skills content is current, but these convergence step(s) are OUTSTANDING: ${_CONVERGENCE_TRIGGERS}"
      echo "    Trying the FAST convergence-only sub-pass before committing to a full content sync..."
      # >>> CONVERGENCE-FAST-PATH-BEGIN (2026-08-10)
      # WHEN THIS RUNS: content is current (A3 digest match) but at least one
      # convergence probe fired. The old behavior fell through to the FULL
      # sync, which re-copies every numbered skill (rm -rf + cp -r per skill)
      # and re-runs the ~77s skill-content-hash.sh per skill on a ~450MB /
      # 16,789-file tree — a multi-minute hang on every already-current re-roll
      # (observed live: all 10 VPS boxes, deterministic). The convergence steps
      # the probes stand in for are SMALL, idempotent repairs; this sub-pass
      # runs exactly those, then re-probes. Only if a probe still fires after
      # the fast pass (or content genuinely drifted) do we fall through to the
      # full sync — the full pass remains the never-weaker backstop.
      # GUARDS: never deletes a healthy skill; never touches a dirty CC
      # checkout with uncommitted client work; every repair is idempotent and
      # reverts to the full pass on any uncertainty.
      _FAST_CONVERGED=1
      if [ -n "${_RECHECK_DRIFT:-}" ]; then
        # Content genuinely drifted — the full sync is required. Do not run
        # the fast path; fall straight through below.
        _FAST_CONVERGED=0
      else
        # --- CC currency (state=behind or state=dirty on a CC checkout) ----
        # Repair: fetch + fast-forward reset to origin/main — but ONLY when
        # the checkout is clean (no uncommitted client work). A dirty checkout
        # is load-bearing (the probe's own comment: "uncommitted work on a
        # client box is load-bearing") — do NOT reset it; report and let the
        # full pass (which also refuses to touch it) surface the same state.
        for _fast_p in "${CC_APP_DIR:-}" "${BLACKCEO_COMMAND_CENTER_ROOT:-}" \
                      "$HOME/projects/command-center" "/data/projects/command-center" \
                      "$HOME/projects/blackceo-command-center" \
                      "/data/projects/blackceo-command-center" \
                      "$HOME/projects/mission-control" "$HOME/blackceo-command-center" \
                      "/opt/mission-control" "/app"; do
          [ -n "$_fast_p" ] || continue
          [ -d "$_fast_p/.git" ] || continue
          _fast_remote="$(git -C "$_fast_p" remote get-url origin 2>/dev/null || true)"
          case "$_fast_remote" in *command-center*) : ;; *) continue ;; esac
          _fast_dirty="$(git -C "$_fast_p" status --porcelain 2>/dev/null || true)"
          if [ -n "$_fast_dirty" ]; then
            echo "    [fast-path] CC checkout $_fast_p has uncommitted changes (load-bearing) — NOT reset; full pass will surface the same state."
            continue
          fi
          if git -C "$_fast_p" fetch --quiet origin 2>/dev/null \
             && git -C "$_fast_p" reset --hard origin/main >/dev/null 2>&1; then
            echo "    [fast-path] CC checkout $_fast_p fast-forwarded to origin/main."
          else
            echo "    [fast-path] CC checkout $_fast_p could not be refreshed (offline? locked?) — full pass will retry."
          fi
          break
        done
        # --- SOP library under-populated (U6c) ------------------------------
        if [ -n "${_U6C_SOPLIB_FAIL:-}" ]; then : # probe reported missing ingester / no reader — full pass handles it
        else
          _fast_sop_db="$( [ -f "/data/projects/command-center/mission-control.db" ] && echo "/data/projects/command-center/mission-control.db" \
                        || ( [ -f "$HOME/projects/command-center/mission-control.db" ] && echo "$HOME/projects/command-center/mission-control.db" || echo "" ) )"
          if [ -n "$_fast_sop_db" ] && [ -f "$_fast_sop_db" ]; then
            _fast_sop_canon="${_U6C_CANON:-2555}"
            _fast_sop_rows="$([ -n "$(command -v sqlite3 2>/dev/null)" ] && sqlite3 "$_fast_sop_db" "SELECT COUNT(*) FROM sops;" 2>/dev/null || echo 0)"
            _fast_sop_rows="${_fast_sop_rows:-0}"
            if [ "${_fast_sop_rows:-0}" -lt "${_fast_sop_canon}" ] 2>/dev/null; then
              _fast_ingest="${SKILLS_DIR:-$HOME/.openclaw/skills}/shared-utils/sop-library/ingest-sop-library.sh"
              [ -f "$_fast_ingest" ] || _fast_ingest="${EXTRACTED_DIR:-}/shared-utils/sop-library/ingest-sop-library.sh"
              if [ -f "$_fast_ingest" ]; then
                echo "    [fast-path] SOP library under-populated (${_fast_sop_rows} < ${_fast_sop_canon}) — running ingest..."
                bash "$_fast_ingest" >/dev/null 2>&1 && echo "    [fast-path] SOP library ingest completed." || echo "    [fast-path] SOP library ingest failed (rc=$?) — full pass will retry."
              else
                echo "    [fast-path] ingest-sop-library.sh not found — full pass handles it."
              fi
            fi
          fi
        fi
        # --- SOP-embeddings under-populated (U6c2) --------------------------
        _fast_emb_db="$( [ -f "/data/projects/command-center/mission-control.db" ] && echo "/data/projects/command-center/mission-control.db" \
                       || ( [ -f "$HOME/projects/command-center/mission-control.db" ] && echo "$HOME/projects/command-center/mission-control.db" || echo "" ) )"
        if [ -n "$_fast_emb_db" ] && [ -f "$_fast_emb_db" ]; then
          _fast_emb_canon="${_U6C_EMB_CANON:-0}"
          if [ "${_fast_emb_canon:-0}" -gt 0 ] 2>/dev/null; then
            _fast_emb_rows="$([ -n "$(command -v sqlite3 2>/dev/null)" ] && sqlite3 "$_fast_emb_db" "SELECT COUNT(*) FROM sop_embeddings;" 2>/dev/null || echo 0)"
            _fast_emb_rows="${_fast_emb_rows:-0}"
            if [ "${_fast_emb_rows:-0}" -lt "${_fast_emb_canon}" ] 2>/dev/null; then
              _fast_emb_ingest="${SKILLS_DIR:-$HOME/.openclaw/skills}/shared-utils/sop-embed-once/embed-sops.sh"
              [ -f "$_fast_emb_ingest" ] || _fast_emb_ingest="${EXTRACTED_DIR:-}/shared-utils/sop-embed-once/embed-sops.sh"
              if [ -f "$_fast_emb_ingest" ]; then
                echo "    [fast-path] SOP-embeddings under-populated (${_fast_emb_rows} < ${_fast_emb_canon}) — running embedder..."
                bash "$_fast_emb_ingest" >/dev/null 2>&1 && echo "    [fast-path] SOP-embeddings ingest completed." || echo "    [fast-path] SOP-embeddings ingest failed (rc=$?) — full pass will retry."
              else
                echo "    [fast-path] embed-sops.sh not found — full pass handles it."
              fi
            fi
          fi
        fi
        # --- persona-index provisioner (U6b) --------------------------------
        _fast_pidx="${SKILLS_DIR:-$HOME/.openclaw/skills}/shared-utils/provision-persona-index.sh"
        [ -f "$_fast_pidx" ] || _fast_pidx="${EXTRACTED_DIR:-}/shared-utils/provision-persona-index.sh"
        if [ -f "$_fast_pidx" ]; then
          echo "    [fast-path] provisioning persona index..."
          bash "$_fast_pidx" >/dev/null 2>&1 && echo "    [fast-path] persona index provisioned." || echo "    [fast-path] persona-index provisioning failed (rc=$?) — full pass will retry."
        fi
        # --- weekly-onboarding-update cron (U6c-adjacent) -------------------
        if command -v install_onboarding_resume_cron >/dev/null 2>&1; then
          echo "    [fast-path] registering weekly onboarding-update cron..."
          install_onboarding_resume_cron >/dev/null 2>&1 && echo "    [fast-path] weekly cron registered." || echo "    [fast-path] weekly cron registration failed (rc=$?) — full pass will retry."
        fi
        # --- AGENTS.md dedup / orphan hygiene -------------------------------
        if [ -f "${EXTRACTED_DIR:-}/scripts/apply-fleet-standards.sh" ]; then
          echo "    [fast-path] running AGENTS.md hygiene..."
          bash "${EXTRACTED_DIR:-}/scripts/apply-fleet-standards.sh" >/dev/null 2>&1 && echo "    [fast-path] AGENTS.md hygiene complete." || echo "    [fast-path] AGENTS.md hygiene reported non-zero (rc=$?) — full pass will retry."
        fi
        # --- PENDING flag ----------------------------------------------------
        for _fast_pending in "${PENDING_PATHS[@]:-}"; do
          [ -n "$_fast_pending" ] || continue
          if [ -f "$_fast_pending" ]; then
            rm -f "$_fast_pending" 2>/dev/null && echo "    [fast-path] cleared UPDATE PENDING flag at $_fast_pending."
          fi
        done
      fi
      if [ "$_FAST_CONVERGED" -eq 1 ]; then
        # Re-probe once. If clean now, we are done WITHOUT the expensive sync.
        _CONVERGENCE_TRIGGERS=""
        _cc_currency_probe || _CONVERGENCE_TRIGGERS="${_CONVERGENCE_TRIGGERS}${_CONVERGENCE_TRIGGERS:+; }Command Center currency"
        _sop_library_currency_probe || _CONVERGENCE_TRIGGERS="${_CONVERGENCE_TRIGGERS}${_CONVERGENCE_TRIGGERS:+; }SOP library/embeddings population"
        _persona_index_currency_probe || _CONVERGENCE_TRIGGERS="${_CONVERGENCE_TRIGGERS}${_CONVERGENCE_TRIGGERS:+; }persona-index sentinel"
        _weekly_cron_currency_probe || _CONVERGENCE_TRIGGERS="${_CONVERGENCE_TRIGGERS}${_CONVERGENCE_TRIGGERS:+; }weekly-onboarding-update cron registration"
        _agents_md_hygiene_probe || _CONVERGENCE_TRIGGERS="${_CONVERGENCE_TRIGGERS}${_CONVERGENCE_TRIGGERS:+; }AGENTS.md dedup/orphan hygiene"
        _pending_flag_currency_probe || _CONVERGENCE_TRIGGERS="${_CONVERGENCE_TRIGGERS}${_CONVERGENCE_TRIGGERS:+; }UPDATE PENDING flag currency"
        if [ -z "$_CONVERGENCE_TRIGGERS" ]; then
          echo "  ✓ [CONVERGENCE FAST PATH] all outstanding convergence steps repaired without a content sync — nothing to do."
          rm -rf "$TEMP_EXTRACT" "$TEMP_ZIP"
          exit 0
        fi
        echo "  ✗ [CONVERGENCE FAST PATH] still outstanding after the fast pass: ${_CONVERGENCE_TRIGGERS}"
        echo "    Proceeding with a full pass so they run — the fast path is exhausted, the full pass is the backstop."
      fi
      # <<< CONVERGENCE-FAST-PATH-END
      echo "  ✗ [CONTENT RECHECK] skills content is current, but these convergence step(s) are OUTSTANDING: ${_CONVERGENCE_TRIGGERS}"
      echo "    Proceeding with a full pass so they run — the version/content stamp is not a signal for any of them."
      # <<< CONTENT-RECHECK-CONVERGENCE-GATE-END
    fi
    echo "  ✗ [CONTENT RECHECK] stamp is current but these trees DRIFTED:${_RECHECK_DRIFT}"
    echo "    Proceeding with a full content sync — version strings are not a sync signal."
  fi

  # v10.15.48 (FIX 1): source the onboarding STATE MACHINE + verification GATE.
  # Seed the state file with every non-archived skill at "pending" from the
  # freshly-pulled source. Statuses then advance downloaded -> wired -> qc-passed
  # as the run progresses; the "complete" report is GATED on these (below).
  # v17.0.19 FIX: resolve + source the onboarding-state shim ROBUSTLY by absolute
  # path — prefer the freshly-pulled tree ($ONBOARDING_DIR), fall back to this
  # updater's own dir ($_SCRIPT_DIR) so the obs_* API stays reachable even if
  # $ONBOARDING_DIR is somehow unset. The shim DEFINES the obs_* honesty
  # state-machine + verification GATE (obs_seed_state / obs_verify_skill /
  # obs_gate_summary / ...); sourcing the canonical oc_* lib ALONE does NOT define
  # obs_*, which is why the seed printed "obs_seed_state: command not found" and the
  # verification gate (command -v obs_verify_skill) degraded to file-sync-only on
  # every roll. After sourcing we SELF-VERIFY obs_seed_state is actually defined
  # before invoking it, so a bundle mismatch degrades LOUDLY (clear message)
  # instead of emitting a raw "command not found".
  _OBS_SHIM=""
  for _obs_cand in "$ONBOARDING_DIR/scripts/onboarding-state.sh" "${_SCRIPT_DIR:-}/scripts/onboarding-state.sh"; do
    if [ -n "$_obs_cand" ] && [ -f "$_obs_cand" ]; then _OBS_SHIM="$_obs_cand"; break; fi
  done
  if [ -n "$_OBS_SHIM" ]; then
    # shellcheck disable=SC1090
    source "$_OBS_SHIM"
    # v17.0.21: source the SHARED onboarding-resume cron installer (repo-root lib)
    # so the roll/hot-patch path can install the SAME SILENT, bounded, self-removing
    # resume cron install.sh registers — no copy-paste drift. Sourced NOW (before the
    # temp-clone cleanup below) so the function persists in-shell; the prompt file it
    # reads is persisted to $OC_PERSISTENT_SCRIPTS_DIR just below.
    for _rc_lib in "$ONBOARDING_DIR/lib-onboarding-resume-cron.sh" "${_SCRIPT_DIR:-}/lib-onboarding-resume-cron.sh"; do
      if [ -n "$_rc_lib" ] && [ -f "$_rc_lib" ]; then
        # shellcheck disable=SC1090
        source "$_rc_lib"; break
      fi
    done
    # v21.3.1: same conditional-source shape as the workspace resolver -- if the
    # lib was absent the loop above sourced NOTHING and this line replaced the
    # installer with a SILENT no-op, so the roll reported success while the
    # self-healing resume cron was never registered. Announce the degradation.
    if ! command -v install_onboarding_resume_cron >/dev/null 2>&1; then
      echo "  ⚠ lib-onboarding-resume-cron.sh not found (looked in \$ONBOARDING_DIR and \${_SCRIPT_DIR}) -- install_onboarding_resume_cron() is a NO-OP for this run: the self-healing onboarding-resume cron will NOT be registered."
      install_onboarding_resume_cron() { :; }
    fi
    if command -v obs_seed_state >/dev/null 2>&1; then
      obs_seed_state "$ONBOARDING_VERSION" "$EXTRACTED_DIR" || echo "  ⚠ onboarding-state seed reported an issue (continuing)"
    else
      echo "  ⚠ onboarding-state.sh sourced ($_OBS_SHIM) but obs_seed_state is UNDEFINED -- honesty gate disabled for this run (bundle mismatch)."
    fi
  else
    echo "  ⚠ onboarding-state.sh not found in pulled repo -- honesty gate disabled for this run (older bundle?)"
    # v21.3.1: say the SECOND consequence out loud. This same file defines
    # obs_resolve_workspace(); without it every workspace lookup this run falls
    # back to reading openclaw.json directly (announced per call by
    # oc_resolve_workspace_announced), and if that also fails the run REFUSES to
    # write rather than guessing a path.
    echo "  ⚠ obs_resolve_workspace() is therefore UNDEFINED for this run -- workspace lookups will use the announced openclaw.json fallback, and will REFUSE to write if that fails."
  fi

  # Backup existing skills.
  #
  # RETENTION (OPENCLAW-BACKUP-RETENTION-V1): this used to write one
  # skills-backup-<ts> directory per run and never remove one, so every box
  # grew an unbounded pile of full skills-tree copies. Now: pre-check disk
  # BEFORE copying a byte (a half-written backup is worse than no backup, and
  # a failed backup aborts the box), then prune to the newest N only AFTER
  # this run's copy has already landed.
  _SKILLS_BACKUP_ROOT="$HOME/Downloads/openclaw-backups"
  if [ -d "$SKILLS_DIR" ] && [ "$(ls -A "$SKILLS_DIR" 2>/dev/null)" ]; then
    BACKUP_DIR="$_SKILLS_BACKUP_ROOT/skills-backup-$(date +%Y%m%d-%H%M%S)"
    _SKILLS_BACKUP_KB="$(oc_backup_size_kb "$SKILLS_DIR")"
    if ! oc_backup_precheck_disk "$BACKUP_DIR" "$_SKILLS_BACKUP_KB" "skills backup of $SKILLS_DIR"; then
      echo "  ✗ Refusing to update skills without a backup. Free disk and re-run."
      exit 1
    fi
    echo "  Creating backup: $BACKUP_DIR"
    mkdir -p "$BACKUP_DIR"
    cp -r "$SKILLS_DIR"/* "$BACKUP_DIR/" 2>/dev/null || true
    # Prune ONLY after the new backup exists — never delete the only good one
    # to make room for one that then fails.
    if [ -d "$BACKUP_DIR" ]; then
      oc_backup_prune "$_SKILLS_BACKUP_ROOT" "skills-backup-" "$BACKUP_DIR"
    else
      echo "  [backup-prune] SKIPPED: this run's backup dir was not created — nothing pruned"
    fi
  fi

  # Ensure skills directory exists
  mkdir -p "$SKILLS_DIR"

  # Copy new skills
  echo "  Installing skills to $SKILLS_DIR..."
  NEW_SKILLS_CSV=""
  SKIPPED_COUNT=0
  for SKILL_DIR in "$EXTRACTED_DIR"/[0-9]*/; do
    [ -d "$SKILL_DIR" ] || continue
    SKILL_NAME=$(basename "$SKILL_DIR")

    # Skip archived skills
    case "$SKILL_NAME" in *ARCHIVED*) continue ;; esac

    # --only filter: if ONLY_SKILLS is set, install only matching prefixes
    if [ -n "$ONLY_SKILLS" ]; then
      SKILL_PREFIX=$(echo "$SKILL_NAME" | cut -d'-' -f1)
      MATCH="false"
      OIFS=$IFS; IFS=','
      for want in $ONLY_SKILLS; do
        want_trimmed=$(echo "$want" | tr -d '[:space:]')
        if [ "$SKILL_PREFIX" = "$want_trimmed" ]; then
          MATCH="true"
          break
        fi
      done
      IFS=$OIFS
      if [ "$MATCH" != "true" ]; then
        SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
        continue
      fi
    fi

    # Check if this is a NEW skill (doesn't exist in current install)
    if [ ! -d "$SKILLS_DIR/$SKILL_NAME" ]; then
      # Track for flag + Telegram
      if [ -z "$NEW_SKILLS_CSV" ]; then
        NEW_SKILLS_CSV="$SKILL_NAME"
      else
        NEW_SKILLS_CSV="$NEW_SKILLS_CSV, $SKILL_NAME"
      fi
      echo ""
      echo "  🆕 NEW SKILL DETECTED: $SKILL_NAME"
      echo "  ============================================"
      echo "  This skill requires ACTIVATION after install."
      echo "  The agent MUST follow these steps:"
      echo ""
      echo "  a. READ all files (Teach Yourself Protocol)"
      echo "     → SKILL.md, INSTALL.md, CORE_UPDATES.md, QC.md"
      echo "     → Plus any references/*.md files"
      echo ""
      echo "  b. CHECK prerequisites, search .env files"
      echo "     → Verify API keys, credentials, software"
      echo "     → Check ~/.openclaw/skills/ for dependencies"
      echo ""
      echo "  c. EXECUTE setup (different from reading!)"
      echo "     → Follow INSTALL.md activation steps"
      echo "     → Copy scripts, create files, run commands"
      echo "     → 'Teach Yourself' means READ. 'Activate' means EXECUTE."
      echo ""
      echo "  d. APPLY CORE_UPDATES.md surgically"
      echo "     → Add to AGENTS.md, TOOLS.md, MEMORY.md"
      echo "     → Update HEARTBEAT.md if needed"
      echo ""
      echo "  e. RUN QC.md checks"
      echo "     → Verify all components work"
      echo "     → Test API connections"
      echo ""
      echo "  f. TELL client what was set up"
      echo "     → List activated features"
      echo "     → Note any pending items"
      echo ""
      echo "  ============================================"
    fi

    # Remove old version if exists
    rm -rf "$SKILLS_DIR/$SKILL_NAME"

    # Copy new version.
    # IMPORTANT: strip the trailing slash from SKILL_DIR before passing to cp.
    # The glob pattern [0-9]*/ always appends a trailing slash.
    # `cp -r "path/01-skill/" dest/` copies the CONTENTS of 01-skill/ flat
    # into dest/ (the dir itself is not created) -- this is the root cause of
    # the "132 loose files dumped into ~/.openclaw/skills/" flatten bug.
    # `cp -r "path/01-skill" dest/` (no trailing slash) copies the dir as a
    # named subdirectory, producing dest/01-skill/ as intended.
    cp -r "${SKILL_DIR%/}" "$SKILLS_DIR/"
    echo "    Updated: $SKILL_NAME"
    # FIX 1: state transition -- files are on disk = DOWNLOADED (NOT installed).
    command -v obs_set_status >/dev/null 2>&1 && obs_set_status "$SKILL_NAME" "downloaded"
  done

  # ----------------------------------------------------------
  # v14.24.0: Refresh shared-utils/ on every update so PR-delivered helpers
  # (adaptive_weights.py, prebuilt-index manifest) reach update-only boxes.
  # Mirrors install.sh:2876-2882.
  # ----------------------------------------------------------
  _SHAREDUTILS_STATUS="ok"
  if [ -d "$EXTRACTED_DIR/shared-utils" ]; then
    mkdir -p "$SKILLS_DIR/shared-utils"
    cp -r "$EXTRACTED_DIR/shared-utils/." "$SKILLS_DIR/shared-utils/"
    chmod +x "$SKILLS_DIR/shared-utils/"*.sh "$SKILLS_DIR/shared-utils/"*.py 2>/dev/null || true
    # v20.0.11: VERIFY the refresh actually landed every source top-level entry.
    # shared-utils/ (incl. sop-embed-once/) is NOT covered by the A3 numbered-skill
    # content-gate (skill-content-hash.sh enumerates only [0-9]* dirs), so a silently
    # partial cp here previously left boxes missing entire helper trees while still
    # getting stamped (observed: a box missing the whole sop-embed-once/ dir). We assert
    # source ⊆ dest (missing source entries only — dest supersets are fine) and gate the
    # stamp on it via _STEP_GATE_FAILS below.
    # v20.0.74: the original assertion iterated "$EXTRACTED_DIR/shared-utils/"*
    # and tested `[ -e ]` on the BASENAME only — top-level existence, one level
    # deep, no content comparison. A file drifted or absent INSIDE
    # prebuilt-index/, sop-embed-once/ or tone-writing-core/ was invisible to
    # it, and a top-level file present-but-stale passed. Recurse, and compare
    # bytes. Absence still gates the stamp (below); byte differences are
    # reported but deliberately NOT gated, so a file legitimately rewritten at
    # install time cannot withhold the stamp fleet-wide.
    _ocs_tree_compare "$EXTRACTED_DIR/shared-utils" "$SKILLS_DIR/shared-utils"
    _SU_MISSING="$_OC_TREE_MISSING"
    [ -n "$_OC_TREE_DIFFERS" ] && echo "  ! shared-utils content differences:${_OC_TREE_DIFFERS}" || true
    if [ -n "$_SU_MISSING" ]; then
      _SHAREDUTILS_STATUS="fail"
      echo "  ✗ shared-utils refresh INCOMPLETE — source entries missing from box:${_SU_MISSING}"
    else
      echo "  ✓ shared-utils refreshed in $SKILLS_DIR/shared-utils"
    fi

    # U006: ORPHAN DETECTION. The merge-copy above is ADDITIVE (trailing "/."):
    # it creates/overwrites but never deletes, so a file canonical has RETIRED
    # stays on the box forever (the _ocs_tree_compare check above only asserts
    # src ⊆ dest and treats dest supersets as fine). Run the orphan reconciler in
    # REPORT-ONLY mode (no --apply) so a retired file is LOGGED, never silently
    # left invisible and never moved during an automated update. Non-fatal: an
    # orphan report must never withhold the stamp or fail the update. The
    # operator can quarantine with:
    #   python3 shared-utils/reconcile-orphan-shared-utils.py \
    #     --src <canonical>/shared-utils --dest "$SKILLS_DIR/shared-utils" --apply
    _SU_ORPHAN_TOOL="$EXTRACTED_DIR/shared-utils/reconcile-orphan-shared-utils.py"
    if [ -f "$_SU_ORPHAN_TOOL" ]; then
      if python3 "$_SU_ORPHAN_TOOL" \
           --src "$EXTRACTED_DIR/shared-utils" \
           --dest "$SKILLS_DIR/shared-utils" \
           --quarantine-root "$SKILLS_DIR" >&2; then
        : # clean (no orphans) — nothing to report
      else
        _SU_ORPHAN_RC=$?
        # rc 10 = orphans found (dry-run); anything else is a tool problem. Both
        # are advisory here — never fail the update on an orphan report.
        if [ "$_SU_ORPHAN_RC" -eq 10 ]; then
          echo "  ! shared-utils has ORPHAN files canonical no longer ships (see report above; run the reconciler with --apply to quarantine)"
        else
          echo "  ! shared-utils orphan reconciler exited ${_SU_ORPHAN_RC} (advisory; update continues)"
        fi
      fi
    fi
  fi

  # v14.24.0: Deliver universal-sops/ SOP cluster (Skills 47/48 source tree).
  # Neither install nor update copied this before; Skills 47/48 wiring FAILed
  # with a FATAL looking for funnel/presentation/video/ad SOPs.
  _UNIVERSALSOPS_STATUS="ok"
  if [ -d "$EXTRACTED_DIR/universal-sops" ]; then
    rm -rf "$SKILLS_DIR/universal-sops"
    if ! cp -r "$EXTRACTED_DIR/universal-sops" "$SKILLS_DIR/"; then
      _UNIVERSALSOPS_STATUS="fail"
    fi
    # PARITY WITH shared-utils (v20.0.11). This tree is rm -rf'd first, so a
    # partial cp leaves the box with FEWER SOPs than it started with — and the
    # old code printed "✓ universal-sops refreshed" UNCONDITIONALLY, with no
    # status latch anywhere in this file, so a truncated copy was silent AND
    # still stamped. universal-sops/ is not covered by the A3 numbered-skill
    # gate either (skill-content-hash.sh enumerates only [0-9]* dirs), so this
    # was the last unverified write in the run. Assert source ⊆ dest.
    _ocs_tree_compare "$EXTRACTED_DIR/universal-sops" "$SKILLS_DIR/universal-sops"
    if [ -n "$_OC_TREE_MISSING" ]; then
      _UNIVERSALSOPS_STATUS="fail"
      echo "  ✗ universal-sops refresh INCOMPLETE — source SOPs missing from box:${_OC_TREE_MISSING}"
    else
      echo "  ✓ universal-sops refreshed in $SKILLS_DIR/universal-sops"
    fi
    # Byte differences are surfaced but do NOT withhold the stamp: a file
    # legitimately rewritten later in the run must not block the fleet.
    [ -n "$_OC_TREE_DIFFERS" ] && echo "  ! universal-sops content differences:${_OC_TREE_DIFFERS}" || true
  fi

  # ----------------------------------------------------------
  # A2.5: EARLY CONTENT-GATE — assert the copy landed, RIGHT HERE.
  #
  # This is an ORDERING fix, not a new kind of check. The authoritative A3 gate
  # lives ~2000 lines below, immediately before the version stamp. Everything
  # between here and there — QC, workforce provisioning, department floors,
  # wiring, activation — can terminate the run first. When it does, the copy is
  # NEVER verified, and the box is left silently truncated with no signal on any
  # surface.
  #
  # Observed in the field: a run copied part of the tree, exited rc=3 on a QC
  # department-floor failure, and never reached A3. That box then sat for days
  # missing 17 skill directories and ~43% of one skill's files while every
  # status surface reported healthy — because the one check that would have
  # caught it never executed. The gate was sound; it just ran too late to run
  # at all.
  #
  # So the copy is asserted HERE, the moment it finishes, while a failure is
  # still attributable to the copy that caused it. A3 below is UNCHANGED and
  # remains authoritative for the stamp; this is a fail-fast tripwire in front
  # of it, deliberately duplicating that logic rather than moving it.
  # ----------------------------------------------------------
  if [ -n "$SRC_MANIFEST" ] && [ -f "$_CONTENT_HASH_SCRIPT" ]; then
    echo ""
    echo "  [A2.5] Early content-gate: verifying the copy landed before continuing..."
    _EARLY_DEST_MANIFEST=$(bash "$_CONTENT_HASH_SCRIPT" "$SKILLS_DIR" 2>/dev/null || true)
    _EARLY_FAIL=0
    _EARLY_DETAIL=""
    if [ -z "$_EARLY_DEST_MANIFEST" ]; then
      # Could not measure. That is NOT a pass and NOT a failure — defer to A3
      # rather than inventing a verdict from a broken instrument.
      echo "  [A2.5] destination manifest unavailable — no early verdict; deferring to the A3 gate" >&2
    else
      while IFS='|' read -r _e_skill _e_src; do
        [ -z "$_e_skill" ] && continue
        [ "$_e_skill" = "__TREE_SHA__" ] && continue
        case "$_e_skill" in *ARCHIVED*) continue ;; esac

        # Mirror A3's --only scoping so a deliberately narrow run is not failed
        # by drift in a skill this run never intended to copy.
        if [ -n "${ONLY_SKILLS:-}" ]; then
          _e_prefix=$(echo "$_e_skill" | cut -d'-' -f1)
          _e_want=0
          _e_oifs=$IFS; IFS=','
          for _e_o in $ONLY_SKILLS; do
            [ "$_e_prefix" = "$(echo "$_e_o" | tr -d '[:space:]')" ] && _e_want=1
          done
          IFS=$_e_oifs
          [ "$_e_want" -eq 1 ] || continue
        fi

        _e_dest=$(printf '%s\n' "$_EARLY_DEST_MANIFEST" | grep "^${_e_skill}|" | cut -d'|' -f2 | head -1)
        if [ -z "$_e_dest" ]; then
          _EARLY_DETAIL="${_EARLY_DETAIL}  ${_e_skill}: expected=${_e_src} found=<missing>\n"
          _EARLY_FAIL=1
        elif [ "$_e_dest" != "$_e_src" ]; then
          _EARLY_DETAIL="${_EARLY_DETAIL}  ${_e_skill}: expected=${_e_src} found=${_e_dest}\n"
          _EARLY_FAIL=1
        fi
      done <<< "$SRC_MANIFEST"
    fi

    if [ "$_EARLY_FAIL" -eq 1 ]; then
      echo ""
      echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
      echo "  A2.5 EARLY CONTENT-GATE FAILED — the copy did not land completely."
      echo ""
      echo "  Stopping HERE, at the copy site, rather than continuing into QC"
      echo "  and risking an exit that never reaches the A3 verification below."
      echo "  The following skills do not match the source tree:"
      printf '%b' "$_EARLY_DETAIL"
      echo "  No version stamp has been written."
      echo "  Re-run this updater from a current checkout to retry the install."
      echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
      rm -rf "$TEMP_EXTRACT" "$TEMP_ZIP" 2>/dev/null || true
      exit 1
    fi
    echo "  [A2.5] Early content-gate PASSED — copy verified at the copy site."
  fi

  # SK1-63 (fleet-installer wiring, update path): mirror the same runtime-dir
  # manifest placement install.sh's install_skill_47_movie_producer() does on
  # fresh installs. executive_producer.py's load_manifest() resolves the
  # manifest via a repo-root walk-up (finds universal-sops/ as a sibling of
  # 47-movie-producer/ under $SKILLS_DIR, refreshed just above) BEFORE it ever
  # reaches this runtime-dir copy, so this is defense-in-depth — not the only
  # path — but it is the one Skill 47's OWN install.sh documents as canonical
  # and the fleet installer must not depend solely on the walk-up continuing to
  # work. Only runs when Skill 47 is actually installed on this box (opt-in
  # skill — never install OpenMontage or touch the network here, pure local
  # file copy). Non-fatal: never fails the update over an optional video skill.
  if [ -d "$SKILLS_DIR/47-movie-producer" ]; then
    S47_MANIFEST_SRC="$SKILLS_DIR/universal-sops/video-pipeline-craft/VIDEO-PIPELINE-MANIFEST.json"
    S47_OPENMONTAGE_DIR="${OPENCLAW_OPENMONTAGE_DIR:-$HOME/.openclaw/openmontage-runtime/OpenMontage}"
    S47_MANIFEST_DEST="$(dirname "$S47_OPENMONTAGE_DIR")/VIDEO-PIPELINE-MANIFEST.json"
    if [ -f "$S47_MANIFEST_SRC" ]; then
      mkdir -p "$(dirname "$S47_MANIFEST_DEST")" 2>/dev/null
      if cp "$S47_MANIFEST_SRC" "$S47_MANIFEST_DEST" 2>>"$LOG_FILE" && \
         python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$S47_MANIFEST_DEST" 2>>"$LOG_FILE"; then
        echo "  ✓ Skill 47: VIDEO-PIPELINE-MANIFEST.json refreshed at $S47_MANIFEST_DEST (fleet-installer path)"
      else
        echo "  ⚠ Skill 47: could not refresh VIDEO-PIPELINE-MANIFEST.json at $S47_MANIFEST_DEST (see $LOG_FILE) — load_manifest() falls back to the universal-sops sibling walk-up"
      fi
    fi
  fi

  # ----------------------------------------------------------
  # U001 -- Presentations manifest+ruleset placement (canonical-home wiring)
  #
  # Copy the cluster-canonical PIPELINE-MANIFEST.json and
  # MASTER-QC-AUTOFAIL-RULESET.md into the materialized Presentations department's
  # sops/ directory so manifests_source.py's resolve_manifest() / resolve_ruleset()
  # find the installed copy FIRST (provenance "installed"), before falling back to
  # the cluster walk-up or legacy paths.  Also write MANIFEST-SOURCE.txt with the
  # content_sha256 so the checker can refuse on mismatch instead of silently
  # reading a stale manifest.  Guarded on the department existing; non-fatal.
  #
  # WORKSPACE-RESOLUTION FIX (WI-01, 2026-08-10): the prior shape resolved the
  # department dir ONLY as "$OC_WS_RESOLVED/departments/Presentations", where
  # OC_WS_RESOLVED comes from agents.list[id=main].workspace /
  # agents.defaults.workspace. On a box whose main agent's workspace is
  # $HOME/clawd (the operator box is exactly this), U001 targeted
  # ~/clawd/departments/Presentations and SKIPPED because the materialized
  # department lives at <oc-root>/workspace/departments/Presentations (the
  # dept-Presentations agent's own declared workspace) — so future fleet rolls
  # never landed the canonical manifest on the live department. The fix
  # enumerates candidate department homes in priority order — (1) this box's
  # openclaw.json dept-Presentations agent's OWN workspace, (2) the announced
  # workspace, (3) the canonical <oc-root>/workspace — and picks the first one
  # that EXISTS and is materialized (sops/ + scripts/build_deck.py present).
  # Announced loud; a miss names every candidate probed, never a bare skip.
  # ----------------------------------------------------------
  _u001_presentations_manifest_placement() {
    # Announced resolution of the GENERAL workspace stays (candidate 2 below),
    # but it is never the only candidate: the main agent's workspace can point
    # at $HOME/clawd on this box while the materialized department lives under
    # <oc-root>/workspace.
    oc_resolve_workspace_announced "U001 presentations manifest placement" 2>/dev/null || true
    local _oc_root="$HOME/.openclaw"
    [ -d "/data/.openclaw" ] && _oc_root="/data/.openclaw"
    local _oc_json="$_oc_root/openclaw.json"
    local _dept_ws_from_config=""
    if [ -f "$_oc_json" ] && command -v python3 >/dev/null 2>&1; then
      _dept_ws_from_config="$(OC_JSON="$_oc_json" python3 - <<'PYEOF' 2>/dev/null || true
import json, os
try:
    cfg = json.load(open(os.environ["OC_JSON"]))
    for ag in cfg.get("agents", {}).get("list", []) or []:
        if isinstance(ag, dict) and str(ag.get("id", "")).lower() == "dept-presentations" and ag.get("workspace"):
            print(os.path.expanduser(ag["workspace"]))
            break
except Exception:
    pass
PYEOF
)"
    fi
    local _dept_dir=""
    local _probed=""
    local _c
    for _c in \
      ${_dept_ws_from_config:+"$_dept_ws_from_config"} \
      ${OC_WS_RESOLVED:+"$OC_WS_RESOLVED/departments/Presentations"} \
      "$_oc_root/workspace/departments/Presentations"; do
      _probed="${_probed:+$_probed | }$_c"
      if [ -n "$_c" ] && [ -d "$_c" ] && [ -d "$_c/sops" ] && [ -f "$_c/scripts/build_deck.py" ]; then
        _dept_dir="$_c"
        break
      fi
    done
    if [ -z "$_dept_dir" ]; then
      echo "  [U001] presentations manifest placement SKIPPED (no materialized Presentations department; probed: $_probed)" >&2
      return 0
    fi
    echo "  [U001] presentations workspace -> $_dept_dir"
    echo "  [U001] resolved via: candidates probed in order [dept-Presentations agent workspace from $_oc_json, announced workspace, canonical $_oc_root/workspace]; first EXISTING materialized directory (sops/ + scripts/build_deck.py) wins"
    local _sops_dir="$_dept_dir/sops"
    mkdir -p "$_sops_dir" 2>/dev/null
    local _manifest_src="$SKILLS_DIR/universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json"
    local _ruleset_src="$SKILLS_DIR/universal-sops/presentation-slide-craft/MASTER-QC-AUTOFAIL-RULESET.md"
    local _manifest_dest="$_sops_dir/PIPELINE-MANIFEST.json"
    local _ruleset_dest="$_sops_dir/MASTER-QC-AUTOFAIL-RULESET.md"
    local _source_txt="$_sops_dir/MANIFEST-SOURCE.txt"
    if [ ! -f "$_manifest_src" ]; then
      echo "  ⚠ U001: cluster manifest not found at $_manifest_src — placement skipped"
      return 0
    fi
    if ! cp "$_manifest_src" "$_manifest_dest" 2>>"$LOG_FILE" || \
       ! python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$_manifest_dest" 2>>"$LOG_FILE"; then
      echo "  ⚠ U001: could not validate PIPELINE-MANIFEST.json at $_manifest_dest (see $LOG_FILE)"
      return 0
    fi
    if [ -f "$_ruleset_src" ]; then
      cp "$_ruleset_src" "$_ruleset_dest" 2>>"$LOG_FILE" || true
    fi
    local _git_sha=""
    if git -C "$SKILLS_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
      _git_sha="$(git -C "$SKILLS_DIR" log -1 --format=%H -- universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json 2>/dev/null || true)"
    fi
    local _content_sha256
    _content_sha256="$(python3 -c "import hashlib; print(hashlib.sha256(open('$_manifest_dest','rb').read()).hexdigest())" 2>/dev/null || true)"
    {
      printf 'source_path=%s\n' "$_manifest_src"
      printf 'git_sha=%s\n' "$_git_sha"
      printf 'content_sha256=%s\n' "$_content_sha256"
      printf 'installed_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } > "$_source_txt"
    echo "  ✓ U001: PIPELINE-MANIFEST.json + MASTER-QC-AUTOFAIL-RULESET.md placed at $_sops_dir"
  }
  _u001_presentations_manifest_placement

  # ----------------------------------------------------------
  # UNIFIED COMPLETENESS-GATE LATCHES (D3/D4/D5 convergence). Initialized here,
  # BEFORE Step U6b, so every latch is set -u safe no matter which branch below
  # runs. PASS values by default (0 / "ok" / 1) -- flipped to FAIL only on a
  # genuine completeness-critical miss. The single stamp gate inserted between
  # the A3 content-gate and the version-stamp write reads all of these; see
  # that block for the consolidated pass/fail contract. Universal convention:
  # PASS == fully completed OR a benign/legitimate skip (idempotent no-op,
  # already-current, pre-interview no-op, nothing-to-do, out-of-scope); FAIL
  # ONLY when a completeness-critical action genuinely did not happen.
  # ----------------------------------------------------------
  # CONTENT-integrity latches (each GATES the .onboarding-version stamp -- a fail
  # WITHHOLDS the stamp because the skills CONTENT is not verifiably current):
  _U6B_PERSONA_FAIL=0            # persona-index CONTENT wiring (sentinel != pinned release_tag, triad-divergent library, or helper did not run)
  _D2_REFRESH_STATUS="ok"       # in-scope role/SOP CONTENT refresh (refresh-stale-roles.py rc 3 -- new library content that SHOULD have re-applied to an EXISTING artifact did not)
  _D2_DEPTSCRIPTS_STATUS="ok"   # UNCONDITIONAL dept scripts/ mirror (refresh-dept-scripts.py rc 3 -- a materialized department's canonical scripts/ file missing/diverged from the library AFTER the copy step; runs every roll, independent of any gap map -- fixes delivery causes 2/3)
  _SHAREDCORE_STATUS="ok"       # shared-core-file wiring step (link_shared_core_files)
  # WORKFORCE-provisioning latches (v20.0.10: DECOUPLED from the content stamp --
  # they describe "is the client's workforce fully built", NOT "is the skills
  # content current". A miss is surfaced as an advisory and driven to completion
  # by the POST-stamp qc-completeness run + the onboarding-resume cron; it NEVER
  # withholds the skills-version stamp):
  _D2_MIGRATE_STATUS="ok"       # workforce floor-fill / workforce QC (migrate-existing-workforce.sh: empty depts for an interview-incomplete client, or a dept below the 95% floor)
  _D5_ACTIVATION_PASS=1         # dept-agent activation (materialize-dept-agents.sh: agents.list[] below this box's computed department floor)
  _D5_NOTLIVE_DETAIL=""
  _D5_AGENT_COUNT=0
  _D5_DEPT_STATE="skipped"
  _STEP_GATE_FAILS=""
  _WORKFORCE_INCOMPLETE_NOTES=""  # workforce-provisioning advisories -- surfaced, NEVER stamp-gating
  # GHL MCP Tier-2 RUNTIME conformance latch (DEFECT 2). Declared here, with the
  # other latches, so it is `set -u` safe on every path — including the ones that
  # never reach the wiring loop. It is INFRASTRUCTURE, not skills content: it
  # never withholds the version stamp, but it DOES make this run exit 2 instead
  # of 0, because a roll that leaves the MCP misconfigured is not a success.
  GHL_MCP_RUNTIME_FATAL="no"
  GHL_MCP_RUNTIME_DETAIL=""
  GHL_MCP_AUTOSTART_RAN="not-run"
  # Command Center runtime-config (U6d) FINAL-VERDICT latch (U6D-CC-RUNTIME
  # fix, 2026-08-04 -- NOT the "DEFECT 2" GHL-MCP-runtime latch just above;
  # a separate fix, same pattern). Declared here alongside GHL_MCP_RUNTIME_FATAL, which it
  # mirrors exactly: a genuine reconcile_command_center_runtime.py failure
  # (invalid/corrupt existing CC runtime data the reconciler correctly
  # refuses to clobber, or an I/O error) is CC-side runtime configuration,
  # not skills content -- it must never withhold the version stamp, but a
  # roll that leaves it unreconciled is not a clean success either, so it
  # makes this run's FINAL exit code 2 instead of 0 (see the U6D-CC-RUNTIME
  # final verdict block near the end of main()). The genuinely-unprovisioned case
  # (this box's workforce interview hasn't completed yet) is a SEPARATE,
  # fully benign outcome -- see the interview-completion-aware WARNING
  # appended to _WORKFORCE_INCOMPLETE_NOTES at the U6d call site itself; it
  # never touches this latch.
  _U6D_CC_RUNTIME_FATAL="no"
  _U6D_CC_RUNTIME_DETAIL=""

  # ----------------------------------------------------------
  # U008: PRE-FLIGHT SPEND CHECK. Runs BEFORE the first paid-API step (U6b
  # persona embedding, and the QC gates / floor-fill that follow). Warns (or,
  # with OPENCLAW_SPEND_GATE=1, gates) when the org's remaining budget is below
  # OPENCLAW_ORG_SPEND_LIMIT, so a depleted budget is never burned through
  # silently — especially important for fleet-wide rolls. When no budget figure
  # is configured the check is a no-op (AC#3: runs with sufficient/unknown budget
  # proceed unchanged, no new warning, same exit code).
  _U008_SKIP_PAID_STEPS=0
  if ! u008_preflight_spend_check; then
    _U008_SKIP_PAID_STEPS=1
  fi

  # ----------------------------------------------------------
  # Step U6b: Provision prebuilt persona index + wire GHL funnel catalog
  # (v14.25.0) — mirrors install.sh Step 6b so update-only boxes receive
  # the section-tagged canonical persona DB and catalog path vars identically to a
  # fresh install.  Uses shared-utils/provision-persona-index.sh (copied
  # above by the shared-utils refresh block).
  #
  # F2.1: reconcile_persona_assets now UNION-merges persona-categories.json
  # (client-local personas preserved, not clobbered) and provision_persona_index
  # treats a client canonical+local-delta index as canonical (superset) instead
  # of re-downloading over it. A genuine re-download preserves origin:local rows;
  # any it cannot preserve are queued in .persona-local-reembed-queue, surfaced
  # to the operator below.
  #
  # COACHING_DB_DIR: OC_WORKSPACE is defined later (line 1677+) so we
  # resolve the coaching DB dir inline using the same platform detection
  # already set at the top of this script (OC_CONFIG).
  # ----------------------------------------------------------
  _U6B_MANIFEST="$SKILLS_DIR/shared-utils/prebuilt-index/INDEX-MANIFEST.json"
  [ -f "$_U6B_MANIFEST" ] || _U6B_MANIFEST="$EXTRACTED_DIR/shared-utils/prebuilt-index/INDEX-MANIFEST.json"

  _U6B_COACHING_DB_DIR="$HOME/.openclaw/workspace/data/coaching-personas"
  [ -d "/data/.openclaw" ] && _U6B_COACHING_DB_DIR="/data/.openclaw/workspace/data/coaching-personas"

  _U6B_OC_JSON="$HOME/.openclaw/openclaw.json"
  [ -f "/data/.openclaw/openclaw.json" ] && _U6B_OC_JSON="/data/.openclaw/openclaw.json"
  _U6B_OC_SECRETS_ENV="$HOME/.openclaw/secrets/.env"
  [ -d "/data/.openclaw" ] && _U6B_OC_SECRETS_ENV="/data/.openclaw/secrets/.env"
  # Defensive 0600 on the secrets file before anything is handed its path.
  #
  # The credential WRITES live in shared-utils/provision-persona-index.sh, which
  # already chmod 600s correctly (on touch, and again after each append). This
  # line is not duplicating that -- it tightens a file that may ALREADY exist
  # with loose permissions from an older install, which nothing on this code
  # path previously did.
  #
  # It also un-freezes this file. .githooks/pre-commit rule 4 blocks any .sh that
  # references secrets/.env without containing a `chmod 600`; that check is
  # per-file and cannot see the delegation above, so it had blocked every commit
  # touching this script -- which is why ONBOARDING_VERSION sat at v21.4.2 while
  # /version and install.sh moved to v21.4.16. The rule is a reasonable heuristic
  # and this satisfies it truthfully rather than working around it.
  [ -f "$_U6B_OC_SECRETS_ENV" ] && chmod 600 "$_U6B_OC_SECRETS_ENV" 2>/dev/null || true

  _U6B_HELPER="${SKILLS_DIR:-$HOME/.openclaw/skills}/shared-utils/provision-persona-index.sh"
  [ -f "$_U6B_HELPER" ] || _U6B_HELPER="${EXTRACTED_DIR:-}/shared-utils/provision-persona-index.sh"

  # Workspace + Skill-22 source for the persona reconcile (v14.27.2).
  _U6B_WS="$HOME/.openclaw/workspace"
  [ -d "/data/.openclaw" ] && _U6B_WS="/data/.openclaw/workspace"
  _U6B_SK22="$SKILLS_DIR/22-book-to-persona-coaching-leadership-system"

  if [ "$_U008_SKIP_PAID_STEPS" = "1" ]; then
    # U008 budget GATE (OPENCLAW_SPEND_GATE=1 + remaining budget below the
    # limit): skip the paid persona-embedding step. This is a legitimate
    # budget-driven skip, NOT a content failure, so _U6B_PERSONA_FAIL is NOT set
    # and the content stamp is NOT withheld. The onboarding-resume cron re-runs
    # this once the budget is restored.
    _PIDX_SKIP_WARNINGS="${_PIDX_SKIP_WARNINGS:+$_PIDX_SKIP_WARNINGS; }persona-index provisioning SKIPPED by the U008 pre-flight spend gate (remaining budget below OPENCLAW_ORG_SPEND_LIMIT)"
    echo "  ⚠️  Persona-index provisioning SKIPPED by the U008 pre-flight spend gate (paid step deferred until budget is restored)"
  elif [ -f "$_U6B_MANIFEST" ] && [ -f "$_U6B_HELPER" ]; then
    # shellcheck source=/dev/null
    source "$_U6B_HELPER"
    # PRE-ROLL PERSONA-SET TRIAD (fail-closed backstop). Before shipping the
    # pulled persona library to this box, the N38 count triad — blueprint dirs ==
    # persona-categories.json keys == INDEX-MANIFEST persona_count == canonical —
    # MUST agree. CI enforces this at the PR boundary; this is the roll-side
    # backstop so a roll off a non-main / dirty / mid-catch-up checkout REFUSES to
    # provision a stale/divergent persona set instead of silently shipping the OLD
    # count. On divergence we SKIP persona provisioning (keep the box's current
    # set) and surface a loud operator warning, rather than shipping a broken set.
    _U6B_TRIAD_GUARD="$_U6B_SK22/pipeline/assert-personas-published.sh"
    _U6B_TRIAD_OK=1
    if [ -f "$_U6B_TRIAD_GUARD" ]; then
      if ! bash "$_U6B_TRIAD_GUARD" --repo "$SKILLS_DIR" --repo-only >/dev/null 2>&1; then
        _U6B_TRIAD_OK=0
      fi
    fi
    # ASSET-FRESHNESS PRE-ROLL (FDN-7 / F1.3 gate 2). A manifest carrying
    # asset_rebuild_required:true was count-synced by a --no-asset staging bump:
    # the four SET counts agree (so the triad guard above passes) but the
    # published gemini-index.sqlite.gz still lacks vectors for the newest
    # persona(s). Provisioning from it would ship a counted-but-vector-less
    # library (Layer-5 degrades to keyword for those personas). REFUSE and KEEP
    # the box's current index until a real build-and-publish.sh clears the flag.
    # Coordinates with the FDN-6 triad pre-roll above — BOTH must pass to
    # provision. Fail-open on a read error (never block a roll on a parse hiccup).
    _U6B_ASSET_OK=1
    if command -v python3 >/dev/null 2>&1; then
      _U6B_ASSET_REBUILD="$(python3 -c 'import json,sys
try:
    print("true" if json.load(open(sys.argv[1])).get("asset_rebuild_required") is True else "false")
except Exception:
    print("false")' "$_U6B_MANIFEST" 2>/dev/null || echo false)"
      [ "$_U6B_ASSET_REBUILD" = "true" ] && _U6B_ASSET_OK=0
    fi
    if [ "$_U6B_TRIAD_OK" != "1" ]; then
      _PIDX_SKIP_WARNINGS="${_PIDX_SKIP_WARNINGS:+$_PIDX_SKIP_WARNINGS; }persona-set triad DIVERGENT in the pulled repo (blueprint dirs / categories keys / INDEX-MANIFEST persona_count disagree) — persona provisioning SKIPPED (refused to ship a stale library). Run 22-…/pipeline/publish-personas-to-fleet.sh, merge, and re-roll."
      _U6B_PERSONA_FAIL=1  # D3: triad-divergent skip is completeness-critical, not benign
      echo "  ✗ PRE-ROLL persona-set triad DIVERGENT — REFUSING to provision a stale/divergent persona library on this box."
      echo "     Fix the repo with 22-book-to-persona-coaching-leadership-system/pipeline/publish-personas-to-fleet.sh and re-roll."
    elif [ "$_U6B_ASSET_OK" != "1" ]; then
      _PIDX_SKIP_WARNINGS="${_PIDX_SKIP_WARNINGS:+$_PIDX_SKIP_WARNINGS; }INDEX-MANIFEST asset_rebuild_required:true (a --no-asset staging manifest — the published asset lacks vectors for the newest persona(s)) — persona index provisioning SKIPPED (kept the box's current index). Rebuild+publish the asset via shared-utils/prebuilt-index/build-and-publish.sh, merge, and re-roll."
      _U6B_PERSONA_FAIL=1  # D3: asset-rebuild-required skip is completeness-critical, not benign
      echo "  ✗ PRE-ROLL asset_rebuild_required:true — REFUSING to (re)provision from a staged --no-asset manifest (would ship a counted-but-vector-less library). Keeping the box's current persona index."
      echo "     Rebuild+publish the real asset with shared-utils/prebuilt-index/build-and-publish.sh and re-roll."
    else
      # Reconcile categories + blueprints to the workspace FIRST so the index
      # gate sees the persona dirs (furnace-safe), then provision the index.
      reconcile_persona_assets "$_U6B_SK22" "$_U6B_COACHING_DB_DIR" "$_U6B_WS"
      provision_persona_index "$_U6B_MANIFEST" "$_U6B_COACHING_DB_DIR"

      # ----------------------------------------------------------
      # D3 (C4): COMPLETION RE-ASSERTION. reconcile_persona_assets /
      # provision_persona_index both always `return 0` (so a bare caller under
      # set -euo pipefail never aborts mid-provision) -- truth is carried
      # out-of-band via the exported _RECONCILE_OK (0/1) plus the on-disk
      # .prebuilt-index-version sentinel. Re-check BOTH here so a reconcile
      # failure or a sentinel that never reached the manifest's release_tag
      # flips the completeness-gate latch instead of silently passing.
      # ----------------------------------------------------------
      _U6B_RELEASE_TAG="$(python3 -c 'import json,sys
try:
    print(json.load(open(sys.argv[1])).get("release_tag",""))
except Exception:
    print("")' "$_U6B_MANIFEST" 2>/dev/null || true)"
      _U6B_SENTINEL_VAL="$(cat "$_U6B_COACHING_DB_DIR/.prebuilt-index-version" 2>/dev/null | tr -d '[:space:]' || true)"
      if [ "${_RECONCILE_OK:-1}" = "0" ] || [ -z "$_U6B_RELEASE_TAG" ] || [ "$_U6B_SENTINEL_VAL" != "$_U6B_RELEASE_TAG" ]; then
        _U6B_PERSONA_FAIL=1
        _PIDX_SKIP_WARNINGS="${_PIDX_SKIP_WARNINGS:+$_PIDX_SKIP_WARNINGS; }persona-index completion re-assertion FAILED (reconcile_ok=${_RECONCILE_OK:-unset}, sentinel=${_U6B_SENTINEL_VAL:-<missing>}, manifest release_tag=${_U6B_RELEASE_TAG:-<unknown>}) — persona provisioning incomplete on this box"
        echo "  ✗ [D3] U6b completion re-assertion FAILED — sentinel(${_U6B_SENTINEL_VAL:-<missing>}) != release_tag(${_U6B_RELEASE_TAG:-<unknown>}) or reconcile not ok(${_RECONCILE_OK:-unset})"
      else
        echo "  ✓ [D3] U6b completion re-assertion PASSED (sentinel == manifest release_tag, reconcile ok)"
      fi

      # F2.1: if a re-download could not preserve some client-local persona
      # rows, provision_persona_index leaves a .persona-local-reembed-queue
      # marker. Surface it in the operator completion report (never client-
      # visible) so the operator re-embeds those personas with the CLIENT's own
      # key — their blueprints remain on disk, so this is a delta re-embed.
      _U6B_REEMBED_QUEUE="$_U6B_COACHING_DB_DIR/.persona-local-reembed-queue"
      if [ -s "$_U6B_REEMBED_QUEUE" ]; then
        _U6B_QN="$(grep -c . "$_U6B_REEMBED_QUEUE" 2>/dev/null || echo '?')"
        _PIDX_SKIP_WARNINGS="${_PIDX_SKIP_WARNINGS:+$_PIDX_SKIP_WARNINGS; }${_U6B_QN} client-local persona(s) need a delta re-embed with the client's own key (see $_U6B_REEMBED_QUEUE) — index re-download could not carry their vectors over"
        echo "  ⚠️  ${_U6B_QN} client-local persona(s) queued for delta re-embed (client's OWN key) — $_U6B_REEMBED_QUEUE"
      fi
      # qmd provisioning removed 2026-07-23.  The qmd tool (better-sqlite3 backed)
      # was replaced by Google/OpenAI embeddings. Runs AFTER reconcile + provision so the
      # canonical dir holds the current blueprints.
      # reconcile_qmd_persona_index call removed — inventory answers from persona-categories.json per N16.
      # FIX 4 (cascade): if reconcile_persona_assets detected the SET grew
      # (_SET_CHANGED=1), re-wire matching + Command Center + the dept persona
      # reflex (governing-personas.md refresh + stickiness bust). Static/idempotent.
      if [ "${_SET_CHANGED:-0}" = "1" ]; then
        echo "  → persona SET changed — re-wiring governing-personas.md + busting stickiness"
        rewire_on_persona_set_change "$SKILLS_DIR" "$_U6B_WS"
      fi
      wire_ghl_funnel_catalog "$SKILLS_DIR" "$_U6B_OC_SECRETS_ENV" "$_U6B_OC_JSON"
    fi
  else
    # P11-1: this is the "helper/bundle missing" skip at the CALLER level (the
    # file itself is absent, so provision-persona-index.sh's own
    # _pidx_skip_warn accumulator was never sourced). Feed the same
    # _PIDX_SKIP_WARNINGS accumulator directly so this box's completion report
    # (built below from ONBOARDING_GATE_SUMMARY/QC_STATUS_LINE) surfaces it
    # too, instead of a plain log line an operator would never see.
    _PIDX_SKIP_WARNINGS="${_PIDX_SKIP_WARNINGS:+$_PIDX_SKIP_WARNINGS; }persona-index manifest or provision helper not found — Step U6b did not run"
    _U6B_PERSONA_FAIL=1  # D3: manifest/helper missing means U6b genuinely did not run -- completeness-critical, not benign
    echo "  ⚠️  Persona-index provisioning SKIPPED: manifest or provision helper not found — Step U6b did not run"
  fi

  # ----------------------------------------------------------
  # >>> U6C-SOP-LIBRARY-BEGIN  (extracted verbatim by tests/unit/update-skills-u6c-set-e-continuation.test.sh)
  # Step U6c: SOP V2 LIBRARY INGESTION (v20.1.0).
  #
  # THE DEFECT THIS CLOSES. The updater synced FILES but never populated the
  # SOP DATABASE. Proven live across two boxes: a box that ran the update,
  # received every file and reported a green "update complete" still held 24
  # `sops` rows -- 23 of them the CC boot-seed demo fixture (autoSeedStarterSOPs
  # / STARTER_SOPS) plus 1 manual, with `SELECT COUNT(*) FROM sops WHERE source
  # IS NOT NULL` = 0, i.e. NOTHING was ever ingested from any file. A correctly
  # populated box holds 2578 (2555 library + 23 starters). 24/2578 means
  # semantic SOP search covered 0.9% of the corpus while the box reported pass.
  #
  # WHY THE EXISTING WIRING DID NOT COVER IT. run-full-install.sh phase 6i DOES
  # ingest, and DOES run in --update-only mode, and update-skills.sh DOES invoke
  # it further down. But that invocation is
  #     if bash "$_CC_RUN_INSTALL" --update-only ... ; then ✓ else ⚠ fi
  # -- a phase-6i fail_install is swallowed into an advisory "⚠ reported errors"
  # line that neither latches a gate, nor withholds the stamp, nor fails the
  # run. Phase 6i additionally SKIPS itself entirely (exit 0) when no CLIENT_SLUG
  # resolves, and is a documented NO-OP whenever this box's CC checkout is not at
  # the installer's hardcoded DASHBOARD_DIR. Three independent silent paths to
  # "green with an empty library". This step is the fail-CLOSED backstop.
  #
  # CONTRACT:
  #   - IDEMPOTENT + NEVER CLOBBERS A HEALTHY BOX. ingest-sop-library.sh's
  #     already-populated gate exits 0 without downloading, backing up, or
  #     writing ANYTHING once the box is at/above the manifest's canonical
  #     population. A box already carrying the full library (and any
  #     client-authored SOPs on top) is left byte-for-byte alone. The ingester
  #     itself is upsert-only (INSERT OR REPLACE on a deterministic
  #     `sop_<slug>` primary key, INSERT OR IGNORE elsewhere) and DELETES
  #     nothing, so even a forced re-run cannot duplicate a row or drop a
  #     client SOP.
  #   - STARTER SEED PRESERVED. The 23 CC starters and the 2555 library rows
  #     occupy disjoint id-spaces (verified: 0 collisions), which is exactly why
  #     a populated box reads 2578 and not 2555.
  #   - SLUG IS NOT A BLOCKER. The client slug only scopes `client_template_vars`
  #     rows; the SOP rows themselves are global. So unlike phase 6i, a box with
  #     no resolvable slug still gets its library -- it falls back rather than
  #     skipping the ingest and calling that success.
  #   - ZERO EMBEDDING COST. This step ingests CONTENT ONLY. It makes no
  #     embedding API call and cannot bill the client's Gemini key. See the
  #     operator note the ingester prints about the resulting unembedded rows.
  #   - FAILS LOUD. Any genuine failure latches _U6C_SOPLIB_FAIL, which withholds
  #     the version stamp and exits 1 via the content-completeness gate below.
  #     "No Command Center DB on this box" is NOT a failure (the CC is simply not
  #     installed here) -- that is an informational skip.
  # ----------------------------------------------------------
  _U6C_SOPLIB_FAIL=0
  _U6C_SOPLIB_NOTE=""
  _U6C_INGEST_SH="$SKILLS_DIR/32-command-center-setup/scripts/ingest-sop-library.sh"
  [ -f "$_U6C_INGEST_SH" ] || _U6C_INGEST_SH="$EXTRACTED_DIR/32-command-center-setup/scripts/ingest-sop-library.sh"
  _U6C_ASSERT_PY="$SKILLS_DIR/32-command-center-setup/scripts/assert-sop-library-populated.py"
  [ -f "$_U6C_ASSERT_PY" ] || _U6C_ASSERT_PY="$EXTRACTED_DIR/32-command-center-setup/scripts/assert-sop-library-populated.py"
  _U6C_MANIFEST="$SKILLS_DIR/shared-utils/sop-library/SOP-LIBRARY-MANIFEST.json"
  [ -f "$_U6C_MANIFEST" ] || _U6C_MANIFEST="$EXTRACTED_DIR/shared-utils/sop-library/SOP-LIBRARY-MANIFEST.json"

  # ----------------------------------------------------------------------
  # SQLITE ACCESS (DEFECT FIX, sibling of ingest-sop-library.sh's own fix,
  # same live 2026-08 Hostinger VPS finding). U6c and U6c2 below re-read
  # `sops` / `sop_embeddings` row counts via a raw `sqlite3` CLI call with a
  # `2>/dev/null || echo 0` fallback -- on the shared Hostinger base image
  # (which ships libsqlite3-0 but NOT the sqlite3 CLI binary) that silently
  # turns "the CLI does not exist" into a FALSE ZERO. That false zero then
  # trips `_U6C_AFTER < _U6C_CANON` at the post-ingest re-check below EVEN
  # WHEN ingest-sop-library.sh (fixed the same night, now python3-stdlib
  # primary) just correctly reported success with the TRUE row count -- i.e.
  # fixing ingest-sop-library.sh alone is not sufficient; this updater's own
  # redundant re-verification carried the identical false-0 trap one layer
  # up. python3's stdlib sqlite3 (already a hard dependency of this exact
  # block's own DB resolution just below) is the primary path; the CLI is
  # kept only as a fallback. True "neither tool available" prints the
  # distinguishable, non-numeric sentinel SQLITE_UNAVAILABLE -- NEVER a
  # number -- so a caller that forgets to check it fails a `-lt`/`-ge`
  # integer test loudly instead of silently comparing against 0.
  # ----------------------------------------------------------------------
  _U6C_HAVE_PY3_SQLITE=0
  if command -v python3 >/dev/null 2>&1 && python3 -c 'import sqlite3' >/dev/null 2>&1; then
    _U6C_HAVE_PY3_SQLITE=1
  fi
  _U6C_HAVE_SQLITE3_CLI=0
  command -v sqlite3 >/dev/null 2>&1 && _U6C_HAVE_SQLITE3_CLI=1
  _sqlite_count() {  # _sqlite_count <db> <sql>
    local _scdb="$1" _scsql="$2"
    if [ "$_U6C_HAVE_PY3_SQLITE" = "1" ]; then
      SQLITE_COUNT_DB="$_scdb" SQLITE_COUNT_SQL="$_scsql" python3 -c '
import os, sqlite3
db = os.environ["SQLITE_COUNT_DB"]
sql = os.environ["SQLITE_COUNT_SQL"]
try:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=10)
    row = conn.execute(sql).fetchone()
    conn.close()
    print(int(row[0]) if row and row[0] is not None else 0)
except Exception:
    print(0)
' 2>/dev/null || echo 0
    elif [ "$_U6C_HAVE_SQLITE3_CLI" = "1" ]; then
      sqlite3 "file:${_scdb}?mode=ro" "$_scsql" 2>/dev/null || echo 0
    else
      echo "SQLITE_UNAVAILABLE"
    fi
  }

  # Canonical population from the manifest (single source of truth shared with
  # the ingester and embedding_health.py's coverage leg).
  _U6C_CANON=2555
  if [ -f "$_U6C_MANIFEST" ] && command -v python3 >/dev/null 2>&1; then
    _U6C_CANON="$(python3 -c 'import json,sys
try:
    print(int(json.load(open(sys.argv[1])).get("canonical_sop_count") or 2555))
except Exception:
    print(2555)' "$_U6C_MANIFEST" 2>/dev/null || echo 2555)"
  fi

  # Resolve the SAME mission-control.db every other Skill-32 script resolves,
  # via the shared resolver (honors $DASHBOARD_DB_PATH / $DATABASE_PATH first).
  _U6C_DB=""
  if command -v python3 >/dev/null 2>&1; then
    _U6C_DB="$(python3 -c '
import sys
from pathlib import Path
su = Path(sys.argv[1])
sys.path.insert(0, str(su))
try:
    from resolve_db import find_dashboard_db, is_db_found
    p = find_dashboard_db()
    print(str(p) if is_db_found(p) else "")
except Exception:
    print("")' "$SKILLS_DIR/shared-utils" 2>/dev/null || true)"
  fi

  echo ""
  echo "  Step U6c: SOP V2 library population check..."
  if [ ! -f "$_U6C_INGEST_SH" ]; then
    _U6C_SOPLIB_FAIL=1
    _U6C_SOPLIB_NOTE="ingest-sop-library.sh not found on this box (Skill 32 install is partial) — the SOP library could never be ingested"
    echo "  ✗ SOP library: ingester MISSING ($_U6C_INGEST_SH) — cannot populate the SOP database."
  elif [ -z "$_U6C_DB" ] || [ ! -f "$_U6C_DB" ]; then
    # No Command Center on this box: legitimately nothing to populate.
    echo "  — SOP library: no mission-control.db resolved on this box (Command Center not installed) — SKIP (informational, not a failure)."
  elif [ "$_U6C_HAVE_PY3_SQLITE" != "1" ] && [ "$_U6C_HAVE_SQLITE3_CLI" != "1" ]; then
    # Neither reader is available -- an honest, distinguishable FAIL, never a
    # false "0 rows". Latches like any other genuine U6c failure (see the
    # FAILS LOUD contract above) rather than guessing at a population number
    # that was never actually read.
    _U6C_SOPLIB_FAIL=1
    _U6C_SOPLIB_NOTE="cannot verify SOP library population -- neither python3's stdlib sqlite3 module nor a sqlite3 CLI binary is available on this box"
    echo "  ✗ SOP library: cannot verify population (neither python3's stdlib sqlite3 module nor a sqlite3 CLI binary is available) — refusing to guess."
  else
    _U6C_BEFORE="$(_sqlite_count "$_U6C_DB" "SELECT COUNT(*) FROM sops;")"
    echo "  → SOP library: db=$_U6C_DB  rows=$_U6C_BEFORE  canonical=$_U6C_CANON"
    if [ "${_U6C_BEFORE:-0}" -ge "${_U6C_CANON:-2555}" ] 2>/dev/null; then
      # Healthy box (e.g. an already-rolled client at 2578). Touch NOTHING.
      echo "  ✓ SOP library already at/above canonical population ($_U6C_BEFORE >= $_U6C_CANON) — no download, no write, DB untouched."
    else
      # Slug scopes client_template_vars only; the SOP rows are global, so a
      # missing slug must NOT skip the ingest (that is phase 6i's silent hole).
      _U6C_SLUG=""
      _U6C_STATE="$OC_WORKSPACE_DEFAULT/.workforce-build-state.json"
      if [ -f "$_U6C_STATE" ]; then
        _U6C_SLUG=$(jq -r '.companySlug // .clientSlug // ""' "$_U6C_STATE" 2>/dev/null || echo "")
      fi
      [ -n "$_U6C_SLUG" ] || _U6C_SLUG="default"
      echo "  → Ingesting SOP V2 library (box is under-populated: $_U6C_BEFORE < $_U6C_CANON)..."
      # DEFECT FIX (live 2026-08 Hostinger VPS finding): the previous form,
      # `_U6C_OUT="$(...)"; _U6C_RC=$?`, is a command-substitution ASSIGNMENT
      # followed by a SEPARATE statement (`;`). Under `set -euo pipefail`
      # (active at L128) a failing assignment aborts the script the instant
      # the substitution returns non-zero -- `_U6C_RC=$?` is never even
      # reached, so a genuine ingest-sop-library.sh failure killed the WHOLE
      # updater before Step U6c's own "FAILS LOUD... latches _U6C_SOPLIB_FAIL,
      # continues to the end" design (see the comment block above) ever got a
      # chance to run, and every phase after U6c (skill-38, MCP, pm2, the
      # stamp write) never executed. The `if VAR="$(...)"; then RC=0; else
      # RC=$?; fi` idiom below is set -e SAFE (the assignment is the tested
      # condition of an `if`, which `set -e` never aborts on) and is the exact
      # pattern this file already ships for the sibling U6c2 capture just
      # below and the R4 runtime-conformance verdict (~L5340).
      if _U6C_OUT="$(MISSION_CONTROL_DB="$_U6C_DB" bash "$_U6C_INGEST_SH" "$_U6C_SLUG" 2>&1)"; then
        _U6C_RC=0
      else
        _U6C_RC=$?
      fi
      printf '%s\n' "$_U6C_OUT" >> "$LOG_FILE"
      _U6C_TAIL="$(printf '%s' "$_U6C_OUT" | tail -n 3 | tr '\n' ' ')"
      if [ "$_U6C_RC" -ne 0 ]; then
        _U6C_SOPLIB_FAIL=1
        _U6C_SOPLIB_NOTE="ingest-sop-library.sh FAILED (rc=$_U6C_RC) — SOP library NOT populated (was $_U6C_BEFORE rows, canonical $_U6C_CANON). Last output: ${_U6C_TAIL}"
        echo "  ✗ SOP library ingest FAILED (rc=$_U6C_RC) — see $LOG_FILE"
      else
        _U6C_AFTER="$(_sqlite_count "$_U6C_DB" "SELECT COUNT(*) FROM sops;")"
        # Independent re-assert with the fail-CLOSED row-count gate (the same
        # one run-full-install.sh phase 6i uses). rc 0 from the ingester is not
        # accepted as proof on its own.
        _U6C_ASSERT_RC=0
        if [ -f "$_U6C_ASSERT_PY" ] && command -v python3 >/dev/null 2>&1; then
          python3 "$_U6C_ASSERT_PY" --db "$_U6C_DB" --min-total "$_U6C_CANON" --min-role-library 0 >>"$LOG_FILE" 2>&1 || _U6C_ASSERT_RC=$?
        fi
        if [ "${_U6C_AFTER:-0}" -lt "${_U6C_CANON:-2555}" ] 2>/dev/null || [ "$_U6C_ASSERT_RC" -ne 0 ]; then
          _U6C_SOPLIB_FAIL=1
          _U6C_SOPLIB_NOTE="SOP library ingest reported success but the table is STILL under-populated ($_U6C_AFTER rows < canonical $_U6C_CANON, row-count gate rc=$_U6C_ASSERT_RC) — refusing to call this update complete"
          echo "  ✗ SOP library STILL under-populated after ingest ($_U6C_AFTER < $_U6C_CANON, gate rc=$_U6C_ASSERT_RC)"
        else
          echo "  ✓ SOP library populated: $_U6C_BEFORE → $_U6C_AFTER rows (canonical $_U6C_CANON, row-count gate PASS)"
          printf '%s\n' "$_U6C_OUT" | grep -E '^\[sop-library\] (NOTE|  )' || true
        fi
      fi
    fi
  fi
  # <<< U6C-SOP-LIBRARY-END

  # ----------------------------------------------------------
  # >>> U6C2-SOP-EMBEDDINGS-BEGIN  (extracted verbatim by tests/unit/sop-embeddings-independent-gate.test.sh)
  # Step U6c2: SOP-embeddings population check (Bug D).
  #
  # WHY THIS IS SEPARATE FROM U6c ABOVE. U6c's gate is CONTENT row-count (the
  # `sops` table) vs the SOP-LIBRARY manifest's canonical_sop_count. A box
  # already at/above that threshold takes the "touch nothing" branch above
  # and ingest-sop-library.sh is NEVER INVOKED AT ALL from this updater -- so
  # the SOP-embeddings asset (a separate, free, sha256-pinned download that
  # makes ZERO embedding API calls) never reaches an already-populated box:
  # semantic SOP search stays keyword-only on that box forever. This step
  # reads its OWN signal -- `sop_embeddings` row count vs
  # SOP-EMBEDDINGS-MANIFEST.json's sop_count -- and provisions directly via
  # provision_sop_embeddings.py, independent of whatever U6c decided above.
  # provision_sop_embeddings.py carries its own idempotency gate (marker
  # table + row count vs manifest), so calling it here is safe even on the
  # under-populated path above, where U6c's own ingest already called it too.
  #
  # ADVISORY ONLY: never fails the roll, never withholds the version stamp,
  # never latches _U6C_SOPLIB_FAIL or any other stamp-gating flag. No client
  # key is ever billed -- this is a sha256-verified download + sqlite
  # ATTACH/INSERT, never an embedding API call.
  #
  # SELF-CONTAINED sqlite reader (DEFECT FIX, same live 2026-08 Hostinger VPS
  # finding as U6c above): this block is INDEPENDENT of U6c by design (see
  # test (4) below) and tests/unit/sop-embeddings-independent-gate.test.sh
  # extracts and sources it IN ISOLATION -- it must never depend on a helper
  # function U6c happens to define. python3's stdlib sqlite3 is the primary
  # path (a sqlite3 CLI is not guaranteed on every box, see U6c's comment);
  # the CLI is a fallback. Deliberately does NOT introduce a hard-fail branch
  # here (unlike U6c's gate) -- this step is advisory-only by contract, so
  # "cannot verify" degrades to the existing "under-populated" provisioning
  # attempt rather than a new failure mode.
  # ----------------------------------------------------------
  _u6c2_sqlite_count() {  # _u6c2_sqlite_count <db> <sql>
    local _u6c2scdb="$1" _u6c2scsql="$2"
    if command -v python3 >/dev/null 2>&1 && python3 -c 'import sqlite3' >/dev/null 2>&1; then
      SQLITE_COUNT_DB="$_u6c2scdb" SQLITE_COUNT_SQL="$_u6c2scsql" python3 -c '
import os, sqlite3
db = os.environ["SQLITE_COUNT_DB"]
sql = os.environ["SQLITE_COUNT_SQL"]
try:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=10)
    row = conn.execute(sql).fetchone()
    conn.close()
    print(int(row[0]) if row and row[0] is not None else 0)
except Exception:
    print(0)
' 2>/dev/null || echo 0
    elif command -v sqlite3 >/dev/null 2>&1; then
      sqlite3 "file:${_u6c2scdb}?mode=ro" "$_u6c2scsql" 2>/dev/null || echo 0
    else
      echo 0
    fi
  }
  _U6C2_EMBED_DIR="$SKILLS_DIR/shared-utils/sop-embed-once"
  [ -d "$_U6C2_EMBED_DIR" ] || _U6C2_EMBED_DIR="$EXTRACTED_DIR/shared-utils/sop-embed-once"
  _U6C2_MANIFEST="$_U6C2_EMBED_DIR/SOP-EMBEDDINGS-MANIFEST.json"
  _U6C2_PROVISION_PY="$_U6C2_EMBED_DIR/provision_sop_embeddings.py"

  echo ""
  echo "  Step U6c2: SOP-embeddings population check (independent of U6c content gate)..."
  if [ -z "$_U6C_DB" ] || [ ! -f "$_U6C_DB" ]; then
    echo "  — SOP embeddings: no mission-control.db resolved on this box — SKIP (informational, not a failure)."
  elif [ ! -f "$_U6C2_MANIFEST" ] || [ ! -f "$_U6C2_PROVISION_PY" ]; then
    echo "  — SOP embeddings: manifest or provisioner not found on this box — SKIP (informational, not a failure)."
  elif ! command -v python3 >/dev/null 2>&1; then
    echo "  — SOP embeddings: python3 MISSING — SKIP (informational, not a failure)."
  else
    _U6C2_SOP_COUNT=0
    if _U6C2_SOP_COUNT_RAW="$(python3 -c 'import json,sys
try:
    print(int(json.load(open(sys.argv[1])).get("sop_count") or 0))
except Exception:
    print(0)' "$_U6C2_MANIFEST" 2>/dev/null)"; then
      _U6C2_SOP_COUNT="$_U6C2_SOP_COUNT_RAW"
    fi
    _U6C2_EMB_TABLE="$(_u6c2_sqlite_count "$_U6C_DB" "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='sop_embeddings';")"
    _U6C2_EMB_ROWS=0
    if [ "${_U6C2_EMB_TABLE:-0}" = "1" ]; then
      _U6C2_EMB_ROWS="$(_u6c2_sqlite_count "$_U6C_DB" "SELECT COUNT(*) FROM sop_embeddings;")"
    fi
    echo "  → SOP embeddings: db=$_U6C_DB  rows=$_U6C2_EMB_ROWS  manifest sop_count=$_U6C2_SOP_COUNT"
    if [ "${_U6C2_SOP_COUNT:-0}" -le 0 ] 2>/dev/null; then
      echo "  — SOP embeddings: manifest sop_count missing/zero — SKIP (informational, no trustworthy count)."
    elif [ "${_U6C2_EMB_ROWS:-0}" -lt "${_U6C2_SOP_COUNT:-0}" ] 2>/dev/null; then
      echo "  → SOP embeddings under-populated ($_U6C2_EMB_ROWS < $_U6C2_SOP_COUNT) — provisioning shipped asset (download + sqlite ATTACH/INSERT only, ZERO embedding API calls)..."
      _U6C2_OUT=""
      if _U6C2_OUT="$(python3 "$_U6C2_PROVISION_PY" "$_U6C2_MANIFEST" "$_U6C_DB" 2>&1)"; then
        _U6C2_RC=0
      else
        _U6C2_RC=$?
      fi
      printf '%s\n' "$_U6C2_OUT" >> "$LOG_FILE"
      echo "  $(printf '%s' "$_U6C2_OUT" | tail -n 1)"
      if [ "$_U6C2_RC" -ne 0 ]; then
        echo "  ⚠ SOP-embeddings provisioning returned non-zero (rc=$_U6C2_RC) — ADVISORY, does not fail the roll or withhold the version stamp."
      fi
    else
      echo "  ✓ SOP embeddings already at/above manifest sop_count ($_U6C2_EMB_ROWS >= $_U6C2_SOP_COUNT) — SKIP, nothing to provision."
    fi
  fi
  # <<< U6C2-SOP-EMBEDDINGS-END

  # ----------------------------------------------------------
  # Step U6d: Command Center runtime configuration reconciliation.
  #
  # Mirrors U6c's update-path backstop for the two other runtime stores that
  # file sync alone cannot populate. The Command Center deliberately ships
  # config/departments.json as [] and company-config.json with the exact
  # template companyName "Your Company". Skill 32's later --update-only call
  # tries to populate departments, but both that phase and the outer caller
  # historically converted failures into WARN-only success. No update path
  # applied the build-state/ZHC identity to company-config or logo-config.
  #
  # CONTRACT:
  #   - source departments ONLY from this client's durable Skill-23 ZHC
  #     departments.json (exact build-state slug; no most-recent cross-client
  #     fallback);
  #   - source branding ONLY from .workforce-build-state.json and the matching
  #     ZHC company-config.json; never invent a company name;
  #   - replace ONLY the exact shipped companyName "Your Company", populate
  #     ONLY an empty departments array / empty logo URL, and preserve every
  #     already-correct value byte-for-byte;
  #   - independently re-assert all three files after the helper returns; a
  #     failed post-reconcile assertion, a missing python3, or a missing
  #     reconciler script withholds the version stamp through
  #     _U6D_CC_CONFIG_FAIL below (unchanged from before this fix).
  #
  # U6D-CC-RUNTIME FIX (2026-08-04 -- NOT the "DEFECT 2" GHL-MCP-runtime fix
  # elsewhere in this file; a separate fix, same pattern): the reconciler's
  # own non-zero exit used to be ONE undifferentiated "_U6D_CC_CONFIG_FAIL=1"
  # outcome regardless of WHY it failed, withholding the skills-content stamp
  # for a CC-side runtime-config
  # gap that has nothing to do with skills content — SKILL38 and the GHL MCP
  # converged perfectly on the boxes this blocked; only the stamp was
  # withheld, with no path back to green. reconcile_command_center_runtime.py
  # now distinguishes (see its own module docstring / main() contract):
  #   rc=2  UNPROVISIONED — this box's workforce interview has not completed,
  #         so no ZHC department/identity artifact exists yet. A KNOWN, VALID
  #         state: degrades to a plain advisory (_WORKFORCE_INCOMPLETE_NOTES,
  #         same bucket _D2_MIGRATE_STATUS already uses) — never touches
  #         _U6D_CC_CONFIG_FAIL, never withholds the stamp.
  #   rc=1  a genuine reconciliation failure (invalid/corrupt existing CC
  #         runtime data it correctly refuses to clobber — its own FATAL
  #         message states the exact remediation command — or an I/O error).
  #         Real, but CC-side, not skills-content: latches
  #         _U6D_CC_RUNTIME_FATAL (mirrors GHL_MCP_RUNTIME_FATAL) instead of
  #         _U6D_CC_CONFIG_FAIL, so the roll CONTINUES, the stamp still WRITES,
  #         and this run's FINAL exit code is 2 (not 0) — latch, continue,
  #         report, exit non-zero, the same pattern this file already ships
  #         for the GHL MCP runtime-conformance verdict and the dirty-Command-
  #         Center-checkout skip.
  # ----------------------------------------------------------
  _U6D_CC_CONFIG_FAIL=0
  _U6D_CC_CONFIG_NOTE=""
  _U6D_RECONCILE_PY="$SKILLS_DIR/shared-utils/reconcile_command_center_runtime.py"
  [ -f "$_U6D_RECONCILE_PY" ] || _U6D_RECONCILE_PY="$EXTRACTED_DIR/shared-utils/reconcile_command_center_runtime.py"
  _U6D_CC_DIR=""

  # Resolve an EXISTING Command Center only. No directory is created here; the
  # later D5/F10 branch owns first-time bootstrap. Explicit per-box overrides
  # win, followed by the platform's canonical path and legacy read paths.
  if [ "$OPENCLAW_PLATFORM" = "vps" ]; then
    _U6D_CC_CANDIDATES=(
      "${CC_APP_DIR:-}" "${BLACKCEO_COMMAND_CENTER_ROOT:-}"
      "/data/projects/command-center" "$HOME/projects/command-center"
      "/data/projects/blackceo-command-center"
      "$HOME/projects/blackceo-command-center"
      "$HOME/projects/mission-control" "$HOME/blackceo-command-center"
      "/opt/mission-control" "/app"
    )
  else
    _U6D_CC_CANDIDATES=(
      "${CC_APP_DIR:-}" "${BLACKCEO_COMMAND_CENTER_ROOT:-}"
      "$HOME/projects/command-center" "/data/projects/command-center"
      "$HOME/projects/blackceo-command-center"
      "/data/projects/blackceo-command-center"
      "$HOME/projects/mission-control" "$HOME/blackceo-command-center"
      "/opt/mission-control" "/app"
    )
  fi
  for _U6D_CANDIDATE in "${_U6D_CC_CANDIDATES[@]}"; do
    [ -n "$_U6D_CANDIDATE" ] || continue
    _U6D_REMOTE="$(git -C "$_U6D_CANDIDATE" remote get-url origin 2>/dev/null || echo "")"
    if [ -d "$_U6D_CANDIDATE/config" ] && [ -d "$_U6D_CANDIDATE/.git" ] && \
       [ -f "$_U6D_CANDIDATE/package.json" ] && \
       printf '%s' "$_U6D_REMOTE" | grep -q 'blackceo-command-center'; then
      _U6D_CC_DIR="$_U6D_CANDIDATE"
      break
    fi
  done
  unset _U6D_CANDIDATE _U6D_CC_CANDIDATES _U6D_REMOTE

  echo ""
  echo "  Step U6d: Command Center departments + branding population check..."
  if [ -z "$_U6D_CC_DIR" ]; then
    echo "  — Command Center runtime config: no installed Command Center checkout — SKIP (informational)."
  elif ! command -v python3 >/dev/null 2>&1; then
    _U6D_CC_CONFIG_FAIL=1
    _U6D_CC_CONFIG_NOTE="python3 is unavailable — departments/branding could not be reconciled or verified"
    echo "  ✗ Command Center runtime config: python3 MISSING — cannot populate or verify."
  elif [ ! -f "$_U6D_RECONCILE_PY" ]; then
    _U6D_CC_CONFIG_FAIL=1
    _U6D_CC_CONFIG_NOTE="reconcile_command_center_runtime.py is missing — the update cannot populate departments/branding"
    echo "  ✗ Command Center runtime config: reconciler MISSING ($_U6D_RECONCILE_PY)."
  else
    _U6D_OUT=""
    _U6D_RC=0
    if _U6D_OUT="$(python3 "$_U6D_RECONCILE_PY" \
        --workspace "$OC_WORKSPACE_DEFAULT" \
        --command-center-dir "$_U6D_CC_DIR" 2>&1)"; then
      printf '%s\n' "$_U6D_OUT" >> "$LOG_FILE"
    else
      _U6D_RC=$?
      printf '%s\n' "$_U6D_OUT" >> "$LOG_FILE"
    fi
    if [ "$_U6D_RC" -eq 2 ]; then
      # UNPROVISIONED (case a): a KNOWN, VALID state -- this box's workforce
      # interview has not completed, so there is no legitimate ZHC artifact
      # to source departments/identity from yet. Route to the SAME advisory
      # bucket _D2_MIGRATE_STATUS already uses below, worded the same
      # interview-completion-aware way (never implying an interview is
      # unfinished when the box's own state records it complete). Does NOT
      # touch _U6D_CC_CONFIG_FAIL and does NOT withhold the stamp.
      _U6D_TAIL="$(printf '%s' "$_U6D_OUT" | tail -n 3 | tr '\n' ' ')"
      _U6D_IV_STATE_FILE="$OC_WORKSPACE_DEFAULT/.workforce-build-state.json"
      _U6D_IV_DONE="$(jq -r '.interviewComplete // false' "$_U6D_IV_STATE_FILE" 2>/dev/null || echo false)"
      if [ "$_U6D_IV_DONE" = "true" ]; then
        _WORKFORCE_INCOMPLETE_NOTES="${_WORKFORCE_INCOMPLETE_NOTES}  - Command Center runtime config (U6d, reconcile_command_center_runtime.py): interview COMPLETE (respected) — no ZHC department/identity artifact resolved yet for this client; advisory only, does NOT withhold the stamp — ${_U6D_TAIL}\n"
      else
        _WORKFORCE_INCOMPLETE_NOTES="${_WORKFORCE_INCOMPLETE_NOTES}  - Command Center runtime config (U6d, reconcile_command_center_runtime.py): workforce interview not yet complete for this box — dashboard departments/branding stay unpopulated until it is; advisory only, does NOT withhold the stamp — ${_U6D_TAIL}\n"
      fi
      echo "  ⚠ Command Center runtime config: box not yet provisioned (workforce interview incomplete) — ADVISORY, NOT blocking the version stamp."
    elif [ "$_U6D_RC" -ne 0 ]; then
      # Genuine reconciliation failure (case b): CC-side runtime-config data
      # problem, not skills content. Latch the FINAL-verdict flag (mirrors
      # GHL_MCP_RUNTIME_FATAL) instead of the stamp-gating _U6D_CC_CONFIG_FAIL
      # -- the roll continues and the stamp still writes; this run's exit
      # code becomes 2 at the very end (see the U6D-CC-RUNTIME final verdict block).
      _U6D_CC_RUNTIME_FATAL="yes"
      _U6D_TAIL="$(printf '%s' "$_U6D_OUT" | tail -n 6 | tr '\n' ' ')"
      _U6D_CC_RUNTIME_DETAIL="reconcile_command_center_runtime.py FAILED (rc=$_U6D_RC): ${_U6D_TAIL}"
      echo "  ✗ Command Center departments/branding reconciliation FAILED (rc=$_U6D_RC) — see $LOG_FILE"
      echo "    (skills content stays current and the version stamp still writes; this run will exit 2 — see the final summary for the exact remediation)"
    elif ! python3 -c 'import json,sys
cc=sys.argv[1]
deps=json.load(open(cc+"/config/departments.json"))
company=json.load(open(cc+"/config/company-config.json"))
# CONTENT-integrity assertions ONLY: departments must be populated and the
# exact "Your Company" placeholder must be gone. The logo is intentionally NOT
# asserted here — an empty logoUrl is a BRANDING gap, not a content failure,
# and must never withhold the version stamp (the "optional step aborts the
# updater before the stamp" bug class). Logo is checked advisory-only below.
assert isinstance(deps,list) and len(deps)>0
assert company.get("companyName") != "Your Company"' \
        "$_U6D_CC_DIR" >>"$LOG_FILE" 2>&1; then
      _U6D_CC_CONFIG_FAIL=1
      _U6D_CC_CONFIG_NOTE="reconciler returned success but independent assertion found empty departments or the exact placeholder companyName"
      echo "  ✗ Command Center runtime config STILL incomplete after reconciliation — refusing update success."
    elif python3 -c 'import json,sys
cc=sys.argv[1]
logo=json.load(open(cc+"/public/logo-config.json"))
sys.exit(0 if (isinstance(logo.get("logoUrl"),str) and logo["logoUrl"].strip()) else 1)' \
        "$_U6D_CC_DIR" >>"$LOG_FILE" 2>&1; then
      echo "  ✓ Command Center runtime config populated and verified (departments non-empty; branding non-placeholder; logo present)."
    else
      echo "  ⚠ Command Center runtime config verified (departments non-empty; branding non-placeholder); logoUrl is empty — ADVISORY branding gap, NOT blocking the version stamp."
    fi
  fi

  # ----------------------------------------------------------
  # v10.15.47: WIRING PHASE -- per-skill executed steps (not prose).
  # For every installed skill folder, this phase:
  #   1. Runs the skill's own installer (wire.sh > install.sh > setup-*.sh) if present, idempotent.
  #   2. Idempotently merges CORE_UPDATES.md into workspace AGENTS/TOOLS/MEMORY/SOUL files.
  #   3. Installs OS prereqs (imagemagick/ffmpeg) via brew (Mac) idempotently.
  #   4. Wires skill 36's GHL MCP under nested mcp.servers via `openclaw mcp set`.
  #
  # State guard: each skill writes a sentinel file $SKILLS_DIR/<skill>/.wired-<version>
  # so the loop is safe to re-run -- it skips already-wired skills.
  #
  # Scope: additive only. Never edits IDENTITY.md, never rebuilds workforce,
  # never clobbers existing AGENTS.md sections -- only appends new ones.
  # ----------------------------------------------------------

  # Resolve workspace directory (2026.x-aware; mirrors write_update_pending_flag).
  # v14.3.15 2026.x agent-dir fix: the old heuristic checked $HOME/clawd first — on VPS
  # boxes that still carry a legacy /data/clawd/ (or symlink at $HOME/clawd) the
  # sentinels and core-update blocks were written to that dead path while the
  # running agent read from the 2026.x agent dir, not the legacy workspace. The gate
  # then reported core-sentinel-missing even when the wiring ran cleanly.
  # FIX: use obs_resolve_workspace (which honours openclaw.json agents[].workspace)
  # as the primary resolver.  Then ALSO detect the active 2026.x agent dir and
  # dual-write sentinels there so both the legacy-workspace path AND the agent-dir
  # path are covered — whichever path the running agent reads from will see the
  # sentinel.
  #
  # v21.3.1: the "legacy heuristic" fallback that used to live here was
  #     WIRE_WORKSPACE_DIR="$HOME/clawd"
  #     [ ! -d "$WIRE_WORKSPACE_DIR" ] && WIRE_WORKSPACE_DIR="$HOME/.openclaw/workspace"
  # -- a SILENT guess, and a guess that DISAGREED with the equally silent guess in
  # write_update_pending_flag ($HOME/.openclaw/workspace). So the same run could
  # write core-update blocks into one AGENTS.md and the UPDATE PENDING flag into a
  # DIFFERENT one, purely because scripts/onboarding-state.sh is sourced
  # CONDITIONALLY. "A directory exists" is not evidence that it is the workspace.
  # Now: the one announced resolver, and an unresolvable workspace STOPS the run
  # before a single core file is touched.
  WIRE_WORKSPACE_DIR=""
  if ! oc_resolve_workspace_announced "core-update wiring target (AGENTS/TOOLS/MEMORY/SOUL/IDENTITY/USER)"; then
    echo "  ✗ Refusing to wire CORE_UPDATES -- workspace unresolved (see above). No core file was touched." >&2
    exit 1
  fi
  WIRE_WORKSPACE_DIR="$OC_WS_RESOLVED"
  mkdir -p "$WIRE_WORKSPACE_DIR"

  # Detect the active 2026.x agent dir for dual-write.
  # On VPS the agent reads from /data/.openclaw/agents/<name>/AGENTS.md;
  # on Mac from $HOME/.openclaw/agents/<name>/AGENTS.md.  Prefer /data prefix.
  _OC_AGENTS_ROOT="$HOME/.openclaw/agents"
  [ -d "/data/.openclaw/agents" ] && _OC_AGENTS_ROOT="/data/.openclaw/agents"
  WIRE_AGENT_DIR=""
  if [ -d "$_OC_AGENTS_ROOT/main" ]; then
    WIRE_AGENT_DIR="$_OC_AGENTS_ROOT/main"
  else
    for _oa in "$_OC_AGENTS_ROOT"/*/; do
      [ -d "${_oa%/}" ] && { WIRE_AGENT_DIR="${_oa%/}"; break; }
    done
    unset _oa
  fi
  unset _OC_AGENTS_ROOT

  # Brew path (Mac only; VPS branch kept out, VPS uses update-skills-vps.sh)
  BREW_CMD="$(command -v brew 2>/dev/null || echo '')"

  # ---- Helper: idempotent CORE_UPDATES.md merger (v12.3.11 format-robust) ----
  # Recognises ALL 14 header conventions found in the repo (em-dash, bracket h2/h3,
  # bold-bracket, plain h3, Add-to, (append), Addition, Update, bare filename h2).
  # Adds IDENTITY and USER to target_map. Wraps appended blocks in BEGIN/END markers
  # for future in-place updates. Stamps sentinel even when 0 mergeable sections found.
  # Emits UNRECOGNIZED HEADER warnings; exits non-zero under CORE_UPDATES_STRICT=1.
  wire_core_updates() {
    local SKILL_FOLDER="$1"   # e.g. "36-ghl-mcp-setup"
    local CU_FILE="$SKILLS_DIR/$SKILL_FOLDER/CORE_UPDATES.md"
    [ -f "$CU_FILE" ] || return 0

    # Map section headers to workspace target files
    local AGENTS_FILE="$WIRE_WORKSPACE_DIR/AGENTS.md"
    local TOOLS_FILE="$WIRE_WORKSPACE_DIR/TOOLS.md"
    local MEMORY_FILE="$WIRE_WORKSPACE_DIR/MEMORY.md"
    local SOUL_FILE="$WIRE_WORKSPACE_DIR/SOUL.md"
    local IDENTITY_FILE="$WIRE_WORKSPACE_DIR/IDENTITY.md"
    local USER_FILE="$WIRE_WORKSPACE_DIR/USER.md"
    touch "$AGENTS_FILE" "$TOOLS_FILE" "$MEMORY_FILE" "$SOUL_FILE" \
          "$IDENTITY_FILE" "$USER_FILE" 2>/dev/null || true

    # Sentinel: skip if this skill's core updates are already merged.
    # v14.3.15: also check the 2026.x agent dir AGENTS.md so a box that was
    # previously wired via the agent-dir path is not re-wired into the workspace.
    local SENTINEL="<!-- skill:${SKILL_FOLDER}:core-update-applied -->"
    if grep -qF "$SENTINEL" "$AGENTS_FILE" 2>/dev/null || \
       grep -qF "$SENTINEL" "$TOOLS_FILE" 2>/dev/null || \
       grep -qF "$SENTINEL" "$MEMORY_FILE" 2>/dev/null || \
       grep -qF "$SENTINEL" "$SOUL_FILE" 2>/dev/null || \
       grep -qF "$SENTINEL" "$IDENTITY_FILE" 2>/dev/null || \
       grep -qF "$SENTINEL" "$USER_FILE" 2>/dev/null || \
       ([ -n "$WIRE_AGENT_DIR" ] && grep -qF "$SENTINEL" "$WIRE_AGENT_DIR/AGENTS.md" 2>/dev/null); then
      return 0
    fi

    # Parse CORE_UPDATES.md with the format-robust normalising parser.
    # Recognises ALL header conventions across all 14 formats in the repo:
    #   FORMAT 1/3: ## X.md - UPDATE REQUIRED  (ASCII / en-dash h2)
    #   FORMAT 2:   ## X.md — UPDATE REQUIRED  (em-dash h2)
    #   FORMAT 4:   ## [ADD TO X.md]           (bracket h2, optional trailing note)
    #   FORMAT 5:   ### [ADD TO X.md]          (bracket h3)
    #   FORMAT 6:   **[ADD TO X.md]**          (bold-bracket inline)
    #   FORMAT 7:   ### X.md                   (plain h3, under Suggested snippets)
    #   FORMAT 8/9: ## Add to X.md             (verb-first h2)
    #   FORMAT 10:  ## X.md (append)           (paren suffix h2)
    #   FORMAT 11:  ## X.md append             (bare suffix word h2)
    #   FORMAT 12:  ## X.md Addition/Update    (mixed suffix h2)
    #   FORMAT 13:  ## X.md                    (bare filename h2, where:+fenced)
    # python3 is a hard dependency on Mac (already noted in the existing comment).
    # Resolve THIS box's master-files root so `[MASTER_FILES_FOLDER]`-style
    # template variables in a CORE_UPDATES.md payload are FILLED before the block
    # is written. An unfilled variable shipped to a live box as the literal text
    # `[MASTER_FILES_FOLDER]/64-agnes-video/agnes-video-full.md` — a pointer to a
    # path that exists nowhere. Same platform rule the skill installers use.
    local CU_MASTER_FILES_DIR="${OPENCLAW_MASTER_FILES_DIR:-}"
    if [ -z "$CU_MASTER_FILES_DIR" ]; then
      if [ -f /data/.openclaw/openclaw.json ]; then
        CU_MASTER_FILES_DIR="/data/.openclaw/master-files"
      else
        CU_MASTER_FILES_DIR="$HOME/Downloads/openclaw-master-files"
      fi
    fi

    python3 - \
        "$CU_FILE" "$AGENTS_FILE" "$TOOLS_FILE" "$MEMORY_FILE" \
        "$SOUL_FILE" "$IDENTITY_FILE" "$USER_FILE" \
        "$SENTINEL" "$SKILL_FOLDER" \
        "${CORE_UPDATES_STRICT:-0}" "$CU_MASTER_FILES_DIR" <<'PYEOF'
import sys, re, os

(cu_path, agents_f, tools_f, memory_f, soul_f,
 identity_f, user_f, sentinel, skill_folder, strict_mode,
 master_files_dir) = sys.argv[1:]
strict = (strict_mode == "1")

target_map = {
    'agents':   agents_f,
    'tools':    tools_f,
    'memory':   memory_f,
    'soul':     soul_f,
    'identity': identity_f,
    'user':     user_f,
}

try:
    text = open(cu_path, encoding='utf-8', errors='replace').read()
except Exception:
    sys.exit(0)

# ---------------------------------------------------------------------------
# HEADER RECOGNITION
# A "core section header" is a line that:
#   (a) starts with ## or ### (h2/h3), OR is a **[ADD TO X.md]** bold-bracket,
#   (b) AND contains exactly one of the six target filenames.
#
# The regex captures:
#   group(hashes)  — ## or ### (or None for bold-bracket)
#   group(target)  — AGENTS|TOOLS|MEMORY|SOUL|IDENTITY|USER (case-insensitive)
#   group(rest)    — remainder of the line after ".md" (for directive parsing)
#
# We build a single pattern that handles all known formats.
# The "no update" / "no change" signals come from the full line text (rest).
# ---------------------------------------------------------------------------

TARGETS = r'(AGENTS|TOOLS|MEMORY|SOUL|IDENTITY|USER)'

# Structural headers that must NOT be treated as target sections even though
# they contain one of the target names (e.g. "## Relevant (update allowed)")
STRUCTURAL_PREFIXES = (
    'rule', 'relevant', 'optional', 'non-relevant', 'what not',
    'where to', 'purpose', 'quick reference', 'core .md', 'what to add',
    'suggested snippets', 'verification', 'placement decision',
    'credential storage', 'add this', 'paste these', 'check if running',
)

def is_structural(line_text):
    """Return True if the heading looks like a structural/meta header."""
    # Strip leading #, *, [, whitespace
    stripped = re.sub(r'^[#*\[\s]+', '', line_text).strip().lower()
    return any(stripped.startswith(p) for p in STRUCTURAL_PREFIXES)

def classify_directive(rest_text):
    """
    Given the text AFTER '<TARGET>.md' on a header line, decide:
      'skip'   — this section is a no-op (no-update / no-change / do-not-edit)
      'merge'  — real content section
    """
    t = rest_text.lower()
    # Explicit skip signals
    skip_signals = ('no update', 'no change', 'do not edit', 'not relevant',
                    'no update needed', 'no update required')
    for sig in skip_signals:
        if sig in t:
            return 'skip'
    return 'merge'

# Build the master header recognition regex.
# It matches lines in these forms:
#   1. ^(#{2,3})\s+  ... TARGET\.md ...   (h2/h3 with target anywhere on line)
#   2. ^\*\*\[ADD TO TARGET\.md\]\*\*     (bold-bracket)
#
# We use MULTILINE so ^ matches start-of-line.
# We capture the target name and the full line text so we can classify it.

HEADER_PATTERN = re.compile(
    r'^(?:'
    # h2/h3: optional leading [, optional ADD/APPEND TO, target, optional rest
    r'(#{2,3})\s+(?:\[?(?:ADD\s+TO|APPEND\s+TO|ADD|APPEND|UPDATE)?\s*)?'
    + TARGETS + r'\.md(.*?)'
    r'|'
    # bold-bracket: **[ADD TO TARGET.md]** (optional trailing text)
    r'\*\*\[(?:ADD\s+TO|APPEND\s+TO)?\s*' + TARGETS + r'\.md\]?\*\*(.*?)'
    r')$',
    re.IGNORECASE | re.MULTILINE
)

def extract_target_and_directive(m):
    """
    From a regex match, return (target_key, directive) where
      target_key  — lowercase 'agents'|'tools'|'memory'|'soul'|'identity'|'user'
      directive   — 'merge' or 'skip'
    """
    # Group layout: (hashes, target_h2, rest_h2, target_bold, rest_bold)
    # group(1)=hashes, group(2)=target for h2/h3, group(3)=rest for h2/h3
    # group(4)=target for bold, group(5)=rest for bold
    target = (m.group(2) or m.group(4) or '').lower()
    rest   = (m.group(3) or m.group(5) or '')
    directive = classify_directive(rest)
    return target, directive

# ---------------------------------------------------------------------------
# STRUCTURAL HEADER DETECTION (for section boundary purposes)
# Any h2 that does NOT match a target name stops the current section.
# ---------------------------------------------------------------------------
ANY_H2_RE = re.compile(r'^#{1,3}\s+\S', re.MULTILINE)

# ---------------------------------------------------------------------------
# SCAN: collect all section matches with their positions
# ---------------------------------------------------------------------------
all_matches = list(HEADER_PATTERN.finditer(text))

# Filter out structural headers
real_sections = []
for m in all_matches:
    full_line = m.group(0)
    if is_structural(full_line):
        continue
    target, directive = extract_target_and_directive(m)
    if not target or target not in target_map:
        continue
    real_sections.append((m, target, directive))

# ---------------------------------------------------------------------------
# UNRECOGNIZED HEADER detection
# Any line that contains "TARGET.md" in a heading/bold context but was NOT
# captured by our regex is potentially an unrecognized format.
# ---------------------------------------------------------------------------
LOOSE_RE = re.compile(
    r'^(?:#{2,3}|\*\*\[)[^\n]*' + TARGETS + r'\.md[^\n]*$',
    re.IGNORECASE | re.MULTILINE
)
all_loose = set(m.group(0).strip() for m in LOOSE_RE.finditer(text))
recognized_lines = set(m[0].group(0).strip() for m in real_sections)
# Also count structural headers as recognized (they are intentionally not merged)
structural_lines = set()
for m in all_matches:
    if is_structural(m.group(0)):
        structural_lines.add(m.group(0).strip())

unrecognized = []
for line in all_loose:
    if line not in recognized_lines and line not in structural_lines:
        unrecognized.append(line)

if unrecognized:
    for u in unrecognized:
        print(f'[CORE_UPDATES] UNRECOGNIZED HEADER in {skill_folder}: {u}', file=sys.stderr)
    if strict:
        sys.exit(1)

# ---------------------------------------------------------------------------
# MERGE PHASE
# For each real non-skip section, extract content up to the next section header
# (of any kind) and append it wrapped in BEGIN/END markers.
# ---------------------------------------------------------------------------

# Fenced-code spans: headings INSIDE a ``` ... ``` fence are payload text, not
# section boundaries. CORE_UPDATES.md puts the real "exact text to add" inside a
# fenced block whose FIRST line is often itself an h2 (e.g. the skill-22 AGENTS.md
# payload starts with "## Book-to-Persona Skill (Installed)"). Without this guard
# the boundary scan cut the section at that in-fence heading, so the actual
# payload (the Persona Reflex / Task-Mode body) never merged while the sentinel
# was still stamped — a marker with no body. Excluding in-fence heading positions
# lets the WHOLE fenced payload transfer.
def _fenced_spans(s):
    spans = []
    start = None
    for fm in re.finditer(r'^[ \t]*```', s, re.MULTILINE):
        if start is None:
            start = fm.start()
        else:
            spans.append((start, fm.end()))
            start = None
    return spans

_FENCES = _fenced_spans(text)

def _in_fence(pos):
    return any(a <= pos < b for (a, b) in _FENCES)

# Build a flat list of all heading positions (for section boundary detection),
# skipping any heading that lives inside a fenced code block (payload, not boundary).
all_heading_positions = sorted(
    [m.start() for m in ANY_H2_RE.finditer(text) if not _in_fence(m.start())] +
    [m.start() for m in re.finditer(r'^\*\*\[', text, re.MULTILINE) if not _in_fence(m.start())]
)

def next_section_start(pos):
    """Return start of next heading at or after pos, or len(text)."""
    for hp in all_heading_positions:
        if hp > pos:
            return hp
    return len(text)

merged_count = 0

# ---------------------------------------------------------------------------
# EXECUTE THE INSTRUCTION — never paste it. (no-paste rule)
#
# THE DEFECT THIS CLOSES. The merger copied the section body verbatim, and almost
# every CORE_UPDATES.md writes its payload as an INSTRUCTION wrapping the payload:
#
#     ## AGENTS.md - UPDATE REQUIRED
#     Add:
#     ```
#     ## Agnes Image 2.1 Flash
#     - ...
#     ```
#     ---
#
# So what landed in every box's AGENTS.md was the word "Add:", a markdown code
# fence, the payload, the closing fence and a horizontal rule — the recipe pasted
# instead of executed. Proven live: skills 63 and 64 both shipped that shape to the
# fleet, and skill 64's pointer additionally arrived as the UNFILLED template
# variable `[MASTER_FILES_FOLDER]/64-agnes-video/agnes-video-full.md`.
#
# clean_block() removes exactly three things and NOTHING else:
#   1. a leading imperative directive line ("Add:", "Append:", "Add this:", …)
#   2. a code fence that WRAPS THE WHOLE remaining block — opening fence on the
#      first line, closing fence on the last, and an EVEN number of fence lines
#      between them (so any fenced example inside the payload is itself balanced
#      and survives intact). An ODD inner count means the first line is not a
#      wrapper at all, and the block is then left exactly as written.
#   3. a trailing horizontal rule left over from the doc's section separator
# then fills the master-files template variables with this box's resolved path.
# Every other byte of the payload is preserved exactly.
# ---------------------------------------------------------------------------
DIRECTIVE_LINE_RE = re.compile(
    r'^\s*(?:add|append|add this|add the following|append the following|'
    r'paste|paste this|insert|insert this)\b[^\n:]{0,40}:\s*$',
    re.IGNORECASE,
)
FENCE_LINE_RE = re.compile(r'^\s*```')
MASTER_FILES_TOKENS = (
    '[MASTER_FILES_FOLDER]', '[MASTER-FILES-FOLDER]', '{{MASTER_FILES_FOLDER}}',
    '<MASTER_FILES_FOLDER>', '[MASTER_FILES_DIR]', '{{MASTER_FILES_DIR}}',
)


def clean_block(raw):
    lines = raw.split('\n')

    # 1. leading directive line(s) + the blank lines that follow them
    while lines and (not lines[0].strip() or DIRECTIVE_LINE_RE.match(lines[0])):
        if lines[0].strip() and not DIRECTIVE_LINE_RE.match(lines[0]):
            break
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()

    # 3. trailing horizontal rule (done before the fence check so a rule sitting
    #    AFTER the closing fence cannot hide it)
    while lines and lines[-1].strip() in ('---', '***', '___'):
        lines.pop()
        while lines and not lines[-1].strip():
            lines.pop()

    # 2. a fence that wraps the WHOLE block
    if len(lines) >= 2 and FENCE_LINE_RE.match(lines[0]) and FENCE_LINE_RE.match(lines[-1]):
        inner = lines[1:-1]
        if sum(1 for ln in inner if FENCE_LINE_RE.match(ln)) % 2 == 0:
            lines = inner
            while lines and not lines[0].strip():
                lines.pop(0)
            while lines and not lines[-1].strip():
                lines.pop()

    out = '\n'.join(lines).strip()
    if master_files_dir:
        for tok in MASTER_FILES_TOKENS:
            out = out.replace(tok, master_files_dir)
    return out


for (m, target, directive) in real_sections:
    if directive == 'skip':
        continue
    target_file = target_map[target]

    # Extract block: from end of matched header line to next heading
    content_start = m.end()
    content_end = next_section_start(m.start() + 1)
    block = clean_block(text[content_start:content_end].strip())

    if not block:
        continue

    # Check for BEGIN/END idempotency marker in target file
    begin_marker = f'<!-- BEGIN skill:{skill_folder}:{target} -->'
    end_marker   = f'<!-- END skill:{skill_folder}:{target} -->'

    try:
        existing = open(target_file, encoding='utf-8', errors='replace').read()
    except Exception:
        existing = ''

    if begin_marker in existing:
        # Already merged for this target — skip
        continue

    # SELF-HEAL an orphan END (END present, BEGIN absent).
    #
    # The idempotency guard above only looks for the BEGIN marker, so a block
    # whose BEGIN was lost — an interrupted write, an external edit, a
    # summariser — becomes invisible to it: the END is never detected, never
    # repaired, and stays orphaned forever. Measured 2026-07-31: three of four
    # sampled fleet boxes carried the SAME orphan
    # (`16-summarize-youtube:agents  BEGIN=0 END=1`).
    #
    # Consequences: every BEGIN/END pair-balance check on that box fails, and
    # scripts/dedup-agents-md.py deliberately refuses to worsen wiring, so the
    # box's duplicate blocks never get cleaned either. One orphan line blocks
    # the whole self-heal path.
    #
    # Narrowly scoped on purpose: only the end_marker for THIS skill_folder and
    # THIS target, and only when its BEGIN is genuinely absent. A matched pair is
    # never touched. Failure here is non-fatal — we fall through and append a
    # clean pair regardless, because a duplicate marker is recoverable while a
    # crashed updater is not.
    if end_marker in existing:
        try:
            repaired = existing.replace(end_marker + '\n', '').replace(end_marker, '')
            with open(target_file, 'w', encoding='utf-8') as fh:
                fh.write(repaired)
            print(
                f'[CORE_UPDATES] repaired orphan END marker (no matching BEGIN) '
                f'for skill:{skill_folder}:{target} in {os.path.basename(target_file)}',
                file=sys.stderr,
            )
        except Exception as exc:
            print(
                f'[CORE_UPDATES] WARN: could not repair orphan END for '
                f'skill:{skill_folder}:{target} ({exc}) — appending a fresh pair anyway',
                file=sys.stderr,
            )

    # Append wrapped block
    with open(target_file, 'a', encoding='utf-8') as fh:
        fh.write(f'\n\n{begin_marker}\n')
        fh.write(block)
        fh.write(f'\n{end_marker}\n')

    merged_count += 1

# ---------------------------------------------------------------------------
# WARN on zero-section skills (possible format regression, but not an error)
# ---------------------------------------------------------------------------
mergeable_sections = [(m, t, d) for (m, t, d) in real_sections if d != 'skip']
if not mergeable_sections:
    print(f'[CORE_UPDATES] WARN: {skill_folder} produced no mergeable section', file=sys.stderr)

# ---------------------------------------------------------------------------
# SENTINEL: always stamp to AGENTS.md so install.sh VERIFICATION GATE passes.
# This is unconditional — even for genuine no-op skills (all-skip sections).
# ---------------------------------------------------------------------------
try:
    existing = open(agents_f, encoding='utf-8', errors='replace').read()
except Exception:
    existing = ''
if sentinel not in existing:
    with open(agents_f, 'a', encoding='utf-8') as fh:
        fh.write('\n' + sentinel + '\n')

PYEOF
    # v14.3.15 dual-write: stamp sentinel to the 2026.x agent dir AGENTS.md too.
    # On VPS boxes that have a legacy $HOME/clawd/ (or /data/clawd/), the Python
    # block above writes to WIRE_WORKSPACE_DIR/AGENTS.md.  If the running agent
    # reads from $HOME/.openclaw/agents/<name>/AGENTS.md instead, the gate sees
    # core-sentinel-missing.  Writing to BOTH paths is safe (idempotent grep check
    # guards against duplicates) and ensures the sentinel is visible regardless of
    # which read-path the agent uses.
    if [ -n "$WIRE_AGENT_DIR" ] && \
       [ "$WIRE_AGENT_DIR/AGENTS.md" != "$AGENTS_FILE" ]; then
      touch "$WIRE_AGENT_DIR/AGENTS.md" 2>/dev/null || true
      if ! grep -qF "$SENTINEL" "$WIRE_AGENT_DIR/AGENTS.md" 2>/dev/null; then
        printf '\n%s\n' "$SENTINEL" >> "$WIRE_AGENT_DIR/AGENTS.md" 2>/dev/null || true
      fi
    fi
    echo "    Wired CORE_UPDATES.md: $SKILL_FOLDER"
  }

  # ---- Helper: install OS prereqs for a skill (idempotent) ----
  wire_prereqs() {
    local SKILL_FOLDER="$1"
    # Skills 25/26/27/28 need ffmpeg + imagemagick; 16 needs nothing extra.
    # We detect by folder prefix; adding explicit cases is safer than parsing INSTALL.md.
    local NEED_FFMPEG=0
    local NEED_IMAGEMAGICK=0
    case "$SKILL_FOLDER" in
      25-video-creator|26-caption-creator|27-video-editor|28-cinematic-forge)
        NEED_FFMPEG=1; NEED_IMAGEMAGICK=1 ;;
    esac

    [ "$NEED_FFMPEG" -eq 0 ] && [ "$NEED_IMAGEMAGICK" -eq 0 ] && return 0
    [ -z "$BREW_CMD" ] && { echo "    (brew not found -- skipping prereqs for $SKILL_FOLDER)"; return 0; }

    if [ "$NEED_FFMPEG" -eq 1 ]; then
      if command -v ffmpeg >/dev/null 2>&1; then
        echo "    ffmpeg: already installed"
      else
        echo "    Installing ffmpeg via brew..."
        "$BREW_CMD" install ffmpeg >> "$LOG_FILE" 2>&1 && echo "    ffmpeg: installed" || echo "    ffmpeg: install failed (see $LOG_FILE)"
      fi
    fi

    if [ "$NEED_IMAGEMAGICK" -eq 1 ]; then
      if command -v convert >/dev/null 2>&1 || command -v magick >/dev/null 2>&1; then
        echo "    imagemagick: already installed"
      else
        echo "    Installing imagemagick via brew..."
        "$BREW_CMD" install imagemagick >> "$LOG_FILE" 2>&1 && echo "    imagemagick: installed" || echo "    imagemagick: install failed (see $LOG_FILE)"
      fi
    fi
  }

  # ---- Helper: wire skill 36 GHL MCP under nested mcp.servers (idempotent) ----
  wire_ghl_mcp() {
    local SKILL_FOLDER="$1"
    [ "$SKILL_FOLDER" = "36-ghl-mcp-setup" ] || return 0

    if ! command -v openclaw >/dev/null 2>&1; then
      echo "    (openclaw CLI not found -- skipping GHL MCP registration)"
      return 0
    fi

    # v21.5.0: the old "already registered -> return 0" short-circuit keyed on
    # ghl-mcp OR ghl-community-mcp being present in mcp.servers. Tier 1 (ghl-mcp)
    # is registered on virtually every box, so this function returned BEFORE
    # running the autostart -- meaning an update pass never started, rebuilt or
    # repaired a down/deaf Tier 2 server. The registration state is now irrelevant
    # to whether the server gets wired, so the short-circuit is gone.
    local OCJSON="$HOME/.openclaw/openclaw.json"

    # Read GHL MCP URL from skill's INSTALL.md or default to the community server
    local GHL_MCP_PORT=8765
    local GHL_MCP_INSTALL_MD="$SKILLS_DIR/36-ghl-mcp-setup/INSTALL.md"
    if [ -f "$GHL_MCP_INSTALL_MD" ]; then
      local DETECTED_PORT
      DETECTED_PORT=$(grep -oE 'localhost:[0-9]+' "$GHL_MCP_INSTALL_MD" 2>/dev/null | head -1 | cut -d: -f2 || true)
      [ -n "$DETECTED_PORT" ] && GHL_MCP_PORT="$DETECTED_PORT"
    fi

    # v21.5.0: DO NOT register ghl-community-mcp under mcp.servers.
    # Skill 36 v1.1.0 made Tier 2 ON-DEMAND CURL: its tool schemas would otherwise
    # ride in EVERY session's init whether or not GHL is touched, and a down/deaf
    # server makes every agent init pay the full connectionTimeoutMs (that is the
    # 30s-per-init stall seen fleet-wide on 2026-08-01/02). The skill's own QC
    # (qc-ghl-mcp-setup.sh Section D) ASSERTS it is NOT registered and 36/wire.sh
    # migration M2 REMOVES it -- while this function put it straight back. The
    # flip-flop is over: we only publish the canonical URL that the on-demand curl
    # path reads, and remove a legacy registration if one is present.
    openclaw config set env.vars.GHL_COMMUNITY_MCP_URL "http://localhost:${GHL_MCP_PORT}" >> "$LOG_FILE" 2>&1 || true
    if openclaw mcp list 2>/dev/null | grep -q 'ghl-community-mcp'; then
      # B2: `openclaw mcp remove` IS NOT A COMMAND on OpenClaw 2026.7.1-2 — it
      # exits 1 with "Too many arguments for this command." The verb is `unset`.
      # This line used `remove`, swallowed by `|| true`, so a roll NEVER
      # de-registered Tier 2 on any box and ghl-mcp-assert-runtime.sh check 10
      # could never pass. Try the real verb, keep `remove` for an older CLI, and
      # re-read rather than assuming the write stuck.
      echo "    GHL MCP: de-registering legacy ghl-community-mcp (Tier 2 is on-demand curl)"
      if openclaw mcp unset ghl-community-mcp >> "$LOG_FILE" 2>&1 \
         || openclaw mcp remove ghl-community-mcp >> "$LOG_FILE" 2>&1; then
        if openclaw mcp list 2>/dev/null | grep -q 'ghl-community-mcp'; then
          echo "    ⚠ GHL MCP: de-registration ran but ghl-community-mcp is STILL listed — the gateway may have rewritten openclaw.json from memory. Will retry next roll."
        else
          echo "    ✓ GHL MCP: Tier 2 de-registered and verified absent from mcp.servers"
        fi
      else
        echo "    ⚠ GHL MCP: neither 'openclaw mcp unset' nor 'openclaw mcp remove' was accepted by this CLI — Tier 2 is STILL registered and every agent init keeps paying its connection cost. Check 'openclaw mcp --help'." >&2
      fi
    else
      echo "    GHL MCP: Tier 2 correctly unregistered (on-demand curl at localhost:${GHL_MCP_PORT})"
    fi

    # FIX 3 (v10.15.48): registration alone NEVER starts the local server, so
    # the GHL tools don't resolve. Run the EXECUTED autostart (launchd KeepAlive
    # on :8765 + healthcheck + auto-restart). Idempotent -- no-op if already
    # healthy + registered; honest SKIP line if GHL creds are absent.
    # BUG FIX (v10.15.49): run NON-BLOCKING so the wiring loop + .onboarding-version
    # stamp always complete. macOS has no `timeout`, so backgrounding is the safe
    # cross-platform fix. The MCP still starts; the updater no longer waits on it.
    # ── WHICH COPY OF THE AUTOSTART RUNS, AND FROM WHERE ────────────────────
    # DEFECT 2 (3-box pilot): a roll ran cleanly everywhere and converged NO box
    # to the hardened state. Two reasons, both here.
    #
    # (a) WRONG COPY. $ONBOARDING_DIR is the TEMP CLONE (/tmp/openclaw-onboarding-
    #     update). ghl-mcp-autostart.sh's FIRST pin-resolver candidate is
    #     "$SELF_DIR/../config/ghl-mcp-pin.env" — from the temp clone that
    #     resolves inside the clone, which the updater `rm -rf`s at its Cleanup
    #     step. The DELIVERED copy at $OC_ROOT/scripts/ is the one whose
    #     ../config sibling is the delivered $OC_ROOT/config/. Prefer it, so the
    #     pin the roll just delivered is the pin the autostart reads.
    # (b) BACKGROUNDED, THEN ASSERTED IMMEDIATELY. `( … & )` returned in
    #     milliseconds and the runtime assert below ran against the PRE-autostart
    #     state — it could only ever measure the defect it was meant to verify was
    #     fixed. Worse, the temp clone was deleted out from under the still-running
    #     child.
    #
    # FIX: run the DELIVERED copy, and WAIT for it, bounded. macOS has no
    # `timeout(1)`, which is why this was backgrounded in the first place
    # (v10.15.49) — so we background it and poll its PID with a hard ceiling,
    # which keeps the "a hung autostart can never stall a roll" property AND
    # makes the assert below measure the post-autostart state. The ceiling is
    # generous because a cold box does a real `npm ci` + build.
    local AUTOSTART=""
    local _AS_SRC=""
    for _as_cand in \
        "${OC_PERSISTENT_SCRIPTS_DIR:-}/ghl-mcp-autostart.sh" \
        "$HOME/.openclaw/scripts/ghl-mcp-autostart.sh" \
        "/data/.openclaw/scripts/ghl-mcp-autostart.sh" \
        "$ONBOARDING_DIR/scripts/ghl-mcp-autostart.sh"; do
      case "$_as_cand" in "/ghl-mcp-autostart.sh"|"") continue ;; esac
      if [ -f "$_as_cand" ]; then
        AUTOSTART="$_as_cand"
        case "$_as_cand" in
          "$ONBOARDING_DIR"/*) _AS_SRC="TEMP CLONE (delivered copy not found — its ../config sibling will not resolve; expect PIN_UNVERIFIED)" ;;
          *)                   _AS_SRC="delivered copy (its ../config sibling is the delivered pin)" ;;
        esac
        break
      fi
    done
    unset _as_cand

    GHL_MCP_AUTOSTART_RAN="no"
    if [ -n "$AUTOSTART" ]; then
      local _AS_MAX="${OPENCLAW_GHL_MCP_AUTOSTART_TIMEOUT:-900}"
      echo "    Running GHL MCP autostart and WAITING for it (max ${_AS_MAX}s) -- $_AS_SRC"
      echo "      $AUTOSTART  -- log: /tmp/ghl-mcp-autostart.log"
      ( GHL_MCP_PORT="$GHL_MCP_PORT" bash "$AUTOSTART" >/tmp/ghl-mcp-autostart.log 2>&1 ) &
      local _AS_PID=$! _AS_WAITED=0
      while kill -0 "$_AS_PID" 2>/dev/null; do
        [ "$_AS_WAITED" -ge "$_AS_MAX" ] && break
        sleep 2
        _AS_WAITED=$(( _AS_WAITED + 2 ))
      done
      if kill -0 "$_AS_PID" 2>/dev/null; then
        echo "    ⚠ GHL MCP autostart still running after ${_AS_MAX}s -- leaving it to finish in the background and NOT waiting further (a slow build must never stall a fleet roll)." >&2
        echo "    ⚠ The runtime conformance verdict below is therefore measured MID-INSTALL and may report FATALs that resolve once the build completes. Re-run scripts/ghl-mcp-assert-runtime.sh afterwards." >&2
        GHL_MCP_AUTOSTART_RAN="timeout"
      else
        wait "$_AS_PID" 2>/dev/null || true
        echo "    ✓ GHL MCP autostart completed in ~${_AS_WAITED}s"
        GHL_MCP_AUTOSTART_RAN="yes"
      fi
    else
      echo "    ⚠ ghl-mcp-autostart.sh not found in the delivered scripts dir OR the pulled bundle -- server NOT started; GHL tools will not resolve until it is run." >&2
    fi

    # v21.6.0 / R4: RUNTIME conformance verdict on the update path.
    # qc-assert-ghl-mcp-supervised.sh is STATIC — it reads the shipped script
    # and proves what a FRESH install WOULD do. It cannot see a hand-edited
    # plist, a live 859-tool /health, or a still-registered Tier 2, and on
    # 2026-08-03 all three were true on a box that gate would have called PASS.
    # This asserts what the box IS running. Non-fatal by design (the update must
    # not abort on a pre-existing runtime defect) but LOUD, and it names the one
    # command that fixes it.
    local RUNTIME_ASSERT=""
    for _rt_cand in \
        "${OC_PERSISTENT_SCRIPTS_DIR:-}/ghl-mcp-assert-runtime.sh" \
        "$HOME/.openclaw/scripts/ghl-mcp-assert-runtime.sh" \
        "/data/.openclaw/scripts/ghl-mcp-assert-runtime.sh" \
        "$ONBOARDING_DIR/scripts/ghl-mcp-assert-runtime.sh"; do
      case "$_rt_cand" in "/ghl-mcp-assert-runtime.sh"|"") continue ;; esac
      [ -f "$_rt_cand" ] && { RUNTIME_ASSERT="$_rt_cand"; break; }
    done
    unset _rt_cand
    if [ -n "$RUNTIME_ASSERT" ]; then
      local _RT_OUT _RT_RC=0
      _RT_OUT="$(bash "$RUNTIME_ASSERT" 2>&1)" || _RT_RC=$?
      printf '%s\n' "$_RT_OUT" >> "$LOG_FILE" 2>/dev/null || true
      case "$_RT_RC" in
        0) echo "    ✓ GHL MCP runtime conformance: OK (the INSTALLED service matches the pin)" ;;
        2) echo "    GHL MCP runtime conformance: not installed on this box -- nothing to assert" ;;
        *)
           # DEFECT 2, second half: this verdict used to be a bare warning that
           # nothing read, so a roll printed the FATALs and then exited 0 — a
           # HOLLOW UPDATE reported as a success. The verdict now LATCHES and is
           # surfaced in the end-of-run summary and in this run's EXIT CODE.
           #
           # WHY exit 2 AND NOT exit 1. The stamp gates in this script are
           # deliberately split (see the CONTENT-COMPLETENESS GATE): exit 1 means
           # "skills CONTENT is not verifiably current, stamp WITHHELD", and
           # wire_ghl_mcp runs BEFORE the stamp. Failing this to 1 would withhold
           # the content stamp on every box carrying a PRE-EXISTING Tier 2 defect
           # — bricking fleet rolls over an infrastructure fault that has nothing
           # to do with skills content. exit 2 is this script's existing,
           # documented "content current, infrastructure needs attention" code,
           # which fleet drivers already distinguish. That is exactly this state,
           # and it is emphatically NOT exit 0.
           GHL_MCP_RUNTIME_FATAL="yes"
           GHL_MCP_RUNTIME_DETAIL="$(printf '%s\n' "$_RT_OUT" | grep -F '[ghl-mcp-runtime] FAIL' || true)"
           {
             echo ""
             echo "  ############################################################"
             echo "  ## GHL MCP RUNTIME CONFORMANCE FAILED (rc=$_RT_RC)"
             echo "  ## The INSTALLED service on this box does NOT match the shipped standard."
             echo "  ## This run will exit 2 (content current, infrastructure needs attention)"
             echo "  ## rather than 0 — a roll that leaves the MCP misconfigured is not a success."
             printf '%s\n' "$GHL_MCP_RUNTIME_DETAIL" | sed 's/^/  ##   /'
             echo "  ## FIX: bash ${AUTOSTART:-<autostart not found on this box>}"
             echo "  ##      (it regenerates the service definition from the delivered pin)"
             echo "  ############################################################"
             echo ""
           } >&2
           ;;
      esac
    else
      echo "    ⚠ ghl-mcp-assert-runtime.sh not found on this box -- the RUNTIME conformance verdict did NOT run. The static gate cannot see a hand-edited plist, a 859-tool /health, or a still-registered Tier 2." >&2
    fi
  }

  # ---- Main wiring loop ----
  echo ""
  echo "  Wiring installed skills (CORE_UPDATES, prereqs, MCP registration)..."
  WIRED_COUNT=0
  SKIPPED_WIRED_COUNT=0

  for SKILL_DIR in "$SKILLS_DIR"/[0-9]*/; do
    [ -d "$SKILL_DIR" ] || continue
    SKILL_NAME=$(basename "$SKILL_DIR")
    case "$SKILL_NAME" in *ARCHIVED*) continue ;; esac

    # Per-box model-map RE-RESOLVE -- NOT sentinel-gated (runs BEFORE the wired-sentinel
    # short-circuit below). The anthology-engine's tier map (skill-dir model-map.json,
    # preflight.sh's default output) is resolved from the CLIENT's OWN configured models;
    # if a client changes their models
    # between update passes, the .wired-<version> sentinel would otherwise skip install.sh
    # and leave a STALE map -- which then fails closed deep at S9 (UnresolvedMapError) or
    # trips judge-independence. Re-resolve every pass (idempotent; fail is non-fatal here,
    # the engine's own GATE 1b RESOLVE-then-check is the fail-closed gate at run time).
    if [ -f "$SKILL_DIR/preflight.sh" ] && [ -f "$SKILL_DIR/config/model-map.template.json" ]; then
      echo "    Re-resolving model-map (preflight.sh) for $SKILL_NAME (not sentinel-gated)..."
      if bash "$SKILL_DIR/preflight.sh" >> "$LOG_FILE" 2>&1; then
        echo "    Model-map re-resolved: $SKILL_NAME"
      else
        echo "    Model-map re-resolve FAILED CLOSED for $SKILL_NAME (client has no resolvable/independent model; see $LOG_FILE) -- engine GATE 1b will refuse at run time until fixed"
      fi
    fi

    # GHL MCP (skill 36) -- NOT sentinel-gated, for the same reason the model-map
    # re-resolve above is not (R14).
    #
    # This used to be Step 4 INSIDE the sentinel-gated section below, so it ran
    # exactly once per ONBOARDING_VERSION bump -- which made the release note's
    # "weekly updates actually maintain the server" untrue between bumps. The
    # server is a live third-party process on :8765: it drifts, dies, goes deaf,
    # and (until this release) came back bound to 0.0.0.0 after any rebuild.
    # Repairing it is exactly the kind of convergence that must happen on EVERY
    # pass, not once per version.
    #
    # Concretely, sentinel-gating it would mean the D6 loopback-bind fix reached
    # a box only when the version number happened to change -- the same
    # "shipped but never delivered" failure this release exists to end.
    #
    # Safe to run every pass: wire_ghl_mcp is idempotent (it de-registers a legacy
    # mcp.servers entry and backgrounds ghl-mcp-autostart.sh, which fast-paths to
    # a no-op when the server is already healthy, pinned and answering JSON-RPC).
    wire_ghl_mcp "$SKILL_NAME"

    # DEFECT FIX: the Skill 38 AGENTS.md pointer-stanza rewriter
    # (05-update-agents-md.sh -- the source of the ~24k-char AGENTS.md size
    # win) was invoked NOWHERE in the automated pipeline: not by wiring, not
    # by wire_core_updates(), not by obs_verify_skill. It was documented only
    # as a MANUAL INSTALL.md step-5. Evidence it had not run in months: one
    # box's newest AGENTS.md.bak-skill38-* was ~7 version bumps stale while
    # every sibling skill wrote fresh backups on every roll. Wired here, NOT
    # sentinel-gated -- same reasoning as wire_ghl_mcp just above: the script
    # is idempotent/self-healing by design (a true no-op when the live file
    # already carries the current stanzas, per its own header) and its
    # "staged descent" design for a box running a core-file watcher NEEDS
    # MULTIPLE passes to converge past the watcher's shrink-floor -- gating
    # this to once-per-version-bump would break that convergence on any
    # watched box, the same "shipped but never delivered" failure class this
    # release exists to end.
    if [ "$SKILL_NAME" = "38-conversational-ai-system" ] \
       && [ -x "$SKILL_DIR/scripts/05-update-agents-md.sh" ]; then
      if AGENTS_MD="$WIRE_WORKSPACE_DIR/AGENTS.md" bash "$SKILL_DIR/scripts/05-update-agents-md.sh" >>"$LOG_FILE" 2>&1; then
        echo "    ✓ AGENTS.md pointer stanzas verified/refreshed (05-update-agents-md.sh)"
      else
        echo "    ⚠ 05-update-agents-md.sh reported an error for $SKILL_NAME (see $LOG_FILE) -- continuing"
      fi
    fi

    # Per-skill idempotency sentinel
    WIRED_SENTINEL="$SKILL_DIR/.wired-${ONBOARDING_VERSION}"
    if [ -f "$WIRED_SENTINEL" ]; then
      SKIPPED_WIRED_COUNT=$((SKIPPED_WIRED_COUNT + 1))
      continue
    fi

    # Step 1: Run the skill's own executable installer if present
    # Priority: wire.sh > install.sh > setup-*.sh (first match)
    SKILL_INSTALLER=""
    # Reset per skill -- gates the sentinel write below. A failed installer
    # must NOT be sentinel-gated (that was the defect that made a failed
    # cron registration permanent -- see the note at the sentinel write for
    # the full story).
    _INSTALLER_FAILED=0
    for _candidate in "$SKILL_DIR/wire.sh" "$SKILL_DIR/install.sh" "$SKILL_DIR/scripts/install.sh"; do
      if [ -x "$_candidate" ]; then
        SKILL_INSTALLER="$_candidate"
        break
      fi
    done
    # Also check for setup-*.sh pattern
    if [ -z "$SKILL_INSTALLER" ]; then
      for _candidate in "$SKILL_DIR"/setup-*.sh "$SKILL_DIR"/scripts/setup-*.sh; do
        if [ -x "$_candidate" ]; then
          SKILL_INSTALLER="$_candidate"
          break
        fi
      done
    fi

    if [ -n "$SKILL_INSTALLER" ]; then
      echo "    Running installer: $(basename "$SKILL_INSTALLER") for $SKILL_NAME..."
      _installer_rc=0
      bash "$SKILL_INSTALLER" --idempotent >> "$LOG_FILE" 2>&1 || _installer_rc=$?
      if [ "$_installer_rc" = "0" ]; then
        echo "    Installer OK: $SKILL_NAME"
      else
        _INSTALLER_FAILED=1
        echo "    Installer FAILED for $SKILL_NAME (rc=$_installer_rc; see $LOG_FILE) -- .wired sentinel withheld, will retry next roll"
      fi
    fi

    # Step 2: Idempotently merge CORE_UPDATES.md into workspace files
    wire_core_updates "$SKILL_NAME"

    # Step 3: Install OS prereqs (ffmpeg/imagemagick for video skills)
    wire_prereqs "$SKILL_NAME"

    # Step 4: (GHL MCP wiring moved ABOVE the sentinel -- see the note there.)

    # Step 5 (v12.0.0): Per-skill prerequisite check -- NOT sentinel-gated.
    # Runs on every wiring pass so a prereq satisfied between runs clears on
    # the next update. Exit 2 = installed-with-missing-prereqs (note + continue).
    # Exit 3 = malformed PREREQS.json (warn + continue). Read-only; self-records.
    PREREQ_CHECKER_UPDATE="$SKILLS_DIR/shared-utils/check-skill-prereqs.sh"
    if [[ -x "$PREREQ_CHECKER_UPDATE" && -f "$SKILL_DIR/PREREQS.json" ]]; then
      PREREQ_RC_UPDATE=0
      bash "$PREREQ_CHECKER_UPDATE" "$SKILL_DIR" || PREREQ_RC_UPDATE=$?
      if [[ $PREREQ_RC_UPDATE -eq 2 ]]; then
        echo "    [prereq] $SKILL_NAME: installed with missing prerequisites"
      elif [[ $PREREQ_RC_UPDATE -eq 3 ]]; then
        echo "    [prereq] $SKILL_NAME: WARN malformed PREREQS.json (skipped)"
      fi
    fi

    # Mark skill as wired for this version -- UNLESS its own installer
    # failed. This is the fix for tonight's false alarm: the sentinel used to
    # be written unconditionally, so a failed `wire.sh` (e.g. the Rescue
    # Rangers cron registration silently swallowing a gateway error) still
    # got sentinel-gated and every later roll skipped the skill entirely --
    # permanently reporting a wired/successful roll while nothing was ever
    # scheduled. A failed installer must remain retryable on the next roll,
    # so withhold the sentinel (and the "wired" status/count) when it failed.
    if [ "$_INSTALLER_FAILED" = "1" ]; then
      echo "    NOT marking $SKILL_NAME wired for $ONBOARDING_VERSION -- installer failed this pass, next roll will retry it"
      command -v obs_set_status >/dev/null 2>&1 && obs_set_status "$SKILL_NAME" "pending"
    else
      touch "$WIRED_SENTINEL" 2>/dev/null || true
      # FIX 1: state transition -- installer + CORE_UPDATES merge ran = WIRED
      # (still NOT "installed" until the verification gate passes below).
      command -v obs_set_status >/dev/null 2>&1 && obs_set_status "$SKILL_NAME" "wired"
      WIRED_COUNT=$((WIRED_COUNT + 1))
    fi
  done

  echo "  Wiring complete: $WIRED_COUNT skill(s) wired, $SKIPPED_WIRED_COUNT already wired (idempotent skip)"

  # ----------------------------------------------------------
  # v16.2.6: DEFENSIVE tool-drift report (installed CLIs vs skill source).
  # Some skills install a standalone CLI by copying their engine into
  # ~/.openclaw/tools/<tool>/ and `pip install -e` on the copy (e.g. caf, skill
  # 44). The routine sync updates skill SOURCE files but the installed binary can
  # still drift. scripts/tool-drift-check.sh reads each tool's .installed-from
  # stamp, compares it to skill-version.txt, and capability-probes the binary.
  # This is REPORT-ONLY and MUST NOT change the update's exit status: it runs
  # only when the script is present + executable, and any non-zero verdict is
  # swallowed (`|| true`) so a stale/missing tool never fails the update here —
  # it is surfaced loudly for an operator/agent rebuild instead.
  TOOL_DRIFT_CHECK="$ONBOARDING_DIR/scripts/tool-drift-check.sh"
  if [ -x "$TOOL_DRIFT_CHECK" ]; then
    TOOL_DRIFT_JSON="${LOG_FILE%.log}-tool-drift.json"
    echo ""
    echo "  Checking installed CLI tools for drift vs skill source (report-only)..."
    if bash "$TOOL_DRIFT_CHECK" --json-only > "$TOOL_DRIFT_JSON" 2>>"$LOG_FILE"; then
      echo "  tool-drift: all installed CLIs in sync with source."
    else
      echo "  tool-drift: STALE/UNPROVEN TOOLING DETECTED -- see $TOOL_DRIFT_JSON"
      echo "  (rebuild commands are printed in that JSON; rebuild is opt-in, never auto-run here)"
    fi || true
  fi

  # ----------------------------------------------------------
  # Harden Google Workspace (gws) credential resilience on the ROLL path too.
  # ----------------------------------------------------------
  # Same guard install.sh Step 8c runs, so an updated box also gets: the file
  # keyring backend forced for every shell (append-only ~/.zshenv etc.), the
  # gws-as PATH wrapper, and an off-box encrypted snapshot of the default gws
  # credential store. This closes the v16.1.x self-wipe class on every box that
  # only ever takes the update path. Idempotent + additive + box-user; best-effort
  # so it can never change the update's exit status.
  HARDEN_GWS="$ONBOARDING_DIR/scripts/harden-gws-credential-resilience.sh"
  [ -f "$HARDEN_GWS" ] || HARDEN_GWS="$OC_CONFIG/scripts/harden-gws-credential-resilience.sh"
  if [ -f "$HARDEN_GWS" ]; then
    echo ""
    echo "  Hardening gws credential resilience (file keyring backend + gws-as wrapper + off-box backup)..."
    if OC_CONFIG="${OC_CONFIG:-}" bash "$HARDEN_GWS" >> "$LOG_FILE" 2>&1; then
      echo "  harden-gws-credential-resilience.sh: OK"
    else
      echo "  harden-gws-credential-resilience.sh: completed with warnings (see $LOG_FILE)"
    fi || true
  else
    echo "  (harden-gws-credential-resilience.sh not found -- skipping gws hardening; older bundle)"
  fi

  # ----------------------------------------------------------
  # v10.15.42: Run migrate-existing-workforce.sh so copied skills
  # actually install into the client's live department tree.
  # This script is idempotent and additive -- it never deletes or
  # overwrites existing departments, only fills gaps.
  #
  # v16.0.2: migrate-existing-workforce.sh Step 2b now MATERIALIZES missing
  # canonical floor roles/SOPs via floor-fill-driver.py (fed by
  # make-gap-from-staleness.py). Before v16.0.2 the update path DETECTED the
  # missing v16 floor roles (devils-advocate/healer per dept, video/graphics/
  # presentations expansions) but never FILLED them, leaving every v16-updated
  # box with an incomplete floor. Running migrate here closes that on the update
  # path (the same floor-fill backstop runs on the install path -- see
  # install.sh step 6b). Idempotent, skip-existing, no-clobber, box-user.
  # ----------------------------------------------------------
  MIGRATE_SCRIPT="$SKILLS_DIR/23-ai-workforce-blueprint/scripts/migrate-existing-workforce.sh"
  if [ -x "$MIGRATE_SCRIPT" ]; then
    echo ""
    echo "  Running workforce migration (installs copied skills into department tree)..."
    if bash "$MIGRATE_SCRIPT" "$(hostname)" --apply >> "$LOG_FILE" 2>&1; then
      echo "  migrate-existing-workforce.sh: OK"
    else
      echo "  migrate-existing-workforce.sh: completed with warnings (see $LOG_FILE)"
      # v20.0.10: migrate-existing-workforce.sh is WORKFORCE floor-fill -- its
      # exit code is its Step-5 qc-completeness WORKFORCE verdict (rc 2 = a dept
      # below the 95% floor; rc 3 = a dept at zero materialization / no workforce
      # built yet for an interview-incomplete client). Those are WORKFORCE-
      # provisioning states, NOT skills-content problems: the A3 content-gate, the
      # U6b persona-content re-assertion, and the refresh-stale-roles IN-SCOPE
      # content-refresh check are what protect the content stamp. A half-built
      # workforce must NOT withhold the skills-version stamp (the box IS on current
      # content) -- it is surfaced as an advisory and driven to completion by the
      # POST-stamp qc-completeness run + the onboarding-resume cron. So route it to
      # the workforce latch, decoupled from the content stamp (was _D2_REFRESH_STATUS,
      # which conflated workforce floor-fill with in-scope content refresh).
      _D2_MIGRATE_STATUS="fail"
    fi
  else
    echo "  (migrate-existing-workforce.sh not found or not executable -- skipping)"
  fi

  # ----------------------------------------------------------
  # v12.27.0: PER-ARTIFACT STALENESS DETECTION (drives the refresh flow).
  # After the new library version lands and the migration filled structural gaps,
  # ask detect-stale-artifacts.py whether THIS client's built roles / depts / SOPs
  # are out of date vs the installed role-library content manifest. The hash is
  # canonical-source based (computed over the library TEMPLATE with {{TOKENS}}
  # intact, NOT rendered client bytes), so this has ZERO per-client false
  # positives: a future edit to ONE role .md flags ONLY clients built from the old
  # content_sha, for ONLY that artifact. rc 10 + the --json item list are the
  # refresh work queue: STALE roles are re-instantiated via the SAME copy+token-fill
  # path migrate-existing-workforce.sh / build-workforce use, MISSING roles are
  # added, build-state.artifactProvenance is rewritten, and the per-file
  # workforce-provenance marker is re-stamped — returning the client to CURRENT.
  # READ-ONLY here (report + queue); the re-instantiation reuses the existing
  # additive migration path so this never deletes or overwrites client edits.
  # ----------------------------------------------------------
  DETECT_SCRIPT="$SKILLS_DIR/23-ai-workforce-blueprint/scripts/detect-stale-artifacts.py"
  DETECT_MANIFEST="$SKILLS_DIR/23-ai-workforce-blueprint/templates/role-library/_index.json"
  if [ "$OPENCLAW_PLATFORM" = "vps" ]; then
    OC_WORKSPACE="/data/.openclaw/workspace"
  else
    OC_WORKSPACE="$HOME/.openclaw/workspace"
  fi
  if [ -f "$DETECT_SCRIPT" ] && [ -f "$DETECT_MANIFEST" ] && \
     { [ -d "$OC_WORKSPACE/departments" ] || [ -f "$OC_WORKSPACE/.workforce-build-state.json" ]; } && \
     command -v python3 >/dev/null 2>&1; then
    echo ""
    echo "  Detecting per-artifact staleness (role / dept / SOP) vs new library content manifest..."
    if DETECT_OUT="$(python3 "$DETECT_SCRIPT" --workspace "$OC_WORKSPACE" --manifest "$DETECT_MANIFEST" --json 2>>"$LOG_FILE")"; then DETECT_RC=0; else DETECT_RC=$?; fi
    if [ -n "$DETECT_OUT" ]; then
      # Persist the refresh work queue so the orchestrator / a follow-up
      # re-instantiation pass can consume it (and for audit).
      QUEUE_FILE="$OC_WORKSPACE/.artifact-refresh-queue.json"
      printf '%s' "$DETECT_OUT" > "$QUEUE_FILE" 2>/dev/null || true
      printf '%s' "$DETECT_OUT" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
s = d.get('summary', {})
act = s.get('stale',0)+s.get('missing',0)+s.get('orphan',0)+s.get('untracked',0)
print(f\"  artifact staleness: CURRENT={s.get('current',0)} STALE={s.get('stale',0)} \"
      f\"MISSING={s.get('missing',0)} ORPHAN={s.get('orphan',0)} UNTRACKED={s.get('untracked',0)}\")
if act:
    print(f'  -> {act} artifact(s) queued for refresh (.artifact-refresh-queue.json); '
          'STALE/MISSING re-instantiate via the additive library-fill path')
else:
    print('  -> all artifacts CURRENT (nothing to refresh)')
" 2>/dev/null || true
      if [ "$DETECT_RC" -eq 10 ]; then
        echo "  (refresh queue written: $QUEUE_FILE)"
      fi
    else
      echo "  (detect-stale-artifacts.py produced no output -- skipping; see $LOG_FILE)"
    fi
  else
    echo "  (detect-stale-artifacts.py / manifest / workspace not present -- skipping per-artifact staleness check)"
  fi

  # ----------------------------------------------------------
  # P2-08 step 2: ARTIFACT-REFRESH-QUEUE CONSUMER.
  # The queue write above (.artifact-refresh-queue.json) has had a producer
  # since v12.27.0 but NEVER a consumer for the STALE-role case -- a box kept
  # OLD role docs forever after an upgrade (Presentation spec Section 13.9
  # deploy trap; the v16.0.2 floor-fill-driver.py only ever handled MISSING
  # roles, skip-existing/no-clobber by design, so it never touches a role
  # that already has a folder on disk). refresh-stale-roles.py drains ONLY
  # kind=="role" AND status=="STALE" queue rows: it re-copies the current
  # library content into the EXISTING role's how-to.md via the SAME
  # library_lookup()/try_library_fill() path create_role_workspace() uses for
  # a brand-new role, then re-stamps the provenance marker with the CURRENT
  # content_sha so a future detect-stale-artifacts.py run classifies it
  # CURRENT. It resolves the department directory against what is ACTUALLY on
  # disk (both the bare `departments/<dept>` layout live boxes use and the
  # legacy `-dept` suffixed form) -- assuming one layout was the 2026-07-21
  # defect that made this step repair nothing on every box while reporting
  # success. persona rows and MISSING/ORPHAN/UNTRACKED rows are left in the
  # queue untouched (out of this consumer's scope).
  #
  # A poisoned row (nonexistent role path, corrupt JSON, no library match) is
  # left queued and never ABORTS the drain -- later rows still drain. But it
  # is NOT swallowed: since 2026-07-21 any in-scope row the drain could not
  # complete is a DETECTED gap left UNFILLED, so the consumer exits 3 and the
  # `if PIPE; then` capture below trips _D2_REFRESH_STATUS. That latch feeds
  # the pre-stamp gate, which withholds the completion stamp and exits 1. A
  # repair step that cannot repair must say so loudly. A MISSING consumer
  # tool (older bundle) is still a benign skip -- see the else branch.
  # ----------------------------------------------------------
  REFRESH_CONSUMER="$SKILLS_DIR/23-ai-workforce-blueprint/scripts/refresh-stale-roles.py"
  if [ -f "$REFRESH_CONSUMER" ] && command -v python3 >/dev/null 2>&1; then
    echo ""
    echo "  Draining artifact-refresh-queue (STALE role docs -> fresh library content)..."
    # D4[F]: pipefail-correct capture (set -euo pipefail active at L50) -- the
    # old `cmd | tee ... || echo` swallowed refresh-stale-roles.py's own exit
    # code (0=drain complete/benign, 3=in-scope refresh incomplete,
    # 1=usage-only) because `tee`'s exit status, not python3's, terminated the
    # pipeline. `if PIPE; then` under `set -o pipefail` correctly reflects the
    # FIRST failing command in the pipe.
    if python3 "$REFRESH_CONSUMER" --workspace "$OC_WORKSPACE" --apply 2>&1 | tee -a "$LOG_FILE"; then
      :
    else
      echo "  refresh-stale-roles.py: completed with warnings (see $LOG_FILE)"
      _D2_REFRESH_STATUS="fail"
    fi
  else
    echo "  (refresh-stale-roles.py not found or python3 unavailable -- skipping artifact-refresh-queue drain; older bundle)"
  fi

  # ----------------------------------------------------------
  # FIX-DELIVERY-02: UNCONDITIONAL DEPARTMENT-SCRIPTS MIRROR.
  # The refresh-stale-roles.py drain immediately above -- like every other
  # repair step on this box -- only ever acts on rows detect-stale-artifacts.py
  # put in a queue. detect-stale-artifacts.py's load_current() never emits a
  # "scripts" kind at all (the literal string never appears in the manifest,
  # and there is no code path that could produce one), so a department's
  # canonical scripts/ files (build_deck.py, capacity.py, deliverables.py,
  # self_audit.py, qc_check.py, ...) can NEVER be queued STALE or MISSING --
  # not on a fresh install, and never again afterward. The only other writer,
  # scaffold_department() (create_role_workspaces.py), has exactly one runtime
  # caller (floor-fill-driver.py), gated behind migrate-existing-workforce.sh's
  # `FF_GAP_DEPTS -gt 0` check -- on a HEALTHY steady-state box (no missing
  # roles/sops/depts) that gate is false and floor-fill-driver.py never runs,
  # so not even the depth-1 files this repo already treats as fleet-owned
  # (.py/.sh/.js/.tpl/.sha256/.pdf) ever refresh again after day one.
  #
  # refresh-dept-scripts.py closes both gaps at once: it mirrors every
  # role-library department's scripts/ tree onto the box's materialized
  # department directory UNCONDITIONALLY, every roll, with no gap-map
  # dependency (same unconditional-every-roll shape as refresh-stale-roles.py
  # above), honoring the same ownership policy scaffold_department already
  # enforces (.py/.sh/.js/.tpl/.sha256/.pdf fleet-owned/always-overwrite-when-
  # divergent; .json box-owned/additive/missing-only). Its pass/fail verdict
  # is re-derived from the filesystem AFTER the copy step (sha256 of the
  # library file vs the destination file), never from its own copy-loop
  # counter, so an incomplete or sabotaged copy is caught here exactly like
  # scaffold_department's own post-materialization proof.
  #
  # A poisoned/missing department is a benign SKIP (not this script's job to
  # create one -- that stays floor-fill-driver.py's MISSING-department job).
  # Only a materialized department whose canonical files fail to verify AFTER
  # the copy counts against the completeness contract (rc 3), which trips
  # _D2_DEPTSCRIPTS_STATUS below -- same pipefail-correct `if PIPE; then`
  # capture as the refresh-stale-roles.py block above. A MISSING generator
  # (older bundle) is still a benign skip -- see the else branch.
  # ----------------------------------------------------------
  DEPT_SCRIPTS_REFRESH="$SKILLS_DIR/23-ai-workforce-blueprint/scripts/refresh-dept-scripts.py"
  if [ -f "$DEPT_SCRIPTS_REFRESH" ] && command -v python3 >/dev/null 2>&1; then
    echo ""
    echo "  Mirroring department scripts/ trees (unconditional, every roll)..."
    if python3 "$DEPT_SCRIPTS_REFRESH" --workspace "$OC_WORKSPACE" --apply 2>&1 | tee -a "$LOG_FILE"; then
      :
    else
      echo "  refresh-dept-scripts.py: completed with warnings (see $LOG_FILE)"
      _D2_DEPTSCRIPTS_STATUS="fail"
    fi
  else
    echo "  (refresh-dept-scripts.py not found or python3 unavailable -- skipping dept scripts/ mirror; older bundle)"
  fi

  # ----------------------------------------------------------
  # U007: MISSING-DEPARTMENTS ANOMALY WARNING. The role-staleness drain above
  # checks role docs against the departments/ tree. If that directory is absent
  # while .workforce-build-state.json says interviewComplete=true, the drain has
  # no departments to check against and SILENTLY skips — the anomaly is invisible
  # (a completed-interview box with no departments on disk is almost always an
  # accidental deletion, not a legitimate state). Surface it explicitly so it is
  # never mistaken for "nothing to do". Advisory only: this never withholds the
  # stamp and never fails the update — it only makes the invisible visible.
  # AC#3: when departments/ IS present this is a no-op (no warning, same
  # staleness result and exit code as before).
  u007_missing_departments_warning "${OC_WORKSPACE:-$HOME/.openclaw/workspace}"

  # U004 -- Assert department doctrine provenance (warn-mode).
  # Non-fatal; logged through $LOG_FILE.
  u004_assert_doctrine_provenance

  # ----------------------------------------------------------
  # RETIRED-LIBRARY-FILE RECONCILE (2026-07-21). Canonical DELETIONS reach the
  # live skill dir -- `rm -rf "$SKILLS_DIR/$SKILL_NAME"` + `cp -r` above is a
  # WHOLESALE replace, and it is measured clean (role-library = 913 files, ZERO
  # orphans, on all 30 reachable boxes). They do NOT reach three other trees:
  #   1. $OC_CONFIG/onboarding -- the PERSISTENT staging checkout, merge-copied
  #      by install.sh:3165 (`cp -r .../openclaw-onboarding-main/* $ONBOARDING_DIR/`)
  #      into a durable dir that also holds client state and is never wiped.
  #   2. skills installed FROM that dirty staging tree by install.sh:3193-3205,
  #      which is additive too (no rm -rf), so a re-run can RE-SEED dead files.
  #   3. strays inside the skill search path the wholesale replace never visits
  #      because they are not <NN-skill-name> dirs: skills/onboarding/,
  #      skills/openclaw-onboarding/, skills/templates/role-library/.
  # Measured 2026-07-21: 755 orphan instances across 30 boxes, 369 in
  # agent-reachable trees, 207 of those MISLEADING (a superseded 17,221-byte
  # SOP still readable next to its 22,496-byte replacement).
  #
  # DRY-RUN IS THE DEFAULT and stays the default: this step REPORTS what it
  # would quarantine and touches nothing. Removal is opt-in per box via
  # OPENCLAW_RECONCILE_ORPHANS=apply, and even then it MOVES files to
  # <oc-root>/.orphan-quarantine/<ts>/ (restorable), never unlinks. The tool
  # can only act on a file whose path AND content_sha are both recorded in
  # templates/role-library/_retired.json (generated from git history,
  # CI-gated) -- a client-authored file matches neither, a locally-modified
  # dead file matches only the path and is reported as a CONFLICT.
  # Cold backups (skills.bak*, backups/, updater-src-*) are pruned from the
  # walk: they are rollback material, deleting them would be the bug.
  #
  # ADVISORY ONLY -- it never withholds the version stamp. An orphan is a
  # cleanliness/read-hazard finding about trees the updater does not own; a
  # box that is otherwise fully current must not be held back by one.
  # ----------------------------------------------------------
  RECONCILE_ORPHANS="$SKILLS_DIR/23-ai-workforce-blueprint/scripts/reconcile-orphan-library-files.py"
  if [ -f "$RECONCILE_ORPHANS" ] && command -v python3 >/dev/null 2>&1; then
    echo ""
    _RO_ROOT="$(dirname "$SKILLS_DIR")"
    # rc 10 = orphans found in dry-run, rc 4 = a conflict/undecidable file was
    # reported and skipped, rc 2 = unusable ledger/manifest (nothing touched).
    # None of those is an update failure, and none is swallowed either -- the
    # tool's full report, including its own RECONCILE_STATUS line, is printed.
    if [ "${OPENCLAW_RECONCILE_ORPHANS:-report}" = "apply" ]; then
      echo "  Reconciling RETIRED library files (OPENCLAW_RECONCILE_ORPHANS=apply -> quarantine)..."
      python3 "$RECONCILE_ORPHANS" --root "$SKILLS_DIR" --root "$_RO_ROOT/onboarding" \
        --apply 2>&1 | tee -a "$LOG_FILE" || true
    else
      echo "  Reconciling RETIRED library files (REPORT-ONLY; set OPENCLAW_RECONCILE_ORPHANS=apply to quarantine)..."
      python3 "$RECONCILE_ORPHANS" --root "$SKILLS_DIR" --root "$_RO_ROOT/onboarding" \
        2>&1 | tee -a "$LOG_FILE" || true
    fi
    unset _RO_ROOT
  else
    echo "  (reconcile-orphan-library-files.py not found or python3 unavailable -- skipping retired-file reconcile; older bundle)"
  fi

  # ----------------------------------------------------------
  # v10.15.51: SHARED CORE FILE UNIFICATION (Zero-Human-Workforce file model).
  # AFTER skills + workspaces + CORE_UPDATES wiring + workforce migration, every
  # agent/sub-agent on THIS box shares the box's ONE canonical AGENTS.md /
  # TOOLS.md / USER.md via a real file COPY (N29 amended -- the OpenClaw
  # runtime rejects a symlink whose realpath resolves outside the reading
  # agent's own workspace; see link_shared_core_files() above). Per-agent
  # IDENTITY/SOUL/MEMORY/HEARTBEAT stay each agent's own. Nested workflow
  # agents exempt. Idempotent. Reads THIS box's openclaw.json only
  # (co-mingling guard) -- never a foreign/hardcoded target.
  # ----------------------------------------------------------
  echo ""
  echo "  Unifying shared core files (AGENTS/TOOLS/USER copied from this box's canonical)..."
  if link_shared_core_files; then
    :
  else
    echo "  ⚠ link_shared_core_files reported warnings (update continues)"
    _SHAREDCORE_STATUS="fail"  # D4[G]: renamed from the old _D5_ACTIVATION_STATUS name collision
  fi

  # ----------------------------------------------------------
  # D5 -- PRE-STAMP dept-agent activation gate (feeds the unified completeness
  # gate below). Runs materialize-dept-agents.sh here so a genuine
  # registration failure blocks the version stamp; the existing POST-stamp
  # materialize block further down (routing-correct final registration) is
  # LEFT IN PLACE and still runs its own idempotent re-pass afterward -- D5
  # keeps BOTH runs. A pre-interview self-skip (INTERVIEW_NOT_COMPLETE) and a
  # box where Skill 32 is not yet installed are BOTH benign -- PASS, not
  # fail. A genuine non-zero exit always flips _D5_ACTIVATION_PASS. For an
  # interview-complete run, agents.list[] is compared against THIS box's real
  # expected department count (department-floor.py's expected_floor_count --
  # the 24-mandatory + 6-universal-primary 30-department floor from
  # department-naming-map.json, net of any owner-declined department) rather
  # than a fixed "under 2" magic number -- a box whose activation genuinely
  # failed for most departments but still kept >=2 agents no longer sails
  # through. When department-floor.py cannot resolve a verdict for this box
  # (older bundle, or no departments dir yet), the gate falls back to the
  # prior "under 2" wiring-only check rather than false-FAIL a box with no
  # computable floor.
  # ----------------------------------------------------------
  _D5_MATERIALIZE="$SKILLS_DIR/32-command-center-setup/scripts/materialize-dept-agents.sh"
  if [ -f "$_D5_MATERIALIZE" ]; then
    echo ""
    echo "  [D5] Pre-stamp dept-agent activation check (materialize-dept-agents.sh)..."
    if _D5_OUT="$(bash "$_D5_MATERIALIZE" 2>&1)"; then _D5_RC=0; else _D5_RC=$?; fi
    if [ "$_D5_RC" -ne 0 ]; then
      _D5_ACTIVATION_PASS=0
      _D5_DEPT_STATE="fail"
      _D5_NOTLIVE_DETAIL="materialize-dept-agents.sh exited $_D5_RC"
      echo "  ✗ [D5] materialize-dept-agents.sh exited $_D5_RC — dept agents NOT registered"
    elif printf '%s' "$_D5_OUT" | grep -q "INTERVIEW_NOT_COMPLETE"; then
      _D5_DEPT_STATE="interview-not-complete"
      echo "  ✓ [D5] pre-interview self-skip (INTERVIEW_NOT_COMPLETE) — benign, not a failure"
    else
      _D5_AGENT_COUNT=0
      if [ -f "$OC_JSON" ]; then
        _D5_AGENT_COUNT=$(python3 -c "import json,sys; d=json.load(open('$OC_JSON')); sys.stdout.write(str(len(d.get('agents',{}).get('list',[]))))" 2>/dev/null || echo "0")
      fi
      # D5[F2]: gate on THIS box's real expected department count instead of a
      # fixed "-lt 2" magic number. A genuine interview-complete box carries the
      # 30-department universal floor (department-naming-map.json v2.8.0: 24
      # mandatory + 6 universal-primary, net of any owner-declined dept) -- "-lt 2" let a
      # box whose activation genuinely failed for MOST departments but still
      # kept >=2 agents.list[] entries false-PASS. department-floor.py is the
      # single source of truth qc-completeness.sh's own floor gate already
      # imports, so this stays in lockstep with the rest of the completeness
      # contract instead of drifting from it.
      _D5_EXPECTED_COUNT=""
      _D5_FLOOR_SCRIPT="$SKILLS_DIR/23-ai-workforce-blueprint/scripts/department-floor.py"
      if [ -f "$_D5_FLOOR_SCRIPT" ] && command -v python3 >/dev/null 2>&1; then
        _D5_FLOOR_JSON="$(python3 "$_D5_FLOOR_SCRIPT" --json 2>/dev/null || true)"
        _D5_EXPECTED_COUNT="$(printf '%s' "$_D5_FLOOR_JSON" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
n = d.get('expected_floor_count')
if isinstance(n, int) and n > 0:
    sys.stdout.write(str(n))
" 2>/dev/null || true)"
      fi
      if [ -n "$_D5_EXPECTED_COUNT" ]; then
        # Precise per-box floor available -- gate on THIS box's real expected count.
        if [ -z "$_D5_AGENT_COUNT" ] || [ "$_D5_AGENT_COUNT" -lt "$_D5_EXPECTED_COUNT" ]; then
          _D5_ACTIVATION_PASS=0
          _D5_DEPT_STATE="fail"
          _D5_NOTLIVE_DETAIL="agents.list[] has only ${_D5_AGENT_COUNT:-0} entries after materialize, below this box's computed department floor of ${_D5_EXPECTED_COUNT} (interview complete)"
          echo "  ✗ [D5] WIRING-ASSERT FAIL: agents.list[] has only ${_D5_AGENT_COUNT:-0} entries after materialize, below the computed department floor of ${_D5_EXPECTED_COUNT}"
        else
          _D5_DEPT_STATE="registered"
          echo "  ✓ [D5] dept agents registered (${_D5_AGENT_COUNT} agents in agents.list[], floor=${_D5_EXPECTED_COUNT})"
        fi
      elif [ -z "$_D5_AGENT_COUNT" ] || [ "$_D5_AGENT_COUNT" -lt 2 ]; then
        # department-floor.py unavailable / no verdict for this box -- fall
        # back to the prior wiring-only check so we never false-FAIL a box
        # we have no computable floor for.
        _D5_ACTIVATION_PASS=0
        _D5_DEPT_STATE="fail"
        _D5_NOTLIVE_DETAIL="agents.list[] has only ${_D5_AGENT_COUNT:-0} entries after materialize (interview complete; department-floor.py unavailable -- fell back to the wiring-only check)"
        echo "  ✗ [D5] WIRING-ASSERT FAIL: agents.list[] has only ${_D5_AGENT_COUNT:-0} entries after materialize"
      else
        _D5_DEPT_STATE="registered"
        echo "  ✓ [D5] dept agents registered (${_D5_AGENT_COUNT} agents in agents.list[]; department-floor.py unavailable -- wiring-only check)"
      fi
    fi
  else
    echo "  (materialize-dept-agents.sh not found -- Skill 32 not yet installed on this box; D5 pre-stamp activation check SKIPPED, benign)"
  fi

  # ----------------------------------------------------------
  # A3: CONTENT-GATE — verify installed content matches source
  # BEFORE writing the version stamp. This replaces the old
  # tautological verify (script wrote its own constant) with a
  # real content assertion (destination digest == source digest).
  # If ANY installed skill's content does not match the source,
  # the stamp is NEVER written and the script exits 1.
  # ----------------------------------------------------------
  _A3_GATE_PASS=1
  _A3_MISMATCH_SKILLS=""
  if [ -n "$SRC_MANIFEST" ] && [ -f "$_CONTENT_HASH_SCRIPT" ]; then
    echo ""
    echo "  [A3] Running content-gate: verifying destination matches source..."
    DEST_MANIFEST=$(bash "$_CONTENT_HASH_SCRIPT" "$SKILLS_DIR" 2>/dev/null || true)

    # Compare per-skill digests for skills that were installed this run.
    # We skip skills that were not in scope (ARCHIVED, or not updated by --only).
    while IFS='|' read -r skill_name src_digest; do
      [ -z "$skill_name" ] && continue
      [[ "$skill_name" == "__TREE_SHA__" ]] && continue
      case "$skill_name" in *ARCHIVED*) continue ;; esac

      # U004: when --only is set, restrict A3 check to the target skill(s) only.
      # Otherwise drift in a non-copied skill falsely withholds the stamp.
      if [ -n "$ONLY_SKILLS" ]; then
        _SKILL_PREFIX=$(echo "$skill_name" | cut -d'-' -f1)
        _A3_MATCH="false"
        _A3_OIFS=$IFS; IFS=','
        for _a3_want in $ONLY_SKILLS; do
          _a3_want_trimmed=$(echo "$_a3_want" | tr -d '[:space:]')
          if [ "$_SKILL_PREFIX" = "$_a3_want_trimmed" ]; then
            _A3_MATCH="true"
            break
          fi
        done
        IFS=$_A3_OIFS
        if [ "$_A3_MATCH" != "true" ]; then
          continue
        fi
      fi

      dest_digest=$(echo "$DEST_MANIFEST" | grep "^${skill_name}|" | cut -d'|' -f2 | head -1 || true)
      if [ -z "$dest_digest" ]; then
        echo "    [A3] MISMATCH: $skill_name — present in source but NOT in destination" >&2
        _A3_MISMATCH_SKILLS="${_A3_MISMATCH_SKILLS}  $skill_name: expected=$src_digest found=<missing>\n"
        _A3_GATE_PASS=0
      elif [ "$dest_digest" != "$src_digest" ]; then
        echo "    [A3] MISMATCH: $skill_name — content digest differs" >&2
        _A3_MISMATCH_SKILLS="${_A3_MISMATCH_SKILLS}  $skill_name: expected=$src_digest found=$dest_digest\n"
        _A3_GATE_PASS=0
      else
        : # echo "    [A3] OK: $skill_name"
      fi
    done <<< "$SRC_MANIFEST"

    if [ "$_A3_GATE_PASS" -eq 0 ]; then
      echo ""
      echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
      echo "  A3 CONTENT-GATE FAILED — stamp NOT written."
      echo "  The following skills have content that does not match source:"
      printf '%b' "$_A3_MISMATCH_SKILLS"
      echo ""
      echo "  The version stamp is NEVER written when content is mismatched."
      echo "  Re-run update-skills.sh to retry the install from scratch."
      echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
      rm -rf "$TEMP_EXTRACT" "$TEMP_ZIP"
      exit 1
    fi
    echo "  [A3] Content-gate PASSED — all installed skills match source."
  else
    echo "  [A3] skill-content-hash.sh unavailable — skipping content verification (legacy path)"
  fi

  # ----------------------------------------------------------
  # CONTENT-COMPLETENESS GATE (v20.0.10: content-vs-workforce split).
  # The .onboarding-version stamp certifies "this box's skills CONTENT is current
  # and matches the pinned tag" -- NOT "this client's workforce is fully built".
  # Runs strictly AFTER the A3 content-gate above and reuses its exit-1 discipline.
  # A healthy box ALWAYS reaches the stamp below: a fail here is reserved for a
  # genuine SKILLS-CONTENT integrity miss. Workforce-provisioning incompleteness
  # (empty depts for an interview-incomplete client, floor-fill for a box with no
  # workforce, a dept below the 95% floor) is surfaced as an ADVISORY and driven to
  # completion by the POST-stamp qc-completeness run + the onboarding-resume cron --
  # it NO LONGER withholds the content stamp (the ~11-box "content current but
  # unstamped" defect this release fixes).
  #
  # STAMP-GATING (content/wiring integrity -- WITHHOLD the stamp on fail):
  #   - A3 content-gate (above): installed skill digests == source digests.
  #   - _U6B_PERSONA_FAIL: persona-index CONTENT wiring -- triad-divergent library,
  #     asset lacking vectors, installed sentinel != manifest release_tag (installed
  #     persona content does NOT match the pinned tag), or the provision helper
  #     genuinely did not run.
  #   - _D2_REFRESH_STATUS: refresh-stale-roles.py rc 3 -- an IN-SCOPE role/SOP
  #     content refresh that SHOULD have re-applied the new library content to an
  #     EXISTING artifact genuinely failed. (Out-of-scope / MISSING / floor-fill
  #     rows exit 0 and never land here.)
  #   - _D2_DEPTSCRIPTS_STATUS: refresh-dept-scripts.py rc 3 (FIX-DELIVERY-02) --
  #     a MATERIALIZED department's canonical scripts/ file (.py/.sh/.js/.tpl/.sha256/.pdf)
  #     was missing or hash-diverged from the role library AFTER this run's own
  #     copy step -- an incomplete/sabotaged mirror. (A department not yet
  #     materialized on this box is a benign skip and never lands here.)
  #   - _U6C_SOPLIB_FAIL: SOP V2 library CONTENT population (U6c) -- the ingester
  #     is missing, failed, or ran and left the `sops` table below the manifest's
  #     canonical population. A box whose SOP database is a demo fixture must
  #     never be stamped as current: that is the 24-of-2578 defect this closes.
  #   - _U6D_CC_CONFIG_FAIL: Command Center runtime departments + branding (U6d)
  #     tooling was unavailable (python3 missing / reconciler script missing), or
  #     the reconciler returned success but independent re-assertion still found
  #     empty departments or the exact placeholder companyName. (U6D-CC-RUNTIME
  #     fix, 2026-08-04: a genuine reconciler FAILURE (rc!=0, invalid/corrupt existing
  #     CC data, or an unprovisioned box) is CC-side runtime config, not skills
  #     content -- it no longer lands here; see _U6D_CC_RUNTIME_FATAL and
  #     _WORKFORCE_INCOMPLETE_NOTES at the U6d call site instead.)
  #   - _SHAREDCORE_STATUS: link_shared_core_files wiring step errored.
  #   - _SHAREDUTILS_STATUS: shared-utils/ refresh landed incomplete (a source
  #     top-level entry — e.g. sop-embed-once/ — is missing from the box). This tree
  #     is NOT covered by the A3 numbered-skill content-gate, so it is gated here.
  # NOT STAMP-GATING (workforce provisioning -- advisory only): _D2_MIGRATE_STATUS,
  #   _D5_ACTIVATION_PASS (handled in the advisory block below).
  # ----------------------------------------------------------
  if [ "${_U6B_PERSONA_FAIL:-0}" -eq 1 ]; then
    _STEP_GATE_FAILS="${_STEP_GATE_FAILS}  - persona index (U6b, provision-persona-index.sh): content incomplete${_PIDX_SKIP_WARNINGS:+ — ${_PIDX_SKIP_WARNINGS}}\n"
  fi
  if [ "${_U6C_SOPLIB_FAIL:-0}" -eq 1 ]; then
    _STEP_GATE_FAILS="${_STEP_GATE_FAILS}  - SOP V2 library (U6c, ingest-sop-library.sh): the SOP DATABASE was not populated${_U6C_SOPLIB_NOTE:+ — ${_U6C_SOPLIB_NOTE}}\n"
  fi
  if [ "${_U6D_CC_CONFIG_FAIL:-0}" -eq 1 ]; then
    _STEP_GATE_FAILS="${_STEP_GATE_FAILS}  - Command Center runtime config (U6d, reconcile_command_center_runtime.py): departments/branding not populated${_U6D_CC_CONFIG_NOTE:+ — ${_U6D_CC_CONFIG_NOTE}}\n"
  fi
  if [ "${_D2_REFRESH_STATUS:-ok}" != "ok" ]; then
    _STEP_GATE_FAILS="${_STEP_GATE_FAILS}  - in-scope role/SOP content refresh (D2, refresh-stale-roles.py rc 3): an in-scope refresh that SHOULD have applied did not — see $LOG_FILE\n"
  fi
  if [ "${_D2_DEPTSCRIPTS_STATUS:-ok}" != "ok" ]; then
    _STEP_GATE_FAILS="${_STEP_GATE_FAILS}  - department scripts/ mirror (FIX-DELIVERY-02, refresh-dept-scripts.py rc 3): a materialized department's canonical scripts/ file did not verify after the copy step — see $LOG_FILE\n"
  fi
  if [ "${_SHAREDCORE_STATUS:-ok}" != "ok" ]; then
    _STEP_GATE_FAILS="${_STEP_GATE_FAILS}  - shared core file unification (link_shared_core_files): incomplete\n"
  fi
  if [ "${_SHAREDUTILS_STATUS:-ok}" != "ok" ]; then
    _STEP_GATE_FAILS="${_STEP_GATE_FAILS}  - shared-utils refresh (cp -r shared-utils): incomplete — source files missing from box (recursive check); not covered by the A3 numbered-skill gate\n"
  fi
  if [ "${_UNIVERSALSOPS_STATUS:-ok}" != "ok" ]; then
    _STEP_GATE_FAILS="${_STEP_GATE_FAILS}  - universal-sops refresh (rm -rf + cp -r universal-sops): incomplete — source SOPs missing from box; not covered by the A3 numbered-skill gate\n"
  fi

  # WORKFORCE-provisioning advisories (v20.0.10): recorded + surfaced, but they
  # NEVER withhold the content stamp. The POST-stamp qc-completeness run
  # (QC_COMPLETENESS_RC) and the onboarding-resume cron drive these to completion.
  if [ "${_D2_MIGRATE_STATUS:-ok}" != "ok" ]; then
    # v20.0.98: NEVER imply the interview is unfinished when the box's own state
    # records it as complete. A completed-interview box (interviewComplete=true)
    # that trips this is a role/SOP FLOOR-fill matter, not an interview matter —
    # the old "/ interview-incomplete" wording caused established clients (built
    # workforce, closeout done) to look like they had skipped the interview.
    _WF_STATE_FILE="${OC_WORKSPACE:-$HOME/.openclaw/workspace}/.workforce-build-state.json"
    _IV_DONE="$(jq -r '.interviewComplete // false' "$_WF_STATE_FILE" 2>/dev/null || echo false)"
    if [ "$_IV_DONE" = "true" ]; then
      _WORKFORCE_INCOMPLETE_NOTES="${_WORKFORCE_INCOMPLETE_NOTES}  - workforce floor-fill (migrate-existing-workforce.sh): interview COMPLETE (respected) — one or more departments are below the role/SOP floor; advisory only, does NOT withhold the stamp and does NOT re-run the interview — see $LOG_FILE\n"
    else
      _WORKFORCE_INCOMPLETE_NOTES="${_WORKFORCE_INCOMPLETE_NOTES}  - workforce floor-fill (migrate-existing-workforce.sh): workforce below floor (interview not yet marked complete for this box) — see $LOG_FILE\n"
    fi
  fi
  if [ "${_D5_ACTIVATION_PASS:-1}" -ne 1 ]; then
    _WORKFORCE_INCOMPLETE_NOTES="${_WORKFORCE_INCOMPLETE_NOTES}  - dept-agent activation (D5, materialize-dept-agents.sh): incomplete${_D5_NOTLIVE_DETAIL:+ — ${_D5_NOTLIVE_DETAIL}}\n"
  fi
  if [ -n "$_WORKFORCE_INCOMPLETE_NOTES" ]; then
    echo ""
    echo "  ------------------------------------------------------------"
    echo "  WORKFORCE-PROVISIONING INCOMPLETE (advisory — does NOT withhold the"
    echo "  skills-content stamp; this box IS on current $ONBOARDING_VERSION content):"
    printf '%b' "$_WORKFORCE_INCOMPLETE_NOTES"
    echo "  Driven to completion by the post-stamp qc-completeness run and the"
    echo "  onboarding-resume cron (re-fires wiring + QC until green)."
    echo "  ------------------------------------------------------------"
  fi

  # --- Claude Code subagent concurrency (operator directive 2026-08-14) -------
  # Merges CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS + CLAUDE_CODE_MAX_SUBAGENTS_PER_SESSION
  # into this box's Claude Code profile(s). Runs AFTER the shared-utils refresh so
  # the helper is present. Deliberately NON-GATING: a box with no Claude Code
  # profile, or an unparseable settings.json we refuse to touch, is an advisory —
  # it must never withhold the content stamp or fail a fleet roll. The helper is
  # idempotent, merge-only, backs up before writing, and restores on any failure.
  # It does NOT change the Workflow tool's per-run cap, which is computed from the
  # box's own CPU count (min(16, max(2, cores-2))) and reads no env var.
  _CCS_HELPER="${SKILLS_DIR:-$HOME/.openclaw/skills}/shared-utils/provision-claude-settings.sh"
  [ -f "$_CCS_HELPER" ] || _CCS_HELPER="${EXTRACTED_DIR:-}/shared-utils/provision-claude-settings.sh"
  if [ -f "$_CCS_HELPER" ]; then
    echo ""
    echo "  Provisioning Claude Code subagent concurrency (500 concurrent / 10000 per session)..."
    if ! bash "$_CCS_HELPER"; then
      echo "  ⚠️  Claude subagent-concurrency provisioning reported a problem (advisory — does NOT withhold the stamp)." >&2
    fi
  else
    echo "  ⚠️  provision-claude-settings.sh not found on this box — subagent concurrency left at platform defaults (advisory)." >&2
  fi

  if [ -n "$_STEP_GATE_FAILS" ]; then
    echo ""
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    echo "  CONTENT-COMPLETENESS GATE FAILED — stamp NOT written."
    echo "  The following skills-content integrity step(s) did not finish:"
    printf '%b' "$_STEP_GATE_FAILS"
    echo ""
    echo "  The version stamp is NEVER written when a content-integrity step fails."
    echo "  Re-run update-skills.sh to retry the incomplete step(s)."
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    rm -rf "$TEMP_EXTRACT" "$TEMP_ZIP"
    exit 1
  fi

  # ----------------------------------------------------------
  # A3: CONTENT-MANIFEST + VERSION-STAMP (v20.0.11 ROOT-CAUSE FIX for the fleet
  # false-"done" defect). Ordering is now MANIFEST-FIRST, STAMP-LAST:
  #
  #   Previously the .onboarding-version stamp was written UNCONDITIONALLY here,
  #   BEFORE the manifest, and the manifest write was (a) gated on a possibly-empty
  #   $SRC_MANIFEST (so it was silently SKIPPED whenever skill-content-hash.sh was
  #   unavailable in the source, i.e. the "legacy path" that also skips A3) and
  #   (b) swallowed with "... || echo WARN (non-fatal)" so a python3/mv failure
  #   left the box STAMPED but WITHOUT a manifest. check-updates.sh (A4) then reads
  #   a missing manifest as "first install — not an error" and reports the box
  #   CURRENT on a version match. Net effect: v20.0.x stamp over stale/unverifiable
  #   content that no drift-detector can ever catch (A4 needs the manifest to compare).
  #
  #   The stamp is a "content is current AND recorded" certificate. It must NEVER
  #   exist without a matching manifest. So we now: build + validate the manifest
  #   to a temp file, FAIL THE WHOLE UPDATE (withhold the stamp) if it cannot be
  #   written or committed, and only THEN drop the stamp as the LAST artifact.
  #   Even on the legacy path (empty $SRC_MANIFEST) we still emit a DEGRADED
  #   manifest (content_verified="unavailable", empty skills map) so the stamp is
  #   never orphaned and A4 can treat the box as degraded rather than silently current.
  # ----------------------------------------------------------
  _NOW_ISO="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  _MANIFEST_TMP=$(mktemp)
  _SKILLS_JSON=""
  _TREE_SHA="unknown"
  _CONTENT_VERIFIED="true"
  if [ -n "$SRC_MANIFEST" ]; then
    # Build the per-skill JSON block from the A2/A3 source manifest.
    while IFS='|' read -r _sn _sd; do
      [ -z "$_sn" ] && continue
      [[ "$_sn" == "__TREE_SHA__" ]] && continue
      case "$_sn" in *ARCHIVED*) continue ;; esac
      [ -n "$_SKILLS_JSON" ] && _SKILLS_JSON="${_SKILLS_JSON},"
      _SKILLS_JSON="${_SKILLS_JSON}\"${_sn}\":\"${_sd}\""
    done <<< "$SRC_MANIFEST"
    _TREE_SHA=$(echo "$SRC_MANIFEST" | grep "^__TREE_SHA__|" | cut -d'|' -f2 | head -1 || true)
    [ -z "$_TREE_SHA" ] && _TREE_SHA="unknown"
  else
    # Legacy path: skill-content-hash.sh was unavailable in source, so A3 was
    # skipped and there are no per-skill digests. Still emit a manifest so the
    # stamp is never orphaned; mark content unverifiable so A4 sees a degraded box.
    _CONTENT_VERIFIED="unavailable"
  fi

  # Build + validate the manifest to a temp file. A build failure is FATAL:
  # the stamp is withheld so this box is never reported "current" without a manifest.
  if ! python3 -c "
import json, sys
data = {
    'version': '${ONBOARDING_VERSION}',
    'src_git_sha': '${SRC_GIT_SHA:-unknown}',
    'src_from_zip': bool(${SRC_FROM_ZIP:-0}),
    'tree_sha': '${_TREE_SHA:-unknown}',
    'content_verified': '${_CONTENT_VERIFIED}',
    'installed_at': '${_NOW_ISO}',
    'skills': {${_SKILLS_JSON}},
    'activation': {
        'deptAgents': '${_D5_DEPT_STATE:-skipped}',
        'deptAgentCount': ${_D5_AGENT_COUNT:-0},
        'skillVerifyGate': '${ONBOARDING_GATE_OK:-pending-resume-cron}'
    }
}
with open('${_MANIFEST_TMP}', 'w') as f:
    json.dump(data, f, indent=2)
    f.write('\n')
"; then
    rm -f "$_MANIFEST_TMP"
    echo ""
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    echo "  A3 MANIFEST-WRITE FAILED — version stamp NOT written."
    echo "  Could not build the content-manifest companion file (python3 error)."
    echo "  The stamp is withheld so this box is never reported 'current' without a"
    echo "  matching manifest. Re-run update-skills.sh to retry."
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    rm -rf "$TEMP_EXTRACT" "$TEMP_ZIP"
    exit 1
  fi

  # Commit the manifest atomically. A commit failure is FATAL for the same reason.
  if ! mv "$_MANIFEST_TMP" "$SKILLS_DIR/.onboarding-content-manifest.json"; then
    rm -f "$_MANIFEST_TMP"
    echo ""
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    echo "  A3 MANIFEST-COMMIT FAILED — version stamp NOT written."
    echo "  Could not move the content-manifest into $SKILLS_DIR. Stamp withheld."
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    rm -rf "$TEMP_EXTRACT" "$TEMP_ZIP"
    exit 1
  fi

  # Post-write re-assertion: re-read and confirm tree_sha persisted intact. If the
  # manifest we just wrote is unreadable or diverged, the active dir was modified
  # mid-write — abort with the stamp STILL withheld.
  _RECHECK_TREE=$(python3 -c "import json; d=json.load(open('$SKILLS_DIR/.onboarding-content-manifest.json')); print(d.get('tree_sha',''))" 2>/dev/null || echo "")
  if [ "$_RECHECK_TREE" != "$_TREE_SHA" ]; then
    echo ""
    echo "  A3 POST-WRITE ASSERTION FAILED: tree_sha in manifest does not match what was just written."
    echo "  Expected: $_TREE_SHA  Found: ${_RECHECK_TREE:-<unreadable>}"
    echo "  Active dir may have been modified during the write — aborting (stamp withheld)."
    rm -rf "$TEMP_EXTRACT" "$TEMP_ZIP"
    exit 1
  fi

  # Manifest is committed and validated. NOW write the version stamp as the LAST
  # artifact — ordering guarantees a box is never stamped-without-manifest (the
  # exact false-"done" condition this fix eliminates).
  echo "$ONBOARDING_VERSION" > "$SKILLS_DIR/.onboarding-version"

  # Sync version marker to legacy locations if they exist.
  #
  # Bug E: $HOME/.openclaw/onboarding is DELIBERATELY EXCLUDED from this loop.
  # ONBOARDING_DIR is set (~line 2648: ONBOARDING_DIR="$EXTRACTED_DIR") to the
  # TEMP clone, which is `rm -rf`'d a few lines below (Cleanup) -- nothing in
  # this script ever refreshes $HOME/.openclaw/onboarding's CONTENT. It is
  # written once, by install.sh, during a full install, and never again. This
  # loop used to bump its .onboarding-version stamp anyway, which made a
  # stale tree advertise the current version -- the exact lie
  # reap_dead_skill_manifest() was written to kill for .skill-manifest.json.
  # A stale tree with a stale stamp is honest; a stale tree with a current
  # stamp is not. Do not delete the directory here (other things may read
  # it) -- just stop lying about its version.
  #
  # (Array, not a bare word -- keeps this extensible without a shellcheck
  # SC2066 "loop will only run once" false-flag on a single-element list.)
  _LEGACY_MARKERS=(
    "$HOME/Downloads/openclaw-master-files/.onboarding-version"
  )
  for _LEGACY_MARKER in "${_LEGACY_MARKERS[@]}"; do
    if [ -f "$_LEGACY_MARKER" ]; then
      echo "$ONBOARDING_VERSION" > "$_LEGACY_MARKER" 2>/dev/null || true
    fi
  done

  # Secondary check: verify the stamp was physically written (defense-in-depth)
  VERIFY_VER=$(cat "$SKILLS_DIR/.onboarding-version" 2>/dev/null | tr -d '[:space:]')
  if [ "$VERIFY_VER" != "$ONBOARDING_VERSION" ]; then
    echo ""
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    echo "  FAILURE: active skills dir was NOT updated!"
    echo "  Expected version : $ONBOARDING_VERSION"
    echo "  Found version    : ${VERIFY_VER:-<missing>}"
    echo "  Active dir       : $SKILLS_DIR"
    echo "  The running agent is still on the OLD skills."
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    rm -rf "$TEMP_EXTRACT" "$TEMP_ZIP"
    exit 1
  fi
  VERIFY_SKILL_COUNT=$(ls -d "$SKILLS_DIR"/[0-9]*/ 2>/dev/null | wc -l | tr -d ' ')
  if [ "$VERIFY_SKILL_COUNT" -eq 0 ]; then
    echo ""
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    echo "  FAILURE: no skill folders found in active dir after update!"
    echo "  Active dir : $SKILLS_DIR"
    echo "  The running agent is still on the OLD skills."
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    rm -rf "$TEMP_EXTRACT" "$TEMP_ZIP"
    exit 1
  fi

  # v14.24.0: Persist hooks/ library before temp-clone is removed.
  # lib-ceo-tool-gate.sh is resolved from ~/.openclaw/hooks/ (or
  # /data/.openclaw/hooks/ on VPS) after the temp clone is gone. Without this,
  # update-only boxes keep the pre-#398/#403 gate library until the next full
  # install.
  # NOTE 2026-08-05: lib-ceo-consent.sh used to be the other consumer named here.
  # It and ceo-intent-gate.sh were DELETED with the intent-gate removal, and the
  # copy below never prunes — see the UN-WIRE block right after it, which deletes
  # those two stale files from already-wired boxes.
  _OC_HOOKS_DEST="$HOME/.openclaw/hooks"
  [ -d "/data/.openclaw" ] && _OC_HOOKS_DEST="/data/.openclaw/hooks"
  mkdir -p "$_OC_HOOKS_DEST" 2>/dev/null || true
  if [ -d "$EXTRACTED_DIR/hooks" ]; then
    # Bug F: the old top-level `hooks/*.sh` glob was non-recursive (silently
    # dropped anything under a subdirectory) and always printed a bare ✓
    # regardless of whether the copy actually succeeded (`|| true` swallowed
    # the failure). Recursive copy of hooks/'s CONTENTS via the trailing
    # `/.` so subdirectories survive, and gate the ✓ on the copy's own exit
    # code -- advisory only, still never fails the roll.
    if cp -Rf "$EXTRACTED_DIR/hooks/." "$_OC_HOOKS_DEST/" 2>/dev/null; then
      find "$_OC_HOOKS_DEST" -type f -name '*.sh' -exec chmod +x {} + 2>/dev/null || true
      echo "  ✓ hooks/ library persisted to $_OC_HOOKS_DEST"
    else
      echo "  ✗ hooks/ library copy FAILED (source: $EXTRACTED_DIR/hooks, dest: $_OC_HOOKS_DEST) — advisory, does not fail the roll"
    fi
  fi

  # ----------------------------------------------------------
  # UN-WIRE the removed CEO intent-gate (2026-08-05, Trevor).
  #
  # The hook staging above is COPY-ONLY: `cp -Rf .../hooks/. "$_OC_HOOKS_DEST/"`
  # never prunes. So deleting hooks/ceo-intent-gate.sh and hooks/lib-ceo-consent.sh
  # from the REPO uninstalls NOTHING from a box that is already wired — the stale
  # files keep sitting in ~/.openclaw/hooks/ and, worse, the PreToolUse entry in
  # ~/.claude/settings.json keeps INVOKING them. That is precisely the write-deny
  # loop that ate two weeks of Telegram messages. Removing the installer is not
  # the same as uninstalling; a box has to be actively un-wired.
  #
  # Idempotent (a clean box changes nothing and prints nothing actionable) and
  # strictly NON-FATAL — an un-wire failure must never fail a roll.
  # ----------------------------------------------------------
  for _stale in ceo-intent-gate.sh lib-ceo-consent.sh; do
    for _stale_path in "$_OC_HOOKS_DEST/$_stale" "$_OC_HOOKS_DEST/$_stale".bak-*; do
      if [ -e "$_stale_path" ]; then
        if rm -f "$_stale_path"; then
          echo "  ✓ un-wired: removed stale $(basename "$_stale_path") from $_OC_HOOKS_DEST"
        else
          echo "  ⚠ could not remove $_stale_path — advisory, does not fail the roll"
        fi
      fi
    done
  done
  # NOTE on hooks/lib-ceo-tool-gate.sh — deliberately KEPT, not deleted.
  # It is NOT the loop: the loop was the PreToolUse hook (ceo-intent-gate.sh)
  # plus a non-empty production deny. The lib is now an EMPTY-DENY SHIM
  # (CEO_GATE_DENY_TOOLS=()) that still supplies two things nobody asked to
  # remove: CEO_GATE_ALLOW_TOOLS (a GRANT list, the opposite of a gate) and
  # CEO_GATE_MCP_PROVIDERS (the GHL MCP deny-by-provider, a separate brake that
  # keeps the router out of client CRM). scripts/grant-ceo-consent.sh sources it,
  # so deleting it would break that script for the second time in one change.
  # Its empty array is `set -u`-safe via the "${arr[*]:-}" guards in
  # ceo_gate_tools() — proven under /bin/bash 3.2.57, which is what the fleet runs.
  #
  # Residual production deny on the router: a box rolled BEFORE the retirement can
  # still carry write/edit/apply_patch in agents.list[].tools.deny. Nothing else
  # in this roll removes it (the stampers only ADD), so it is cleared here.
  # Claude settings: BOTH settings.json and settings.local.json are checked.
  for _cs in "${CLAUDE_SETTINGS_FILE:-$HOME/.claude/settings.json}" \
             "$HOME/.claude/settings.local.json"; do
    [ -f "$_cs" ] || continue
    CEO_UNWIRE_SETTINGS="$_cs" python3 <<'PY' || echo "  ⚠ ceo-intent-gate un-wire from $(basename "$_cs") FAILED — advisory, does not fail the roll"
import json, os, shutil, sys, time

path = os.environ["CEO_UNWIRE_SETTINGS"]
TARGET = "ceo-intent-gate.sh"
try:
    with open(path) as _f:
        cfg = json.load(_f)
except Exception as _e:
    print("  ⚠ settings.json unreadable or not JSON (%s) — left untouched" % _e)
    sys.exit(0)

hooks = cfg.get("hooks")
if not isinstance(hooks, dict):
    sys.exit(0)
pre = hooks.get("PreToolUse")
if not isinstance(pre, list):
    sys.exit(0)

removed = 0
new_pre = []
for group in pre:
    if not isinstance(group, dict):
        new_pre.append(group)
        continue
    # Flat form: the entry itself is the command hook.
    if TARGET in str(group.get("command", "")):
        removed += 1
        continue
    # Nested/matcher form: {"matcher": ..., "hooks": [{"command": ...}, ...]}
    inner = group.get("hooks")
    if isinstance(inner, list):
        kept = [h for h in inner
                if TARGET not in str(h.get("command", "") if isinstance(h, dict) else h)]
        dropped = len(inner) - len(kept)
        if dropped:
            removed += dropped
            if not kept:
                # the matcher group existed only to run the removed hook
                continue
            group = dict(group)
            group["hooks"] = kept
    new_pre.append(group)

if not removed:
    sys.exit(0)

if new_pre:
    hooks["PreToolUse"] = new_pre
else:
    hooks.pop("PreToolUse", None)
if not hooks:
    cfg.pop("hooks", None)

# Atomic write + timestamped backup: this is the user's live Claude settings.
_bak = "%s.bak.ceo-unwire-%s" % (path, time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()))
shutil.copy2(path, _bak)
_tmp = path + ".tmp.ceo-unwire"
with open(_tmp, "w") as _f:
    json.dump(cfg, _f, indent=2)
    _f.write("\n")
    _f.flush()
    os.fsync(_f.fileno())
os.replace(_tmp, path)
print("  ✓ un-wired: removed %d ceo-intent-gate PreToolUse entr%s from %s (backup: %s)"
      % (removed, "y" if removed == 1 else "ies", path, os.path.basename(_bak)))
PY
  done

  # Clear any RESIDUAL production deny left on the router by a pre-retirement roll.
  if [ -f "$OC_JSON" ]; then
    CEO_UNWIRE_OC_JSON="$OC_JSON" python3 <<'PY' || echo "  ⚠ residual CEO production-deny sweep FAILED — advisory, does not fail the roll"
import json, os, shutil, sys, time

path = os.environ["CEO_UNWIRE_OC_JSON"]
# The retired gate's production tools. GHL MCP globs are NOT in this set — that
# deny is a separate, still-wanted brake and must survive untouched.
RETIRED = {"write", "edit", "apply_patch", "browser", "canvas", "image", "process"}
ROUTER_IDS = {"main", "dept-ceo", "ceo", "master-orchestrator",
              "dept-master-orchestrator", "dept-executive-office"}

try:
    with open(path) as _f:
        cfg = json.load(_f)
except Exception as _e:
    print("  ⚠ openclaw.json unreadable or not JSON (%s) — left untouched" % _e)
    sys.exit(0)

def _is_router(ag):
    if not isinstance(ag, dict):
        return False
    if ag.get("is_master") is True:
        return True
    if isinstance(ag.get("role"), str) and ag["role"].strip().lower() == "router":
        return True
    return ag.get("id") in ROUTER_IDS

cleared = []
agents = (cfg.get("agents") or {}).get("list") or []
targets = [a for a in agents if _is_router(a)]
# agents.defaults can carry the same poison.
_defaults = (cfg.get("agents") or {}).get("defaults")
if isinstance(_defaults, dict):
    targets.append(_defaults)

for ag in targets:
    t = ag.get("tools")
    if not isinstance(t, dict) or not isinstance(t.get("deny"), list):
        continue
    keep = [x for x in t["deny"] if x not in RETIRED]
    if len(keep) != len(t["deny"]):
        gone = sorted(set(t["deny"]) - set(keep))
        if keep:
            t["deny"] = keep
        else:
            t.pop("deny", None)
        cleared.append("%s:[%s]" % (ag.get("id", "agents.defaults"), ",".join(gone)))

if not cleared:
    sys.exit(0)

_bak = "%s.bak.ceo-unwire-%s" % (path, time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()))
shutil.copy2(path, _bak)
_tmp = path + ".tmp.ceo-unwire"
with open(_tmp, "w") as _f:
    json.dump(cfg, _f, indent=2)
    _f.write("\n")
    _f.flush()
    os.fsync(_f.fileno())
os.replace(_tmp, path)
print("  ✓ un-wired: cleared the retired CEO production deny from %s (backup: %s)"
      % ("; ".join(cleared), os.path.basename(_bak)))
PY
  fi

  # Cleanup
  rm -rf "$TEMP_EXTRACT" "$TEMP_ZIP"

  # ----------------------------------------------------------
  # FIX 1: VERIFICATION GATE -- run the gate on EVERY non-archived skill.
  # A skill counts INSTALLED only if (a) openclaw skills info shows it,
  # (b) its CORE_UPDATES sentinel is present (if it ships one), and (c) its
  # qc-*.sh exits 0 (if it ships one). We DO NOT claim "installed/onboarded"
  # for un-registered skills. The "complete" Telegram below is CONDITIONAL on
  # this gate. ONBOARDING_GATE_OK / _SUMMARY drive the honest report.
  # ----------------------------------------------------------
  ONBOARDING_GATE_OK="unknown"
  ONBOARDING_GATE_SUMMARY=""
  if command -v obs_verify_skill >/dev/null 2>&1; then
    echo ""
    echo "  Running the per-skill VERIFICATION GATE (skills info + CORE_UPDATES sentinel + qc-*.sh)..."
    for _gskill in "$SKILLS_DIR"/[0-9]*/; do
      [ -d "$_gskill" ] || continue
      _gname="$(basename "$_gskill")"
      case "$_gname" in *ARCHIVED*) continue ;; esac
      if _greason="$(obs_verify_skill "$_gname" "$SKILLS_DIR")"; then
        echo "    ✓ verified-installed: $_gname"
      else
        echo "    ✗ NOT verified: $_gname -- ${_greason}"
      fi
    done
    ONBOARDING_GATE_SUMMARY="$(obs_gate_summary "$SKILLS_DIR" 2>/dev/null | grep '^GATE-HUMAN:' | sed 's/^GATE-HUMAN: //' || true)"
    if obs_gate_summary "$SKILLS_DIR" >/dev/null 2>&1; then
      ONBOARDING_GATE_OK="yes"
    else
      ONBOARDING_GATE_OK="no"
    fi
  else
    echo "  ⚠ verification gate unavailable (onboarding-state.sh not sourced) -- cannot honestly verify; will report file-sync only."
  fi

  echo ""
  echo "============================================"
  if [ "$ONBOARDING_GATE_OK" = "yes" ]; then
    echo "   Skills updated AND verified-installed."
  elif [ "$ONBOARDING_GATE_OK" = "no" ]; then
    echo "   Skills FILE-SYNCED to disk -- NOT all verified-installed yet."
    echo "   ${ONBOARDING_GATE_SUMMARY:-(gate summary unavailable)}"
    echo "   (The onboarding-resume cron will re-fire wiring + QC until all pass.)"
  else
    echo "   Skills file-synced to disk (verification gate did not run)."
  fi
  echo "   Version: $ONBOARDING_VERSION"
  echo "   Location: $SKILLS_DIR"
  echo "   Files on disk: $VERIFY_SKILL_COUNT skill folders confirmed in active dir"
  if [ -n "$ONLY_SKILLS" ]; then
    echo "   Mode: SELECTIVE -- only [$ONLY_SKILLS]"
    echo "   Skipped: $SKIPPED_COUNT other skills (not in --only list)"
  fi
  echo "============================================"

  # Mark the check timestamp so the catchup logic in future runs is accurate
  date -u +%Y-%m-%dT%H:%M:%SZ > "$SKILLS_DIR/.last-update-check" 2>/dev/null || true

  # ----------------------------------------------------------
  # U001-U003 SUNDAY TIMEZONE UNIFICATION (2026-07-23)
  #
  # Before this fix, two mechanisms could fire concurrently at 03:00 on
  # ET boxes: (a) a system crontab entry `0 3 * * 0` running in the
  # system's LOCAL timezone, and (b) this OpenClaw cron entry running in
  # America/New_York.  On ET they collided; on PT/UTC they did not
  # collide, but the inconsistency was a latent bug.
  #
  # Resolution:
  #   - U001's retire_legacy_sunday_crontab removes the system crontab
  #     entry via mutex, so cron(8) no longer fires any Sunday update on
  #     any box.
  #   - U003 confirms that the OpenClaw cron below is the ONE surviving
  #     mechanism, with an EXPLICIT America/New_York timezone.
  #
  #   Single mechanism -> no collision, deterministic timezone, and the
  #   self-heal heal_weekly_cron_updater (defined above at line 1468)
  #   repoints any stale on-disk cron scripts to the canonical root
  #   updater URL, so every box converges to this same path.
  #
  #   If the crontab is ever re-added (new box provision, operator manual
  #   edit), the U001-U003 duplicate-detection gate below calls
  #   retire_legacy_sunday_crontab to remove it again and WARNs the owner.
  #
  # ----------------------------------------------------------
  # U001-U003 DUPLICATE-DETECTION GATE: even though retire_legacy_sunday_crontab
  # runs at main() entry (above), someone could re-add a legacy Sunday crontab
  # entry after the lock is taken but before this cron registration. Re-detect
  # and re-retire to guarantee no collision at 03:00 ET on Sunday.
  # ----------------------------------------------------------
  if detect_legacy_sunday_crontab; then
    echo "  [crontab] WARNING: legacy Sunday '0 3 * * 0' crontab entry detected during update path — re-retiring"
    retire_legacy_sunday_crontab
  fi

  # Ensure the Sunday weekly update-check cron exists (idempotent)
  # Existing clients on pre-v9.2.0 won't have it; running the updater
  # backfills it.
  # ----------------------------------------------------------
  # JSON-exact cron presence check (fix/industry-gate-and-idempotent-crons):
  # `weekly-onboarding-update` is 24 chars — over the ~22-char threshold at
  # which `openclaw cron list`'s TEXT TABLE truncates names — so a text-grep
  # presence gate here false-negatives and re-adds a duplicate on every update
  # run (the same defect confirmed in Skill 39 / Skill 38's own registrars; see
  # shared-utils/cron-lib.sh). Sourced with an inline fallback so this update
  # pass never depends on a specific working directory.
  command -v oc_cron_present >/dev/null 2>&1 || {
    _lib_cron_present_uskl="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/shared-utils/cron-lib.sh"
    if [ -f "$_lib_cron_present_uskl" ]; then
      # shellcheck source=/dev/null
      source "$_lib_cron_present_uskl"
    fi
  }
  command -v oc_cron_present >/dev/null 2>&1 || oc_cron_present() {
    local _name="$1" _raw
    _raw=$(openclaw cron list --json 2>/dev/null) || _raw=""
    if [ -n "$_raw" ] && command -v jq >/dev/null 2>&1; then
      printf '%s' "$_raw" | jq -e --arg n "$_name" '
        ( if type == "array" then . else .jobs // [] end ) | map(select(.name == $n)) | length > 0
      ' >/dev/null 2>&1
      return $?
    fi
    if [ -n "$_raw" ] && command -v python3 >/dev/null 2>&1; then
      OC_CRON_RAW="$_raw" python3 - "$_name" 2>/dev/null <<'PYEOF'
import json, os, sys
name = sys.argv[1]
raw = os.environ.get("OC_CRON_RAW", "")
try:
    data = json.loads(raw)
except Exception:
    sys.exit(1)
jobs = data if isinstance(data, list) else data.get("jobs", [])
sys.exit(0 if any(j.get("name") == name for j in jobs) else 1)
PYEOF
      return $?
    fi
    return 1
  }
  # DURABLE TOMBSTONE fallback (fix/industry-gate-and-idempotent-crons,
  # live-VPS finding): fail OPEN (never tombstoned) if shared-utils/cron-lib.sh
  # wasn't found above — never block registration outright over a missing
  # helper file. The real oc_cron_tombstoned (durable file-marker check) is
  # used automatically when the shared lib IS found.
  command -v oc_cron_tombstoned >/dev/null 2>&1 || oc_cron_tombstoned() { return 1; }

  if command -v openclaw >/dev/null 2>&1 && oc_cron_tombstoned "weekly-onboarding-update"; then
    echo "  weekly-onboarding-update is TOMBSTONED (deliberately removed) — NOT re-registering. Un-tombstone: bash scripts/tombstone-cron.sh --remove weekly-onboarding-update"
  elif command -v openclaw >/dev/null 2>&1; then
    #=== BEGIN WEEKLY-CRON-FULL-REGISTRATION-V1 ===
    #=== BEGIN WEEKLY-CRON-MESSAGE-REFRESH-V1 ===
    # refresh_weekly_cron_message <job_id> <job_kind> <new_content>
    #
    # THE DRIFT BUG THIS CLOSES (2026-07-30): an EXISTING weekly-onboarding-update
    # cron (the "already installed" branch a few lines below) was never touched
    # again after creation. cron-prompt.txt could gain new RULES -- or drop a
    # pattern this same repo now calls a leak -- forever without a single
    # already-provisioned box ever seeing the change; only a box whose cron was
    # ABSENT, or still carried the old auto-announce wiring, ever got a fresh
    # payload. This function is the missing refresh path: it reads the job's
    # CURRENTLY STORED message via `openclaw cron get`, and only when that
    # differs from the freshly-fetched cron-prompt.txt does it patch the message
    # in place with `openclaw cron edit <id> --message` (or `--system-event` for
    # a systemEvent-kind job) -- confirmed via `openclaw cron edit --help` to be
    # a field-level PATCH ("Edit a cron job (patch fields)"), so schedule, tz,
    # sessionTarget, wakeMode, timeoutSeconds, and delivery are never touched
    # because they are never passed. Deliberately NOT delete+recreate: that would
    # require this function to already know every other field to preserve, and
    # getting even one wrong would silently reset it -- an in-place patch cannot.
    #
    # FAIL-SAFE: every step that can fail (CLI missing, gateway unreachable,
    # malformed JSON, python3 absent, edit rejected) is guarded and logs a
    # SKIP/WARN instead of propagating a nonzero exit -- this function always
    # returns 0 so it can never abort the enclosing `set -euo pipefail` run. A
    # failed refresh leaves the OLD message in place (stale-but-safe), never a
    # blank or partial one.
    command -v refresh_weekly_cron_message >/dev/null 2>&1 || refresh_weekly_cron_message() {
      local _job_id="$1" _job_kind="$2" _new_content="$3"
      if [ -z "$_job_id" ] || [ -z "$_new_content" ]; then
        echo "  [weekly-cron-refresh] SKIP — missing job id or empty new content; nothing changed"
        return 0
      fi
      if ! command -v openclaw >/dev/null 2>&1; then
        echo "  [weekly-cron-refresh] SKIP — openclaw CLI not found; nothing changed"
        return 0
      fi
      local _current_json=""
      _current_json=$(openclaw cron get "$_job_id" 2>/dev/null) || _current_json=""
      if [ -z "$_current_json" ]; then
        echo "  [weekly-cron-refresh] SKIP — could not read current cron job ($_job_id); nothing changed"
        return 0
      fi
      local _current_message=""
      if command -v python3 >/dev/null 2>&1; then
        _current_message=$(OC_CRON_JOB_JSON="$_current_json" python3 - <<'PYEOF' 2>/dev/null
import json, os
raw = os.environ.get("OC_CRON_JOB_JSON", "")
try:
    data = json.loads(raw)
except Exception:
    raise SystemExit(0)
payload = data.get("payload") or {}
msg = payload.get("message")
if msg is None:
    msg = payload.get("systemEvent")
print(msg if isinstance(msg, str) else "", end="")
PYEOF
) || _current_message=""
      fi
      if [ -z "$_current_message" ]; then
        echo "  [weekly-cron-refresh] SKIP — could not parse current message from cron get output; nothing changed"
        return 0
      fi
      if [ "$_current_message" = "$_new_content" ]; then
        echo "  [weekly-cron-refresh] OK — cron-prompt.txt content already current, no rewrite needed"
        return 0
      fi
      local -a _edit_flags=(--message "$_new_content")
      if [ "$_job_kind" = "systemEvent" ]; then
        _edit_flags=(--system-event "$_new_content")
      fi
      if openclaw cron edit "$_job_id" "${_edit_flags[@]}" >/dev/null 2>&1; then
        echo "  [weekly-cron-refresh] DONE — refreshed stale cron message from current cron-prompt.txt (schedule/tz/sessionTarget/delivery untouched -- cron edit patches only the flags passed)"
      else
        echo "  [weekly-cron-refresh] WARN — cron edit rejected/failed; message left as-is (stale but safe), will retry next run"
      fi
      return 0
    }
    #=== END WEEKLY-CRON-MESSAGE-REFRESH-V1 ===

    # CRON REWRITE MIGRATION (fix/existing-box-cron-rewrite v14.19.1):
    # Boxes provisioned BEFORE the silent-cron fix (v14.10.2) carry the OLD
    # weekly-onboarding-update cron wired with --announce --channel telegram
    # --to <client-chat-id>.  The scheduler auto-delivers the raw maintenance
    # prompt into the CLIENT's Telegram chat every Sunday — internal operator
    # traffic the client was never meant to see.  A plain "already installed"
    # skip leaves the leaking cron in place.  Fix: detect old delivery wiring
    # via openclaw cron list --json and delete the stale entry so the creation
    # block below always lands the SILENT main-session form.
    if oc_cron_present "weekly-onboarding-update"; then
      _CRON_HAS_OLD_WIRING=false
      if command -v python3 >/dev/null 2>&1; then
        _OC_RAW_JSON=$(openclaw cron list --json 2>/dev/null) || _OC_RAW_JSON=""
        if [ -n "$_OC_RAW_JSON" ] && \
           OC_CRON_JSON="$_OC_RAW_JSON" python3 - <<'PYEOF' 2>/dev/null
import json, os, sys
raw = os.environ.get('OC_CRON_JSON', '')
try:
    data = json.loads(raw)
except Exception:
    sys.exit(1)
jobs = data if isinstance(data, list) else data.get('jobs', [])
for j in jobs:
    if j.get('name') == 'weekly-onboarding-update':
        dl = j.get('delivery') or {}
        if dl.get('mode') == 'announce' or dl.get('to'):
            sys.exit(0)  # old auto-announce wiring detected
sys.exit(1)
PYEOF
        then
          _CRON_HAS_OLD_WIRING=true
        fi
      fi
      if [ "$_CRON_HAS_OLD_WIRING" = "true" ]; then
        echo "  ↻ Existing weekly-onboarding-update cron has old auto-announce delivery — deleting for silent-form recreate"
        openclaw cron delete --name "weekly-onboarding-update" >/dev/null 2>&1 || true
        # Fall through to creation block below (cron is now absent)
      else
        echo "  ✓ Sunday weekly update-check cron already installed (SILENT — no client auto-announce)"
        # Refresh the stored message from the CURRENT cron-prompt.txt so a RULE
        # change in the repo actually reaches a box whose cron already exists --
        # see refresh_weekly_cron_message above; this branch used to be a
        # permanent no-op, the confirmed root cause of the RULE 5.6 drift.
        _WOU_JOB_ID=""
        _WOU_JOB_KIND=""
        if [ -n "${_OC_RAW_JSON:-}" ] && command -v python3 >/dev/null 2>&1; then
          _WOU_ID_KIND=$(OC_CRON_JSON="$_OC_RAW_JSON" python3 - <<'PYEOF' 2>/dev/null
import json, os
raw = os.environ.get('OC_CRON_JSON', '')
try:
    data = json.loads(raw)
except Exception:
    raise SystemExit(0)
jobs = data if isinstance(data, list) else data.get('jobs', [])
for j in jobs:
    if j.get('name') == 'weekly-onboarding-update':
        print("%s\t%s" % (j.get('id', ''), (j.get('payload') or {}).get('kind', '')))
        break
PYEOF
) || _WOU_ID_KIND=""
          IFS=$'\t' read -r _WOU_JOB_ID _WOU_JOB_KIND <<< "$_WOU_ID_KIND" || true
        fi
        if [ -n "$_WOU_JOB_ID" ]; then
          _WOU_PROMPT_TMP="/tmp/openclaw-cron-refresh-check-$$.txt"
          if curl -fsSL --max-time 15 "https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/cron-prompt.txt" -o "$_WOU_PROMPT_TMP" 2>/dev/null && [ -s "$_WOU_PROMPT_TMP" ]; then
            refresh_weekly_cron_message "$_WOU_JOB_ID" "$_WOU_JOB_KIND" "$(cat "$_WOU_PROMPT_TMP")"
          else
            echo "  [weekly-cron-refresh] SKIP — could not fetch cron-prompt.txt; nothing changed"
          fi
          rm -f "$_WOU_PROMPT_TMP" 2>/dev/null || true
        else
          echo "  [weekly-cron-refresh] SKIP — could not resolve job id for weekly-onboarding-update; nothing changed"
        fi
      fi
    fi
    # Create cron only when it is absent (never existed, or just deleted above)
    if ! oc_cron_present "weekly-onboarding-update"; then
      # ── SILENT-OPERATOR-CRON RULE (chore/silent-operator-crons) ───────────
      # weekly-onboarding-update is a MAINTENANCE/update-check cron, NOT an
      # owner-facing announcement. The old form registered it
      # `--session isolated --announce --channel telegram --to <owner-chat>`,
      # so the scheduler AUTO-DELIVERED the raw update-check prompt into the
      # CLIENT chat every Sunday — internal operator traffic the owner was never
      # meant to see (the leak OPERATOR-MAINTENANCE.md forbids). NOTE: the old
      # `isolated + --announce + --channel` shape is ALSO rejected by the gateway
      # on some builds (confirmed live; see 35-social-media-planner/INSTRUCTIONS.md).
      #
      # FIX: register a SILENT main-session agent-message cron — `--agent main
      # --session-target main --light-context` with NO --channel/--to/--announce.
      # The update-check runs in the agent's OWN context (log-only); the agent
      # then decides, via its own deliberate `openclaw message send`, whether to
      # surface an owner-facing "an update is available, may I apply it?" question.
      # Nothing is auto-pushed to the client. No owner target needed, so the old
      # operator-ID resolver/guard is removed entirely. Mirrors install.sh Step 12.
      PROMPT_TMP="/tmp/openclaw-cron-prompt-$$.txt"
      REPO_URL="https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main"
      # Unified repo: same URL for both Mac and VPS platforms
      if curl -fsSL --max-time 15 "${REPO_URL}/cron-prompt.txt" -o "$PROMPT_TMP" 2>/dev/null && [ -s "$PROMPT_TMP" ]; then
        PROMPT_CONTENT=$(cat "$PROMPT_TMP")
        # fix/cron-flag-skew: define the runtime-compatible cron helper on the
        # guaranteed path to the create below (the resume-cron lib that also
        # defines it is sourced inside a conditional block above, so we re-guard
        # it here — its definition wins if already present). Emits the flags the
        # INSTALLED runtime accepts: 2026.6.11+ needs `--session main
        # --system-event`; older CLIs `--session-target main --message`.
        command -v _oc_cron_silent_main >/dev/null 2>&1 || _oc_cron_silent_main() {
          local _name="$1" _agent="$2" _expr="$3" _tz="$4" _prompt="$5"; shift 5
          local _extra=( "$@" ); local _n=${#_extra[@]}
          local _base=( --name "$_name" --agent "$_agent" --cron "$_expr" --tz "$_tz" )
          local _help _modern=0
          _help="$(openclaw cron add --help 2>&1 || true)"
          printf '%s' "$_help" | grep -qE '^[[:space:]]*--session[[:space:]<]' && _modern=1
          local _order _k
          if [ "$_modern" = "1" ]; then _order="modern old"; else _order="old modern"; fi
          for _k in $_order; do
            if [ "$_k" = "modern" ]; then
              [ "$_n" -gt 0 ] && openclaw cron create "${_base[@]}" "${_extra[@]}" --session main --system-event "$_prompt" >/dev/null 2>&1 && return 0
              openclaw cron create "${_base[@]}" --session main --system-event "$_prompt" >/dev/null 2>&1 && return 0
            else
              [ "$_n" -gt 0 ] && openclaw cron create "${_base[@]}" "${_extra[@]}" --session-target main --message "$_prompt" >/dev/null 2>&1 && return 0
              openclaw cron create "${_base[@]}" --session-target main --message "$_prompt" >/dev/null 2>&1 && return 0
            fi
          done
          openclaw cron create "$_expr" "$_prompt" --name "$_name" --agent "$_agent" --tz "$_tz" --session main >/dev/null 2>&1 && return 0
          openclaw cron create "${_base[@]}" --message "$_prompt" --no-deliver >/dev/null 2>&1 && return 0
          return 1
        }
        # Runtime-compatible SILENT main-session cron (fix/cron-flag-skew). The
        # 2026.6.11 runtime rejects `--session-target` and requires
        # `--session main --system-event` for main-session jobs; the old two-branch
        # form only ever emitted `--session-target main --message`, so a rolled box
        # silently installed NO weekly cron. _oc_cron_silent_main probes the CLI,
        # emits the accepted form, and degrades gracefully (never hard-fails).
        _WEEKLY_DESC="Sunday 3am ET -- SILENT update-check: look for OpenClaw onboarding + command-center updates; ask the owner permission (via your own message send) before applying anything."
        if _oc_cron_silent_main "weekly-onboarding-update" "main" "0 3 * * 0" "America/New_York" "$PROMPT_CONTENT" \
             --description "$_WEEKLY_DESC" --exact --light-context --thinking high --timeout-seconds 7200; then
          echo "  ✓ Sunday weekly update-check cron installed (Sundays 3am ET, SILENT main-session — no client auto-announce)"
        else
          echo "  ⚠ Cron install failed -- agent can retry manually (SILENT main-session form)"
        fi
        rm -f "$PROMPT_TMP"
      else
        echo "  ⚠ Could not fetch cron-prompt.txt -- agent can install cron manually later"
      fi
    fi
    #=== END WEEKLY-CRON-FULL-REGISTRATION-V1 ===
  fi

  # ----------------------------------------------------------
  # v12.34.0 (ZHC-EXPERIENCE fix BREAK #1): (RE)INSTALL THE PIPELINE TRIGGER CRONS.
  # The fleet HOT-PATCH path used to register ONLY weekly-onboarding-update — so a
  # box patched only via update-skills.sh got the new Skill 37 files but NO
  # closeout trigger, and silently depended on a prior full install.sh run. This
  # call backfills ALL pipeline trigger crons (workforce-build-resume,
  # interview-nudge, closeout-readiness-watchdog, closeout-resume) idempotently,
  # so files AND triggers now land together on the hot-patch path. Shared
  # registrar — the SAME script install.sh runs at end of run.
  # ----------------------------------------------------------
  echo ""
  echo "  Ensuring pipeline trigger crons (closeout experience triggers — hot-patch parity with install.sh)..."
  # BUG-FIX v13.0.1: this block runs AFTER the "# Cleanup" rm -rf "$TEMP_EXTRACT"
  # that wipes the freshly-pulled clone ($ONBOARDING_DIR/$EXTRACTED_DIR). On the
  # SUCCESS path $ONBOARDING_DIR no longer exists here, so resolve the persistent
  # copy first (stashed to ~/.openclaw/scripts during the install phase, before
  # cleanup). Fall back to the clone path / legacy path for older bundles.
  _PERSIST_SCRIPTS="${OC_PERSISTENT_SCRIPTS_DIR:-}"
  if [ -z "$_PERSIST_SCRIPTS" ]; then
    _PERSIST_SCRIPTS="$HOME/.openclaw/scripts"
    [ -d "/data/.openclaw" ] && _PERSIST_SCRIPTS="/data/.openclaw/scripts"
  fi
  ENSURE_CRONS="$_PERSIST_SCRIPTS/ensure-pipeline-crons.sh"
  [ -f "$ENSURE_CRONS" ] || ENSURE_CRONS="$ONBOARDING_DIR/scripts/ensure-pipeline-crons.sh"
  [ -f "$ENSURE_CRONS" ] || ENSURE_CRONS="$SKILLS_DIR/../onboarding/scripts/ensure-pipeline-crons.sh"
  if [ -f "$ENSURE_CRONS" ]; then
    if bash "$ENSURE_CRONS" >> "$LOG_FILE" 2>&1; then
      echo "  ✓ Pipeline trigger crons asserted (closeout has at least one live trigger)"
    else
      echo "  ⚠ ensure-pipeline-crons.sh returned non-zero — one or more pipeline crons not registered (see $LOG_FILE). Re-run to backfill."
    fi
  else
    echo "  ⚠ ensure-pipeline-crons.sh not found — pipeline cron backfill skipped (older bundle?). Closeout trigger may be absent on this box."
  fi

  # ----------------------------------------------------------
  # CEO gate removed 2026-08-05 per Trevor -- was creating loops; see openclaw-telegram-master-plan.md
  # U134 -- Fleet tool allowlist config-patch step (DISABLED).
  # ----------------------------------------------------------
  echo ""
  echo "  CEO tool deny gate removed 2026-08-05 -- U134 step skipped"
  # The u134 script itself is a no-op (keep-safe SKIP) if ever called.

  # Fleet standards: ensure sub-agents fully permitted + Telegram media 50MB
  # (idempotent -- applied on every update, no-op if already canonical)
  # ----------------------------------------------------------
  # Capture openclaw.json hash BEFORE any config mutations so the conditional
  # gateway-restart gate at the end of this section can tell whether anything
  # actually changed (avoids a disruptive restart on a no-op update).
  _OC_CONFIG_HASH_BEFORE=""
  if [ -f "$OC_JSON" ]; then
    _OC_CONFIG_HASH_BEFORE=$(python3 -c "import hashlib; print(hashlib.md5(open('$OC_JSON','rb').read()).hexdigest())" 2>/dev/null || true)
  fi
  echo ""
  echo "  Applying fleet standards (sub-agents fully permitted, Telegram media 50MB)..."
  # BUG-FIX v13.0.1: prefer the persistent copy — $ONBOARDING_DIR (the clone) was
  # already removed by the "# Cleanup" rm -rf above on the success path, which is
  # why this previously printed "Fleet standards script not found" on EVERY
  # successful update. Fall back to the clone path for older/edge bundles.
  FLEET_STD="$_PERSIST_SCRIPTS/apply-fleet-standards.sh"
  [ -f "$FLEET_STD" ] || FLEET_STD="$ONBOARDING_DIR/scripts/apply-fleet-standards.sh"
  if [ -f "$FLEET_STD" ]; then
    # v21.4.41: redirect to LOG_FILE instead of /dev/null (was discarding ALL
    # output, including the AGENTS.md dedup step's greppable one-line summary
    # -- see scripts/dedup-agents-md.py, wired inside apply-fleet-standards.sh
    # 5a-DEDUP). Surfacing to LOG_FILE lets post-roll verification `grep` for
    # it without spamming this console with the full config-merge dump.
    if bash "$FLEET_STD" >> "$LOG_FILE" 2>&1; then
      echo "  ✓ Fleet standards applied"
    else
      echo "  ⚠ Fleet standards application reported errors (update continues)"
    fi
    _DEDUP_LOG_LINE="$(grep -m1 '^\[apply-fleet-standards\] \[AGENTS DEDUP\]' "$LOG_FILE" 2>/dev/null || true)"
    [ -n "$_DEDUP_LOG_LINE" ] && echo "  (check) $_DEDUP_LOG_LINE"
  else
    echo "  ⚠ Fleet standards script not found"
  fi

  # ----------------------------------------------------------
  # v14.24.0: Operator Telegram channel separation (mirrors install.sh:7113-7124).
  # configure-operator-telegram.sh is idempotent; it emits a machine-readable
  # STATUS: operator-telegram=<state> line for honest reporting.
  # ----------------------------------------------------------
  echo ""
  echo "  Configuring operator Telegram channel separation..."
  _OPTG="$_PERSIST_SCRIPTS/configure-operator-telegram.sh"
  [ -f "$_OPTG" ] || _OPTG="$ONBOARDING_DIR/scripts/configure-operator-telegram.sh"
  if [ -f "$_OPTG" ]; then
    _OPTG_OUT="$(bash "$_OPTG" 2>&1)" || true
    _OPTG_STATUS="$(printf '%s\n' "$_OPTG_OUT" | grep -E '^STATUS:' | tail -1 || true)"
    case "$_OPTG_STATUS" in
      *=CONFIGURED*)                  echo "  ✓ Operator Telegram separation live (${_OPTG_STATUS})" ;;
      *STRUCTURE_ONLY_NEEDS_TOKEN*)   echo "  ⚠ Operator Telegram structure written; bot token still needed (${_OPTG_STATUS})" ;;
      *VALIDATE_FAILED*)              echo "  ⚠ Operator Telegram merge failed validation + rolled back (${_OPTG_STATUS})" ;;
      *)                              echo "  ℹ Operator Telegram config ran (${_OPTG_STATUS:-(no STATUS line)})" ;;
    esac
  else
    echo "  ⚠ configure-operator-telegram.sh not found — skipping"
  fi

  # ----------------------------------------------------------
  # v14.24.0: Install hardening (mirrors install.sh:6770-6776).
  # Idempotent + non-blocking: hooks.token auto-gen, brew check, media tools.
  # ----------------------------------------------------------
  echo ""
  echo "  Running install hardening (hooks.token, brew check, media tools)..."
  _HARDENING="$_PERSIST_SCRIPTS/install-hardening.sh"
  [ -f "$_HARDENING" ] || _HARDENING="$ONBOARDING_DIR/scripts/install-hardening.sh"
  if [ -f "$_HARDENING" ]; then
    bash "$_HARDENING" 2>&1 | tail -5 || true
    echo "  ✓ Install hardening complete"
  else
    echo "  ℹ install-hardening.sh not in bundle — skipping (older bundle, harmless)"
  fi

  # ----------------------------------------------------------
  # v14.24.0: Sane heartbeat defaults (mirrors install.sh Fix D / Fix D2).
  # CONDITIONAL: only sets when unset or below 6h threshold.
  # ----------------------------------------------------------
  echo ""
  echo "  Ensuring heartbeat defaults (6h min, main-only, capped tokens)..."
  _ENSURE_HB="$_PERSIST_SCRIPTS/ensure-heartbeat-defaults.sh"
  [ -f "$_ENSURE_HB" ] || _ENSURE_HB="$ONBOARDING_DIR/scripts/ensure-heartbeat-defaults.sh"
  if [ -f "$_ENSURE_HB" ]; then
    bash "$_ENSURE_HB" 2>&1 || true
  else
    echo "  ℹ ensure-heartbeat-defaults.sh not in bundle — skipping"
  fi

  # ----------------------------------------------------------
  # Built-in per-turn tool-loop detector: ENSURE tools.loopDetection.enabled=true
  # (v20.0.101). OpenClaw ships this key OFF by default — tools.loopDetection.enabled
  # defaults to false (docs.openclaw.ai/tools/loop-detection) — so the per-turn
  # loop detector is disabled on every box out of the box. With it OFF a model that
  # falls into a repeated (tool, args, result) loop runs UNSUPERVISED; the runaway
  # model loop that motivated this fix ran ~46 minutes. With it ON, OpenClaw watches
  # the rolling tool-call history every turn and ABORTS a repeated (tool,args,result)
  # loop (plus a post-compaction guard) in seconds. This step corrects the default to
  # ON, fleet-wide, on every roll.
  #
  # SAFETY-ADDITIVE + NON-FATAL. It uses the validated CLI writer
  # `openclaw config set` — NEVER a root file edit of openclaw.json (writing the
  # config as root freezes the box). OpenClaw itself performs the atomic,
  # schema-validated, single-key write, so it touches ONLY tools.loopDetection.enabled
  # — no models, no routing (primary/fallbacks), no credentials, and no other key is
  # read, reordered, or clobbered. Idempotent: when the key is already true this is a
  # read-only no-op (no write, so the conditional gateway-restart gate below does not
  # fire). GUARDED for old versions: `openclaw config set` validates its own input and
  # exits non-zero if the key is unknown on an older build (or the value is invalid),
  # in which case we DEGRADE to a logged note and CONTINUE — this must NEVER block the
  # roll or the version stamp (same convention as the other ensure-* steps here and
  # the v20.0.99/100 "an optional step must never abort before the stamp" fixes; note
  # this step runs AFTER the stamp, so it structurally cannot withhold it either).
  # ----------------------------------------------------------
  echo ""
  echo "  Ensuring built-in per-turn tool-loop detector is ON (tools.loopDetection.enabled=true)..."
  if command -v openclaw >/dev/null 2>&1; then
    _LD_CUR="$(openclaw config get tools.loopDetection.enabled 2>/dev/null | tr -d '[:space:]' || true)"
    if [ "$_LD_CUR" = "true" ]; then
      echo "  ✓ tools.loopDetection.enabled already true — no change (idempotent no-op)"
    elif openclaw config set tools.loopDetection.enabled true >>"$LOG_FILE" 2>&1; then
      _LD_NOW="$(openclaw config get tools.loopDetection.enabled 2>/dev/null | tr -d '[:space:]' || true)"
      if [ "$_LD_NOW" = "true" ]; then
        echo "  ✓ tools.loopDetection.enabled set to true — per-turn tool-loop detector now ON"
      else
        echo "  ✓ tools.loopDetection.enabled write applied (read-back inconclusive; see $LOG_FILE)"
      fi
    else
      echo "  ℹ Could not set tools.loopDetection.enabled — this OpenClaw build may not support the key"
      echo "    (older version) or rejected the value. Skipping; update continues. Enable it manually with"
      echo "    'openclaw config set tools.loopDetection.enabled true' once on a supported build."
      echo "    Reference: docs.openclaw.ai/tools/loop-detection"
    fi
  else
    echo "  ℹ openclaw CLI not on PATH — skipping loopDetection enablement (update continues)."
  fi

  # ----------------------------------------------------------
  # FLEET MEMORY STANDARDIZATION (v21.2.0) — kills the dark-memory default
  # gap fleet-wide. Root cause: a box ran 17 days with a completely empty
  # embedding index because its qmd vector backend was stalled and the
  # memory-lancedb plugin was disabled — the memory pipeline was fully dark
  # (no recall of any past work) and NOTHING surfaced it. Per the loopDetection
  # precedent (v20.0.101, directly above), the fleet default must be ON, not
  # OFF — so every roll now converges the memory stack to a serveable,
  # always-on state:
  #
  #   (a) memory-lancedb plugin force-disabled when its entry exists
  #       (plugins.entries.memory-lancedb.enabled=false) — it was replaced by
  #       Google/OpenAI embeddings; a present-but-disabled entry is drift.
  #   (b) legacy qmd backend neutralized — the qmd tool (better-sqlite3
  #       backed) was retired 2026-07-23 (U132) and the code no longer
  #       invokes it, but a box may still carry the stale binary or a legacy
  #       qmd config key. When a Google or OpenAI key is configured AND qmd
  #       is present we log "qmd backend migrated to Google/OpenAI
  #       embeddings, skipping" and best-effort disable any legacy
  #       plugins.entries.qmd / memorySearch.qmd keys. The binary itself is
  #       NEVER touched.
  #   (c) embedding default standardized on google/gemini-embedding-2 when a
  #       Google key is SET (presence-only check — the key VALUE is never
  #       read, printed, or written; the provider apiKey stays where the box
  #       already has it), ensuring models.providers.google.models carries
  #       the gemini-embedding-2 entry and agents.defaults.memorySearch pins
  #       provider=gemini model=gemini-embedding-2. Falls back to
  #       openai/text-embedding-3-small when only an OpenAI key is set, and
  #       logs a non-blocking warning when NEITHER is set (never pins a
  #       keyless model — the v13.2.0 regression class).
  #   (d) dreaming ENABLED fleet-wide: plugins.entries.memory-core.enabled=true
  #       plus config.dreaming.enabled=true with the fleet-standard nightly
  #       schedule (frequency "0 3 * * *", timezone America/New_York).
  #
  # SAFETY-ADDITIVE + NON-FATAL, same contract as the loopDetection step:
  # every write goes through the schema-validated CLI writer
  # `openclaw config set` — NEVER a root file edit of openclaw.json. Each key
  # is pre-read and only written when different (idempotent no-op on a
  # converged box). On an older build that rejects a key the step logs a note
  # and CONTINUES — it can never block the roll or withhold the version
  # stamp (this step runs AFTER the stamp, so it structurally cannot). No
  # models, no routing (primary/fallbacks), and no credential VALUES are
  # touched. Any config mutation is picked up by the conditional
  # gateway-restart gate at the end of this section, which activates the
  # dreaming cron.
  # ----------------------------------------------------------
  echo ""
  echo "  Fleet memory standardization (kill qmd/LanceDB, standardize embeddings, enable dreaming)..."
  if command -v openclaw >/dev/null 2>&1; then
    # Presence-only helper: prints SET/NOT-SET for a provider apiKey WITHOUT
    # ever exposing the value. `openclaw config get` on a secret path can
    # echo the key, so output is swallowed and only the exit/success signal
    # and a length bucket are used.
    _ms_key_state() {
      local _raw
      _raw="$(openclaw config get "$1" 2>/dev/null || true)"
      _raw="$(printf '%s' "$_raw" | tr -d '[:space:]')"
      # A real key is never empty and never one of the CLI's null markers.
      if [ -n "$_raw" ] && [ "$_raw" != "null" ] && [ "$_raw" != "undefined" ] \
         && [ "$_raw" != '""' ] && [ "$_raw" != "''" ]; then
        echo "SET"
      else
        echo "NOT-SET"
      fi
    }

    _GOOGLE_KEY_STATE="$(_ms_key_state models.providers.google.apiKey)"
    _OPENAI_KEY_STATE="$(_ms_key_state models.providers.openai.apiKey)"

    # ── (a) memory-lancedb force-disable (only when the entry exists) ──────
    _LDB_PRESENT="$(openclaw config get plugins.entries.memory-lancedb 2>/dev/null | tr -d '[:space:]' || true)"
    if [ -n "$_LDB_PRESENT" ] && [ "$_LDB_PRESENT" != "null" ] && [ "$_LDB_PRESENT" != "undefined" ]; then
      _LDB_CUR="$(openclaw config get plugins.entries.memory-lancedb.enabled 2>/dev/null | tr -d '[:space:]' || true)"
      if [ "$_LDB_CUR" = "false" ]; then
        echo "  ✓ plugins.entries.memory-lancedb.enabled already false — no change (idempotent no-op)"
      elif openclaw config set plugins.entries.memory-lancedb.enabled false >>"$LOG_FILE" 2>&1; then
        echo "  ✓ memory-lancedb plugin force-disabled (replaced by Google/OpenAI embeddings)"
      else
        echo "  ℹ Could not disable memory-lancedb — older build may not support the key; update continues."
      fi
    else
      echo "  ✓ memory-lancedb entry not present — nothing to disable"
    fi

    # ── (b) legacy qmd backend neutralization ──────────────────────────────
    if command -v qmd >/dev/null 2>&1; then
      if [ "$_GOOGLE_KEY_STATE" = "SET" ] || [ "$_OPENAI_KEY_STATE" = "SET" ]; then
        echo "  ℹ qmd backend migrated to Google/OpenAI embeddings, skipping"
        # Legacy qmd config keys were superseded 2026-07-23. Best-effort
        # disable when present; ignore failures (key may not exist — that is
        # the converged state).
        for _QMD_KEY in plugins.entries.qmd.enabled memorySearch.qmd.enabled; do
          _QMD_CUR="$(openclaw config get "$_QMD_KEY" 2>/dev/null | tr -d '[:space:]' || true)"
          if [ "$_QMD_CUR" = "true" ]; then
            openclaw config set "$_QMD_KEY" false >>"$LOG_FILE" 2>&1 \
              && echo "  ✓ legacy qmd key $_QMD_KEY disabled" \
              || echo "  ℹ could not disable $_QMD_KEY (older build) — update continues"
          fi
        done
        unset _QMD_CUR _QMD_KEY
      else
        echo "  ⚠ qmd present but NO Google/OpenAI key set — qmd retired; set GOOGLE_API_KEY or OPENAI_API_KEY to restore memory search"
      fi
    fi

    # ── (c) embedding default standardization ──────────────────────────────
    if [ "$_GOOGLE_KEY_STATE" = "SET" ]; then
      # Ensure the gemini-embedding-2 entry is present in the Google provider
      # model list. --merge merges the object map instead of replacing the
      # whole provider block.
      _GMS_CUR="$(openclaw config get models.providers.google.models 2>/dev/null || true)"
      if printf '%s' "$_GMS_CUR" | grep -q '"gemini-embedding-2"' 2>/dev/null; then
        echo "  ✓ models.providers.google.models already includes gemini-embedding-2 — no change"
      elif openclaw config set models.providers.google.models \
          '[{"id":"gemini-embedding-2","name":"Gemini Embedding 2","input":["text"],"contextWindow":2048}]' \
          --strict-json >>"$LOG_FILE" 2>&1; then
        echo "  ✓ models.providers.google.models now includes gemini-embedding-2 (Gemini Embedding 2, text, 2048 ctx)"
      else
        echo "  ℹ Could not write models.providers.google.models — older build may reject the key; update continues."
      fi
      _MSP_CUR="$(openclaw config get agents.defaults.memorySearch.provider 2>/dev/null | tr -d '[:space:]' || true)"
      _MSM_CUR="$(openclaw config get agents.defaults.memorySearch.model 2>/dev/null | tr -d '[:space:]' || true)"
      if [ "$_MSP_CUR" = "gemini" ] && [ "$_MSM_CUR" = "gemini-embedding-2" ]; then
        echo "  ✓ agents.defaults.memorySearch already gemini/gemini-embedding-2 — no change"
      elif openclaw config set agents.defaults.memorySearch.provider gemini >>"$LOG_FILE" 2>&1 \
        && openclaw config set agents.defaults.memorySearch.model gemini-embedding-2 >>"$LOG_FILE" 2>&1; then
        echo "  ✓ agents.defaults.memorySearch standardized → gemini/gemini-embedding-2 (fleet default)"
      else
        echo "  ℹ Could not set agents.defaults.memorySearch — older build may reject the key; update continues."
      fi
      unset _GMS_CUR _MSP_CUR _MSM_CUR
    elif [ "$_OPENAI_KEY_STATE" = "SET" ]; then
      _MSM_CUR="$(openclaw config get agents.defaults.memorySearch.model 2>/dev/null | tr -d '[:space:]' || true)"
      if [ "$_MSM_CUR" = "text-embedding-3-small" ]; then
        echo "  ✓ agents.defaults.memorySearch already openai/text-embedding-3-small — no change"
      elif openclaw config set agents.defaults.memorySearch.provider openai >>"$LOG_FILE" 2>&1 \
        && openclaw config set agents.defaults.memorySearch.model text-embedding-3-small >>"$LOG_FILE" 2>&1; then
        echo "  ✓ agents.defaults.memorySearch standardized → openai/text-embedding-3-small (no Google key; fleet fallback)"
      else
        echo "  ℹ Could not set agents.defaults.memorySearch — older build may reject the key; update continues."
      fi
      unset _MSM_CUR
    else
      echo "  ⚠ No embedding provider configured — memory features will be degraded. Set GOOGLE_API_KEY or OPENAI_API_KEY."
    fi

    # ── (d) dreaming enablement (memory-core) ──────────────────────────────
    _MC_PRESENT="$(openclaw config get plugins.entries.memory-core 2>/dev/null | tr -d '[:space:]' || true)"
    if [ -n "$_MC_PRESENT" ] && [ "$_MC_PRESENT" != "null" ] && [ "$_MC_PRESENT" != "undefined" ]; then
      _MC_WAS="$(openclaw config get plugins.entries.memory-core.enabled 2>/dev/null | tr -d '[:space:]' || true)"
      if [ "$_MC_WAS" = "true" ]; then
        echo "  ✓ plugins.entries.memory-core.enabled already true — no change"
      elif openclaw config set plugins.entries.memory-core.enabled true >>"$LOG_FILE" 2>&1; then
        echo "  ✓ memory-core plugin enabled (dreaming memory-consolidation now active)"
        echo "    gateway reload (conditional restart below) registers the dreaming cron"
      else
        echo "  ℹ Could not enable memory-core — older build may not support the key; update continues."
      fi
      # Dreaming config: enabled + fleet-standard nightly schedule. Written
      # as one nested object via --strict-json only when not already enabled.
      _DRM_CUR="$(openclaw config get plugins.entries.memory-core.config.dreaming.enabled 2>/dev/null | tr -d '[:space:]' || true)"
      if [ "$_DRM_CUR" = "true" ]; then
        echo "  ✓ memory-core dreaming already enabled — no change"
      elif openclaw config set plugins.entries.memory-core.config.dreaming \
          '{"enabled":true,"frequency":"0 3 * * *","timezone":"America/New_York"}' \
          --strict-json >>"$LOG_FILE" 2>&1; then
        echo "  ✓ memory-core dreaming enabled (nightly 03:00 America/New_York)"
      else
        echo "  ℹ Could not write memory-core dreaming config — older build may not support the key; update continues."
      fi
      unset _MC_WAS _DRM_CUR
    else
      echo "  ℹ memory-core entry not present — this OpenClaw build may predate the dreaming plugin; skipping (update continues)."
    fi

    unset _GOOGLE_KEY_STATE _OPENAI_KEY_STATE _LDB_PRESENT _LDB_CUR _MC_PRESENT
  else
    echo "  ℹ openclaw CLI not on PATH — skipping fleet memory standardization (update continues)."
  fi

  # ----------------------------------------------------------
  # Loop / furnace protection activation (Skill 60 EWS + Skill 61 Loop
  # Protection). Post-sync hook — the SAME shared helper install.sh calls, so the
  # roll/update path activates identically (no copy-paste drift). Client-box
  # activation is GATED HELD by default (61-loop-protection-system/config/
  # rollout.json; env OPENCLAW_LOOP_PROTECTION_ROLLOUT overrides); it installs the
  # 60-then-61 watchdogs (ews-tick + loop-tick crons + ledgers) in DRY_RUN
  # observe-only ONLY when the fleet rollout gate is enabled, and NEVER arms.
  # See GRAPHICS-FURNACE-CONTEXT-RESCUE-SPEC Topic 2 §2.3 item 2. Best-effort.
  # ----------------------------------------------------------
  echo ""
  echo "  Loop/furnace protection (Skill 60 + 61): activation gate (HELD by default; DRY_RUN, never arms)..."
  _ACT_LOOP="$_PERSIST_SCRIPTS/activate-loop-protection.sh"
  [ -f "$_ACT_LOOP" ] || _ACT_LOOP="$ONBOARDING_DIR/scripts/activate-loop-protection.sh"
  if [ -f "$_ACT_LOOP" ]; then
    bash "$_ACT_LOOP" --role client --skills-dir "$SKILLS_DIR" 2>&1 | tail -6 || true
  else
    echo "  ℹ activate-loop-protection.sh not in bundle — loop protection wiring skipped (older bundle)"
  fi

  # ----------------------------------------------------------
  # Routing-defect permanent fix (4-layer: doctrine path, pptx deny, symlink
  # unblock, dept workspace seeding). Mirror of install.sh — idempotent on every
  # update, no-op when already applied. tools.sessions.visibility + agentToAgent
  # require a gateway reload to take effect; that reload is gated below.
  # apply-routing-fix.sh is persisted to $_PERSIST_SCRIPTS at the persistent-copy
  # loop above so it survives the temp-clone cleanup, same as apply-fleet-standards.sh.
  # ----------------------------------------------------------
  echo ""
  echo "  Applying routing-defect permanent fix (4-layer: doctrine, pptx deny, symlink unblock, dept seeding)..."
  ROUTING_FIX="$_PERSIST_SCRIPTS/apply-routing-fix.sh"
  [ -f "$ROUTING_FIX" ] || ROUTING_FIX="$ONBOARDING_DIR/scripts/apply-routing-fix.sh"
  if [ -f "$ROUTING_FIX" ]; then
    bash "$ROUTING_FIX" >/dev/null 2>&1 && echo "  ✓ Routing fix applied" || echo "  ⚠ Routing fix reported errors (update continues — re-run apply-routing-fix.sh)"
  else
    echo "  ⚠ apply-routing-fix.sh not found (skipping routing fix)"
  fi

  # ----------------------------------------------------------
  # ----------------------------------------------------------
  # CEO gate removed 2026-08-05 per Trevor -- was creating loops; see openclaw-telegram-master-plan.md
  # CEO PreToolUse intent-gate -- wiring DISABLED. The CEO tool-deny gate has been removed;
  # the intent-gate hook installer is preserved for review but NOT invoked on update.
  # ----------------------------------------------------------
  echo ""
  echo "  CEO tool deny gate removed 2026-08-05 -- intent-gate wiring skipped (see openclaw-telegram-master-plan.md)"

  # ----------------------------------------------------------
  # Post-stamp verification: verify-routing.sh static gates G1–G8.
  # (CEO tool deny gate removed 2026-08-05 — intent-gate wiring not applied on update.)
  # ----------------------------------------------------------
  VERIFY_ROUTING="$_PERSIST_SCRIPTS/verify-routing.sh"
  [ -f "$VERIFY_ROUTING" ] || VERIFY_ROUTING="$ONBOARDING_DIR/scripts/verify-routing.sh"
  if [ -f "$VERIFY_ROUTING" ]; then
    echo ""
    echo "  Verifying routing wiring (verify-routing.sh static gates G1–G8)..."
    if bash "$VERIFY_ROUTING" 2>&1; then
      echo "  ✓ verify-routing: all static gates PASS"
    else
      echo "  ⚠ verify-routing: one or more gates FAILED — routing/intent-gate wiring incomplete on this box."
      echo "  ⚠ Update continues; re-run apply-routing-fix.sh, then 'bash scripts/verify-routing.sh' to see which gate. (CEO tool deny gate removed 2026-08-05.)"
    fi
  else
    echo "  ⚠ verify-routing.sh not found (skipping post-stamp routing verification)"
  fi

  # ----------------------------------------------------------
  # CEO Routing Doctrine pre-injection plugin (2026-08-05, Trevor).
  # Replaces the removed CEO gate with a before_prompt_build prompt-injection
  # layer: injects "route, don't self-execute" + the human-override carve-out
  # every turn, with NO tool-deny (so no write-denial loop). Installs the
  # extension to ~/.openclaw/extensions/ and enables it in openclaw.json with
  # enabled:true ONLY. Idempotent.
  #
  # FLEET-KILL DEFECT FIX (2026-08-06): this block used to ALSO write
  # plugins.entries.ceo-routing-doctrine.hooks = {allowPromptInjection:true}.
  # `hooks` on a plugins.entries.<id> is additionalProperties:false and does
  # NOT accept `allowPromptInjection` on OpenClaw <=2026.6.11 (the extension's
  # own dist/index.js comment claims that gate only as of 2026.7.1-2, a schema
  # version not yet uniformly on the fleet) -- writing it made
  # `openclaw config validate` FAIL with "hooks: Invalid input". Config
  # validation is FATAL at gateway startup: the gateway never starts, the
  # cron scheduler never initializes, next_run_at_ms freezes in the past
  # forever, and NO cron on the box ever fires again -- silently, because the
  # ALREADY-RUNNING gateway is unaffected until the box's NEXT restart/reboot
  # (this is exactly what update-skills.sh triggers on every fleet roll).
  # DO NOT re-add this key here without first confirming (via
  # `openclaw config validate` against the box's actual installed gateway
  # version) that the target schema accepts
  # plugins.entries.<id>.hooks.allowPromptInjection.
  # ----------------------------------------------------------
  echo "  Installing CEO Routing Doctrine pre-injection plugin..."
  _RD_SRC="$ONBOARDING_DIR/extensions/ceo-routing-doctrine"
  _RD_DST="$HOME/.openclaw/extensions/ceo-routing-doctrine"
  if [ -d "$_RD_SRC" ]; then
    mkdir -p "$_RD_DST"
    # "$_RD_SRC/." -> "$_RD_DST/" copies CONTENTS INTO the dir. The previous form
    # (cp -r "$_RD_SRC" "$_RD_DST") NESTS once $_RD_DST exists: run 2 produces
    # ceo-routing-doctrine/ceo-routing-doctrine/, so every weekly roll added
    # another nested copy despite the "Idempotent" claim above. Verified by
    # repro: run1 clean, run2 nested; the "/." form is stable across 3+ runs.
    # Errors are NOT swallowed (no 2>/dev/null || true) — a real copy failure
    # must be visible instead of silently shipping a box with no doctrine.
    if ! cp -R "$_RD_SRC/." "$_RD_DST/"; then
      echo "  ⚠ FAILED to copy ceo-routing-doctrine into $_RD_DST — plugin NOT installed"
    else
      python3 - <<'PY'
import json, os, shutil, time
cfg_path = os.path.expanduser("~/.openclaw/openclaw.json")
if os.path.isfile(cfg_path):
    with open(cfg_path) as _f:
        cfg = json.load(_f)
    cfg.setdefault("plugins", {}).setdefault("entries", {})
    cfg["plugins"]["entries"]["ceo-routing-doctrine"] = {
        "enabled": True,
    }
    cfg.setdefault("plugins", {}).setdefault("load", {}).setdefault("paths", [])
    # PORTABILITY: expanduser, never "/Users/%s" % USER. The hardcoded /Users
    # prefix is macOS-only and breaks every Linux box in the fleet (10 VPS +
    # 2 Contabo, where $HOME is /root or /home/<user>) — load.paths would point
    # at a directory that does not exist, so the doctrine would never load. It
    # also planted an operator username in a repo that must stay client-neutral.
    p = os.path.expanduser("~/.openclaw/extensions")
    if p not in cfg["plugins"]["load"]["paths"]:
        cfg["plugins"]["load"]["paths"].append(p)
    # plugins.allow, WHEN PRESENT, is an allowlist. apply-fleet-standards.sh
    # rewrites it to the currently-BUNDLED plugin ids, and this extension reports
    # origin:"config" (path-loaded), NOT "bundled" — confirmed against a live
    # `openclaw plugins list --json`. apply-fleet-standards.sh also runs EARLIER
    # in a roll than this installer, so without this the doctrine is silently
    # dropped from the allowlist on a later roll, leaving neither the CEO gate
    # nor the doctrine. Only EXTEND an allowlist that already exists — never
    # create one, since an allowlist where none existed disables every other
    # plugin on the box.
    _allow = cfg["plugins"].get("allow")
    if isinstance(_allow, list) and "ceo-routing-doctrine" not in _allow:
        _allow.append("ceo-routing-doctrine")
    # ATOMIC WRITE + timestamped backup. The previous form was
    # json.dump(cfg, open(cfg_path, "w")) — an exception, signal, or full disk
    # mid-write TRUNCATES the box's openclaw.json and the gateway will not start.
    _bak = "%s.bak.ceo-doctrine-%s" % (cfg_path, time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()))
    shutil.copy2(cfg_path, _bak)
    _tmp = cfg_path + ".tmp.ceo-doctrine"
    with open(_tmp, "w") as _f:
        json.dump(cfg, _f, indent=2)
        _f.write("\n")
        _f.flush()
        os.fsync(_f.fileno())
    os.replace(_tmp, cfg_path)
    print("ceo-routing-doctrine enabled + load.paths set (config backup: %s)" % os.path.basename(_bak))
PY
      echo "  ✓ CEO Routing Doctrine plugin installed + enabled (prompt-injection replacement for CEO gate)"
    fi
  else
    echo "  ⚠ ceo-routing-doctrine extension not found in repo ($_RD_SRC) — skipping install"
  fi

  # ----------------------------------------------------------
  # Dept-agent registration: turn built workspace folders into REAL agents in
  # openclaw.json. Runs after apply-routing-fix.sh so the routing config
  # (tools.sessions.visibility / agentToAgent) is set before agents are registered.
  # Idempotent: re-running adds 0 duplicates; updates stale entries in place.
  # Skipped silently when Skill 32 is not yet installed on this box.
  # ----------------------------------------------------------
  _MATERIALIZE="$SKILLS_DIR/32-command-center-setup/scripts/materialize-dept-agents.sh"
  if [ -f "$_MATERIALIZE" ]; then
    echo ""
    echo "  Registering dept agents in openclaw.json (materialize-dept-agents)..."
    if bash "$_MATERIALIZE" >/dev/null 2>&1; then
      # WIRING-ASSERT (v14.26.0): mirrors run-full-install.sh Phase 4 hard gate.
      # Verifies agents.list[] >=2 after materialize so a zero-dept scan, a path
      # miss, or a silent empty run is surfaced loudly — NOT swallowed with a
      # soft "update continues" message.  Skips gracefully when openclaw.json is
      # absent (Skill 32 not yet built on this box).
      _AGENT_COUNT=0
      if [ -f "$OC_JSON" ]; then
        _AGENT_COUNT=$(python3 -c "import json,sys; d=json.load(open('$OC_JSON')); sys.stdout.write(str(len(d.get('agents',{}).get('list',[]))))" 2>/dev/null || echo "0")
      fi
      if [ -z "$_AGENT_COUNT" ] || [ "$_AGENT_COUNT" -lt 2 ]; then
        echo "  ⚠ WIRING-ASSERT FAIL: agents.list[] has only ${_AGENT_COUNT:-0} entries after materialize"
        echo "  ⚠ Dept agents NOT live — re-run update after build-workforce.py completes or check Skill 32 path"
      else
        echo "  ✓ Dept agents registered (${_AGENT_COUNT} agents in agents.list[])"
      fi

      # DEPARTMENT-RUNTIME-PARITY GUARD (belt-and-suspenders on update runs): the
      # WIRING-ASSERT above only floors the TOTAL agents.list[] count — it never
      # verifies EACH INDIVIDUAL department board row (a mission-control.db
      # `workspaces` row) has ITS OWN matching runtime entry (the
      # no_specialist_runtime failure class). Cross-checks every seeded
      # department against agents.list[] using the same slug variants
      # blackceo-command-center's resolveSpecialistSessionKey() tries. Non-fatal
      # here (matches this block's own WARN-and-continue convention above) —
      # the SAME check is a HARD, install-blocking gate in run-full-install.sh
      # Phase 6e2, which this update run also invokes moments later via
      # --update-only below, so a real mismatch is never silently swallowed.
      _DEPT_PARITY_GUARD="$SKILLS_DIR/32-command-center-setup/scripts/guard-department-runtime-parity.py"
      if [ -f "$_DEPT_PARITY_GUARD" ]; then
        if _DEPT_PARITY_OUT="$(python3 "$_DEPT_PARITY_GUARD" --config "$OC_JSON" 2>&1)"; then
          echo "  ✓ ${_DEPT_PARITY_OUT##*] }"
        else
          echo "  ⚠ DEPARTMENT-RUNTIME-PARITY FAIL — one or more seeded departments have no matching OpenClaw runtime:"
          printf '%s\n' "$_DEPT_PARITY_OUT" | while IFS= read -r _line; do echo "  ⚠   $_line"; done
          echo "  ⚠ Update continues; this is also a hard install-blocking gate in run-full-install.sh (Phase 6e2)"
        fi
      fi
    else
      echo "  ⚠ WIRING-ASSERT FAIL: materialize-dept-agents.sh exited non-zero — dept agents NOT registered"
      echo "  ⚠ Check that Skill 32 is installed and build-workforce.py has produced department folders"
    fi

  # U006 — Co-locate the canonical presentation entry script + guard into the
  # materialized department's scripts/ directory.
  colocate_presentation_entry

  # ----------------------------------------------------------
  # D5 — Command Center web-app refresh (v14.27.0):
  # git pull --ff-only + npm install + db:push + sync-departments + pm2 restart.
  # Closes the CC #108/#109/#112 delivery gap on EXISTING boxes.
  #
  # install.sh delivers CC v4.54.0 via the Skill-37 closeout agent (run-full-install.sh
  # Phase 6). update-skills.sh previously copied Skill-32 scripts but never INVOKED
  # run-full-install.sh, so existing boxes kept the stale dashboard + the #109
  # demo-department regression until an owner manually approved the weekly cron.
  #
  # Guarded: verify-remote guard — only fires when ~/projects/command-center is a git
  # checkout of blackceo-command-center. Does NOT re-embed the persona index (honors
  # "never rebuild a live correct index" and "client uses own keys").
  #
  # EXIT-CODE CONTRACT (post-stamp section, never withholds the version stamp):
  #   0 = fully current (skills content + CC infrastructure both up to date)
  #   1 = stamp WITHHELD (a content-integrity gate before the stamp failed)
  #   2 = content current, but CC infrastructure is incomplete or needs attention
  #       (advisory — does NOT exit 1 so fleet drivers can distinguish
  #       "stamp withheld" from "CC needs attention"; prevents the exit-1 loop
  #       described in U002 where a post-stamp CC failure causes a re-run that
  #       finds the stamp current but fails CC again → infinite loop).
  #
  # U002 — EXIT-CODE CONTRACT (this section runs AFTER the version stamp is
  # written, so its failures must NOT masquerade as "stamp withheld"):
  #   exit 0 = fully current (stamp written AND CC infrastructure complete)
  #   exit 1 = stamp withheld (content NOT current — raised only by the stamp
  #            verification gates above, never by this section)
  #   exit 2 = content current but CC infrastructure incomplete (a CC refresh
  #            or bootstrap failure below). Fleet drivers: treat 2 as
  #            "onboarding content applied; Command Center needs attention",
  #            NOT as a failed update — re-running the updater will not clear
  #            it until the CC install log is addressed.
  # ----------------------------------------------------------
  # ----------------------------------------------------------
  # TRAP-3 (second-Command-Center guard): _CC_DIR was hardcoded to the SINGLE
  # candidate "$HOME/projects/command-center". Every "does a CC already exist?"
  # test below keyed off that one path, so a box whose CC lives ANYWHERE else
  # (VPS /data/projects/command-center, legacy $HOME/projects/mission-control,
  # a blackceo-command-center-named checkout) looked CC-less to this updater.
  # The F10 bootstrap branch then ran run-full-install.sh in FULL mode, which
  # clones a SECOND Command Center into $HOME/projects/command-center and —
  # 32-command-center-setup/scripts/run-full-install.sh:1215-1218 —
  # `pm2 delete blackceo-command-center` (evicting the LIVE board) and restarts
  # pm2 from the brand-new clone. On a client box that is a service outage plus
  # a divergent mission-control.db. It was disarmed on the operator Mac ONLY
  # because .workforce-build-state.json had an empty contactEmail — an accident,
  # not a guard.
  #
  # Fix: resolve _CC_DIR by scanning the same candidate set the rest of the
  # fleet already uses (32-command-center-setup/scripts/add-department.sh:153-158,
  # qc-command-center-setup.sh:23 `find $HOME /data ... -name blackceo-command-center`),
  # accepting only a VALIDATED checkout (.git + origin remote is
  # blackceo-command-center + package.json). Bootstrap is then gated on ABSENCE
  # proven three independent ways (no checkout, no pm2 app, port unbound)
  # instead of on an unrelated build-state field.
  # ----------------------------------------------------------
  # >>> TRAP3-CC-GUARD-HELPERS-BEGIN  (extracted verbatim by scripts/test-updater-traps-1-and-3.sh)
  _CC_DIR_CANONICAL="$HOME/projects/command-center"
  _CC_PORT="${CC_PORT:-4000}"
  _CC_PM2_NAMES="blackceo-command-center mission-control command-center"

  # cc_is_valid_checkout — a directory is a real Command Center checkout only if
  # it is a git repo whose origin remote is the blackceo-command-center repo AND
  # it carries a package.json. Remote match is what stops an unrelated
  # ~/projects/command-center scratch dir from being mistaken for the board.
  cc_is_valid_checkout() {
    _ccv_dir="$1"
    [ -n "$_ccv_dir" ] || return 1
    [ -d "$_ccv_dir/.git" ] || return 1
    [ -f "$_ccv_dir/package.json" ] || return 1
    _ccv_remote=$(git -C "$_ccv_dir" remote get-url origin 2>/dev/null || echo "")
    echo "$_ccv_remote" | grep -q 'blackceo-command-center' || return 1
    return 0
  }

  # cc_resolve_existing_dir — echo the first VALIDATED CC checkout on this box.
  # Canonical path first so an already-correct box resolves unchanged; then the
  # documented fleet alternates. Echoes nothing and returns 1 when none exists.
  cc_resolve_existing_dir() {
    for _ccr_cand in \
      "$_CC_DIR_CANONICAL" \
      "/data/projects/command-center" \
      "$HOME/projects/blackceo-command-center" \
      "/data/projects/blackceo-command-center" \
      "$HOME/projects/mission-control" \
      "$HOME/blackceo-command-center" \
      "/opt/mission-control" \
      "/app"
    do
      if cc_is_valid_checkout "$_ccr_cand"; then
        echo "$_ccr_cand"
        return 0
      fi
    done
    return 1
  }

  # cc_running_pm2_app — echo the name of any pm2 app already running a Command
  # Center (canonical or legacy alias). Absence of pm2 is NOT evidence of
  # absence of a CC; it just means this signal abstains.
  cc_running_pm2_app() {
    command -v pm2 >/dev/null 2>&1 || return 1
    _ccp_list=$(pm2 jlist 2>/dev/null || echo "")
    [ -n "$_ccp_list" ] || return 1
    for _ccp_name in $_CC_PM2_NAMES; do
      if printf '%s' "$_ccp_list" \
        | CC_WANT="$_ccp_name" python3 -c 'import json,os,sys
want = os.environ["CC_WANT"]
try:
    apps = json.load(sys.stdin)
except Exception:
    sys.exit(1)
sys.exit(0 if any(a.get("name") == want for a in apps) else 1)' 2>/dev/null; then
        echo "$_ccp_name"
        return 0
      fi
    done
    return 1
  }

  # cc_port_bound — 0 when something is already LISTENING on the CC port.
  # Tries lsof, then ss, then netstat, then an HTTP probe. Every probe missing
  # means "unknown", which returns 1 (abstain) — the checkout and pm2 signals
  # still gate the bootstrap.
  cc_port_bound() {
    if command -v lsof >/dev/null 2>&1; then
      lsof -nP -iTCP:"$_CC_PORT" -sTCP:LISTEN >/dev/null 2>&1 && return 0
      return 1
    fi
    if command -v ss >/dev/null 2>&1; then
      ss -ltn 2>/dev/null | grep -qE "[:.]${_CC_PORT}[[:space:]]" && return 0
      return 1
    fi
    if command -v netstat >/dev/null 2>&1; then
      netstat -an 2>/dev/null | grep -qE "[:.]${_CC_PORT}[[:space:]]+.*LISTEN" && return 0
      return 1
    fi
    if command -v curl >/dev/null 2>&1; then
      curl -fsS -o /dev/null --max-time 5 "http://127.0.0.1:${_CC_PORT}/" 2>/dev/null && return 0
    fi
    return 1
  }

  _CC_DIR="$(cc_resolve_existing_dir || echo "")"
  if [ -n "$_CC_DIR" ]; then
    [ "$_CC_DIR" = "$_CC_DIR_CANONICAL" ] \
      || echo "  ℹ Command Center checkout resolved at non-canonical path: $_CC_DIR"
  else
    # No existing checkout — the canonical path is where a bootstrap would land.
    _CC_DIR="$_CC_DIR_CANONICAL"
  fi
  _CC_RUN_INSTALL="$SKILLS_DIR/32-command-center-setup/scripts/run-full-install.sh"
  # <<< TRAP3-CC-GUARD-HELPERS-END
  # Resolve client identity from build-state once (used by BOTH the refresh and
  # the F10 bootstrap branch). An interview-completed box has these populated.
  _STATE_FILE="$OC_WORKSPACE_DEFAULT/.workforce-build-state.json"
  _CC_SLUG=""
  _CC_COMPANY=""
  _CC_EMAIL=""
  if [ -f "$_STATE_FILE" ]; then
    # P1-3: build-workforce.py now writes the slug as `companySlug` (canonical) and
    # `clientSlug` (transition alias). Read companySlug first, fall back to clientSlug,
    # so both build-state generations resolve. jq fallback chain (was: clientSlug-only).
    _CC_SLUG=$(jq -r '.companySlug // .clientSlug // ""' "$_STATE_FILE" 2>/dev/null || echo "")
    _CC_COMPANY=$(python3 -c "import json; d=json.load(open('$_STATE_FILE')); print(d.get('companyName',''))" 2>/dev/null || echo "")
    _CC_EMAIL=$(python3 -c "import json; d=json.load(open('$_STATE_FILE')); print(d.get('contactEmail',''))" 2>/dev/null || echo "")
  fi
  # ----------------------------------------------------------
  # D5-PRE (stale-checkout guard): both D5 branches below run the ON-BOX Skill-32
  # installer ($SKILLS_DIR/32-command-center-setup/scripts/run-full-install.sh).
  # But the copy loop only refreshes Skill 32 when it is in THIS run's copy set —
  # an `--only <not-32>` run (or a resume/closeout path) leaves a STALE on-box
  # installer, yet D5 invokes it unconditionally. A stale installer silently
  # lacks cc_mirror_api_auth_to_agent_secrets (Skill-32 v12.9.31), so it writes
  # the token to CC .env.local but never mirrors it to $OC_ROOT/secrets/.env —
  # the server is half-provisioned and dept-agent write-backs 401 (root cause of
  # boxes that "provisioned" but stayed dispatch-dead). Fix: bring the on-box
  # Skill-32 folder CURRENT from the freshly-cloned source BEFORE running it, so
  # the installer that runs always carries the latest provisioning logic. Version-
  # gated (skill-version.txt compare) so it is a no-op when already current; best-
  # effort and never fatal.
  if [ -n "${ONBOARDING_DIR:-}" ] \
     && [ -f "$ONBOARDING_DIR/32-command-center-setup/scripts/run-full-install.sh" ]; then
    _CC_SRC_VER=$(tr -d '[:space:]' < "$ONBOARDING_DIR/32-command-center-setup/skill-version.txt" 2>/dev/null || echo "")
    _CC_DST_VER=$(tr -d '[:space:]' < "$SKILLS_DIR/32-command-center-setup/skill-version.txt" 2>/dev/null || echo "")
    if [ -n "$_CC_SRC_VER" ] && [ "$_CC_SRC_VER" != "$_CC_DST_VER" ]; then
      echo "  [D5-PRE] Refreshing on-box Skill 32 (${_CC_DST_VER:-none} -> ${_CC_SRC_VER}) before running the CC installer (stale-checkout guard)..."
      rm -rf "$SKILLS_DIR/32-command-center-setup"
      cp -r "$ONBOARDING_DIR/32-command-center-setup" "$SKILLS_DIR/"
      command -v obs_set_status >/dev/null 2>&1 && obs_set_status "32-command-center-setup" "downloaded"
    fi
  fi

  # Bug B fix: _cc_currency_probe was called from exactly ONE place in this
  # script -- inside the _SAME_VERSION_RECHECK branch far above, which is
  # ONLY entered on a same-version re-roll. On a version-bump roll (the
  # NORMAL case -- every box's version differs from the new release) that
  # branch is never reached, so .command-center-state was never written at
  # all. PROVEN LIVE: a canary run going v21.1.0 -> v21.4.43 produced no
  # `[CC CURRENCY]` line whatsoever. Call it here too, unconditionally, on
  # every full pass -- this call is MARKER-WRITE/REPORT ONLY: the return
  # value is intentionally discarded and must NEVER gate or alter anything
  # below (the full pass already performs the actual CC refresh via
  # run-full-install.sh in the branches that follow). The recheck-branch call
  # above is untouched and still gates its own early exit.
  _cc_currency_probe || true

  # >>> TRAP3-CC-BOOTSTRAP-BRANCH-BEGIN  (extracted verbatim by scripts/test-updater-traps-1-and-3.sh)
  #
  # U005 -- EXIT-CODE CONTRACT (STAMP/CC-REFRESH ORDERING):
  # The .onboarding-version stamp was written ABOVE this point and certifies
  # that skills CONTENT is current. Command Center infrastructure steps below
  # are ADVISORY: they do not invalidate the content stamp. The exit-code
  # contract is therefore:
  #   exit 0 = skills content current, CC infrastructure refreshed/bootstrapped
  #   exit 1 = stamp WITHHELD (content mismatch, manifest failure, etc.)
  #   exit 2 = skills content current, CC infrastructure INCOMPLETE (advisory)
  # Fleet drivers read exit 2 as "box has current skills; CC needs attention."
  # This contract is asserted by U002 and structuralized by U005.
  #
  if cc_is_valid_checkout "$_CC_DIR" && [ ! -f "$_CC_RUN_INSTALL" ]; then
    echo "FATAL: Command Center exists at $_CC_DIR but the current Skill-32 updater is missing: $_CC_RUN_INSTALL" >&2
    echo "       Refusing a partial one-repo update." >&2
    echo "       ADVISORY: skills CONTENT is current (.onboarding-version stamp written); CC installer missing, refresh deferred." >&2
    exit 2
  fi
  if cc_is_valid_checkout "$_CC_DIR" && [ -f "$_CC_RUN_INSTALL" ]; then
    echo ""
    # DIRTY-CHECKOUT GUARD (defect fix): `run-full-install.sh --update-only` does
    # a `git pull`, which is unsafe (and unpredictable) against a checkout that
    # carries uncommitted local changes. On 2 of 3 pilot boxes THIS is what made
    # the CC refresh fail below, which used to `exit 2` and abort the ENTIRE
    # updater before the PENDING-flag lifecycle (further down this script) ever
    # ran -- a dirty client checkout must never take down the whole update. Fix:
    # detect dirty BEFORE attempting the pull, skip ONLY the CC refresh, report
    # it as a WARNING with the exact remediation, and fall through so every
    # unrelated step below (including the PENDING-flag lifecycle) still runs.
    # Nothing is stashed, reset, or discarded here -- uncommitted work on a
    # client box is load-bearing (same rule _cc_currency_probe's own dirty-state
    # marker already follows). This is intentionally NOT the same code path as
    # the genuine installer-failure / not-on-origin-main cases below (U005
    # exit-2 advisory, unchanged) -- those remain fatal-to-this-section by
    # design; a dirty tree is a different, recoverable, expected condition.
    _CC_DIRTY_STATUS="$(git -C "$_CC_DIR" status --porcelain 2>/dev/null || true)"
    if [ -n "$_CC_DIRTY_STATUS" ]; then
      echo "  ⚠ Command Center checkout at $_CC_DIR has UNCOMMITTED local changes — refresh SKIPPED." >&2
      echo "    A git pull against a dirty tree is unsafe, so nothing was pulled, reset, or discarded." >&2
      printf '%s\n' "$_CC_DIRTY_STATUS" | head -n 10 | sed 's/^/      /' >&2
      echo "    REMEDIATION: on this box, run:" >&2
      echo "      cd \"$_CC_DIR\" && git status --short" >&2
      echo "      git stash                    # to park the changes, OR" >&2
      echo "      git add -A && git commit      # to keep them" >&2
      echo "    then re-run the updater to pick up the Command Center refresh." >&2
      echo "    Skills content is current; the rest of this update continues normally." >&2
    else
      echo "  Refreshing Command Center web app (CC #108/#109/#112 — git pull + db:push + workspace seed + sync-departments)..."
      # Pin the exact validated checkout. Without --app-dir, non-canonical fleet
      # layouts silently refreshed $HOME/projects/command-center instead (or did
      # nothing). The installer also proves it is on the origin default branch,
      # contains latest origin/main, and ends on a freshly-built GREEN deployment.
      if bash "$_CC_RUN_INSTALL" --update-only --app-dir "$_CC_DIR" \
          "${_CC_SLUG:-}" "${_CC_COMPANY:-}" "${_CC_EMAIL:-}" >>"$LOG_FILE" 2>&1; then
        _CC_BRANCH="$(git -C "$_CC_DIR" symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
        _CC_DEFAULT="$(git -C "$_CC_DIR" symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null | sed 's|^origin/||')"
        [ -n "$_CC_DEFAULT" ] || _CC_DEFAULT="main"
        if [ "$_CC_BRANCH" != "$_CC_DEFAULT" ] \
           || ! git -C "$_CC_DIR" merge-base --is-ancestor "origin/$_CC_DEFAULT" HEAD 2>/dev/null; then
          echo "FATAL: Command Center installer returned success but checkout is not current on origin/$_CC_DEFAULT" >&2
          echo "       ADVISORY: skills CONTENT is current (.onboarding-version stamp written); CC checkout not on origin/$_CC_DEFAULT." >&2
          exit 2
        fi
        echo "  ✓ Command Center app refreshed, current on origin/$_CC_DEFAULT, rebuilt, and health-verified"
      else
        echo "FATAL: Command Center refresh failed or rolled back; skills content is current but CC web-app is NOT fully refreshed." >&2
        echo "       Check $OC_WORKSPACE_DEFAULT/.command-center-install.log and re-run the updater." >&2
        echo "       ADVISORY: skills CONTENT is current (.onboarding-version stamp written); CC web-app refresh FAILED — check install log." >&2
        exit 2
      fi
    fi
  elif [ -f "$_CC_RUN_INSTALL" ]; then
    # F10 — CC bootstrap on update. The refresh branch above is the path for a
    # box that already HAS a Command Center; this branch is strictly for a box
    # that has NONE. Run run-full-install.sh in FULL mode (clone + npm install +
    # db:push + Phase 6b workspace seed + sync-departments + pm2 start) so the
    # update path truly converges to the install path.
    #
    # TRAP-3: bootstrap is now gated on PROVEN ABSENCE, checked three
    # independent ways, because run-full-install.sh in FULL mode is destructive
    # to an existing board (it pm2-deletes the canonical app and restarts from
    # its own fresh clone). ANY positive existence signal aborts the bootstrap
    # and says so out loud. The previous gate leaned on build-state
    # slug/company/email being populated; an empty contactEmail is an accident
    # of interview state, not a statement about whether a CC exists.

    # PLACEHOLDER-SLUG BOOTSTRAP (bootstrap gap fix, 2026-07-28): companySlug /
    # clientSlug is written by build-workforce.py ONLY at interview-completion
    # (see build-state-schema.json) — so a box with no CC and no completed
    # interview deferred here FOREVER on "interview not completed," blocked on
    # the very artifact only the interview produces. Per OQ-1 the LOCKED
    # `/interview` shell must ship before the interview completes, so waiting
    # on the interview's own output to unblock the shell is the bug. Fix: when
    # no slug exists yet, derive one from the box's own owner-identity — set at
    # initial pairing, long before Skill 23's interview — using the same
    # openclaw.json field order as install.sh's resolve_owner_name(). Operator
    # ruling (2026-07-28): default PERMANENTLY to the client's name-derived
    # slug — e.g. a client named "Jane Doe" gets slug "jane" (first name only,
    # lowercased), derived this same way; this pattern already runs in
    # production without issue. No rename/migration path is built here; the
    # name-derived slug is the final answer for this box.
    if [ -z "$_CC_SLUG" ]; then
      _CC_OWNER_NAME=""
      if [ -n "${OC_JSON:-}" ] && [ -f "${OC_JSON:-}" ]; then
        _CC_OWNER_NAME=$(OC_JSON_PATH="$OC_JSON" python3 - <<'PYEOF' 2>/dev/null
import json, os
candidates = []
env_name = os.environ.get("OPENCLAW_OWNER_NAME", "").strip()
if env_name:
    candidates.append(env_name)
try:
    d = json.load(open(os.environ["OC_JSON_PATH"]))
    for path in (("meta", "ownerName"), ("owner", "name"), ("wizard", "ownerName"),
                 ("meta", "owner", "name"), ("owner", "firstName")):
        cur = d
        for k in path:
            cur = cur.get(k, {}) if isinstance(cur, dict) else {}
        if isinstance(cur, str) and cur.strip():
            candidates.append(cur.strip())
            break
except Exception:
    pass
for n in candidates:
    print(n.split()[0])
    break
PYEOF
)
      fi
      if [ -n "$_CC_OWNER_NAME" ]; then
        _CC_SLUG=$(printf '%s' "$_CC_OWNER_NAME" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//')
      fi
      if [ -n "$_CC_SLUG" ]; then
        [ -n "$_CC_COMPANY" ] || _CC_COMPANY="$_CC_OWNER_NAME"
        [ -n "$_CC_EMAIL" ] || _CC_EMAIL="pending+${_CC_SLUG}@zerohumanworkforce.com"
        echo ""
        echo "  ℹ Command Center slug not yet written (interview not complete) — derived permanent placeholder slug '$_CC_SLUG' from the box owner identity so the LOCKED /interview shell can ship now (OQ-1)."
      fi
    fi

    _CC_EXISTS_REASON=""
    if cc_is_valid_checkout "$_CC_DIR"; then
      _CC_EXISTS_REASON="a valid Command Center checkout is present at $_CC_DIR"
    fi
    if [ -z "$_CC_EXISTS_REASON" ]; then
      _CC_PM2_FOUND="$(cc_running_pm2_app || echo "")"
      [ -n "$_CC_PM2_FOUND" ] \
        && _CC_EXISTS_REASON="pm2 is already running a Command Center app named '$_CC_PM2_FOUND'"
    fi
    if [ -z "$_CC_EXISTS_REASON" ] && cc_port_bound; then
      _CC_EXISTS_REASON="port $_CC_PORT is already bound by a listening process"
    fi

    # Poisoned-target guard: run-full-install.sh only clones when
    # $DASHBOARD_DIR/.git is ABSENT (run-full-install.sh:1132). If the canonical
    # path already holds some OTHER git repo, the installer skips the clone and
    # silently adopts that repo as the Command Center. Refuse loudly instead.
    _CC_TARGET_BLOCKED=""
    if [ -z "$_CC_EXISTS_REASON" ] && [ -d "$_CC_DIR_CANONICAL/.git" ] \
       && ! cc_is_valid_checkout "$_CC_DIR_CANONICAL"; then
      _CC_TARGET_BLOCKED="$_CC_DIR_CANONICAL contains a git repo that is NOT blackceo-command-center"
    fi

    if [ -n "$_CC_TARGET_BLOCKED" ]; then
      echo ""
      echo "  ⚠ Command Center bootstrap REFUSED — $_CC_TARGET_BLOCKED."
      echo "    The installer skips its clone when a .git is already present, so it would"
      echo "    adopt that unrelated repo as the Command Center. Move or remove that"
      echo "    directory, then re-run the update."
    elif [ -n "$_CC_EXISTS_REASON" ]; then
      echo ""
      echo "  ⏭ Command Center bootstrap SKIPPED — this box already has one: $_CC_EXISTS_REASON."
      echo "    Bootstrap is only for a box with NO Command Center. Running the full"
      echo "    installer here would clone a second copy, pm2-delete the running app and"
      echo "    restart from the new clone (service outage + divergent mission-control.db)."
      echo "    If this box genuinely needs a rebuild, run run-full-install.sh manually."
    elif [ -n "$_CC_SLUG" ] && [ -n "$_CC_COMPANY" ] && [ -n "$_CC_EMAIL" ]; then
      # Absence proven. slug+company+email are required ARGUMENTS of a full
      # install (run-full-install.sh:73-83 hard-exits without all three) — an
      # input-completeness precondition, not the safety guard.
      echo ""
      echo "  Command Center not present on this box (no checkout, no pm2 app, port $_CC_PORT free) — bootstrapping full install (clone + db:push + workspace seed + sync)..."
      if bash "$_CC_RUN_INSTALL" "$_CC_SLUG" "$_CC_COMPANY" "$_CC_EMAIL" >>"$LOG_FILE" 2>&1; then
        echo "  ✓ Command Center bootstrapped (clone + npm install + db:push + workspace seed + sync-departments + pm2 start)"
      else
        echo "FATAL: Command Center bootstrap failed; skills content is current but CC web-app was not bootstrapped." >&2
        echo "       Check $OC_WORKSPACE_DEFAULT/.command-center-install.log and re-run." >&2
        echo "       ADVISORY: skills CONTENT is current (.onboarding-version stamp written); CC bootstrap FAILED." >&2
        exit 2
      fi
    elif [ -n "$_CC_SLUG" ]; then
      echo ""
      echo "  ℹ Command Center not provisioned and build-state is missing company/email — bootstrap deferred (needs slug+company+email)."
    else
      echo ""
      echo "  ℹ Command Center not provisioned and build-state has no client slug — bootstrap deferred (interview not completed)."
    fi
  fi
  # <<< TRAP3-CC-BOOTSTRAP-BRANCH-END

  # POST-REFRESH CC CURRENCY PROBE (2026-08-15 fix): the pre-refresh probe call
  # above wrote the marker BEFORE the CC refresh ran. run-full-install.sh's
  # Phase 6b seed (seed-workspaces.py -> generate-brand-css.py) re-stamps
  # public/brand.css AFTER the refresh, re-dirtying the tree — so the marker
  # was written while the tree was still clean and never updated after the
  # refresh dirtied it, leaving 3-4 boxes perpetually state=dirty even though
  # their CC code is at origin/main. Re-probe HERE, after the refresh
  # completes, so the marker reflects the true post-update state. Same
  # marker-write/report-only contract: return value intentionally discarded,
  # must never gate or alter anything.
  _cc_currency_probe || true

  fi

  # ----------------------------------------------------------
  # Conditional gateway restart: only restart when openclaw.json was actually
  # mutated by fleet-standards, routing-fix, or materialize this run.
  # This ensures tools.sessions.visibility and agentToAgent are live immediately
  # without restarting the gateway on every no-op update.
  # Platform dispatch: openclaw CLI first (works on Mac + VPS); falls back to
  # launchctl kickstart (Mac) or docker restart (VPS) when CLI is not on PATH.
  # ----------------------------------------------------------
  _OC_CONFIG_HASH_AFTER=""
  if [ -f "$OC_JSON" ]; then
    _OC_CONFIG_HASH_AFTER=$(python3 -c "import hashlib; print(hashlib.md5(open('$OC_JSON','rb').read()).hexdigest())" 2>/dev/null || true)
  fi
  if [ -n "$_OC_CONFIG_HASH_BEFORE" ] && [ -n "$_OC_CONFIG_HASH_AFTER" ]       && [ "$_OC_CONFIG_HASH_BEFORE" != "$_OC_CONFIG_HASH_AFTER" ]; then
    echo ""
    echo "  openclaw.json changed — restarting gateway to activate routing config..."
    if command -v openclaw >/dev/null 2>&1; then
      openclaw gateway restart >/dev/null 2>&1         && echo "  ✓ Gateway restarted (routing config now live)"         || echo "  ⚠ Gateway restart failed — restart manually: openclaw gateway restart"
    elif [ "$OC_PLATFORM" = "vps" ]; then
      docker restart openclaw >/dev/null 2>&1         && echo "  ✓ Gateway restarted via docker (routing config now live)"         || echo "  ⚠ docker restart failed — restart manually: openclaw gateway restart"
    else
      # v16.2.13: `awk '...exit'` closes the pipe on the first match → `launchctl
      # list` (hundreds of lines) dies with SIGPIPE (rc 141) → `pipefail` promotes
      # it → the plain assignment would abort the updater under `set -e` (same
      # SIGPIPE class as the persona-index reconcile bug). `|| true` neutralizes it;
      # the empty fallback on the next line already supplies the default label.
      GW_LABEL="$(launchctl list 2>/dev/null | awk '/openclaw.*gateway/{print $3; exit}' || true)"
      [ -z "$GW_LABEL" ] && GW_LABEL="ai.openclaw.gateway"
      launchctl kickstart -k "gui/$(id -u)/$GW_LABEL" >/dev/null 2>&1 \
        && echo "  ✓ Gateway restarted via launchctl (routing config now live)" \
        || echo "  ⚠ launchctl restart failed — restart manually: openclaw gateway restart"
    fi
  else
    echo "  ℹ Routing config unchanged — no gateway restart needed"
  fi

  # ----------------------------------------------------------
  # FIX-PRES-02: PRESENTATION DEPS CONVERGE (idempotent, fail-soft). A Mac box that
  # predates install.sh Step 6.5 never receives the four presentation-pipeline
  # runtime deps (soffice, pdftoppm, reportlab, python-pptx) from update-skills.sh,
  # so it would forever refuse every deck build at GATE 1 even after pulling the
  # latest skills. Converge them here exactly like install.sh Step 6.5's Mac branch
  # (VPS is handled by the reassert script the same step writes), then hard-WARN if
  # any dep is still missing. It never blocks the update; the following
  # qc-completeness gate re-checks the same four deps.
  # ----------------------------------------------------------
  converge_presentation_deps() {
    echo ""
    echo "  Converging presentation-pipeline runtime deps (soffice, pdftoppm, reportlab, python-pptx)..."
    if [ "${OPENCLAW_PLATFORM:-}" = "vps" ]; then
      local _reassert="/data/.openclaw/scripts/reassert-presentation-deps.sh"
      if [ -x "$_reassert" ]; then
        echo "    VPS: running the idempotent reassert script ($_reassert)..."
        bash "$_reassert" >/dev/null 2>&1 || echo "    ⚠ reassert script reported an issue (non-fatal)"
      else
        echo "    VPS: reassert script not present yet ($_reassert) — run install.sh Step 6.5 once to create it."
      fi
    else
      # Mac: brew formula for poppler, NONINTERACTIVE cask for LibreOffice (loud
      # warn on failure — a cask can need an admin password), pip --user for the
      # two Python modules. NONINTERACTIVE + no `read` so a silent roll never hangs.
      if command -v pdftoppm >/dev/null 2>&1; then
        echo "    pdftoppm (poppler) already present"
      elif command -v brew >/dev/null 2>&1; then
        brew install poppler >/dev/null 2>&1 && echo "    poppler (pdftoppm) installed" \
          || echo "    ⚠ brew install poppler failed — pdftoppm unavailable (Phase-6 QC PNG extraction will fail)"
      else
        echo "    ⚠ Homebrew not found — cannot install poppler (pdftoppm)"
      fi
      if command -v soffice >/dev/null 2>&1 || [ -x /Applications/LibreOffice.app/Contents/MacOS/soffice ]; then
        echo "    soffice (LibreOffice) already present"
      elif command -v brew >/dev/null 2>&1; then
        echo "    Installing LibreOffice (soffice) via NONINTERACTIVE Homebrew cask..."
        NONINTERACTIVE=1 brew install --cask libreoffice >/dev/null 2>&1 \
          && echo "    LibreOffice cask install completed" \
          || echo "    ⚠ NONINTERACTIVE LibreOffice cask install failed (may need an admin password). Run once interactively: brew install --cask libreoffice"
      else
        echo "    ⚠ Homebrew not found — cannot install LibreOffice (soffice)"
      fi
      if command -v python3 >/dev/null 2>&1; then
        if python3 -c "import reportlab, pptx" >/dev/null 2>&1; then
          echo "    reportlab + python-pptx already importable"
        else
          echo "    Installing reportlab + python-pptx (pip --user --break-system-packages)..."
          python3 -m pip install --user --break-system-packages reportlab python-pptx >/dev/null 2>&1 \
            && echo "    reportlab + python-pptx installed" \
            || echo "    ⚠ pip install reportlab/python-pptx failed — deck assembly + presenter PDF will fail"
        fi
      fi
    fi
    # Hard end-of-converge WARNING when any of the four deps is STILL missing.
    local _pres_missing=""
    command -v soffice  >/dev/null 2>&1 || _pres_missing="${_pres_missing} soffice"
    command -v pdftoppm >/dev/null 2>&1 || _pres_missing="${_pres_missing} pdftoppm"
    if command -v python3 >/dev/null 2>&1; then
      python3 -c "import reportlab, pptx" >/dev/null 2>&1 || _pres_missing="${_pres_missing} python(reportlab+python-pptx)"
    fi
    if [ -n "$_pres_missing" ]; then
      echo "  ⚠⚠ PRESENTATION_DEPS_MISSING after converge:${_pres_missing}. The Skill 23 presentation pipeline will refuse every deck build at GATE 1 until these resolve. Mac: brew install poppler; brew install --cask libreoffice; python3 -m pip install --user --break-system-packages reportlab python-pptx. VPS: bash /data/.openclaw/scripts/reassert-presentation-deps.sh"
    else
      echo "  ✓ presentation deps converged: soffice + pdftoppm + reportlab + python-pptx all present"
    fi
  }
  converge_presentation_deps

  # ----------------------------------------------------------
  # R14: REAP THE GHL MCP STATUS LINE.
  #
  # wire_ghl_mcp backgrounds ghl-mcp-autostart.sh to /tmp/ghl-mcp-autostart.log
  # and nothing ever read it. The backgrounding is deliberate and stays (v10.15.49:
  # a blocking autostart stalled the whole wiring loop, and macOS has no `timeout`)
  # -- but it meant the ENTIRE STATUS contract was invisible on the path the fleet
  # actually uses. PIN_INVALID, PIN_MISMATCH, BUILD_FAILED, TOKEN_REJECTED, DEAF,
  # STARTED_UNHEALTHY: install.sh Step 14a parses every one of them, and a fleet
  # roll saw none, so a roll could report success having refused to start an
  # unpinned server on every box.
  #
  # Reading it here -- late, after the wiring loop has had time to finish -- costs
  # nothing and closes the blind spot. The severity mapping mirrors install.sh
  # Step 14a exactly, so the two paths describe the same state the same way.
  # ----------------------------------------------------------
  GHL_MCP_STATUS_LINE=""
  if [ -f /tmp/ghl-mcp-autostart.log ]; then
    GHL_MCP_STATUS_LINE="$(grep -E '^STATUS:' /tmp/ghl-mcp-autostart.log 2>/dev/null | tail -1 || true)"
  fi
  echo ""
  case "$GHL_MCP_STATUS_LINE" in
    "")                             echo "  GHL MCP: no STATUS line captured (autostart may still be running in the background, or skill 36 is not installed) -- see /tmp/ghl-mcp-autostart.log" ;;
    *HEALTHY_ALREADY*|*"=HEALTHY "*) echo "  ✓ GHL MCP running + ANSWERING JSON-RPC. ${GHL_MCP_STATUS_LINE}" ;;
    *SKIPPED_NO_CREDS*)             echo "  ℹ GHL MCP not started -- GHL token absent (honest gap, not a failure). ${GHL_MCP_STATUS_LINE}" ;;
    *"=DEAF"*)                      echo "  ⚠ GHL MCP is listening but ANSWERING NOTHING (stale-dist deafness) -- every agent init will burn the full connectionTimeoutMs until fixed. ${GHL_MCP_STATUS_LINE}" ;;
    *TOKEN_REJECTED*)               echo "  ⚠ GHL rejected the PIT -- the MCP is deliberately NOT running (no restart loop). Rotate/repair GOHIGHLEVEL_API_KEY then re-run scripts/ghl-mcp-autostart.sh. ${GHL_MCP_STATUS_LINE}" ;;
    *PIN_MISMATCH*|*PIN_INVALID*)   echo "  ⚠ GHL MCP refused to start: the vetted commit pin could not be honoured -- an UNPINNED third-party MCP is never started. ${GHL_MCP_STATUS_LINE}" ;;
    # DEFECT 1 (proven live 2026-08-04): before this STATUS existed, running
    # ghl-mcp-autostart.sh as root against a checkout owned by a different uid
    # silently swallowed every git error and surfaced ONLY as the generic
    # PIN_MISMATCH above -- which sent the operator to re-vet an innocent pin.
    # This dedicated line names the real remedy so a fleet roll never repeats
    # that misdiagnosis.
    *ROOT_OWNERSHIP_MISMATCH*)      echo "  ⚠ GHL MCP refused to start: this roll invoked ghl-mcp-autostart.sh as ROOT against a checkout owned by a different uid -- every git command was refused by git's dubious-ownership guard. FIX: never invoke it as root (VPS/Docker: docker exec -u node <ctr> bash ...; see scripts/activate-loop-protection.sh for the convention). ${GHL_MCP_STATUS_LINE}" ;;
    *STARTED_UNHEALTHY*)            echo "  ⚠ GHL MCP service installed but /health not green yet -- crash-only restart will retry. ${GHL_MCP_STATUS_LINE}" ;;
    *BUILD_FAILED*)                 echo "  ⚠ GHL MCP build failed -- the PREVIOUS dist was left intact. ${GHL_MCP_STATUS_LINE}" ;;
    *)                              echo "  GHL MCP autostart ran. ${GHL_MCP_STATUS_LINE}" ;;
  esac

  # ----------------------------------------------------------
  # v10.15.4: Post-pull qc-completeness check. Read-only. Runs against the live
  # workforce after every successful skill pull.
  #
  # SILENT-MAINTENANCE (v17.0.18): a fleet roll / skill update is inherently
  # MAINTENANCE, so this embedded QC call MUST run with OPENCLAW_MAINTENANCE=1.
  # That forces qc-completeness.sh into quiet mode and SUPPRESSES its Telegram
  # alert entirely (log-only) — the embedded QC step can NEVER message a client
  # during a roll. The operator still gets the workforce QC STATUS folded into the
  # OPERATOR-ROUTED update note below (send_telegram_progress), so no visibility is
  # lost — only the client-facing alert is suppressed.
  #
  # v20.0.9 (SECURITY/PRIVACY): belt-and-suspenders — this call ALSO passes --quiet
  # (log-only path) AND inherits the roll-wide OPENCLAW_MAINTENANCE_SILENT=1 exported
  # at the top of main(). Any ONE of the three (OPENCLAW_MAINTENANCE=1, --quiet,
  # OPENCLAW_MAINTENANCE_SILENT=1) fully suppresses the send, and qc-completeness now
  # routes only to the OPERATOR (never the client owner / allowFrom[0]) in any case.
  # ----------------------------------------------------------
  QC_COMPLETENESS_SCRIPT="$SKILLS_DIR/23-ai-workforce-blueprint/scripts/qc-completeness.sh"
  QC_STATUS_LINE=""
  QC_COMPLETENESS_RC=0   # FIX 1: HONOR this exit code (was ignored). 0=PASS, 2=PARTIAL, 3=FAIL, 4=NO_WORKFORCE
  if [ -x "$QC_COMPLETENESS_SCRIPT" ]; then
    echo ""
    echo "  Running qc-completeness.sh against live workforce (maintenance mode — client alert suppressed)..."
    QC_OUTPUT="$(OPENCLAW_MAINTENANCE=1 bash "$QC_COMPLETENESS_SCRIPT" --quiet 2>&1)" || QC_COMPLETENESS_RC=$?
    QC_STATUS_LINE="$(printf '%s\n' "$QC_OUTPUT" | grep -E '^STATUS:' | tail -1 || true)"
    echo "  ${QC_STATUS_LINE:-qc-completeness ran (no STATUS line captured)} (exit $QC_COMPLETENESS_RC)"
  fi

  # ----------------------------------------------------------
  # Post-update: UPDATE PENDING flag LIFECYCLE + Telegram + backup block
  #
  # The flag is written ONLY when this run genuinely left activation work behind,
  # and REMOVED when it did not. The old code called write_update_pending_flag
  # unconditionally, so every clean run re-stamped a fresh "UPDATE PENDING" block
  # into AGENTS.md that told the agent to activate skills it had already
  # qc-passed, and nothing ever took it back out.
  #
  # The verdict is the SAME _RESUME_NEEDED signal the onboarding-resume cron
  # block below already used to decide there was nothing to self-heal — it was
  # simply never consulted before writing the flag. Computing it ONCE, here,
  # makes the flag and the cron agree by construction:
  #   gate == "no"            -> the gate PROVED unverified skills remain
  #   NEW_SKILLS_CSV non-empty -> new numbered skills need activation
  #   gate == "unknown"        -> the gate could not run; we do NOT know the box
  #                               is clean, so keep the flag (fail toward telling
  #                               the agent there is work, never toward silence)
  #   _pending_flag_currency_probe fails -> AGENTS.md still carries a PENDING
  #                               section from a DIFFERENT (or unparsable)
  #                               version. Neither ONBOARDING_GATE_OK nor
  #                               NEW_SKILLS_CSV can see this: a box whose
  #                               EXISTING skills all read qc-passed and grew
  #                               no new folders can still be sitting on a
  #                               stale, never-processed flag from a run weeks
  #                               ago. Its presence is not proof the work
  #                               happened -- see the probe's own header
  #                               comment (CONTENT-RECHECK-CONVERGENCE-PROBES,
  #                               above) for the 3-box pilot that reproduced
  #                               this: exit 0, stamp advanced, AGENTS.md and
  #                               MEMORY.md byte-identical, self-heal never ran.
  # ----------------------------------------------------------
  # >>> UPDATE-PENDING-FLAG-LIFECYCLE-BEGIN (extracted verbatim by
  #     tests/unit/update-skills-pending-flag-staleness.test.sh)
  _RESUME_NEEDED="no"
  [ "${ONBOARDING_GATE_OK:-unknown}" = "no" ] && _RESUME_NEEDED="yes"       # gate proved unverified skills remain
  [ "${ONBOARDING_GATE_OK:-unknown}" = "unknown" ] && _RESUME_NEEDED="yes"  # gate did not run -- do not claim clean
  [ -n "${NEW_SKILLS_CSV:-}" ] && _RESUME_NEEDED="yes"                      # new numbered skills need activation
  _pending_flag_currency_probe || _RESUME_NEEDED="yes"                     # a stale/unparsable PENDING section is outstanding

  echo ""
  if [ "$_RESUME_NEEDED" = "yes" ]; then
    echo "  Writing UPDATE PENDING flag for agent activation..."
    write_update_pending_flag "$ONBOARDING_VERSION" "$NEW_SKILLS_CSV"
  else
    echo "  Verification gate GREEN and no new skills — removing the UPDATE PENDING flag (and sweeping any stale one)..."
    clear_update_pending_flag
  fi
  # <<< UPDATE-PENDING-FLAG-LIFECYCLE-END

  # ----------------------------------------------------------
  # v17.0.21: make roll-time activation SELF-HEALING. When this roll left work
  # for the agent (new numbered skills copied, OR the verification gate did NOT
  # pass), install the SAME SILENT, bounded, self-removing onboarding-resume cron
  # that install.sh installs — so the activation flag we just wrote is actually
  # driven to qc-passed autonomously instead of waiting on a human. CONDITIONAL:
  # if there is NO pending activation (gate green AND no new skills) we install
  # NOTHING. IDEMPOTENT: install_onboarding_resume_cron() leaves any existing
  # cron in place. SILENT: the cron carries no --channel/--to/--announce (it is a
  # main-session self-ping); it can never push to a client chat.
  if [ "$_RESUME_NEEDED" = "yes" ]; then
    echo "  Pending activation detected — ensuring the SILENT onboarding-resume cron (idempotent)..."
    if command -v install_onboarding_resume_cron >/dev/null 2>&1; then
      install_onboarding_resume_cron || echo "  ⚠ onboarding-resume cron install reported an issue (non-fatal; agent still has the flag)"
    else
      echo "  ⚠ install_onboarding_resume_cron unavailable (resume-cron lib not sourced) — skipping cron (agent still has the AGENTS.md flag)"
    fi
  else
    echo "  ✓ No pending activation (gate green, no new skills) — onboarding-resume cron NOT installed (nothing to self-heal)."
  fi

  echo "  Sending Telegram notification..."
  # ----------------------------------------------------------
  # FIX 1: HONEST REPORTING CONTRACT. The headline is CONDITIONAL on the
  # verification gate (ONBOARDING_GATE_OK) AND the workforce qc-completeness
  # exit code (QC_COMPLETENESS_RC, previously ignored). We NEVER say
  # "complete/installed/onboarded" unless BOTH gates pass. Otherwise we report
  # the truth: how many skills are verified vs. not, and that resume will retry.
  # ----------------------------------------------------------
  _TG_HEADLINE=""
  if [ "$ONBOARDING_GATE_OK" = "yes" ] && { [ "${QC_COMPLETENESS_RC:-0}" -eq 0 ] || [ "${QC_COMPLETENESS_RC:-0}" -eq 4 ]; }; then
    # Gate passed (qc=PASS, or NO_WORKFORCE which is not an install failure).
    _TG_HEADLINE="✅ OpenClaw skill update ${ONBOARDING_VERSION} verified-installed.

${ONBOARDING_GATE_SUMMARY:-all skills verified}."
  else
    # Honest partial. NEVER claim done.
    _TG_HEADLINE="⏳ OpenClaw skill update ${ONBOARDING_VERSION}: files synced, NOT all verified yet.

${ONBOARDING_GATE_SUMMARY:-verification gate did not produce a summary}.

The onboarding-resume cron will keep re-firing wiring + QC until every skill passes (it does NOT stop on a self-declared 'done')."
  fi

  send_telegram_progress "${_TG_HEADLINE}

New skills (need activation): ${NEW_SKILLS_CSV:-none -- updates only}.

Workforce QC: ${QC_STATUS_LINE:-not run} (exit ${QC_COMPLETENESS_RC:-?})

GHL MCP (Tier 2): ${GHL_MCP_STATUS_LINE:-no STATUS line captured}

Persona-index provisioning: ${_PIDX_SKIP_WARNINGS:+⚠️ SKIPPED — }${_PIDX_SKIP_WARNINGS:-OK (no skip warnings)}

Paste this to your agent:

▶ \"I just ran update-skills.sh. There is an UPDATE PENDING flag at the top of my AGENTS.md describing what changed. Check .onboarding-state.json and run the verification gate (scripts/onboarding-state.sh). Activate + QC every skill that is not yet qc-passed. Do NOT report done until the gate passes. Send me a summary when the gate is green.\"

(If you didn't get THIS Telegram note, the same instructions are also printed in your Terminal.)"

  case "$TELEGRAM_LAST_RESULT" in
    sent-operator:*)        echo "  ✓ Update-result note sent to OPERATOR chat ${TELEGRAM_LAST_RESULT#sent-operator:} (not the client)" ;;
    logged-no-operator-chat) echo "  ℹ Update-result note LOG-ONLY (no operator escalation chat configured) — agent picks up the AGENTS.md UPDATE PENDING flag; client is NOT auto-notified" ;;
    no-openclaw-cli)        echo "  ⚠ Update-result note skipped -- openclaw CLI not on PATH (Terminal backup block below)" ;;
    failed-operator:*)      echo "  ⚠ Update-result operator send FAILED -- see $LOG_FILE (NOT routed to client; Terminal backup block below)" ;;
  esac

  # Always print the backup block so client is never stranded
  cat <<'BACKUP_BLOCK'

╔════════════════════════════════════════════════════════════════════╗
║   BACKUP -- IF YOU DID NOT GET A TELEGRAM NOTE                      ║
╠════════════════════════════════════════════════════════════════════╣
║                                                                    ║
║   Open whatever you use to talk to your OpenClaw agent (Telegram,  ║
║   web UI, terminal chat -- whatever you have set up).               ║
║                                                                    ║
║   Paste this EXACT message to your agent (copy between the         ║
║   >>> and <<< markers):                                            ║
║                                                                    ║
║   >>>                                                              ║
║   I just ran update-skills.sh. There is an UPDATE PENDING flag     ║
║   at the top of my AGENTS.md describing what changed. Please       ║
║   follow the activation steps for any new skills listed in the     ║
║   flag. Run QC after each one. Send me a summary when complete.    ║
║   <<<                                                              ║
║                                                                    ║
║   Your agent will read the flag and walk through the activation    ║
║   for you. You don't need to type any other commands.              ║
║                                                                    ║
╚════════════════════════════════════════════════════════════════════╝

BACKUP_BLOCK

  # ----------------------------------------------------------
  # DEFECT 2 — FINAL VERDICT ON THE GHL MCP TIER-2 RUNTIME.
  #
  # Before this, wire_ghl_mcp printed the runtime FATALs and the run exited 0.
  # A 3-box pilot therefore reported "exit 0, 17-20 skills updated, stamp
  # advanced" on three boxes that were each carrying 7-10 runtime FATALs. That
  # is a HOLLOW UPDATE reported as a success, and it is the reason the hardening
  # "shipped" for a full release without landing anywhere.
  #
  # The exit code is 2, not 1, on purpose — see the long note at the latch in
  # wire_ghl_mcp. 2 is this script's documented "skills content is current, the
  # box's infrastructure needs attention" code, which fleet drivers already
  # distinguish from "stamp withheld" (1). Withholding the content stamp over a
  # pre-existing Tier-2 defect would brick rolls on boxes whose skills are
  # perfectly current.
  # ----------------------------------------------------------
  # ----------------------------------------------------------
  # U6D-CC-RUNTIME — FINAL VERDICT ON THE COMMAND CENTER RUNTIME-CONFIG
  # RECONCILER (2026-08-04 fix; NOT the "DEFECT 2" GHL-MCP block above — a
  # separate defect, same latch/continue/report/exit-non-zero pattern).
  #
  # Before this fix, ANY non-zero exit from reconcile_command_center_runtime.py
  # — including an UNPROVISIONED box (no ZHC identity yet, a KNOWN valid state)
  # and a genuine "refusing to clobber invalid existing data" case with no
  # remediation path — set _U6D_CC_CONFIG_FAIL, which withheld the
  # skills-content stamp entirely (exit 1) on boxes where SKILL38 and the GHL
  # MCP had both converged perfectly. The unprovisioned case is now a plain
  # advisory (see _WORKFORCE_INCOMPLETE_NOTES above) and never reaches here.
  # A genuine reconciliation failure (rc=1: invalid/corrupt existing CC
  # runtime data, or an I/O error) now latches _U6D_CC_RUNTIME_FATAL instead:
  # the stamp still writes, and this run's exit code becomes 2 — the SAME
  # "content current, infrastructure needs attention" code the GHL MCP block
  # above already uses, so fleet drivers do not need a new code to recognize
  # it.
  # ----------------------------------------------------------
  # REGISTRY-PARITY-CALL (post). Runs after EVERY write this updater makes,
  # immediately before the final return -- see registry_parity_gate() above.
  # A registry-parity failure is more severe than the infra-degraded (exit 2)
  # cases below: it is possible agent data was just lost, so this OVERRIDES
  # whatever exit code the rest of this run would otherwise report and exits
  # 78 (EX_CONFIG) directly, the moment it is detected, rather than folding
  # into the normal return-code decision tree.
  _REGISTRY_PARITY_POST_RC=0
  registry_parity_gate post || _REGISTRY_PARITY_POST_RC=$?
  if [ "$_REGISTRY_PARITY_POST_RC" -ne 0 ]; then
    echo "FATAL: registry-parity gate REFUSED at the END of this run (exit 78 / EX_CONFIG) -- see the banner above." >&2
    echo "       Skills content may already be current on disk, but the agent registry did not verify -- treat this box as UNVERIFIED, not updated." >&2
    exit 78
  fi

  if [ "${_U6D_CC_RUNTIME_FATAL:-no}" = "yes" ]; then
    {
      echo ""
      echo "  ============================================================"
      echo "  UPDATE COMPLETED, BUT THE COMMAND CENTER RUNTIME CONFIG (U6d)"
      echo "  COULD NOT BE RECONCILED."
      echo "  Skills content IS current and the version stamp WAS written."
      printf '%s\n' "${_U6D_CC_RUNTIME_DETAIL:-  (no detail captured)}" | sed 's/^/    /'
      echo ""
      echo "  The reconciler's own FATAL message above states the exact"
      echo "  remediation command for this box's specific data problem."
      echo "  Fix it, then re-run:"
      echo "    python3 \"\$OC_ROOT\"/skills/23-ai-workforce-blueprint/../shared-utils/reconcile_command_center_runtime.py \\"
      echo "      --workspace \$OC_WORKSPACE --command-center-dir <your Command Center checkout>"
      echo "  (\$OC_ROOT is ~/.openclaw on Mac, /data/.openclaw on VPS)"
      echo ""
      echo "  Exiting 2 = content current, infrastructure needs attention."
      echo "  This is deliberately NOT 0: a roll that leaves the Command"
      echo "  Center departments/branding unreconciled has not fully succeeded."
      echo "  ============================================================"
      echo ""
    } >&2
  fi

  if [ "${GHL_MCP_RUNTIME_FATAL:-no}" = "yes" ]; then
    {
      echo ""
      echo "  ============================================================"
      echo "  UPDATE COMPLETED, BUT THE GHL MCP (Tier 2) IS MISCONFIGURED."
      echo "  Skills content IS current and the version stamp WAS written."
      echo "  The INSTALLED MCP service does not match the shipped standard:"
      printf '%s\n' "${GHL_MCP_RUNTIME_DETAIL:-  (no detail captured)}" | sed 's/^/    /'
      echo ""
      echo "  autostart on this run: ${GHL_MCP_AUTOSTART_RAN:-unknown}"
      echo "  Re-run the autostart, then re-assert:"
      echo "    bash \"\$OC_ROOT\"/scripts/ghl-mcp-autostart.sh"
      echo "    bash \"\$OC_ROOT\"/scripts/ghl-mcp-assert-runtime.sh"
      echo "  (\$OC_ROOT is ~/.openclaw on Mac, /data/.openclaw on VPS)"
      echo ""
      echo "  Exiting 2 = content current, infrastructure needs attention."
      echo "  This is deliberately NOT 0: a roll that leaves the MCP"
      echo "  misconfigured has not succeeded."
      echo "  ============================================================"
      echo ""
    } >&2
  fi

  if [ "${GHL_MCP_RUNTIME_FATAL:-no}" = "yes" ] || [ "${_U6D_CC_RUNTIME_FATAL:-no}" = "yes" ]; then
    return 2
  fi
  return 0
}

main "$@"
