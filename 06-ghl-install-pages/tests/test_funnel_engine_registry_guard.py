"""Offline, mock-only tests for the P1-9 STEP-0 skeleton guard + registry readiness.

No network, no model, no GHL writes: every case runs against a TMP registry
(written to tmp_path and passed via the ``registry_path`` kwarg or the
``GHL_FUNNEL_ENGINE_REGISTRY`` env override) or against the real on-disk
registry read-only. A skeleton-marked winning engine must be REFUSED by
step0_select_engine (no task stamps, a REFUSE_SKELETON match-decision receipt,
a NO_ENGINE_MATCH-style decision) unless --force-skeleton is passed, in which
case the receipt records forced: true with a loud stderr warning. Production
engines (49 / 56) must be byte-identically unaffected.
"""

import json
import os
import sys

import pytest

_TOOLS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
_SKILL_DIR = os.path.dirname(_TOOLS_DIR)
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import funnel_engine_selector as sel  # noqa: E402

_CINEMATIC = {
    "id": "cinematic-web-funnel-engine",
    "skill": "62-cinematic-web-funnel-engine",
    "name": "Cinematic and Web Funnel Engine",
    "entry": "62-cinematic-web-funnel-engine/cinematic-web-funnel-entry.sh",
    "priority": 8,
    "confidence_threshold": 0.55,
    "match": {
        "names": ["cinematic website", "cinematic funnel"],
        "keywords": ["scroll animation website", "immersive funnel"],
        "signals": ["scroll", "cinematic", "animated"],
        "anti_signals": ["signature funnel", "plain website"],
    },
    "readiness": {"status": "skeleton", "certify_capable": False,
                  "note": "offline build complete (CWFE-MANIFEST.json build_status "
                          "COMPLETE offline); live E2E deliberately HELD pending "
                          "operator-approved live run"},
}
_SIGNATURE = {
    "id": "signature-funnel",
    "skill": "49-signature-funnel",
    "name": "Trevor Otts Signature Funnel",
    "entry": "49-signature-funnel/signature-funnel-entry.sh",
    "priority": 10,
    "confidence_threshold": 0.55,
    "match": {
        "names": ["signature funnel"],
        "keywords": ["12-section hero"],
        "signals": ["upsell", "downsell"],
        "anti_signals": [],
    },
}
_SALES_PAGE = {
    "id": "sales-page-assets",
    "skill": "56-sales-page-assets",
    "name": "Trevor Otts Sales Page Assets (Direct-Response)",
    "entry": "56-sales-page-assets/sales-page-assets-entry.sh",
    "priority": 9,
    "confidence_threshold": 0.55,
    "match": {
        "names": ["sales page assets"],
        "keywords": ["order bump copy", "direct response"],
        "signals": ["order bump", "bump"],
        "anti_signals": ["signature funnel"],
    },
}
_CINEMATIC_REQUEST = {"brief": "build me a cinematic website with scroll animation",
                      "goal": "cinematic funnel"}


def _write_registry(tmp_path, engines):
    path = tmp_path / "registry.json"
    path.write_text(json.dumps({"schema": "funnel-engine-registry/v1",
                                "engines": engines}, indent=2), encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# Registry schema: readiness block (mock-only; the real registry's shape is
# exercised read-only in test_real_registry_marks_skill62_skeleton)
# ---------------------------------------------------------------------------
def test_skeleton_engine_loads_and_selects_with_readiness(tmp_path):
    reg = sel.load_registry(_write_registry(tmp_path, [_CINEMATIC]))
    assert reg["_loaded"] is True
    d = sel.select_engine(_CINEMATIC_REQUEST, reg)
    assert d["decision"] == sel.DEC_ROUTE
    assert d["engine"]["readiness"]["status"] == "skeleton"
    assert d["engine"]["readiness"]["certify_capable"] is False


def test_engine_without_readiness_key_is_unguarded(tmp_path):
    bare = {k: v for k, v in _CINEMATIC.items() if k != "readiness"}
    reg = sel.load_registry(_write_registry(tmp_path, [bare]))
    d = sel.select_engine(_CINEMATIC_REQUEST, reg)
    assert d["decision"] == sel.DEC_ROUTE
    assert "readiness" not in d["engine"]


# ---------------------------------------------------------------------------
# step0 refusal path (the core P1-9 guard)
# ---------------------------------------------------------------------------
def test_skeleton_win_refused_no_task_stamps(tmp_path):
    reg_path = _write_registry(tmp_path, [_CINEMATIC])
    task = {"brief": _CINEMATIC_REQUEST["brief"]}
    d = sel.step0_select_engine(task, str(tmp_path), registry_path=reg_path)
    assert d["decision"] == sel.DEC_NONE
    assert d["skeleton_guard"]["refused"] is True
    assert d["skeleton_guard"]["required_flag"] == "--force-skeleton"
    assert d["skeleton_guard"]["engine_id"] == "cinematic-web-funnel-engine"
    assert "deliberately HELD" in d["rationale"]
    # NO task stamps — the task must never name a skeleton engine as its route.
    assert not any(k.startswith("funnel_engine") for k in task), task


def test_skeleton_win_refused_writes_refuse_skeleton_receipt(tmp_path):
    reg_path = _write_registry(tmp_path, [_CINEMATIC])
    task = {"brief": _CINEMATIC_REQUEST["brief"]}
    sel.step0_select_engine(task, str(tmp_path), registry_path=reg_path)
    receipt = json.loads((tmp_path / "routing" / "match-decision.json").read_text())
    assert receipt["flex_decision"] == "REFUSE_SKELETON"
    assert receipt["route"] == "REFUSE_SKELETON"
    assert receipt["confident_match"] is False
    assert receipt["skeleton_guard"]["refused"] is True
    assert receipt["skeleton_guard"]["required_flag"] == "--force-skeleton"
    assert receipt["readiness"] == {"status": "skeleton", "certify_capable": False}
    assert "--force-skeleton" in receipt["reason"]


def test_refused_decision_is_not_a_raise_and_falls_through(tmp_path):
    """The guard refuses like NO_ENGINE_MATCH — it never raises and never blocks
    the build; the caller falls through to the template-first matcher."""
    reg_path = _write_registry(tmp_path, [_CINEMATIC])
    task = {"brief": _CINEMATIC_REQUEST["brief"]}
    d = sel.step0_select_engine(task, str(tmp_path), registry_path=reg_path)
    assert d["decision"] == sel.DEC_NONE          # NO_ENGINE_MATCH-style
    assert d.get("engine") is None
    # funnel-engine-match.json still written for the evidence trail
    match = json.loads((tmp_path / "routing" / "funnel-engine-match.json").read_text())
    assert match["decision"] == sel.DEC_NONE


def test_force_skeleton_stamps_task_and_records_forced_receipt(tmp_path, capsys):
    reg_path = _write_registry(tmp_path, [_CINEMATIC])
    task = {"brief": _CINEMATIC_REQUEST["brief"]}
    d = sel.step0_select_engine(task, str(tmp_path), registry_path=reg_path,
                                force_skeleton=True)
    assert d["decision"] == sel.DEC_ROUTE
    assert d["skeleton_guard"] == {"required_flag": "--force-skeleton",
                                   "engine_id": "cinematic-web-funnel-engine",
                                   "refused": False, "forced": True}
    assert task["funnel_engine"] == "cinematic-web-funnel-engine"
    assert task["funnel_engine_skill"] == "62-cinematic-web-funnel-engine"
    assert task["funnel_engine_entry"] == _CINEMATIC["entry"]
    receipt = json.loads((tmp_path / "routing" / "match-decision.json").read_text())
    assert receipt["flex_decision"] == sel.DEC_ROUTE
    assert receipt["skeleton_guard"]["forced"] is True
    assert receipt["skeleton_guard"]["refused"] is False
    assert receipt["readiness"]["status"] == "skeleton"
    # loud warning on stderr
    err = capsys.readouterr().err
    assert "--force-skeleton" in err and "skeleton" in err.lower()


def test_refused_then_forced_second_call_leaves_both_receipts(tmp_path):
    """The jsonl evidence trail records BOTH the refusal and the forced route."""
    reg_path = _write_registry(tmp_path, [_CINEMATIC])
    task = {"brief": _CINEMATIC_REQUEST["brief"]}
    d1 = sel.step0_select_engine(task, str(tmp_path), registry_path=reg_path)
    d2 = sel.step0_select_engine(task, str(tmp_path), registry_path=reg_path,
                                 force_skeleton=True)
    lines = [json.loads(l) for l in
             (tmp_path / "routing" / "funnel-engine-decisions.jsonl").read_text().splitlines()]
    assert d1["decision"] == sel.DEC_NONE and d2["decision"] == sel.DEC_ROUTE
    assert lines[0]["skeleton_guard"]["refused"] is True
    assert lines[1]["skeleton_guard"]["forced"] is True


# ---------------------------------------------------------------------------
# Production engines unaffected (byte-identical receipt contract)
# ---------------------------------------------------------------------------
def test_signature_funnel_still_routes_with_untouched_receipt(tmp_path):
    reg_path = _write_registry(tmp_path, [_SIGNATURE, _CINEMATIC])
    task = {"brief": "build me a signature funnel for my coaching offer"}
    d = sel.step0_select_engine(task, str(tmp_path), registry_path=reg_path)
    assert d["decision"] == sel.DEC_ROUTE
    assert d["engine_id"] == "signature-funnel"
    assert "skeleton_guard" not in d
    assert task["funnel_engine"] == "signature-funnel"
    receipt = json.loads((tmp_path / "routing" / "match-decision.json").read_text())
    assert receipt["flex_decision"] == sel.DEC_ROUTE
    assert set(receipt) == {"skill", "matched_template_id", "matched_template_key",
                            "template_path", "flex_decision", "route", "engine_id",
                            "engine_skill", "engine_entry", "confident_match",
                            "funnel_template_id", "confidence", "ts"}


def test_sales_page_assets_still_routes(tmp_path):
    reg_path = _write_registry(tmp_path, [_SALES_PAGE, _CINEMATIC])
    task = {"brief": "order bump copy plus direct response sales page assets"}
    d = sel.step0_select_engine(task, str(tmp_path), registry_path=reg_path)
    assert d["decision"] == sel.DEC_ROUTE
    assert d["engine_id"] == "sales-page-assets"
    assert "skeleton_guard" not in d
    assert task["funnel_engine"] == "sales-page-assets"


def test_no_engine_match_unaffected_by_guard(tmp_path):
    reg_path = _write_registry(tmp_path, [_CINEMATIC])
    task = {"brief": "set up a basic webinar registration funnel"}
    d = sel.step0_select_engine(task, str(tmp_path), registry_path=reg_path)
    assert d["decision"] == sel.DEC_NONE
    assert d.get("skeleton_guard") is None
    assert not any(k.startswith("funnel_engine") for k in task)
    # no receipt is emitted for a plain fall-through
    assert not (tmp_path / "routing" / "match-decision.json").exists()


# ---------------------------------------------------------------------------
# GHL_FUNNEL_ENGINE_REGISTRY env override (the mock-only seam)
# ---------------------------------------------------------------------------
def test_env_override_registry_respected(tmp_path, monkeypatch):
    reg_path = _write_registry(tmp_path, [_CINEMATIC])
    monkeypatch.setenv("GHL_FUNNEL_ENGINE_REGISTRY", reg_path)
    task = {"brief": _CINEMATIC_REQUEST["brief"]}
    d = sel.step0_select_engine(task, str(tmp_path))
    assert d["decision"] == sel.DEC_NONE
    assert d["skeleton_guard"]["refused"] is True


# ---------------------------------------------------------------------------
# Real registry (read-only): the shipped configuration
# ---------------------------------------------------------------------------
def test_real_registry_marks_skill62_skeleton_and_others_clean():
    reg = sel.load_registry()
    assert reg["_loaded"] is True
    by_id = {e["id"]: e for e in reg["engines"]}
    assert by_id["cinematic-web-funnel-engine"]["readiness"]["status"] == "skeleton"
    assert by_id["cinematic-web-funnel-engine"]["readiness"]["certify_capable"] is False
    assert "deliberately HELD pending operator-approved live run" \
        in by_id["cinematic-web-funnel-engine"]["readiness"]["note"]
    assert "readiness" not in by_id["signature-funnel"]
    assert "readiness" not in by_id["sales-page-assets"]


def test_real_registry_step0_refuses_cinematic_route(tmp_path):
    task = {"brief": "build me a cinematic website with scroll animation"}
    d = sel.step0_select_engine(task, str(tmp_path))
    assert d["decision"] == sel.DEC_NONE
    assert d["skeleton_guard"]["engine_id"] == "cinematic-web-funnel-engine"
    assert d["skeleton_guard"]["refused"] is True
    assert not any(k.startswith("funnel_engine") for k in task)


# ---------------------------------------------------------------------------
# CLI: --self-test still exits 0; --list shows readiness
# ---------------------------------------------------------------------------
def test_cli_self_test_exits_zero():
    assert sel.main(["--self-test"]) == 0


def test_cli_list_shows_readiness_status(capsys):
    assert sel.main(["--list", "--json"]) == 0
    rows = {r["id"]: r for r in json.loads(capsys.readouterr().out)}
    assert rows["cinematic-web-funnel-engine"]["readiness_status"] == "skeleton"
    assert "readiness_status" not in rows["signature-funnel"]
    assert "readiness_status" not in rows["sales-page-assets"]


def test_cli_list_human_output_shows_readiness(capsys):
    assert sel.main(["--list"]) == 0
    out = capsys.readouterr().out
    assert "[readiness: skeleton]" in out
    assert "signature-funnel" in out


def test_cli_match_refuses_skeleton_and_json_carries_guard(capsys):
    assert sel.main(["--json", "--match",
                     "build me a cinematic website with scroll animation"]) == 0
    d = json.loads(capsys.readouterr().out)
    assert d["decision"] == sel.DEC_NONE
    assert d["skeleton_guard"]["refused"] is True


def test_cli_match_force_skeleton_routes(capsys):
    assert sel.main(["--json", "--force-skeleton", "--match",
                     "build me a cinematic website with scroll animation"]) == 0
    d = json.loads(capsys.readouterr().out)
    assert d["decision"] == sel.DEC_ROUTE
    assert d["skeleton_guard"]["forced"] is True
    assert d["engine_id"] == "cinematic-web-funnel-engine"
