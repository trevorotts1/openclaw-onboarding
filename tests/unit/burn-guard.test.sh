#!/usr/bin/env bash
# tests/unit/burn-guard.test.sh — scripts/ensure-burn-guard.sh + its hooks.
#
# The fake `openclaw` models the behaviour measured on live OpenClaw 2026.9.x boxes:
#   config get <unset key>   -> "Config path is valid but unset: ..." (rc 1)
#   config get <unknown key> -> "Unknown config path: ..."            (rc 1)
#   config set mode <v>      -> hot reload; the reconciler projects every
#                               skill-collection-review job enabled = (v == "auto")
#   cron edit <review job>   -> REFUSED "system-owned monitor jobs cannot be edited"
#   cron list --json         -> enabled jobs only; --all adds disabled ones
# Cases (each fails on the pre-fix tree, which has no ensure-burn-guard.sh):
#   T1 unset -> propose, review crons disabled-not-deleted, one backup, report line
#   T2 auto  -> propose (explicit auto is not an operator opt-out of the fix)
#   T3 explicit off / propose left alone: no write, no backup
#   T4 idempotent re-run is a no-op (no write, no new backup, "disabled 0")
#   T5 write rejected / cron list unreadable / key unknown -> ADVISORY, exit 0, no write
#   T6 hooks: update-skills.sh + install.sh call it; the fleet runner lifts the line
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/ensure-burn-guard.sh"
SB="$(mktemp -d)"; trap 'rm -rf "$SB"' EXIT
PASS=0; FAIL=0
ok()  { echo "  PASS: $1"; PASS=$((PASS+1)); }
bad() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

mkdir -p "$SB/bin"
cat > "$SB/bin/openclaw" <<'PYEOF'
#!/usr/bin/env python3
import json, os, sys
st_p = os.environ["FAKE_STATE"]; st = json.load(open(st_p)); a = sys.argv[1:]
open(os.environ["FAKE_CALLS"], "a").write(" ".join(a) + "\n")
KEY = "skills.workshop.autonomous.mode"
def save(): json.dump(st, open(st_p, "w"))
if a[:2] == ["config", "get"]:
    if not st.get("known", True): print(f"Unknown config path: {a[2]}."); sys.exit(1)
    if st.get("mode") is None: print(f"Config path is valid but unset: {a[2]}."); sys.exit(1)
    print(json.dumps(st["mode"])); sys.exit(0)
if a[:2] == ["config", "set"] and a[2] == KEY:
    if st.get("set_fails"): print("Error: config write rejected", file=sys.stderr); sys.exit(1)
    st["mode"] = a[3]
    for j in st["jobs"]:
        if j.get("declarationKey", "").startswith("skill-collection-review:"):
            j["enabled"] = a[3] == "auto"
    save(); print(f"Updated {KEY}. Change will apply without restarting the gateway."); sys.exit(0)
if a[:2] == ["cron", "list"]:
    if st.get("list_fails"): sys.exit(1)
    jobs = st["jobs"] if "--all" in a else [j for j in st["jobs"] if j.get("enabled", True)]
    print(json.dumps({"jobs": jobs})); sys.exit(0)
if a[:2] == ["cron", "edit"]:
    print("Error: system-owned monitor jobs cannot be edited by cron clients"); sys.exit(1)
if a[:2] == ["cron", "rm"] or a[:2] == ["cron", "delete"]:
    sys.exit(3)
sys.exit(0)
PYEOF
chmod +x "$SB/bin/openclaw"

mkbox() { # <name> <state-json-extras> -> HOME; 3 review jobs (enabled per mode) + 1 user job
  local h="$SB/$1"; mkdir -p "$h/.openclaw"; echo '{"skills":{}}' > "$h/.openclaw/openclaw.json"
  python3 - "$h/state.json" "$2" <<'EOF'
import json, sys
extra = json.loads(sys.argv[2])
on = extra.get("mode") in (None, "auto")
jobs = [{"id": f"r{i}", "name": f"skill-collection-review-a{i}", "declarationKey": f"skill-collection-review:a{i}", "enabled": on} for i in range(3)]
jobs.append({"id": "u1", "name": "cc-watchdog", "enabled": True})
json.dump({"jobs": jobs, **extra}, open(sys.argv[1], "w"))
EOF
  : > "$h/calls"; echo "$h"
}
run() { HOME="$1" PATH="$SB/bin:$PATH" FAKE_STATE="$1/state.json" FAKE_CALLS="$1/calls" BURN_GUARD_WAIT_S=0 bash "$SCRIPT" > "$1/out" 2>&1; echo $? > "$1/rc"; }
st() { python3 -c "import json,sys; s=json.load(open(sys.argv[1])); print(eval(sys.argv[2]))" "$1/state.json" "$2"; }  # test-authored expressions only
nbak() { ls "$1/.openclaw/" | grep -c 'openclaw.json.burn-guard-'; }

echo "=== burn-guard ==="
[ -f "$SCRIPT" ] || { echo "  FAIL: scripts/ensure-burn-guard.sh missing"; exit 1; }

H=$(mkbox t1 '{"mode": null}'); run "$H"
[ "$(st "$H" "s['mode']")" = "propose" ] && ok "T1a unset -> propose" || bad "T1a mode=$(st "$H" "s['mode']")"
[ "$(st "$H" "[j['enabled'] for j in s['jobs'] if j['id'].startswith('r')]")" = "[False, False, False]" ] && ok "T1b review crons disabled" || bad "T1b $(st "$H" "s['jobs']")"
[ "$(st "$H" "len(s['jobs'])")" = "4" ] && ! grep -qE "cron (rm|delete)" "$H/calls" && ok "T1c nothing deleted" || bad "T1c jobs deleted"
[ "$(nbak "$H")" = "1" ] && ok "T1d exactly one openclaw.json backup" || bad "T1d backups=$(nbak "$H")"
grep -q "^burn-guard: mode=propose, review crons disabled 3 (already off 0); set from unset" "$H/out" && ok "T1e report line" || bad "T1e line: $(cat "$H/out")"
[ "$(cat "$H/rc")" = "0" ] && ok "T1f exit 0" || bad "T1f rc=$(cat "$H/rc")"

H2=$(mkbox t2 '{"mode": "auto"}'); run "$H2"
[ "$(st "$H2" "s['mode']")" = "propose" ] && grep -q "disabled 3 (already off 0); set from auto" "$H2/out" && ok "T2 auto -> propose, 3 disabled" || bad "T2 $(cat "$H2/out")"

for m in off propose; do
  H3=$(mkbox "t3$m" "{\"mode\": \"$m\"}"); run "$H3"
  if [ "$(st "$H3" "s['mode']")" = "$m" ] && ! grep -q "config set" "$H3/calls" && [ "$(nbak "$H3")" = "0" ] \
     && grep -q "^burn-guard: mode=$m, review crons disabled 0 (already off 3)$" "$H3/out"; then
    ok "T3 explicit $m left alone (no write, no backup)"
  else bad "T3 explicit $m: $(cat "$H3/out") calls=$(tr '\n' '|' < "$H3/calls")"; fi
done

: > "$H/calls"; run "$H"
if ! grep -q "config set" "$H/calls" && [ "$(nbak "$H")" = "1" ] && grep -q "^burn-guard: mode=propose, review crons disabled 0 (already off 3)$" "$H/out"; then
  ok "T4 idempotent re-run is a no-op"
else bad "T4 re-run: $(cat "$H/out") backups=$(nbak "$H")"; fi

H5=$(mkbox t5a '{"mode": "auto", "set_fails": true}'); run "$H5"
[ "$(cat "$H5/rc")" = "0" ] && grep -q "ADVISORY could not set" "$H5/out" && [ "$(nbak "$H5")" = "0" ] && [ "$(st "$H5" "s['mode']")" = "auto" ] \
  && ok "T5a rejected write -> ADVISORY, exit 0, no backup left" || bad "T5a $(cat "$H5/out")"
H5=$(mkbox t5b '{"mode": null, "list_fails": true}'); run "$H5"
[ "$(cat "$H5/rc")" = "0" ] && grep -q "review crons ADVISORY: cron list unreadable" "$H5/out" && ok "T5b cron list unreadable -> ADVISORY, exit 0" || bad "T5b $(cat "$H5/out")"
H5=$(mkbox t5c '{"mode": null, "known": false}'); run "$H5"
[ "$(cat "$H5/rc")" = "0" ] && grep -q "ADVISORY this OpenClaw build has no" "$H5/out" && ! grep -q "config set" "$H5/calls" && ok "T5c unknown key -> ADVISORY, no write" || bad "T5c $(cat "$H5/out")"

# The hook must sit BEFORE the content-recheck `exit 0`, or content-current re-rolls never run it.
_hook=$(grep -n 'scripts/ensure-burn-guard.sh' "$REPO_ROOT/update-skills.sh" | head -1 | cut -d: -f1)
_exit=$(grep -n 'CONTENT RECHECK\] stamp current AND installed content matches source' "$REPO_ROOT/update-skills.sh" | head -1 | cut -d: -f1)
[ -n "$_hook" ] && [ -n "$_exit" ] && [ "$_hook" -lt "$_exit" ] && ok "T6a update-skills.sh runs the burn guard before the content-recheck early exit" \
  || bad "T6a update-skills.sh hook missing or after the early exit (hook=${_hook:-none} exit=${_exit:-none})"
grep -q 'scripts/ensure-burn-guard.sh' "$REPO_ROOT/install.sh" && ok "T6b install.sh runs the burn guard" || bad "T6b install.sh hook missing"
python3 - "$REPO_ROOT/shared-utils" <<'EOF' && ok "T6c fleet runner lifts the burn-guard line into steps" || bad "T6c fleet runner parse"
import sys; sys.path.insert(0, sys.argv[1])
import fleet_refresh_runner as f
assert f._burn_guard_step("x\nburn-guard: mode=propose, review crons disabled 3 (already off 0)\n") == "ok: mode=propose, review crons disabled 3 (already off 0)"
assert f._burn_guard_step("burn-guard: ADVISORY could not set x").startswith("ok:advisory:")
assert f._burn_guard_step("nothing").startswith("n/a:")
assert "failed" not in f._burn_guard_step("burn-guard: ADVISORY cron list unreadable")
EOF

echo "=== $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ]
