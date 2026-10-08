#!/usr/bin/env bash
# Folded from .github/workflows/checker-false-fail-guards.yml (job "Checker false-fail regression suites (Skills 31, 44, 35, 05, 10, 08)"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Syntax-check the checkers and their suites
set -e -o pipefail
set -euo pipefail
bash -n 31-upgraded-memory-system/qc-upgraded-memory-system.sh
bash -n 44-convert-and-flow-operator/qc-convert-and-flow.sh
bash -n tests/unit/qc-upgraded-memory-key-resolution.test.sh
bash -n tests/unit/qc-convert-and-flow-layout-and-path.test.sh
bash -n 35-social-media-planner/qc-skill35.sh
bash -n 05-ghl-setup/qc-ghl-setup.sh
bash -n tests/unit/qc-skill35-installed-layout.test.sh
bash -n tests/unit/qc-ghl-setup-legacy-alias-probe.test.sh
bash -n 10-github-setup/qc-github-setup.sh
bash -n 08-vercel-setup/qc-vercel-setup.sh
bash -n tests/unit/qc-sovereign-lock-forbidden-cli.test.sh
python3 -m py_compile docs/tools/check_lattice_citation.py
echo "syntax OK"
)
( # step: Skill 31 — Layer 4 credential resolution regression suite
set -e -o pipefail
bash tests/unit/qc-upgraded-memory-key-resolution.test.sh
)
( # step: Skill 44 — installed-layout + bare-PATH regression suite
set -e
export OPENCLAW_PLATFORM='mac'
bash tests/unit/qc-convert-and-flow-layout-and-path.test.sh
)
( # step: Skill 35 — installed-copy layout regression suite (T2-02)
set -e -o pipefail
bash tests/unit/qc-skill35-installed-layout.test.sh
)
( # step: Skill 05 — resolved-PIT reaches the probes regression suite (T2-03)
set -e -o pipefail
bash tests/unit/qc-ghl-setup-legacy-alias-probe.test.sh
)
( # step: Skills 08 and 10 — sovereign-lock forbidden-CLI regression suite (T2-19)
set -e -o pipefail
bash tests/unit/qc-sovereign-lock-forbidden-cli.test.sh
)
( # step: Assert neither gate re-requires the CLI its own skill forbids
set -e -o pipefail
set -euo pipefail
# Belt-and-suspenders on the sovereign lock. The behavioural proof is
# the suite above; this catches a re-introduction at review time.
if grep -qE '^[[:space:]]*assert .*command -v gh' 10-github-setup/qc-github-setup.sh \
   || grep -qE '^[[:space:]]*assert .*gh auth status' 10-github-setup/qc-github-setup.sh; then
  echo "FAIL: qc-github-setup.sh hard-asserts the GitHub CLI, which SKILL.md's SOVEREIGN lock forbids." >&2
  exit 1
fi
if grep -qE '^[[:space:]]*assert .*command -v vercel' 08-vercel-setup/qc-vercel-setup.sh; then
  echo "FAIL: qc-vercel-setup.sh hard-asserts the Vercel CLI, which SKILL.md's SOVEREIGN lock forbids." >&2
  exit 1
fi
echo "PASS: neither install gate requires a CLI its own sovereign lock forbids."
)
( # step: Assert the absent-checker path is a SKIP, never a silent pass
set -e -o pipefail
set -euo pipefail
# Belt-and-suspenders on the governing rule: a skipped check must be
# visibly reported as skipped and must never be counted as a pass.
if ! grep -q 'SKIP: GK-27 lattice citation tripwire' 44-convert-and-flow-operator/qc-convert-and-flow.sh; then
  echo "FAIL: the visible SKIP for an absent lattice checker was removed." >&2
  exit 1
fi
if grep -qE 'assert .*check_lattice_citation\.py' 44-convert-and-flow-operator/qc-convert-and-flow.sh \
   && ! grep -q 'if \[ -f "\$LATTICE_CHECKER" \]' 44-convert-and-flow-operator/qc-convert-and-flow.sh; then
  echo "FAIL: the lattice checker is invoked without a presence guard again." >&2
  exit 1
fi
if ! grep -q 'SKIP: GK-27 lattice citation tripwire' 35-social-media-planner/qc-skill35.sh; then
  echo "FAIL: Skill 35's visible SKIP for an absent lattice checker was removed." >&2
  exit 1
fi
if grep -qE 'assert .*check_lattice_citation\.py' 35-social-media-planner/qc-skill35.sh \
   && ! grep -q 'if \[ -f "\$LATTICE_CHECKER" \]' 35-social-media-planner/qc-skill35.sh; then
  echo "FAIL: Skill 35 invokes the lattice checker without a presence guard again." >&2
  exit 1
fi
# The resolved PIT must be folded into the variable the probes send.
if ! grep -q 'GOHIGHLEVEL_API_KEY="\$RESOLVED_PIT"' 05-ghl-setup/qc-ghl-setup.sh; then
  echo "FAIL: the resolved PIT is no longer normalised into GOHIGHLEVEL_API_KEY (T2-03 regressed)." >&2
  exit 1
fi
echo "PASS: absent lattice checkers remain visible SKIPs; present checkers remain hard asserts; resolved PIT still reaches the probes."
)
