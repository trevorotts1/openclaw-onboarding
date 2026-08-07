#!/usr/bin/env bash
# tests/unit/ghl-mcp-runtime-stop-exit-codes.test.sh
#
# DEFECT 3 (proven live on a VPS pilot box, 2026-08-04):
# scripts/ghl-mcp-assert-runtime.sh's `_GHL_FILTER_PM2_RECORD` embedded Python
# read `env.get("stop_exit_codes") or []`. pm2 v7.0.1 stores a single-element
# stop_exit_codes as the BARE SCALAR 0 (not the list [0]). Python's `or []`
# treats the falsy int 0 as absent, so a CORRECTLY configured box reported
# `stop_exit_codes='<unset>'` and FATAL-failed check "pm2 stop_exit_codes
# includes 0" -- on every pm2 box in wave 2, since this is exactly how pm2
# writes a single-code list. Verified live: an isolated disposable pm2 test
# app (exits 0, autorestart:true) was NOT restarted -- restart_time stayed 0
# for 14+ seconds -- so crash-only semantics genuinely worked; only the
# checker was wrong.
#
# TWO LAYERS OF PROOF:
#   PART A -- the embedded Python filter in ISOLATION, fed each shape pm2 (or
#             a hand-edited ecosystem file) might actually produce: bare
#             scalar 0, "0" string, list [0], list [0,1], list with no 0,
#             and genuinely absent. Fast, hermetic, no pm2 binary needed.
#   PART B -- the REAL gate script, end to end, against a SIMULATED VPS+pm2
#             box (a fake `pm2` on PATH, GHL_MCP_PLATFORM_OVERRIDE=vps -- the
#             new test hook this fix adds, matching the file's existing
#             GHL_MCP_DIR/GHL_MCP_PLIST override convention). Proves the
#             DOWNSTREAM verdict: a correctly-configured box now PASSES, and a
#             genuinely misconfigured box (no 0 in stop_exit_codes) still
#             FAILS -- the anti-vacuity control that proves this fix did not
#             just make the check unconditionally pass.
#
# Isolated: SIM_PORT=18765 (never the real 8765), a temp PATH-prepended pm2
# stub (no real pm2 daemon touched), MCP dir/log dir/openclaw.json/pin all
# redirected via the script's documented override env vars.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GATE_SRC="$REPO_ROOT/scripts/ghl-mcp-assert-runtime.sh"
PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== ghl-mcp-runtime-stop-exit-codes.test.sh ==="
echo ""

[ -f "$GATE_SRC" ] || { echo "  FAIL: gate not found at $GATE_SRC"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "  FAIL: python3 required"; exit 1; }

# ── PART A: the embedded filter, in isolation ────────────────────────────────
# Extract the single-quoted _GHL_FILTER_PM2_RECORD='...' Python body verbatim
# so this test always exercises the ACTUAL shipped snippet, never a copy that
# could drift from it.
SNIPPET="$(awk '
  /^_GHL_FILTER_PM2_RECORD=.$/ { grab=1; next }
  grab && /^.$/ { exit }
  grab { print }
' "$GATE_SRC")"

if [ -z "$SNIPPET" ]; then
  fail "(setup) could not extract _GHL_FILTER_PM2_RECORD from $GATE_SRC — anchor drifted"
else
  pass "(setup) extracted _GHL_FILTER_PM2_RECORD ($(printf '%s' "$SNIPPET" | wc -l | tr -d ' ') lines)"
fi

# _filter_case <json> <expected __stop_exit_codes__ value> <description>
_filter_case() {
  local json="$1" expect="$2" desc="$3" out got
  out="$(printf '%s' "$json" | python3 -c "$SNIPPET" 2>&1)"
  got="$(printf '%s\n' "$out" | sed -n 's/^__stop_exit_codes__=//p')"
  if [ "$got" = "$expect" ]; then
    pass "(A) $desc -> __stop_exit_codes__='$got'"
  else
    fail "(A) $desc -> expected '__stop_exit_codes__=$expect', got '__stop_exit_codes__=$got' (full output: $out)"
  fi
}

# The exact pm2 v7.0.1 shape that broke every correctly-configured box.
_filter_case '[{"name":"ghl-community-mcp","pm2_env":{"stop_exit_codes":0,"pm_exec_path":"x"}}]' \
  "0" "bare scalar 0 (pm2 v7.0.1's actual on-disk shape)"

# Scalar as a JSON string (some pm2/ecosystem-loader paths stringify).
_filter_case '[{"name":"ghl-community-mcp","pm2_env":{"stop_exit_codes":"0","pm_exec_path":"x"}}]' \
  "0" "scalar string \"0\""

# The list shape the OLD code assumed was the only valid one.
_filter_case '[{"name":"ghl-community-mcp","pm2_env":{"stop_exit_codes":[0],"pm_exec_path":"x"}}]' \
  "0" "list [0] (the shape the old code assumed exclusively)"

# A multi-element list including 0.
_filter_case '[{"name":"ghl-community-mcp","pm2_env":{"stop_exit_codes":[0,1],"pm_exec_path":"x"}}]' \
  "0,1" "list [0,1]"

# Genuinely absent (key not present at all) — must stay empty. Anti-vacuity:
# a fix that always reports "0" no matter what would pass every case above for
# the wrong reason; this proves absence is still detected as absence.
_filter_case '[{"name":"ghl-community-mcp","pm2_env":{"pm_exec_path":"x"}}]' \
  "" "genuinely absent (key not present) — must stay empty, not '0'"

# Explicit JSON null — also absent, not a stringified "None".
_filter_case '[{"name":"ghl-community-mcp","pm2_env":{"stop_exit_codes":null,"pm_exec_path":"x"}}]' \
  "" "explicit JSON null — must stay empty, never the literal 'None'"

# A misconfigured box: stop_exit_codes present but does NOT include 0. Must
# report the real value (not empty, not silently coerced to include 0).
_filter_case '[{"name":"ghl-community-mcp","pm2_env":{"stop_exit_codes":[1,2],"pm_exec_path":"x"}}]' \
  "1,2" "list without 0 — must report the true (bad) value, not swallow it"

echo ""

# ── PART B: the REAL gate, end to end, against a simulated VPS+pm2 box ───────
if ! command -v python3 >/dev/null 2>&1; then
  echo "  SKIP: part B requires python3"
else
  SIM_PORT=18765
  SIM_COMMIT="bfc2bbe15a4090b82351593b6ca52eed7a8dbbe3"

  # _make_vps_box <stop_exit_codes_json_fragment> -> echoes the sandbox root
  _make_vps_box() {
    local sec_frag="$1" tmp
    tmp="$(mktemp -d)"
    mkdir -p "$tmp/bin" "$tmp/scripts" "$tmp/config" "$tmp/mcp" "$tmp/logs"
    cp "$GATE_SRC" "$tmp/scripts/ghl-mcp-assert-runtime.sh"

    cat > "$tmp/config/ghl-mcp-pin.env" <<EOF
GHL_MCP_VETTED_COMMIT="$SIM_COMMIT"
GHL_MCP_TOOL_PROFILE="curated"
GHL_MCP_PORT="$SIM_PORT"
GHL_MCP_EXPECT_MIN_TOOLS="1"
GHL_MCP_EXPECT_MAX_TOOLS="200"
GHL_MCP_LOG_MAX_BYTES="10485760"
GHL_MCP_PIN_VETTED_VERDICT="CLEAN"
EOF

    : > "$tmp/mcp/.ghl-mcp-launch.sh"
    printf '{\n  "commit": "%s",\n  "profile": "curated"\n}\n' "$SIM_COMMIT" > "$tmp/mcp/.ghl-mcp-build.json"
    printf '{"mcp":{"servers":{"ghl-mcp":{}}}}\n' > "$tmp/openclaw.json"

    # A fake pm2 on PATH. `describe` reports the app exists (so _HAVE_PM2=1).
    # `jlist` emits ONE record for ghl-community-mcp, script pinned to the
    # crash-only launcher, profile/ports matching the pin, and
    # stop_exit_codes set to whatever shape this case is proving.
    cat > "$tmp/bin/pm2" <<PM2EOF
#!/usr/bin/env bash
case "\$1" in
  describe) exit 0 ;;
  jlist)
    cat <<JSONEOF
[{"name":"ghl-community-mcp","pm2_env":{"pm_exec_path":"$tmp/mcp/.ghl-mcp-launch.sh","GHL_TOOL_PROFILE":"curated","PORT":"$SIM_PORT","MCP_SERVER_PORT":"$SIM_PORT","GHL_MCP_LOG_DIR":"$tmp/logs"${sec_frag}}}]
JSONEOF
    ;;
  *) exit 0 ;;
esac
PM2EOF
    chmod +x "$tmp/bin/pm2"
    printf '%s' "$tmp"
  }

  _run_vps_gate() {  # <box> -> "<rc>|<output>"
    local box="$1" out rc=0
    out="$(PATH="$box/bin:$PATH" \
           GHL_MCP_PLATFORM_OVERRIDE=vps \
           GHL_MCP_DIR="$box/mcp" \
           GHL_MCP_LOG_DIR_OVERRIDE="$box/logs" \
           GHL_MCP_OC_JSON="$box/openclaw.json" \
           GHL_MCP_PLIST="$box/nonexistent.plist" \
           GHL_MCP_PROBE_PLIST="$box/nonexistent-probe.plist" \
           GHL_MCP_SYSTEMD_UNIT="$box/nonexistent.service" \
           bash "$box/scripts/ghl-mcp-assert-runtime.sh" 2>&1)" || rc=$?
    printf '%s|%s' "$rc" "$out"
  }

  # (B1) DEFECT SIGNATURE: bare scalar 0 — the exact pm2 v7.0.1 on-disk shape.
  # The one FATAL that must be ABSENT is the stop_exit_codes one. Other checks
  # (build stamp match, profile, ports, log dir) are all correct in this
  # fixture, but check 11 (periodic probe / cron) has nothing to find in this
  # sandbox, so it is expected to warn/fail independently of this defect —
  # this test greps for the SPECIFIC stop_exit_codes line rather than
  # asserting overall rc=0, so it stays pinned to defect 3 alone.
  BOX="$(_make_vps_box ',"stop_exit_codes":0')"
  RES="$(_run_vps_gate "$BOX")"; OUT="${RES#*|}"
  if printf '%s' "$OUT" | grep -qF 'FAIL  pm2 stop_exit_codes'; then
    fail "(B1) bare scalar stop_exit_codes:0 (pm2 v7.0.1 shape) still reports a FATAL — the defect is NOT fixed. Line:"
    printf '%s\n' "$OUT" | grep -F 'stop_exit_codes' | sed 's/^/        /'
  elif printf '%s' "$OUT" | grep -qF 'PASS  pm2 stop_exit_codes includes 0'; then
    pass "(B1) bare scalar stop_exit_codes:0 (pm2 v7.0.1 shape) PASSES through the real gate — the correctly-configured box is no longer a false FATAL"
  else
    fail "(B1) neither the PASS nor the FAIL line for stop_exit_codes appeared — output shape drifted. Output:"
    printf '%s\n' "$OUT" | sed 's/^/        /'
  fi
  rm -rf "$BOX"

  # (B2) ANTI-VACUITY CONTROL: a genuinely misconfigured box (stop_exit_codes
  # present but does NOT include 0) must still FATAL. A fix that stopped
  # detecting the real defect would pass B1 and be worthless.
  BOX="$(_make_vps_box ',"stop_exit_codes":[1,2]')"
  RES="$(_run_vps_gate "$BOX")"; OUT="${RES#*|}"
  if printf '%s' "$OUT" | grep -qF 'FAIL  pm2 stop_exit_codes'; then
    pass "(B2) stop_exit_codes=[1,2] (genuinely wrong — no 0) still correctly FAILS (anti-vacuity control)"
  else
    fail "(B2) stop_exit_codes=[1,2] did NOT fail — the fix over-corrected and now accepts a genuinely broken box. Output:"
    printf '%s\n' "$OUT" | sed 's/^/        /'
  fi
  rm -rf "$BOX"

  # (B3) ANTI-VACUITY CONTROL: stop_exit_codes genuinely absent must still
  # FATAL (not silently treated as "0 present").
  BOX="$(_make_vps_box '')"
  RES="$(_run_vps_gate "$BOX")"; OUT="${RES#*|}"
  if printf '%s' "$OUT" | grep -qF 'FAIL  pm2 stop_exit_codes'; then
    pass "(B3) stop_exit_codes genuinely absent still correctly FAILS (absence is not '0 present')"
  else
    fail "(B3) stop_exit_codes absent did NOT fail — the fix treats a missing key as present. Output:"
    printf '%s\n' "$OUT" | sed 's/^/        /'
  fi
  rm -rf "$BOX"

  # (B4) list [0] — the shape the OLD code already handled correctly. Must
  # still pass after the fix (no regression on the previously-working shape).
  BOX="$(_make_vps_box ',"stop_exit_codes":[0]')"
  RES="$(_run_vps_gate "$BOX")"; OUT="${RES#*|}"
  if printf '%s' "$OUT" | grep -qF 'PASS  pm2 stop_exit_codes includes 0'; then
    pass "(B4) list [0] (the pre-existing working shape) still PASSES — no regression"
  else
    fail "(B4) list [0] regressed. Output:"
    printf '%s\n' "$OUT" | sed 's/^/        /'
  fi
  rm -rf "$BOX"
fi

echo ""
echo "=== Result: $PASS passed | $FAIL failed ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
