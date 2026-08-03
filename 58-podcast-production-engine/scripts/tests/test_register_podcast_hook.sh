#!/usr/bin/env bash
# =============================================================================
# PODCAST PRODUCTION ENGINE :: register-podcast-hook.sh tests
#
# Offline battery (temp config file only; no network, no live gateway, no real
# ~/.openclaw state, no secret values beyond a synthetic fixture that must
# NEVER leak into the written config). Asserts the unit contract:
#
#   1. bash -n passes
#   2. usage / --help exits 0 and documents --client-slug and --dry-run
#   3. missing or invalid --client-slug fails closed (exit 2)
#   4. --dry-run prints the planned registration and writes nothing
#   5. a real registration without PODCAST_INTAKE_HOOK_SECRET fails closed
#   6. a real registration lands the route at the documented location
#      plugins.entries.webhooks.config.routes.<routeId> with the wiring.json
#      session binding, a SecretRef by LABEL (never a value), and the podcast
#      agent id + podcast: prefix merged into hooks.allowedAgentIds /
#      hooks.allowedSessionKeyPrefixes while preserving sibling entries
#   7. the defaultSessionKey crash-loop guard (the pre-existing default stays
#      inside allowedSessionKeyPrefixes)
#   8. re-run is an idempotent no-op (config bytes unchanged, no second backup)
#   9. positional caller shape (provision/revoke contract) is honored, and a
#      mismatched mapping id is refused
#  10. --remove deletes the route and the podcast allow-list entries, preserves
#      siblings, and is idempotent
#  11. an unparseable config and a disabled webhooks plugin fail closed
#  12. service-env: injects the SecretRef env vars + PODCAST_INTAKE_ROUTE_ID
#      into the mocked gateway service-env file (plist ProgramArguments seam)
#  13. service-env: idempotent (a second run leaves the file bytes unchanged)
#  14. service-env: drift heal of a stale PODCAST_INTAKE_ROUTE_ID
#  15. service-env: --dry-run never modifies the service-env file
#  16. service-env: missing plist warns and never fails the registration
#  17. service-env: never invoked during --remove
#  18. service-env: PODCAST_CLIENT_LOCATION_ID (the intake tenant check) is
#      appended when SET, and the value never appears in the output
#  19. service-env: PODCAST_CLIENT_LOCATION_ID absent means a skip, not a fail
#  20. service-env: resolves the env file from the REAL fleet plist shape
#      (/bin/sh, env-wrapper.sh, env-file, node, index.js, gateway, --port)
#      and never touches the wrapper script
#  21. service-env: heal on rerun. A no-op config merge (route already
#      registered) still appends the missing labels to the service-env file
#      and creates no config backup
# =============================================================================
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_UNDER_TEST="$HERE/../register-podcast-hook.sh"

PASS=0
FAIL=0
pass() { PASS=$((PASS + 1)); printf 'PASS: %s\n' "$1"; }
fail() { FAIL=$((FAIL + 1)); printf 'FAIL: %s\n' "$1"; }
check() { # $1 name ; $2 condition (0 true)
  if [ "$2" -eq 0 ]; then pass "$1"; else fail "$1"; fi
}

WORK="$(mktemp -d "${TMPDIR:-/tmp}/reg-hook-test.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
CFG="$WORK/openclaw.json"

# Run the script with a controlled environment (never a real HOME or config).
# $1 expected rc ; remaining args go to the script. Captures output for the
# caller to inspect via $OUT (combined stdout+stderr).
run_script() {
  local want_rc="$1"; shift
  local rc=0
  OUT="$(HOME="$WORK/home" PODCAST_OPENCLAW_CONFIG="$CFG" "$@" 2>&1)" || rc=$?
  LAST_RC=$rc
  if [ "$rc" -eq "$want_rc" ]; then return 0; fi
  return 1
}

write_cfg() { printf '%s' "$1" > "$CFG"; }
route_of() { jq -c --arg rid "$1" '.plugins.entries.webhooks.config.routes[$rid] // empty' "$CFG"; }

# --------------------------------------------------------------------------- #
# 1. syntax
# --------------------------------------------------------------------------- #
if bash -n "$SCRIPT_UNDER_TEST"; then pass "bash -n"; else fail "bash -n"; fi

# --------------------------------------------------------------------------- #
# 2. usage
# --------------------------------------------------------------------------- #
write_cfg '{}'
if run_script 0 "$SCRIPT_UNDER_TEST" --help && printf '%s' "$OUT" | grep -q -- "--client-slug" && printf '%s' "$OUT" | grep -q -- "--dry-run"; then
  pass "usage documents --client-slug and --dry-run"
else
  fail "usage documents --client-slug and --dry-run"
fi

# --------------------------------------------------------------------------- #
# 3. input validation (fail closed)
# --------------------------------------------------------------------------- #
if run_script 2 "$SCRIPT_UNDER_TEST"; then
  pass "missing --client-slug -> exit 2"
else
  fail "missing --client-slug -> exit 2 (rc=$LAST_RC)"
fi
if run_script 2 "$SCRIPT_UNDER_TEST" --client-slug "Bad Slug!"; then
  pass "invalid slug -> exit 2"
else
  fail "invalid slug -> exit 2 (rc=$LAST_RC)"
fi

# --------------------------------------------------------------------------- #
# 4. dry-run prints the plan and writes nothing
# --------------------------------------------------------------------------- #
write_cfg '{"agents":{"list":[{"id":"main"}]}}'
SUM_BEFORE="$(shasum "$CFG" | awk '{print $1}')"
if run_script 0 env PODCAST_INTAKE_HOOK_SECRET=synthetic-fixture-secret \
     "$SCRIPT_UNDER_TEST" --client-slug acme-media --dry-run \
   && printf '%s' "$OUT" | grep -q "podcast-intake-acme-media" \
   && printf '%s' "$OUT" | grep -q "podcast:intake:acme-media" \
   && printf '%s' "$OUT" | grep -q "dry-run"; then
  SUM_AFTER="$(shasum "$CFG" | awk '{print $1}')"
  if [ "$SUM_BEFORE" = "$SUM_AFTER" ]; then
    pass "dry-run prints the planned registration and writes nothing"
  else
    fail "dry-run mutated the config file"
  fi
else
  fail "dry-run prints the planned registration (rc=$LAST_RC)"
fi
# dry-run with the secret label NOT SET still plans (with a warning)
if run_script 0 env -u PODCAST_INTAKE_HOOK_SECRET \
     "$SCRIPT_UNDER_TEST" --client-slug acme-media --dry-run \
   && printf '%s' "$OUT" | grep -q "NOT SET"; then
  pass "dry-run with unset secret plans with a warning"
else
  fail "dry-run with unset secret plans with a warning (rc=$LAST_RC)"
fi

# --------------------------------------------------------------------------- #
# 5. real registration without the route secret fails closed
# --------------------------------------------------------------------------- #
write_cfg '{}'
SUM_BEFORE="$(shasum "$CFG" | awk '{print $1}')"
if run_script 2 env -u PODCAST_INTAKE_HOOK_SECRET \
     "$SCRIPT_UNDER_TEST" --client-slug acme-media; then
  SUM_AFTER="$(shasum "$CFG" | awk '{print $1}')"
  if [ "$SUM_BEFORE" = "$SUM_AFTER" ]; then
    pass "unset route secret -> fail closed, nothing written"
  else
    fail "unset route secret still wrote the config"
  fi
else
  fail "unset route secret -> fail closed (rc=$LAST_RC)"
fi

# --------------------------------------------------------------------------- #
# 6. real registration: documented location + wiring.json session binding +
#    SecretRef by label + allow-list merge + sibling preservation + no leak
# --------------------------------------------------------------------------- #
write_cfg '{
  "hooks": {
    "enabled": true,
    "path": "/hooks",
    "token": "${SOME_OTHER_HOOKS_TOKEN}",
    "defaultSessionKey": "hook:ghl:default",
    "allowRequestSessionKey": true,
    "allowedSessionKeyPrefixes": ["hook:ghl:"],
    "allowedAgentIds": ["main"],
    "mappings": [{"id":"ghl-inbound","match":{"path":"ghl-inbound"},"action":"agent"}]
  },
  "plugins": {"entries": {"webhooks": {"enabled": true, "config": {"routes": {
    "other-skill-route": {"sessionKey": "other:thing", "secret": "x"}
  }}}}}
}'
SUM_BEFORE="$(shasum "$CFG" | awk '{print $1}')"
BACKUPS_BEFORE="$(ls "$WORK" | grep -c 'bak-podcast-hook' || true)"
if run_script 0 env PODCAST_INTAKE_HOOK_SECRET=synthetic-fixture-secret \
     PODCAST_CLIENT_LOCATION_ID=LOC0000000000000000abcd \
     "$SCRIPT_UNDER_TEST" --client-slug acme-media; then
  R="$(route_of podcast-intake-acme-media)"
  ok=0
  [ -n "$R" ] || ok=1
  [ "$(printf '%s' "$R" | jq -r '.sessionKey')" = "podcast:intake:acme-media" ] || ok=1
  [ "$(printf '%s' "$R" | jq -r '.secret.source')" = "env" ] || ok=1
  [ "$(printf '%s' "$R" | jq -r '.secret.provider')" = "default" ] || ok=1
  [ "$(printf '%s' "$R" | jq -r '.secret.id')" = "PODCAST_INTAKE_HOOK_SECRET" ] || ok=1
  [ "$(printf '%s' "$R" | jq -r '.path')" = "/plugins/webhooks/podcast-intake-acme-media" ] || ok=1
  [ "$(printf '%s' "$R" | jq -r '.controllerId')" = "webhooks/podcast-intake-acme-media" ] || ok=1
  jq -e '.hooks.allowedAgentIds | index("dept-podcast") != null' "$CFG" >/dev/null || ok=1
  jq -e '.hooks.allowedSessionKeyPrefixes | index("podcast:") != null' "$CFG" >/dev/null || ok=1
  # sibling route + sibling hook mapping preserved byte-for-byte where untouched
  [ "$(jq -r '.plugins.entries.webhooks.config.routes["other-skill-route"].sessionKey' "$CFG")" = "other:thing" ] || ok=1
  [ "$(jq -r '.hooks.mappings[0].id' "$CFG")" = "ghl-inbound" ] || ok=1
  # the secret VALUE never lands in the config; only the label
  if grep -q "synthetic-fixture-secret" "$CFG"; then ok=1; fi
  if printf '%s' "$OUT" | grep -q "synthetic-fixture-secret"; then ok=1; fi
  # exactly one backup was created
  BACKUPS_AFTER="$(ls "$WORK" | grep -c 'bak-podcast-hook' || true)"
  [ "$((BACKUPS_AFTER - BACKUPS_BEFORE))" -eq 1 ] || ok=1
  check "registration lands at the documented location with the session binding" "$ok"
else
  fail "registration run (rc=$LAST_RC): $OUT"
fi

# --------------------------------------------------------------------------- #
# 7. defaultSessionKey crash-loop guard (U88-GK-26): the pre-existing default
#    session key stays inside allowedSessionKeyPrefixes
# --------------------------------------------------------------------------- #
if jq -e '.hooks.allowedSessionKeyPrefixes | index("hook:ghl:default") != null' "$CFG" >/dev/null \
   && jq -e '.hooks.allowedSessionKeyPrefixes | index("hook:ghl:") != null' "$CFG" >/dev/null; then
  pass "defaultSessionKey preserved inside allowedSessionKeyPrefixes"
else
  fail "defaultSessionKey preserved inside allowedSessionKeyPrefixes"
fi

# --------------------------------------------------------------------------- #
# 8. idempotency: re-run is a no-op (bytes unchanged, no second backup)
# --------------------------------------------------------------------------- #
SUM_AFTER_REG="$(shasum "$CFG" | awk '{print $1}')"
BACKUPS_BEFORE="$(ls "$WORK" | grep -c 'bak-podcast-hook' || true)"
if run_script 0 env PODCAST_INTAKE_HOOK_SECRET=synthetic-fixture-secret \
     "$SCRIPT_UNDER_TEST" --client-slug acme-media \
   && printf '%s' "$OUT" | grep -qi "no-op"; then
  SUM_RERUN="$(shasum "$CFG" | awk '{print $1}')"
  BACKUPS_AFTER="$(ls "$WORK" | grep -c 'bak-podcast-hook' || true)"
  if [ "$SUM_AFTER_REG" = "$SUM_RERUN" ] && [ "$BACKUPS_BEFORE" = "$BACKUPS_AFTER" ]; then
    pass "re-run is an idempotent no-op (no rewrite, no second backup)"
  else
    fail "re-run rewrote the config or added a backup"
  fi
else
  fail "re-run is an idempotent no-op (rc=$LAST_RC): $OUT"
fi

# --------------------------------------------------------------------------- #
# 9. positional caller contract (provision + revoke shapes)
# --------------------------------------------------------------------------- #
write_cfg '{}'
if run_script 0 env PODCAST_INTAKE_HOOK_SECRET=synthetic-fixture-secret \
     "$SCRIPT_UNDER_TEST" acme-media podcast-intake-acme-media; then
  if [ -n "$(route_of podcast-intake-acme-media)" ]; then
    pass "positional <slug> <mapping-id> caller shape honored"
  else
    fail "positional caller shape did not register the route"
  fi
else
  fail "positional <slug> <mapping-id> caller shape (rc=$LAST_RC): $OUT"
fi
if run_script 2 env PODCAST_INTAKE_HOOK_SECRET=synthetic-fixture-secret \
     "$SCRIPT_UNDER_TEST" acme-media podcast-intake-OTHER-client; then
  pass "mismatched mapping id refused (fail closed)"
else
  fail "mismatched mapping id refused (rc=$LAST_RC)"
fi

# --------------------------------------------------------------------------- #
# 10. --remove: deletes route + podcast allow-list entries, preserves siblings,
#     idempotent on a second run. Seed a config that already carries the
#     registered podcast route plus a sibling route, then remove it.
# --------------------------------------------------------------------------- #
write_cfg '{
  "hooks": {
    "enabled": true,
    "allowedSessionKeyPrefixes": ["hook:ghl:", "podcast:"],
    "allowedAgentIds": ["main", "dept-podcast"]
  },
  "plugins": {"entries": {"webhooks": {"enabled": true, "config": {"routes": {
    "other-skill-route": {"sessionKey": "other:thing", "secret": "x"},
    "podcast-intake-acme-media": {"enabled": true, "path": "/plugins/webhooks/podcast-intake-acme-media", "sessionKey": "podcast:intake:acme-media", "secret": {"source": "env", "provider": "default", "id": "PODCAST_INTAKE_HOOK_SECRET"}, "controllerId": "webhooks/podcast-intake-acme-media"}
  }}}}}
}'
if run_script 0 env PODCAST_INTAKE_HOOK_SECRET=synthetic-fixture-secret \
     "$SCRIPT_UNDER_TEST" --remove acme-media podcast-intake-acme-media; then
  ok=0
  [ -z "$(route_of podcast-intake-acme-media)" ] || ok=1
  jq -e '.hooks.allowedAgentIds | index("dept-podcast") == null' "$CFG" >/dev/null || ok=1
  jq -e '.hooks.allowedSessionKeyPrefixes | index("podcast:") == null' "$CFG" >/dev/null || ok=1
  [ "$(jq -r '.plugins.entries.webhooks.config.routes["other-skill-route"].sessionKey' "$CFG")" = "other:thing" ] || ok=1
  check "--remove deletes the route and podcast allow-list entries, preserves siblings" "$ok"
else
  fail "--remove (rc=$LAST_RC): $OUT"
fi
if run_script 0 env PODCAST_INTAKE_HOOK_SECRET=synthetic-fixture-secret \
     "$SCRIPT_UNDER_TEST" --remove acme-media podcast-intake-acme-media \
   && printf '%s' "$OUT" | grep -qi "no-op"; then
  pass "--remove on an absent route is a no-op"
else
  fail "--remove on an absent route is a no-op (rc=$LAST_RC)"
fi

# --------------------------------------------------------------------------- #
# 11. fail-closed on a broken box: unparseable config, disabled plugin
# --------------------------------------------------------------------------- #
write_cfg '{ not json'
SUM_BEFORE="$(shasum "$CFG" | awk '{print $1}')"
if run_script 2 env PODCAST_INTAKE_HOOK_SECRET=synthetic-fixture-secret \
     "$SCRIPT_UNDER_TEST" --client-slug acme-media; then
  SUM_AFTER="$(shasum "$CFG" | awk '{print $1}')"
  if [ "$SUM_BEFORE" = "$SUM_AFTER" ]; then
    pass "unparseable config refused untouched (fail closed)"
  else
    fail "unparseable config was touched"
  fi
else
  fail "unparseable config refused (rc=$LAST_RC)"
fi
write_cfg '{"plugins":{"entries":{"webhooks":{"enabled":false}}}}'
if run_script 2 env PODCAST_INTAKE_HOOK_SECRET=synthetic-fixture-secret \
     "$SCRIPT_UNDER_TEST" --client-slug acme-media \
   && printf '%s' "$OUT" | grep -qi "disabled"; then
  pass "explicitly disabled webhooks plugin refused (fail closed)"
else
  fail "explicitly disabled webhooks plugin refused (rc=$LAST_RC)"
fi

# --------------------------------------------------------------------------- #
# 12. Service-env injection: mock a plist + service-env file, register the
#     route, and assert PODCAST_INTAKE_ROUTE_ID and PODCAST_INTAKE_HOOK_SECRET
#     are injected into the gateway service-env file.
# --------------------------------------------------------------------------- #
write_cfg '{"hooks":{"enabled":true,"allowedSessionKeyPrefixes":["hook:ghl:"],"allowedAgentIds":["main"]},"plugins":{"entries":{"webhooks":{"enabled":true,"config":{"routes":{}}}}}}'
PLIST_DIR="$WORK/home/Library/LaunchAgents"
mkdir -p "$PLIST_DIR"
export SVC_ENV="$WORK/service-env/ai.openclaw.gateway.env"
mkdir -p "$(dirname "$SVC_ENV")"
printf '%s\n' "SOME_EXISTING_VAR=keep-me" > "$SVC_ENV"
# Write a binary plist with ProgramArguments: [env-wrapper.sh, <env-file>, gateway]
python3 -c "
import plistlib
pl = {'ProgramArguments': ['env-wrapper.sh', '${SVC_ENV}', '/usr/local/bin/openclaw-gateway']}
with open('${PLIST_DIR}/ai.openclaw.gateway.plist', 'wb') as f:
    plistlib.dump(pl, f, fmt=plistlib.FMT_BINARY)
"
if run_script 0 env PODCAST_INTAKE_HOOK_SECRET=synthetic-fixture-secret \
     PODCAST_CLIENT_LOCATION_ID=LOC0000000000000000abcd \
     HOME="$WORK/home" \
     "$SCRIPT_UNDER_TEST" --client-slug acme-media; then
  ok=0
  grep -q "PODCAST_INTAKE_ROUTE_ID=podcast-intake-acme-media" "$SVC_ENV" || ok=1
  grep -q "PODCAST_INTAKE_HOOK_SECRET=synthetic-fixture-secret" "$SVC_ENV" || ok=1
  grep -q "SOME_EXISTING_VAR=keep-me" "$SVC_ENV" || ok=1
  # The secret VALUE is inside the env file (that file IS secrets), but must
  # never appear in stdout.
  if printf '%s' "$OUT" | grep -q "synthetic-fixture-secret"; then ok=1; fi
  check "service-env: injects SecretRef env vars + PODCAST_INTAKE_ROUTE_ID into gateway service-env file" "$ok"
else
  fail "service-env injection run (rc=$LAST_RC): $OUT"
fi

# --------------------------------------------------------------------------- #
# 13. Service-env: is idempotent (second run does not change the file)
# --------------------------------------------------------------------------- #
SVC_SUM_BEFORE="$(shasum "$SVC_ENV" | awk '{print $1}')"
if run_script 0 env PODCAST_INTAKE_HOOK_SECRET=synthetic-fixture-secret \
     HOME="$WORK/home" \
     "$SCRIPT_UNDER_TEST" --client-slug acme-media; then
  SVC_SUM_AFTER="$(shasum "$SVC_ENV" | awk '{print $1}')"
  check "service-env: idempotent (no duplicate injection)" "$([ "$SVC_SUM_BEFORE" = "$SVC_SUM_AFTER" ]; echo $?)"
else
  fail "service-env idempotent run (rc=$LAST_RC): $OUT"
fi

# --------------------------------------------------------------------------- #
# 14. Service-env: updates stale values (drift heal)
# --------------------------------------------------------------------------- #
sed -i '' -e 's/PODCAST_INTAKE_ROUTE_ID=podcast-intake-acme-media/PODCAST_INTAKE_ROUTE_ID=wrong-value/' "$SVC_ENV"
if run_script 0 env PODCAST_INTAKE_HOOK_SECRET=synthetic-fixture-secret \
     HOME="$WORK/home" \
     "$SCRIPT_UNDER_TEST" --client-slug acme-media; then
  check "service-env: heals a stale PODCAST_INTAKE_ROUTE_ID" \
    "$(grep -c "PODCAST_INTAKE_ROUTE_ID=podcast-intake-acme-media" "$SVC_ENV" || true)"
else
  fail "service-env drift heal (rc=$LAST_RC): $OUT"
fi

# --------------------------------------------------------------------------- #
# 15. Service-env: the injection step is skipped when the secret is absent but
#     the registration succeeds (dry-run; the real-registration fail-closed-on-
#     missing-secret guard is tested in test 5 -- this verifies dry-run does not
#     try to write the service-env file).
# --------------------------------------------------------------------------- #
write_cfg '{"hooks":{"enabled":true,"allowedSessionKeyPrefixes":["hook:ghl:"],"allowedAgentIds":["main"]},"plugins":{"entries":{"webhooks":{"enabled":true,"config":{"routes":{}}}}}}'
rm -rf "$(dirname "$SVC_ENV")"
mkdir -p "$(dirname "$SVC_ENV")"
printf '%s\n' "SOME_EXISTING_VAR=keep-me" > "$SVC_ENV"
SUM_BEFORE="$(shasum "$SVC_ENV" | awk '{print $1}')"
if run_script 0 env -u PODCAST_INTAKE_HOOK_SECRET \
     HOME="$WORK/home" \
     "$SCRIPT_UNDER_TEST" --client-slug acme-media --dry-run; then
  SUM_AFTER="$(shasum "$SVC_ENV" | awk '{print $1}')"
  if [ "$SUM_BEFORE" = "$SUM_AFTER" ]; then
    pass "service-env: dry-run does not modify the service-env file"
  else
    fail "service-env: dry-run modified the service-env file"
  fi
else
  fail "service-env dry-run guard (rc=$LAST_RC): $OUT"
fi

# --------------------------------------------------------------------------- #
# 16. Service-env: without a plist, warns and does not fail
# --------------------------------------------------------------------------- #
write_cfg '{}'
rm -f "$PLIST_DIR/ai.openclaw.gateway.plist"
if run_script 0 env PODCAST_INTAKE_HOOK_SECRET=synthetic-fixture-secret \
     HOME="$WORK/home" \
     "$SCRIPT_UNDER_TEST" --client-slug acme-media \
   && printf '%s' "$OUT" | grep -qi "plist not found"; then
  pass "service-env: missing plist warns (non-fatal; registration succeeds)"
else
  fail "service-env missing plist (rc=$LAST_RC): $OUT"
fi

# --------------------------------------------------------------------------- #
# 17. Service-env: does NOT run during --remove or --dry-run
# --------------------------------------------------------------------------- #
# Verify --remove mode does not invoke service-env injection
write_cfg '{
  "hooks": {"enabled": true, "allowedSessionKeyPrefixes": ["podcast:"], "allowedAgentIds": ["main","dept-podcast"]},
  "plugins": {"entries": {"webhooks": {"enabled": true, "config": {"routes": {
    "podcast-intake-acme-media": {"enabled": true, "path": "/plugins/webhooks/podcast-intake-acme-media", "sessionKey": "podcast:intake:acme-media", "secret": {"source": "env", "provider": "default", "id": "PODCAST_INTAKE_HOOK_SECRET"}, "controllerId": "webhooks/podcast-intake-acme-media"}
  }}}}}
}'
rm -rf "$(dirname "$SVC_ENV")"
mkdir -p "$(dirname "$SVC_ENV")"
printf '%s\n' "BEFORE_REMOVE=should-survive" > "$SVC_ENV"
# Recreate plist so inject_service_env can find the env file
rm -f "$PLIST_DIR/ai.openclaw.gateway.plist"
python3 -c "
import plistlib
pl = {'ProgramArguments': ['env-wrapper.sh', '${SVC_ENV}', '/usr/local/bin/openclaw-gateway']}
with open('${PLIST_DIR}/ai.openclaw.gateway.plist', 'wb') as f:
    plistlib.dump(pl, f, fmt=plistlib.FMT_BINARY)
"
if run_script 0 env PODCAST_INTAKE_HOOK_SECRET=synthetic-fixture-secret \
     HOME="$WORK/home" \
     "$SCRIPT_UNDER_TEST" --remove acme-media podcast-intake-acme-media; then
  if grep -q "BEFORE_REMOVE=should-survive" "$SVC_ENV" \
     && ! grep -q "PODCAST_INTAKE_ROUTE_ID" "$SVC_ENV" \
     && ! printf '%s' "$OUT" | grep -q "service-env"; then
    pass "service-env: not invoked during --remove"
  else
    fail "service-env: invoked during --remove or modified the service-env file"
  fi
else
  fail "service-env remove guard (rc=$LAST_RC): $OUT"
fi

# --------------------------------------------------------------------------- #
# 18. Service-env: PODCAST_CLIENT_LOCATION_ID (the intake handler's hard
#     tenant check) is appended when SET, and its value never leaks to output.
# --------------------------------------------------------------------------- #
write_cfg '{"hooks":{"enabled":true,"allowedSessionKeyPrefixes":["hook:ghl:"],"allowedAgentIds":["main"]},"plugins":{"entries":{"webhooks":{"enabled":true,"config":{"routes":{}}}}}}'
rm -rf "$(dirname "$SVC_ENV")"
mkdir -p "$(dirname "$SVC_ENV")"
printf '%s\n' "MARKER=keep" > "$SVC_ENV"
if run_script 0 env PODCAST_INTAKE_HOOK_SECRET=synthetic-fixture-secret \
     PODCAST_CLIENT_LOCATION_ID=LOC0000000000000000abcd \
     HOME="$WORK/home" \
     "$SCRIPT_UNDER_TEST" --client-slug acme-media; then
  ok=0
  grep -q "^export PODCAST_CLIENT_LOCATION_ID=LOC0000000000000000abcd$" "$SVC_ENV" || ok=1
  grep -q "MARKER=keep" "$SVC_ENV" || ok=1
  # the location id is a tenant credential: never in the script's output
  if printf '%s' "$OUT" | grep -q "LOC0000000000000000abcd"; then ok=1; fi
  check "service-env: appends PODCAST_CLIENT_LOCATION_ID when SET (value not printed)" "$ok"
else
  fail "service-env tenant check injection run (rc=$LAST_RC): $OUT"
fi

# --------------------------------------------------------------------------- #
# 19. Service-env: PODCAST_CLIENT_LOCATION_ID absent is a skip, not a failure.
# --------------------------------------------------------------------------- #
rm -rf "$(dirname "$SVC_ENV")"
mkdir -p "$(dirname "$SVC_ENV")"
printf '%s\n' "MARKER=keep" > "$SVC_ENV"
write_cfg '{}'
if run_script 0 env -u PODCAST_CLIENT_LOCATION_ID \
     PODCAST_INTAKE_HOOK_SECRET=synthetic-fixture-secret \
     HOME="$WORK/home" \
     "$SCRIPT_UNDER_TEST" --client-slug acme-media; then
  ok=0
  if grep -q "PODCAST_CLIENT_LOCATION_ID=" "$SVC_ENV"; then ok=1; fi
  grep -q "MARKER=keep" "$SVC_ENV" || ok=1
  check "service-env: absent PODCAST_CLIENT_LOCATION_ID skipped, registration succeeds" "$ok"
else
  fail "service-env absent tenant check run (rc=$LAST_RC): $OUT"
fi

# --------------------------------------------------------------------------- #
# 20. Service-env: the REAL fleet plist shape resolves. On the fleet the
#     ProgramArguments are [/bin/sh, env-wrapper.sh, <env-file>, node,
#     index.js, gateway, --port, ...]; the env file is found by its *.env
#     suffix and the wrapper script is never touched.
# --------------------------------------------------------------------------- #
write_cfg '{}'
FLEET_ENV="$WORK/service-env/fleet-gateway.env"
FLEET_WRAPPER="$WORK/service-env/ai.openclaw.gateway-env-wrapper.sh"
rm -rf "$(dirname "$FLEET_ENV")"
mkdir -p "$(dirname "$FLEET_ENV")"
printf '%s\n' "#!/bin/sh" ". \"\$1\"" "exec \"\$@\"" > "$FLEET_WRAPPER"
chmod +x "$FLEET_WRAPPER"
printf '%s\n' "FLEET_MARKER=pre-existing" > "$FLEET_ENV"
WRAP_SUM_BEFORE="$(shasum "$FLEET_WRAPPER" | awk '{print $1}')"
rm -f "$PLIST_DIR/ai.openclaw.gateway.plist"
python3 -c "
import plistlib
pl = {'ProgramArguments': ['/bin/sh', '${FLEET_WRAPPER}', '${FLEET_ENV}',
                           '/usr/local/bin/node',
                           '/usr/local/lib/node_modules/openclaw/dist/index.js',
                           'gateway', '--port', '18789']}
with open('${PLIST_DIR}/ai.openclaw.gateway.plist', 'wb') as f:
    plistlib.dump(pl, f, fmt=plistlib.FMT_BINARY)
"
if run_script 0 env PODCAST_INTAKE_HOOK_SECRET=synthetic-fixture-secret \
     PODCAST_CLIENT_LOCATION_ID=LOC0000000000000000abcd \
     HOME="$WORK/home" \
     "$SCRIPT_UNDER_TEST" --client-slug acme-media; then
  ok=0
  grep -q "FLEET_MARKER=pre-existing" "$FLEET_ENV" || ok=1
  grep -q "^export PODCAST_INTAKE_HOOK_SECRET=synthetic-fixture-secret$" "$FLEET_ENV" || ok=1
  grep -q "^export PODCAST_INTAKE_ROUTE_ID=podcast-intake-acme-media$" "$FLEET_ENV" || ok=1
  WRAP_SUM_AFTER="$(shasum "$FLEET_WRAPPER" | awk '{print $1}')"
  [ "$WRAP_SUM_BEFORE" = "$WRAP_SUM_AFTER" ] || ok=1
  check "service-env: real fleet plist shape resolves; wrapper untouched" "$ok"
else
  fail "service-env fleet plist shape (rc=$LAST_RC): $OUT"
fi

# --------------------------------------------------------------------------- #
# 21. Service-env: heal on rerun. The route is already registered exactly
#     (config merge no-op), but the service-env file is missing the labels;
#     re-running the registrar appends them without rewriting the config or
#     adding a backup (the Leanne's-box state).
# --------------------------------------------------------------------------- #
rm -rf "$(dirname "$FLEET_ENV")"
mkdir -p "$(dirname "$FLEET_ENV")"
printf '%s\n' "HEAL_MARKER=reset" > "$FLEET_ENV"
BACKUPS_BEFORE="$(ls "$WORK" | grep -c 'bak-podcast-hook' || true)"
if run_script 0 env -u PODCAST_CLIENT_LOCATION_ID \
     PODCAST_INTAKE_HOOK_SECRET=synthetic-fixture-secret \
     HOME="$WORK/home" \
     "$SCRIPT_UNDER_TEST" --client-slug acme-media \
   && printf '%s' "$OUT" | grep -qi "no-op"; then
  ok=0
  grep -q "HEAL_MARKER=reset" "$FLEET_ENV" || ok=1
  grep -q "^export PODCAST_INTAKE_HOOK_SECRET=synthetic-fixture-secret$" "$FLEET_ENV" || ok=1
  grep -q "^export PODCAST_INTAKE_ROUTE_ID=podcast-intake-acme-media$" "$FLEET_ENV" || ok=1
  BACKUPS_AFTER="$(ls "$WORK" | grep -c 'bak-podcast-hook' || true)"
  [ "$BACKUPS_BEFORE" = "$BACKUPS_AFTER" ] || ok=1
  check "service-env: no-op rerun heals the missing service-env labels" "$ok"
else
  fail "service-env heal on rerun (rc=$LAST_RC): $OUT"
fi

# --------------------------------------------------------------------------- #
# Summary
# --------------------------------------------------------------------------- #
echo
echo "== register-podcast-hook.sh tests: $PASS passed, $FAIL failed =="
if [ "$FAIL" -eq 0 ]; then exit 0; fi
exit 1
