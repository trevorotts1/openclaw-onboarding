#!/usr/bin/env python3
"""SKS-008 plan-dict test for config/fix-classes.json (October OpenClaw update).

Offline and hermetic: reads the shipped JSON, builds plan dicts through the real
loop_killcards.plan()/apply(), runs no subprocess and no network. LOOP_NO_PROBES=1.

Covers spec Fix 12 (LF-8 heartbeat proposal) and Fix 13 (LF-9/10/11 re-point; LF-12 text).
Run:  python3 tests/test_fix_classes_plan.py      (exit 0 = pass)
"""
import copy
import json
import os
import sys
from pathlib import Path

os.environ["LOOP_NO_PROBES"] = "1"
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import loop_killcards as KC  # noqa: E402  (path set above)

LF8_COMMANDS = [
    "openclaw config set agents.defaults.heartbeat.isolatedSession true --strict-json",
    "openclaw config set agents.defaults.heartbeat.lightContext true --strict-json",
]
PARAM_KEYS = {  # OpenClaw 2026.9.x gateway schemas (SessionsAbortParams / SessionsResetParams)
    "sessions.abort": {"key", "runId", "agentId", "clearQueued"},
    "sessions.reset": {"key", "agentId", "reason", "expectedSessionId"},
}
FORBIDDEN_IN_COMMANDS = (" mv ", "shutil", "rm ", ".jsonl", "pm2 jlist", "launchctl print")


def _by_id(fx):
    return {f["id"]: f for f in fx["fix_classes"]}


def _active(entry):
    """Everything the class says NOW (superseded_text is the preserved old record)."""
    return json.dumps({k: v for k, v in entry.items() if k != "superseded_text"}).lower()


def _params(cmd):
    """Parse the --params '<json>' payload out of a gateway-call command string."""
    head = "--params '"
    assert head in cmd and cmd.endswith("'"), "gateway call must carry --params '<json>': %r" % cmd
    return json.loads(cmd.split(head, 1)[1][:-1])


def check_all(fx):
    fcs = _by_id(fx)
    # nothing was deleted: the full LF-1..LF-12 set is still present
    assert set(fcs) == {"LF-%d" % i for i in range(1, 13)}, sorted(fcs)

    # ---- LF-8 (Fix 12): prepared proposal, exact commands, Tier 2, no model ----
    lf8 = fcs["LF-8"]
    assert lf8["tier"] == 2, "LF-8 STAYS Tier 2"
    assert lf8["commands"] == LF8_COMMANDS, lf8["commands"]
    assert all(c.endswith("--strict-json") for c in lf8["commands"])
    assert lf8["snapshot_before"] == [
        "openclaw config get agents.defaults.heartbeat.isolatedSession",
        "openclaw config get agents.defaults.heartbeat.lightContext"]
    rv = lf8["revert_commands"]
    assert len(rv) == 2 and all("<PRIOR_" in c and c.endswith("--strict-json") for c in rv), rv
    assert "prior" in lf8["reversible_in"].lower()
    assert lf8["revert_commands_if_prior_unset"] == [
        "openclaw config unset agents.defaults.heartbeat.isolatedSession",
        "openclaw config unset agents.defaults.heartbeat.lightContext"]
    assert lf8["touches_only"] == [
        "agents.defaults.heartbeat.isolatedSession", "agents.defaults.heartbeat.lightContext"]
    assert "model" not in _active(lf8), "LF-8 must never reference a heartbeat/client model"
    assert "requireapproval" not in _active(lf8)
    assert "PREPARED PROPOSAL" in lf8["title"] and "never applied" in lf8["title"]

    # ---- LF-9 (Fix 13): sessions.abort RPC, Tier 2 ----
    lf9 = fcs["LF-9"]
    assert lf9["tier"] == 2
    assert len(lf9["commands"]) == 1 and lf9["commands"][0].startswith(
        "openclaw gateway call sessions.abort --params '")
    p9 = _params(lf9["commands"][0])
    assert set(p9) <= PARAM_KEYS["sessions.abort"] and "clearQueued" not in p9, p9
    assert "no supported run-abort cli was found" not in _active(lf9), "stale July claim"
    assert "2026.7.1-2" not in _active(lf9)
    assert "sessions.abort" in lf9["proof"] and "chat.abort" in lf9["proof"]

    # ---- LF-10 (Fix 13): sessions.reset / sessions archive, gateway-mediated ----
    lf10 = fcs["LF-10"]
    assert lf10["tier"] == 2, "LF-10 is Tier 1 only AFTER sessions.reset is proven on the operator box"
    assert len(lf10["commands"]) == 1 and lf10["commands"][0].startswith(
        "openclaw gateway call sessions.reset --params '")
    p10 = _params(lf10["commands"][0])
    assert set(p10) <= PARAM_KEYS["sessions.reset"] and "expectedSessionId" in p10, p10
    alts = lf10["alternative_commands"]
    assert alts and all(a.startswith("openclaw sessions archive ") for a in alts), alts
    assert any("--dry-run" in a for a in alts)
    cmds = " | ".join(lf10["commands"] + alts)
    assert not any(bad in cmds for bad in FORBIDDEN_IN_COMMANDS), cmds
    assert any("no active run" in p.lower() for p in lf10["preconditions"])
    assert "history" in lf10["reversible_in"].lower()
    assert "move the archived transcript back" not in _active(lf10), "stale file-move revert"

    # ---- LF-11 (Fix 13 item 4): retired, kept as a record, nothing to run ----
    lf11 = fcs["LF-11"]
    assert lf11["retired"] is True and lf11["commands"] == []
    assert lf11["title"].startswith("RETIRED")
    assert "does not create compaction checkpoint" in lf11["proof"]

    # ---- LF-12: text matches the sessions.abort RPC with clearQueued ----
    lf12 = fcs["LF-12"]
    assert lf12["tier"] == 1
    assert len(lf12["commands"]) == 1
    p12 = _params(lf12["commands"][0])
    assert p12.get("clearQueued") is True and set(p12) <= PARAM_KEYS["sessions.abort"], p12
    assert "clearqueued:true" in _active(lf12)
    assert "park below is what actually stops" not in _active(lf12)

    # ---- every re-pointed command goes through the running gateway, never a file ----
    for fid in ("LF-8", "LF-9", "LF-10", "LF-12"):
        for c in fcs[fid]["commands"] + fcs[fid].get("alternative_commands", []):
            assert c.startswith("openclaw "), (fid, c)
            assert not any(bad in c for bad in FORBIDDEN_IN_COMMANDS), (fid, c)

    # ---- disable-never-delete: the pre-October text is preserved verbatim ----
    for fid in ("LF-8", "LF-9", "LF-10", "LF-11", "LF-12"):
        sup = fcs[fid]["superseded_text"]
        assert {"title", "reversible_in", "proof"} <= set(sup), fid
    assert "heartbeat allowlist flip" in fcs["LF-8"]["superseded_text"]["title"]
    assert "2026.7.1-2" in fcs["LF-9"]["superseded_text"]["proof"]
    assert "move the archived transcript back" in fcs["LF-10"]["superseded_text"]["reversible_in"]


def check_plan_dicts():
    """Through the real plan()/apply(): Tier 2 classes are proposal-only, even ARMED."""
    for lc, fid in (("LP-A2", "LF-8"), ("LP-A8-abort", "LF-9"),
                    ("LP-A8", "LF-10"), ("LP-A8-checkpoints", "LF-11")):
        p = KC.plan({"loop_class": lc, "finding_id": 7})
        assert p["fix_class"] == fid and p["tier"] == 2, (lc, p)
        # executors={} + armed=True: a Tier 2 class must still return 'planned' (never runs)
        r = KC.apply(p, None, armed=True, executors={})
        assert r["status"] == "planned" and "proposal only" in r["detail"], (fid, r)
        assert r["escalate"] is False, (fid, r)
    p12 = KC.plan({"loop_class": "LP-A10", "finding_id": 12})
    assert p12["fix_class"] == "LF-12" and p12["tier"] == 1


def _expect_fail(label, mutate):
    fx = json.loads((ROOT / "config" / "fix-classes.json").read_text(encoding="utf-8"))
    mutate(_by_id(fx))
    try:
        check_all(fx)
    except AssertionError:
        return
    raise SystemExit("MUTATION SURVIVED (test would not catch it): " + label)


def main():
    fx = json.loads((ROOT / "config" / "fix-classes.json").read_text(encoding="utf-8"))
    check_all(fx)
    check_plan_dicts()
    print("  fix-classes plan case: PASS (LF-8 exact commands + revert + Tier 2 + no model; "
          "LF-9 sessions.abort; LF-10 sessions.reset; LF-11 retired; LF-12 clearQueued)")

    # mutation checks: each broken variant MUST be rejected by check_all
    _expect_fail("LF-8 drops --strict-json", lambda f: f["LF-8"]["commands"].__setitem__(
        0, LF8_COMMANDS[0].replace(" --strict-json", "")))
    _expect_fail("LF-8 promoted to Tier 1", lambda f: f["LF-8"].__setitem__("tier", 1))
    _expect_fail("LF-8 mentions a model", lambda f: f["LF-8"]["commands"].append(
        "openclaw config set agents.defaults.heartbeat.model x --strict-json"))
    _expect_fail("LF-9 back to July claim", lambda f: f["LF-9"].__setitem__(
        "proof", "As of OpenClaw 2026.7.1-2 no supported run-abort CLI was found"))
    _expect_fail("LF-10 file move", lambda f: f["LF-10"]["commands"].__setitem__(
        0, "mv session.jsonl session.jsonl.bak"))
    _expect_fail("LF-11 un-retired", lambda f: f["LF-11"].__setitem__("retired", False))
    _expect_fail("LF-12 loses clearQueued", lambda f: f["LF-12"]["commands"].__setitem__(
        0, "openclaw gateway call sessions.abort --params '{\"key\":\"k\"}'"))
    print("  mutation case: PASS (7 broken variants all rejected)")
    print("[test_fix_classes_plan] PASS")


if __name__ == "__main__":
    main()
