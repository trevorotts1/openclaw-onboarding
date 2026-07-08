"""Tests for ghl_pipeline_builder.py (v18.1.6) — the browser-control PIPELINE
builder (fix/skill6-ghl-form-iframe-drag).

WHY BROWSER CONTROL: GHL exposes NO public API to create a pipeline or
create/edit pipeline stages (confirmed against the real v2 AND v3 OpenAPI
specs, 2026-07-07; the only public surface is the read-only
GET /opportunities/pipelines that Skill 44 already wraps). Skill 44 has no
pipeline-creation capability of any kind (audited 2026-07-07), so the walk
lives in Skill 6, riding the SAME proven DO-layer primitives as the form
builder (text verbs, role+exact clicks, poll-with-deadline waits, positive
leaf-count verification, walk_state, fail-closed cleanup).

HERMETIC — NO network, NO live browser, NO GHL. Style, imports, and sys.path
handling mirror the sibling 06 tests.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

# ── sys.path setup (mirrors the sibling 06 tests) ─────────────────────────────
_TESTS_DIR = Path(__file__).resolve().parent
_TOOLS_DIR = _TESTS_DIR.parent / "tools"
for _p in (str(_TOOLS_DIR), str(_TESTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ghl_form_builder as fb  # noqa: E402
import ghl_pipeline_builder as pb  # noqa: E402


def _cp(rc: int, stdout: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr="")


@pytest.fixture(autouse=True)
def _fast_and_mute(monkeypatch):
    monkeypatch.setattr(fb, "_TEXT_WAIT_TIMEOUT_S", 0.05)
    monkeypatch.setattr(fb, "_TEXT_WAIT_SUBCALL_S", 1)
    monkeypatch.setattr(fb, "_TEXT_WAIT_POLL_S", 0.005)
    monkeypatch.setattr(fb, "_screenshot", lambda session, path: None)
    monkeypatch.setattr(pb.time, "sleep", lambda s: None)


# ---------------------------------------------------------------------------
# 1. THINK layer
# ---------------------------------------------------------------------------
class TestThinkLayer:
    def test_selftest_passes(self):
        assert pb._selftest() == 0

    def test_pipeline_name_gets_zhc_prefix(self):
        plan = pb._build_pipeline_plan({"pipeline_name": "Sales Pipeline",
                                        "location_id": "L"}, ["A"])
        assert plan["pipeline_name"] == "ZHC Sales Pipeline"

    def test_stages_normalized_and_terminal_stripped(self):
        """Won/Lost are GHL-automatic terminal stages — a manual duplicate
        would corrupt the pipeline's win/loss semantics."""
        out = pb._resolve_stages({"stages": [" New Lead ", "New Lead", "Won",
                                             "LOST", "", "Booked Call"]})
        assert out == ["New Lead", "Booked Call"]

    def test_default_reference_stages_used_when_absent(self):
        assert pb._resolve_stages({}) == pb.REFERENCE_STAGES

    def test_click_list_carries_api_boundary_and_phases(self, tmp_path):
        res = pb.build_pipeline({"pipeline_name": "P", "location_id": "L",
                                 "stages": ["S1", "S2"]}, str(tmp_path))
        cl = res["click_list"]
        phases = {s["phase"] for s in cl["steps"]}
        assert {"PL1", "PL2", "PL3", "PL4", "PL5", "PL6"} <= phases
        blob = json.dumps(cl)
        assert "caf opportunities pipelines" in blob, \
            "the Skill-44 read-API id-capture handoff must be spelled out"
        stage_steps = [s for s in cl["steps"] if s["phase"] == "PL4"]
        assert len(stage_steps) == 2

    def test_preflight_blocks_missing_location(self, tmp_path):
        res = pb.build_pipeline({"pipeline_name": "P", "location_id": ""},
                                str(tmp_path))
        assert res["preflight"]["pass"] is False

    def test_dry_run_never_touches_the_browser(self, tmp_path, monkeypatch):
        def _boom(*a, **k):
            raise AssertionError("dry-run must not touch the DO layer")

        for name in ("_router_push", "_click_button", "_click", "_fill", "_ab"):
            monkeypatch.setattr(fb, name, _boom)
        res = pb.build_pipeline({"pipeline_name": "P", "location_id": "L"},
                                str(tmp_path))
        assert res["dry_run"] is True and res["pipeline_created"] is False


# ---------------------------------------------------------------------------
# 1b. EXACT-NAME mode — the Anthology Engine (Skill 59) integration contract:
#     anthology_registry.py provision-pipeline invokes this builder with
#     --exact-name and binds the created pipeline BY NAME through the read API
#     afterwards, so the ZHC container prefix must NOT be applied.
# ---------------------------------------------------------------------------
class TestExactNameMode:
    def test_exact_name_is_byte_exact_no_zhc_prefix(self):
        plan = pb._build_pipeline_plan({"pipeline_name": "Anthology Engine",
                                        "location_id": "L", "exact_name": True},
                                       ["Intake", "Avatar"])
        assert plan["pipeline_name"] == "Anthology Engine"
        assert plan["exact_name"] is True

    def test_default_mode_unchanged_still_zhc(self):
        plan = pb._build_pipeline_plan({"pipeline_name": "Anthology Engine",
                                        "location_id": "L"}, ["Intake"])
        assert plan["pipeline_name"] == "ZHC Anthology Engine"
        assert plan["exact_name"] is False

    def test_exact_name_preflight_passes(self):
        task = {"pipeline_name": "Anthology Engine", "location_id": "L",
                "exact_name": True}
        plan = pb._build_pipeline_plan(task, ["Intake", "Avatar"])
        pf = pb._run_preflight(task, plan, ["Intake", "Avatar"])
        assert pf["pass"] is True
        names = {c["check"] for c in pf["checks"]}
        assert "PL-P2:exact_pipeline_name" in names
        assert "PL-P2:zhc_pipeline_name" not in names

    def test_exact_name_preflight_refuses_empty_name(self):
        task = {"pipeline_name": "   ", "location_id": "L", "exact_name": True}
        plan = pb._build_pipeline_plan(task, ["Intake"])
        pf = pb._run_preflight(task, plan, ["Intake"])
        assert pf["pass"] is False

    def test_cli_exact_name_flag_wires_through(self, monkeypatch, tmp_path):
        seen = {}

        def _fake_build(task, evidence_root, *, dry_run=True):
            seen.update(task)
            seen["_dry_run"] = dry_run
            return {"location_gate_ok": True}

        monkeypatch.setattr(pb, "build_pipeline", _fake_build)
        rc = pb.main(["--dry-run", "--exact-name", "--location-id", "L",
                      "--pipeline-name", "Anthology Engine",
                      "--stages", "Intake,Avatar",
                      "--evidence-root", str(tmp_path)])
        assert rc == 0
        assert seen["exact_name"] is True
        assert seen["pipeline_name"] == "Anthology Engine"
        assert seen["stages"] == ["Intake", "Avatar"]

    def test_cli_default_has_no_exact_name(self, monkeypatch, tmp_path):
        seen = {}

        def _fake_build(task, evidence_root, *, dry_run=True):
            seen.update(task)
            return {"location_gate_ok": True}

        monkeypatch.setattr(pb, "build_pipeline", _fake_build)
        rc = pb.main(["--dry-run", "--location-id", "L",
                      "--pipeline-name", "Sales", "--stages", "A,B",
                      "--evidence-root", str(tmp_path)])
        assert rc == 0
        assert seen["exact_name"] is False


# ---------------------------------------------------------------------------
# 2. Runtime label binding (docs disagree on capitalization — bind live)
# ---------------------------------------------------------------------------
class TestRuntimeLabelBinding:
    @pytest.mark.parametrize("label", ["Create new pipeline", "Create New Pipeline"])
    def test_create_label_bound_exactly_as_seen(self, label):
        assert pb.find_visible_label(f"header {label} rest", pb.CREATE_PIPELINE_RE) == label

    def test_absent_label_returns_empty_never_invented(self):
        assert pb.find_visible_label("nothing relevant", pb.CREATE_PIPELINE_RE) == ""

    @pytest.mark.parametrize("label", ["Add stage", "Add Stage"])
    def test_add_stage_label_bound(self, label):
        assert pb.find_visible_label(f"dialog {label}", pb.ADD_STAGE_RE) == label


# ---------------------------------------------------------------------------
# 3. Walk — positive verification + fail-closed STOPs
# ---------------------------------------------------------------------------
class TestWalk:
    def _wire_happy(self, monkeypatch, calls):
        monkeypatch.setattr(fb, "_router_push",
                            lambda session, path, expect_contains="": "nav:" + path)
        monkeypatch.setattr(fb, "_wait_text_polling", lambda session, text, **k: True)
        monkeypatch.setattr(fb, "_snapshot",
                            lambda session, timeout=20: "Create new pipeline Add stage")
        monkeypatch.setattr(fb, "_click_button",
                            lambda session, name, timeout=15: (calls["buttons"].append(name), _cp(0))[1])
        monkeypatch.setattr(fb, "_click", lambda session, target, timeout=15: _cp(0))
        monkeypatch.setattr(fb, "_fill",
                            lambda session, label, value, timeout=15: (calls["fills"].append((label, value)), _cp(0))[1])
        monkeypatch.setattr(fb, "_ab",
                            lambda session, *a, timeout=30, stdin=None: (calls["ab"].append(a), _cp(0))[1])
        monkeypatch.setattr(fb, "_eval_leaf_count", lambda session, text: 1)
        monkeypatch.setattr(fb, "_capture_entry_diag", lambda session: "{}")

    def test_happy_walk_creates_and_positively_verifies(self, monkeypatch, tmp_path):
        calls = {"buttons": [], "fills": [], "ab": []}
        self._wire_happy(monkeypatch, calls)
        plan = pb._build_pipeline_plan({"pipeline_name": "Sales Pipeline",
                                        "location_id": "L"}, ["New Lead", "Booked Call"])
        state, steps = {}, []
        out = pb._walk_pipeline_build("s", plan, str(tmp_path), [0], steps, state)
        assert out["rendered_rows"] == 1
        assert state["pipeline_created"] is True
        assert state["pipeline_name_typed"] == "ZHC Sales Pipeline"
        assert "Create new pipeline" in calls["buttons"], \
            "the create click must use the RUNTIME-BOUND label"
        assert ("Pipeline Name", "ZHC Sales Pipeline") in calls["fills"]
        assert any(s.startswith("PL6:verified-rows") for s in steps)

    def test_landing_without_create_control_stops(self, monkeypatch):
        monkeypatch.setattr(fb, "_router_push",
                            lambda session, path, expect_contains="": "nav")
        monkeypatch.setattr(fb, "_wait_text_polling", lambda session, text, **k: True)
        monkeypatch.setattr(fb, "_snapshot", lambda session, timeout=20: "wrong screen")
        monkeypatch.setattr(fb, "_capture_entry_diag", lambda session: "{}")
        with pytest.raises(pb.StopAndReport) as ei:
            pb._land_on_pipelines("s", "L")
        assert ei.value.step == "PL1.land"

    def test_unrendered_pipeline_name_stops(self, monkeypatch):
        monkeypatch.setattr(fb, "_fill", lambda session, label, value, timeout=15: _cp(0))
        monkeypatch.setattr(fb, "_wait_text_polling", lambda session, text, **k: False)
        monkeypatch.setattr(fb, "_capture_entry_diag", lambda session: "{}")
        with pytest.raises(pb.StopAndReport) as ei:
            pb._fill_pipeline_name("s", "ZHC P")
        assert ei.value.step == "PL3.name"

    def test_unrendered_stage_stops_with_stage_name(self, monkeypatch):
        monkeypatch.setattr(fb, "_fill", lambda session, label, value, timeout=15: _cp(1))
        monkeypatch.setattr(fb, "_snapshot", lambda session, timeout=20: "Add stage")
        monkeypatch.setattr(fb, "_click_button", lambda session, name, timeout=15: _cp(0))
        monkeypatch.setattr(fb, "_ab", lambda session, *a, timeout=30, stdin=None: _cp(0))
        monkeypatch.setattr(fb, "_wait_text_polling", lambda session, text, **k: False)
        monkeypatch.setattr(fb, "_capture_entry_diag", lambda session: "{}")
        with pytest.raises(pb.StopAndReport) as ei:
            pb._add_stage("s", "Booked Call", 2)
        assert ei.value.step == "PL4.stage:Booked Call"

    def test_save_without_rendered_row_stops(self, monkeypatch):
        monkeypatch.setattr(fb, "_click_button", lambda session, name, timeout=15: _cp(0))
        monkeypatch.setattr(fb, "_wait_text_polling", lambda session, text, **k: True)
        monkeypatch.setattr(fb, "_eval_leaf_count", lambda session, text: 0)
        monkeypatch.setattr(fb, "_capture_entry_diag", lambda session: "{}")
        with pytest.raises(pb.StopAndReport) as ei:
            pb._save_and_verify("s", "ZHC P")
        assert ei.value.step == "PL6.verify"
        assert "unverified creation" in ei.value.reason


# ---------------------------------------------------------------------------
# 4. Cleanup — present→delete→absent, count-gated affordances
# ---------------------------------------------------------------------------
class TestDeletePipeline:
    def _wire(self, monkeypatch, leaf_seq, button_count):
        monkeypatch.setattr(fb, "_router_push",
                            lambda session, path, expect_contains="": "nav")
        monkeypatch.setattr(fb, "_wait_text_polling", lambda session, text, **k: True)
        monkeypatch.setattr(fb, "_snapshot",
                            lambda session, timeout=20: "Create new pipeline")
        monkeypatch.setattr(fb, "_click", lambda session, target, timeout=15: _cp(0))
        monkeypatch.setattr(fb, "_click_button", lambda session, name, timeout=15: _cp(0))
        monkeypatch.setattr(fb, "_capture_entry_diag", lambda session: "{}")
        seq = {"i": 0}

        def leaf(session, text):
            i = min(seq["i"], len(leaf_seq) - 1)
            seq["i"] += 1
            return leaf_seq[i]

        monkeypatch.setattr(fb, "_eval_leaf_count", leaf)
        monkeypatch.setattr(fb, "_eval",
                            lambda session, js, timeout=12: str(button_count))

    def test_present_then_absent_is_verified_deleted(self, monkeypatch):
        self._wire(monkeypatch, leaf_seq=[1, 0], button_count=1)
        out = pb._delete_pipeline("s", "L", "ZHC TEST P")
        assert out["deleted"] is True and out["verified_gone"] is True
        assert out["residue_in_list"] is False

    def test_already_absent_is_a_positive_clean_proof(self, monkeypatch):
        self._wire(monkeypatch, leaf_seq=[0], button_count=1)
        out = pb._delete_pipeline("s", "L", "ZHC TEST P")
        assert out["deleted"] is True and out["verified_gone"] is True

    def test_multiple_rows_fail_closed(self, monkeypatch):
        self._wire(monkeypatch, leaf_seq=[2], button_count=1)
        out = pb._delete_pipeline("s", "L", "ZHC TEST P")
        assert out["deleted"] is False
        assert "EXACTLY ONE" in out["reason"]

    def test_ambiguous_delete_affordance_refused(self, monkeypatch):
        """>1 'Delete' buttons on screen → clicking could hit the wrong control
        on a REAL client account. Refuse, honestly."""
        self._wire(monkeypatch, leaf_seq=[1, 1], button_count=2)
        out = pb._delete_pipeline("s", "L", "ZHC TEST P")
        assert out["deleted"] is False
        assert "ambiguous" in out["reason"]

    def test_unlocatable_delete_affordance_flags_operator(self, monkeypatch):
        self._wire(monkeypatch, leaf_seq=[1, 1], button_count=0)
        out = pb._delete_pipeline("s", "L", "ZHC TEST P")
        assert out["deleted"] is False
        assert "OPERATOR REVIEW REQUIRED" in out["reason"]

    def test_lingering_row_is_residue_not_success(self, monkeypatch):
        self._wire(monkeypatch, leaf_seq=[1, 1, 1, 1], button_count=1)
        out = pb._delete_pipeline("s", "L", "ZHC TEST P")
        assert out["deleted"] is False
        assert out["residue_in_list"] is True

    def test_unknown_counts_never_read_as_gone(self, monkeypatch):
        self._wire(monkeypatch, leaf_seq=[1, -1], button_count=1)
        out = pb._delete_pipeline("s", "L", "ZHC TEST P")
        assert out["deleted"] is False


# ---------------------------------------------------------------------------
# 5. Source-level locks (same doctrine as the form/survey builders)
# ---------------------------------------------------------------------------
class TestSourceLocks:
    def test_no_bare_text_verb_emissions(self):
        src = (_TOOLS_DIR / "ghl_pipeline_builder.py").read_text(encoding="utf-8")
        import re as _re
        assert _re.search(r'_ab\(session,\s*"click",', src) is None
        assert _re.search(r'_ab\(session,\s*"fill",', src) is None
        assert _re.search(r'"wait",\s*"--",', src) is None

    def test_no_anthropic_or_banned_models_in_ladders(self, tmp_path):
        """The plan's model ladders (shared with the form builder) must carry no
        Anthropic slug and no banned model — same check the form builder's own
        selftest enforces (a doctrine COMMENT saying 'never Anthropic' is fine;
        a routable slug is not)."""
        res = pb.build_pipeline({"pipeline_name": "P", "location_id": "L"},
                                str(tmp_path))
        plan = json.loads((tmp_path / "routing" / "pipeline-plan.json").read_text())
        lad = json.dumps(plan["model_ladders"]).lower()
        for banned in ("anthropic", "claude", "opus", "sonnet", "haiku",
                       "minimax-m2", "minimax_m2"):
            assert banned not in lad, f"banned model token in ladders: {banned}"
        assert res["location_gate_ok"] is True

    def test_reuses_the_proven_do_layer_not_a_fork(self):
        """One implementation of the text-verb/role+exact/poll doctrine: the
        pipeline walk must call ghl_form_builder's primitives, not carry its
        own copies of _click/_fill/_wait_text."""
        src = (_TOOLS_DIR / "ghl_pipeline_builder.py").read_text(encoding="utf-8")
        assert "import ghl_form_builder as fb" in src
        for forbidden in ("def _click(", "def _fill(", "def _wait_text(",
                          "def _router_push(", "def _seed_and_land("):
            assert forbidden not in src, f"forked DO-layer primitive: {forbidden}"

    def test_no_manual_won_lost_anywhere_in_the_click_list(self, tmp_path):
        res = pb.build_pipeline({"pipeline_name": "P", "location_id": "L",
                                 "stages": ["Won", "Lost", "Real Stage"]},
                                str(tmp_path))
        pl4 = [s for s in res["click_list"]["steps"] if s["phase"] == "PL4"]
        assert len(pl4) == 1 and "Real Stage" in pl4[0]["target"]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
