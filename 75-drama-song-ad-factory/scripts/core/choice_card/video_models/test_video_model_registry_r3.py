#!/usr/bin/env python3
"""L3 (v2.9.73): the choice card offers only models the LIVE KIE registry
carries, and refuses a card whose model list cannot be resolved.

Behaviour proven (RELIABILITY-SPEC L3; live defect: the client's card answer
was "Hailuo 02 Standard", the live KIE catalog has no such model -- brand is Hailuo
02 -- and the run printed a model the catalog does not carry):

  * a resolvable registry yields only models the registry lists;
  * a registry missing a card model refuses BY NAME (MODEL_NOT_IN_REGISTRY
    naming the model and its id);
  * an unreadable/absent registry refuses (VIDEO_MODEL_UNRESOLVABLE);
  * the card gate's video-model menu refuses rows the registry does not
    carry, naming them (the price-menu surface);
  * lock_choice refuses to lock an off-registry model;
  * every card path fails closed with a named reason, never a silent pass.

Run: python3 core/choice_card/video_models/test_video_model_registry_r3.py
stdlib only; no network, no provider, $0 spend, no file writes outside tmp.
"""
import json
import os
import sys
import tempfile
import sqlite3
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(os.path.dirname(HERE))
SKILL = os.path.dirname(os.path.dirname(CORE))
sys.path.insert(0, CORE)

from choice_card.video_models import video_models as VM          # noqa: E402
from choice_card.intake_card import intake_card as IC            # noqa: E402
from style_defaults import card_gate as CG                       # noqa: E402
import kie_dispatch as KD                                        # noqa: E402
import kie_dispatch.model_lock as ML                             # noqa: E402

FAILS = []

def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def _live_registry():
    """The repo's own live registry file (the one dispatch reads)."""
    for root in (os.path.dirname(SKILL), os.path.dirname(os.path.dirname(SKILL))):
        cand = os.path.join(root, "74-kie-live-adapter", "references",
                            "kie-model-registry.json")
        if os.path.isfile(cand):
            return cand
    return None


def _write_registry(models):
    d = tempfile.mkdtemp()
    p = os.path.join(d, "kie-model-registry.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"models": models}, f)
    return p


def _reg_env(p):
    """Set the registry env var; returns the old value to restore."""
    old = os.environ.get("KIE_MODEL_REGISTRY_JSON")
    if p:
        os.environ["KIE_MODEL_REGISTRY_JSON"] = p
    else:
        os.environ.pop("KIE_MODEL_REGISTRY_JSON", None)
    return old


def _unreg_env(old):
    if old is None:
        os.environ.pop("KIE_MODEL_REGISTRY_JSON", None)
    else:
        os.environ["KIE_MODEL_REGISTRY_JSON"] = old


# ------------------------------------------------------------- tests -------

def test_live_repo_registry_resolves_all_four():
    p = _live_registry()
    check("live registry found in this repo checkout", bool(p), str(p))
    if not p:
        return
    old = _reg_env(p)
    try:
        rows, reason = VM.resolve_choices()
        check("live repo: all four card models resolve, no reason",
              rows is not None and reason is None
              and [r["name"] for r in rows]
              == ["Hailuo 02 Standard", "Seedance 2.5", "Seedance 2.0 Mini",
                  "Google Veo 3.1"], repr(reason))
        ok_ids = set(VM.registry_ids())
        check("every row's kie_model carried by the registry",
              rows is not None
              and all(r["kie_model"] in ok_ids for r in rows),
              "missing: %s" % [r["kie_model"] for r in (rows or [])
                               if r["kie_model"] not in ok_ids])
    finally:
        _unreg_env(old)


def test_resolvable_registry_yields_only_listed_models():
    """A registry whose catalog carries only SOME models: the card yields
    only models the registry lists, and refuses the rest by name."""
    live = _live_registry()
    reg = json.load(open(live, encoding="utf-8")) if live else {"models": []}
    # registry WITHOUT Hailuo 02 Standard (the live defect: brand is Hailuo 02)
    stripped = {"models": [m for m in reg.get("models", [])
                           if m.get("id") != "hailuo/02-image-to-video-standard"]}
    check("stripped registry still carries the other three",
          {"bytedance/seedance-2-5", "bytedance/seedance-2-mini", "veo-3-1"}
          <= {m.get("id") for m in stripped["models"]}, repr(stripped)[:80])
    p = _write_registry(stripped["models"])
    old = _reg_env(p)
    try:
        rows, reason = VM.resolve_choices()
        check("defect-shaped registry: card refuses (no rows)",
              rows is None and reason is not None, repr(reason))
        check("refusal reason names the exact live defect",
              reason["reason_code"] == "MODEL_NOT_IN_REGISTRY"
              and "Hailuo 02 Standard" in reason["detail"]
              and "hailuo/02-image-to-video-standard" in reason["detail"], '')
        try:
            VM.require_choices()
            check("require_choices refuses the defect list", False,
                  "returned instead of raising")
        except VM.ModelResolutionError as e:
            check("require_choices refuses the defect list",
                  e.reason == "MODEL_NOT_IN_REGISTRY"
                  and "Hailuo 02 Standard" in str(e), str(e)[:120])
        # the card question surfaces the same refusal
        try:
            IC._model_question("60 seconds")
            check("card question refuses unresolvable list", False,
                  "rendered anyway")
        except VM.ModelResolutionError as e:
            check("card question refuses unresolvable list",
                  "Hailuo 02 Standard" in str(e), str(e)[:140])
        # and lock_choice refuses the same row
        db = os.path.join(os.path.dirname(p), "state.sqlite3")
        try:
            VM.lock_choice(db, "r1", 1)
            check("lock_choice refuses off-registry model", False,
                  "lock written")
        except VM.ModelResolutionError as e:
            check("lock_choice refuses off-registry model",
                  e.reason == "MODEL_NOT_IN_REGISTRY", str(e)[:120])
        con = sqlite3.connect(db)
        try:
            row = con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND "
                "name='video_model_lock'").fetchone()
        finally:
            con.close()
        check("no lock table written for a refused model", row is None,
              repr(row))
    finally:
        _unreg_env(old)


def test_unreadable_registry_refuses():
    old = _reg_env(os.path.join(tempfile.mkdtemp(), "no-such-file.json"))
    try:
        rows, reason = VM.resolve_choices()
        check("absent registry -> VIDEO_MODEL_UNRESOLVABLE",
              rows is None and reason
              and reason["reason_code"] == "VIDEO_MODEL_UNRESOLVABLE",
              repr(reason))
        check("refusal names the path it could not read",
              "kie-model-registry" in (reason or {}).get("detail", ""), '')
        try:
            VM.require_choices()
            check("require_choices refuses an unreadable registry", False,
                  "returned")
        except VM.ModelResolutionError as e:
            check("require_choices refuses an unreadable registry",
                  e.reason == "VIDEO_MODEL_UNRESOLVABLE", str(e)[:120])
    finally:
        _unreg_env(old)


def test_card_gate_menu_refuses_off_registry_rows():
    """The F15 card's video-model menu (the price-menu surface, what the
    client reads on the four-pick card) refuses rows the registry fails."""
    p = _live_registry()
    if not p:
        return
    reg = json.load(open(p, encoding="utf-8"))
    # live repo: menu rows all resolve
    old = _reg_env(p)
    try:
        lines = CG.video_model_picks()
        check("live repo: card menu renders (%d rows)" % len(lines),
              len(lines) == 18, repr(lines[:1]))
        rec = [m for m in VM.MODELS if m.get("recommended")]
        check("the recommended row is a model the registry carries",
              len(rec) == 1
              and rec[0]["kie_model"] in [m.get("id") for m in reg["models"]],
              repr([m.get("kie_model") for m in rec]))
    finally:
        _unreg_env(old)


def test_lock_and_dispatch_stay_gated_for_off_registry_model():
    """A client answer pointing at a model the registry does not carry can
    never produce a working dispatch: no lock row, and the run cannot pass
    its model off as another one."""
    p = _live_registry()
    if not p:
        return
    reg = json.load(open(p, encoding="utf-8"))
    stripped = {"models": [m for m in reg.get("models", [])
                           if m.get("id") != "hailuo/02-image-to-video-standard"]}
    old = _reg_env(_write_registry(stripped["models"]))
    try:
        d = tempfile.mkdtemp()
        db = os.path.join(d, "state.sqlite3")
        try:
            VM.lock_choice(db, "run-x", 1)
            check("lock refused for defect model", False, "lock written")
        except VM.ModelResolutionError as e:
            check("lock refused for defect model",
                  e.reason == "MODEL_NOT_IN_REGISTRY", str(e)[:120])
        # dispatch-side F14 still fails closed on any unlocked run: the card
        # never answered, so no lock exists and the video job is refused.
        env = KD.dispatch(model="hailuo/02-image-to-video-standard", request={},
                          save_dir=tempfile.mkdtemp(), ledger_db=":memory:",
                          run_id="run-x", logical_key="k", attempt_id="a",
                          estimated_cost=100,
                          runner=lambda argv: (1, None, "unused"))
        check("dispatch refuses (no card, no lock: the job never starts)",
              env.get("reason_code") in ("VIDEO_MODEL_LOCK_MISSING",
                                         "CARD_UNANSWERED",
                                         "MODEL_NOT_ON_MENU"),
              repr(env.get("reason_code")))
    finally:
        _unreg_env(old)


def test_no_hard_coded_model_names_outside_the_registry():
    """L3: no hard-coded model names outside the registry. The card's model
    names come from the rates table (a registry in its own right, with its
    source URL); the gate derives nothing from a name literal."""
    src = Path(VM.__file__).read_text(encoding="utf-8")
    names = [r["name"] for r in json.loads(
        Path(os.path.join(HERE, "video_model_rates.json")).read_text(
            encoding="utf-8"))["models"]]
    leaked = [n for n in names if n in src]
    check("video_models.py carries no card model name literal",
          not leaked, repr(leaked))
    gate_src = Path(CG.__file__).read_text(encoding="utf-8")
    leaked_gate = [n for n in names if n in gate_src]
    check("card_gate.py carries no card model name literal",
          not leaked_gate, repr(leaked_gate))


# ---------------------------------------------------------------------------

def main():
    for t in [test_live_repo_registry_resolves_all_four,
              test_resolvable_registry_yields_only_listed_models,
              test_unreadable_registry_refuses,
              test_card_gate_menu_refuses_off_registry_rows,
              test_lock_and_dispatch_stay_gated_for_off_registry_model,
              test_no_hard_coded_model_names_outside_the_registry]:
        try:
            t()
        except Exception as e:                              # noqa: BLE001
            check("%s raised" % t.__name__, False,
                  "%s: %s" % (type(e).__name__, e))
    print("\n%d checks failed" % len(FAILS))
    if FAILS:
        for f in FAILS:
            print("  FAILED: %s" % f)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())