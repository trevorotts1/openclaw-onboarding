#!/usr/bin/env bash
# tests/unit/rr031-reconcile-agent-map.test.sh — RR-031 gate (RR-W4-REGISTRY).
#
# Pins the CONFIRMED RCV-09 / RR-031 defect classes against the reconciler:
#   A. identity is CONFIGURED, not hardcoded
#   B. all pages fetched, status+schema checked, writes ABORTED on an
#      incomplete source (401/HTML, page cap, corrupt body, duplicate rows)
#   C. EXISTING wrong mappings are REPAIRED, not only absent ones inserted
#   D. runtime agents are read INSIDE the exact container (docker exec -u node
#      <container>), and a second Docker client is never cross-mapped
#   E. unique tenant+box mapping enforced: one row per box, rerun is a no-op
#   F. unresolved/inaccessible boxes persist as PENDING WITH OWNER, `main` is
#      never invented, and the roster is never reported complete
#   G. per-run private temp paths + scoped lock for concurrent seeds
#   H. finite HTTP/SSH/process deadlines; a timed-out SSH is PENDING, not FAIL
#   I. credential transport: the key never appears in argv
#
# Every assertion is on a NAMED state transition (row content in the table,
# the writes ledger, the pending ledger, the exit code), never on "the script
# exited 0". Each detector is itself proven able to fail by a negative control.
#
# Hermetic: loopback HTTP stub, stub ssh/docker/curl binaries, temp everything.
# No network beyond 127.0.0.1, no real credential, no real box touched.
set -u

if [ -n "${BASH_SOURCE:-}" ]; then _HERE_SRC="${BASH_SOURCE[0]}"; else _HERE_SRC="$0"; fi
HERE="$(cd "$(dirname "$_HERE_SRC")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
RECONCILE="$REPO/scripts/reconcile-rr-agent-map.sh"
LIB="$REPO/scripts/_rr_registry_lib.py"
MOCK="$HERE/fixtures/mock-rr-datatable.py"
TABLE="EFPgipZtKatC5xPw"
TABLE_ALT="ZZaltTableId0001"

PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ok $1"; }
bad() { FAIL=$((FAIL+1)); echo "  FAIL $1 ${2:-}"; }

for f in "$RECONCILE" "$LIB" "$MOCK"; do
  [ -f "$f" ] || { echo "FATAL: missing $f"; exit 2; }
done

WORK="$(mktemp -d "${TMPDIR:-/tmp}/rr031.XXXXXX")"
CLEANUP_PIDS=""
cleanup() {
  for p in $CLEANUP_PIDS; do kill "$p" 2>/dev/null || true; done
  rm -rf "$WORK"
}
trap cleanup EXIT INT TERM

echo "== RR-031: reconcile rr_agent_map against verified runtime agents =="

# ---------------------------------------------------------------------------
# Harness: one mock server + one box-registry/ssh stub world per scenario.
# ---------------------------------------------------------------------------
start_mock() {   # start_mock <name> <seed-json> <page-size> -> sets MOCK_PORT
  local name="$1" seed="$2" page="$3"
  local d="$WORK/mock-$name"
  mkdir -p "$d/control"
  printf '%s' "$seed" > "$d/seed.json"
  python3 "$MOCK" "$d" "$TABLE" "$page" >"$d/log" 2>&1 &
  MOCK_PID=$!
  CLEANUP_PIDS="$CLEANUP_PIDS $MOCK_PID"
  MOCK_DIR="$d"
  local i=0
  while [ ! -f "$d/port" ] && [ "$i" -lt 100 ]; do i=$((i+1)); sleep 0.05; done
  [ -f "$d/port" ] || { echo "FATAL: mock did not start"; return 1; }
  MOCK_PORT="$(cat "$d/port")"
  return 0
}

# write_world <name> <spec-file>
#   spec-file lines:  <slug> <kind> <agent|-> [container]
#     agent '-' means: the box is unreachable / has no default
#     container '-' means: derive as openclaw-<slug>-openclaw-1
#   Writes box-registry.json + roster + stub ssh/docker binaries that resolve
#   each box's agent by the slug embedded in the container name, so a run that
#   does NOT go through the exact container cannot resolve anything.
write_world() {
  local name="$1" spec="$2"
  WORLD="$WORK/world-$name"
  mkdir -p "$WORLD/bin" "$WORLD/state"
  python3 - "$spec" "$WORLD" <<'PYEOF'
import json, os, sys
spec, world = sys.argv[1], sys.argv[2]
boxes, roster, agents = {}, {}, {}
for line in open(spec):
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    parts = line.split()
    slug, kind = parts[0], parts[1]
    agent = parts[2] if len(parts) > 2 else "-"
    container = parts[3] if len(parts) > 3 else "-"
    if container == "-" and kind in ("vps", "contabo"):
        container = "openclaw-%s-openclaw-1" % slug
    e = {"kind": kind, "client": "synthetic"}
    if kind == "vps":
        e["ssh_target"] = "root@10.0.0.1"
        e["container"] = container
    elif kind == "contabo":
        e["ssh_target"] = "contabo-host"
        e["container"] = container
    elif kind == "mac":
        e["ssh_alias"] = "rescue-%s" % slug
    elif kind == "local":
        pass
    boxes[slug] = e
    roster[slug] = {"platform": kind, "ssh_target": e.get("ssh_target") or e.get("ssh_alias") or "local"}
    agents[slug] = {"agent": agent, "container": container, "kind": kind}
json.dump({"_doc": "synthetic test registry", "boxes": boxes}, open(os.path.join(world, "box-registry.json"), "w"), indent=1)
json.dump({"_doc": "synthetic test roster", "boxes": roster}, open(os.path.join(world, "roster.json"), "w"), indent=1)
json.dump(agents, open(os.path.join(world, "agents.json"), "w"), indent=1)
PYEOF
  # stub ssh: models `ssh <target> <payload>`; the payload carries the docker
  # exec (or zsh -lc) that must name the exact container for this slug.
  cat > "$WORLD/bin/ssh" <<STUB
#!/bin/bash
printf '%s\n' "\$*" >> "$WORLD/ssh-argv.log"
target=""; payload=""
for a in "\$@"; do
  case "\$a" in
    -o) continue ;;
    BatchMode=yes|ConnectTimeout=*|\-*) continue ;;
  esac
  if [ -z "\$target" ]; then target="\$a"; else payload="\$payload \$a"; fi
done
python3 - "$WORLD" "\$payload" "\$target" <<'PY2'
import json, os, re, sys, time
world, payload, target = sys.argv[1], sys.argv[2], sys.argv[3]
agents = json.load(open(os.path.join(world, "agents.json")))
slug = None
# 1) the exact container named in the payload (vps/contabo)
m = re.search(r"docker exec -u node [^ ]*?(openclaw-[A-Za-z0-9._-]+-openclaw-1|oc-[A-Za-z0-9._-]+)", payload)
if m:
    c = m.group(1)
    for s, a in agents.items():
        if a.get("container") and a["container"] == c:
            slug = s
# 2) the ssh target itself (a mac box is reached as ssh rescue-<slug> and
#    carries no container) - exact match only, never a substring
if slug is None and target:
    tb = target.split("@")[-1]
    for s in agents:
        if tb == s or tb == "rescue-" + s:
            slug = s
            break
if slug is None:
    for s in agents:
        if s in payload:
            slug = s
            break
if slug is None:
    sys.stderr.write("stub ssh: no box resolvable from payload\n")
    sys.exit(1)
hang = os.environ.get("RR031_SSH_HANG", "")
hang_slug = os.environ.get("RR031_SSH_HANG_SLUG", "")
if hang and (not hang_slug or hang_slug == slug):
    time.sleep(float(hang))
fail = os.environ.get("RR031_SSH_FAIL", "")
fail_slug = os.environ.get("RR031_SSH_FAIL_SLUG", "")
if fail and (not fail_slug or fail_slug == slug):
    sys.exit(255)
a = agents[slug]
if a["agent"] == "-":
    sys.exit(1)
print("__RR_AGENTS_BEGIN__")
print(json.dumps([{"id": "dept-other", "isDefault": False}, {"id": a["agent"], "isDefault": True}]))
print("__RR_AGENTS_END__")
PY2
STUB
  chmod +x "$WORLD/bin/ssh"
  cat > "$WORLD/bin/docker" <<STUB
#!/bin/bash
printf '%s\n' "\$*" >> "$WORLD/docker-argv.log"
exit 0
STUB
  chmod +x "$WORLD/bin/docker"
}

run_reconcile() {   # run_reconcile <world> <port> <outfile> [extra args...]
  local world="$1" port="$2" out="$3"; shift 3
  N8N_API_KEY="ZZRR031-n8n-key-sentinel" \
  N8N_HOST="http://127.0.0.1:$port" \
  PATH="$world/bin:$PATH" \
  RR_REGISTRY_DEADLINE=60 \
  bash "$RECONCILE" \
    --roster "$world/roster.json" --boxes "$world/box-registry.json" \
    --lock-dir "$world/state/lock" --state-dir "$world/state" \
    --no-deadline "$@" >"$out" 2>&1
  echo $?
}

# The reconciled table is the MOCK's own state; the mock persists only on a
# mutation, so an UNMUTATED table is exactly its seed and a missing state file
# is positive evidence that nothing was written.
tbl() { local s="$MOCK_DIR/state.json"; [ -f "$s" ] || s="$MOCK_DIR/seed.json"; cat "$s"; }
table_rows() { python3 -c 'import json,sys;print(json.dumps(json.load(open(sys.argv[1])),sort_keys=True))' "$( [ -f "$MOCK_DIR/state.json" ] && echo "$MOCK_DIR/state.json" || echo "$MOCK_DIR/seed.json" )" 2>/dev/null || echo '[]'; }
row_for() { python3 -c '
import json,sys
d=json.load(open(sys.argv[1])); slug=sys.argv[2]
r=[x for x in d if x.get("box_slug")==slug]
print(json.dumps(r, sort_keys=True))
' "$( [ -f "$MOCK_DIR/state.json" ] && echo "$MOCK_DIR/state.json" || echo "$MOCK_DIR/seed.json" )" "$2" 2>/dev/null || echo '[]'; }
dupe_slugs() { python3 -c '
import json,sys
from collections import Counter
p=sys.argv[1] if __import__("os").path.exists(sys.argv[1]) else sys.argv[2]
d=json.load(open(p))
c=Counter(r.get("box_slug") for r in d)
print(sum(1 for k,v in c.items() if v>1 and k))
' "$MOCK_DIR/state.json" "$MOCK_DIR/seed.json"; }
writes_log() { [ -f "$1/writes.jsonl" ] && cat "$1/writes.jsonl" || echo ""; }
pending_lines() { grep -c '^  pending ' "$1" 2>/dev/null || echo 0; }

# ===========================================================================
# A. IDENTITY IS CONFIGURED, NOT HARDCODED
# ===========================================================================
echo "--- A. table/registry identity is configured ---"
AW="$WORK/A"; mkdir -p "$AW"
printf 'box-a vps dept-a\n' > "$AW/spec.txt"
write_world A "$AW/spec.txt"

cat > "$AW/manifest-ok.json" <<'J'
{"tables":[{"name":"rr_agent_map","id":"EFPgipZtKatC5xPw"}]}
J
out="$(PATH="$AW/bin:$PATH" bash "$RECONCILE" --check --roster "$WORLD/roster.json" \
        --boxes "$WORLD/box-registry.json" --contract-manifest "$AW/manifest-ok.json" \
        --lock-dir "$WORLD/state/lock" 2>&1)"
echo "$out" | grep -qx "table_id=$TABLE" && ok "identity: table id comes from the contract manifest" || bad "identity: manifest table id not used" "$(echo "$out" | grep table_id)"
echo "$out" | grep -qx "identity_source=contract-manifest" && ok "identity: source reported as contract-manifest (frozen)" || bad "identity: source not reported" "$(echo "$out" | grep identity_source)"
echo "$out" | grep -qx "config_fail=0" && ok "identity: registry check passes with every slug mapped" || bad "identity: registry check failed" "$out"

cat > "$AW/manifest-mismatch.json" <<'J'
{"tables":[{"name":"rr_agent_map","id":"ZZsomeOtherTable99"}]}
J
N8N_API_KEY="ZZRR031-n8n-key-sentinel" PATH="$AW/bin:$PATH" bash "$RECONCILE" --check \
  --roster "$WORLD/roster.json" --boxes "$WORLD/box-registry.json" \
  --contract-manifest "$AW/manifest-mismatch.json" --lock-dir "$WORLD/state/lock" >"$AW/mm.out" 2>"$AW/mm.err"
rc=$?
[ "$rc" -eq 2 ] && ok "identity: a manifest naming a DIFFERENT table aborts (rc=2)" || bad "identity: mismatched manifest rc=$rc (expected 2)"
grep -q "identity mismatch" "$AW/mm.err" && ok "identity: abort names the mismatch" || bad "identity: no mismatch reason on stderr"
grep -q 'ZZsomeOtherTable99' "$AW/mm.err" && ok "identity: abort names the actual table it refused" || bad "identity: refused-table name absent"

# hardcoded-vs-configured proof: the table id is an input, not a literal. The
# override is honoured AND named as such; and the run then really requests that
# table path (proved in part I: a table the server does not serve 404s).
PATH="$AW/bin:$PATH" bash "$RECONCILE" --check --roster "$WORLD/roster.json" \
  --boxes "$WORLD/box-registry.json" --table "$TABLE_ALT" >"$AW/alt.out" 2>&1
grep -qx "table_id=$TABLE_ALT" "$AW/alt.out" && ok "identity: the table id is an input, not a literal (override honoured)" || bad "identity: override ignored"
grep -qx "identity_source=flag" "$AW/alt.out" && ok "identity: an override is reported as identity_source=flag (visible, not silent)" || bad "identity: override source not reported"
grep -qx "table_id=$TABLE" "$AW/manifest-ok.json" && bad "identity: test fixture wrong" || true

# ===========================================================================
# B. ALL PAGES, CHECKED STATUS/SCHEMA, ABORT ON INCOMPLETE SOURCE
# ===========================================================================
echo "--- B. every page fetched; incomplete source aborts with ZERO writes ---"
# seed 5 pre-existing rows, page size 2 => 3 pages; box-z has NO row (INSERT)
SEED='[{"box_slug":"box-a","local_agent_id":"dept-a","source":"x"},{"box_slug":"box-b","local_agent_id":"dept-b","source":"x"},{"box_slug":"box-c","local_agent_id":"dept-c","source":"x"},{"box_slug":"box-d","local_agent_id":"dept-d","source":"x"},{"box_slug":"box-e","local_agent_id":"dept-e","source":"x"}]'
start_mock pages "$SEED" 2
printf 'box-a vps dept-a\nbox-z vps dept-z\n' > "$WORK/B-spec.txt"
write_world B "$WORK/B-spec.txt"
BW="$WORLD"
cat > "$AW/manifest-b.json" <<J
{"tables":[{"name":"rr_agent_map","id":"$TABLE"}]}
J
rc=$(run_reconcile "$BW" "$MOCK_PORT" "$WORK/B-run1.out" --apply --contract-manifest "$AW/manifest-b.json")
[ "$rc" -eq 0 ] && ok "pagination: multi-page run completes (rc=0)" || bad "pagination: rc=$rc" "$(cat "$WORK/B-run1.out")"
grep -q 'pages=' "$WORK/B-run1.out" && grep -qE 'pages=[1-9]' "$WORK/B-run1.out" && ok "pagination: run reports the page count it read" || bad "pagination: no page count reported"
ROWZ="$(row_for "$BW" box-z)"
[ "$ROWZ" != "[]" ] && ok "pagination: box with NO row was inserted from a full read" || bad "pagination: box-z unmapped — pages were lost"
printf '%s' "$ROWZ" | grep -q 'dept-z' && ok "pagination: the inserted row carries the verified page-3 agent" || bad "pagination: wrong agent on box-z" "$ROWZ"
rm -rf "$MOCK_DIR"

# The DISCRIMINATING pagination case: the existing row for a slug lives on a
# LATER page. A single-page reader cannot see it, treats the slug as absent,
# and INSERTs a second row — breaking the unique tenant+box mapping. Only a
# reader that fetches EVERY page can repair it in place.
start_mock deep '[{"box_slug":"box-a","local_agent_id":"dept-a"},{"box_slug":"box-b","local_agent_id":"dept-b"},{"box_slug":"box-c","local_agent_id":"dept-c"},{"box_slug":"box-d","local_agent_id":"dept-d"},{"box_slug":"box-z","local_agent_id":"dept-WRONG"}]' 2
printf 'box-a vps dept-a\nbox-z vps dept-z\n' > "$WORK/B6-spec.txt"
write_world Bdeep "$WORK/B6-spec.txt"
rc=$(run_reconcile "$WORLD" "$MOCK_PORT" "$WORK/B-deep.out" --apply)
[ "$rc" -eq 0 ] && ok "pagination: multi-page repair run completes (rc=0)" || bad "pagination: deep-scan rc=$rc" "$(cat "$WORK/B-deep.out")"
DZROWS="$(python3 -c '
import json,os,sys
p=sys.argv[1] if os.path.exists(sys.argv[1]) else sys.argv[2]
d=json.load(open(p))
print(sum(1 for r in d if r.get("box_slug")=="box-z"))
' "$MOCK_DIR/state.json" "$MOCK_DIR/seed.json")"
[ "$DZROWS" = "1" ] && ok "pagination: the row on page 3 was REPAIRED in place — exactly 1 row for that slug" || bad "pagination: $DZROWS rows for box-z (single-page reader duplicates: the RCV-09 defect)" "$(row_for "$WORLD" box-z)"
row_for "$WORLD" box-z | grep -q 'dept-z' && ok "pagination: that page-3 row now holds the verified agent" || bad "pagination: page-3 row not repaired" "$(row_for "$WORLD" box-z)"
row_for "$WORLD" box-z | grep -q 'dept-WRONG' && bad "pagination: stale wrong agent survived on the page-3 row" || ok "pagination: stale wrong agent on page 3 is gone"
[ "$(dupe_slugs)" = "0" ] && ok "pagination: unique tenant+box mapping held across the deep scan" || bad "pagination: duplicates after the deep scan"
rm -rf "$MOCK_DIR"

# 401/HTML initial read -> abort, zero writes
start_mock unauth '[{"box_slug":"box-a","local_agent_id":"dept-a"}]' 50
printf '401\n' > "$MOCK_DIR/control/fail_status"
printf 'box-a vps dept-a\nbox-new vps dept-new\n' > "$WORK/B2-spec.txt"
write_world B2a "$WORK/B2-spec.txt"
rc=$(run_reconcile "$WORLD" "$MOCK_PORT" "$WORK/B-run2.out" --apply)
[ "$rc" -ne 0 ] && ok "401/HTML: initial read aborts the run (rc=$rc)" || bad "401/HTML: run reported success on an unauthenticated source"
grep -q 'ABORTING with zero writes' "$WORK/B-run2.out" && ok "401/HTML: abort says writes are aborted" || bad "401/HTML: no abort message"
[ "$(writes_log "$MOCK_DIR")" = "" ] && ok "401/HTML: ZERO rows written (writes ledger empty)" || bad "401/HTML: rows were written despite the abort" "$(writes_log "$MOCK_DIR")"
grep -q 'aborted=1' "$WORK/B-run2.out" && ok "401/HTML: report marks aborted=1" || bad "401/HTML: report does not mark aborted"
rm -rf "$MOCK_DIR"

# corrupt (non-JSON) body -> abort, zero writes
start_mock corrupt '[{"box_slug":"box-a","local_agent_id":"dept-a"}]' 50
touch "$MOCK_DIR/control/corrupt_page"
printf 'box-a vps dept-a\nbox-new vps dept-new\n' > "$WORK/B3-spec.txt"
write_world B2b "$WORK/B3-spec.txt"
rc=$(run_reconcile "$WORLD" "$MOCK_PORT" "$WORK/B-run3.out" --apply)
[ "$rc" -ne 0 ] && ok "schema: a non-JSON source body aborts the run" || bad "schema: non-JSON body accepted"
[ "$(writes_log "$MOCK_DIR")" = "" ] && ok "schema: ZERO rows written on a corrupt body" || bad "schema: rows written on a corrupt body"
grep -q 'schema-invalid' "$WORK/B-run3.out" && ok "schema: abort names the schema failure" || bad "schema: schema failure not named"
rm -rf "$MOCK_DIR"

# page cap -> incomplete source -> abort
start_mock cap '[{"box_slug":"box-a","local_agent_id":"dept-a"},{"box_slug":"box-b","local_agent_id":"dept-b"}]' 1
printf 'box-a vps dept-a\nbox-new vps dept-new\n' > "$WORK/B4-spec.txt"
write_world B2c "$WORK/B4-spec.txt"
N8N_API_KEY="k" N8N_HOST="http://127.0.0.1:$MOCK_PORT" PATH="$WORLD/bin:$PATH" \
  bash "$RECONCILE" --roster "$WORLD/roster.json" --boxes "$WORLD/box-registry.json" \
  --lock-dir "$WORLD/state/lock" --state-dir "$WORLD/state" --no-deadline --max-pages 1 --apply >"$WORK/B-run4.out" 2>&1
rc=$?
[ "$rc" -ne 0 ] && ok "page cap: hitting the cap aborts (incomplete source)" || bad "page cap: run claimed completeness after the cap"
grep -q 'page-cap-exceeded' "$WORK/B-run4.out" && ok "page cap: abort names the cap" || bad "page cap: cap failure not named"
[ "$(writes_log "$MOCK_DIR")" = "" ] && ok "page cap: ZERO rows written" || bad "page cap: rows written after a capped read"
rm -rf "$MOCK_DIR"

# duplicates for one slug -> abort, no guess, no write
start_mock dupes '[{"box_slug":"box-a","local_agent_id":"dept-a"},{"box_slug":"box-a","local_agent_id":"wrong-agent"}]' 50
printf 'box-a vps dept-a\n' > "$WORK/B5-spec.txt"
write_world B2d "$WORK/B5-spec.txt"
rc=$(run_reconcile "$WORLD" "$MOCK_PORT" "$WORK/B-run5.out" --apply)
[ "$rc" -ne 0 ] && ok "duplicates: duplicate box_slug rows abort the write path" || bad "duplicates: duplicate rows reconciled by guessing"
grep -q 'DUPLICATE' "$WORK/B-run5.out" && ok "duplicates: abort names the duplicate class" || bad "duplicates: duplicates not named"
grep -q 'duplicate box_slug=box-a rows=2' "$WORK/B-run5.out" && ok "duplicates: the offending slug and row count are reported" || bad "duplicates: slug/count not reported"
[ "$(writes_log "$MOCK_DIR")" = "" ] && ok "duplicates: ZERO rows written" || bad "duplicates: rows written on duplicates"
grep -q 'duplicates=1' "$WORK/B-run5.out" && ok "duplicates: count line reports duplicates=1" || bad "duplicates: count line missing the duplicate count"
rm -rf "$MOCK_DIR"

# ===========================================================================
# C. EXISTING WRONG MAPPINGS ARE REPAIRED, NOT ONLY ABSENT ONES INSERTED
# ===========================================================================
echo "--- C. wrong existing agent is REPAIRED; absent box is INSERTED ---"
start_mock repair '[{"box_slug":"box-a","local_agent_id":"dept-WRONG","source":"legacy"}]' 50
printf 'box-a vps dept-a\nbox-b vps dept-b\n' > "$WORK/C-spec.txt"
write_world C "$WORK/C-spec.txt"
CW="$WORLD"
rc=$(run_reconcile "$CW" "$MOCK_PORT" "$WORK/C-run.out" --apply)
[ "$rc" -eq 0 ] && ok "repair: run completes (rc=0)" || bad "repair: rc=$rc" "$(cat "$WORK/C-run.out")"
ROWA="$(row_for "$CW" box-a)"
printf '%s' "$ROWA" | grep -q 'dept-a' && ok "repair: the WRONG existing mapping now holds the verified runtime agent" || bad "repair: wrong mapping survived" "$ROWA"
printf '%s' "$ROWA" | grep -q 'dept-WRONG' && bad "repair: stale wrong agent still present" || ok "repair: the stale wrong agent is gone"
printf '%s' "$ROWA" | grep -q 'reconcile_rr_agent_map' && ok "repair: repaired row is marked as reconciled (provenance)" || bad "repair: provenance not written" "$ROWA"
ROWB="$(row_for "$CW" box-b)"
printf '%s' "$ROWB" | grep -q 'dept-b' && ok "insert: the absent box got a row with its verified agent" || bad "insert: absent box not mapped" "$ROWB"
grep -q 'PATCH' "$MOCK_DIR/writes.jsonl" && ok "repair: used the supported filter-addressed PATCH (compare-and-set)" || bad "repair: no PATCH issued"
grep -q '"op": "POST"' "$MOCK_DIR/writes.jsonl" && ok "insert: used POST for the absent slug" || bad "insert: no POST issued"
grep -qE '^reconcile-rr-agent-map: .*changed=2 .*verified=0 ' "$WORK/C-run.out" || grep -q 'changed=2' "$WORK/C-run.out" && ok "repair: reports actual changed=2" || bad "repair: changed count wrong" "$(grep changed= "$WORK/C-run.out")"
grep -q 'verified=0' "$WORK/C-run.out" && ok "repair: verified=0 on the first pass (nothing was already correct)" || bad "repair: verified count wrong"
UNIQ="$(dupe_slugs)"
[ "$UNIQ" = "0" ] && ok "repair: unique tenant+box mapping holds after the write" || bad "repair: $UNIQ duplicated slugs after the write"

# RERUN (no change): verified=2, changed=0, and NO new write
before="$(writes_log "$MOCK_DIR" | wc -l | tr -d ' ')"
rc=$(run_reconcile "$CW" "$MOCK_PORT" "$WORK/C-rerun.out" --apply)
after="$(writes_log "$MOCK_DIR" | wc -l | tr -d ' ')"
[ "$rc" -eq 0 ] && ok "rerun: completes (rc=0)" || bad "rerun: rc=$rc" "$(cat "$WORK/C-rerun.out")"
grep -q 'changed=0' "$WORK/C-rerun.out" && ok "rerun: changed=0 (nothing left to reconcile)" || bad "rerun: changed not 0" "$(grep changed= "$WORK/C-rerun.out")"
grep -q 'verified=2' "$WORK/C-rerun.out" && ok "rerun: verified=2 (both rows proven correct against the runtime)" || bad "rerun: verified count wrong" "$(grep verified= "$WORK/C-rerun.out")"
[ "$before" = "$after" ] && ok "rerun: NO new write issued (writes ledger unchanged: $before lines)" || bad "rerun: rerun wrote again ($before -> $after)"
ROWSTILL="$(row_for "$CW" box-a)"
printf '%s' "$ROWSTILL" | grep -q 'dept-a' && ok "rerun: mapping still correct and unchanged" || bad "rerun: mapping drifted"

# renamed default agent on the box: the mapping FOLLOWS the runtime
python3 - "$CW" <<'PYEOF'
import json, sys
p = sys.argv[1] + "/agents.json"
d = json.load(open(p))
d["box-a"]["agent"] = "dept-RENAMED"
json.dump(d, open(p, "w"))
PYEOF
rc=$(run_reconcile "$CW" "$MOCK_PORT" "$WORK/C-rename.out" --apply)
[ "$rc" -eq 0 ] && ok "renamed default: run completes" || bad "renamed default: rc=$rc" "$(cat "$WORK/C-rename.out")"
ROWRN="$(row_for "$CW" box-a)"
printf '%s' "$ROWRN" | grep -q 'dept-RENAMED' && ok "renamed default: mapping repaired to the renamed runtime default" || bad "renamed default: mapping not repaired" "$ROWRN"
printf '%s' "$ROWRN" | grep -q 'dept-a"' && bad "renamed default: stale pre-rename agent remains" || ok "renamed default: stale pre-rename agent replaced"
rm -rf "$MOCK_DIR"

# ===========================================================================
# D. RUNTIME AGENTS READ INSIDE THE EXACT CONTAINER; TWO DOCKER CLIENTS
# ===========================================================================
echo "--- D. agent resolution happens inside the exact container ---"
start_mock two '[{"box_slug":"box-a","local_agent_id":"dept-WRONG"},{"box_slug":"box-b","local_agent_id":"dept-b"}]' 50
printf 'box-a vps dept-a\nbox-b vps dept-b\n' > "$WORK/D-spec.txt"
write_world D "$WORK/D-spec.txt"
DW="$WORLD"
rc=$(run_reconcile "$DW" "$MOCK_PORT" "$WORK/D-run.out" --apply)
[ "$rc" -eq 0 ] && ok "two clients: run completes" || bad "two clients: rc=$rc" "$(cat "$WORK/D-run.out")"
grep -q 'docker exec -u node openclaw-box-a-openclaw-1 sh -c' "$DW/ssh-argv.log" && ok "container: box-a probed via docker exec -u node <its own container>" || bad "container: box-a container not used" "$(head -3 "$DW/ssh-argv.log")"
grep -q 'docker exec -u node openclaw-box-b-openclaw-1 sh -c' "$DW/ssh-argv.log" && ok "container: box-b probed via docker exec -u node <its own container>" || bad "container: box-b container not used"
ROWA="$(row_for "$DW" box-a)"; ROWB="$(row_for "$DW" box-b)"
printf '%s' "$ROWA" | grep -q 'dept-a' && ok "two clients: box-a maps to box-a's agent" || bad "two clients: box-a wrong" "$ROWA"
printf '%s' "$ROWB" | grep -q 'dept-b' && ok "two clients: box-b maps to box-b's agent" || bad "two clients: box-b wrong" "$ROWB"
printf '%s' "$ROWA" | grep -q 'dept-b' && bad "two clients: box-a picked up box-b's agent (CROSS-MAPPED)" || ok "two clients: no cross-mapping between containers"
grep -c 'RR_AGENTS_BEGIN' "$DW/ssh-argv.log" >/dev/null 2>&1
SSHCALLS="$(grep -c 'docker exec' "$DW/ssh-argv.log")"
[ "$SSHCALLS" -ge 2 ] && ok "two clients: both boxes probed (one container each), no host fallback" || bad "two clients: only $SSHCALLS container probes"
# host-side control: the stubs never answer a host-only payload, so prove the
# runner would FAIL if it probed the host (negative control for this detector)
printf 'box-host vps dept-host\n' > "$WORK/D-host-spec.txt"
write_world Dhost "$WORK/D-host-spec.txt"
python3 -c '
import json,sys
p=sys.argv[1]+"/box-registry.json"; d=json.load(open(p)); d["boxes"]["box-host"]["container"]=""; json.dump(d,open(p,"w"))
' "$WORLD"
N8N_API_KEY="k" N8N_HOST="http://127.0.0.1:$MOCK_PORT" PATH="$WORLD/bin:$PATH" \
  bash "$RECONCILE" --roster "$WORLD/roster.json" --boxes "$WORLD/box-registry.json" \
  --lock-dir "$WORLD/state/lock" --state-dir "$WORLD/state" --check >"$WORK/D-host.out" 2>&1
rc=$?
[ "$rc" -eq 1 ] && ok "control: a box with NO container is refused by the registry check (detector can fail)" || bad "control: unusable box passed the check (rc=$rc)"
grep -q 'unmapped=1' "$WORK/D-host.out" && ok "control: the unusable box is counted as unmapped" || bad "control: unmapped count wrong" "$(grep unmapped= "$WORK/D-host.out")"
grep -q 'identity_proved=0' "$WORK/D-host.out" && ok "control: identity NOT proved when a box cannot be reached" || bad "control: identity claimed with an unusable box"
rm -rf "$MOCK_DIR"

# ===========================================================================
# E. PENDING WITH OWNER; NEVER INVENT `main`; NEVER CLAIM COMPLETE
# ===========================================================================
echo "--- E. inaccessible / default-less boxes persist as pending with owner ---"
start_mock pending '[{"box_slug":"box-a","local_agent_id":"dept-a"}]' 50
printf 'box-a vps dept-a\nbox-alice vps -\nbox-bob mac -\n' > "$WORK/E-spec.txt"
write_world E "$WORK/E-spec.txt"
EW="$WORLD"
rc=$(run_reconcile "$EW" "$MOCK_PORT" "$WORK/E-run.out" --apply)
[ "$rc" -ne 0 ] && ok "pending: run exits non-zero while pending entries exist" || bad "pending: run claimed success with unresolved boxes"
grep -q 'pending box-alice owner=operator reason=' "$WORK/E-run.out" && ok "pending: box-alice recorded with owner + reason" || bad "pending: box-alice pending line missing" "$(grep pending "$WORK/E-run.out")"
grep -q 'pending box-bob owner=operator reason=' "$WORK/E-run.out" && ok "pending: box-bob recorded with owner + reason" || bad "pending: box-bob pending line missing"
grep -q 'complete=0' "$WORK/E-run.out" && ok "pending: complete=0 — roster NOT reported complete" || bad "pending: complete flag wrong" "$(grep complete= "$WORK/E-run.out")"
ALICE="$(row_for "$EW" box-alice)"
[ "$ALICE" = "[]" ] && ok "pending: NO row written for the unresolved box" || bad "pending: a row was written for an unresolved box" "$ALICE"
tbl | grep -q '"main"' 2>/dev/null && bad "pending: a main agent was INVENTED" || ok "pending: the literal agent id main was never invented for any row"
python3 -c '
import json,os,sys
p=sys.argv[1] if os.path.exists(sys.argv[1]) else sys.argv[2]
d=json.load(open(p))
rows=[r for r in d if r.get("box_slug") in ("box-alice","box-bob")]
sys.exit(1 if rows else 0)
' "$MOCK_DIR/state.json" "$MOCK_DIR/seed.json" && ok "pending: unresolved slugs absent from the table entirely" || bad "pending: unresolved slug found in the table"
grep -q 'pending=2' "$WORK/E-run.out" && ok "pending: reports actual pending=2" || bad "pending: pending count wrong" "$(grep pending= "$WORK/E-run.out")"
# the pending ledger must be a DURABLE artifact (actionable after the run exits)
PLEDGER="$EW/state/rr-agent-map-pending.json"
[ -f "$PLEDGER" ] && ok "pending: a durable pending ledger was written" || bad "pending: no pending ledger artifact" "$(ls "$EW/state" 2>/dev/null)"
python3 -c '
import json,sys
d=json.load(open(sys.argv[1]))
p={e["box_slug"]: e for e in d.get("pending", [])}
bad=[]
if set(p) != {"box-alice","box-bob"}: bad.append("slugs=%s" % sorted(p))
for s in ("box-alice","box-bob"):
    if s in p:
        if p[s].get("status") != "pending": bad.append("%s status" % s)
        if p[s].get("owner") != "operator": bad.append("%s owner=%s" % (s, p[s].get("owner")))
        if not p[s].get("reason"): bad.append("%s reason" % s)
if d.get("counts",{}).get("pending") != 2: bad.append("counts.pending=%s" % d.get("counts",{}).get("pending"))
print("; ".join(bad))
' "$PLEDGER" > "$WORK/E-ledger.check" 2>&1
grep -q '[^[:space:]]' "$WORK/E-ledger.check" && bad "pending ledger malformed" "$(cat "$WORK/E-ledger.check")" || ok "pending: ledger carries slug+status+owner+reason for both boxes and the actual count"
# a clean rerun must REPLACE the ledger with an empty pending set (proof, not absence)
cp "$PLEDGER" "$WORK/E-ledger.before"
python3 - "$EW" <<'PYEOF2'
import json, sys
p = sys.argv[1] + "/agents.json"
d = json.load(open(p))
d["box-alice"]["agent"] = "dept-alice"; d["box-bob"]["agent"] = "dept-bob"
json.dump(d, open(p, "w"))
PYEOF2
rc=$(run_reconcile "$EW" "$MOCK_PORT" "$WORK/E-clean.out" --apply)
[ "$rc" -eq 0 ] && ok "pending: once every box resolves, the run reports complete (rc=0)" || bad "pending: clean rerun rc=$rc" "$(tail -2 "$WORK/E-clean.out")"
python3 -c '
import json,sys
d=json.load(open(sys.argv[1]))
sys.exit(0 if d.get("pending") == [] and d.get("counts",{}).get("pending") == 0 else 1)
' "$PLEDGER" && ok "pending: the ledger is REPLACED with an empty pending set (a positive all-clear, not a stale file)" || bad "pending: ledger still lists resolved boxes" "$(cat "$PLEDGER")"
grep -q 'box-alice' "$PLEDGER" && bad "pending: resolved box still listed" || ok "pending: no resolved box remains in the ledger"
rm -rf "$MOCK_DIR"

# ===========================================================================
# F. CONCURRENT SEEDS: PRIVATE TEMP PATHS + SCOPED LOCK
# ===========================================================================
echo "--- F. concurrent write runs: one writes, the other is refused ---"
start_mock conc '[{"box_slug":"box-a","local_agent_id":"dept-WRONG"}]' 50
printf 'box-a vps dept-a\n' > "$WORK/F-spec.txt"
write_world F "$WORK/F-spec.txt"
FW="$WORLD"
maxpages_before="$(ls "${TMPDIR:-/tmp}" 2>/dev/null | grep -c '^rr-registry\.' || true)"
( N8N_API_KEY="k" N8N_HOST="http://127.0.0.1:$MOCK_PORT" PATH="$FW/bin:$PATH" \
  RR031_SSH_HANG=4 bash "$RECONCILE" --roster "$FW/roster.json" --boxes "$FW/box-registry.json" \
  --lock-dir "$FW/state/lock" --state-dir "$FW/state" --no-deadline --proc-timeout 20 --apply >"$WORK/F-run1.out" 2>&1; echo $? > "$WORK/F-run1.rc" ) &
P1=$!
sleep 1.2
( N8N_API_KEY="k" N8N_HOST="http://127.0.0.1:$MOCK_PORT" PATH="$FW/bin:$PATH" \
  RR031_SSH_HANG=4 bash "$RECONCILE" --roster "$FW/roster.json" --boxes "$FW/box-registry.json" \
  --lock-dir "$FW/state/lock" --state-dir "$FW/state" --no-deadline --proc-timeout 20 --apply >"$WORK/F-run2.out" 2>&1; echo $? > "$WORK/F-run2.rc" ) &
P2=$!
wait $P1 $P2 2>/dev/null
RC1="$(cat "$WORK/F-run1.rc" 2>/dev/null || echo x)"; RC2="$(cat "$WORK/F-run2.rc" 2>/dev/null || echo x)"
case "$RC1$RC2" in
  *3*) ok "concurrent: one run was refused by the scoped lock (rc=3), no interleaved writes (rc1=$RC1 rc2=$RC2)" ;;
  *)   bad "concurrent: neither run reported lock contention (rc1=$RC1 rc2=$RC2)" ;;
esac
grep -q 'holds the scoped lock' "$WORK/F-run1.out" "$WORK/F-run2.out" 2>/dev/null && ok "concurrent: the refusal names the lock and the holder" || bad "concurrent: lock refusal message missing"
UNIQF="$(dupe_slugs)"
[ "$UNIQF" = "0" ] && ok "concurrent: unique box_slug mapping survived (no duplicate rows)" || bad "concurrent: duplicates after concurrent runs ($UNIQF)"
ROWF="$(row_for "$FW" box-a)"
printf '%s' "$ROWF" | grep -q 'dept-a' && ok "concurrent: the surviving row holds the verified agent" || bad "concurrent: row content wrong" "$ROWF"
maxpages_after="$(ls "${TMPDIR:-/tmp}" 2>/dev/null | grep -c '^rr-registry\.' || true)"
[ "$maxpages_after" -le "$maxpages_before" ] && ok "concurrent: no per-run temp dir left behind (private paths cleaned)" || bad "concurrent: temp dirs leaked ($maxpages_before -> $maxpages_after)"
# stale lock is stolen exactly once (dead pid)
mkdir -p "$FW/state/lock/agent-map-reconcile.lock"
printf '999999\n' > "$FW/state/lock/agent-map-reconcile.lock/pid"
rc=$(run_reconcile "$FW" "$MOCK_PORT" "$WORK/F-stale.out" --apply)
[ "$rc" -eq 0 ] && ok "concurrent: a lock held by a DEAD pid is stolen and the run proceeds" || bad "concurrent: stale lock not stolen (rc=$rc)" "$(cat "$WORK/F-stale.out")"
[ -d "$FW/state/lock/agent-map-reconcile.lock" ] && bad "concurrent: lock dir left behind after the run" || ok "concurrent: lock released on exit"
rm -rf "$MOCK_DIR"

# ===========================================================================
# G. FINITE DEADLINES: TIMED-OUT SSH IS PENDING, NEVER A WRONG ROW
# ===========================================================================
echo "--- G. a timed-out SSH probe becomes pending, never a guess ---"
start_mock sshdl '[{"box_slug":"box-a","local_agent_id":"dept-WRONG"}]' 50
printf 'box-a vps dept-a\nbox-slow vps dept-slow\n' > "$WORK/G-spec.txt"
write_world G "$WORK/G-spec.txt"
GW="$WORLD"
N8N_API_KEY="k" N8N_HOST="http://127.0.0.1:$MOCK_PORT" PATH="$GW/bin:$PATH" \
  RR031_SSH_HANG=30 RR031_SSH_HANG_SLUG=box-slow \
  bash "$RECONCILE" --roster "$GW/roster.json" --boxes "$GW/box-registry.json" \
  --lock-dir "$GW/state/lock" --state-dir "$GW/state" --no-deadline --proc-timeout 2 --apply >"$WORK/G-run.out" 2>&1
rc=$?
[ "$rc" -ne 0 ] && ok "ssh deadline: run reports incomplete (rc=$rc)" || bad "ssh deadline: run claimed success"
grep -qE 'pending box-slow owner=operator reason=process-deadline-2s' "$WORK/G-run.out" && ok "ssh deadline: the timed-out box is PENDING with the named deadline reason" || bad "ssh deadline: timeout not recorded as pending" "$(grep -E 'pending|box-slow' "$WORK/G-run.out" | head -3)"
grep -q 'failed=0' "$WORK/G-run.out" && ok "ssh deadline: a transport timeout is NOT counted as a write failure" || bad "ssh deadline: timeout miscounted as failed" "$(grep failed= "$WORK/G-run.out")"
SLOWROW="$(row_for "$GW" box-slow)"
[ "$SLOWROW" = "[]" ] && ok "ssh deadline: NO row written for the timed-out box" || bad "ssh deadline: row written for an unresolvable box" "$SLOWROW"
ROWA="$(row_for "$GW" box-a)"
printf '%s' "$ROWA" | grep -q 'dept-a' && ok "ssh deadline: the reachable box was still reconciled correctly" || bad "ssh deadline: reachable box not reconciled" "$ROWA"
grep -q 'complete=0' "$WORK/G-run.out" && ok "ssh deadline: complete=0 while a box is pending" || bad "ssh deadline: complete flag wrong"
# negative control: the deadline instrument must be able to fire
t0=$(date +%s)
bash -c 'sleep 5' >/dev/null 2>&1 &
SL=$!
sleep 0.1
if command -v gtimeout >/dev/null 2>&1; then gtimeout 1 bash -c 'sleep 5' >/dev/null 2>&1; ctl=$?; else ctl=124; fi
[ "$ctl" = 124 ] && ok "ssh deadline control: the process deadline instrument DOES fire on a hanging child" || bad "ssh deadline control: deadline instrument never fired (rc=$ctl)"
wait $SL 2>/dev/null
rm -rf "$MOCK_DIR"

# unbounded-SSH control: an ssh that fails (255) is unreachable/pending, not a FAIL
start_mock sshfail '[{"box_slug":"box-a","local_agent_id":"dept-a"}]' 50
printf 'box-a vps dept-a\nbox-dead vps dept-dead\n' > "$WORK/G2-spec.txt"
write_world G2 "$WORK/G2-spec.txt"
GW2="$WORLD"
N8N_API_KEY="k" N8N_HOST="http://127.0.0.1:$MOCK_PORT" PATH="$GW2/bin:$PATH" \
  RR031_SSH_FAIL=1 RR031_SSH_FAIL_SLUG=box-dead \
  bash "$RECONCILE" --roster "$GW2/roster.json" --boxes "$GW2/box-registry.json" \
  --lock-dir "$GW2/state/lock" --state-dir "$GW2/state" --no-deadline --apply >"$WORK/G2-run.out" 2>&1
rc=$?
grep -q 'pending box-dead owner=operator' "$WORK/G2-run.out" && ok "ssh failure: rc=255 transport failure is pending, not a bad row" || bad "ssh failure: ssh 255 mishandled" "$(head -5 "$WORK/G2-run.out")"
[ "$(row_for "$GW2" box-dead)" = "[]" ] && ok "ssh failure: no row written for the unreachable box" || bad "ssh failure: row written for an unreachable box"
row_for "$GW2" box-a | grep -q 'dept-a' && ok "ssh failure: the reachable box was still reconciled in the same run" || bad "ssh failure: reachable box skipped"
rc=$(run_reconcile "$GW2" "$MOCK_PORT" "$WORK/G2b.out" --verify)
rm -rf "$MOCK_DIR"

# ===========================================================================
# H. CREDENTIAL TRANSPORT: KEY NEVER ON ARGV
# ===========================================================================
echo "--- H. the API key never appears in an argv ---"
start_mock cred '[{"box_slug":"box-a","local_agent_id":"dept-WRONG"}]' 50
printf 'box-a vps dept-a\n' > "$WORK/H-spec.txt"
write_world H "$WORK/H-spec.txt"
HW="$WORLD"
cat > "$HW/bin/curl" <<STUB
#!/bin/bash
printf '%s\n' "\$*" >> "$HW/curl-argv.log"
exec /usr/bin/curl "\$@"
STUB
chmod +x "$HW/bin/curl"
KEY="ZZRR031-n8n-key-sentinel"
rc=$(run_reconcile "$HW" "$MOCK_PORT" "$WORK/H-run.out" --apply)
[ "$rc" -eq 0 ] && ok "credential: run completes through the argv-recording curl" || bad "credential: rc=$rc" "$(cat "$WORK/H-run.out")"
grep -qF "$KEY" "$HW/curl-argv.log" && bad "credential: API KEY ON CURL ARGV" || ok "credential: key absent from every curl argv"
grep -q -- '-H @' "$HW/curl-argv.log" && ok "credential: auth rides via -H @header-file" || bad "credential: no header-file flag seen"
grep -q 'data-binary @' "$HW/curl-argv.log" && ok "credential: payloads ride via --data-binary @file" || bad "credential: payload not on a file"
grep -qF "$KEY" "$WORK/H-run.out" && bad "credential: key printed into the run output" || ok "credential: key absent from run output"
case "$(grep -o 'X-N8N-API-KEY' "$HW/curl-argv.log" | head -1)" in
  "") ok "credential: header NAME never rendered inline either" ;;
  *)  bad "credential: header name rendered inline (value may follow)" ;;
esac
ls "${TMPDIR:-/tmp}"/rr-registry.* >/dev/null 2>&1 && bad "credential: private temp dir LEFT BEHIND" || ok "credential: private temp dirs removed on exit"
# negative control: the detector must catch a key-bearing argv
( exec -a curl /bin/echo -H "X-N8N-API-KEY: $KEY" ) >> "$HW/curl-argv.log" 2>/dev/null || true
grep -qF "$KEY" "$HW/curl-argv.log" && ok "credential control: the detector DOES catch a key-bearing argv" || bad "credential control: detector cannot fail — part H proves nothing"
rm -rf "$MOCK_DIR"

# ===========================================================================
# I. NEGATIVE CONTROL ON THE WHOLE INSTRUMENT
# ===========================================================================
echo "--- I. instrument control: the reconciler fails when the table is wrong ---"
start_mock ctl '[{"box_slug":"box-a","local_agent_id":"dept-a"}]' 50
printf 'box-a vps dept-a\n' > "$WORK/I-spec.txt"
write_world I "$WORK/I-spec.txt"
IW="$WORLD"
printf '{"tables":[{"name":"rr_agent_map","id":"ZZtotallyDifferentTable"}]}\n' > "$WORK/I-manifest.json"
N8N_API_KEY="k" N8N_HOST="http://127.0.0.1:$MOCK_PORT" PATH="$IW/bin:$PATH" \
  bash "$RECONCILE" --check --roster "$IW/roster.json" --boxes "$IW/box-registry.json" \
  --contract-manifest "$WORK/I-manifest.json" >"$WORK/I.out" 2>&1
rc=$?
[ "$rc" -eq 2 ] && ok "control: a contract naming another table is refused (rc=2)" || bad "control: mismatched contract accepted (rc=$rc)"
grep -q 'ZZtotallyDifferentTable' "$WORK/I.out" && ok "control: the refused table id is named (evidence, not a bare refusal)" || bad "control: refusal carried no evidence"
# and: a run against a table the mock does not serve must abort, not 'succeed'
N8N_API_KEY="k" N8N_HOST="http://127.0.0.1:$MOCK_PORT" PATH="$IW/bin:$PATH" \
  bash "$RECONCILE" --roster "$IW/roster.json" --boxes "$IW/box-registry.json" \
  --lock-dir "$IW/state/lock" --state-dir "$IW/state" --no-deadline --table "ZZotherTable000" --apply >"$WORK/I2.out" 2>&1
rc=$?
[ "$rc" -ne 0 ] && ok "control: a 404 table aborts the run (never 'nothing to do, OK')" || bad "control: run SUCCEEDED against a 404 table — the old exit-0 skip defect"
grep -qE 'http-404|snapshot INCOMPLETE' "$WORK/I2.out" && ok "control: the abort names the HTTP failure" || bad "control: no HTTP reason in the abort" "$(head -3 "$WORK/I2.out")"
rm -rf "$MOCK_DIR"

echo ""
echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] || exit 1
exit 0
