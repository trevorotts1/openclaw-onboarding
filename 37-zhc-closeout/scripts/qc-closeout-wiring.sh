#!/usr/bin/env bash
# qc-closeout-wiring.sh — PER-BOX GATE: verify the ZHC closeout experience is
# fully WIRED on this box (files + crons + state scaffolding), not just present
# on disk.
#
# WHY THIS EXISTS (see ZHC-EXPERIENCE-DIAGNOSIS Part 3 Fix 4):
#   "files on disk = installed" was a lie. A box could have every Skill 37 file
#   and still NEVER deliver a closeout because no trigger cron was registered
#   (the Jennifer ENOENT class + the hot-patch-no-cron class). This gate fails
#   LOUD (non-zero) with a precise reason whenever the closeout would silently
#   never fire, so the fleet sweep / installer can detect + repair it.
#
# CHECKS (each failure is reported with a precise reason):
#   C1  Skill 37 SKILL.md present at $SKILLS/37-zhc-closeout/SKILL.md
#   C2  run-closeout.sh present AND executable
#   C3  resume-closeout-cron.sh present AND executable
#   C4  at least ONE closeout TRIGGER cron registered
#       (closeout-resume OR workforce-build-resume — either reaches run-closeout.sh)
#   C5  build-state scaffolding sane: if buildCompletedAt is set, then either
#       closeoutStatus ∈ {done,sent} OR a resume cron is alive to drive it
#       (i.e. a built-but-not-closed box must have a live trigger)
#
# USAGE:
#   qc-closeout-wiring.sh            # human-readable report + exit code
#   qc-closeout-wiring.sh --json     # machine-readable JSON report
#   qc-closeout-wiring.sh --quiet    # exit code only, no stdout on pass
#
# EXIT CODES:
#   0  fully wired (all checks pass)
#   1  a hard wiring defect (missing file / missing trigger cron / stranded build)
#   2  usage / environment error (no OpenClaw root, no CLI for cron checks)
#
# bash-not-zsh.
#
# Onboarding repo version markers (kept in sync by scripts/bump-version.sh):
#   QC_CLOSEOUT_WIRING_VERSION
QC_CLOSEOUT_WIRING_VERSION="v12.33.0"

set -u

JSON=0
QUIET=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --json)  JSON=1; shift ;;
    --quiet) QUIET=1; shift ;;
    --help|-h)
      grep '^#' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

# ---- platform detection ----
if [[ -d /data/.openclaw ]]; then
  OC_ROOT="/data/.openclaw"
elif [[ -d "${HOME}/.openclaw" ]]; then
  OC_ROOT="${HOME}/.openclaw"
else
  echo "qc-closeout-wiring: no OpenClaw root found (.openclaw absent)" >&2
  exit 2
fi

SKILLS_DIR="$OC_ROOT/skills"
SKILL37="$SKILLS_DIR/37-zhc-closeout"
STATE_FILE="$OC_ROOT/workspace/.workforce-build-state.json"

FAILURES=()
fail() { FAILURES+=("$1"); }

# --- C1: SKILL.md present (prevents the Jennifer ENOENT silently) ---
if [[ ! -f "$SKILL37/SKILL.md" ]]; then
  fail "C1 SKILL.md MISSING at $SKILL37/SKILL.md — Skill 37 was never copied to this box (stale/never-run install)."
fi

# --- C2: run-closeout.sh present + executable ---
if [[ ! -f "$SKILL37/scripts/run-closeout.sh" ]]; then
  fail "C2 run-closeout.sh MISSING at $SKILL37/scripts/run-closeout.sh."
elif [[ ! -x "$SKILL37/scripts/run-closeout.sh" ]]; then
  fail "C2 run-closeout.sh present but NOT executable (chmod +x missing)."
fi

# --- C3: resume-closeout-cron.sh present + executable ---
if [[ ! -f "$SKILL37/scripts/resume-closeout-cron.sh" ]]; then
  fail "C3 resume-closeout-cron.sh MISSING — the dedicated closeout trigger script is absent."
elif [[ ! -x "$SKILL37/scripts/resume-closeout-cron.sh" ]]; then
  fail "C3 resume-closeout-cron.sh present but NOT executable (chmod +x missing)."
fi

# --- C4: at least one closeout TRIGGER cron registered ---
CRON_LIST=""
HAVE_CLI=0
TRIGGER_PRESENT=0
if command -v openclaw >/dev/null 2>&1; then
  HAVE_CLI=1
  CRON_LIST="$(openclaw cron list 2>/dev/null || true)"
  if printf '%s' "$CRON_LIST" | grep -qiE 'closeout-resume|workforce-build-resume'; then
    TRIGGER_PRESENT=1
  else
    fail "C4 NO closeout trigger cron registered (neither 'closeout-resume' nor 'workforce-build-resume' present). Closeout will NEVER fire. Run scripts/ensure-pipeline-crons.sh to backfill."
  fi
else
  fail "C4 openclaw CLI not on PATH — cannot verify trigger crons. Closeout trigger UNVERIFIABLE on this box."
fi

# --- C5: built-but-not-closed must have a live trigger ---
BUILD_COMPLETED=""
CLOSEOUT_STATUS=""
if [[ -f "$STATE_FILE" ]] && command -v jq >/dev/null 2>&1; then
  BUILD_COMPLETED="$(jq -r '.buildCompletedAt // empty' "$STATE_FILE" 2>/dev/null || true)"
  CLOSEOUT_STATUS="$(jq -r '.closeoutStatus // empty' "$STATE_FILE" 2>/dev/null || true)"
  if [[ -n "$BUILD_COMPLETED" ]]; then
    case "$CLOSEOUT_STATUS" in
      done|sent)
        : ;; # closeout delivered — fine
      *)
        # build is done but closeout is not → MUST have a live trigger cron
        if [[ "$TRIGGER_PRESENT" -ne 1 ]]; then
          fail "C5 STRANDED BUILD: buildCompletedAt is set + closeoutStatus='${CLOSEOUT_STATUS:-unset}' but NO trigger cron is alive. This client built a workforce and will NEVER receive the closeout experience."
        fi
        ;;
    esac
  fi
fi

# ---- report ----
WIRED="true"
[[ ${#FAILURES[@]} -gt 0 ]] && WIRED="false"

if [[ "$JSON" -eq 1 ]]; then
  # Build a JSON failures array safely.
  if command -v jq >/dev/null 2>&1; then
    printf '%s\n' "${FAILURES[@]:-}" | jq -R . | jq -s \
      --arg wired "$WIRED" \
      --arg ver "$QC_CLOSEOUT_WIRING_VERSION" \
      --arg bc "$BUILD_COMPLETED" \
      --arg cs "$CLOSEOUT_STATUS" \
      --argjson cli "$HAVE_CLI" \
      --argjson trig "$TRIGGER_PRESENT" \
      '{wired: ($wired=="true"), version:$ver, buildCompletedAt:$bc, closeoutStatus:$cs, cliPresent:($cli==1), triggerCronPresent:($trig==1), failures: (map(select(length>0)))}'
  else
    echo "{\"wired\":$([[ $WIRED == true ]] && echo true || echo false),\"version\":\"$QC_CLOSEOUT_WIRING_VERSION\"}"
  fi
else
  if [[ "$WIRED" == "true" ]]; then
    [[ "$QUIET" -eq 1 ]] || echo "qc-closeout-wiring: PASS — closeout fully wired on this box (files + trigger cron + state sane)."
  else
    echo "qc-closeout-wiring: FAIL — closeout is NOT wired on this box:"
    for f in "${FAILURES[@]}"; do
      echo "  ✗ $f"
    done
    echo "  → Repair: bash $SKILLS_DIR/../onboarding/scripts/ensure-pipeline-crons.sh  (or re-run install.sh / update-skills.sh)"
  fi
fi

[[ "$WIRED" == "true" ]] && exit 0
exit 1
