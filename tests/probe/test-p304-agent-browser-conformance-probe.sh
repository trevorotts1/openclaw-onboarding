#!/usr/bin/env bash
# ============================================================
#  test-p304-agent-browser-conformance-probe.sh — P3-04 (c)5 regression lock
#
#  Proves scripts/probe/p304-agent-browser-conformance-probe.py's 5 checks
#  (headed-flag lock / guard+headless-lock version floor / reaper cron
#  present+hourly / zero stale Chromium under the profile tree / Mac-vs-VPS
#  env matrix incl. bash-3.2-safety) each correctly flip the overall verdict.
#
#  Every scenario stubs throwaway browser_manager.sh/.py, guard-agent-
#  browser-managed.sh, agent-browser-reaper.sh, a cron-list JSON, and a `ps`
#  output file so this test NEVER touches the real box's cron list, live
#  process table, or the real Skill-6 scripts.
#
#  FAIL-FIRST PROOF (reproducible): before
#  scripts/probe/p304-agent-browser-conformance-probe.py existed, scenario 0
#  below fails (script not found) and every dependent scenario fails with it
#  -- 0/N pass. With the script shipped, N/N pass.
#
#  EXIT CODES: 0 all passed, 1 one or more failed.
# ============================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PROBE="$REPO_ROOT/scripts/probe/p304-agent-browser-conformance-probe.py"
FAIL_COUNT=0
PASS_COUNT=0

_pass() { echo "  PASS: $1"; PASS_COUNT=$((PASS_COUNT + 1)); }
_fail() { echo "  FAIL: $1" >&2; FAIL_COUNT=$((FAIL_COUNT + 1)); }
_section() { echo ""; echo "=== $1 ==="; }

_section "Scenario 0 — the probe script must exist and be syntactically valid python3"
if [ -f "$PROBE" ]; then
  _pass "p304-agent-browser-conformance-probe.py shipped at $PROBE"
else
  _fail "p304-agent-browser-conformance-probe.py NOT FOUND at $PROBE -- pre-fix tree"
fi
if [ -f "$PROBE" ] && python3 -m py_compile "$PROBE" 2>/dev/null; then
  _pass "python3 -m py_compile OK"
else
  [ -f "$PROBE" ] && _fail "python3 -m py_compile FAILED"
fi
if [ ! -f "$PROBE" ]; then
  _section "SUMMARY"; echo "  Passed: $PASS_COUNT   Failed: $FAIL_COUNT"; exit 1
fi

TESTHOME="$(mktemp -d)"
trap 'rm -rf "$TESTHOME"' EXIT

_mk_browser_manager_sh() {
  # $1=path  $2=lock_present(0/1)  $3=floor_version
  local f="$1" lock="$2" floor="$3"
  {
    echo "#!/usr/bin/env bash"
    echo "BM_HEADLESS_LOCK_FLOOR=\"$floor\""
    if [ "$lock" = "1" ]; then
      echo "unset AGENT_BROWSER_HEADED 2>/dev/null || true"
      echo "export AGENT_BROWSER_HEADED=false"
    fi
  } > "$f"
}

_mk_guard_sh() {
  # $1=path  $2=version
  printf '#!/usr/bin/env bash\nGUARD_AGENT_BROWSER_MANAGED_VERSION="%s"\n' "$2" > "$1"
}

_mk_reaper_sh_clean() {
  cat > "$1" <<'EOF'
#!/usr/bin/env bash
# BASH 3.2 COMPAT note: do NOT reintroduce `declare -A` / `mapfile` here.
SCOPED_PIDS=()
while IFS= read -r _pid; do
  [ -n "$_pid" ] || continue
  SCOPED_PIDS[${#SCOPED_PIDS[@]}]="$_pid"
done < <(echo)
EOF
}

_mk_reaper_sh_unsafe() {
  cat > "$1" <<'EOF'
#!/usr/bin/env bash
mapfile -t page_specs < <(echo)
EOF
}

_mk_browser_manager_py() {
  # $1=path  $2=is_vps(0/1)
  local f="$1" vps="$2"
  cat > "$f" <<EOF
def durable_root(env=None, isdir=None):
    return "/data/.openclaw" if $vps else "/Users/testbox/.openclaw"
def is_vps(env=None, isdir=None):
    return bool($vps)
def supervisor(env=None):
    return "pm2-or-systemd" if $vps else "launchd"
EOF
}

_run_probe() { python3 "$PROBE" "$@"; }

# ─── Scenario 1: everything healthy — ARMED, exit 0 ─────────────────────────
_section "Scenario 1 — all 5 checks healthy -> ARMED, exit 0"
BMSH1="$TESTHOME/browser_manager1.sh"; _mk_browser_manager_sh "$BMSH1" 1 "v14.1.4"
BMPY1="$TESTHOME/browser_manager1.py"; _mk_browser_manager_py "$BMPY1" 0
GUARD1="$TESTHOME/guard1.sh"; _mk_guard_sh "$GUARD1" "v19.58.0"
REAPER1="$TESTHOME/reaper1.sh"; _mk_reaper_sh_clean "$REAPER1"
PS1="$TESTHOME/ps1.txt"; : > "$PS1"
CRON1='[{"name":"agent-browser-reaper","schedule":"13 * * * *"}]'
OUT1="$(_run_probe --json --browser-manager-sh "$BMSH1" --browser-manager-py "$BMPY1" \
  --guard-sh "$GUARD1" --reaper-sh "$REAPER1" --ps-output-file "$PS1" \
  --cron-list-json "$CRON1" 2>&1)"; RC1=$?
if [ "$RC1" -eq 0 ] && echo "$OUT1" | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert d['overall_armed'] is True
assert d['headless_lock']['rc'] == 0
assert d['version_floor']['rc'] == 0
assert d['reaper_cron']['rc'] == 0
assert d['stale_chromium']['rc'] == 0
assert d['env_matrix']['rc'] == 0
"; then
  _pass "all-healthy inputs -> ARMED, exit 0, every sub-check rc=0"
else
  _fail "all-healthy inputs did not report ARMED (rc=$RC1): $OUT1"
fi

# ─── Scenario 2: headed lock missing -> DEGRADED ────────────────────────────
_section "Scenario 2 — box-level headless lock missing from browser_manager.sh -> DEGRADED"
BMSH2="$TESTHOME/browser_manager2.sh"; _mk_browser_manager_sh "$BMSH2" 0 "v14.1.4"
OUT2="$(_run_probe --json --browser-manager-sh "$BMSH2" --browser-manager-py "$BMPY1" \
  --guard-sh "$GUARD1" --reaper-sh "$REAPER1" --ps-output-file "$PS1" \
  --cron-list-json "$CRON1" 2>&1)"; RC2=$?
if [ "$RC2" -eq 1 ] && echo "$OUT2" | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert d['overall_armed'] is False
assert d['headless_lock']['rc'] == 1
assert d['headless_lock']['unset_present'] is False
"; then
  _pass "missing headless lock correctly reported DEGRADED"
else
  _fail "missing-headless-lock case did not report DEGRADED correctly (rc=$RC2): $OUT2"
fi

# ─── Scenario 3: guard version below floor -> DEGRADED ─────────────────────
_section "Scenario 3 — guard version below v14.1.4 floor -> DEGRADED"
GUARD3="$TESTHOME/guard3.sh"; _mk_guard_sh "$GUARD3" "v13.8.10"
OUT3="$(_run_probe --json --browser-manager-sh "$BMSH1" --browser-manager-py "$BMPY1" \
  --guard-sh "$GUARD3" --reaper-sh "$REAPER1" --ps-output-file "$PS1" \
  --cron-list-json "$CRON1" 2>&1)"; RC3=$?
if [ "$RC3" -eq 1 ] && echo "$OUT3" | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert d['overall_armed'] is False
assert d['version_floor']['rc'] == 1
assert d['version_floor']['guard_meets_floor'] is False
"; then
  _pass "below-floor guard version correctly reported DEGRADED"
else
  _fail "below-floor-version case did not report DEGRADED correctly (rc=$RC3): $OUT3"
fi

# ─── Scenario 4: reaper cron missing entirely -> DEGRADED ──────────────────
_section "Scenario 4 — no agent-browser-reaper cron registered -> DEGRADED"
OUT4="$(_run_probe --json --browser-manager-sh "$BMSH1" --browser-manager-py "$BMPY1" \
  --guard-sh "$GUARD1" --reaper-sh "$REAPER1" --ps-output-file "$PS1" \
  --cron-list-json '[{"name":"some-other-cron","schedule":"0 * * * *"}]' 2>&1)"; RC4=$?
if [ "$RC4" -eq 1 ] && echo "$OUT4" | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert d['overall_armed'] is False
assert d['reaper_cron']['reaper_present'] is False
"; then
  _pass "missing reaper cron correctly reported DEGRADED"
else
  _fail "missing-reaper-cron case did not report DEGRADED correctly (rc=$RC4): $OUT4"
fi

# ─── Scenario 5: reaper cron present but wrong schedule -> DEGRADED ────────
_section "Scenario 5 — reaper cron present but NOT hourly 13 * * * * -> DEGRADED"
OUT5="$(_run_probe --json --browser-manager-sh "$BMSH1" --browser-manager-py "$BMPY1" \
  --guard-sh "$GUARD1" --reaper-sh "$REAPER1" --ps-output-file "$PS1" \
  --cron-list-json '[{"name":"agent-browser-reaper","schedule":"*/10 * * * *"}]' 2>&1)"; RC5=$?
if [ "$RC5" -eq 1 ] && echo "$OUT5" | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert d['overall_armed'] is False
assert d['reaper_cron']['reaper_present'] is True
assert d['reaper_cron']['schedule_hourly'] is False
"; then
  _pass "wrong-schedule reaper cron correctly reported DEGRADED"
else
  _fail "wrong-schedule case did not report DEGRADED correctly (rc=$RC5): $OUT5"
fi

# ─── Scenario 6: cron list unavailable (no override, no CLI) -> UNRESOLVABLE
_section "Scenario 6 — cron list source unavailable and no override -> UNRESOLVABLE, exit 2"
# A minimal PATH carrying python3 (needed to RUN the probe itself and to
# verify its JSON output below) but deliberately EXCLUDING wherever the real
# `openclaw` CLI lives on this box -- proves the "no fabricated pass" fail-
# closed behavior when the live cron source is genuinely unavailable, without
# breaking the test's own python3-based assertions.
_PY3_DIR="$(dirname "$(command -v python3)")"
_NARROW_PATH="$_PY3_DIR:/usr/bin:/bin"
OUT6="$(PATH="$_NARROW_PATH" _run_probe --json --browser-manager-sh "$BMSH1" --browser-manager-py "$BMPY1" \
  --guard-sh "$GUARD1" --reaper-sh "$REAPER1" --ps-output-file "$PS1" 2>&1)"; RC6=$?
if [ "$RC6" -eq 2 ] && echo "$OUT6" | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert d['overall_rc'] == 2
assert d['reaper_cron']['rc'] == 2
assert 'never fabricated as a pass' in d['reaper_cron']['note']
"; then
  _pass "unavailable cron source correctly reported UNRESOLVABLE, never fabricated a pass"
else
  _fail "unavailable-cron-source case did not report UNRESOLVABLE correctly (rc=$RC6): $OUT6"
fi

# ─── Scenario 7: a stale Chromium proc under the profile tree -> DEGRADED ──
_section "Scenario 7 — one Chromium proc under the profile tree older than TTL -> DEGRADED, count reported"
PS7="$TESTHOME/ps7.txt"
cat > "$PS7" <<EOF
12345 40:00 /Applications/Chromium.app/Contents/MacOS/Chromium --headless --user-data-dir=/Users/testbox/.agent-browser/profile
EOF
OUT7="$(_run_probe --json --browser-manager-sh "$BMSH1" --browser-manager-py "$BMPY1" \
  --guard-sh "$GUARD1" --reaper-sh "$REAPER1" --ps-output-file "$PS7" \
  --ab-engine-dir "/Users/testbox/.agent-browser" --playwright-dir "/Users/testbox/.cache/ms-playwright-ghl" \
  --ttl-seconds 1800 --cron-list-json "$CRON1" 2>&1)"; RC7=$?
if [ "$RC7" -eq 1 ] && echo "$OUT7" | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert d['overall_armed'] is False
assert d['stale_chromium']['rc'] == 1
assert d['stale_chromium']['stale_count'] == 1
assert '12345' in d['stale_chromium']['stale_pids']
"; then
  _pass "a stale scoped Chromium proc (age 2400s > TTL 1800s) correctly reported DEGRADED with count=1"
else
  _fail "stale-chromium case did not report DEGRADED correctly (rc=$RC7): $OUT7"
fi

# ─── Scenario 8: a Chromium proc under the profile but WITHIN TTL -> ARMED ──
_section "Scenario 8 — scoped Chromium proc within TTL -> not counted as stale"
PS8="$TESTHOME/ps8.txt"
cat > "$PS8" <<EOF
12346 05:00 /Applications/Chromium.app/Contents/MacOS/Chromium --headless --user-data-dir=/Users/testbox/.agent-browser/profile
EOF
OUT8="$(_run_probe --json --browser-manager-sh "$BMSH1" --browser-manager-py "$BMPY1" \
  --guard-sh "$GUARD1" --reaper-sh "$REAPER1" --ps-output-file "$PS8" \
  --ab-engine-dir "/Users/testbox/.agent-browser" --playwright-dir "/Users/testbox/.cache/ms-playwright-ghl" \
  --ttl-seconds 1800 --cron-list-json "$CRON1" 2>&1)"; RC8=$?
if [ "$RC8" -eq 0 ] && echo "$OUT8" | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert d['stale_chromium']['scoped_total'] == 1
assert d['stale_chromium']['stale_count'] == 0
"; then
  _pass "in-TTL scoped Chromium proc correctly NOT counted as stale (scoped=1, stale=0)"
else
  _fail "within-TTL case did not report correctly (rc=$RC8): $OUT8"
fi

# ─── Scenario 9: an UNRELATED chrome/Claude proc must NEVER be flagged ─────
_section "Scenario 9 — bare Chrome/Claude proc (not under the profile) must NEVER be flagged"
PS9="$TESTHOME/ps9.txt"
cat > "$PS9" <<EOF
99999 99:00:00 /Applications/Google Chrome.app/Contents/MacOS/Google Chrome
88888 99:00:00 /Applications/Claude.app/Contents/MacOS/Claude
EOF
OUT9="$(_run_probe --json --browser-manager-sh "$BMSH1" --browser-manager-py "$BMPY1" \
  --guard-sh "$GUARD1" --reaper-sh "$REAPER1" --ps-output-file "$PS9" \
  --ab-engine-dir "/Users/testbox/.agent-browser" --playwright-dir "/Users/testbox/.cache/ms-playwright-ghl" \
  --cron-list-json "$CRON1" 2>&1)"; RC9=$?
if [ "$RC9" -eq 0 ] && echo "$OUT9" | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert d['stale_chromium']['scoped_total'] == 0
assert d['overall_armed'] is True
"; then
  _pass "bare Chrome/Claude (unscoped) never flagged -- scoped_total=0, ARMED"
else
  _fail "unrelated-process case incorrectly flagged (rc=$RC9): $OUT9"
fi

# ─── Scenario 10: bash-3.2-unsafe construct in a REAL code line -> DEGRADED ─
_section "Scenario 10 — real mapfile usage (not a comment) in a core script -> DEGRADED"
REAPER10="$TESTHOME/reaper10.sh"; _mk_reaper_sh_unsafe "$REAPER10"
OUT10="$(_run_probe --json --browser-manager-sh "$BMSH1" --browser-manager-py "$BMPY1" \
  --guard-sh "$GUARD1" --reaper-sh "$REAPER10" --ps-output-file "$PS1" \
  --cron-list-json "$CRON1" 2>&1)"; RC10=$?
if [ "$RC10" -eq 1 ] && echo "$OUT10" | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert d['overall_armed'] is False
assert d['env_matrix']['rc'] == 1
assert len(d['env_matrix']['bash32_violations']) >= 1
assert d['env_matrix']['bash32_violations'][0]['construct'] == 'mapfile'
"; then
  _pass "real mapfile usage in code correctly reported DEGRADED via env_matrix.bash32_violations"
else
  _fail "real-mapfile-usage case did not report DEGRADED correctly (rc=$RC10): $OUT10"
fi

# ─── Scenario 11: mapfile mentioned only in a COMMENT -> NEVER flagged ─────
_section "Scenario 11 — mapfile/declare -A mentioned ONLY in a comment (doc prose) -> NEVER flagged"
OUT11="$(_run_probe --json --browser-manager-sh "$BMSH1" --browser-manager-py "$BMPY1" \
  --guard-sh "$GUARD1" --reaper-sh "$REAPER1" --ps-output-file "$PS1" \
  --cron-list-json "$CRON1" 2>&1)"; RC11=$?
# REAPER1 (_mk_reaper_sh_clean) has a comment mentioning "declare -A" / "mapfile"
# by name in its header prose, but zero real usage -- this is the false-positive
# regression this scenario locks (found + fixed during this unit's own build).
if [ "$RC11" -eq 0 ] && echo "$OUT11" | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert d['env_matrix']['bash32_violations'] == []
"; then
  _pass "comment-only mention of banned constructs never false-positives"
else
  _fail "comment-only mention incorrectly flagged as a violation (rc=$RC11): $OUT11"
fi

# ─── Scenario 12: VPS platform detection via browser_manager.py is_vps() ───
_section "Scenario 12 — VPS platform correctly detected via durable_root()/is_vps()"
BMPY12="$TESTHOME/browser_manager12.py"; _mk_browser_manager_py "$BMPY12" 1
OUT12="$(_run_probe --json --browser-manager-sh "$BMSH1" --browser-manager-py "$BMPY12" \
  --guard-sh "$GUARD1" --reaper-sh "$REAPER1" --ps-output-file "$PS1" \
  --cron-list-json "$CRON1" 2>&1)"; RC12=$?
if [ "$RC12" -eq 0 ] && echo "$OUT12" | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert d['env_matrix']['platform'] == 'vps'
assert d['env_matrix']['durable_root'] == '/data/.openclaw'
assert d['env_matrix']['supervisor'] == 'pm2-or-systemd'
"; then
  _pass "VPS platform correctly detected via the SAME durable_root()/is_vps()/supervisor() primitives ENV-MATRIX.md names"
else
  _fail "VPS platform detection did not report correctly (rc=$RC12): $OUT12"
fi

# ─── Scenario 13: human-readable output includes a VERDICT line ────────────
_section "Scenario 13 — human-readable output includes per-check tags + VERDICT line"
OUT13="$(_run_probe --browser-manager-sh "$BMSH1" --browser-manager-py "$BMPY1" \
  --guard-sh "$GUARD1" --reaper-sh "$REAPER1" --ps-output-file "$PS1" \
  --cron-list-json "$CRON1" 2>&1)"
if echo "$OUT13" | grep -q "VERDICT: ARMED" && echo "$OUT13" | grep -q "headed flag locked false"; then
  _pass "human-readable output includes per-check line + VERDICT"
else
  _fail "human-readable output missing expected content: $OUT13"
fi

_section "SUMMARY"
echo "  Passed: $PASS_COUNT   Failed: $FAIL_COUNT"
if [ "$FAIL_COUNT" -gt 0 ]; then
  exit 1
fi
exit 0
