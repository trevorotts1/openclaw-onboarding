#!/usr/bin/env bash
# tests/unit/ghl-mcp-pm2-registration-mismatch.test.sh
#
# DEFECT 2 (proven live on a VPS box, 2026-08-04): `pm2 startOrReload`
# MERGES a regenerated ecosystem.config.js onto an app's EXISTING pm2
# registration. When the new file changes `script:`/`interpreter:` (e.g. to
# the generated `.ghl-mcp-launch.sh` with `interpreter: bash`), pm2 keeps the
# STALE `script: dist/main.js` and pairs it with the NEW interpreter — bash
# tries to execute compiled JavaScript as a shell script and crash-loops.
#
# THE FIX under test (the GHL-MCP-PM2-REGISTRATION-MISMATCH block):
# `_pm2_registration_mismatch <app> <want_script> <want_interp>` detects
# whether the LIVE pm2 registration (read via a real `pm2 jlist` parse — a
# fake pm2 stub on PATH here, real parsing logic) disagrees with what this
# run is about to write, so the caller can choose `pm2 delete` + `pm2 start`
# ONLY when needed, never unconditionally (an unconditional delete would
# reset uptime/restart-count history on every ordinary matching restart).
#
# BOTH DIRECTIONS proven:
#   - a genuine mismatch (stale dist/main.js + no interpreter, or any
#     interpreter/script disagreement) -> mismatch=YES (force delete+start)
#   - a matching registration, or no live app at all (fresh install) ->
#     mismatch=NO (safe to use startOrReload, preserving history)
#
# Extraction, not re-implementation: the GHL-MCP-PM2-REGISTRATION-MISMATCH
# block is sourced verbatim from the shipped script (same convention as
# tests/unit/ghl-mcp-env-credential-guard.test.sh). A hand-written copy of
# this logic could pass while the shipped file regressed. No real pm2 daemon
# is ever touched — `pm2` is a throwaway shell stub earlier on PATH.

set -uo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SELF_DIR/../.." && pwd)"
SRC="$REPO_ROOT/scripts/ghl-mcp-autostart.sh"

FAILURES=0
pass() { printf '  PASS  %s\n' "$*"; }
fail() { printf '  FAIL  %s\n' "$*" >&2; FAILURES=$((FAILURES+1)); }

echo "=== ghl-mcp-pm2-registration-mismatch.test.sh ==="
echo ""

[ -f "$SRC" ] || { echo "FATAL: $SRC not found"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "FATAL: python3 required"; exit 1; }

BLOCK="$(mktemp "${TMPDIR:-/tmp}/ghl-pm2-mismatch-block.XXXXXX")"
awk '/^# >>> GHL-MCP-PM2-REGISTRATION-MISMATCH-BEGIN/{f=1;next} /^# <<< GHL-MCP-PM2-REGISTRATION-MISMATCH-END/{f=0} f' \
  "$SRC" > "$BLOCK"
if [ ! -s "$BLOCK" ]; then
  echo "FATAL: the GHL-MCP-PM2-REGISTRATION-MISMATCH markers are missing from $SRC — the fix cannot be proven, failing closed."
  rm -f "$BLOCK"; exit 1
fi

for _needle in '_pm2_live_registration' '_pm2_registration_mismatch' 'pm2 jlist'; do
  grep -qF "$_needle" "$BLOCK" \
    || { echo "FATAL: extracted block no longer contains $_needle"; rm -f "$BLOCK"; exit 1; }
done
pass "(setup) extracted GHL-MCP-PM2-REGISTRATION-MISMATCH block, contains all load-bearing pieces"

# Prove the CALLER (start_service_vps) actually branches on the decision
# function rather than always calling startOrReload — a refactor that left
# the helper defined-but-unused would pass every case below for the wrong
# reason.
if grep -qF 'if _pm2_registration_mismatch ghl-community-mcp' "$SRC" \
   && grep -qF 'pm2 delete ghl-community-mcp' "$SRC" \
   && grep -qF 'pm2 startOrReload ecosystem.config.js' "$SRC"; then
  pass "(setup) start_service_vps() branches on _pm2_registration_mismatch: delete+start on mismatch, startOrReload otherwise"
else
  fail "(setup) start_service_vps() no longer calls _pm2_registration_mismatch to choose the pm2 start strategy"
fi

# ── Harness: a fake pm2 on PATH. `describe` reports existence; `jlist` emits
#    one record shaped however the case needs. No real pm2 daemon involved. ──
_make_fake_pm2() {  # _make_fake_pm2 <bindir> <script_or_""> <interp_or_"">
  local bindir="$1" script="$2" interp="$3"
  mkdir -p "$bindir"
  if [ -z "$script" ]; then
    # No live app at all — `describe` fails, `jlist` returns an empty array.
    cat > "$bindir/pm2" <<'EOF'
#!/usr/bin/env bash
case "$1" in
  describe) exit 1 ;;
  jlist) echo '[]' ;;
  *) exit 0 ;;
esac
EOF
  else
    cat > "$bindir/pm2" <<EOF
#!/usr/bin/env bash
case "\$1" in
  describe) exit 0 ;;
  jlist)
    cat <<JSONEOF
[{"name":"ghl-community-mcp","pm2_env":{"pm_exec_path":"${script}","exec_interpreter":"${interp}"}}]
JSONEOF
    ;;
  *) exit 0 ;;
esac
EOF
  fi
  chmod +x "$bindir/pm2"
}

# _case <desc> <live_script> <live_interp> <expect: mismatch|match>
_case() {
  local desc="$1" live_script="$2" live_interp="$3" expect="$4"
  local bindir; bindir="$(mktemp -d "${TMPDIR:-/tmp}/ghl-pm2-bin.XXXXXX")"
  _make_fake_pm2 "$bindir" "$live_script" "$live_interp"
  local out rc
  out="$(
    PATH="$bindir:$PATH" bash -c '
      . "'"$BLOCK"'"
      if _pm2_registration_mismatch ghl-community-mcp ".ghl-mcp-launch.sh" "bash"; then
        echo MISMATCH
      else
        echo MATCH
      fi
    ' 2>&1
  )"
  rc=$?
  rm -rf "$bindir"
  local got=""
  printf '%s' "$out" | grep -q '^MISMATCH$' && got="mismatch"
  printf '%s' "$out" | grep -q '^MATCH$' && got="match"
  if [ "$got" = "$expect" ]; then
    pass "$desc -> $got"
  else
    fail "$desc -> expected '$expect', got '${got:-neither}' (rc=$rc, output: $out)"
  fi
}

# ── THE DEFECT SIGNATURE: stale script, no interpreter override ─────────────
_case "live=dist/main.js interp=(none) [the pre-fix on-disk shape that crash-loops]" \
  "/data/mcp-servers/ghl-community-mcp/dist/main.js" "" "mismatch"

# ── the exact failure mode Trevor described: NEW interpreter (bash) paired
#    with the STALE script (dist/main.js) — startOrReload would keep this. ──
_case "live=dist/main.js interp=bash [half-migrated: bash paired with stale JS]" \
  "/data/mcp-servers/ghl-community-mcp/dist/main.js" "bash" "mismatch"

# ── a correctly-registered box: script + interpreter both already match. ────
_case "live=.ghl-mcp-launch.sh interp=bash [already correct]" \
  "/data/mcp-servers/ghl-community-mcp/.ghl-mcp-launch.sh" "bash" "match"

# ── interpreter alone disagrees (script correct, interpreter stale/wrong). ──
_case "live=.ghl-mcp-launch.sh interp=node [script right, interpreter wrong]" \
  "/data/mcp-servers/ghl-community-mcp/.ghl-mcp-launch.sh" "node" "mismatch"

# ── ANTI-VACUITY: no live app at all (fresh install) — must NOT report a
#    mismatch; there is nothing stale to collide with, and `startOrReload`
#    already falls through to `pm2 start` for a name pm2 has never seen. A
#    fix that reported "mismatch" here would force an unnecessary delete on
#    every single fresh install. ──────────────────────────────────────────
_case "no live app at all [fresh install]" "" "" "match"

rm -f "$BLOCK"

echo ""
echo "=== Result: $FAILURES failure(s) ==="
[ "$FAILURES" -eq 0 ] && exit 0 || exit 1
