#!/usr/bin/env bash
# tests/unit/report-missing-999.test.sh
# -----------------------------------------------------------------------------
# Locks scripts/fleet-roll/report-missing-999.sh (operator-box, read-only report
# of fleet boxes without 999-setup installed).
#
# Hermetic: a fake fleet-access tool and a fake ssh, both driven by fixture
# home directories under a mktemp sandbox. No real fleet box, no network, no
# ~/.ssh/config, no ~/.openclaw.
#
#   T1  --selftest passes (the probe separates installed / empty / partial)
#   T2  installed via a Documents checkout        -> INSTALLED
#   T3  installed via the skill link              -> INSTALLED
#   T4  empty home / partial checkout             -> MISSING (listed in the
#       MISSING section)
#   T5  fleet-access says REFUSED                 -> UNKNOWN, never MISSING
#   T6  ssh dies silently on a "reachable" box    -> UNKNOWN, never MISSING
#   T7  VPS / Contabo (no per-box shell route)    -> UNKNOWN, never MISSING
#   T8  hostile alias from tool output            -> UNKNOWN, ssh never run on it
#   T9  operator (local) box is probed in place   -> INSTALLED
#   T10 fleet-access exit 2 / garbage output      -> exit 2, no report printed
#   T11 read-only: the only remote command is `sh -s`, no fixture file changed,
#       probe body carries no write/network verb
#   T12 runs under /bin/bash 3.2 (macOS system bash) and the final RESULT line
#       counts add up
#   T13 the probe's checkout locations match shared-utils/fleet_refresh_runner.py
#       (a drift here means the report disagrees with what the roll refreshes)
#
# Exit 0 = all pass.
# -----------------------------------------------------------------------------
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/fleet-roll/report-missing-999.sh"
RUNNER="$REPO_ROOT/shared-utils/fleet_refresh_runner.py"

PASS=0
FAIL=0
ok()  { printf '  ok   %s\n' "$1"; PASS=$((PASS + 1)); }
bad() { printf '  FAIL %s\n' "$1"; FAIL=$((FAIL + 1)); }
hdr() { printf '\n== %s ==\n' "$1"; }
has() { grep -qF -- "$2" "$1"; }

SANDBOX="$(mktemp -d "${TMPDIR:-/tmp}/report-missing-999-test.XXXXXX")"
trap 'rm -rf "$SANDBOX"' EXIT
FX="$SANDBOX/fx"
mkdir -p "$FX/homes"

# --- fixture homes (one per fake alias) ---------------------------------------
plant_checkout() {   # plant_checkout <home> <relative checkout dir>
  local d="$1/$2"
  mkdir -p "$d/.claude/skills/nine-router-setup/scripts" "$d/CONTROL"
  : > "$d/.claude/skills/nine-router-setup/scripts/setup-macos.sh"
  : > "$d/AGENT_INSTALL.md"
  : > "$d/CONTROL/bundled-skills.txt"
}
mkdir -p "$FX/homes/rescue-inst-docs" "$FX/homes/rescue-inst-link" "$FX/homes/rescue-empty" \
         "$FX/homes/rescue-partial" "$FX/homes/rescue-silent" "$FX/homes/local-home"
plant_checkout "$FX/homes/rescue-inst-docs" "Documents/999-setup"
plant_checkout "$FX/homes/rescue-inst-link" "Elsewhere/my-999"
mkdir -p "$FX/homes/rescue-inst-link/.claude/skills"
ln -s "$FX/homes/rescue-inst-link/Elsewhere/my-999/.claude/skills/nine-router-setup" \
      "$FX/homes/rescue-inst-link/.claude/skills/nine-router-setup"
mkdir -p "$FX/homes/rescue-partial/Documents/999-setup/CONTROL"
: > "$FX/homes/rescue-partial/Documents/999-setup/CONTROL/bundled-skills.txt"
plant_checkout "$FX/homes/local-home" "Downloads/999-setup-main"

# --- fake fleet-access: preamble + JSON, same shape as the real --all --json ---
cat > "$FX/fleet.json" <<'JSON_EOF'
{
 "sources": {"ssh_config": {"status": "OK", "rows": 4}},
 "boxes": [
  {"slug": "rescue-inst-docs", "platform": "mac", "verdict": "REACHABLE",
   "paths": [{"path": "P1", "route": "alias:rescue-inst-docs", "verdict": "REACHABLE", "reason": "host"}]},
  {"slug": "rescue-inst-link", "platform": "mac", "verdict": "REACHABLE",
   "paths": [{"path": "P1", "route": "alias:rescue-inst-link", "verdict": "REACHABLE", "reason": "host"}]},
  {"slug": "rescue-empty", "platform": "mac", "verdict": "REACHABLE",
   "paths": [{"path": "P1", "route": "alias:rescue-empty", "verdict": "REACHABLE", "reason": "host"}]},
  {"slug": "rescue-partial", "platform": "mac", "verdict": "REACHABLE",
   "paths": [{"path": "P1", "route": "alias:rescue-partial", "verdict": "REACHABLE", "reason": "host"}]},
  {"slug": "rescue-silent", "platform": "mac", "verdict": "REACHABLE",
   "paths": [{"path": "P1", "route": "alias:rescue-silent", "verdict": "REACHABLE", "reason": "host"}]},
  {"slug": "rescue-refused", "platform": "mac", "verdict": "ROUTE_FOUND_BUT_REFUSED(auth-denied)",
   "paths": [{"path": "P1", "route": "alias:rescue-refused", "verdict": "ROUTE_FOUND_BUT_REFUSED", "reason": "auth-denied"}]},
  {"slug": "rescue-hostile", "platform": "mac", "verdict": "REACHABLE",
   "paths": [{"path": "P1", "route": "alias:-oProxyCommand=touch SANDBOX_PWNED", "verdict": "REACHABLE", "reason": "host"}]},
  {"slug": "openclaw-vps1", "platform": "vps", "verdict": "REACHABLE",
   "paths": [{"path": "P3", "route": "root@<ip:redacted>", "verdict": "REACHABLE", "reason": "host"}]},
  {"slug": "oc-contabo1", "platform": "contabo", "verdict": "REACHABLE",
   "paths": [{"path": "P3", "route": "alias:contabo-host", "verdict": "REACHABLE", "reason": "host"}]},
  {"slug": "operator-box", "platform": "local", "verdict": "REACHABLE", "paths": []}
 ],
 "class_control": {"mac": {"reachable": 5, "total": 7}},
 "class_control_failed": [],
 "class_control_suspect": {}
}
JSON_EOF
sed -i.bak "s#SANDBOX_PWNED#$SANDBOX/PWNED#" "$FX/fleet.json" && rm -f "$FX/fleet.json.bak"

cat > "$FX/fake-fleet-access.sh" <<EOF
#!/bin/sh
[ "\$1" = "--all" ] && [ "\$2" = "--json" ] || { echo "fake fleet-access: bad args \$*" >&2; exit 64; }
echo "SOURCES CONSULTED (every one, with load status):"
echo "  ok ssh_config               OK       rows=4   ~/.ssh/config"
cat "$FX/fleet.json"
EOF
chmod +x "$FX/fake-fleet-access.sh"

# --- fake ssh: records the remote command, runs the probe in the alias's home --
cat > "$FX/fake-ssh.sh" <<EOF
#!/bin/sh
# last arg = remote command, second-to-last = alias (real ssh option shape)
for a in "\$@"; do prev2=\$prev1; prev1=\$a; done
alias_name=\$prev2; remote=\$prev1
echo "\$alias_name|\$remote" >> "$FX/ssh-calls.log"
case "\$alias_name" in
  -*) echo "fake ssh: option-shaped host was passed" >&2; exit 97 ;;
  rescue-silent) exit 255 ;;
esac
HOME="$FX/homes/\$alias_name" exec /bin/sh -c "\$remote"
EOF
chmod +x "$FX/fake-ssh.sh"

snapshot() { (cd "$FX/homes" && find . | LC_ALL=C sort | cksum); }

run() {   # run <outfile> [args]  -> sets RC
  local out="$1"; shift
  : > "$FX/ssh-calls.log"
  FLEET_ACCESS_BIN="$FX/fake-fleet-access.sh" REPORT_999_SSH_BIN="$FX/fake-ssh.sh" \
    HOME="$FX/homes/local-home" "$SCRIPT" "$@" > "$out" 2> "$out.err"
  RC=$?
}

# ------------------------------------------------------------------------------
hdr "T1 selftest"
run "$SANDBOX/self.out" --selftest
[ "$RC" -eq 0 ] && has "$SANDBOX/self.out" "SELFTEST PASSED" && ok "selftest passes" || bad "selftest rc=$RC"

hdr "T2-T9 full report against fixtures"
BEFORE="$(snapshot)"
run "$SANDBOX/report.out"
R="$SANDBOX/report.out"
[ "$RC" -eq 0 ] && ok "report exits 0" || bad "report exit $RC: $(tail -n 3 "$R.err")"

section() {   # section <HEADER-prefix> -> body lines up to blank line
  awk -v h="$1" 'index($0,h)==1{f=1;next} f&&/^$/{exit} f{print}' "$R"
}
MISSING_SEC="$(section 'MISSING 999-setup')"
INSTALLED_SEC="$(section 'INSTALLED (')"
UNKNOWN_SEC="$(section 'UNKNOWN (')"

grep -q 'rescue-inst-docs.*~/Documents/999-setup' <<<"$INSTALLED_SEC" && ok "T2 Documents checkout -> INSTALLED" || bad "T2 inst-docs not INSTALLED: $INSTALLED_SEC"
grep -q 'rescue-inst-link' <<<"$INSTALLED_SEC" && ok "T3 skill-link install -> INSTALLED" || bad "T3 inst-link not INSTALLED"
grep -q 'rescue-empty' <<<"$MISSING_SEC" && ok "T4 empty home -> MISSING" || bad "T4 empty not MISSING"
grep -q 'rescue-partial' <<<"$MISSING_SEC" && ok "T4 partial checkout -> MISSING" || bad "T4 partial not MISSING"
grep -q 'rescue-refused' <<<"$UNKNOWN_SEC" && ! grep -q 'rescue-refused' <<<"$MISSING_SEC" && ok "T5 refused -> UNKNOWN, not MISSING" || bad "T5 refused misfiled"
grep -q 'rescue-silent' <<<"$UNKNOWN_SEC" && ! grep -q 'rescue-silent' <<<"$MISSING_SEC" && ok "T6 silent ssh failure -> UNKNOWN, not MISSING" || bad "T6 silent misfiled"
{ grep -q 'openclaw-vps1' <<<"$UNKNOWN_SEC" && grep -q 'oc-contabo1' <<<"$UNKNOWN_SEC"; } \
  && ! grep -qE 'openclaw-vps1|oc-contabo1' <<<"$MISSING_SEC" && ok "T7 vps + contabo -> UNKNOWN, not MISSING" || bad "T7 vps/contabo misfiled"
grep -q 'rescue-hostile' <<<"$UNKNOWN_SEC" && ok "T8 hostile alias -> UNKNOWN" || bad "T8 hostile alias not UNKNOWN"
[ ! -e "$SANDBOX/PWNED" ] && ! grep -q '^-' "$FX/ssh-calls.log" && ok "T8 option-shaped alias never reached ssh" || bad "T8 hostile alias reached ssh"
grep -q 'operator-box.*Downloads/999-setup-main' <<<"$INSTALLED_SEC" && ok "T9 operator box probed in place -> INSTALLED" || bad "T9 operator box: $INSTALLED_SEC"
grep -q 'NOT searched' "$R" && ok "report names what was not searched" || bad "report omits the not-searched line"

hdr "T11 read-only"
AFTER="$(snapshot)"
[ "$BEFORE" = "$AFTER" ] && ok "no fixture file created, changed or removed" || bad "fixture tree changed during the report"
BADCMD="$(cut -d'|' -f2- "$FX/ssh-calls.log" | sort -u | grep -vx 'sh -s' || true)"
[ -z "$BADCMD" ] && [ -s "$FX/ssh-calls.log" ] && ok "only remote command is: sh -s" || bad "unexpected remote command: $BADCMD"
PROBE_BODY="$(awk "/^cat > \"\\\$PROBE\" <<'PROBE_EOF'/{f=1;next} /^PROBE_EOF/{f=0} f" "$SCRIPT")"
[ -n "$PROBE_BODY" ] || bad "could not extract probe body"
# 2>/dev/null only discards stderr; every other redirect or write verb is a failure
PROBE_CHECK="$(sed 's#2>/dev/null##g' <<<"$PROBE_BODY")"
if grep -qE '(^|[^a-z_])(rm|mv|cp|mkdir|touch|tee|curl|wget|git|sudo|chmod|ln|dd|sed -i)([^a-z_]|$)|>' <<<"$PROBE_CHECK"; then
  bad "probe body contains a write or network verb"
else
  ok "probe body has no write or network verb"
fi
if grep -v '^[[:space:]]*#' "$SCRIPT" | grep -q 'ssh/config'; then bad "script reads ssh config directly"; else ok "never reads ~/.ssh/config (fleet-access only)"; fi

hdr "T12 counts + bash 3.2"
TOTAL_LINE="$(grep '^RESULT ' "$R")"
[ "$TOTAL_LINE" = "RESULT total=10 missing=2 installed=3 unknown=5" ] && ok "RESULT line: $TOTAL_LINE" || bad "RESULT line wrong: '$TOTAL_LINE'"
if [ -x /bin/bash ]; then
  : > "$FX/ssh-calls.log"
  FLEET_ACCESS_BIN="$FX/fake-fleet-access.sh" REPORT_999_SSH_BIN="$FX/fake-ssh.sh" \
    HOME="$FX/homes/local-home" /bin/bash "$SCRIPT" > "$SANDBOX/b3.out" 2> "$SANDBOX/b3.err"
  B3=$?
  [ "$B3" -eq 0 ] && [ "$(grep '^RESULT ' "$SANDBOX/b3.out")" = "$TOTAL_LINE" ] && ok "same report under /bin/bash" || bad "/bin/bash run rc=$B3: $(tail -n 2 "$SANDBOX/b3.err")"
fi

hdr "T10 tooling failure is exit 2 with no report"
cat > "$FX/failing-fleet-access.sh" <<'EOF'
#!/bin/sh
echo "TOOLING FAILURE: not one source loaded." >&2
exit 2
EOF
cat > "$FX/garbage-fleet-access.sh" <<'EOF'
#!/bin/sh
echo "SOURCES CONSULTED"
echo "no json here"
EOF
cat > "$FX/empty-fleet-access.sh" <<'EOF'
#!/bin/sh
printf '{\n "boxes": []\n}\n'
EOF
chmod +x "$FX"/failing-fleet-access.sh "$FX"/garbage-fleet-access.sh "$FX"/empty-fleet-access.sh
for t in failing garbage empty; do
  FLEET_ACCESS_BIN="$FX/$t-fleet-access.sh" REPORT_999_SSH_BIN="$FX/fake-ssh.sh" \
    HOME="$FX/homes/local-home" "$SCRIPT" > "$SANDBOX/$t.out" 2> "$SANDBOX/$t.err"
  rc=$?
  if [ "$rc" -eq 2 ] && ! grep -q 'MISSING 999-setup' "$SANDBOX/$t.out" && has "$SANDBOX/$t.err" "TOOLING FAILURE"; then
    ok "$t fleet-access -> exit 2, no report"
  else
    bad "$t fleet-access -> rc=$rc (want 2, no report)"
  fi
done

hdr "T13 probe locations match the roll's refresh step"
if /usr/bin/python3 - "$RUNNER" "$SCRIPT" <<'PY_EOF'
import re, sys
runner = open(sys.argv[1]).read()
script = open(sys.argv[2]).read()
def tup(name):
    m = re.search(name + r"\s*=\s*\((.*?)\)", runner, re.S)
    return re.findall(r'"([^"]+)"', m.group(1))
links, cands = tup("_999_SKILL_LINKS"), tup("_999_CANDIDATES")
inst = re.search(r'_999_INSTALLER\s*=\s*"([^"]+)"', runner).group(1)
probe = re.search(r"<<'PROBE_EOF'\n(.*?)\nPROBE_EOF", script, re.S).group(1)
missing = [x for x in links + cands if x not in probe]
if inst.replace(".claude/skills/nine-router-setup/", "") not in probe:
    missing.append(inst)
for f in ("AGENT_INSTALL.md", "CONTROL/bundled-skills.txt"):
    if f not in probe:
        missing.append(f)
if missing:
    sys.exit("probe is missing runner locations: %s" % missing)
PY_EOF
then ok "every runner location and marker file is in the probe"; else bad "probe drifted from fleet_refresh_runner.py"; fi

printf '\n%d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
