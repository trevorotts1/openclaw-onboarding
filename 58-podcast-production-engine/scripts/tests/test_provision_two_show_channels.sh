#!/usr/bin/env bash
# =============================================================================
# SKILL 58 - PODCAST PRODUCTION ENGINE :: two-show channel capture tests
# -----------------------------------------------------------------------------
# Proves provision-podcast-client.sh STEP 5.5 (the two-show convention wiring,
# SOP-PODCAST-02 Section 2.5). The block is extracted from the provisioning
# script and sourced inside a harness that records ledger steps and facts, so
# no Cloudflare API, no network, no secrets are involved. Asserts:
#   1. bash -n: the full provisioning script still parses.
#   2. the extraction anchor is unique: exactly one STEP 5.5 header, exactly
#      one STEP 6 header (an extraction that grabbed the wrong region would
#      silently test nothing).
#   3. both channel ids supplied with a valid slug -> channels:personal OK and
#      channels:interview OK, both ids recorded as ledger facts.
#   4. nothing supplied -> BOTH steps record PENDING, nothing is invented, and
#      the printed env contract names PODBEAN_PODCAST_ID and the show var.
#   5. interview id without a slug -> channels:interview PENDING (the show var
#      cannot be named without a slug).
#   6. a lowercase/bad slug -> channels:interview PENDING (slug must be
#      uppercase, underscore form to build PODBEAN_PODCAST_ID_<SHOW_SLUG>).
#   7. dry-run records the DRY-RUN step and never writes ledger facts.
# Run:  bash 58-podcast-production-engine/scripts/tests/test_provision_two_show_channels.sh
# =============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROVISION="$HERE/../provision-podcast-client.sh"

bash -n "$PROVISION" || { echo "FAIL: bash -n provision-podcast-client.sh"; exit 1; }

# Anchor uniqueness: the extraction below is only trustworthy if the STEP 5.5
# and STEP 6 headers each occur exactly once.
N55="$(grep -c 'two-show channel capture (SOP-PODCAST-02 Section 2.5' "$PROVISION" || true)"
N6="$(grep -c '^# STEP 6: delegated box-side wiring' "$PROVISION" || true)"
[ "$N55" -eq 1 ] || { echo "FAIL: STEP 5.5 header count=$N55 (want 1)"; exit 1; }
[ "$N6" -eq 1 ] || { echo "FAIL: STEP 6 header count=$N6 (want 1)"; exit 1; }
echo "PASS: extraction anchors unique (STEP 5.5 and STEP 6 headers)"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
awk '/two-show channel capture \(SOP-PODCAST-02 Section 2.5/{f=1} f{print} /^# STEP 6: delegated box-side wiring/{if(f)exit}' "$PROVISION" > "$WORK/block.sh"
grep -q 'provision_channels$' "$WORK/block.sh" || { echo "FAIL: block extraction missed provision_channels"; exit 1; }

# Harness: record ledger steps/facts, capture the printed contract.
STEPS_FILE="$WORK/steps.txt"
FACTS_FILE="$WORK/facts.txt"
LOG_FILE="$WORK/log.txt"
reset_harness() { : > "$STEPS_FILE"; : > "$FACTS_FILE"; : > "$LOG_FILE"; }
ledger_step() { printf '%s|%s|%s\n' "$2" "$1" "${3:-}" >> "$STEPS_FILE"; }
ledger_fact() { printf '%s=%s\n' "$1" "$2" >> "$FACTS_FILE"; }
log() { printf '%s\n' "$*" >> "$LOG_FILE"; }

run_block() {
  reset_harness
  # shellcheck disable=SC1090
  source "$WORK/block.sh"
}

# ledger_step records "STATUS|NAME|DETAIL"; facts record "KEY=VALUE".
has_step() { grep -q "^$2|$1|" "$STEPS_FILE"; }
has_fact() { grep -q "^$1=$2$" "$FACTS_FILE"; }

# --- 3. both channels + valid slug: both OK, facts recorded -----------------
PERSONAL_CHANNEL_ID="chan-personal-123"
INTERVIEW_CHANNEL_ID="chan-interview-456"
INTERVIEW_SHOW_SLUG="SOFT_GIRL_ERA"
DRY_RUN="0"
run_block
has_step "channels:personal" "OK" || { echo "FAIL: channels:personal not OK"; cat "$STEPS_FILE"; exit 1; }
has_step "channels:interview" "OK" || { echo "FAIL: channels:interview not OK"; cat "$STEPS_FILE"; exit 1; }
has_fact "personal_channel_id" "chan-personal-123" || { echo "FAIL: personal fact missing"; exit 1; }
has_fact "interview_channel_id" "chan-interview-456" || { echo "FAIL: interview fact missing"; exit 1; }
has_fact "interview_show_slug" "SOFT_GIRL_ERA" || { echo "FAIL: slug fact missing"; exit 1; }
grep -q 'PODBEAN_PODCAST_ID=chan-personal-123' "$LOG_FILE" || { echo "FAIL: contract missing personal line"; exit 1; }
grep -q 'PODBEAN_PODCAST_ID_SOFT_GIRL_ERA=chan-interview-456' "$LOG_FILE" || { echo "FAIL: contract missing interview line"; exit 1; }
echo "PASS: both channels supplied -> both OK + ledger facts + printed contract"

# --- 4. nothing supplied: both PENDING, nothing invented ---------------------
PERSONAL_CHANNEL_ID=""
INTERVIEW_CHANNEL_ID=""
INTERVIEW_SHOW_SLUG=""
DRY_RUN="0"
run_block
has_step "channels:personal" "PENDING" || { echo "FAIL: channels:personal not PENDING"; cat "$STEPS_FILE"; exit 1; }
has_step "channels:interview" "PENDING" || { echo "FAIL: channels:interview not PENDING"; cat "$STEPS_FILE"; exit 1; }
has_fact "personal_channel_id" "NOT-SUPPLIED" || { echo "FAIL: personal fact should be NOT-SUPPLIED"; exit 1; }
grep -q 'PODBEAN_PODCAST_ID=<personal-show Channel ID>' "$LOG_FILE" || { echo "FAIL: contract missing personal placeholder"; exit 1; }
echo "PASS: no channels supplied -> both PENDING, never invented"

# --- 5. interview id without slug: PENDING ------------------------------------
PERSONAL_CHANNEL_ID="chan-personal-123"
INTERVIEW_CHANNEL_ID="chan-interview-456"
INTERVIEW_SHOW_SLUG=""
DRY_RUN="0"
run_block
has_step "channels:interview" "PENDING" || { echo "FAIL: channels:interview should be PENDING without slug"; cat "$STEPS_FILE"; exit 1; }
echo "PASS: interview channel without slug -> PENDING"

# --- 6. lowercase slug rejected ------------------------------------------------
PERSONAL_CHANNEL_ID="chan-personal-123"
INTERVIEW_CHANNEL_ID="chan-interview-456"
INTERVIEW_SHOW_SLUG="soft_girl_era"
DRY_RUN="0"
run_block
has_step "channels:interview" "PENDING" || { echo "FAIL: lowercase slug should yield PENDING"; cat "$STEPS_FILE"; exit 1; }
echo "PASS: lowercase slug -> PENDING (slug must be uppercase, underscore form)"

# --- 7. dry-run: DRY-RUN step, no facts ----------------------------------------
PERSONAL_CHANNEL_ID="chan-personal-123"
INTERVIEW_CHANNEL_ID="chan-interview-456"
INTERVIEW_SHOW_SLUG="SOFT_GIRL_ERA"
DRY_RUN="1"
run_block
has_step "channels:two-show" "DRY-RUN" || { echo "FAIL: dry-run step missing"; cat "$STEPS_FILE"; exit 1; }
if has_fact "personal_channel_id" "chan-personal-123"; then
  echo "FAIL: dry-run must not write ledger facts"; exit 1
fi
echo "PASS: dry-run records DRY-RUN and writes no ledger facts"

echo "ALL PASS: test_provision_two_show_channels.sh (5 checks + 2 anchor guards)"
