#!/usr/bin/env python3
"""sc18_music_before_words_repair.py — acceptance row SC-18 (S75-W10-U1).

Condition (SCENARIO-MATRIX.json, row SC-18, verbatim):
    "Music-before-words repair"

Required result (verbatim):
    "NEGATIVE: when music was produced before words, the repair stage runs
     before delivery; delivery is refused while the repair is pending"

Every fact here comes from the REAL core modules of the tree under test:
``state_store`` (receipt aging + stage moves), ``qc_gate`` (the delivered-audio
acceptance gate) and ``spend_ledger``/``job_recovery`` are not needed. Only the
plan revisions are fixtures: music is measured under approved-plan revision 1,
the approved lyric sheet ("the words") lands and makes revision 2 current.
No network, no provider, no graph mutation.

Modes:
  (no flag)   run the scenario and print one assertion line per check
  --dry-run   identical checks, receipt marked mode=dry-run
  selftest    re-run under deliberate defects and REQUIRE the named
              assertions to turn RED (proves the harness can fail)

Exit 0 = every assertion held; 1 = at least one failed; 2 = tooling.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _harness as H  # noqa: E402

ROW = "sc18"
TITLE = "music-before-words repair gates delivery"

RUN_ID = "runSC18"
WORKER = "worker-a"
EVIDENCE_CHECK = "delivery.audio.acceptance"
MIX_BYTES = b"sc18 fixture mix bytes"
MIX_SHA = hashlib.sha256(MIX_BYTES).hexdigest()
REVIEWER = {"identity": "indep-reviewer", "session": "sess-sc18",
            "authority": "final-qc"}


def load_core(core):
    ss = H.load_file(core / "state_store.py", "state_store")
    qg = H.load_file(core / "qc_gate.py", "qc_gate")
    return ss, qg


def drive(st, stage, worker=WORKER, revision=1):
    """One stage through the real state machine to COMPLETE."""
    if st.get(RUN_ID, stage)["state"] == "NOT_STARTED":
        st.transition(RUN_ID, stage, "READY", worker)
    st.claim(RUN_ID, stage, worker, lease_s=300)
    st.transition(RUN_ID, stage, "QC", worker)
    st.transition(RUN_ID, stage, "COMPLETE", worker)
    return revision


def acceptance_doc(qg, rev, stage="delivery"):
    return qg.measurement_evidence(
        EVIDENCE_CHECK, {"accepted": True}, verdict="PASS",
        artifact_sha256=MIX_SHA, plan_revision=rev,
        evaluator_version="song_files/1.0",
        evidence_source="delivery_variants.song_files",
        run_id=RUN_ID, stage=stage, reviewer=REVIEWER)


def scenario(core, muts=frozenset()):
    ss, qg = load_core(core)
    c = H.Checks(ROW, TITLE)
    print("SC18 %s — tree %s%s"
          % (TITLE, core, (" [defect: %s]" % ",".join(sorted(muts)))
             if muts else ""))

    # The words land AFTER the music was produced. Under the
    # "words_never_landed" defect the run never records them, so revision 1
    # stays current and nothing is stale.
    stale_rev = "1"
    approved_rev = "1" if "words_never_landed" in muts else "2"

    with H.Scratch() as tmp:
        db = str(Path(tmp) / "state.db")
        st = ss.Store(db)
        try:
            st.init_run(RUN_ID, ["script-lyrics", "music", "qc-retakes",
                                 "delivery"])
            drive(st, "script-lyrics")
            drive(st, "music")

            # music measured + accepted BEFORE the words existed
            saved = st.save_receipt(
                RUN_ID, "music", "measurement", "audio-hash-1", "det/1",
                "pol/1", stale_rev, {"measurement": {"sung_pct": 71.0}})
            st.save_receipt(
                RUN_ID, "music", "acceptance", "audio-hash-1", "det/1",
                "pol/1", stale_rev, {"verdict": "PASS"},
                parent_key=saved["cache_key"])
            stale_doc = acceptance_doc(qg, stale_rev, stage="music")

            # ---- the words land: read-only impact, then the real aging ----
            impact = st.non_generating_op("reconcile", run_id=RUN_ID,
                                          plan_revision=approved_rev)
            c.check("sc18:words-after-music-obsolete-the-music-measurement",
                    bool(impact["obsolete_receipts"]),
                    "obsolete receipts=%d (approved revision %s, music "
                    "measured at %s)"
                    % (len(impact["obsolete_receipts"]), approved_rev,
                       stale_rev))
            aged = st.invalidate_receipts(RUN_ID, plan_revision=approved_rev)
            reread = st.get_receipt("measurement", "audio-hash-1", "det/1",
                                    "pol/1", stale_rev)
            c.check("sc18:stale-music-measurement-reads-as-absent",
                    len(aged["invalidated"]) >= 1 and reread is None,
                    "invalidated=%d reread=%r"
                    % (len(aged["invalidated"]), reread))

            # ---- delivery while the repair is pending --------------------
            before = st.get(RUN_ID, "delivery")
            gate = qg.delivery_acceptance([stale_doc],
                                          artifact_sha256=MIX_SHA,
                                          plan_revision=approved_rev)
            codes = sorted({s["code"] for s in gate["structural"]})
            c.check("sc18:delivery-refused-while-repair-pending",
                    gate["accepted"] is False and "STALE_BINDING" in codes,
                    "accepted=%s structural=%s (evidence revision %s, "
                    "approved revision %s)"
                    % (gate["accepted"], codes, stale_rev, approved_rev))
            c.check("sc18:delivery-stage-stays-not-started",
                    before["state"] == "NOT_STARTED",
                    "delivery state=%s" % before["state"])

            # ---- deliberate defect: deliver before the repair runs -------
            if "deliver_before_repair" in muts:
                drive(st, "delivery")

            # ---- the repair stage runs (re-measure at the approved rev) --
            fresh = None
            if "words_never_landed" not in muts:
                if st.get(RUN_ID, "qc-retakes")["state"] == "NOT_STARTED":
                    st.transition(RUN_ID, "qc-retakes", "READY",
                                  "worker-repair")
                st.claim(RUN_ID, "qc-retakes", "worker-repair", lease_s=300)
                st.non_generating_op(
                    "remeasure", run_id=RUN_ID, stage="qc-retakes",
                    audio_hash="audio-hash-1", evaluator_version="det/1",
                    policy_version="pol/1", plan_revision=approved_rev,
                    measure=lambda *a, **k: {"sung_pct": 71.0})
                fresh = acceptance_doc(qg, approved_rev, stage="qc-retakes")
                st.transition(RUN_ID, "qc-retakes", "QC", "worker-repair")
                st.transition(RUN_ID, "qc-retakes", "COMPLETE", "worker-repair")
            else:
                fresh = acceptance_doc(qg, approved_rev, stage="qc-retakes")

            # ---- delivery now accepted, and only now does it advance -----
            after = qg.delivery_acceptance([fresh], artifact_sha256=MIX_SHA,
                                           plan_revision=approved_rev)
            c.check("sc18:repaired-evidence-accepted-at-approved-revision",
                    after["accepted"] is True and not after["structural"],
                    "accepted=%s structural=%s verified=%d"
                    % (after["accepted"], after["structural"],
                       after["counts"]["pass"]))
            c.check("sc18:delivery-passing-evidence-authoured-by-repair-stage",
                    (fresh.get("record") or {}).get("stage") == "qc-retakes",
                    "evidence stage=%r check_id=%r"
                    % ((fresh.get("record") or {}).get("stage"),
                       fresh.get("check_id")))

            if "deliver_before_repair" not in muts and after["accepted"]:
                drive(st, "delivery")
                H.write_json(Path(tmp) / "delivery-receipt.json",
                             {"schema": "blackceo.sc18.delivery-receipt/v1",
                              "run_id": RUN_ID,
                              "artifact_sha256": MIX_SHA,
                              "plan_revision": approved_rev})

            final = st.get(RUN_ID, "delivery")
            c.check("sc18:delivery-complete-only-after-repair",
                    final["state"] == "COMPLETE"
                    and Path(tmp, "delivery-receipt.json").is_file(),
                    "delivery state=%s receipt=%s"
                    % (final["state"],
                       Path(tmp, "delivery-receipt.json").is_file()))

            # ---- ordering: repair receipt before delivery COMPLETE ------
            events = st.events(RUN_ID)
            repair_i = next((i for i, e in enumerate(events)
                             if e[1] == "receipt-save"
                             and "measurement|" in str(e[2])
                             and str(e[2]).endswith("|" + approved_rev)), None)
            deliv_i = next((i for i, e in enumerate(events)
                            if e[0] == "delivery"
                            and str(e[2]).strip().endswith("COMPLETE")), None)
            ordered = (repair_i is not None and deliv_i is not None
                       and repair_i < deliv_i)
            c.check("sc18:repair-runs-before-delivery",
                    ordered,
                    "repair event index=%s, delivery COMPLETE index=%s"
                    % (repair_i, deliv_i))
        finally:
            st.close()
    return c


MUTATIONS = {
    "words_never_landed": [
        "sc18:words-after-music-obsolete-the-music-measurement",
        "sc18:delivery-refused-while-repair-pending",
    ],
    "deliver_before_repair": [
        "sc18:repair-runs-before-delivery",
    ],
}


def selftest(core):
    ok = True
    for name in sorted(MUTATIONS):
        c = scenario(core, frozenset([name]))
        failed = [r["name"] for r in c.failed()]
        expected = MUTATIONS[name]
        hit = [e for e in expected if e in failed]
        good = len(hit) == len(expected) and len(failed) >= 1
        ok = ok and good
        print("selftest:%s — %s; red=%s"
              % (name, "RED as required" if good
                 else "DID NOT FAIL AS EXPECTED", failed or "none"))
        print("selftest:%s — expected hit=%d/%d"
              % (name, len(hit), len(expected)))
    print("selftest — %s"
          % ("harness fails on every defect" if ok
             else "HARNESS CANNOT PROVE A FAILURE"))
    return 0 if ok else 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "selftest":
        args = H.add_args(description="sc18 selftest").parse_args(argv[1:])
        return selftest(H.resolve_core(args))

    ap = H.add_args(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    core = H.resolve_core(args)
    result = scenario(core)
    if args.out:
        path = Path(args.out) / "receipts"
        code = result.finish(path)
        receipt = path / "sc18.scenario.json"
        if receipt.is_file():
            doc = json.loads(receipt.read_text("utf-8"))
            doc["mode"] = "dry-run" if args.dry_run else "run"
            receipt.write_text(json.dumps(doc, indent=2) + "\n", "utf-8")
        return code
    return result.finish()


if __name__ == "__main__":
    sys.exit(main())
