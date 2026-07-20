#!/usr/bin/env bash
# tests/unit/podbean-publish-provision-roll.test.sh
#
# S58-U18 — sandboxed end-to-end proof of the fleet provision roll
# (scripts/fleet-roll/podbean-publish-provision-roll.sh) against a throwaway
# home root (P18_HOME + per-entry "home" override — the script's documented
# sandbox mechanism). SSH and Docker paths use local fakes only; there is no
# network and no write outside the mktemp sandbox. The real operator store is
# never read: P18_HOME redirects the token lookup into the sandbox too.
#
# Proves, against the REAL script:
#   1. manifest rows with EMPTY optional fields (home ordering quirk aside:
#      first_name, podcast_id, container, compose_dir) parse without column
#      shift — the recovered original used tab-delimited rows and IFS=tab,
#      which collapses consecutive tabs and blocked every production entry.
#   2. --apply writes BOTH stores (env + ocjson) and grades OK, changed=yes.
#   3. re-apply is an exact no-op: OK_ALREADY, changed=no, secrets/.env
#      byte-identical (hash-compared).
#   4. incomplete roster identity is BLOCKED fail-closed in --apply (exit 2).
#   5. --apply --local selecting more than one box is REFUSED up front (the
#      unguarded original would have written every identity onto THIS box).
#   6. an unparseable openclaw.json FAILS the box and is NOT rebuilt/clobbered
#      (the original fell back to d={} and would have destroyed the config).
#   7. the secret token value never appears on stdout or in the ledger.
#   8. --no-restart on a changed box grades PARTIAL, never a clean OK.
#   9. empty optional podcast_id reaches the downstream dry-run and grades OK.
#  10. manifest and runtime guards reject local transport for client identities.
#  11. invalid platforms are rejected before any SSH transport can run.
#  12. Mac restart uses launchctl and proves PID change plus ok:true health;
#      failures surface GATEWAY_DOWN in the fleet summary.
#  13. the duplicate is retired and secret-bearing data stays off child argv.
#  14. a nonzero SSH/transport exit overrides a parsed result=OK and keeps the
#      operator gate closed.
#  15. VPS host env backup is one unique timestamped copy of the original.
#  16. backup-copy failure aborts before the first store mutation.
#  17. VPS recreate proves container-ID change, health, and inherited values.
#  18. host-only VPS changes grade OK, never the no-restart OK_ALREADY verdict.
#  19. an unwritable ledger aborts before transport.
#  20. manifest build rejects duplicate names, SSH hosts, and operators.
#
# Exit 0 = all checks pass. Exit 1 = one or more failed.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ROLL="${ROLL_UNDER_TEST:-$REPO_ROOT/scripts/fleet-roll/podbean-publish-provision-roll.sh}"
MANIFEST_BUILDER="${MANIFEST_BUILDER_UNDER_TEST:-$REPO_ROOT/scripts/fleet-roll/podbean-publish-provision-manifest.py}"
OLD_ROLL="${OLD_ROLL_UNDER_TEST:-$REPO_ROOT/scripts/fleet-roll/podcast-publish-roll.sh}"

PASS=0
FAIL=0
pass() { printf '  PASS: %s\n' "$1"; PASS=$((PASS + 1)); }
fail() { printf '  FAIL: %s\n' "$1"; FAIL=$((FAIL + 1)); }

echo "=== podbean-publish-provision-roll.test.sh ==="

[ -f "$ROLL" ] || { echo "FAIL: roll script not found at $ROLL"; exit 1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

SB="$WORK/home"
mkdir -p "$SB/.openclaw/secrets"
TOKEN="sandbox-token-Zq7vK9-never-real"
printf 'PODBEAN_PUBLISH_TOKEN=%s\n' "$TOKEN" > "$SB/.openclaw/secrets/.env"
chmod 600 "$SB/.openclaw/secrets/.env"
printf '{}\n' > "$SB/.openclaw/openclaw.json"

MANIFEST="$WORK/manifest.json"
cat > "$MANIFEST" <<EOF
[
  {"name": "sandbox-op", "role": "operator", "platform": "mac",
   "ssh_target": "local", "home": "$SB",
   "identity": {"last_name": "Sandbox", "email": "sandbox@example.test",
                "first_name": "", "podcast_id": "", "complete": true}},
  {"name": "sandbox-client-incomplete", "role": "client", "platform": "mac",
   "ssh_target": "local", "home": "$SB",
   "identity": {"last_name": "", "email": "", "first_name": "",
                "podcast_id": "", "complete": false}}
]
EOF

LOG="$WORK/ledger.log"
run_roll() { P18_HOME="$SB" bash "$ROLL" --boxes-file "$MANIFEST" --log-file "$LOG" "$@" 2>&1; }

# --- 1. dry-run survey: empty optional fields must not shift columns ---------
OUT="$(run_roll)"; RC=$?
if [ "$RC" = "0" ]; then pass "dry-run exits 0"; else fail "dry-run exit=$RC"; echo "$OUT"; fi
if printf '%s\n' "$OUT" | grep -q '\[sandbox-op\] probe:PODBEAN_PUBLISH_TOKEN:env=SET'; then
  pass "probe parsed the operator row (empty first_name/podcast_id did not shift columns)"
else
  fail "operator probe line missing — manifest column shift?"; echo "$OUT"
fi
if printf '%s\n' "$OUT" | grep -q 'box=sandbox-op .*verdict=OK'; then
  pass "operator row graded OK in dry-run"
else
  fail "operator row not OK in dry-run"
fi
if printf '%s\n' "$OUT" | grep -q 'box=sandbox-client-incomplete .*verdict=BLOCKED_IDENTITY_INCOMPLETE'; then
  pass "incomplete identity BLOCKED in dry-run survey"
else
  fail "incomplete identity not blocked in dry-run"
fi

# --- 2. apply writes both stores ---------------------------------------------
OUT="$(run_roll --apply --local --box sandbox-op --no-standing-probe)"; RC=$?
if [ "$RC" = "0" ]; then pass "apply exits 0"; else fail "apply exit=$RC"; echo "$OUT"; fi
for want in 'env:PODBEAN_PUBLISH_WEBHOOK_URL=WRITTEN' 'ocjson:PODBEAN_PUBLISH_WEBHOOK_URL=WRITTEN' \
            'env:PODCAST_CLIENT_LAST_NAME=WRITTEN' 'changed=yes' 'restart=skipped_sandbox_home' 'result=OK'; do
  if printf '%s\n' "$OUT" | grep -q "$want"; then pass "apply reports $want"; else fail "apply missing $want"; echo "$OUT"; fi
done
if [ -d "$SB/.openclaw/backups" ] && ls "$SB/.openclaw/backups"/s58-u18-*/secrets.env >/dev/null 2>&1; then
  pass "timestamped backup of secrets/.env taken before write"
else
  fail "no backup dir/copy found"
fi

# --- 3. re-apply is an exact byte-identical no-op ----------------------------
H1="$(shasum -a 256 "$SB/.openclaw/secrets/.env" | cut -d' ' -f1)"
OUT="$(run_roll --apply --local --box sandbox-op --no-standing-probe)"; RC=$?
H2="$(shasum -a 256 "$SB/.openclaw/secrets/.env" | cut -d' ' -f1)"
if [ "$RC" = "0" ] && printf '%s\n' "$OUT" | grep -q 'verdict=OK_ALREADY'; then
  pass "re-apply grades OK_ALREADY"
else
  fail "re-apply not OK_ALREADY (rc=$RC)"; echo "$OUT"
fi
if printf '%s\n' "$OUT" | grep -q 'changed=no'; then pass "re-apply changed=no"; else fail "re-apply changed!=no"; fi
if [ "$H1" = "$H2" ]; then pass "secrets/.env byte-identical across re-apply"; else fail "secrets/.env mutated by a no-op re-apply"; fi

# --- 4. incomplete identity blocked fail-closed in apply ---------------------
OUT="$(run_roll --apply --local --box sandbox-client-incomplete --include-clients)"; RC=$?
if [ "$RC" = "2" ] && printf '%s\n' "$OUT" | grep -q 'verdict=BLOCKED_IDENTITY_INCOMPLETE'; then
  pass "incomplete identity BLOCKED and counted failed in apply (exit 2)"
else
  fail "incomplete identity apply: rc=$RC"; echo "$OUT"
fi

# --- 5. per-row guards replace a batch-wide --local fatal ---------------------
OUT="$(run_roll --apply --local --include-clients)"; RC=$?
if [ "$RC" = "2" ] && printf '%s\n' "$OUT" | grep -q 'verdict=BLOCKED_IDENTITY_INCOMPLETE'; then
  pass "--apply --local multi-box run continues and blocks the unsafe row"
else
  fail "--apply --local multi-box did not use per-row guards (rc=$RC)"; echo "$OUT"
fi

# --- 6. unparseable openclaw.json: FAILED, file NOT rebuilt ------------------
cp "$SB/.openclaw/openclaw.json" "$WORK/ocjson.good"
printf '{ this is not json' > "$SB/.openclaw/openclaw.json"
HB="$(shasum -a 256 "$SB/.openclaw/openclaw.json" | cut -d' ' -f1)"
OUT="$(run_roll --apply --local --box sandbox-op --no-standing-probe)"; RC=$?
HA="$(shasum -a 256 "$SB/.openclaw/openclaw.json" | cut -d' ' -f1)"
if [ "$RC" = "2" ] && printf '%s\n' "$OUT" | grep -q 'ocjson:PODBEAN_PUBLISH_WEBHOOK_URL=UNPARSEABLE'; then
  pass "unparseable openclaw.json fails the box (no silent d={} rebuild)"
else
  fail "unparseable ocjson: rc=$RC"; echo "$OUT"
fi
if [ "$HB" = "$HA" ]; then
  pass "unparseable openclaw.json left byte-identical (never clobbered)"
else
  fail "unparseable openclaw.json was MODIFIED"
fi
cp "$WORK/ocjson.good" "$SB/.openclaw/openclaw.json"

# --- 7. secret value never on stdout or in the ledger ------------------------
ALLOUT="$(run_roll; run_roll --apply --local --box sandbox-op --no-standing-probe)"
if printf '%s\n' "$ALLOUT" | grep -qF "$TOKEN"; then
  fail "token VALUE leaked to stdout"
else
  pass "token value never on stdout"
fi
if grep -qF "$TOKEN" "$LOG" 2>/dev/null; then
  fail "token VALUE leaked into the ledger log"
else
  pass "token value never in the ledger"
fi

# --- 8. --no-restart on a changed box grades PARTIAL, never OK ---------------
rm -f "$SB/.openclaw/secrets/.env"
printf 'PODBEAN_PUBLISH_TOKEN=%s\n' "$TOKEN" > "$SB/.openclaw/secrets/.env"
printf '{}\n' > "$SB/.openclaw/openclaw.json"
OUT="$(run_roll --apply --local --box sandbox-op --no-standing-probe --no-restart)"; RC=$?
if [ "$RC" = "2" ] && printf '%s\n' "$OUT" | grep -q 'result=PARTIAL reason=changed_but_not_restarted'; then
  pass "--no-restart on a changed box grades PARTIAL (exit 2), not a false OK"
else
  fail "--no-restart changed box: rc=$RC"; echo "$OUT"
fi

# --- 9. optional podcast_id must not turn an apply into PARTIAL ---------------
SKILL_DIR="$SB/.openclaw/skills/58-podcast-production-engine/scripts"
mkdir -p "$SKILL_DIR"
cat > "$SKILL_DIR/podbean_publish.sh" <<'EOF'
#!/bin/sh
# Proxy-mode recognition marker: PODBEAN_PUBLISH_WEBHOOK_URL
[ -n "${PODCAST_CLIENT_LAST_NAME:-}" ] || exit 21
[ -n "${PODCAST_CLIENT_EMAIL:-}" ] || exit 22
[ -z "${PODBEAN_PODCAST_ID:-}" ] || exit 23
printf '%s\n' '{"good_standing":true}'
EOF
chmod 700 "$SKILL_DIR/podbean_publish.sh"
OUT="$(run_roll --apply --local --box sandbox-op)"; RC=$?
if [ "$RC" = "0" ] && printf '%s\n' "$OUT" | grep -q 'dryrun_exit=0 good_standing=true'; then
  pass "empty optional podcast_id reaches the downstream dry-run and grades OK"
else
  fail "empty optional podcast_id blocked the apply (rc=$RC)"; echo "$OUT"
fi

# --- 10. local transport is forbidden for every non-operator row -------------
LOCAL_FLEET="$WORK/local-client-fleet.json"
cat > "$LOCAL_FLEET" <<'EOF'
[{"name":"sandbox-local-row","role":"client","platform":"mac","ssh_target":"local"}]
EOF
OUT="$(python3 "$MANIFEST_BUILDER" --fleet-file "$LOCAL_FLEET" --out "$WORK/local-rejected.json" 2>&1)"; RC=$?
if [ "$RC" = "1" ] && printf '%s\n' "$OUT" | grep -q 'non-operator.*ssh_target.*local'; then
  pass "manifest builder rejects non-operator ssh_target=local"
else
  fail "manifest builder accepted non-operator ssh_target=local (rc=$RC)"; echo "$OUT"
fi

GUARD_HOME="$WORK/local-guard-home"
mkdir -p "$GUARD_HOME/.openclaw/secrets"
printf 'PODBEAN_PUBLISH_TOKEN=%s\n' "$TOKEN" > "$GUARD_HOME/.openclaw/secrets/.env"
printf '{}\n' > "$GUARD_HOME/.openclaw/openclaw.json"
GUARD_MANIFEST="$WORK/local-guard-manifest.json"
cat > "$GUARD_MANIFEST" <<EOF
[
  {"name":"sandbox-guard-op","role":"operator","platform":"mac","ssh_target":"local","home":"$GUARD_HOME",
   "identity":{"last_name":"Operator","email":"operator@example.test","first_name":"","podcast_id":"","complete":true}},
  {"name":"sandbox-guard-row","role":"client","platform":"mac","ssh_target":"local","home":"$GUARD_HOME",
   "identity":{"last_name":"Client","email":"client@example.test","first_name":"","podcast_id":"","complete":true}}
]
EOF
OUT="$(P18_HOME="$GUARD_HOME" bash "$ROLL" --boxes-file "$GUARD_MANIFEST" --log-file "$WORK/local-guard.log" --apply --include-clients --no-standing-probe 2>&1)"; RC=$?
if [ "$RC" = "2" ] && printf '%s\n' "$OUT" | grep -q 'verdict=BLOCKED_LOCAL_CLIENT_IDENTITY'; then
  pass "row-level local transport guard blocks client identity and continues"
else
  fail "row-level local transport guard did not block the client (rc=$RC)"; echo "$OUT"
fi

FLAG_GUARD_MANIFEST="$WORK/local-flag-guard-manifest.json"
cat > "$FLAG_GUARD_MANIFEST" <<EOF
[{"name":"sandbox-flag-row","role":"client","platform":"mac","ssh_target":"host.invalid","home":"$GUARD_HOME",
  "identity":{"last_name":"Client","email":"client@example.test","first_name":"","podcast_id":"","complete":true}}]
EOF
OUT="$(P18_HOME="$GUARD_HOME" bash "$ROLL" --boxes-file "$FLAG_GUARD_MANIFEST" --log-file "$WORK/local-flag-guard.log" --apply --local --include-clients --no-standing-probe 2>&1)"; RC=$?
if [ "$RC" = "2" ] && printf '%s\n' "$OUT" | grep -q 'verdict=BLOCKED_LOCAL_CLIENT_IDENTITY'; then
  pass "row-level guard uses the same --local OR ssh_target=local condition as transport"
else
  fail "--local flag did not use the row-level local identity guard (rc=$RC)"; echo "$OUT"
fi

# --- 11. invalid platforms are rejected and never reach ssh ------------------
BAD_PLATFORM_FLEET="$WORK/bad-platform-fleet.json"
cat > "$BAD_PLATFORM_FLEET" <<'EOF'
[{"name":"sandbox-bad-platform","role":"client","platform":"vpz","ssh_target":"host.invalid"}]
EOF
OUT="$(python3 "$MANIFEST_BUILDER" --fleet-file "$BAD_PLATFORM_FLEET" --out "$WORK/platform-rejected.json" 2>&1)"; RC=$?
if [ "$RC" = "1" ] && printf '%s\n' "$OUT" | grep -q 'unsupported platform'; then
  pass "manifest builder rejects platform outside mac/vps"
else
  fail "manifest builder accepted an unsupported platform (rc=$RC)"; echo "$OUT"
fi

FAKEBIN="$WORK/fakebin"
mkdir -p "$FAKEBIN"
SSH_CALLED="$WORK/ssh-called"
cat > "$FAKEBIN/ssh" <<'EOF'
#!/bin/sh
: > "$SSH_CALLED"
exit 0
EOF
chmod 700 "$FAKEBIN/ssh"
BAD_PLATFORM_MANIFEST="$WORK/bad-platform-manifest.json"
cat > "$BAD_PLATFORM_MANIFEST" <<'EOF'
[{"name":"sandbox-bad-platform","role":"operator","platform":"vpz","ssh_target":"host.invalid",
  "identity":{"last_name":"Operator","email":"operator@example.test","first_name":"","podcast_id":"","complete":true}}]
EOF
OUT="$(SSH_CALLED="$SSH_CALLED" PATH="$FAKEBIN:$PATH" P18_HOME="$SB" bash "$ROLL" --boxes-file "$BAD_PLATFORM_MANIFEST" --log-file "$WORK/bad-platform.log" 2>&1)"; RC=$?
if [ "$RC" = "2" ] && [ ! -e "$SSH_CALLED" ] && printf '%s\n' "$OUT" | grep -q 'unsupported_platform'; then
  pass "roll hard-refuses an invalid platform before transport"
else
  fail "invalid platform reached transport or was not refused (rc=$RC)"; echo "$OUT"
fi

# --- 12. Mac restart uses launchctl and proves PID change plus health ---------
RESTART_BIN="$WORK/restart-bin"
mkdir -p "$RESTART_BIN"
cat > "$RESTART_BIN/launchctl" <<'EOF'
#!/bin/sh
case "$1" in
  list)
    pid="$(sed -n '1p' "$MOCK_STATE" 2>/dev/null)"
    [ -n "$pid" ] && printf '%s\t0\tai.openclaw.gateway\n' "$pid"
    ;;
  kickstart)
    printf '%s\n' kickstart >> "$MOCK_LOG"
    case "$MOCK_RESTART_MODE" in
      success) printf '%s\n' 202 > "$MOCK_STATE"; exit 0 ;;
      fallback) exit 125 ;;
      unchanged) exit 0 ;;
    esac
    ;;
  stop)
    printf '%s\n' stop >> "$MOCK_LOG"
    printf '%s\n' 303 > "$MOCK_STATE"
    exit 0
    ;;
esac
exit 0
EOF
cat > "$RESTART_BIN/curl" <<'EOF'
#!/bin/sh
printf '%s\n' health >> "$MOCK_LOG"
[ "$MOCK_HEALTH_MODE" = "up" ] || exit 1
printf '%s\n' '{"ok":true}'
EOF
cat > "$RESTART_BIN/openclaw" <<'EOF'
#!/bin/sh
printf '%s\n' openclaw >> "$MOCK_LOG"
exit 0
EOF
cat > "$RESTART_BIN/sleep" <<'EOF'
#!/bin/sh
exit 0
EOF
chmod 700 "$RESTART_BIN/launchctl" "$RESTART_BIN/curl" "$RESTART_BIN/openclaw" "$RESTART_BIN/sleep"

RESTART_HOME="$WORK/restart-home"
mkdir -p "$RESTART_HOME/.openclaw/secrets"
printf 'PODBEAN_PUBLISH_TOKEN=%s\n' "$TOKEN" > "$RESTART_HOME/.openclaw/secrets/.env"
printf '{}\n' > "$RESTART_HOME/.openclaw/openclaw.json"
RESTART_MANIFEST="$WORK/restart-manifest.json"
cat > "$RESTART_MANIFEST" <<'EOF'
[{"name":"sandbox-restart-op","role":"operator","platform":"mac","ssh_target":"local",
  "identity":{"last_name":"Operator","email":"operator@example.test","first_name":"","podcast_id":"","complete":true}}]
EOF
MOCK_STATE="$WORK/restart-state"; MOCK_LOG="$WORK/restart-calls"
printf '%s\n' 101 > "$MOCK_STATE"; : > "$MOCK_LOG"
OUT="$(unset P18_HOME; HOME="$RESTART_HOME" MOCK_STATE="$MOCK_STATE" MOCK_LOG="$MOCK_LOG" MOCK_RESTART_MODE=success MOCK_HEALTH_MODE=up PATH="$RESTART_BIN:$PATH" bash "$ROLL" --boxes-file "$RESTART_MANIFEST" --log-file "$WORK/restart.log" --apply --no-standing-probe 2>&1)"; RC=$?
if [ "$RC" = "0" ] && grep -q '^kickstart$' "$MOCK_LOG" && grep -q '^health$' "$MOCK_LOG" && ! grep -q '^openclaw$' "$MOCK_LOG" && printf '%s\n' "$OUT" | grep -q 'restart=ok pid_changed=1 health_ok=1'; then
  pass "Mac restart uses launchctl and proves PID change plus ok:true health"
else
  fail "Mac restart mechanism/proof was incomplete (rc=$RC)"; echo "$OUT"
fi

rm -rf "$RESTART_HOME/.openclaw/backups"
printf 'PODBEAN_PUBLISH_TOKEN=%s\n' "$TOKEN" > "$RESTART_HOME/.openclaw/secrets/.env"
printf '{}\n' > "$RESTART_HOME/.openclaw/openclaw.json"
printf '%s\n' 101 > "$MOCK_STATE"; : > "$MOCK_LOG"
OUT="$(unset P18_HOME; HOME="$RESTART_HOME" MOCK_STATE="$MOCK_STATE" MOCK_LOG="$MOCK_LOG" MOCK_RESTART_MODE=fallback MOCK_HEALTH_MODE=up PATH="$RESTART_BIN:$PATH" bash "$ROLL" --boxes-file "$RESTART_MANIFEST" --log-file "$WORK/restart-fallback.log" --apply --no-standing-probe 2>&1)"; RC=$?
if [ "$RC" = "0" ] && grep -q '^kickstart$' "$MOCK_LOG" && grep -q '^stop$' "$MOCK_LOG" && ! grep -q '^openclaw$' "$MOCK_LOG"; then
  pass "Mac restart uses launchctl stop fallback for kickstart rc 125"
else
  fail "Mac restart rc-125 fallback was not launchctl stop (rc=$RC)"; echo "$OUT"
fi

rm -rf "$RESTART_HOME/.openclaw/backups"
printf 'PODBEAN_PUBLISH_TOKEN=%s\n' "$TOKEN" > "$RESTART_HOME/.openclaw/secrets/.env"
printf '{}\n' > "$RESTART_HOME/.openclaw/openclaw.json"
printf '%s\n' 101 > "$MOCK_STATE"; : > "$MOCK_LOG"
OUT="$(unset P18_HOME; HOME="$RESTART_HOME" MOCK_STATE="$MOCK_STATE" MOCK_LOG="$MOCK_LOG" MOCK_RESTART_MODE=unchanged MOCK_HEALTH_MODE=up PATH="$RESTART_BIN:$PATH" bash "$ROLL" --boxes-file "$RESTART_MANIFEST" --log-file "$WORK/restart-unchanged.log" --apply --no-standing-probe 2>&1)"; RC=$?
if [ "$RC" = "2" ] && printf '%s\n' "$OUT" | grep -q 'restart=failed pid_changed=0 health_ok=1'; then
  pass "healthy old process with an unchanged PID cannot prove restart success"
else
  fail "unchanged gateway PID was accepted as restart proof (rc=$RC)"; echo "$OUT"
fi

rm -rf "$RESTART_HOME/.openclaw/backups"
printf 'PODBEAN_PUBLISH_TOKEN=%s\n' "$TOKEN" > "$RESTART_HOME/.openclaw/secrets/.env"
printf '{}\n' > "$RESTART_HOME/.openclaw/openclaw.json"
printf '%s\n' 101 > "$MOCK_STATE"; : > "$MOCK_LOG"
OUT="$(unset P18_HOME; HOME="$RESTART_HOME" MOCK_STATE="$MOCK_STATE" MOCK_LOG="$MOCK_LOG" MOCK_RESTART_MODE=success MOCK_HEALTH_MODE=down PATH="$RESTART_BIN:$PATH" bash "$ROLL" --boxes-file "$RESTART_MANIFEST" --log-file "$WORK/restart-down.log" --apply --no-standing-probe 2>&1)"; RC=$?
if [ "$RC" = "2" ] && printf '%s\n' "$OUT" | grep -q 'GATEWAY_DOWN=1' && printf '%s\n' "$OUT" | grep -q 'gateway_down=1'; then
  pass "failed restart emits GATEWAY_DOWN=1 and surfaces it in the summary"
else
  fail "failed restart did not surface a dark gateway (rc=$RC)"; echo "$OUT"
fi

# --- 13. duplicate is retired and secret-bearing values stay off argv --------
if sed -n '86,94p' "$OLD_ROLL" | grep -q '^echo "SUPERSEDED"$' &&
   sed -n '86,94p' "$OLD_ROLL" | grep -q 'podbean-publish-provision-roll.sh' &&
   sed -n '86,94p' "$OLD_ROLL" | grep -q '^exit 1$'; then
  pass "duplicate roll exits SUPERSEDED before any fleet logic"
else
  fail "duplicate roll is not retired immediately after pipefail setup"
fi
if grep -q 'python3 - .*\$PUBLISH_TOKEN' "$ROLL" || grep -q 'shquote "\$_pb64"' "$ROLL"; then
  fail "publish token or token-bearing payload remains on a child process argv"
else
  pass "publish token and token-bearing payload are absent from child argv"
fi

# --- 14. nonzero transport status overrides parsed result=OK -----------------
TRANSPORT_BIN="$WORK/transport-bin"
mkdir -p "$TRANSPORT_BIN"
TRANSPORT_CALLS="$WORK/transport-calls"
cat > "$TRANSPORT_BIN/ssh" <<'EOF'
#!/bin/sh
printf '%s\n' called >> "$TRANSPORT_CALLS"
cat >/dev/null
printf '%s\n' \
  'changed=yes' \
  'validate:PODBEAN_PUBLISH_WEBHOOK_URL:env=SET:ocjson=SET' \
  'validate:PODBEAN_PUBLISH_TOKEN:env=SET:ocjson=SET' \
  'validate:PODCAST_CLIENT_LAST_NAME:env=SET:ocjson=SET' \
  'validate:PODCAST_CLIENT_EMAIL:env=SET:ocjson=SET' \
  'result=OK'
exit 23
EOF
chmod 700 "$TRANSPORT_BIN/ssh"
TRANSPORT_MANIFEST="$WORK/transport-manifest.json"
cat > "$TRANSPORT_MANIFEST" <<'EOF'
[
  {"name":"sandbox-transport-op","role":"operator","platform":"mac","ssh_target":"op.invalid",
   "identity":{"last_name":"Operator","email":"operator@example.test","complete":true}},
  {"name":"sandbox-transport-client","role":"client","platform":"mac","ssh_target":"client.invalid",
   "identity":{"last_name":"Client","email":"client@example.test","complete":true}}
]
EOF
: > "$TRANSPORT_CALLS"
OUT="$(TRANSPORT_CALLS="$TRANSPORT_CALLS" PATH="$TRANSPORT_BIN:$PATH" P18_HOME="$SB" bash "$ROLL" --boxes-file "$TRANSPORT_MANIFEST" --log-file "$WORK/transport.log" --apply --include-clients --no-standing-probe 2>&1)"; RC=$?
if [ "$RC" = "2" ] && [ "$(wc -l < "$TRANSPORT_CALLS" | tr -d ' ')" = "1" ] &&
   printf '%s\n' "$OUT" | grep -q 'box=sandbox-transport-op .*verdict=FAILED.*transport_rc=23' &&
   printf '%s\n' "$OUT" | grep -q 'box=sandbox-transport-client .*verdict=REFUSED_OPERATOR_NOT_PROVEN'; then
  pass "nonzero transport exit fails apply and keeps operator gate closed"
else
  fail "nonzero transport exit was ignored or opened the operator gate (rc=$RC)"; echo "$OUT"
fi

# --- 15/17/18. fake VPS exercises host env, recreate, health, and verdict -----
VPS_BIN="$WORK/vps-bin"
VPS_HOME="$WORK/vps-home"
VPS_COMPOSE="$WORK/vps-compose"
VPS_STATE="$WORK/vps-container-id"
mkdir -p "$VPS_BIN" "$VPS_HOME/.openclaw/secrets" "$VPS_COMPOSE"
printf '%s\n' old-container-id > "$VPS_STATE"
printf '%s\n' 'services: {}' > "$VPS_COMPOSE/compose.yaml"
cat > "$VPS_BIN/ssh" <<'EOF'
#!/bin/sh
sh -s
EOF
cat > "$VPS_BIN/docker" <<'EOF'
#!/bin/sh
case "$1" in
  exec)
    shift
    runtime_mode=""
    while [ "$#" -gt 0 ]; do
      case "$1" in
        -i) shift ;;
        -u) shift 2 ;;
        -e)
          case "$2" in P18_MODE_OVERRIDE=*) runtime_mode="${2#*=}" ;; esac
          shift 2
          ;;
        *) shift; break ;;
      esac
    done
    if [ "$runtime_mode" = "runtimeverify" ]; then
      set -a
      . "$MOCK_HOST_ENV"
      set +a
      [ "${MOCK_RUNTIME_STALE:-0}" = "1" ] && unset PODBEAN_PUBLISH_WEBHOOK_URL
    fi
    P18_HOME="$MOCK_VPS_HOME" P18_MODE_OVERRIDE="$runtime_mode" sh -s
    ;;
  compose)
    printf '%s-new\n' "$(sed -n '1p' "$MOCK_CID_STATE")" > "$MOCK_CID_STATE"
    ;;
  ps)
    printf '%s\n' 'Up 10 seconds'
    ;;
  inspect)
    case "$3" in
      *State.Running*) printf '%s\n' true ;;
      *Id*) sed -n '1p' "$MOCK_CID_STATE" ;;
      *) exit 1 ;;
    esac
    ;;
  *) exit 2 ;;
esac
EOF
cat > "$VPS_BIN/curl" <<'EOF'
#!/bin/sh
printf '%s\n' '{"ok":true}'
EOF
cat > "$VPS_BIN/sleep" <<'EOF'
#!/bin/sh
exit 0
EOF
chmod 700 "$VPS_BIN/ssh" "$VPS_BIN/docker" "$VPS_BIN/curl" "$VPS_BIN/sleep"

printf '%s\n' \
  "PODBEAN_PUBLISH_WEBHOOK_URL=https://main.blackceoautomations.com/webhook/podbean-publish" \
  "PODBEAN_PUBLISH_TOKEN=$TOKEN" \
  'PODCAST_CLIENT_LAST_NAME=Operator' \
  'PODCAST_CLIENT_EMAIL=operator@example.test' > "$VPS_HOME/.openclaw/secrets/.env"
TOKEN="$TOKEN" VPS_OCJSON="$VPS_HOME/.openclaw/openclaw.json" python3 - <<'PY'
import json, os
json.dump({"env": {"vars": {
    "PODBEAN_PUBLISH_WEBHOOK_URL": "https://main.blackceoautomations.com/webhook/podbean-publish",
    "PODBEAN_PUBLISH_TOKEN": os.environ["TOKEN"],
    "PODCAST_CLIENT_LAST_NAME": "Operator",
    "PODCAST_CLIENT_EMAIL": "operator@example.test",
}}}, open(os.environ["VPS_OCJSON"], "w"))
PY
cat > "$VPS_COMPOSE/.env" <<EOF
UNCHANGED_MARKER=original
PODBEAN_PUBLISH_WEBHOOK_URL=https://main.blackceoautomations.com/webhook/podbean-publish
PODBEAN_PUBLISH_TOKEN=$TOKEN
PODCAST_CLIENT_LAST_NAME=Operator
PODCAST_CLIENT_EMAIL=stale@example.test
EOF
cp "$VPS_COMPOSE/.env" "$WORK/vps-host-env.original"
VPS_MANIFEST="$WORK/vps-manifest.json"
cat > "$VPS_MANIFEST" <<EOF
[{"name":"sandbox-vps","role":"operator","platform":"vps","ssh_target":"vps.invalid",
  "container":"sandbox-vps-openclaw-1","compose_dir":"$VPS_COMPOSE",
  "identity":{"last_name":"Operator","email":"operator@example.test","complete":true}}]
EOF
OUT="$(MOCK_HOST_ENV="$VPS_COMPOSE/.env" MOCK_VPS_HOME="$VPS_HOME" MOCK_CID_STATE="$VPS_STATE" PATH="$VPS_BIN:$PATH" P18_HOME="$SB" bash "$ROLL" --boxes-file "$VPS_MANIFEST" --log-file "$WORK/vps.log" --apply --no-standing-probe 2>&1)"; RC=$?
VPS_BACKUPS="$(find "$VPS_COMPOSE" -maxdepth 1 -type f -name '.env.bak.s58u18-*' -print)"
if [ "$(printf '%s\n' "$VPS_BACKUPS" | sed '/^$/d' | wc -l | tr -d ' ')" = "1" ] && cmp -s "$WORK/vps-host-env.original" "$VPS_BACKUPS"; then
  pass "VPS host env has one unique timestamped snapshot of the original"
else
  fail "VPS host env backup was missing, repeated, or not the original"
fi
if [ "$RC" = "0" ] && printf '%s\n' "$OUT" | grep -q 'restart=recreate rc=0 container_id_changed=1 health_ok=1 runtime_values=1'; then
  pass "VPS recreate proves new container, health, and inherited values"
else
  fail "VPS recreate lacked identity/health/runtime proof (rc=$RC)"; echo "$OUT"
fi
if printf '%s\n' "$OUT" | grep -q 'box=sandbox-vps .*verdict=OK ' &&
   ! printf '%s\n' "$OUT" | grep -q 'box=sandbox-vps .*verdict=OK_ALREADY'; then
  pass "host-only VPS change is reported OK, not OK_ALREADY"
else
  fail "host-only VPS change was misreported as OK_ALREADY"; echo "$OUT"
fi

printf '{}\n' > "$VPS_HOME/.openclaw/openclaw.json"
OUT="$(MOCK_RUNTIME_STALE=1 MOCK_HOST_ENV="$VPS_COMPOSE/.env" MOCK_VPS_HOME="$VPS_HOME" MOCK_CID_STATE="$VPS_STATE" PATH="$VPS_BIN:$PATH" P18_HOME="$SB" bash "$ROLL" --boxes-file "$VPS_MANIFEST" --log-file "$WORK/vps-stale.log" --apply --no-standing-probe 2>&1)"; RC=$?
if [ "$RC" = "2" ] && printf '%s\n' "$OUT" | grep -q 'runtime_values=0'; then
  pass "VPS recreate rejects a healthy container with stale inherited values"
else
  fail "VPS recreate accepted stale inherited values (rc=$RC)"; echo "$OUT"
fi

# --- 16. backup copy failure aborts before mutation --------------------------
BACKUP_HOME="$WORK/backup-home"
BACKUP_BIN="$WORK/backup-bin"
mkdir -p "$BACKUP_HOME/.openclaw/secrets" "$BACKUP_BIN"
printf 'PODBEAN_PUBLISH_TOKEN=%s\n' "$TOKEN" > "$BACKUP_HOME/.openclaw/secrets/.env"
printf '{}\n' > "$BACKUP_HOME/.openclaw/openclaw.json"
cat > "$BACKUP_BIN/cp" <<'EOF'
#!/bin/sh
exit 73
EOF
chmod 700 "$BACKUP_BIN/cp"
BACKUP_MANIFEST="$WORK/backup-manifest.json"
cat > "$BACKUP_MANIFEST" <<EOF
[{"name":"sandbox-backup-op","role":"operator","platform":"mac","ssh_target":"local","home":"$BACKUP_HOME",
  "identity":{"last_name":"Operator","email":"operator@example.test","complete":true}}]
EOF
BEFORE_ENV="$(shasum -a 256 "$BACKUP_HOME/.openclaw/secrets/.env" | cut -d' ' -f1)"
BEFORE_JSON="$(shasum -a 256 "$BACKUP_HOME/.openclaw/openclaw.json" | cut -d' ' -f1)"
OUT="$(PATH="$BACKUP_BIN:$PATH" P18_HOME="$BACKUP_HOME" bash "$ROLL" --boxes-file "$BACKUP_MANIFEST" --log-file "$WORK/backup.log" --apply --no-standing-probe 2>&1)"; RC=$?
AFTER_ENV="$(shasum -a 256 "$BACKUP_HOME/.openclaw/secrets/.env" | cut -d' ' -f1)"
AFTER_JSON="$(shasum -a 256 "$BACKUP_HOME/.openclaw/openclaw.json" | cut -d' ' -f1)"
if [ "$RC" = "2" ] && [ "$BEFORE_ENV" = "$AFTER_ENV" ] && [ "$BEFORE_JSON" = "$AFTER_JSON" ] &&
   printf '%s\n' "$OUT" | grep -q 'reason=backup_copy_failed'; then
  pass "backup copy failure aborts before any config mutation"
else
  fail "backup copy failure did not fail closed before mutation (rc=$RC)"; echo "$OUT"
fi

# --- 19. ledger must be writable before transport ----------------------------
LEDGER_BIN="$WORK/ledger-bin"
LEDGER_MARKER="$WORK/ledger-transport-called"
mkdir -p "$LEDGER_BIN" "$WORK/ledger-is-a-directory"
cat > "$LEDGER_BIN/ssh" <<'EOF'
#!/bin/sh
: > "$LEDGER_MARKER"
cat >/dev/null
exit 0
EOF
chmod 700 "$LEDGER_BIN/ssh"
OUT="$(LEDGER_MARKER="$LEDGER_MARKER" PATH="$LEDGER_BIN:$PATH" P18_HOME="$SB" bash "$ROLL" --boxes-file "$TRANSPORT_MANIFEST" --box sandbox-transport-op --log-file "$WORK/ledger-is-a-directory" 2>&1)"; RC=$?
if [ "$RC" = "1" ] && [ ! -e "$LEDGER_MARKER" ] && printf '%s\n' "$OUT" | grep -q 'ledger'; then
  pass "unwritable ledger aborts before any box transport"
else
  fail "unwritable ledger did not abort before transport (rc=$RC)"; echo "$OUT"
fi

# --- 20. manifest builder rejects duplicate identities/targets ---------------
DUP_NAMES="$WORK/duplicate-names.json"
cat > "$DUP_NAMES" <<'EOF'
[
  {"name":"sandbox-dup","role":"client","platform":"vps","ssh_target":"one.invalid","compose_dir":"/tmp/one"},
  {"name":"sandbox-dup","role":"client","platform":"vps","ssh_target":"two.invalid","compose_dir":"/tmp/two"}
]
EOF
OUT="$(python3 "$MANIFEST_BUILDER" --fleet-file "$DUP_NAMES" --out "$WORK/dup-names-out.json" 2>&1)"; RC=$?
if [ "$RC" = "1" ] && printf '%s\n' "$OUT" | grep -q 'duplicate.*name'; then
  pass "manifest builder rejects duplicate box names"
else
  fail "manifest builder accepted duplicate box names (rc=$RC)"; echo "$OUT"
fi

DUP_HOSTS="$WORK/duplicate-hosts.json"
cat > "$DUP_HOSTS" <<'EOF'
[
  {"name":"sandbox-one","role":"client","platform":"vps","ssh_target":"first@same.invalid","compose_dir":"/tmp/one"},
  {"name":"sandbox-two","role":"client","platform":"vps","ssh_target":"second@same.invalid","compose_dir":"/tmp/two"}
]
EOF
OUT="$(python3 "$MANIFEST_BUILDER" --fleet-file "$DUP_HOSTS" --out "$WORK/dup-hosts-out.json" 2>&1)"; RC=$?
if [ "$RC" = "1" ] && printf '%s\n' "$OUT" | grep -q 'duplicate.*SSH host'; then
  pass "manifest builder rejects duplicate SSH hosts"
else
  fail "manifest builder accepted duplicate SSH hosts (rc=$RC)"; echo "$OUT"
fi

DUP_OPERATORS="$WORK/duplicate-operators.json"
cat > "$DUP_OPERATORS" <<'EOF'
[
  {"name":"sandbox-op-one","role":"operator","platform":"mac","ssh_target":"one.invalid"},
  {"name":"sandbox-op-two","role":"operator","platform":"mac","ssh_target":"two.invalid"}
]
EOF
OUT="$(python3 "$MANIFEST_BUILDER" --fleet-file "$DUP_OPERATORS" --out "$WORK/dup-operators-out.json" 2>&1)"; RC=$?
if [ "$RC" = "1" ] && printf '%s\n' "$OUT" | grep -q 'duplicate.*operator'; then
  pass "manifest builder rejects duplicate operator entries"
else
  fail "manifest builder accepted duplicate operator entries (rc=$RC)"; echo "$OUT"
fi

echo "=== result: PASS=$PASS FAIL=$FAIL ==="
[ "$FAIL" = "0" ] || exit 1
exit 0
