"""Offline tests for Skill 06 v3.0 P5 (C6, B06-B10, B17-B18): funnel / folder /
website / step / page recipe identities, idempotency, readback and the
disabled native split-test capability.

MOCK-ONLY: no network, no browser, no live GoHighLevel, no credentials. Every
"live" collaborator is an injected fake; every id is a synthetic fixture value.
No client or operator data appears anywhere in this file.

C6 acceptance lines, each with the test that proves it:
  * folder/funnel/website/step/page identities distinct  -> TestKindSeparation
  * scoped IDs + persistence                             -> TestScopedIdentity,
                                                            TestReadback
  * second run no duplicate (B17)                        -> TestTwoRunIdempotency
  * unchanged control variant (B10)                      -> TestVariantDisabled
  * no publish / traffic changes                         -> TestNoPublication
  * wrong-parent + name-collision refusal (B09)          -> TestReconciliation
  * llm_calls_during_recipe == 0 (B18)                   -> TestNoLlmInRecipe

Run:
    python3 -m pytest tests/test_ghl_recipe_objects_p5.py -v
"""
from __future__ import annotations

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
import ghl_split_variant as sv  # noqa: E402

LOC = "loc-fixture-0001"
OTHER_LOC = "loc-fixture-0002"


def _funnel_row(fid="funnel-1", name="ZHC One", parent="", loc=LOC, **kw):
    row = {"id": fid, "name": name, "locationId": loc, "type": "funnel",
           "parentId": parent}
    row.update(kw)
    return row


def _website_row(wid="site-1", name="ZHC One", parent="", loc=LOC, **kw):
    row = {"id": wid, "name": name, "locationId": loc, "type": "website",
           "parentId": parent}
    row.update(kw)
    return row


def _folder_row(fid="folder-1", name="ZHC One", loc=LOC, type_="funnel", **kw):
    row = {"id": fid, "name": name, "locationId": loc, "type": type_}
    row.update(kw)
    return row


# ── Identity separation (a funnel folder is not a website folder) ────────────

class TestKindSeparation:
    def test_all_six_kinds_are_declared_and_distinct(self):
        assert set(ro.ALL_KINDS) == {
            "funnel_folder", "website_folder", "funnel", "website",
            "step", "page", "variant",
        }
        assert len(set(ro.ALL_KINDS)) == len(ro.ALL_KINDS)

    def test_funnel_folder_and_website_folder_differ_in_platform_type(self):
        ff = ro.schema_for(ro.KIND_FUNNEL_FOLDER)
        wf = ro.schema_for(ro.KIND_WEBSITE_FOLDER)
        assert ff.platform_type == "funnel"
        assert wf.platform_type == "website"
        assert ff.kind != wf.kind

    def test_funnel_and_website_are_distinct_kinds_with_same_route_family(self):
        fn = ro.schema_for(ro.KIND_FUNNEL)
        wb = ro.schema_for(ro.KIND_WEBSITE)
        assert fn.platform_type != wb.platform_type
        # Both live on /funnels/* — the route does NOT distinguish them; the
        # `type` field does. This is the conflation the module exists to stop.
        assert "funnels" in fn.list_route and "funnels" in wb.list_route

    def test_website_row_never_satisfies_a_funnel_request(self):
        result = ro.reconcile([_website_row(name="ZHC One")],
                              kind=ro.KIND_FUNNEL, location_id=LOC,
                              name="ZHC One")
        assert result.action == ro.CREATE

    def test_funnel_row_never_satisfies_a_website_request(self):
        result = ro.reconcile([_funnel_row(name="ZHC One")],
                              kind=ro.KIND_WEBSITE, location_id=LOC,
                              name="ZHC One")
        assert result.action == ro.CREATE

    def test_funnel_folder_row_never_satisfies_a_website_folder_request(self):
        result = ro.reconcile(
            [_folder_row(name="ZHC One", type_="funnel")],
            kind=ro.KIND_WEBSITE_FOLDER, location_id=LOC, name="ZHC One",
        )
        assert result.action == ro.CREATE

    def test_unknown_kind_raises_rather_than_defaulting(self):
        with pytest.raises(KeyError):
            ro.schema_for("funnel_ish")

    def test_variant_kind_is_declared_pending(self):
        schema = ro.schema_for(ro.KIND_VARIANT)
        assert schema.ui_baseline_status == ro.BASELINE_PENDING
        assert "NONE CAPTURED" in schema.list_route


# ── Scoped identity ─────────────────────────────────────────────────────────

class TestScopedIdentity:
    def test_identity_key_is_kind_id_location_parent(self):
        ident = ro.build_identity(ro.KIND_FUNNEL, "funnel-1", LOC, "folder-1",
                                  parent_kind=ro.KIND_FUNNEL_FOLDER)
        assert ident.key() == ("funnel", "funnel-1", LOC, "folder-1")
        assert ident.as_dict()["parent_id"] == "folder-1"

    def test_same_name_different_parent_is_a_different_identity(self):
        a = ro.build_identity(ro.KIND_FUNNEL, "funnel-1", LOC, "folder-1",
                              parent_kind=ro.KIND_FUNNEL_FOLDER)
        b = ro.build_identity(ro.KIND_FUNNEL, "funnel-2", LOC, "folder-2",
                              parent_kind=ro.KIND_FUNNEL_FOLDER)
        assert a.key() != b.key()

    def test_blank_native_id_is_refused(self):
        with pytest.raises(ro.IdentityError):
            ro.build_identity(ro.KIND_FUNNEL, "", LOC)

    def test_blank_location_is_refused(self):
        with pytest.raises(ro.IdentityError):
            ro.build_identity(ro.KIND_FUNNEL, "funnel-1", "   ")

    def test_parent_required_for_a_step(self):
        with pytest.raises(ro.IdentityError):
            ro.build_identity(ro.KIND_STEP, "step-1", LOC)

    def test_folder_kind_may_hang_at_the_location_root(self):
        ident = ro.build_identity(ro.KIND_FUNNEL_FOLDER, "folder-1", LOC)
        assert ident.parent_id == ""

    def test_wrong_parent_kind_is_refused_at_identity_time(self):
        # A funnel may not hang under a website folder.
        with pytest.raises(ro.IdentityError) as exc:
            ro.build_identity(ro.KIND_FUNNEL, "funnel-1", LOC, "site-folder-1",
                              parent_kind=ro.KIND_WEBSITE_FOLDER)
        assert "website_folder" in str(exc.value)

    def test_variant_may_only_hang_under_a_step(self):
        assert ro.schema_for(ro.KIND_VARIANT).parent_kinds == ("step",)
        with pytest.raises(ro.IdentityError):
            ro.build_identity(ro.KIND_VARIANT, "v-1", LOC, "funnel-1",
                              parent_kind=ro.KIND_FUNNEL)


# ── Reconciliation: reuse / create / refuse ─────────────────────────────────

class TestReconciliation:
    def test_native_id_match_in_scope_reuses(self):
        r = ro.reconcile([_funnel_row()], kind=ro.KIND_FUNNEL,
                         location_id=LOC, native_id="funnel-1")
        assert r.action == ro.REUSE
        assert r.identity.native_id == "funnel-1"

    def test_native_id_match_in_another_location_refuses_wrong_scope(self):
        r = ro.reconcile([_funnel_row(loc=OTHER_LOC)], kind=ro.KIND_FUNNEL,
                         location_id=LOC, native_id="funnel-1")
        assert r.action == ro.REFUSE_WRONG_SCOPE
        assert "different scope" in r.reason

    def test_native_id_match_under_another_parent_refuses_wrong_scope(self):
        r = ro.reconcile([_funnel_row(parent="folder-other")],
                         kind=ro.KIND_FUNNEL, location_id=LOC,
                         parent_id="folder-1", native_id="funnel-1")
        assert r.action == ro.REFUSE_WRONG_SCOPE

    def test_unique_name_in_scope_reuses(self):
        r = ro.reconcile([_funnel_row()], kind=ro.KIND_FUNNEL,
                         location_id=LOC, name="ZHC One")
        assert r.action == ro.REUSE

    def test_two_same_name_rows_in_scope_refuse_ambiguous(self):
        rows = [_funnel_row(fid="funnel-1"), _funnel_row(fid="funnel-2")]
        r = ro.reconcile(rows, kind=ro.KIND_FUNNEL, location_id=LOC,
                         name="ZHC One")
        assert r.action == ro.REFUSE_AMBIGUOUS
        assert set(r.candidates) == {"funnel-1", "funnel-2"}

    def test_name_collision_elsewhere_refuses_b09(self):
        """B09: a same-name object in ANOTHER parent is a different object.
        It is never adopted and never overwritten."""
        rows = [_funnel_row(parent="folder-other", name="ZHC One")]
        r = ro.reconcile(rows, kind=ro.KIND_FUNNEL, location_id=LOC,
                         parent_id="folder-1", name="ZHC One")
        assert r.action == ro.REFUSE_COLLISION
        assert "OUTSIDE" in r.reason

    def test_name_collision_in_another_location_refuses_b09(self):
        rows = [_funnel_row(loc=OTHER_LOC, name="ZHC One")]
        r = ro.reconcile(rows, kind=ro.KIND_FUNNEL, location_id=LOC,
                         name="ZHC One")
        assert r.action == ro.REFUSE_COLLISION

    def test_uncertain_prior_attempt_refuses_contradiction(self):
        """Recorded id gone, name taken by a DIFFERENT id in the same scope:
        the prior attempt is uncertain. Reconcile by hand, never retry (B07)."""
        rows = [_funnel_row(fid="funnel-other", name="ZHC One")]
        r = ro.reconcile(rows, kind=ro.KIND_FUNNEL, location_id=LOC,
                         native_id="funnel-1", name="ZHC One")
        assert r.action == ro.REFUSE_CONTRADICTION
        assert "reconcile" in r.reason.lower()

    def test_incomplete_read_never_licenses_a_create(self):
        r = ro.reconcile([], kind=ro.KIND_FUNNEL, location_id=LOC,
                         name="ZHC New", read_complete=False)
        assert r.action == ro.REFUSE_UNPROVEN_READ

    def test_no_identity_at_all_refuses(self):
        r = ro.reconcile([], kind=ro.KIND_FUNNEL, location_id=LOC)
        assert r.action == ro.REFUSE_CONTRADICTION

    def test_absence_in_a_complete_read_creates(self):
        r = ro.reconcile([_funnel_row(name="ZHC Other")], kind=ro.KIND_FUNNEL,
                         location_id=LOC, name="ZHC New")
        assert r.action == ro.CREATE

    def test_step_requires_a_parent_before_any_decision(self):
        r = ro.reconcile([], kind=ro.KIND_STEP, location_id=LOC, name="Opt-in")
        assert r.action == ro.REFUSE_WRONG_SCOPE

    def test_assert_admissible_raises_for_every_refusal(self):
        for action in ro.REFUSALS:
            with pytest.raises(ro.RecipeRefusal):
                ro.assert_admissible(ro.ReconcileResult(action, reason="x"))

    def test_assert_admissible_passes_reuse_and_create(self):
        for action in (ro.REUSE, ro.CREATE):
            assert ro.assert_admissible(
                ro.ReconcileResult(action)).action == action


# ── Readback: native id + saved state on every create ───────────────────────

class TestReadback:
    def test_page_id_comes_from_the_captured_create_step_shape(self):
        response = {"page": {"_ref": {"_path": {"segments":
                                                ["funnel_pages", "page-99"]}}}}
        assert ro.extract_native_id(ro.KIND_PAGE, response) == "page-99"

    def test_page_id_falls_back_to_inline_id(self):
        assert ro.extract_native_id(
            ro.KIND_PAGE, {"page": {"_id": "page-inline"}}) == "page-inline"

    def test_page_id_absent_raises_not_guesses(self):
        with pytest.raises(ro.ReadbackIncomplete):
            ro.extract_native_id(ro.KIND_PAGE, {"page": {"name": "Untitled"}})

    def test_funnel_id_read_from_the_create_response(self):
        assert ro.extract_native_id(ro.KIND_FUNNEL,
                                    {"id": "funnel-1"}) == "funnel-1"

    def test_readback_proves_id_location_parent_and_saved_state(self):
        native = ro.assert_readback(
            ro.KIND_FUNNEL, {"id": "funnel-1"},
            {"id": "funnel-1", "locationId": LOC, "parentId": "folder-1",
             "name": "ZHC One", "steps": []},
            location_id=LOC, parent_id="folder-1",
            saved_state_keys=("name", "steps"),
        )
        assert native == "funnel-1"

    def test_readback_id_mismatch_fails(self):
        with pytest.raises(ro.ReadbackIncomplete):
            ro.assert_readback(ro.KIND_FUNNEL, {"id": "funnel-1"},
                               {"id": "funnel-2", "locationId": LOC},
                               location_id=LOC)

    def test_readback_wrong_location_fails(self):
        with pytest.raises(ro.ReadbackIncomplete):
            ro.assert_readback(ro.KIND_FUNNEL, {"id": "funnel-1"},
                               {"id": "funnel-1", "locationId": OTHER_LOC},
                               location_id=LOC)

    def test_readback_wrong_parent_fails(self):
        with pytest.raises(ro.ReadbackIncomplete) as exc:
            ro.assert_readback(
                ro.KIND_FUNNEL, {"id": "funnel-1"},
                {"id": "funnel-1", "locationId": LOC, "parentId": "folder-2"},
                location_id=LOC, parent_id="folder-1")
        assert "wrong-parent" in str(exc.value)

    def test_readback_missing_saved_state_key_fails(self):
        with pytest.raises(ro.ReadbackIncomplete):
            ro.assert_readback(
                ro.KIND_FUNNEL, {"id": "funnel-1"},
                {"id": "funnel-1", "locationId": LOC},
                location_id=LOC, saved_state_keys=("name",))

    def test_readback_with_no_read_supplied_fails(self):
        with pytest.raises(ro.ReadbackIncomplete):
            ro.assert_readback(ro.KIND_FUNNEL, {"id": "funnel-1"}, {},
                               location_id=LOC)


# ── Publication + traffic gating ────────────────────────────────────────────

class TestNoPublication:
    def test_draft_payload_passes(self):
        ro.assert_no_publication({"pageType": "draft", "manualSave": True})

    def test_published_payload_is_refused(self):
        with pytest.raises(ro.PublicationRefused):
            ro.assert_no_publication({"pageType": "published"})

    def test_publish_true_is_refused(self):
        with pytest.raises(ro.PublicationRefused):
            ro.assert_no_publication({"publish": True})

    @pytest.mark.parametrize("key", ["traffic", "control_traffic", "split"])
    def test_traffic_keys_are_refused(self, key):
        with pytest.raises(ro.PublicationRefused):
            ro.assert_no_publication({key: 50})


# ── B18: zero LLM calls inside the recipe loop ──────────────────────────────

class TestNoLlmInRecipe:
    def test_fresh_guard_reports_zero(self):
        assert ro.LlmCallGuard("r").assert_zero() == 0

    def test_any_recorded_call_raises(self):
        guard = ro.LlmCallGuard("r")
        guard.record("click", "Create")
        with pytest.raises(ro.RecipeLlmCallViolation) as exc:
            guard.assert_zero()
        assert "llm_calls_during_recipe=1" in str(exc.value)

    def test_runner_reports_zero_calls_on_a_clean_run(self):
        run = self._run()
        assert run.llm_calls_during_recipe == 0

    def test_runner_propagates_a_violating_guard_count(self):
        guard = ro.LlmCallGuard("r")
        guard.record("fill", "name")
        run = self._run(llm_guard=guard)
        assert run.llm_calls_during_recipe == 1

    def _run(self, llm_guard=None):
        contract = self._contract()
        return rr.run_recipe(
            contract,
            inputs={"name": "ZHC T", "slug": "t"},
            inventory=lambda: {"rows": [], "complete": True},
            create=lambda p: {"id": "funnel-1"},
            readback=lambda i: {"id": i, "locationId": LOC,
                                "parentId": "folder-1"},
            payload={"locationId": LOC, "pageType": "draft"},
            llm_guard=llm_guard,
        )

    @staticmethod
    def _contract():
        return ro.recipe_contract_for(
            ro.KIND_FUNNEL, location_id=LOC, parent_id="folder-1",
            parent_kind=ro.KIND_FUNNEL_FOLDER,
            scoped_approval="APPROVED-test")


# ── Two-run idempotency (B17) through the ordered runner ───────────────────

class TestTwoRunIdempotency:
    def _harness(self, kind=ro.KIND_FUNNEL, parent="folder-1",
                 parent_kind=ro.KIND_FUNNEL_FOLDER, name="ZHC Idem"):
        state = {"store": {}, "creates": [], "reads": [], "releases": []}

        def inventory():
            return {"rows": list(state["store"].values()), "complete": True}

        def create(payload):
            state["creates"].append(payload)
            return {"id": f"obj-{len(state['creates'])}"}

        def readback(native_id):
            state["reads"].append(native_id)
            row = {"id": native_id, "name": name, "locationId": LOC,
                   "parentId": parent, "type": ro.schema_for(kind).platform_type}
            state["store"][native_id] = row
            return row

        contract = ro.recipe_contract_for(
            kind, location_id=LOC, parent_id=parent, parent_kind=parent_kind,
            scoped_approval="APPROVED-test")
        kwargs = dict(
            inputs={"name": name, "slug": "idem"},
            inventory=inventory, create=create, readback=readback,
            authenticate=lambda: LOC,
            acquire_lease=lambda: "lease",
            release_lease=state["releases"].append,
            payload={"locationId": LOC, "name": name, "pageType": "draft"},
            saved_state_keys=("name",),
            recipe_id="idem-test",
        )
        return contract, kwargs, state

    def test_second_run_reuses_and_does_not_duplicate(self):
        contract, kwargs, state = self._harness()
        first = rr.run_recipe(contract, **kwargs)
        second = rr.run_recipe(contract, **kwargs)
        assert first.outcome == rr.OK_CREATED
        assert second.outcome == rr.OK_REUSED
        assert len(state["creates"]) == 1, "B17: second run duplicated the object"
        assert second.native_id == first.native_id

    def test_second_run_makes_no_create_call_and_no_read(self):
        contract, kwargs, state = self._harness()
        rr.run_recipe(contract, **kwargs)
        reads_after_first = len(state["reads"])
        rr.run_recipe(contract, **kwargs)
        assert len(state["reads"]) == reads_after_first

    def test_three_runs_still_one_object(self):
        contract, kwargs, state = self._harness()
        for _ in range(3):
            rr.run_recipe(contract, **kwargs)
        assert len(state["creates"]) == 1
        assert len(state["store"]) == 1

    def test_website_recipe_also_idempotent(self):
        contract, kwargs, state = self._harness(
            kind=ro.KIND_WEBSITE, parent="site-folder-1",
            parent_kind=ro.KIND_WEBSITE_FOLDER, name="ZHC Site")
        rr.run_recipe(contract, **kwargs)
        second = rr.run_recipe(contract, **kwargs)
        assert second.outcome == rr.OK_REUSED
        assert len(state["creates"]) == 1

    def test_folder_recipe_is_idempotent_at_the_root(self):
        contract, kwargs, state = self._harness(
            kind=ro.KIND_FUNNEL_FOLDER, parent="", parent_kind="",
            name="ZHC Folder")
        rr.run_recipe(contract, **kwargs)
        second = rr.run_recipe(contract, **kwargs)
        assert second.outcome == rr.OK_REUSED
        assert len(state["creates"]) == 1

    def test_resume_with_a_recorded_native_id_reuses_without_creating(self):
        """B07: a resumed run passes the id it already recorded; the object is
        proven, not re-created."""
        contract, kwargs, state = self._harness(name="ZHC Resume")
        first = rr.run_recipe(contract, **kwargs)
        resumed = dict(kwargs)
        resumed["inputs"] = {"name": "ZHC Resume", "slug": "idem",
                             "native_id": first.native_id}
        again = rr.run_recipe(contract, **resumed)
        assert again.outcome == rr.OK_REUSED
        assert again.native_id == first.native_id
        assert len(state["creates"]) == 1

    def test_resume_with_a_stale_native_id_refuses_when_name_is_taken(self):
        """A recorded id that no longer exists while its name is taken by a
        different object is an uncertain prior attempt: refuse, do not retry."""
        contract, kwargs, state = self._harness(name="ZHC Stale")
        rr.run_recipe(contract, **kwargs)
        stale = dict(kwargs)
        stale["inputs"] = {"name": "ZHC Stale", "slug": "idem",
                           "native_id": "obj-gone"}
        again = rr.run_recipe(contract, **stale)
        assert again.outcome == rr.REFUSED
        assert len(state["creates"]) == 1


# ── Runner sequence: ordering, refusal, unconditional release ───────────────

class TestRunnerSequence:
    def _contract(self, **kw):
        base = dict(location_id=LOC, parent_id="folder-1",
                    parent_kind=ro.KIND_FUNNEL_FOLDER,
                    scoped_approval="APPROVED-test")
        base.update(kw)
        return ro.recipe_contract_for(ro.KIND_FUNNEL, **base)

    def test_happy_path_runs_the_declared_sequence_in_order(self):
        released = []
        run = rr.run_recipe(
            self._contract(),
            inputs={"name": "ZHC S", "slug": "s"},
            inventory=lambda: {"rows": [], "complete": True},
            create=lambda p: {"id": "funnel-1"},
            readback=lambda i: {"id": i, "locationId": LOC,
                                "parentId": "folder-1"},
            authenticate=lambda: LOC,
            acquire_lease=lambda: "lease",
            release_lease=released.append,
            payload={"locationId": LOC, "pageType": "draft"},
            recipe_id="seq",
        )
        assert run.outcome == rr.OK_CREATED
        assert run.steps == ["validate_request", "assert_no_publication",
                             "admission", "browser_lease",
                             "authenticate_and_verify_location", "reconcile",
                             "execute", "readback", "verify", "release"]
        assert run.released is True
        assert released == ["lease"]

    def test_verify_failure_refuses_and_does_not_report_created(self):
        run = rr.run_recipe(
            self._contract(),
            inputs={"name": "ZHC S", "slug": "s"},
            inventory=lambda: {"rows": [], "complete": True},
            create=lambda p: {"id": "funnel-1"},
            readback=lambda i: {"id": i, "locationId": LOC,
                                "parentId": "folder-1"},
            verify=lambda i, r: {"ok": False, "reason": "preview broken"},
            payload={"locationId": LOC, "pageType": "draft"},
        )
        assert run.outcome == rr.REFUSED
        assert "canonical verification" in run.error

    def test_wrong_authenticated_location_refuses_before_write(self):
        creates = []
        run = rr.run_recipe(
            self._contract(),
            inputs={"name": "ZHC S", "slug": "s"},
            inventory=lambda: {"rows": [], "complete": True},
            create=lambda p: creates.append(p) or {"id": "funnel-1"},
            readback=lambda i: {"id": i, "locationId": LOC},
            authenticate=lambda: OTHER_LOC,
            payload={"locationId": LOC, "pageType": "draft"},
        )
        assert run.outcome == rr.REFUSED
        assert creates == [], "no write may happen under a wrong location"
        assert run.steps == ["validate_request", "assert_no_publication",
                             "admission", "browser_lease", "release"]

    def test_publishing_payload_refuses_before_any_collaborator(self):
        called = []
        run = rr.run_recipe(
            self._contract(),
            inputs={"name": "ZHC S", "slug": "s"},
            inventory=lambda: called.append("inv") or {"rows": [], "complete": True},
            create=lambda p: called.append("create") or {"id": "x"},
            readback=lambda i: {"id": i},
            payload={"locationId": LOC, "pageType": "published"},
        )
        assert run.outcome == rr.REFUSED
        assert called == []

    def test_lease_is_released_on_a_create_exception(self):
        released = []

        def boom(_payload):
            raise RuntimeError("rail down")

        run = rr.run_recipe(
            self._contract(),
            inputs={"name": "ZHC S", "slug": "s"},
            inventory=lambda: {"rows": [], "complete": True},
            create=boom,
            readback=lambda i: {"id": i},
            acquire_lease=lambda: "lease",
            release_lease=released.append,
            payload={"locationId": LOC, "pageType": "draft"},
        )
        assert run.outcome == rr.FAILED
        assert released == ["lease"]
        assert run.released is True

    def test_disabled_contract_never_reaches_admission(self):
        adm = []
        contract = ro.recipe_contract_for(
            ro.KIND_VARIANT, location_id=LOC, parent_id="step-1",
            parent_kind=ro.KIND_STEP, scoped_approval="APPROVED-test")
        assert contract.execution_mode == "disabled"
        run = rr.run_recipe(
            contract,
            inputs={"name": "v", "slug": "v"},
            inventory=lambda: {"rows": [], "complete": True},
            create=lambda p: {"id": "v"},
            readback=lambda i: {"id": i},
            admit=lambda: adm.append("admit"),
        )
        assert run.outcome == rr.REFUSED
        assert adm == []

    def test_undeclared_input_key_is_refused(self):
        run = rr.run_recipe(
            self._contract(),
            inputs={"name": "ZHC S", "slug": "s", "publish": True},
            inventory=lambda: {"rows": [], "complete": True},
            create=lambda p: {"id": "funnel-1"},
            readback=lambda i: {"id": i, "locationId": LOC},
            payload={"locationId": LOC, "pageType": "draft"},
        )
        assert run.outcome == rr.REFUSED
        assert "undeclared" in run.error


# ── Contract declaration ────────────────────────────────────────────────────

class TestRecipeContract:
    def test_contract_requires_a_parent_for_a_step(self):
        with pytest.raises(ro.ContractError):
            ro.recipe_contract_for(ro.KIND_STEP, location_id=LOC).validate()

    def test_contract_refuses_a_wrong_parent_kind(self):
        with pytest.raises(ro.ContractError):
            ro.recipe_contract_for(
                ro.KIND_FUNNEL, location_id=LOC, parent_id="sf-1",
                parent_kind=ro.KIND_WEBSITE_FOLDER,
                scoped_approval="APPROVED-test").validate()

    def test_bare_name_idempotency_key_is_refused(self):
        c = ro.recipe_contract_for(
            ro.KIND_FUNNEL, location_id=LOC, parent_id="folder-1",
            parent_kind=ro.KIND_FUNNEL_FOLDER, scoped_approval="APPROVED-test")
        c.idempotency_key = "name"
        with pytest.raises(ro.ContractError):
            c.validate()

    def test_unset_scoped_approval_is_refused(self):
        c = ro.recipe_contract_for(
            ro.KIND_FUNNEL, location_id=LOC, parent_id="folder-1",
            parent_kind=ro.KIND_FUNNEL_FOLDER)
        with pytest.raises(ro.ContractError):
            c.validate()

    def test_pending_capture_kind_cannot_validate_as_runnable(self):
        c = ro.recipe_contract_for(
            ro.KIND_VARIANT, location_id=LOC, parent_id="step-1",
            parent_kind=ro.KIND_STEP, scoped_approval="APPROVED-test")
        assert c.execution_mode == "disabled"
        with pytest.raises(ro.ContractError):
            c.validate()

    def test_folder_contract_declares_runtime_capture_not_locked(self):
        c = ro.recipe_contract_for(ro.KIND_FUNNEL_FOLDER, location_id=LOC,
                                   scoped_approval="APPROVED-test")
        assert c.expected_ui_baseline_status == ro.BASELINE_RUNTIME_CAPTURE
        assert "NOT captured" in c.expected_ui_baseline

    def test_every_kind_contract_validates_except_variant(self):
        for kind in ro.ALL_KINDS:
            schema = ro.schema_for(kind)
            non_root = [p for p in schema.parent_kinds if p]
            parent = non_root[0] if non_root else ""
            pid = "parent-1" if parent else ""
            c = ro.recipe_contract_for(kind, location_id=LOC, parent_id=pid,
                                       parent_kind=parent,
                                       scoped_approval="APPROVED-test")
            if kind == ro.KIND_VARIANT:
                with pytest.raises(ro.ContractError):
                    c.validate()
            else:
                assert c.validate() is c


# ── Native split-test variant: DISABLED, never a fake A/B ───────────────────

class TestVariantDisabled:
    def test_default_state_is_pending_capture_and_disabled(self):
        state = sv.capability_state()
        assert state["state"] == sv.PENDING_LIVE_SELECTOR_CAPTURE
        assert state["enabled"] is False
        assert sorted(state["missing_capture_fields"]) == \
            sorted(sv.REQUIRED_CAPTURE_FIELDS)

    def test_plan_variant_refuses_and_returns_no_payload(self):
        req = sv.VariantRequest(location_id=LOC, funnel_id="funnel-1",
                                step_id="step-1", name="B", slug="b")
        plan = sv.plan_variant(req)
        assert plan.enabled is False
        assert plan.request is None
        assert plan.state == sv.PENDING_LIVE_SELECTOR_CAPTURE

    def test_partial_capture_stays_pending(self):
        partial = {"location_id": LOC, "step_id": "step-1"}
        state = sv.capability_state(partial)
        assert state["state"] == sv.PENDING_LIVE_SELECTOR_CAPTURE
        assert "traffic_field" in state["missing_capture_fields"]

    def test_synthetic_shape_fixture_is_detected_and_refused(self):
        assert sv.is_synthetic_capture(sv.SYNTHETIC_COMPLETE_CAPTURE) is True
        req = sv.VariantRequest(location_id=LOC, funnel_id="funnel-1",
                                step_id="step-1", name="B", slug="b")
        with pytest.raises(sv.CaptureRequired):
            sv.plan_variant_from_real_capture(req, sv.SYNTHETIC_COMPLETE_CAPTURE)

    def test_two_disconnected_steps_are_refused_as_fake_ab(self):
        with pytest.raises(sv.VariantRefused) as exc:
            sv.assert_no_fake_ab(sv.SYNTHETIC_STEPS)
        assert sv.PENDING_LIVE_SELECTOR_CAPTURE in str(exc.value)

    def test_platform_linked_steps_pass_the_fake_ab_guard(self):
        sv.assert_no_fake_ab(sv.SYNTHETIC_STEPS_SPLIT)  # no raise

    def test_control_cannot_be_declared_by_a_recipe(self):
        with pytest.raises(sv.VariantRefused):
            sv.VariantRequest(location_id=LOC, funnel_id="f", step_id="s",
                              name="C", slug="c", is_control=True).validate()

    def test_control_identity_stability_is_a_required_capture_field(self):
        assert "control_id_before" in sv.REQUIRED_CAPTURE_FIELDS
        assert "control_id_after" in sv.REQUIRED_CAPTURE_FIELDS

    def test_traffic_weights_are_forbidden_until_captured(self):
        for key in ("split_percentage", "traffic_weight", "auto_promote"):
            assert key in sv.FORBIDDEN_UNTIL_CAPTURE

    def test_capture_complete_grants_review_not_execution(self):
        capture = {f: "observed" for f in sv.REQUIRED_CAPTURE_FIELDS}
        state = sv.capability_state(capture)
        assert state["state"] == sv.ENABLED_FOR_REVIEW
        assert state["enabled"] is False
