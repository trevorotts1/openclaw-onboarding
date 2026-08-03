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
#     hook           inbound intake webhook routes registered for the box's
#                    provisioned clients
#     agent          the podcast department agent registered on the box
#     intake-runner  the production processor (controller) runnable AND
#                    scheduled; the engine is no-daemon by design, so the
#                    scheduled heartbeat IS the runner's proof of life
#
#   Output is a fleet status table (box | hook | agent | intake-runner |
#   overall) plus a summary that counts how many boxes are unhealthy.
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
# REMOTE CHECK (read-only, guard-first)
#   Per box the audit runs the activation guard that ships with the skill:
#       <box skills>/58-podcast-production-engine/scripts/guard-activation-health.py
#   Mode selection, per the guard's own severity model:
#     --repo-only  when the box does NOT declare itself provisioned
#     --strict     (full mode: repo + on-box) when the box declares itself
#                  provisioned in its OWN environment:
#                  $PODCAST_ACTIVATION_PROVISIONED=1 or a non-empty
#                  $PODCAST_CLIENT_SLUGS, both read on the box, never shipped
#                  in from the audit host. The guard itself reads the slugs
#                  from $PODCAST_CLIENT_SLUGS.
#   --strict keeps every on-box FAIL fatal; without it the guard downgrades
#   on-box findings on an unprovisioned box to non-fatal warnings and its
#   RESULT line would overstate box health. The guard's exit code is NOT
#   trusted for grading; only its printed grammar is. When the guard script is
#   absent from the box (or emits no parseable check lines), a built-in
#   repo-only fallback probe runs and emits the same grammar for R1-R3 only.
#   Either way the audit:
#     - NEVER installs, writes, restarts, or mutates anything on a box.
#     - NEVER reads or prints secret values. The guard prints presence,
#       behavior, and SET/NOT-SET only; the fallback probe prints paths only.
#
# GUARD OUTPUT GRAMMAR PARSED (text mode, never --json)
#   header     : "== Podcast Production Engine :: guard-activation-health =="
#                "  mode: <mode> | repo root: <root>"
#   check line : "  [<STATUS>] <id> <title> : <detail>" with STATUS in
#                PASS|FAIL|SKIP (WARN is reserved but never assigned to a
#                check line), id in R1,R2,R3 (repo presence) and B1..B5
#                (on-box activation)
#   verdict    : "RESULT: PASS - ..."  or
#                "RESULT: FAIL (fail-closed) - <n> fatal finding(s):"
#                the FAIL form is followed by one line per fatal finding:
#                "  [AF-PPE-ACTIVATION-REPO|AF-PPE-ACTIVATION-BOX] <id> : <detail>"
#                then optional "  [non-fatal WARN] ..." / "  [SKIP] ..." lines
#   The audit additionally tolerates NOTE: <text> and REMOTE-ERROR: <text>
#   diagnostic lines from the payload. A box whose output carries no RESULT
#   line and no check line is graded UNREACHABLE (fail-closed); a box with
#   check lines but no RESULT line is graded FAIL (fail-closed).
#
# CHECK-ID TO COLUMN MAPPING (honest per the guard's actual semantics)
#   hook          <- B4 "intake webhook routes registered": a route
#                    podcast-intake-<slug> exists in the box openclaw.json for
#                    every configured client slug (route ids only; the route
#                    objects embed secrets and are never read or printed).
#                    B4 SKIP means no slug is configured on that box; per the
#                    guard's non-FAIL semantics the column grades PASS and a
#                    note records the skip.
#   agent         <- B2 "podcast department agent registered": a NON-EMPTY
#                    agents/dept-podcast directory (an empty dir routes intake
#                    to the wrong session and FAILs).
#   intake-runner <- B5 "controller runnable and scheduled": the guard bundles
#                    the runner (podcast_controller.py --help exits 0) and the
#                    scheduler (crontab entry or launchd plist naming the
#                    controller or installer) into ONE check; this column
#                    cannot split them.
#   overall       <- the guard's RESULT line, the authoritative verdict. It
#                    also covers the checks that have no dedicated column:
#                    R1-R3 (activation files present in the build), B1 (the
#                    three scripts installed on the box), B3 (loopback
#                    TaskFlow gateway reachable).
#   Boxes audited in --repo-only mode show "-" for hook/agent/intake-runner
#   (the guard emitted no B lines) and their overall comes from R1-R3 only.
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
# ENV (audit host)
#   PODCAST_BOX_REGISTRY   registry path override
#   PODCAST_OC_ROOT_LOCAL  audit the local box against this root instead of
#                          $HOME/.openclaw (sandbox/test use only)
# ENV (read on each box, never shipped in)
#   PODCAST_ACTIVATION_PROVISIONED  =1 marks the box provisioned (full mode)
#   PODCAST_CLIENT_SLUGS            comma list of provisioned client slugs;
#                                   non-empty also marks the box provisioned
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

usage() { awk 'NR > 4 { if ($0 ~ /^# ====+ *$/) exit; print }' "$0" | sed 's/^# \{0,1\}//'; }

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
# the local box). STRICTLY READ-ONLY: it runs the guard's bounded read-only
# probes (file presence, an HTTP HEAD to the loopback gateway, crontab/launchd
# listing reads), writes nothing, installs nothing, restarts nothing, and
# never reads or prints a secret value. Preamble variables (exported by the
# caller): OC_ROOT_ARG  the box's OpenClaw root   BOX_SLUG  the box's slug
# --------------------------------------------------------------------------- #
remote_payload() {
cat <<'PAYLOAD'
set -u
OC_ROOT="${OC_ROOT_ARG:-}"
[ -n "$OC_ROOT" ] || { echo "REMOTE-ERROR: OC_ROOT_ARG not supplied"; echo "RESULT: FAIL (fail-closed) - audit payload misuse"; exit 1; }

SKILL_DIR=""
for c in "$OC_ROOT"/skills/58-podcast*; do
  [ -d "$c" ] || continue
  SKILL_DIR="$c"
  break
done

# Provisioned status is declared by the BOX's own environment, never shipped
# in from the audit host: PODCAST_ACTIVATION_PROVISIONED=1 or any configured
# client slug in PODCAST_CLIENT_SLUGS. The guard reads the slugs itself.
PROVISIONED=0
if [ "${PODCAST_ACTIVATION_PROVISIONED:-}" = "1" ]; then PROVISIONED=1; fi
if [ -n "${PODCAST_CLIENT_SLUGS:-}" ]; then PROVISIONED=1; fi

GUARD="$SKILL_DIR/scripts/guard-activation-health.py"

run_guard() {
  if [ ! -f "$GUARD" ]; then
    echo "NOTE: guard-activation-health.py not present under ${SKILL_DIR:-$OC_ROOT/skills}; built-in repo-only probe ran"
    return 1
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    echo "REMOTE-ERROR: python3 not present on this box"
    return 1
  fi
  if [ "$PROVISIONED" = "1" ]; then
    # Full mode (repo + on-box). --strict keeps every on-box FAIL fatal so
    # the RESULT line is the true verdict for this box.
    gout="$(python3 "$GUARD" --strict 2>&1)" || true
  else
    # Repo-only mode: the CI/merge-gate surface (R1-R3).
    gout="$(python3 "$GUARD" --repo-only 2>&1)" || true
  fi
  printf '%s\n' "$gout"
  if printf '%s\n' "$gout" | grep -qE '^[[:space:]]*\[(PASS|FAIL|WARN|SKIP)\] [A-Za-z0-9]+ '; then
    return 0
  fi
  echo "NOTE: guard-activation-health.py emitted no parseable check lines; built-in repo-only probe ran"
  return 1
}

# Built-in fallback probe: mirrors the guard's repo-only surface (R1-R3) in
# the guard's own grammar. A box without the guard cannot self-report on-box
# state, so no B lines are emitted and the audit shows "-" for those columns.
lightweight_probe() {
  if ! command -v python3 >/dev/null 2>&1; then
    echo "REMOTE-ERROR: python3 not present on this box; cannot probe"
    for cid in R1 R2 R3; do
      echo "  [FAIL] $cid activation layer file : python3 unavailable, cannot check"
    done
    echo "RESULT: FAIL (fail-closed) - 3 fatal finding(s):"
    return 0
  fi
  SKILL_DIR="$SKILL_DIR" python3 - <<'PY'
import os

skill = os.environ.get("SKILL_DIR", "")
files = (
    ("R1", "register-podcast-hook.sh", "intake hook registration script"),
    ("R2", "podcast_controller.py", "production processor (controller)"),
    ("R3", "install-podcast-department.sh", "department + scheduler installer"),
)
fatal = 0
for cid, name, what in files:
    path = os.path.join(skill, "scripts", name) if skill else ""
    if skill and os.path.isfile(path):
        print("  [PASS] %s %s : present: %s" % (cid, what, path))
    else:
        fatal += 1
        suffix = "" if skill else " (skill 58 directory not found)"
        print("  [FAIL] %s %s : MISSING: %s%s" % (cid, what, name, suffix))
if fatal:
    print("RESULT: FAIL (fail-closed) - %d fatal finding(s):" % fatal)
else:
    print("RESULT: PASS - the activation layer is present.")
PY
}

if ! run_guard; then
  lightweight_probe
fi
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

# Guard-grammar parsers (see GUARD OUTPUT GRAMMAR PARSED in the header).
status_of() { # $1=guard check id -> PASS|FAIL|SKIP|WARN|"" (first line wins)
  sed -n -E "s/^[[:space:]]*\[(PASS|FAIL|WARN|SKIP)\] $1 .*/\1/p" "$OUT_FILE" 2>/dev/null \
    | head -n 1
}

col_grade() { # $1=raw check status -> fleet table cell
  case "$1" in
    PASS) printf 'PASS' ;;
    SKIP) printf 'PASS' ;;   # the guard's non-FAIL semantics; noted separately
    WARN) printf 'WARN' ;;
    FAIL) printf 'FAIL' ;;
    *)    printf -- '-' ;;   # check not emitted (e.g. --repo-only mode)
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
    row="$(printf '%-26s %-7s %-7s %-14s %s' "$slug" "-" "-" "-" "$state")"
    TABLE_ROWS="${TABLE_ROWS}${row}"$'\n'
    continue
  fi

  # The grammar, not the transport or the exit code, grades the box. No
  # RESULT line AND no check line means nothing parseable came back: dark.
  has_result=0
  if grep -q '^RESULT: ' "$OUT_FILE" 2>/dev/null; then has_result=1; fi
  has_checks=0
  if grep -qE '^[[:space:]]*\[(PASS|FAIL|WARN|SKIP)\] [A-Za-z0-9]+ ' "$OUT_FILE" 2>/dev/null; then has_checks=1; fi
  if [ "$transport_rc" != "0" ] || { [ "$has_result" != "1" ] && [ "$has_checks" != "1" ]; }; then
    CNT_UNREACHABLE=$((CNT_UNREACHABLE + 1))
    UNREACHABLE_LIST="${UNREACHABLE_LIST} ${slug}"
    row="$(printf '%-26s %-7s %-7s %-14s %s' "$slug" "-" "-" "-" "UNREACHABLE")"
    TABLE_ROWS="${TABLE_ROWS}${row}"$'\n'
    continue
  fi

  s_hook="$(status_of B4)"
  s_agent="$(status_of B2)"
  s_runner="$(status_of B5)"
  g_hook="$(col_grade "$s_hook")"
  g_agent="$(col_grade "$s_agent")"
  g_runner="$(col_grade "$s_runner")"

  # Overall comes from the guard's RESULT line (authoritative). Check lines
  # with no RESULT line grade FAIL, fail-closed.
  if grep -q '^RESULT: PASS' "$OUT_FILE" 2>/dev/null; then
    overall="PASS"
  else
    overall="FAIL"
  fi

  if [ "$overall" = "PASS" ]; then
    CNT_PASS=$((CNT_PASS + 1))
  else
    CNT_MISSING=$((CNT_MISSING + 1))
    MISSING_LIST="${MISSING_LIST} ${slug}"
  fi

  row="$(printf '%-26s %-7s %-7s %-14s %s' "$slug" "$g_hook" "$g_agent" "$g_runner" "$overall")"
  TABLE_ROWS="${TABLE_ROWS}${row}"$'\n'

  if [ "$s_hook" = "SKIP" ]; then
    row="$(printf '%-26s %s' "" "note: hook graded PASS from B4 SKIP (no client slugs configured on the box)")"
    TABLE_ROWS="${TABLE_ROWS}${row}"$'\n'
  fi

  # Diagnostics: payload NOTE / REMOTE-ERROR lines surface for every box
  # (they are audit telemetry and, by contract, never carry secret values);
  # the guard's fatal finding lines are attached under non-PASS boxes.
  diag="$(grep -E '^(NOTE|REMOTE-ERROR):' "$OUT_FILE" 2>/dev/null || true)"
  if [ "$overall" != "PASS" ]; then
    diag="${diag}
$(grep -E '^[[:space:]]*\[AF-PPE-' "$OUT_FILE" 2>/dev/null || true)"
  fi
  diag="$(printf '%s\n' "$diag" | sed '/^[[:space:]]*$/d')"
  if [ -n "$diag" ]; then
    while IFS= read -r dline; do
      row="$(printf '%-26s %s' "" "$dline")"
      TABLE_ROWS="${TABLE_ROWS}${row}"$'\n'
    done <<EOF
$diag
EOF
  fi
done <<EOF
$ROWS
EOF

# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #
log ""
printf '%s\n' "FLEET STATUS TABLE"
printf '%-26s %-7s %-7s %-14s %s\n' "box" "hook" "agent" "intake-runner" "overall"
printf '%-26s %-7s %-7s %-14s %s\n' "--------------------------" "-------" "-------" "--------------" "-------"
printf '%s' "$TABLE_ROWS"

log ""
log "==== PODCAST ACTIVATION AUDIT SUMMARY ===="
log "boxes in roster              : ${BOX_COUNT}"
log "healthy (overall PASS)       : ${CNT_PASS}"
log "unhealthy (overall FAIL)     : ${CNT_MISSING}"
log "unreachable                  : ${CNT_UNREACHABLE}"
log "skipped (no transport info)  : ${CNT_SKIP}"
if [ -n "$MISSING_LIST" ]; then
  log "unhealthy boxes              :${MISSING_LIST}"
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
log "RESULT: fleet podcast activation is NOT healthy (${CNT_MISSING} unhealthy, ${CNT_UNREACHABLE} unreachable, ${CNT_SKIP} skipped of ${BOX_COUNT})"
exit 1
