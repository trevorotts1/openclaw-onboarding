#!/usr/bin/env python3
# =============================================================================
# PODCAST PRODUCTION ENGINE (Skill 58) :: EPISODE GATE B, ATTEMPT GATE
# -----------------------------------------------------------------------------
# The attempt-and-retry controller for the EPISODE gate (Gate B). Python stdlib
# only, no network, no model turn, no third-party import. It owns the persisted
# qc.attempts counter for one episode and enforces the furnace design's four
# runtime bounds (furnace-design Guardrail 4):
#
#   1  THREE-STRIKE CAP. Hard stop at qc_max_attempts (default 3) failed
#      attempts: stop, hand the founder the failing checks and the BEST draft.
#      Standards are never relaxed to clear a three-strike failure.
#   2  FROZEN RESEARCH. The research package is frozen after Step 3; QC retries
#      REUSE it. A retry may not re-run research. Sole exception: a Tier 1
#      check 12 (fabrication) failure unlocks ONE supplemental research pass of
#      at most web_research_bonus_on_fabrication_fail (default 4) calls, once
#      per episode.
#   3  TARGETED RETRIES. Attempts 2 and 3 revise only the failing sections and
#      dimensions. A full Step 6-8 rewrite is permitted ONLY on attempt 2 when
#      MORE THAN 4 rubric dimensions failed (default threshold 5). Attempt 3 is
#      always targeted. Worst case is roughly 1.6x a single write, never 3x.
#   4  ACCEPT only when Tier 1 is fully clean AND every rubric dimension scores
#      8 or higher. No averaging.
#
# THIS IS THE EPISODE GATE (Gate B), NEVER the 8.5 BUILD/MERGE gate (Gate A).
# Gate A (10-category fleet rubric at 8.5) decides whether BUILD WORK merges;
# Gate B decides whether an EPISODE ships. They are never conflated.
#
# STATE OWNERSHIP: this gate is the SOLE writer of its own per-episode attempt
# ledger at state/qc-attempts/<episode_id>.json. It does NOT write the episode
# record or the dashboard database; podcast_state.py remains the sole writer of
# those. Every decision emits a qc state_patch (attempts, last_failures,
# decision) for podcast_state.py to mirror, so the single-writer contract holds.
# This gate never sends a Telegram message; the founder notification it decides
# on is routed through alert-dedup.py by the caller (never a raw send).
#
# SINGLE SOURCE OF TRUTH for the numbers: config/qc-gate.json when present, else
# the built-in DEFAULTS below (so the gate runs standalone). --config overrides.
#
# SUBCOMMANDS:
#   record          record one attempt's QC result and decide the next action
#   authorize-retry validate a PROPOSED retry against policy (no state change)
#   status          print the current attempt ledger
#   reset           clear the ledger for an episode (guarded; needs --yes)
#   --self-test     run built-in fixtures and exit
#
# DECISIONS (in the emitted JSON "action" field):
#   ACCEPT               Tier 1 clean and every rubric dimension >= 8; deliver.
#   RETRY                a legal next attempt is authorized (scope + research).
#   STOP_NOTIFY_FOUNDER  three-strike cap reached; halt, escalate best draft.
#   AUTHORIZED           (authorize-retry) the proposed retry is legal.
#   REJECTED             (authorize-retry) the proposed retry violates policy.
#
# EXIT CODES (parse "action" from --json for the precise decision):
#   0  PROCEED   the pipeline has a legal forward action (ACCEPT / RETRY /
#                AUTHORIZED).
#   2  HALT      the pipeline must stop or escalate (STOP_NOTIFY_FOUNDER /
#                REJECTED).
#   3  USAGE/IO  bad arguments or unreadable state (fail-closed).
#
# USAGE:
#   python3 qc-attempt-gate.py record --episode pd-abc --result result.json [--json]
#   python3 qc-attempt-gate.py authorize-retry --episode pd-abc --scope targeted \
#       --rerun-research false [--json]
#   python3 qc-attempt-gate.py status --episode pd-abc
#   python3 qc-attempt-gate.py --self-test
#
# result.json shape:
#   {"tier1_failures": [1, 10], "rubric_failures": [{"dimension": 3, "score": 6}],
#    "fabrication_failed": false, "draft_ref": "path/or/id", "draft_score": 0.72}
# =============================================================================
"""Fail-closed attempt-and-retry controller for the Podcast Production Engine Episode Gate B (Skill 58)."""

import argparse
import json
import sys
import tempfile
from pathlib import Path

EXIT_PROCEED = 0
EXIT_HALT = 2
EXIT_USAGE = 3

_SKILL_DIR = Path(__file__).resolve().parent.parent
_DEFAULT_CONFIG = _SKILL_DIR / "config" / "qc-gate.json"
_DEFAULT_LEDGER_DIR = _SKILL_DIR / "state" / "qc-attempts"

DEFAULTS = {
    "qc_max_attempts": 3,
    "web_research_bonus_on_fabrication_fail": 4,
    # a full rewrite needs MORE THAN 4 failed dimensions, i.e. 5 or more.
    "full_rewrite_min_failed_dimensions": 5,
    "rubric_pass_min_score": 8,
}


def load_config(path=None):
    cfg = dict(DEFAULTS)
    p = Path(path) if path else _DEFAULT_CONFIG
    try:
        if p.is_file():
            override = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(override, dict):
                src = override.get("qc_gate", override)
                # tolerate the furnace consolidated block shape too.
                limits = override.get("podcast_engine", {}).get("limits", {}) if isinstance(override, dict) else {}
                for k in cfg:
                    if k in src:
                        cfg[k] = src[k]
                    elif k in limits:
                        cfg[k] = limits[k]
    except (OSError, ValueError):
        pass
    return cfg


# ---- ledger persistence (this gate is the sole writer of its own ledger) ----
def _ledger_path(episode_id, ledger_dir=None):
    base = Path(ledger_dir) if ledger_dir else _DEFAULT_LEDGER_DIR
    safe = "".join(c for c in str(episode_id) if c.isalnum() or c in "-_.")
    if not safe:
        raise ValueError("empty or invalid episode id")
    return base / (safe + ".json")


def _blank_ledger(episode_id):
    return {
        "episode_id": episode_id,
        "attempts": [],                 # one record per completed attempt
        "supplemental_research_used": False,
        "best_draft": None,             # {draft_ref, draft_score} highest score so far
        "decision": None,
        "closed": False,
    }


def load_ledger(episode_id, ledger_dir=None):
    p = _ledger_path(episode_id, ledger_dir)
    if p.is_file():
        obj = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(obj, dict) and obj.get("episode_id") == episode_id:
            for k, v in _blank_ledger(episode_id).items():
                obj.setdefault(k, v)
            return obj
    return _blank_ledger(episode_id)


def save_ledger(ledger, ledger_dir=None):
    p = _ledger_path(ledger["episode_id"], ledger_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    # atomic write so a crash never leaves a half-written counter.
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), suffix=".tmp")
    try:
        with open(fd, "w", encoding="utf-8") as fh:
            json.dump(ledger, fh, indent=2)
        Path(tmp).replace(p)
    except BaseException:
        try:
            Path(tmp).unlink()
        except OSError:
            pass
        raise
    return p


# ---- policy core ------------------------------------------------------------
def _result_is_pass(result, cfg):
    if result.get("tier1_failures"):
        return False
    for rf in result.get("rubric_failures") or []:
        if isinstance(rf, dict):
            score = rf.get("score")
            if score is None or score < cfg["rubric_pass_min_score"]:
                return False
        else:
            return False
    return True


def _failing_checks(result):
    out = []
    for t in result.get("tier1_failures") or []:
        out.append({"kind": "tier1", "check": t})
    for rf in result.get("rubric_failures") or []:
        if isinstance(rf, dict):
            out.append({"kind": "rubric", "dimension": rf.get("dimension"), "score": rf.get("score")})
        else:
            out.append({"kind": "rubric", "dimension": rf})
    return out


def _update_best_draft(ledger, result):
    ref = result.get("draft_ref")
    score = result.get("draft_score")
    if ref is None and score is None:
        return
    best = ledger.get("best_draft")
    cur = -1.0
    if isinstance(best, dict) and isinstance(best.get("draft_score"), (int, float)):
        cur = best["draft_score"]
    new = score if isinstance(score, (int, float)) else -1.0
    if best is None or new >= cur:
        ledger["best_draft"] = {"draft_ref": ref, "draft_score": score}


def _authorized_scope_for_next(prev_result, next_attempt_n, cfg):
    """What the NEXT attempt is allowed to do. Full rewrite is legal only on
    attempt 2 when more than 4 rubric dimensions failed; else targeted."""
    if next_attempt_n == 2:
        failed_dims = len(prev_result.get("rubric_failures") or [])
        if failed_dims >= cfg["full_rewrite_min_failed_dimensions"]:
            return "full_rewrite"
    return "targeted"


def record(episode_id, result, cfg, ledger_dir=None):
    ledger = load_ledger(episode_id, ledger_dir)
    if ledger.get("closed"):
        # idempotent: a closed episode is terminal; re-report the last decision.
        return ledger, _decision_payload(ledger, cfg, replay=True)

    attempt_n = len(ledger["attempts"]) + 1
    _update_best_draft(ledger, result)
    passed = _result_is_pass(result, cfg)
    entry = {
        "n": attempt_n,
        "passed": passed,
        "tier1_failures": result.get("tier1_failures") or [],
        "rubric_failures": result.get("rubric_failures") or [],
        "fabrication_failed": bool(result.get("fabrication_failed")),
        "draft_ref": result.get("draft_ref"),
        "draft_score": result.get("draft_score"),
    }
    ledger["attempts"].append(entry)

    if passed:
        ledger["decision"] = "ACCEPT"
        ledger["closed"] = True
    elif attempt_n >= cfg["qc_max_attempts"]:
        ledger["decision"] = "STOP_NOTIFY_FOUNDER"
        ledger["closed"] = True
    else:
        ledger["decision"] = "RETRY"

    payload = _decision_payload(ledger, cfg, prev_result=result)
    # consume the supplemental-research grant only when it is actually offered.
    if payload.get("authorized_rerun_research"):
        ledger["supplemental_research_used"] = True
    save_ledger(ledger, ledger_dir)
    return ledger, payload


def _decision_payload(ledger, cfg, prev_result=None, replay=False):
    decision = ledger.get("decision")
    attempts = ledger["attempts"]
    n = len(attempts)
    payload = {
        "episode_id": ledger["episode_id"],
        "action": decision,
        "attempt": n,
        "attempts_used": n,
        "attempts_max": cfg["qc_max_attempts"],
        "closed": ledger.get("closed", False),
        "replay": replay,
        "state_patch": {
            "qc": {
                "attempts": n,
                "last_failures": _failing_checks(attempts[-1]) if attempts else [],
                "decision": decision,
            }
        },
    }
    if decision == "ACCEPT":
        payload["message"] = "Tier 1 clean and every rubric dimension at or above %d; deliverable." % cfg["rubric_pass_min_score"]
    elif decision == "STOP_NOTIFY_FOUNDER":
        payload["failing_checks"] = _failing_checks(attempts[-1]) if attempts else []
        payload["best_draft"] = ledger.get("best_draft")
        payload["message"] = ("Three-strike cap reached at %d attempts. Halt and escalate the failing checks "
                              "and the best draft to the founder through alert-dedup. Standards are not relaxed."
                              % n)
    elif decision == "RETRY":
        src = prev_result if prev_result is not None else (attempts[-1] if attempts else {})
        next_n = n + 1
        scope = _authorized_scope_for_next(src, next_n, cfg)
        fab = bool(src.get("fabrication_failed"))
        grant = fab and not ledger.get("supplemental_research_used", False)
        payload["next_attempt"] = next_n
        payload["authorized_scope"] = scope
        payload["research_frozen"] = True
        payload["authorized_rerun_research"] = grant
        payload["research_call_budget"] = cfg["web_research_bonus_on_fabrication_fail"] if grant else 0
        payload["targeted_failures"] = _failing_checks(attempts[-1]) if attempts else []
        payload["message"] = ("Targeted retry authorized (scope=%s). Reuse the frozen research package%s."
                              % (scope, "" if not grant else "; one supplemental research pass unlocked by the fabrication failure"))
    return payload


def authorize_retry(episode_id, proposed_scope, proposed_rerun_research, cfg, ledger_dir=None):
    """Validate a PROPOSED retry request against policy WITHOUT recording it."""
    ledger = load_ledger(episode_id, ledger_dir)
    attempts = ledger["attempts"]
    n = len(attempts)
    next_n = n + 1
    base = {
        "episode_id": episode_id,
        "attempts_used": n,
        "attempts_max": cfg["qc_max_attempts"],
        "next_attempt": next_n,
        "proposed_scope": proposed_scope,
        "proposed_rerun_research": bool(proposed_rerun_research),
    }
    if ledger.get("closed") and ledger.get("decision") == "ACCEPT":
        base.update(action="REJECTED", reason="episode already accepted; no retry")
        return base
    if next_n > cfg["qc_max_attempts"]:
        base.update(action="REJECTED",
                    reason="three-strike cap reached (%d of %d used); must stop and notify the founder"
                    % (n, cfg["qc_max_attempts"]))
        return base
    prev = attempts[-1] if attempts else {}
    if proposed_scope == "full_rewrite":
        allowed = _authorized_scope_for_next(prev, next_n, cfg)
        if allowed != "full_rewrite":
            base.update(action="REJECTED",
                        reason=("full rewrite is legal only on attempt 2 when more than 4 rubric dimensions "
                                "failed; use a targeted retry"))
            return base
    elif proposed_scope not in ("targeted", "full_rewrite"):
        base.update(action="REJECTED", reason="scope must be 'targeted' or 'full_rewrite'")
        return base
    if proposed_rerun_research:
        fab = bool(prev.get("fabrication_failed"))
        if not fab:
            base.update(action="REJECTED",
                        reason="research is frozen; a re-run is unlocked only by a fabrication (check 12) failure")
            return base
        if ledger.get("supplemental_research_used", False):
            base.update(action="REJECTED",
                        reason="the one supplemental research pass has already been used for this episode")
            return base
    base.update(action="AUTHORIZED",
                reason="retry within policy",
                research_call_budget=(cfg["web_research_bonus_on_fabrication_fail"] if proposed_rerun_research else 0))
    return base


# ---- emit + CLI -------------------------------------------------------------
def _emit(payload, as_json):
    if as_json:
        print(json.dumps(payload, indent=2))
        return
    print("== Podcast Engine :: Episode Gate B, ATTEMPT gate ==")
    print("episode: %s" % payload.get("episode_id"))
    print("action: %s" % payload.get("action"))
    for k in ("attempt", "attempts_used", "attempts_max", "next_attempt",
              "authorized_scope", "research_frozen", "authorized_rerun_research",
              "research_call_budget", "proposed_scope", "proposed_rerun_research", "reason"):
        if k in payload:
            print("  %-24s %s" % (k, payload[k]))
    if payload.get("failing_checks"):
        print("  failing_checks: %s" % json.dumps(payload["failing_checks"]))
    if payload.get("best_draft"):
        print("  best_draft: %s" % json.dumps(payload["best_draft"]))
    if payload.get("message"):
        print("  note: %s" % payload["message"])


def _exit_for(action):
    if action in ("ACCEPT", "RETRY", "AUTHORIZED"):
        return EXIT_PROCEED
    if action in ("STOP_NOTIFY_FOUNDER", "REJECTED"):
        return EXIT_HALT
    return EXIT_USAGE


def cmd_record(args):
    cfg = load_config(args.config)
    try:
        result = json.loads(Path(args.result).read_text(encoding="utf-8"))
        if not isinstance(result, dict):
            raise ValueError("result JSON must be an object")
    except FileNotFoundError:
        _emit({"action": None, "reason": "result file not found: %s" % args.result}, args.json)
        return EXIT_USAGE
    except (OSError, ValueError) as exc:
        _emit({"action": None, "reason": "cannot read result: %s" % exc}, args.json)
        return EXIT_USAGE
    _ledger, payload = record(args.episode, result, cfg, ledger_dir=args.ledger_dir)
    _emit(payload, args.json)
    return _exit_for(payload.get("action"))


def cmd_authorize(args):
    cfg = load_config(args.config)
    rerun = str(args.rerun_research).strip().lower() in ("1", "true", "yes", "y")
    payload = authorize_retry(args.episode, args.scope, rerun, cfg, ledger_dir=args.ledger_dir)
    _emit(payload, args.json)
    return _exit_for(payload.get("action"))


def cmd_status(args):
    ledger = load_ledger(args.episode, args.ledger_dir)
    if args.json:
        print(json.dumps(ledger, indent=2))
    else:
        print("episode: %s  attempts: %d  decision: %s  closed: %s"
              % (ledger["episode_id"], len(ledger["attempts"]),
                 ledger.get("decision"), ledger.get("closed")))
        print("  supplemental_research_used: %s" % ledger.get("supplemental_research_used"))
        print("  best_draft: %s" % json.dumps(ledger.get("best_draft")))
    return EXIT_PROCEED


def cmd_reset(args):
    if not args.yes:
        print("refusing to reset without --yes", file=sys.stderr)
        return EXIT_USAGE
    p = _ledger_path(args.episode, args.ledger_dir)
    if p.is_file():
        p.unlink()
    print("reset: %s" % args.episode)
    return EXIT_PROCEED


# =============================================================================
# SELF-TEST: every decision path exercised on a temp ledger directory.
# =============================================================================
def self_test():
    import shutil
    cfg = load_config(None)
    ok = True
    tmp = Path(tempfile.mkdtemp(prefix="qc-gate-selftest-"))

    def show(name, good, extra=""):
        nonlocal ok
        ok = ok and good
        print("  [%s] %-36s %s" % ("PASS" if good else "MISS", name, extra))

    try:
        # accept on the first clean attempt
        _l, p = record("ep-accept", {"tier1_failures": [], "rubric_failures": [
            {"dimension": d, "score": 9} for d in range(1, 11)], "draft_score": 0.9}, cfg, ledger_dir=tmp)
        show("accept_first_pass", p["action"] == "ACCEPT" and _exit_for(p["action"]) == 0)

        # a rubric dimension below 8 is not a pass
        _l, p = record("ep-lowdim", {"tier1_failures": [], "rubric_failures": [
            {"dimension": 4, "score": 7}], "draft_score": 0.5}, cfg, ledger_dir=tmp)
        show("low_rubric_dim_retries", p["action"] == "RETRY")

        # targeted retry on a single-dimension failure (attempt 2 stays targeted)
        show("attempt2_targeted_scope", p.get("authorized_scope") == "targeted")

        # full rewrite offered only when > 4 dims fail on attempt 1
        _l, p = record("ep-many", {"tier1_failures": [], "rubric_failures": [
            {"dimension": d, "score": 6} for d in range(1, 7)], "draft_score": 0.4}, cfg, ledger_dir=tmp)
        show("attempt2_full_rewrite_offered", p["action"] == "RETRY" and p.get("authorized_scope") == "full_rewrite")

        # three-strike cap: three failed attempts stop and escalate best draft
        eid = "ep-strike"
        record(eid, {"tier1_failures": [3], "rubric_failures": [], "draft_score": 0.30}, cfg, ledger_dir=tmp)
        record(eid, {"tier1_failures": [3], "rubric_failures": [], "draft_score": 0.55}, cfg, ledger_dir=tmp)
        _l, p3 = record(eid, {"tier1_failures": [3], "rubric_failures": [], "draft_score": 0.40}, cfg, ledger_dir=tmp)
        show("three_strike_stop", p3["action"] == "STOP_NOTIFY_FOUNDER" and _exit_for(p3["action"]) == 2)
        show("best_draft_is_highest_score",
             isinstance(p3.get("best_draft"), dict) and p3["best_draft"].get("draft_score") == 0.55,
             extra="best=%s" % json.dumps(p3.get("best_draft")))
        show("strike_reports_failing_checks", bool(p3.get("failing_checks")))

        # frozen research: authorize-retry rejects a research re-run with no fabrication fail
        a = authorize_retry("ep-lowdim", "targeted", True, cfg, ledger_dir=tmp)
        show("research_rerun_rejected_no_fabrication", a["action"] == "REJECTED" and _exit_for(a["action"]) == 2)

        # fabrication failure unlocks exactly one supplemental research pass
        eid2 = "ep-fab"
        _l, pf = record(eid2, {"tier1_failures": [12], "rubric_failures": [],
                               "fabrication_failed": True, "draft_score": 0.6}, cfg, ledger_dir=tmp)
        show("fabrication_unlocks_research",
             pf["action"] == "RETRY" and pf.get("authorized_rerun_research") is True
             and pf.get("research_call_budget") == cfg["web_research_bonus_on_fabrication_fail"])
        a2 = authorize_retry(eid2, "targeted", True, cfg, ledger_dir=tmp)
        show("supplemental_research_single_use",
             a2["action"] == "REJECTED", extra=a2.get("reason", ""))

        # illegal full rewrite on a small failure is rejected
        a3 = authorize_retry("ep-lowdim", "full_rewrite", False, cfg, ledger_dir=tmp)
        show("illegal_full_rewrite_rejected", a3["action"] == "REJECTED")

        # cap: a fourth authorize after three strikes is rejected
        a4 = authorize_retry(eid, "targeted", False, cfg, ledger_dir=tmp)
        show("authorize_after_cap_rejected", a4["action"] == "REJECTED")

        # accepted episode refuses further retries
        a5 = authorize_retry("ep-accept", "targeted", False, cfg, ledger_dir=tmp)
        show("accepted_refuses_retry", a5["action"] == "REJECTED")

        # legal targeted retry authorizes
        a6 = authorize_retry("ep-lowdim", "targeted", False, cfg, ledger_dir=tmp)
        show("legal_targeted_authorized", a6["action"] == "AUTHORIZED" and _exit_for(a6["action"]) == 0)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("== self-test: %s ==" % ("ALL ASSERTIONS PASSED" if ok else "FAILURES ABOVE"))
    return EXIT_PROCEED if ok else EXIT_HALT


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Attempt-and-retry controller for the Podcast Production Engine Episode Gate B.")
    ap.add_argument("--self-test", dest="self_test", action="store_true", help="run built-in fixtures and exit")
    sub = ap.add_subparsers(dest="cmd")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--episode", required=True, help="episode id (job key)")
    common.add_argument("--ledger-dir", dest="ledger_dir", help="attempt-ledger directory (default: skill state dir)")
    common.add_argument("--config", help="path to config/qc-gate.json (default: skill config or built-ins)")
    common.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    p_rec = sub.add_parser("record", parents=[common], help="record one attempt result and decide")
    p_rec.add_argument("--result", required=True, help="path to the attempt result JSON")

    p_auth = sub.add_parser("authorize-retry", parents=[common], help="validate a proposed retry")
    p_auth.add_argument("--scope", required=True, choices=["targeted", "full_rewrite"])
    p_auth.add_argument("--rerun-research", dest="rerun_research", default="false")

    sub.add_parser("status", parents=[common], help="print the attempt ledger")

    p_reset = sub.add_parser("reset", parents=[common], help="clear the ledger for an episode")
    p_reset.add_argument("--yes", action="store_true", help="confirm the reset")

    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if args.cmd == "record":
        return cmd_record(args)
    if args.cmd == "authorize-retry":
        return cmd_authorize(args)
    if args.cmd == "status":
        return cmd_status(args)
    if args.cmd == "reset":
        return cmd_reset(args)
    ap.error("a subcommand is required (record | authorize-retry | status | reset) or --self-test")


if __name__ == "__main__":
    sys.exit(main())
