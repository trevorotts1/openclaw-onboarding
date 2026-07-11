#!/usr/bin/env bash
# =============================================================================
# SKILL 60 - ZHC EARLY WARNING SYSTEM :: verify.sh
# THE INDEPENDENT, FAILABLE DRILL BATTERY (spec 5.3 / Section 9).
# -----------------------------------------------------------------------------
# READ-ONLY and idempotent. Proves the whole system end to end against SCRATCH
# fixtures (never the live config): every script self-test, the four merge-gate
# scanners clean over the tree, and one drill per signal class (D-S1/S2, D-S3,
# D-S4, D-S6, D-S8, D-REVERT, D-DEADMAN). The live-pipeline D-ALERT drill fires a
# clearly-marked [DRILL] through the REAL gateway to the operator account ONLY
# when a gateway + operator target are configured; otherwise it is SKIPPED with a
# note (never a silent pass, never a client-visible message).
#
# EXIT: 0 verified, 4 drift/failure.
# =============================================================================
set -uo pipefail
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SCRIPTS="$SELF_DIR/scripts"
TAG="[ews-verify]"
FAILS=0

step() { echo; echo "== $* =="; }
ok()   { echo "  PASS: $*"; }
bad()  { echo "  FAIL: $*" >&2; FAILS=$((FAILS+1)); }

command -v python3 >/dev/null 2>&1 || { echo "$TAG FATAL: python3 required" >&2; exit 4; }

# ---- 1. every script self-test (the aggregate gate) -------------------------
step "1/4 every script --self-test"
if bash "$SELF_DIR/ews-entry.sh" --self-test >/tmp/ews-verify-selftest.$$ 2>&1; then
    ok "all script self-tests"
else
    bad "a script self-test failed (see /tmp/ews-verify-selftest.$$)"
    tail -20 /tmp/ews-verify-selftest.$$ >&2
fi
rm -f /tmp/ews-verify-selftest.$$ 2>/dev/null || true

# ---- 2. four merge-gate scanners CLEAN over the tree ------------------------
step "2/4 four merge-gate scanners CLEAN over the skill tree"
python3 "$SCRIPTS/guard-no-anthropic-runtime.py" >/dev/null 2>&1 && ok "guard-no-anthropic (0)" || bad "guard-no-anthropic"
SCAN_ALL_FILES=1 bash "$SCRIPTS/scan-no-secrets.sh" --root "$SELF_DIR" --strict >/dev/null 2>&1 && ok "scan-no-secrets (0)" || bad "scan-no-secrets"
SCAN_ALL_FILES=1 bash "$SCRIPTS/scan-no-client-identifiers.sh" --root "$SELF_DIR" >/dev/null 2>&1 && ok "scan-no-client-identifiers (0)" || bad "scan-no-client-identifiers"
SCAN_ALL_FILES=1 bash "$SCRIPTS/scan-no-json-exports.sh" --root "$SELF_DIR" >/dev/null 2>&1 && ok "scan-no-json-exports (0)" || bad "scan-no-json-exports"

# ---- 3. fixture drills, one per signal class --------------------------------
step "3/4 fixture drills (D-S1/S2, D-S3, D-CONTEXT-USAGE, D-S4, D-S6, D-S8, D-REVERT, D-DEADMAN)"
SCRIPTS="$SCRIPTS" SKILL_DIR="$SELF_DIR" python3 - <<'PY'
import json, os, sys, tempfile
sys.path.insert(0, os.environ["SCRIPTS"])
fx = os.path.join(os.environ["SKILL_DIR"], "tests", "fixtures")
import ews_common as C
import ews_baseline as B
import ews_sentinel as S
import ews_alert as A
from ews_ledger import Ledger, now_utc
import ews_snapshot as SNAP
import ews_revert as REV
import ews_fleet as FLEET
os.environ["EWS_ALLOW_ROOT"] = "1"  # allow the revert write in a CI/root sandbox

fails = []
def check(name, cond):
    print(("  PASS: " if cond else "  FAIL: ") + name)
    if not cond:
        fails.append(name)

def load(name):
    return json.load(open(os.path.join(fx, name)))

sig = C.load_signatures()
th = C.load_skill_config("thresholds.json")
clean = load("baseline-clean.json")

with tempfile.TemporaryDirectory() as td:
    os.environ["EWS_STATE_DIR"] = os.path.join(td, "ews")
    os.environ["EWS_CONFIG_PATH"] = os.path.join(fx, "baseline-clean.json")
    baseline = B.build_baseline(clean)

    # D-S4: cap-raise fixture -> unstamped raise = P1 with a revert line
    caps = load("cap-raise.json")
    d = B.compute_diff(baseline, caps)
    led = Ledger()
    f4 = S.sig_s4(d, led, "client", enforce_caps=False, revert_cmd="bash ews-entry.sh revert --to X")
    check("D-S4 unstamped cap raise = P1 + revert line",
          any(x["severity"] == "P1" and x["revert_cmd"] for x in f4))
    # stamped raise is silent
    raised_val = C.dotpath_get(caps, "agents.defaults.subagents.maxConcurrent")
    led.record_stamp("agents.defaults.subagents.maxConcurrent", C.sha256_of_value(raised_val), "operator")
    check("D-S4 stamped raise = silent",
          S.sig_s4(B.compute_diff(baseline, caps), led, "client", False) == [])
    led.close()

    # D-S3: subtractive misconfig fixture -> P1 broken-config to the OPERATOR
    sub = load("subtractive-misconfig.json")
    f3 = S.sig_s3(sub, th, context_window=sub.get("_contextWindow"))
    check("D-S3 subtractive misconfig = P1 to operator",
          any(x["severity"] == "P1" and x["route"] == S.R_OPERATOR for x in f3))
    # synthetic 86% usage -> handoff routed to the BOX agent, not the operator
    f3low = S.sig_s3({"agents": {"defaults": {}}}, th, usage_pct=86)
    check("D-S3 running-low routes to box agent (D5)",
          f3low and f3low[0]["route"] == S.R_BOX_AGENT)

    # D-CONTEXT-USAGE: _context_usage() computes a REAL usage_pct off a fixture
    # trajectory file, feeds sig_s3()'s handoff branch, and the narrow D5
    # Lane-2 exception (operator box only) fires - and stays silent everywhere
    # else. Before this fix, nothing in the tick computed usage_pct at all:
    # sig_s3(config, thresholds) was called with no usage argument, so the
    # 70%/85% branches were dead code (see D-CONTEXT-USAGE.md).
    oc_root = os.path.join(td, "oc-context-usage")
    sess_dir = os.path.join(oc_root, "agents", "main", "sessions")
    os.makedirs(sess_dir, exist_ok=True)
    with open(os.path.join(fx, "context-usage-86pct.trajectory.jsonl")) as fh:
        traj_text = fh.read()
    with open(os.path.join(sess_dir, "sess-example.trajectory.jsonl"), "w") as fh:
        fh.write(traj_text)
    os.environ["EWS_OPENCLAW_ROOT"] = oc_root
    cw_cfg = load("context-window-clean.json")
    u_pct, ctx_win = S._context_usage(cw_cfg, None)
    check("D-CONTEXT-USAGE live trajectory -> 86% of a 128000 window",
          u_pct == 86 and ctx_win == 128000)
    fh_handoff = S.sig_s3(cw_cfg, th, usage_pct=u_pct, context_window=ctx_win)
    check("D-CONTEXT-USAGE feeds sig_s3() a real S3|handoff finding",
          any(x["dedup_key"] == "S3|handoff" and x["route"] == S.R_BOX_AGENT
              for x in fh_handoff))
    # broken-config box: _context_usage never guesses a pct even with tokens present
    broken_ceiling_cfg = load("subtractive-misconfig.json")
    check("D-CONTEXT-USAGE never guesses a pct on an already-broken ceiling",
          S._context_usage(broken_ceiling_cfg, None) == (None, None))

    handoff_finding = [x for x in fh_handoff if x["dedup_key"] == "S3|handoff"][0]
    sent_log = []
    def fake_sender(account, target, text):
        sent_log.append({"account": account, "target": target, "text": text})
        return True, "fake-sent"
    os.environ["EWS_OPERATOR_CHAT"] = "9999operator-example"
    os.environ["EWS_BOX_NAME"] = "context-usage-drill-box"
    with Ledger() as led_ctx:
        led_ctx.set_meta("role", "operator")
    A.route_finding(handoff_finding, sender=fake_sender)
    check("D-CONTEXT-USAGE Lane 2 fires on the OPERATOR's own box",
          len(sent_log) == 1 and "working memory" in sent_log[0]["text"])
    notices = A.read_box_agent_notices()
    check("D-CONTEXT-USAGE the notice reader consumes the D5 self-notice",
          bool(notices) and A.read_box_agent_notices() == [])
    with Ledger() as led_ctx:
        led_ctx.set_meta("role", "client")
    client_finding = dict(handoff_finding, dedup_key="client-box|S3|handoff")
    A.route_finding(client_finding, sender=fake_sender)
    check("D-CONTEXT-USAGE Lane 2 NEVER fires on a client box (D5 boundary holds)",
          len(sent_log) == 1)  # unchanged - the client-box call sent nothing
    for k in ("EWS_OPENCLAW_ROOT", "EWS_OPERATOR_CHAT", "EWS_BOX_NAME"):
        os.environ.pop(k, None)

    # D-S1/S2: trajectory fixture -> out-of-allowlist model event flagged
    events = []
    for line in open(os.path.join(fx, "anthropic-fallback.trajectory.jsonl")):
        line = line.strip()
        if line:
            r = json.loads(line)
            events.append({"modelId": r.get("modelId"), "provider": r.get("provider"),
                           "sessionId": r.get("sessionId")})
    f2 = S.sig_s2(baseline.get("model_allowlist", []), events, "client", sig)
    check("D-S1/S2 out-of-allowlist runtime model flagged", bool(f2))

    # D-S6: root-owned config = P1
    f6 = S.sig_s6([], "root", "node", sig.get("known_writer_argv_tokens", []))
    check("D-S6 root-owned config = P1",
          any(x["severity"] == "P1" and x["key_path"] == "config.owner" for x in f6))

    # D-S8: planted synthetic key (fragment-assembled) caught value-free
    synthetic = "sk" + "-" + "0Aa1Bb2Cc3Dd4Ee5Ff6Gg7Hh8Ii9Jj"
    f8 = S.sig_s8([("scratch.jsonl", 'K="%s"' % synthetic)])
    check("D-S8 secret caught, value NOT in alert",
          bool(f8) and all(synthetic not in x["detail"] for x in f8))

    # D-S10: announce-cron fixture -> announce-to-non-operator = P1
    ann = load("announce-cron.json")
    f10 = S.sig_s10(baseline.get("cron_inventory", []), C.cron_inventory(ann))
    check("D-S10 announce-to-non-operator = P1",
          any(x["severity"] == "P1" for x in f10))

    # D-REVERT: snapshot the clean fixture, mutate the live path, revert byte-identical
    live = os.path.join(td, "openclaw.json")
    with open(live, "w") as fh:
        json.dump(clean, fh)
    os.environ["EWS_CONFIG_PATH"] = live
    snap = SNAP.take_snapshot(live)
    with open(live, "w") as fh:
        fh.write('{"tampered": true}')
    rc, res = REV.do_revert(snap["ts"], live)
    orig = open(os.path.join(fx, "baseline-clean.json"), "rb").read()
    reverted = open(live, "rb").read()
    check("D-REVERT restore byte-identical + validated",
          rc == 0 and reverted == open(snap["path"], "rb").read())

# D-DEADMAN (operator box): a box silent for 2 cycles = P1 sentinel-dark
with tempfile.TemporaryDirectory() as td:
    os.environ["EWS_FLEET_DIR"] = os.path.join(td, "ews-fleet")
    os.environ["EWS_STATE_DIR"] = os.path.join(td, "ews")
    FLEET.cmd_ingest("drill-box-example", {"last_tick_ts": now_utc(), "by_severity": {}})
    FLEET.cmd_cycle(dry_run=True)  # cycle 1
    res = FLEET.cmd_cycle(dry_run=True)  # cycle 2 -> silent since ingest at cycle 0
    check("D-DEADMAN box silent 2 cycles = sentinel dark",
          "drill-box-example" in res["sentinel_dark"])
    os.environ.pop("EWS_FLEET_DIR", None)

for k in ("EWS_STATE_DIR", "EWS_CONFIG_PATH", "EWS_ALLOW_ROOT"):
    os.environ.pop(k, None)

if fails:
    print("DRILL FAILURES: %s" % fails, file=sys.stderr)
    sys.exit(4)
print("  all fixture drills PASS")
sys.exit(0)
PY
[ $? -eq 0 ] || bad "fixture drills"

# ---- 4. live-pipeline D-ALERT (only when a gateway + operator target exist) --
step "4/4 D-ALERT live pipeline (real [DRILL] to the operator account)"
if command -v openclaw >/dev/null 2>&1 && { [ -n "${EWS_OPERATOR_CHAT:-}" ] || [ -n "${OPERATOR_TELEGRAM_CHAT_ID:-}" ]; }; then
    DRILL_JSON='{"signal":"S0","severity":"DRILL","key_path":"verify.drill","class":"drill","detail":"[DRILL] EWS verify.sh live-pipeline test - operator only, ignore.","route":"operator","dedup_key":"drill-'"$(date +%s)"'"}'
    if printf '%s' "$DRILL_JSON" | python3 "$SCRIPTS/ews_alert.py" route --finding - >/dev/null 2>&1; then
        ok "D-ALERT [DRILL] routed through the real gateway to the operator"
    else
        bad "D-ALERT could not deliver the [DRILL] message"
    fi
else
    echo "  SKIP: no gateway/operator target configured (D-ALERT proven live at the canary)."
fi

echo
if [ "$FAILS" -eq 0 ]; then
    echo "$TAG VERIFIED: every self-test, scanner, and drill passed."
    exit 0
else
    echo "$TAG DRIFT: $FAILS check(s) failed." >&2
    exit 4
fi
