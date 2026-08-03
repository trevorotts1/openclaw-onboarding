#!/usr/bin/env bash
# =============================================================================
# Tests for audit-podcast-activation.sh (fleet podcast activation audit).
#
# Hermetic by construction: no real ssh, no network, no fleet access. The ssh
# binary is a PATH shim whose behavior is scripted per test; remote boxes are
# simulated by the shim emitting the guard's output grammar, and local boxes
# run fixture guards (or the built-in probe) against a sandboxed OC root
# (PODCAST_OC_ROOT_LOCAL).
#
# The fixtures emit the REAL guard-activation-health.py grammar:
#     "  [<STATUS>] <id> <title> : <detail>"   check lines (R1..R3, B1..B5)
#     "RESULT: PASS - ..." | "RESULT: FAIL (fail-closed) - <n> fatal finding(s):"
#     "  [AF-PPE-ACTIVATION-REPO|AF-PPE-ACTIVATION-BOX] <id> : <detail>"
#
# Assertions:
#   T1  bash -n passes
#   T2  healthy local box (all-PASS grammar) grades PASS in every column,
#       exit 0
#   T3  box with fatal on-box findings grades FAIL, is counted as unhealthy
#       in the summary, its AF finding line surfaces, exit 1
#   T4  --box filters to one box; unknown slug exits 3
#   T5  vps transport: ssh shim sees BatchMode + docker exec -i -u node
#       <container> bash -s; grammar from the shim grades the box
#   T6  mac transport: ssh shim sees the ssh alias and zsh -lc wrapper
#   T7  unreachable box grades UNREACHABLE and never aborts the sweep
#   T8  registry row without transport info grades SKIPPED
#   T9  targets-format roster (--boxes) is read; client identity fields are
#       never printed (canary strings absent from the output)
#   T10 guard mode selection from the box's own env: provisioned boxes
#       (PODCAST_ACTIVATION_PROVISIONED=1 or PODCAST_CLIENT_SLUGS set) run
#       --strict, others run --repo-only; the guard's exit code is ignored
#   T11 no secret value (fixture token canary) ever appears in the output
#   T12 box without the guard falls back to the built-in repo-only probe
#       emitting the same grammar; on-box columns show "-"
#   T13 a guard that emits no parseable check lines falls back to the
#       built-in probe
#   T14 B4 SKIP (no client slugs) grades hook PASS with a note
# =============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_UNDER_TEST="$HERE/../audit-podcast-activation.sh"

PASS_COUNT=0
FAIL_COUNT=0
ok()   { PASS_COUNT=$((PASS_COUNT + 1)); printf 'PASS %s\n' "$1"; }
bad()  { FAIL_COUNT=$((FAIL_COUNT + 1)); printf 'FAIL %s\n' "$1"; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
MOCK_BIN="$WORK/bin"
mkdir -p "$MOCK_BIN"

# --- T1: syntax -------------------------------------------------------------
if bash -n "$SCRIPT_UNDER_TEST"; then ok "T1 bash -n"; else bad "T1 bash -n"; fi

# --------------------------------------------------------------------------- #
# Fixtures. Every fixture guard emits the real guard grammar.
# --------------------------------------------------------------------------- #
SECRET_CANARY="SEKR1T-TOKEN-CANARY-9f8e7d"
IDENTITY_CANARY="canary-identity-9f8e7d@example.com"

make_guard_dir() { # $1=root
  mkdir -p "$1/skills/58-podcast-production-engine/scripts"
}

# Healthy box: full grammar, all checks PASS.
ROOT_HEALTHY="$WORK/oc-healthy"
make_guard_dir "$ROOT_HEALTHY"
cat > "$ROOT_HEALTHY/skills/58-podcast-production-engine/scripts/guard-activation-health.py" <<'EOF'
#!/usr/bin/env python3
print("== Podcast Production Engine :: guard-activation-health ==")
print("  mode: repo + on-box (severity: provisioned) | repo root: /data")
print("  [PASS] R1 intake hook registration script : present: /data/scripts/register-podcast-hook.sh")
print("  [PASS] R2 production processor (controller) : present: /data/scripts/podcast_controller.py")
print("  [PASS] R3 department + scheduler installer : present: /data/scripts/install-podcast-department.sh")
print("  [PASS] B1 activation scripts installed on this box : all three present under /data")
print("  [PASS] B2 podcast department agent registered : non-empty agent dir: /data/agents/dept-podcast")
print("  [PASS] B3 TaskFlow gateway reachable : http://127.0.0.1:18789 answered within 5.0s")
print("  [PASS] B4 intake webhook routes registered : route podcast-intake-<slug> registered for every configured slug: acme-media (config /data/openclaw.json)")
print("  [PASS] B5 controller runnable and scheduled : controller --help exits 0; scheduled: crontab entry references podcast_controller.py")
print("RESULT: PASS - the activation layer is present and healthy where checkable.")
EOF
cat > "$ROOT_HEALTHY/openclaw.json" <<EOF
{"hooks": {"enabled": true, "token": "${SECRET_CANARY}", "mappings": []}}
EOF

# Broken box: repo present, but the on-box layer is dead (the Leanne case).
ROOT_BROKEN="$WORK/oc-broken"
make_guard_dir "$ROOT_BROKEN"
cat > "$ROOT_BROKEN/skills/58-podcast-production-engine/scripts/guard-activation-health.py" <<'EOF'
#!/usr/bin/env python3
print("== Podcast Production Engine :: guard-activation-health ==")
print("  mode: repo + on-box (severity: strict) | repo root: /data")
print("  [PASS] R1 intake hook registration script : present: /data/scripts/register-podcast-hook.sh")
print("  [PASS] R2 production processor (controller) : present: /data/scripts/podcast_controller.py")
print("  [PASS] R3 department + scheduler installer : present: /data/scripts/install-podcast-department.sh")
print("  [PASS] B1 activation scripts installed on this box : all three present under /data")
print("  [PASS] B2 podcast department agent registered : non-empty agent dir: /data/agents/dept-podcast")
print("  [FAIL] B3 TaskFlow gateway reachable : http://127.0.0.1:18789 not reachable within 5.0s (url error: connection refused)")
print("  [FAIL] B4 intake webhook routes registered : no route podcast-intake-<slug> for: acme-media (config /data/openclaw.json; registered podcast routes: none)")
print("  [FAIL] B5 controller runnable and scheduled : not scheduled: no crontab entry or launchd plist names podcast_controller.py or install-podcast-department.sh (the heartbeat that wakes the processor is missing)")
print("RESULT: FAIL (fail-closed) - 3 fatal finding(s):")
print("  [AF-PPE-ACTIVATION-BOX] B5 : not scheduled: no crontab entry or launchd plist names podcast_controller.py")
sys.exit(2)  # exit code must be IGNORED; the grammar grades the box
EOF

# Repo-only box: guard ran --repo-only (R lines only), all present.
ROOT_REPOONLY="$WORK/oc-repoonly"
make_guard_dir "$ROOT_REPOONLY"
cat > "$ROOT_REPOONLY/skills/58-podcast-production-engine/scripts/guard-activation-health.py" <<'EOF'
#!/usr/bin/env python3
print("== Podcast Production Engine :: guard-activation-health ==")
print("  mode: repo-only | repo root: /data")
print("  [PASS] R1 intake hook registration script : present: /data/scripts/register-podcast-hook.sh")
print("  [PASS] R2 production processor (controller) : present: /data/scripts/podcast_controller.py")
print("  [PASS] R3 department + scheduler installer : present: /data/scripts/install-podcast-department.sh")
print("RESULT: PASS - the activation layer is present.")
EOF

# Box with no slug configured: B4 SKIP must grade hook PASS with a note.
ROOT_SKIPHUB="$WORK/oc-skiphook"
make_guard_dir "$ROOT_SKIPHUB"
cat > "$ROOT_SKIPHUB/skills/58-podcast-production-engine/scripts/guard-activation-health.py" <<'EOF'
#!/usr/bin/env python3
print("== Podcast Production Engine :: guard-activation-health ==")
print("  mode: repo + on-box (severity: strict) | repo root: /data")
print("  [PASS] R1 intake hook registration script : present: /data/scripts/register-podcast-hook.sh")
print("  [PASS] R2 production processor (controller) : present: /data/scripts/podcast_controller.py")
print("  [PASS] R3 department + scheduler installer : present: /data/scripts/install-podcast-department.sh")
print("  [PASS] B1 activation scripts installed on this box : all three present under /data")
print("  [PASS] B2 podcast department agent registered : non-empty agent dir: /data/agents/dept-podcast")
print("  [PASS] B3 TaskFlow gateway reachable : http://127.0.0.1:18789 answered within 5.0s")
print("  [SKIP] B4 intake webhook routes registered : no client slugs configured (--client-slug or $PODCAST_CLIENT_SLUGS); nothing to assert")
print("  [PASS] B5 controller runnable and scheduled : controller --help exits 0; scheduled: crontab entry references podcast_controller.py")
print("RESULT: PASS - the activation layer is present and healthy where checkable.")
print("  [SKIP] B4 : no client slugs configured (--client-slug or $PODCAST_CLIENT_SLUGS); nothing to assert")
EOF

# Box whose guard records its argv so mode selection can be asserted.
ROOT_ARGPROBE="$WORK/oc-argprobe"
make_guard_dir "$ROOT_ARGPROBE"
cat > "$ROOT_ARGPROBE/skills/58-podcast-production-engine/scripts/guard-activation-health.py" <<'EOF'
#!/usr/bin/env python3
import sys
print("NOTE: guard args: " + " ".join(sys.argv[1:]))
print("  [PASS] R1 intake hook registration script : present")
print("  [PASS] R2 production processor (controller) : present")
print("  [PASS] R3 department + scheduler installer : present")
print("  [PASS] B1 activation scripts installed on this box : all three present")
print("  [PASS] B2 podcast department agent registered : non-empty agent dir")
print("  [PASS] B3 TaskFlow gateway reachable : answered")
print("  [PASS] B4 intake webhook routes registered : all slugs covered")
print("  [PASS] B5 controller runnable and scheduled : runnable; scheduled")
print("RESULT: PASS - the activation layer is present and healthy where checkable.")
EOF

# Box without the guard: the built-in repo-only probe must run. All three
# activation files are present, so R1-R3 PASS and overall PASSes.
ROOT_NOGUARD="$WORK/oc-noguard"
make_guard_dir "$ROOT_NOGUARD"
for f in register-podcast-hook.sh podcast_controller.py install-podcast-department.sh; do
  printf '#!/usr/bin/env bash\nexit 0\n' > "$ROOT_NOGUARD/skills/58-podcast-production-engine/scripts/$f"
done

# Box whose guard emits NO parseable check lines: must fall back to the
# built-in probe (which finds all three activation files here).
ROOT_BADGUARD="$WORK/oc-badguard"
make_guard_dir "$ROOT_BADGUARD"
cat > "$ROOT_BADGUARD/skills/58-podcast-production-engine/scripts/guard-activation-health.py" <<'EOF'
#!/usr/bin/env python3
print("nothing useful here")
EOF
for f in register-podcast-hook.sh podcast_controller.py install-podcast-department.sh; do
  printf '#!/usr/bin/env bash\nexit 0\n' > "$ROOT_BADGUARD/skills/58-podcast-production-engine/scripts/$f"
done

# Registry for the local sweep (one slug per fixture; the audit runs every
# local slug against ONE root, so each case gets its own --box run).
REG_A="$WORK/reg-a.json"
cat > "$REG_A" <<'EOF'
{"boxes": {
  "box-healthy":   {"kind": "local"},
  "box-broken":    {"kind": "local"},
  "box-repoonly":  {"kind": "local"},
  "box-skiphook":  {"kind": "local"},
  "box-argprobe":  {"kind": "local"},
  "box-noguard":   {"kind": "local"},
  "box-badguard":  {"kind": "local"}
}}
EOF

# ssh shim. Behavior driven by $WORK/ssh-plan.txt (target|action). Records
# every invocation to $WORK/ssh-log.txt. The "healthy" action emits the real
# guard grammar (all PASS), exactly as the guard's text mode does.
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
    printf '== Podcast Production Engine :: guard-activation-health ==\n'
    printf '  mode: repo + on-box (severity: provisioned) | repo root: /data\n'
    printf '  [PASS] R1 intake hook registration script : present\n'
    printf '  [PASS] R2 production processor (controller) : present\n'
    printf '  [PASS] R3 department + scheduler installer : present\n'
    printf '  [PASS] B1 activation scripts installed on this box : all three present\n'
    printf '  [PASS] B2 podcast department agent registered : non-empty agent dir\n'
    printf '  [PASS] B3 TaskFlow gateway reachable : answered\n'
    printf '  [PASS] B4 intake webhook routes registered : all slugs covered\n'
    printf '  [PASS] B5 controller runnable and scheduled : runnable; scheduled\n'
    printf 'RESULT: PASS - the activation layer is present and healthy where checkable.\n'
    ;;
esac
exit 0
EOF
chmod +x "$MOCK_BIN/ssh"

run_audit() {
  env PATH="$MOCK_BIN:$PATH" bash "$SCRIPT_UNDER_TEST" "$@"
}

sweep_local() { # $1=slug $2=root -> prints the full report
  PODCAST_OC_ROOT_LOCAL="$2" run_audit --registry "$REG_A" --box "$1" 2>&1 || true
}

# --- T2: healthy box, all-PASS grammar -------------------------------------- #
OUT_HEALTHY="$(sweep_local box-healthy "$ROOT_HEALTHY")"
printf '%s' "$OUT_HEALTHY" | grep -q '^box-healthy .*PASS *PASS *PASS *PASS$' \
  && ok "T2a healthy box grades PASS in every column" || bad "T2a healthy row: $(printf '%s' "$OUT_HEALTHY" | grep '^box-healthy')"
printf '%s' "$OUT_HEALTHY" | grep -Eq 'healthy \(overall PASS\) +: 1' \
  && ok "T2b healthy count is 1" || bad "T2b healthy count"

# --- T3: broken box, FAIL RESULT + AF finding surfaces ----------------------- #
OUT_BROKEN="$(sweep_local box-broken "$ROOT_BROKEN")"
printf '%s' "$OUT_BROKEN" | grep -q '^box-broken .*FAIL *PASS *FAIL *FAIL$' \
  && ok "T3a broken box: hook FAIL, agent PASS, runner FAIL, overall FAIL" || bad "T3a broken row: $(printf '%s' "$OUT_BROKEN" | grep '^box-broken')"
printf '%s' "$OUT_BROKEN" | grep -Eq 'unhealthy \(overall FAIL\) +: 1' \
  && ok "T3b unhealthy summary count is 1" || bad "T3b unhealthy count"
printf '%s' "$OUT_BROKEN" | grep -q 'unhealthy boxes              : box-broken' \
  && ok "T3c unhealthy list names the box" || bad "T3c unhealthy list"
printf '%s' "$OUT_BROKEN" | grep -q 'AF-PPE-ACTIVATION-BOX' \
  && ok "T3d fatal AF finding line surfaces for non-PASS box" || bad "T3d AF finding line"

# --- T14: B4 SKIP grades hook PASS with a note ------------------------------- #
OUT_SKIPHUB="$(sweep_local box-skiphook "$ROOT_SKIPHUB")"
printf '%s' "$OUT_SKIPHUB" | grep -q '^box-skiphook .*PASS *PASS *PASS *PASS$' \
  && ok "T14a B4 SKIP grades hook PASS, overall PASS" || bad "T14a skiphook row: $(printf '%s' "$OUT_SKIPHUB" | grep '^box-skiphook')"
printf '%s' "$OUT_SKIPHUB" | grep -q 'note: hook graded PASS from B4 SKIP' \
  && ok "T14b B4 SKIP note recorded" || bad "T14b skip note"

# --- T12: box without the guard -> built-in probe, on-box columns "-" -------- #
OUT_NOGUARD="$(sweep_local box-noguard "$ROOT_NOGUARD")"
printf '%s' "$OUT_NOGUARD" | grep -q '^box-noguard .*- *- *- *PASS$' \
  && ok "T12a no-guard box: probe runs, on-box columns '-', overall PASS" || bad "T12a noguard row: $(printf '%s' "$OUT_NOGUARD" | grep '^box-noguard')"
printf '%s' "$OUT_NOGUARD" | grep -q 'built-in repo-only probe ran' \
  && ok "T12b fallback note surfaced" || bad "T12b fallback note"

# --- T13: guard with no parseable lines -> built-in probe --------------------- #
OUT_BADGUARD="$(sweep_local box-badguard "$ROOT_BADGUARD")"
printf '%s' "$OUT_BADGUARD" | grep -q '^box-badguard .*- *- *- *PASS$' \
  && ok "T13a markerless guard falls back to built-in probe" || bad "T13a badguard row: $(printf '%s' "$OUT_BADGUARD" | grep '^box-badguard')"
printf '%s' "$OUT_BADGUARD" | grep -q 'emitted no parseable check lines' \
  && ok "T13b no-parse note surfaced" || bad "T13b no-parse note"

# --- T10: guard mode selection from the box's own env ------------------------- #
OUT_ARG_STRICT="$(PODCAST_OC_ROOT_LOCAL="$ROOT_ARGPROBE" PODCAST_ACTIVATION_PROVISIONED=1 \
  run_audit --registry "$REG_A" --box box-argprobe 2>&1 || true)"
printf '%s' "$OUT_ARG_STRICT" | grep -q 'guard args: --strict' \
  && ok "T10a provisioned box (env=1) runs the guard --strict" || bad "T10a strict mode"
OUT_ARG_SLUGS="$(PODCAST_OC_ROOT_LOCAL="$ROOT_ARGPROBE" PODCAST_CLIENT_SLUGS=acme-media \
  run_audit --registry "$REG_A" --box box-argprobe 2>&1 || true)"
printf '%s' "$OUT_ARG_SLUGS" | grep -q 'guard args: --strict' \
  && ok "T10b provisioned box (slugs set) runs the guard --strict" || bad "T10b slugs strict mode"
OUT_ARG_REPO="$(sweep_local box-argprobe "$ROOT_ARGPROBE")"
printf '%s' "$OUT_ARG_REPO" | grep -q 'guard args: --repo-only' \
  && ok "T10c unprovisioned box runs the guard --repo-only" || bad "T10c repo-only mode"
printf '%s' "$OUT_ARG_REPO" | grep -q '^box-argprobe .*PASS *PASS *PASS *PASS$' \
  && ok "T10d guard grammar grades the box (exit code never trusted)" || bad "T10d argprobe row"

# --- T5/T6/T7/T8: remote transports, unreachable, skipped --------------------- #
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
printf '%s' "$OUT_REMOTE" | grep -q '^box-vps .*PASS *PASS *PASS *PASS$' \
  && ok "T5a vps box graded from ssh grammar" || bad "T5a vps row: $(printf '%s' "$OUT_REMOTE" | grep '^box-vps')"
printf '%s' "$OUT_REMOTE" | grep -q '^box-mac .*PASS *PASS *PASS *PASS$' \
  && ok "T6a mac box graded from ssh grammar" || bad "T6a mac row: $(printf '%s' "$OUT_REMOTE" | grep '^box-mac')"
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
  bad "T11 secret canary leaked"
else
  ok "T11 secret value never printed"
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
