#!/usr/bin/env bash
# =============================================================================
# fleet-refresh.sh — PRD item 1.11
# =============================================================================
# The ONE way changes reach clients (all three layers):
#   Layer 1 — pull the pinned onboarding + CC versions (deployed = merged)
#   Layer 2 — sessions.reset the CEO/main agent (loaded = deployed)
#   Layer 3 — verify the marker is in the INJECTED system prompt, NOT just on disk
#
# Architecture (mirrors migrate-zhc-to-master-files.sh):
#   This script = bash wrapper: flags, box fan-out, concurrency, isolation.
#   shared-utils/fleet_refresh_runner.py = per-box 8-step state machine + verifier.
#
# USAGE:
#   bash scripts/fleet-refresh.sh                    # DRY-RUN (default — safe, read-only)
#   bash scripts/fleet-refresh.sh --apply            # deploy to every box in the fleet
#   bash scripts/fleet-refresh.sh --box <name>       # restrict to one box (repeatable)
#   bash scripts/fleet-refresh.sh --boxes-file <f>   # explicit box manifest (JSON)
#   bash scripts/fleet-refresh.sh --local            # run against THIS box only (no SSH)
#   bash scripts/fleet-refresh.sh --verify-only      # read-only verifier sweep (no pull/build/reset)
#   bash scripts/fleet-refresh.sh --max-parallel N   # concurrency cap (default 8)
#   bash scripts/fleet-refresh.sh --force-cc         # stash CC dirty tree instead of aborting
#   bash scripts/fleet-refresh.sh --expected-sha <s> # inform verifier of expected onboarding SHA
#   bash scripts/fleet-refresh.sh --wave first|rest  # only the boxes-file entries in that wave
#                                                    # (implies --boxes-file ~/.openclaw/fleet/boxes.json)
#   bash scripts/fleet-refresh.sh --help
#
# ROLL ORDER (see scripts/make-fleet-boxes-file.py):
#   1. operator box:  bash scripts/fleet-refresh.sh --local --apply
#   2. first three client boxes (one Mac, one Hostinger, one Contabo):
#                     bash scripts/fleet-refresh.sh --wave first --apply
#   3. every other client box: bash scripts/fleet-refresh.sh --wave rest --apply
#   Each run ends with a one-screen UPDATED / ROLLED_BACK / FAILED / SKIPPED table.
#   Every box is snapshotted first, then checked after the update: health
#   (gateway, Telegram getMe, Command Center, session reset) AND content (persona
#   index + embeddings, SOP library + embeddings, role library, departments).
#   A failed check is FIXED first, up to 3 attempts (restart the gateway, re-run
#   the failed step, rebuild the Command Center); only then is the box rolled
#   back to its snapshot. Roll-backs and failures alert the OPERATOR (Telegram
#   via his own agent's bot, plus email on his Mac). No client is ever messaged.
#
# BOX MANIFEST FORMAT (--boxes-file):
#   JSON array of objects:
#   [
#     {
#       "client": "Client Name",         # whose box it is: every line and alert names
#                                        # the box "Client Name (Platform)", never its id
#       "name": "client-box-01",
#       "ssh_target": "clientuser@<host>",
#       "cf_tunnel_id": "bfbd47ae...",
#       "cf_access_env_prefix": "CF_ACCESS_CLIENT",
#       "platform": "mac",               # mac | hostinger | contabo
#       "container": "<name>",           # optional: run inside it via docker exec
#       "docker_exec_user": "node",      # optional (default node)
#       "openclaw_root": "/path",        # optional: exported as OPENCLAW_ROOT
#       "wave": "first"                  # optional: first | rest (default rest)
#     },
#     ...
#   ]
#
# SAFETY GUARANTEES:
#   • --dry-run is the default.  --apply must be passed explicitly.
#   • NEVER issues `openclaw gateway restart` (Mac err 125 → box DOWN).
#     The gateway is restarted ONLY as a fix attempt after a failed health
#     check: Mac `launchctl kickstart -k` (fallback `launchctl stop`, KeepAlive
#     restarts it); Hostinger `docker compose up -d --force-recreate <service>`
#     and Contabo `docker restart <container>`, both run on the HOST by this script.
#   • Per-box failure is isolated: one box failing never aborts others.
#   • Aggregate exit: 0=all ok; 2=any partial/failed; 3=any unknown (CI-visible nonzero).
#   • CC deploy goes through scripts/atomic-deploy.sh ONLY (B.2).
#     No raw npm build or direct pm2 restart paths exist.
#   • Not a standing loop (loop doctrine): operator-invoked, not a cron.
#
# EXIT CODES:
#   0  all boxes ok (or dry-run completed)
#   1  fatal (e.g., cannot find runner, bad flags)
#   2  at least one box partial or failed
#   3  at least one box UNKNOWN (atomic-deploy exit 3 — CC state indeterminate)
#
# PRD 1.11 — v11.14.0 (WAVE 5)
# =============================================================================
set -euo pipefail

# ── Script location ───────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SHARED_UTILS="$REPO_ROOT/shared-utils"
RUNNER="$SHARED_UTILS/fleet_refresh_runner.py"

# ── Defaults ──────────────────────────────────────────────────────────────────
APPLY=0
VERIFY_ONLY=0
LOCAL=0
FORCE_CC=0
MAX_PARALLEL=8
EXPECTED_SHA=""
BOXES_FILE=""
WAVE=""
declare -a BOX_NAMES=()

# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply)        APPLY=1; shift ;;
    --dry-run)      APPLY=0; shift ;;
    --verify-only)  VERIFY_ONLY=1; shift ;;
    --local)        LOCAL=1; shift ;;
    --force-cc)     FORCE_CC=1; shift ;;
    --box)          BOX_NAMES+=("$2"); shift 2 ;;
    --boxes-file)   BOXES_FILE="$2"; shift 2 ;;
    --max-parallel) MAX_PARALLEL="$2"; shift 2 ;;
    --expected-sha) EXPECTED_SHA="$2"; shift 2 ;;
    --wave)         WAVE="$2"; shift 2 ;;
    --help|-h)
      grep '^#' "$0" | grep -v '^#!/' | sed 's/^# \?//' | head -80
      exit 0
      ;;
    *)
      echo "Unknown flag: $1" >&2
      echo "Run $0 --help for usage." >&2
      exit 1
      ;;
  esac
done

case "$WAVE" in
  ""|first|rest) ;;
  *) echo "FATAL: --wave must be first or rest (got: $WAVE)" >&2; exit 1 ;;
esac
if [ -n "$WAVE" ] && [ -z "$BOXES_FILE" ]; then
  BOXES_FILE="$HOME/.openclaw/fleet/boxes.json"
fi

# ── Sanity checks ─────────────────────────────────────────────────────────────
if [ ! -f "$RUNNER" ]; then
  echo "FATAL: runner not found at $RUNNER" >&2
  echo "Run this script from the openclaw-onboarding repo." >&2
  exit 1
fi

if [ ! -f "$REPO_ROOT/cc-compat.json" ]; then
  echo "FATAL: cc-compat.json not found at $REPO_ROOT/cc-compat.json" >&2
  echo "This file is required for fleet-refresh to know which CC version to deploy." >&2
  exit 1
fi

# ── Wave-5 deploy preflight (FAIL-CLOSED — NO BYPASS) ────────────────────────
# Runs unconditionally BEFORE any box work (including dry-run).
# Blocks the entire fan-out until B.1 + B.2 + B.3 are merged to origin/main of
# trevorotts1/blackceo-command-center.
# There is NO flag and NO env-var that bypasses this check.
wave5_deploy_preflight() {
  local repo="trevorotts1/blackceo-command-center"
  local b1="scripts/cc-health-check.sh"
  local b2="scripts/atomic-deploy.sh"
  # B.3 duck-test: probe duck-test.ts first (TypeScript source), fall back to
  # duck-test (extensionless/shell).  First 200 wins; both absent = BLOCKED.
  local b3_candidates=("tests/e2e/duck-test.ts" "tests/e2e/duck-test")
  local missing=()

  echo "[fleet-refresh] Wave-5 preflight: checking B.1 + B.2 + B.3 on origin/main of ${repo} ..."

  # ── B.1 and B.2: single-path checks ─────────────────────────────────────────
  for entry in "B.1:${b1}" "B.2:${b2}"; do
    local label="${entry%%:*}"
    local path="${entry#*:}"
    local api_url="https://api.github.com/repos/${repo}/contents/${path}?ref=main"

    local http_code
    local curl_opts=(-s -o /dev/null -w "%{http_code}" --max-time 20)
    if [ -n "${GITHUB_TOKEN:-}" ]; then
      curl_opts+=(-H "Authorization: Bearer ${GITHUB_TOKEN}")
    fi
    curl_opts+=(-H "Accept: application/vnd.github+json" "$api_url")

    if command -v curl >/dev/null 2>&1; then
      http_code=$(curl "${curl_opts[@]}" 2>/dev/null || echo "000")
    else
      http_code="000"
    fi

    if [ "$http_code" = "200" ]; then
      echo "[fleet-refresh]   ${label} PRESENT on main: ${path}"
    else
      missing+=("${label}:${path}:${http_code}")
      echo "[fleet-refresh]   ${label} MISSING on main (HTTP ${http_code}): ${path}" >&2
    fi
  done

  # ── B.3: duck-test path duck-test (duck-test.ts OR duck-test) ───────────────
  # Probes duck-test.ts first; if absent tries extensionless duck-test.
  # Either 200 satisfies the gate.  This makes the preflight resilient to CC
  # repos that ship either the TypeScript source or a compiled/extensionless copy.
  local b3_found=0
  for b3_candidate in "${b3_candidates[@]}"; do
    local b3_url="https://api.github.com/repos/${repo}/contents/${b3_candidate}?ref=main"
    local b3_curl_opts=(-s -o /dev/null -w "%{http_code}" --max-time 20)
    if [ -n "${GITHUB_TOKEN:-}" ]; then
      b3_curl_opts+=(-H "Authorization: Bearer ${GITHUB_TOKEN}")
    fi
    b3_curl_opts+=(-H "Accept: application/vnd.github+json" "$b3_url")

    local b3_http="000"
    if command -v curl >/dev/null 2>&1; then
      b3_http=$(curl "${b3_curl_opts[@]}" 2>/dev/null || echo "000")
    fi

    if [ "$b3_http" = "200" ]; then
      b3_found=1
      echo "[fleet-refresh]   B.3 PRESENT on main: ${b3_candidate}"
      break
    fi
  done

  if [ $b3_found -eq 0 ]; then
    missing+=("B.3:tests/e2e/duck-test{.ts,}:404")
    echo "[fleet-refresh]   B.3 MISSING on main (checked duck-test.ts AND duck-test)" >&2
  fi

  if [ ${#missing[@]} -gt 0 ]; then
    echo "" >&2
    echo "[fleet-refresh] ╔══════════════════════════════════════════════════════════════════╗" >&2
    echo "[fleet-refresh] ║  FATAL: Wave-5 deploy BLOCKED — B.1+B.2+B.3 preflight FAILED    ║" >&2
    echo "[fleet-refresh] ╠══════════════════════════════════════════════════════════════════╣" >&2
    for entry in "${missing[@]}"; do
      local lbl="${entry%%:*}"
      local rest="${entry#*:}"
      local fp="${rest%%:*}"
      echo "[fleet-refresh] ║  MISSING from ${repo} @ main:              ║" >&2
      echo "[fleet-refresh] ║    [${lbl}] ${fp}" >&2
    done
    echo "[fleet-refresh] ╠══════════════════════════════════════════════════════════════════╣" >&2
    echo "[fleet-refresh] ║  Wave 5 is BLOCKED until ALL three paths are merged to main:     ║" >&2
    echo "[fleet-refresh] ║    B.1  scripts/cc-health-check.sh                               ║" >&2
    echo "[fleet-refresh] ║    B.2  scripts/atomic-deploy.sh                                 ║" >&2
    echo "[fleet-refresh] ║    B.3  tests/e2e/duck-test.ts  (or duck-test)                   ║" >&2
    echo "[fleet-refresh] ║                                                                  ║" >&2
    echo "[fleet-refresh] ║  Merge B.1 + B.2 + B.3 to main in blackceo-command-center,      ║" >&2
    echo "[fleet-refresh] ║  then retry.                                                     ║" >&2
    echo "[fleet-refresh] ╚══════════════════════════════════════════════════════════════════╝" >&2
    exit 1
  fi

  echo "[fleet-refresh] Wave-5 preflight PASSED — B.1 + B.2 + B.3 all present on origin/main."
}

wave5_deploy_preflight

# --local --apply updates THIS checkout in place (update-skills.sh hard-syncs it
# to origin/main; a rollback resets it to the snapshot). Never do that to a
# development checkout: require a clean clone on main.
if [ $LOCAL -eq 1 ] && [ $APPLY -eq 1 ] && [ -d "$REPO_ROOT/.git" ]; then
  _branch="$(git -C "$REPO_ROOT" symbolic-ref --quiet --short HEAD 2>/dev/null || echo detached)"
  if [ "$_branch" != "main" ] || [ -n "$(git -C "$REPO_ROOT" status --porcelain --untracked-files=no 2>/dev/null)" ]; then
    echo "FATAL: --local --apply must run from a clean onboarding clone on main" >&2
    echo "       ($REPO_ROOT is on '$_branch'$( [ -n "$(git -C "$REPO_ROOT" status --porcelain --untracked-files=no 2>/dev/null)" ] && printf ' with uncommitted changes')). This run would reset it." >&2
    echo "       Use a dedicated clone, e.g.: git clone https://github.com/trevorotts1/openclaw-onboarding.git ~/clawd/openclaw-onboarding" >&2
    exit 1
  fi
fi

# ── Mode banner ───────────────────────────────────────────────────────────────
if [ $APPLY -eq 1 ]; then
  echo "[fleet-refresh] MODE: APPLY (--apply passed)"
  echo "[fleet-refresh] Will deploy onboarding + CC + reset CEO sessions."
elif [ $VERIFY_ONLY -eq 1 ]; then
  echo "[fleet-refresh] MODE: VERIFY-ONLY (read-only verifier sweep)"
else
  echo "[fleet-refresh] MODE: DRY-RUN (default — no mutations)"
  echo "[fleet-refresh] Pass --apply to perform a real deployment."
fi

# ── Build the flags for the runner ───────────────────────────────────────────
RUNNER_FLAGS=""
[ $APPLY -eq 1 ]       && RUNNER_FLAGS="$RUNNER_FLAGS --apply"
[ $VERIFY_ONLY -eq 1 ] && RUNNER_FLAGS="$RUNNER_FLAGS --verify-only"
[ $LOCAL -eq 1 ]       && RUNNER_FLAGS="$RUNNER_FLAGS --local"
[ $FORCE_CC -eq 1 ]    && RUNNER_FLAGS="$RUNNER_FLAGS --force-cc"
[ -n "$EXPECTED_SHA" ] && RUNNER_FLAGS="$RUNNER_FLAGS --expected-sha $EXPECTED_SHA"

# One commit for the whole roll: a PR merged while the roll runs must not reach
# the boxes that happen to start (or self-sync) after it.
ROLL_SHA=$(git ls-remote "${FLEET_ROLL_REPO_URL:-https://github.com/trevorotts1/openclaw-onboarding.git}" refs/heads/main 2>/dev/null | cut -f1)
[ -n "$ROLL_SHA" ] && echo "[fleet-refresh] Rolling onboarding main at ${ROLL_SHA:0:12}"
# Same for the Command Center: pull-cc and update.sh deploy this commit, not a
# main that moved after the roll started.
ROLL_CC_SHA=$(git ls-remote "${FLEET_ROLL_CC_REPO_URL:-https://github.com/trevorotts1/blackceo-command-center.git}" refs/heads/main 2>/dev/null | cut -f1)
if [ -n "$ROLL_CC_SHA" ]; then
  export CC_UPDATE_TARGET="$ROLL_CC_SHA"
  echo "[fleet-refresh] Rolling Command Center main at ${ROLL_CC_SHA:0:12}"
fi

# ── Resolve box list ──────────────────────────────────────────────────────────
TMPDIR_RESULTS="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_RESULTS"' EXIT
# Per-box runner logs (stderr) are kept after the run for post-mortems.
RUN_LOG_DIR="$HOME/.openclaw/fleet/runs/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$RUN_LOG_DIR" 2>/dev/null && chmod 700 "$HOME/.openclaw/fleet" "$RUN_LOG_DIR" 2>/dev/null || RUN_LOG_DIR="$TMPDIR_RESULTS"

# If --local, run once against this machine with no SSH
if [ $LOCAL -eq 1 ]; then
  echo "[fleet-refresh] Running in LOCAL mode (this box only, no SSH)"
  BOX_NAMES=("local")
fi

# If --boxes-file, load it (optionally filtered to one --wave)
declare -a BOX_ENTRIES=()
if [ -n "$BOXES_FILE" ] && [ $LOCAL -eq 0 ]; then
  if [ ! -f "$BOXES_FILE" ]; then
    echo "FATAL: --boxes-file not found: $BOXES_FILE" >&2
    [ -n "$WAVE" ] && echo "       Generate it with: python3 $REPO_ROOT/scripts/make-fleet-boxes-file.py" >&2
    exit 1
  fi
  while IFS= read -r name; do
    [ -n "$name" ] && BOX_ENTRIES+=("$name")
  done < <(python3 - "$BOXES_FILE" "$WAVE" <<'PY'
import json, sys
entries = json.load(open(sys.argv[1]))
wave = sys.argv[2]
for e in entries:
    if not e.get('name'):
        continue
    w = e.get('wave') or 'rest'
    if wave and w != wave:
        continue
    print(e['name'])
PY
)
  if [ ${#BOX_ENTRIES[@]} -eq 0 ]; then
    echo "FATAL: boxes-file has no valid entries${WAVE:+ in wave '$WAVE'}" >&2
    exit 1
  fi
  echo "[fleet-refresh] Loaded ${#BOX_ENTRIES[@]} boxes from $BOXES_FILE${WAVE:+ (wave: $WAVE)}"
fi

# Every human-facing line names a box by its CLIENT: "Client Name (Platform)".
# box id <TAB> client <TAB> label, from the private boxes file (none: the id).
LABELS_FILE="$TMPDIR_RESULTS/labels.tsv"
: > "$LABELS_FILE"
# A box's own --local run names itself from the client.json the operator's
# roll left beside its roll copy (scripts/fleet-roll-copy.sh).
if [ $LOCAL -eq 1 ]; then
  python3 - > "$LABELS_FILE" <<'PY' || true
import json, os
from pathlib import Path
root = os.environ.get("OPENCLAW_ROOT") or ("/data/.openclaw" if Path("/data/.openclaw").is_dir() else str(Path.home() / ".openclaw"))
try:
    c = json.loads((Path(root) / "fleet-refresh" / "client.json").read_text())
    if c.get("client") and c.get("label"):
        print("\t".join(("local", c["client"], c["label"])))
except (OSError, ValueError):
    pass
PY
elif [ -n "$BOXES_FILE" ] && [ -f "$BOXES_FILE" ]; then
  python3 - "$BOXES_FILE" "$SHARED_UTILS" > "$LABELS_FILE" <<'PY' || true
import json, sys
sys.path.insert(0, sys.argv[2])
from fleet_notify import client_label
for e in json.load(open(sys.argv[1])):
    if e.get('name'):
        client = e.get('client') or f"UNKNOWN CLIENT ({e['name']})"
        print('\t'.join((e['name'], client, client_label({**e, 'client': client}))))
PY
fi
# label_of <box> [id]: "Client Name (Platform)"; with "id", the box id once too:
# "Client Name (Platform, box <id>)" -- for lines used to find a box's log.
label_of() {
  local l
  l=$(awk -F'\t' -v b="$1" '$1 == b { print $3; exit }' "$LABELS_FILE")
  if [ -z "$l" ]; then printf '%s' "$1"
  elif [ "${2:-}" = id ]; then printf '%s' "${l%)}, box $1)"
  else printf '%s' "$l"; fi
}
labels_of() { local b out=""; for b in "$@"; do out="${out:+$out, }$(label_of "$b")"; done; printf '%s' "$out"; }

# Add the client's name to a box result: the runner on the box never knows it.
stamp_client() {
  local box="$1" result_file="$TMPDIR_RESULTS/$1.json" client
  client=$(awk -F'\t' -v b="$box" '$1 == b { print $2; exit }' "$LABELS_FILE")
  [ -n "$client" ] && [ -f "$result_file" ] || return 0
  python3 - "$result_file" "$client" "$(label_of "$box")" <<'PY' || true
import json, sys
d = json.load(open(sys.argv[1]))
d.update(client=sys.argv[2], label=sys.argv[3])
json.dump(d, open(sys.argv[1], "w"))
PY
}

# If specific boxes named, use those
if [ ${#BOX_NAMES[@]} -gt 0 ]; then
  echo "[fleet-refresh] Restricting to boxes: $(labels_of "${BOX_NAMES[@]}")"
fi

# Determine final box set
FINAL_BOXES=()
if [ ${#BOX_NAMES[@]} -gt 0 ]; then
  FINAL_BOXES=("${BOX_NAMES[@]}")
elif [ ${#BOX_ENTRIES[@]} -gt 0 ]; then
  FINAL_BOXES=("${BOX_ENTRIES[@]}")
elif [ $LOCAL -eq 1 ]; then
  FINAL_BOXES=("local")
else
  echo "[fleet-refresh] No boxes specified. Use --local for this box, --box <name>, or --boxes-file <file>."
  echo "[fleet-refresh] In --local mode the runner operates on this machine directly."
  exit 1
fi

echo "[fleet-refresh] Running on ${#FINAL_BOXES[@]} box(es): $(labels_of "${FINAL_BOXES[@]}")"
echo "[fleet-refresh] max-parallel: $MAX_PARALLEL"
echo "[fleet-refresh] per-box logs: $RUN_LOG_DIR"
echo ""

# The runner prints exactly one JSON object as its LAST stdout line; a login
# shell on the box may print banners before it. Keep only that line, or wrap
# the failure as a result object so every box always has one.
finish_result() {
  local box="$1" rc="$2" raw="$3" result_file="$4" prefix="$5"
  if python3 - "$raw" "$result_file" <<'PY'
import json, sys
lines = [l for l in open(sys.argv[1], errors="replace").read().splitlines() if l.strip()]
for line in reversed(lines):
    try:
        obj = json.loads(line)
    except ValueError:
        continue
    if isinstance(obj, dict) and "box" in obj:
        json.dump(obj, open(sys.argv[2], "w"))
        sys.exit(0)
sys.exit(1)
PY
  then
    return 0
  fi
  local msg
  msg="$( { tail -3 "$raw"; tail -3 "$RUN_LOG_DIR/${box}.log" 2>/dev/null; } | tr '\n"\\' '   ' | cut -c1-300)"
  python3 - "$box" "$rc" "$prefix" "$msg" "$result_file" <<'PY'
import json, sys
box, rc, prefix, msg, out = sys.argv[1:6]
json.dump({"box": box, "result": "failed", "outcome": "FAILED",
           "outcome_detail": f"{prefix} exited {rc}: {msg}",
           "errors": [f"{prefix} exited {rc}: {msg}"]}, open(out, "w"))
PY
}

run_box_local() {
  local box="$1"
  local raw="$TMPDIR_RESULTS/${box}.out"
  local rc=0
  # shellcheck disable=SC2086
  python3 "$RUNNER" \
    --box "$box" \
    --shared-utils "$SHARED_UTILS" \
    --repo-root "$REPO_ROOT" \
    $RUNNER_FLAGS \
    > "$raw" 2> "$RUN_LOG_DIR/${box}.log" || rc=$?
  finish_result "$box" "$rc" "$raw" "$TMPDIR_RESULTS/${box}.json" "runner"
}

# Single-quote a string for a remote POSIX shell.
sq() { printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"; }

run_box_ssh() {
  local box="$1"
  local raw="$TMPDIR_RESULTS/${box}.out"
  local result_file="$TMPDIR_RESULTS/${box}.json"

  # One lookup for every field this box needs (tab-separated, empty = unset).
  local fields ssh_target container exec_user oc_root platform cf_prefix
  fields=$(python3 - "$BOXES_FILE" "$box" <<'PY'
import json, sys
for e in json.load(open(sys.argv[1])):
    if e.get('name') == sys.argv[2]:
        print('\t'.join(str(e.get(k) or '-') for k in
              ('ssh_target', 'container', 'docker_exec_user', 'openclaw_root', 'platform', 'cf_access_env_prefix')))
        break
PY
)
  IFS=$'\t' read -r ssh_target container exec_user oc_root platform cf_prefix <<< "$fields" || true
  [ "$container" = "-" ] && container=""
  [ "$exec_user" = "-" ] && exec_user="node"
  [ "$oc_root" = "-" ] && oc_root=""
  [ "$cf_prefix" = "-" ] && cf_prefix=""
  if [ -z "$ssh_target" ] || [ "$ssh_target" = "-" ]; then
    echo "{\"box\":\"$box\",\"result\":\"failed\",\"outcome\":\"FAILED\",\"outcome_detail\":\"ssh_target not found in boxes-file\",\"errors\":[\"ssh_target not found in boxes-file\"]}" > "$result_file"
    return 2
  fi

  # SSH with CF Access service token if available
  local ssh_opts="-o StrictHostKeyChecking=no -o ConnectTimeout=30 -o ServerAliveInterval=30"
  local ssh_extra_env=""
  if [ -n "$cf_prefix" ]; then
    local client_id_var="${cf_prefix}_SVC_CLIENT_ID"
    local secret_var="${cf_prefix}_SVC_CLIENT_SECRET"
    if [ -n "${!client_id_var:-}" ] && [ -n "${!secret_var:-}" ]; then
      ssh_extra_env="CF_ACCESS_CLIENT_ID=${!client_id_var} CF_ACCESS_CLIENT_SECRET=${!secret_var}"
    fi
  fi

  # Where the command runs: inside the client's container (Hostinger /
  # Contabo), or in a login shell on the box (Mac: launchd PATH is not the
  # login PATH, and openclaw / pm2 / node live on the login PATH).
  remote() {
    local cmd="$1"
    if [ -n "$container" ]; then
      local envs=""
      [ -n "$oc_root" ] && envs="-e OPENCLAW_ROOT=$(sq "$oc_root")"
      printf 'docker exec -u %s %s %s bash -lc %s' "$(sq "$exec_user")" "$envs" "$(sq "$container")" "$(sq "$cmd")"
    elif [ "$platform" = "mac" ]; then
      printf 'zsh -lc %s' "$(sq "$cmd")"
    else
      printf 'bash -lc %s' "$(sq "$cmd")"
    fi
  }

  # ── The roll's own copy of the onboarding repo on the box ─────────────────
  # scripts/fleet-roll-copy.sh keeps ONE dedicated clone per box (inside the
  # container on Docker boxes), refreshed to origin/main every run, and the
  # runner runs from it. Whatever old clones the box has (shallow, tag-only,
  # detached) are never used, changed or deleted.
  local copied verdict remote_root prev_sha
  # shellcheck disable=SC2086
  local client_json
  client_json=$(awk -F'\t' -v b="$box" '$1 == b && $2 !~ /^UNKNOWN CLIENT/ { printf "{\"client\": \"%s\", \"label\": \"%s\"}", $2, $3; exit }' "$LABELS_FILE")
  copied=$(env $ssh_extra_env ssh $ssh_opts "$ssh_target" \
    "$(remote "FLEET_CLIENT_JSON=$(sq "$client_json") FLEET_ROLL_SHA=$(sq "$ROLL_SHA")
$(cat "$SCRIPT_DIR/fleet-roll-copy.sh")")" \
    2>>"$RUN_LOG_DIR/${box}.log" | grep -E '^(COPY|COPYFAIL) ' | tail -1 | tr -d '\r' || true)
  if [ -z "$copied" ]; then
    finish_result "$box" 255 /dev/null "$result_file" "ssh (roll copy)"
    return 2
  fi
  if [ "${copied%% *}" = "COPYFAIL" ]; then
    python3 - "$box" "${copied#COPYFAIL }" "$result_file" <<'PY'
import json, sys
box, why, out = sys.argv[1:4]
json.dump({"box": box, "result": "failed", "outcome": "SKIPPED",
           "outcome_detail": f"not updated: the roll's onboarding copy could not be prepared ({why})",
           "errors": [why]}, open(out, "w"))
PY
    return 2
  fi
  read -r _ verdict prev_sha remote_root <<< "$copied"
  echo "[fleet-refresh]   $(label_of "$box") — roll copy of onboarding: $remote_root ($verdict)" >&2

  # --apply: never start under a fleet-refresh already running on the box.
  # The copy's previous SHA is the runner's rollback target for it.
  local prep=""
  if [ $APPLY -eq 1 ]; then
    prep="for L in \"\${OPENCLAW_ROOT:-/nonexistent}\" /data/.openclaw \"\$HOME/.openclaw\"; do
  P=\$(cat \"\$L/.fleet-refresh.lock/pid\" 2>/dev/null) && kill -0 \"\$P\" 2>/dev/null && {
    echo '{\"box\":\"'$box'\",\"result\":\"skipped\",\"outcome\":\"SKIPPED\",\"outcome_detail\":\"another fleet-refresh is running on this box\"}'; exit 0; }
done
export FLEET_PREV_ONBOARDING_SHA=$(sq "${prev_sha#-}")
"
  fi
  # A dropped SSH session must not kill the runner half way through an update
  # or a rollback: ignore SIGHUP and write to files on the box, echoing them
  # back at the end. (If the session does drop, the result stays at $O.)
  # Inside a container the runner cannot restart its own gateway; it asks for
  # it (exit 4, outcome PENDING) and this wrapper does it on the HOST.
  local extra=""
  [ -n "$container" ] && [ $APPLY -eq 1 ] && extra="--host-restart"
  runner_cmd() {   # $1 = shell prefix, $2 = extra runner flags
    printf '%s' "trap '' HUP
${1}${CC_UPDATE_TARGET:+export CC_UPDATE_TARGET=$CC_UPDATE_TARGET
}O=\${TMPDIR:-/tmp}/fleet-refresh-$box.json; E=\${TMPDIR:-/tmp}/fleet-refresh-$box.log
rm -f \"\$O\"
python3 $(sq "$remote_root/shared-utils/fleet_refresh_runner.py") --box $(sq "$box") --shared-utils $(sq "$remote_root/shared-utils") --repo-root $(sq "$remote_root") $RUNNER_FLAGS $2 > \"\$O\" 2> \"\$E\"
rc=\$?; cat \"\$E\" >&2; cat \"\$O\"; exit \$rc"
  }

  local rc=0
  # shellcheck disable=SC2086
  env $ssh_extra_env ssh $ssh_opts "$ssh_target" "$(remote "$(runner_cmd "$prep" "$extra")")" \
    > "$raw" 2>> "$RUN_LOG_DIR/${box}.log" || rc=$?
  finish_result "$box" "$rc" "$raw" "$result_file" "ssh/runner"

  # A dropped SSH session (exit 255) does not stop the runner: it ignores
  # SIGHUP and writes its result on the box. Wait for it there and read that
  # result, instead of reporting a box that updated fine as FAILED.
  if [ "$rc" -eq 255 ]; then
    local waitcmd="for i in \$(seq 1 120); do busy=; for L in \"\${OPENCLAW_ROOT:-/nonexistent}\" /data/.openclaw \"\$HOME/.openclaw\"; do P=\$(cat \"\$L/.fleet-refresh.lock/pid\" 2>/dev/null) && kill -0 \"\$P\" 2>/dev/null && busy=1; done; [ -z \"\$busy\" ] && break; sleep 30; done; cat \"\${TMPDIR:-/tmp}/fleet-refresh-$box.json\" 2>/dev/null"
    local try back_rc=255
    for try in 1 2 3; do
      back_rc=0
      # shellcheck disable=SC2086
      env $ssh_extra_env ssh $ssh_opts "$ssh_target" "$(remote "$waitcmd")" \
        > "$raw.back" 2>> "$RUN_LOG_DIR/${box}.log" || back_rc=$?
      [ "$back_rc" -ne 255 ] && break
      sleep 30
    done
    if [ "$back_rc" -ne 255 ] && grep -q '"box"' "$raw.back" 2>/dev/null; then
      cp "$raw.back" "$raw"
      finish_result "$box" 0 "$raw" "$result_file" "ssh/runner (read back)"
      rc=$(python3 -c '
import json, sys
d = json.load(open(sys.argv[1]))
d["outcome_detail"] = (d.get("outcome_detail") or "") + " (read back from the box after the SSH session dropped)"
json.dump(d, open(sys.argv[1], "w"))
print(4 if d.get("outcome") == "PENDING" else 0)
' "$result_file")
    fi
  fi

  # Fix loop, host half: restart the container the way this platform needs,
  # then let the runner re-check and continue (it caps the attempts at 3).
  local round
  for round in 1 2 3; do
    [ "$rc" -eq 4 ] && [ -n "$container" ] || break
    local state host_cmd host_out
    state=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('heal',{}).get('state_path',''))" "$result_file" 2>/dev/null)
    [ -n "$state" ] || break
    if [ "$platform" = "contabo" ]; then
      # Contabo keeps pm2 and the Command Center identity in the container
      # layer: restart it, never recreate it.
      host_cmd="docker restart $(sq "$container") >/dev/null && echo 'docker restart ok'"
    else
      # Hostinger: 'up -d' (re-reads env), forced so a hung gateway is replaced.
      host_cmd="d=\$(docker inspect -f '{{ index .Config.Labels \"com.docker.compose.project.working_dir\" }}' $(sq "$container")) && svc=\$(docker inspect -f '{{ index .Config.Labels \"com.docker.compose.service\" }}' $(sq "$container")) && [ -n \"\$d\" ] && cd \"\$d\" && docker compose up -d --force-recreate \"\$svc\" >/dev/null 2>&1 && echo \"docker compose up -d --force-recreate \$svc ok\""
    fi
    echo "[fleet-refresh]   $(label_of "$box") — fix attempt needs the gateway restarted: $host_cmd" >&2
    # shellcheck disable=SC2086
    host_out=$(env $ssh_extra_env ssh $ssh_opts "$ssh_target" "$host_cmd; for i in \$(seq 1 24); do [ \"\$(docker inspect -f '{{.State.Running}}' $(sq "$container") 2>/dev/null)\" = true ] && break; sleep 5; done" 2>>"$RUN_LOG_DIR/${box}.log" | tail -1 | tr -d "'\"") || true
    # If the host restart failed, resume WITHOUT --host-restart: the runner
    # records it, carries on with its other fixes, and rolls back if it must.
    local again="--host-restart"
    [ -n "$host_out" ] || { again=""; host_out="FAILED - the host restart did not complete"; }
    rc=0
    # shellcheck disable=SC2086
    env $ssh_extra_env ssh $ssh_opts "$ssh_target" \
      "$(remote "$(runner_cmd "" "$again --continue-heal $(sq "$state") --host-restart-result $(sq "$host_out")")")" \
      > "$raw" 2>> "$RUN_LOG_DIR/${box}.log" || rc=$?
    finish_result "$box" "$rc" "$raw" "$result_file" "ssh/runner (continue-heal)"
  done
  if [ "$rc" -eq 4 ]; then   # never leave a box reported as pending
    python3 - "$result_file" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
d.update(result="failed", outcome="FAILED",
         outcome_detail="a fix needed the container restarted from the host and that could not be completed; "
                        "the box was left mid-fix - check it by hand")
json.dump(d, open(sys.argv[1], "w"))
PY
  fi
}

# As each box finishes: name its client in the result and, on an operator roll,
# tell the operator the moment a box passes (Telegram only; the end-of-run
# alert covers roll-backs and failures, by Telegram and email).
finish_box() {
  stamp_client "$1"
  if [ $APPLY -eq 1 ] && [ $LOCAL -eq 0 ] && [ -f "$TMPDIR_RESULTS/$1.json" ]; then
    python3 "$SHARED_UTILS/fleet_notify.py" --passed "$TMPDIR_RESULTS/$1.json" 2>&1 \
      | sed 's/^/[fleet-refresh] pass note: /' || true
  fi
}

# Track active jobs
declare -a PIDS=()
declare -a PID_BOXES=()

run_with_concurrency() {
  local box="$1"

  # Wait if at max-parallel
  while [ "${#PIDS[@]}" -ge "$MAX_PARALLEL" ]; do
    local new_pids=()
    local new_boxes=()
    for i in "${!PIDS[@]}"; do
      if kill -0 "${PIDS[$i]}" 2>/dev/null; then
        new_pids+=("${PIDS[$i]}")
        new_boxes+=("${PID_BOXES[$i]}")
      fi
    done
    PIDS=("${new_pids[@]+"${new_pids[@]}"}")
    PID_BOXES=("${new_boxes[@]+"${new_boxes[@]}"}")
    [ "${#PIDS[@]}" -ge "$MAX_PARALLEL" ] && sleep 0.5
  done

  if [ $LOCAL -eq 1 ] || [ "$box" = "local" ] || [ -z "$BOXES_FILE" ]; then
    { run_box_local "$box" || true; finish_box "$box"; } &
  else
    { run_box_ssh "$box" || true; finish_box "$box"; } &
  fi
  PIDS+=($!)
  PID_BOXES+=("$box")
}

for box in "${FINAL_BOXES[@]}"; do
  echo "[fleet-refresh] Queuing $(label_of "$box" id)"
  run_with_concurrency "$box"
done

# Wait for all remaining jobs
for pid in "${PIDS[@]+"${PIDS[@]}"}"; do
  wait "$pid" || true
done

echo ""
echo "[fleet-refresh] ═══════════════════════════════════════════"
echo "[fleet-refresh]  FLEET SUMMARY"
echo "[fleet-refresh] ═══════════════════════════════════════════"

# ── Collect + print results ───────────────────────────────────────────────────
ALL_RESULTS="[]"
ALL_OK=1
ANY_FAILED=0
ANY_UNKNOWN=0

for box in "${FINAL_BOXES[@]}"; do
  result_file="$TMPDIR_RESULTS/${box}.json"
  label="$(label_of "$box")"
  if [ ! -f "$result_file" ]; then
    echo "[fleet-refresh]   $label — FATAL: no result file"
    echo "{\"box\":\"$box\",\"result\":\"failed\",\"outcome\":\"FAILED\",\"outcome_detail\":\"no result file\"}" > "$result_file"
    stamp_client "$box"
  fi

  box_result=$(cat "$result_file")

  # Validate JSON
  if ! echo "$box_result" | python3 -c "import json,sys; json.load(sys.stdin)" 2>/dev/null; then
    echo "[fleet-refresh]   $label — FATAL: invalid JSON result"
    echo "$box_result" | head -5
    ANY_FAILED=1
    continue
  fi

  # Extract key fields
  result_val=$(echo "$box_result" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('result','unknown'))")
  onb_ver=$(echo "$box_result" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('onboarding_version','?'))")
  cc_ver=$(echo "$box_result" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('cc_version','?'))")
  loaded=$(echo "$box_result" | python3 -c "import json,sys; d=json.load(sys.stdin); l=d.get('loaded',{}); print('YES' if l.get('present') else 'NO')")
  confidence=$(echo "$box_result" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('loaded',{}).get('loaded_confidence','?'))")
  errors=$(echo "$box_result" | python3 -c "import json,sys; d=json.load(sys.stdin); errs=d.get('errors',[]); print('; '.join(errs[:2]) if errs else '')")
  # B.6: embedding-health outcome (extracted from steps dict)
  emb_health=$(echo "$box_result" | python3 -c "
import json,sys
d=json.load(sys.stdin)
v=d.get('steps',{}).get('embedding-health','not-run')
if v=='pass': print('PASS')
elif v is None or v=='not-run': print('NOT-RUN')
elif str(v).startswith('warn:'): print('WARN')
elif str(v).startswith('failed:'): print('FAIL')
else: print(str(v)[:16])
" 2>/dev/null || echo "?")
  # false-success closer: provisioning-completeness outcome (VERSION+BRANDING+
  # DEPARTMENTS+PERSONAS gate). Surfaced next to embed= so an incompletely-
  # provisioned box is never mistaken for a clean PASS at a glance.
  prov_health=$(echo "$box_result" | python3 -c "
import json,sys
d=json.load(sys.stdin)
v=d.get('steps',{}).get('provisioning-completeness','not-run')
if v=='ok': print('OK')
elif v is None or v=='not-run': print('NOT-RUN')
elif str(v).startswith('failed:'): print('FAIL')
else: print(str(v)[:16])
" 2>/dev/null || echo "?")

  case "$result_val" in
    ok)      icon="✓" ;;
    dry-run) icon="○" ;;
    partial)
      # Check for [exit-3] transient marker in steps — if present, mark UNKNOWN
      # rather than FAILED.  UNKNOWN boxes are retried; on repeated failure they
      # are marked UNKNOWN in the fleet manifest (never destructive on exit-3).
      has_exit3=$(echo "$box_result" | python3 -c "
import json,sys
d=json.load(sys.stdin)
steps=d.get('steps',{})
print('yes' if any('[exit-3]' in str(v) for v in steps.values()) else 'no')
" 2>/dev/null || echo "no")
      if [ "$has_exit3" = "yes" ]; then
        icon="?"; ANY_UNKNOWN=1
        echo "[fleet-refresh]   ? $label — TRANSIENT (exit-3): retry then mark UNKNOWN if repeated"
      else
        icon="△"; ANY_FAILED=1
      fi
      ;;
    unknown) icon="?"; ANY_UNKNOWN=1 ;;
    *)       icon="✗"; ANY_FAILED=1; ALL_OK=0 ;;
  esac

  outcome_val=$(echo "$box_result" | python3 -c "import json,sys; print(json.load(sys.stdin).get('outcome','?'))" 2>/dev/null || echo "?")
  echo "[fleet-refresh]   $icon  $label  [$outcome_val  result=$result_val  onb=$onb_ver  cc=v$cc_ver  loaded=$loaded($confidence)  embed=$emb_health  prov=$prov_health]"
  [ -n "$errors" ] && echo "[fleet-refresh]        ERRORS: $errors"

  # Accumulate into fleet summary JSON
  # (Parsed as JSON, not pasted into Python source: a result's true/false/null
  # made the old paste a NameError, so the summary was always empty.)
  ALL_RESULTS=$(python3 -c "
import json,sys
arr = json.loads(sys.argv[1])
arr.append(json.load(open(sys.argv[2])))
print(json.dumps(arr))
" "$ALL_RESULTS" "$result_file" 2>/dev/null || echo "$ALL_RESULTS")
done

echo "[fleet-refresh] ═══════════════════════════════════════════"

# Write fleet summary
SUMMARY_FILE="$REPO_ROOT/.fleet-refresh-summary.json"
echo "$ALL_RESULTS" | python3 -c "
import json,sys
arr = json.load(sys.stdin)
print(json.dumps(arr, indent=2))
" > "$SUMMARY_FILE" 2>/dev/null || true
echo "[fleet-refresh] Fleet summary written to: $SUMMARY_FILE"

# ── Retirement trigger check (APPLY mode only — never dry-run) ────────────────
# Persists per-box loaded=YES state to the fleet loaded-state manifest.
# When every box in the manifest reports loaded=YES, opens/updates the
# "retire legacy shim + clawd fallbacks" GitHub issue exactly once.
#
# DRY-RUN SAFETY: the retirement_triggered flag is NEVER set during dry-run.
# This was the root cause of the AF4 QC gap: an earlier design persisted
# retirement_triggered=True during --dry-run --update-box, which permanently
# blocked gh issue creation. The correct intent (documented in the original
# code comment: "retirement trigger check with real gh runs once at the end")
# requires that dry-run is fully inert for this path.
LOADED_STATE_FILE="$REPO_ROOT/.fleet-loaded-state.json"
RETIREMENT_ISSUE_TITLE="Retire legacy shim + clawd fallbacks (auto-triggered: all boxes loaded)"
RETIREMENT_ISSUE_LABEL="retirement-tracker"

# Only run the retirement-trigger machinery in APPLY mode, and never for a
# single-box --local run (every box's Sunday run is one): "all boxes loaded"
# is a fleet-wide fact. Dry-run and verify-only are 100% inert for this path.
if [ $APPLY -eq 1 ] && [ $LOCAL -eq 0 ]; then
  python3 - <<PYEOF || echo "[fleet-refresh] WARNING: retirement check failed (non-fatal)" >&2
import json, os, sys, subprocess, time
from pathlib import Path

loaded_state_file = Path("$LOADED_STATE_FILE")
all_results_json  = """$ALL_RESULTS"""
apply             = True
dry_run           = False

# Load the current per-box loaded-state manifest (create if absent).
state = {}
if loaded_state_file.is_file():
    try:
        state = json.loads(loaded_state_file.read_text())
    except Exception:
        state = {}

# Validate the state schema:
#   state["boxes"]              = { box_name: { "loaded": bool, "ts": int, ... } }
#   state["retirement_triggered"] = bool  (set to True once; never unset)
if "boxes" not in state or not isinstance(state["boxes"], dict):
    state["boxes"] = {}
if "retirement_triggered" not in state:
    state["retirement_triggered"] = False

# Parse this run's results and update per-box loaded state.
try:
    results = json.loads(all_results_json)
except Exception:
    results = []

for box_result in results:
    box  = box_result.get("box", "")
    if not box:
        continue
    loaded_present = box_result.get("loaded", {}).get("present", False)
    result_val     = box_result.get("result", "unknown")
    # Only count a box as loaded if the run actually applied (result=ok).
    # A dry-run result is never propagated here (APPLY=1 guard above),
    # but be explicit: dry-run result strings MUST NOT advance the state.
    if result_val in ("ok",):
        state["boxes"][box] = {
            "loaded":    loaded_present,
            "result":    result_val,
            "ts":        int(time.time()),
            "onboarding_version": box_result.get("onboarding_version", "unknown"),
        }

# Persist updated state to the manifest (APPLY only — dry-run never reaches here).
try:
    loaded_state_file.write_text(json.dumps(state, indent=2))
    print(f"[fleet-refresh] Retirement manifest updated: {loaded_state_file}")
except Exception as e:
    print(f"[fleet-refresh] WARNING: could not write loaded-state manifest: {e}", file=sys.stderr)

# Check whether ALL tracked boxes are now loaded=YES.
if not state["boxes"]:
    print("[fleet-refresh] Retirement check: no boxes in manifest yet — skipping")
    sys.exit(0)

all_loaded = all(entry.get("loaded", False) for entry in state["boxes"].values())
not_loaded = [b for b, e in state["boxes"].items() if not e.get("loaded", False)]

print(f"[fleet-refresh] Retirement check: {len(state['boxes'])} boxes tracked; "
      f"not-loaded={not_loaded if not_loaded else '(none)'}")

if not all_loaded:
    print(f"[fleet-refresh] Retirement trigger NOT fired: {len(not_loaded)} box(es) not loaded yet.")
    sys.exit(0)

if state["retirement_triggered"]:
    print("[fleet-refresh] Retirement trigger: all boxes loaded=YES — issue already opened; skipping duplicate create.")
    sys.exit(0)

# ALL boxes loaded=YES and retirement not yet triggered — fire the trigger.
print("[fleet-refresh] RETIREMENT TRIGGER: all boxes loaded=YES — opening/updating retirement tracker issue.")

issue_title  = "$RETIREMENT_ISSUE_TITLE"
issue_label  = "$RETIREMENT_ISSUE_LABEL"
box_list     = "\n".join(f"- {b}" for b in sorted(state["boxes"].keys()))
triggered_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

issue_body = f"""## Automated Retirement Trigger

The fleet-refresh.sh retirement-clock fired because **every tracked box
reports \`loaded=YES\`** (CEO_ORCHESTRATOR_RULE_V2 is in the live system
prompt). The deprecation shim and legacy-root fallbacks documented in
\`docs/LEGACY-RETIREMENT.md\` are now safe to remove.

**Triggered:** {triggered_ts}

**All-loaded boxes ({len(state['boxes'])}):**
{box_list}

## Retirement tasks

Follow the plan in \`docs/LEGACY-RETIREMENT.md\`:

1. Remove the \`roots.extend([HOME / "clawd" / ..., ...])\` blocks from:
   - \`32-command-center-setup/scripts/generate-kpi-rollup.py\`
   - \`32-command-center-setup/scripts/generate-brand-css.py\`
   - \`32-command-center-setup/scripts/seed-workspaces.py\`
   - \`32-command-center-setup/scripts/seed-dashboard-content.py\`
2. Remove equivalent blocks from Skill 23 and Skill 22 files (see \`LEGACY-RETIREMENT.md\`).
3. Consolidate \`shared-utils/key_resolver.py\` secrets path into \`api_key_utils.py\`.
4. Remove the DEPRECATED SHIM marker from \`23-ai-workforce-blueprint/scripts/select-persona-for-task.py\`.
5. Clear \`docs/LEGACY-RETIREMENT.md\` tracked-files tables (empty = zero local loops allowed).
6. The CI guard (\`AF3: local-candidate-loop guard\`) will then enforce zero local loops.

_Auto-opened by fleet-refresh.sh v11.13.0 retirement-clock._
"""

# Attempt to create/update the GitHub issue via the gh CLI.
# (No backticks in this unquoted heredoc: the shell would run them -- a bare
# gh here injected its help text and crashed every --apply run.)
gh_bin = subprocess.run(["which", "gh"], capture_output=True, text=True).stdout.strip()
if not gh_bin:
    print("[fleet-refresh] WARNING: gh not on PATH — writing trigger sentinel file instead.")
    trigger_file = Path("$REPO_ROOT") / ".fleet-retirement-triggered"
    trigger_file.write_text(json.dumps({
        "triggered_ts": triggered_ts,
        "boxes": list(state["boxes"].keys()),
        "reason": "gh not on PATH",
    }, indent=2))
    print(f"[fleet-refresh] Retirement trigger sentinel written: {trigger_file}")
else:
    # Check for an existing open retirement-tracker issue first.
    existing = subprocess.run(
        ["gh", "issue", "list",
         "--repo", "trevorotts1/openclaw-onboarding",
         "--label", issue_label,
         "--state", "open",
         "--json", "number,title",
         "--limit", "5"],
        capture_output=True, text=True, timeout=30,
    )
    existing_number = None
    if existing.returncode == 0:
        try:
            existing_issues = json.loads(existing.stdout)
            for iss in existing_issues:
                if "retire" in iss.get("title", "").lower() or "retirement" in iss.get("title", "").lower():
                    existing_number = iss["number"]
                    break
        except Exception:
            pass

    if existing_number:
        # Update (comment on) the existing issue.
        result = subprocess.run(
            ["gh", "issue", "comment", str(existing_number),
             "--repo", "trevorotts1/openclaw-onboarding",
             "--body", f"**Retirement clock re-confirmed {triggered_ts}:** all {len(state['boxes'])} boxes still loaded=YES.\\n\\n{box_list}"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            print(f"[fleet-refresh] Updated existing retirement issue #{existing_number}")
        else:
            print(f"[fleet-refresh] WARNING: gh issue comment failed: {result.stderr[:200]}", file=sys.stderr)
    else:
        # Create a new issue.
        result = subprocess.run(
            ["gh", "issue", "create",
             "--repo", "trevorotts1/openclaw-onboarding",
             "--title", issue_title,
             "--label", issue_label,
             "--body", issue_body],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            issue_url = result.stdout.strip()
            print(f"[fleet-refresh] Retirement issue created: {issue_url}")
        else:
            print(f"[fleet-refresh] WARNING: gh issue create failed: {result.stderr[:200]}", file=sys.stderr)
            # Fall back to sentinel file so the trigger isn't lost.
            trigger_file = Path("$REPO_ROOT") / ".fleet-retirement-triggered"
            trigger_file.write_text(json.dumps({
                "triggered_ts": triggered_ts,
                "boxes": list(state["boxes"].keys()),
                "gh_error": result.stderr[:200],
            }, indent=2))
            print(f"[fleet-refresh] Retirement trigger sentinel written: {trigger_file}")

# Mark retirement_triggered=True in the manifest so we never duplicate.
state["retirement_triggered"] = True
try:
    loaded_state_file.write_text(json.dumps(state, indent=2))
except Exception as e:
    print(f"[fleet-refresh] WARNING: could not persist retirement_triggered flag: {e}", file=sys.stderr)

PYEOF
fi

# ── One-screen verdict per box ───────────────────────────────────────────────
python3 - "$SUMMARY_FILE" <<'PY' || true
import json, sys
try:
    rows = json.load(open(sys.argv[1]))
except Exception:
    rows = []
order = {"FAILED": 0, "ROLLED_BACK": 1, "SKIPPED": 2, "UPDATED": 3}
def outcome(r):
    o = r.get("outcome")
    if o in order:
        return o
    return {"ok": "UPDATED", "dry-run": "SKIPPED", "rolled_back": "ROLLED_BACK"}.get(r.get("result"), "FAILED")
name = lambda r: str(r.get("label") or r.get("box"))   # "Client Name (Platform)"
rows = sorted(rows, key=lambda r: (order[outcome(r)], name(r)))
w = max([len(name(r)) for r in rows] + [6])
print("")
print("=" * 78)
print(f" {'CLIENT':<{w}}  {'OUTCOME':<11}  DETAIL")
print("-" * 78)
for r in rows:
    detail = r.get("outcome_detail") or "; ".join(r.get("errors") or [])[:140]
    print(f" {name(r):<{w}}  {outcome(r):<11}  {detail[:140]}")
counts = {}
for r in rows:
    counts[outcome(r)] = counts.get(outcome(r), 0) + 1
print("-" * 78)
print(" " + "   ".join(f"{k}={counts.get(k, 0)}" for k in ("UPDATED", "ROLLED_BACK", "FAILED", "SKIPPED")))
print("=" * 78)
PY
echo "[fleet-refresh] per-box logs: $RUN_LOG_DIR"

# Roll-back / failure alert to the OPERATOR only (Telegram through his own agent's
# bot via the operator-alert webhook; email too on his Mac). Never a client.
if [ $APPLY -eq 1 ]; then
  _origin="operator roll"
  _self="$(label_of local)"
  [ "$_self" = "local" ] && _self="$(hostname -s 2>/dev/null || hostname)"
  [ $LOCAL -eq 1 ] && _origin="$_self (its own update)"
  python3 "$SHARED_UTILS/fleet_notify.py" --summary "$SUMMARY_FILE" --origin "$_origin" 2>&1 \
    | sed 's/^/[fleet-refresh] operator alert: /' || true
  # The operator's box list backup: last result per box, refreshed in Drive.
  if [ $LOCAL -eq 0 ] && [ -n "$BOXES_FILE" ]; then
    python3 "$REPO_ROOT/scripts/make-fleet-boxes-file.py" --out "$BOXES_FILE" --record-roll "$SUMMARY_FILE" 2>&1 \
      | sed 's/^/[fleet-refresh] box list: /' || true
  fi
fi

if [ $ANY_FAILED -eq 1 ]; then
  echo "[fleet-refresh] RESULT: PARTIAL/FAILED — check errors above"
  exit 2
elif [ $ANY_UNKNOWN -eq 1 ]; then
  echo "[fleet-refresh] RESULT: UNKNOWN — at least one box returned exit 3 (CC state indeterminate)"
  echo "[fleet-refresh]   atomic-deploy.sh exit 3 means the health-check was inconclusive after all retries."
  echo "[fleet-refresh]   No rollback was performed on those boxes. Operator must investigate."
  exit 3
else
  echo "[fleet-refresh] RESULT: OK — all boxes refreshed"
  exit 0
fi
