#!/usr/bin/env bash
# tests/unit/podbean-publish-provisioning.test.sh
#
# S58-U15 — install.sh provisioning injection for the Podbean SERVER-SIDE
# PUBLISH-PROXY pair (PODBEAN_PUBLISH_WEBHOOK_URL / PODBEAN_PUBLISH_TOKEN) and
# the per-box podcast client identity (PODCAST_CLIENT_LAST_NAME / _EMAIL /
# _FIRST_NAME), reusing install.sh's existing broker-pair injection mechanism
# (inject_shared_operator_secrets) and credential checklist
# (discover_all_credentials).
#
# This test extracts the REAL function bodies out of install.sh BY NAME (an
# awk scan for the exact `<name>() {` / `}` markers, not a fixed line range,
# so the test survives future edits elsewhere in the 8000-line file) and
# sources them behind hermetic stubs for the logging/discovery helpers they
# call (success/warn/note/step/search_env_var*). It never sources the whole
# install.sh (which is a top-to-bottom script, not a library, and would run
# the entire installer as a side effect).
#
# Proves, against the REAL extracted code:
#   1. publish-proxy pair: written when BOTH set; refused (not half-seeded)
#      when only one is set — mirrors the broker-pair both-or-neither guard.
#   2. identity pair: written when BOTH set with a plausible email; refused
#      when only one is set, or when the email is malformed (whitespace / no
#      "@x.y" shape).
#   3. first name is independent (no pairing requirement — display/email
#      only, never authorization).
#   4. regression: the pre-existing broker pair injection is unaffected by
#      this unit's new code (no accidental short-circuit / brace mismatch).
#   5. the credential checklist (discover_all_credentials) reports all five
#      new canonical names by their box-local names, found/missing correctly.
#   6. MUTATION PROOF: each guard is proven load-bearing by neutering it in a
#      text-mutated copy of the extracted source and showing the
#      corresponding negative assertion flips to the wrong (unsafe) outcome —
#      a guard nothing tests is decoration.
#
# Exit 0 = all checks pass. Exit 1 = one or more failed.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INSTALL_SH="$REPO_ROOT/install.sh"

PASS=0
FAIL=0
pass() { printf '  PASS: %s\n' "$1"; PASS=$((PASS + 1)); }
fail() { printf '  FAIL: %s\n' "$1"; FAIL=$((FAIL + 1)); }

echo "=== podbean-publish-provisioning.test.sh ==="

[ -f "$INSTALL_SH" ] || { echo "FAIL: install.sh not found at $INSTALL_SH"; exit 1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# --- extraction (by function name, not line number) -------------------------
extract_fn() {
    # $1 = function name; the function must start at column 0 as
    # "<name>() {" and close with a bare "}" at column 0 (install.sh's own
    # top-level function convention, verified by this test's own PASS/FAIL —
    # if the convention ever changes, extraction returns empty and the test
    # fails loudly at the guard below rather than silently testing nothing).
    awk -v fn="$1() {" '
        $0 == fn { grab = 1 }
        grab { print }
        grab && /^}/ { grab = 0 }
    ' "$INSTALL_SH"
}

INJECT_SRC="$(extract_fn "inject_shared_operator_secrets")"
DISCOVER_SRC="$(extract_fn "discover_all_credentials")"

if [ -z "$INJECT_SRC" ]; then
    echo "FAIL: could not extract inject_shared_operator_secrets() from install.sh (function renamed/moved?)"
    exit 1
fi
if [ -z "$DISCOVER_SRC" ]; then
    echo "FAIL: could not extract discover_all_credentials() from install.sh (function renamed/moved?)"
    exit 1
fi

# Sanity: the extracted source must actually mention the S58-U15 vars, else
# this test would hermetically pass against code that was never touched.
case "$INJECT_SRC" in
    *PODBEAN_PUBLISH_WEBHOOK_URL*PODCAST_CLIENT_LAST_NAME*) : ;;
    *) echo "FAIL: extracted inject_shared_operator_secrets() does not mention the S58-U15 vars — extraction or the unit itself is broken"; exit 1 ;;
esac
case "$DISCOVER_SRC" in
    *PODBEAN_PUBLISH_WEBHOOK_URL*PODCAST_CLIENT_EMAIL*) : ;;
    *) echo "FAIL: extracted discover_all_credentials() does not mention the S58-U15 vars — extraction or the unit itself is broken"; exit 1 ;;
esac

STUBS='
# Hermetic stubs for install.sh helpers this unit calls but does not define.
success() { printf "SUCCESS: %s\n" "$*"; }
warn()    { printf "WARN: %s\n" "$*"; }
note()    { printf "NOTE: %s\n" "$*"; }
step()    { printf "STEP: %s\n" "$*"; }
CREDS_FOUND_LIST=""
search_env_var_mac() { return 1; }
search_env_var() { eval "printf %s \"\${$1:-}\""; }
'

FIXTURE="$WORK/fixture.sh"
{
    printf '%s\n' "$STUBS"
    printf '%s\n' "$INJECT_SRC"
    printf '%s\n' "$DISCOVER_SRC"
} > "$FIXTURE"
bash -n "$FIXTURE" || { echo "FAIL: extracted fixture is not valid bash"; exit 1; }

# --- helpers ------------------------------------------------------------- #
# Run inject_shared_operator_secrets in a hermetic subshell against a given
# fixture file (so mutation runs can pass a neutered copy) and a given set of
# NAME=VALUE env assignments. Captures secrets/.env content + stdout.
ALL_KNOWN_VARS="OPENCLAW_PODBEAN_PUBLISH_URL OPENCLAW_PODBEAN_PUBLISH_TOKEN \
OPENCLAW_PODCAST_CLIENT_LAST_NAME OPENCLAW_PODCAST_CLIENT_EMAIL OPENCLAW_PODCAST_CLIENT_FIRST_NAME \
OPENCLAW_PODBEAN_BROKER_URL OPENCLAW_PODBEAN_BROKER_TOKEN \
OPENCLAW_PODBEAN_CLIENT_ID OPENCLAW_PODBEAN_CLIENT_SECRET \
RESCUE_RANGERS_WEBHOOK_URL RESCUE_RANGERS_WEBHOOK_SECRET RESCUE_RANGERS_HELP_CHAT_ID"

run_inject() {
    # $1 = fixture path, $2 = secrets file path, remaining = NAME=VALUE pairs
    local fixture="$1" secrets="$2"
    shift 2
    (
        # shellcheck disable=SC2086
        unset $ALL_KNOWN_VARS 2>/dev/null || true
        for kv in "$@"; do
            export "$kv"
        done
        export OC_SECRETS_ENV="$secrets"
        export OC_JSON="$WORK/nonexistent-openclaw.json"
        : > "$secrets"
        # shellcheck source=/dev/null
        source "$fixture"
        inject_shared_operator_secrets
    )
}

file_has_line() { grep -qxF "$2" "$1" 2>/dev/null; }

# =========================================================================
# (1) PUBLISH-PROXY PAIR
# =========================================================================
echo ""
echo "--- (1) publish-proxy pair ---"

S1="$WORK/secrets1.env"
OUT1="$(run_inject "$FIXTURE" "$S1" \
    "OPENCLAW_PODBEAN_PUBLISH_URL=https://main.example.test/webhook/podbean-publish" \
    "OPENCLAW_PODBEAN_PUBLISH_TOKEN=unit-test-token-aaa111")"
file_has_line "$S1" "PODBEAN_PUBLISH_WEBHOOK_URL=https://main.example.test/webhook/podbean-publish" \
    && pass "1a: both set -> PODBEAN_PUBLISH_WEBHOOK_URL written" \
    || fail "1a: PODBEAN_PUBLISH_WEBHOOK_URL missing from secrets/.env"
file_has_line "$S1" "PODBEAN_PUBLISH_TOKEN=unit-test-token-aaa111" \
    && pass "1b: both set -> PODBEAN_PUBLISH_TOKEN written" \
    || fail "1b: PODBEAN_PUBLISH_TOKEN missing from secrets/.env"
case "$OUT1" in
    *"SUCCESS: Podbean publish-proxy pair injected"*) pass "1c: success message emitted" ;;
    *) fail "1c: no success message for the publish-proxy pair (out: $OUT1)" ;;
esac

S2="$WORK/secrets2.env"
OUT2="$(run_inject "$FIXTURE" "$S2" "OPENCLAW_PODBEAN_PUBLISH_URL=https://main.example.test/webhook/podbean-publish")"
if grep -q 'PODBEAN_PUBLISH_WEBHOOK_URL' "$S2" 2>/dev/null; then
    fail "1d: URL-only -> PODBEAN_PUBLISH_WEBHOOK_URL was WRONGLY written (half-seeded)"
else
    pass "1d: URL-only -> nothing written (refused, not half-seeded)"
fi
case "$OUT2" in
    *"WARN: Only one of OPENCLAW_PODBEAN_PUBLISH_URL"*) pass "1e: URL-only warns" ;;
    *) fail "1e: URL-only did not warn (out: $OUT2)" ;;
esac

S3="$WORK/secrets3.env"
OUT3="$(run_inject "$FIXTURE" "$S3" "OPENCLAW_PODBEAN_PUBLISH_TOKEN=unit-test-token-aaa111")"
if grep -q 'PODBEAN_PUBLISH_TOKEN' "$S3" 2>/dev/null; then
    fail "1f: TOKEN-only -> PODBEAN_PUBLISH_TOKEN was WRONGLY written (half-seeded)"
else
    pass "1f: TOKEN-only -> nothing written (refused, not half-seeded)"
fi

# =========================================================================
# (2) IDENTITY PAIR
# =========================================================================
echo ""
echo "--- (2) podcast client identity pair ---"

S4="$WORK/secrets4.env"
OUT4="$(run_inject "$FIXTURE" "$S4" \
    "OPENCLAW_PODCAST_CLIENT_LAST_NAME=Testerson" \
    "OPENCLAW_PODCAST_CLIENT_EMAIL=unit-test@example.test")"
file_has_line "$S4" "PODCAST_CLIENT_LAST_NAME=Testerson" \
    && pass "2a: both set (valid email) -> PODCAST_CLIENT_LAST_NAME written" \
    || fail "2a: PODCAST_CLIENT_LAST_NAME missing from secrets/.env"
file_has_line "$S4" "PODCAST_CLIENT_EMAIL=unit-test@example.test" \
    && pass "2b: both set (valid email) -> PODCAST_CLIENT_EMAIL written" \
    || fail "2b: PODCAST_CLIENT_EMAIL missing from secrets/.env"

S5="$WORK/secrets5.env"
OUT5="$(run_inject "$FIXTURE" "$S5" "OPENCLAW_PODCAST_CLIENT_LAST_NAME=Testerson")"
if grep -q 'PODCAST_CLIENT_LAST_NAME' "$S5" 2>/dev/null; then
    fail "2c: last-name-only -> PODCAST_CLIENT_LAST_NAME was WRONGLY written (half-seeded)"
else
    pass "2c: last-name-only -> nothing written (refused, not half-seeded)"
fi

S6="$WORK/secrets6.env"
OUT6="$(run_inject "$FIXTURE" "$S6" \
    "OPENCLAW_PODCAST_CLIENT_LAST_NAME=Testerson" \
    "OPENCLAW_PODCAST_CLIENT_EMAIL=not-an-email")"
if grep -q 'PODCAST_CLIENT_LAST_NAME\|PODCAST_CLIENT_EMAIL' "$S6" 2>/dev/null; then
    fail "2d: malformed email (no @x.y) -> identity was WRONGLY written"
else
    pass "2d: malformed email (no @x.y) -> refused"
fi
case "$OUT6" in
    *"WARN: OPENCLAW_PODCAST_CLIENT_EMAIL does not look like an email"*) pass "2e: malformed email warns" ;;
    *) fail "2e: malformed email did not warn (out: $OUT6)" ;;
esac

S7="$WORK/secrets7.env"
OUT7="$(run_inject "$FIXTURE" "$S7" \
    "OPENCLAW_PODCAST_CLIENT_LAST_NAME=Testerson" \
    "OPENCLAW_PODCAST_CLIENT_EMAIL=bad address@example.test")"
if grep -q 'PODCAST_CLIENT_LAST_NAME\|PODCAST_CLIENT_EMAIL' "$S7" 2>/dev/null; then
    fail "2f: whitespace in email -> identity was WRONGLY written"
else
    pass "2f: whitespace in email -> refused"
fi

# =========================================================================
# (3) FIRST NAME — independent, no pairing requirement
# =========================================================================
echo ""
echo "--- (3) first name (display only, no pairing) ---"

S8="$WORK/secrets8.env"
run_inject "$FIXTURE" "$S8" "OPENCLAW_PODCAST_CLIENT_FIRST_NAME=Unit" >/dev/null
file_has_line "$S8" "PODCAST_CLIENT_FIRST_NAME=Unit" \
    && pass "3a: first name alone -> written (no last name / email required)" \
    || fail "3a: PODCAST_CLIENT_FIRST_NAME missing when set alone"

# =========================================================================
# (4) REGRESSION — pre-existing broker pair unaffected
# =========================================================================
echo ""
echo "--- (4) regression: broker pair still works, publish vars absent when unset ---"

S9="$WORK/secrets9.env"
run_inject "$FIXTURE" "$S9" \
    "OPENCLAW_PODBEAN_BROKER_URL=https://main.example.test/webhook/podbean-broker" \
    "OPENCLAW_PODBEAN_BROKER_TOKEN=unit-test-broker-token" >/dev/null
file_has_line "$S9" "PODBEAN_BROKER_WEBHOOK_URL=https://main.example.test/webhook/podbean-broker" \
    && pass "4a: broker pair still injects PODBEAN_BROKER_WEBHOOK_URL" \
    || fail "4a: broker pair regression — PODBEAN_BROKER_WEBHOOK_URL missing"
file_has_line "$S9" "PODBEAN_BROKER_TOKEN=unit-test-broker-token" \
    && pass "4b: broker pair still injects PODBEAN_BROKER_TOKEN" \
    || fail "4b: broker pair regression — PODBEAN_BROKER_TOKEN missing"
if grep -q 'PODBEAN_PUBLISH_\|PODCAST_CLIENT_' "$S9" 2>/dev/null; then
    fail "4c: broker-only run wrongly wrote publish-proxy/identity keys"
else
    pass "4c: broker-only run wrote no publish-proxy/identity keys"
fi

S10="$WORK/secrets10.env"
run_inject "$FIXTURE" "$S10" >/dev/null
if [ -s "$S10" ] && grep -q 'PODBEAN_\|PODCAST_CLIENT_' "$S10" 2>/dev/null; then
    fail "4d: nothing set -> some Podbean/podcast key was wrongly written"
else
    pass "4d: nothing set -> no Podbean/podcast key written, no crash"
fi

# =========================================================================
# (5) CREDENTIAL CHECKLIST — discover_all_credentials reports the 5 new names
# =========================================================================
echo ""
echo "--- (5) credential checklist (discover_all_credentials) ---"

OUT11="$(
    (
        # shellcheck disable=SC2086
        unset $ALL_KNOWN_VARS 2>/dev/null || true
        export OPENCLAW_PODBEAN_PUBLISH_URL="https://main.example.test/webhook/podbean-publish"
        export OPENCLAW_PODBEAN_PUBLISH_TOKEN="unit-test-token-aaa111"
        # discover_all_credentials resolves box-LOCAL names via search_env_var,
        # so seed those directly (mirrors what the injector above would have
        # written to secrets/.env on a real box).
        export PODBEAN_PUBLISH_WEBHOOK_URL="https://main.example.test/webhook/podbean-publish"
        export PODBEAN_PUBLISH_TOKEN="unit-test-token-aaa111"
        export PODCAST_CLIENT_LAST_NAME="Testerson"
        # PODCAST_CLIENT_EMAIL intentionally left unset for this run.
        unset MAC_ENV_FILE_LIST 2>/dev/null || true
        # shellcheck source=/dev/null
        source "$FIXTURE"
        discover_all_credentials
    )
)"
case "$OUT11" in
    *"Found PODBEAN_PUBLISH_WEBHOOK_URL"*) pass "5a: checklist reports PODBEAN_PUBLISH_WEBHOOK_URL found" ;;
    *) fail "5a: checklist did not report PODBEAN_PUBLISH_WEBHOOK_URL found (out: $OUT11)" ;;
esac
case "$OUT11" in
    *"Found PODBEAN_PUBLISH_TOKEN"*) pass "5b: checklist reports PODBEAN_PUBLISH_TOKEN found" ;;
    *) fail "5b: checklist did not report PODBEAN_PUBLISH_TOKEN found" ;;
esac
case "$OUT11" in
    *"Found PODCAST_CLIENT_LAST_NAME"*) pass "5c: checklist reports PODCAST_CLIENT_LAST_NAME found" ;;
    *) fail "5c: checklist did not report PODCAST_CLIENT_LAST_NAME found" ;;
esac
case "$OUT11" in
    *"PODCAST_CLIENT_EMAIL"*"Podcast client email"*) pass "5d: checklist lists PODCAST_CLIENT_EMAIL as not-yet-configured" ;;
    *) fail "5d: checklist did not report PODCAST_CLIENT_EMAIL as missing (out: $OUT11)" ;;
esac

# =========================================================================
# (6) MUTATION PROOF — each guard is load-bearing
# =========================================================================
echo ""
echo "--- (6) mutation proof: guards are load-bearing, not decoration ---"

# Text-mutate a copy of the extracted fixture. find/repl are passed to python
# via TEMP FILES (never interpolated into a heredoc) so arbitrary shell
# metacharacters ($, ", {, }, newlines) in the matched code round-trip byte
# for byte with no quoting hazard.
mutate_fixture() {
    local out="$1" find_text="$2" repl_text="$3"
    local findfile replfile
    findfile="$(mktemp "$WORK/mut-find.XXXXXX")"
    replfile="$(mktemp "$WORK/mut-repl.XXXXXX")"
    printf '%s' "$find_text" > "$findfile"
    printf '%s' "$repl_text" > "$replfile"
    python3 - "$FIXTURE" "$out" "$findfile" "$replfile" <<'PY'
import sys
src_path, out_path, find_path, repl_path = sys.argv[1:5]
src = open(src_path, "r", encoding="utf-8").read()
find = open(find_path, "r", encoding="utf-8").read()
repl = open(repl_path, "r", encoding="utf-8").read()
if find not in src:
    sys.stderr.write("MUTATE-FAIL: target text not found in fixture source\n")
    sys.exit(1)
src = src.replace(find, repl, 1)
open(out_path, "w", encoding="utf-8").write(src)
PY
    local rc=$?
    rm -f "$findfile" "$replfile"
    return "$rc"
}

# --- 6a: neuter the publish-proxy both-or-neither guard (&& -> ||) ----------
MUT_A="$WORK/mut-pair-guard.sh"
if mutate_fixture "$MUT_A" \
    'if [ -n "${OPENCLAW_PODBEAN_PUBLISH_URL:-}" ] && [ -n "${OPENCLAW_PODBEAN_PUBLISH_TOKEN:-}" ]; then' \
    'if [ -n "${OPENCLAW_PODBEAN_PUBLISH_URL:-}" ] || [ -n "${OPENCLAW_PODBEAN_PUBLISH_TOKEN:-}" ]; then'
then
    bash -n "$MUT_A" && pass "6a-setup: mutated fixture (both-or-neither -> either-or) is valid bash" \
        || fail "6a-setup: mutated fixture failed to parse"
    # TOKEN is exported EMPTY (declared, not merely absent) so this exercises
    # the pairing guard itself rather than an unrelated set -u crash on a
    # variable the real code never expects to reference unguarded here.
    SM1="$WORK/secrets-mut1.env"
    run_inject "$MUT_A" "$SM1" \
        "OPENCLAW_PODBEAN_PUBLISH_URL=https://main.example.test/webhook/podbean-publish" \
        "OPENCLAW_PODBEAN_PUBLISH_TOKEN=" >/dev/null
    if grep -q 'PODBEAN_PUBLISH_WEBHOOK_URL' "$SM1" 2>/dev/null; then
        pass "6a: URL-only NOW WRITES under the neutered guard — proves 1d/1e depend on the real && guard"
    else
        fail "6a: mutation did not flip the outcome — the both-or-neither guard may not be the thing 1d/1e actually tests"
    fi
else
    fail "6a-setup: could not locate the publish-proxy guard text to mutate"
fi

# --- 6b: neuter the identity email-shape guard (case pattern always matches valid branch) ---
MUT_B="$WORK/mut-email-shape.sh"
if mutate_fixture "$MUT_B" \
    '            *@*.*)
                _shared_write_env "PODCAST_CLIENT_LAST_NAME"' \
    '            *)
                _shared_write_env "PODCAST_CLIENT_LAST_NAME"'
then
    bash -n "$MUT_B" && pass "6b-setup: mutated fixture (email shape case widened to *) is valid bash" \
        || fail "6b-setup: mutated fixture failed to parse"
    SM2="$WORK/secrets-mut2.env"
    run_inject "$MUT_B" "$SM2" \
        "OPENCLAW_PODCAST_CLIENT_LAST_NAME=Testerson" \
        "OPENCLAW_PODCAST_CLIENT_EMAIL=not-an-email" >/dev/null
    if grep -q 'PODCAST_CLIENT_LAST_NAME' "$SM2" 2>/dev/null; then
        pass "6b: malformed email NOW WRITES under the neutered shape guard — proves 2d/2e depend on the real case pattern"
    else
        fail "6b: mutation did not flip the outcome — the email shape guard may not be the thing 2d/2e actually tests"
    fi
else
    fail "6b-setup: could not locate the email-shape case arm to mutate"
fi

# --- 6c: neuter the identity both-or-neither guard (&& -> ||) ---------------
MUT_C="$WORK/mut-identity-guard.sh"
if mutate_fixture "$MUT_C" \
    'if [ -n "${OPENCLAW_PODCAST_CLIENT_LAST_NAME:-}" ] && [ -n "${OPENCLAW_PODCAST_CLIENT_EMAIL:-}" ]; then' \
    'if [ -n "${OPENCLAW_PODCAST_CLIENT_LAST_NAME:-}" ] || [ -n "${OPENCLAW_PODCAST_CLIENT_EMAIL:-}" ]; then'
then
    bash -n "$MUT_C" && pass "6c-setup: mutated fixture (identity both-or-neither -> either-or) is valid bash" \
        || fail "6c-setup: mutated fixture failed to parse"
    # Scenario: last name EMPTY (declared, not merely unset — the case-shape
    # guard on email would independently block a genuinely-absent email, so an
    # unset-email scenario cannot isolate what the && pairing guard alone
    # protects). A valid, present email + an empty last name is exactly the
    # corrupted half-identity the && guard exists to refuse.
    SM3="$WORK/secrets-mut3.env"
    run_inject "$MUT_C" "$SM3" \
        "OPENCLAW_PODCAST_CLIENT_LAST_NAME=" \
        "OPENCLAW_PODCAST_CLIENT_EMAIL=unit-test@example.test" >/dev/null
    if grep -q 'PODCAST_CLIENT_EMAIL=unit-test@example.test' "$SM3" 2>/dev/null; then
        pass "6c: empty-last-name + valid email NOW WRITES a corrupted half-identity under the neutered guard — proves 2c depends on the real && guard"
    else
        fail "6c: mutation did not flip the outcome — the identity pairing guard may not be the thing 2c actually tests"
    fi
else
    fail "6c-setup: could not locate the identity pairing guard text to mutate"
fi

echo ""
echo "=== podbean-publish-provisioning: $PASS passed | $FAIL failed ==="
[ "$FAIL" -gt 0 ] && exit 1 || exit 0
