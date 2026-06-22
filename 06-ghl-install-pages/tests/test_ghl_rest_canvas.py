"""MOCK-only unit tests — ghl_rest_canvas (the cracked GHL canvas-REST surface).

These tests are MOCK-ONLY. There are NO live GHL calls, no real fixture, no
agent-browser against real GHL, no network of any kind. The agent-browser eval
and the HTTP responses are mocked; the assertions cover:

  * request SHAPES — paths, headers, payloads (the ``token-id`` scheme, the
    SPA channel/source/version, the numeric pageVersion, the draft pageType).
  * the GAP-1 image-swap / Code-element splice (pure transform, copy semantics).
  * the GAP-3 trigger rewire body (whole record + changed fields) and the
    ``?includeTriggers=true`` read contract.
  * REVERSIBILITY — byte-identical (md5) restore logic.
  * token staging via a python-WRITTEN JS file (never bash ${VAR@Q}).
  * the D6 headless-forced agent-browser eval wrapper.

No real client/operator names, ids, emails, or location-ids appear — all values
are generic / parameterised fakes.
"""
from __future__ import annotations

import json
import os
import sys

# Ensure ghl_rest_canvas (and its ghl_builder sibling) are importable regardless
# of working directory — same convention as the other tests in this suite.
_TOOLS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "tools")
)
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import pytest

import ghl_rest_canvas as rc


# ── Generic fakes (NO real client/operator data) ─────────────────────────────

FAKE_TOKEN = "eyJhbG.fake-jwt.signature"  # not a real JWT; structurally JWT-ish
FAKE_PAGE_ID = "PAGEID0000000000fake"
FAKE_FUNNEL_ID = "FUNNELID000000000fake"
FAKE_LOC = "LOCATION0000000fake"
FAKE_WF = "WORKFLOW0000000fake"
FAKE_TRIGGER = "TRIGGER00000000fake"


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
        "location_id": FAKE_LOC,
        "conditions": [],
        "actions": [],
        "active": True,
    }


# ── Path builders ─────────────────────────────────────────────────────────────

class TestPaths:
    def test_page_read_path_with_location(self):
        assert rc.page_read_path(FAKE_PAGE_ID, FAKE_LOC) == \
            f"/funnels/page/{FAKE_PAGE_ID}?locationId={FAKE_LOC}"

    def test_page_read_path_without_location(self):
        assert rc.page_read_path(FAKE_PAGE_ID) == f"/funnels/page/{FAKE_PAGE_ID}"

    def test_page_autosave_path(self):
        assert rc.page_autosave_path(FAKE_PAGE_ID) == \
            f"/funnels/builder/autosave/{FAKE_PAGE_ID}"

    def test_workflow_detail_path_includes_triggers(self):
        path = rc.workflow_detail_path(FAKE_LOC, FAKE_WF)
        assert path == f"/workflow/{FAKE_LOC}/{FAKE_WF}?includeTriggers=true"
        # The ?includeTriggers=true contract is LOAD-BEARING.
        assert "includeTriggers=true" in path

    def test_trigger_put_path(self):
        assert rc.trigger_put_path(FAKE_LOC, FAKE_TRIGGER) == \
            f"/workflow/{FAKE_LOC}/trigger/{FAKE_TRIGGER}"

    @pytest.mark.parametrize("bad", ["", "   ", None])
    def test_empty_path_component_rejected(self, bad):
        with pytest.raises(ValueError):
            rc.page_read_path(bad)
        with pytest.raises(ValueError):
            rc.page_autosave_path(bad)


# ── autosave_body / next_page_version ─────────────────────────────────────────

class TestAutosaveBody:
    def test_default_is_draft_and_numeric_bump(self):
        body = rc.autosave_body(FAKE_FUNNEL_ID, _customcode_blob(), page_version=1)
        assert body["pageType"] == "draft"          # default DRAFT keeps it unpublished
        assert body["pageVersion"] == 2             # numeric n+1
        assert body["manualSave"] is True
        assert body["funnelId"] == FAKE_FUNNEL_ID
        assert body["integrations"] == {}

    def test_publish_flag_sets_published(self):
        body = rc.autosave_body(FAKE_FUNNEL_ID, _customcode_blob(), page_version=4,
                                publish=True)
        assert body["pageType"] == "published"
        assert body["pageVersion"] == 5

    def test_integrations_passthrough(self):
        integ = {"ga": {"id": "X"}}
        body = rc.autosave_body(FAKE_FUNNEL_ID, _customcode_blob(), page_version=1,
                                integrations=integ)
        assert body["integrations"] == integ

    def test_uuid_page_version_rejected(self):
        # A UUID 422s on the live API ("pageVersion must be a number"); reject early.
        with pytest.raises(ValueError):
            rc.autosave_body(FAKE_FUNNEL_ID, _customcode_blob(),
                             page_version="11111111-2222-3333-4444-555555555555")

    def test_non_dict_page_data_rejected(self):
        with pytest.raises(TypeError):
            rc.autosave_body(FAKE_FUNNEL_ID, "not-a-dict", page_version=1)

    def test_next_page_version(self):
        assert rc.next_page_version({"pageVersion": 7}) == 8

    def test_next_page_version_non_numeric_raises(self):
        with pytest.raises(ValueError):
            rc.next_page_version({"pageVersion": "abc-uuid"})


# ── GAP-1: edit_element_customcode (pure transform) ───────────────────────────

class TestEditElementCustomcode:
    def test_swaps_raw_custom_code(self):
        blob = _customcode_blob("<img src='old.png'>")
        out = rc.edit_element_customcode(
            blob, {"section_idx": 0, "element_idx": 0}, "<img src='new.png'>")
        assert out["sections"][0]["elements"][0]["extra"]["customCode"]["value"]["rawCustomCode"] \
            == "<img src='new.png'>"

    def test_input_blob_untouched_copy_semantics(self):
        # Reversibility hinges on the caller keeping a pristine baseline — the
        # transform MUST NOT mutate its input.
        blob = _customcode_blob("<img src='old.png'>")
        before = json.dumps(blob, sort_keys=True)
        rc.edit_element_customcode(
            blob, {"section_idx": 0, "element_idx": 0}, "<img src='new.png'>")
        assert json.dumps(blob, sort_keys=True) == before

    def test_wrong_element_fails_loud_not_silent(self):
        # A non-custom-code element must raise, never silently no-op (a silent
        # no-op would look like an edit that never landed).
        blob = {"sections": [{"elements": [{"id": "x", "type": "image", "extra": {}}]}]}
        with pytest.raises(KeyError):
            rc.edit_element_customcode(
                blob, {"section_idx": 0, "element_idx": 0}, "v")

    def test_out_of_range_index_raises(self):
        blob = _customcode_blob()
        with pytest.raises(IndexError):
            rc.edit_element_customcode(
                blob, {"section_idx": 9, "element_idx": 0}, "v")

    def test_non_int_locator_rejected(self):
        blob = _customcode_blob()
        with pytest.raises(TypeError):
            rc.edit_element_customcode(blob, {"section_idx": "0", "element_idx": 0}, "v")


# ── GAP-3: trigger rewire body ────────────────────────────────────────────────

class TestTriggerRewireBody:
    def test_merges_changed_fields_over_existing(self):
        existing = _trigger_record(name="Old", ttype="contact_created")
        spec = {"name": "New", "type": "contact_changed"}
        body = rc.trigger_rewire_body(existing, spec)
        assert body["name"] == "New"
        assert body["type"] == "contact_changed"
        # Unrelated fields preserved (not dropped).
        assert body["workflow_id"] == FAKE_WF
        assert body["location_id"] == FAKE_LOC
        assert body["id"] == FAKE_TRIGGER

    def test_inputs_not_mutated(self):
        existing = _trigger_record()
        before = json.dumps(existing, sort_keys=True)
        rc.trigger_rewire_body(existing, {"name": "Changed"})
        assert json.dumps(existing, sort_keys=True) == before

    def test_empty_spec_rejected(self):
        with pytest.raises(ValueError):
            rc.trigger_rewire_body(_trigger_record(), {})


# ── Reversibility (byte-identical restore) ────────────────────────────────────

class TestReversibility:
    def test_md5_stable_across_key_order(self):
        a = {"x": 1, "y": 2}
        b = {"y": 2, "x": 1}
        assert rc.blob_md5(a) == rc.blob_md5(b)

    def test_edit_then_revert_is_byte_identical(self):
        baseline = _customcode_blob("<img src='old.png'>")
        edited = rc.edit_element_customcode(
            baseline, {"section_idx": 0, "element_idx": 0}, "<img src='new.png'>")
        # Edited differs from baseline.
        assert not rc.is_byte_identical(baseline, edited)
        # Revert = re-post the pristine baseline; canonical re-read == baseline.
        restored = json.loads(json.dumps(baseline))  # simulate the re-read blob
        assert rc.is_byte_identical(baseline, restored)

    def test_revert_body_reposts_pristine_as_draft(self):
        baseline = _customcode_blob("<img src='old.png'>")
        body = rc.revert_body(FAKE_FUNNEL_ID, baseline, current_page_version=2)
        assert body["pageType"] == "draft"          # never publishes on revert
        assert body["pageVersion"] == 3             # new draft version (n+1)
        assert rc.is_byte_identical(body["pageData"], baseline)


# ── Token staging (python-written JS — NEVER bash ${VAR@Q}) ───────────────────

class TestTokenStaging:
    def test_stage_token_js_uses_json_encoded_literal(self):
        js = rc.stage_token_js(FAKE_TOKEN)
        # The token is embedded as a json.dumps string literal (safe), not raw.
        assert json.dumps(FAKE_TOKEN) in js
        assert js.startswith(f"window.{rc.TOKEN_JS_GLOBAL} =")

    def test_stage_token_js_no_bash_var_q(self):
        # The whole point: no ${...@Q} / bash interpolation anywhere in the JS.
        js = rc.stage_token_js(FAKE_TOKEN)
        assert "@Q" not in js
        assert "${" not in js

    def test_stage_token_js_escapes_dangerous_chars(self):
        # A token with quotes/backslashes must round-trip through JSON.parse safely.
        tricky = 'abc"def\\ghi'
        js = rc.stage_token_js(tricky)
        # Recover the literal and confirm it decodes back to the exact token.
        literal = js.split("=", 1)[1].strip().rstrip(";").strip()
        assert json.loads(literal) == tricky

    def test_write_token_js_file(self, tmp_path):
        out = tmp_path / "token.js"
        path = rc.write_token_js_file(FAKE_TOKEN, str(out))
        assert path == str(out)
        content = out.read_text(encoding="utf-8")
        assert content.startswith(f"window.{rc.TOKEN_JS_GLOBAL} =")
        assert json.dumps(FAKE_TOKEN) in content

    def test_empty_token_rejected(self):
        with pytest.raises(ValueError):
            rc.stage_token_js("")

    def test_bad_global_name_rejected(self):
        with pytest.raises(ValueError):
            rc.stage_token_js(FAKE_TOKEN, global_name="not a name")


# ── build_fetch_js — request shape / headers / payload ────────────────────────

class TestBuildFetchJs:
    def test_get_carries_token_id_header_not_bearer(self):
        path = rc.page_read_path(FAKE_PAGE_ID, FAKE_LOC)
        js = rc.build_fetch_js("GET", path)
        # token-id is the scheme; Authorization: Bearer is the WRONG scheme (401).
        assert '"token-id": window.__VT' in js
        assert "Authorization" not in js
        assert "Bearer" not in js

    def test_get_carries_spa_headers(self):
        js = rc.build_fetch_js("GET", rc.page_read_path(FAKE_PAGE_ID))
        assert f'"channel": "{rc.SPA_CHANNEL}"' in js
        assert f'"source": "{rc.SPA_SOURCE}"' in js
        assert f'"version": "{rc.SPA_VERSION}"' in js
        assert rc.SPA_VERSION == "2021-07-28"

    def test_get_targets_backend_origin(self):
        js = rc.build_fetch_js("GET", rc.page_read_path(FAKE_PAGE_ID))
        assert rc.GHL_BACKEND_ORIGIN in js
        assert f"{rc.GHL_BACKEND_ORIGIN}/funnels/page/{FAKE_PAGE_ID}" in js

    def test_get_has_no_body(self):
        js = rc.build_fetch_js("GET", rc.page_read_path(FAKE_PAGE_ID))
        assert '"GET"' in js
        assert "JSON.stringify" not in js

    def test_post_attaches_json_body_and_content_type(self):
        body = rc.autosave_body(FAKE_FUNNEL_ID, _customcode_blob(), page_version=1)
        js = rc.build_fetch_js("POST", rc.page_autosave_path(FAKE_PAGE_ID), body=body)
        assert '"POST"' in js
        assert '"Content-Type":"application/json"' in js
        assert "JSON.stringify" in js
        # The numeric draft version + draft type are in the serialised payload.
        assert '"pageVersion": 2' in js or '"pageVersion":2' in js
        assert "draft" in js

    def test_put_attaches_body(self):
        body = rc.trigger_rewire_body(_trigger_record(), {"type": "contact_changed"})
        js = rc.build_fetch_js("PUT", rc.trigger_put_path(FAKE_LOC, FAKE_TRIGGER), body=body)
        assert '"PUT"' in js
        assert "contact_changed" in js

    def test_get_with_body_rejected(self):
        with pytest.raises(ValueError):
            rc.build_fetch_js("GET", "/x", body={"a": 1})

    def test_post_without_body_rejected(self):
        with pytest.raises(ValueError):
            rc.build_fetch_js("POST", "/x")

    def test_unsupported_method_rejected(self):
        with pytest.raises(ValueError):
            rc.build_fetch_js("PATCH", "/x")

    def test_fetch_js_is_valid_json_url_literal(self):
        # The URL is embedded via json.dumps — it must be a valid JSON string.
        js = rc.build_fetch_js("GET", rc.page_read_path(FAKE_PAGE_ID))
        # Extract the fetch(...) first argument and confirm it parses as JSON.
        start = js.index("fetch(") + len("fetch(")
        url_literal = js[start: js.index(",", start)].strip()
        assert json.loads(url_literal).startswith(rc.GHL_BACKEND_ORIGIN)


# ── agent-browser eval wrapper (D6 headless-forced) ───────────────────────────

class TestAgentBrowserEvalCmd:
    def test_argv_is_headless_forced(self):
        argv = rc.agent_browser_eval_cmd("sess-fake", "1+1")
        assert argv[0] == "agent-browser"
        # D6: --headed false MUST be present (no visible window can ever open).
        assert "--headed" in argv
        assert argv[argv.index("--headed") + 1] == "false"
        assert "--session" in argv and "sess-fake" in argv
        assert "eval" in argv

    def test_empty_session_rejected(self):
        with pytest.raises(ValueError):
            rc.agent_browser_eval_cmd("", "1+1")


# ── High-level step emitters (the in-browser eval steps the agent runs) ───────

class TestPageReadStep:
    def test_emits_get_step(self):
        step = rc.page_read(FAKE_PAGE_ID, FAKE_LOC)
        assert step["method"] == "GET"
        assert step["path"] == f"/funnels/page/{FAKE_PAGE_ID}?locationId={FAKE_LOC}"
        assert '"token-id": window.__VT' in step["eval"]
        # No argv unless a session is supplied (this module never drives a browser).
        assert "argv" not in step

    def test_argv_present_with_session(self):
        step = rc.page_read(FAKE_PAGE_ID, session="sess-fake")
        assert step["argv"][0] == "agent-browser"
        assert "--headed" in step["argv"]


class TestPageAutosaveStep:
    def test_draft_save_confirmation_contract(self):
        blob = rc.edit_element_customcode(
            _customcode_blob(), {"section_idx": 0, "element_idx": 0}, "<img src='new.png'>")
        step = rc.page_autosave(FAKE_PAGE_ID, blob, funnel_id=FAKE_FUNNEL_ID,
                                page_version=1)
        assert step["method"] == "POST"
        assert step["body"]["pageType"] == "draft"
        # The saved-blob + draft-pointer-unchanged confirmation contract.
        exp = step["expect"]
        assert exp["status"] == 201
        assert exp["response_keys"] == ["pageDataUrl", "pageDataDownloadUrl", "traceId"]
        assert exp["saved_page_version"] == 2
        assert exp["saved_page_type"] == "draft"
        assert exp["live_pointer_unchanged"] is True   # draft never moves the pointer

    def test_publish_marks_pointer_will_move(self):
        step = rc.page_autosave(FAKE_PAGE_ID, _customcode_blob(),
                                funnel_id=FAKE_FUNNEL_ID, page_version=1, publish=True)
        assert step["body"]["pageType"] == "published"
        assert step["expect"]["live_pointer_unchanged"] is False


class TestWorkflowReadTriggersStep:
    def test_include_triggers_contract(self):
        step = rc.workflow_read_triggers(FAKE_LOC, FAKE_WF)
        assert step["method"] == "GET"
        assert "includeTriggers=true" in step["path"]
        # The read contract: triggers are inline ONLY because of the query param.
        assert step["expect"]["includes_triggers_query"] is True
        assert step["expect"]["triggers_inline"] is True


class TestWorkflowRewireStep:
    def test_rewire_step_shape_and_verify_read(self):
        existing = _trigger_record(name="Old", ttype="contact_created")
        spec = {"name": "New", "type": "contact_changed"}
        step = rc.workflow_rewire_trigger(
            FAKE_LOC, FAKE_WF, FAKE_TRIGGER, spec, existing_trigger=existing)
        assert step["method"] == "PUT"
        assert step["path"] == f"/workflow/{FAKE_LOC}/trigger/{FAKE_TRIGGER}"
        # Body = whole record + changed fields.
        assert step["body"]["type"] == "contact_changed"
        assert step["body"]["workflow_id"] == FAKE_WF
        # Landing contract.
        assert step["expect"]["status"] == 200
        assert step["expect"]["response_message"] == "Trigger updated successfully"
        # The rewire-landed check re-reads WITH ?includeTriggers=true.
        assert "includeTriggers=true" in step["verify_read"]["path"]
        assert step["verify_changed_fields"] == ["name", "type"]


# ── End-to-end MOCK flow: edit → save → verify → revert (no live calls) ───────

class TestMockEndToEndReversibility:
    """Drives the full GAP-1 flow with a MOCKED agent-browser eval + MOCKED HTTP
    responses, asserting request shapes and byte-identical revert. No network."""

    def _mock_eval(self, captured: list):
        """Return a fake agent-browser eval: records the JS it was 'run' with and
        returns a canned response object (mirroring {status, ok, body})."""
        def _runner(js: str, response: dict):
            captured.append(js)
            return response
        return _runner

    def test_full_flow(self):
        captured: list[str] = []
        run = self._mock_eval(captured)

        baseline = _customcode_blob("<img src='old.png'>")

        # 1. READ — mock the GET response (numeric pageVersion + signed URL).
        read_step = rc.page_read(FAKE_PAGE_ID, FAKE_LOC)
        read_resp = run(read_step["eval"], {
            "status": 200, "ok": True,
            "body": {"pageVersion": 1,
                     "pageDataDownloadUrl": "https://signed.example/blob.json"},
        })
        assert read_resp["body"]["pageVersion"] == 1
        page_version = read_resp["body"]["pageVersion"]

        # 2. EDIT — GAP-1 image swap (pure transform; baseline preserved).
        edited = rc.edit_element_customcode(
            baseline, {"section_idx": 0, "element_idx": 0}, "<img src='new.png'>")
        assert not rc.is_byte_identical(baseline, edited)

        # 3. SAVE — mock the autosave 201 (draft; live pointer unchanged).
        save_step = rc.page_autosave(FAKE_PAGE_ID, edited, funnel_id=FAKE_FUNNEL_ID,
                                     page_version=page_version)
        save_resp = run(save_step["eval"], {
            "status": 201, "ok": True,
            "body": {"pageDataUrl": "u", "pageDataDownloadUrl": "u2", "traceId": "t"},
        })
        assert save_resp["status"] == 201
        assert save_step["body"]["pageType"] == "draft"
        assert save_step["body"]["pageVersion"] == 2

        # 4. VERIFY — mock the canonical re-read carrying the edit; live pointer
        #    stayed at 1 (never published).
        verify_resp = run(read_step["eval"], {
            "status": 200, "ok": True,
            "body": {"pageVersion": 1, "_blob": edited},
        })
        assert verify_resp["body"]["pageVersion"] == 1  # LIVE pointer unchanged
        assert "new.png" in verify_resp["body"]["_blob"]["sections"][0]["elements"][0][
            "extra"]["customCode"]["value"]["rawCustomCode"]

        # 5. REVERT — re-post pristine baseline; canonical re-read byte-identical.
        revert = rc.revert_body(FAKE_FUNNEL_ID, baseline, current_page_version=1)
        restored_resp = run(rc.build_fetch_js("POST", rc.page_autosave_path(FAKE_PAGE_ID),
                                              body=revert),
                            {"status": 201, "ok": True, "body": {"_blob": baseline}})
        assert restored_resp["status"] == 201
        assert rc.is_byte_identical(restored_resp["body"]["_blob"], baseline)

        # The mocked eval recorded JS for read, save, verify, revert — all
        # carrying the token-id header, none using Authorization: Bearer.
        assert len(captured) == 4
        for js in captured:
            assert '"token-id": window.__VT' in js
            assert "Bearer" not in js


# ── Wire-in contract: the eval-cmd reuses ghl_builder.browser_cmd (D6) ────────

class TestEvalCmdReusesBuilderHeadlessPrefix:
    """The wire-in depends on agent_browser_eval_cmd lazily importing
    ghl_builder.browser_cmd so the D6 `--headed false` prefix is applied through
    the SINGLE source of truth (not re-implemented here). Assert the emitted argv
    is exactly what browser_cmd would produce, tokenised."""

    def test_argv_equals_builder_browser_cmd_tokenised(self):
        import shlex
        import ghl_builder as b
        js = rc.build_fetch_js("GET", rc.page_read_path(FAKE_PAGE_ID))
        argv = rc.agent_browser_eval_cmd("sess-fake", js)
        # browser_cmd is the single source of truth for the headless prefix.
        expected = shlex.split(b.browser_cmd("--session", "sess-fake", "eval", js))
        assert argv == expected
        # And it really carries the D6 headless override.
        assert argv[:3] == ["agent-browser", "--headed", "false"]


class TestByteIdenticalAsymmetry:
    """is_byte_identical must be FALSE for an edit and TRUE only for a true
    restore — the property the revert plan's md5 contract relies on."""

    def test_edit_is_not_byte_identical_but_restore_is(self):
        baseline = _customcode_blob("<img src='old.png'>")
        edited = rc.edit_element_customcode(
            baseline, {"section_idx": 0, "element_idx": 0}, "<img src='new.png'>")
        assert rc.is_byte_identical(baseline, edited) is False
        # A re-read of the pristine bytes round-trips byte-identical.
        restored = json.loads(json.dumps(baseline))
        assert rc.is_byte_identical(baseline, restored) is True
        assert rc.blob_md5(baseline) == rc.blob_md5(restored)
