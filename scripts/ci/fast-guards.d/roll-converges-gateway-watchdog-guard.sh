#!/usr/bin/env bash
# Folded from .github/workflows/roll-converges-gateway-watchdog-guard.yml (job "Fleet roll must converge the Mac gateway health watchdog"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Syntax-check every file in the blast radius
set -e
bash -n update-skills.sh
bash -n platform/mac/service-selfheal/install-service-remediate.sh
bash -n tests/unit/roll-converges-gateway-watchdog.test.sh
bash -n tests/unit/full-update-path-contract.test.sh
# These two are /bin/sh files. Check them with sh, not bash.
sh -n platform/mac/service-selfheal/gateway-health-watchdog.sh
sh -n platform/mac/service-selfheal/remediate.sh
)
( # step: The roll converges the watchdog, and the watchdog heals both dead states
set -e
bash tests/unit/roll-converges-gateway-watchdog.test.sh
)
( # step: The update-path contract still holds
set -e
bash tests/unit/full-update-path-contract.test.sh
)
( # step: Meta-check 1 - removing the converge from the roll must go RED
set -e
cp update-skills.sh /tmp/us.orig
python3 - <<'PY'
p = "update-skills.sh"
lines = open(p, encoding="utf-8").read().split("\n")
a = lines.index("  # ---- BEGIN gateway-watchdog converge ----")
b = lines.index("  # ---- END gateway-watchdog converge ----")
open(p, "w", encoding="utf-8").write("\n".join(lines[:a] + lines[b + 1:]))
PY
if bash tests/unit/roll-converges-gateway-watchdog.test.sh >/dev/null 2>&1; then
  echo "::error::VACUOUS TEST - the suite still passes with the converge block deleted from update-skills.sh."
  cp /tmp/us.orig update-skills.sh
  exit 1
fi
echo "OK: the suite goes RED when the roll stops converging the watchdog."
cp /tmp/us.orig update-skills.sh
)
( # step: Meta-check 2 - reverting the watchdog to kickstart-only must go RED
set -e
cp platform/mac/service-selfheal/gateway-health-watchdog.sh /tmp/wd.orig
python3 - <<'PY'
p = "platform/mac/service-selfheal/gateway-health-watchdog.sh"
s = open(p, encoding="utf-8").read()
needle = '      if launchctl print "gui/$(id -u)/$lbl" >/dev/null 2>&1; then'
assert needle in s, "booted-out branch not found - update this meta-check"
s = s.replace(needle, "      if true; then", 1)
open(p, "w", encoding="utf-8").write(s)
PY
if bash tests/unit/roll-converges-gateway-watchdog.test.sh >/dev/null 2>&1; then
  echo "::error::VACUOUS TEST - the suite still passes with a dead-and-booted-out gateway left unhealable."
  cp /tmp/wd.orig platform/mac/service-selfheal/gateway-health-watchdog.sh
  exit 1
fi
echo "OK: the suite goes RED when the booted-out bootstrap is removed."
cp /tmp/wd.orig platform/mac/service-selfheal/gateway-health-watchdog.sh
)
( # step: Meta-check 3 - dropping the migration-gate clear must go RED
set -e
cp platform/mac/service-selfheal/gateway-health-watchdog.sh /tmp/wd2.orig
python3 - <<'PY'
p = "platform/mac/service-selfheal/gateway-health-watchdog.sh"
s = open(p, encoding="utf-8").read()
needle = "  clear_session_store_migration_gate || true\n"
assert s.count(needle) == 1, "migration-gate call not found - update this meta-check"
open(p, "w", encoding="utf-8").write(s.replace(needle, "", 1))
PY
if bash tests/unit/roll-converges-gateway-watchdog.test.sh >/dev/null 2>&1; then
  echo "::error::VACUOUS TEST - the suite still passes with the 2026.9.x session-store gate never cleared."
  cp /tmp/wd2.orig platform/mac/service-selfheal/gateway-health-watchdog.sh
  exit 1
fi
echo "OK: the suite goes RED when the migration-gate clear is removed."
cp /tmp/wd2.orig platform/mac/service-selfheal/gateway-health-watchdog.sh
)
