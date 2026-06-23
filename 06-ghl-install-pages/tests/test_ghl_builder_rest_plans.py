"""MOCK-only unit tests — the REST-autosave canvas wire-in (solution doc §5.2).

Covers the three plan-emitters added to ``ghl_builder.py`` that orchestrate the
proven ``ghl_rest_canvas`` primitives into ordered, agent-runnable eval-step
PLANS:

  * ``emit_rest_save_plan``   — read -> splice -> autosave(DRAFT) -> verify -> revert
  * ``emit_workflow_rewire_plan`` — read(?includeTriggers=true) -> rewire -> re-read
  * ``emit_revert_plan``      — byte-identical baseline restore

These tests are MOCK-ONLY: NO live GHL, no real fixture, no agent-browser against
real GHL, NO network of any kind. The emitters are pure plan builders (they make
no network calls and open no browser), so the assertions cover the EMITTED PLAN
SHAPE only:

  * the ORDERED steps each plan emits (and that the autosave defaults to DRAFT);
  * the publish gate (``may_publish``) flipping the autosave + ledger target;
  * the sub-account hard gate (``subaccount_matches``) REFUSING on MISMATCH
    (zero steps, ``ok=False`` — a hard stop, never an advisory);
  * the BYTE-IDENTICAL revert contract (the md5 the re-read must match);
  * the workflow ``?includeTriggers=true`` LOAD-BEARING read contract;
  * the ``token-id`` scheme on every in-browser step (never ``Authorization:
    Bearer``);
  * the pristine-baseline-preserved invariant the revert hinges on;
  * the parallel ``wf-rewired`` ledger state;
  * the CLI subcommands (``rest-save-plan`` / ``wf-rewire-plan`` / ``revert-plan``)
    and their exit codes (0 on a valid plan, 1 on a refused MISMATCH plan).

No real client/operator names, ids, emails, or location-ids appear. The
sub-account hard gate is parameterised on a generic 20-char fixture location id
(``FIXTURE0LOCATION0000``) — shaped like a real 20-char GHL location id (NOT a
short placeholder) only so the gate's minimum-length check passes the PASS path;
it is not any real sub-account. Every other value is a generic / parameterised
fake.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

# Ensure ghl_builder (and its ghl_rest_canvas sibling) are importable regardless
# of working directory — same convention as the other tests in this suite.
_TOOLS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "tools")
)
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import pytest

import browser_manager  # SINGLETON POOLED BROWSER gateway (session bracket)
import ghl_builder as b
import ghl_rest_canvas as rc


# ── Generic fakes (NO real client/operator data) ─────────────────────────────
# The fixture location is a generic 20-char id shaped like a real GHL location
# id, which the hard gate is parameterised on (a too-short / placeholder target
# is rejected by the gate, so the tests use a real-shaped fixture id to exercise
# the PASS path).
FIXTURE_LOC = "FIXTURE0LOCATION0000"  # generic 20-char fixture id (NOT a real sub-account)
WRONG_LOC = "WRONGLOCATION000fake"     # a different (fake) sub-account
FAKE_PAGE_ID = "PAGEID0000000000fake"
FAKE_FUNNEL_ID = "FUNNELID000000000fake"
FAKE_WF = "WORKFLOW0000000fake"
FAKE_TRIGGER = "TRIGGER00000000fake"
FAKE_PREVIEW = f"https://www.example.com/preview/{FAKE_PAGE_ID}"
MARKER = "ZHC-REST-WIRE-MARKER"


def _customcode_blob(raw: str = "<img src='old.png'>") -> dict:
    """A minimal page-data blob with a single custom-code element at [0][0]."""
    return {
        "sections": [
            {
                "elements": [
                    {
                        "id": "el-0",
                        "type": "custom-code",
                        "extra": {"customCode": {"value": {"rawCustomCode": raw}}},
                    }
                ]
            }
        ],
        "settings": {},
        "trackingCode": {"head": ""},
    }


def _trigger_record(name: str = "Old Trigger", ttype: str = "contact_created") -> dict:
    return {
        "id": FAKE_TRIGGER,
        "name": name,
        "type": ttype,
        "workflow_id": FAKE_WF,
        "location_id": FIXTURE_LOC,
        "conditions": [],
        "actions": [],
        "active": True,
    }


def _save_kwargs(**overrides) -> dict:
    """Baseline kwargs for emit_rest_save_plan; override per-test."""
    kwargs = dict(
        page_id=FAKE_PAGE_ID,
        funnel_id=FAKE_FUNNEL_ID,
        location_id=FIXTURE_LOC,
        current_location_id=FIXTURE_LOC,
        locator={"section_idx": 0, "element_idx": 0},
        new_value=f"<img src='https://storage.googleapis.com/msgsndr/x.png'> {MARKER}",
        page_version=1,
        page_data=_customcode_blob(),
        preview_url=FAKE_PREVIEW,
        marker=MARKER,
    )
    kwargs.update(overrides)
    return kwargs


# ── emit_rest_save_plan — ordered steps + draft default ───────────────────────

class TestRestSavePlanOrder:
    def test_emits_the_six_ordered_steps(self):
        plan = b.emit_rest_save_plan(**_save_kwargs())
        assert plan["ok"] is True
        assert plan["plan"] == "rest_save"
        # The exact read -> splice -> autosave -> verify -> revert recipe order,
        # preceded by the token-staging step.
        assert [s["step"] for s in plan["steps"]] == [
            "stage_token", "page_read", "edit",
            "page_autosave", "verify_preview", "revert_baseline",
        ]

    def test_default_autosave_is_draft(self):
        plan = b.emit_rest_save_plan(**_save_kwargs())  # no approval => DRAFT
        assert plan["publish"] is False
        save = next(s for s in plan["steps"] if s["step"] == "page_autosave")
        assert save["body"]["pageType"] == "draft"
        assert save["body"]["pageVersion"] == 2          # numeric n+1
        # Draft never moves the live pointer (the confirmation contract).
        assert save["expect"]["live_pointer_unchanged"] is True

    def test_ledger_targets_default_draft(self):
        plan = b.emit_rest_save_plan(**_save_kwargs())
        assert plan["ledger_targets"]["page_autosave"] == "page-saved"
        assert plan["ledger_targets"]["edit"] == "code-saved"
        assert plan["ledger_targets"]["verify_preview"] == "previewed"

    def test_edit_step_carries_the_marker_and_locator(self):
        plan = b.emit_rest_save_plan(**_save_kwargs())
        edit = next(s for s in plan["steps"] if s["step"] == "edit")
        assert edit["locator"] == {"section_idx": 0, "element_idx": 0}
        assert edit["marker_in_value"] is True

    def test_verify_step_uses_verify_url_contract(self):
        plan = b.emit_rest_save_plan(**_save_kwargs())
        verify = next(s for s in plan["steps"] if s["step"] == "verify_preview")
        assert verify["action"] == "verify_url"
        assert verify["url"] == FAKE_PREVIEW
        assert verify["marker"] == MARKER
        assert verify["expect"] == {"ok": True, "http": 200, "marker_found": True}


# ── emit_rest_save_plan — publish gate (may_publish) ──────────────────────────

class TestRestSavePlanPublishGate:
    @pytest.mark.parametrize("approval", ["live", "publish", "yes", "approved", "go"])
    def test_explicit_live_answer_publishes(self, approval):
        plan = b.emit_rest_save_plan(**_save_kwargs(approval=approval))
        assert plan["publish"] is True
        save = next(s for s in plan["steps"] if s["step"] == "page_autosave")
        assert save["body"]["pageType"] == "published"
        assert plan["ledger_targets"]["page_autosave"] == "published"

    @pytest.mark.parametrize("approval", [None, "", "no", "draft", "maybe", "later"])
    def test_absent_or_ambiguous_stays_draft(self, approval):
        plan = b.emit_rest_save_plan(**_save_kwargs(approval=approval))
        assert plan["publish"] is False
        save = next(s for s in plan["steps"] if s["step"] == "page_autosave")
        assert save["body"]["pageType"] == "draft"
        assert plan["ledger_targets"]["page_autosave"] == "page-saved"


# ── emit_rest_save_plan — sub-account hard gate (refuse on MISMATCH) ───────────

class TestRestSavePlanSubaccountGate:
    def test_mismatch_refuses_with_zero_steps(self):
        plan = b.emit_rest_save_plan(**_save_kwargs(current_location_id=WRONG_LOC))
        assert plan["ok"] is False
        assert plan["refused"] is True
        assert plan["steps"] == []                       # nothing can run
        assert "MISMATCH" in plan["reason"]
        assert plan["guard"]["ok"] is False

    def test_too_short_target_refused(self):
        # A too-short / placeholder target can never be a real location_id.
        plan = b.emit_rest_save_plan(**_save_kwargs(location_id="test",
                                                    current_location_id="test"))
        assert plan["ok"] is False
        assert plan["steps"] == []

    def test_match_passes_and_reports_target_id(self):
        plan = b.emit_rest_save_plan(**_save_kwargs())
        assert plan["ok"] is True
        assert plan["location_id"] == FIXTURE_LOC.lower()  # normalised
        assert plan["guard"]["ok"] is True


# ── emit_rest_save_plan — pristine-baseline-preserved invariant ───────────────

class TestRestSavePlanBaselinePreserved:
    def test_input_blob_not_mutated_by_the_splice(self):
        # Reversibility hinges on the caller keeping a pristine baseline — the
        # plan's edit step must not mutate the caller's page_data.
        blob = _customcode_blob("<img src='old.png'>")
        before = json.dumps(blob, sort_keys=True)
        b.emit_rest_save_plan(**_save_kwargs(page_data=blob))
        assert json.dumps(blob, sort_keys=True) == before
        # And the original raw value is still the pristine one.
        assert blob["sections"][0]["elements"][0]["extra"]["customCode"]["value"][
            "rawCustomCode"] == "<img src='old.png'>"

    def test_autosave_body_carries_the_edited_blob_not_baseline(self):
        plan = b.emit_rest_save_plan(**_save_kwargs())
        save = next(s for s in plan["steps"] if s["step"] == "page_autosave")
        saved_raw = save["body"]["pageData"]["sections"][0]["elements"][0][
            "extra"]["customCode"]["value"]["rawCustomCode"]
        assert MARKER in saved_raw                       # the spliced value
        assert "old.png" not in saved_raw

    def test_revert_step_targets_the_pristine_baseline_md5(self):
        blob = _customcode_blob("<img src='old.png'>")
        plan = b.emit_rest_save_plan(**_save_kwargs(page_data=blob))
        revert = next(s for s in plan["steps"] if s["step"] == "revert_baseline")
        # The byte-identical bar is the PRISTINE baseline's md5, not the edit's.
        assert revert["expect"]["byte_identical_md5"] == rc.blob_md5(blob)
        # The revert body re-posts the pristine bytes as a DRAFT.
        assert revert["body"]["pageType"] == "draft"
        assert rc.is_byte_identical(revert["body"]["pageData"], blob)


# ── emit_rest_save_plan — token-id scheme on every in-browser step ────────────

class TestRestSavePlanTokenScheme:
    def test_every_eval_step_uses_token_id_not_bearer(self):
        plan = b.emit_rest_save_plan(**_save_kwargs())
        eval_steps = [s for s in plan["steps"] if "eval" in s]
        # read + autosave + revert all carry an eval.
        assert {s["step"] for s in eval_steps} == {
            "page_read", "page_autosave", "revert_baseline"}
        for s in eval_steps:
            assert '"token-id": window.__VT' in s["eval"]
            assert "Authorization" not in s["eval"]
            assert "Bearer" not in s["eval"]

    def test_stage_token_uses_python_written_js_not_bash(self):
        plan = b.emit_rest_save_plan(**_save_kwargs())
        stage = next(s for s in plan["steps"] if s["step"] == "stage_token")
        assert stage["action"] == "write_token_js_file"
        assert stage["token_global"] == rc.TOKEN_JS_GLOBAL
        # The note is explicit that bash ${VAR@Q} is forbidden.
        assert "${VAR@Q}" in stage["note"]

    def test_session_adds_headless_forced_argv_to_each_step(self):
        # Emitters that produce argv must run inside the singleton session bracket.
        with browser_manager.browser_session("sess-fake"):
            plan = b.emit_rest_save_plan(**_save_kwargs(session="sess-fake"))
        for s in plan["steps"]:
            if "eval" in s:
                assert s["argv"][0] == "agent-browser"
                assert "--headed" in s["argv"]
                assert s["argv"][s["argv"].index("--headed") + 1] == "false"


# ── emit_workflow_rewire_plan ─────────────────────────────────────────────────

class TestWorkflowRewirePlan:
    def _kwargs(self, **overrides) -> dict:
        kwargs = dict(
            location_id=FIXTURE_LOC,
            current_location_id=FIXTURE_LOC,
            workflow_id=FAKE_WF,
            trigger_id=FAKE_TRIGGER,
            spec={"name": "New", "type": "contact_changed"},
            existing_trigger=_trigger_record(),
        )
        kwargs.update(overrides)
        return kwargs

    def test_emits_ordered_read_then_rewire(self):
        plan = b.emit_workflow_rewire_plan(**self._kwargs())
        assert plan["ok"] is True
        assert [s["step"] for s in plan["steps"]] == [
            "stage_token", "read_triggers", "rewire_trigger"]

    def test_read_uses_include_triggers_query(self):
        plan = b.emit_workflow_rewire_plan(**self._kwargs())
        read = next(s for s in plan["steps"] if s["step"] == "read_triggers")
        # The ?includeTriggers=true query is LOAD-BEARING.
        assert "includeTriggers=true" in read["path"]
        assert read["expect"]["triggers_inline"] is True

    def test_rewire_body_is_whole_record_plus_changed_fields(self):
        plan = b.emit_workflow_rewire_plan(**self._kwargs())
        rewire = next(s for s in plan["steps"] if s["step"] == "rewire_trigger")
        assert rewire["body"]["type"] == "contact_changed"   # changed
        assert rewire["body"]["name"] == "New"               # changed
        assert rewire["body"]["workflow_id"] == FAKE_WF      # preserved
        assert rewire["body"]["id"] == FAKE_TRIGGER          # preserved
        # The verify re-read also uses ?includeTriggers=true.
        assert "includeTriggers=true" in rewire["verify_read"]["path"]
        assert rewire["verify_changed_fields"] == ["name", "type"]

    def test_ledger_target_is_the_parallel_wf_rewired_state(self):
        plan = b.emit_workflow_rewire_plan(**self._kwargs())
        assert plan["ledger_target"] == b.WORKFLOW_LEDGER_STATE == "wf-rewired"

    def test_mismatch_refuses(self):
        plan = b.emit_workflow_rewire_plan(**self._kwargs(current_location_id=WRONG_LOC))
        assert plan["ok"] is False
        assert plan["refused"] is True
        assert plan["steps"] == []

    def test_token_id_scheme_on_eval_steps(self):
        plan = b.emit_workflow_rewire_plan(**self._kwargs())
        for s in plan["steps"]:
            if "eval" in s:
                assert '"token-id": window.__VT' in s["eval"]
                assert "Bearer" not in s["eval"]


# ── emit_revert_plan ──────────────────────────────────────────────────────────

class TestRevertPlan:
    def _kwargs(self, **overrides) -> dict:
        kwargs = dict(
            page_id=FAKE_PAGE_ID,
            funnel_id=FAKE_FUNNEL_ID,
            location_id=FIXTURE_LOC,
            current_location_id=FIXTURE_LOC,
            baseline_page_data=_customcode_blob(),
            current_page_version=2,
        )
        kwargs.update(overrides)
        return kwargs

    def test_single_draft_step_reposts_pristine_baseline(self):
        blob = _customcode_blob("<img src='old.png'>")
        plan = b.emit_revert_plan(**self._kwargs(baseline_page_data=blob))
        assert plan["ok"] is True
        assert len(plan["steps"]) == 1
        step = plan["steps"][0]
        assert step["step"] == "revert_baseline"
        assert step["method"] == "POST"
        assert step["body"]["pageType"] == "draft"        # revert is always draft
        assert step["body"]["pageVersion"] == 3           # new draft version n+1
        assert rc.is_byte_identical(step["body"]["pageData"], blob)

    def test_expect_carries_byte_identical_md5(self):
        blob = _customcode_blob("<img src='old.png'>")
        plan = b.emit_revert_plan(**self._kwargs(baseline_page_data=blob))
        assert plan["expect"]["byte_identical_md5"] == rc.blob_md5(blob)
        assert plan["expect"]["live_pointer_unchanged"] is True

    def test_external_caller_runs_the_gate(self):
        # An external caller (no _skip_gate) gets the guard attached.
        plan = b.emit_revert_plan(**self._kwargs())
        assert "guard" in plan
        assert plan["guard"]["ok"] is True

    def test_mismatch_refuses(self):
        plan = b.emit_revert_plan(**self._kwargs(current_location_id=WRONG_LOC))
        assert plan["ok"] is False
        assert plan["refused"] is True
        assert plan["steps"] == []

    def test_token_id_scheme(self):
        plan = b.emit_revert_plan(**self._kwargs())
        assert '"token-id": window.__VT' in plan["steps"][0]["eval"]
        assert "Bearer" not in plan["steps"][0]["eval"]


# ── The revert step embedded in emit_rest_save_plan == a standalone revert ────

class TestRestSaveRevertConsistency:
    def test_embedded_revert_matches_standalone_emit_revert_plan(self):
        blob = _customcode_blob("<img src='old.png'>")
        save = b.emit_rest_save_plan(**_save_kwargs(page_data=blob, page_version=1))
        embedded = next(s for s in save["steps"] if s["step"] == "revert_baseline")
        standalone = b.emit_revert_plan(
            page_id=FAKE_PAGE_ID, funnel_id=FAKE_FUNNEL_ID,
            location_id=FIXTURE_LOC, current_location_id=FIXTURE_LOC,
            baseline_page_data=blob, current_page_version=1,
        )["steps"][0]
        # Same byte-identical target + same draft body.
        assert embedded["expect"]["byte_identical_md5"] == \
            standalone["expect"]["byte_identical_md5"]
        assert embedded["body"]["pageVersion"] == standalone["body"]["pageVersion"]
        assert embedded["body"]["pageType"] == standalone["body"]["pageType"] == "draft"


# ── ledger_write accepts the parallel wf-rewired state ────────────────────────

class TestLedgerWorkflowState:
    def test_wf_rewired_state_is_accepted_and_persisted(self, tmp_path, monkeypatch):
        # Redirect the ledger root into tmp so nothing is written to /tmp/<run-id>.
        run_id = "rest-wire-test"
        monkeypatch.setattr(
            b, "_ledger_path",
            lambda rid, funnel, step: str(tmp_path / rid / funnel / f"{step}.json"),
        )
        path = b.ledger_write(run_id, "zhc-f", "wf-step",
                              b.WORKFLOW_LEDGER_STATE, {"workflow_id": FAKE_WF})
        rec = json.load(open(path))
        assert rec["state"] == "wf-rewired"
        assert rec["workflow_id"] == FAKE_WF

    def test_wf_rewired_is_not_ordered_against_page_states(self, tmp_path, monkeypatch):
        # The parallel state must not rewind a real page state (nor be rewound by
        # one) — it is never compared against the LEDGER_STATES ordering.
        monkeypatch.setattr(
            b, "_ledger_path",
            lambda rid, funnel, step: str(tmp_path / rid / funnel / f"{step}.json"),
        )
        # Write a page step at 'page-saved', then the SAME step at 'wf-rewired':
        # the page state must survive (wf-rewired is not "earlier", so no rewind
        # logic touches it), and re-writing 'page-saved' keeps page-saved.
        b.ledger_write("r", "zhc-f", "pg", "page-saved")
        b.ledger_write("r", "zhc-f", "pg", "wf-rewired")
        rec = json.load(open(b._ledger_path("r", "zhc-f", "pg")))
        # Last write wins for a non-ordered state (no rewind comparison applies).
        assert rec["state"] == "wf-rewired"

    def test_unknown_state_still_rejected(self):
        with pytest.raises(ValueError):
            b.ledger_write("r", "f", "s", "not-a-real-state")


# ── CLI subcommands (rest-save-plan / wf-rewire-plan / revert-plan) ───────────

class TestRestPlanCli:
    def _run(self, args: list[str]):
        return subprocess.run(
            [sys.executable, os.path.join(_TOOLS_DIR, "ghl_builder.py"), *args],
            capture_output=True, text=True,
        )

    def test_rest_save_plan_cli_match_exit_zero(self, tmp_path):
        spec = _save_kwargs()
        spec_path = tmp_path / "save_spec.json"
        spec_path.write_text(json.dumps(spec))
        res = self._run(["rest-save-plan", str(spec_path)])
        assert res.returncode == 0, res.stderr
        plan = json.loads(res.stdout)
        assert plan["ok"] is True
        assert [s["step"] for s in plan["steps"]][0] == "stage_token"

    def test_rest_save_plan_cli_mismatch_exit_one(self, tmp_path):
        spec = _save_kwargs(current_location_id=WRONG_LOC)
        spec_path = tmp_path / "save_spec_bad.json"
        spec_path.write_text(json.dumps(spec))
        res = self._run(["rest-save-plan", str(spec_path)])
        # A refused (MISMATCH) plan is a hard stop -> non-zero exit.
        assert res.returncode == 1
        plan = json.loads(res.stdout)
        assert plan["refused"] is True
        assert plan["steps"] == []

    def test_wf_rewire_plan_cli(self, tmp_path):
        spec = dict(
            location_id=FIXTURE_LOC, current_location_id=FIXTURE_LOC,
            workflow_id=FAKE_WF, trigger_id=FAKE_TRIGGER,
            spec={"type": "contact_changed"}, existing_trigger=_trigger_record(),
        )
        spec_path = tmp_path / "wf_spec.json"
        spec_path.write_text(json.dumps(spec))
        res = self._run(["wf-rewire-plan", str(spec_path)])
        assert res.returncode == 0, res.stderr
        plan = json.loads(res.stdout)
        assert plan["ledger_target"] == "wf-rewired"

    def test_revert_plan_cli(self, tmp_path):
        spec = dict(
            page_id=FAKE_PAGE_ID, funnel_id=FAKE_FUNNEL_ID,
            location_id=FIXTURE_LOC, current_location_id=FIXTURE_LOC,
            baseline_page_data=_customcode_blob(), current_page_version=2,
        )
        spec_path = tmp_path / "revert_spec.json"
        spec_path.write_text(json.dumps(spec))
        res = self._run(["revert-plan", str(spec_path)])
        assert res.returncode == 0, res.stderr
        plan = json.loads(res.stdout)
        assert plan["steps"][0]["step"] == "revert_baseline"
