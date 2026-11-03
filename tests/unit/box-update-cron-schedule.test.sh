#!/usr/bin/env bash
# Box update cron: Tue/Fri/Sun 2:00 AM Eastern COMMAND job (shared-utils/cron-lib.sh
# oc_box_update_cron_ensure). Runs the real function against a fake `openclaw`
# that keeps its jobs in a JSON file.
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
FAIL=0
ok()  { echo "  PASS $1"; }
bad() { echo "  FAIL $1"; FAIL=1; }

mkdir -p "$T/bin"
cat > "$T/bin/openclaw" <<'PYEOF'
#!/usr/bin/env python3
import json, os, sys, uuid
store = os.environ["FAKE_OC_STORE"]
jobs = json.load(open(store)) if os.path.exists(store) else []
a = sys.argv[1:]
open(os.environ["FAKE_OC_CALLS"], "a").write(" ".join(a[:2]) + (" --help" if "--help" in a else "") + "\n")
def save(): json.dump(jobs, open(store, "w"))
def flag(n):
    return a[a.index(n) + 1] if n in a else None
if a[:2] == ["cron", "add"] and "--help" in a:
    print("--name <name>  --cron <expr>  --tz <iana>  --exact  --no-deliver")
    if os.environ.get("FAKE_OC_NO_COMMAND") != "1":
        print("  --command <shell>                Command payload run as sh -lc <shell>")
    sys.exit(0)
if a[:2] == ["cron", "list"]:
    print(json.dumps({"jobs": jobs})); sys.exit(0)
if a[:2] == ["cron", "add"]:
    if os.environ.get("FAKE_OC_ADD_FAIL") == "1": sys.exit(1)
    jobs.append({"id": str(uuid.uuid4()), "name": flag("--name"), "enabled": True,
                 "schedule": {"kind": "cron", "expr": flag("--cron"), "tz": flag("--tz")},
                 "payload": {"kind": "command", "argv": ["sh", "-lc", flag("--command")]},
                 "delivery": {"mode": "none" if "--no-deliver" in a else "announce"}})
    save(); sys.exit(0)
if a[:2] == ["cron", "rm"]:
    # FAKE_OC_RM_FAIL_TIMES: the first N rm calls fail (busy box: SQLite admission timeout)
    cnt = os.environ.get("FAKE_OC_RM_COUNT")
    if cnt:
        done = int(open(cnt).read() or 0) if os.path.exists(cnt) else 0
        open(cnt, "w").write(str(done + 1))
        if done < int(os.environ.get("FAKE_OC_RM_FAIL_TIMES", "0")): sys.exit(1)
    n = len(jobs); jobs[:] = [j for j in jobs if j["id"] != a[2]]; save()
    sys.exit(0 if len(jobs) < n else 1)
sys.exit(0)
PYEOF
chmod +x "$T/bin/openclaw"
export PATH="$T/bin:$PATH" FAKE_OC_STORE="$T/jobs.json" FAKE_OC_CALLS="$T/calls"
# shellcheck source=/dev/null
source "$REPO/shared-utils/cron-lib.sh"

export OC_BOX_UPDATE_RM_DELAY=0
reset() { printf '%s' "${1:-[]}" > "$FAKE_OC_STORE"; : > "$FAKE_OC_CALLS"; rm -f "$T/rmcount"; unset FAKE_OC_NO_COMMAND FAKE_OC_ADD_FAIL FAKE_OC_RM_FAIL_TIMES FAKE_OC_RM_COUNT; }
jobs_summary() { python3 - "$FAKE_OC_STORE" <<'EOF'
import json, sys
j = [x for x in json.load(open(sys.argv[1])) if x["name"] == "weekly-onboarding-update"]
print(len(j), *(f'{x["payload"]["kind"]}|{x["schedule"]["expr"]}|{x["schedule"]["tz"]}|{x["delivery"]["mode"]}' for x in j))
EOF
}
WANT="1 command|0 2 * * 0,2,5|America/New_York|none"
OLD='[{"id":"old-1","name":"weekly-onboarding-update","enabled":true,"schedule":{"kind":"cron","expr":"0 3 * * 0","tz":"America/New_York"},"payload":{"kind":"systemEvent","text":"It is Sunday"},"delivery":{"mode":"none"}},{"id":"old-2","name":"weekly-onboarding-update","enabled":true,"schedule":{"kind":"cron","expr":"0 3 * * 0","tz":"America/New_York"},"payload":{"kind":"agentTurn","message":"dup"},"delivery":{"mode":"none"}},{"id":"keep","name":"some-other-job","schedule":{"expr":"0 3 * * 0"},"payload":{"kind":"agentTurn"}}]'

echo "== 1. no job yet -> one silent command job on the new schedule"
reset; oc_box_update_cron_ensure >/dev/null; rc=$?
[ "$rc" = 0 ] && [ "$(jobs_summary)" = "$WANT" ] && ok "created ($(jobs_summary))" || bad "rc=$rc got: $(jobs_summary)"
python3 -c 'import json,sys;j=json.load(open(sys.argv[1]))[0];c=j["payload"]["argv"][2];assert "scripts/weekly-full-update.sh" in c and "raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/" in c' "$FAKE_OC_STORE" \
  && ok "command runs weekly-full-update.sh from main" || bad "command does not run weekly-full-update.sh from main"

echo "== 2. old Sunday agent job + duplicate -> exactly one new job, other jobs untouched"
reset "$OLD"; oc_box_update_cron_ensure >/dev/null; rc=$?
[ "$rc" = 0 ] && [ "$(jobs_summary)" = "$WANT" ] && ok "converted ($(jobs_summary))" || bad "rc=$rc got: $(jobs_summary)"
grep -q '"some-other-job"' "$FAKE_OC_STORE" && ok "unrelated job kept" || bad "unrelated job removed"

echo "== 3. already current -> no add, no rm (idempotent)"
oc_box_update_cron_ensure >/dev/null; rc=$?
: > "$FAKE_OC_CALLS"; oc_box_update_cron_ensure >/dev/null; rc=$?
[ "$rc" = 0 ] && ! grep -qE '^cron (add|rm)$' "$FAKE_OC_CALLS" && ok "no changes on a current box" || bad "rc=$rc calls: $(tr '\n' ';' < "$FAKE_OC_CALLS")"

echo "== 4. OpenClaw without command jobs -> rc 1, nothing touched"
reset "$OLD"; export FAKE_OC_NO_COMMAND=1; oc_box_update_cron_ensure >/dev/null; rc=$?
[ "$rc" = 1 ] && [ "$(jobs_summary | cut -d' ' -f1)" = 2 ] && ok "fell back, old jobs intact" || bad "rc=$rc got: $(jobs_summary)"

echo "== 5. create fails -> rc 2, old job still in place (box never left without an update job)"
reset "$OLD"; export FAKE_OC_ADD_FAIL=1; oc_box_update_cron_ensure >/dev/null; rc=$?
[ "$rc" = 2 ] && [ "$(jobs_summary | cut -d' ' -f1)" = 2 ] && ok "old jobs kept on failed create" || bad "rc=$rc got: $(jobs_summary)"

echo "== 6. busy box: rm fails 3 times, then works -> retried, exactly one command job left"
reset "$OLD"; export FAKE_OC_RM_COUNT="$T/rmcount" FAKE_OC_RM_FAIL_TIMES=3
out="$(oc_box_update_cron_ensure)"; rc=$?
[ "$rc" = 0 ] && [ "$(jobs_summary)" = "$WANT" ] && ! printf '%s' "$out" | grep -q "could NOT remove" && ok "old jobs removed after retries ($(jobs_summary))" || bad "rc=$rc got: $(jobs_summary) out: $out"

echo "== 7. rm never works -> loud warning naming the stuck ids, new job still in place"
reset "$OLD"; export FAKE_OC_RM_COUNT="$T/rmcount" FAKE_OC_RM_FAIL_TIMES=999
out="$(oc_box_update_cron_ensure)"; rc=$?
printf '%s' "$out" | grep -q "could NOT remove old job(s) old-1 old-2" && ok "warning names stuck ids" || bad "no loud warning: $out"
python3 -c 'import json,sys;j=json.load(open(sys.argv[1]));c=[x for x in j if x["name"]=="weekly-onboarding-update" and x["payload"]["kind"]=="command"];assert len(c)==1' "$FAKE_OC_STORE" \
  && ok "exactly one new command job despite failed removals" || bad "command job count wrong: $(jobs_summary)"

echo "== 8. next run on that box (rm works again) -> keeps the command job, removes only leftovers, no new job"
export FAKE_OC_RM_FAIL_TIMES=0; rm -f "$T/rmcount"; : > "$FAKE_OC_CALLS"
oc_box_update_cron_ensure >/dev/null; rc=$?
[ "$rc" = 0 ] && [ "$(jobs_summary)" = "$WANT" ] && ! grep -qE '^cron add$' "$FAKE_OC_CALLS" && ok "self-healed without creating a second job ($(jobs_summary))" || bad "rc=$rc got: $(jobs_summary) calls: $(tr '\n' ';' < "$FAKE_OC_CALLS")"

exit $FAIL
