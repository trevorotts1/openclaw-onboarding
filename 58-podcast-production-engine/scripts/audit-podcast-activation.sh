#!/usr/bin/env bash
# =============================================================================
# audit-podcast-activation.sh  (fleet-wide podcast activation health audit)
# =============================================================================
# WHAT
#   Answers "who else has Leanne's problem". Leanne's ticket proved a client
#   box can be provisioned (edge live, dashboard up) and STILL never get the
#   podcast processor activated on the box. That failure is invisible per box
#   until an episode is submitted, so this audit sweeps EVERY box in the fleet
#   roster and reports, per box, whether the Podcast Production Engine (skill
#   58) activation layer is actually in place:
#
#     hook        the inbound webhook intake mapping for podcast is registered
#                 (hooks.enabled, a non-empty hooks token, and a mapping whose
#                 id/name/sessionKey/agentId mentions podcast)
#     agent       the podcast department agent exists on the box
#     controller  podcast_controller.py present in the box's skill 58 scripts
#     scheduler   processor scheduler present: a scheduler script in the box's
#                 skill 58 scripts, or an enabled podcast cron job that is not
#                 the provision smoke-test cron (podcast-smoke-*)
#
#   Output is a fleet status table (box | hook | agent | controller |
#   scheduler | overall) plus a summary that counts how many boxes are missing
#   the processor.
#
# BOX ENUMERATION (explicit roster, never auto-discovery)
#   The fleet roster is the fleet-prover box registry, the same source
#   scripts/fleet-standing/propagate-fleet-standing-gate.sh reads:
#       ~/clawd/fleet-prover/box-registry.json
#   boxes: { <slug>: {kind: local|vps|mac|rescue_mac, ssh_target, container,
#                     ssh_alias, ...} }
#   Override the path with --registry FILE or PODCAST_BOX_REGISTRY. As an
#   alternative, --boxes FILE accepts the pipe-delimited targets format of
#   scripts/fleet-roll/podcast-roll-targets.example.txt
#   (slug|type|address|container|compose_dir|...); only the first five fields
#   are read and the client identity fields are NEVER read or printed.
#
# REMOTE CHECK (read-only, repo-first)
#   Per box the audit prefers the activation guard from the activation layer:
#       <box skills>/58-podcast-production-engine/scripts/guard-activation-health.py --repo-only
#   and parses its ACT_* marker lines. When that script is not on the box yet,
#   a lightweight built-in repo-only probe runs instead, checking the same four
#   pieces against the box's own openclaw.json, cron/jobs.json, departments
#   directory, and skill 58 scripts directory. Either way the audit:
#     - NEVER installs, writes, restarts, or mutates anything on a box.
#     - NEVER reads or prints secret values. Config files are inspected for
#       presence and shape only (a token is checked non-empty, never echoed).
#
# MARKER CONTRACT (what both the guard and the built-in probe emit)
#   ACT_HOOK=PASS|FAIL        ACT_AGENT=PASS|FAIL
#   ACT_CONTROLLER=PASS|FAIL  ACT_SCHEDULER=PASS|FAIL
#   ACT_OVERALL=PASS|FAIL     RESULT=OK
#   Diagnostic lines may be emitted as NOTE: <text> and REMOTE-ERROR: <text>.
#   A missing marker is graded FAIL (fail-closed), never PASS.
#
# TRANSPORT (mirrors scripts/fleet-standing/propagate-fleet-standing-gate.sh)
#   local : the probe runs directly against this box.
#   vps   : ssh to ssh_target, then docker exec -i -u node <container> bash -s
#           against /data/.openclaw.
#   mac   : ssh to ssh_alias (resolved from ~/.ssh/config), wrapped in
#           zsh -lc 'bash -s', against $HOME/.openclaw.
#   All ssh is BatchMode with a connect timeout. A box that is unreachable or
#   dark is graded UNREACHABLE and never aborts the sweep.
#
# USAGE
#   bash 58-podcast-production-engine/scripts/audit-podcast-activation.sh
#   bash 58-podcast-production-engine/scripts/audit-podcast-activation.sh --box openclaw-hy5t
#   bash 58-podcast-production-engine/scripts/audit-podcast-activation.sh --registry FILE
#   bash 58-podcast-production-engine/scripts/audit-podcast-activation.sh --boxes FILE
#
# FLAGS
#   --box <slug>       audit ONE box only (must exist in the roster)
#   --registry <file>  box registry path (default $PODCAST_BOX_REGISTRY or
#                      ~/clawd/fleet-prover/box-registry.json)
#   --boxes <file>     targets-format roster override (see BOX ENUMERATION)
#   -h, --help         show this help
#
# ENV
#   PODCAST_BOX_REGISTRY   registry path override
#   PODCAST_OC_ROOT_LOCAL  audit the local box against this root instead of
#                          $HOME/.openclaw (sandbox/test use only)
#
# EXIT CODES
#   0  every rostered box graded PASS
#   1  one or more boxes graded FAIL, UNREACHABLE, or SKIPPED
#   2  usage error, or the roster could not be read
#   3  no boxes selected (empty roster, or --box slug not found)
# =============================================================================
set -euo pipefail

REGISTRY_DEFAULT="${HOME}/clawd/fleet-prover/box-registry.json"
REGISTRY="${PODCAST_BOX_REGISTRY:-$REGISTRY_DEFAULT}"
TARGETS_FILE=""
ONLY_BOX=""
LOCAL_OC_ROOT="${PODCAST_OC_ROOT_LOCAL:-${HOME}/.openclaw}"
SSH_OPTS_VPS=(-o BatchMode=yes -o ConnectTimeout=20 -o StrictHostKeyChecking=accept-new)
SSH_OPTS_MAC=(-o BatchMode=yes -o ConnectTimeout=25 -o StrictHostKeyChecking=accept-new)

usage() { sed -n '2,88p' "$0" | sed 's/^# \{0,1\}//'; }

log() { printf '%s\n' "$*"; }
err() { printf '%s\n' "$*" >&2; }
die() { local code="$1"; shift; err "FATAL ($code): $*"; exit "$code"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --box)      ONLY_BOX="${2:-}"; shift 2 ;;
    --registry) REGISTRY="${2:-}"; shift 2 ;;
    --boxes)    TARGETS_FILE="${2:-}"; shift 2 ;;
    -h|--help)  usage; exit 0 ;;
    *) die 2 "unknown argument: $1 (see --help)" ;;
  esac
done

command -v python3 >/dev/null 2>&1 || die 2 "python3 is required to read the roster and run the probe"

# --------------------------------------------------------------------------- #
# Roster loading. Emits one row per box, joined with the ASCII unit separator
# (\x1f). A non-whitespace separator is REQUIRED: tab is an IFS-whitespace
# character, so consecutive tabs collapse and a row with empty interior fields
# (a mac box has none of ssh_target/container) would shift its columns.
#   slug <US> kind <US> ssh_target <US> container <US> ssh_alias
# Two sources; both are operator-private and never committed:
#   registry  : the fleet-prover box registry (default)
#   targets   : the fleet-roll pipe format (identity fields ignored)
# --------------------------------------------------------------------------- #
load_registry_rows() {
  [ -f "$REGISTRY" ] || die 2 "box registry not found: $REGISTRY (pass --registry FILE or --boxes FILE)"
  python3 - "$REGISTRY" <<'PY'
import json, sys
try:
    reg = json.load(open(sys.argv[1]))
except Exception as e:
    sys.stderr.write("registry unreadable: %s\n" % e)
    sys.exit(1)
boxes = reg.get("boxes", reg) if isinstance(reg, dict) else {}
if not isinstance(boxes, dict):
    sys.stderr.write("registry has no boxes map\n")
    sys.exit(1)
for slug in sorted(boxes):
    v = boxes[slug] or {}
    if not isinstance(v, dict):
        v = {}
    print("\x1f".join([
        slug,
        str(v.get("kind", "")),
        str(v.get("ssh_target", "") or ""),
        str(v.get("container", "") or ""),
        str(v.get("ssh_alias", "") or ""),
    ]))
PY
}

load_targets_rows() {
  [ -f "$TARGETS_FILE" ] || die 2 "targets file not found: $TARGETS_FILE"
  # Only fields 1 to 5 are consumed; the trailing identity fields are never
  # read into a variable, never logged, never printed.
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%%$'\r'}"
    [ -z "$line" ] && continue
    case "$line" in \#*) continue ;; esac
    slug="$(printf '%s' "$line" | cut -d'|' -f1)"
    btype="$(printf '%s' "$line" | cut -d'|' -f2)"
    addr="$(printf '%s' "$line" | cut -d'|' -f3)"
    container="$(printf '%s' "$line" | cut -d'|' -f4)"
    case "$btype" in
      vps)
        # targets format stores the bare VPS IP in the address column (see
        # podcast-roll-targets.example.txt: "ssh root@IP"); the registry stores
        # ssh_target as root@<ip>. Normalize to root@<ip> when the address has
        # no user part, matching the fleet-roll ssh convention.
        case "$addr" in *@*) vps_target="$addr" ;; *) vps_target="root@${addr}" ;; esac
        printf '%s\x1f%s\x1f%s\x1f%s\x1f%s\n' "$slug" "vps" "$vps_target" "$container" ""
        ;;
      mac)   printf '%s\x1f%s\x1f%s\x1f%s\x1f%s\n' "$slug" "mac" "" "" "$addr" ;;
      local) printf '%s\x1f%s\x1f%s\x1f%s\x1f%s\n' "$slug" "local" "" "" "" ;;
      *) die 2 "targets row '$slug': type must be vps, mac, or local" ;;
    esac
  done < "$TARGETS_FILE"
}

ROWS=""
if [ -n "$TARGETS_FILE" ]; then
  ROWS="$(load_targets_rows)"
else
  ROWS="$(load_registry_rows)" || die 2 "failed to parse box registry: $REGISTRY"
fi
[ -n "$ROWS" ] || die 3 "no boxes found in the roster"

if [ -n "$ONLY_BOX" ]; then
  # bash case-match, not awk -F: the unit separator is awkward to pass as an
  # awk field separator across BSD and GNU awks.
  FILTERED=""
  while IFS= read -r _row; do
    case "$_row" in
      "${ONLY_BOX}"$'\x1f'*) FILTERED="$_row" ;;
    esac
  done <<EOF
$ROWS
EOF
  [ -n "$FILTERED" ] || die 3 "--box '$ONLY_BOX' not found in the roster"
  ROWS="$FILTERED"
fi

BOX_COUNT="$(printf '%s\n' "$ROWS" | wc -l | tr -d '[:space:]')"

# --------------------------------------------------------------------------- #
# Remote probe payload. Ships to the box over ssh stdin (or runs directly for
# the local box). STRICTLY READ-ONLY: it reads config files and directory
# listings only, writes nothing, installs nothing, restarts nothing, and never
# reads or prints a secret value. Preamble variables (exported by the caller):
#   OC_ROOT_ARG  the box's OpenClaw root   BOX_SLUG  the box's slug
# --------------------------------------------------------------------------- #
remote_payload() {
cat <<'PAYLOAD'
set -u
OC_ROOT="${OC_ROOT_ARG:-}"
SLUG="${BOX_SLUG:-}"
[ -n "$OC_ROOT" ] || { echo "REMOTE-ERROR: OC_ROOT_ARG not supplied"; echo "RESULT=FAIL"; exit 1; }

SKILL_DIR=""
for c in "$OC_ROOT"/skills/58-podcast*; do
  [ -d "$c" ] || continue
  SKILL_DIR="$c"
  break
done

# Preferred check: the activation guard (activation layer), repo-only mode.
# Its exit code is NOT trusted for grading; only its ACT_* markers are.
run_guard() {
  [ -n "$SKILL_DIR" ] || return 1
  [ -f "$SKILL_DIR/scripts/guard-activation-health.py" ] || return 1
  command -v python3 >/dev/null 2>&1 || return 1
  gout="$(python3 "$SKILL_DIR/scripts/guard-activation-health.py" --repo-only 2>&1)" || true
  printf '%s\n' "$gout"
  case "$gout" in
    *"ACT_HOOK="*) return 0 ;;
    *) echo "NOTE: guard-activation-health.py emitted no ACT_* markers; falling back to the built-in probe"
       return 1 ;;
  esac
}

# Built-in lightweight repo-only probe (same marker contract as the guard).
lightweight_probe() {
  if ! command -v python3 >/dev/null 2>&1; then
    echo "REMOTE-ERROR: python3 not present on this box; cannot probe"
    echo "ACT_HOOK=FAIL"
    echo "ACT_AGENT=FAIL"
    echo "ACT_CONTROLLER=FAIL"
    echo "ACT_SCHEDULER=FAIL"
    echo "ACT_OVERALL=FAIL"
    return 0
  fi
  OC_ROOT="$OC_ROOT" BOX_SLUG="$SLUG" python3 - <<'PY'
import glob, json, os

oc = os.environ.get("OC_ROOT", "")
res = {"HOOK": False, "AGENT": False, "CONTROLLER": False, "SCHEDULER": False}
notes = []

def load(p):
    try:
        with open(p) as f:
            return json.load(f)
    except Exception:
        return None

cfg = load(os.path.join(oc, "openclaw.json"))
if cfg is None or not isinstance(cfg, dict):
    notes.append("NOTE: openclaw.json missing or unreadable under %s" % oc)
else:
    h = cfg.get("hooks") or {}
    hook_hit = False
    for m in (h.get("mappings") or []):
        if not isinstance(m, dict):
            continue
        blob = " ".join(str(m.get(k, "")) for k in ("id", "name", "sessionKey", "agentId")).lower()
        if "podcast" in blob:
            hook_hit = True
            break
    res["HOOK"] = bool(h.get("enabled")) and bool(h.get("token")) and hook_hit
    for a in ((cfg.get("agents") or {}).get("list") or []):
        if not isinstance(a, dict):
            continue
        blob = " ".join(str(a.get(k, "")) for k in ("id", "name", "department")).lower()
        if "podcast" in blob:
            res["AGENT"] = True
            break
    if not res["AGENT"]:
        ddir = os.path.join(oc, "workspace", "departments")
        if os.path.isdir(ddir):
            for nm in os.listdir(ddir):
                if "podcast" in nm.lower():
                    res["AGENT"] = True
                    break

skill = ""
for c in sorted(glob.glob(os.path.join(oc, "skills", "58-podcast*"))):
    if os.path.isdir(c):
        skill = c
        break
if not skill:
    notes.append("NOTE: skill 58 directory not found under %s/skills" % oc)
else:
    res["CONTROLLER"] = os.path.isfile(os.path.join(skill, "scripts", "podcast_controller.py"))
    sched_files = glob.glob(os.path.join(skill, "scripts", "*schedul*"))
    cron_hit = False
    cj = load(os.path.join(oc, "cron", "jobs.json"))
    jobs = cj.get("jobs") if isinstance(cj, dict) else cj
    if isinstance(jobs, list):
        for j in jobs:
            if not isinstance(j, dict):
                continue
            nm = str(j.get("name", "")).lower()
            if "podcast" not in nm:
                continue
            if nm.startswith("podcast-smoke-"):
                continue  # the provision smoke-test cron is not the processor scheduler
            if j.get("enabled", True):
                cron_hit = True
                break
    res["SCHEDULER"] = bool(sched_files) or cron_hit

for k in ("HOOK", "AGENT", "CONTROLLER", "SCHEDULER"):
    print("ACT_%s=%s" % (k, "PASS" if res[k] else "FAIL"))
print("ACT_OVERALL=%s" % ("PASS" if all(res.values()) else "FAIL"))
for n in notes:
    print(n)
PY
}

if ! run_guard; then
  lightweight_probe
fi
echo "RESULT=OK"
PAYLOAD
}

# Preamble: args ride as exported env lines ahead of the payload, so nothing
# crosses the ssh/docker layers as positional arguments.
preamble() { # $1=oc_root $2=slug
  printf 'export OC_ROOT_ARG="%s" BOX_SLUG="%s"\n' "$1" "$2"
}

# --------------------------------------------------------------------------- #
# Per-box runners. Each captures the probe's stdout+stderr into $OUT_FILE and
# returns the transport exit status. ONE box failing never aborts the sweep.
# --------------------------------------------------------------------------- #
run_local() { # $1=oc_root $2=slug
  { preamble "$1" "$2"; remote_payload; } | bash -s > "$OUT_FILE" 2>&1
}

run_mac() { # $1=alias $2=slug
  { preamble '$HOME/.openclaw' "$2"; remote_payload; } \
    | ssh "${SSH_OPTS_MAC[@]}" "$1" "zsh -lc 'bash -s'" > "$OUT_FILE" 2>&1
}

run_vps() { # $1=ssh_target $2=container $3=slug
  { preamble "/data/.openclaw" "$3"; remote_payload; } \
    | ssh "${SSH_OPTS_VPS[@]}" "$1" "docker exec -i -u node $2 bash -s" > "$OUT_FILE" 2>&1
}

marker() { # $1=piece -> raw marker value from $OUT_FILE ("" when absent)
  grep -m1 "^ACT_$1=" "$OUT_FILE" 2>/dev/null | cut -d= -f2 || true
}

grade() { # $1=raw marker -> PASS | FAIL | NOINFO
  case "$1" in
    PASS) printf 'PASS' ;;
    FAIL) printf 'FAIL' ;;
    *)    printf 'NOINFO' ;;
  esac
}

# --------------------------------------------------------------------------- #
# Sweep
# --------------------------------------------------------------------------- #
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
OUT_FILE="$WORK/out"

CNT_PASS=0
CNT_MISSING=0
CNT_UNREACHABLE=0
CNT_SKIP=0
MISSING_LIST=""
UNREACHABLE_LIST=""
SKIP_LIST=""
TABLE_ROWS=""

log "podcast activation audit  (started $TS, read-only, ${BOX_COUNT} box(es))"
log "roster: $([ -n "$TARGETS_FILE" ] && printf '%s' "$TARGETS_FILE" || printf '%s' "$REGISTRY")"
log ""

while IFS=$'\x1f' read -r slug kind ssh_target container ssh_alias; do
  [ -n "$slug" ] || continue
  : > "$OUT_FILE"
  transport_rc=0
  case "$kind" in
    local)
      run_local "$LOCAL_OC_ROOT" "$slug" || transport_rc=$?
      ;;
    vps)
      if [ -z "$ssh_target" ] || [ -z "$container" ]; then
        transport_rc=99
      else
        run_vps "$ssh_target" "$container" "$slug" || transport_rc=$?
      fi
      ;;
    mac|rescue_mac)
      tgt="${ssh_alias:-$slug}"
      run_mac "$tgt" "$slug" || transport_rc=$?
      ;;
    *)
      transport_rc=98
      ;;
  esac

  if [ "$transport_rc" = "99" ] || [ "$transport_rc" = "98" ]; then
    state="SKIPPED"
    if [ "$transport_rc" = "98" ]; then note="unknown kind '$kind'"
    else note="registry row lacks ssh_target/container"; fi
    CNT_SKIP=$((CNT_SKIP + 1))
    SKIP_LIST="${SKIP_LIST} ${slug} (${note})"
    row="$(printf '%-26s %-7s %-7s %-12s %-11s %s' "$slug" "-" "-" "-" "-" "$state")"
    TABLE_ROWS="${TABLE_ROWS}${row}"$'\n'
    continue
  fi

  if [ "$transport_rc" != "0" ] || ! grep -q '^RESULT=OK$' "$OUT_FILE"; then
    CNT_UNREACHABLE=$((CNT_UNREACHABLE + 1))
    UNREACHABLE_LIST="${UNREACHABLE_LIST} ${slug}"
    row="$(printf '%-26s %-7s %-7s %-12s %-11s %s' "$slug" "-" "-" "-" "-" "UNREACHABLE")"
    TABLE_ROWS="${TABLE_ROWS}${row}"$'\n'
    continue
  fi

  g_hook="$(grade "$(marker HOOK)")"
  g_agent="$(grade "$(marker AGENT)")"
  g_controller="$(grade "$(marker CONTROLLER)")"
  g_scheduler="$(grade "$(marker SCHEDULER)")"
  raw_overall="$(marker OVERALL)"
  if [ "$g_hook" = "PASS" ] && [ "$g_agent" = "PASS" ] && [ "$g_controller" = "PASS" ] && [ "$g_scheduler" = "PASS" ]; then
    overall="PASS"
  elif [ -n "$raw_overall" ]; then
    overall="$(grade "$raw_overall")"
    [ "$overall" = "NOINFO" ] && overall="FAIL"
  else
    overall="FAIL"
  fi

  if [ "$overall" = "PASS" ]; then
    CNT_PASS=$((CNT_PASS + 1))
  else
    CNT_MISSING=$((CNT_MISSING + 1))
    MISSING_LIST="${MISSING_LIST} ${slug}"
  fi

  row="$(printf '%-26s %-7s %-7s %-12s %-11s %s' "$slug" "$g_hook" "$g_agent" "$g_controller" "$g_scheduler" "$overall")"
  TABLE_ROWS="${TABLE_ROWS}${row}"$'\n'

  # Diagnostics for non-PASS boxes: NOTE and REMOTE-ERROR lines only (the
  # marker contract forbids secret values in either).
  if [ "$overall" != "PASS" ]; then
    diag="$(grep -E '^(NOTE|REMOTE-ERROR):' "$OUT_FILE" 2>/dev/null || true)"
    if [ -n "$diag" ]; then
      while IFS= read -r dline; do
        row="$(printf '%-26s %s' "" "$dline")"
        TABLE_ROWS="${TABLE_ROWS}${row}"$'\n'
      done <<EOF
$diag
EOF
    fi
  fi
done <<EOF
$ROWS
EOF

# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #
log ""
printf '%s\n' "FLEET STATUS TABLE"
printf '%-26s %-7s %-7s %-12s %-11s %s\n' "box" "hook" "agent" "controller" "scheduler" "overall"
printf '%-26s %-7s %-7s %-12s %-11s %s\n' "--------------------------" "-------" "-------" "------------" "-----------" "-------"
printf '%s' "$TABLE_ROWS"

log ""
log "==== PODCAST ACTIVATION AUDIT SUMMARY ===="
log "boxes in roster              : ${BOX_COUNT}"
log "healthy (overall PASS)       : ${CNT_PASS}"
log "missing processor (FAIL)     : ${CNT_MISSING}"
log "unreachable                  : ${CNT_UNREACHABLE}"
log "skipped (no transport info)  : ${CNT_SKIP}"
if [ -n "$MISSING_LIST" ]; then
  log "boxes missing the processor  :${MISSING_LIST}"
fi
if [ -n "$UNREACHABLE_LIST" ]; then
  log "unreachable boxes            :${UNREACHABLE_LIST}"
fi
if [ -n "$SKIP_LIST" ]; then
  log "skipped boxes                :${SKIP_LIST}"
fi
log "==========================================="
log ""

if [ "$CNT_PASS" -eq "$BOX_COUNT" ]; then
  log "RESULT: fleet podcast activation is HEALTHY (all ${BOX_COUNT} box(es) PASS)"
  exit 0
fi
log "RESULT: fleet podcast activation is NOT healthy (${CNT_MISSING} missing, ${CNT_UNREACHABLE} unreachable, ${CNT_SKIP} skipped of ${BOX_COUNT})"
exit 1
