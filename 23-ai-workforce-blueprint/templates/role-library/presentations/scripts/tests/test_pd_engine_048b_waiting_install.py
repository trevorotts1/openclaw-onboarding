"""PD-048b -- A PAGE INSTALL THAT IS WAITING ON A PERSON IS A PAUSE, NOT A
FAILURE LOOP. (D-10 HOLD: staged, not merged.)

Acceptance rows proven here, verbatim from the unit's spec row
(``## PD-048b`` in the project's acceptance extract):

  A1  fixture run, sales pages elected, no adapter: the client-facing message
      list contains no string with ``AF-``, ``P-U-`` or "artifact check
      failed"; the phase is recorded waiting; a phase with no dependency on it
      still runs.
  A2  control: with the heal path un-patched (test the old function directly)
      the same fixture produces the "Regenerating" message -- proving the test
      can fail. Under PD-018b that message is the internal event
      ``report.internal``, never a client transport line.
  A3  after a complete receipt is written by the installer's in-memory adapter
      and the engine is resumed, the phase finishes.

The fixture is the REAL producer, not a stand-in: P-U-GHL-SALES runs
``ghl_external_installer.py`` through the engine's own script executor with no
Skill 06 adapter in process -- the production DELEGATED path. It exits 0 and
writes ``working/sales-checkout/ghl_build_receipt.json`` with
``status: pending_external_execution``; on the pre-fix tree that receipt was
read as missing substance and the heal ladder told the CLIENT
"P-U-GHL-SALES artifact check failed (AF-U-...) -- Regenerating".

A3's receipt is written by the installer's OWN in-memory adapter
(``MemoryPageAdapter``). Two things about that receipt are PD-048a's, not
this unit's, and are named here so no reader mistakes them for this unit's
claim:
  * PD-048a (ACCEPTED, staged on pd/fl16-page-installer, D-10) makes the
    installer write the FLAT receipt fields the phase check reads
    (execution_id / input_sha256 / location_id / funnel_id / page_id). That
    work is NOT on this branch -- checked: ``flat_receipt_fields`` is absent
    from ``ghl_external_installer.py`` at this head. Until it merges,
    ``_apply_pd048a_flat_contract`` copies the SAME values out of the nested
    fields the installer already wrote (nothing is invented), and the
    integration-tree proof in the BUILD REPORT runs the same row against
    PD-048a's actual accepted file.
  * ``ghl_media.resolve_location_pit/resolve_location_id`` are bound to a test
    double (PD-048a's own tests did the same) so the verifier's READ-ONLY
    readback NOTE cannot fail the row on a box with no GHL credential. No
    network call is made: without a file_id/media_id the readback returns
    before any transport.

No sleeps, no network, no model call.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import ghl_external_installer as gx  # noqa: E402
import phase_verifiers  # noqa: E402
from presentation_job import heal  # noqa: E402
from presentation_job.manifest import Manifest  # noqa: E402
from presentation_job.phases import (  # noqa: E402
    Engine, PHASE_STATUS_DONE, PHASE_STATUS_WAITING,
)
from presentation_job.state import StateStore, EXIT_OK  # noqa: E402

LOC = "locPD048BCLIENT"
ENV = {"GOHIGHLEVEL_LOCATION_ID": LOC}
INSTALL = "P-U-GHL-SALES"
RECEIPT_REL = "working/sales-checkout/ghl_build_receipt.json"

# ---------------------------------------------------------------------------
# Fixture: a three-phase scratch manifest over the REAL installer.
#   INSTALL : P-U-GHL-SALES, executor = ghl_external_installer.py (delegated)
#   SIBLING : no dependency on it
#   CONSUMER: consumes the install receipt
# ---------------------------------------------------------------------------
INSTALL_CMD = ("python3 scripts/ghl_external_installer.py "
               "--run-dir {run_dir} --phase P-U-GHL-SALES")

def _write_cmd(rel: str) -> str:
    target = json.dumps(rel)
    body = (f"import pathlib;p=pathlib.Path({target});"
            "p.parent.mkdir(parents=True,exist_ok=True);p.write_text('done')")
    return f"python3 -c {json.dumps(body)}"

_CLIENT_REPORT = {
    "start_template": "Step {k} of {N} — {name} — starting{eta}",
    "done_template": "Step {k} of {N} — {name} — complete",
}

def _intake(rd: Path) -> None:
    (rd / "working" / "copy").mkdir(parents=True, exist_ok=True)
    (rd / "working" / "copy" / "intake.json").write_text(json.dumps({
        "deck_slug": "acme-widget",
        "company": "Acme Co",
        "want_sales_checkout": "yes",
        "pre_presentation_capture": {"WANT_SALES_CHECKOUT": "yes"},
    }))
    html = rd / "working" / "sales-checkout" / "html"
    html.mkdir(parents=True, exist_ok=True)
    (html / "sales.html").write_text("<h1>Sales</h1>" + "x" * 300)
    (html / "checkout.html").write_text("<h1>Checkout</h1>" + "x" * 300)

def _engine(tmp_path: Path) -> Engine:
    rd = tmp_path / "run"
    rd.mkdir(parents=True, exist_ok=True)
    _intake(rd)
    mp = tmp_path / "PIPELINE-MANIFEST.json"
    mp.write_text(json.dumps({
        "manifest_version": 25,
        "phases": [
            {"id": INSTALL, "order": 1.0, "owning_role": "media-librarian-ghl-updater",
             "name": "Upsell Sales + Checkout GHL Funnel Build",
             "produces_artifact": [RECEIPT_REL],
             "client_report": dict(_CLIENT_REPORT),
             "executor": {"kind": "script", "cmd": INSTALL_CMD}},
            {"id": "SIBLING", "order": 2.0, "owning_role": "test",
             "name": "Independent sibling",
             "produces_artifact": ["working/sibling.txt"],
             "client_report": dict(_CLIENT_REPORT),
             "executor": {"kind": "script", "cmd": _write_cmd("working/sibling.txt")}},
            {"id": "CONSUMER", "order": 3.0, "owning_role": "test",
             "name": "Consumes the install receipt",
             "produces_artifact": ["working/consumer.txt"],
             "consumes": [RECEIPT_REL],
             "client_report": dict(_CLIENT_REPORT),
             "executor": {"kind": "script", "cmd": _write_cmd("working/consumer.txt")}},
        ],
    }), encoding="utf-8")
    manifest = Manifest(mp)
    store = StateStore(rd)
    state = {
        "schema_version": 1, "job_id": "t", "run_dir": str(rd),
        "created_at": "2026-01-01T00:00:00+00:00",
        "manifest_path": str(mp), "manifest_version": 25,
        "manifest_sha256": manifest.sha256,
        "presentation_type": "from_scratch",
        "requester": {"chat_id": "tc"},
        "phases": [], "gates": {}, "waivers": [], "events": [], "sent": {},
        "undeliverable": [], "heartbeat": {}, "terminal": None,
        "intake": json.loads((rd / "working" / "copy" / "intake.json").read_text()),
    }
    store.save(state)
    return Engine(rd, manifest, store, state, dry_run=False)

def _phase(eng: Engine, pid: str):
    return next(p for p in eng.manifest.phases if p.id == pid)

@pytest.fixture(autouse=True)
def _seams(monkeypatch):
    """Scratch phase ids SIBLING/CONSUMER have no registered substance
    verifier and the engine fails closed on that. Pass them through; the
    three PRES-011 phases keep the REAL verifier (the subject of A3)."""
    real_verify = phase_verifiers.verify

    def _verify(pid, run_dir):
        if pid in (INSTALL, "P-U-GHL-VSL", "P-U-FORM-GATE"):
            return real_verify(pid, run_dir)
        return True, []

    monkeypatch.setattr(phase_verifiers, "verify", _verify)
    # PD-048a's test seam: a bound, non-placeholder location and resolvable
    # PIT so the verifier's identity/readback checks judge the receipt rather
    # than a test box's missing credential. No transport: no file_id present.
    import ghl_media
    monkeypatch.setattr(ghl_media, "resolve_location_pit", lambda: "pit-pd048b")
    monkeypatch.setattr(ghl_media, "resolve_location_id", lambda: LOC)
    monkeypatch.setenv("GOHIGHLEVEL_LOCATION_ID", LOC)
    yield

def _capture_transport(monkeypatch) -> list:
    """Every client-facing dispatch, captured at the REAL transport boundary
    (presentation_job.report.dispatch3) -- not a helper's return value."""
    from presentation_job import report as report_mod
    sent: list = []

    def _stub(chat_id, kind, message):
        sent.append((kind, message))
        return report_mod.CheckResult.PASS

    monkeypatch.setattr(report_mod, "dispatch3", _stub)
    return sent

def _messages(sent: list) -> list:
    return [m for _kind, m in sent]

# ---------------------------------------------------------------------------
# A1
# ---------------------------------------------------------------------------
class TestA1WaitingIsAPause:
    def test_install_waiting_leaves_no_failure_text_and_siblings_run(self, tmp_path, monkeypatch):
        sent = _capture_transport(monkeypatch)
        eng = _engine(tmp_path)

        # 1. The REAL installer runs through the engine's script executor.
        rc = eng.run_phase(_phase(eng, INSTALL))

        # 2. Client-facing message list FIRST (the headline property): no
        #    leak, and the pause IS explained. On the pre-fix engine this is
        #    the assertion that goes red -- "P-U-GHL-SALES artifact check
        #    failed (AF-U-...) -- Regenerating" (see the M1 mutation proof in
        #    the BUILD REPORT).
        body = "\n".join(_messages(sent))
        assert "AF-" not in body, body
        assert "P-U-" not in body, body
        assert "artifact check failed" not in body, body
        waiting_msgs = [m for kind, m in sent if kind == "waiting"]
        assert waiting_msgs, f"the client was never told about the pause: {sent}"
        assert "GoHighLevel" in waiting_msgs[0]
        assert "Regenerating" not in body

        # 3. A pause is not a failure: the unit returns OK ...
        assert rc == EXIT_OK, "a person-wait must not fail the unit"

        # 4. Artefact proof (not a returned value): the pending receipt is on
        #    disk and the engine's record says waiting.
        receipt = json.loads((eng.run_dir / RECEIPT_REL).read_text())
        assert receipt["status"] == gx.STATUS_PENDING == "pending_external_execution"
        ps = eng._phase_state(INSTALL)
        assert ps["status"] == PHASE_STATUS_WAITING
        assert ps["waiting_on"] == "person"
        assert ps["waiting_status"] == "pending_external_execution"
        assert RECEIPT_REL in ps["waiting_receipts"]
        assert ps.get("waiting_since")
        assert ps["status"] != "quarantined" and ps["status"] != "blocked"

        # 5. The waiting phase is NOT re-admitted on the next claim scan (the
        #    failure loop, moved) ...
        tick = eng._ready_queue_tick(eng.manifest.phases, {}, {})
        assert INSTALL not in [p.id for p in tick["ready"]]
        # ... and it holds only its own consumer ...
        assert ("CONSUMER", INSTALL) in tick["waiting"]
        # ... while a phase with NO dependency on it is ready and RUNS.
        assert "SIBLING" in [p.id for p in tick["ready"]]
        rc_sib = eng.run_phase(_phase(eng, "SIBLING"))
        assert rc_sib == EXIT_OK
        assert eng._phase_state("SIBLING")["status"] == PHASE_STATUS_DONE
        assert (eng.run_dir / "working" / "sibling.txt").is_file()

        # 6. And the run end records a PAUSE, never a close/done and never a
        #    failed-units park.
        rc_pause = eng._pause_run_for_person()
        assert rc_pause != EXIT_OK
        assert eng.state["terminal"] == "BLOCKED"
        assert eng.state["blocked"]["kind"] == "waiting_on_person"
        assert eng.state["blocked"]["phases"] == [INSTALL]
        assert eng.state["waiting_for_person"][0]["phase"] == INSTALL
        assert not eng.state.get("failed_units")

    def test_complete_receipt_is_not_a_wait(self, tmp_path):
        """The detector's negative: a complete receipt is not a pause."""
        eng = _engine(tmp_path)
        rc, _rec = gx.execute_phase(eng.run_dir, INSTALL,
                                    page_adapter=gx.MemoryPageAdapter(LOC), env=ENV)
        assert rc == EXIT_OK
        disk = json.loads((eng.run_dir / RECEIPT_REL).read_text())
        assert disk["status"] == gx.STATUS_COMPLETE
        assert heal.waiting_on_person(eng.run_dir, _phase(eng, INSTALL)) is None

# ---------------------------------------------------------------------------
# A2 -- the control that proves A1 can fail
# ---------------------------------------------------------------------------
class TestA2ControlOldHealPath:
    def test_old_heal_path_still_says_regenerating(self, tmp_path, monkeypatch):
        """With the heal path un-patched -- the OLD function called directly --
        the same fixture still produces the "Regenerating" line, so A1's
        forbidding of that line is not vacuous.

        PD-018b (accepted sibling, and a stated dependency of this unit) moved
        the legacy line off the client transport: technical repair text is
        internal work, recorded as ``report.internal``, and the client hears
        nothing. The control therefore reads the event log, and also asserts
        that none of the legacy text reached the client. If the old path stops
        emitting the line, or the internal-only contract regresses, this row
        goes red.
        """
        sent = _capture_transport(monkeypatch)
        eng = _engine(tmp_path)
        phase = _phase(eng, INSTALL)

        rc = heal.rung2_regenerate(
            eng, phase,
            "substance check failed: AF-U-P-U-GHL-SALES: carries no location_id.")
        assert rc == EXIT_OK  # the re-run script exits 0, receipt still pending

        # The same strings A1 forbids are exactly the ones this old path emits
        # -- at the boundary PD-018b defines: the event log.
        internal = [e for e in eng.state.get("events", [])
                    if e.get("kind") == "report.internal"]
        assert internal, "the old heal path emitted no internal repair line"
        body = "\n".join(e.get("message", "") for e in internal)
        assert "Regenerating" in body
        assert "P-U-GHL-SALES artifact check failed" in body
        assert "AF-U-" in body
        assert "artifact check failed" in body

        # PD-018b's contract: none of it reaches the client.
        client = "\n".join(_messages(sent))
        assert "Regenerating" not in client
        assert "artifact check failed" not in client
        assert "AF-" not in client
        assert "P-U-" not in client

        # Prove the capture boundary is live, so "client" above is a real
        # absence and not a transport that never started.
        eng.report.to_requester("blocked", "transport control")
        assert "transport control" in "\n".join(_messages(sent))

# ---------------------------------------------------------------------------
# A3 -- a complete receipt + a resume finishes the phase
# ---------------------------------------------------------------------------
def _apply_pd048a_flat_contract(receipt_path: Path) -> dict:
    """PD-048a's flat receipt fields, copied out of the nested values the
    installer wrote. PD-048a is ACCEPTED on its own branch and staged behind
    D-10; it is not on this branch, so this test supplies the projection it
    adds. Nothing is invented -- every value is the installer's own."""
    obj = json.loads(receipt_path.read_text())
    obj["execution_id"] = obj["execution"]["execution_id"]
    obj["input_sha256"] = hashlib.sha256(
        json.dumps(obj["input_hashes"], sort_keys=True,
                   separators=(",", ":")).encode("utf-8")).hexdigest()
    obj["location_id"] = obj["scope"].get("location_id")
    remote = obj.get("remote") or {}
    obj["funnel_id"] = remote.get("funnel_id")
    page_id = ""
    for key in ("sales_page_id", "checkout_page_id", "vsl_page_id"):
        if remote.get(key):
            page_id = remote[key]
            break
    if not page_id:
        for key in sorted(remote):
            if key.endswith("_page_id") and remote[key]:
                page_id = remote[key]
                break
    obj["page_id"] = page_id
    receipt_path.write_text(json.dumps(obj, indent=2))
    return obj

class TestA3ResumeFinishes:
    def test_complete_receipt_then_resume_finishes_the_phase(self, tmp_path, monkeypatch):
        sent = _capture_transport(monkeypatch)
        eng = _engine(tmp_path)

        # First admission: the delegated install pauses.
        assert eng.run_phase(_phase(eng, INSTALL)) == EXIT_OK
        assert eng._phase_state(INSTALL)["status"] == PHASE_STATUS_WAITING

        # The person executes the install: the installer's OWN in-memory
        # adapter writes the complete receipt.
        rc, rec = gx.execute_phase(eng.run_dir, INSTALL,
                                   page_adapter=gx.MemoryPageAdapter(LOC), env=ENV)
        assert rc == EXIT_OK and rec["status"] == gx.STATUS_COMPLETE
        flat = _apply_pd048a_flat_contract(eng.run_dir / RECEIPT_REL)
        assert flat["execution_id"] and flat["input_sha256"]
        assert flat["location_id"] == LOC and flat["funnel_id"] and flat["page_id"]

        # Resume: the department's own unpark helper re-admits the waiting
        # phase, then the engine re-enters it.
        from presentation_job.phases import readmit_retryable_phases
        eng.state["terminal"] = None
        readmitted = readmit_retryable_phases(eng.state)
        record = next(r for r in readmitted if r["phase"] == INSTALL)
        assert record["prior_status"] == PHASE_STATUS_WAITING
        assert eng._phase_state(INSTALL)["status"] == "pending"

        rc = eng.run_phase(_phase(eng, INSTALL))
        assert rc == EXIT_OK
        ps = eng._phase_state(INSTALL)
        assert ps["status"] == PHASE_STATUS_DONE
        assert ps["verifier_ok"] is True
        assert not ps.get("verifier_notes")
        # Artefact proof: the complete receipt is STILL on disk -- the resume
        # did not downgrade it to a pending plan shell (the installer's own
        # VERIFIED short-circuit re-validates it and exits 0, and the verifier
        # then passes it; proven by the receipt bytes, not by a return value).
        assert json.loads((eng.run_dir / RECEIPT_REL).read_text())["status"] == "complete"
        # And nothing failed or was healed along the way.
        assert not [e for e in eng.state.get("events", [])
                    if e.get("kind") == "report.blocked"]
        assert eng.state.get("failed_units") in (None, [])
        assert "Regenerating" not in "\n".join(_messages(sent))
