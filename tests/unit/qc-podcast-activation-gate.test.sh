#!/usr/bin/env bash
# tests/unit/qc-podcast-activation-gate.test.sh
#
# act-6 -- the QC gate that makes a missing or broken podcast ACTIVATION LAYER
# fail LOUDLY (this is the class of gap behind Leanne's ticket: intake and
# publish worked, but the production processor never activated and queued
# flows sat forever). The gate is
# 58-podcast-production-engine/scripts/guard-activation-health.py, wired into
# 58-podcast-production-engine/qc-podcast.sh.
#
# Contract (act-8 gate alignment): the activation layer is NO-DAEMON. The
# three build files are register-podcast-hook.sh, webhook/intake_handler.py
# (the deterministic first step of the route's controllerId runbook), and
# install-podcast-department.sh. There is NO podcast_controller.py and NO
# podcast_scheduler.py anywhere in the contract. B4 verifies the route
# BINDING SHAPE (controllerId + sessionKey podcast:intake:<slug>), B5
# verifies the intake env secrets presence and the no-poller doctrine.
## This suite proves, hermetically (temp trees, no network, no box state read
# or written):
#
#   1. guard --self-test passes
#   2. --repo-only exits 0 when the three activation files are present and
#      exits 2 when any one is missing (the CI/merge gate surface); the
#      no-longer-required controller file is never in the missing list#   3. on-box findings are non-fatal WARNs on an unprovisioned box (exit 0)
#      but FATAL when the box is provisioned ($PODCAST_ACTIVATION_PROVISIONED=1
#      or a client slug configured) or --strict is passed
#   4. qc-podcast.sh integration: the gate FAILs the whole install QC (exit 1)
#      when the activation files are absent from the build, and PASSES (exit 0)
#      once the files are present (post-merge simulation)
#   5. route binding shape: B4 finds podcast-intake-<slug> with sessionKey and
#      controllerId in the box config map and reports a FAIL for a configured
#      slug with no route or a wrong binding; B5 reports the intake secrets
#      SET/NOT-SET and flags a poller cron#   6. conventions: bash -n / py_compile clean, zero em dashes in both files
#
# Exit 0 = all checks pass. Exit 1 = one or more failed.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GUARD="$REPO_ROOT/58-podcast-production-engine/scripts/guard-activation-health.py"
GATE="$REPO_ROOT/58-podcast-production-engine/qc-podcast.sh"

PASS=0
FAIL=0
pass() { printf '  PASS: %s\n' "$1"; PASS=$((PASS + 1)); }
fail() { printf '  FAIL: %s\n' "$1"; FAIL=$((FAIL + 1)); }

echo "=== qc-podcast-activation-gate.test.sh ==="

[ -f "$GUARD" ] || { echo "FAIL: guard not found at $GUARD"; exit 1; }
[ -f "$GATE" ] || { echo "FAIL: gate not found at $GATE"; exit 1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# --- helpers -------------------------------------------------------------
# Build a fake repo tree: $1 = root dir, $2 = with-activation (yes|no).
make_tree() {
  local root="$1" with_act="$2"
  mkdir -p "$root/58-podcast-production-engine/scripts/webhook"
  if [ "$with_act" = "yes" ]; then
    printf '#!/usr/bin/env bash\nexit 0\n' \
      > "$root/58-podcast-production-engine/scripts/register-podcast-hook.sh"
    printf '#!/usr/bin/env python3\n# deterministic first step of the controllerId runbook\n' \
      > "$root/58-podcast-production-engine/scripts/webhook/intake_handler.py"    printf '#!/usr/bin/env bash\nexit 0\n' \
      > "$root/58-podcast-production-engine/scripts/install-podcast-department.sh"
  fi
}

# Run the guard with ALL box-state seams pinned to the sandbox (hermetic).
# The two intake secrets are unset at script top so B5 is deterministic
# regardless of the host environment (tests that need them set export them
# explicitly on the run_guard call).run_guard() {  # $@ = extra guard args
  PODCAST_CRONTAB_BIN="$WORK/bin/false-crontab" \
  PODCAST_LAUNCHD_DIR="$WORK/launchd" \
  OPENCLAW_CONFIG="$WORK/openclaw.json" \
  HOME="$WORK/home" \
  python3 "$GUARD" "$@"
}
unset PODCAST_INTAKE_HOOK_SECRET PODCAST_INTAKE_INBOUND_SECRET 2>/dev/null || true
mkdir -p "$WORK/bin" "$WORK/home"
printf '#!/usr/bin/env bash\nexit 1\n' > "$WORK/bin/false-crontab"
chmod +x "$WORK/bin/false-crontab"
# A clean no-poller crontab stub (exit 0, empty listing): the only recurring
# podcast cron in the design is the daily smoke test, and it rides openclaw
# cron, never the box crontab.
printf '#!/usr/bin/env bash\nexit 0\n' > "$WORK/bin/clean-crontab"
chmod +x "$WORK/bin/clean-crontab"
# --- 0. syntax + conventions ----------------------------------------------
echo "--- conventions ---"
if bash -n "$GATE" 2>/dev/null; then pass "qc-podcast.sh bash -n clean"; else fail "qc-podcast.sh bash -n"; fi
if python3 -m py_compile "$GUARD" 2>/dev/null; then pass "guard py_compile clean"; else fail "guard py_compile"; fi
EMDASH_GUARD=$(grep -c $'\xe2\x80\x94' "$GUARD" 2>/dev/null || true)
EMDASH_GATE_SECTION=$(sed -n '/act-6: activation-layer health gate/,/^echo ""$/p' "$GATE" | grep -c $'\xe2\x80\x94' || true)
if [ "${EMDASH_GUARD:-1}" -eq 0 ]; then pass "guard has zero em dashes"; else fail "guard contains em dashes"; fi
if [ "${EMDASH_GATE_SECTION:-1}" -eq 0 ]; then pass "qc-podcast.sh act-6 section has zero em dashes"; else fail "qc-podcast.sh act-6 section contains em dashes"; fi

# --- 1. self-test -----------------------------------------------------------
echo "--- guard self-test ---"
if HOME="$WORK/home" python3 "$GUARD" --self-test > "$WORK/selftest.log" 2>&1; then
  pass "guard --self-test exits 0"
else
  fail "guard --self-test"; sed 's/^/    /' "$WORK/selftest.log"
fi

# --- 2. repo-only surface ----------------------------------------------------
echo "--- repo-only surface ---"
make_tree "$WORK/tree-full" "yes"
make_tree "$WORK/tree-bare" "no"
RO_FULL_RC=0
run_guard --repo-only --repo-root "$WORK/tree-full" > "$WORK/ro-full.log" 2>&1 || RO_FULL_RC=$?
RO_BARE_RC=0
run_guard --repo-only --repo-root "$WORK/tree-bare" > "$WORK/ro-bare.log" 2>&1 || RO_BARE_RC=$?
[ "$RO_FULL_RC" -eq 0 ] && pass "--repo-only exits 0 when activation files present" \
  || { fail "--repo-only with files present (rc=$RO_FULL_RC)"; sed 's/^/    /' "$WORK/ro-full.log"; }
[ "$RO_BARE_RC" -eq 2 ] && pass "--repo-only exits 2 when activation files missing" \
  || { fail "--repo-only with files missing (rc=$RO_BARE_RC)"; sed 's/^/    /' "$WORK/ro-bare.log"; }
grep -q "register-podcast-hook.sh" "$WORK/ro-bare.log" \
  && pass "missing-file finding names register-podcast-hook.sh" \
  || fail "missing-file finding does not name the script"
grep -q "intake_handler.py" "$WORK/ro-bare.log" \
  && pass "missing-file finding names webhook/intake_handler.py" \
  || fail "missing-file finding does not name the intake handler"
if grep -q "podcast_controller.py" "$WORK/ro-bare.log"; then
  fail "the excluded controller daemon is back in the missing list"
else
  pass "the excluded controller daemon is not in the missing list (no-daemon contract)"
fi
# --- 3. severity model on a fake box ------------------------------------------
echo "--- severity model (fake box) ---"
mkdir -p "$WORK/tree-full/agents/dept-podcast"
printf 'podcast department agent\n' > "$WORK/tree-full/agents/dept-podcast/agent.md"
# An unreachable gateway URL (port 1): deterministic connection refusal.
BOX_ARGS=(--repo-root "$WORK/tree-full" --agents-root "$WORK/tree-full/agents"
          --gateway-url "http://127.0.0.1:1" --timeout 2)

# 3a. unprovisioned: on-box failures degrade to WARN (exit 0)
unset PODCAST_ACTIVATION_PROVISIONED PODCAST_CLIENT_SLUGS 2>/dev/null || true
SEV_WARN_RC=0
run_guard "${BOX_ARGS[@]}" > "$WORK/sev-warn.log" 2>&1 || SEV_WARN_RC=$?
[ "$SEV_WARN_RC" -eq 0 ] && pass "unprovisioned box: on-box findings are WARN, exit 0" \
  || { fail "unprovisioned severity (rc=$SEV_WARN_RC)"; sed 's/^/    /' "$WORK/sev-warn.log"; }
grep -q "non-fatal WARN" "$WORK/sev-warn.log" \
  && pass "unprovisioned box: findings labeled non-fatal WARN" \
  || fail "unprovisioned box: no WARN label found"

# 3b. provisioned via env: same box state is now FATAL (exit 2)
SEV_PROV_RC=0
PODCAST_ACTIVATION_PROVISIONED=1 run_guard "${BOX_ARGS[@]}" > "$WORK/sev-prov.log" 2>&1 || SEV_PROV_RC=$?
[ "$SEV_PROV_RC" -eq 2 ] && pass "provisioned box: on-box findings are FATAL, exit 2" \
  || { fail "provisioned severity (rc=$SEV_PROV_RC)"; sed 's/^/    /' "$WORK/sev-prov.log"; }

# 3c. strict flag: same promotion
SEV_STRICT_RC=0
run_guard --strict "${BOX_ARGS[@]}" > "$WORK/sev-strict.log" 2>&1 || SEV_STRICT_RC=$?
[ "$SEV_STRICT_RC" -eq 2 ] && pass "--strict: on-box findings are FATAL, exit 2" \
  || { fail "--strict severity (rc=$SEV_STRICT_RC)"; sed 's/^/    /' "$WORK/sev-strict.log"; }

# --- 4. route binding shape check (B4) ----------------------------------------
echo "--- route binding shape (B4) ---"
cat > "$WORK/openclaw.json" <<'JSON'
{
  "plugins": { "entries": { "webhooks": { "config": { "routes": {
    "podcast-intake-acme-media": {
      "enabled": true,
      "sessionKey": "podcast:intake:acme-media",
      "controllerId": "webhooks/podcast-intake-acme-media"
    },
    "podcast-intake-zeta-corp": {
      "enabled": true,
      "sessionKey": "podcast:intake:WRONG-SESSION",
      "controllerId": "webhooks/podcast-intake-zeta-corp"
    },    "some-other-route": { "enabled": true }
  } } } } }
}
JSON
ROUTE_HIT_RC=0
run_guard "${BOX_ARGS[@]}" --client-slug acme-media > "$WORK/route-hit.log" 2>&1 || ROUTE_HIT_RC=$?
grep -q "\[PASS\] B4" "$WORK/route-hit.log" \
  && pass "B4 PASS when the route carries the right binding shape" \
  || { fail "B4 with correctly bound route (rc=$ROUTE_HIT_RC)"; sed 's/^/    /' "$WORK/route-hit.log"; }
# A configured slug with no route: FAIL (and fatal, because a slug = provisioned)
ROUTE_MISS_RC=0
run_guard "${BOX_ARGS[@]}" --client-slug ghost-slug > "$WORK/route-miss.log" 2>&1 || ROUTE_MISS_RC=$?
[ "$ROUTE_MISS_RC" -eq 2 ] && pass "B4 FAIL (fatal) when a configured slug has no route" \
  || { fail "B4 missing route severity (rc=$ROUTE_MISS_RC)"; sed 's/^/    /' "$WORK/route-miss.log"; }
grep -q "ghost-slug" "$WORK/route-miss.log" \
  && pass "B4 finding names the unregistered slug" \
  || fail "B4 finding does not name the slug"
# A registered route with the WRONG sessionKey: FAIL naming the route
BADSHAPE_RC=0
run_guard "${BOX_ARGS[@]}" --client-slug zeta-corp > "$WORK/route-badshape.log" 2>&1 || BADSHAPE_RC=$?
[ "$BADSHAPE_RC" -eq 2 ] && pass "B4 FAIL when the binding shape is wrong (sessionKey)" \
  || { fail "B4 wrong-shape severity (rc=$BADSHAPE_RC)"; sed 's/^/    /' "$WORK/route-badshape.log"; }
grep -q "podcast-intake-zeta-corp sessionKey" "$WORK/route-badshape.log" \
  && pass "B4 wrong-shape finding names the route and the sessionKey" \
  || fail "B4 wrong-shape finding does not name the sessionKey mismatch"

# --- 4b. intake env secrets and no-poller (B5) --------------------------------
echo "--- intake secrets + no poller (B5) ---"
# Secrets UNSET (the run_guard default): B5 reports NOT-SET and FAILs
run_guard "${BOX_ARGS[@]}" > "$WORK/b5-nosecret.log" 2>&1 || true
grep -q "PODCAST_INTAKE_HOOK_SECRET NOT-SET" "$WORK/b5-nosecret.log" \
  && pass "B5 reports PODCAST_INTAKE_HOOK_SECRET NOT-SET when unset" \
  || { fail "B5 NOT-SET report missing"; sed 's/^/    /' "$WORK/b5-nosecret.log"; }
grep -q "\[FAIL\] B5" "$WORK/b5-nosecret.log" \
  && pass "B5 FAILs while an intake secret is NOT-SET" \
  || fail "B5 did not fail on a missing intake secret"
# Both secrets SET + clean crontab: B5 PASSes. Direct guard call (not
# run_guard) so the clean-crontab seam is the one the guard sees.
SEV_SECRETS_RC=0
PODCAST_CRONTAB_BIN="$WORK/bin/clean-crontab" \
PODCAST_LAUNCHD_DIR="$WORK/launchd" \
OPENCLAW_CONFIG="$WORK/openclaw.json" \
HOME="$WORK/home" \
PODCAST_INTAKE_HOOK_SECRET="sandbox-not-a-real-secret" \
PODCAST_INTAKE_INBOUND_SECRET="sandbox-not-a-real-secret" \
python3 "$GUARD" "${BOX_ARGS[@]}" > "$WORK/b5-secrets.log" 2>&1 || SEV_SECRETS_RC=$?
grep -q "\[PASS\] B5" "$WORK/b5-secrets.log" \
  && pass "B5 PASSes when both intake secrets are SET and no poller cron exists" \
  || { fail "B5 with secrets present (rc=$SEV_SECRETS_RC)"; sed 's/^/    /' "$WORK/b5-secrets.log"; }
grep -q "no-poller OK" "$WORK/b5-secrets.log" \
  && pass "B5 reports the no-poller doctrine holds" \
  || fail "B5 no-poller report missing"
# A crontab naming a controller/scheduler daemon: B5 FAILs as POLLER FOUND
printf '#!/usr/bin/env bash\necho "*/5 * * * * python3 /x/podcast_scheduler.py sweep"\n' \
  > "$WORK/bin/poller-crontab"
chmod +x "$WORK/bin/poller-crontab"
PODCAST_CRONTAB_BIN="$WORK/bin/poller-crontab" \
PODCAST_LAUNCHD_DIR="$WORK/launchd" \
OPENCLAW_CONFIG="$WORK/openclaw.json" \
HOME="$WORK/home" \
PODCAST_INTAKE_HOOK_SECRET="sandbox-not-a-real-secret" \
PODCAST_INTAKE_INBOUND_SECRET="sandbox-not-a-real-secret" \
python3 "$GUARD" "${BOX_ARGS[@]}" > "$WORK/b5-poller.log" 2>&1 || true
grep -q "POLLER FOUND" "$WORK/b5-poller.log" \
  && pass "B5 flags a poller cron (no-daemon doctrine)" \
  || { fail "B5 did not flag the poller cron"; sed 's/^/    /' "$WORK/b5-poller.log"; }
# --- 5. qc-podcast.sh integration ----------------------------------------------
echo "--- qc-podcast.sh integration ---"
# 5a. THIS branch (activation files absent from the build): the whole install
#     QC must FAIL with the activation gate as a fatal finding. Sandbox HOME so
#     secrets/agent-dir lookups never touch real box state.
# Podbean transport env: set (proxy mode) so the activation gate, not the
# credential asserts, decides these outcomes. Values are throwaway sandbox
# strings; the gate only checks presence.
mkdir -p "$WORK/home/.openclaw/skills/58-podcast-production-engine"
QC_BARE_RC=0
env -u PODCAST_ACTIVATION_PROVISIONED -u PODCAST_CLIENT_SLUGS \
    -u PODCAST_INTAKE_HOOK_SECRET -u PODCAST_INTAKE_INBOUND_SECRET \
  HOME="$WORK/home" QC_N8N_PROBE_MODE=warn \  PODBEAN_PODCAST_ID="sandbox-channel-id" PODBEAN_PUBLISH_TOKEN="sandbox-proxy-token" \
  bash "$GATE" > "$WORK/qc-bare.log" 2>&1 || QC_BARE_RC=$?
[ "$QC_BARE_RC" -eq 1 ] && pass "qc-podcast.sh exits 1 while activation layer absent" \
  || { fail "qc-podcast.sh exit with absent layer (rc=$QC_BARE_RC)"; sed 's/^/    /' "$WORK/qc-bare.log"; }
grep -q "activation-layer health gate (act-6)" "$WORK/qc-bare.log" \
  && pass "qc-podcast.sh runs the activation-layer health section" \
  || fail "qc-podcast.sh does not run the activation section"
grep -q "FAIL -- activation-layer health" "$WORK/qc-bare.log" \
  && pass "qc-podcast.sh reports the activation gate as FAIL" \
  || fail "qc-podcast.sh missing the activation FAIL line"

# 5b. Post-merge simulation: copy the real skill tree, drop in the three
#     activation files, and run the COPIED gate. Repo findings pass; on-box
#     findings stay non-fatal (unprovisioned), so the whole QC exits 0.
mkdir -p "$WORK/merged"
cp -R "$REPO_ROOT/58-podcast-production-engine" "$WORK/merged/58-podcast-production-engine"
make_tree "$WORK/merged" "yes"
QC_MERGED_RC=0
env -u PODCAST_ACTIVATION_PROVISIONED -u PODCAST_CLIENT_SLUGS \
    -u PODCAST_INTAKE_HOOK_SECRET -u PODCAST_INTAKE_INBOUND_SECRET \
  HOME="$WORK/home" QC_N8N_PROBE_MODE=warn \  PODBEAN_PODCAST_ID="sandbox-channel-id" PODBEAN_PUBLISH_TOKEN="sandbox-proxy-token" \
  bash "$WORK/merged/58-podcast-production-engine/qc-podcast.sh" \
  > "$WORK/qc-merged.log" 2>&1 || QC_MERGED_RC=$?
[ "$QC_MERGED_RC" -eq 0 ] && pass "qc-podcast.sh exits 0 once activation files are present (post-merge simulation)" \
  || { fail "qc-podcast.sh post-merge simulation (rc=$QC_MERGED_RC)"; tail -30 "$WORK/qc-merged.log" | sed 's/^/    /'; }
grep -q "PASS -- activation-layer health" "$WORK/qc-merged.log" \
  && pass "qc-podcast.sh reports the activation gate as PASS post-merge" \
  || fail "qc-podcast.sh missing the activation PASS line post-merge"

echo ""
echo "=== result: $PASS passed | $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then exit 1; fi
exit 0
