#!/usr/bin/env python3
"""KIE dispatch: plan section 5.4 stage driver. stdlib only.

Stage order (never reordered, never partially skipped):

  1. ledger reserve      ``spend_ledger.plan`` + ``reserve`` (directive 18/24.4)
  2. Skill 74 health     read ``adapter_mode``; only ``active`` continues
  3. Skill 74 preflight  balance must cover price x 1.30
  4. prompt-budget check exit 4 = over max, exit 3 = under floor
  5. run / save          one Skill 74 ``run`` call, files saved immediately
  6. ledger reconcile    succeeded/failed settle; unknown retains reservation

Shadow / off: stop **before the approval card**. The client is told generation
is not switched on. There is no fallback to a private KIE client and no second
transport - Skill 74 is the one KIE path - and a skip is recorded as
*not generated*: the reservation is released at zero cost, never settled as a
generation.

Unknown: a ``run`` answer whose ``state`` is not a known adapter state, an
unparsable ``run`` answer, or an exception raised while ``run`` was in flight,
marks the reservation ``unknown`` and STOPS. No retry, no resubmit; reconcile
from provider records or operator evidence first.

This module carries no HTTP client of its own: the adapter path comes from
``KIE_LIVE_ADAPTER_PATH`` or a search relative to this file, and every call is
one ``subprocess`` of ``kie_live_adapter.py`` (injectable as ``runner`` so the
tests never touch the network or the ledger of a real run).

Exit codes (EXIT): ok 0, error 1, waiting 3, parked 4, rejected 5.
Output: a single JSON object (the envelope) on stdout.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import spend_ledger as L  # noqa: E402  (sibling module in the same core/ tree)

TOOL_NAME = "kie_dispatch"
TOOL_VERSION = "1.0.0"
SCHEMA_VERSION = "blackceo.kie-dispatch/envelope/v1"
EXIT = {"ok": 0, "error": 1, "waiting": 3, "parked": 4, "rejected": 5}

ADAPTER_SKILL = "74-kie-live-adapter"
ADAPTER_SCRIPT = "kie_live_adapter.py"
ADAPTER_RELS = (
    ("74-kie-live-adapter", "scripts", "kie_live_adapter.py"),
    ("onboarding", "74-kie-live-adapter", "scripts", "kie_live_adapter.py"),
    ("skills", "74-kie-live-adapter", "scripts", "kie_live_adapter.py"),
    (".claude", "skills", "74-kie-live-adapter", "scripts", "kie_live_adapter.py"),
    ("installer-registration", "helpers", "74-kie-live-adapter",
     "scripts", "kie_live_adapter.py"),
    ("999-setup", "installer-registration", "helpers", "74-kie-live-adapter",
     "scripts", "kie_live_adapter.py"),
)

# Adapter states that mean "generation produced output".
RUN_OK = "success"
RUN_SKIPPED = "skipped"
RUN_FAILED = "fail"
RUN_PENDING = ("queued", "running")


class DispatchError(Exception):
    """Carries a machine reason code; never escapes dispatch()."""


def envelope(command, outcome, reason_code, next_action="", run_id="",
             logical_key="", attempt_id="", evidence=None, state_version=0):
    return {"schema_version": SCHEMA_VERSION, "tool": TOOL_NAME,
            "tool_version": TOOL_VERSION, "command": command,
            "run_id": run_id, "logical_key": logical_key,
            "attempt_id": attempt_id, "outcome": outcome,
            "reason_code": reason_code, "next_action": next_action,
            "evidence": evidence or {}, "state_version": state_version}


def resolve_adapter(explicit=None):
    """Path to Skill 74's entrypoint, or None. Never a hard-coded user path."""
    if explicit:
        return explicit if os.path.isfile(explicit) else None
    env = os.environ.get("KIE_LIVE_ADAPTER_PATH")
    if env:
        return env if os.path.isfile(env) else None
    start = Path(__file__).resolve()
    for parent in (start,) + tuple(start.parents):
        for rel in ADAPTER_RELS:
            cand = parent.joinpath(*rel)
            if cand.is_file():
                return str(cand)
    return None


def make_runner(timeout=300):
    """Real Skill 74 subprocess. The tests never use this."""
    def _run(argv):
        r = subprocess.run([sys.executable] + list(argv),
                           capture_output=True, text=True, timeout=timeout,
                           env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        return r.returncode, r.stdout
    return _run


def _call(runner, adapter, args):
    """One Skill 74 command -> (rc, parsed_or_None, raw). No exception escapes."""
    try:
        rc, out = runner([adapter] + list(args))
    except Exception as e:                                  # noqa: BLE001
        return -1, None, "runner-error: %s" % e
    rc = rc if isinstance(rc, int) else -1
    if isinstance(out, (dict, list)):                       # already parsed
        try:
            return rc, out, json.dumps(out, sort_keys=True, default=str)
        except Exception:                                   # noqa: BLE001
            return rc, None, ""
    try:
        return rc, json.loads(out), out
    except Exception:                                       # noqa: BLE001
        return rc, None, out if isinstance(out, str) else str(out)


def _settle(db, run_id, logical_key, attempt_id, owner, job_state, final,
            actual_cost, task_id="", provider_ref="", evidence_ref=""):
    """reserved/submitted -> succeeded|failed -> reconciled. Zero on not-generated."""
    st = job_state
    if st == "reserved":
        if task_id:
            sub = L.mark_submitted(db, run_id, logical_key, attempt_id,
                                   task_id, owner=owner)
            if sub["outcome"] == "ok":
                st = "submitted"
        if st == "reserved":
            can = L.cancel(db, run_id, logical_key, attempt_id, owner=owner)
            if can["outcome"] == "ok":
                st = "unknown"
    if st in ("submitted", "unknown"):
        term = L.mark_terminal(db, run_id, logical_key, attempt_id, final,
                               owner=owner)
        if term["outcome"] != "ok":
            return term
    return L.reconcile(db, run_id, logical_key, attempt_id, final, actual_cost,
                       provider_ref=provider_ref, evidence_ref=evidence_ref,
                       owner=owner)


def _hold_unknown(db, run_id, logical_key, attempt_id, owner, extra):
    """Retain the reservation and stop. Never retry from here."""
    unk = L.mark_unknown(db, run_id, logical_key, attempt_id, owner=owner)
    ev = dict(extra)
    ev.update({"retries": 0, "resubmitted": False, "disposition": "unknown"})
    return envelope(
        "dispatch", "waiting", "unknown-outcome-no-retry",
        "reconcile via provider records or operator evidence before any retry; "
        "do not auto-resubmit",
        run_id=run_id, logical_key=logical_key, attempt_id=attempt_id,
        evidence=ev, state_version=unk.get("state_version", 0))


def dispatch(*, model, request, save_dir, ledger_db, run_id, logical_key,
             attempt_id, estimated_cost, prompt="", units=1, stage="kie",
             owner="kie-dispatch", adapter_path=None, runner=None,
             timeout=300):
    """Run the plan 5.4 pipeline once. Returns one envelope; never raises."""
    if not model:
        return envelope("dispatch", "rejected", "MODEL_REQUIRED",
                        "name the model id; this module never picks one",
                        run_id=run_id, logical_key=logical_key,
                        attempt_id=attempt_id)
    if not isinstance(estimated_cost, int) or estimated_cost < 0:
        return envelope("dispatch", "rejected", "UNKNOWN_PRICE",
                        "record an estimated cost before dispatch",
                        run_id=run_id, logical_key=logical_key,
                        attempt_id=attempt_id)
    run = runner or make_runner(timeout)

    # ---- 1. ledger reserve -------------------------------------------------
    digest = L.digest_request(request)
    pl = L.plan(ledger_db, run_id, logical_key, attempt_id, digest,
                estimated_cost, stage=stage, owner=owner)
    if pl["outcome"] != "ok":
        return envelope("dispatch", pl["outcome"], pl["reason_code"],
                        pl.get("next_action", ""), run_id=run_id,
                        logical_key=logical_key, attempt_id=attempt_id,
                        state_version=pl.get("state_version", 0))
    rs = L.reserve(ledger_db, run_id, logical_key, attempt_id, owner=owner)
    if rs["outcome"] != "ok":
        return envelope("dispatch", rs["outcome"], rs["reason_code"],
                        rs.get("next_action", ""), run_id=run_id,
                        logical_key=logical_key, attempt_id=attempt_id,
                        state_version=rs.get("state_version", 0))
    job_state = "reserved"

    def stop(outcome, reason, next_action, evidence, final="failed", cost=0,
             settle=True):
        """Leave the ledger clean and return the envelope."""
        if settle:
            rec = _settle(ledger_db, run_id, logical_key, attempt_id, owner,
                          job_state, final, cost)
            if rec["outcome"] not in ("ok", "parked"):
                outcome, reason = "error", "ledger-settle-failed"
                next_action = rec.get("next_action", "") or next_action
                evidence = dict(evidence or {}, ledger=rec)
        return envelope("dispatch", outcome, reason, next_action,
                        run_id=run_id, logical_key=logical_key,
                        attempt_id=attempt_id, evidence=evidence or {},
                        state_version=rec.get("state_version", 0)
                        if settle else rs.get("state_version", 0))

    # ---- 2. Skill 74 health (mode) ----------------------------------------
    adapter = resolve_adapter(adapter_path)
    if not adapter:
        return stop("error", "adapter-not-found",
                    "install Skill 74 (%s); there is no private KIE client"
                    % ADAPTER_SKILL,
                    {"skill": ADAPTER_SKILL, "generated": False})
    h_rc, h, h_raw = _call(run, adapter, ["health", "--json"])
    if h is None:
        return stop("error", "adapter-health-unreadable",
                    "Skill 74 health did not answer JSON; do not dispatch",
                    {"rc": h_rc, "raw": (h_raw or "")[-400:],
                     "generated": False})
    mode = h.get("adapter_mode")
    if mode not in ("off", "shadow", "active"):
        return stop("error", "adapter-mode-unknown",
                    "Skill 74 reported no usable mode; do not dispatch",
                    {"adapter_mode": mode, "generated": False})
    if mode != "active":
        return stop(
            "waiting", "generation-not-switched-on",
            "tell the client generation is not switched on; nothing was "
            "generated and no approval card exists. Activate Skill 74 "
            "(mode=active) before dispatching again.",
            {"adapter_mode": mode, "generated": False,
             "approval_card": None, "fallback_used": False,
             "disposition": "not-generated",
             "client_message": "Generation is not switched on for this "
                               "client yet - nothing has been generated."})

    # ---- 3. Skill 74 preflight --------------------------------------------
    p_rc, p, p_raw = _call(run, adapter,
                           ["preflight", "--model", model,
                            "--units", str(units), "--json"])
    if p is None:
        return stop("error", "preflight-unreadable",
                    "Skill 74 preflight did not answer JSON; do not dispatch",
                    {"rc": p_rc, "raw": (p_raw or "")[-400:],
                     "generated": False})
    p_data = p.get("data") or {}
    p_err = p.get("error") or {}
    shortfall = p_data.get("shortfall")
    if p.get("state") == "fail" or p_data.get("ok") is False:
        reason = ("preflight-shortfall"
                  if p_err.get("code") == "insufficient_credits"
                  or shortfall is not None else "preflight-failed")
        return stop(
            "rejected", reason,
            "top up the balance so it covers price x 1.30, then retry with a "
            "new attempt id; nothing was generated",
            {"adapter_state": p.get("state"), "code": p_err.get("code"),
             "shortfall": shortfall, "data": p_data, "generated": False})

    # ---- 4. prompt-budget --check -----------------------------------------
    tmp = tempfile.mkdtemp(prefix="kie-dispatch-")
    try:
        prompt_file = os.path.join(tmp, "prompt.txt")
        with open(prompt_file, "w", encoding="utf-8") as f:
            f.write(prompt or "")
        b_rc, b, b_raw = _call(run, adapter,
                               ["prompt-budget", "--model", model, "--check",
                                "--prompt-file", prompt_file, "--json"])
        if b is None:
            return stop("rejected", "prompt-budget-unreadable",
                        "Skill 74 prompt-budget did not answer JSON; do not "
                        "dispatch",
                        {"exit_code": b_rc, "raw": (b_raw or "")[-400:],
                         "generated": False})
        if b_rc == 4 or (b.get("data") or {}).get("status") == "ABOVE_MAX":
            d = b.get("data") or {}
            return stop("rejected", "prompt-over-max",
                        "cut %s characters from the prompt (max %s) and recheck"
                        % (d.get("cut", "?"), d.get("max", "?")),
                        {"exit_code": b_rc, "data": d, "generated": False})
        if b_rc == 3 or (b.get("data") or {}).get("status") == "BELOW_FLOOR":
            d = b.get("data") or {}
            return stop("rejected", "prompt-below-floor",
                        "add %s characters to the prompt (floor %s) and recheck"
                        % (d.get("add_to_floor", "?"), d.get("floor", "?")),
                        {"exit_code": b_rc, "data": d, "generated": False})
        if b_rc != 0:
            return stop("rejected", "prompt-budget-failed",
                        "Skill 74 prompt-budget refused the prompt; fix it "
                        "before dispatch",
                        {"exit_code": b_rc, "raw": (b_raw or "")[-400:],
                         "generated": False})

        # ---- 5. run / save -------------------------------------------------
        req_file = os.path.join(tmp, "request.json")
        with open(req_file, "w", encoding="utf-8") as f:
            json.dump(request, f, sort_keys=True)
        os.makedirs(save_dir, exist_ok=True)
        try:
            r_rc, r, r_raw = _call(run, adapter,
                                   ["run", "--request", req_file,
                                    "--save-dir", save_dir, "--json"])
        except Exception as e:                              # pragma: no cover
            return _hold_unknown(ledger_db, run_id, logical_key, attempt_id,
                                 owner, {"stage": "run", "error": str(e)})
        if r is None:
            return _hold_unknown(
                ledger_db, run_id, logical_key, attempt_id, owner,
                {"stage": "run", "rc": r_rc, "raw": (r_raw or "")[-400:]})
        state = r.get("state")
        task_id = r.get("task_id") or ""
        if state == RUN_OK:
            credits = r.get("credits_consumed")
            if isinstance(credits, (int, float)) and not isinstance(credits, bool):
                actual = int(credits)
                warn = []
            else:
                actual = int(estimated_cost)
                warn = ["ACTUAL_COST_UNREPORTED"]
            rec = _settle(ledger_db, run_id, logical_key, attempt_id, owner,
                          "reserved", "succeeded", actual, task_id=task_id,
                          provider_ref="kie", evidence_ref=task_id)
            if rec["outcome"] not in ("ok", "parked"):
                return envelope("dispatch", rec["outcome"],
                                rec.get("reason_code", "ledger-settle-failed"),
                                rec.get("next_action", ""),
                                run_id=run_id, logical_key=logical_key,
                                attempt_id=attempt_id,
                                evidence={"task_id": task_id,
                                          "saved_paths": r.get("saved_paths") or []},
                                state_version=rec.get("state_version", 0))
            return envelope(
                "dispatch", "ok", "KIE_DISPATCH_OK",
                "files saved before the links expire; record the receipt",
                run_id=run_id, logical_key=logical_key,
                attempt_id=attempt_id,
                evidence={"adapter_mode": mode, "generated": True,
                          "task_id": task_id,
                          "saved_paths": r.get("saved_paths") or [],
                          "credits_consumed": credits,
                          "actual_cost": actual, "warnings": warn,
                          "retries": 0},
                state_version=rec.get("state_version", 0))
        if state == RUN_SKIPPED:
            return stop(
                "waiting", "generation-skipped-not-generated",
                "Skill 74 skipped the run; skipped is not generated. Do not "
                "fall back to a private KIE client - activate mode=active.",
                {"adapter_state": state, "generated": False,
                 "approval_card": None, "fallback_used": False,
                 "disposition": "not-generated"})
        if state == RUN_FAILED:
            err = r.get("error") or {}
            credits = r.get("credits_consumed")
            cost = (int(credits) if isinstance(credits, (int, float))
                    and not isinstance(credits, bool) else 0)
            return stop("rejected", "kie-run-failed",
                        "Skill 74 reported a failed run (%s); reconcile the "
                        "charge, then retry with a new attempt id"
                        % (err.get("code") or "unknown"),
                        {"adapter_state": state, "error": err,
                         "task_id": task_id, "actual_cost": cost,
                         "generated": False},
                        final="failed", cost=cost)
        if state in RUN_PENDING:
            if not task_id:
                return _hold_unknown(
                    ledger_db, run_id, logical_key, attempt_id, owner,
                    {"stage": "run", "adapter_state": state,
                     "remote_task_id": None})
            sub = L.mark_submitted(ledger_db, run_id, logical_key, attempt_id,
                                   task_id, owner=owner)
            return envelope(
                "dispatch", "waiting", "kie-run-incomplete",
                "poll this job; polling is not resubmitting",
                run_id=run_id, logical_key=logical_key,
                attempt_id=attempt_id,
                evidence={"adapter_state": state, "task_id": task_id,
                          "generated": False},
                state_version=sub.get("state_version", 0))
        return _hold_unknown(ledger_db, run_id, logical_key, attempt_id, owner,
                             {"stage": "run", "adapter_state": state,
                              "task_id": task_id,
                              "known_states": [RUN_OK, RUN_SKIPPED,
                                               RUN_FAILED] + list(RUN_PENDING)})
    except Exception as e:                                  # noqa: BLE001
        return stop("error", "dispatch-internal-error",
                    str(e)[:300], {"error": str(e)[:300], "generated": False})
    finally:
        try:
            for name in os.listdir(tmp):
                os.unlink(os.path.join(tmp, name))
            os.rmdir(tmp)
        except OSError:
            pass


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="kie_dispatch.py",
        description="Plan 5.4 KIE dispatch: reserve -> Skill 74 health -> "
                    "preflight -> prompt-budget -> run/save -> reconcile.")
    d = ap.add_subparsers(dest="cmd", required=True)
    x = d.add_parser("dispatch", help="Run one reserved KIE generation.")
    x.add_argument("--model", required=True, help="Exact model id (never picked here).")
    x.add_argument("--request", required=True, help="Skill 74 req.json path.")
    x.add_argument("--save-dir", required=True)
    x.add_argument("--ledger", required=True, help="spend_ledger SQLite path.")
    x.add_argument("--run-id", required=True)
    x.add_argument("--logical-key", required=True)
    x.add_argument("--attempt-id", required=True)
    x.add_argument("--cost", type=int, required=True,
                   help="Estimated cost in ledger units, recorded before dispatch.")
    x.add_argument("--units", type=int, default=1)
    x.add_argument("--prompt", default=None)
    x.add_argument("--prompt-file", default=None)
    x.add_argument("--stage", default="kie")
    x.add_argument("--owner", default="kie-dispatch")
    x.add_argument("--adapter", default=None,
                   help="Path to kie_live_adapter.py (default: search).")
    x.add_argument("--timeout", type=int, default=300)
    a = ap.parse_args(argv)

    if a.cmd == "dispatch":
        with open(a.request, encoding="utf-8") as f:
            request = json.load(f)
        if a.prompt_file:
            if a.prompt_file == "-":
                prompt = sys.stdin.read()
            else:
                with open(a.prompt_file, encoding="utf-8") as f:
                    prompt = f.read()
        else:
            prompt = a.prompt or ""
        env = dispatch(model=a.model, request=request, save_dir=a.save_dir,
                       ledger_db=a.ledger, run_id=a.run_id,
                       logical_key=a.logical_key, attempt_id=a.attempt_id,
                       estimated_cost=a.cost, prompt=prompt, units=a.units,
                       stage=a.stage, owner=a.owner, adapter_path=a.adapter,
                       timeout=a.timeout)
        json.dump(env, sys.stdout, indent=2, sort_keys=True, default=str)
        sys.stdout.write("\n")
        return EXIT[env["outcome"]]
    return 1


if __name__ == "__main__":
    sys.exit(main())
