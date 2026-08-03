#!/usr/bin/env bash
# qc-assert-pin-delivery-paths.sh — v21.6.0
#
# STATIC CROSS-REFERENCE GATE: every path a script SEARCHES for
# config/ghl-mcp-pin.env must be a path an installer actually POPULATES.
#
# ─────────────────────────────────────────────────────────────────────────────
# WHY THIS EXISTS
#
# v21.5.0 shipped config/ghl-mcp-pin.env as "the single source of truth for
# every launch surface", with five resolver candidates in the autostart, five
# in the probe, four in the VPS overlay and three in the static QC gate — and
# delivered the file to NOT ONE of them. update-skills.sh copied scripts/ and
# nothing else and then deleted its temp clone. Every weekly-updated box fell
# through to the hardcoded fallback constants baked into the scripts, a pin
# bump propagated nowhere, and the box-side QC gate hard-failed while CI stayed
# green — because CI runs in the one layout where the file exists.
#
# That whole class of bug is "a resolver list and a delivery list that nobody
# ever compared". This gate compares them, on every CI run, mechanically.
#
# ─────────────────────────────────────────────────────────────────────────────
# HOW IT WORKS
#
# It parses the LITERAL candidate paths out of each consumer's resolver loop
# (the lines mentioning ghl-mcp-pin.env), normalises $HOME / $OC_CONFIG / the
# script-relative forms to a small set of symbolic roots, and asserts each one
# is in the DELIVERED set declared below. The delivered set is not guessed: it
# is asserted separately against the installers, so a delivery step that is
# deleted or renamed fails this gate too.
#
# SYMBOLIC ROOTS
#   REPO        the repo checkout itself ($SELF_DIR/../config, …/../../../config)
#               — always allowed: it is how CI and a developer checkout resolve.
#   MAC_CONFIG      $HOME/.openclaw/config
#   MAC_ONBOARDING  $HOME/.openclaw/onboarding/config
#   MAC_SKILLS      $HOME/.openclaw/skills/config
#   VPS_CONFIG      /data/.openclaw/config
#   VPS_ONBOARDING  /data/.openclaw/onboarding/config
#   VPS_SKILLS      /data/.openclaw/skills/config
#
# Exit codes:
#   0  every resolver path is delivered, and both installers still deliver
#   1  INVARIANT VIOLATED — a resolver searches somewhere nothing populates,
#      or an installer stopped delivering config/
#
# Usage: bash scripts/qc-assert-pin-delivery-paths.sh [--quiet]
#
# Wired in:
#   .github/workflows/ghl-mcp-supervised-guard.yml
#   scripts/qc-system-integrity.sh (CHECK X.13c)

set -uo pipefail

QUIET=0
for _arg in "$@"; do [ "$_arg" = "--quiet" ] && QUIET=1; done

_pass() { [ "$QUIET" = "0" ] && printf '[qc-pin-delivery] PASS  %s\n' "$*"; return 0; }
_fail() { printf '[qc-pin-delivery] FATAL INVARIANT VIOLATED — %s\n' "$*" >&2; return 0; }
_info() { [ "$QUIET" = "0" ] && printf '[qc-pin-delivery] INFO  %s\n' "$*"; return 0; }

FAILURES=0
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SELF_DIR/.." && pwd)"

# ─────────────────────────────────────────────────────────────────────────────
# 1. THE DELIVERED SET — what the installers actually populate.
#    MAC_CONFIG / VPS_CONFIG      <- update-skills.sh AND install.sh (explicit)
#    MAC_ONBOARDING / VPS_ONBOARDING <- install.sh's whole-repo copy into
#                                       $OC_CONFIG/onboarding/
#    MAC_SKILLS / VPS_SKILLS      <- NOT delivered by anything. Kept out of the
#                                    set on purpose: those two candidates were
#                                    dead weight in v21.5.0 and a resolver that
#                                    lists an undeliverable path is a lie about
#                                    where the file can be.
# ─────────────────────────────────────────────────────────────────────────────
DELIVERED="REPO MAC_CONFIG VPS_CONFIG MAC_ONBOARDING VPS_ONBOARDING"

_is_delivered() {
  case " $DELIVERED " in *" $1 "*) return 0 ;; *) return 1 ;; esac
}

# ─────────────────────────────────────────────────────────────────────────────
# 2. Normalise one literal candidate path to a symbolic root.
# ─────────────────────────────────────────────────────────────────────────────
_classify() {
  case "$1" in
    *'$SELF_DIR/../config/ghl-mcp-pin.env'*)             printf 'REPO' ;;
    *'$SELF_DIR/../../../config/ghl-mcp-pin.env'*)       printf 'REPO' ;;
    *'$REPO_ROOT/config/ghl-mcp-pin.env'*)               printf 'REPO' ;;
    *'/.openclaw/onboarding/config/ghl-mcp-pin.env'*)
      case "$1" in /data/*) printf 'VPS_ONBOARDING' ;; *) printf 'MAC_ONBOARDING' ;; esac ;;
    *'/.openclaw/skills/config/ghl-mcp-pin.env'*)
      case "$1" in /data/*) printf 'VPS_SKILLS' ;; *) printf 'MAC_SKILLS' ;; esac ;;
    *'/.openclaw/config/ghl-mcp-pin.env'*)
      case "$1" in /data/*) printf 'VPS_CONFIG' ;; *) printf 'MAC_CONFIG' ;; esac ;;
    *) printf 'UNKNOWN' ;;
  esac
}

# ─────────────────────────────────────────────────────────────────────────────
# 3. Extract the literal candidates from a consumer, ignoring comment lines
#    (the resolver lists are documented in prose right above themselves).
# ─────────────────────────────────────────────────────────────────────────────
_candidates() {
  local f="$1"
  sed 's/#.*$//' "$f" 2>/dev/null \
    | grep -o '"[^"]*ghl-mcp-pin\.env"' 2>/dev/null \
    | tr -d '"' \
    | sort -u
}

CONSUMERS="
scripts/ghl-mcp-autostart.sh
scripts/ghl-mcp-probe.sh
scripts/ghl-mcp-assert-runtime.sh
scripts/qc-assert-ghl-mcp-supervised.sh
scripts/ghl-mcp-check-pin-digest.sh
platform/vps/36-ghl-mcp-setup-scripts/start-ghl-mcp-server.sh
"

for rel in $CONSUMERS; do
  f="$REPO_ROOT/$rel"
  if [ ! -f "$f" ]; then
    _fail "$rel is missing — it is one of the consumers whose resolver list this gate keeps honest."
    FAILURES=$((FAILURES+1))
    continue
  fi
  found_any=0
  while IFS= read -r cand; do
    [ -n "$cand" ] || continue
    found_any=1
    root="$(_classify "$cand")"
    if [ "$root" = "UNKNOWN" ]; then
      _fail "$rel searches '$cand', which this gate cannot classify. Either use one of the canonical roots or teach _classify() about the new one AND make an installer populate it."
      FAILURES=$((FAILURES+1))
    elif _is_delivered "$root"; then
      _pass "$rel -> $cand  [$root, delivered]"
    else
      _fail "$rel searches '$cand'  [$root] — NOTHING delivers config/ there. A resolver candidate that no installer populates is exactly the v21.5.0 defect: the file exists in the repo and on no box."
      FAILURES=$((FAILURES+1))
    fi
  done <<EOF
$(_candidates "$f")
EOF
  if [ "$found_any" = "0" ]; then
    _fail "$rel declares NO ghl-mcp-pin.env candidate at all — it can no longer read the pin."
    FAILURES=$((FAILURES+1))
  fi
done

# ─────────────────────────────────────────────────────────────────────────────
# 4. The delivery side must still exist. A resolver list that matches a
#    delivery step which was quietly deleted is the same bug wearing a hat.
# ─────────────────────────────────────────────────────────────────────────────
_installer_delivers() {   # <file> <human name>
  local f="$1" name="$2" body
  if [ ! -f "$f" ]; then
    _fail "$name not found at $f — cannot verify it delivers config/."
    FAILURES=$((FAILURES+1)); return 0
  fi
  body="$(sed 's/#.*$//' "$f" 2>/dev/null)"
  if grep -qF 'OC_CANONICAL_CONFIG_DEST' <<< "$body"; then
    _pass "$name declares the canonical config/ delivery destination (OC_CANONICAL_CONFIG_DEST)"
  else
    _fail "$name no longer contains the canonical config/ delivery step (marker OC_CANONICAL_CONFIG_DEST). Boxes would stop receiving config/ghl-mcp-pin.env and every autostart would report PIN_UNVERIFIED."
    FAILURES=$((FAILURES+1))
  fi
  if grep -qF 'ghl-mcp-pin.env' <<< "$body"; then
    _pass "$name asserts the pin file landed after delivery"
  else
    _fail "$name does not assert config/ghl-mcp-pin.env is readable after delivery — a silent delivery failure would surface only as a fleet-wide PIN_UNVERIFIED much later."
    FAILURES=$((FAILURES+1))
  fi
}

_installer_delivers "$REPO_ROOT/update-skills.sh" "update-skills.sh"
_installer_delivers "$REPO_ROOT/install.sh"       "install.sh"

# ─────────────────────────────────────────────────────────────────────────────
# 5. The pin file itself must be in the repo — it is the thing being delivered.
# ─────────────────────────────────────────────────────────────────────────────
if [ -f "$REPO_ROOT/config/ghl-mcp-pin.env" ]; then
  _pass "config/ghl-mcp-pin.env exists in the repo"
else
  _fail "config/ghl-mcp-pin.env is missing from the repo — there is nothing to deliver."
  FAILURES=$((FAILURES+1))
fi

if [ "$FAILURES" -gt 0 ]; then
  _fail "$FAILURES pin-delivery cross-reference violation(s) — a resolver searches where nothing delivers, or a delivery step was removed."
  exit 1
fi
_info "resolver lists and installer delivery destinations agree."
exit 0
