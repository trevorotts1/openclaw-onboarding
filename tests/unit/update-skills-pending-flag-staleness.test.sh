#!/usr/bin/env bash
# tests/unit/update-skills-pending-flag-staleness.test.sh
# ---------------------------------------------------------------------------
# THE DEFECT. A live 3-box pilot proved update-skills.sh runs cleanly
# everywhere (exit 0, skills genuinely updated on disk, version stamp
# advanced) yet AGENTS.md and MEMORY.md came out BYTE-IDENTICAL on 3 of 3
# boxes: the pointer/self-heal pass the fresh UPDATE PENDING flag exists to
# trigger never ran. Root cause: _RESUME_NEEDED (the switch between
# write_update_pending_flag() and clear_update_pending_flag()) was computed
# SOLELY from ONBOARDING_GATE_OK (the per-skill qc gate) and NEW_SKILLS_CSV
# (brand-new skill FOLDERS). Neither signal has any idea a "## UPDATE
# PENDING -- Skill Update to vX" section from a PRIOR, never-processed run
# (measured: 2-7 weeks old, three stacked copies on one box) is still sitting
# in AGENTS.md -- an EXISTING skill can receive a genuine CONTENT update
# while its qc sentinel stays stamped from the PREVIOUS pass, so the gate
# reads "yes", NEW_SKILLS_CSV stays empty, and clear_update_pending_flag()
# ran instead of write_update_pending_flag(): a stale block's mere PRESENCE
# was silently treated as proof its work was already queued/done.
#
# THE FIX. _pending_flag_currency_probe() (added alongside the other
# CONTENT-RECHECK-CONVERGENCE-PROBES) reads AGENTS.md, extracts the version
# named by every "## ... UPDATE PENDING ..." / "## ... ONBOARDING PENDING
# ..." header, and reports "stale" the moment ANY of them names a version
# other than the run's own ONBOARDING_VERSION (or is unparsable). The
# Post-update UPDATE PENDING flag LIFECYCLE now ORs this probe into
# _RESUME_NEEDED, so a stale flag forces write_update_pending_flag() --
# which sweeps EVERY stale/duplicate section (via the shared, pre-existing
# _strip_update_pending_sections()) and appends exactly one fresh,
# current-version flag -- instead of silently vanishing under
# clear_update_pending_flag().
#
# METHOD. This test does NOT reimplement any of that logic (the drift that
# already bit tests/unit/update-skills-resume-cron.test.sh's hand-copied
# `decide()`, which omits the gate=="unknown" branch update-skills.sh has
# carried since this morning). It extracts the REAL blocks/functions
# VERBATIM from update-skills.sh -- the CONTENT-RECHECK-CONVERGENCE-PROBES
# marker block (for _pending_flag_currency_probe), the new
# UPDATE-PENDING-FLAG-LIFECYCLE marker block (the exact _RESUME_NEEDED
# formula + write/clear dispatch), and the pre-existing top-level functions
# oc_resolve_workspace_announced / oc_file_size_bytes /
# _strip_update_pending_sections / clear_update_pending_flag /
# write_update_pending_flag -- and sources them together. If any marker or
# function drifts or vanishes, the suite fails loudly (exit 2) rather than
# silently testing nothing.
#
# Each scenario runs against a REAL AGENTS.md fixture under a throwaway
# sandbox $HOME with a minimal openclaw.json (agents.list[0].workspace),
# executes the extracted LIFECYCLE block for real, and asserts on the
# ACTUAL resulting AGENTS.md content and _RESUME_NEEDED -- not a stand-in.
# FULLY OFFLINE: no network call, no real box, nothing under the real
# $HOME or /data/.openclaw is ever read or written.
#
# THE MUTATION-PROOF TABLE THIS PROVES (both directions):
#   1. stale PENDING present (older version stamp) -> swept, fresh flag
#      written, _RESUME_NEEDED=yes (the self-heal/resume-cron trigger)
#   2. CURRENT PENDING present -> not duplicated, not swept spuriously
#   3. no PENDING present -> clean write (or clean no-op when nothing else
#      is outstanding)
#   4. multiple stacked stale blocks (the VPS case: 3) -> all swept, exactly
#      one correct outcome
#   5. re-run immediately after -> byte-identical no-op
# ---------------------------------------------------------------------------
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
UPDATER="$REPO_ROOT/update-skills.sh"

PASS=0
FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ✓ $1"; }
bad() { FAIL=$((FAIL+1)); echo "  ✗ $1"; }

[ -f "$UPDATER" ] || { echo "FATAL: $UPDATER not found"; exit 2; }

WORK="$(mktemp -d -t pending-flag-staleness-test-XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

# --- verbatim extraction between markers (mirrors
#     tests/unit/content-recheck-convergence-probes.test.sh) ---------------
extract_block() {
  awk -v b=">>> $1-BEGIN" -v e="<<< $1-END" '
    index($0, b) { p=1; next }
    index($0, e) { p=0 }
    p { print }
  ' "$UPDATER"
}

# --- verbatim extraction of a single top-level `name() { ... }` function,
#     by brace-matching its own bare closing "}" line (col 0). -------------
extract_function() {
  awk -v fn="$1() {" '
    $0 == fn { p=1 }
    p { print }
    p && $0 == "}" { exit }
  ' "$UPDATER"
}

extract_block "CONTENT-RECHECK-CONVERGENCE-PROBES" > "$WORK/probes.inc"
if [ ! -s "$WORK/probes.inc" ]; then
  echo "FATAL: marker block 'CONTENT-RECHECK-CONVERGENCE-PROBES' not found in update-skills.sh (marker drift?)"
  exit 2
fi
if ! grep -q '_pending_flag_currency_probe() {' "$WORK/probes.inc"; then
  echo "FATAL: _pending_flag_currency_probe() not found inside the PROBES block (drift?)"
  exit 2
fi

extract_block "UPDATE-PENDING-FLAG-LIFECYCLE" > "$WORK/lifecycle.inc"
if [ ! -s "$WORK/lifecycle.inc" ]; then
  echo "FATAL: marker block 'UPDATE-PENDING-FLAG-LIFECYCLE' not found in update-skills.sh (marker drift?)"
  exit 2
fi

for fn in oc_resolve_workspace_announced oc_file_size_bytes \
          _strip_update_pending_sections clear_update_pending_flag \
          write_update_pending_flag; do
  extract_function "$fn" > "$WORK/${fn}.inc"
  if [ ! -s "$WORK/${fn}.inc" ]; then
    echo "FATAL: could not extract ${fn}() from update-skills.sh (drift?)"
    exit 2
  fi
done

# Assemble ONE sourceable library: helpers first, then the probes block
# (unwrapped -- its functions are plain top-level `name() {` definitions
# despite the 2-space indent inherited from its enclosing scope in the real
# script, so sourcing the block directly registers them), then the
# lifecycle block wrapped as a callable function (it is a sequence of
# statements, not a function definition, in the real script).
{
  cat "$WORK/oc_resolve_workspace_announced.inc"
  echo
  cat "$WORK/oc_file_size_bytes.inc"
  echo
  cat "$WORK/_strip_update_pending_sections.inc"
  echo
  cat "$WORK/clear_update_pending_flag.inc"
  echo
  cat "$WORK/write_update_pending_flag.inc"
  echo
  cat "$WORK/probes.inc"
  echo
  echo 'run_lifecycle() {'
  cat "$WORK/lifecycle.inc"
  echo '}'
} > "$WORK/lib.sh"
bash -n "$WORK/lib.sh" || { echo "FATAL: assembled library does not parse"; exit 2; }

echo "== static: the lifecycle block actually ORs in the new staleness probe =="
grep -q '_pending_flag_currency_probe || _RESUME_NEEDED="yes"' "$WORK/lifecycle.inc" \
  && ok "LIFECYCLE block forces _RESUME_NEEDED=yes on a stale/unparsable PENDING section" \
  || bad "LIFECYCLE block does not consult _pending_flag_currency_probe"
grep -q 'write_update_pending_flag "\$ONBOARDING_VERSION" "\$NEW_SKILLS_CSV"' "$WORK/lifecycle.inc" \
  && ok "LIFECYCLE block still dispatches to write_update_pending_flag on _RESUME_NEEDED=yes" \
  || bad "LIFECYCLE block does not call write_update_pending_flag"
grep -q 'clear_update_pending_flag' "$WORK/lifecycle.inc" \
  && ok "LIFECYCLE block still dispatches to clear_update_pending_flag on _RESUME_NEEDED=no" \
  || bad "LIFECYCLE block does not call clear_update_pending_flag"

# Cross-check against the update-skills-resume-cron.test.sh (E) contract:
# the self-heal resume cron is installed exactly when _RESUME_NEEDED=="yes".
# This test proves what _RESUME_NEEDED COMES OUT AS for each scenario; (E)
# already proves the cron install is gated on that same variable.
if grep -q 'if \[ "\$_RESUME_NEEDED" = "yes" \]; then' "$UPDATER"; then
  ok "update-skills.sh still gates the onboarding-resume self-heal cron on _RESUME_NEEDED (verified by update-skills-resume-cron.test.sh)"
else
  bad "update-skills.sh no longer gates the resume cron on _RESUME_NEEDED (drift?)"
fi

# ---------------------------------------------------------------------------
# Harness: run the REAL extracted lifecycle against a sandboxed workspace.
# ---------------------------------------------------------------------------
count_pending_sections() {  # count_pending_sections <file>
  grep -cE '^## .*(UPDATE PENDING|ONBOARDING PENDING)' "$1" 2>/dev/null || true
}

# run_scenario <case_dir> <agents_md_fixture_or_empty> <gate> <new_skills_csv> <version>
# Returns via files under case_dir: resume_needed, agents_after.md, stderr.log
run_scenario() {
  local case_dir="$1" fixture="$2" gate="$3" new_skills="$4" version="$5"
  mkdir -p "$case_dir/home/.openclaw" "$case_dir/ws"
  python3 -c "
import json
json.dump({'agents': {'list': [{'id': 'main', 'workspace': '$case_dir/ws'}]}}, open('$case_dir/home/.openclaw/openclaw.json', 'w'))
"
  if [ -n "$fixture" ]; then
    cp "$fixture" "$case_dir/ws/AGENTS.md"
  fi
  (
    set -euo pipefail
    # shellcheck source=/dev/null
    source "$WORK/lib.sh"
    HOME="$case_dir/home"
    ONBOARDING_GATE_OK="$gate"
    NEW_SKILLS_CSV="$new_skills"
    ONBOARDING_VERSION="$version"
    LOG_FILE="$case_dir/log"
    run_lifecycle
    echo "$_RESUME_NEEDED" > "$case_dir/resume_needed"
  ) >"$case_dir/stdout.log" 2>"$case_dir/stderr.log"
}

echo ""
echo "== Scenario 1: STALE PENDING present (older version), gate green, no new skills =="
D1="$WORK/s1"; mkdir -p "$D1"
cat > "$D1/agents-before.md" <<'EOF'
# AGENTS.md

Some ordinary operating content that must survive untouched.

## UPDATE PENDING -- Skill Update to v21.7.2

A skill update was applied via update-skills.sh on 2026-06-15. Activate each new skill below
and run the verification gate.

**You do NOT need to delete this section.** update-skills.sh owns it.
EOF
run_scenario "$D1" "$D1/agents-before.md" "yes" "" "v21.7.5"
RN1="$(cat "$D1/resume_needed" 2>/dev/null || echo "<missing>")"
[ "$RN1" = "yes" ] && ok "(s1) _RESUME_NEEDED=yes despite gate=yes + no new skills (the stale flag alone forces it)" \
  || bad "(s1) _RESUME_NEEDED=$RN1 (expected yes): $(cat "$D1/stderr.log")"
AFTER1="$D1/ws/AGENTS.md"
[ -f "$AFTER1" ] || { bad "(s1) AGENTS.md missing after the run"; }
N1="$(count_pending_sections "$AFTER1")"
[ "${N1:-0}" -eq 1 ] 2>/dev/null && ok "(s1) exactly ONE UPDATE PENDING section remains (stale swept, fresh appended)" \
  || bad "(s1) expected exactly 1 PENDING section, found ${N1:-?}: $(grep -n '^##' "$AFTER1" 2>/dev/null)"
grep -q 'Skill Update to v21.7.5' "$AFTER1" 2>/dev/null && ok "(s1) the surviving section names the CURRENT version (v21.7.5)" \
  || bad "(s1) surviving section does not name v21.7.5"
grep -q 'Skill Update to v21.7.2' "$AFTER1" 2>/dev/null && bad "(s1) the STALE v21.7.2 section is still present -- not swept" \
  || ok "(s1) the stale v21.7.2 section is gone"
grep -q 'Some ordinary operating content' "$AFTER1" 2>/dev/null && ok "(s1) unrelated AGENTS.md content survived untouched" \
  || bad "(s1) unrelated content was lost"

echo ""
echo "== Scenario 2: CURRENT-version PENDING present, gate green, no new skills =="
D2="$WORK/s2"; mkdir -p "$D2"
cat > "$D2/agents-before.md" <<'EOF'
# AGENTS.md

## UPDATE PENDING -- Skill Update to v21.7.5

A skill update was applied via update-skills.sh today. Activate each new skill below.
EOF
run_scenario "$D2" "$D2/agents-before.md" "yes" "" "v21.7.5"
RN2="$(cat "$D2/resume_needed" 2>/dev/null || echo "<missing>")"
[ "$RN2" = "no" ] && ok "(s2) _RESUME_NEEDED=no (current-version flag is not treated as stale)" \
  || bad "(s2) _RESUME_NEEDED=$RN2 (expected no): $(cat "$D2/stderr.log")"
AFTER2="$D2/ws/AGENTS.md"
N2="$(count_pending_sections "$AFTER2")"
[ "${N2:-0}" -eq 0 ] 2>/dev/null && ok "(s2) gate genuinely green -> the now-obsolete CURRENT flag is correctly cleared (not left duplicated)" \
  || bad "(s2) expected 0 PENDING sections after a clean gate, found ${N2:-?}"

echo ""
echo "== Scenario 2b: CURRENT-version PENDING present, gate STILL red (mid-cycle re-run) =="
D2B="$WORK/s2b"; mkdir -p "$D2B"
cp "$D2/agents-before.md" "$D2B/agents-before.md"
run_scenario "$D2B" "$D2B/agents-before.md" "no" "" "v21.7.5"
RN2B="$(cat "$D2B/resume_needed" 2>/dev/null || echo "<missing>")"
[ "$RN2B" = "yes" ] && ok "(s2b) _RESUME_NEEDED=yes (gate=no on its own already forces this)" \
  || bad "(s2b) _RESUME_NEEDED=$RN2B (expected yes): $(cat "$D2B/stderr.log")"
AFTER2B="$D2B/ws/AGENTS.md"
N2B="$(count_pending_sections "$AFTER2B")"
[ "${N2B:-0}" -eq 1 ] 2>/dev/null && ok "(s2b) re-writing a CURRENT-version flag stays at exactly ONE copy (not duplicated)" \
  || bad "(s2b) expected exactly 1 PENDING section, found ${N2B:-?}"

echo ""
echo "== Scenario 3: no PENDING present, gate green, no new skills =="
D3="$WORK/s3"; mkdir -p "$D3"
cat > "$D3/agents-before.md" <<'EOF'
# AGENTS.md

Nothing pending. A perfectly ordinary operating file.
EOF
run_scenario "$D3" "$D3/agents-before.md" "yes" "" "v21.7.5"
RN3="$(cat "$D3/resume_needed" 2>/dev/null || echo "<missing>")"
[ "$RN3" = "no" ] && ok "(s3) _RESUME_NEEDED=no (nothing pending anywhere)" \
  || bad "(s3) _RESUME_NEEDED=$RN3 (expected no): $(cat "$D3/stderr.log")"
AFTER3="$D3/ws/AGENTS.md"
if diff -q "$D3/agents-before.md" "$AFTER3" >/dev/null 2>&1; then
  ok "(s3) clean write: AGENTS.md is BYTE-IDENTICAL to before (no PENDING to add or remove)"
else
  bad "(s3) AGENTS.md changed even though nothing was pending"
fi
BAK3_COUNT=$(find "$D3/ws" -maxdepth 1 -name 'AGENTS.md.bak-*' 2>/dev/null | wc -l | tr -d ' ')
[ "${BAK3_COUNT:-0}" -eq 0 ] && ok "(s3) no backup file was created for a genuine no-op" \
  || bad "(s3) a backup file was created even though nothing changed (found $BAK3_COUNT)"

echo ""
echo "== Scenario 4: THREE stacked stale blocks (measured VPS case), gate green, no new skills =="
D4="$WORK/s4"; mkdir -p "$D4"
cat > "$D4/agents-before.md" <<'EOF'
# AGENTS.md

Operating content above the flags.

## UPDATE PENDING -- Skill Update to v21.6.9

Wave 1, never processed (oldest).

## UPDATE PENDING -- Skill Update to v21.7.0

Wave 2, never processed.

## UPDATE PENDING -- Skill Update to v21.7.3

Wave 3, never processed (newest of the three, still not current).
EOF
run_scenario "$D4" "$D4/agents-before.md" "yes" "" "v21.7.5"
RN4="$(cat "$D4/resume_needed" 2>/dev/null || echo "<missing>")"
[ "$RN4" = "yes" ] && ok "(s4) _RESUME_NEEDED=yes with three stacked stale sections present" \
  || bad "(s4) _RESUME_NEEDED=$RN4 (expected yes): $(cat "$D4/stderr.log")"
AFTER4="$D4/ws/AGENTS.md"
N4="$(count_pending_sections "$AFTER4")"
[ "${N4:-0}" -eq 1 ] 2>/dev/null && ok "(s4) all three stacked stale sections swept down to exactly ONE fresh section" \
  || bad "(s4) expected exactly 1 PENDING section after sweeping 3 stale ones, found ${N4:-?}: $(grep -n '^##' "$AFTER4" 2>/dev/null)"
for v in v21.6.9 v21.7.0 v21.7.3; do
  grep -q "Skill Update to $v" "$AFTER4" 2>/dev/null \
    && bad "(s4) stale section for $v is still present" \
    || ok "(s4) stale section for $v was swept"
done
grep -q 'Skill Update to v21.7.5' "$AFTER4" 2>/dev/null && ok "(s4) surviving section names the CURRENT version (v21.7.5)" \
  || bad "(s4) surviving section does not name v21.7.5"
grep -q 'Operating content above the flags' "$AFTER4" 2>/dev/null && ok "(s4) unrelated content above the stacked flags survived" \
  || bad "(s4) unrelated content above the stacked flags was lost"

echo ""
echo "== Scenario 5: re-run immediately after (idempotency) =="
echo "-- 5a: re-run scenario 3's genuinely-clean box -- must stay byte-identical --"
D5A="$WORK/s5a"; mkdir -p "$D5A"
cp "$AFTER3" "$D5A/agents-before.md"
run_scenario "$D5A" "$D5A/agents-before.md" "yes" "" "v21.7.5"
AFTER5A="$D5A/ws/AGENTS.md"
if diff -q "$D5A/agents-before.md" "$AFTER5A" >/dev/null 2>&1; then
  ok "(s5a) re-running an already-clean box a second time is byte-identical (no-op stays a no-op)"
else
  bad "(s5a) second run diverged from the first on an already-clean box"
fi

echo "-- 5b: re-run scenario 1's freshly-swept box, gate STILL red -- content-stable --"
D5B="$WORK/s5b"; mkdir -p "$D5B"
cp "$AFTER1" "$D5B/agents-before.md"
run_scenario "$D5B" "$D5B/agents-before.md" "no" "" "v21.7.5"
AFTER5B="$D5B/ws/AGENTS.md"
RN5B="$(cat "$D5B/resume_needed" 2>/dev/null || echo "<missing>")"
if diff -q "$D5B/agents-before.md" "$AFTER5B" >/dev/null 2>&1; then
  ok "(s5b) re-writing an already-current flag on the same day is byte-identical (strip+append reproduces the same bytes)"
else
  bad "(s5b) re-run of an already-current flag changed the file's bytes: $(diff "$D5B/agents-before.md" "$AFTER5B" 2>&1 | head -5)"
fi
[ "$RN5B" = "yes" ] && ok "(s5b) gate=no alone (unrelated to the staleness probe) still correctly forces _RESUME_NEEDED=yes" \
  || bad "(s5b) _RESUME_NEEDED=$RN5B (expected yes, driven by gate=no)"

echo ""
echo "----------------------------------------"
echo "  PASS: $PASS    FAIL: $FAIL"
echo "----------------------------------------"
[ "$FAIL" -eq 0 ] || exit 1
