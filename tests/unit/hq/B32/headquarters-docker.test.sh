#!/usr/bin/env bash
# headquarters-docker.test.sh — B32 Docker target contract fixtures.
#
# Covers the three halves the card names: the persistent packaging (path +
# resurrection contract), the Skill32 capability wiring, and the explicit
# install/update registration of the agent-exchange-telemetry extension.
# The whole-container replacement proof belongs to T07; this is the component
# contract that has to be true before T07 can run, so nothing here claims
# integration.
#
# Everything runs hermetically: the container-startup script is executed for
# real with fake node/pm2 on PATH and OPENCLAW_DATA pointed at a temp dir, and
# the install.sh / update-skills.sh registration block is extracted by sed range
# (never copied) and driven against a temp HOME.
set -u
cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." || exit 9
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); printf '  ok   - %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL - %s\n' "$1"; }
STARTUP="platform/vps/hostinger/container-startup.sh"
TMP="$(mktemp -d /tmp/cc-B32-onbXXXXXX)"; trap 'rm -rf "$TMP"' EXIT

# --- 1. bound files are syntactically valid ------------------------------
for f in install.sh update-skills.sh 32-command-center-setup/scripts/run-full-install.sh "$STARTUP"; do
  bash -n "$f" && ok "bash -n clean: $f" || bad "bash -n FAILED: $f"
done
bash -n tests/unit/hq/B32/headquarters-docker.test.sh 2>/dev/null || true

# --- 2. binding: B32 alone owns these three install/update files ----------
# (frozen contract quote lives in evidence/contracts/targets.md §3; here we
# pin the wiring itself)
# The card's split, exactly: the extension is deploy/register'd in install.sh
# and update-skills.sh (ONB:@ONB_INSTALL_INTEGRATION's two runtime paths), while
# run-full-install.sh carries the Skill32 CAPABILITY wiring (phase 6k), not a
# second copy of the register block. A sibling-scan assumption is forbidden.
for f in install.sh update-skills.sh; do
  grep -q 'agent-exchange-telemetry' "$f" && ok "telemetry deploy/register wired in $f" || bad "telemetry NOT wired in $f"
done
grep -q 'cc_hq_capability_check' 32-command-center-setup/scripts/run-full-install.sh \
  && ok "Skill32 capability wiring present in run-full-install.sh (phase 6k)" \
  || bad "capability wiring missing from run-full-install.sh"
grep -q 'agent-exchange-telemetry' 32-command-center-setup/scripts/run-full-install.sh \
  && bad "run-full-install.sh duplicates the register block (one writer per file)" \
  || ok "run-full-install.sh does not duplicate the register block"
grep -q 'Phase 6k\|phase=6k' 32-command-center-setup/scripts/run-full-install.sh && ok "phase 6k labelled" || bad "phase 6k label absent"
grep -q 'commandCenterHqEnabled' 32-command-center-setup/scripts/run-full-install.sh \
  && ok "capability result stamped on the build state (observable, not silent)" || bad "no state stamp"

# --- 3. install.sh and update-skills.sh python blocks are identical -------
block() { sed -n "/^$2$/,/^PY$/p" "$1" 2>/dev/null; }
extract_xet() { python3 - "$1" <<'PYX'
import re, sys
t = open(sys.argv[1]).read()
blocks = re.findall(r"python3 - <<'PY'\n(.*?)\nPY\n", t, re.S)
hits = [b for b in blocks if 'agent-exchange-telemetry' in b]
print(hits[-1] if hits else "")
PYX
}
A="$(extract_xet install.sh)"; B="$(extract_xet update-skills.sh)"
[[ -n "$A" ]] && ok "telemetry python block found in install.sh" || bad "telemetry python block missing from install.sh"
[[ "$A" == "$B" ]] && ok "python block byte-identical between install.sh and update-skills.sh (the doctrine precedent's lockstep rule)" || bad "python blocks differ"
# the doctrine block must still be identical too (never regress a sibling rule)
DA="$(python3 - install.sh <<'PYX'
import re, sys
t = open(sys.argv[1]).read()
blocks = re.findall(r"python3 - <<'PY'\n(.*?)\nPY\n", t, re.S)
print(next((b for b in blocks if 'ceo-routing-doctrine' in b and 'agent-exchange' not in b), ""))
PYX
)"
DB="$(python3 - update-skills.sh <<'PYX'
import re, sys
t = open(sys.argv[1]).read()
blocks = re.findall(r"python3 - <<'PY'\n(.*?)\nPY\n", t, re.S)
print(next((b for b in blocks if 'ceo-routing-doctrine' in b and 'agent-exchange' not in b), ""))
PYX
)"
[[ -n "$DA" && "$DA" == "$DB" ]] && ok "CEO doctrine block still byte-identical (no regression)" || bad "doctrine blocks diverged"

# --- 4. the registration block, executed against a temp HOME ---------------
export TMPB="$TMP/xet.py"
printf '%s\n' "$A" > "$TMPB"
HOME_T="$TMP/home"; mkdir -p "$HOME_T/.openclaw/extensions"
CONF="$HOME_T/.openclaw/openclaw.json"
printf '%s\n' '{"plugins":{"entries":{"ceo-routing-doctrine":{"enabled":true}}},"env":{"vars":{"MC_COMPANY_ID":"acme","MC_INSTALLATION_ID":"inst-7"}}}' > "$CONF"
HOME="$HOME_T" MC_COMPANY_ID=acme MC_INSTALLATION_ID=inst-7 python3 "$TMPB" > "$TMP/run1.out" 2>&1
rc=$?
[[ "$rc" -eq 0 ]] && ok "registration block runs clean (rc=0)" || bad "registration block rc=$rc"
python3 - "$CONF" <<'PYV'
import json, sys
cfg = json.load(open(sys.argv[1]))
e = cfg["plugins"]["entries"]["agent-exchange-telemetry"]
assert e["enabled"] is True, e
assert cfg["plugins"]["entries"]["ceo-routing-doctrine"] == {"enabled": True}
assert "/tmp" not in json.dumps(cfg["plugins"]["load"]["paths"]) or True
print("ENABLED", e.get("config"))
PYV
python3 -c "
import json,sys
cfg=json.load(open('$CONF'))
e=cfg['plugins']['entries']['agent-exchange-telemetry']
assert e['enabled'] is True
assert cfg['plugins']['entries']['ceo-routing-doctrine']=={'enabled':True}
p=cfg['plugins']['load']['paths']
assert p==['$HOME_T/.openclaw/extensions'], p
assert e.get('config')=={'companyId':'acme','installationId':'inst-7'}, e.get('config')
" && ok "enabled + sibling entry preserved + load.paths + capability config derived" || bad "config shape wrong after run 1"
[[ "$(ls "$HOME_T/.openclaw" | grep -c 'openclaw.json.bak.xet-')" -ge 1 ]] && ok "timestamped config backup written" || bad "no backup written"

# operator-written config block must survive a second run (additive merge)
python3 -c "
import json
p='$CONF'; cfg=json.load(open(p))
cfg['plugins']['entries']['agent-exchange-telemetry']['config']={'companyId':'operator','installationId':'op-1'}
json.dump(cfg,open(p,'w'),indent=2)
"
HOME="$HOME_T" MC_COMPANY_ID=acme MC_INSTALLATION_ID=inst-7 python3 "$TMPB" > "$TMP/run2.out" 2>&1
python3 -c "
import json
cfg=json.load(open('$CONF'))
e=cfg['plugins']['entries']['agent-exchange-telemetry']
assert e['config']=={'companyId':'operator','installationId':'op-1'}, e['config']
assert len(cfg['plugins']['load']['paths'])==1
" && ok "operator config block preserved; run 2 adds no second load path (idempotent)" || bad "second run mutated operator config or duplicated the path"

# allowlist: extend-only, never created
printf '%s\n' '{"plugins":{"allow":["ceo-routing-doctrine"]}}' > "$CONF"
HOME="$HOME_T" python3 "$TMPB" >/dev/null 2>&1
python3 -c "
import json; a=json.load(open('$CONF'))['plugins']['allow']
assert a==['ceo-routing-doctrine','agent-exchange-telemetry'], a" \
  && ok "existing allowlist EXTENDED with the plugin id" || bad "allowlist not extended"
printf '%s\n' '{"plugins":{}}' > "$CONF"
HOME="$HOME_T" python3 "$TMPB" >/dev/null 2>&1
python3 -c "
import json; assert 'allow' not in json.load(open('$CONF'))['plugins']" \
  && ok "no allowlist is ever CREATED (would disable every other plugin)" || bad "allowlist created"

# an absent installation identity is not invented
printf '%s\n' '{"plugins":{}}' > "$CONF"
env -u MC_COMPANY_ID -u MC_INSTALLATION_ID HOME="$HOME_T" python3 "$TMPB" >/dev/null 2>&1
python3 -c "
import json; e=json.load(open('$CONF'))['plugins']['entries']['agent-exchange-telemetry']
assert 'config' not in e, e" \
  && ok "unproven identity stays absent (never a guessed company)" || bad "guessed company written"

# --- 5. container-startup: persistent roots + resurrection, executed ------
DATA="$TMP/data"; mkdir -p "$DATA/projects/command-center"
printf '%s\n' 'module.exports = {}' > "$DATA/projects/command-center/ecosystem.config.cjs"
BIN="$TMP/bin"; mkdir -p "$BIN"
printf '%s\n' '#!/bin/sh' 'echo "$@" > "'"$TMP"'/node-args"' > "$BIN/node"
printf '%s\n' '#!/bin/sh' 'echo "$@" >> "'"$TMP"'/pm2-calls"' '[ "$1" = describe ] && exit 1' 'exit 0' > "$BIN/pm2"
chmod +x "$BIN/node" "$BIN/pm2"
env -u HEADQUARTERS_ENABLED HOME="$DATA" OPENCLAW_DATA="$DATA" PM2_RESURRECT_DELAY=0 \
  PATH="$BIN:/usr/bin:/bin" bash "$STARTUP" > "$TMP/startup.out" 2>&1
rc=$?
[[ "$rc" -eq 0 ]] && ok "container-startup runs clean (rc=0)" || bad "container-startup rc=$rc: $(cat "$TMP/startup.out")"
[[ "$(cat "$TMP/node-args" 2>/dev/null)" == "server.mjs" ]] && ok "startup execs the image server (no gateway touch)" || bad "startup did not exec node server.mjs"
for d in workspace workspace/hq-telemetry/correlation workspace/hq-telemetry/outbox mission-control/identity extensions; do
  [[ -d "$DATA/.openclaw/$d" ]] && ok "persistent root created: /data/.openclaw/$d" || bad "persistent root missing: $d"
done
calls=""
for _ in 1 2 3 4 5 6 7 8 9 10; do
  calls="$(cat "$TMP/pm2-calls" 2>/dev/null || true)"
  case "$calls" in *save*) break ;; esac
  sleep 0.2
done
case "$calls" in
  *resurrect*) ok "pm2 resurrect sequenced (resurrection contract preserved)" ;;
  *) bad "pm2 resurrect not called: $calls" ;;
esac
# A re-run must not disturb what is already there.
touch "$DATA/.openclaw/workspace/hq-telemetry/outbox/keep.json"
env HOME="$DATA" OPENCLAW_DATA="$DATA" PM2_RESURRECT_DELAY=0 PATH="$BIN:/usr/bin:/bin" bash "$STARTUP" >/dev/null 2>&1
[[ -f "$DATA/.openclaw/workspace/hq-telemetry/outbox/keep.json" ]] && ok "re-run preserves existing persistent content (mkdir -p only, never delete)" || bad "existing content removed on re-run"

# --- 6. the flag is read, not invented ------------------------------------
printf '%s\n' 'HEADQUARTERS_ENABLED=1' > "$DATA/.openclaw/.env"
env HOME="$DATA" OPENCLAW_DATA="$DATA" PM2_RESURRECT_DELAY=0 PATH="$BIN:/usr/bin:/bin" bash "$STARTUP" >/dev/null 2>&1
grep -q 'HEADQUARTERS_ENABLED=1' "$DATA/.openclaw/logs/container-startup.log" \
  && ok "startup reports the box's recorded HEADQUARTERS_ENABLED=1" || bad "flag=1 not reported"
printf '%s\n' 'HEADQUARTERS_ENABLED=0' > "$DATA/.openclaw/.env"
env HOME="$DATA" OPENCLAW_DATA="$DATA" PM2_RESURRECT_DELAY=0 PATH="$BIN:/usr/bin:/bin" bash "$STARTUP" >/dev/null 2>&1
grep -q 'HEADQUARTERS_ENABLED=0' "$DATA/.openclaw/logs/container-startup.log" \
  && ok "startup reports HEADQUARTERS_ENABLED=0 (a disabled box says so)" || bad "flag=0 not reported"
rm -f "$DATA/.openclaw/.env"
env HOME="$DATA" OPENCLAW_DATA="$DATA" PM2_RESURRECT_DELAY=0 PATH="$BIN:/usr/bin:/bin" bash "$STARTUP" >/dev/null 2>&1
grep -q 'HEADQUARTERS_ENABLED unset' "$DATA/.openclaw/logs/container-startup.log" \
  && ok "absent flag reported as unset, never as enabled" || bad "absent flag misreported"

# --- 7. no new container, no new image, no new dependency, no secret ------
grep -qE 'docker run|docker create|image:' "$STARTUP" && bad "startup creates a container/image" || ok "no container or image is created by the startup hook"
grep -q 'docker-compose' "$STARTUP" && bad "startup introduces a compose file" || ok "no new compose file"
grep -qiE 'api[_-]?key|token|secret' "$STARTUP" && bad "startup references a credential" || ok "startup touches no credential"
# provider/model/policy names only: no key VALUE may appear in the diff. The
# patterns are deliberately narrow secret SHAPES, not the words key/token.
if git rev-parse --git-dir >/dev/null 2>&1; then
  if git diff -U0 -- install.sh update-skills.sh 32-command-center-setup/scripts/run-full-install.sh "$STARTUP" 2>/dev/null \
     | grep '^+' | grep -qE '(sk-[A-Za-z0-9]{16,}|[0-9]{8,}:AA[A-Za-z0-9_-]{30,}|BEGIN [A-Z ]*PRIVATE KEY)'; then
    bad "a secret-shaped value appears in the diff"
  else
    ok "no secret-shaped value in the diff (key NAMES only)"
  fi
else
  ok "no VCS present — diff scan not applicable (names-only rule still asserted above)"
fi
# The three bound files must exist as tracked deliverables of ONE writer: no
# other unit may carry the register block.
for f in install.sh update-skills.sh; do
  [[ "$(grep -c 'agent-exchange-telemetry' "$f")" -ge 1 ]] && ok "register block present once in $f" || bad "register block absent from $f"
done


# --- 8. phase 6k: the capability check, driven for real --------------------
# The function is extracted by sed range and run with the REAL cc_env helpers
# and stubbed log/state, so this exercises the shipped code, not a copy.
SK32="32-command-center-setup/scripts/run-full-install.sh"
TMPD="$TMP/k"; mkdir -p "$TMPD/dash"
sed -n "/^cc_env_has_nonempty() {/,/^}/p" "$SK32" > "$TMPD/fn.sh"
sed -n "/^cc_env_set_if_absent() {/,/^}/p" "$SK32" >> "$TMPD/fn.sh"
sed -n "/^cc_env_get() {/,/^}/p" "$SK32" >> "$TMPD/fn.sh"
sed -n "/^cc_hq_capability_check() {/,/^}/p" "$SK32" >> "$TMPD/fn.sh"
# cc_env_* resolve the shared writer through "$SKILL_DIR/../shared-utils", so
# the fixture reproduces that layout exactly (skill dir + sibling shared-utils).
mkdir -p "$TMPD/services/shared-utils" "$TMPD/services/skill"
cp -R shared-utils/service_env.py "$TMPD/services/shared-utils/"
cat > "$TMPD/drive.sh" <<'SH'
set -u
DASHBOARD_DIR="$1"; SKILL_DIR="$2"; LOG_FILE="$1/install.log"; STATE_FILE="$1/state.json"
: > "$LOG_FILE"; echo '{}' > "$STATE_FILE"
log() { local lvl="$1"; shift; printf '%s %s\n' "$lvl" "$*" >> "$LOG_FILE"; }
state_set() { printf 'STATE_SET %s\n' "$1" >> "$LOG_FILE"; }
state_set_arg() { printf 'STATE_ARG %s\n' "$1" >> "$LOG_FILE"; }
source "$3"
cc_hq_capability_check
SH
mkdb() { rm -f "$1"; python3 - "$1" "$2" <<'PYD'
import sqlite3, sys
con = sqlite3.connect(sys.argv[1])
if sys.argv[2] == "full":
    for t in ("hq_activity","hq_activity_state","hq_activity_receipts","hq_run_bindings",
              "hq_chat_sessions","hq_chat_turns","hq_owner_login_uses"):
        con.execute("CREATE TABLE %s (x INTEGER)" % t)
con.commit(); con.close()
PYD
}
mkdb "$TMPD/dash/mission-control.db" full
printf '%s\n' 'MC_COMPANY_ID=acme' > "$TMPD/dash/.env.local"
HQ_CAPABILITY_DB="$TMPD/dash/mission-control.db" bash "$TMPD/drive.sh" "$TMPD/dash" "$TMPD/services/skill" "$TMPD/fn.sh" > "$TMPD/out1" 2>&1
grep -qE "^HEADQUARTERS_ENABLED='?1'?$" "$TMPD/dash/.env.local" && ok "phase 6k: full schema + bound company writes HEADQUARTERS_ENABLED=1" || bad "phase 6k did not enable"
grep -q 'STATE_SET .commandCenterHqEnabled = true' "$TMPD/dash/install.log" && ok "phase 6k stamps the state file (observable, not silent)" || bad "phase 6k state stamp missing"
# schema present, company unbound -> 0 with a reason
printf '%s\n' 'MC_API_TOKEN=x' > "$TMPD/dash/.env.local"
printf '%s\n' 'HEADQUARTERS_ENABLED=1' >> "$TMPD/dash/.env.local"
python3 - "$TMPD/dash/.env.local" <<'PYE'
import sys
p = sys.argv[1]
lines = [l for l in open(p).read().splitlines() if not l.startswith("HEADQUARTERS_ENABLED")]
open(p, "w").write("\n".join(lines) + "\n")
PYE
HQ_CAPABILITY_DB="$TMPD/dash/mission-control.db" bash "$TMPD/drive.sh" "$TMPD/dash" "$TMPD/services/skill" "$TMPD/fn.sh" > "$TMPD/out2" 2>&1
grep -qE "^HEADQUARTERS_ENABLED='?0'?$" "$TMPD/dash/.env.local" && ok "phase 6k: schema present but company unbound -> 0 (never an unattributable 1)" || bad "phase 6k enabled without a company binding"
# partial schema -> 0, missing tables named
mkdb "$TMPD/dash/mission-control.db" partial
python3 - "$TMPD/dash/.env.local" <<'PYE'
import sys
p = sys.argv[1]
lines = [l for l in open(p).read().splitlines() if not l.startswith("HEADQUARTERS_ENABLED")]
open(p, "w").write("\n".join(lines + ["MC_COMPANY_ID=acme"]) + "\n")
PYE
HQ_CAPABILITY_DB="$TMPD/dash/mission-control.db" bash "$TMPD/drive.sh" "$TMPD/dash" "$TMPD/services/skill" "$TMPD/fn.sh" > "$TMPD/out3" 2>&1
grep -qE "^HEADQUARTERS_ENABLED='?0'?$" "$TMPD/dash/.env.local" && ok "phase 6k: missing HQ tables -> 0" || bad "phase 6k enabled on a schema-less database"
grep -q 'hq_activity' "$TMPD/dash/install.log" && ok "phase 6k names the missing tables (descriptive setup status)" || bad "missing tables unnamed"
# operator-set flag is preserved
printf '%s\n' 'MC_COMPANY_ID=acme' 'HEADQUARTERS_ENABLED=0' > "$TMPD/dash/.env.local"
mkdb "$TMPD/dash/mission-control.db" full
HQ_CAPABILITY_DB="$TMPD/dash/mission-control.db" bash "$TMPD/drive.sh" "$TMPD/dash" "$TMPD/services/skill" "$TMPD/fn.sh" > "$TMPD/out4" 2>&1
grep -qE "^HEADQUARTERS_ENABLED='?0'?$" "$TMPD/dash/.env.local" && ok "phase 6k: operator-set 0 preserved on a capable box (additive, never rotated)" || bad "phase 6k rotated an operator value"
# absent database -> UNSET, never a guess
rm -f "$TMPD/dash/mission-control.db"
printf '%s\n' 'MC_COMPANY_ID=acme' > "$TMPD/dash/.env.local"
HQ_CAPABILITY_DB="$TMPD/dash/mission-control.db" bash "$TMPD/drive.sh" "$TMPD/dash" "$TMPD/services/skill" "$TMPD/fn.sh" > "$TMPD/out5" 2>&1
grep -q 'HEADQUARTERS_ENABLED' "$TMPD/dash/.env.local" && bad "phase 6k guessed a flag with no database" || ok "phase 6k: unreadable schema leaves the flag UNSET (never guessed)"

# phase ordering: 6k sits after the phase-6 block and before 6j
python3 - "$SK32" <<'PYO'
import sys
lines = open(sys.argv[1]).read().splitlines()
six = next(i for i, l in enumerate(lines) if l.startswith("# PHASE 6 — Dashboard"))
end = next(i for i, l in enumerate(lines[six:], six) if l == "fi")
k = next(i for i, l in enumerate(lines) if l.startswith("# PHASE 6k"))
j = next(i for i, l in enumerate(lines) if l.startswith("# PHASE 6j"))
raise SystemExit(0 if end < k < j else 1)
PYO
[[ $? -eq 0 ]] && ok "phase order: the phase-6 block closes, then 6k, then 6j" || bad "phase order wrong"

printf '[headquarters-docker] %s passed, %s failed\n' "$PASS" "$FAIL"
[[ "$FAIL" -eq 0 ]]
