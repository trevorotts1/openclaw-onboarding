#!/usr/bin/env bash
# ==============================================================================
# cinematic-web-funnel-entry.sh — the CANONICAL, fail-closed front door for
# Skill 62 (Cinematic and Web Funnel Engine). Per ADR-6, NOTHING may run a phase
# gate, call a media/CRM/hosting provider, or mint a certificate except THROUGH
# this shell. Mirrors the fail-closed entry-shell pattern of Skill 49
# (signature-funnel-entry.sh) and Skill 56 (sales-page-assets-entry.sh). It
# performs, in order, all fail-closed:
#
#   1. DEPS        — python3 present (else abort).
#   2. VERSION     — skill-version.txt is present + non-empty and its major
#                    version agrees with SKILL.md frontmatter (lockstep gate;
#                    the same invariant scripts/qc-assert-skill-frontmatter-
#                    version.sh enforces repo-wide).
#   3. NONCE       — write a run-scoped 0600 front-door nonce; export
#                    CWFE_RUN_NONCE.
#   4. ORCHESTRATE — run_cinematic_web_funnel.py with the nonce (the no-skip,
#                    manifest-driven state machine); it emits the signed
#                    PROCESS-CERTIFICATE only when every phase in
#                    CWFE-MANIFEST.json passes.
#
# A hash-pin step (recompute + compare the sha256 of the enforcement core —
# provers + manifest + orchestrator, the same technique Skill 49 uses) is added
# once the phase gate scripts exist in a later build unit; pinning zero files
# today would be a placeholder, not a real guard, so it is deliberately absent
# from this skeleton rather than faked.
#
# Usage:
#   bash cinematic-web-funnel-entry.sh --run-dir <RUN_DIR>
#   bash cinematic-web-funnel-entry.sh --self-test
# Exit: 0 = certified / self-test green; nonzero = a fail-closed guard tripped.
# ==============================================================================
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
PY="${PYTHON:-python3}"
EXPECTED_MAJOR="1"

die() { printf 'ABORT [%s]: %s\n' "$1" "$2" >&2; exit 1; }

step_deps() {
  command -v "$PY" >/dev/null 2>&1 || die "DEPS" "python3 not found on PATH"
}

# Extract the top-level frontmatter `version:` from SKILL.md (column-0 key inside
# the first --- ... --- block only, so a nested key never matches).
frontmatter_version() {
  awk '
    BEGIN { fence = 0 }
    {
      if ($0 == "---") { fence++; if (fence >= 2) exit; next }
      if (fence == 1 && $0 ~ /^version:/) {
        val = $0
        sub(/^version:[ \t]*/, "", val)
        print val
        exit
      }
    }
  ' "$SKILL_DIR/SKILL.md"
}

step_version() {
  local vf="$SKILL_DIR/skill-version.txt"
  [ -s "$vf" ] || die "VERSION" "skill-version.txt missing/empty"
  local sv; sv="$(tr -d '[:space:]' < "$vf")"
  case "$sv" in
    "$EXPECTED_MAJOR".*) : ;;
    *) die "VERSION" "skill-version.txt is '$sv', expected major $EXPECTED_MAJOR.x" ;;
  esac
  local fm; fm="$(frontmatter_version | tr -d '[:space:]"'"'"'')"
  [ -n "$fm" ] || die "VERSION" "SKILL.md has no top-level frontmatter version: field"
  [ "$fm" = "$sv" ] || die "VERSION" "SKILL.md frontmatter version ($fm) != skill-version.txt ($sv) — drift"
}

step_nonce() {
  local rd="$1"
  local nonce; nonce="$("$PY" -c 'import secrets; print(secrets.token_hex(32))')"
  local nf="$rd/.cwfe_run_nonce"
  ( umask 077; printf '%s' "$nonce" > "$nf" )
  chmod 600 "$nf"
  printf '%s' "$nonce"
}

run_pipeline() {
  local rd="$1"
  [ -n "$rd" ] || die "USAGE" "--run-dir is required"
  mkdir -p "$rd" 2>/dev/null || true
  rd="$(cd "$rd" 2>/dev/null && pwd || true)"
  [ -n "$rd" ] && [ -d "$rd" ] || die "USAGE" "run-dir does not exist and could not be created"
  step_deps
  step_version
  local nonce; nonce="$(step_nonce "$rd")"
  export CWFE_RUN_NONCE="$nonce"
  echo "== cinematic-web-funnel-entry :: front door cleared (deps/version/nonce) =="
  "$PY" "$SKILL_DIR/run_cinematic_web_funnel.py" --run-dir "$rd" --nonce "$nonce"
}

self_test() {
  echo "== cinematic-web-funnel-entry :: --self-test =="
  step_deps
  echo "  [PASS] python3 on PATH"
  step_version
  echo "  [PASS] skill-version.txt <-> SKILL.md frontmatter lockstep (major $EXPECTED_MAJOR)"

  local fails=0
  local tmp_rd; tmp_rd="$(mktemp -d)"

  # 1) Direct orchestrator call with NO nonce must be rejected (ADR-6 / AF-CWFE-FRONT-DOOR).
  if "$PY" "$SKILL_DIR/run_cinematic_web_funnel.py" --run-dir "$tmp_rd" >/tmp/cwfe_nonone.log 2>&1; then
    echo "  [FAIL] orchestrator ran WITHOUT a nonce — ADR-6 front door is not enforced"; fails=$((fails + 1))
  else
    grep -q "AF-CWFE-FRONT-DOOR" /tmp/cwfe_nonone.log && echo "  [PASS] orchestrator rejects a call with no --nonce (AF-CWFE-FRONT-DOOR)" \
      || { echo "  [FAIL] orchestrator rejected the no-nonce call but not with AF-CWFE-FRONT-DOOR"; sed 's/^/         /' /tmp/cwfe_nonone.log; fails=$((fails + 1)); }
  fi

  # 2) Direct orchestrator call with a WRONG nonce (no nonce file yet in tmp_rd) must be rejected.
  if "$PY" "$SKILL_DIR/run_cinematic_web_funnel.py" --run-dir "$tmp_rd" --nonce "deadbeef" >/tmp/cwfe_wrongnonce.log 2>&1; then
    echo "  [FAIL] orchestrator ran with a nonce that matches no nonce file"; fails=$((fails + 1))
  else
    grep -q "AF-CWFE-FRONT-DOOR" /tmp/cwfe_wrongnonce.log && echo "  [PASS] orchestrator rejects a nonce that does not match the front-door nonce file (AF-CWFE-FRONT-DOOR)" \
      || { echo "  [FAIL] orchestrator rejected the wrong-nonce call but not with AF-CWFE-FRONT-DOOR"; sed 's/^/         /' /tmp/cwfe_wrongnonce.log; fails=$((fails + 1)); }
  fi

  # 3) run_cinematic_web_funnel.py's own --self-test (manifest load + phase-order integrity).
  if "$PY" "$SKILL_DIR/run_cinematic_web_funnel.py" --self-test >/tmp/cwfe_orch.log 2>&1; then
    echo "  [PASS] run_cinematic_web_funnel.py --self-test"
  else
    echo "  [FAIL] run_cinematic_web_funnel.py --self-test"; sed 's/^/         /' /tmp/cwfe_orch.log; fails=$((fails + 1))
  fi

  # 4) A real front-door pipeline run against a bare run-dir must fail-closed at
  #    the FIRST phase and emit NO certificate. All 17 phase gate scripts now
  #    exist, so a bare run no longer stops at GATE-SCRIPT-MISSING — with no
  #    resolved model environment it fail-closes at P0-ENVIRONMENT
  #    (AF-CWFE-P0-ENVIRONMENT). The CWFE_MODEL_* / CWFE_ENVIRONMENT vars are
  #    unset for this one check so the outcome stays deterministic regardless of
  #    the operator's own shell (a shell that HAS them set would instead stop
  #    fail-closed at P1-INTAKE on a bare run-dir; either way, no certificate).
  local run_rd; run_rd="$(mktemp -d)"
  if ( unset CWFE_MODEL_ARCHITECT_JUDGE CWFE_MODEL_BUILDER CWFE_MODEL_MECHANICAL_VERIFIER CWFE_ENVIRONMENT CWFE_RUN_NONCE
       run_pipeline "$run_rd" ) >/tmp/cwfe_pipeline.log 2>&1; then
    echo "  [FAIL] full pipeline run CERTIFIED against a bare run-dir — impossible, investigate"; fails=$((fails + 1))
  else
    if grep -qF "[FAIL] P0-ENVIRONMENT" /tmp/cwfe_pipeline.log \
       && grep -q "AF-CWFE-P0-ENVIRONMENT" /tmp/cwfe_pipeline.log \
       && grep -q "RESULT: NOT CERTIFIED" /tmp/cwfe_pipeline.log \
       && [ ! -f "$run_rd/PROCESS-CERTIFICATE.json" ]; then
      echo "  [PASS] full pipeline run correctly fail-closes at P0-ENVIRONMENT (AF-CWFE-P0-ENVIRONMENT, no certificate emitted)"
    else
      echo "  [FAIL] full pipeline run failed for the wrong reason, or a certificate leaked out"; sed 's/^/         /' /tmp/cwfe_pipeline.log; fails=$((fails + 1))
    fi
  fi
  rm -rf "$run_rd" "$tmp_rd"

  [ "$fails" -eq 0 ] || die "SELF-TEST" "$fails check(s) failed"
  echo "RESULT: PASS — entry self-test green."
}

main() {
  local mode="" rd=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --run-dir) rd="${2:-}"; shift 2 ;;
      --self-test) mode="selftest"; shift ;;
      -h|--help) grep -E '^#( |$)' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
      *) die "USAGE" "unknown arg: $1" ;;
    esac
  done
  case "$mode" in
    selftest) self_test ;;
    *) run_pipeline "$rd" ;;
  esac
}

main "$@"
