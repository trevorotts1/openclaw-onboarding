#!/usr/bin/env bash
# routing-check.sh (RF-014, part d) -- does the ROUTING of this box work? Read-only.
#
# Companion to scripts/health/library-gate-check.sh (RF-011): that one checks the
# library standard, this one checks the routing layer. Call BOTH from the health
# gate; neither writes anything and neither sends anything.
#
# Prints, one verdict per line (PASS / WARN / FAIL / UNDETERMINED):
#   routing-mode     which mode the box is in and who chose it (env/store/default),
#                    including a tripwire flip: mode=legacy + WHO set it matters
#   routing-tripwire tripwire state: armed / tripped (with the flag path Rescue
#                    Rangers can read) / how close (N of threshold)
#   routing-works    can the box actually route: the model-mode default model
#                    resolves (when mode=model), and a capability probe of the
#                    installed bridge answers schemaVersion 1.x (2 s cap).
#                    UNDETERMINED when the probe cannot run -- never a pass.
#
# Exit: 0 = no FAIL (warnings allowed)   1 = at least one FAIL
#       2 = bad usage                    5 = cannot tell (no OC root / no python3)
#
# Usage: routing-check.sh [--oc-config DIR]
set -uo pipefail

PY="${WORKFORCE_PYTHON:-$(command -v python3 || true)}"
[ -n "$PY" ] || { echo "[routing-check] UNDETERMINED: python3 not found -- cannot check (exit 5)" >&2; exit 5; }

ONB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OC_CONFIG_ARG=""
while [ $# -gt 0 ]; do
  case "$1" in
    --oc-config) OC_CONFIG_ARG="${2:-}"; shift 2 ;;
    *) echo "[routing-check] unknown argument: $1 (usage: routing-check.sh [--oc-config DIR])" >&2; exit 2 ;;
  esac
done

# The switch module ships with shared-utils; a repo checkout beside this script wins.
SU=""
for _CAND in "$ONB_DIR/shared-utils" "${OPENCLAW_SKILLS_DIR:-}/shared-utils"; do
  [ -n "${_CAND%/}" ] && [ -f "$_CAND/routing_switch.py" ] && { SU="$_CAND"; break; }
done
[ -n "$SU" ] || SU="$(ls -d "${OC_CONFIG_ARG:-${OC_CONFIG:-$HOME/.openclaw}}/skills/shared-utils" /data/.openclaw/skills/shared-utils 2>/dev/null | head -1)"
[ -n "$SU" ] && [ -f "$SU/routing_switch.py" ] || {
  echo "[routing-check] UNDETERMINED: routing_switch.py not found in shared-utils (exit 5)" >&2
  exit 5
}

export OPENCLAW_ROUTING_NO_RECORD=1   # a health check changes nothing
exec "$PY" - "$SU" "$OC_CONFIG_ARG" "$ONB_DIR" <<'PYEOF'
import json, os, subprocess, sys, tempfile
from pathlib import Path

su, oc_arg, onb = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, su)
import routing_switch as rs
import model_route as mr

root = rs.oc_root(oc_arg or None)
failed = warned = 0
verdicts = []

def line(item, verdict, msg):
    global failed, warned
    print("[routing-check] %s: %s - %s" % (item, verdict, msg))
    verdicts.append({"item": item, "verdict": verdict, "msg": msg})
    if verdict == "FAIL":
        failed += 1
    elif verdict == "WARN":
        warned += 1

if not root.is_dir():
    print("[routing-check] UNDETERMINED: no OpenClaw root at %s -- cannot check (exit 5)" % root, file=sys.stderr)
    sys.exit(5)

st = rs.status(root)
who = {"env": "$OPENCLAW_DECISION_ENGINE_MODE (owner/automation pin)",
       "file": "stored choice (owner pin)" if st["safetyNet"] == "pinned"
               else "tripped by the safety net (was the default)",
       "default": "release default (nothing stored)"}
who_txt = who.get(st["source"], st["source"])

# ---- routing-mode: which mode, who chose it ----
if not st["valid"]:
    line("routing-mode", "FAIL",
         "mode store holds %r, not one of %s -- no routing reader accepts it. Fix: routing-mode.sh reset" % (st["mode"], "|".join(rs.mode_names())))
elif st["safetyNet"] == "tripped":
    line("routing-mode", "WARN",
         "mode=%s -- the TRIPWIRE flipped the box automatically after %s consecutive JEV routing failures (last: %s). The owner switches back: routing-mode.sh set auto" % (
             st["mode"], st["consecutiveFailures"], st.get("lastFailureReason") or "unknown"))
    warned += 1
else:
    line("routing-mode", "PASS", "mode=%s (%s)" % (st["mode"], who_txt))

# ---- routing-tripwire: armed / tripped / how close ----
flag = st.get("flag") or {}
if st["safetyNet"] == "tripped" or flag:
    line("routing-tripwire", "WARN",
         "TRIPPED -- flipped to %s; incident at %s (%s failures, threshold %s). Clear for Rescue Rangers: %s/%s" % (
             flag.get("flippedTo", "legacy"), flag.get("ts") or "unknown",
             flag.get("failures"), flag.get("threshold"), root, rs.FLAG))
    warned += 1
elif st["consecutiveFailures"]:
    line("routing-tripwire", "WARN",
         "%s of %s consecutive JEV routing failures (last: %s) -- at %s the box flips itself to legacy" % (
             st["consecutiveFailures"], st["threshold"], st.get("lastFailureReason") or "unknown",
             "or past" if st["consecutiveFailures"] >= st["threshold"] else "threshold"))
    warned += 1
else:
    line("routing-tripwire", "PASS", "armed, no recorded failures (threshold %s)" % st["threshold"])

# ---- routing-works: can this box actually route? ----
if st["mode"] in ("legacy", "off"):
    line("routing-works", "WARN",
         "JEV is not routing by the owner's choice (mode=%s); tasks go through the old path. Turn it back on: routing-mode.sh set auto" % st["mode"])
    warned += 1
else:
    core = None
    for cand in (Path(su) / "decision-engine.py",):
        if cand.is_file():
            core = cand
    if core is None:
        line("routing-works", "UNDETERMINED", "installed bridge decision-engine.py not found in %s -- cannot probe (exit 5)" % su)
        sys.exit(5)
    probe = None
    try:
        with tempfile.TemporaryDirectory(prefix="rf014-route-check-") as tmp:
            env = dict(os.environ, HOME=tmp, OC_CONFIG=str(root),
                       OPENCLAW_ROUTING_NO_RECORD="1")
            env.pop("OPENCLAW_DECISION_ENGINE_MODE", None)
            proc = subprocess.run([sys.executable, str(core), "--capability"],
                                  capture_output=True, text=True, env=env,
                                  timeout=2, check=False)  # 2 s cap, like a health check should
            if proc.returncode == 0:
                try:
                    probe = (json.loads(proc.stdout) or {}).get("schemaVersion")
                except ValueError:
                    probe = None
    except (OSError, subprocess.SubprocessError, ValueError):
        probe = None
    if probe is None:
        line("routing-works", "FAIL",
             "the installed bridge does not answer a capability probe (2 s cap) -- JEV routing cannot work. Roll the box / re-run the updater")
        failed += 1
    elif str(probe).split(".")[0] != "1":
        line("routing-works", "FAIL",
             "bridge answers schemaVersion %r, not 1.x -- Command Center will not call it" % probe)
        failed += 1
    else:
        model_txt = ""
        if st["mode"] == "model":
            got = st.get("defaultModel")
            if got:
                model_txt = "; model mode default model resolves: %s" % got
            else:
                line("routing-works", "WARN",
                     "mode=model but no default model resolves from %s/openclaw.json -- unplaceable tasks fall back to legacy and are logged" % root)
                warned += 1
        line("routing-works", "PASS",
             "bridge answers schemaVersion %s%s" % (probe, model_txt))

print("[routing-check] %s (%d failed, %d warned)" % (
    "FAIL" if failed else "PASS", failed, warned))
sys.exit(1 if failed else 0)
PYEOF