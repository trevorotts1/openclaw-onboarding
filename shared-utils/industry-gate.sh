#!/usr/bin/env bash
# industry-gate.sh — shared FAIL-CLOSED industry-gate helper.
#
# WHY THIS EXISTS (fix/industry-gate-and-idempotent-crons, 2026-07-11):
# Skill 39 (39-real-estate-playbook) — the real-estate vertical, INCLUDING its
# two pipeline crons — used to install and wire on EVERY box regardless of the
# client's captured industry. There was NO industry gate anywhere in Skill 39's
# provisioning path (00-verify-prerequisites.sh checked Skill 38 + jq/curl only;
# wire.sh ran every step unconditionally). This file is the single canonical
# predicate every real-estate-vertical provisioning step must call before
# installing ANY real-estate content, so the gate lives in ONE place instead of
# being re-implemented (and drifting) per call site.
#
# GATE KEY (canonical): <OC_ROOT>/workspace/.workforce-build-state.json ->
#   .industryPack.slug == "real-estate"  (any .industryPack.source accepted:
#   auto-detected | owner-confirmed | owner-corrected — see
#   23-ai-workforce-blueprint/scripts/record-industry-pack.sh).
#
# SECONDARY FALLBACK: used ONLY when .industryPack is entirely absent from the
#   state file (older/hand-seeded build-state). A top-level .industry field
#   (schema: build-state-schema.json line 47) is then matched case-insensitively
#   against "real estate" / "real-estate". The primary key is always
#   industryPack.slug when present.
#
# FAIL CLOSED (mandatory): ANY of the following => NOT real estate, i.e. do
#   NOT install/wire the real-estate vertical:
#     - no OC_ROOT resolvable (neither /data/.openclaw nor $HOME/.openclaw)
#     - build-state file missing
#     - build-state present but unparsable (no jq/python3, or invalid JSON)
#     - .industryPack present but .slug is null/empty/"unknown"/anything other
#       than "real-estate"
#     - .industryPack entirely absent AND no matching top-level .industry
#   Absence of information is NEVER treated as permission to install.
#
# USAGE: `source` this file, then call `oc_is_real_estate_industry`.
#   Returns 0  = box industry IS real-estate (proceed).
#   Returns 1  = NOT real-estate / unknown / absent (fail closed — skip).
#   Sets OC_INDUSTRY_GATE_REASON as a side effect (human-readable, for logging).
#
# Platform detection mirrors scripts/ensure-pipeline-crons.sh (VPS /data first,
# then Mac $HOME) so every caller resolves the SAME state file.
#
# bash-not-zsh.

oc_is_real_estate_industry() {
  OC_INDUSTRY_GATE_REASON=""
  local oc_root state_file

  if [[ -d /data/.openclaw ]]; then
    oc_root="/data/.openclaw"
  elif [[ -d "${HOME}/.openclaw" ]]; then
    oc_root="${HOME}/.openclaw"
  else
    OC_INDUSTRY_GATE_REASON="no OpenClaw root found (.openclaw absent) — cannot resolve build-state; fail closed (not real-estate)"
    return 1
  fi

  state_file="$oc_root/workspace/.workforce-build-state.json"
  if [[ ! -f "$state_file" ]]; then
    OC_INDUSTRY_GATE_REASON="build-state file absent ($state_file) — fail closed (not real-estate)"
    return 1
  fi

  local slug="" has_industry_pack="0" top_industry=""

  if command -v jq >/dev/null 2>&1; then
    if ! jq -e '.' "$state_file" >/dev/null 2>&1; then
      OC_INDUSTRY_GATE_REASON="build-state file is not valid JSON ($state_file) — fail closed (not real-estate)"
      return 1
    fi
    if jq -e '(.industryPack // null) != null' "$state_file" >/dev/null 2>&1; then
      has_industry_pack="1"
      slug="$(jq -r '.industryPack.slug // ""' "$state_file" 2>/dev/null)"
    fi
    top_industry="$(jq -r '.industry // ""' "$state_file" 2>/dev/null)"
  elif command -v python3 >/dev/null 2>&1; then
    local py_out
    py_out="$(python3 - "$state_file" <<'PYEOF' 2>/dev/null
import json, sys
try:
    data = json.load(open(sys.argv[1]))
except Exception:
    print("ERR")
    sys.exit(0)
ip = data.get("industryPack")
has = "1" if isinstance(ip, dict) else "0"
slug = (ip.get("slug", "") if isinstance(ip, dict) else "") or ""
top = data.get("industry", "") or ""
print("OK\t" + has + "\t" + slug + "\t" + top)
PYEOF
)"
    if [[ "$py_out" == OK$'\t'* ]]; then
      IFS=$'\t' read -r _ has_industry_pack slug top_industry <<< "$py_out"
    else
      OC_INDUSTRY_GATE_REASON="could not parse build-state JSON ($state_file) — fail closed (not real-estate)"
      return 1
    fi
  else
    OC_INDUSTRY_GATE_REASON="neither jq nor python3 available to read build-state — fail closed (not real-estate)"
    return 1
  fi

  if [[ "$has_industry_pack" == "1" ]]; then
    if [[ "$slug" == "real-estate" ]]; then
      OC_INDUSTRY_GATE_REASON="industryPack.slug=real-estate"
      return 0
    fi
    OC_INDUSTRY_GATE_REASON="industryPack.slug='${slug:-<empty>}' (not real-estate) — fail closed"
    return 1
  fi

  # industryPack entirely absent — secondary fallback on top-level .industry.
  local top_lc
  top_lc="$(printf '%s' "$top_industry" | tr '[:upper:]' '[:lower:]')"
  case "$top_lc" in
    "real estate"|"real-estate")
      OC_INDUSTRY_GATE_REASON="no industryPack; top-level .industry='${top_industry}' matches real estate (secondary fallback)"
      return 0
      ;;
  esac
  OC_INDUSTRY_GATE_REASON="no industryPack and top-level .industry='${top_industry:-<empty>}' does not match real estate — fail closed"
  return 1
}
