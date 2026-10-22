"""Offline tests for the FOLDER-CREATE implementation (Skill 06 v3.0 §10.2).

The gap this file closes: `funnel_folder` / `website_folder` existed in the
recipe contract, the LIST route was captured live, and NO folder-create path or
verb existed anywhere in `tools/*.py`. The create is now implemented in
`ghl_rest_canvas.folder_create*` behind a capture gate, wired into the recipe
contract via `ro.folder_create_recipe_contract`, and runnable through
`rr.run_folder_recipe`.

MOCK-ONLY: no network, no browser, no live GoHighLevel, no credentials. Every
"live" collaborator is an injected fake; every id is a synthetic fixture value.

What is proven here:
  * the create path/body come VERBATIM from the capture (nothing invented)
  * the capture gate: closed by default, refuses unreviewed, refuses synthetic
  * idempotent create/reuse: second run reuses the same native_id, no duplicate
  * the refusal paths: ambiguous name, wrong type scope, wrong location,
    wrong parent kind, missing schema fields
  * the recipe contract is `disabled` while the gate is closed

Run:
    python3 -m pytest tests/test_ghl_folder_create.py -v
"""
from __future__ import annotations

import json
import os
import sys

import pytest

_TOOLS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"
)
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import ghl_recipe_objects as ro  # noqa: E402
import ghl_recipe_runner as rr  # noqa: E402
import ghl_rest_canvas as canvas  # noqa: E402

LOC = "loc-fixture-0001"
OTHER_LOC = "loc-fixture-0002"
SHA = "sha256:" + "a" * 64


def _capture(**kw):
    """A schema-valid capture shape. NOT evidence — the `_fixture` marker is
    what keeps it out of any real path; drop it only to exercise the shape."""
    cap = {
        "location_id": LOC,
        "folder_type": "funnel",
        "create_method": "POST",
        "create_path": "/funnels/funnel/folder/create",
        "body_location_key": "locationId",
        "body_name_key": "name",
        "body_type_key": "type",
        "response_id_field": "id",
        "readback_keys": ["id", "name", "locationId", "type"],
        "expect_status": 201,
        "capture_evidence": "har://folder-create.json " + SHA,
    }
    cap.update(kw)
    return cap


def _web_capture(**kw):
    base = dict(
        folder_type="website",
        create_path="/funnels/funnel/folder/create",
        readback_keys=["id", "name", "locationId"],
    )
    base.update(kw)
    return _capture(**base)


def _folder_row(fid="folder-1", name="ZHC One", loc=LOC, type_="funnel"):
    return {"id": fid, "name": name, "locationId": loc, "type": type_}


# ── 1. Path + body shape ────────────────────────────────────────────────────

class TestPathAndBodyShape:
    def test_list_path_is_the_captured_route_for_both_scopes(self):
        assert canvas.folder_list_path(LOC, "funnel") == (
            f"/funnels/funnel/folder/list?locationId={LOC}&type=funnel"
        )
        assert canvas.folder_list_path(LOC, "website") == (
            f"/funnels/funnel/folder/list?locationId={LOC}&type=website"
        )

    def test_list_path_refuses_an_undeclared_type_scope(self):
        with pytest.raises(ValueError, match="folder_type"):
            canvas.folder_list_path(LOC, "blog")

    def test_create_path_is_replayed_verbatim_from_the_capture(self):
        cap = _capture(create_path="/funnels/funnel/folder/create-v2")
        assert canvas.folder_create_path(cap, reviewed=True) == (
            "/funnels/funnel/folder/create-v2"
        )

    def test_create_body_uses_the_captured_key_names_only(self):
        cap = _capture(body_location_key="locId", body_name_key="title",
                       body_type_key="kind")
        body = canvas.folder_create_body(LOC, "ZHC A", "funnel",
                                        capture=cap, reviewed=True)
        assert body == {"locId": LOC, "title": "ZHC A", "kind": "funnel"}
        assert "locationId" not in body and "name" not in body

    def test_body_type_key_is_omitted_when_the_capture_saw_none(self):
        body = canvas.folder_create_body(LOC, "ZHC A", "funnel",
                                        capture=_capture(body_type_key=""),
                                        reviewed=True)
        assert body == {"locationId": LOC, "name": "ZHC A"}

    def test_create_step_carries_the_captured_method_and_status(self):
        cap = _capture(create_method="PUT", expect_status=200)
        step = canvas.folder_create(LOC, "ZHC A", "funnel", capture=cap,
                                    reviewed=True)
        assert step["method"] == "PUT"
        assert step["expect"]["status"] == 200
        assert step["path"] == cap["create_path"]
        assert step["folder_type"] == "funnel"

    def test_create_step_expect_names_the_captured_id_field(self):
        cap = _capture(response_id_field="folderId",
                       readback_keys=["folderId", "name"])
        step = canvas.folder_create(LOC, "ZHC A", "funnel", capture=cap,
                                    reviewed=True)
        assert step["expect"]["new_folder_id_field"] == "folderId"
        assert step["expect"]["readback_keys"] == ["folderId", "name"]


# ── 2. The capture gate ─────────────────────────────────────────────────────

class TestCaptureGate:
    def test_default_state_is_pending_and_disabled(self):
        state = canvas.folder_create_capability_state()
        assert state["state"] == canvas.FOLDER_CREATE_PENDING
        assert state["enabled"] is False
        assert sorted(state["missing_capture_fields"]) == sorted(
            canvas.FOLDER_CREATE_REQUIRED_CAPTURE_FIELDS
        )

    def test_no_capture_means_capture_required(self):
        with pytest.raises(canvas.CaptureRequired):
            canvas.folder_create_path()

    def test_a_schema_valid_capture_alone_does_not_enable(self):
        state = canvas.folder_create_capability_state(_capture())
        assert state["state"] == canvas.FOLDER_CREATE_ENABLED_FOR_REVIEW
        assert state["schema_valid"] is True
        assert state["enabled"] is False

    def test_unreviewed_capture_refuses_the_operation(self):
        with pytest.raises(canvas.FolderCreateRefused, match="NOT reviewed"):
            canvas.folder_create_path(_capture())

    def test_reviewed_capture_enables_the_operation(self):
        assert canvas.folder_create_capability_state(
            _capture(), reviewed=True
        )["enabled"] is True
        assert canvas.folder_create_path(_capture(), reviewed=True)

    def test_the_shipped_fixture_is_never_evidence(self):
        assert canvas.is_synthetic_folder_capture(canvas.OFFLINE_FOLDER_CAPTURE)
        with pytest.raises(canvas.CaptureRequired, match="synthetic"):
            canvas.folder_create_path(canvas.OFFLINE_FOLDER_CAPTURE, reviewed=True)

    def test_a_plausible_but_malformed_capture_cannot_enable(self):
        bad = _capture(expect_status=500, create_path="funnel/create")
        state = canvas.folder_create_capability_state(bad, reviewed=True)
        assert state["state"] == canvas.FOLDER_CREATE_PENDING
        assert state["enabled"] is False
        assert state["schema_problems"]

    @pytest.mark.parametrize("field", list(
        canvas.FOLDER_CREATE_REQUIRED_CAPTURE_FIELDS))
    def test_each_missing_field_keeps_the_gate_closed(self, field):
        cap = _capture()
        cap.pop(field)
        assert canvas.folder_create_capability_state(
            cap, reviewed=True)["enabled"] is False

    def test_body_type_key_may_be_an_empty_string(self):
        cap = _capture(body_type_key="")
        assert canvas.validate_folder_create_capture(cap) == []
        assert canvas.folder_create_capability_state(
            cap, reviewed=True)["enabled"] is True

    def test_readback_keys_must_carry_the_response_id_field(self):
        cap = _capture(readback_keys=["name", "locationId"])
        problems = canvas.validate_folder_create_capture(cap)
        assert any("response_id_field" in p for p in problems)

    def test_capture_checklist_covers_every_required_field(self):
        names = [f["name"] for f in
                 canvas.folder_create_capture_checklist()["fields"]]
        assert names == list(canvas.FOLDER_CREATE_REQUIRED_CAPTURE_FIELDS)

    def test_unreadable_capture_path_is_capture_required(self, tmp_path):
        with pytest.raises(canvas.CaptureRequired):
            canvas.load_folder_create_capture(str(tmp_path / "absent.json"))

    def test_a_capture_file_round_trips_through_the_loader(self, tmp_path):
        p = tmp_path / "capture.json"
        p.write_text(json.dumps(_capture()), encoding="utf-8")
        assert canvas.load_folder_create_capture(str(p))["create_path"] == (
            "/funnels/funnel/folder/create"
        )

    def test_a_fixture_file_is_refused_by_the_loader(self, tmp_path):
        p = tmp_path / "fixture.json"
        p.write_text(json.dumps(canvas.OFFLINE_FOLDER_CAPTURE), encoding="utf-8")
        with pytest.raises(canvas.CaptureRequired, match="synthetic"):
            canvas.load_folder_create_capture(str(p))


# ── 3. Refusal paths ────────────────────────────────────────────────────────

class TestRefusals:
    def test_a_funnel_capture_cannot_create_a_website_folder(self):
        with pytest.raises(canvas.FolderCreateRefused, match="type scope"):
            canvas.folder_create_body(LOC, "ZHC A", "website",
                                      capture=_capture(), reviewed=True)

    def test_a_capture_authorizes_only_its_own_location(self):
        with pytest.raises(canvas.FolderCreateRefused, match="location"):
            canvas.folder_create_body(OTHER_LOC, "ZHC A", "funnel",
                                      capture=_capture(), reviewed=True)

    def test_ambiguous_folder_name_refuses_to_guess(self):
        rows = [_folder_row("f1", "ZHC Dup"), _folder_row("f2", "ZHC Dup")]
        r = ro.reconcile(rows, kind=ro.KIND_FUNNEL_FOLDER, location_id=LOC,
                         name="ZHC Dup")
        assert r.action == ro.REFUSE_AMBIGUOUS
        assert sorted(r.candidates) == ["f1", "f2"]

    def test_a_website_folder_never_satisfies_a_funnel_folder_request(self):
        r = ro.reconcile([_folder_row("wf1", "ZHC One", type_="website")],
                         kind=ro.KIND_FUNNEL_FOLDER, location_id=LOC,
                         name="ZHC One")
        assert r.action == ro.CREATE, "a different type scope is not a match"

    def test_an_incomplete_read_never_licenses_a_create(self):
        r = ro.reconcile([], kind=ro.KIND_FUNNEL_FOLDER, location_id=LOC,
                         name="ZHC New", read_complete=False)
        assert r.action == ro.REFUSE_UNPROVEN_READ

    def test_a_folder_capture_cannot_be_used_for_a_funnel(self):
        with pytest.raises(ro.ContractError, match="not a folder kind"):
            ro.folder_create_recipe_contract(
                ro.KIND_FUNNEL, location_id=LOC, capture=_capture(),
                reviewed=True, scoped_approval="APPROVED-test")

    def test_the_contract_refuses_a_capture_from_the_other_type_scope(self):
        with pytest.raises(ro.ContractError, match="type scope"):
            ro.folder_create_recipe_contract(
                ro.KIND_WEBSITE_FOLDER, location_id=LOC,
                capture=_capture(), reviewed=True,
                scoped_approval="APPROVED-test")


# ── 4. The recipe contract is disabled while the gate is closed ─────────────

class TestFolderRecipeContract:
    def test_no_capture_makes_the_contract_disabled(self):
        c = ro.folder_create_recipe_contract(
            ro.KIND_FUNNEL_FOLDER, location_id=LOC,
            scoped_approval="APPROVED-test")
        assert c.execution_mode == "disabled"
        with pytest.raises(ro.ContractError):
            c.validate()

    def test_an_unreviewed_capture_also_leaves_it_disabled(self):
        c = ro.folder_create_recipe_contract(
            ro.KIND_FUNNEL_FOLDER, location_id=LOC, capture=_capture(),
            scoped_approval="APPROVED-test")
        assert c.execution_mode == "disabled"

    def test_a_reviewed_matching_capture_makes_it_runnable(self):
        c = ro.folder_create_recipe_contract(
            ro.KIND_FUNNEL_FOLDER, location_id=LOC, capture=_capture(),
            reviewed=True, scoped_approval="APPROVED-test")
        assert c.execution_mode == "rest_in_browser"
        c.validate()

    def test_website_folder_contract_is_runnable_on_its_own_capture(self):
        c = ro.folder_create_recipe_contract(
            ro.KIND_WEBSITE_FOLDER, location_id=LOC, capture=_web_capture(),
            reviewed=True, scoped_approval="APPROVED-test")
        c.validate()
        assert c.object_kind == ro.KIND_WEBSITE_FOLDER

    def test_the_gate_state_is_reported_as_plain_data(self):
        state = ro.folder_create_gate_state(_capture(), reviewed=True)
        assert state["enabled"] is True
        assert state["folder_type"] == "funnel"


# ── 5. Two-run idempotency through the runner ───────────────────────────────

class TestFolderTwoRunIdempotency:
    def _harness(self, kind=ro.KIND_FUNNEL_FOLDER, capture=None,
                 reviewed=False, loc=LOC, name="ZHC Idem"):
        state = {"store": {}, "creates": [], "reads": []}

        def inventory():
            return {"rows": list(state["store"].values()), "complete": True}

        def create(payload):
            state["creates"].append(payload)
            return {"id": f"folder-{len(state['creates'])}"}

        def readback(native_id):
            state["reads"].append(native_id)
            row = {"id": native_id, "name": name, "locationId": loc,
                   "type": ro.schema_for(kind).platform_type}
            state["store"][native_id] = row
            return row

        kwargs = dict(
            location_id=loc, name=name, capture=capture, reviewed=reviewed,
            scoped_approval="APPROVED-test", inventory=inventory,
            create=create, readback=readback, authenticate=lambda: loc,
            acquire_lease=lambda: "lease", release_lease=lambda _l: None,
            recipe_id="folder-idem",
        )
        return kind, kwargs, state

    def test_first_run_creates_then_second_run_reuses_the_same_native_id(self):
        kind, kwargs, state = self._harness(capture=_capture(), reviewed=True)
        first = rr.run_folder_recipe(kind, **kwargs)
        second = rr.run_folder_recipe(kind, **kwargs)
        assert first.outcome == rr.OK_CREATED
        assert second.outcome == rr.OK_REUSED
        assert second.native_id == first.native_id
        assert len(state["creates"]) == 1, "B17: second run duplicated the folder"

    def test_reuse_needs_no_capture_at_all(self):
        """Proving an EXISTING folder uses the captured list route, not the
        gated create — so a closed gate must still reuse."""
        kind, kwargs, state = self._harness(capture=_capture(), reviewed=True)
        first = rr.run_folder_recipe(kind, **kwargs)
        closed = dict(kwargs, capture=None, reviewed=False)
        again = rr.run_folder_recipe(kind, **closed)
        assert again.outcome == rr.OK_REUSED
        assert again.native_id == first.native_id
        assert len(state["creates"]) == 1

    def test_closed_gate_refuses_the_create_and_writes_nothing(self):
        kind, kwargs, state = self._harness()
        run = rr.run_folder_recipe(kind, **kwargs)
        assert run.outcome == rr.REFUSED
        assert state["creates"] == []
        assert canvas.FOLDER_CREATE_PENDING in run.error

    def test_website_folder_recipe_is_also_idempotent(self):
        kind, kwargs, state = self._harness(
            kind=ro.KIND_WEBSITE_FOLDER, capture=_web_capture(), reviewed=True,
            name="ZHC Site")
        rr.run_folder_recipe(kind, **kwargs)
        second = rr.run_folder_recipe(kind, **kwargs)
        assert second.outcome == rr.OK_REUSED
        assert len(state["creates"]) == 1

    def test_the_create_body_reaches_the_rail_shaped_from_the_capture(self):
        cap = _capture(body_location_key="locId", body_name_key="title")
        kind, kwargs, state = self._harness(capture=cap, reviewed=True)
        rr.run_folder_recipe(kind, **kwargs)
        assert state["creates"][0] == {"locId": LOC, "title": "ZHC Idem",
                                       "type": "funnel"}

    def test_a_wrong_authenticated_location_refuses_before_any_write(self):
        kind, kwargs, state = self._harness(capture=_capture(), reviewed=True)
        kwargs["authenticate"] = lambda: OTHER_LOC
        run = rr.run_folder_recipe(kind, **kwargs)
        assert run.outcome == rr.REFUSED
        assert state["creates"] == []

    def test_the_shipped_fixture_cannot_open_the_runner_gate(self):
        kind, kwargs, state = self._harness(
            capture=dict(canvas.OFFLINE_FOLDER_CAPTURE), reviewed=True)
        with pytest.raises(canvas.CaptureRequired, match="synthetic"):
            rr.run_folder_recipe(kind, **kwargs)
        assert state["creates"] == []

    def test_an_ambiguous_existing_name_refuses_even_with_an_open_gate(self):
        kind, kwargs, state = self._harness(capture=_capture(), reviewed=True)
        state["store"] = {
            "f1": _folder_row("f1", "ZHC Idem"),
            "f2": _folder_row("f2", "ZHC Idem"),
        }
        run = rr.run_folder_recipe(kind, **kwargs)
        assert run.outcome == rr.REFUSED
        assert run.action == ro.REFUSE_AMBIGUOUS
        assert state["creates"] == []
