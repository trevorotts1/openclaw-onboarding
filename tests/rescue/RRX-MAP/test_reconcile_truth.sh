#!/usr/bin/env bash
# tests/rescue/RRX-MAP/test_reconcile_truth.sh   (RRX-046)
#
# Pins the four RRX-046 truths about scripts/reconcile-rr-agent-map.sh:
#   (a) a WRITE run with N8N_API_KEY unset is a CONFIGURATION failure (exit 2),
#       never the old exit 0 a wrapper could read as "ok"
#   (b) a failed write names the box that failed — not $slug, which still holds
#       the LAST box of the probe loop — and the other rows are still attempted
#   (c) HTTP 200 with the body `false` is a FAILED row: rows_updated=0 failed=1
#   (d) the pending ledger records complete=0 whenever the run is incomplete
#
# Hermetic: stub curl + stub openclaw on PATH, synthetic roster / box registry,
# nothing outside the temp dir. Run by the quality-check agent, never a builder.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
RECONCILE="$REPO/scripts/reconcile-rr-agent-map.sh"
[ -f "$RECONCILE" ] || { echo "FATAL: missing $RECONCILE"; exit 2; }

PASS=0; FAIL=0
ok()  { PASS=$((PASS + 1)); echo "  ok   $1"; }
bad() { FAIL=$((FAIL + 1)); echo "  FAIL $1 ${2:-}"; }

WORK="$(mktemp -d "${TMPDIR:-/tmp}/rrx046.XXXXXX")"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT INT TERM

# write_world <dir> <slug>...  — one synthetic LOCAL box per slug, plus a stub
# curl that serves the seed page and scripts the PATCH verdicts.
write_world() {
  local w="$1"; shift
  mkdir -p "$w/bin" "$w/state"
  python3 - "$w/roster.json" "$w/box-registry.json" "$@" <<'PY'
import json, sys
roster_path, boxes_path, slugs = sys.argv[1], sys.argv[2], sys.argv[3:]
json.dump({"_doc": "synthetic roster",
           "boxes": {s: {"platform": "local"} for s in slugs}},
          open(roster_path, "w"), indent=1)
json.dump({"_doc": "synthetic box registry",
           "boxes": {s: {"kind": "local", "client": "synthetic"} for s in slugs}},
          open(boxes_path, "w"), indent=1)
PY
  printf '[]' > "$w/seed.json"

  cat > "$w/bin/openclaw" <<'STUB'
#!/bin/sh
printf '%s\n' '[{"id":"dept-a","isDefault":true}]'
STUB
  chmod +x "$w/bin/openclaw"

  cat > "$w/bin/curl" <<STUB
#!/bin/bash
out=""; method="GET"; code="200"; body=""
while [ \$# -gt 0 ]; do
  case "\$1" in
    -o) out="\$2"; shift 2 ;;
    -w) shift 2 ;;
    -X) method="\$2"; shift 2 ;;
    --data-binary) shift 2 ;;
    -H) shift 2 ;;
    -G) shift ;;
    --max-time|--connect-timeout) shift 2 ;;
    --data-urlencode) shift 2 ;;
    *) shift ;;
  esac
done
case "\$method" in
  GET)   body="{\"data\":\$(cat "$w/seed.json"),\"nextCursor\":null}" ;;
  PATCH)
         n=\$(cat "$w/patch.count" 2>/dev/null || printf 0); n=\$((n + 1)); printf '%s' "\$n" > "$w/patch.count"
         if [ "\${RRX046_FAIL_FIRST:-0}" = "1" ] && [ "\$n" -eq 1 ]; then
           code=500; body='{"message":"stub failure"}'
         elif [ "\${RRX046_BODY_FALSE:-0}" = "1" ]; then
           code=200; body='false'
         else
           code=200; body='true'
         fi ;;
  POST)  code=200; body='{"insertedRows":1}' ;;
  *)     code=200; body='{}' ;;
esac
if [ -n "\$out" ]; then printf '%s' "\$body" > "\$out"; fi
printf '%s' "\$code"
STUB
  chmod +x "$w/bin/curl"
}

run_reconcile() {   # run_reconcile <world> <out> <key: yes|no> [extra args...]
  local w="$1" out="$2" key="$3"; shift 3
  local -a e=( "N8N_HOST=http://127.0.0.1:9" "PATH=$w/bin:$PATH" "RR_REGISTRY_DEADLINE=60" )
  [ "$key" = "yes" ] && e+=( "N8N_API_KEY=ZZRRX046-n8n-key-sentinel" )
  [ "${STUB_FAIL_FIRST:-0}" = "1" ] && e+=( "RRX046_FAIL_FIRST=1" )
  [ "${STUB_BODY_FALSE:-0}" = "1" ] && e+=( "RRX046_BODY_FALSE=1" )
  local rc=0
  env -u N8N_API_KEY "${e[@]}" bash "$RECONCILE" \
    --roster "$w/roster.json" --boxes "$w/box-registry.json" \
    --state-dir "$w/state" --no-deadline "$@" >"$out" 2>&1 || rc=$?
  echo "$rc"
}

# ===========================================================================
# (a) a write run that cannot write is not a success
# ===========================================================================
echo "== (a) --apply with N8N_API_KEY unset exits 2, never 0 =="
AW="$WORK/A"; write_world "$AW" box-a
rc=$(run_reconcile "$AW" "$WORK/a.out" no --apply)
[ "$rc" -eq 2 ] && ok "(a) --apply with no key exits 2 (configuration failure)" || bad "(a) exit was $rc, expected 2" "$(cat "$WORK/a.out")"
grep -q 'N8N_API_KEY not set' "$WORK/a.out" && ok "(a) the reason is still stated" || bad "(a) reason missing"
[ ! -f "$AW/patch.count" ] && ok "(a) no write was attempted" || bad "(a) a write was attempted without a key"

# ===========================================================================
# (b) the failed write names the box that failed, and (d) the ledger says incomplete
# ===========================================================================
echo "== (b) a failed PATCH names its own box, not the last probed box =="
BW="$WORK/B"; write_world "$BW" box-a box-b
printf '%s' '[{"box_slug":"box-a","local_agent_id":"dept-WRONG"},{"box_slug":"box-b","local_agent_id":"dept-WRONG"}]' > "$BW/seed.json"
STUB_FAIL_FIRST=1
rc=$(run_reconcile "$BW" "$WORK/b.out" yes --apply)
STUB_FAIL_FIRST=0
[ "$rc" -ne 0 ] && ok "(b) the run exits non-zero" || bad "(b) run exited 0 with a failed write"
grep -q 'patch box-a' "$WORK/b.out" && ok "(b) the failing box-a is named" || bad "(b) box-a missing from the failure message" "$(cat "$WORK/b.out")"
if grep -q 'patch box-b' "$WORK/b.out"; then
  bad "(b) the failure blamed box-b (the last probe-loop slug), not box-a" "$(grep 'patch ' "$WORK/b.out")"
else
  ok "(b) box-b is not blamed for box-a's failure"
fi

# ===========================================================================
# (d) the pending ledger carries the run's real completeness
# ===========================================================================
echo "== (d) the pending ledger records complete=0 for an incomplete run =="
python3 - "$BW/state/rr-agent-map-pending.json" <<'PY' && ok "(d) ledger complete=0 (a failed write can never be recorded complete)" || bad "(d) ledger complete is not 0" "$(cat "$BW/state/rr-agent-map-pending.json" 2>/dev/null)"
import json, sys
d = json.load(open(sys.argv[1]))
sys.exit(0 if d.get("complete") == 0 else 1)
PY

# ===========================================================================
# (c) HTTP 200 with the body false is a FAILED row
# ===========================================================================
echo "== (c) HTTP 200 + body false reports rows_updated=0 failed=1 =="
CW="$WORK/C"; write_world "$CW" box-a
printf '%s' '[{"box_slug":"box-a","local_agent_id":"dept-WRONG"}]' > "$CW/seed.json"
STUB_BODY_FALSE=1
rc=$(run_reconcile "$CW" "$WORK/c.out" yes --apply)
STUB_BODY_FALSE=0
[ "$rc" -ne 0 ] && ok "(c) a false verdict is not a success" || bad "(c) run exited 0 on the body false"
grep -q 'rows_updated=0' "$WORK/c.out" && grep -q 'failed=1' "$WORK/c.out" && ok "(c) machine line: rows_updated=0 failed=1" || bad "(c) counts wrong" "$(grep 'reconcile-rr-agent-map:' "$WORK/c.out")"
if grep -q 'rows_updated=1' "$WORK/c.out"; then
  bad "(c) the false verdict was counted as updated"
else
  ok "(c) the false verdict was never counted as updated"
fi

echo
echo "RRX-046 reconcile truth: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
