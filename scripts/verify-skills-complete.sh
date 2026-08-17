#!/usr/bin/env bash
# ============================================================
#  verify-skills-complete.sh — standalone install-completeness check
#
#  WHY THIS EXISTS
#  ---------------
#  update-skills.sh already carries a real content-gate (A3): it compares
#  per-skill digests of the installed tree against the source tree, and it is
#  fatal — mismatch means the version stamp is never written and the run exits 1.
#  That gate is sound, but it only runs INSIDE a full updater run, and it runs
#  LATE. Any earlier termination — a QC failure, a crash, an operator Ctrl-C,
#  a box that runs out of memory — skips it entirely, and the box is then left
#  with a partially-copied skills tree that NOTHING subsequently re-checks.
#
#  Observed in the field: a box sat with ~43% of one skill's files missing and
#  17 skill directories absent for roughly six days. Every surface reported
#  healthy, because the only check that would have caught it never executed.
#
#  This script is that missing check, factored out so it can run on its own:
#  cheap, read-only, no install side effects, safe to call from a heartbeat or
#  by hand at any time.
#
#  It also covers shared-utils/, which the A3 gate is structurally blind to —
#  skill-content-hash.sh enumerates only numbered [0-9]* skill directories, so
#  a partially-copied shared-utils/ tree passes A3 untouched.
#
#  USAGE:
#    bash verify-skills-complete.sh [--source <checkout-dir>] [--skills <skills-dir>] [--quiet]
#
#    --source  Source of truth: an onboarding git checkout.
#              Default: $HOME/.openclaw/onboarding
#    --skills  Installed skills tree to check.
#              Default: $HOME/.openclaw/skills
#    --quiet   Print only the final verdict line.
#
#  EXIT CODES:
#    0  — COMPLETE: every source skill is present in the destination with a
#         matching content digest, and shared-utils/ is a superset of source.
#    1  — DRIFT: at least one skill is missing or its content differs, or a
#         shared-utils/ entry is missing. Details are printed.
#    2  — TOOLING FAILURE: a required path or helper is unavailable, so NO
#         verdict is possible. This is deliberately NOT folded into exit 1 —
#         "I could not check" must never be reported as "I checked and it is
#         fine", and it must never be reported as drift either.
#
#  Destination SUPERSETS are not drift: a box legitimately carries install
#  markers and locally-generated artifacts the source tree does not have. Only
#  MISSING or DIFFERING source content is a failure.
# ============================================================
set -uo pipefail

SRC_DIR="${HOME}/.openclaw/onboarding"
SKILLS_DIR="${HOME}/.openclaw/skills"
QUIET=0

while [ $# -gt 0 ]; do
  case "$1" in
    --source) SRC_DIR="${2:-}"; shift 2 ;;
    --skills) SKILLS_DIR="${2:-}"; shift 2 ;;
    --quiet)  QUIET=1; shift ;;
    -h|--help)
      sed -n '2,50p' "$0" | sed 's/^#  \{0,1\}//'
      exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; exit 2 ;;
  esac
done

say() { [ "$QUIET" -eq 1 ] || echo "$@"; }

# ---- tooling preflight: absence of a prerequisite is exit 2, never a verdict --
[ -n "$SRC_DIR" ] && [ -d "$SRC_DIR" ] || {
  echo "TOOLING-FAILURE: source checkout not found or not a directory: ${SRC_DIR:-<empty>}" >&2
  echo "  Pass one explicitly with --source <dir>." >&2
  exit 2; }
[ -n "$SKILLS_DIR" ] && [ -d "$SKILLS_DIR" ] || {
  echo "TOOLING-FAILURE: skills dir not found or not a directory: ${SKILLS_DIR:-<empty>}" >&2
  exit 2; }

HASH_SCRIPT="$SRC_DIR/scripts/skill-content-hash.sh"
[ -f "$HASH_SCRIPT" ] || {
  echo "TOOLING-FAILURE: content-hash helper not found: $HASH_SCRIPT" >&2
  echo "  Cannot compute digests, so no completeness verdict is possible." >&2
  exit 2; }

say "== verify-skills-complete =="
say "  source : $SRC_DIR"
say "  skills : $SKILLS_DIR"
say ""

SRC_MANIFEST=$(bash "$HASH_SCRIPT" "$SRC_DIR" 2>/dev/null)
if [ $? -ne 0 ] || [ -z "$SRC_MANIFEST" ]; then
  echo "TOOLING-FAILURE: could not build the SOURCE manifest from $SRC_DIR" >&2
  exit 2
fi
DEST_MANIFEST=$(bash "$HASH_SCRIPT" "$SKILLS_DIR" 2>/dev/null)
if [ $? -ne 0 ] || [ -z "$DEST_MANIFEST" ]; then
  echo "TOOLING-FAILURE: could not build the DESTINATION manifest from $SKILLS_DIR" >&2
  exit 2
fi

MISSING=""
DIFFERS=""
CHECKED=0

while IFS='|' read -r skill_name src_digest; do
  [ -z "$skill_name" ] && continue
  [ "$skill_name" = "__TREE_SHA__" ] && continue
  case "$skill_name" in *ARCHIVED*) continue ;; esac

  CHECKED=$((CHECKED + 1))
  dest_digest=$(printf '%s\n' "$DEST_MANIFEST" | grep "^${skill_name}|" | cut -d'|' -f2 | head -1)

  if [ -z "$dest_digest" ]; then
    MISSING="${MISSING}  ${skill_name} — present in source, ABSENT on this box"$'\n'
  elif [ "$dest_digest" != "$src_digest" ]; then
    DIFFERS="${DIFFERS}  ${skill_name} — content differs (expected ${src_digest}, found ${dest_digest})"$'\n'
  fi
done <<< "$SRC_MANIFEST"

# ---- shared-utils/: the A3 gate's structural blind spot ----------------------
# skill-content-hash.sh walks only numbered [0-9]* dirs, so a partially-copied
# shared-utils/ is invisible to it. Assert source is a subset of destination,
# recursively. Destination extras are fine.
SU_MISSING=""
SU_CHECKED=0
if [ -d "$SRC_DIR/shared-utils" ]; then
  if [ -d "$SKILLS_DIR/shared-utils" ]; then
    while IFS= read -r rel; do
      [ -z "$rel" ] && continue
      SU_CHECKED=$((SU_CHECKED + 1))
      [ -e "$SKILLS_DIR/shared-utils/$rel" ] || SU_MISSING="${SU_MISSING}  shared-utils/${rel}"$'\n'
    done < <(cd "$SRC_DIR/shared-utils" && find . -type f 2>/dev/null | sed 's|^\./||')
  else
    SU_MISSING="  shared-utils/ — entire tree ABSENT on this box"$'\n'
  fi
fi

say "  checked: ${CHECKED} skill(s), ${SU_CHECKED} shared-utils file(s)"
say ""

if [ -n "$MISSING" ] || [ -n "$DIFFERS" ] || [ -n "$SU_MISSING" ]; then
  echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
  echo "  INSTALL INCOMPLETE — this box does not match its source tree."
  [ -n "$MISSING" ]    && { echo ""; echo "  MISSING skills:";        printf '%s' "$MISSING"; }
  [ -n "$DIFFERS" ]    && { echo ""; echo "  MISMATCHED skills:";     printf '%s' "$DIFFERS"; }
  [ -n "$SU_MISSING" ] && { echo ""; echo "  MISSING shared-utils:";  printf '%s' "$SU_MISSING"; }
  echo ""
  echo "  FIX: re-run the updater from a current checkout:"
  echo "    cd \"$SRC_DIR\" && git fetch origin main && git reset --hard origin/main && bash update-skills.sh"
  echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
  exit 1
fi

echo "COMPLETE — all ${CHECKED} source skills present with matching content; shared-utils intact."
exit 0
