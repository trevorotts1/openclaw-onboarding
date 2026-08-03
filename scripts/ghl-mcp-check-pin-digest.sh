#!/usr/bin/env bash
# ghl-mcp-check-pin-digest.sh — the ONE implementation of the GHL MCP
# vetting-digest canonical form. CI, the pre-push hook, the box-side installer
# and the vetting tool all call THIS file. Nothing recomputes the digest inline:
# a second implementation is a second chance to disagree, and two gates that
# disagree are one gate that can be walked past.
#
# ── WHY A DIGEST AT ALL ──────────────────────────────────────────────────────
# The vetting record used to be three prose fields plus a comment addressed to a
# human: "Any change to GHL_MCP_VETTED_COMMIT MUST reset the three
# GHL_MCP_PIN_VETTED_* fields to PENDING." A rule that requires someone to
# remember an extra step is not enforcement, it is documentation. It was also
# inert: the verdict was sourced into the environment by three scripts and read
# by none of them, nor by the QC gate, nor by CI.
#
# The obvious repair -- "make CI assert VERDICT == CLEAN" -- is worse than
# nothing. It is satisfied by editing one word, and it actively TRAINS whoever
# bumps the pin to type "CLEAN", because that is what makes the build go green.
#
# So the verdict is bound to everything it is a judgment ABOUT. Change the
# commit, the lockfile hash, the source repository, the date, the reviewer or
# the verdict word itself, and the stored digest no longer recomputes. Every
# consumer then refuses. FORGETTING TO RE-VET PRODUCES REFUSAL, which is the
# only property that matters here. It is a lockfile applied to a security
# judgment.
#
# ── WHAT THIS IS NOT ─────────────────────────────────────────────────────────
# NOT a signature. NOT tamper-proofing. The canonical form below is public and
# unkeyed, so anyone with write access to this repo can recompute a valid
# digest -- but only DELIBERATELY, by running the vetting tool (or by
# reimplementing it on purpose). It closes the accident, not the attack.
# Upgrade path if tamper-evidence is ever wanted: sign the same canonical
# string with `git tag -s` or minisign and verify the signature here. The
# canonical form and every consumer's call shape stay exactly as they are.
#
# ── WHAT IS BOUND, AND WHAT IS DELIBERATELY NOT ──────────────────────────────
# BOUND (changing any one of these invalidates the record):
#   commit            the vetted 40-char upstream SHA -- the thing reviewed
#   verdict           CLEAN | DIRTY | PENDING
#   on                review date
#   by                reviewer
#   deps_lock_sha256  sha256 of package-lock.json AT the vetted commit. The
#                     verdict claims "dependency graph unchanged"; without this
#                     the claim covers source but not the dependency tree that
#                     source pulls in.
#   repo_url          the repository the commit is fetched FROM. Unbound, a
#                     mirror swap to an attacker-controlled clone keeps a valid
#                     digest while changing every byte the box executes: the SHA
#                     names an object, not the host that serves it.
#
# NOT BOUND, on purpose:
#   tool profile, port, tool-count band, log rotation, probe timeout. These are
#   operational knobs, not security judgments. Binding them would force a
#   re-vet to widen a log file -- a trap that gets the gate disabled.
#
# ── USAGE ────────────────────────────────────────────────────────────────────
#   ghl-mcp-check-pin-digest.sh [--pin-file PATH] [--quiet]
#       Verify. Exit 0 only if the record is well-formed, the digest recomputes
#       AND the verdict is CLEAN.
#   ghl-mcp-check-pin-digest.sh --compute [--pin-file PATH]
#       Print the digest the file's CURRENT field values imply. Used by
#       ghl-mcp-vet-pin.sh to seal a record. Does not compare, does not judge.
#   ghl-mcp-check-pin-digest.sh --integrity-only [--pin-file PATH]
#       Verify well-formedness + digest, but accept a non-CLEAN verdict. For
#       callers that want to distinguish "record intact, verdict DIRTY" from
#       "record broken".
#   ghl-mcp-check-pin-digest.sh --canonical [--pin-file PATH]
#       Print the exact bytes that get hashed. For debugging a mismatch.
#
# ── EXIT CODES (consumers depend on these being distinct) ────────────────────
#   0  OK
#   1  GATE FAILURE -- definite and reproducible. Malformed field, missing
#      digest, digest mismatch, or (without --integrity-only) verdict != CLEAN.
#      A caller must always refuse on 1.
#   2  Pin file not found. Fail-closed for the installer and CI (the file is
#      supposed to be delivered); tolerable for a local hook.
#   3  Environment failure -- no sha256 utility. Nothing was verified. Never
#      treat 3 as a pass; treat it as "could not check" and say so.
#
# The pin file is PARSED, never sourced. Sourcing would execute it, which means
# a hostile pin file could define a shell function that makes this gate lie
# about its own result. The gate that judges a file must not run it.

set -uo pipefail

PIN_FILE=""
MODE="verify"
QUIET=0

while [ $# -gt 0 ]; do
  case "$1" in
    --pin-file)       PIN_FILE="${2:-}"; shift ;;
    --compute)        MODE="compute" ;;
    --canonical)      MODE="canonical" ;;
    --integrity-only) MODE="integrity" ;;
    --quiet|-q)       QUIET=1 ;;
    -h|--help)        sed -n '2,75p' "$0"; exit 0 ;;
    *) echo "ghl-mcp-check-pin-digest.sh: unknown argument '$1'" >&2; exit 1 ;;
  esac
  shift
done

say() { [ "$QUIET" -eq 1 ] || printf '%s\n' "$*"; }
err() { printf '%s\n' "$*" >&2; }

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

# Resolver order is deliberately IDENTICAL to the installers' own order, so the
# gate can never judge a different file from the one the box will execute.
if [ -z "$PIN_FILE" ]; then
  for _c in "$SELF_DIR/../config/ghl-mcp-pin.env" \
            "$HOME/.openclaw/config/ghl-mcp-pin.env" \
            "$HOME/.openclaw/onboarding/config/ghl-mcp-pin.env" \
            "$HOME/.openclaw/skills/config/ghl-mcp-pin.env" \
            "/data/.openclaw/config/ghl-mcp-pin.env" \
            "/data/.openclaw/onboarding/config/ghl-mcp-pin.env" \
            "/data/.openclaw/skills/config/ghl-mcp-pin.env"; do
    [ -f "$_c" ] && { PIN_FILE="$_c"; break; }
  done
fi

if [ -z "$PIN_FILE" ] || [ ! -f "$PIN_FILE" ]; then
  err "PIN-DIGEST: pin file not found${PIN_FILE:+ at $PIN_FILE}"
  exit 2
fi

# ── sha256 helper ────────────────────────────────────────────────────────────
if command -v shasum >/dev/null 2>&1; then
  _sha256() { shasum -a 256 | awk '{print $1}'; }
elif command -v sha256sum >/dev/null 2>&1; then
  _sha256() { sha256sum | awk '{print $1}'; }
else
  err "PIN-DIGEST: no shasum/sha256sum on PATH — NOTHING WAS VERIFIED."
  exit 3
fi

# ── Field reader ─────────────────────────────────────────────────────────────
# Reads KEY="value" assignments. LAST assignment wins, matching what `.` would
# do, so the gate and a sourcing installer can never see different values.
# Only double-quoted single-line values are recognised; the vetting tool refuses
# to write anything else, and an unrecognised shape reads as empty, which fails
# the well-formedness checks below rather than silently passing.
field() {
  awk -v key="$1" '
    $0 ~ "^" key "=\"" {
      line = $0
      sub("^" key "=\"", "", line)
      idx = index(line, "\"")
      if (idx > 0) val = substr(line, 1, idx - 1)
      else         val = ""
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

# ── Canonical form v1 ────────────────────────────────────────────────────────
# Newline-separated, explicitly LABELLED fields under a versioned domain-
# separator line. Labels (rather than a bare "a|b|c" join) mean no pair of field
# values can be shuffled across the boundary to produce the same hash, and the
# version line means a future format change is distinguishable from a mismatch
# rather than silently colliding with it.
canonical() {
  printf 'GHL-MCP-PIN-VET-v1\n'
  printf 'commit=%s\n'           "$COMMIT"
  printf 'verdict=%s\n'          "$VERDICT"
  printf 'on=%s\n'               "$VET_ON"
  printf 'by=%s\n'               "$VET_BY"
  printf 'deps_lock_sha256=%s\n' "$LOCK_SHA"
  printf 'repo_url=%s\n'         "$REPO_URL"
}

compute() { canonical | _sha256; }

case "$MODE" in
  canonical) canonical; exit 0 ;;
  compute)   compute;   exit 0 ;;
esac

# ── Well-formedness ──────────────────────────────────────────────────────────
# Checked BEFORE the digest comparison so a broken record reports what is
# actually wrong instead of an unhelpful "digest mismatch".
FAILED=0
bad() { err "PIN-DIGEST FAIL: $*"; FAILED=1; }

case "$COMMIT" in
  *[!0-9a-f]*|"") bad "GHL_MCP_VETTED_COMMIT is not lowercase hex" ;;
  *) [ "${#COMMIT}" -eq 40 ] || bad "GHL_MCP_VETTED_COMMIT is ${#COMMIT} chars, not a full 40-char SHA (a short SHA or branch name is not a pin)" ;;
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
  "") bad "GHL_MCP_REPO_URL is empty — the vetted commit has no stated source" ;;
  *)  bad "GHL_MCP_REPO_URL='$REPO_URL' is not an http(s) URL" ;;
esac

# A MISSING digest is a FAILURE, never a skip. "No digest, so nothing to check"
# is precisely the silent pass this mechanism exists to eliminate: deleting one
# line must not be easier than re-vetting.
case "$STORED" in
  "") bad "GHL_MCP_PIN_VETTED_DIGEST is missing — an unsealed vetting record fails closed. Seal it with scripts/ghl-mcp-vet-pin.sh." ;;
  *[!0-9a-f]*) bad "GHL_MCP_PIN_VETTED_DIGEST is not lowercase hex" ;;
  *) [ "${#STORED}" -eq 64 ] || bad "GHL_MCP_PIN_VETTED_DIGEST is ${#STORED} chars, not a 64-char sha256" ;;
esac

if [ "$FAILED" -ne 0 ]; then
  err "PIN-DIGEST: vetting record in $PIN_FILE is malformed — refusing."
  exit 1
fi

ACTUAL="$(compute)"
if [ "$ACTUAL" != "$STORED" ]; then
  err ""
  err "PIN-DIGEST FAIL: the vetting record does not match what it claims to have vetted."
  err "  pin file : $PIN_FILE"
  err "  stored   : $STORED"
  err "  computed : $ACTUAL"
  err ""
  err "Some bound value was changed WITHOUT re-vetting: the commit, the verdict,"
  err "the review date, the reviewer, the dependency lockfile hash, or the source"
  err "repository URL. That is exactly the case this gate exists to refuse."
  err ""
  err "There is no way to hand-repair this, and there should not be. Re-run the"
  err "review and seal the result:"
  err "    scripts/ghl-mcp-vet-pin.sh <commit-sha>                  # review"
  err "    scripts/ghl-mcp-vet-pin.sh <commit-sha> --verdict clean  # seal"
  exit 1
fi

if [ "$MODE" != "integrity" ] && [ "$VERDICT" != "CLEAN" ]; then
  err "PIN-DIGEST FAIL: vetting record is intact and sealed, but the verdict is '$VERDICT', not CLEAN."
  err "  A DIRTY or PENDING pin must never reach a client box."
  exit 1
fi

say "PIN-DIGEST OK: $(basename "$PIN_FILE") — verdict=$VERDICT commit=${COMMIT:0:12} digest=${STORED:0:12}"
exit 0
