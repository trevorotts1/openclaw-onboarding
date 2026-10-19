#!/usr/bin/env bash
# qc-assert-ghl-mcp-supervised.sh — v22.0.0
#
# STATIC QC INVARIANT: the GHL Community MCP (Tier 2, skill 36) is RETIRED.
#
# This file used to enforce that the community service was PROPERLY supervised
# (launchd KeepAlive / pm2 + resurrect / systemd). That world is gone: the
# operator decision is that the community MCP is retired, fresh installs omit it
# entirely, and updated boxes must finish VERIFIED_OFF (or explicitly
# MIGRATION_FAILED with real residual state). It must not be able to restart
# itself.
#
# The old gate PASSED whenever its own inputs were absent, so DELETING the
# scripts made it green. This rewrite never treats absence as "nothing to
# enforce". It asserts the retirement state explicitly:
#
#   REPO LAYOUT (install.sh + update-skills.sh at the repo root):
#     1. install.sh must not invoke the community start/autostart path — fresh
#        installs omit the service entirely.
#     2. update-skills.sh must carry the ORDERED RETIREMENT TRANSACTION
#        contract: inventory, stage, archive, disable-resurrection, stop,
#        verify, receipt, and the two terminal states VERIFIED_OFF /
#        MIGRATION_FAILED. A roll that deletes the old scripts but cannot retire
#        a live box is a red build, not a green one.
#     3. Any lifecycle script still shipped must carry the GHL_MCP_RETIRED
#        refusal marker (an inert tombstone, never a start surface).
#     4. No shipped script may start, restart, register, schedule or resurrect
#        the community MCP (launchctl bootstrap/kickstart, pm2 start/restart/
#        resurrect, systemctl enable/start, openclaw mcp set
#        ghl-community-mcp, @reboot cron, setsid loop).
#     5. The OFFICIAL ghl-mcp (Tier 1) registration must still exist — retirement
#        removes Tier 2 only.
#
#   BOX LAYOUT (no repo):
#     The delivered script trees must contain NO community lifecycle script.
#     That absence is the explicit assertion (every named tree is checked), not
#     a silent skip.
#
# Exit codes:
#   0  retirement state holds
#   1  retirement state VIOLATED (a resurrection surface still ships, the update
#      transaction is missing, or the official Tier 1 registration is gone)
#
# Usage:
#   bash qc-assert-ghl-mcp-supervised.sh
#   bash qc-assert-ghl-mcp-supervised.sh --quiet
#
# Wired in:
#   scripts/qc-system-integrity.sh  (CHECK X.12)

set -uo pipefail

QUIET=0
for _arg in "$@"; do
  [[ "$_arg" == "--quiet" ]] && QUIET=1
done

_pass() { [ "$QUIET" = "0" ] && printf '[qc-ghl-mcp-supervised] PASS  %s\n' "$*"; }
_fail() { printf '[qc-ghl-mcp-supervised] FATAL INVARIANT VIOLATED — %s\n' "$*" >&2; }
_info() { [ "$QUIET" = "0" ] && printf '[qc-ghl-mcp-supervised] INFO  %s\n' "$*"; }

FAILURES=0
_fail_counts() { FAILURES=$((FAILURES+1)); }

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SELF_DIR/.." 2>/dev/null && pwd || echo "$SELF_DIR")"
SELF_BASE="$(basename "${BASH_SOURCE[0]}")"

# Strip full-line and inline comments while preserving line numbers, so prose
# documenting a retired launch surface never trips its own gate.
_code_of() {
  awk '{ sub(/#.*/, ""); printf "%d:%s\n", NR, $0 }' "$1" 2>/dev/null
}

# ── Resurrection surfaces that must not exist in shipped code ────────────────
FORBIDDEN_PATTERNS=(
  'launchctl[[:space:]]+(bootstrap|kickstart)[^|;]*com\.clawd\.ghl-mcp'
  'pm2[[:space:]]+(start|restart|startOrReload)[^|;]*ghl-community-mcp'
  'ghl-community-mcp[^|;]*pm2[[:space:]]+(start|restart|startOrReload)'
  'pm2[[:space:]]+resurrect[^|;]*ghl'
  'ghl[^|;]*pm2[[:space:]]+resurrect'
  'systemctl[[:space:]]+(enable|start|restart)[^|;]*ghl-mcp'
  'openclaw[[:space:]]+mcp[[:space:]]+set[^|;]*ghl-community-mcp'
  'setsid[^|;]*ghl-community-mcp'
  '@reboot[^|;]*ghl'
)
# A retirement tombstone/tool legitimately contains supervisor verbs (delete,
# bootout, disable, stop) and historical dead branches. Its guarantee is the
# refusal marker plus its own behavioural tests, so the generic start-verb scan
# exempts it. Everything WITHOUT the marker is scanned normally.
RETIRE_MARKER_RE='GHL_MCP_RETIRED|RETIRED_VERIFIED_OFF|START_REFUSED_RETIRED'
FORBIDDEN_RE="$(printf '%s|' "${FORBIDDEN_PATTERNS[@]}")"
FORBIDDEN_RE="${FORBIDDEN_RE%|}"

# True when a file carries a retirement refusal/verified marker.
# NOTE: never `grep -q` a large producer under `pipefail` — grep -q exits at the
# first match, the writer takes SIGPIPE, and pipefail turns a MATCH into 141.
_has_retire_marker() {
  # Intent declarations legitimately live in the file header, so scan RAW text.
  # No pipeline here, so pipefail/SIGPIPE cannot turn a match into a failure.
  grep -qE "$RETIRE_MARKER_RE" "$1" 2>/dev/null
}

# Scan a newline-delimited file list from stdin (paths may contain spaces).
# Prints every offending file:line and returns 1 on a hit.
_scan_forbidden() {
  local f hits rc=0
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    [ -f "$f" ] || continue
    case "$(basename "$f")" in "$SELF_BASE") continue ;; esac
    if _has_retire_marker "$f"; then
      continue   # retirement tombstone/tool — allowed to contain stop/delete verbs
    fi
    hits="$(_code_of "$f" | grep -E "$FORBIDDEN_RE" 2>/dev/null || true)"
    if [ -n "$hits" ]; then
      rc=1
      printf '%s\n' "$hits" | while IFS= read -r line; do
        printf '[qc-ghl-mcp-supervised] FATAL INVARIANT VIOLATED — %s:%s is a live community-MCP resurrection surface (RETIRED)\n' "$f" "$line" >&2
      done
    fi
  done
  return "$rc"
}

# A tree carrying EITHER installer is a repo layout: a half-deleted repo must
# not fall through to the box branch and look green.
REPO_LAYOUT=0
if [ -f "$REPO_ROOT/install.sh" ] || [ -f "$REPO_ROOT/update-skills.sh" ]; then
  REPO_LAYOUT=1
fi

# ─────────────────────────────────────────────────────────────────────────────
# REPO LAYOUT — enforce the retirement contract.
# ─────────────────────────────────────────────────────────────────────────────
if [ "$REPO_LAYOUT" = "1" ]; then
  _info "repo layout at $REPO_ROOT — enforcing the community-MCP retirement contract"

  # CHECK 1: fresh installs must OMIT the community MCP entirely.
  if _code_of "$REPO_ROOT/install.sh" | grep -q 'ghl-mcp-autostart'; then
    _fail "install.sh still invokes the community MCP start path (ghl-mcp-autostart) — fresh installs must omit Tier 2 entirely (RETIRED)."
    _fail_counts
  else
    _pass "install.sh omits the community MCP start path (fresh installs retired)"
  fi

  # CHECK 2: the update path must carry the ordered retirement transaction.
  RETIRE_FILES="$REPO_ROOT/update-skills.sh"
  for f in "$REPO_ROOT/scripts/ghl-mcp-autostart.sh" \
           "$REPO_ROOT"/scripts/ghl-mcp-retire*.sh "$REPO_ROOT"/scripts/ghl-mcp-retirement*.sh; do
    [ -f "$f" ] && RETIRE_FILES="$RETIRE_FILES
$f"
  done
  RETIRE_BODY=""
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    RETIRE_BODY="$RETIRE_BODY$(_code_of "$f")
"
  done <<EOF
$RETIRE_FILES
EOF

  RETIRE_BODY_LC="$(printf '%s' "$RETIRE_BODY" | tr '[:upper:]' '[:lower:]')"
  case "$RETIRE_BODY" in
    *--retire*|*ghl-mcp-retire*|*retire_ghl_mcp*|*retire_community_mcp*|*GHL_MCP_RETIRED*|*START_REFUSED_RETIRED*)
      _pass "the update path declares a community-MCP retirement entry point" ;;
    *)
      _fail "update-skills.sh (and any scripts/ghl-mcp-retire*.sh) declares NO retirement entry point — deleting the old scripts is not a migration; live boxes would never be retired."
      _fail_counts ;;
  esac

  for _token in VERIFIED_OFF MIGRATION_FAILED; do
    case "$RETIRE_BODY" in
      *"$_token"*) _pass "the update path can reach the terminal state $_token" ;;
      *)
        _fail "the update path never writes the terminal state $_token — the receipt cannot distinguish a verified retirement from a failed migration (RETIRED end state requires both)."
        _fail_counts ;;
    esac
  done

  for _token in inventory stage archive disable stop verify receipt; do
    case "$RETIRE_BODY_LC" in
      *"$_token"*) _pass "the ordered retirement transaction carries the '$_token' stage" ;;
      *)
        _fail "the ordered retirement transaction is missing the '$_token' stage — required sequence: inventory, stage, archive, disable resurrection, stop, verify, receipt."
        _fail_counts ;;
    esac
  done

  # CHECK 3: any lifecycle script still shipped must be an inert tombstone.
  LIFECYCLE_RELS="
scripts/ghl-mcp-autostart.sh
scripts/ghl-mcp-probe.sh
scripts/ghl-mcp-assert-runtime.sh
platform/vps/36-ghl-mcp-setup-scripts/start-ghl-mcp-server.sh
"
  for rel in $LIFECYCLE_RELS; do
    f="$REPO_ROOT/$rel"
    if [ -f "$f" ]; then
      if _has_retire_marker "$f"; then
        _pass "$rel is an inert retirement tombstone/tool (carries a refusal/verified marker)"
      else
        _fail "$rel still ships without a retirement refusal marker ($RETIRE_MARKER_RE) — a retired lifecycle script that can still start or heal the service is a resurrection surface."
        _fail_counts
      fi
    else
      _pass "$rel is retired (absent from the shipped tree)"
    fi
  done

  # CHECK 4: no shipped script may start/register/schedule/resurrect Tier 2.
  SCAN_FILES=""
  for f in "$REPO_ROOT/install.sh" "$REPO_ROOT/update-skills.sh" "$REPO_ROOT/force-update.sh"; do
    [ -f "$f" ] && SCAN_FILES="$SCAN_FILES
$f"
  done
  if [ -d "$REPO_ROOT/scripts" ]; then
    while IFS= read -r f; do
      [ -n "$f" ] || continue
      case "$(basename "$f")" in "$SELF_BASE") continue ;; esac
      SCAN_FILES="$SCAN_FILES
$f"
    done <<EOF
$(find "$REPO_ROOT/scripts" -type f -name '*.sh' 2>/dev/null)
EOF
  fi
  if [ -d "$REPO_ROOT/platform" ]; then
    while IFS= read -r f; do
      [ -n "$f" ] || continue
      SCAN_FILES="$SCAN_FILES
$f"
    done <<EOF
$(find "$REPO_ROOT/platform" -type f \( -name '*.sh' -o -name '*.plist' -o -name '*.service' \) 2>/dev/null)
EOF
  fi
  if [ -d "$REPO_ROOT/36-ghl-mcp-setup" ]; then
    while IFS= read -r f; do
      [ -n "$f" ] || continue
      SCAN_FILES="$SCAN_FILES
$f"
    done <<EOF
$(find "$REPO_ROOT/36-ghl-mcp-setup" -type f -name '*.sh' 2>/dev/null)
EOF
  fi
  if printf '%s\n' "$SCAN_FILES" | _scan_forbidden; then
    _pass "no shipped script starts, restarts, registers, schedules or resurrects the community MCP"
  else
    _fail "one or more shipped scripts still contain a community-MCP resurrection surface (see file:line above)."
    _fail_counts
  fi

  # CHECK 5: official MCP (Tier 1) registration is preserved.
  OFFICIAL_HIT=0
  for f in "$REPO_ROOT/install.sh" "$REPO_ROOT/update-skills.sh" \
           "$REPO_ROOT/36-ghl-mcp-setup/wire.sh" "$REPO_ROOT/36-ghl-mcp-setup/INSTALL.md"; do
    [ -f "$f" ] || continue
    grep -qE 'mcp[[:space:]]+set[[:space:]]+ghl-mcp' "$f" 2>/dev/null && OFFICIAL_HIT=1
  done
  if [ "$OFFICIAL_HIT" = "1" ]; then
    _pass "the official ghl-mcp (Tier 1) registration surface is preserved"
  else
    _fail "no shipped surface registers the official ghl-mcp (Tier 1) — retirement removes Tier 2 ONLY; the official MCP registration must survive."
    _fail_counts
  fi
else
  # ───────────────────────────────────────────────────────────────────────────
  # BOX LAYOUT — assert the retired delivered tree explicitly. Every named
  # location is checked; a stale lifecycle script is a resurrection surface even
  # when it is not currently loaded.
  # ───────────────────────────────────────────────────────────────────────────
  _info "no repo layout at $REPO_ROOT — asserting the RETIRED delivered-tree state"

  LIVE_HITS=""
  for base in "$HOME/.openclaw" "/data/.openclaw" \
              "$HOME/.openclaw/skills" "/data/.openclaw/skills"; do
    for sub in scripts onboarding/scripts; do
      for name in ghl-mcp-autostart.sh ghl-mcp-probe.sh ghl-mcp-assert-runtime.sh; do
        [ -f "$base/$sub/$name" ] && LIVE_HITS="$LIVE_HITS
$base/$sub/$name"
      done
    done
    for name in start-ghl-mcp-server.sh; do
      [ -f "$base/platform/vps/36-ghl-mcp-setup-scripts/$name" ] \
        && LIVE_HITS="$LIVE_HITS
$base/platform/vps/36-ghl-mcp-setup-scripts/$name"
    done
  done

  if [ -z "$LIVE_HITS" ]; then
    _pass "no community MCP lifecycle script is delivered in any named tree (RETIRED)"
  else
    while IFS= read -r f; do
      [ -n "$f" ] || continue
      _fail "$f is still delivered — a retired lifecycle script can restart the community MCP (RETIRED)."
      _fail_counts
    done <<EOF
$(printf '%s\n' "$LIVE_HITS" | sed '/^$/d')
EOF
  fi

  # Delivered trees must also carry no supervisor definition that loads it.
  PLIST_HITS=""
  for base in "$HOME/.openclaw" "/data/.openclaw" "$HOME"/Library/LaunchAgents; do
    for name in com.clawd.ghl-mcp.plist com.clawd.ghl-mcp-probe.plist; do
      [ -f "$base/$name" ] && PLIST_HITS="$PLIST_HITS
$base/$name"
    done
  done
  if [ -z "$PLIST_HITS" ]; then
    _pass "no community MCP launchd definition is delivered (RETIRED)"
  else
    while IFS= read -r f; do
      [ -n "$f" ] || continue
      _fail "$f is still present — RunAtLoad/StartInterval can resurrect the retired community MCP."
      _fail_counts
    done <<EOF
$(printf '%s\n' "$PLIST_HITS" | sed '/^$/d')
EOF
  fi
fi

# ── Verdict ───────────────────────────────────────────────────────────────────
if [ "$FAILURES" -gt 0 ]; then
  _fail "$FAILURES community-MCP retirement invariant(s) violated — the retired service can still be installed, started, registered or resurrected."
  exit 1
fi
_pass "community MCP retirement state holds (no install path, no supervision/resurrection surface, official Tier 1 preserved)."
exit 0
