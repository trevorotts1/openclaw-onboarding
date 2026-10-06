#!/usr/bin/env bash
# 69-archify/scripts/onboarding-smoke.sh
#
# ONBOARDING-NATIVE VERIFIER for Skill 69 (archify).
#
# Why this exists: the vendored `package.json` is byte-identical to upstream, so
# its npm scripts still reference the upstream MONOREPO root (`../scripts/*.mjs`)
# which is deliberately not vendored, and its generator/test scripts import
# upstream devDependencies that are intentionally not installed. None of those
# can verify this skill. This script can, using ONLY the shipped runtime.
#
# What it proves, in order (and it stops at the first failure):
#   1. `node` exists on PATH and is major version >= 18.
#   2. `bin/archify.mjs` exists and `doctor` exits 0 (whole vendored tree intact).
#   3. `validate <type> <example> --quality showcase --json` exits 0 AND the
#      receipt says "ok": true.
#   4. `render <type> <example> <tmp>/smoke.html` exits 0 AND the produced HTML
#      exists and is non-empty.
#   5. The temporary directory is removed.
#
# Guarantees:
#   * The skill root is derived from THIS script's location, so the script works
#     from any working directory and from any symlink-free absolute path.
#   * It writes nothing inside the skill tree: the render target is a temp dir.
#   * Exit 0 = pass (prints ONBOARDING SMOKE PASS).
#     Exit 1 = fail (prints a SMOKE FAIL line naming the failed step).
#     Exit 2 = the script could not resolve its own directory / the skill root.
#
# Usage:
#   bash scripts/onboarding-smoke.sh
#   bash /abs/path/to/69-archify/scripts/onboarding-smoke.sh   # from anywhere
#
# v1.0.0 (Skill 69 onboarding, archify upstream 2.17.0 @ 851b279f)

set -uo pipefail

# ── Resolve the skill root from the script's own location (never hardcoded) ───
SCRIPT_PATH="${BASH_SOURCE[0]}"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" >/dev/null 2>&1 && pwd)" || {
  echo "SMOKE FAIL: cannot resolve this script's directory from: $SCRIPT_PATH" >&2
  exit 2
}
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." >/dev/null 2>&1 && pwd)" || {
  echo "SMOKE FAIL: cannot resolve the skill root (parent of $SCRIPT_DIR)" >&2
  exit 2
}

CLI="bin/archify.mjs"
EXAMPLE_TYPE="architecture"
EXAMPLE_JSON="examples/web-app.architecture.json"
SKILL_VERSION="$(cat "$SKILL_ROOT/skill-version.txt" 2>/dev/null || echo 'unknown')"

TMP_DIR=""
STEP="startup"

# Invoked indirectly: registered below with `trap cleanup EXIT INT TERM`.
# shellcheck disable=SC2329
cleanup() {
  if [ -n "$TMP_DIR" ] && [ -d "$TMP_DIR" ]; then
    rm -rf "$TMP_DIR"
  fi
}
trap cleanup EXIT INT TERM

fail() {
  echo "" >&2
  echo "SMOKE FAIL [step: $STEP] $*" >&2
  echo "  skill root : $SKILL_ROOT" >&2
  echo "  hint       : run 'node $CLI doctor' from the skill root for the full receipt" >&2
  exit 1
}

say() { printf '%s\n' "$*"; }

say "=== archify (69) onboarding smoke test ==="
say "  skill root : $SKILL_ROOT"
say "  version    : $SKILL_VERSION"

# ── Step 1: Node >= 18 ───────────────────────────────────────────────────────
STEP="node-prerequisite"
if ! command -v node >/dev/null 2>&1; then
  fail "node is not on PATH. archify is a Node.js CLI and requires Node.js >= 18."
fi
if ! node -e 'const m=Number(process.versions.node.split(".")[0]); process.exit(m>=18?0:1)' >/dev/null 2>&1; then
  fail "node $(node --version 2>/dev/null || echo '(unknown)') is too old. Node.js >= 18 is required."
fi
say "  [ok] node $(node --version)"

# ── Step 2: the shipped tree is present ──────────────────────────────────────
STEP="tree-presence"
[ -f "$SKILL_ROOT/$CLI" ] || fail "missing CLI entry point: $SKILL_ROOT/$CLI"
[ -f "$SKILL_ROOT/$EXAMPLE_JSON" ] || fail "missing bundled example: $SKILL_ROOT/$EXAMPLE_JSON"
say "  [ok] $CLI and $EXAMPLE_JSON present"

cd "$SKILL_ROOT" || fail "cannot cd into the skill root"

# ── Step 3: doctor ───────────────────────────────────────────────────────────
STEP="doctor"
DOCTOR_OUT="$(node "$CLI" doctor 2>&1)"
DOCTOR_RC=$?
if [ "$DOCTOR_RC" -ne 0 ]; then
  printf '%s\n' "$DOCTOR_OUT" | tail -20 >&2
  fail "'node $CLI doctor' exited $DOCTOR_RC (expected 0). The vendored tree is incomplete."
fi
OK_COUNT="$(printf '%s\n' "$DOCTOR_OUT" | grep -c '^\[ok\]')"
if [ "$OK_COUNT" -lt 15 ]; then
  printf '%s\n' "$DOCTOR_OUT" | tail -20 >&2
  fail "'doctor' reported $OK_COUNT [ok] subsystem(s); expected 15. Re-vendor, do not patch."
fi
say "  [ok] doctor: $OK_COUNT subsystems ok, exit 0"

# ── Step 4: validate the bundled example ─────────────────────────────────────
STEP="validate"
VALIDATE_OUT="$(node "$CLI" validate "$EXAMPLE_TYPE" "$EXAMPLE_JSON" --quality showcase --json 2>&1)"
VALIDATE_RC=$?
if [ "$VALIDATE_RC" -ne 0 ]; then
  printf '%s\n' "$VALIDATE_OUT" | tail -20 >&2
  fail "validate exited $VALIDATE_RC (expected 0) for $EXAMPLE_TYPE $EXAMPLE_JSON"
fi
if ! printf '%s' "$VALIDATE_OUT" | grep -Eq '"ok"[[:space:]]*:[[:space:]]*true'; then
  printf '%s\n' "$VALIDATE_OUT" | tail -20 >&2
  fail "validate exited 0 but the receipt did not report \"ok\": true"
fi
say "  [ok] validate: ok=true (showcase), exit 0"

# ── Step 5: render to a temp file and prove a real artifact came out ─────────
STEP="render"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/archify-onboarding-smoke.XXXXXX")" \
  || fail "could not create a temporary directory"
OUT_HTML="$TMP_DIR/smoke.html"

RENDER_OUT="$(node "$CLI" render "$EXAMPLE_TYPE" "$EXAMPLE_JSON" "$OUT_HTML" 2>&1)"
RENDER_RC=$?
if [ "$RENDER_RC" -ne 0 ]; then
  printf '%s\n' "$RENDER_OUT" | tail -20 >&2
  fail "render exited $RENDER_RC (expected 0)"
fi
[ -f "$OUT_HTML" ] || fail "render exited 0 but produced no file at $OUT_HTML"
BYTES="$(wc -c < "$OUT_HTML" | tr -d '[:space:]')"
if [ -z "$BYTES" ] || [ "$BYTES" -eq 0 ]; then
  fail "render produced a 0-byte HTML artifact at $OUT_HTML"
fi
say "  [ok] render: $BYTES bytes standalone HTML, exit 0"

# ── Step 6: cleanup + verdict ────────────────────────────────────────────────
STEP="cleanup"
rm -rf "$TMP_DIR" || say "  [warn] could not remove temp dir: $TMP_DIR"
if [ -d "$TMP_DIR" ]; then
  fail "temporary directory survived cleanup: $TMP_DIR"
fi
TMP_DIR=""
say "  [ok] temp artifacts removed"

say ""
say "ONBOARDING SMOKE PASS: archify (69) $SKILL_VERSION is operational (doctor + validate + render all green)."
exit 0
