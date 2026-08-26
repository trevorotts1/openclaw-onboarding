#!/usr/bin/env bash
# =============================================================================
# SKILL 61 - LOOP PROTECTION SYSTEM :: verify.sh
# THE INDEPENDENT, FAILABLE DRILL BATTERY (spec Section 9.4).
# -----------------------------------------------------------------------------
# READ-ONLY and idempotent. Sections 1-3 are FULLY OFFLINE: every drill runs
# against SCRATCH fixtures (never a live box, never a live config, never a real
# credential). Section 4, the v0.6.5 STANDING GATE, is the deliberate exception -
# it READS this box's own cron table and ledger, because a battery that only ever
# examined scratch fixtures stayed green while 25 of 34 boxes accumulated 2-12
# duplicate loop-tick cron jobs and nobody could tell which boxes were ticking.
# It adds, edits and removes NOTHING: no cron job, no finding, no config. It is
# not literally write-free, and saying so would be the kind of convenient claim
# this skill exists to catch - opening the ledger runs the same idempotent schema
# bootstrap every tick already performs, and on a box with no ledger yet it
# creates an empty one. Skip it with --offline or LOOP_VERIFY_NO_LIVE=1; run it
# alone with --live.
#
# Sections 1-3 NEVER touch an external API - the D-ESCALATE drill injects a failing transport
# to prove the UNSENT fallback WITHOUT any network call. Proves the whole system
# end to end: every script self-test, the four merge-gate scanners clean over the
# tree, and one drill per class (D-RESTART, D-SIG, D-RESEND, D-OFFSET, D-ORPHAN,
# D-BURN, D-BACKOFF, D-HEALERLOOP, D-ESCALATE, D-ESC-DRIFT, D-ESC-DEDUP,
# D-ESC-BACKOFF, D-ESC-NEWKEY, D-ESC-TICK, D-DRYRUN, D-ARMED-PARK, D-REVERT,
# D-COLLECT, D-COLLECT-DELTA, D-COLLECT-FALLBACK, D-POISON*, D-POISON-REROLL*),
# plus section 4's two LIVE checks: D-CRON-ONE (exactly one enabled loop-tick job,
# proven through `openclaw cron list --all`) and D-TICK-FRESH (the watchdog
# COMPLETED a tick within 45 minutes, read from ledger meta last_tick_ts - NOT
# from MAX(findings.tick_ts), which measures whether the box HAS a loop and so
# calls a healthy box dead).
# D-ARMED-PARK proves an ARMED tick actually PARKS the unit + trips the process
# breaker (the RESPOND flagship, exercised through the whole tick); D-REVERT executes
# the EMITTED one-line revert and proves it unparks (spec 4.2: a fix that cannot be
# reverted in one line does not ship); the D-POISON-REROLL family holds the line on a
# REPRODUCED crash - a non-idempotent roll that re-archived its own archive every
# tick until the filename passed 255 bytes and the uncaught OSError killed the
# scheduled job.
#
# EXIT: 0 verified, 4 drift/failure, 5 STANDING GATE UNDETERMINED (v0.6.5 - the
# live checks could not be PROVEN either way; never folded into a pass).
# =============================================================================
set -uo pipefail
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SCRIPTS="$SELF_DIR/scripts"
TAG="[loop-verify]"
FAILS=0
UNDET=0

# v0.6.5. The offline drills prove the MECHANISM; the standing gate proves THIS
# BOX. Both matter, and they answer different questions - a battery that only
# ever ran against scratch fixtures is how 25 of 34 boxes accumulated duplicate
# cron jobs while every drill stayed green.
#   (default)   offline drills + standing gate
#   --live      the standing gate ONLY (fast operator check on a real box)
#   --offline   the offline drills ONLY (source checkout / CI; no gateway)
RUN_OFFLINE=1; RUN_LIVE=1
while [ $# -gt 0 ]; do
    case "$1" in
        --live)    RUN_OFFLINE=0; RUN_LIVE=1; shift ;;
        --offline) RUN_OFFLINE=1; RUN_LIVE=0; shift ;;
        -h|--help) echo "$TAG usage: verify.sh [--live | --offline]"; exit 0 ;;
        *) echo "$TAG unknown arg: $1" >&2; exit 2 ;;
    esac
done
[ "${LOOP_VERIFY_NO_LIVE:-0}" = "1" ] && RUN_LIVE=0

step() { echo; echo "== $* =="; }
ok()   { echo "  PASS: $*"; }
bad()  { echo "  FAIL: $*" >&2; FAILS=$((FAILS+1)); }

command -v python3 >/dev/null 2>&1 || { echo "$TAG FATAL: python3 required" >&2; exit 4; }

if [ "$RUN_OFFLINE" -eq 1 ]; then
# ---- 1. every script self-test (the aggregate gate) -------------------------
step "1/4 every script --self-test"
if bash "$SELF_DIR/loop-companion.sh" --self-test >/tmp/loop-verify-selftest.$$ 2>&1; then
    ok "all script self-tests"
else
    bad "a script self-test failed (see below)"
    tail -25 /tmp/loop-verify-selftest.$$ >&2
fi
rm -f /tmp/loop-verify-selftest.$$ 2>/dev/null || true

# ---- 2. four merge-gate scanners CLEAN over the tree ------------------------
step "2/4 four merge-gate scanners CLEAN over the skill tree"
python3 "$SCRIPTS/guard-no-anthropic-runtime.py" >/dev/null 2>&1 && ok "guard-no-anthropic (0)" || bad "guard-no-anthropic"
SCAN_ALL_FILES=1 bash "$SCRIPTS/scan-no-secrets.sh" --root "$SELF_DIR" --strict >/dev/null 2>&1 && ok "scan-no-secrets (0)" || bad "scan-no-secrets"
SCAN_ALL_FILES=1 bash "$SCRIPTS/scan-no-client-identifiers.sh" --root "$SELF_DIR" >/dev/null 2>&1 && ok "scan-no-client-identifiers (0)" || bad "scan-no-client-identifiers"
SCAN_ALL_FILES=1 bash "$SCRIPTS/scan-no-json-exports.sh" --root "$SELF_DIR" >/dev/null 2>&1 && ok "scan-no-json-exports (0)" || bad "scan-no-json-exports"

# ---- 3. fixture drills, one per class (all OFFLINE) -------------------------
step "3/4 fixture drills (D-RESTART, D-SIG, D-RESEND, D-OFFSET, D-ORPHAN, D-BURN, D-BACKOFF, D-HEALERLOOP, D-ESCALATE, D-ESC-DRIFT, D-ESC-DEDUP, D-ESC-BACKOFF, D-ESC-NEWKEY, D-ESC-TICK, D-DRYRUN, D-ARMED-PARK, D-REVERT, D-COLLECT, D-COLLECT-DELTA, D-COLLECT-FALLBACK, D-POISON, D-POISON-CLEAN, D-POISON-ROLL, D-POISON-LIVE, D-POISON-REROLL, D-POISON-REROLL-BOUND, D-POISON-REROLL-REFUSAL, D-POISON-REROLL-TICK)"
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
import loop_watchdog as W
from datetime import datetime, timedelta, timezone
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

# D-RESEND: 3 identical cross-run resends within the window = D7 loop-confirmed
# P1 (LP-A10, the 2026-08-04 sessions_send-timeout-misread incident); a 2-send
# pair below the P1 threshold never reaches P1 (WARN only, at most); a
# legitimate 3-message fan-out with DISTINCT payloads (a real multi-step
# handoff) never fires at all. The hash is computed HERE from the fixture's
# plaintext payload via the real C.cross_run_payload_hash (never a pre-baked
# literal), and the raw payload text is asserted absent from every finding
# (hash only - a transcript can carry a live client credential).
resend_raw = load("cross-run-resend.sends.json")
sends = [dict(source=r["source"], target=r["target"], run_id=r["run_id"], ts=r["ts"],
             hash=C.cross_run_payload_hash(r["source"], r["target"], r["payload"]))
        for r in resend_raw]
f7 = D.d7_cross_run_resend(sends, th)
p1_units = {x["unit"] for x in f7 if x["severity"] == "P1" and x["loop_class"] == "LP-A10"}
all_units = {x["unit"] for x in f7}
all_findings_text = C.canonical(f7)
raw_leaked = any(r["payload"] in all_findings_text for r in resend_raw)
check("D-RESEND 3 identical cross-run resends = P1 loop-confirmed; 2-send stays "
      "below P1; distinct-payload fan-out never fires; raw payload never in a finding",
      "agent:orchestrator-1:main" in p1_units
      and "agent:orchestrator-2:main" not in p1_units
      and "agent:orchestrator-3:main" not in all_units
      and not raw_leaked)

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

# --------------------------------------------------------------------------- #
# D-ESC-DRIFT / D-ESC-DEDUP / D-ESC-BACKOFF / D-ESC-NEWKEY / D-ESC-TICK
# RR-ESC-GATE-20260826. The Rescue Rangers escalation path had NO dedup and NO
# backoff while the operator alert beside it had both. Measured on ONE live box:
# a single dedup_key produced 992 escalations and the findings table held 4,084
# rows across 12 distinct keys, against an intake whose rate limit is GLOBAL
# across the fleet - so one box's runaway key sheds OTHER clients' escalations.
#
# Every drill below is FAILABLE IN BOTH DIRECTIONS: each proves the gate HOLDS
# when it should AND RELEASES when it should. A suppression drill that cannot
# demonstrate the release is exactly how a noisy system is turned into a silent
# one with nobody noticing, and silent loss is the worse failure of the two.
def _esc_th(window_hours):
    """thresholds with ONLY alert.escalation.dedup_window_hours overridden."""
    t = json.loads(json.dumps(th))
    t["alert"]["escalation"]["dedup_window_hours"] = window_hours
    return t

def _backdate_digest(led, key, hours):
    ts = (datetime.now(timezone.utc) - timedelta(hours=hours)) \
        .replace(microsecond=0).isoformat()
    led.conn.execute("UPDATE digests SET sent_ts=? WHERE dedup_key=?",
                     (ts, W.ESCALATION_DIGEST_PREFIX + key))
    led.conn.commit()

F_A = {"loop_class": "LP-A4", "severity": "P1", "unit": "unit-a",
       "dedup_key": "LP-A4|unit-a"}
F_B = {"loop_class": "LP-A4", "severity": "P1", "unit": "unit-b",
       "dedup_key": "LP-A4|unit-b"}

# D-ESC-DRIFT: the shipped config value and the code fallback must AGREE (so
# deleting the config key cannot silently change behaviour), and the escalation
# window must stay DIFFERENT from the alert window. Both numbers are LITERALS
# here, never read from the module under test. The second half is the
# anti-vacuity guard: if someone "tidies" the escalation window to the alert's
# 6h, the honoured-value drills below silently lose their power to discriminate
# a config read from a hardcoded constant, and a green board would prove nothing.
check("D-ESC-DRIFT shipped escalation window == code fallback (12h) and stays "
      "DISTINCT from the 6h alert window",
      th["alert"]["escalation"]["dedup_window_hours"] == 12
      and W.DEFAULT_ESCALATION_DEDUP_WINDOW_HOURS == 12
      and th["alert"]["dedup_window_hours"] == 6)

# D-ESC-DEDUP: holds inside the window, RELEASES outside it, and honours an
# override that is neither the shipped 12h nor the alert 6h.
with tempfile.TemporaryDirectory() as td:
    led = Ledger(os.path.join(td, "loop-protection"))
    g0 = W._escalation_gate(led, F_A, th)             # nothing recorded yet -> clear
    W._escalation_admitted(led, "LP-A4|unit-a")
    g1 = W._escalation_gate(led, F_A, th)             # digest is NOW      -> HELD
    _backdate_digest(led, "LP-A4|unit-a", 11)
    g2 = W._escalation_gate(led, F_A, th)             # 11h < 12h          -> HELD
    _backdate_digest(led, "LP-A4|unit-a", 13)
    g3 = W._escalation_gate(led, F_A, th)             # 13h > 12h          -> RELEASED
    _backdate_digest(led, "LP-A4|unit-a", 4)
    g4 = W._escalation_gate(led, F_A, _esc_th(3))     # 4h > 3h            -> RELEASED
    g5 = W._escalation_gate(led, F_A, _esc_th(5))     # 4h < 5h            -> HELD
    g6 = W._escalation_gate(led, F_A, _esc_th(0))     # 0 = no dedup       -> RELEASED
    led.close()
    # g4/g5 are the discriminators: a hardcoded 12 fails g4, a read of the
    # alert's 6 fails g4, and ignoring the window entirely fails g5.
    check("D-ESC-DEDUP holds inside the window and RELEASES outside it; a 3h/5h "
          "override beats both the shipped 12h and the alert 6h; an explicit 0 "
          "disables the dedup rather than falling back to the default",
          g0["ok"] and g0["reason"] == "clear"
          and (not g1["ok"]) and g1["reason"] == "dedup" and g1["window_hours"] == 12.0
          and (not g2["ok"]) and g2["reason"] == "dedup"
          and g3["ok"] and g3["reason"] == "clear"
          and g4["ok"]
          and (not g5["ok"]) and g5["reason"] == "dedup"
          and g6["ok"] and g6["window_hours"] == 0.0)

# D-ESC-BACKOFF: a refusal advances the EXISTING loop_backoff ladder on that key
# and writes NO digest, so the refusal can never silence its own retry.
with tempfile.TemporaryDirectory() as td:
    led = Ledger(os.path.join(td, "loop-protection"))
    t0 = datetime.now(timezone.utc)
    r1 = W._escalation_refused(led, "LP-A4|unit-a", th)
    d1 = (C.parse_iso8601(r1["next_at"]) - t0).total_seconds()
    gb1 = W._escalation_gate(led, F_A, th)
    no_digest = led.recent_digest(W.ESCALATION_DIGEST_PREFIX + "LP-A4|unit-a", 24) is None
    r2 = W._escalation_refused(led, "LP-A4|unit-a", th)
    # RELEASE direction: once next_at is in the PAST the key retries. A backoff
    # that never expires is silence wearing a backoff's name.
    led.upsert_backoff("escalate:LP-A4|unit-a", attempt=2, base_seconds=7200,
                       cap_seconds=86400,
                       next_at=(t0 - timedelta(hours=1)).replace(microsecond=0).isoformat())
    gb2 = W._escalation_gate(led, F_A, th)
    W._escalation_admitted(led, "LP-A4|unit-a")   # an admission is the artifact
    cleared = int(led.get_backoff("escalate:LP-A4|unit-a")["attempt"])
    led.close()
    check("D-ESC-BACKOFF a refusal schedules ~2h then ~4h (jittered, NEVER an "
          "immediate identical retry), writes NO digest, RELEASES once next_at "
          "passes, and an admitted delivery resets the ladder to 0",
          r1["attempt"] == 1 and 6480 <= d1 <= 7920
          and (not gb1["ok"]) and gb1["reason"] == "backoff"
          and no_digest
          and r2["attempt"] == 2 and 12960 <= r2["interval_seconds"] <= 15840
          and gb2["ok"] and gb2["reason"] == "clear"
          and cleared == 0)

# D-ESC-NEWKEY: THE ONE THAT MATTERS MOST. A genuinely new problem must escalate
# immediately even while another key is both deduped and pinned at the 24h cap.
with tempfile.TemporaryDirectory() as td:
    led = Ledger(os.path.join(td, "loop-protection"))
    W._escalation_admitted(led, "LP-A4|unit-a")
    for _ in range(6):
        rN = W._escalation_refused(led, "LP-A4|unit-a", th)
    ga = W._escalation_gate(led, F_A, th)
    gbnew = W._escalation_gate(led, F_B, th)
    led.close()
    check("D-ESC-NEWKEY a NEW dedup_key escalates IMMEDIATELY while another key "
          "is deduped AND pinned at the 24h backoff cap - suppression is per "
          "key, never per class, per box or global",
          (not ga["ok"]) and ga["attempt"] == 6
          and rN["attempt"] == 6 and 77760 <= rN["interval_seconds"] <= 95040
          and gbnew["ok"] and gbnew["reason"] == "clear" and gbnew["attempt"] == 0)

# D-ESC-TICK: REACHABILITY BY EXECUTION, not by grep. The gate is exercised
# through the WHOLE tick() pipeline with real detectors and a real ledger. The
# second tick injects a transport that RECORDS THE FACT IT WAS CALLED, so a
# leaking gate cannot hide: if the deduped key reaches ESC.send, the recorder
# fires and the assertion names it.
with tempfile.TemporaryDirectory() as td:
    os.environ["LOOP_STATE_DIR"] = os.path.join(td, "loop-protection")
    led = Ledger()
    _b = {"units": [], "windows": [], "runs": [], "wedge": {}}
    _c1 = [{"name": "esc-drill-1", "declared_schedule": "@daily",
            "actual_fires_per_day": 300}]
    _c2 = _c1 + [{"name": "esc-drill-2", "declared_schedule": "@daily",
                  "actual_fires_per_day": 300}]
    # The transport records the finding_id it was handed. The escalation PROSE
    # names no unit ("cron fired 300/day vs declared bound 1/day"), so WHICH key
    # got through is resolved from the ledger by id - measured, never inferred
    # from a string that happens to contain the name.
    _seen = []
    def _admit(url, body):
        _seen.append(json.loads(body.decode("utf-8"))["machine"]["finding_id"])
        return True
    def _record_and_refuse(url, body):
        _seen.append(json.loads(body.decode("utf-8"))["machine"]["finding_id"])
        raise RuntimeError("intake HTTP 429 (drill): refused")
    t1 = W.tick(dict(_b, crons=_c1), led, armed=True,
                escalate_transport=_admit, box="box-example")
    n1 = len(_seen)
    t2 = W.tick(dict(_b, crons=_c1), led, armed=True,
                escalate_transport=_record_and_refuse, box="box-example")
    n2 = len(_seen)
    t3 = W.tick(dict(_b, crons=_c2), led, armed=True,
                escalate_transport=_record_and_refuse, box="box-example")
    n3 = len(_seen)
    def _key_of(fid):
        r = led.conn.execute("SELECT dedup_key FROM findings WHERE finding_id=?",
                             (fid,)).fetchone()
        return r["dedup_key"] if r else None
    reached_t3 = [_key_of(x) for x in _seen[n2:]]
    states_t3 = {_key_of(r["finding_id"]): r["state"] for r in led.all_findings()}
    led.close()
    os.environ.pop("LOOP_STATE_DIR", None)
    print("    D-ESC-TICK tick1 (admitted)  : %s" % json.dumps(
        {k: t1[k] for k in ("escalated", "escalation_unsent", "escalation_suppressed",
                            "escalation_suppressed_by")}, sort_keys=True))
    print("    D-ESC-TICK tick2 (same key)  : %s" % json.dumps(
        {k: t2[k] for k in ("escalated", "escalation_unsent", "escalation_suppressed",
                            "escalation_suppressed_by")}, sort_keys=True))
    print("    D-ESC-TICK tick3 (+ NEW key) : %s" % json.dumps(
        {k: t3[k] for k in ("escalated", "escalation_unsent", "escalation_suppressed",
                            "escalation_suppressed_by")}, sort_keys=True))
    print("    D-ESC-TICK transport calls   : tick1=%d tick2=%d tick3=%d" %
          (n1, n2 - n1, n3 - n2))
    print("    D-ESC-TICK keys reaching the transport on tick3: %s" % reached_t3)
    check("D-ESC-TICK through the real tick(): 1st escalates, 2nd is SUPPRESSED "
          "and never reaches the transport, 3rd delivers the NEW key on the very "
          "tick the old key stays suppressed; a suppressed finding is never "
          "marked escalated and no tick raises",
          t1["escalated"] == 1 and t1["escalation_suppressed"] == 0 and t1["errors"] == 0
          and t2["escalated"] == 0 and t2["escalation_unsent"] == 0
          and t2["escalation_suppressed"] == 1
          and t2["escalation_suppressed_by"] == {"dedup": 1}
          and n2 == n1 and t2["errors"] == 0
          and t3["escalation_suppressed"] == 1 and t3["escalation_unsent"] == 1
          and t3["escalated"] == 0 and t3["errors"] == 0
          and reached_t3 == ["LP-A4|esc-drill-2"]
          and states_t3 == {"LP-A4|esc-drill-1": "escalated",
                            "LP-A4|esc-drill-2": "open"})

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

# D-POISON / D-POISON-CLEAN: the STOCK detector, proven in BOTH directions in one
# drill pair. D1-D4 measure flow and go quiet when a loop pauses; D5 measures how
# much of a transcript is ALREADY loop wreckage, which is what persists and keeps
# degrading every later turn. A detector is only worth shipping if it discriminates,
# so the control here is deliberately the HARDER file: the clean fixture is BIGGER
# (more bytes, 7x the records, more compaction checkpoints) than the poisoned one.
# If size or age could trip D5, D-POISON-CLEAN fails.
with tempfile.TemporaryDirectory() as td:
    os.environ["LOOP_STATE_DIR"] = os.path.join(td, "loop-protection")
    os.environ["LOOP_OPENCLAW_ROOT"] = os.path.join(td, "openclaw")
    os.environ["LOOP_NO_PROBES"] = "1"
    sess = os.path.join(td, "openclaw", "agents", "main", "sessions")
    os.makedirs(sess)
    import shutil as _sh
    for _n in ("loop-blocked-session.jsonl", "healthy-session.jsonl"):
        _sh.copy2(os.path.join(fx, _n), os.path.join(sess, _n))
    measured = W.collect_sessions()
    bymap = {os.path.basename(m["path"]): m for m in measured}
    poisoned = bymap["loop-blocked-session.jsonl"]
    control = bymap["healthy-session.jsonl"]
    f5 = D.d5_transcript_poison(measured, th)
    p1s = [x for x in f5 if x["severity"] == "P1" and x["loop_class"] == "LP-A8"]
    check("D-POISON blocked-burst transcript = P1 LP-A8 (ignition + the checkpoint "
          "carrier that survives a roll)",
          poisoned["blocked_records"] == 60 and poisoned["max_burst"] == 60
          and poisoned["poisoned_checkpoints"] == 1
          and len(p1s) == 1
          and "IGNITION" in p1s[0]["detail"] and "SECOND CARRIER" in p1s[0]["detail"])
    # The control is asserted TWICE: once as measured, and once with its byte count
    # forced past the memoryFlush re-arm floor (the real-world control archive was
    # 17,160,766 bytes - 8x that floor - with zero blocks). Size is a severity
    # MODIFIER in D5, never a trigger; this is the assertion that pins that down,
    # because the committed fixture is deliberately small and would not reach the
    # floor on its own.
    _huge_clean = dict(control, bytes=17160766)
    check("D-POISON-CLEAN control transcript is BIGGER and busier yet D5 is SILENT, "
          "and stays silent even 8x past the flush re-arm floor (size NEVER fires "
          "alone; a detector that fires on everything is not a detector)",
          control["bytes"] > poisoned["bytes"]
          and control["tail_records"] > poisoned["tail_records"]
          and control["checkpoint_rows"] >= poisoned["checkpoint_rows"]
          and control["blocked_records"] == 0
          and D.d5_transcript_poison([control], th) == []
          and D.d5_transcript_poison([_huge_clean], th) == []
          and len(f5) == 1)
    # ARMED: the poisoned transcript is MOVED to an archive (never deleted) and the
    # control is untouched; a transcript still being written is REFUSED.
    _past = __import__("time").time() - 3600
    for _n in ("loop-blocked-session.jsonl", "healthy-session.jsonl"):
        os.utime(os.path.join(sess, _n), (_past, _past))
    _led = Ledger()
    _sum = W.tick({"units": [], "windows": [], "runs": [], "crons": [], "wedge": {},
                   "sessions": W.collect_sessions()}, _led, armed=True,
                  escalate_transport=lambda u, b: True, box="box-example")
    _arch = [n for n in os.listdir(sess) if n.startswith("loop-blocked-session.loop-archive-")]
    _orig_gone = not os.path.exists(os.path.join(sess, "loop-blocked-session.jsonl"))
    _ctl_ok = os.path.isfile(os.path.join(sess, "healthy-session.jsonl"))
    _archived_bytes = os.path.getsize(os.path.join(sess, _arch[0])) if _arch else 0
    _led.close()
    check("D-POISON-ROLL armed tick ARCHIVES the poisoned transcript (moved, never "
          "deleted) and leaves the clean one untouched",
          _sum["applied"] == 1 and len(_arch) == 1 and _orig_gone and _ctl_ok
          and _archived_bytes == poisoned["bytes"])
    # copy2 preserves the SOURCE mtime, so without the utime below this fixture
    # would read as STALE once the repo checkout aged past roll_min_idle_minutes -
    # the drill would pass on a fresh clone and fail days later. Stamp it to NOW so
    # "still being written" means live at RUN time.
    _sh.copy2(os.path.join(fx, "loop-blocked-session.jsonl"),
              os.path.join(sess, "live-session.jsonl"))
    os.utime(os.path.join(sess, "live-session.jsonl"), None)
    _led = Ledger()
    _live_ev = [m for m in W.collect_sessions() if m["path"].endswith("live-session.jsonl")]
    _s = W.tick({"units": [], "windows": [], "runs": [], "crons": [], "wedge": {},
                 "sessions": _live_ev}, _led, armed=True,
                escalate_transport=lambda u, b: True, box="box-example")
    _live_still = os.path.isfile(os.path.join(sess, "live-session.jsonl"))
    _led.close()
    check("D-POISON-LIVE a transcript still being written is REFUSED even when armed "
          "(never roll the conversation someone is in); the P1 still lands",
          _s["findings"] == 1 and _s["applied"] == 0 and _live_still)
    for k in ("LOOP_STATE_DIR", "LOOP_OPENCLAW_ROOT", "LOOP_NO_PROBES"):
        os.environ.pop(k, None)

# D-POISON-REROLL: the roll must be IDEMPOTENT, its constructed name BOUNDED, and a
# filesystem failure must never kill the tick. Regression drill for a REPRODUCED
# crash: an LF-10 archive is a *.jsonl in the same sessions directory, keeps the
# original mtime (shutil.move preserves it) and keeps the poisoned bytes - so D5
# re-measured it as poisoned AND idle on the next tick and LF-10 archived the
# archive, appending another marker to the name every tick until the component
# passed 255 bytes and shutil.move raised ENAMETOOLONG - UNCAUGHT, killing the
# scheduled job (measured: 7 rolls, crash on the 8th). The healer self-breaker was
# blind to it because D5's unit comes from the FILENAME, which changed every roll.
# See tests/drills/D-POISON-REROLL.md for the tick-by-tick measurement.
with tempfile.TemporaryDirectory() as td:
    os.environ["LOOP_STATE_DIR"] = os.path.join(td, "loop-protection")
    os.environ["LOOP_OPENCLAW_ROOT"] = os.path.join(td, "openclaw")
    os.environ["LOOP_NO_PROBES"] = "1"
    sess = os.path.join(td, "openclaw", "agents", "main", "sessions")
    os.makedirs(sess)
    import shutil as _sh
    import time as _time
    _sh.copy2(os.path.join(fx, "loop-blocked-session.jsonl"),
              os.path.join(sess, "loop-blocked-session.jsonl"))

    def _age_all():
        _p = _time.time() - 3600  # past roll_min_idle_minutes, every tick
        for _e in os.listdir(sess):
            os.utime(os.path.join(sess, _e), (_p, _p))

    def _armed_tick(_led, sessions=None):
        return W.tick({"units": [], "windows": [], "runs": [], "crons": [],
                       "wedge": {},
                       "sessions": W.collect_sessions() if sessions is None else sessions},
                      _led, armed=True, escalate_transport=lambda u, b: True,
                      box="box-example")

    # 255 is written as a LITERAL here, never read from the module under test: a drill
    # that takes its ceiling from the code it is testing cannot catch a weakened bound.
    _FS_NAME_MAX = 255
    _led = Ledger()
    _rolls = 0
    _found = 0
    for _i in range(10):
        _age_all()
        _t_sum = _armed_tick(_led)
        _rolls += _t_sum["applied"]
        _found += _t_sum["findings"]
    _led.close()
    _names = sorted(os.listdir(sess))
    _archives = [n for n in _names if KC.ARCHIVE_MARKER in n]
    _longest = max(len(n.encode("utf-8")) for n in _names)
    # findings is asserted as well as applied, and that is the assertion that catches a
    # collector regression on its own: with the archive back in D5's scope the kill
    # card's own already-rolled guard still refuses the second roll, so `applied`
    # stays 1 and the defect hides. The FINDING count does not hide - a re-measured
    # archive raises a fresh P1 every tick, forever.
    check("D-POISON-REROLL 10 armed ticks over ONE poisoned transcript yield EXACTLY "
          "one finding and one roll, then silence; no archive is re-archived; no name "
          "growth",
          _rolls == 1 and _found == 1 and len(_names) == 1 and len(_archives) == 1
          and _archives[0].count(KC.ARCHIVE_MARKER) == 1
          and _longest <= _FS_NAME_MAX)

    # D-POISON-REROLL-BOUND: the name bound, on the helper AND end to end. A 240-byte
    # stem is legal on every filesystem this skill ships to; the natural archive name
    # built from it is NOT (240 + marker + stamp + suffix > 255), and that is an
    # OSError out of shutil.move - a crash in an unattended job, not a refusal.
    _stem = "s" * 240
    _stamp = "20260101T000000Z"
    _natural = "%s%s%s%s" % (_stem, KC.ARCHIVE_MARKER, _stamp, ".jsonl")
    _bounded = KC.bounded_archive_name(_stem, _stamp, ".jsonl")
    _bounded_again = KC.bounded_archive_name(_stem, _stamp, ".jsonl")
    _short_in = "session-abc"
    _short = KC.bounded_archive_name(_short_in, _stamp, ".jsonl")
    _long_src = os.path.join(sess, _stem + ".jsonl")
    _sh.copy2(os.path.join(fx, "loop-blocked-session.jsonl"), _long_src)
    _r_long = KC.lf10_archive_and_roll_session(_long_src, dry_run=False,
                                              idle_minutes=999.0)
    _long_arch = os.path.basename(_r_long.get("archived_to") or "")
    check("D-POISON-REROLL-BOUND over-long stem is truncated + sha256-tagged to <=255 "
          "bytes DETERMINISTICALLY, a fitting stem is left byte-identical, and a real "
          "240-byte-stem roll SUCCEEDS end to end",
          len(_natural.encode("utf-8")) > _FS_NAME_MAX
          and len(_bounded.encode("utf-8")) <= _FS_NAME_MAX
          and _bounded == _bounded_again
          and _bounded.endswith("%s%s%s" % (KC.ARCHIVE_MARKER, _stamp, ".jsonl"))
          and _short == "%s%s%s%s" % (_short_in, KC.ARCHIVE_MARKER, _stamp, ".jsonl")
          and _r_long.get("applied") is True
          and len(_long_arch.encode("utf-8")) <= _FS_NAME_MAX
          and os.path.isfile(os.path.join(sess, _long_arch))
          and not os.path.exists(_long_src))

    # D-POISON-REROLL-REFUSAL: an OSError from the move (read-only mount, permissions,
    # a parent that vanished mid-tick) must come back as {applied: False} with the
    # transcript left EXACTLY as found. Injected at shutil.move so the drill is
    # deterministic and does not depend on the euid running it.
    _refuse_src = os.path.join(sess, "refusal-session.jsonl")
    _sh.copy2(os.path.join(fx, "loop-blocked-session.jsonl"), _refuse_src)
    _before_bytes = open(_refuse_src, "rb").read()
    _real_move = KC.shutil.move

    def _dead_move(*_a, **_k):
        raise OSError(63, "File name too long (injected: no real FS fault needed)")
    KC.shutil.move = _dead_move
    try:
        _r_ref = KC.lf10_archive_and_roll_session(_refuse_src, dry_run=False,
                                                 idle_minutes=999.0)
    finally:
        KC.shutil.move = _real_move
    check("D-POISON-REROLL-REFUSAL an OSError from the archive move is a REFUSAL, not a "
          "crash; the transcript is left byte-identical and nothing is deleted",
          _r_ref.get("applied") is False and "refused" in _r_ref.get("reason", "")
          and os.path.isfile(_refuse_src)
          and open(_refuse_src, "rb").read() == _before_bytes)
    os.remove(_refuse_src)

    # D-POISON-REROLL-TICK: the OUTER boundary. Two poisoned transcripts, the FIRST
    # rigged to raise straight out of the kill card. The tick must return, count the
    # error, and STILL roll the second one - a single bad unit never kills a scheduled
    # tick, because a watchdog that dies quietly leaves a box that only looks watched.
    for _e in os.listdir(sess):
        os.remove(os.path.join(sess, _e))
    for _n in ("boom-session.jsonl", "good-session.jsonl"):
        _sh.copy2(os.path.join(fx, "loop-blocked-session.jsonl"), os.path.join(sess, _n))
    _age_all()
    _real_lf10 = KC.lf10_archive_and_roll_session

    def _selective_lf10(session_path, *_a, **_k):
        if "boom-session" in str(session_path):
            raise OSError(63, "File name too long (injected at the kill-card seam)")
        return _real_lf10(session_path, *_a, **_k)
    KC.lf10_archive_and_roll_session = _selective_lf10
    try:
        _led = Ledger()
        # boom FIRST, so a tick that aborts on it can never reach the good one
        _ordered = sorted(W.collect_sessions(),
                          key=lambda m: 0 if "boom-session" in m["path"] else 1)
        _s_tick = _armed_tick(_led, sessions=_ordered)
        _led.close()
    finally:
        KC.lf10_archive_and_roll_session = _real_lf10
    _after = sorted(os.listdir(sess))
    check("D-POISON-REROLL-TICK an exception escaping a kill card is CONTAINED: the "
          "tick returns, counts errors=1, and still processes the finding behind it",
          _ordered and "boom-session" in _ordered[0]["path"]
          and _s_tick["findings"] == 2 and _s_tick["errors"] == 1
          and _s_tick["applied"] == 1
          and "boom-session.jsonl" in _after
          and "good-session.jsonl" not in _after
          and len([n for n in _after if n.startswith("good-session")
                   and KC.ARCHIVE_MARKER in n]) == 1)
    for k in ("LOOP_STATE_DIR", "LOOP_OPENCLAW_ROOT", "LOOP_NO_PROBES"):
        os.environ.pop(k, None)

os.environ.pop("LOOP_ALLOW_ROOT", None)
if fails:
    print("DRILL FAILURES: %s" % fails, file=sys.stderr)
    sys.exit(4)
print("  all fixture drills PASS")
sys.exit(0)
PY
[ $? -eq 0 ] || bad "fixture drills"
fi   # RUN_OFFLINE

# ---- 4. THE STANDING GATE: this box, right now (v0.6.5) ---------------------
# Everything above runs against scratch fixtures and proves the CODE is right.
# It cannot see that this box carries 7 duplicate cron jobs, or that nothing has
# ticked since Tuesday. Two live facts, each with a NAMED negative:
#
#   D-CRON-ONE    EXACTLY ONE enabled loop-tick job, and it is ours.
#                 Instrument: `openclaw cron list --all` via loop_cron.py status.
#                 --all is load-bearing: without it a DISABLED job is invisible.
#   D-TICK-FRESH  the watchdog COMPLETED a tick within 45 minutes (three ticks).
#                 Instrument: ledger meta last_tick_ts via loop_ledger liveness.
#                 NOT MAX(findings.tick_ts) - that measures whether the box HAS a
#                 loop, so a healthy box reads as a dead watchdog. It produced a
#                 false "6 boxes unwatched" report on 2026-08-26; one of the six
#                 had ticked 13 minutes earlier.
#
# UNDETERMINED IS ITS OWN VERDICT (exit 5), never folded into PASS. An
# unreachable gateway, an unresolvable openclaw, a ledger that does not exist
# because this is a source checkout - none of those are evidence that the box is
# fine, and none are evidence that it is broken.
if [ "$RUN_LIVE" -eq 1 ]; then
    step "4/4 STANDING GATE (this box): D-CRON-ONE, D-TICK-FRESH"
    _cron_out="$(python3 "$SCRIPTS/loop_cron.py" status --json 2>&1)"; _cron_rc=$?
    case "$_cron_rc" in
        0) ok "D-CRON-ONE exactly one enabled loop-tick job, and it is ours"
           echo "      $(printf '%s' "$_cron_out" | tail -1)" ;;
        3) UNDET=$((UNDET+1))
           echo "  UNDETERMINED: D-CRON-ONE could not READ this box's cron table." >&2
           printf '%s\n' "$_cron_out" | sed 's/^/      /' >&2 ;;
        *) bad "D-CRON-ONE this box does NOT carry exactly one enabled loop-tick job"
           printf '%s\n' "$_cron_out" | sed 's/^/      /' >&2 ;;
    esac

    _live_out="$(python3 "$SCRIPTS/loop_ledger.py" liveness --max-age-minutes 45 2>&1)"; _live_rc=$?
    if [ "$_live_rc" -eq 0 ]; then
        ok "D-TICK-FRESH the watchdog completed a tick within 45 minutes"
        echo "      $(printf '%s' "$_live_out" | tail -1)"
    elif printf '%s' "$_live_out" | /usr/bin/grep -q '"last_tick_ts": null'; then
        # A pre-0.6.5 watchdog never wrote the key. Absence of the INSTRUMENT is
        # not absence of the TICK - reporting it as failure would be the same
        # false-negative this release exists to kill.
        UNDET=$((UNDET+1))
        echo "  UNDETERMINED: D-TICK-FRESH no last_tick_ts in this ledger (a watchdog" >&2
        echo "      older than v0.6.5, or one that has never completed a tick). Not a" >&2
        echo "      verdict on whether the box is watched - check D-CRON-ONE above." >&2
    else
        bad "D-TICK-FRESH no completed tick in the last 45 minutes (3 missed ticks)"
        printf '%s\n' "$_live_out" | sed 's/^/      /' >&2
    fi
fi

echo
if [ "$FAILS" -ne 0 ]; then
    echo "$TAG DRIFT: $FAILS check(s) failed." >&2
    exit 4
fi
if [ "$UNDET" -ne 0 ]; then
    echo "$TAG UNDETERMINED: $UNDET standing-gate check(s) could not be PROVEN." >&2
    echo "$TAG   Everything that COULD be checked passed. This is not a pass." >&2
    exit 5
fi
if [ "$RUN_LIVE" -eq 1 ] && [ "$RUN_OFFLINE" -eq 1 ]; then
    echo "$TAG VERIFIED: every self-test, scanner and drill passed, AND this box"
    echo "$TAG   carries exactly one loop-tick job with a fresh completed tick."
elif [ "$RUN_LIVE" -eq 1 ]; then
    echo "$TAG VERIFIED (standing gate only): exactly one loop-tick job, fresh tick."
else
    echo "$TAG VERIFIED (offline only): every self-test, scanner and drill passed."
    echo "$TAG   THE STANDING GATE DID NOT RUN - this says nothing about whether any"
    echo "$TAG   box is actually scheduled or ticking. Run verify.sh --live on the box."
fi
exit 0
