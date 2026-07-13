#!/usr/bin/env bash
# =============================================================================
# SKILL 61 - LOOP PROTECTION SYSTEM :: verify.sh
# THE INDEPENDENT, FAILABLE DRILL BATTERY (spec Section 9.4).
# -----------------------------------------------------------------------------
# READ-ONLY and idempotent. FULLY OFFLINE: every drill runs against SCRATCH
# fixtures (never a live box, never a live config, never a real credential) and
# NEVER touches an external API - the D-ESCALATE drill injects a failing transport
# to prove the UNSENT fallback WITHOUT any network call. Proves the whole system
# end to end: every script self-test, the four merge-gate scanners clean over the
# tree, and one drill per class (D-RESTART, D-SIG, D-OFFSET, D-ORPHAN, D-BURN,
# D-BACKOFF, D-HEALERLOOP, D-ESCALATE, D-DRYRUN, D-ARMED-PARK, D-REVERT,
# D-COLLECT, D-COLLECT-DELTA, D-COLLECT-FALLBACK).
# D-ARMED-PARK proves an ARMED tick actually PARKS the unit + trips the process
# breaker (the RESPOND flagship, exercised through the whole tick); D-REVERT executes
# the EMITTED one-line revert and proves it unparks (spec 4.2: a fix that cannot be
# reverted in one line does not ship).
#
# EXIT: 0 verified, 4 drift/failure.
# =============================================================================
set -uo pipefail
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SCRIPTS="$SELF_DIR/scripts"
TAG="[loop-verify]"
FAILS=0

step() { echo; echo "== $* =="; }
ok()   { echo "  PASS: $*"; }
bad()  { echo "  FAIL: $*" >&2; FAILS=$((FAILS+1)); }

command -v python3 >/dev/null 2>&1 || { echo "$TAG FATAL: python3 required" >&2; exit 4; }

# ---- 1. every script self-test (the aggregate gate) -------------------------
step "1/3 every script --self-test"
if bash "$SELF_DIR/loop-companion.sh" --self-test >/tmp/loop-verify-selftest.$$ 2>&1; then
    ok "all script self-tests"
else
    bad "a script self-test failed (see below)"
    tail -25 /tmp/loop-verify-selftest.$$ >&2
fi
rm -f /tmp/loop-verify-selftest.$$ 2>/dev/null || true

# ---- 2. four merge-gate scanners CLEAN over the tree ------------------------
step "2/3 four merge-gate scanners CLEAN over the skill tree"
python3 "$SCRIPTS/guard-no-anthropic-runtime.py" >/dev/null 2>&1 && ok "guard-no-anthropic (0)" || bad "guard-no-anthropic"
SCAN_ALL_FILES=1 bash "$SCRIPTS/scan-no-secrets.sh" --root "$SELF_DIR" --strict >/dev/null 2>&1 && ok "scan-no-secrets (0)" || bad "scan-no-secrets"
SCAN_ALL_FILES=1 bash "$SCRIPTS/scan-no-client-identifiers.sh" --root "$SELF_DIR" >/dev/null 2>&1 && ok "scan-no-client-identifiers (0)" || bad "scan-no-client-identifiers"
SCAN_ALL_FILES=1 bash "$SCRIPTS/scan-no-json-exports.sh" --root "$SELF_DIR" >/dev/null 2>&1 && ok "scan-no-json-exports (0)" || bad "scan-no-json-exports"

# ---- 3. fixture drills, one per class (all OFFLINE) -------------------------
step "3/3 fixture drills (D-RESTART, D-SIG, D-OFFSET, D-ORPHAN, D-BURN, D-BACKOFF, D-HEALERLOOP, D-ESCALATE, D-DRYRUN, D-ARMED-PARK, D-REVERT, D-COLLECT, D-COLLECT-DELTA, D-COLLECT-FALLBACK)"
SCRIPTS="$SCRIPTS" SKILL_DIR="$SELF_DIR" python3 - <<'PY'
import json, os, sys, tempfile
sys.path.insert(0, os.environ["SCRIPTS"])
fx = os.path.join(os.environ["SKILL_DIR"], "tests", "fixtures")
import loop_common as C
import loop_detectors as D
import loop_breaker as BR
import loop_backoff as BO
import loop_killcards as KC
import loop_escalate as ESC
from loop_ledger import Ledger
os.environ["LOOP_ALLOW_ROOT"] = "1"  # allow config-touching kill cards in a CI/root sandbox

th = C.load_skill_config("thresholds.json")
brs = BR.load_breakers()
fails = []
def check(name, cond):
    print(("  PASS: " if cond else "  FAIL: ") + name)
    if not cond:
        fails.append(name)

def load(name):
    return json.load(open(os.path.join(fx, name)))

# D-RESTART: a Box A-class storm trips the process breaker in ONE tick, and the
# raw pm2 env block (which carries credential shapes) is DROPPED by the filter.
raw = load("restart-storm.jlist.json")
units = [dict(C.filter_pm2_record(r), delta=C.filter_pm2_record(r)["restarts"]) for r in raw]
assert all("pm2_env" not in u and "env" not in u for u in units)
assert "PLACEHOLDER" not in C.canonical(units)  # env never survives into D1 evidence
f1 = D.d1_restart_velocity(units, th)
storm = [x for x in f1 if x["unit"] == "cc-app"]
check("D-RESTART storm=P1 at <=10 restarts; env dropped",
      bool(storm) and storm[0]["severity"] == "P1"
      and BR.process_breaker_trips("cc-app", units[0]["delta"], units[0]["restarts"], brs))

# D-SIG: 5 identical failure signatures = D3 loop-confirmed P1.
runs = load("identical-signature.runs.json")
f3 = D.d3_identical_signature(runs, th)
check("D-SIG identical signature x5 = P1 loop-confirmed",
      any(x["severity"] == "P1" and x["loop_class"] == "LP-A1" for x in f3))

# D-OFFSET: corrupted offset rewinds to oldest-1, byte-verified.
with tempfile.TemporaryDirectory() as td:
    offp = os.path.join(td, "offset.json")
    o = load("corrupted-offset.json")
    json.dump(o, open(offp, "w"))
    r = KC.lf2_rewind_offset(offp, dry_run=False)
    check("D-OFFSET rewind to oldest_pending-1 (byte-verified)",
          r["applied"] and r["rewound_to"] == o["expected_rewind_to"]
          and json.load(open(offp))["stored_offset"] == o["expected_rewind_to"])

# D-ORPHAN: orphan :18789 listener + stale handoff = LP-B3 P1; the finding names
# ONLY the orphan pid, never the supervisor (kill-list contains only the orphan).
wedge = load("orphan-port.json")
f4 = D.d4_timer_refire([], wedge, th)
orphan = [x for x in f4 if x["loop_class"] == "LP-B3"]
check("D-ORPHAN orphan listener = P1; only the orphan pid named",
      bool(orphan) and str(wedge["orphan_listener_pid"]) in orphan[0]["detail"]
      and str(wedge["supervisor_pid"]) not in orphan[0]["detail"].split("supervisor pid")[0])

# D-BURN: idle-window paid burn = D2 P1; a working window is silent; the alert text
# carries counts only, no secret shape.
windows = [json.loads(l) for l in open(os.path.join(fx, "idle-burn.trajectory.jsonl")) if l.strip()]
windows = [{"label": w["window"], "paid_tokens": w["paid_tokens"],
            "initiated_sessions": w["initiated_sessions"],
            "idle_consecutive": w["idle_consecutive"]} for w in windows]
f2 = D.d2_token_burn_rate(windows, th)
check("D-BURN idle paid burn = P1; working window silent; no secret shape",
      any(x["severity"] == "P1" and x["unit"] == "02:00-03:00" for x in f2)
      and not any(x["unit"] == "09:00-10:00" for x in f2)
      and all("sk-" not in x["detail"] for x in f2))

# D-BACKOFF: 2h/4h/8h intervals persisted across a watchdog restart.
with tempfile.TemporaryDirectory() as td:
    sd = os.path.join(td, "loop-protection")
    led = Ledger(sd)
    r1 = BO.register_failure("job-x", th, led, max_tries=5, rand=0.5)
    r2 = BO.register_failure("job-x", th, led, max_tries=5, rand=0.5)
    led.close()
    led2 = Ledger(sd)  # simulate a watchdog restart: state must survive
    r3 = BO.register_failure("job-x", th, led2, max_tries=5, rand=0.5)
    persisted = led2.get_backoff("job-x")["attempt"]
    led2.close()
    check("D-BACKOFF 2h/4h/8h + attempt persists across a restart",
          r1["interval_seconds"] == 7200 and r2["interval_seconds"] == 14400
          and r3["interval_seconds"] == 28800 and persisted == 3)

# D-HEALERLOOP: a fix class rigged to fail verify -> healer breaker stops it,
# escalates, and does NOT auto-retry.
with tempfile.TemporaryDirectory() as td:
    led = Ledger(os.path.join(td, "loop-protection"))
    res = KC.apply({"loop_class": "LP-B1", "fix_class": "LF-6", "tier": 1, "unit": "cc-app"},
                   led, armed=True, executors={"LF-6": lambda dry_run: {"applied": True}},
                   verify_failed_last=True)
    check("D-HEALERLOOP verify-fail -> escalate, NO second auto-attempt",
          res["status"] == "escalated" and res["escalate"] is True)
    led.close()

# D-ESCALATE: OFFLINE. A [DRILL] escalation with a DEAD transport (no network)
# lands in the UNSENT fallback; the UNSENT path is proven by pointing at a dead URL.
with tempfile.TemporaryDirectory() as td:
    os.environ["LOOP_STATE_DIR"] = td
    payload = ESC.build_payload(box="box-example", loop_class="LP-B3",
        finding="[DRILL] verify.sh offline escalation test",
        evidence_path="tests/fixtures/orphan-port.json",
        proposed_fix="LF-3 orphan clear", why="drill", action_needed="ignore (drill)",
        finding_id=1, killcard_cmd="loop-companion.sh fix 1",
        revert_cmd="loop-companion.sh unpark --finding 1")
    def dead(url, body):  # no real network; proves the UNSENT fallback
        raise OSError("offline drill")
    r = ESC.send(payload, transport=dead, url="http://webhook.invalid/x")
    unsent_ok = (not r["sent"]) and r["unsent_path"] and os.path.isfile(r["unsent_path"])
    body = open(r["unsent_path"]).read() if unsent_ok else ""
    check("D-ESCALATE offline UNSENT fallback (no external API), no secret in payload",
          unsent_ok and "LP-B3" in body and "sk-" not in body)
    os.environ.pop("LOOP_STATE_DIR", None)

# D-DRYRUN: armed=false -> a Tier-1 kill card PLANS and the target file is byte-identical.
with tempfile.TemporaryDirectory() as td:
    cron = os.path.join(td, "crons.json")
    json.dump({"crons": [{"id": "resume", "enabled": True}]}, open(cron, "w"), indent=2)
    before = open(cron, "rb").read()
    led = Ledger(os.path.join(td, "loop-protection"))
    execs = {"LF-4": lambda dry_run: KC.lf4_disable_cron(cron, "resume", dry_run=dry_run)}
    res = KC.apply({"loop_class": "LP-A4", "fix_class": "LF-4", "tier": 1, "unit": "resume"},
                   led, armed=False, executors=execs)
    after = open(cron, "rb").read()
    led.close()
    check("D-DRYRUN armed=false plans, filesystem byte-identical",
          res["status"] == "planned" and before == after)

# D-ARMED-PARK: an ARMED tick over the restart-storm fixture actually PARKS the unit
# and TRIPS the process breaker in ONE tick - the RESPOND flagship, exercised through
# the WHOLE tick pipeline (not the isolated BR.process_breaker_trips predicate). The
# old empty-executors watchdog ESCALATED here instead of parking; this drill fails if
# that regresses. A quiet unit is never parked.
import loop_watchdog as W
with tempfile.TemporaryDirectory() as td:
    led = Ledger(os.path.join(td, "loop-protection"))
    raw = load("restart-storm.jlist.json")
    units = [dict(C.filter_pm2_record(r), delta=C.filter_pm2_record(r)["restarts"]) for r in raw]
    ev = {"units": units, "windows": [], "runs": [], "crons": [], "wedge": {}}
    def _dead_tx(url, body):  # no network in a drill
        raise OSError("offline drill")
    summary = W.tick(ev, led, armed=True, escalate_transport=_dead_tx, box="box-example")
    parked = [r["unit"] for r in led.parked_units()]
    tripped = [(r["unit"], r["breaker"]) for r in led.tripped_breakers()]
    check("D-ARMED-PARK armed tick parks cc-app AND trips the process breaker (full tick, not the predicate)",
          summary["applied"] >= 1 and "cc-app" in parked
          and ("cc-app", "process") in tripped and "gateway" not in parked)
    led.close()

# D-REVERT: the operator's ONE-LINE revert actually reverts. Record a real finding,
# `fix` it (LF-6 parks the unit for real), then run the EMITTED one-line revert
# (loop-companion.sh unpark --finding <id>) through the REAL companion entry and prove
# the unit is UNPARKED. This exercises revert_command_for + the companion + the new
# loop_breaker/loop_killcards CLIs end to end (spec 4.2).
import subprocess
with tempfile.TemporaryDirectory() as td:
    sd = os.path.join(td, "loop-protection")
    led = Ledger(sd)
    fid = led.record_finding("LP-B1", "P1", unit="cc-app", detail="[DRILL] restart storm", tier=1)
    led.close()
    companion = os.path.join(os.environ["SKILL_DIR"], "loop-companion.sh")
    denv = dict(os.environ, LOOP_STATE_DIR=sd)
    fixp = subprocess.run(["bash", companion, "fix", str(fid)], capture_output=True, text=True, env=denv)
    led = Ledger(sd); parked_after_fix = [r["unit"] for r in led.parked_units()]; led.close()
    emitted = C.revert_command_for(fid)
    shape_ok = ("loop-companion.sh unpark --finding %d" % fid) in emitted
    revp = subprocess.run(["bash", companion, "unpark", "--finding", str(fid)],
                          capture_output=True, text=True, env=denv)
    led = Ledger(sd); parked_after_revert = [r["unit"] for r in led.parked_units()]; led.close()
    check("D-REVERT fix parks; the emitted `unpark --finding <id>` one-line revert unparks it",
          fixp.returncode == 0 and "cc-app" in parked_after_fix
          and shape_ok and revp.returncode == 0 and "cc-app" not in parked_after_revert)

# D-COLLECT: the collect layer feeds the detectors REAL evidence (the incident
# regression: the old collect_evidence() stub handed D2/D3/D4 EMPTY evidence even
# fully armed). A synthetic loop trajectory in a SCRATCH openclaw root (real v20
# schema; LOOP_NO_PROBES=1 so zero subprocess probes fire) must yield non-empty
# windows + runs, D2 must flag the idle paid burn, D3 must flag the repeated
# identical SUCCESSFUL turn, and the slice must be offset-consumed (a second
# collect returns no runs).
from datetime import datetime, timedelta, timezone
with tempfile.TemporaryDirectory() as td:
    os.environ["LOOP_STATE_DIR"] = os.path.join(td, "loop-protection")
    os.environ["LOOP_OPENCLAW_ROOT"] = os.path.join(td, "openclaw")
    os.environ["LOOP_NO_PROBES"] = "1"
    sess = os.path.join(td, "openclaw", "agents", "main", "sessions")
    os.makedirs(sess)
    now = datetime.now(timezone.utc)
    t0 = (now - timedelta(minutes=90)).replace(microsecond=0)
    rows = [{"type": "session.started", "ts": t0.isoformat(), "sessionId": "s1",
             "sessionKey": "agent:main:main", "runId": "r0",
             "modelId": "minimax-m3:cloud", "provider": "ollama",
             "data": {"trigger": "cron"}}]
    for i in range(12):
        common = {"ts": (t0 + timedelta(minutes=2 * i)).isoformat(),
                  "sessionId": "s1", "sessionKey": "agent:main:main",
                  "runId": "r%d" % (i + 1), "seq": i,
                  "modelId": "minimax-m3:cloud", "provider": "ollama"}
        rows.append(dict(common, type="model.completed",
                         data={"usage": {"input": 250000, "output": 50000,
                                         "total": 300000}}))
        rows.append(dict(common, type="trace.artifacts",
                         data={"finalStatus": "success", "usage": {"total": 300000},
                               "toolMetas": [{"toolName": "exec"},
                                             {"toolName": "message"}]}))
    with open(os.path.join(sess, "s1.trajectory.jsonl"), "w") as fh:
        fh.write("\n".join(json.dumps(r) for r in rows) + "\n")
    led = Ledger()
    ev = W.collect_evidence(led)
    fnd = W.run_detectors(ev, th, C.load_signatures())
    d2_p1 = [x for x in fnd if x["detector"] == "D2" and x["severity"] == "P1"]
    d3_p1 = [x for x in fnd if x["detector"] == "D3" and x["severity"] == "P1"]
    ev2 = W.collect_evidence(led)
    led.close()
    for k in ("LOOP_STATE_DIR", "LOOP_OPENCLAW_ROOT", "LOOP_NO_PROBES"):
        os.environ.pop(k, None)
    check("D-COLLECT synthetic loop -> real windows/runs; D2+D3 P1; slice offset-consumed",
          bool(ev["windows"]) and len(ev["runs"]) >= 12
          and bool(d2_p1) and bool(d3_p1) and ev2["runs"] == [])

# D-COLLECT-DELTA: within-run cumulative charging + the derivedTotal fallback. A
# SINGLE runId whose cumulative usage rises 100k -> 800k, carried as COMPONENT
# BUCKETS ONLY (input, no `usage.total`), must be charged as the 800k telescoping
# DELTA and NOT the 3.6M naive sum of per-completion totals. Exercises BOTH the
# within-run delta path (the D-COLLECT fixture above uses a DISTINCT runId per
# completion, so that path was untested) AND the multi-candidate component-sum
# fallback - so it FAILS against the old single-field `usage.total` reader (None ->
# 0 -> zero paid) and PASSES after the 0.3.1 hardening.
with tempfile.TemporaryDirectory() as td:
    os.environ["LOOP_OPENCLAW_ROOT"] = os.path.join(td, "openclaw")
    os.environ["LOOP_NO_PROBES"] = "1"
    sess = os.path.join(td, "openclaw", "agents", "main", "sessions")
    os.makedirs(sess)
    now = datetime.now(timezone.utc)
    t0 = (now - timedelta(minutes=60)).replace(microsecond=0)
    rows = [{"type": "session.started", "ts": t0.isoformat(), "sessionId": "sD",
             "sessionKey": "agent:main:main", "runId": "rDELTA",
             "modelId": "minimax-m3:cloud", "provider": "ollama",
             "data": {"trigger": "cron"}}]
    for i in range(8):  # cumulative 100k, 200k, ... 800k under ONE runId
        cum = 100000 * (i + 1)
        rows.append({"type": "model.completed",
                     "ts": (t0 + timedelta(minutes=i + 1)).isoformat(),
                     "sessionId": "sD", "sessionKey": "agent:main:main",
                     "runId": "rDELTA", "seq": i,
                     "modelId": "minimax-m3:cloud", "provider": "ollama",
                     "data": {"usage": {"input": cum}}})  # buckets only, no `total`
    with open(os.path.join(sess, "sD.trajectory.jsonl"), "w") as fh:
        fh.write("\n".join(json.dumps(r) for r in rows) + "\n")
    charged = sum(w["paid_tokens"] for w in W.collect_windows())
    for k in ("LOOP_OPENCLAW_ROOT", "LOOP_NO_PROBES"):
        os.environ.pop(k, None)
    check("D-COLLECT-DELTA single-run cumulative 100k->800k charges the 800k DELTA "
          "(not the 3.6M naive sum); component-sum fallback",
          charged == 800000 and charged != 3600000)

# D-COLLECT-FALLBACK: a `total_tokens`-only row (no `usage.total`) must still charge
# non-zero and light D2 - proving the multi-candidate reader's raw-alias fallback.
# FAILS against the old single-field reader (usage.total absent -> None -> zero paid
# -> D2 silent) and PASSES after the 0.3.1 hardening.
with tempfile.TemporaryDirectory() as td:
    os.environ["LOOP_OPENCLAW_ROOT"] = os.path.join(td, "openclaw")
    os.environ["LOOP_NO_PROBES"] = "1"
    sess = os.path.join(td, "openclaw", "agents", "main", "sessions")
    os.makedirs(sess)
    now = datetime.now(timezone.utc)
    t0 = (now - timedelta(minutes=30)).replace(microsecond=0)
    rows = [{"type": "session.started", "ts": t0.isoformat(), "sessionId": "sF",
             "sessionKey": "agent:main:main", "runId": "rF0",
             "modelId": "minimax-m3:cloud", "provider": "ollama",
             "data": {"trigger": "cron"}},
            {"type": "model.completed", "ts": t0.isoformat(), "sessionId": "sF",
             "sessionKey": "agent:main:main", "runId": "rF1", "seq": 0,
             "modelId": "minimax-m3:cloud", "provider": "ollama",
             "data": {"usage": {"total_tokens": 500000}}}]  # alias only, no `total`
    with open(os.path.join(sess, "sF.trajectory.jsonl"), "w") as fh:
        fh.write("\n".join(json.dumps(r) for r in rows) + "\n")
    winF = W.collect_windows()
    paidF = sum(w["paid_tokens"] for w in winF)
    d2F = D.d2_token_burn_rate(winF, th)
    for k in ("LOOP_OPENCLAW_ROOT", "LOOP_NO_PROBES"):
        os.environ.pop(k, None)
    check("D-COLLECT-FALLBACK total_tokens-only row charges non-zero; D2 P1 fires "
          "(multi-candidate raw-alias fallback)",
          paidF == 500000 and any(x["severity"] == "P1" for x in d2F))

os.environ.pop("LOOP_ALLOW_ROOT", None)
if fails:
    print("DRILL FAILURES: %s" % fails, file=sys.stderr)
    sys.exit(4)
print("  all fixture drills PASS")
sys.exit(0)
PY
[ $? -eq 0 ] || bad "fixture drills"

echo
if [ "$FAILS" -eq 0 ]; then
    echo "$TAG VERIFIED: every self-test, scanner, and drill passed (fully offline)."
    exit 0
else
    echo "$TAG DRIFT: $FAILS check(s) failed." >&2
    exit 4
fi
