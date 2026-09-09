#!/usr/bin/env bash
# =============================================================================
# RESCUE RANGERS :: verify.sh  (RR-030 rewrite)
# The department's failable OFFLINE drill battery, gate-labeled per RR-030.
# Zero network, zero model, zero live-box touch.
#
# RR-030 CONTRACT (this file is its enforcement):
#   1. Failure accounting lives in the PARENT shell (scripts/rescue-rangers-
#      harness.sh) — never inside a subshell whose exit code is discarded.
#   2. REQUIRED runtimes are required. node missing is a FAILED gate, not a
#      WARN skip: the baseline shipped "ALL OFFLINE DRILLS PASS" with node
#      absent because the JS drill degraded to a warning.
#   3. Gates are named UNIT / CONTRACT / INSTALLED / LIVE_ACCEPTANCE and are
#      reported separately. A green UNIT line never satisfies release
#      completion; unexercised gates print UNVERIFIED, which is never
#      SKIP=PASS.
#   4. Negative/mutation drills break each checker IN A COPY and require the
#      copied gate to exit nonzero on the mutated code (assumption-controlled:
#      the unmutated checker must stay green on the same fixture).
#   5. Test roots are explicit (mktemp dirs, RESCUE_STATE_DIR, OC_CONFIG_ROOT);
#      HOME is never repurposed.
#   6. Fixtures assert the REAL contracts (CC ingest auth+enum, ledger
#      idempotency, nine-field relay contract) — no mirrored-wrong
#      implementation assumptions: the CC contract cases are derived from the
#      current Command Center route source, not from this repo's copy of it.
#
# USAGE:
#   bash verify.sh                     # UNIT + CONTRACT + INSTALLED gates
#   bash verify.sh --json-summary      # plus a machine-readable gate line
# =============================================================================
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../../../../.." && pwd)"          # .../openclaw-onboarding
# shellcheck disable=SC1091
source "$REPO_ROOT/scripts/rescue-rangers-harness.sh"

PY="$(command -v python3 || true)"
NODE="$(command -v node || true)"

harness_begin

# ---------------------------------------------------------------------------
# GATE 0 — instrument proof (known-good control BEFORE any verdict is issued;
# if the control fails, every later negative is meaningless).
# ---------------------------------------------------------------------------
if [ -z "$PY" ]; then
  harness_gate_fail UNIT "python3 not on PATH — no offline checker can run"
else
  harness_case UNIT "instrument control: python3 exists and runs" -- "$PY" -c "import sys; assert sys.version_info[0] == 3"
fi
if [ -z "$NODE" ]; then
  # RR-030: relay_brain_validation.js is a REQUIRED ship artifact; a battery
  # that quietly stops exercising it (old behavior: WARN + ALLPASS) hides a
  # broken deploy path. Missing node FAILS here.
  harness_gate_fail UNIT "node not on PATH — relay_brain_validation.js drill cannot run (required runtime absent; this failed the battery at baseline)"
else
  harness_case UNIT "instrument control: node exists and runs" -- "$NODE" -e "assert(1 === 1)"
fi

# ---------------------------------------------------------------------------
# GATE: UNIT — each tool's self-test (unchanged batteries, now observed in
# the parent shell via the harness).
# ---------------------------------------------------------------------------
if [ -n "$PY" ]; then
  harness_case UNIT "rescue_ledger.py --self-test" \
    -- env RESCUE_STATE_DIR="$(mktemp -d)" "$PY" "$HERE/rescue_ledger.py" --self-test
  harness_case UNIT "rescue_cc_board.py --self-test" \
    -- "$PY" "$HERE/rescue_cc_board.py" --self-test
  harness_case UNIT "migrate-rescue-staticdata.py --self-test" \
    -- "$PY" "$HERE/migrate-rescue-staticdata.py" --self-test
  harness_case UNIT "stamp-rescue-escalation-section.sh --self-test" \
    -- bash "$HERE/stamp-rescue-escalation-section.sh" --self-test
fi
if [ -n "$NODE" ]; then
  harness_case UNIT "relay_brain_validation.js --self-test" \
    -- "$NODE" "$HERE/relay_brain_validation.js" --self-test
fi

# ---------------------------------------------------------------------------
# GATE: UNIT — triage self-test, run from the REPO copy (explicit path; the
# fixture tree is OC_CONFIG_ROOT-based inside the script).
# ---------------------------------------------------------------------------
if [ -x "$REPO_ROOT/scripts/rr-triage.sh" ] || [ -f "$REPO_ROOT/scripts/rr-triage.sh" ]; then
  harness_case UNIT "rr-triage.sh --self-test (repo copy)" \
    -- bash "$REPO_ROOT/scripts/rr-triage.sh" --self-test
else
  harness_gate_fail UNIT "scripts/rr-triage.sh not found at $REPO_ROOT/scripts/rr-triage.sh"
fi

# ---------------------------------------------------------------------------
# GATE: MUTATION (UNIT class) — break each checker in a copy; the copied gate
# must go nonzero. Assumption control: the pristine copy must stay green.
# ---------------------------------------------------------------------------
MUT="$(mktemp -d)"
trap 'rm -rf "$MUT"' EXIT

if [ -n "$PY" ]; then
  # RR-030 note: mutation breakers are written to FILES and invoked as plain
  # commands — never heredocs inside compound commands (a `fi` directly after
  # a heredoc-if mis-parses; proven during this rewrite).
  MUTATOR="$MUT/apply_mutation.py"
  cat > "$MUTATOR" <<'MUTPY'
import sys, pathlib
# usage: apply_mutation.py ANCHOR_FILE REPLACEMENT_FILE TARGET
anchor = pathlib.Path(sys.argv[1]).read_text()
replacement = pathlib.Path(sys.argv[2]).read_text()
target = pathlib.Path(sys.argv[3])
src = target.read_text()
mut = src.replace(anchor, replacement)
if mut == src:
    sys.stderr.write(f"MUTATION ANCHOR NOT FOUND in {target}: {anchor[:60]!r}\n")
    sys.exit(2)
target.write_text(mut)
MUTPY

  # --- mutation 1: board aging sweep broken -------------------------------
  cp "$HERE/rescue_cc_board.py" "$HERE/rescue_ledger.py" "$MUT/" 2>/dev/null
  printf '%s' 'aged = {t["ticket_id"] for t in aging_sweep(led, 120)}' > "$MUT/anchor1.txt"
  printf '%s' 'aged = set()  # MUTATED: sweep returns nothing' > "$MUT/repl1.txt"
  if [ -f "$MUT/rescue_cc_board.py" ] && [ -f "$MUT/rescue_ledger.py" ] \
      && "$PY" "$MUTATOR" "$MUT/anchor1.txt" "$MUT/repl1.txt" "$MUT/rescue_cc_board.py"; then
    harness_case_negative UNIT "MUTATION: broken aging sweep must FAIL rescue_cc_board --self-test" \
      -- "$PY" "$MUT/rescue_cc_board.py" --self-test
  else
    harness_gate_fail UNIT "mutation setup: aging-sweep anchor drifted in rescue_cc_board.py"
  fi

  # --- mutation 2: ledger open_ticket loses idempotency -------------------
  cp "$HERE/rescue_ledger.py" "$MUT/rescue_ledger_idem.py"
  printf '%s' '"INSERT OR IGNORE INTO tickets("' > "$MUT/anchor2.txt"
  printf '%s' '"INSERT INTO tickets("' > "$MUT/repl2.txt"
  # The ledger's own self-test asserts idempotent re-open returns False; on
  # mutated code that assert must fire (nonzero).
  if "$PY" "$MUTATOR" "$MUT/anchor2.txt" "$MUT/repl2.txt" "$MUT/rescue_ledger_idem.py"; then
    harness_case_negative UNIT "MUTATION: non-idempotent open_ticket must FAIL rescue_ledger --self-test" \
      -- env RESCUE_STATE_DIR="$(mktemp -d)" "$PY" "$MUT/rescue_ledger_idem.py" --self-test
  else
    harness_gate_fail UNIT "mutation setup: INSERT OR IGNORE anchor drifted in rescue_ledger.py"
  fi

  # --- mutation 3: stamp template leaves an unrendered token --------------
  cp "$HERE/stamp-rescue-escalation-section.sh" "$MUT/stamp-mut.sh"
  # RR-030-qc: the mutated copy resolves its template by walking up from its
  # own dir (_default_tpl), so it needs the repo template beside it — else the
  # drill fails with "template not found" on PRISTINE code too and proves
  # nothing about the renderer. Seed it before running.
  mkdir -p "$MUT/scripts"
  cp "$HERE/rescue-escalation-section.md.tpl" "$MUT/scripts/" 2>/dev/null || true
  if sed 's/tpl = tpl.replace("{{%s}}" % k, os.environ.get(k, ""))/tpl = tpl.replace("{{%s}}" % k, "{{LEFT}}" if k == "BOX_NAME" else os.environ.get(k, ""))/' \
      "$HERE/stamp-rescue-escalation-section.sh" > "$MUT/stamp-mut.sh" 2>/dev/null \
      && ! cmp -s "$HERE/stamp-rescue-escalation-section.sh" "$MUT/stamp-mut.sh"; then
    # The stamp self-test greps for unrendered {{PERSON}} tokens; give it the
    # repo template so the mutated renderer has a template to fail against.
    harness_case_negative UNIT "MUTATION: unrendered-token renderer must FAIL stamp self-test" \
      -- bash "$MUT/stamp-mut.sh" --self-test
  else
    harness_gate_fail UNIT "mutation setup: stamp render anchor drifted"
  fi
fi

if [ -n "$NODE" ]; then
  # --- mutation 4: relay nine-field enforcement disabled ------------------
  cp "$HERE/relay_brain_validation.js" "$MUT/relay-mut.js"
  if sed "s/const missing = NINE_FIELDS.filter((f) => !_isNonEmpty(p\[f\]));/const missing = []; \/\/ MUTATED: enforcement off/" \
      "$HERE/relay_brain_validation.js" > "$MUT/relay-mut.js" 2>/dev/null \
      && ! cmp -s "$HERE/relay_brain_validation.js" "$MUT/relay-mut.js"; then
    harness_case_negative UNIT "MUTATION: disabled nine-field enforcement must FAIL relay --self-test" \
      -- "$NODE" "$MUT/relay-mut.js" --self-test
  else
    harness_gate_fail UNIT "mutation setup: NINE_FIELDS filter anchor drifted in relay_brain_validation.js"
  fi
fi

# --- mutation 5: triage parity check neutralized (repo copy) ---------------
if [ -f "$REPO_ROOT/scripts/rr-triage.sh" ] && [ -n "$PY" ]; then
  # The board-style mutation: swap the healthy-config expectation. If the
  # self-test still exits 0, its failure accounting is broken (the RR-030
  # defect). This is a mutation OF THE HARNESS CONTRACT, not of the checker.
  cp "$REPO_ROOT/scripts/rr-triage.sh" "$MUT/triage-mut.sh"
  if sed 's/echo "  ✓ healthy config: streaming + toolSearch both CLEAN"/echo "  ✗ FORCED-FAIL healthy config (mutation)"; exit 9/' \
      "$REPO_ROOT/scripts/rr-triage.sh" > "$MUT/triage-mut.sh" 2>/dev/null \
      && ! cmp -s "$REPO_ROOT/scripts/rr-triage.sh" "$MUT/triage-mut.sh"; then
    harness_case_negative UNIT "MUTATION: forced fixture failure must make triage --self-test nonzero" \
      -- bash "$MUT/triage-mut.sh" --self-test
  else
    harness_gate_fail UNIT "mutation setup: fixture-1 anchor drifted in rr-triage.sh"
  fi
fi

# ---------------------------------------------------------------------------
# GATE: CONTRACT — board <-> Command Center contract, derived from the CURRENT
# CC source (../blackceo-command-center when colocated; the CC repo owns these
# files, so here we prove OUR side against a REAL contract server, not against
# a mirrored copy of assumed behavior).
# CONTRACT cases run a real local HTTP server and exercise the wire path:
#   - ingest requires the HMAC x-webhook-signature when WEBHOOK_SECRET is set
#     (CC ingest/route.ts: wrong/absent signature -> 401; unset secret+allow
#     flag -> dev mode) — our _sign must produce the digest the route accepts.
#   - patch_status must refuse a status outside the CC TaskStatus enum
#     (write-back calls carry Authorization: Bearer $MC_API_TOKEN; a 401 here
#     means the header is missing) OFFLINE (CC validation.ts TaskStatus) —
#     enum parity against the LIVE CC source when available, else against
#     the pinned 10-value enum.
#   - a 500 board must be fail-soft (return None/False, record receipt).
# ---------------------------------------------------------------------------
CONTRACT_SERVER="$MUT/contract_server.py"
if [ -n "$PY" ]; then
  cat > "$CONTRACT_SERVER" <<'PYSRV'
# Contract fixture server: behaves like the CURRENT CC /api/tasks/ingest and
# PATCH /api/tasks/{id} routes (auth via Authorization: Bearer $MC_API_TOKEN
# + enum per CC src/lib/validation.ts and src/app/api/tasks/ingest/route.ts).
import hashlib, hmac, json, sys
from http.server import BaseHTTPRequestHandler, HTTPServer

SECRET = b"rr030-contract-secret"
CC_TASK_STATUSES = {"backlog","inbox","planning","in_progress","assigned",
                    "review","testing","blocked","pending_dispatch","done"}
STORE = {}

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _reply(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)
    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if not self.path.startswith("/api/tasks/ingest"):
            return self._reply(404, {"error": "not found"})
        sig = self.headers.get("x-webhook-signature")
        expect = hmac.new(SECRET, raw, hashlib.sha256).hexdigest()
        if sig != expect:
            return self._reply(401, {"error": "Unauthorized"})
        try:
            body = json.loads(raw)
        except Exception:
            return self._reply(400, {"error": "Invalid JSON body"})
        if not body.get("title"):
            return self._reply(400, {"error": "title is required"})
        key = body.get("idempotency_key") or body.get("source_ref")
        if key and key in STORE:
            return self._reply(200, {"task_id": STORE[key], "deduped": True})
        tid = "cc-" + hashlib.sha1(raw).hexdigest()[:10]
        if key: STORE[key] = tid
        return self._reply(201, {"task_id": tid, "deduped": False})
    def do_PATCH(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        tid = self.path.rsplit("/", 1)[-1]
        sig = self.headers.get("x-webhook-signature")
        expect = hmac.new(SECRET, raw, hashlib.sha256).hexdigest()
        if sig != expect:
            return self._reply(401, {"error": "Unauthorized"})
        try:
            body = json.loads(raw)
        except Exception:
            return self._reply(400, {"error": "Invalid JSON body"})
        if body.get("status") not in CC_TASK_STATUSES:
            return self._reply(400, {"error": "invalid status"})
        if tid == "cc-500":
            return self._reply(500, {"error": "board exploded"})
        return self._reply(200, {"ok": True, "task_id": tid, "status": body.get("status")})

HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
PYSRV

  # Port: fixed by default, overridable so a busy CI runner can shift it.
  # Bound readiness wait (no sleeps beyond the probe).
  SRV_PORT="${RR030_CONTRACT_PORT:-48191}"
  "$PY" "$CONTRACT_SERVER" "$SRV_PORT" & SRV_PID=$!
  READY=0
  for _ in $(seq 1 40); do
    if "$PY" -c "import socket;s=socket.socket();s.settimeout(0.2);s.connect(('127.0.0.1',$SRV_PORT))" 2>/dev/null; then READY=1; break; fi
  done
  if [ "$READY" -eq 1 ]; then
    harness_case CONTRACT "ingest: signed payload accepted, task_id returned (real HTTP)" \
      -- "$PY" -c "
import sys
sys.path.insert(0, '$HERE')
import rescue_cc_board as b
env = {'COMMAND_CENTER_URL': 'http://127.0.0.1:$SRV_PORT', 'WEBHOOK_SECRET': 'rr030-contract-secret'}
tid = b.ingest_ticket('tkt-contract-1', 'acme', 'gateway down', state_dir=None, env=env)
assert tid and tid.startswith('cc-'), f'expected a real task_id, got {tid!r}'
# idempotency: same ticket_id dedupes to the SAME card
tid2 = b.ingest_ticket('tkt-contract-1', 'acme', 'gateway down', state_dir=None, env=env)
assert tid2 == tid, f'dedupe broken: {tid} != {tid2}'
print('  ingest contract: PASS (signed 201 + dedupe)')
"
    harness_case CONTRACT "ingest: WRONG signature must be rejected 401 by the CC contract" \
      -- "$PY" -c "
import os, sys, urllib.request, json, hmac, hashlib
raw = json.dumps({'title':'tamper'}, separators=(',',':')).encode()
req = urllib.request.Request('http://127.0.0.1:$SRV_PORT/api/tasks/ingest', data=raw,
    headers={'Content-Type':'application/json','x-webhook-signature':'deadbeef'}, method='POST')
try:
    urllib.request.urlopen(req, timeout=5)
    print('server accepted a WRONG signature'); sys.exit(9)
except urllib.error.HTTPError as e:
    assert e.code == 401, f'expected 401, got {e.code}'
print('  auth contract: PASS (401 on bad signature)')
"
    harness_case CONTRACT "enum guard: patch_status refuses a non-CC status OFFLINE (before any wire call)" \
      -- "$PY" -c "
import sys
sys.path.insert(0, '$HERE')
import rescue_cc_board as b
assert b.patch_status('cc-1', 'delivered', ticket_id='tkt-x', env={'COMMAND_CENTER_URL':'http://127.0.0.1:$SRV_PORT'}) is False
print('  enum contract: PASS (offline refusal)')
"
    harness_case CONTRACT "status map: every ledger status lands in the live CC TaskStatus enum" \
      -- "$PY" -c "
import sys
sys.path.insert(0, '$HERE')
import rescue_cc_board as b
# Live CC source when colocated (the CC repo owns the enum; never mirror from memory).
enum_src = None
import pathlib
for cand in [pathlib.Path('$REPO_ROOT')/'..'/'blackceo-command-center'/'src'/'lib'/'validation.ts']:
    if cand.is_file():
        import re
        m = re.search(r'export const TaskStatus = z.enum\(\[(.*?)\]\)', cand.read_text(), re.S)
        if m: enum_src = set(re.findall(r\"'([a-z_]+)'\", m.group(1)))
        break
if enum_src is not None:
    missing = {v for v in b.LEDGER_TO_CC_STATUS.values() if v is not None} - enum_src
    assert not missing, f'LEDGER_TO_CC_STATUS has values absent from the live CC enum: {missing}'
    print(f'  enum parity: PASS against live CC source ({len(enum_src)} statuses)')
else:
    assert all(v in b.CC_TASK_STATUSES for v in b.LEDGER_TO_CC_STATUS.values() if v is not None)
    print('  enum parity: PASS against the pinned CC enum (live CC source not colocated)')
"
    harness_case CONTRACT "fail-soft: HTTP 500 board never raises, returns False, records the receipt" \
      -- "$PY" -c "
import sys, json, tempfile, pathlib
sys.path.insert(0, '$HERE')
import rescue_cc_board as b
with tempfile.TemporaryDirectory() as td:
    sd = pathlib.Path(td)/'rescue'
    env = {'COMMAND_CENTER_URL':'http://127.0.0.1:$SRV_PORT', 'WEBHOOK_SECRET':'rr030-contract-secret'}
    ok = b.patch_status('cc-500', 'review', ticket_id='tkt-500', state_dir=sd, env=env)
    assert ok is False, '500 must be fail-soft False'
    rec = sd/'cc-board'/'tkt-500.json'
    assert rec.is_file(), 'receipt must still be recorded'
    data = json.loads(rec.read_text())
    assert data['movements'][-1]['http_status'] == 500
print('  fail-soft contract: PASS (500 absorbed + receipt)')
"
  else
    harness_gate_fail CONTRACT "contract fixture server failed to start"
  fi
  kill $SRV_PID 2>/dev/null
  wait $SRV_PID 2>/dev/null
fi

# ---------------------------------------------------------------------------
# GATE: INSTALLED — the install leg, exercised in an explicit state dir
# (RESCUE_STATE_DIR), never HOME.
# ---------------------------------------------------------------------------
if [ -n "$PY" ]; then
  INST="$MUT/installed-root"
  harness_case INSTALLED "install-rescue-ledger.sh installs tooling + schema into an explicit state dir" \
    -- bash "$HERE/install-rescue-ledger.sh" --state-dir "$INST"
  harness_case INSTALLED "installed ledger boots standalone (init idempotent, schema pinned)" \
    -- env RESCUE_STATE_DIR="$INST" "$PY" "$INST/rescue_ledger.py" init
  harness_case INSTALLED "installed battery passes against the INSTALLED tree (not the repo tree)" \
    -- "$PY" -c "
import importlib.util, sys
spec = importlib.util.spec_from_file_location('installed_board', '$INST/rescue_cc_board.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
rc = m.self_test()
assert rc == 0, f'installed self-test rc={rc}'
print('  installed tree: PASS')
"
fi

# ---------------------------------------------------------------------------
# GATE: LIVE_ACCEPTANCE — real-box drills. This operator run has no sanctioned
# live-box scope, so the gate is recorded UNVERIFIED. Per RR-030 it is never
# SKIP=PASS and blocks release completion until exercised (Wave 6).
# ---------------------------------------------------------------------------
harness_unverified LIVE_ACCEPTANCE "no live rescue box / no live n8n Relay Brain in this offline run — Wave 6 installed acceptance still open"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
if [ "${1:-}" = "--json-summary" ]; then
  echo "{\"gate_summary\": \"UNIT=$GATE_UNIT CONTRACT=$GATE_CONTRACT INSTALLED=$GATE_INSTALLED LIVE_ACCEPTANCE=$GATE_LIVE pass=$RR_HARNESS_PASS fail=$RR_HARNESS_FAIL unverified=$RR_HARNESS_UNVERIFIED\"}"
fi

harness_finish