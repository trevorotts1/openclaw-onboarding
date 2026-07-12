#!/usr/bin/env bash
# pack-agent-browser-skill.test.sh — P3-06 step (c)1 regression test.
#
# Proves:
#   1. FAIL-FIRST: a fixture copy of the ORIGINAL (pre-fix) hand-packaged
#      agent-browser.skill -- captured from origin/main before this unit's
#      regeneration -- FAILS `pack-agent-browser-skill.sh --check` and names
#      the exact stale files (INSTALL.md, CORE_UPDATES.md). This is the 2.1
#      "test that would fail against the pre-fix tree" proof, self-contained
#      (no network/git-history dependency at test time).
#   2. `--check` PASSES against the live regenerated archive in this repo.
#   3. Two independent regenerations from identical source content produce a
#      BYTE-IDENTICAL archive (deterministic packer, no --check flakiness).
#   4. Planting a one-byte drift into a scratch copy's INSTALL.md and
#      rebuilding into a throwaway archive, then --check against the CHANGED
#      source but the OLD archive, is caught and named.
#   5. The regenerated archive's INSTALL.md carries all four hardening
#      sections the pre-fix archive lacked (N24, --headed false, the
#      guaranteed-close trap, GATEWAY RESTART PROTOCOL).
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && cd .. && pwd)"
PACKER="$SKILL_DIR/scripts/pack-agent-browser-skill.sh"

PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

echo "=== pack-agent-browser-skill.test.sh (P3-06) ==="
[[ -f "$PACKER" ]] || { echo "FAIL: packer not found: $PACKER"; exit 1; }

WORK="$(mktemp -d)"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

# ── (1) FAIL-FIRST: reconstruct the pre-fix hand-packaged archive as a fixture,
#        and prove --check fails against it, naming the stale files. This is
#        the archive AS CLONED from origin/main before P3-06 regenerated it:
#        it ships a STALE INSTALL.md (pre-v1.5.0-hardening text, no N24, no
#        --headed false, no guaranteed-close trap, no Lifecycle hygiene, no
#        GATEWAY RESTART PROTOCOL) and a STALE CORE_UPDATES.md, while SKILL.md
#        and CHANGELOG.md were already in sync.
PRE_FIX="$WORK/pre-fix"
mkdir -p "$PRE_FIX/agent-browser"
cat > "$PRE_FIX/agent-browser/SKILL.md" <<'EOF'
---
name: agent-browser
description: Install and use Vercel's agent-browser CLI for precise, ref-based browser automation. This is the preferred browser automation tool for OpenClaw onboarding and setup workflows.
---

# Agent Browser (Vercel) Skill

## What This Does

This skill ensures **agent-browser** is installed and usable.

agent-browser is our **preferred** browser automation tool because it:
- Produces accessibility snapshots with stable element refs (@e1, @e2, etc.)
- Lets the agent click/fill by ref for high-precision automation
- Is easier to operate reliably than ad-hoc browser clicking

## Where The Real Documentation Lives

This onboarding package includes a lightweight wrapper.

The full operational skill docs live on the machine at:
- `~/clawd/skills/agent-browser/SKILL.md`

If that path exists, treat it as the source of truth.
EOF
cat > "$PRE_FIX/agent-browser/CHANGELOG.md" <<'EOF'
# Changelog - Agent Browser (Vercel)

All notable changes to this skill wrapper are documented here.

---

## [v1.5.0] - March 7, 2026

### Changed
- Converted INSTALL.md to agent-executable, autonomous execution format.
- Ensured TYP guardrails are present: MANDATORY TYP CHECK, CONFLICT RULE, and TYP file storage instructions.
- Added wrapper skill to ensure agent-browser is installed and available as the preferred browser automation tool.
EOF
cat > "$PRE_FIX/agent-browser/CORE_UPDATES.md" <<'EOF'
# CORE_UPDATES.md - Agent Browser (Vercel)

## Purpose

This skill is a dependency installer and does not require any core file changes.
EOF
# Minimal pre-hardening INSTALL.md (no N24 / no --headed false / no trap /
# no Lifecycle hygiene / no GATEWAY RESTART PROTOCOL) -- a faithful stand-in
# for the stale archive content confirmed by direct diff against origin/main.
cat > "$PRE_FIX/agent-browser/INSTALL.md" <<'EOF'
# INSTALL.md - Agent Browser (Vercel)

## Goal

Ensure `agent-browser` is installed and available as the primary browser automation tool.

## Step 4 - Smoke test a simple browser session

Run:
```bash
agent-browser open https://example.com
agent-browser snapshot -i
agent-browser close
```

If the snapshot shows interactive elements with refs like `@e1`, `@e2`, installation is good.
EOF
( cd "$PRE_FIX" && zip -X -q -r pre-fix.skill agent-browser )

# A scratch "source dir" mirroring the CURRENT (post-fix) on-disk docs, which
# do carry the hardening. --check compares the fixture archive above against
# THIS dir, so it reproduces exactly the drift a real --check would have hit
# against origin/main before the archive was regenerated.
CURRENT_SRC="$WORK/current-src"
mkdir -p "$CURRENT_SRC"
for doc in INSTALL.md SKILL.md CHANGELOG.md CORE_UPDATES.md; do
  cp "$SKILL_DIR/$doc" "$CURRENT_SRC/$doc"
done

source "$SKILL_DIR/scripts/lib-archive-diff.sh"
PRE_FIX_DRIFT="$(agent_browser_archive_diff "$PRE_FIX/pre-fix.skill" "$CURRENT_SRC")"
if echo "$PRE_FIX_DRIFT" | grep -q "^INSTALL.md$" && echo "$PRE_FIX_DRIFT" | grep -q "^CORE_UPDATES.md$"; then
  pass "fail-first: the pre-fix hand-packaged archive fixture is caught as STALE, naming INSTALL.md and CORE_UPDATES.md (drift: $(echo "$PRE_FIX_DRIFT" | tr '\n' ',')"
else
  fail "expected pre-fix fixture archive to drift on INSTALL.md + CORE_UPDATES.md; got: $PRE_FIX_DRIFT"
fi

# ── (2) --check PASSES against THIS repo's live (regenerated) archive ────────
if bash "$PACKER" --check >/tmp/p306-check-out.$$ 2>&1; then
  pass "--check PASSES against the live regenerated agent-browser.skill in this repo"
else
  fail "--check FAILED against the live repo archive (should be in sync post-regeneration): $(cat /tmp/p306-check-out.$$)"
fi
rm -f /tmp/p306-check-out.$$

# ── (3) Deterministic rebuild: two regenerations of identical content match ──
OUT1="$WORK/out1.skill"
OUT2="$WORK/out2.skill"
bash "$PACKER" --out "$OUT1" >/dev/null
sleep 3  # cross a >2s wall-clock boundary to prove normalization holds even
         # when the live build-time second (and the live build-time minute,
         # on a slow box) changes between regenerations -- not a 1-tick fluke
bash "$PACKER" --out "$OUT2" >/dev/null
if cmp -s "$OUT1" "$OUT2"; then
  pass "two independent regenerations of identical source content are byte-identical (deterministic packer)"
else
  fail "two regenerations of identical content produced DIFFERENT archive bytes -- --check would be flaky"
fi

# ── (4) Plant a one-byte drift; prove it's caught and named ──────────────────
DRIFTED_SRC="$WORK/drifted-src"
mkdir -p "$DRIFTED_SRC"
cp "$SKILL_DIR"/INSTALL.md "$SKILL_DIR"/SKILL.md "$SKILL_DIR"/CHANGELOG.md "$SKILL_DIR"/CORE_UPDATES.md "$DRIFTED_SRC/"
# One-byte drift: flip a single character deep in INSTALL.md.
python3 - "$DRIFTED_SRC/INSTALL.md" <<'PY'
import sys
p = sys.argv[1]
data = open(p, "rb").read()
i = len(data) // 2
b = bytearray(data)
b[i] = (b[i] + 1) % 256
open(p, "wb").write(bytes(b))
PY
DRIFT_ONE="$(agent_browser_archive_diff "$OUT1" "$DRIFTED_SRC")"
if [[ "$DRIFT_ONE" == "INSTALL.md" ]]; then
  pass "one-byte drift in INSTALL.md is caught by the archive-diff gate, naming exactly INSTALL.md"
else
  fail "expected a one-byte drift to be reported as exactly 'INSTALL.md'; got: $DRIFT_ONE"
fi

# ── (5) Regenerated archive carries all four hardening sections ──────────────
VERIFY_DIR="$WORK/verify-extract"
mkdir -p "$VERIFY_DIR"
unzip -o -q "$SKILL_DIR/agent-browser.skill" -d "$VERIFY_DIR"
MISSING=""
for sig in "N24" "headed false" "trap 'agent-browser close' EXIT" "GATEWAY RESTART PROTOCOL"; do
  grep -q -- "$sig" "$VERIFY_DIR/agent-browser/INSTALL.md" 2>/dev/null || MISSING="$MISSING [$sig]"
done
if [[ -z "$MISSING" ]]; then
  pass "regenerated archive's INSTALL.md contains all four hardening sections (N24, --headed false, guaranteed-close trap, GATEWAY RESTART PROTOCOL)"
else
  fail "regenerated archive is missing hardening section(s):$MISSING"
fi

echo ""
echo "================================================="
echo "Results: $PASS passed, $FAIL failed"
echo "================================================="
if [[ "$FAIL" -eq 0 ]]; then
  echo "ALL TESTS PASSED"
  exit 0
else
  echo "TESTS FAILED"
  exit 1
fi
