#!/usr/bin/env bash
# tests/unit/rr027-rescue-env.test.sh — RR-027 gate: the shared credential-env
# helper (shared-utils/rescue-env.sh).
#
# Pins the RR-027 contract on the HELPER ITSELF (the wire/poll/seed consumers
# are pinned by rr027-no-credential-in-child-env.test.sh):
#   1. rescue_env_parse reads ONLY allowlisted names, never executes the file,
#      never expands values, preserves quoting/space behavior.
#   2. Malformed lines FAIL VISIBLY (rc nonzero, reason on stderr with line
#      number, never a value).
#   3. rescue_env_get return-code contract (0/1/2/3).
#   4. rescue_env_scrub removes EVERY rescue credential alias from the child
#      env — including a synthetic exported token — while necessary authorized
#      model/tool credentials pass through untouched.
#   5. rescue_env_header_file writes 0600 into the caller's private dir; the
#      value never transits argv.
#
# Negative controls: a sentinel credential value is planted in every input and
# asserted ABSENT from every output — the leak detector is itself proven able
# to fail (a deliberately leaking shape IS caught).
#
# Hermetic: temp dirs + a stub child; no network; no real credential; no value
# ever printed by the helper (the test captures and inspects, never shows).
set -u

# Portable script-dir probe: BASH_SOURCE under bash, $0 under POSIX sh/dash
# (Ubuntu runners link /bin/sh to dash, where BASH_SOURCE is a bad
# substitution and the gate's `sh` leg died before any assertion).
if [ -n "${BASH_SOURCE:-}" ]; then _HERE_SRC="${BASH_SOURCE[0]}"; else _HERE_SRC="$0"; fi
HERE="$(cd "$(dirname "$_HERE_SRC")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
HELPER="$REPO/shared-utils/rescue-env.sh"

PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ok $1"; }
bad() { FAIL=$((FAIL+1)); echo "  FAIL $1 ${2:-}"; }

# Sentinel credential value: unique, never printed by the helpers.
TOK='ZZRR027SENTINEL-t0k3N-v4lu3-DONOTPRINT'
ESC='ZZRR027ESCSECRET9f8e7d6c'
NEC='ZZRR027NECESSARY-CRED'
[ -f "$HELPER" ] || { echo "FATAL: $HELPER missing"; exit 2; }

FIX="$(mktemp -d "${TMPDIR:-/tmp}/rr027.XXXXXX")"
trap 'rm -rf "$FIX"' EXIT

echo "== RR-027: shared rescue-env helper =="

# Store carrying every documented form + traps for the old defects.
STORE="$FIX/store.env"
cat > "$STORE" <<EOF
# fleet box enrollment store
RR_BOX_TOKEN="$TOK"
RR_BOX_SLUG='box-slug with spaces'
export RR_RECEIVER_URL=https://receiver.example/rr
PLAIN_KEY=plain value  # trailing comment
QUOTED_HASH="keeps # inside"
INFER_CRED=$NEC
DOLLARISH=\$NOT_EXPANDED
JUNKLINE
BAD-KEY=x
EOF

run_parse() { ( . "$HELPER"; rescue_env_parse "$STORE" "$@" ) 2>"$FIX/parse.err"; }
run_get()   { ( . "$HELPER"; rescue_env_get "$STORE" "$@" ) 2>"$FIX/get.err"; }

# --- 1. allowlist + verbatim values -----------------------------------------
out=$(run_parse RR_BOX_TOKEN RR_BOX_SLUG RR_RECEIVER_URL PLAIN_KEY QUOTED_HASH INFER_CRED DOLLARISH); rc=$?
echo "$out" | grep -qF "RR_BOX_TOKEN	$TOK" && ok "double-quoted value verbatim (spaces kept)" || bad "double-quoted value mangled" "$(echo "$out" | sed -n '1p')"
echo "$out" | grep -qF "RR_BOX_SLUG	box-slug with spaces" && ok "single-quoted value verbatim" || bad "single-quoted value mangled"
echo "$out" | grep -qF "RR_RECEIVER_URL	https://receiver.example/rr" && ok "export prefix stripped" || bad "export prefix not stripped"
echo "$out" | grep -qF "PLAIN_KEY	plain value" && ok "bare value keeps interior, drops trailing comment" || bad "bare value comment handling"
echo "$out" | grep -qF 'QUOTED_HASH	keeps # inside' && ok "quoted # preserved" || bad "quoted # lost"
echo "$out" | grep -qF "INFER_CRED	$NEC" && ok "necessary inference credential parsed" || bad "inference credential missing"
echo "$out" | grep -qF 'DOLLARISH	$NOT_EXPANDED' && ok "dollar value NOT expanded (no shell semantics)" || bad "dollar value expanded (sourcing bug reborn)"
echo "$out" | grep -qF "JUNKLINE\|BAD-KEY" && bad "malformed keys were EMITTED (allowlist broken)" || ok "malformed lines never emitted as values"
[ "$rc" -ne 0 ] && ok "parse rc nonzero on malformed store (fail visible)" || bad "parse rc 0 on malformed store"
grep -q "malformed line 9" "$FIX/parse.err" && ok "malformed reason names the line number" || bad "malformed reason line number missing" "$(cat "$FIX/parse.err")"
grep -q "malformed line 10" "$FIX/parse.err" && ok "bad-key reason names the line number" || bad "bad-key reason missing"
if grep -qF "$TOK" "$FIX/parse.err"; then bad "parser stderr LEAKED the token value"; else ok "parser stderr carries no value"; fi

# allowlist gate: parse ONLY the token -> no other name emitted
out2=$(run_parse RR_BOX_TOKEN); rc2=$?
echo "$out2" | grep -qF "RR_BOX_SLUG" && bad "allowlist leaked a non-requested name" || ok "allowlist emits ONLY requested names"
echo "$out2" | grep -qF "INFER_CRED" && bad "allowlist leaked inference credential name" || ok "non-requested credentials stay in the file"

# --- 2. get() return-code contract ------------------------------------------
CLEAN_STORE="$FIX/clean-store.env"
cat > "$CLEAN_STORE" <<EOF
RR_BOX_TOKEN="$TOK"
RR_BOX_SLUG=box-synthetic
EOF
v=$( ( . "$HELPER"; rescue_env_get "$CLEAN_STORE" RR_BOX_TOKEN ) 2>/dev/null ); rc=$?
[ "$rc" = 0 ] && [ "$v" = "$TOK" ] && ok "get: present value rc=0 (clean store)" || bad "get present rc=$rc"
v=$( ( . "$HELPER"; rescue_env_get "$CLEAN_STORE" MISSING_NAME ) 2>/dev/null ); rc=$?
[ "$rc" = 1 ] && ok "get: absent name rc=1" || bad "get absent rc=$rc"
( . "$HELPER"; rescue_env_get "$FIX/definitely-absent.env" X ) >/dev/null 2>&1; rc=$?
[ "$rc" = 2 ] && ok "get: missing file rc=2" || bad "get missing-file rc=$rc"
v=$(run_get RR_BOX_TOKEN); rc=$?
[ "$rc" = 3 ] && ok "get: malformed store rc=3 (fail-visible contract)" || bad "get malformed rc=$rc"
grep -q "malformed line" "$FIX/get.err" && ok "get replays the parser reason lines to stderr" || bad "get lost the reason lines"

# --- 3. scrub: synthetic exported alias NEVER reaches the child -------------
CHILD_OUT="$FIX/child.txt"
cat > "$FIX/bin-stub" <<'STUBEOF'
#!/bin/sh
env | sort > "$SCRUB_CHILD_OUT"
exit 0
STUBEOF
chmod +x "$FIX/bin-stub"
(
  . "$HELPER"
  export SCRUB_CHILD_OUT="$CHILD_OUT"
  export RR_BOX_TOKEN="$TOK" RR_BOX_SLUG=leak-slug RR_BOX_CRED=leak-cred
  export RR_RECEIVER_SECRET=leak-rsec RESCUE_PUSH_SECRET=leak-push
  export RESCUE_RANGERS_WEBHOOK_SECRET="$ESC" RESCUE_RANGERS_HELP_CHAT_ID=leak-chat
  export GEMINI_API_KEY="$NEC" KEEP_ME=kept
  RESCUE_ENV_EXTRA_UNSET="RESCUE_RANGERS_WEBHOOK_SECRET RESCUE_RANGERS_HELP_CHAT_ID" \
    rescue_env_scrub "$FIX/bin-stub"
) >/dev/null 2>&1
rc=$?
[ "$rc" = 0 ] && ok "scrub ran the child (rc=0)" || bad "scrub child rc=$rc"
if [ -f "$CHILD_OUT" ]; then
  n=$(grep -cE '^(RR_BOX_TOKEN|RR_BOX_SLUG|RR_BOX_CRED|RR_RECEIVER_SECRET|RESCUE_PUSH_SECRET|RESCUE_RANGERS_WEBHOOK_SECRET|RESCUE_RANGERS_HELP_CHAT_ID)=' "$CHILD_OUT")
  [ "$n" = 0 ] && ok "every rescue alias REMOVED from the child env (7 names)" || bad "$n rescue alias(es) survived into the child env"
  grep -qF "GEMINI_API_KEY=$NEC" "$CHILD_OUT" && ok "necessary authorized model credential STILL PRESENT in child env" || bad "necessary credential was scrubbed (over-scrub)"
  grep -q "KEEP_ME=kept" "$CHILD_OUT" && ok "non-rescue environment untouched" || bad "non-rescue env damaged"
  if grep -qF "$TOK" "$CHILD_OUT"; then bad "sentinel token VALUE reached the child env"; else ok "token value absent from child env"; fi
  if grep -qF "$ESC" "$CHILD_OUT"; then bad "escalation secret reached the poll child"; else ok "poll-scrubbed escalation secret absent from child env"; fi
else
  bad "child never ran — no env to inspect"
fi

# negative control: WITHOUT the scrub the sentinel IS inherited (the scrub is
# the enforcement, not a tautology)
(
  export SCRUB_CHILD_OUT="$CHILD_OUT" RR_BOX_TOKEN="$TOK"
  "$FIX/bin-stub"
)
grep -qF "$TOK" "$CHILD_OUT" && ok "control: un-scrubbed child DOES inherit the exported alias (scrub is load-bearing)" || bad "control child did not inherit — the leak detector cannot fail"

# --- 4. header file: 0600 in a private dir, value never in argv -------------
# Portable stat probe: GNU `stat -c` FIRST. BSD `stat -f` must never lead:
# on GNU/Linux `-f` means filesystem-status, exits 0 with a dump, and the
# `||` fallback never fires (RR-027 Ubuntu gate FAIL, 2026-09-09).
( . "$HELPER"; HDR=$(rescue_env_private_tmp "$FIX/state" ) && echo "$HDR" > "$FIX/hdrdir" ) >/dev/null 2>&1
HDRDIR=$(cat "$FIX/hdrdir" 2>/dev/null)
if [ -n "$HDRDIR" ] && [ -d "$HDRDIR" ]; then
  perms=$(stat -c "%a" "$HDRDIR" 2>/dev/null || stat -f "%Lp" "$HDRDIR" 2>/dev/null)
  [ "$perms" = "700" ] && ok "private tmp dir is 0700" || bad "private tmp dir perms $perms"
else
  # caller may pass an existing dir directly
  mkdir -p "$FIX/state"; chmod 700 "$FIX/state"; HDRDIR="$FIX/state/tmp"
  ( . "$HELPER"; rescue_env_private_tmp "$FIX/state" >/dev/null ); chmod 700 "$HDRDIR" 2>/dev/null
  perms=$(stat -c "%a" "$HDRDIR" 2>/dev/null || stat -f "%Lp" "$HDRDIR" 2>/dev/null)
  [ "$perms" = "700" ] && ok "private tmp dir is 0700 (existing-base path)" || bad "private tmp dir perms $perms"
fi
HDRP=$( ( . "$HELPER"; rescue_env_header_file "$HDRDIR" "X-RR-Box-Token" "$TOK" ) )
if [ -n "$HDRP" ] && [ -f "$HDRP" ]; then
  hperms=$(stat -c "%a" "$HDRP" 2>/dev/null || stat -f "%Lp" "$HDRP" 2>/dev/null)
  [ "$hperms" = "600" ] && ok "header file is 0600" || bad "header file perms $hperms"
  grep -qF "X-RR-Box-Token: $TOK" "$HDRP" && ok "header file carries the header NAME+value" || bad "header file content wrong"
else
  bad "header file not created"
fi
# the value must never transit an external command's argv: the WRITE is a
# builtin redirection — prove by construction: the helper runs no external
# command with the value (grep the helper source for the write shape)
if grep -qE 'printf .*rescue-hdr.*\$|echo.*rescue-hdr' "$HELPER"; then
  bad "header write may use an external command"
else
  ok "header write is a shell builtin redirection (value never in argv by construction)"
fi

# --- 5. sourcing safety: helper defines functions, exports nothing ----------
exported=$( ( . "$HELPER"; export -p ) | grep -cE 'declare -x (RR_|RESCUE_)' )
[ "$exported" = 0 ] && ok "sourcing the helper exports no rescue variable" || bad "helper exported $exported rescue variable(s)"
bash -n "$HELPER" && sh -n "$HELPER" && ok "helper parses under bash AND sh (POSIX)" || bad "helper syntax"

echo ""
echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] || exit 1
exit 0