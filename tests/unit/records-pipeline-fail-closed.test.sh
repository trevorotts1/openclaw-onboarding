#!/usr/bin/env bash
# tests/unit/records-pipeline-fail-closed.test.sh
#
# Acceptance tests for the Skill 39 + Skill 40 records-pipeline fail-closed
# programme (SK1-30). One test per finding, each written so it FAILS against the
# pre-fix behaviour and PASSES after:
#
#   T0-49  the audit-log append was fire-and-forget in BOTH skills
#          (`_emit` swallowed the status; property-lookup.sh redirected straight
#          into the file and announced success either way)
#   T0-51  a failed extension copy still emitted an "installed" event and
#          printed Done
#   T0-53  the target validator passed an UNEDITED template as "safe to use as a
#          live tier target" because it counted selector KEYS
#   T0-54  the compliance gate printed "RESULT: PASS" and exited 0 when jq was
#          missing, having run no assertion at all
#   T0-55  the no-fabrication assertion checked that `resolved` EXISTS, not that
#          it is false
#   T1-05  the cache key omitted the query, so one address could be served
#          another address's attributed record as a cache hit
#   T2-33  the rate limiter stamped the timestamp before sleeping, so
#          consecutive fetches landed inside the configured interval
#   T2-34  a passing validation recorded no attestation
#
# Every negative assertion is paired with a MUTATION PROOF: a private copy of
# the fixed file is reverted to the defect and the same assertion is re-run,
# which must then observe the defect. A mutation that changes nothing means the
# assertion was not testing what it claims.
#
# Hermetic: private sandboxes, a stubbed resolver/tier (no network), a fake
# retrieval hook, and a fake transport. No fleet box, no real ~/.openclaw.
#
# Exit 0 = all checks pass. Exit 1 = one or more failed (CI FAIL).

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
S40="$REPO_ROOT/40-zhc-public-records-scraper"
S39="$REPO_ROOT/39-real-estate-playbook"
PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== records-pipeline-fail-closed.test.sh ==="
echo ""

command -v jq >/dev/null 2>&1 || { echo "SKIP-IMPOSSIBLE: jq is required to run this suite"; exit 1; }

SANDBOX="$(mktemp -d)"
cleanup() { chmod -R u+rwX "$SANDBOX" 2>/dev/null || true; rm -rf "$SANDBOX" 2>/dev/null || true; }
trap cleanup EXIT
case "$SANDBOX" in
  */.openclaw|*/.openclaw/*) echo "REFUSING: sandbox resolved into a real .openclaw ($SANDBOX)"; exit 2 ;;
esac

# A private copy of both skills so mutation proofs never touch the repo files.
COPY="$SANDBOX/repo"
mkdir -p "$COPY"
cp -R "$S40" "$COPY/"
cp -R "$S39" "$COPY/"
C40="$COPY/$(basename "$S40")"
C39="$COPY/$(basename "$S39")"

# ---------------------------------------------------------------------------
# A driver that exercises lib-records.sh :: query() WITHOUT a network. It
# sources the library (whose CLI dispatch is guarded by BASH_SOURCE==$0) and
# replaces resolve()/tier() with fixed answers, so the cache, audit and
# rate-limit paths under test run exactly as they do in production.
# ---------------------------------------------------------------------------
_driver() { # <lib-path> <master-files-dir> <query> [<retrieve-hook>|none]
  local lib="$1" mfd="$2" q="$3" hook="${4:-none}"
  local env_hook=()
  if [ "$hook" != "none" ]; then
    env_hook=(SKILL40_RETRIEVE_CMD="$hook" SKILL40_ALLOW_RETRIEVE_CMD=1)
  fi
  env MASTER_FILES_DIR="$mfd" PR_PER_TARGET_MIN_INTERVAL_S=0 "${env_hook[@]}" \
    bash -c '
      set -uo pipefail
      . "$1"
      resolve() { echo "{\"resolved\":true,\"county_fips\":\"99999\",\"state\":\"99\",\"county_name\":\"Mock\",\"state_abbr\":\"XX\"}"; }
      tier()    { echo "{\"tier\":\"tier3\",\"target_ref\":\"mock-target\",\"platform\":\"custom\",\"reason\":\"test stub\"}"; }
      query "$2" ownership
    ' _ "$lib" "$q"
}

_mk_hook() { # <path> <owner-value>
  cat > "$1" <<HOOK
#!/usr/bin/env bash
printf '%s' '{"owner":"$2","source":"https://records.example.invalid/portal","retrieved_at":"2026-07-05T00:00:00Z"}'
HOOK
  chmod +x "$1"
}

# ===========================================================================
# T0-49 — Skill 40: a failed audit append must not produce a record
# ===========================================================================
echo "--- T0-49a: skill 40 _emit propagates a failed append ---"
SB1="$SANDBOX/mfd-emit"; mkdir -p "$SB1"
# Make the events log unwritable by planting a DIRECTORY where the JSONL goes.
mkdir -p "$SB1/public-records-queries.jsonl"

rc_fixed=0
MASTER_FILES_DIR="$SB1" bash -c '. "$1"; _emit query "{\"t\":1}"' _ "$C40/scripts/lib-records.sh" >/dev/null 2>&1 || rc_fixed=$?
[ "$rc_fixed" -ne 0 ] && pass "T0-49a: _emit returns non-zero when the append fails (rc=$rc_fixed)" \
  || fail "T0-49a: _emit returned 0 for a failed append — the status is still swallowed"

# MUTATION: restore `|| true` on the event helper (the exact pre-fix line).
MUT="$SANDBOX/lib-records.MUTATED-emit.sh"
cp "$C40/scripts/lib-records.sh" "$MUT"
python3 - "$MUT" <<'PY'
import re, sys
p = sys.argv[1]
s = open(p).read()
start = s.index("_emit() {")
end = s.index("\n}\n", start) + 3
s = s[:start] + '_emit() { bash "$EVENTS" pr_event "$1" "$2" >/dev/null 2>&1 || true; }\n' + s[end:]
open(p, "w").write(s)
PY
rc_mut=0
MASTER_FILES_DIR="$SB1" bash -c '. "$1"; _emit query "{\"t\":1}"' _ "$MUT" >/dev/null 2>&1 || rc_mut=$?
[ "$rc_mut" -eq 0 ] && pass "T0-49a MUTATION: with '|| true' restored the same failed append returns 0 — the assertion above is discriminating" \
  || fail "T0-49a MUTATION: the pre-fix helper also returned non-zero — the mutation harness is broken"

echo ""
echo "--- T0-49b: skill 40 query() returns no record when the audit append fails ---"
HOOK="$SANDBOX/hook-a.sh"; _mk_hook "$HOOK" "OWNER-A"
OUT_BAD="$(_driver "$C40/scripts/lib-records.sh" "$SB1" "123 Main St, Springfield IL" "$HOOK" 2>/dev/null)"; rc_bad=$?
if [ "$rc_bad" -ne 0 ] && printf '%s' "$OUT_BAD" | jq -e '.blocked == true and .available == false' >/dev/null 2>&1; then
  pass "T0-49b: an unwritable audit log yields a non-zero, blocked, available:false result (rc=$rc_bad)"
else
  fail "T0-49b: rc=$rc_bad output=$OUT_BAD (expected non-zero + blocked/available:false)"
fi
if find "$SB1/public-records-cache" -name 'v2-*.json' 2>/dev/null | read -r _; then
  fail "T0-49b: a cache entry was PUBLISHED even though the audit append failed"
else
  pass "T0-49b: no cache entry was published (the staged write was discarded)"
fi

echo ""
echo "--- T0-49c: the healthy path still succeeds (anti-false-positive) ---"
SB2="$SANDBOX/mfd-ok"; mkdir -p "$SB2"
OUT_OK="$(_driver "$C40/scripts/lib-records.sh" "$SB2" "123 Main St, Springfield IL" "$HOOK" 2>/dev/null)"; rc_ok=$?
if [ "$rc_ok" -eq 0 ] && printf '%s' "$OUT_OK" | jq -e '.available == true and .owner == "OWNER-A"' >/dev/null 2>&1; then
  pass "T0-49c: a writable audit log still returns the attributed record (rc=0)"
else
  fail "T0-49c: the healthy path regressed — rc=$rc_ok output=$OUT_OK"
fi
if jq -e -s 'map(select(.event=="query")) | length > 0' < "$SB2/public-records-queries.jsonl" >/dev/null 2>&1; then
  pass "T0-49c: the query event was appended to the audit log"
else
  fail "T0-49c: no query event in the audit log"
fi

# ===========================================================================
# T1-05 — the cache key carries the query identity
# ===========================================================================
echo ""
echo "--- T1-05: a different query in the same county is a MISS, not a hit ---"
SB3="$SANDBOX/mfd-cache"; mkdir -p "$SB3"
_driver "$C40/scripts/lib-records.sh" "$SB3" "123 Main St, Springfield IL" "$HOOK" >/dev/null 2>&1
# Second query: a DIFFERENT address, same target/county/record type, and NO
# retrieval hook. Anything it returns can only have come from the cache.
OUT2="$(_driver "$C40/scripts/lib-records.sh" "$SB3" "987 Other Ave, Springfield IL" none 2>/dev/null)"
if printf '%s' "$OUT2" | jq -e '.cache_hit == true' >/dev/null 2>&1; then
  fail "T1-05: the second address was served the FIRST address's cached record: $OUT2"
elif printf '%s' "$OUT2" | jq -e '(.owner // empty) == "OWNER-A"' >/dev/null 2>&1; then
  fail "T1-05: the second address received the first address's record content: $OUT2"
else
  pass "T1-05: a different address is a cache MISS (honest available:false handoff)"
fi
# The SAME query must still hit (a key that never hits is not a cache).
OUT3="$(_driver "$C40/scripts/lib-records.sh" "$SB3" "123 MAIN ST,  Springfield  IL" none 2>/dev/null)"
if printf '%s' "$OUT3" | jq -e '.cache_hit == true and .owner == "OWNER-A"' >/dev/null 2>&1; then
  pass "T1-05: the same query (case/whitespace variant) still hits the cache"
else
  fail "T1-05: the same query no longer hits the cache — the key is unstable: $OUT3"
fi

# MUTATION, each side SEPARATELY. The writer and the reader AGREEING is the
# defect, so a mutation applied to both at once would prove nothing. Dropping
# the query from ONE side alone must break the cache-identity property this
# suite asserts — either a different address starts hitting, or the same query
# stops hitting. Both outcomes turn the assertions above red.
for SIDE in writer reader; do
  MUTC="$SANDBOX/lib-records.MUTATED-$SIDE.sh"
  cp "$C40/scripts/lib-records.sh" "$MUTC"
  python3 - "$MUTC" "$SIDE" <<'MUTKEY'
import sys
p, side = sys.argv[1], sys.argv[2]
lines = open(p).read().split("\n")
marker = "# writer side of the shared key" if side == "writer" else "# reader side of the shared key"
hit = False
for i, l in enumerate(lines):
    if marker in l:
        lines[i] = l.replace('"$q")', '"")')
        hit = True
assert hit, "mutation marker not found for " + side
open(p, "w").write("\n".join(lines))
MUTKEY
  SBM="$SANDBOX/mfd-mut-$SIDE"; mkdir -p "$SBM"
  _driver "$MUTC" "$SBM" "123 Main St, Springfield IL" "$HOOK" >/dev/null 2>&1
  OUT_DIFF="$(_driver "$MUTC" "$SBM" "987 Other Ave, Springfield IL" none 2>/dev/null)"
  OUT_SAME="$(_driver "$MUTC" "$SBM" "123 Main St, Springfield IL" none 2>/dev/null)"
  diff_hits=no; same_hits=no
  printf '%s' "$OUT_DIFF" | jq -e '.cache_hit == true' >/dev/null 2>&1 && diff_hits=yes
  printf '%s' "$OUT_SAME" | jq -e '.cache_hit == true' >/dev/null 2>&1 && same_hits=yes
  if [ "$diff_hits" = "yes" ] || [ "$same_hits" != "yes" ]; then
    pass "T1-05 MUTATION ($SIDE): dropping the query from the $SIDE side alone breaks the cache-identity property (different-address hit=$diff_hits, same-query hit=$same_hits) — the assertions above are discriminating"
  else
    fail "T1-05 MUTATION ($SIDE): the property still held with the $SIDE side mutated — the cache-key assertions are not discriminating"
  fi
done

# ===========================================================================
# T2-33 — the rate limiter measures the request boundary
# ===========================================================================
echo ""
echo "--- T2-33: three consecutive requests are each spaced by the interval ---"
SB4="$SANDBOX/mfd-rate"; mkdir -p "$SB4"
INTERVAL=2
_now() { python3 -c 'import time; print("%.3f" % time.time())'; }
prev=""; spacing_ok=1; observed=""
for i in 1 2 3; do
  MASTER_FILES_DIR="$SB4" PR_PER_TARGET_MIN_INTERVAL_S=$INTERVAL \
    bash "$C40/scripts/lib-cost-cap.sh" rate_wait rate-target >/dev/null 2>&1
  now="$(_now)"
  if [ -n "$prev" ]; then
    gap="$(awk -v a="$prev" -v b="$now" 'BEGIN{printf "%.3f", b-a}')"
    observed="$observed ${gap}s"
    awk -v g="$gap" -v i="$INTERVAL" 'BEGIN{exit !(g >= i - 0.01)}' || spacing_ok=0
  fi
  prev="$now"
done
[ "$spacing_ok" -eq 1 ] && pass "T2-33: observed spacing$observed, every gap >= ${INTERVAL}s measured at the request boundary" \
  || fail "T2-33: observed spacing$observed — a request landed inside the configured interval"

# MUTATION: stamp the timestamp where it used to be stamped (before the sleep)
# and let the caller do the sleeping — the exact pre-fix shape.
MUTR="$SANDBOX/lib-cost-cap.MUTATED-rate.sh"
cp "$C40/scripts/lib-cost-cap.sh" "$MUTR"
python3 - "$MUTR" <<'PY'
import sys
p = sys.argv[1]
s = open(p).read()
start = s.index("rate_wait() {")
end = s.index("\nif [ \"${BASH_SOURCE[0]:-}\"", start)
prefix_impl = '''rate_wait() {
  local target="${1:-default}" lf last now diff d
  d="$(_cache_dir)" || return 1
  lf="$d/.last-fetch-$(printf '%s' "$target" | tr -c 'A-Za-z0-9_-' '_')"
  mkdir -p "$d" 2>/dev/null || true
  now="$(date +%s)"
  last=0; [ -f "$lf" ] && last="$(tr -d '[:space:]' < "$lf" 2>/dev/null || echo 0)"
  diff=$(( now - ${last:-0} ))
  if [ "$diff" -lt "$PR_PER_TARGET_MIN_INTERVAL_S" ] && [ "${last:-0}" -gt 0 ]; then
    local wait=$(( PR_PER_TARGET_MIN_INTERVAL_S - diff ))
    echo "$wait"
  else
    echo "0"
  fi
  printf '%s\\n' "$(date +%s)" > "$lf"
}
'''
open(p, "w").write(s[:start] + prefix_impl + s[end:])
PY
SB5="$SANDBOX/mfd-rate-mut"; mkdir -p "$SB5"
prev=""; mut_inside=0; mut_observed=""
for i in 1 2 3; do
  w="$(MASTER_FILES_DIR="$SB5" PR_PER_TARGET_MIN_INTERVAL_S=$INTERVAL bash "$MUTR" rate_wait rate-target 2>/dev/null)"
  [ "${w:-0}" -gt 0 ] 2>/dev/null && sleep "$w"     # the pre-fix caller slept
  now="$(_now)"
  if [ -n "$prev" ]; then
    gap="$(awk -v a="$prev" -v b="$now" 'BEGIN{printf "%.3f", b-a}')"
    mut_observed="$mut_observed ${gap}s"
    awk -v g="$gap" -v i="$INTERVAL" 'BEGIN{exit !(g >= i - 0.01)}' || mut_inside=1
  fi
  prev="$now"
done
[ "$mut_inside" -eq 1 ] && pass "T2-33 MUTATION: the pre-fix stamp order lets a request land inside the interval (observed$mut_observed) — the assertion above is discriminating" \
  || fail "T2-33 MUTATION: the pre-fix shape also held spacing (observed$mut_observed) — the mutation harness is broken"

# ===========================================================================
# T0-53 / T2-34 — the target validator
# ===========================================================================
echo ""
echo "--- T0-53: an UNEDITED tier-3 template is rejected ---"
V="$SANDBOX/validate"; mkdir -p "$V"
cp "$C40/templates/tier3-config.template.json" "$V/unedited.json"
bash "$C40/scripts/05-validate-target.sh" --tier3 "$V/unedited.json" > "$V/unedited.log" 2>&1
rc_unedited=$?
[ "$rc_unedited" -ne 0 ] && pass "T0-53: the unedited template FAILS validation (exit $rc_unedited)" \
  || fail "T0-53: the unedited template was certified live-safe (exit 0)"
grep -q "VALIDATION PASS" "$V/unedited.log" \
  && fail "T0-53: the unedited template still printed VALIDATION PASS" \
  || pass "T0-53: no VALIDATION PASS marker was printed for the unedited template"

echo ""
echo "--- T0-53/T2-34: a filled config with a real results page passes and attests ---"
cat > "$V/good.json" <<'CFG'
{"tier":"tier3","slug":"mock-county-xx","county_fips":"99999","platform":"custom",
 "portal_url":"https://records.example.invalid","search_path":"/search",
 "tos_url":"https://records.example.invalid/terms",
 "record_types":["ownership"],
 "selectors":{"result_row":"tr.result-row","owner":"td.owner"},
 "validated":false}
CFG
cat > "$V/results.html" <<'HTML'
<html><body><table id="results"><tbody>
<tr class="result-row"><td class="owner">REDACTED</td></tr>
<tr class="result-row"><td class="owner">REDACTED</td></tr>
</tbody></table></body></html>
HTML
bash "$C40/scripts/05-validate-target.sh" --tier3 "$V/good.json" --fixture "$V/results.html" > "$V/good.log" 2>&1
rc_good=$?
[ "$rc_good" -eq 0 ] && pass "T0-53: a filled config whose selectors match a real page PASSES (exit 0)" \
  || { fail "T0-53: a correct config was rejected (exit $rc_good)"; sed 's/^/      /' "$V/good.log"; }
if jq -e '.validated == true and (.validation.fields_sha256 | type == "string") and (.validation.validated_at | type == "string")' "$V/good.json" >/dev/null 2>&1; then
  pass "T2-34: the pass wrote a content-bound attestation (validated + hash + timestamp)"
else
  fail "T2-34: no attestation was written by a passing validation"
fi
ATT="$(jq -r '.validation.fields_sha256' "$V/good.json")"
NOW="$(bash "$C40/scripts/lib-records.sh" config_fields_hash "$V/good.json")"
[ -n "$ATT" ] && [ "$ATT" = "$NOW" ] && pass "T2-34: the attestation hash matches the configuration that passed" \
  || fail "T2-34: attestation hash $ATT does not bind to the configuration ($NOW)"
bash "$C40/scripts/lib-records.sh" config_servable "$V/good.json" >/dev/null 2>&1 \
  && pass "T2-34: the attested config IS servable to the router" \
  || fail "T2-34: an attested, validated config is not servable"
jq '.selectors.owner = "td.SOMETHING-ELSE"' "$V/good.json" > "$V/tampered.json"
bash "$C40/scripts/lib-records.sh" config_servable "$V/tampered.json" >/dev/null 2>&1 \
  && fail "T2-34: a config edited AFTER validation is still servable — the attestation binds to nothing" \
  || pass "T2-34: editing the config after validation invalidates the attestation (not servable)"

echo ""
echo "--- T0-53: a selector that matches nothing is a failure, not a warning ---"
jq '.selectors.owner = "td.no-such-class" | .validated = false | del(.validation)' "$V/good.json" > "$V/nomatch.json"
bash "$C40/scripts/05-validate-target.sh" --tier3 "$V/nomatch.json" --fixture "$V/results.html" > "$V/nomatch.log" 2>&1
[ $? -ne 0 ] && pass "T0-53: a non-matching selector FAILS validation" \
  || fail "T0-53: a selector that matches nothing was accepted"
echo "--- T0-53: a selector that cannot be evaluated is a failure, never a skip ---"
jq '.selectors.owner = "td:first-child" | .validated = false | del(.validation)' "$V/good.json" > "$V/unsup.json"
bash "$C40/scripts/05-validate-target.sh" --tier3 "$V/unsup.json" --fixture "$V/results.html" > "$V/unsup.log" 2>&1
if [ $? -ne 0 ] && grep -q "UNSUPPORTED" "$V/unsup.log"; then
  pass "T0-53: an unevaluable selector is reported and FAILS (never silently passed)"
else
  fail "T0-53: an unevaluable selector did not fail visibly"
fi
echo "--- T0-53: no results page at all is INCOMPLETE, not a pass ---"
jq '.validated = false | del(.validation)' "$V/good.json" > "$V/nofixture.json"
bash "$C40/scripts/05-validate-target.sh" --tier3 "$V/nofixture.json" > "$V/nofixture.log" 2>&1
if [ $? -ne 0 ] && grep -q "INCOMPLETE" "$V/nofixture.log"; then
  pass "T0-53: with no results page the validator reports INCOMPLETE and exits non-zero"
else
  fail "T0-53: a validation that could not evaluate its selectors did not report that visibly"
fi

# ===========================================================================
# T0-54 — the compliance gate cannot pass without its dependency
# ===========================================================================
echo ""
echo "--- T0-54: qc-compliance.sh with jq absent from PATH ---"
MINBIN="$SANDBOX/minbin"; mkdir -p "$MINBIN"
for c in dirname basename mktemp rm date; do
  src="$(command -v "$c" 2>/dev/null || true)"
  [ -n "$src" ] && ln -sf "$src" "$MINBIN/$c"
done
env -i HOME="$HOME" PATH="$MINBIN" bash "$C40/scripts/qc-compliance.sh" > "$SANDBOX/nojq.log" 2>&1
rc_nojq=$?
if [ "$rc_nojq" -ne 0 ] && ! grep -q "RESULT: PASS" "$SANDBOX/nojq.log"; then
  pass "T0-54: the compliance gate exits non-zero with NO PASS marker when jq is missing (exit $rc_nojq)"
else
  fail "T0-54: exit=$rc_nojq and the log still contains a PASS marker:"; sed 's/^/      /' "$SANDBOX/nojq.log"
fi
echo "--- T0-54: with jq present the gate still passes (anti-false-positive) ---"
bash "$C40/scripts/qc-compliance.sh" > "$SANDBOX/withjq.log" 2>&1 \
  && pass "T0-54: the compliance gate still exits 0 on a healthy box" \
  || { fail "T0-54: the compliance gate regressed on a healthy box"; sed 's/^/      /' "$SANDBOX/withjq.log"; }

# ===========================================================================
# T0-55 — the no-fabrication assertion tests the VALUE
# ===========================================================================
echo ""
echo "--- T0-55: a truthy 'resolved' on an unresolvable query must go red ---"
STUB='{"resolved":true,"source":"census","county_fips":"17167","state":"17","county_name":"Sangamon"}'
bash "$C40/scripts/qc-no-fabrication.sh" assert_honest_gap "$STUB" >/dev/null 2>&1 \
  && fail "T0-55: the predicate ACCEPTED a fabricated resolution" \
  || pass "T0-55: the predicate REJECTS a fabricated resolution"
bash "$C40/scripts/qc-no-fabrication.sh" assert_honest_gap '{"resolved":false,"reason":"could not resolve"}' >/dev/null 2>&1 \
  && pass "T0-55: the predicate accepts a real honest gap (anti-false-positive)" \
  || fail "T0-55: the predicate rejected a genuine honest gap"
# MUTATION: restore the presence-only predicate.
MUTF="$SANDBOX/qc-no-fabrication.MUTATED.sh"
cp "$C40/scripts/qc-no-fabrication.sh" "$MUTF"
python3 - "$MUTF" <<'MUTPRED'
import re, sys
p = sys.argv[1]
s = open(p).read()
# Restore the pre-fix predicate: PRESENCE of the resolved field only. The
# ".resolved == false" assertion and the invented-county/state assertion are
# both removed, which is exactly what the gate looked like before the fix.
start = s.index("  printf '%s' \"$json\" | jq -e '.resolved == false'")
end = s.index("  return 0\n}", start)
open(p, "w").write(s[:start] + s[end:])
MUTPRED
bash "$MUTF" assert_honest_gap "$STUB" >/dev/null 2>&1 \
  && pass "T0-55 MUTATION: the presence-only predicate accepts the fabricated resolution — the assertion above is discriminating" \
  || fail "T0-55 MUTATION: the mutated predicate also rejected it — the mutation harness is broken"

# ===========================================================================
# T0-51 — a failed extension copy must not emit an installed event
# ===========================================================================
echo ""
echo "--- T0-51: skill 39 extension install with an unusable destination ---"
EXT="$SANDBOX/ext"; mkdir -p "$EXT/skills/38-conversational-ai-system/protocols" "$EXT/mfd"
# Plant a DIRECTORY where the extension file must land: the copy cannot produce
# the artifact, under any uid.
mkdir -p "$EXT/skills/38-conversational-ai-system/protocols/sales-best-practices-real-estate-extension.md"
OPENCLAW_SKILLS_DIR="$EXT/skills" MASTER_FILES_DIR="$EXT/mfd" HOME="$EXT" \
  bash "$C39/scripts/05-install-sales-brain-extension.sh" > "$EXT/install.log" 2>&1
rc_inst=$?
[ "$rc_inst" -ne 0 ] && pass "T0-51: the install exits non-zero when the extension cannot be placed (exit $rc_inst)" \
  || fail "T0-51: the install exited 0 with the extension never in place"
if [ -f "$EXT/mfd/real-estate-events.jsonl" ] && jq -e -s 'map(select(.event=="sales_brain_extension_installed")) | length > 0' < "$EXT/mfd/real-estate-events.jsonl" >/dev/null 2>&1; then
  fail "T0-51: an installed event was written for an extension that is not there"
else
  pass "T0-51: NO installed event was written"
fi
grep -q "Done. Re-run is idempotent." "$EXT/install.log" \
  && fail "T0-51: the Done banner still printed on a failed install" \
  || pass "T0-51: no Done banner on a failed install"

echo "--- T0-51: a healthy install still succeeds (anti-false-positive) ---"
EXT2="$SANDBOX/ext-ok"; mkdir -p "$EXT2/skills/38-conversational-ai-system/protocols" "$EXT2/mfd"
OPENCLAW_SKILLS_DIR="$EXT2/skills" MASTER_FILES_DIR="$EXT2/mfd" HOME="$EXT2" \
  bash "$C39/scripts/05-install-sales-brain-extension.sh" > "$EXT2/install.log" 2>&1
rc_ok2=$?
if [ "$rc_ok2" -eq 0 ] && cmp -s "$C39/references/sales-brain-real-estate-extension.md" \
     "$EXT2/skills/38-conversational-ai-system/protocols/sales-best-practices-real-estate-extension.md"; then
  pass "T0-51: a healthy install exits 0 and the extension is byte-identical on disk"
else
  fail "T0-51: the healthy install regressed (exit $rc_ok2)"; sed 's/^/      /' "$EXT2/install.log"
fi

# ===========================================================================
# T0-49 (skill 39) — property-lookup.sh must not announce an append that failed
# ===========================================================================
echo ""
echo "--- T0-49d: skill 39 property-lookup with an unwritable event log ---"
PL="$SANDBOX/pl"; mkdir -p "$PL/real-estate-events.jsonl"
MASTER_FILES_DIR="$PL" HOME="$PL" bash "$C39/scripts/property-lookup.sh" \
  --address "123 Main St, Springfield, IL 62701" --want property_lookup > "$PL/out.log" 2>&1
rc_pl=$?
[ "$rc_pl" -ne 0 ] && pass "T0-49d: property-lookup exits non-zero when the F52 append fails (exit $rc_pl)" \
  || fail "T0-49d: property-lookup exited 0 with the event never appended"
grep -q "F52 event appended" "$PL/out.log" \
  && fail "T0-49d: it still printed 'F52 event appended' for an append that failed" \
  || pass "T0-49d: the appended-message is printed only in the success branch"

echo "--- T0-49e: property-lookup still logs and succeeds on a healthy box ---"
PL2="$SANDBOX/pl-ok"; mkdir -p "$PL2"
MASTER_FILES_DIR="$PL2" HOME="$PL2" bash "$C39/scripts/property-lookup.sh" \
  --address "123 Main St, Springfield, IL 62701" --want property_lookup > "$PL2/out.log" 2>&1
rc_pl2=$?
if [ "$rc_pl2" -eq 0 ] && jq -e -s 'map(select(.event=="property_lookup")) | length > 0' < "$PL2/real-estate-events.jsonl" >/dev/null 2>&1; then
  pass "T0-49e: the healthy path exits 0 and appends exactly the F52 property_lookup event"
else
  fail "T0-49e: the healthy path regressed (exit $rc_pl2)"; sed 's/^/      /' "$PL2/out.log"
fi

# ---------------------------------------------------------------------------
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
  echo "FAIL: $FAIL check(s) failed — CI guard triggered"
  exit 1
fi
echo "PASS: all records-pipeline fail-closed checks pass"
exit 0
