#!/usr/bin/env bash
# ghl-mcp-pin-digest.sh — canonical SELF-INVALIDATING VETTING DIGEST primitive
# for config/ghl-mcp-pin.env.
#
# ─────────────────────────────────────────────────────────────────────────────
# WHY THIS EXISTS
#
# The vetting verdict used to be a rule addressed to a human:
#   "Any change to GHL_MCP_VETTED_COMMIT MUST reset the three
#    GHL_MCP_PIN_VETTED_* fields to PENDING until the new commit is re-vetted."
# A rule that requires somebody to remember an extra step is documentation, not
# enforcement. The verdict field was sourced by three scripts and read by NONE
# of them, so the default outcome of forgetting was SILENT ACCEPTANCE.
#
# The digest inverts that: it binds the verdict to the commit. Change the
# commit by hand and the digest no longer recomputes, so every consumer
# REFUSES. The default outcome of forgetting becomes refusal.
#
# THIS IS NOT A SIGNATURE AND DOES NOT PRETEND TO BE. It is a plain unkeyed
# SHA-256; anyone with repo write access can recompute it. Its job is to make
# FORGETTING impossible, not to stop a determined attacker. (Upgrade path if
# tamper-evidence is wanted later: sign the same tuple with `git tag -s` or
# minisign — the consumer check shape below does not change.)
#
# ─────────────────────────────────────────────────────────────────────────────
# THE CANONICAL ALGORITHM  (algorithm id: ghl-mcp-pin-v1)
#
#   payload = each of the following, in this exact order, each followed by a
#             single LF (0x0A), UTF-8, no other separators, no trailing pad:
#
#       1.  the literal string   ghl-mcp-pin-v1
#       2.  GHL_MCP_VETTED_COMMIT
#       3.  GHL_MCP_PIN_VETTED_VERDICT
#       4.  GHL_MCP_PIN_VETTED_ON
#       5.  GHL_MCP_PIN_VETTED_BY
#       6.  GHL_MCP_DEPS_LOCK_SHA256
#
#   digest  = lowercase hex SHA-256 of that byte string.
#
#   Reference one-liner (portable):
#       printf '%s\n' ghl-mcp-pin-v1 "$commit" "$verdict" "$on" "$by" "$deps" \
#         | shasum -a 256 | cut -d' ' -f1
#
#   Field values are read WITHOUT sourcing the file (the pin file is `.env`-
#   shaped but is `.`-sourced by the installers; a digest tool must never
#   execute what it is auditing). Values are the contents of the LAST
#   `^KEY="…"` assignment, with the surrounding double quotes removed and any
#   trailing ` # comment` on the same line removed. A field that is absent is
#   the empty string — which is why an absent field cannot silently produce a
#   matching digest for a different field set.
#
# ─────────────────────────────────────────────────────────────────────────────
# CONTRACT FOR scripts/ghl-mcp-vet-pin.sh  (the human vetting workflow, R7)
#
#   The vetting tool MUST NOT reimplement the algorithm. It MUST call:
#
#       DIGEST="$(bash scripts/ghl-mcp-pin-digest.sh compute <pin-file>)"
#
#   after it has written the new commit / verdict / date / reviewer /
#   deps-lock-sha into the file, and then write that value into
#   GHL_MCP_PIN_VETTED_DIGEST. `compute` deliberately ignores any existing
#   GHL_MCP_PIN_VETTED_DIGEST line, so compute-then-write is idempotent.
#
#   CI (`ghl-mcp-check-pin-digest.sh`), the pre-push hook, and the box-side
#   installers all call `verify` and gate on its exit code.
#
# ─────────────────────────────────────────────────────────────────────────────
# USAGE
#   ghl-mcp-pin-digest.sh compute <pin-file>   # print the canonical digest
#   ghl-mcp-pin-digest.sh verify  <pin-file>   # compare against the recorded one
#   ghl-mcp-pin-digest.sh fields  <pin-file>   # print the parsed tuple (debug)
#
# EXIT CODES (`verify`) — consumers MUST distinguish 3 from 1:
#   0  MATCH        digest present and recomputes
#   1  MISMATCH     digest present and does NOT recompute  -> hard refusal
#   3  ABSENT       no GHL_MCP_PIN_VETTED_DIGEST field yet -> caller falls back
#                   to requiring GHL_MCP_PIN_VETTED_VERDICT=CLEAN (transitional;
#                   see R9 in the hardening analysis)
#   4  UNUSABLE     pin file missing/unreadable, or no sha256 tool on PATH
#
# Never writes anything. Safe to run anywhere.

set -u

_usage() {
  printf 'usage: %s {compute|verify|fields} <pin-file>\n' "$(basename "$0")" >&2
}

MODE="${1:-}"
PIN_FILE="${2:-}"

case "$MODE" in
  compute|verify|fields) : ;;
  *) _usage; exit 4 ;;
esac

if [ -z "$PIN_FILE" ] || [ ! -r "$PIN_FILE" ]; then
  printf 'ghl-mcp-pin-digest: pin file not readable: %s\n' "${PIN_FILE:-<none>}" >&2
  exit 4
fi

# ── sha256, portable across macOS (shasum) and Linux (sha256sum) ─────────────
_sha256() {
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 | cut -d' ' -f1
  elif command -v sha256sum >/dev/null 2>&1; then
    sha256sum | cut -d' ' -f1
  else
    return 1
  fi
}

if ! printf '' | _sha256 >/dev/null 2>&1; then
  printf 'ghl-mcp-pin-digest: no sha256 tool on PATH (shasum/sha256sum)\n' >&2
  exit 4
fi

# ── Read a field WITHOUT sourcing the file ───────────────────────────────────
# Last `^KEY="value"` wins. Strips the quotes and any trailing `# comment`.
_field() {
  local key="$1" line
  line="$(sed -n "s/^${key}=\"\\(.*\\)\"[[:space:]]*\\(#.*\\)\\{0,1\\}\$/\\1/p" "$PIN_FILE" 2>/dev/null | tail -1)"
  if [ -z "$line" ]; then
    # Tolerate an unquoted assignment (KEY=value) — same trailing-comment rule.
    line="$(sed -n "s/^${key}=\\([^\"#]*\\).*\$/\\1/p" "$PIN_FILE" 2>/dev/null | tail -1)"
    # Trim trailing whitespace left by the comment strip.
    line="${line%"${line##*[![:space:]]}"}"
  fi
  printf '%s' "$line"
}

PIN_COMMIT="$(_field GHL_MCP_VETTED_COMMIT)"
PIN_VERDICT="$(_field GHL_MCP_PIN_VETTED_VERDICT)"
PIN_ON="$(_field GHL_MCP_PIN_VETTED_ON)"
PIN_BY="$(_field GHL_MCP_PIN_VETTED_BY)"
PIN_DEPS="$(_field GHL_MCP_DEPS_LOCK_SHA256)"
PIN_RECORDED="$(_field GHL_MCP_PIN_VETTED_DIGEST)"

_compute() {
  printf '%s\n' \
    'ghl-mcp-pin-v1' \
    "$PIN_COMMIT" \
    "$PIN_VERDICT" \
    "$PIN_ON" \
    "$PIN_BY" \
    "$PIN_DEPS" | _sha256
}

case "$MODE" in
  fields)
    printf 'algorithm=%s\n' 'ghl-mcp-pin-v1'
    printf 'commit=%s\n'    "$PIN_COMMIT"
    printf 'verdict=%s\n'   "$PIN_VERDICT"
    printf 'vetted_on=%s\n' "$PIN_ON"
    printf 'vetted_by=%s\n' "$PIN_BY"
    printf 'deps_lock_sha256=%s\n' "$PIN_DEPS"
    printf 'recorded_digest=%s\n'  "$PIN_RECORDED"
    printf 'computed_digest=%s\n'  "$(_compute)"
    exit 0
    ;;
  compute)
    _compute
    exit 0
    ;;
  verify)
    if [ -z "$PIN_RECORDED" ]; then
      printf 'ghl-mcp-pin-digest: ABSENT — %s carries no GHL_MCP_PIN_VETTED_DIGEST yet (transitional; caller must fall back to requiring VERDICT=CLEAN)\n' \
        "$PIN_FILE" >&2
      exit 3
    fi
    _COMPUTED="$(_compute)"
    if [ "$_COMPUTED" = "$PIN_RECORDED" ]; then
      printf 'ghl-mcp-pin-digest: MATCH %s\n' "$_COMPUTED"
      exit 0
    fi
    printf 'ghl-mcp-pin-digest: MISMATCH — recorded=%s computed=%s\n' "$PIN_RECORDED" "$_COMPUTED" >&2
    printf 'ghl-mcp-pin-digest: the pin was edited without re-running the vetting tool. Re-vet with scripts/ghl-mcp-vet-pin.sh; do NOT hand-edit the digest.\n' >&2
    exit 1
    ;;
esac
