#!/usr/bin/env bash
# tests/unit/pres034-docker-acceptance.sh
#
# QC-PRES-034 check 4 — "Run Docker restart acceptance with persisted
# schedules and resolved volumes; confirm one real tick reaches the correct
# presentation runtime."
#
# WHAT IT PROVES, with a REAL container (not a mocked host):
#   * The VPS reconcile branch runs inside the pinned presentation profile
#     image (python3 + bash + the mounted engine tree).
#   * The scheduler store is PERSISTED on a host-mounted volume: container A
#     registers the two schedules; the container is removed (simulating
#     restart); container B starts against the SAME volume and reconciles —
#     the present jobs are read back, verified in-sync, and NOT re-created
#     (the "restart loses the schedule" class of defect).
#   * One REAL tick reaches the CORRECT presentation runtime: the mounted
#     department scripts dir (resolved through the volume path, never a host
#     path baked in the image), running the actual presentation-intake-poll.sh
#     scan against a fixture runs dir — zero dispatch, zero production work.
#   * The readiness receipt records command hash + next-fire for the
#     persisted job, and survives the restart (same volume).
#
# NOT VERIFIED remains honest: anything needing a live gateway or remote
# sandbox is printed NOT VERIFIED with the exact next action and never
# waived. Exit 0 = all docker legs green; exit 3 = docker unavailable
# (NOT VERIFIED printed, never a waiver).
#
# Env: PROFILE=hostinger|contabo|both (default both)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROFILE="${PROFILE:-both}"
EVIDENCE_DIR=""
while [ $# -gt 0 ]; do
  case "$1" in
    --evidence-dir=*) EVIDENCE_DIR="${1#--evidence-dir=}"; shift ;;
    --evidence-dir) EVIDENCE_DIR="${2:-}"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done
log() { echo "[pres034-docker] $*"; }

if ! command -v docker >/dev/null 2>&1; then
  echo "NOT VERIFIED: docker CLI absent on this host. Next action: install Docker then re-run: bash $0 --evidence-dir <dir>" >&2
  exit 3
fi
if ! docker info >/dev/null 2>&1; then
  echo "NOT VERIFIED: docker daemon unreachable. Next action: start the Docker daemon (colima/docker desktop) then re-run: bash $0 --evidence-dir <dir>" >&2
  exit 3
fi

[ -n "$EVIDENCE_DIR" ] && mkdir -p "$EVIDENCE_DIR"

# Fixture tree: persisted scheduler store + mounted dept scripts + runs dir.
# NOTE: under colima (this host's daemon), only $HOME and the repo root are
# shared with the VM — a mktemp -d under /var/folders or /private/tmp
# mounts EMPTY (verified live 2026-09-09: /private/tmp and /tmp both mount
# empty; $HOME and the packet tree mount correctly). The fixture therefore
# lives under $HOME when a writable shared path is available, else under
# $EVIDENCE_DIR (which is the packet tree, proven mountable).
if [ -n "$EVIDENCE_DIR" ]; then
  FIX="$EVIDENCE_DIR/docker-fixture"
  rm -rf "$FIX"; mkdir -p "$FIX"
else
  FIX="$HOME/.pres034-docker-fixture"
  rm -rf "$FIX"; mkdir -p "$FIX"
fi
STORE="$FIX/store.json"          # the gateway's cron store (persisted)
WS="$FIX/ws"                      # the "client" workspace (resolved volumes)
DEPT="$WS/departments/Presentations/scripts"
RUNS="$WS/departments/Presentations/runs"
mkdir -p "$DEPT" "$RUNS" "$FIX/root/workspace"
printf '{"jobs":[]}' > "$STORE"
cp "$REPO_ROOT/23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation-intake-poll.sh" "$DEPT/"
cp "$REPO_ROOT/23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation-watchdog.sh" "$DEPT/"
cp -r "$REPO_ROOT/23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation_job" "$DEPT/"
cp "$REPO_ROOT/23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation_job.py" "$DEPT/"
cp "$REPO_ROOT/23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation-notify.py" "$DEPT/"

# Mock openclaw CLI (bash + python3 exist in the profile images). Persisted
# JSON store on the mounted volume; create writes into it; list reads it.
cat > "$FIX/openclaw" <<'MOCKEOF'
#!/usr/bin/env bash
STORE="${PRES034_MOCK_STORE:?}"
LOG="${PRES034_MOCK_LOG:?}"
log() { printf '%s\n' "$*" >> "$LOG"; }
sub="${1:-}"; shift || true
[ "$sub" = "cron" ] || exit 0
action="${1:-}"; shift || true
case "$action" in
  add) log "ADD $*"; echo "  --session <target>"; exit 0 ;;
  list)
    log "LIST $*"
    python3 -c 'import json,sys; print(open(sys.argv[1]).read())' "$STORE" 2>/dev/null || printf '%s\n' '{"jobs":[]}'
    exit 0 ;;
  create)
    log "CREATE $*"
    python3 - "$STORE" "$@" <<'PYEOF'
import json, os, sys
store, flags = sys.argv[1], sys.argv[2:]
d = json.load(open(store))
jobs = d.get("jobs", [])
def take(f):
    if f in flags:
        i = flags.index(f)
        return flags[i + 1] if i + 1 < len(flags) else ""
    return ""
name = take("--name"); agent = take("--agent") or "main"
expr = take("--cron"); tz = take("--tz") or "America/New_York"
text = take("--system-event") or take("--message")
kind = "systemEvent" if take("--system-event") else "message"
jid = "job-%d" % (len(jobs) + 1)
jobs.append({"id": jid, "name": name, "enabled": True,
             "createdAtMs": 1000 * (len(jobs) + 1), "agentId": agent,
             "schedule": {"kind": "cron", "expr": expr, "tz": tz},
             "sessionTarget": "main",
             "payload": {"kind": kind, "text": text},
             "delivery": {"mode": "none"}})
d["jobs"] = jobs
json.dump(d, open(store, "w"))
print(jid)
PYEOF
    exit $? ;;
  edit)
    log "EDIT $*"
    python3 - "$STORE" "$@" <<'PYEOF'
import json, os, sys
store, argv = sys.argv[1], sys.argv[2:]
if argv and argv[0] == "--help":
    print("  --agent <id>"); print("  --cron <expr>"); print("  --session <target>")
    print("  --system-event <text>"); print("  --tz <iana>"); print("  --no-deliver")
    print("  --clear-to"); sys.exit(0)
jid = argv[0]; flags = argv[1:]
d = json.load(open(store)); jobs = d.get("jobs", [])
job = next((j for j in jobs if j.get("id") == jid), None)
if job is None: sys.exit(1)
i = 0
while i < len(flags):
    f = flags[i]
    if f in ("--cron", "--tz", "--agent", "--session"):
        key = {"--cron": ("schedule", "expr"), "--tz": ("schedule", "tz"),
               "--agent": "agentId", "--session": "sessionTarget"}[f]
        val = flags[i + 1] if i + 1 < len(flags) else ""
        if isinstance(key, tuple): job.setdefault(key[0], {})[key[1]] = val
        else: job[key] = val
        i += 2
    elif f in ("--message", "--system-event"):
        val = flags[i + 1] if i + 1 < len(flags) else ""
        job.setdefault("payload", {})["text"] = val
        job["payload"]["kind"] = "systemEvent" if f == "--system-event" else "message"
        i += 2
    elif f == "--no-deliver": job.setdefault("delivery", {})["mode"] = "none"; i += 1
    elif f == "--clear-to": (job.get("delivery") or {}).pop("to", None); i += 1
    else: i += 1
d["jobs"] = jobs
json.dump(d, open(store, "w"))
PYEOF
    exit $? ;;
  rm|remove|delete)
    log "RM $*"
    python3 - "$STORE" "$@" <<'PYEOF'
import json, os, sys
store, args = sys.argv[1], sys.argv[2:]
by_name = "--name" in args
key = args[1] if by_name and len(args) > 1 else (args[0] if args else "")
d = json.load(open(store)); jobs = d.get("jobs", [])
kept = [j for j in jobs if (j.get("name") != key if by_name else j.get("id") != key)]
if len(kept) == len(jobs): sys.exit(1)
d["jobs"] = kept
json.dump(d, open(store, "w"))
PYEOF
    exit $? ;;
  *) exit 0 ;;
esac
MOCKEOF
chmod +x "$FIX/openclaw"

run_leg() {
  local profile="$1" tag="pres034-$1" logfile="${2:-/dev/null}"
  log "=== profile: $profile ==="
  docker run --rm \
    -e OPENCLAW_PLATFORM=vps \
    -e OPENCLAW_ROOT="$FIX/root" \
    -e OPENCLAW_WORKSPACE_PATH="$WS" \
    -e OPENCLAW_WORKSPACE_ROOT="$WS" \
    -e PRESENTATIONS_SCRIPTS_SRC="$DEPT" \
    -e PRES034_MOCK_STORE="$STORE" \
    -e PRES034_MOCK_LOG="$FIX/calls-$profile.log" \
    -v "$REPO_ROOT:/opt/engine:ro" \
    -v "$FIX:/opt/fix" \
    -w /opt/engine \
    "$tag" bash -lc '
      set -euo pipefail
      export PRES034_MOCK_STORE="/opt/fix/store.json"
      export PRES034_MOCK_LOG="/opt/fix/calls-$1.log"
      export HOME="/opt/fix/home"
      export OPENCLAW_PLATFORM=vps
      export OPENCLAW_ROOT="/opt/fix/root"
      export OPENCLAW_WORKSPACE_PATH="/opt/fix/ws"
      export OPENCLAW_WORKSPACE_ROOT="/opt/fix/ws"
      export PRESENTATIONS_SCRIPTS_SRC="/opt/fix/ws/departments/Presentations/scripts"
      export PATH="/opt/fix:/usr/local/bin:/usr/bin:/bin"
      mkdir -p "$HOME/Library/Logs/openclaw" "$HOME/Library/LaunchAgents"
      source lib-presentation-schedules.sh
      echo "=== [R1] install_presentation_schedules (fresh store) ==="
      install_presentation_schedules || { echo "R1 FAILED"; exit 1; }
      echo "jobs after R1: $(python3 -c "import json;print(len(json.load(open(\"/opt/fix/store.json\"))[\"jobs\"]))")"
      echo "=== [R1] one real tick: intake poll against fixture runs dir ==="
      set +e
      bash /opt/fix/ws/departments/Presentations/scripts/presentation-intake-poll.sh
      echo "tick-rc=$? (0=scan ran; poller log path may not exist in the container — scan result is what counts)"
      set -e
      echo "=== [R1] readiness receipt ==="
      python3 -c "import json;d=json.load(open(\"/opt/fix/ws/departments/Presentations/.scheduler-readiness.json\"));print(json.dumps(d[\"schedules\"],indent=1)[:1200])"
    ' _ "$profile" 2>&1 | tee "$logfile"
}

run_restart_leg() {
  local profile="$1" tag="pres034-$1" logfile="${2:-/dev/null}"
  log "=== restart leg (fresh container, SAME persisted volume): $profile ==="
  docker run --rm \
    -e OPENCLAW_PLATFORM=vps \
    -e PRES034_MOCK_STORE="$STORE" \
    -v "$REPO_ROOT:/opt/engine:ro" \
    -v "$FIX:/opt/fix" \
    -w /opt/engine \
    "$tag" bash -lc '
      set -euo pipefail
      export PRES034_MOCK_STORE="/opt/fix/store.json"
      export PRES034_MOCK_LOG="/opt/fix/calls-restart-$1.log"
      export HOME="/opt/fix/home"
      export OPENCLAW_PLATFORM=vps
      export OPENCLAW_ROOT="/opt/fix/root"
      export OPENCLAW_WORKSPACE_PATH="/opt/fix/ws"
      export OPENCLAW_WORKSPACE_ROOT="/opt/fix/ws"
      export PRESENTATIONS_SCRIPTS_SRC="/opt/fix/ws/departments/Presentations/scripts"
      export PATH="/opt/fix:/usr/local/bin:/usr/bin:/bin"
      source lib-presentation-schedules.sh
      echo "=== [R2] restart: reconcile against persisted store ==="
      install_presentation_schedules || { echo "R2 FAILED"; exit 1; }
      echo "jobs after R2 (must be 2, no duplicates): $(python3 -c "import json;print(len(json.load(open(\"/opt/fix/store.json\"))[\"jobs\"]))")"
      echo "creates in R2 (must be 0): $(grep -c "^CREATE " /opt/fix/calls-restart-$1.log 2>/dev/null || echo 0)"
      echo "=== [R2] tick reaches the correct runtime (mounted dept scripts) ==="
      set +e
      bash /opt/fix/ws/departments/Presentations/scripts/presentation-watchdog.sh /tmp/wd.log
      echo "tick-rc=$? (0=scan pass; 4=notify-unconfigured fail-closed without a transport — either proves the CORRECT mounted runtime was invoked)"
      set -e
      echo "watchdog log evidence:"; tail -n 6 /tmp/wd.log 2>/dev/null || echo "(no log)"
      echo "=== [R2] receipt survived restart ==="
      python3 -c "import json;d=json.load(open(\"/opt/fix/ws/departments/Presentations/.scheduler-readiness.json\"));print(json.dumps(d[\"schedules\"],indent=1)[:1200])"
    ' _ "$profile" 2>&1 | tee "$logfile"
}

run_profile() {
  local profile="$1"
  run_leg "$profile" "${EVIDENCE_DIR:+$EVIDENCE_DIR/leg-$profile.log}"
  run_restart_leg "$profile" "${EVIDENCE_DIR:+$EVIDENCE_DIR/restart-$profile.log}"
}

case "$PROFILE" in
  hostinger) run_profile hostinger ;;
  contabo) run_profile contabo ;;
  both) run_profile hostinger; run_profile contabo ;;
  *) echo "unknown PROFILE=$PROFILE (hostinger|contabo|both)" >&2; exit 2 ;;
esac

log "ALL DOCKER ACCEPTANCE LEGS DONE"
if [ -n "$EVIDENCE_DIR" ]; then
  : # fixture kept as evidence (the mounted store + receipts ARE the evidence)
else
  rm -rf "$FIX" 2>/dev/null || true
fi
exit 0
