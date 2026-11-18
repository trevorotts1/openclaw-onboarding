#!/usr/bin/env bash
# The weekly-onboarding-update openclaw cron job is RETIRED (Tue/Fri/Sun auto-update).
# This file used to assert the 2:00 AM Tue/Fri/Sun COMMAND job that shared-utils/cron-lib.sh
# oc_box_update_cron_ensure created. It now asserts the opposite, against the same kind of fake
# `openclaw` that keeps its jobs in a JSON file:
#   - oc_box_update_cron_ensure no longer exists, so nothing can re-create the job;
#   - the installer removes EVERY job with that name (by id, with retries on a busy box) and leaves other jobs alone;
#   - the schedule that replaced it is one crontab tick, not an openclaw cron job.
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
FAIL=0
ok()  { echo "  PASS $1"; }
bad() { echo "  FAIL $1"; FAIL=1; }

mkdir -p "$T/bin" "$T/home/.openclaw/skills"
cat > "$T/bin/openclaw" <<'PYEOF'
#!/usr/bin/env python3
import json, os, sys
store = os.environ["FAKE_OC_STORE"]
jobs = json.load(open(store)) if os.path.exists(store) else []
a = sys.argv[1:]
def save(): json.dump(jobs, open(store, "w"))
if a[:2] == ["cron", "list"]:
    print(json.dumps({"jobs": jobs})); sys.exit(0)
if a[:2] == ["cron", "rm"]:
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
cat > "$T/bin/crontab" <<'CTEOF'
#!/bin/bash
F="$FAKE_CRON_FILE"
case "$1" in -l) [ -f "$F" ] && cat "$F" || { echo "no crontab for user" >&2; exit 1; } ;; -) cat > "$F" ;; esac
CTEOF
chmod +x "$T/bin/crontab"
export PATH="$T/bin:$PATH" HOME="$T/home" OPENCLAW_ROOT="$T/home/.openclaw" FAKE_OC_STORE="$T/jobs.json" \
       FAKE_OC_RM_COUNT="$T/rmcount" FAKE_CRON_FILE="$T/crontab.txt" AUTO_UPDATE_RM_DELAY=0

# assert 1: the creator is gone, from the library and from both entry points
if grep -q "oc_box_update_cron_ensure()" "$REPO/shared-utils/cron-lib.sh"; then bad "cron-lib.sh still defines oc_box_update_cron_ensure (the job could be re-created)"; else ok "cron-lib.sh no longer defines oc_box_update_cron_ensure"; fi
if grep -q "oc_box_update_cron_ensure" "$REPO/update-skills.sh" "$REPO/install.sh"; then bad "update-skills.sh or install.sh still calls oc_box_update_cron_ensure"; else ok "update-skills.sh and install.sh no longer call oc_box_update_cron_ensure"; fi

# assert 2: the installer removes every weekly-onboarding-update job (also after busy-box rm failures), keeps other jobs
printf '%s' '[{"id":"a1","name":"weekly-onboarding-update","enabled":true},{"id":"b2","name":"weekly-onboarding-update"},{"id":"k3","name":"clients-own-job"}]' > "$FAKE_OC_STORE"
export FAKE_OC_RM_FAIL_TIMES=1
python3 "$REPO/scripts/auto_update.py" install >/dev/null 2>&1
LEFT="$(python3 -c 'import json,os; print(" ".join(sorted(j["id"] for j in json.load(open(os.environ["FAKE_OC_STORE"])))))')"
[ "$LEFT" = "k3" ] && ok "both weekly-onboarding-update jobs removed by id, the client's own job kept (left: $LEFT)" || bad "jobs left after install: $LEFT (want only k3)"

# assert 3: the replacement is ONE crontab tick line (not an openclaw cron job), installed once
N="$(grep -c '# openclaw-auto-update' "$FAKE_CRON_FILE" 2>/dev/null || echo 0)"
[ "$N" = "1" ] && ok "exactly one tick line in the crontab" || bad "tick lines in the crontab: $N (want 1)"
python3 "$REPO/scripts/auto_update.py" install >/dev/null 2>&1
N2="$(grep -c '# openclaw-auto-update' "$FAKE_CRON_FILE" 2>/dev/null || echo 0)"
[ "$N2" = "1" ] && ok "second install changes nothing (still exactly one tick line)" || bad "second install left $N2 tick lines"

exit $FAIL
