#!/usr/bin/env bash
# tests/unit/registry-parity-gate.test.sh
# ---------------------------------------------------------------------------
# R0 -- proves the registry-parity gate (update-skills.sh) actually catches
# the 2026-08-11 registry-strip class, not merely that the code exists.
#
# METHOD, matching tests/unit/content-recheck-convergence-probes.test.sh: the
# real functions are extracted VERBATIM from update-skills.sh by brace-
# matching their own top-level `name() { ... }` definitions and sourced --
# never reimplemented. If a function is renamed or its shape drifts, this
# suite fails loudly (exit 2) rather than silently testing a stale copy.
#
# FULLY OFFLINE. HOME is redirected into a throwaway sandbox for every test;
# nothing under the real $HOME or /data/.openclaw is ever read or written.
# The one live-network scenario (escalation POST) talks only to a python
# http.server bound to 127.0.0.1 that this suite starts and stops itself.
#
# Every scenario below is one of: a CONTROL (proves the instrument can
# produce a clean pass), an ASSERTION (proves the bad case is caught), or a
# MUTATION PROOF (disables the one detector under test and shows the exact
# same bad case now passes -- proving the check enforces, not merely exists).
# ---------------------------------------------------------------------------
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
UPDATER="$REPO_ROOT/update-skills.sh"

[ -f "$UPDATER" ] || { echo "FATAL: $UPDATER not found"; exit 2; }

if [ -z "${BASH_VERSION:-}" ]; then
  echo "FATAL: not running under bash"; exit 2
fi
echo "Running under BASH_VERSION=$BASH_VERSION (asserted, not assumed)"

PASS=0
FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ✓ $1"; }
bad() { FAIL=$((FAIL+1)); echo "  ✗ $1"; }

WORK="$(mktemp -d -t registry-parity-test-XXXXXX)"
trap 'rm -rf "$WORK"; [ -n "${MOCK_PID:-}" ] && kill "$MOCK_PID" >/dev/null 2>&1; true' EXIT

# --- verbatim extraction of top-level `name() { ... }` functions, by
#     brace-matching the bare closing "}" line (col 0). Same technique as the
#     established convergence-probes test in this same directory.
extract_function() {
  awk -v fn="$1() {" '
    $0 == fn { p=1 }
    p { print }
    p && $0 == "}" { exit }
  ' "$UPDATER"
}

FUNCS="_registry_parity_ocjson _registry_parity_agentsdir _registry_snapshot _registry_agent_dirs _registry_parity_refuse _registry_parity_escalate registry_parity_gate"
: > "$WORK/gate.inc"
for fn in $FUNCS; do
  out="$(extract_function "$fn")"
  if [ -z "$out" ]; then
    echo "FATAL: function '$fn() {' not found verbatim in $UPDATER (drift?)"
    exit 2
  fi
  printf '%s\n' "$out" >> "$WORK/gate.inc"
  echo >> "$WORK/gate.inc"
done
echo "Extracted ${#FUNCS} functions (verbatim) totalling $(wc -l < "$WORK/gate.inc" | tr -d ' ') lines from $UPDATER"

# ---------------------------------------------------------------------------
# fixture builders
# ---------------------------------------------------------------------------
new_sandbox() {
  # Prints a fresh sandbox HOME path with $1 agents in openclaw.json
  # (agents.list, comma-separated ids in $2) and $3 directories under
  # agents/ (comma-separated names in $4). Neither list needs to match.
  local tag="$1" ids_csv="$2" dirnames_csv="$3" sbx py IFS_OLD id d
  sbx="$WORK/sbx-$tag"
  mkdir -p "$sbx/.openclaw/agents"
  py="$sbx/.openclaw/openclaw.json"
  {
    printf '{"agents":{"list":['
    IFS_OLD="$IFS"; IFS=','
    first=1
    for id in $ids_csv; do
      IFS="$IFS_OLD"
      [ -z "$id" ] && continue
      [ "$first" = 1 ] || printf ','
      printf '{"id":"%s"}' "$id"
      first=0
      IFS=','
    done
    IFS="$IFS_OLD"
    printf ']}}'
  } > "$py"
  IFS_OLD="$IFS"; IFS=','
  for d in $dirnames_csv; do
    IFS="$IFS_OLD"
    [ -z "$d" ] && continue
    mkdir -p "$sbx/.openclaw/agents/$d"
    IFS=','
  done
  IFS="$IFS_OLD"
  printf '%s' "$sbx"
}

new_sandbox_entries() {
  # Same as new_sandbox but writes the POST-MIGRATION agents.entries shape.
  local tag="$1" ids_csv="$2" dirnames_csv="$3" sbx py IFS_OLD id d first
  sbx="$WORK/sbx-$tag"
  mkdir -p "$sbx/.openclaw/agents"
  py="$sbx/.openclaw/openclaw.json"
  {
    printf '{"agents":{"entries":{'
    IFS_OLD="$IFS"; IFS=','
    first=1
    for id in $ids_csv; do
      IFS="$IFS_OLD"
      [ -z "$id" ] && continue
      [ "$first" = 1 ] || printf ','
      printf '"%s":{}' "$id"
      first=0
      IFS=','
    done
    IFS="$IFS_OLD"
    printf '}}}'
  } > "$py"
  IFS_OLD="$IFS"; IFS=','
  for d in $dirnames_csv; do
    IFS="$IFS_OLD"
    [ -z "$d" ] && continue
    mkdir -p "$sbx/.openclaw/agents/$d"
    IFS=','
  done
  IFS="$IFS_OLD"
  printf '%s' "$sbx"
}

run_gate() {
  # run_gate <sandbox-HOME> <phase> -- runs registry_parity_gate in a
  # subshell with HOME redirected, printing its stdout+stderr and its exit
  # code on the last line as "RC=<n>". Sourcing gate.inc fresh each call
  # keeps the module-level _REGISTRY_PARITY_PRE_* globals isolated per
  # subshell chain, so callers must run pre-then-post in the SAME subshell
  # (see run_gate_pair) when a real pre/post relationship is being tested.
  local sbx="$1" phase="$2"
  (
    HOME="$sbx"
    export HOME
    # shellcheck disable=SC1090
    source "$WORK/gate.inc"
    registry_parity_gate "$phase"
    echo "RC=$?"
  ) 2>&1
}

run_gate_pair() {
  # run_gate_pair <pre-sandbox-HOME> <post-sandbox-HOME> -- runs 'pre' against
  # the first sandbox, then 'post' against the second, IN ONE SUBSHELL so the
  # _REGISTRY_PARITY_PRE_* globals captured by 'pre' really are visible to
  # 'post' -- exactly how the two call sites in update-skills.sh behave
  # (same shell, same run). Prints both phases' output; last line is the
  # POST phase's "RC=<n>".
  local pre_sbx="$1" post_sbx="$2"
  (
    HOME="$pre_sbx"
    export HOME
    # shellcheck disable=SC1090
    source "$WORK/gate.inc"
    echo "--pre--"
    registry_parity_gate pre
    echo "pre RC=$?"
    HOME="$post_sbx"
    export HOME
    echo "--post--"
    registry_parity_gate post
    echo "RC=$?"
  ) 2>&1
}

# ---------------------------------------------------------------------------
# SCENARIO 1 (CONTROL, positive): healthy box, unchanged pre->post.
# 5 agents in the registry, 5 matching directories. Expect: pre RC=0, post
# RC=0, "no loss" message. Proves the instrument produces a clean pass on a
# genuinely healthy box (a check that only ever refuses is not a real gate).
# ---------------------------------------------------------------------------
echo ""
echo "=== SCENARIO 1: healthy box, unchanged (CONTROL) ==="
h="$(new_sandbox healthy "main,dept-sales,dept-support,dept-content,dept-ops" "main,dept-sales,dept-support,dept-content,dept-ops")"
out="$(run_gate_pair "$h" "$h")"
echo "$out" | sed 's/^/    /'
rc="$(printf '%s\n' "$out" | tail -1 | sed 's/^RC=//')"
if [ "$rc" = "0" ] && printf '%s' "$out" | grep -q "no loss: pre=5 post=5"; then
  ok "healthy unchanged box: pre+post both pass, 'no loss' reported"
else
  bad "healthy unchanged box: expected rc=0 with 'no loss' message, got rc=$rc"
fi

# ---------------------------------------------------------------------------
# SCENARIO 2 (ASSERTION): the strip class itself. Registry already stripped
# to 1 agent (main only) BEFORE the gate ever runs, directories still show 5
# real agents on disk. This is the exact 2026-08-11 incident shape, and
# critically it must be caught at 'pre' alone -- a box that arrives already
# damaged must never be waved through just because there is no 'pre' snapshot
# yet to regress against.
# ---------------------------------------------------------------------------
echo ""
echo "=== SCENARIO 2: registry already stripped before this run (ASSERTION) ==="
s="$(new_sandbox stripped "main" "main,dept-sales,dept-support,dept-content,dept-ops")"
out="$(run_gate "$s" pre)"
echo "$out" | sed 's/^/    /'
rc="$(printf '%s\n' "$out" | tail -1 | sed 's/^RC=//')"
if [ "$rc" = "78" ] && printf '%s' "$out" | grep -q "ABSOLUTE FLOOR"; then
  ok "already-stripped box refused at 'pre' with ABSOLUTE FLOOR (rc=78)"
else
  bad "already-stripped box: expected rc=78 + ABSOLUTE FLOOR, got rc=$rc"
fi

# ---------------------------------------------------------------------------
# SCENARIO 3 (ASSERTION): the strip happening DURING this run. Pre snapshot
# is healthy (5 agents); by 'post' the registry has been reduced to 1 while
# 5 directories remain -- simulating a raw writer racing the roll itself.
# ---------------------------------------------------------------------------
echo ""
echo "=== SCENARIO 3: strip happens mid-run, pre healthy / post stripped (ASSERTION) ==="
pre3="$(new_sandbox pre3 "main,dept-sales,dept-support,dept-content,dept-ops" "main,dept-sales,dept-support,dept-content,dept-ops")"
post3="$(new_sandbox post3 "main" "main,dept-sales,dept-support,dept-content,dept-ops")"
out="$(run_gate_pair "$pre3" "$post3")"
echo "$out" | sed 's/^/    /'
rc="$(printf '%s\n' "$out" | tail -1 | sed 's/^RC=//')"
if [ "$rc" = "78" ]; then
  ok "mid-run strip refused at 'post' (rc=78)"
else
  bad "mid-run strip: expected rc=78, got rc=$rc"
fi

# ---------------------------------------------------------------------------
# SCENARIO 4 (ASSERTION): partial loss below the absolute floor. pre=5,
# post=3, directories UNCHANGED at 5 (nobody deleted a directory -- the
# registry alone lost two entries). scount=3 does not trip the <=1 floor, so
# ONLY the regression check can catch this.
# ---------------------------------------------------------------------------
echo ""
echo "=== SCENARIO 4: partial loss below the absolute floor (ASSERTION, regression-only) ==="
pre4="$(new_sandbox pre4 "main,dept-sales,dept-support,dept-content,dept-ops" "main,dept-sales,dept-support,dept-content,dept-ops")"
post4="$(new_sandbox post4 "main,dept-sales,dept-support" "main,dept-sales,dept-support,dept-content,dept-ops")"
out="$(run_gate_pair "$pre4" "$post4")"
echo "$out" | sed 's/^/    /'
rc="$(printf '%s\n' "$out" | tail -1 | sed 's/^RC=//')"
if [ "$rc" = "78" ] && printf '%s' "$out" | grep -q "REGRESSION"; then
  ok "partial loss (5->3, dircount unchanged) refused via REGRESSION (rc=78)"
else
  bad "partial loss: expected rc=78 + REGRESSION, got rc=$rc"
fi

# ---------------------------------------------------------------------------
# SCENARIO 5 (ASSERTION): identity swap hidden behind a matching count.
# pre ids=[main,a,b], post ids=[main,a,c] -- same count (3), but 'b' is gone
# and 'c' appeared. Count-only logic would pass this; identity logic must not.
# ---------------------------------------------------------------------------
echo ""
echo "=== SCENARIO 5: identity swap, count unchanged (ASSERTION, identity-only) ==="
pre5="$(new_sandbox pre5 "main,dept-a,dept-b" "main,dept-a,dept-b,dept-c")"
post5="$(new_sandbox post5 "main,dept-a,dept-c" "main,dept-a,dept-b,dept-c")"
out="$(run_gate_pair "$pre5" "$post5")"
echo "$out" | sed 's/^/    /'
rc="$(printf '%s\n' "$out" | tail -1 | sed 's/^RC=//')"
if [ "$rc" = "78" ] && printf '%s' "$out" | grep -q "IDENTITY LOSS"; then
  ok "identity swap (count unchanged, dept-b -> dept-c) refused via IDENTITY LOSS (rc=78)"
else
  bad "identity swap: expected rc=78 + IDENTITY LOSS, got rc=$rc"
fi

# ---------------------------------------------------------------------------
# SCENARIO 6 (CONTROL, edge case): unreadable/malformed config must be
# UNDETERMINED, never treated as a clean zero. pre + post both malformed:
# both phases must return 0 (never silently refuse on a false premise, and
# never silently pass a count check it cannot actually perform) -- each
# phase must explicitly report its own count checks SKIPPED, never "no
# loss" (which would be a false clean bill on a config nobody could read).
# ---------------------------------------------------------------------------
echo ""
echo "=== SCENARIO 6: malformed config is UNDETERMINED, not a false pass or false refuse ==="
m="$WORK/sbx-malformed"
mkdir -p "$m/.openclaw/agents"
printf '{not valid json' > "$m/.openclaw/openclaw.json"
out="$(run_gate_pair "$m" "$m")"
echo "$out" | sed 's/^/    /'
rc="$(printf '%s\n' "$out" | tail -1 | sed 's/^RC=//')"
undetermined_count="$(printf '%s' "$out" | grep -c "UNDETERMINED")"
skipped_count="$(printf '%s' "$out" | grep -c "Count checks SKIPPED this phase")"
if [ "$rc" = "0" ] && [ "$undetermined_count" -ge 2 ] && [ "$skipped_count" -ge 2 ] && ! printf '%s' "$out" | grep -q "no loss"; then
  ok "malformed config: UNDETERMINED both phases (x$undetermined_count), count checks explicitly SKIPPED both phases (x$skipped_count), never 'no loss'"
else
  bad "malformed config: expected rc=0 + UNDETERMINED + explicit skip, got rc=$rc"
fi

# ---------------------------------------------------------------------------
# SCENARIO 7 (CONTROL): fresh/unprovisioned box (no config file at all) is a
# clean no-op, not a refusal and not an UNDETERMINED.
# ---------------------------------------------------------------------------
echo ""
echo "=== SCENARIO 7: fresh box, no config file (CONTROL, no-op) ==="
f="$WORK/sbx-fresh"
mkdir -p "$f"
out="$(run_gate "$f" pre)"
echo "$out" | sed 's/^/    /'
rc="$(printf '%s\n' "$out" | tail -1 | sed 's/^RC=//')"
if [ "$rc" = "0" ] && printf '%s' "$out" | grep -q "nothing to check"; then
  ok "fresh box: clean no-op (rc=0)"
else
  bad "fresh box: expected rc=0 no-op, got rc=$rc"
fi

# ---------------------------------------------------------------------------
# SCENARIO 8 (CONTROL): post-migration agents.entries shape is read
# correctly (schema-agnostic) and a healthy entries-shaped box passes clean.
# ---------------------------------------------------------------------------
echo ""
echo "=== SCENARIO 8: agents.entries (post-migration schema) read correctly (CONTROL) ==="
e="$(new_sandbox_entries entries_ok "main,dept-a,dept-b" "main,dept-a,dept-b")"
out="$(run_gate_pair "$e" "$e")"
echo "$out" | sed 's/^/    /'
rc="$(printf '%s\n' "$out" | tail -1 | sed 's/^RC=//')"
if [ "$rc" = "0" ] && printf '%s' "$out" | grep -q "no loss: pre=3 post=3"; then
  ok "agents.entries schema: read correctly, healthy pass"
else
  bad "agents.entries schema: expected rc=0 + no-loss(3/3), got rc=$rc"
fi

# ---------------------------------------------------------------------------
# SCENARIO 9 (MUTATION PROOF): disable the ABSOLUTE FLOOR condition in a
# private copy of the extracted gate and re-run Scenario 2 (the already-
# stripped box). If the detector is load-bearing, neutralizing it must flip
# the SAME bad case from refused (78) to silently passed (0).
# ---------------------------------------------------------------------------
echo ""
echo "=== SCENARIO 9: MUTATION PROOF -- disable the absolute-floor check, re-run Scenario 2 ==="
sed 's/if \[ "\$scount" -le 1 \] \&\& \[ "\$dircount" -gt 2 \]; then/if false; then/' \
  "$WORK/gate.inc" > "$WORK/gate.mutated-floor.inc"
if diff -q "$WORK/gate.inc" "$WORK/gate.mutated-floor.inc" >/dev/null 2>&1; then
  echo "FATAL: mutation sed did not change anything -- the condition text this test targets has drifted out from under it"
  exit 2
fi
mut_out="$(
  (
    HOME="$s"   # reuse the Scenario 2 already-stripped sandbox
    export HOME
    # shellcheck disable=SC1090
    source "$WORK/gate.mutated-floor.inc"
    registry_parity_gate pre
    echo "RC=$?"
  )
)"
echo "$mut_out" | sed 's/^/    /'
mut_rc="$(printf '%s\n' "$mut_out" | tail -1 | sed 's/^RC=//')"
if [ "$mut_rc" = "0" ]; then
  ok "MUTATION PROOF: with the absolute-floor check disabled, the SAME already-stripped box now silently passes (rc=0) -- confirms the real check (Scenario 2, rc=78) is what enforces this, not incidental behavior"
else
  bad "MUTATION PROOF FAILED: disabling the absolute-floor check should have flipped Scenario 2 to rc=0, got rc=$mut_rc -- something else is also refusing this case, so Scenario 2 may not be testing what it claims to"
fi

# ---------------------------------------------------------------------------
# SCENARIO 10 (MUTATION PROOF): disable the IDENTITY LOSS comparison and
# re-run Scenario 5. Proves the identity check specifically -- not the
# regression-count check -- is what catches a count-preserving swap.
# ---------------------------------------------------------------------------
echo ""
echo "=== SCENARIO 10: MUTATION PROOF -- disable the identity-loss check, re-run Scenario 5 ==="
sed 's/if \[ -n "\$missing" \]; then/if false; then/' \
  "$WORK/gate.inc" > "$WORK/gate.mutated-identity.inc"
if diff -q "$WORK/gate.inc" "$WORK/gate.mutated-identity.inc" >/dev/null 2>&1; then
  echo "FATAL: mutation sed did not change anything -- the condition text this test targets has drifted out from under it"
  exit 2
fi
mut_out="$(
  (
    HOME="$pre5"
    export HOME
    # shellcheck disable=SC1090
    source "$WORK/gate.mutated-identity.inc"
    registry_parity_gate pre >/dev/null
    HOME="$post5"
    export HOME
    registry_parity_gate post
    echo "RC=$?"
  )
)"
echo "$mut_out" | sed 's/^/    /'
mut_rc="$(printf '%s\n' "$mut_out" | tail -1 | sed 's/^RC=//')"
if [ "$mut_rc" = "0" ]; then
  ok "MUTATION PROOF: with the identity-loss check disabled, the SAME count-preserving swap (Scenario 5) now silently passes (rc=0) -- confirms identity checking, not count checking, is what catches this class"
else
  bad "MUTATION PROOF FAILED: disabling the identity check should have flipped Scenario 5 to rc=0, got rc=$mut_rc"
fi

# ---------------------------------------------------------------------------
# SCENARIO 11 (CONTROL, positive escalation): with RESCUE_RANGERS_WEBHOOK_URL
# pointed at a real local listener, a refusal must actually POST a payload
# containing the box's problem -- proving the escalation path is live code,
# not just a printed banner. Skipped gracefully if python3 cannot bind a
# local socket in this sandbox (reported as SKIP, never silently passed).
# ---------------------------------------------------------------------------
echo ""
echo "=== SCENARIO 11: escalation actually POSTs when configured (CONTROL, live-local) ==="
MOCK_PORT=$(( (RANDOM % 5000) + 20000 ))
MOCK_OUT="$WORK/mock-request.json"
python3 - "$MOCK_PORT" "$MOCK_OUT" > "$WORK/mock-server.log" 2>&1 <<'PYEOF' &
import http.server, sys, json
port = int(sys.argv[1])
outfile = sys.argv[2]
class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length)
        with open(outfile, 'wb') as f:
            f.write(body)
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{"ok":true}')
    def log_message(self, *a): pass
srv = http.server.HTTPServer(('127.0.0.1', port), H)
srv.timeout = 8  # bounded: never hang this suite if the client never connects
srv.handle_request()
PYEOF
MOCK_PID=$!
sleep 1
if kill -0 "$MOCK_PID" >/dev/null 2>&1; then
  esc_out="$(
    (
      HOME="$s"   # the Scenario 2 already-stripped sandbox -- guaranteed to refuse
      export HOME
      RESCUE_RANGERS_WEBHOOK_URL="http://127.0.0.1:$MOCK_PORT/webhook"
      FLEET_STANDING_BOX_SLUG="test-box-registry-parity"
      export RESCUE_RANGERS_WEBHOOK_URL FLEET_STANDING_BOX_SLUG
      # shellcheck disable=SC1090
      source "$WORK/gate.inc"
      registry_parity_gate pre
      echo "RC=$?"
    )
  )"
  echo "$esc_out" | sed 's/^/    /'
  wait "$MOCK_PID" 2>/dev/null
  if [ -s "$MOCK_OUT" ] && python3 -c "
import json, sys
d = json.load(open('$MOCK_OUT'))
assert d.get('boxName') == 'test-box-registry-parity', d
assert 'REGISTRY-STRIP' in d.get('problem',''), d
assert d.get('action') == 'escalate', d
print('payload OK:', d)
" 2>"$WORK/mock-assert.log"; then
    ok "escalation POST: mock listener received a valid, correctly-shaped payload"
  else
    cat "$WORK/mock-assert.log" 2>/dev/null | sed 's/^/    /'
    bad "escalation POST: mock listener did not receive the expected payload (see $MOCK_OUT)"
  fi
else
  echo "  (SKIP: local python3 http.server could not bind -- sandbox networking restricted here; not counted as pass or fail)"
fi
MOCK_PID=""

# ---------------------------------------------------------------------------
# SCENARIO 12 (CONTROL, negative escalation): with the webhook env var UNSET
# (the real state on most boxes today), a refusal must NOT attempt a network
# call and must NOT itself fail -- the marker + banner are the record.
# ---------------------------------------------------------------------------
echo ""
echo "=== SCENARIO 12: escalation is a documented no-op when unconfigured (CONTROL) ==="
out="$(
  (
    HOME="$s"
    export HOME
    unset RESCUE_RANGERS_WEBHOOK_URL RESCUE_RANGERS_WEBHOOK_SECRET 2>/dev/null
    # shellcheck disable=SC1090
    source "$WORK/gate.inc"
    registry_parity_gate pre
    echo "RC=$?"
  ) 2>&1
)"
echo "$out" | sed 's/^/    /'
rc="$(printf '%s\n' "$out" | tail -1 | sed 's/^RC=//')"
if [ "$rc" = "78" ] && printf '%s' "$out" | grep -q "skipping the live escalation POST"; then
  ok "escalation with no webhook configured: still refuses (rc=78), explicit documented no-op, no crash"
else
  bad "escalation no-op path: expected rc=78 + explicit skip message, got rc=$rc"
fi

# ---------------------------------------------------------------------------
# SCENARIO 13 (CONTROL): the marker file is actually written on refusal, with
# the fields a human/RR responder needs, not just printed to the console.
# ---------------------------------------------------------------------------
echo ""
echo "=== SCENARIO 13: refusal marker file is written with the right fields (CONTROL) ==="
(
  HOME="$s"
  export HOME
  unset RESCUE_RANGERS_WEBHOOK_URL 2>/dev/null
  # shellcheck disable=SC1090
  source "$WORK/gate.inc"
  registry_parity_gate pre >/dev/null
)
marker="$s/.openclaw/.openclaw-registry-parity-refused"
if [ -f "$marker" ] && grep -q "^phase=pre" "$marker" && grep -q "^reason=ABSOLUTE FLOOR" "$marker"; then
  ok "marker file written at $marker with phase= and reason= fields"
else
  bad "marker file missing or malformed at $marker"
fi

echo ""
echo "============================================================"
echo "RESULT: $PASS passed, $FAIL failed"
echo "============================================================"
[ "$FAIL" -eq 0 ]
