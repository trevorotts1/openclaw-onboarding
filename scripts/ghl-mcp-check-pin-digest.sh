#!/usr/bin/env bash
# ghl-mcp-check-pin-digest.sh — POLICY layer over the vetting digest.
#
# ── RELATIONSHIP TO scripts/ghl-mcp-pin-digest.sh — READ THIS FIRST ──────────
# `ghl-mcp-pin-digest.sh` is the ONE canonical implementation of the digest
# ALGORITHM (compute / verify / fields). It is named as such in its own header
# and nothing is permitted to reimplement it. This file does NOT.
#
# This file adds the POLICY the algorithm deliberately has no opinion about:
#
#   the primitive answers   "does the recorded digest recompute?"
#   this file answers       "is this pin fit to be built and run?"
#
# They are different questions. A record can recompute perfectly and still be a
# hard refusal — a correctly sealed DIRTY verdict is exactly that. A record can
# also be well-formed-looking and still be junk (a 7-char SHA, a date that is
# not a date, an empty reviewer), and the primitive would happily hash all of it
# without complaint, because hashing garbage is not the primitive's problem.
#
# So: well-formedness and verdict policy live here; the byte-exact tuple lives
# there. One algorithm, one policy, no duplication, and the split is on a real
# seam rather than a convenient one.
#
# The pin file is PARSED, never sourced — same rule as the primitive. A gate
# that executes the file it is auditing can be made to lie about its own result.
#
# ── USAGE ────────────────────────────────────────────────────────────────────
#   ghl-mcp-check-pin-digest.sh [--pin-file PATH] [--quiet]
#       Full check: well-formed AND digest recomputes AND verdict is CLEAN.
#   ghl-mcp-check-pin-digest.sh --integrity-only [--pin-file PATH]
#       Well-formed AND digest recomputes; a non-CLEAN verdict is ACCEPTED.
#       For callers that must tell "the review said no" (fix the tree) apart
#       from "the record is broken" (re-vet) — different problems, different
#       fixes, so they must not collapse into one exit code.
#   ghl-mcp-check-pin-digest.sh --compute [--pin-file PATH]
#       Print the digest the file's current fields imply. Delegates to the
#       primitive; kept here so callers have one entry point.
#
# ── EXIT CODES (consumers depend on these being distinct) ────────────────────
#   0  OK
#   1  GATE FAILURE — definite and reproducible. Malformed field, digest
#      mismatch, an ABSENT digest, or (without --integrity-only) a verdict that
#      is not CLEAN. A caller must always refuse on 1.
#   2  Pin file not found. Distinct from 1 so "never delivered" is never
#      confused with "lying about what was vetted".
#   3  Environment failure — no sha256 utility. NOTHING was verified. Never
#      treat 3 as a pass; treat it as "could not check" and say so out loud.
#
# NOTE ON AN ABSENT DIGEST. The primitive returns 3 = ABSENT and tells the
# caller to fall back to requiring VERDICT=CLEAN. That fallback was correct
# while the vetting tool did not exist yet and every pin necessarily had an
# empty digest. The tool exists now and the digest is written, so THIS gate
# treats absence as a FAILURE: "no digest, so nothing to check" is precisely the
# silent pass the mechanism exists to eliminate, and deleting one line must
# never be cheaper than re-vetting. The box-side installers keep the primitive's
# transitional fallback — they must not brick a box that is mid-roll and still
# carrying an older delivered pin file — and this gate is what stops such a file
# from ever being authored in the repo again.

set -uo pipefail

PIN_FILE=""
MODE="verify"
QUIET=0

while [ $# -gt 0 ]; do
  case "$1" in
    --pin-file)       PIN_FILE="${2:-}"; shift ;;
    --compute)        MODE="compute" ;;
    --integrity-only) MODE="integrity" ;;
    --quiet|-q)       QUIET=1 ;;
    -h|--help)        sed -n '2,60p' "$0"; exit 0 ;;
    *) echo "ghl-mcp-check-pin-digest.sh: unknown argument '$1'" >&2; exit 1 ;;
  esac
  shift
done

say() { [ "$QUIET" -eq 1 ] || printf '%s\n' "$*"; }
err() { printf '%s\n' "$*" >&2; }

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
PRIMITIVE="$SELF_DIR/ghl-mcp-pin-digest.sh"
[ -f "$PRIMITIVE" ] || { err "PIN-DIGEST: scripts/ghl-mcp-pin-digest.sh is missing — this gate will not reimplement the algorithm it is supposed to enforce."; exit 3; }

# Resolver order is a SUBSET of what the installers deliver (install.sh writes
# $OC_CONFIG/onboarding/config/ and $OC_CONFIG/config/; update-skills.sh writes
# $OC_CONFIG/config/). scripts/qc-assert-pin-delivery-paths.sh asserts that
# relationship in CI for every consumer, this file included, so the gate can
# never end up judging a file no installer produces.
if [ -z "$PIN_FILE" ]; then
  for _c in "$SELF_DIR/../config/ghl-mcp-pin.env" \
            "$HOME/.openclaw/config/ghl-mcp-pin.env" \
            "$HOME/.openclaw/onboarding/config/ghl-mcp-pin.env" \
            "/data/.openclaw/config/ghl-mcp-pin.env" \
            "/data/.openclaw/onboarding/config/ghl-mcp-pin.env"; do
    [ -f "$_c" ] && { PIN_FILE="$_c"; break; }
  done
fi

if [ -z "$PIN_FILE" ] || [ ! -f "$PIN_FILE" ]; then
  err "PIN-DIGEST: pin file not found${PIN_FILE:+ at $PIN_FILE}"
  exit 2
fi

if [ "$MODE" = "compute" ]; then
  bash "$PRIMITIVE" compute "$PIN_FILE"
  exit $?
fi

# ── Field reader (parse, never source) ───────────────────────────────────────
# Deliberately the same shape as the primitive's: last `^KEY="value"` wins,
# matching what `.` would do, so this gate and a sourcing installer can never
# disagree about what the file says.
field() {
  awk -v key="$1" '
    $0 ~ "^" key "=\"" {
      line = $0
      sub("^" key "=\"", "", line)
      idx = index(line, "\"")
      val = (idx > 0) ? substr(line, 1, idx - 1) : ""
      found = 1
    }
    END { if (found) print val }
  ' "$PIN_FILE"
}

COMMIT="$(field GHL_MCP_VETTED_COMMIT)"
VERDICT="$(field GHL_MCP_PIN_VETTED_VERDICT)"
VET_ON="$(field GHL_MCP_PIN_VETTED_ON)"
VET_BY="$(field GHL_MCP_PIN_VETTED_BY)"
LOCK_SHA="$(field GHL_MCP_DEPS_LOCK_SHA256)"
REPO_URL="$(field GHL_MCP_REPO_URL)"
STORED="$(field GHL_MCP_PIN_VETTED_DIGEST)"

# ── Well-formedness, checked BEFORE the digest ───────────────────────────────
# Order matters for the human reading the failure: a broken record should report
# what is actually wrong, not an unhelpful "digest mismatch" that sends someone
# looking in the wrong place.
FAILED=0
bad() { err "PIN-DIGEST FAIL: $*"; FAILED=1; }

case "$COMMIT" in
  *[!0-9a-f]*|"") bad "GHL_MCP_VETTED_COMMIT is not lowercase hex" ;;
  *) [ "${#COMMIT}" -eq 40 ] || bad "GHL_MCP_VETTED_COMMIT is ${#COMMIT} chars, not a full 40-char SHA (a short SHA or a branch name is not a pin)" ;;
esac

case "$VERDICT" in
  CLEAN|DIRTY|PENDING) : ;;
  "") bad "GHL_MCP_PIN_VETTED_VERDICT is missing" ;;
  *)  bad "GHL_MCP_PIN_VETTED_VERDICT='$VERDICT' is not one of CLEAN|DIRTY|PENDING" ;;
esac

case "$VET_ON" in
  [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]) : ;;
  *) bad "GHL_MCP_PIN_VETTED_ON='$VET_ON' is not YYYY-MM-DD" ;;
esac

[ -n "$VET_BY" ] || bad "GHL_MCP_PIN_VETTED_BY is empty — an unattributed verdict is not a verdict"

case "$LOCK_SHA" in
  *[!0-9a-f]*|"") bad "GHL_MCP_DEPS_LOCK_SHA256 is not lowercase hex" ;;
  *) [ "${#LOCK_SHA}" -eq 64 ] || bad "GHL_MCP_DEPS_LOCK_SHA256 is ${#LOCK_SHA} chars, not a 64-char sha256" ;;
esac

case "$REPO_URL" in
  http://*|https://*) : ;;
  "") bad "GHL_MCP_REPO_URL is empty — the vetted commit has no stated source, and a SHA names an object, never the host that serves it" ;;
  *)  bad "GHL_MCP_REPO_URL='$REPO_URL' is not an http(s) URL" ;;
esac

case "$STORED" in
  "") bad "GHL_MCP_PIN_VETTED_DIGEST is missing — an unsealed vetting record fails closed here. Seal it: bash scripts/ghl-mcp-vet-pin.sh <sha> --verdict clean" ;;
  *[!0-9a-f]*) bad "GHL_MCP_PIN_VETTED_DIGEST is not lowercase hex" ;;
  *) [ "${#STORED}" -eq 64 ] || bad "GHL_MCP_PIN_VETTED_DIGEST is ${#STORED} chars, not a 64-char sha256" ;;
esac

if [ "$FAILED" -ne 0 ]; then
  err "PIN-DIGEST: vetting record in $PIN_FILE is malformed — refusing."
  exit 1
fi

# ── The tuple itself: delegated, never recomputed here ───────────────────────
DIGEST_OUT="$(bash "$PRIMITIVE" verify "$PIN_FILE" 2>&1)"
case $? in
  0) : ;;
  3) err "PIN-DIGEST FAIL: no digest recorded — see above."; exit 1 ;;
  4) err "PIN-DIGEST: the digest primitive could not run — NOTHING WAS VERIFIED. This is not a pass."
     err "$DIGEST_OUT"
     exit 3 ;;
  *)
     err ""
     err "PIN-DIGEST FAIL: the vetting record does not match what it claims to have vetted."
     err "  pin file: $PIN_FILE"
     err "$DIGEST_OUT"
     err ""
     err "Some bound value was changed WITHOUT re-vetting: the commit, the verdict,"
     err "the review date, the reviewer, the dependency lockfile hash, or the source"
     err "repository URL. That is exactly the case this gate exists to refuse."
     err ""
     err "There is no way to hand-repair this, and there should not be. Re-run the"
     err "review and seal the result:"
     err "    bash scripts/ghl-mcp-vet-pin.sh <commit-sha>                  # review"
     err "    bash scripts/ghl-mcp-vet-pin.sh <commit-sha> --verdict clean  # seal"
     exit 1 ;;
esac

if [ "$MODE" != "integrity" ] && [ "$VERDICT" != "CLEAN" ]; then
  err "PIN-DIGEST FAIL: the vetting record is intact and correctly sealed, but the verdict is '$VERDICT', not CLEAN."
  err "  A DIRTY or PENDING pin must never reach a client box. Fix the tree or pin a different commit;"
  err "  do not edit the word."
  exit 1
fi

say "PIN-DIGEST OK: $(basename "$PIN_FILE") — verdict=$VERDICT commit=${COMMIT:0:12} digest=${STORED:0:12}"
exit 0
