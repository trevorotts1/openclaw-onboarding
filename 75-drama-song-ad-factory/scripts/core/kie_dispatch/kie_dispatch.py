#!/usr/bin/env python3
"""KIE dispatch: plan section 5.4 stage driver. stdlib only.

Stage order (never reordered, never partially skipped):

  0. placeholder check   request JSON may carry no unfilled placeholder (F10);
                         refused before the ledger or Skill 74 is touched
  1. ledger reserve      ``spend_ledger.plan`` + ``reserve`` (directive 18/24.4)
  2. Skill 74 health     read ``adapter_mode``; only ``active`` continues
  3. Skill 74 preflight  balance must cover price x 1.30
  4. prompt-budget check exit 4 = over max, exit 3 = under floor
  5. submit/wait/save    Skill 74 ``submit`` (task id persisted immediately),
                         ``wait`` with a modality budget (video 1200 / music
                         600 / image 300, or request["timeout"]), outer
                         subprocess W+120 so the inner wait always returns
                         first, then ``save`` files on success
  6. ledger reconcile    succeeded/failed settle; unknown retains reservation

Shadow / off: stop **before the approval card**. The client is told generation
is not switched on. There is no fallback to a private KIE client and no second
transport - Skill 74 is the one KIE path - and a skip is recorded as
*not generated*: the reservation is released at zero cost, never settled as a
generation.

Unknown: a wait timeout (``state`` running plus ``error.code`` timeout), an
unparsable submit/wait answer, or an exception raised while either was in
flight, marks the reservation ``unknown`` and STOPS - with the remote task id
already stored when submit produced one. No retry, no resubmit; reconcile from
provider records or operator evidence first.

F10 (manual 02): a request whose JSON still carries an unfilled placeholder
(``{{``, ``}}``, ``<TODO``, ``<PLACEHOLDER`` - any case - or the bare tokens
``TODO``, ``PLACEHOLDER``, ``KEYFRAME:`` from the Kiesett incident) is refused
at submission with reason ``REQUEST_PLACEHOLDER`` before anything is reserved
or sent. Any failed task is reported within one poll: the wait path fails on
the FIRST poll answer reading ``fail`` (stage evidence row + ``failure_poll``
in the envelope), never after retries or silent skips.

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
import sqlite3
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

# Outer wait budget per modality (manual C2). request["timeout"] wins.
_WAIT_S = {"video": 1200, "music": 600, "image": 300}
_VIDEO_CUES = ("video", "veo", "kling", "seedance", "hailuo", "pixverse",
               "runway", "wan2", "i2v", "t2v")
_MUSIC_CUES = ("music", "suno", "audio", "tts", "speech", "elevenlabs",
               "voice")

# F10 placeholder tokens. Case-insensitive: {{ }} and the bracketed TODO /
# PLACEHOLDER markers a template leaves behind. Case-sensitive: the bare
# Kiesett-incident tokens, so ordinary prose ("todo list", "Keyframe: 12")
# never trips them. The bare "<" is deliberately excluded - real prompts
# contain "<" as prose every day.
_PLACEHOLDER_CI = ("{{", "}}", "<todo", "<placeholder")
_PLACEHOLDER_CS = ("TODO", "PLACEHOLDER", "KEYFRAME:")


def _walk_str_leaves(obj, path=""):
    """Every string leaf of request JSON with its JSON path."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk_str_leaves(v, "%s/%s" % (path, k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_str_leaves(v, "%s[%d]" % (path, i))
    elif isinstance(obj, str):
        yield path, obj


def _find_placeholder(request):
    """First unfilled placeholder in a request payload -> (path, token), or
    None. Scans the whole request (model/timeout included), not just input -
    a template can hide in any field."""
    for path, value in _walk_str_leaves(request):
        low = value.lower()
        for tok in _PLACEHOLDER_CI:
            if tok in low:
                return path, tok
        for tok in _PLACEHOLDER_CS:
            if tok in value:
                return path, tok
    return None


def _registry_entry(model, adapter=None):
    """Skill 74 registry row for model, or None. Path is relative to adapter."""
    path = adapter or resolve_adapter()
    if not path:
        return None
    reg = (Path(path).resolve().parent.parent / "references"
           / "kie-model-registry.json")
    try:
        data = json.loads(Path(reg).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    models = data.get("models") if isinstance(data, dict) else None
    if not isinstance(models, list):
        return None
    for m in models:
        if isinstance(m, dict) and m.get("id") == model:
            return m
    return None


def _modality(model, adapter=None):
    entry = _registry_entry(model, adapter)
    if entry:
        ttypes = " ".join(entry.get("taskType") or []).lower()
        if "video" in ttypes:
            return "video"
        if "music" in ttypes or "audio" in ttypes or "speech" in ttypes:
            return "music"
        if "image" in ttypes:
            return "image"
    mid = (model or "").lower()
    if any(c in mid for c in _VIDEO_CUES):
        return "video"
    if any(c in mid for c in _MUSIC_CUES):
        return "music"
    return "image"


def _wait_budget_s(request, model, adapter=None):
    """W for Skill 74 wait; the outer subprocess runs with W+120."""
    t = request.get("timeout") if isinstance(request, dict) else None
    if isinstance(t, (int, float)) and not isinstance(t, bool) and t > 0:
        return int(t)
    return _WAIT_S[_modality(model, adapter)]


def _record_stage_evidence(db, run_id, logical_key, attempt_id, stage,
                           status="fail", task_id="", error=None,
                           adapter_state=""):
    """Dispatch evidence for the resolver (events kind='dispatch'). Best-effort."""
    payload = {"stage": stage, "adapter_state": adapter_state,
               "error": error or {}, "task_id": task_id or None,
               "remote_task_id": task_id or None}
    try:
        conn = sqlite3.connect(db, timeout=10)
        try:
            conn.execute(
                "INSERT OR IGNORE INTO events("
                "run_id,logical_key,attempt_id,kind,provider_event_id,"
                "provider_seq,status,payload_json,created_at)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (run_id, logical_key, attempt_id, "dispatch", stage, 0, status,
                 json.dumps(payload, sort_keys=True), L._now_iso()))
            conn.commit()
        finally:
            conn.close()
    except Exception:                                      # noqa: BLE001
        pass


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
    # ---- 0. placeholder check (F10) ---------------------------------------
    # Before the ledger: a refused request reserves nothing and calls nothing.
    ph = _find_placeholder(request)
    if ph:
        return envelope(
            "dispatch", "rejected", "REQUEST_PLACEHOLDER",
            "fill the placeholder at %s (%r) in the request file and dispatch "
            "again; nothing was reserved and nothing was sent" % (ph[0], ph[1]),
            run_id=run_id, logical_key=logical_key, attempt_id=attempt_id,
            evidence={"placeholder_path": ph[0], "placeholder_token": ph[1],
                      "generated": False})
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

        # ---- 5. submit / wait / save ---------------------------------------
        # Split of the old single `run` call (manual C2): the outer subprocess
        # timer used to fire before Skill 74's own wait, so a long video left
        # an unknown row with no task id and the resolver zero-settled spend.
        req_file = os.path.join(tmp, "request.json")
        with open(req_file, "w", encoding="utf-8") as f:
            json.dump(request, f, sort_keys=True)
        os.makedirs(save_dir, exist_ok=True)

        wait_s = _wait_budget_s(request, model, adapter)
        # Injected runners (tests) already stand in for Skill 74; the real
        # wait subprocess gets W+120 so the inner wait always returns first.
        wait_run = run if runner is not None else make_runner(wait_s + 120)

        def _unknown_at(stage, extra, task=""):
            ev = {"stage": stage, "wait_timeout_s": wait_s}
            ev.update(extra)
            if task:
                ev["task_id"] = task
                ev["remote_task_id"] = task
            return _hold_unknown(ledger_db, run_id, logical_key, attempt_id,
                                 owner, ev)

        # (1) submit --------------------------------------------------------
        try:
            s_rc, s, s_raw = _call(run, adapter,
                                   ["submit", "--request", req_file, "--json"])
        except Exception as e:                              # pragma: no cover
            return _unknown_at("submit", {"error": str(e)})
        if s is None:
            return _unknown_at("submit",
                               {"rc": s_rc, "raw": (s_raw or "")[-400:]})

        s_state = s.get("state")
        task_id = s.get("task_id") or ""
        s_err = s.get("error") if isinstance(s.get("error"), dict) else {}

        if s_state == RUN_SKIPPED:
            return stop(
                "waiting", "generation-skipped-not-generated",
                "Skill 74 skipped the submit; skipped is not generated. Do not "
                "fall back to a private KIE client - activate mode=active.",
                {"stage": "submit", "adapter_state": s_state,
                 "generated": False, "approval_card": None,
                 "fallback_used": False, "disposition": "not-generated"})
        if s_state == RUN_FAILED:
            # Definite submit error: settle now. Never leave an unknown row
            # that the resolver could zero-settle without asking KIE.
            credits = s.get("credits_consumed")
            cost = (int(credits) if isinstance(credits, (int, float))
                    and not isinstance(credits, bool) else 0)
            _record_stage_evidence(
                ledger_db, run_id, logical_key, attempt_id, "submit",
                status="fail", task_id=task_id, error=s_err,
                adapter_state=s_state)
            return stop(
                "rejected", "kie-submit-failed",
                "Skill 74 submit refused the job (%s); nothing was generated"
                % (s_err.get("code") or "unknown"),
                {"stage": "submit", "adapter_state": s_state, "error": s_err,
                 "task_id": task_id or None, "actual_cost": cost,
                 "generated": False},
                final="failed", cost=cost)

        if s_state == RUN_OK and not task_id:
            # Sync family already finished inside submit; no pollable id.
            task_id = "sync-" + L.digest_request(request)[:12]

        if task_id:
            sub = L.mark_submitted(ledger_db, run_id, logical_key, attempt_id,
                                   task_id, owner=owner)
            if sub.get("outcome") == "ok":
                job_state = "submitted"
        elif s_state in RUN_PENDING:
            return _unknown_at("submit",
                               {"adapter_state": s_state,
                                "remote_task_id": None})
        elif s_state != RUN_OK:
            return _unknown_at(
                "submit",
                {"adapter_state": s_state, "task_id": task_id or None,
                 "remote_task_id": task_id or None,
                 "known_states": [RUN_OK, RUN_FAILED, RUN_SKIPPED]
                 + list(RUN_PENDING)})

        # (2) wait (async only; sync submit already answered) ---------------
        src = s
        if s_state in RUN_PENDING:
            try:
                w_rc, wj, w_raw = _call(
                    wait_run, adapter,
                    ["wait", "--task-id", task_id,
                     "--timeout", str(wait_s), "--json"])
            except Exception as e:                          # pragma: no cover
                return _unknown_at("wait", {"error": str(e)}, task_id)
            if wj is None:
                return _unknown_at("wait",
                                   {"rc": w_rc, "raw": (w_raw or "")[-400:]},
                                   task_id)
            w_state = wj.get("state")
            w_err = wj.get("error") if isinstance(wj.get("error"), dict) else {}
            task_id = wj.get("task_id") or task_id
            if w_state == RUN_FAILED:
                credits = wj.get("credits_consumed")
                cost = (int(credits) if isinstance(credits, (int, float))
                        and not isinstance(credits, bool) else 0)
                # F10: a failed task is reported within ONE poll - this poll.
                # The evidence row and the rejected envelope carry the task id,
                # the outcome and the receipt, and the ledger settles failed
                # immediately; no further polling, no silent skip.
                _record_stage_evidence(
                    ledger_db, run_id, logical_key, attempt_id, "wait",
                    status="fail", task_id=task_id, error=w_err,
                    adapter_state=w_state)
                return stop(
                    "rejected", "kie-run-failed",
                    "Skill 74 reported a failed run (%s); reconcile the "
                    "charge, then retry with a new attempt id"
                    % (w_err.get("code") or "unknown"),
                    {"stage": "wait", "adapter_state": w_state, "error": w_err,
                     "task_id": task_id, "actual_cost": cost,
                     "failure_poll": 1, "generated": False},
                    final="failed", cost=cost)
            if w_state != RUN_OK:
                # wait timeout (running + error.code == timeout) and any other
                # non-terminal answer: hold unknown WITH the task id so the
                # resolver queries KIE instead of settling at zero.
                return _unknown_at(
                    "wait",
                    {"adapter_state": w_state, "error": w_err,
                     "wait_timeout_s": wait_s,
                     "timed_out": (w_state == "running"
                                   and w_err.get("code") == "timeout")},
                    task_id)
            src = wj

        # (3) save ----------------------------------------------------------
        try:
            v_rc, v, v_raw = _call(run, adapter,
                                   ["save", "--task-id", task_id,
                                    "--save-dir", save_dir, "--json"])
        except Exception as e:                              # pragma: no cover
            v, v_raw, v_rc = None, str(e), -1
        saved = (v.get("saved_paths") or []) if isinstance(v, dict) else []
        credits = src.get("credits_consumed")
        if isinstance(credits, (int, float)) and not isinstance(credits, bool):
            actual = int(credits)
            warn = []
        else:
            actual = int(estimated_cost)
            warn = ["ACTUAL_COST_UNREPORTED"]
        if not saved:
            warn.append("SAVE_FAILED")

        rec = _settle(ledger_db, run_id, logical_key, attempt_id, owner,
                      job_state, "succeeded", actual, task_id=task_id,
                      provider_ref="kie", evidence_ref=task_id)
        if rec["outcome"] not in ("ok", "parked"):
            return envelope("dispatch", rec["outcome"],
                            rec.get("reason_code", "ledger-settle-failed"),
                            rec.get("next_action", ""),
                            run_id=run_id, logical_key=logical_key,
                            attempt_id=attempt_id,
                            evidence={"task_id": task_id,
                                      "saved_paths": saved},
                            state_version=rec.get("state_version", 0))
        return envelope(
            "dispatch", "ok", "KIE_DISPATCH_OK",
            "files saved before the links expire; record the receipt",
            run_id=run_id, logical_key=logical_key, attempt_id=attempt_id,
            evidence={"adapter_mode": mode, "generated": True,
                      "task_id": task_id,
                      "saved_paths": saved,
                      "credits_consumed": credits,
                      "actual_cost": actual, "warnings": warn,
                      "wait_timeout_s": wait_s, "retries": 0},
            state_version=rec.get("state_version", 0))
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
                    "preflight -> prompt-budget -> submit/wait/save -> reconcile.")
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
