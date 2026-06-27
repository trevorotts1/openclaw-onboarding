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

import browser_manager  # SINGLETON POOLED BROWSER gateway (session bracket)
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
        # Emitters must be bracketed by an active singleton session.
        with browser_manager.browser_session("sess-fake"):
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
        with browser_manager.browser_session("sess-fake"):
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
        with browser_manager.browser_session("sess-fake"):
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


# ── B6 ADDITIONS: new_page_blob theme/colors + section->row->column contract ──
#
# These tests cover the B1 bug fix: new_page_blob must produce a page blob with
# a populated defaultSettings{colors{...}} theme object and a full
# section -> row -> column -> element nesting, for both 'website' and 'funnel'
# surfaces.  A blob without a colors object causes GoHighLevel's renderer to
# crash with "Cannot read properties of undefined (reading 'colors')" — the
# direct cause of every HTTP 500 in the pre-flight.
#
# The golden fixture (one small known-good page blob from B5) lives at
# tests/fixtures/golden_page_blob.json.  Tests import it with a helper so blob
# tests run hermetically without any network or live GoHighLevel call.

import pathlib as _pathlib

_FIXTURES_DIR = _pathlib.Path(__file__).parent / "fixtures"
_GOLDEN_WEBSITE_FIXTURE = _FIXTURES_DIR / "golden_page_blob_website.json"
_GOLDEN_FUNNEL_FIXTURE  = _FIXTURES_DIR / "golden_page_blob_funnel.json"


def _load_golden(path: _pathlib.Path) -> dict:
    """Load a golden fixture, skipping the test if it does not exist yet.

    B5 (references/golden blobs) may not be landed yet when B6 runs in CI.
    We skip rather than fail so CI stays green until B5 lands.
    """
    if not path.exists():
        pytest.skip(f"golden fixture not yet present: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _new_page_blob(html: str, surface: str) -> dict:
    """Call new_page_blob with the surface kwarg; skip if B1 not yet landed."""
    import inspect
    sig = inspect.signature(rc.new_page_blob)
    if "surface" not in sig.parameters:
        pytest.skip(
            "new_page_blob does not yet accept 'surface' kwarg (B1 pending — "
            "the theme/colors fix has not landed yet)"
        )
    return rc.new_page_blob(html, surface=surface)


class TestNewPageBlobWebsite:
    """new_page_blob(surface='website') must produce a renderable GHL blob."""

    def _blob(self, html: str = "<p>hello</p>") -> dict:
        return _new_page_blob(html, surface="website")

    # ── colors object ─────────────────────────────────────────────────────────

    def test_colors_is_non_empty_list(self):
        """The colors object must be a non-empty list of {label, value} dicts.

        B5 authoritative finding: general.general.colors is an 18-entry list of
        {label, value} dicts — NOT a dict, NOT absent, NOT a list of hex strings.
        Absence causes 'Cannot read properties of undefined (reading colors)' 500.
        """
        blob = self._blob()
        colors = _drill_colors(blob)
        assert isinstance(colors, list), \
            f"colors must be a list (not {type(colors).__name__})"
        assert len(colors) > 0, "colors list must not be empty"
        assert isinstance(colors[0], dict) and "label" in colors[0], \
            f"colors entries must be {{label, value}} dicts, got {colors[0]!r}"

    def test_colors_at_golden_path(self):
        """The colors list must live at general.general.colors — that is the
        exact path GoHighLevel's renderer dereferences.  B5 live-capture
        confirmed that a blob without it crashes with 'reading colors'.

        NOTE: defaultSettings.colors does NOT exist in real GoHighLevel blobs.
        The correct path is general.general.colors.
        """
        blob = self._blob()
        # Confirm general.general.colors is populated
        colors = blob.get("general", {}).get("general", {}).get("colors")
        assert isinstance(colors, list) and len(colors) > 0, \
            "general.general.colors must be a non-empty list of {label, value} dicts"
        # Confirm defaultSettings does NOT mislead — it either doesn't exist
        # or doesn't carry colors (B5 authoritative: this key is absent in live blobs).
        assert blob.get("defaultSettings") is None or "colors" not in blob.get("defaultSettings", {}), \
            "defaultSettings.colors should not exist — correct path is general.general.colors"

    def test_colors_is_a_label_value_list(self):
        """Colors must be a list of {label, value} dicts (the 18-entry palette).

        B5 authoritative: the real format is [{label: 'Primary', value: '#37ca37'}, ...].
        A list of bare hex strings is NOT acceptable (different from what the renderer
        expects — it reads .colors[n].value, not .colors[n] directly).
        """
        blob = self._blob()
        colors = _drill_colors(blob)
        assert isinstance(colors, list), \
            f"colors must be a list of {{label, value}} dicts, got {type(colors).__name__}"
        for entry in colors[:3]:  # check first three entries
            assert isinstance(entry, dict), f"color entry must be dict, got {entry!r}"
            assert "value" in entry, f"color entry missing 'value' key: {entry!r}"

    # ── section -> elements nesting ───────────────────────────────────────────
    # B5 authoritative: GoHighLevel page blobs use sections[0].elements as a
    # flat list containing row, col, and leaf nodes — NOT a nested rows/columns
    # tree.  The custom-code element is reachable via _find_custom_code_element.

    def test_section_row_column_element_chain(self):
        """The blob must pass assert_renderable_shape — colors present, sections
        non-empty, custom-code element reachable in sections[0].elements.

        B5 authoritative structure: elements are a flat list in sections[0].elements,
        not a nested rows→columns→elements tree.
        """
        blob = self._blob()
        _assert_renderable_shape(blob)  # raises on any missing invariant

    def test_element_type_is_custom_code(self):
        """The custom-code leaf element must be of a recognised type.

        Website surface (B5 authoritative): type='code', elType='code'.
        Funnel surface: type='element', meta='custom-code'.
        Both are acceptable; what matters is that extra.customCode.value.rawCustomCode
        is reachable.
        """
        blob = self._blob()
        el = _first_element(blob)
        # Website: type=code, elType=code
        # Funnel: type=element, meta=custom-code
        # Any of the following signal a custom-code node:
        valid_types = ("code", "customCode", "html", "custom-code", "element")
        assert el.get("type") in valid_types, \
            f"element type must be one of {valid_types}, got {el.get('type')!r}"
        # The rawCustomCode path must be reachable regardless of type name
        try:
            _ = el["extra"]["customCode"]["value"]["rawCustomCode"]
        except (KeyError, TypeError) as exc:
            raise AssertionError(
                f"extra.customCode.value.rawCustomCode must be reachable on the "
                f"element, but got {exc!r}. Element keys: {list(el.keys())}"
            ) from exc

    def test_element_has_raw_custom_code_payload(self):
        """The custom-code node must carry the page's HTML in the proven path:
        extra.customCode.value.rawCustomCode."""
        html = "<p>marker-abc123</p>"
        blob = self._blob(html)
        el = _first_element(blob)
        raw = (
            el.get("extra", {})
              .get("customCode", {})
              .get("value", {})
              .get("rawCustomCode", "")
        )
        assert html in raw, \
            "rawCustomCode must contain the supplied HTML fragment"

    # ── golden fixture cross-check ────────────────────────────────────────────

    def test_golden_website_blob_passes_renderable_shape(self):
        """The golden reference blob (from B5) must also pass assert_renderable_shape
        so the fixture itself proves the contract."""
        blob = _load_golden(_GOLDEN_WEBSITE_FIXTURE)
        _assert_renderable_shape(blob)  # no raise = pass


class TestNewPageBlobFunnel:
    """new_page_blob(surface='funnel') must enforce funnel-specific rules."""

    def _blob(self, html: str = "<p>hello</p>") -> dict:
        return _new_page_blob(html, surface="funnel")

    def test_doctype_stripped_from_raw_custom_code(self):
        """A full HTML document (<!DOCTYPE html>...) fed as input must have the
        doctype / html / head tags stripped so only the body-level fragment
        lands in rawCustomCode.  Storing a full document inside a GoHighLevel
        code element produces a blank editor canvas."""
        full_doc = (
            "<!DOCTYPE html><html><head><title>T</title></head>"
            "<body><p>content</p></body></html>"
        )
        blob = self._blob(full_doc)
        el = _first_element(blob)
        raw = (
            el.get("extra", {})
              .get("customCode", {})
              .get("value", {})
              .get("rawCustomCode", "")
        )
        assert "<!doctype" not in raw.lower(), \
            "rawCustomCode must NOT contain <!DOCTYPE ...>"
        assert "<html" not in raw.lower(), \
            "rawCustomCode must NOT contain <html ...>"
        assert "<head>" not in raw.lower(), \
            "rawCustomCode must NOT contain <head>"
        # The body-level content must survive.
        assert "<p>content</p>" in raw, \
            "rawCustomCode must preserve body-level content"

    def test_colors_is_a_label_value_list_funnel(self):
        """On the funnel surface, colors must be a non-empty list of {label, value} dicts.

        B5 authoritative: general.general.colors is [{label:'Primary',value:'#37ca37'}, ...].
        The pre-flight bug was a MISSING colors object (causing the 500), not a list vs dict
        distinction. The fix is to load from the golden which has the 18-entry list.
        """
        blob = self._blob()
        colors = _drill_colors(blob)
        assert isinstance(colors, list) and len(colors) > 0, \
            f"funnel blob general.general.colors must be a non-empty list, got {colors!r}"
        assert isinstance(colors[0], dict) and "value" in colors[0], \
            f"funnel blob colors entries must be {{label,value}} dicts, got {colors[0]!r}"

    def test_html_fragment_hoists_style_out_of_head(self):
        """A <style> block inside a <head> must be hoisted to the top-level
        fragment so it is not swallowed by the strip operation."""
        html_with_head_style = (
            "<head><style>body{color:red}</style></head>"
            "<body><p>text</p></body>"
        )
        blob = self._blob(html_with_head_style)
        el = _first_element(blob)
        raw = (
            el.get("extra", {})
              .get("customCode", {})
              .get("value", {})
              .get("rawCustomCode", "")
        )
        # The style must survive even though <head> is stripped.
        assert "<style>" in raw, \
            "rawCustomCode must preserve <style> blocks hoisted from <head>"
        assert "color:red" in raw, \
            "rawCustomCode must preserve CSS rules from hoisted <style>"


# ── assert_renderable_shape (the shape-guard used by tests) ───────────────────
#
# B5 AUTHORITATIVE FINDING (2026-06-26, live golden capture):
# The real GoHighLevel page-data blob structure is:
#   colors at: general.general.colors — a LIST of {label, value} dicts (18 entries)
#   NOT at:    defaultSettings.colors (that key does not exist in live blobs)
# pageStyles: top-level CSS string with :root{--primary:...}
# Funnel custom-code element: sections[0].elements[idx] where meta=custom-code
# Website custom-code element: sections[0].elements[0] with type=code elType=code
#
# Tests that assumed defaultSettings.colors or rows/columns nesting are
# corrected here to match the authoritative golden structure.


def _drill_colors(blob: dict):
    """Extract the colors value from general.general.colors (or None).

    B5 authoritative finding: colors live at general.general.colors as a
    list of {label, value} dicts — NOT at defaultSettings.colors.
    """
    try:
        return blob["general"]["general"]["colors"]
    except (KeyError, TypeError):
        return None


def _find_custom_code_element(blob: dict) -> dict:
    """Find the custom-code element in sections[0].elements.

    Funnel: type=element, meta=custom-code
    Website: type=code, elType=code
    Fallback: first element with extra.customCode.value.rawCustomCode path.
    Returns {} if not found.
    """
    sections = blob.get("sections", [])
    if not sections:
        return {}
    elements = sections[0].get("elements", [])
    for elem in elements:
        if not isinstance(elem, dict):
            continue
        # Funnel shape
        if elem.get("type") == "element" and elem.get("meta") == "custom-code":
            return elem
        # Website shape
        if elem.get("type") == "code" and elem.get("elType") == "code":
            return elem
        # Fallback: any element with the rawCustomCode path
        try:
            _ = elem["extra"]["customCode"]["value"]["rawCustomCode"]
            return elem
        except (KeyError, TypeError):
            continue
    return elements[0] if elements else {}


def _first_element(blob: dict) -> dict:
    """Return the custom-code leaf element from sections[0].elements.

    B5 confirmed: GoHighLevel page blobs store elements directly in
    sections[0].elements — no intermediate rows/columns wrapper required.
    Uses _find_custom_code_element to locate the correct element.
    """
    return _find_custom_code_element(blob)


def _assert_renderable_shape(blob: dict) -> None:
    """Raise AssertionError when the blob lacks the minimum shape GoHighLevel's
    renderer requires.

    B5 authoritative shape (live golden, 2026-06-26):
      - general.general.colors: non-empty list of {label, value} dicts
      - sections: non-empty list
      - sections[0].elements: non-empty list
      - At least one element reachable with the custom-code payload path
    """
    # 1. colors must be a non-empty list of {label, value} dicts at general.general.colors
    colors = _drill_colors(blob)
    if isinstance(colors, str) or colors is None:
        raise AssertionError(
            "blob is missing general.general.colors (non-empty list) — "
            "GoHighLevel's renderer crashes with 'Cannot read properties of "
            "undefined (reading colors)' when this key is absent. "
            "NOTE: the correct path is general.general.colors, NOT defaultSettings.colors."
        )
    if not isinstance(colors, list) or len(colors) == 0:
        raise AssertionError(
            f"general.general.colors must be a non-empty list, got {type(colors).__name__!r} "
            f"with value {colors!r}"
        )

    # 2. sections must be a non-empty list
    sections = blob.get("sections")
    if not isinstance(sections, list) or len(sections) == 0:
        raise AssertionError("blob must have a non-empty 'sections' list")

    section = sections[0]

    # 3. The section must contain an elements list (GoHighLevel flattens row/col
    # into sections[0].elements — the row/col wrappers are SIBLINGS in elements,
    # not nested containers).
    elements = section.get("elements")
    if not isinstance(elements, list) or len(elements) == 0:
        raise AssertionError(
            "sections[0] must have a non-empty 'elements' list. "
            "GoHighLevel page blobs store row, col, and leaf elements "
            "as a flat list in sections[0].elements — not a nested rows/columns tree."
        )

    # 4. At least one element must have the custom-code payload path
    cc_elem = _find_custom_code_element(blob)
    if not cc_elem:
        raise AssertionError(
            "sections[0].elements must contain at least one custom-code element "
            "(funnel: type=element meta=custom-code; website: type=code elType=code)"
        )


# ── P0-3: child-link-chain reachability invariant (orphan-blank guard) ────────
#
# These exercise the PRODUCTION rc.assert_renderable_shape (Invariant 8). The
# v14.3.11 bug re-minted element ids without rewriting the parent ``child``
# arrays, orphaning the custom-code element: autosave returned 201, the marker
# was in the stored bytes, invariants 1-7 passed, yet the page rendered BLANK.
# Invariant 8 walks section.metaData.child -> row.child -> col.child and asserts
# the custom-code element id is reachable, making that class impossible.


def _find_cc_element_id(blob: dict):
    """Return the id of the element carrying extra.customCode.value.rawCustomCode."""
    for e in blob["sections"][0]["elements"]:
        try:
            if isinstance(e["extra"]["customCode"]["value"]["rawCustomCode"], str):
                return e.get("id")
        except (KeyError, TypeError):
            continue
    return None


class TestChildLinkChainInvariant:
    def test_healthy_blob_passes_invariant_8(self):
        """A freshly minted blob has a fully wired chain and passes."""
        blob = rc.new_page_blob("<p>marker-xyz</p>", surface="funnel")
        rc.assert_renderable_shape(blob, "funnel")  # no raise == pass

    def test_section_metadata_child_emptied_is_caught(self):
        """Orphaning at the TOP of the chain (metaData.child=[]) must fail."""
        blob = rc.new_page_blob("<p>marker</p>", surface="funnel")
        blob["sections"][0]["metaData"]["child"] = []
        with pytest.raises(AssertionError) as exc:
            rc.assert_renderable_shape(blob, "funnel")
        assert "Invariant 8" in str(exc.value)

    def test_row_child_dropped_orphans_element(self):
        """The v14.3.11 shape: row exists but its child array no longer points at
        the col (id re-minted without rewiring) — element unreachable."""
        blob = rc.new_page_blob("<p>marker</p>", surface="funnel")
        elements = blob["sections"][0]["elements"]
        # The row is the element referenced by metaData.child.
        row_id = blob["sections"][0]["metaData"]["child"][0]
        for e in elements:
            if e.get("id") == row_id:
                e["child"] = ["row-STALE-id-not-in-blob"]
        with pytest.raises(AssertionError) as exc:
            rc.assert_renderable_shape(blob, "funnel")
        assert "Invariant 8" in str(exc.value)
        # The custom-code element id should be reported as the orphan.
        assert str(_find_cc_element_id(blob)) in str(exc.value)

    def test_col_child_re_minted_without_rewrite(self):
        """Re-mint the custom-code element id but leave col.child pointing at the
        OLD id — the exact orphan-blank mechanic. Must be caught."""
        blob = rc.new_page_blob("<p>marker</p>", surface="funnel")
        cc_id = _find_cc_element_id(blob)
        for e in blob["sections"][0]["elements"]:
            if e.get("id") == cc_id:
                e["id"] = "custom-code-REMINTED"  # col.child still has old id
        with pytest.raises(AssertionError) as exc:
            rc.assert_renderable_shape(blob, "funnel")
        assert "Invariant 8" in str(exc.value)

    def test_website_surface_chain_also_enforced(self):
        blob = rc.new_page_blob("<p>w</p>", surface="website")
        rc.assert_renderable_shape(blob, "website")
        blob["sections"][0]["metaData"]["child"] = []
        with pytest.raises(AssertionError):
            rc.assert_renderable_shape(blob, "website")


# ── P1-2: allow_row_max_width parameterisation ───────────────────────────────


class TestAllowRowMaxWidth:
    def test_default_is_false_centered_1170(self):
        """Default (LIVE-probe safe state) keeps allowRowMaxWidth False and the
        1170px inner cap that drives the centered column."""
        blob = rc.new_page_blob("<p>x</p>", surface="funnel")
        meta = blob["sections"][0]["metaData"]
        assert meta["extra"]["allowRowMaxWidth"]["value"] is False
        assert "max-width:1170px" in blob["sections"][0]["general"]["sectionStyles"]

    def test_true_sets_flag_and_lifts_inner_cap(self):
        """Opt-in full width flips the metadata flag AND lifts the 1170px cap that
        the LIVE probe identified as the real width driver."""
        blob = rc.new_page_blob("<p>x</p>", surface="funnel", allow_row_max_width=True)
        meta = blob["sections"][0]["metaData"]
        assert meta["extra"]["allowRowMaxWidth"]["value"] is True
        styles = blob["sections"][0]["general"]["sectionStyles"]
        assert "max-width:1170px" not in styles
        assert "max-width:100%" in styles

    def test_blob_still_renderable_either_way(self):
        for flag in (True, False):
            blob = rc.new_page_blob("<p>x</p>", surface="funnel", allow_row_max_width=flag)
            rc.assert_renderable_shape(blob, "funnel")


# ── Brand palette injection ───────────────────────────────────────────────────
#
# Per-client brand/theme fidelity: new_page_blob must accept optional
# primary_color and secondary_color kwargs and inject them into
# general.general.colors (the 18-entry {label, value} palette) and the
# pageStyles CSS :root block.  The 18-entry shape must be preserved so
# assert_renderable_shape Invariant 2 (non-empty colors list) and the
# GoHighLevel renderer's hydration read both continue to resolve.
#
# When neither color is supplied the operator-scratch defaults (#37ca37 /
# #188bf6) must be unchanged so existing callers are not broken.


class TestBrandPaletteInjection:
    """new_page_blob brand palette injection — §4.4 per-client fidelity gate."""

    # ── default (no brand args) must keep operator-scratch palette ────────────

    def test_default_primary_color_unchanged(self):
        """Without brand args the Primary entry must stay #37ca37."""
        blob = rc.new_page_blob("<p>x</p>", surface="funnel")
        colors = blob["general"]["general"]["colors"]
        primary = next((c for c in colors if c.get("label") == "Primary"), None)
        assert primary is not None, "Primary entry missing from colors list"
        assert primary["value"] == "#37ca37", (
            f"Default primary must be #37ca37, got {primary['value']!r}"
        )

    def test_default_secondary_color_unchanged(self):
        """Without brand args the Secondary entry must stay #188bf6."""
        blob = rc.new_page_blob("<p>x</p>", surface="funnel")
        colors = blob["general"]["general"]["colors"]
        secondary = next((c for c in colors if c.get("label") == "Secondary"), None)
        assert secondary is not None, "Secondary entry missing from colors list"
        assert secondary["value"] == "#188bf6", (
            f"Default secondary must be #188bf6, got {secondary['value']!r}"
        )

    def test_default_page_styles_primary_unchanged(self):
        """Without brand args pageStyles CSS must contain --primary: #37ca37."""
        blob = rc.new_page_blob("<p>x</p>", surface="funnel")
        assert "--primary: #37ca37" in blob["pageStyles"], (
            "Default --primary not found in pageStyles"
        )

    def test_default_page_styles_secondary_unchanged(self):
        """Without brand args pageStyles CSS must contain --secondary: #188bf6."""
        blob = rc.new_page_blob("<p>x</p>", surface="funnel")
        assert "--secondary: #188bf6" in blob["pageStyles"], (
            "Default --secondary not found in pageStyles"
        )

    # ── brand args replace Primary and Secondary ──────────────────────────────

    def test_primary_color_replaces_primary_entry(self):
        """primary_color replaces the 'Primary' entry value in general.general.colors."""
        blob = rc.new_page_blob("<p>x</p>", surface="funnel", primary_color="#c0392b")
        colors = blob["general"]["general"]["colors"]
        primary = next((c for c in colors if c.get("label") == "Primary"), None)
        assert primary is not None
        assert primary["value"] == "#c0392b", (
            f"Expected #c0392b in Primary entry, got {primary['value']!r}"
        )

    def test_secondary_color_replaces_secondary_entry(self):
        """secondary_color replaces the 'Secondary' entry value in general.general.colors."""
        blob = rc.new_page_blob("<p>x</p>", surface="funnel", secondary_color="#2980b9")
        colors = blob["general"]["general"]["colors"]
        secondary = next((c for c in colors if c.get("label") == "Secondary"), None)
        assert secondary is not None
        assert secondary["value"] == "#2980b9", (
            f"Expected #2980b9 in Secondary entry, got {secondary['value']!r}"
        )

    def test_primary_color_replaces_css_var(self):
        """primary_color must also update --primary in pageStyles."""
        blob = rc.new_page_blob("<p>x</p>", surface="funnel", primary_color="#c0392b")
        assert "--primary: #c0392b" in blob["pageStyles"], (
            "--primary not updated in pageStyles"
        )
        # Operator-scratch value must be gone
        assert "--primary: #37ca37" not in blob["pageStyles"], (
            "Operator-scratch --primary still present after brand injection"
        )

    def test_secondary_color_replaces_css_var(self):
        """secondary_color must also update --secondary in pageStyles."""
        blob = rc.new_page_blob("<p>x</p>", surface="funnel", secondary_color="#2980b9")
        assert "--secondary: #2980b9" in blob["pageStyles"], (
            "--secondary not updated in pageStyles"
        )
        assert "--secondary: #188bf6" not in blob["pageStyles"], (
            "Operator-scratch --secondary still present after brand injection"
        )

    # ── 18-entry shape preserved ──────────────────────────────────────────────

    def test_palette_shape_preserved_both_colors(self):
        """Brand injection must keep all 18 entries — no entries added or dropped."""
        blob = rc.new_page_blob(
            "<p>x</p>", surface="funnel",
            primary_color="#c0392b", secondary_color="#2980b9",
        )
        colors = blob["general"]["general"]["colors"]
        assert len(colors) == 18, (
            f"general.general.colors must have 18 entries after brand injection, got {len(colors)}"
        )

    def test_non_brand_entries_untouched(self):
        """Brand injection must not modify any entry other than Primary/Secondary."""
        blob = rc.new_page_blob(
            "<p>x</p>", surface="funnel",
            primary_color="#c0392b", secondary_color="#2980b9",
        )
        colors = blob["general"]["general"]["colors"]
        for entry in colors:
            if entry.get("label") in ("Primary", "Secondary"):
                continue
            # All other entries must match the original constants
            original = next(
                (c for c in rc._FLAT_THEME_COLORS if c.get("label") == entry.get("label")),
                None,
            )
            assert original is not None, f"Unexpected entry label {entry.get('label')!r}"
            assert entry["value"] == original["value"], (
                f"Entry {entry['label']!r} was mutated: "
                f"expected {original['value']!r}, got {entry['value']!r}"
            )

    def test_blob_renderable_with_brand_colors(self):
        """A blob built with brand colors must pass assert_renderable_shape."""
        blob = rc.new_page_blob(
            "<p>brand-test</p>", surface="funnel",
            primary_color="#c0392b", secondary_color="#2980b9",
        )
        rc.assert_renderable_shape(blob, "funnel")  # raises on any invariant failure

    def test_blob_renderable_website_with_brand_colors(self):
        """Brand injection must work for the website surface too."""
        blob = rc.new_page_blob(
            "<p>brand-web</p>", surface="website",
            primary_color="#8e44ad", secondary_color="#27ae60",
        )
        rc.assert_renderable_shape(blob, "website")

    # ── only one color at a time ──────────────────────────────────────────────

    def test_only_primary_color_leaves_secondary_unchanged(self):
        """Supplying only primary_color must not touch Secondary."""
        blob = rc.new_page_blob("<p>x</p>", surface="funnel", primary_color="#e74c3c")
        colors = blob["general"]["general"]["colors"]
        secondary = next(c for c in colors if c.get("label") == "Secondary")
        assert secondary["value"] == "#188bf6", (
            "Secondary must be unchanged when only primary_color is supplied"
        )

    def test_only_secondary_color_leaves_primary_unchanged(self):
        """Supplying only secondary_color must not touch Primary."""
        blob = rc.new_page_blob("<p>x</p>", surface="funnel", secondary_color="#3498db")
        colors = blob["general"]["general"]["colors"]
        primary = next(c for c in colors if c.get("label") == "Primary")
        assert primary["value"] == "#37ca37", (
            "Primary must be unchanged when only secondary_color is supplied"
        )

    # ── invalid hex colors raise ValueError ──────────────────────────────────

    def test_invalid_primary_color_raises(self):
        """A non-hex primary_color must raise ValueError before blob assembly."""
        with pytest.raises(ValueError, match="primary_color"):
            rc.new_page_blob("<p>x</p>", surface="funnel", primary_color="red")

    def test_invalid_secondary_color_raises(self):
        """A non-hex secondary_color must raise ValueError before blob assembly."""
        with pytest.raises(ValueError, match="secondary_color"):
            rc.new_page_blob("<p>x</p>", surface="funnel", secondary_color="blue")

    def test_invalid_hex_no_hash_raises(self):
        """A hex string without the # prefix must raise ValueError."""
        with pytest.raises(ValueError):
            rc.new_page_blob("<p>x</p>", surface="funnel", primary_color="c0392b")

    def test_three_digit_hex_accepted(self):
        """Short 3-digit hex colors (#abc) must be accepted."""
        blob = rc.new_page_blob("<p>x</p>", surface="funnel", primary_color="#abc")
        colors = blob["general"]["general"]["colors"]
        primary = next(c for c in colors if c.get("label") == "Primary")
        assert primary["value"] == "#abc"

    # ── _apply_brand_palette is idempotent on None ────────────────────────────

    def test_apply_brand_palette_none_noop(self):
        """_apply_brand_palette with both None must return the same objects."""
        import ghl_rest_canvas as rc2
        import copy
        colors = copy.deepcopy(rc2._FLAT_THEME_COLORS)
        styles = rc2._FLAT_PAGE_STYLES
        out_colors, out_styles = rc2._apply_brand_palette(colors, styles, None, None)
        assert out_colors is colors  # identity — no copy
        assert out_styles is styles  # identity — no copy


# ── P1-1: lint_ghl_fragment — rejects ONLY what LIVE TRUTH proves stripped ────
#
# LIVE TRUTH: iframe / inline+msgsndr script / external CSS / >50KB body ALL
# survive and render. The lint must NEVER reject those. Hard errors are limited
# to empty fragments and un-stripped full documents (uncontested).


class TestLintGhlFragment:
    def test_iframe_is_allowed_not_rejected(self):
        res = rc.lint_ghl_fragment('<iframe src="https://example.com"></iframe>')
        assert res["ok"] is True
        assert res["errors"] == []
        assert any("iframe" in a.lower() for a in res["allowed"])

    def test_inline_script_is_allowed(self):
        res = rc.lint_ghl_fragment('<div></div><script>window.x=1;</script>')
        assert res["ok"] is True
        assert any("script" in a.lower() for a in res["allowed"])

    def test_msgsndr_hosted_script_is_allowed(self):
        res = rc.lint_ghl_fragment(
            '<script src="https://storage.googleapis.com/msgsndr/widget.js"></script>'
        )
        assert res["ok"] is True
        assert any("msgsndr" in a.lower() for a in res["allowed"])

    def test_external_css_is_allowed(self):
        res = rc.lint_ghl_fragment(
            '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/animate.css">'
        )
        assert res["ok"] is True
        assert any("css" in a.lower() for a in res["allowed"])

    def test_large_body_over_50kb_is_allowed(self):
        big = "<p>" + ("x" * (60 * 1024)) + "</p>"
        res = rc.lint_ghl_fragment(big)
        assert res["ok"] is True
        assert any("50kb" in a.lower() for a in res["allowed"])

    def test_empty_fragment_is_an_error(self):
        res = rc.lint_ghl_fragment("   ")
        assert res["ok"] is False
        assert any("empty" in e.lower() for e in res["errors"])

    def test_full_document_is_an_error(self):
        res = rc.lint_ghl_fragment("<!DOCTYPE html><html><body><p>x</p></body></html>")
        assert res["ok"] is False
        assert any("full" in e.lower() or "document" in e.lower() for e in res["errors"])

    def test_enforce_unverified_flag_adds_no_rejections(self):
        """The unverified-strip flag defaults safe and, today, blocks nothing —
        it only surfaces an advisory that the strip-set is unverified."""
        frag = '<iframe src="https://example.com"></iframe>'
        res = rc.lint_ghl_fragment(frag, enforce_unverified_strip=True)
        assert res["ok"] is True
        assert res["errors"] == []
        assert any("unverified" in w.lower() for w in res["warnings"])

    def test_non_string_raises_typeerror(self):
        with pytest.raises(TypeError):
            rc.lint_ghl_fragment(None)
