#!/usr/bin/env python3
"""test_rewrite_preservation.py -- U10 / PRD Gap G10 + G11 regression tests.

Proves the chapter-rewrite-preservation build (B4):

  G10 - a chapter rewrite lands in its OWN pair (rewrite1 for the first editors'
        rewrite, rewrite2 for the second), so the ORIGINAL chapter and any earlier
        rewrite survive in the producer's Convert and Flow view. A rewrite NEVER
        overwrites the base chapter pair.
  G10 - the rewrite counter is surfaced and the budget is HARD-enforced at 2: a
        third rewrite request is an illegal transition the ledger refuses, and the
        strike gate offers only Approve-as-is / escalate at budget.
  G11 - field-map.json declares every free-text key LARGE_TEXT (matching live and
        the multi-line law); create-or-verify on a FRESH location provisions
        LARGE_TEXT, never TEXT. SINGLE_OPTIONS fields (decision, cover choice) are
        deliberately not in this map.

MOCK GHL: every Convert and Flow interaction runs through the in-memory _StubCaf
(the same offline stand-in caf_delivery's own self-test uses) and the registry's
_FakeCaf. NOTHING here touches a live location, a live GHL write, or a credential.
The ledger enforcement is proven against a hermetic temp SQLite mirror only
(ANTHOLOGY_STATE_* env stripped so no Airtable base is reachable). Python 3 stdlib.

Run: python3 -m pytest 59-anthology-engine/tests/test_rewrite_preservation.py -q
 or: python3 59-anthology-engine/tests/test_rewrite_preservation.py
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_DIR / "scripts"
FIELD_MAP = SKILL_DIR / "config" / "field-map.json"
STATE = SCRIPTS / "anthology_state.py"
STRIKE = SCRIPTS / "qc-strike-gate.py"

sys.path.insert(0, str(SCRIPTS))
import caf_delivery as caf            # noqa: E402
import anthology_registry as registry  # noqa: E402

BASE_CHAPTER =("contact.anthology_chapter_doc_url", "contact.anthology_chapter_pdf_url")
REWRITE1 = ("contact.anthology_chapter_rewrite1_doc_url",
            "contact.anthology_chapter_rewrite1_pdf_url")
REWRITE2 = ("contact.anthology_chapter_rewrite2_doc_url",
            "contact.anthology_chapter_rewrite2_pdf_url")


# ---------------------------------------------------------------------------
# G11: field-map declares LARGE_TEXT everywhere; SINGLE_OPTIONS stays out.
# ---------------------------------------------------------------------------
def test_field_map_all_free_text_is_large_text():
    fm = json.loads(FIELD_MAP.read_text(encoding="utf-8"))
    inv = fm["provisioning"]["fields"]
    # Integration: 19 base + 4 G10 rewrite (U10) + 5 U8 cover-style = 28 keys.
    assert len(inv) == 28, "expected 28 provisioning keys, got %d" % len(inv)
    assert fm["provisioning"]["total_keys"] == 28
    for row in inv:
        # G11: every free-text key is LARGE_TEXT. The one exception is the U8 cover
        # choice, a SINGLE_OPTIONS picklist that legitimately lives in this inventory.
        if row["intended_key"] == "contact.anthology_cover_choice":
            assert row["data_type"] == "SINGLE_OPTIONS", \
                "the cover choice must be SINGLE_OPTIONS, got %s" % row["data_type"]
        else:
            assert row["data_type"] == "LARGE_TEXT", \
                "%s must be LARGE_TEXT (G11), got %s" % (row["intended_key"], row["data_type"])
    # The universal-review DECISION field is SINGLE_OPTIONS and stays out of this map;
    # the U8 cover-choice SINGLE_OPTIONS field IS provisioned here (has its picklist).
    keys = {row["intended_key"] for row in inv}
    assert "contact.anthology_review_decision" not in keys, \
        "the review decision is SINGLE_OPTIONS and must not be in field-map"


def test_field_map_inventory_matches_deliverable_contract():
    fm = json.loads(FIELD_MAP.read_text(encoding="utf-8"))
    contract = set()
    for pair in fm["deliverable_fields"].values():
        contract.update(pair.values())
    contract.update(fm["control_fields"].values())
    # U8 cover-style keys (four sample-url + the choice) are part of the contract too.
    csf = fm.get("cover_style_fields") or {}
    contract.update((csf.get("sample_url_fields") or {}).values())
    if csf.get("choice_field"):
        contract.add(csf["choice_field"])
    inv_keys = {row["intended_key"] for row in fm["provisioning"]["fields"]}
    assert contract == inv_keys, "provisioning inventory drifted from deliverable/control/cover-style keys"
    # the four G10 rewrite keys are present and distinct from the base chapter pair
    assert set(REWRITE1) | set(REWRITE2) <= inv_keys
    assert not (set(BASE_CHAPTER) & (set(REWRITE1) | set(REWRITE2)))


# ---------------------------------------------------------------------------
# G10: rewrite artifact routes to its own slot, never the base chapter.
# ---------------------------------------------------------------------------
def test_rewrite_routes_to_its_own_slot():
    fm = caf.FieldMap.load(FIELD_MAP)
    assert fm.deliverable_for_artifact_type("rewrite", rewrite_number=1) == "rewrite1"
    assert fm.deliverable_for_artifact_type("rewrite", rewrite_number=2) == "rewrite2"
    assert fm.deliverable_for_rewrite("1") == "rewrite1"      # str coercion
    # the base chapter still resolves to chapter; rewrite never does
    assert fm.deliverable_for_artifact_type("chapter") == "chapter"
    # a rewrite WITHOUT a slot is refused -- never a silent overwrite of the base
    for bad in (lambda: fm.deliverable_for_artifact_type("rewrite"),
                lambda: fm.deliverable_for_rewrite(0),
                lambda: fm.deliverable_for_rewrite(3)):
        try:
            bad()
            raise AssertionError("expected a refusal for an out-of-budget rewrite slot")
        except caf.DeliveryError as exc:
            assert exc.code == caf.EX_TENANT
    # the slots are disjoint from the base pair and from each other
    base = set(fm.deliverable_keys("chapter"))
    r1 = set(fm.deliverable_keys("rewrite1"))
    r2 = set(fm.deliverable_keys("rewrite2"))
    assert base == set(BASE_CHAPTER) and r1 == set(REWRITE1) and r2 == set(REWRITE2)
    assert not (base & r1) and not (base & r2) and not (r1 & r2)


# ---------------------------------------------------------------------------
# G10 end-to-end with MOCK GHL: the base chapter survives both rewrites, and
# every write reads back byte-for-byte.
# ---------------------------------------------------------------------------
def _fully_provisioned_stub():
    """A _StubCaf whose location carries ALL 23 anthology fields (fieldKey -> id),
    so resolve_field_ids finds every key live. A pure mock -- no network."""
    stub = caf._StubCaf()
    fm = caf.FieldMap.load(FIELD_MAP)
    stub.fields = {key: "cf_%d" % i for i, key in enumerate(fm.all_keys())}
    return stub


def _deliver(client, fm, contact_id, slot, doc, pdf):
    """Write a deliverable's doc+pdf via the REAL write+read-back engine (the exact
    path cmd_deliver uses) and return the per-field results."""
    doc_key, pdf_key = fm.deliverable_keys(slot)
    return caf.write_and_verify(client, contact_id, [(doc_key, doc), (pdf_key, pdf)],
                                field_map=fm)


def test_delivery_preserves_original_across_two_rewrites():
    fm = caf.FieldMap.load(FIELD_MAP)
    stub = _fully_provisioned_stub()
    client = caf.CafClient("pit-test", "locTEST", opener=stub.open)
    cid = "c_rewrite_demo"

    # 1) the ORIGINAL chapter is delivered to the base pair
    base_doc = "https://docs.example/original"
    base_pdf = "https://storage.example/original.pdf"
    res0 = _deliver(client, fm, cid, "chapter", base_doc, base_pdf)
    assert all(r["match"] for r in res0), "base chapter did not read back byte-for-byte"

    def stored(key):
        fid = stub.fields[key]
        return stub.contacts.get(cid, {}).get(fid)

    assert stored(BASE_CHAPTER[0]) == base_doc and stored(BASE_CHAPTER[1]) == base_pdf

    # 2) rewrite #1 lands in rewrite1 -- base pair UNTOUCHED
    slot1 = fm.deliverable_for_artifact_type("rewrite", rewrite_number=1)
    r1_doc, r1_pdf = "https://docs.example/rewrite1", "https://storage.example/rewrite1.pdf"
    res1 = _deliver(client, fm, cid, slot1, r1_doc, r1_pdf)
    assert all(r["match"] for r in res1), "rewrite1 did not read back byte-for-byte"
    assert stored(REWRITE1[0]) == r1_doc and stored(REWRITE1[1]) == r1_pdf
    assert stored(BASE_CHAPTER[0]) == base_doc and stored(BASE_CHAPTER[1]) == base_pdf, \
        "G10 VIOLATED: the original chapter was overwritten by rewrite 1"
    assert stored(REWRITE2[0]) is None, "rewrite2 must be empty before the second rewrite"

    # 3) rewrite #2 lands in rewrite2 -- base pair AND rewrite1 UNTOUCHED
    slot2 = fm.deliverable_for_artifact_type("rewrite", rewrite_number=2)
    r2_doc, r2_pdf = "https://docs.example/rewrite2", "https://storage.example/rewrite2.pdf"
    res2 = _deliver(client, fm, cid, slot2, r2_doc, r2_pdf)
    assert all(r["match"] for r in res2), "rewrite2 did not read back byte-for-byte"
    assert stored(REWRITE2[0]) == r2_doc and stored(REWRITE2[1]) == r2_pdf
    assert stored(BASE_CHAPTER[0]) == base_doc and stored(BASE_CHAPTER[1]) == base_pdf, \
        "G10 VIOLATED: the original chapter was lost after rewrite 2"
    assert stored(REWRITE1[0]) == r1_doc and stored(REWRITE1[1]) == r1_pdf, \
        "G10 VIOLATED: rewrite 1 was overwritten by rewrite 2"

    # all three versions coexist: original + rewrite1 + rewrite2, six distinct keys
    present = {k for k in (BASE_CHAPTER + REWRITE1 + REWRITE2) if stored(k)}
    assert len(present) == 6, "all six preservation keys must be populated, got %d" % len(present)


def test_readback_mismatch_is_caught_by_mock_ghl():
    """The mock GHL proves the read-back guard is real: a tampered stored value
    raises AF-AE-READBACK-MISMATCH (exit 5), never a silent pass."""
    fm = caf.FieldMap.load(FIELD_MAP)
    stub = _fully_provisioned_stub()

    # a client that corrupts what it stores for the rewrite1 doc key
    class _Tamper(caf.CafClient):
        def write_custom_fields(self, contact_id, id_value_pairs):
            poisoned = [(fid, (val + "_TAMPERED")) for fid, val in id_value_pairs]
            return super().write_custom_fields(contact_id, poisoned)

    client = _Tamper("pit-test", "locTEST", opener=stub.open)
    try:
        _deliver(client, fm, "c_tamper", "rewrite1", "u1", "u2")
        raise AssertionError("a tampered read-back must not pass")
    except caf.DeliveryError as exc:
        assert exc.code == caf.EX_MISMATCH


# ---------------------------------------------------------------------------
# G11: a FRESH location provisions LARGE_TEXT for every field (mock GHL).
# ---------------------------------------------------------------------------
def test_fresh_location_provisions_large_text():
    src = json.loads(FIELD_MAP.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "field-map.json"
        p.write_text(json.dumps(src, indent=2), encoding="utf-8")
        fake = registry._FakeCaf()              # empty location -> all fields created
        dev = _Sink()
        rc = registry.provision_fields(fake, p, "loc_fresh_TEST", out=dev)
        assert rc == registry.EX_OK, "fresh provision rc=%s" % rc
        assert len(fake.fields) == 28, "fresh location should create 28 fields, got %d" % len(fake.fields)
        types = {f["dataType"] for f in fake.fields.values()}
        assert types == {"LARGE_TEXT", "SINGLE_OPTIONS"}, \
            "fresh-location create must be LARGE_TEXT for free-text + SINGLE_OPTIONS for the cover choice, got %s" % types
        # the map stamped every free-text row LARGE_TEXT (all but the cover choice)
        stamped = json.loads(p.read_text(encoding="utf-8"))
        assert all(r["data_type"] == "LARGE_TEXT" for r in stamped["provisioning"]["fields"]
                   if r["intended_key"] != "contact.anthology_cover_choice")


def test_existing_large_text_location_verifies_unchanged():
    """Create-or-verify against a location whose 23 fields already exist as
    LARGE_TEXT (mirrors live) is an idempotent verify-by-key, exit 0 -- the verify
    path asserts fieldKey byte-equality only, so live is undisturbed."""
    src = json.loads(FIELD_MAP.read_text(encoding="utf-8"))
    existing = [{"fieldKey": r["intended_key"], "id": "live_%d" % i, "name": r["create_name"],
                 "dataType": "LARGE_TEXT"}
                for i, r in enumerate(src["provisioning"]["fields"])]
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "field-map.json"
        p.write_text(json.dumps(src, indent=2), encoding="utf-8")
        fake = registry._FakeCaf(existing_fields=existing)
        dev = _Sink()
        rc = registry.provision_fields(fake, p, "loc_live_TEST", out=dev)
        assert rc == registry.EX_OK, "verify against existing LARGE_TEXT rc=%s" % rc
        # nothing new created -- all 23 resolved by verify-by-key
        stamped = json.loads(p.read_text(encoding="utf-8"))
        assert all(r["field_key"] == r["intended_key"] and r["field_id"]
                   for r in stamped["provisioning"]["fields"])


# ---------------------------------------------------------------------------
# G10: the rewrite budget is HARD-enforced at 2 against a REAL ledger, and the
# counter is surfaced. No GHL -- a hermetic temp SQLite mirror only.
# ---------------------------------------------------------------------------
def _clean_env():
    env = dict(os.environ)
    for k in ("ANTHOLOGY_STATE_BASE_ID", "AIRTABLE_API_KEY", "AIRTABLE_TOKEN",
              "AIRTABLE_PAT", "ANTHOLOGY_STATE_AIRTABLE_KEY", "ANTHOLOGY_STATE_DIR"):
        env.pop(k, None)
    return env


def _state(db, *args, env=None):
    return subprocess.run([sys.executable, str(STATE), "--db", str(db), *args],
                          capture_output=True, text=True, env=env or _clean_env())


def _walk_to_s5_gate(db, env):
    pkey = "c1::anthA"
    steps = [
        ["bootstrap"],
        ["upsert-producer", "--producer-id", "prodX", "--producer-email",
         "owner@example.test", "--display-name", "Owner"],
        ["upsert-anthology", "--anthology-id", "anthA", "--producer-id", "prodX",
         "--name", "The Collection", "--min-chapters", "2"],
        ["upsert-participant", "--contact-id", "c1", "--anthology-id", "anthA",
         "--first-name", "Ada"],
        ["advance-stage", "--participant-key", pkey, "--to", "s1_avatar"],
        ["advance-stage", "--participant-key", pkey, "--to", "s1_gate"],
        ["record-approval", "--gate", "s1_producer", "--participant-key", pkey, "--decision", "approve"],
        ["advance-stage", "--participant-key", pkey, "--to", "s2_gate"],
        ["record-approval", "--gate", "s2_producer", "--participant-key", pkey, "--decision", "approve"],
        ["advance-stage", "--participant-key", pkey, "--to", "s3_gate"],
        ["record-approval", "--gate", "s3_selection", "--participant-key", pkey,
         "--decision", "approve", "--title", "Rise", "--subtitle", "A Story"],
        ["advance-stage", "--participant-key", pkey, "--to", "s4_gate_producer"],
        ["record-approval", "--gate", "s4_producer", "--participant-key", pkey, "--decision", "approve"],
        ["record-approval", "--gate", "s4_participant", "--participant-key", pkey, "--decision", "approve"],
        ["record-artifact", "--participant-key", pkey, "--type", "chapter",
         "--sha256", "shaOrig", "--model-used", "glm-5.2"],
        ["advance-stage", "--participant-key", pkey, "--to", "s5_gate"],
    ]
    for st in steps:
        r = _state(db, *st, env=env)
        assert r.returncode == 0, "setup step %s failed rc=%d: %s" % (st[0], r.returncode, r.stderr[-300:])
    return pkey


def _rewrite_count(db, pkey, env):
    r = _state(db, "--json", "get-participant", "--participant-key", pkey, env=env)
    assert r.returncode == 0, r.stderr[-300:]
    return int(json.loads(r.stdout)["rewrite_count"])


def test_third_rewrite_refused_and_count_surfaced_real_ledger():
    env = _clean_env()
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "ledger.sqlite"
        pkey = _walk_to_s5_gate(db, env)
        fm = caf.FieldMap.load(FIELD_MAP)

        assert _rewrite_count(db, pkey, env) == 0, "no rewrite requested yet"

        # rewrite #1: count 0 -> 1, cursor re-enters s5_gate. Slot routes to rewrite1.
        r = _state(db, "record-approval", "--gate", "s5_participant", "--participant-key",
                   pkey, "--decision", "request_rewrite", "--notes", "tighten the open", env=env)
        assert r.returncode == 0, "first rewrite should be allowed: %s" % r.stderr[-300:]
        assert _rewrite_count(db, pkey, env) == 1
        assert fm.deliverable_for_artifact_type("rewrite", rewrite_number=1) == "rewrite1"
        assert _state(db, "advance-stage", "--participant-key", pkey, "--to", "s5_gate",
                      env=env).returncode == 0

        # rewrite #2: count 1 -> 2 (the final, budget-exhausting rewrite). Slot rewrite2.
        r = _state(db, "record-approval", "--gate", "s5_participant", "--participant-key",
                   pkey, "--decision", "request_rewrite", "--notes", "again", env=env)
        assert r.returncode == 0, "second rewrite should be allowed: %s" % r.stderr[-300:]
        assert _rewrite_count(db, pkey, env) == 2
        assert fm.deliverable_for_artifact_type("rewrite", rewrite_number=2) == "rewrite2"
        assert _state(db, "advance-stage", "--participant-key", pkey, "--to", "s5_gate",
                      env=env).returncode == 0

        # rewrite #3: HARD refusal -- an illegal transition (exit 2). Budget is 2.
        r = _state(db, "record-approval", "--gate", "s5_participant", "--participant-key",
                   pkey, "--decision", "request_rewrite", env=env)
        assert r.returncode == 2, "a THIRD rewrite must be refused (exit 2), got %d" % r.returncode
        assert _rewrite_count(db, pkey, env) == 2, "the refused 3rd rewrite must not bump the count"

        # the strike gate surfaces the count and, at budget, offers ONLY approve/escalate.
        sg = subprocess.run([sys.executable, str(STRIKE), "--db", str(db), "--json",
                             "rewrite-gate", "--participant-key", pkey],
                            capture_output=True, text=True, env=env)
        assert sg.returncode == 4, "strike gate at budget must exit 4 (exhausted), got %d" % sg.returncode
        dec = json.loads(sg.stdout)
        assert dec["rewrite_count"] == 2 and dec["budget"] == 2 and dec["remaining"] == 0
        assert dec["exhausted"] is True
        assert dec["gate_actions"] == ["approve_as_is", "escalate_to_producer"], \
            "at budget the gate must NOT offer request_rewrite; got %s" % dec["gate_actions"]


# ---------------------------------------------------------------------------
# Doctrine guard: this unit introduced no Anthropic-family runtime id. Delegates
# to the repo's OWN authoritative scanner (which correctly skips guard-definition
# regexes and negative fixtures), not a naive substring match.
# ---------------------------------------------------------------------------
def test_unit_introduced_no_anthropic_runtime_id():
    guard = SCRIPTS / "guard-no-anthropic-runtime.py"
    if not guard.exists():
        return  # scanner absent on this checkout; verify.sh owns the fleet gate
    for target in ("caf_delivery.py", "stage_s6_rewrite.py", "stage_s8_deliver.py",
                   "anthology_registry.py"):
        r = subprocess.run([sys.executable, str(guard), str(SCRIPTS / target)],
                           capture_output=True, text=True)
        assert r.returncode == 0, "%s failed the anthropic-runtime guard: %s" % (target, r.stdout[-300:])


class _Sink:
    def write(self, *_a, **_k):
        pass


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print("  [PASS] %s" % fn.__name__)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print("  [FAIL] %s -- %s" % (fn.__name__, exc))
    print("test_rewrite_preservation: %s (%d/%d)"
          % ("ALL PASSED" if not failed else "FAILURES", len(fns) - failed, len(fns)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run_all())
