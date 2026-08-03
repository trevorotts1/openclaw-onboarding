#!/usr/bin/env bash
# =============================================================================
# Tests for audit-podcast-activation.sh (fleet podcast activation audit).
#
# Hermetic by construction: no real ssh, no network, no fleet access. The ssh
# binary is a PATH shim whose behavior is scripted per test; remote boxes are
# simulated by the shim emitting the marker contract, and local boxes run the
# real built-in probe against a sandboxed OC root (PODCAST_OC_ROOT_LOCAL).
#
# Assertions:
#   T1  bash -n passes
#   T2  healthy local fixture grades PASS on all four pieces, exit 0
#   T3  fixture missing controller + scheduler grades FAIL, counted as
#       "missing processor" in the summary, exit 1
#   T4  --box filters to one box; unknown slug exits 3
#   T5  vps transport: ssh shim sees BatchMode + docker exec -i -u node
#       <container> bash -s; markers from the shim grade the box
#   T6  mac transport: ssh shim sees the ssh alias and zsh -lc wrapper
#   T7  unreachable box grades UNREACHABLE and never aborts the sweep
#   T8  registry row without transport info grades SKIPPED
#   T9  targets-format roster (--boxes) is read; client identity fields are
#       never printed (canary strings absent from the output)
#   T10 guard-activation-health.py on the box is preferred when it emits
#       ACT_* markers; its NOTE lines surface in the report
#   T11 no secret value (fixture hooks token) ever appears in the output
#   T12 guard that emits no markers falls back to the built-in probe
# =============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_UNDER_TEST="$HERE/../audit-podcast-activation.sh"

PASS_COUNT=0
FAIL_COUNT=0
ok()   { PASS_COUNT=$((PASS_COUNT + 1)); printf 'PASS %s\n' "$1"; }
bad()  { FAIL_COUNT=$((FAIL_COUNT + 1)); printf 'FAIL %s\n' "$1"; }
assert() { # $1=description $2=condition-result (0 true)
  if [ "$2" = "0" ]; then ok "$1"; else bad "$1"; fi
}

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
MOCK_BIN="$WORK/bin"
mkdir -p "$MOCK_BIN"

# --- T1: syntax -------------------------------------------------------------
if bash -n "$SCRIPT_UNDER_TEST"; then ok "T1 bash -n"; else bad "T1 bash -n"; fi

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
SECRET_CANARY="SEKR1T-TOKEN-CANARY-9f8e7d"
IDENTITY_CANARY="canary-identity-9f8e7d@example.com"

# Healthy box: hook mapping + agent + controller + cron-based scheduler.
ROOT_HEALTHY="$WORK/oc-healthy"
mkdir -p "$ROOT_HEALTHY/skills/58-podcast-production-engine/scripts" "$ROOT_HEALTHY/cron"
touch "$ROOT_HEALTHY/skills/58-podcast-production-engine/scripts/podcast_controller.py"
cat > "$ROOT_HEALTHY/openclaw.json" <<EOF
{
  "hooks": {
    "enabled": true,
    "token": "${SECRET_CANARY}",
    "mappings": [
      {"id": "podcast-intake-demo", "name": "podcast-intake-demo",
       "sessionKey": "podcast:intake:demo", "agentId": "dept-podcast"}
    ]
  },
  "agents": {"list": [{"id": "dept-podcast", "name": "Podcast"}]}
}
EOF
cat > "$ROOT_HEALTHY/cron/jobs.json" <<'EOF'
{"version": 1, "jobs": [
  {"name": "podcast-smoke-demo", "enabled": true},
  {"name": "podcast-processor-demo", "enabled": true}
]}
EOF

# Broken box: agent present, no hook mapping, no controller, scheduler script
# only via the smoke-test cron (which must NOT count as the processor).
ROOT_BROKEN="$WORK/oc-broken"
mkdir -p "$ROOT_BROKEN/skills/58-podcast-production-engine/scripts" "$ROOT_BROKEN/cron"
cat > "$ROOT_BROKEN/openclaw.json" <<'EOF'
{
  "hooks": {"enabled": true, "token": "x", "mappings": []},
  "agents": {"list": [{"id": "dept-podcast"}]}
}
EOF
cat > "$ROOT_BROKEN/cron/jobs.json" <<'EOF'
{"version": 1, "jobs": [{"name": "podcast-smoke-demo", "enabled": true}]}
EOF

# Fixture whose skill dir carries a working activation guard.
ROOT_GUARDED="$WORK/oc-guarded"
mkdir -p "$ROOT_GUARDED/skills/58-podcast-production-engine/scripts"
cat > "$ROOT_GUARDED/skills/58-podcast-production-engine/scripts/guard-activation-health.py" <<'EOF'
#!/usr/bin/env python3
import sys
print("ACT_HOOK=PASS")
print("ACT_AGENT=PASS")
print("ACT_CONTROLLER=PASS")
print("ACT_SCHEDULER=FAIL")
print("ACT_OVERALL=FAIL")
print("NOTE: guard fixture ran (marker source: guard)")
sys.exit(7)  # exit code must be IGNORED; markers grade the box
EOF
cat > "$ROOT_GUARDED/openclaw.json" <<'EOF'
{"hooks": {"enabled": false, "token": "", "mappings": []}, "agents": {"list": []}}
EOF

# Fixture whose guard emits NO markers: must fall back to the built-in probe.
ROOT_BADGUARD="$WORK/oc-badguard"
mkdir -p "$ROOT_BADGUARD/skills/58-podcast-production-engine/scripts"
cat > "$ROOT_BADGUARD/skills/58-podcast-production-engine/scripts/guard-activation-health.py" <<'EOF'
#!/usr/bin/env python3
print("nothing useful here")
EOF
cat > "$ROOT_BADGUARD/openclaw.json" <<'EOF'
{"hooks": {"enabled": true, "token": "t",
           "mappings": [{"id": "podcast-intake-z", "sessionKey": "podcast:intake:z", "agentId": "dept-podcast"}]},
 "agents": {"list": [{"id": "dept-podcast"}]}}
EOF
mkdir -p "$ROOT_BADGUARD/cron"
printf '{"version":1,"jobs":[{"name":"podcast-processor-z","enabled":true}]}\n' > "$ROOT_BADGUARD/cron/jobs.json"

# Registry fixture: one healthy local, one broken local, one guarded local,
# one vps with transport, one mac, one unreachable mac, one vps missing
# transport info.
REGISTRY="$WORK/registry.json"
cat > "$REGISTRY" <<'EOF'
{"_doc": "test", "boxes": {
  "box-healthy":   {"kind": "local"},
  "box-broken":    {"kind": "local"},
  "box-guarded":   {"kind": "local"},
  "box-badguard":  {"kind": "local"},
  "box-vps":       {"kind": "vps", "ssh_target": "root@203.0.113.7", "container": "openclaw-boxvps-openclaw-1"},
  "box-mac":       {"kind": "mac", "ssh_alias": "rescue-box-mac"},
  "box-dark":      {"kind": "mac", "ssh_alias": "rescue-box-dark"},
  "box-notransport": {"kind": "vps"}
}}
EOF

# ssh shim. Behavior driven by $MOCK_SSH_PLAN (path to a file mapping ssh
# alias/target to an action). Records every invocation to $MOCK_SSH_LOG.
cat > "$MOCK_BIN/ssh" <<EOF
#!/usr/bin/env bash
printf '%s\n' "\$*" >> "${WORK}/ssh-log.txt"
# target is the first bare ssh argument; the value of a preceding -o flag is
# itself a bare word (BatchMode=yes) and must not be taken as the target
target=""
skip_next=0
for a in "\$@"; do
  if [ "\$skip_next" = "1" ]; then skip_next=0; continue; fi
  case "\$a" in
    -o) skip_next=1 ;;
    -*) : ;;
    *) target="\$a"; break ;;
  esac
done
plan="${WORK}/ssh-plan.txt"
action="fail"
while IFS= read -r line; do
  pat="\${line%%|*}"; act="\${line#*|}"
  case "\$target" in
    *"\$pat"*) action="\$act" ;;
  esac
done < "\$plan"
case "\$action" in
  fail) exit 255 ;;
  healthy)
    printf 'ACT_HOOK=PASS\nACT_AGENT=PASS\nACT_CONTROLLER=PASS\nACT_SCHEDULER=PASS\nACT_OVERALL=PASS\nRESULT=OK\n'
    ;;
esac
exit 0
EOF
chmod +x "$MOCK_BIN/ssh"

run_audit() { # $1=local-root-for-box-healthy-map ... extra args
  env PATH="$MOCK_BIN:$PATH" bash "$SCRIPT_UNDER_TEST" "$@"
}

# --------------------------------------------------------------------------- #
# T2/T3/T10/T12: full sweep over the registry fixture. Local boxes run the
# REAL probe; which root each local slug sees is set per slug below by
# mapping slug -> root through a small dispatcher: the audit only knows one
# local root (PODCAST_OC_ROOT_LOCAL), so each local case gets its own run.
# --------------------------------------------------------------------------- #

# --- sweep A: healthy + broken + badguard local boxes -----------------------
REG_A="$WORK/reg-a.json"
cat > "$REG_A" <<'EOF'
{"boxes": {
  "box-healthy": {"kind": "local"},
  "box-broken": {"kind": "local"},
  "box-guarded": {"kind": "local"},
  "box-badguard": {"kind": "local"}
}}
EOF
# The audit runs every local slug against ONE root, so run the sweep three
# times, once per slug, to exercise each local fixture.
sweep_local() { # $1=slug $2=root -> prints the report line for the slug
  local out
  out="$(PODCAST_OC_ROOT_LOCAL="$2" run_audit --registry "$REG_A" --box "$1" 2>&1 || true)"
  printf '%s\n' "$out"
}

OUT_HEALTHY="$(sweep_local box-healthy "$ROOT_HEALTHY")"
printf '%s' "$OUT_HEALTHY" | grep -q '^box-healthy .*PASS *PASS *PASS *PASS *PASS$' \
  && ok "T2a healthy box all four pieces PASS" || bad "T2a healthy box row: $(printf '%s' "$OUT_HEALTHY" | grep '^box-healthy')"
printf '%s' "$OUT_HEALTHY" | grep -Eq 'healthy \(overall PASS\) +: 1' \
  && ok "T2b healthy count is 1" || bad "T2b healthy count"

OUT_BROKEN="$(sweep_local box-broken "$ROOT_BROKEN")"
printf '%s' "$OUT_BROKEN" | grep -q '^box-broken .*FAIL *PASS *FAIL *FAIL *FAIL$' \
  && ok "T3a broken box grades FAIL with agent PASS only" || bad "T3a broken box row: $(printf '%s' "$OUT_BROKEN" | grep '^box-broken')"
printf '%s' "$OUT_BROKEN" | grep -Eq 'missing processor \(FAIL\) +: 1' \
  && ok "T3b missing-processor summary count is 1" || bad "T3b missing count"
printf '%s' "$OUT_BROKEN" | grep -q 'boxes missing the processor  : box-broken' \
  && ok "T3c missing list names the box" || bad "T3c missing list"

# Guard takes priority over the built-in probe when it emits ACT_* markers,
# even when its exit code is nonzero. The guarded fixture's own config would
# grade hook FAIL via the built-in probe (empty hooks), so a hook PASS here
# proves the guard's markers were used and its exit code was ignored.
OUT_GUARDED="$(PODCAST_OC_ROOT_LOCAL="$ROOT_GUARDED" run_audit --registry "$REG_A" --box box-guarded 2>&1 || true)"
printf '%s' "$OUT_GUARDED" | grep -q '^box-guarded .*PASS *PASS *PASS *FAIL *FAIL$' \
  && ok "T10a guard markers grade the box (guard preferred, exit code ignored)" || bad "T10a guarded row: $(printf '%s' "$OUT_GUARDED" | grep '^box-guarded')"
printf '%s' "$OUT_GUARDED" | grep -q 'marker source: guard' \
  && ok "T10b guard NOTE line surfaced for non-PASS box" || bad "T10b guard NOTE line"

# Guard with no markers falls back to the built-in probe (root has controller
# missing, so controller FAILs; hook/agent/scheduler PASS from the fixture).
OUT_BADGUARD="$(sweep_local box-badguard "$ROOT_BADGUARD")"
printf '%s' "$OUT_BADGUARD" | grep -q '^box-badguard .*PASS *PASS *FAIL *PASS *FAIL$' \
  && ok "T12 markerless guard falls back to built-in probe" || bad "T12 badguard row: $(printf '%s' "$OUT_BADGUARD" | grep '^box-badguard')"

# --- sweep B: remote transports + unreachable + skipped ----------------------
: > "$WORK/ssh-log.txt"
cat > "$WORK/ssh-plan.txt" <<'EOF'
root@203.0.113.7|healthy
rescue-box-mac|healthy
rescue-box-dark|fail
EOF
REG_B="$WORK/reg-b.json"
cat > "$REG_B" <<'EOF'
{"boxes": {
  "box-vps": {"kind": "vps", "ssh_target": "root@203.0.113.7", "container": "openclaw-boxvps-openclaw-1"},
  "box-mac": {"kind": "mac", "ssh_alias": "rescue-box-mac"},
  "box-dark": {"kind": "mac", "ssh_alias": "rescue-box-dark"},
  "box-notransport": {"kind": "vps"}
}}
EOF
OUT_REMOTE="$(run_audit --registry "$REG_B" 2>&1 || true)"
printf '%s' "$OUT_REMOTE" | grep -q '^box-vps .*PASS *PASS *PASS *PASS *PASS$' \
  && ok "T5a vps box graded from ssh markers" || bad "T5a vps row: $(printf '%s' "$OUT_REMOTE" | grep '^box-vps')"
printf '%s' "$OUT_REMOTE" | grep -q '^box-mac .*PASS *PASS *PASS *PASS *PASS$' \
  && ok "T6a mac box graded from ssh markers" || bad "T6a mac row: $(printf '%s' "$OUT_REMOTE" | grep '^box-mac')"
printf '%s' "$OUT_REMOTE" | grep -q '^box-dark .*UNREACHABLE$' \
  && ok "T7a dark box grades UNREACHABLE" || bad "T7a dark row: $(printf '%s' "$OUT_REMOTE" | grep '^box-dark')"
printf '%s' "$OUT_REMOTE" | grep -q '^box-notransport .*SKIPPED$' \
  && ok "T8a transport-less box grades SKIPPED" || bad "T8a notransport row: $(printf '%s' "$OUT_REMOTE" | grep '^box-notransport')"
printf '%s' "$OUT_REMOTE" | grep -Eq 'unreachable +: 1' \
  && ok "T7b unreachable count is 1" || bad "T7b unreachable count"

grep -q -- '-o BatchMode=yes' "$WORK/ssh-log.txt" \
  && ok "T5b ssh uses BatchMode" || bad "T5b BatchMode"
grep -q -- 'docker exec -i -u node openclaw-boxvps-openclaw-1 bash -s' "$WORK/ssh-log.txt" \
  && ok "T5c vps transport runs docker exec as node via bash -s" || bad "T5c docker exec shape"
grep -q "zsh -lc 'bash -s'" "$WORK/ssh-log.txt" \
  && ok "T6b mac transport wraps payload in zsh -lc bash -s" || bad "T6b zsh wrap"
grep -q 'rescue-box-mac' "$WORK/ssh-log.txt" \
  && ok "T6c mac ssh targets the registry ssh_alias" || bad "T6c ssh alias"

# --- T4: --box filter and unknown slug -------------------------------------- #
OUT_ONLY="$(run_audit --registry "$REG_B" --box box-vps 2>&1 || true)"
n_rows="$(printf '%s' "$OUT_ONLY" | grep -cE '^box-' || true)"
[ "$n_rows" = "1" ] && ok "T4a --box selects exactly one box" || bad "T4a got $n_rows rows"
rc=0
run_audit --registry "$REG_B" --box no-such-box >/dev/null 2>&1 || rc=$?
[ "$rc" = "3" ] && ok "T4b unknown --box exits 3" || bad "T4b rc=$rc want 3"

# --- T9: targets-format roster; identity fields never printed ---------------- #
TARGETS="$WORK/targets.txt"
cat > "$TARGETS" <<EOF
# comment line
box-vps|vps|203.0.113.7|openclaw-boxvps-openclaw-1|/docker/openclaw-boxvps|Firsty|Lasty|${IDENTITY_CANARY}
box-mac|mac|rescue-box-mac|-|-|Firsty|Lasty|${IDENTITY_CANARY}
EOF
OUT_TGTS="$(run_audit --boxes "$TARGETS" 2>&1 || true)"
printf '%s' "$OUT_TGTS" | grep -q '^box-vps .*PASS' \
  && ok "T9a targets file drives the sweep" || bad "T9a targets sweep"
if printf '%s' "$OUT_TGTS" | grep -q "${IDENTITY_CANARY}"; then
  bad "T9b identity fields leaked into output"
else
  ok "T9b identity fields never printed"
fi

# --- T11: secret hygiene ------------------------------------------------------ #
if printf '%s' "$OUT_HEALTHY" | grep -q "${SECRET_CANARY}"; then
  bad "T11 hooks token value leaked"
else
  ok "T11 hooks token value never printed"
fi

# --- exit codes ---------------------------------------------------------------- #
REG_OK="$WORK/reg-ok.json"
printf '{"boxes": {"box-healthy": {"kind": "local"}}}\n' > "$REG_OK"
rc=0
PODCAST_OC_ROOT_LOCAL="$ROOT_HEALTHY" run_audit --registry "$REG_OK" >/dev/null 2>&1 || rc=$?
[ "$rc" = "0" ] && ok "exit 0 when every box PASS" || bad "all-PASS rc=$rc want 0"
rc=0
PODCAST_OC_ROOT_LOCAL="$ROOT_BROKEN" run_audit --registry "$REG_OK" >/dev/null 2>&1 || rc=$?
[ "$rc" = "1" ] && ok "exit 1 when a box FAILs" || bad "FAIL rc=$rc want 1"

# --------------------------------------------------------------------------- #
printf '\n%d passed, %d failed\n' "$PASS_COUNT" "$FAIL_COUNT"
[ "$FAIL_COUNT" = "0" ]
