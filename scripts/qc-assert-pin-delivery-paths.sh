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
# RETIREMENT AWARENESS (v22.0.0)
#
# The community MCP is RETIRED. In a retired tree the community pin is EXEMPT:
# it must not be demanded from installers, and consumers that still mention it
# (the retirement tool, policy gates) do not force delivery. This check does NOT
# go green on deletion: while any OTHER file under config/ still ships, both
# installers must still carry the canonical config/ delivery step. Retirement is
# detected from the pin file (absent or marked retired) or an explicit
# retirement entry point in the updaters.
#
# Exit codes:
#   0  every still-required resolver path is delivered, and both installers still
#      deliver the config/ files that STILL SHIP (the retired pin is exempt)
#   1  INVARIANT VIOLATED — a live resolver searches somewhere nothing
#      populates, or an installer stopped delivering a still-shipped config/
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
# 0. RETIREMENT AWARENESS — v22.0.0
#
# The community MCP (Tier 2) is RETIRED. Demanding delivery of its pin would
# force a dead config back onto every box; ignoring a still-shipped config would
# recreate the v21.5.0 defect. So retirement is detected explicitly (pin absent,
# pin marked retired, or the updater carries the retirement entry point) and
# changes only WHICH files must be delivered:
#   * retired  -> the community pin is exempt; any OTHER still-shipped config/
#                 file must still be delivered (marker + landing assert).
#   * live     -> the original invariant holds unchanged.
# ─────────────────────────────────────────────────────────────────────────────
RETIRED=0
PIN_PATH="$REPO_ROOT/config/ghl-mcp-pin.env"
if [ ! -f "$PIN_PATH" ]; then
  RETIRED=1
elif grep -qiE '^GHL_MCP_(RETIRED|STATUS)=.*(1|true|yes|retired)' "$PIN_PATH" 2>/dev/null; then
  RETIRED=1
else
  for _rf in "$REPO_ROOT/update-skills.sh" "$REPO_ROOT/install.sh" "$REPO_ROOT"/scripts/ghl-mcp-retire*.sh; do
    [ -f "$_rf" ] || continue
    if grep -qE 'ghl-mcp-retire|retire_ghl_mcp|GHL_MCP_RETIRED' "$_rf" 2>/dev/null; then
      RETIRED=1
      break
    fi
  done
fi
if [ "$RETIRED" = "1" ]; then
  _info "community MCP is RETIRED — delivery applies only to still-shipped config/"
else
  _info "community MCP is still live in this tree — the full pin-delivery invariant applies"
fi

# A runtime consumer that survives retirement can read the pin and start the
# service again. Policy-only consumers (QC/digest) may stay; they must simply
# stop demanding delivery of the retired pin.
RUNTIME_CONSUMERS="scripts/ghl-mcp-autostart.sh scripts/ghl-mcp-probe.sh scripts/ghl-mcp-assert-runtime.sh platform/vps/36-ghl-mcp-setup-scripts/start-ghl-mcp-server.sh"
_is_runtime_consumer() {
  case " $RUNTIME_CONSUMERS " in *" $1 "*) return 0 ;; *) return 1 ;; esac
}

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
    if [ "$RETIRED" = "1" ]; then
      _pass "$rel is retired (absent from the shipped tree)"
    elif _is_runtime_consumer "$rel"; then
      _fail "$rel is missing — it is one of the RUNTIME consumers whose resolver list this gate keeps honest, and the community MCP is NOT retired."
      FAILURES=$((FAILURES+1))
    else
      _fail "$rel is missing — it is one of the consumers whose resolver list this gate keeps honest."
      FAILURES=$((FAILURES+1))
    fi
    continue
  fi

  # In the retired world a surviving consumer is allowed — the retirement tool
  # itself lives in ghl-mcp-autostart.sh. Whether it is safe (tombstone/refusal)
  # is owned by qc-assert-ghl-mcp-supervised.sh; HERE it only stops requiring
  # delivery of the retired pin.
  if [ "$RETIRED" = "1" ] && _is_runtime_consumer "$rel"; then
    _info "$rel still ships — retirement-safety is asserted by qc-assert-ghl-mcp-supervised.sh; its pin paths are delivery-exempt"
  fi

  found_any=0
  while IFS= read -r cand; do
    [ -n "$cand" ] || continue
    found_any=1
    root="$(_classify "$cand")"
    if [ "$RETIRED" = "1" ]; then
      _info "$rel still lists $cand [$root] — exempt: the community pin is retired and must NOT be demanded from installers."
    elif [ "$root" = "UNKNOWN" ]; then
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
    if [ "$RETIRED" = "1" ]; then
      _pass "$rel no longer resolves the retired community pin"
    else
      _fail "$rel declares NO ghl-mcp-pin.env candidate at all — it can no longer read the pin."
      FAILURES=$((FAILURES+1))
    fi
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
  if [ "$RETIRED" = "1" ]; then
    # The retired community pin is exempt. But this gate must still fail if a
    # config/ file that DOES still ship stops being delivered.
    _still_shipped="$(find "$REPO_ROOT/config" -type f ! -name 'ghl-mcp-pin.env' 2>/dev/null | head -1)"
    if [ -z "$_still_shipped" ]; then
      _info "$name: config/ carries no still-shipped file besides the retired pin — no config delivery requirement (retired)."
      return 0
    fi
    if grep -qF 'OC_CANONICAL_CONFIG_DEST' <<< "$body"; then
      _pass "$name still declares the canonical config/ delivery destination (still-shipped config present)"
    else
      _fail "$name no longer contains the canonical config/ delivery step (marker OC_CANONICAL_CONFIG_DEST) while $(basename "$_still_shipped") STILL SHIPS. Boxes would stop receiving config/ — not just the retired pin."
      FAILURES=$((FAILURES+1))
    fi
    return 0
  fi
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
if [ "$RETIRED" = "1" ]; then
  _pass "config/ghl-mcp-pin.env is retired or absent — nothing to deliver (community MCP RETIRED)"
elif [ -f "$PIN_PATH" ]; then
  _pass "config/ghl-mcp-pin.env exists in the repo"
else
  _fail "config/ghl-mcp-pin.env is missing from the repo — there is nothing to deliver."
  FAILURES=$((FAILURES+1))
fi

# ─────────────────────────────────────────────────────────────────────────────
# 6. THE SAME INVARIANT, GENERALISED TO SIBLING HELPER SCRIPTS (B3).
#
# The pin file was not the only thing whose resolver list disagreed with where
# an installer puts it. ghl-mcp-autostart.sh resolved ghl-mcp-probe.sh from
#     $SELF_DIR/  |  $HOME/.openclaw/skills/scripts/  |  /data/.openclaw/skills/scripts/
# while update-skills.sh delivers the canonical scripts/ tree to
#     $OC_ROOT/scripts        (deliver_canonical_scripts_tree -> _OC_SCRIPTS_DEST)
# — an extra `skills/` segment that matched nothing on a real box. On the fleet
# path $SELF_DIR is the temp extract dir, which the updater `rm -rf`s, so the
# probe resolved EMPTY on every rolled box and install_periodic_probe() took its
# "not co-located — periodic liveness probe NOT installed" branch. The 15-minute
# liveness probe was dead on arrival fleet-wide. It passed in operator-box testing only
# because that run used a persistent checkout. Sections 1-5 above could not see
# it: they only ever looked at ghl-mcp-pin.env.
#
# THE INVARIANT, stated generically: for every helper script a consumer resolves
# from a list of candidates, the DELIVERED location ($OC_ROOT/scripts, both
# platforms) must appear in that list. Legacy candidates (the historical
# $OC_ROOT/skills/scripts layout) are allowed to remain as fallbacks — some
# long-lived boxes still have them — they simply may not be the ONLY option.
# ─────────────────────────────────────────────────────────────────────────────
_SIBLING_CONSUMERS="
scripts/ghl-mcp-autostart.sh
platform/vps/36-ghl-mcp-setup-scripts/start-ghl-mcp-server.sh
"
# The helper scripts whose resolution actually gates behaviour on a box.
_SIBLING_HELPERS="ghl-mcp-probe.sh ghl-mcp-pin-digest.sh"

for rel in $_SIBLING_CONSUMERS; do
  f="$REPO_ROOT/$rel"
  [ -f "$f" ] || continue          # section 1 already fails on a missing consumer
  body="$(sed 's/#.*$//' "$f" 2>/dev/null)"
  for helper in $_SIBLING_HELPERS; do
    # Only assert on helpers this consumer actually resolves.
    grep -qF "$helper" <<< "$body" || continue
    for want in "\$HOME/.openclaw/scripts/$helper" "/data/.openclaw/scripts/$helper"; do
      if grep -qF "$want" <<< "$body"; then
        _pass "$rel resolves $helper from the DELIVERED path $want"
      else
        _fail "$rel resolves $helper but NEVER from '$want' — the path update-skills.sh actually delivers the canonical scripts/ tree to. On the fleet path \$SELF_DIR is the temp extract dir, which is rm -rf'd, so this resolver returns EMPTY on every rolled box. That is exactly the dead-on-arrival liveness probe (B3)."
        FAILURES=$((FAILURES+1))
      fi
    done
  done
done

# The delivery side of THAT invariant must also still exist.
if grep -qF '_OC_SCRIPTS_DEST' "$REPO_ROOT/update-skills.sh" 2>/dev/null; then
  _pass "update-skills.sh still declares the canonical scripts/ delivery destination (_OC_SCRIPTS_DEST)"
else
  _fail "update-skills.sh no longer declares _OC_SCRIPTS_DEST — the canonical scripts/ tree would stop being delivered and every sibling-helper resolver above would go dead."
  FAILURES=$((FAILURES+1))
fi

if [ "$FAILURES" -gt 0 ]; then
  _fail "$FAILURES delivery cross-reference violation(s) — a resolver searches where nothing delivers, or a delivery step was removed."
  exit 1
fi
_info "resolver lists and installer delivery destinations agree (pin file + sibling helper scripts)."
exit 0
