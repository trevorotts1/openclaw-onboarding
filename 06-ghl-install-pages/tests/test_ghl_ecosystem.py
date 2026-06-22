"""MOCK-only unit tests — ghl_ecosystem (T3 ecosystem build + form->CRM proof).

These tests are MOCK-ONLY. There are NO live GHL calls, no real fixture, no
agent-browser, no network of any kind. Every GHL operation is supplied as a
mock callable via ``EcosystemOps`` — the orchestrator and the form->CRM proof
are exercised entirely against in-memory fakes.

Coverage:
  * preflight env gate — passes for the fixture; REFUSES wrong location, empty
    whitelist, non-whitelisted target, missing PIT.
  * payload shapes — calendar/product/price/opt-in-form/opt-in-payload.
  * the form->CRM PROOF — the happy roundtrip AND every failure mode:
      - zero matches, multiple matches
      - missing/partial tags (a partial-tag contact is a FAIL)
      - re-GET id mismatch
      - after_count != before_count + 1
  * the full build_ecosystem sequence — real receipts written to a tmp run dir,
    aggregate summary derived strictly from per-step receipts, FAIL-loud on a
    failing proof, and the consistency guard (summary never more optimistic
    than the raw receipts).

No real client/operator names, emails, or location-ids appear beyond the
operator fixture id constant the module enforces.

Run:
    python3 -m pytest tests/test_ghl_ecosystem.py -v
"""
from __future__ import annotations

import json
import os
import sys

# Ensure ghl_ecosystem (and its siblings) are importable regardless of cwd —
# same convention as the other tests in this suite.
_TOOLS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "tools"))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import pytest

import ghl_ecosystem as eco


FIXTURE_LOC = eco.OPERATOR_FIXTURE_LOCATION_ID


# ── A fake CRM backing the injected ops (in-memory, deterministic) ────────────

class FakeCrm:
    """In-memory CRM that the EcosystemOps mocks drive. No network, no GHL.

    Models exactly what the proof reads: a contacts store keyed by id, a
    create-calendar/product/price/workflow that mint ids, an embed-form that
    succeeds, and a submit_optin that (by default) inserts the contact the way a
    real opt-in capture would.
    """

    def __init__(self, *, submit_inserts=True, tags_on_insert=None,
                 reread_wrong_id=False, double_insert=False):
        self.contacts = {}            # id -> contact dict
        self._seq = 0
        self.submit_inserts = submit_inserts
        self.tags_on_insert = (
            list(eco.WORKSHOP_TAGS) if tags_on_insert is None else list(tags_on_insert)
        )
        self.reread_wrong_id = reread_wrong_id
        self.double_insert = double_insert
        self.deleted = []
        self.calls = []

    def _next(self, prefix):
        self._seq += 1
        return f"{prefix}{self._seq:04d}"

    # ── ops wired into EcosystemOps ──
    def create_calendar(self, body):
        self.calls.append(("create_calendar", body))
        return {"calendar": {"id": self._next("CAL")}}

    def create_product(self, body):
        self.calls.append(("create_product", body))
        return {"product": {"_id": self._next("PROD")}}

    def create_price(self, product_id, body):
        self.calls.append(("create_price", product_id, body))
        return {"_id": self._next("PRICE")}

    def embed_optin_form(self, page_id, html, marker):
        self.calls.append(("embed_optin_form", page_id, marker))
        return {"ok": True, "page_id": page_id, "marker": marker, "http_status": 201}

    def count_contacts(self):
        return len(self.contacts)

    def submit_optin(self, payload):
        self.calls.append(("submit_optin", payload))
        if self.submit_inserts:
            self._insert(payload)
            if self.double_insert:
                self._insert(payload)  # simulate a duplicate-creating opt-in
        return {"ok": True}

    def _insert(self, payload):
        cid = self._next("CONT")
        self.contacts[cid] = {
            "id": cid,
            "email": payload["email"],
            "firstName": payload.get("firstName"),
            "tags": list(self.tags_on_insert),
        }
        return cid

    def search_contact_by_email(self, email):
        matches = [c for c in self.contacts.values()
                   if str(c.get("email", "")).lower() == email.lower()]
        return {"contacts": matches}

    def get_contact(self, contact_id):
        if self.reread_wrong_id:
            return {"contact": {"id": "SOMEOTHERID"}}
        c = self.contacts.get(contact_id)
        return {"contact": c} if c else {}

    def delete_contact(self, contact_id):
        self.deleted.append(contact_id)
        self.contacts.pop(contact_id, None)
        return {"ok": True, "status": "deleted"}

    def create_workflow(self, spec):
        self.calls.append(("create_workflow", spec))
        return {"workflow": {"id": self._next("WF")}}

    def read_workflow_triggers(self, wf_id):
        return {"triggers": [{"id": "TRIG1", "type": "contact_changed"}]}

    def ops(self):
        return eco.EcosystemOps(
            create_calendar=self.create_calendar,
            create_product=self.create_product,
            create_price=self.create_price,
            embed_optin_form=self.embed_optin_form,
            count_contacts=self.count_contacts,
            submit_optin=self.submit_optin,
            search_contact_by_email=self.search_contact_by_email,
            get_contact=self.get_contact,
            delete_contact=self.delete_contact,
            create_workflow=self.create_workflow,
            read_workflow_triggers=self.read_workflow_triggers,
        )


def _good_env():
    return {
        eco.ALLOWED_LOCATIONS_ENV: FIXTURE_LOC,
        "GHL_API_KEY": "fake-pit-token",
    }


def _spec(**kw):
    base = dict(
        location_id=FIXTURE_LOC,
        optin_page_id="PAGEID0000000000fake",
        optin_action_url="/forms/capture/x",
        optin_marker="zhc-optin-TESTMARK",
        workflow_spec={"name": "ZHC Workshop Registrant Nurture"},
    )
    base.update(kw)
    return eco.EcosystemSpec(**base)


# ── preflight ─────────────────────────────────────────────────────────────────

class TestPreflight:
    def test_passes_for_fixture(self):
        out = eco.preflight(FIXTURE_LOC, env=_good_env())
        assert out["target_location_id"] == FIXTURE_LOC
        assert out["allowed_contains_target"] is True
        assert out["pit_present"] is True
        # never leaks the token value
        assert "fake-pit-token" not in json.dumps(out)

    def test_refuses_non_fixture_location(self):
        env = {eco.ALLOWED_LOCATIONS_ENV: "OTHERLOC000000000000", "GHL_API_KEY": "x"}
        with pytest.raises(eco.EcosystemPreflightError, match="fixture"):
            eco.preflight("OTHERLOC000000000000", env=env)

    def test_refuses_empty_whitelist(self):
        with pytest.raises(eco.EcosystemPreflightError, match="empty"):
            eco.preflight(FIXTURE_LOC, env={"GHL_API_KEY": "x"})

    def test_refuses_target_not_in_whitelist(self):
        env = {eco.ALLOWED_LOCATIONS_ENV: "SOMEOTHERLOC00000000", "GHL_API_KEY": "x"}
        # target is the fixture but the whitelist doesn't contain it
        with pytest.raises(eco.EcosystemPreflightError):
            eco.preflight(FIXTURE_LOC, env=env)

    def test_refuses_missing_pit(self):
        with pytest.raises(eco.EcosystemPreflightError, match="PIT"):
            eco.preflight(FIXTURE_LOC, env={eco.ALLOWED_LOCATIONS_ENV: FIXTURE_LOC})


# ── payload shapes ──────────────────────────────────────────────────────────

class TestPayloadShapes:
    def test_calendar_body(self):
        b = eco.calendar_body(FIXTURE_LOC, "ZHC Cal", slot_duration=45,
                              team_member_ids=["U1", "U2"])
        assert b["locationId"] == FIXTURE_LOC
        assert b["slotDuration"] == 45
        assert b["teamMembers"] == [{"userId": "U1"}, {"userId": "U2"}]

    def test_product_body_alt_keys(self):
        b = eco.product_body(FIXTURE_LOC, "ZHC Seat", image_url="https://cdn/x.png")
        assert b["altId"] == FIXTURE_LOC and b["altType"] == "location"
        assert b["productType"] == "SERVICE"
        assert b["image"] == "https://cdn/x.png"

    def test_price_body_requires_positive_cents(self):
        with pytest.raises(ValueError):
            eco.price_body(FIXTURE_LOC, "PROD1", "Seat", 0)
        with pytest.raises(ValueError):
            eco.price_body(FIXTURE_LOC, "", "Seat", 4900)
        b = eco.price_body(FIXTURE_LOC, "PROD1", "Seat", 4900)
        assert b["amount"] == 4900 and b["type"] == "one_time"

    def test_optin_form_html_embeds_marker_and_fields(self):
        html = eco.optin_form_html(action_url="/cap", location_id=FIXTURE_LOC,
                                   marker="MARK123")
        assert "MARK123" in html
        assert 'name="firstName"' in html
        assert 'name="email"' in html
        assert 'name="phone"' in html
        assert 'action="/cap"' in html

    def test_optin_form_html_requires_marker(self):
        with pytest.raises(ValueError):
            eco.optin_form_html(action_url="/cap", location_id=FIXTURE_LOC, marker="")

    def test_make_test_email_unique_and_invalid(self):
        e1, e2 = eco.make_test_email(), eco.make_test_email()
        assert e1 != e2
        assert e1.endswith(".invalid")  # never deliverable

    def test_optin_payload_carries_both_tags(self):
        p = eco.optin_payload("a@b.invalid")
        assert set(eco.WORKSHOP_TAGS).issubset(set(p["tags"]))
        assert p["email"] == "a@b.invalid"


# ── the form->CRM PROOF (the dimension's hard requirement) ───────────────────

class TestFormToCrmProof:
    def test_happy_roundtrip(self):
        crm = FakeCrm()
        ops = crm.ops()
        before = crm.count_contacts()
        email = eco.make_test_email()
        ops.submit_optin(eco.optin_payload(email))
        proof = eco.prove_form_to_crm(ops, email, before_count=before)
        assert proof["tags_confirmed"] is True
        assert proof["before_count"] == 0 and proof["after_count"] == 1
        assert proof["matched_count"] == 1
        assert proof["created_contact_id"].startswith("CONT")

    def test_fails_when_no_contact_created(self):
        crm = FakeCrm(submit_inserts=False)  # opt-in did NOT create a contact
        ops = crm.ops()
        ops.submit_optin(eco.optin_payload("x@y.invalid"))
        with pytest.raises(eco.FormToCrmProofError, match="found 0"):
            eco.prove_form_to_crm(ops, "x@y.invalid", before_count=0)

    def test_fails_when_multiple_contacts_match(self):
        crm = FakeCrm(double_insert=True)  # opt-in created TWO
        ops = crm.ops()
        email = eco.make_test_email()
        ops.submit_optin(eco.optin_payload(email))
        with pytest.raises(eco.FormToCrmProofError, match="found 2"):
            eco.prove_form_to_crm(ops, email, before_count=0)

    def test_fails_when_tags_missing(self):
        crm = FakeCrm(tags_on_insert=[])  # contact created but NO tags
        ops = crm.ops()
        email = eco.make_test_email()
        ops.submit_optin(eco.optin_payload(email))
        with pytest.raises(eco.FormToCrmProofError, match="missing tag"):
            eco.prove_form_to_crm(ops, email, before_count=0)

    def test_fails_when_tags_partial(self):
        crm = FakeCrm(tags_on_insert=["workshop-registrant"])  # only one of two
        ops = crm.ops()
        email = eco.make_test_email()
        ops.submit_optin(eco.optin_payload(email))
        with pytest.raises(eco.FormToCrmProofError, match="missing tag"):
            eco.prove_form_to_crm(ops, email, before_count=0)

    def test_fails_on_reread_id_mismatch(self):
        crm = FakeCrm(reread_wrong_id=True)
        ops = crm.ops()
        email = eco.make_test_email()
        ops.submit_optin(eco.optin_payload(email))
        with pytest.raises(eco.FormToCrmProofError, match="read back"):
            eco.prove_form_to_crm(ops, email, before_count=0)

    def test_fails_when_count_not_plus_one(self):
        crm = FakeCrm()
        ops = crm.ops()
        email = eco.make_test_email()
        ops.submit_optin(eco.optin_payload(email))
        # lie about the baseline so after(1) != before(5)+1
        with pytest.raises(eco.FormToCrmProofError, match="expected"):
            eco.prove_form_to_crm(ops, email, before_count=5)


# ── full build_ecosystem sequence ────────────────────────────────────────────

class TestBuildEcosystem:
    def test_full_build_writes_real_receipts_and_passes(self, tmp_path):
        crm = FakeCrm()
        run_dir = str(tmp_path)
        summary = eco.build_ecosystem(crm.ops(), _spec(), run_dir, env=_good_env())

        assert summary["ok"] is True
        assert summary["verdict"] == "PASS"
        assert summary["form_to_crm_proven"] is True

        eco_dir = os.path.join(run_dir, "ecosystem")
        for fname in ("preflight.json", "calendar.json", "product-price.json",
                      "optin-form.json", "contact-test.json", "workflow.json",
                      "summary.json"):
            assert os.path.isfile(os.path.join(eco_dir, fname)), f"missing {fname}"

        # Receipts are REAL, not "PLANNED".
        cal = json.load(open(os.path.join(eco_dir, "calendar.json")))
        assert cal["http_status"] == 201 and cal["calendar_id"].startswith("CAL")
        assert "PLANNED" not in json.dumps(cal)

        pp = json.load(open(os.path.join(eco_dir, "product-price.json")))
        assert pp["product_id"].startswith("PROD")
        assert pp["price_id"].startswith("PRICE")

        ct = json.load(open(os.path.join(eco_dir, "contact-test.json")))
        assert ct["ok"] is True
        assert ct["tags_confirmed"] is True
        assert ct["before_count"] == 0 and ct["after_count"] == 1
        assert ct["submit_method"] == "form-post"
        assert ct["test_contact_deleted"] is True

        wf = json.load(open(os.path.join(eco_dir, "workflow.json")))
        assert wf["triggers_read_with_includeTriggers"] is True
        assert wf["triggers_count"] == 1

    def test_test_contact_is_cleaned_up(self, tmp_path):
        crm = FakeCrm()
        eco.build_ecosystem(crm.ops(), _spec(), str(tmp_path), env=_good_env())
        # the proof contact was deleted -> store empty again, delete recorded
        assert crm.count_contacts() == 0
        assert len(crm.deleted) == 1

    def test_build_fails_loud_when_proof_fails(self, tmp_path):
        crm = FakeCrm(tags_on_insert=[])  # contact created but untagged -> proof fails
        run_dir = str(tmp_path)
        summary = eco.build_ecosystem(crm.ops(), _spec(), run_dir, env=_good_env())
        assert summary["ok"] is False
        assert summary["verdict"] == "FAIL"
        assert summary["form_to_crm_proven"] is False
        ct = json.load(open(os.path.join(run_dir, "ecosystem", "contact-test.json")))
        assert ct["ok"] is False
        assert "missing tag" in ct["error"]
        # workflow step never ran (we short-circuited on the failing proof)
        assert not os.path.isfile(os.path.join(run_dir, "ecosystem", "workflow.json"))

    def test_build_fails_loud_when_optin_embed_fails(self, tmp_path):
        crm = FakeCrm()
        # make the on-page form embed report not-ok
        crm.embed_optin_form = lambda page_id, html, marker: {"ok": False}
        run_dir = str(tmp_path)
        summary = eco.build_ecosystem(crm.ops(), _spec(), run_dir, env=_good_env())
        assert summary["ok"] is False
        of = json.load(open(os.path.join(run_dir, "ecosystem", "optin-form.json")))
        assert of["ok"] is False

    def test_build_refuses_on_bad_preflight(self, tmp_path):
        crm = FakeCrm()
        with pytest.raises(eco.EcosystemPreflightError):
            eco.build_ecosystem(crm.ops(), _spec(), str(tmp_path),
                                env={"GHL_API_KEY": "x"})  # empty whitelist

    def test_summary_passed_count_matches_raw_receipts(self, tmp_path):
        """The consistency guard: summary.steps_passed == count of ok receipts."""
        crm = FakeCrm()
        run_dir = str(tmp_path)
        summary = eco.build_ecosystem(crm.ops(), _spec(), run_dir, env=_good_env())
        eco_dir = os.path.join(run_dir, "ecosystem")
        raw_ok = 0
        for fn in os.listdir(eco_dir):
            if fn == "summary.json":
                continue
            rec = json.load(open(os.path.join(eco_dir, fn)))
            if rec.get("ok"):
                raw_ok += 1
        assert summary["steps_passed"] == raw_ok

    def test_extract_id_raises_when_no_id(self):
        with pytest.raises(ValueError, match="no resource id"):
            eco._extract_id({"name": "x"}, "product")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
