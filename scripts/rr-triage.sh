#!/bin/bash
# scripts/rr-triage.sh — Rescue Rangers read-only loop/stuck/no-reply triage
# ============================================================================
# R7 of the Rescue Rangers Loop-Response and Fleet Prevention Plan.
# Companion instrument to universal-sops/SOP-RR-LOOP-TRIAGE.md -- read that
# SOP for the full doctrine and the WHY behind each step. This script is the
# read-only, self-controlled ladder walk a responder (human or agent) runs
# over SSH against a box reporting "it loops / it's stuck / no reply".
#
# ⚠️ READ-ONLY, ALWAYS. This script NEVER writes, NEVER restarts anything,
# NEVER contacts a client. It reports. A human (or a separately-authorized
# remediation script) decides and acts.
#
# PLATFORM: Mac (~/.openclaw) and VPS/container (/data/.openclaw) both
# supported; the Contabo path (/opt/clients/<box>/data/config/openclaw.json)
# is detected but its runtime checks (STEP 1) are UNDETERMINED here -- this
# script does not shell into a container.
#
# EXIT CODE CONTRACT (read this before scripting against this tool):
#   0            every step that could run found no problem.
#   3            at least one step is UNDETERMINED -- this OVERRIDES a clean
#                bitmask. An incomplete verdict is NEVER reported as if it
#                were a pass. Read stdout for which step(s) and why.
#   78           STEP 0 itself failed (the box/instrument could not be
#                reached or proven) -- nothing downstream is valid. Same
#                EX_CONFIG convention this repo's other gates use for "needs
#                a human", never a transport failure code.
#   100+bitmask  one or more steps found a real PROBLEM and every step that
#                ran was determined (no step was UNDETERMINED). Subtract 100
#                to get the bitmask; see STEP_BIT_* below for which bit is
#                which mechanism. Offset by 100 so this range can never
#                collide with 0/3/78.
# Never treat a nonzero exit as "the box is broken" without reading which
# branch of this contract produced it -- 3 means "ask again with a working
# instrument", not "problem confirmed".
#
# USAGE:
#   scripts/rr-triage.sh                    # full ladder, human-readable
#   scripts/rr-triage.sh --json             # same ladder, one JSON object
#   scripts/rr-triage.sh --self-test        # offline fixture self-test
# ============================================================================
set -u

STEP_BIT_GATEWAY=1        # STEP 1: crash-loop / gateway down
STEP_BIT_DELIVERY=2       # STEP 2: work completed, delivery died
STEP_BIT_STREAMING=4      # STEP 3: narration spam (streaming.mode partial)
STEP_BIT_TOOLSEARCH=8     # STEP 4: tool-unreachable loop
STEP_BIT_CRON=16          # STEP 5: cron/restart-kill
STEP_BIT_COMPACTION=32    # STEP 6: compaction wedge
STEP_BIT_SUBSTRATE=64     # STEP 7: chown/timeout/registry-parity/raw-writer

PROBLEM_BITS=0
UNDETERMINED_COUNT=0
JSON_MODE=0
RESULTS=""   # newline-separated "STEP|NAME|VERDICT|detail" records

_oc_root() {
  if [ -d "/data/.openclaw" ]; then printf '/data/.openclaw'
  else printf "%s/.openclaw" "$HOME"
  fi
}

_oc_json_path() {
  local root; root="$(_oc_root)"
  printf '%s/openclaw.json' "$root"
}

record() {
  # record STEP NAME VERDICT detail...
  local step="$1" name="$2" verdict="$3"; shift 3
  local detail="$*"
  RESULTS="${RESULTS}${step}|${name}|${verdict}|${detail}
"
  case "$verdict" in
    UNDETERMINED) UNDETERMINED_COUNT=$((UNDETERMINED_COUNT + 1)) ;;
  esac
  if [ "$JSON_MODE" -eq 0 ]; then
    printf '%s %-10s %-13s %s\n' "$step" "$name" "$verdict" "$detail"
  fi
}

# ----------------------------------------------------------------------------
# Config-reading helper. Same bash-3.2.57-heredoc-in-$()-parser workaround
# used throughout this repo (write python source to a temp FILE, run it as a
# plain command substitution, never a heredoc directly inside $(...)), and
# the same mktemp fix: NO literal suffix after the X's (BSD/macOS mktemp does
# not randomize "foo.XXXXXX.py" -- see update-skills.sh's
# _agents_list_detect() for the measured proof).
# ----------------------------------------------------------------------------
_run_py() {
  # _run_py <script-var-name-holding-python-source> <arg...>
  local src="$1"; shift
  local py out rc
  py="$(mktemp "${TMPDIR:-/tmp}/rr-triage.XXXXXX")" || { printf 'PYFAIL'; return 1; }
  printf '%s' "$src" > "$py"
  out="$(python3 "$py" "$@" 2>&1)"; rc=$?
  rm -f "$py"
  printf '%s' "$out"
  return $rc
}

# ============================================================================
# STEP 0 -- reach the box and prove your instruments
# ============================================================================
step0() {
  local ocjson root log_dir today_marker_found=0 db_ok=0 detail

  ocjson="$(_oc_json_path)"
  if [ ! -f "$ocjson" ]; then
    record 0 instruments UNDETERMINED "no config at $ocjson -- cannot prove this is a provisioned box"
    return 1
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    record 0 instruments UNDETERMINED "python3 not on PATH -- cannot parse config or run any downstream check"
    return 1
  fi

  root="$(_oc_root)"
  log_dir="/tmp/openclaw"
  local today; today="$(date +%Y-%m-%d 2>/dev/null || echo unknown)"
  if [ -d "$log_dir" ]; then
    local todays_log="$log_dir/openclaw-${today}.log"
    if [ -f "$todays_log" ] && [ -s "$todays_log" ]; then
      today_marker_found=1
    fi
  fi

  local db_candidates="$root/state.sqlite $root/data/state.sqlite $root/openclaw.sqlite"
  local db f
  for f in $db_candidates; do
    if [ -f "$f" ] && command -v sqlite3 >/dev/null 2>&1; then
      if sqlite3 -readonly "$f" "select 1;" >/dev/null 2>&1; then
        db_ok=1
        db="$f"
        break
      fi
    fi
  done

  if [ "$today_marker_found" -eq 1 ] && [ "$db_ok" -eq 1 ]; then
    record 0 instruments CLEAN "structured log present+non-empty for $today; state db ($db) opens read-only"
    return 0
  fi

  detail="structured-log-today=$today_marker_found db-readonly-open=$db_ok"
  if [ "$today_marker_found" -eq 0 ] && [ "$db_ok" -eq 0 ]; then
    record 0 instruments UNDETERMINED "$detail -- BOTH primary instruments unavailable; nothing downstream in this ladder is valid until this is fixed"
  else
    record 0 instruments UNDETERMINED "$detail -- one primary instrument unavailable; downstream steps that depend on it will report UNDETERMINED too, not a false clean"
  fi
  return 1
}

# ============================================================================
# STEP 1 -- gateway up / crash-looping?
# ============================================================================
step1() {
  if command -v launchctl >/dev/null 2>&1; then
    local label out status
    label="$(launchctl list 2>/dev/null | awk '/openclaw/{print $3; exit}')"
    if [ -n "$label" ]; then
      out="$(launchctl print "gui/$(id -u)/$label" 2>/dev/null)"
      if [ -n "$out" ]; then
        status="$(printf '%s' "$out" | awk '/last exit code/{print $NF; exit}')"
        case "$status" in
          78|EX_CONFIG*)
            PROBLEM_BITS=$((PROBLEM_BITS | STEP_BIT_GATEWAY))
            record 1 gateway PROBLEM "launchctl last exit code=$status (78/EX_CONFIG signature -- schema rejection crash-loop)"
            return 1 ;;
          "")
            record 1 gateway UNDETERMINED "found label $label but could not parse last exit code from launchctl print output" ;;
          *)
            record 1 gateway CLEAN "launchctl label=$label last exit code=$status (not the 78/EX_CONFIG crash-loop signature)" ;;
        esac
        return 0
      fi
    fi
    record 1 gateway UNDETERMINED "launchctl present but no openclaw label found in 'launchctl list' -- may be a VPS/container box misdetected, or the gateway is not loaded at all"
    return 1
  fi
  if command -v docker >/dev/null 2>&1; then
    local cid
    cid="$(docker ps -a --filter "name=openclaw" --format '{{.ID}} {{.Status}}' 2>/dev/null | head -1)"
    if [ -n "$cid" ]; then
      case "$cid" in
        *Restarting*)
          PROBLEM_BITS=$((PROBLEM_BITS | STEP_BIT_GATEWAY))
          record 1 gateway PROBLEM "docker container status shows Restarting -- crash-loop signature: $cid"
          return 1 ;;
        *Up*)
          record 1 gateway CLEAN "docker container is Up: $cid" ;;
        *)
          record 1 gateway UNDETERMINED "docker container found but status unrecognized: $cid" ;;
      esac
      return 0
    fi
    record 1 gateway UNDETERMINED "docker present but no container matching 'openclaw' found"
    return 1
  fi
  record 1 gateway UNDETERMINED "neither launchctl nor docker available -- cannot determine gateway process state on this platform"
  return 1
}

# ============================================================================
# STEP 2 -- did the work complete but the reply die? (DB-only; a log grep
# for handler-timeout is a KNOWN false zero -- see the SOP)
# ============================================================================
step2() {
  local root db f
  root="$(_oc_root)"
  if ! command -v sqlite3 >/dev/null 2>&1; then
    record 2 delivery UNDETERMINED "sqlite3 not on PATH -- delivery_queue_entries / channel_ingress_events cannot be queried"
    return 1
  fi
  for f in "$root/state.sqlite" "$root/data/state.sqlite" "$root/openclaw.sqlite"; do
    [ -f "$f" ] && db="$f" && break
  done
  if [ -z "${db:-}" ]; then
    record 2 delivery UNDETERMINED "no state sqlite db found under $root"
    return 1
  fi
  local total failed timeouts
  total="$(sqlite3 -readonly "$db" "select count(*) from delivery_queue_entries;" 2>/dev/null)"
  if [ -z "$total" ]; then
    record 2 delivery UNDETERMINED "delivery_queue_entries table not present or unreadable in $db"
    return 1
  fi
  failed="$(sqlite3 -readonly "$db" "select count(*) from delivery_queue_entries where status='failed';" 2>/dev/null || echo "")"
  timeouts="$(sqlite3 -readonly "$db" "select count(*) from channel_ingress_events where failed_reason='handler-timeout';" 2>/dev/null || echo "")"
  if [ "${failed:-0}" -gt 0 ] 2>/dev/null || [ "${timeouts:-0}" -gt 0 ] 2>/dev/null; then
    PROBLEM_BITS=$((PROBLEM_BITS | STEP_BIT_DELIVERY))
    record 2 delivery PROBLEM "delivery_queue_entries failed=${failed:-0} of total=$total; channel_ingress_events handler-timeout=${timeouts:-0} -- work may be completing but not reaching the client"
    return 1
  fi
  record 2 delivery CLEAN "delivery_queue_entries total=$total, failed=0; no handler-timeout events"
  return 0
}

# ============================================================================
# STEP 3 -- narration spam? (streaming.mode; ABSENT means "partial", a
# positive finding, not a clean result -- config file only, `openclaw config
# get` cannot answer this)
# ============================================================================
_STEP3_PY='
import json, sys
try:
    with open(sys.argv[1], encoding="utf-8") as fh:
        cfg = json.load(fh)
except Exception as e:
    print("UNDETERMINED|cannot parse config: %s" % e); raise SystemExit(0)
mode = (((cfg.get("channels") or {}).get("telegram") or {}).get("streaming") or {}).get("mode")
if mode is None:
    print("ABSENT|key absent -- effective mode defaults to partial")
else:
    print("PRESENT|%s" % mode)
'
step3() {
  local ocjson out verdict detail
  ocjson="$(_oc_json_path)"
  if [ ! -f "$ocjson" ]; then
    record 3 streaming UNDETERMINED "no config at $ocjson"
    return 1
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    record 3 streaming UNDETERMINED "python3 not on PATH"
    return 1
  fi
  out="$(_run_py "$_STEP3_PY" "$ocjson")"
  verdict="${out%%|*}"
  detail="${out#*|}"
  case "$verdict" in
    ABSENT)
      PROBLEM_BITS=$((PROBLEM_BITS | STEP_BIT_STREAMING))
      record 3 streaming PROBLEM "channels.telegram.streaming.mode is ABSENT -- effective mode is 'partial' (the narration-spam amplifier); absence is a positive finding, not a clean result"
      return 1 ;;
    PRESENT)
      case "$detail" in
        off)
          record 3 streaming CLEAN "streaming.mode explicitly 'off'" ;;
        partial|*)
          PROBLEM_BITS=$((PROBLEM_BITS | STEP_BIT_STREAMING))
          record 3 streaming PROBLEM "streaming.mode explicitly '$detail' -- narration-spam amplifier active"
          return 1 ;;
      esac
      return 0 ;;
    *)
      record 3 streaming UNDETERMINED "$detail"
      return 1 ;;
  esac
}

# ============================================================================
# STEP 4 -- tool-unreachable loop? (toolSearch shape; config file only)
# ============================================================================
_STEP4_PY='
import json, sys
try:
    with open(sys.argv[1], encoding="utf-8") as fh:
        cfg = json.load(fh)
except Exception as e:
    print("UNDETERMINED|cannot parse config: %s" % e); raise SystemExit(0)
ts = (cfg.get("tools") or {}).get("toolSearch")
if ts is None:
    print("ABSENT|no tools.toolSearch key")
elif isinstance(ts, dict):
    mode = ts.get("mode")
    enabled = ts.get("enabled")
    if enabled is True and mode == "directory":
        print("HEALTHY|enabled=true mode=directory")
    else:
        print("MALFORMED_OBJECT|enabled=%r mode=%r" % (enabled, mode))
else:
    print("SCALAR|%r" % (ts,))
'
step4() {
  local ocjson out verdict detail
  ocjson="$(_oc_json_path)"
  if [ ! -f "$ocjson" ]; then
    record 4 toolsearch UNDETERMINED "no config at $ocjson"
    return 1
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    record 4 toolsearch UNDETERMINED "python3 not on PATH"
    return 1
  fi
  out="$(_run_py "$_STEP4_PY" "$ocjson")"
  verdict="${out%%|*}"
  detail="${out#*|}"
  case "$verdict" in
    HEALTHY)
      record 4 toolsearch CLEAN "tools.toolSearch $detail"
      return 0 ;;
    ABSENT|SCALAR|MALFORMED_OBJECT)
      PROBLEM_BITS=$((PROBLEM_BITS | STEP_BIT_TOOLSEARCH))
      record 4 toolsearch PROBLEM "tools.toolSearch verdict=$verdict $detail -- not the healthy {enabled:true,mode:directory} shape"
      return 1 ;;
    *)
      record 4 toolsearch UNDETERMINED "$detail"
      return 1 ;;
  esac
}

# ============================================================================
# STEP 5 -- cron engine or restart-kill?
# ============================================================================
step5() {
  local root db f
  root="$(_oc_root)"
  if ! command -v sqlite3 >/dev/null 2>&1; then
    record 5 cron UNDETERMINED "sqlite3 not on PATH -- cron_run_logs cannot be queried"
    return 1
  fi
  for f in "$root/state.sqlite" "$root/data/state.sqlite" "$root/openclaw.sqlite"; do
    [ -f "$f" ] && db="$f" && break
  done
  if [ -z "${db:-}" ]; then
    record 5 cron UNDETERMINED "no state sqlite db found under $root"
    return 1
  fi
  local runs_today
  runs_today="$(sqlite3 -readonly "$db" "select count(*) from cron_run_logs where date(started_at)=date('now');" 2>/dev/null)"
  if [ -z "$runs_today" ]; then
    record 5 cron UNDETERMINED "cron_run_logs table not present or unreadable in $db"
    return 1
  fi
  if [ "$runs_today" -gt 200 ] 2>/dev/null; then
    PROBLEM_BITS=$((PROBLEM_BITS | STEP_BIT_CRON))
    record 5 cron PROBLEM "cron_run_logs shows $runs_today runs today across all jobs -- check per-job counts against declared caps for a runaway"
    return 1
  fi
  record 5 cron CLEAN "cron_run_logs shows $runs_today runs today (no gross runaway signature; check per-job caps by hand if a specific job is suspected)"
  return 0
}

# ============================================================================
# STEP 6 -- compaction wedge? (structured log only; invisible to every check
# above it -- nothing repeats, nothing is down)
# ============================================================================
step6() {
  local log_dir today todays_log hits
  log_dir="/tmp/openclaw"
  today="$(date +%Y-%m-%d 2>/dev/null || echo unknown)"
  todays_log="$log_dir/openclaw-${today}.log"
  if [ ! -f "$todays_log" ]; then
    record 6 compaction UNDETERMINED "no structured log for $today at $todays_log"
    return 1
  fi
  hits=0
  if command -v grep >/dev/null 2>&1; then
    hits="$(grep -c -E 'contextEngine\.compact\(\) threw|Compaction timed out|could not recover this turn' "$todays_log" 2>/dev/null || echo 0)"
  fi
  if [ "${hits:-0}" -gt 1 ] 2>/dev/null; then
    PROBLEM_BITS=$((PROBLEM_BITS | STEP_BIT_COMPACTION))
    record 6 compaction PROBLEM "$hits compaction-failure markers today -- 2+ is the wedge signature (one alone is routine)"
    return 1
  fi
  record 6 compaction CLEAN "$hits compaction-failure marker(s) today (below the 2+ wedge signature)"
  return 0
}

# ============================================================================
# STEP 7 -- substrate: owner, provider timeouts, registry parity, raw-writer
# fingerprint. Always run last -- always worth confirming.
# ============================================================================
_STEP7_PY='
import json, os, sys
cfg_path = sys.argv[1]
agents_dir = sys.argv[2]
try:
    with open(cfg_path, encoding="utf-8") as fh:
        cfg = json.load(fh)
except Exception as e:
    print("UNDETERMINED|cannot parse config: %s" % e); raise SystemExit(0)

agents = cfg.get("agents") or {}
ids = set()
entries = agents.get("entries")
lst = agents.get("list")
if isinstance(entries, dict):
    ids |= set(str(k) for k in entries.keys())
if isinstance(lst, list):
    for item in lst:
        if isinstance(item, dict) and item.get("id"):
            ids.add(str(item["id"]))
reg_count = len(ids)

dir_count = 0
if os.path.isdir(agents_dir):
    for name in os.listdir(agents_dir):
        if os.path.isdir(os.path.join(agents_dir, name)):
            dir_count += 1

providers = ((cfg.get("providers") or {}))
missing_timeout = []
if isinstance(providers, dict):
    for pname, pcfg in providers.items():
        if isinstance(pcfg, dict) and "timeoutSeconds" not in pcfg:
            missing_timeout.append(str(pname))

parity_problem = reg_count <= 1 and dir_count > 2
print("REPORT|reg_count=%d|dir_count=%d|parity_problem=%s|missing_timeout=%s" % (
    reg_count, dir_count, parity_problem, ",".join(sorted(missing_timeout)) or "none"))
'
step7() {
  local ocjson root agents_dir out verdict detail owner_problem=0 owner_detail=""
  ocjson="$(_oc_json_path)"
  root="$(_oc_root)"
  agents_dir="$root/agents"
  if [ ! -f "$ocjson" ]; then
    record 7 substrate UNDETERMINED "no config at $ocjson"
    return 1
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    record 7 substrate UNDETERMINED "python3 not on PATH"
    return 1
  fi

  # owner-readability check, read-only (never chown here -- this script only
  # reports; the SOP's Step 7 remediation, if authorized, does the chown)
  if [ -r "$ocjson" ]; then
    owner_problem=0
  else
    owner_problem=1
    owner_detail="config not readable by the current user"
  fi

  out="$(_run_py "$_STEP7_PY" "$ocjson" "$agents_dir")"
  verdict="${out%%|*}"
  detail="${out#*|}"
  if [ "$verdict" != "REPORT" ]; then
    record 7 substrate UNDETERMINED "$detail"
    return 1
  fi

  local parity_problem missing_timeout
  parity_problem="$(printf '%s' "$detail" | grep -o 'parity_problem=[A-Za-z]*' | cut -d= -f2)"
  missing_timeout="$(printf '%s' "$detail" | grep -o 'missing_timeout=[^|]*' | cut -d= -f2)"

  if [ "$owner_problem" -eq 1 ] || [ "$parity_problem" = "True" ] || { [ -n "$missing_timeout" ] && [ "$missing_timeout" != "none" ]; }; then
    PROBLEM_BITS=$((PROBLEM_BITS | STEP_BIT_SUBSTRATE))
    record 7 substrate PROBLEM "owner_problem=$owner_problem ($owner_detail) $detail"
    return 1
  fi
  record 7 substrate CLEAN "$detail owner_problem=0"
  return 0
}

# ============================================================================
# main
# ============================================================================
run_ladder() {
  step0
  local step0_rc=$?
  if [ "$step0_rc" -ne 0 ] && [ "$UNDETERMINED_COUNT" -gt 0 ]; then
    # STEP 0 failing (both instruments unavailable) is the hard-stop case;
    # a single-instrument partial failure still lets downstream steps run
    # and report their own UNDETERMINED honestly rather than guessing.
    local ocjson; ocjson="$(_oc_json_path)"
    if [ ! -f "$ocjson" ] || ! command -v python3 >/dev/null 2>&1; then
      echo "STEP 0 FAILED HARD -- nothing downstream is valid. See the line above." >&2
      return 78
    fi
  fi
  step1; step2; step3; step4; step5; step6; step7
  return 0
}

print_summary() {
  echo ""
  echo "============================================================"
  if [ "$UNDETERMINED_COUNT" -gt 0 ]; then
    echo "VERDICT: UNDETERMINED ($UNDETERMINED_COUNT step(s)) -- read-only ladder incomplete."
    echo "This is NOT a clean bill. Re-run with working instruments, or escalate."
  elif [ "$PROBLEM_BITS" -eq 0 ]; then
    echo "VERDICT: CLEAN -- every step that could run found no problem."
  else
    echo "VERDICT: PROBLEM(S) FOUND -- bitmask=$PROBLEM_BITS (exit code = 100+bitmask)"
    [ $((PROBLEM_BITS & STEP_BIT_GATEWAY)) -ne 0 ]    && echo "  - gateway crash-loop (STEP 1)"
    [ $((PROBLEM_BITS & STEP_BIT_DELIVERY)) -ne 0 ]   && echo "  - delivery died after work completed (STEP 2)"
    [ $((PROBLEM_BITS & STEP_BIT_STREAMING)) -ne 0 ]  && echo "  - narration spam / streaming not off (STEP 3)"
    [ $((PROBLEM_BITS & STEP_BIT_TOOLSEARCH)) -ne 0 ] && echo "  - tool-unreachable loop (STEP 4)"
    [ $((PROBLEM_BITS & STEP_BIT_CRON)) -ne 0 ]       && echo "  - cron/restart-kill (STEP 5)"
    [ $((PROBLEM_BITS & STEP_BIT_COMPACTION)) -ne 0 ] && echo "  - compaction wedge (STEP 6)"
    [ $((PROBLEM_BITS & STEP_BIT_SUBSTRATE)) -ne 0 ]  && echo "  - substrate (owner/timeout/registry-parity) (STEP 7)"
  fi
  echo "This script is READ-ONLY. No fix was applied. See SOP-RR-LOOP-TRIAGE.md for the sanctioned remedy at each step."
  echo "============================================================"
}

print_json_summary() {
  python3 -c "
import json, sys
results = []
raw = sys.argv[1]
for line in raw.strip('\n').split('\n'):
    if not line:
        continue
    parts = line.split('|', 3)
    if len(parts) != 4:
        continue
    step, name, verdict, detail = parts
    results.append({'step': int(step), 'name': name, 'verdict': verdict, 'detail': detail})
print(json.dumps({
    'results': results,
    'problem_bits': int(sys.argv[2]),
    'undetermined_count': int(sys.argv[3]),
}, indent=2))
" "$RESULTS" "$PROBLEM_BITS" "$UNDETERMINED_COUNT"
}

self_test() {
  echo "[rr-triage --self-test] offline fixture checks (config-file-based steps only; DB/log steps intentionally report UNDETERMINED off-box)"
  local sbx failures=0
  sbx="$(mktemp -d)"
  trap 'rm -rf "$sbx"' RETURN

  # Fixture 1: healthy config -> STEP3/STEP4 clean, STEP7 clean (no parity problem)
  mkdir -p "$sbx/.openclaw/agents/main"
  cat > "$sbx/.openclaw/openclaw.json" <<'JSON'
{"agents":{"list":[{"id":"main"}]},"channels":{"telegram":{"streaming":{"mode":"off"}}},"tools":{"toolSearch":{"enabled":true,"mode":"directory"}},"providers":{"anthropic":{"timeoutSeconds":120}}}
JSON
  ( HOME="$sbx"; export HOME; PROBLEM_BITS=0; UNDETERMINED_COUNT=0; RESULTS=""
    step3; s3=$?
    step4; s4=$?
    if [ "$s3" -eq 0 ] && [ "$s4" -eq 0 ]; then
      echo "  ✓ healthy config: streaming + toolSearch both CLEAN"
    else
      echo "  ✗ healthy config: expected both clean (s3=$s3 s4=$s4)"; failures=$((failures+1))
    fi
  )

  # Fixture 2: absent streaming key + scalar toolSearch -> both PROBLEM
  mkdir -p "$sbx/.openclaw"
  cat > "$sbx/.openclaw/openclaw.json" <<'JSON'
{"agents":{"list":[{"id":"main"}]},"tools":{"toolSearch":"tools"}}
JSON
  ( HOME="$sbx"; export HOME; PROBLEM_BITS=0; UNDETERMINED_COUNT=0; RESULTS=""
    step3; s3=$?
    step4; s4=$?
    if [ "$s3" -ne 0 ] && [ "$s4" -ne 0 ] && [ $((PROBLEM_BITS & STEP_BIT_STREAMING)) -ne 0 ] && [ $((PROBLEM_BITS & STEP_BIT_TOOLSEARCH)) -ne 0 ]; then
      echo "  ✓ absent-streaming + scalar-toolSearch: both flagged PROBLEM"
    else
      echo "  ✗ absent-streaming + scalar-toolSearch: expected both PROBLEM (s3=$s3 s4=$s4 bits=$PROBLEM_BITS)"; failures=$((failures+1))
    fi
  )

  # Fixture 3: registry-strip signature -> STEP7 PROBLEM
  rm -rf "$sbx/.openclaw"
  mkdir -p "$sbx/.openclaw/agents/main" "$sbx/.openclaw/agents/dept-a" "$sbx/.openclaw/agents/dept-b" "$sbx/.openclaw/agents/dept-c"
  cat > "$sbx/.openclaw/openclaw.json" <<'JSON'
{"agents":{"list":[{"id":"main"}]},"channels":{"telegram":{"streaming":{"mode":"off"}}},"tools":{"toolSearch":{"enabled":true,"mode":"directory"}}}
JSON
  ( HOME="$sbx"; export HOME; PROBLEM_BITS=0; UNDETERMINED_COUNT=0; RESULTS=""
    step7; s7=$?
    if [ "$s7" -ne 0 ] && [ $((PROBLEM_BITS & STEP_BIT_SUBSTRATE)) -ne 0 ]; then
      echo "  ✓ registry-strip signature (1 registered, 4 dirs): STEP7 flagged PROBLEM"
    else
      echo "  ✗ registry-strip signature: expected STEP7 PROBLEM (s7=$s7 bits=$PROBLEM_BITS)"; failures=$((failures+1))
    fi
  )

  # Fixture 4: MUTATION PROOF -- neutralize the registry-parity condition in
  # a copy of this script, re-run fixture 3, must now silently pass.
  local mutated; mutated="$(mktemp "${TMPDIR:-/tmp}/rr-triage-mutated.XXXXXX")"
  sed 's/parity_problem = reg_count <= 1 and dir_count > 2/parity_problem = False/' "$0" > "$mutated"
  if diff -q "$0" "$mutated" >/dev/null 2>&1; then
    echo "  ✗ MUTATION PROOF setup failed: sed made no change -- targeted line has drifted"
    failures=$((failures+1))
  else
    chmod +x "$mutated"
    ( HOME="$sbx"; export HOME
      # shellcheck disable=SC1090
      . "$mutated" --source-only 2>/dev/null
      PROBLEM_BITS=0; UNDETERMINED_COUNT=0; RESULTS=""
      step7; s7=$?
      if [ "$s7" -eq 0 ]; then
        echo "  ✓ MUTATION PROOF: with the parity check disabled, the SAME registry-strip fixture now silently passes -- confirms fixture 3's PROBLEM verdict is the real check enforcing"
      else
        echo "  ✗ MUTATION PROOF FAILED: disabling the check should have flipped fixture 3 to CLEAN (s7=$s7)"
        failures=$((failures+1))
      fi
    )
  fi
  rm -f "$mutated"

  echo "[rr-triage --self-test] $failures failure(s)"
  return $failures
}

# --self-test sources this file (via `.`) to reuse step7/STEP_BIT_* etc.
# without re-running the ladder against the real box; --source-only is
# consumed here so sourcing never falls through into run_ladder below.
if [ "${1:-}" = "--source-only" ]; then
  return 0 2>/dev/null || exit 0
fi

case "${1:-}" in
  --self-test)
    self_test
    exit $? ;;
  --json)
    JSON_MODE=1
    run_ladder
    ladder_rc=$?
    if [ "$ladder_rc" -eq 78 ]; then
      print_json_summary
      exit 78
    fi
    print_json_summary
    ;;
  "")
    run_ladder
    ladder_rc=$?
    if [ "$ladder_rc" -eq 78 ]; then
      print_summary
      exit 78
    fi
    print_summary
    ;;
  -h|--help|*)
    sed -n '2,45p' "$0"
    exit 0 ;;
esac

if [ "$UNDETERMINED_COUNT" -gt 0 ]; then
  exit 3
elif [ "$PROBLEM_BITS" -eq 0 ]; then
  exit 0
else
  exit $((100 + PROBLEM_BITS))
fi
