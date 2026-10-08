#!/usr/bin/env bash
# Folded from .github/workflows/power-resilience-guard.yml (job "Power-outage survival regression guard"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Syntax-check every script in the blast radius
set -e
for f in \
  platform/mac/power-resilience/lib-power-resilience.sh \
  platform/mac/bootstrap.sh \
  platform/mac/tunnel-hardening/harden-mac-tunnel.sh \
  platform/mac/tunnel-hardening/rescue-tunnel-watchdog.sh \
  platform/mac/tunnel-hardening/install-rescue-tunnel-watchdog.sh \
  32-command-center-setup/scripts/setup-tunnel-daemon.sh \
  scripts/fix-power-resilience.sh \
  tests/unit/power-resilience-gate.test.sh; do
  echo "bash -n $f"
  bash -n "$f"
done
)
( # step: FileVault gate must FAIL CLOSED + pmset must be present
set -e
chmod +x tests/unit/power-resilience-gate.test.sh
bash tests/unit/power-resilience-gate.test.sh
)
( # step: Meta-check — the test must actually be able to FAIL (no vacuous green)
set -e
# Reintroduce the EXACT shipped bug (the gate returns 0 instead of 78 on
# a FileVault-ON box) and prove the suite goes red. A test that cannot
# fail is not a test — and a green-but-vacuous suite is precisely how
# this defect reached 11 client boxes.
cp platform/mac/power-resilience/lib-power-resilience.sh /tmp/lib.orig
python3 - <<'PY'
p = "platform/mac/power-resilience/lib-power-resilience.sh"
s = open(p).read()
needle = '    return "$PR_EX_CONFIG"'
assert needle in s, "gate return not found — update this meta-check"
s = s.replace(needle, "    return 0  # MUTATED: fail-open", 1)
open(p, "w").write(s)
PY
if bash tests/unit/power-resilience-gate.test.sh >/dev/null 2>&1; then
  echo "::error::VACUOUS TEST — the suite still passes with a fail-OPEN FileVault gate."
  cp /tmp/lib.orig platform/mac/power-resilience/lib-power-resilience.sh
  exit 1
fi
echo "OK: the suite correctly goes RED when the gate fails open."
cp /tmp/lib.orig platform/mac/power-resilience/lib-power-resilience.sh
)
( # step: No cleartext tunnel token may be rendered into any plist
set -e
# The rendered plists must never carry a bare `--token <jwt>` (visible in
# `ps` to ANY local user) — only `--token-file`.
if grep -rnE '<string>--token</string>' \
     32-command-center-setup/scripts/setup-tunnel-daemon.sh \
     platform/mac/power-resilience/lib-power-resilience.sh; then
  echo "::error::A plist template still passes a cleartext --token. Use --token-file (mode 600)."
  exit 1
fi
echo "OK: no cleartext --token in any plist template."
)
( # step: No hardcoded Homebrew path in a rendered plist (dead on Intel Macs)
set -e
if grep -rnE '<string>/opt/homebrew/bin/cloudflared</string>' \
     32-command-center-setup/scripts/setup-tunnel-daemon.sh; then
  echo "::error::cloudflared is hardcoded to /opt/homebrew — that path does not exist on an Intel Mac (exit 78 EX_CONFIG, forever). Resolve it with 'command -v cloudflared'."
  exit 1
fi
echo "OK: cloudflared is resolved, not hardcoded."
)
