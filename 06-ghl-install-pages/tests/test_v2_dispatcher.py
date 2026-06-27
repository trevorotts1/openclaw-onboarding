"""MOCK-only unit tests — v2_dispatcher (the bounded Funnels-dept dispatcher).

These tests are MOCK-ONLY. The ``builder`` is an injected fake (NO seed/activate,
NO REST autosave, NO live GHL, NO browser, NO network). The canonical verifier is
driven through ghl_verify with an injected fetcher elsewhere; here we inject a
fake verifier OR pass pages that the real ghl_verify reduces with a stubbed
fetcher. The assertions cover the SOP §1 bounded-dispatcher CONTRACT:

  * the state machine backlog -> dispatched -> building -> verified | FAILED,
  * HARD max_inflight=1 (a task is left in backlog, never a 2nd concurrent build),
  * the wall-clock cap converts a HANG / over-long build into a FAILED (the
    HTTP-000-hang fix) — never an indefinite stall,
  * a crashed builder -> FAILED with the partial evidence + reason recorded,
  * the sub-account location gate failure blocks `verified` (NO-COMINGLING),
  * the telemetry-scrub gate blocks `verified` while a leak remains,
  * a clean build reaches `verified` and records the verdict honestly (a FAIL
    overall_pass is reported, never massaged to pass).

No real client/operator names, ids, emails, or location-ids appear.
"""
from __future__ import annotations

import json
import os
import sys

_TOOLS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "tools"))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import pytest

import v2_dispatcher as disp
import ghl_verify as gv


FAKE_TASK = {"id": "taskFAKE", "brand": "Fictional Soap Co",
             "location_id": "LOCATIONfake0000", "brief": "build a funnel"}


def _fake_verifier(overall: bool, passed: int = 1, total: int = 1):
    """Injected verifier mirroring ghl_verify.verify_all's return contract."""
    def _v(evidence_root, pages, **kw):
        summary = {"overall_pass": overall, "passed": passed, "total": total,
                   "failed": total - passed}
        # Write the two canonical files so the evidence tree looks real.
        os.makedirs(os.path.join(evidence_root, "scorecard"), exist_ok=True)
        with open(os.path.join(evidence_root, "scorecard", "verify-summary.json"), "w") as f:
            json.dump(summary, f)
        return {"raw": [], "summary": summary, "raw_path": "", "summary_path": ""}
    return _v


def _builder_ok(pages=None, gate_ok=True, duration=10.0):
    pages = pages if pages is not None else [{"step": "optin", "preview_url": "u", "marker": "m"}]
    def _b(task, evidence_root):
        # A real builder writes ledgers as it goes; the fake writes a stub ledger.
        os.makedirs(os.path.join(evidence_root, "funnel"), exist_ok=True)
        with open(os.path.join(evidence_root, "funnel", "ledger.json"), "w") as f:
            json.dump({"built": True}, f)
        return {"pages": pages, "location_gate_ok": gate_ok, "duration_s": duration}
    return _b


# ── max_inflight = 1 (never a second concurrent build over the fixture) ───────

class TestMaxInflight:
    def test_left_in_backlog_when_inflight_full(self, tmp_path):
        res = disp.dispatch_one(
            FAKE_TASK, str(tmp_path), builder=_builder_ok(),
            verifier=_fake_verifier(True), inflight_now=1, max_inflight=1)
        assert res.state == disp.STATE_BACKLOG
        assert "max_inflight" in res.reason
        # task-record.json reflects the backlog hold.
        rec = json.load(open(os.path.join(tmp_path, "routing", "task-record.json")))
        assert rec["state"] == "backlog"


# ── wall-clock cap converts a hang / over-long build into FAILED ──────────────

class TestWallClockCap:
    def test_over_cap_is_failed_not_stall(self, tmp_path):
        # Builder "ran" 5000s — over the 1800s cap -> FAILED (the HTTP-000 fix).
        res = disp.dispatch_one(
            FAKE_TASK, str(tmp_path), builder=_builder_ok(duration=5000.0),
            verifier=_fake_verifier(True), wallclock_cap_s=1800)
        assert res.state == disp.STATE_FAILED
        assert "timeout" in res.reason
        rec = json.load(open(os.path.join(tmp_path, "routing", "task-record.json")))
        assert rec["state"] == "FAILED"
        assert rec["build_duration_s"] == 5000.0

    def test_under_cap_proceeds(self, tmp_path):
        res = disp.dispatch_one(
            FAKE_TASK, str(tmp_path), builder=_builder_ok(duration=10.0),
            verifier=_fake_verifier(True), wallclock_cap_s=1800)
        assert res.state == disp.STATE_VERIFIED


# ── a crashed builder -> FAILED with the reason recorded (evidence kept) ──────

class TestBuilderCrash:
    def test_builder_exception_is_failed(self, tmp_path):
        def _boom(task, root):
            raise RuntimeError("seed/activate failed")
        res = disp.dispatch_one(FAKE_TASK, str(tmp_path), builder=_boom,
                                verifier=_fake_verifier(True))
        assert res.state == disp.STATE_FAILED
        assert "builder raised" in res.reason
        assert "seed/activate failed" in res.reason


# ── sub-account location gate failure blocks `verified` (NO-COMINGLING) ───────

class TestLocationGate:
    def test_gate_not_ok_blocks_verified(self, tmp_path):
        res = disp.dispatch_one(
            FAKE_TASK, str(tmp_path), builder=_builder_ok(gate_ok=False),
            verifier=_fake_verifier(True))
        assert res.state == disp.STATE_FAILED
        assert "location gate" in res.reason.lower()


# ── telemetry-scrub gate blocks `verified` while a leak remains ───────────────

class TestTelemetryGate:
    def test_leaked_telemetry_is_scrubbed_then_passes(self, tmp_path):
        # A dirty telemetry file is scrubbed by the gate; after scrub it is clean,
        # so the build proceeds to verified.
        tdir = tmp_path / "logs"
        tdir.mkdir()
        tfile = tdir / "agent-turn-3.out.json"
        tfile.write_text(json.dumps({"tools": ["redacted-client__messages_send"]}))
        res = disp.dispatch_one(
            FAKE_TASK, str(tmp_path), builder=_builder_ok(),
            verifier=_fake_verifier(True), telemetry_glob=[str(tfile)])
        assert res.state == disp.STATE_VERIFIED
        # The file on disk is now scrubbed clean.
        import scrub_turn_telemetry as scrub
        assert scrub.is_clean(tfile.read_text())


# ── clean build reaches verified; the verdict is recorded HONESTLY ────────────

class TestVerifiedHonestVerdict:
    def test_overall_pass_true_is_truthy_result(self, tmp_path):
        res = disp.dispatch_one(
            FAKE_TASK, str(tmp_path), builder=_builder_ok(),
            verifier=_fake_verifier(True, passed=2, total=2))
        assert res.state == disp.STATE_VERIFIED
        assert bool(res) is True
        assert res.verify["overall_pass"] is True

    def test_overall_fail_recorded_not_massaged(self, tmp_path):
        # The build ran and verified, but the canonical verifier says FAIL (e.g.
        # markers didn't land). The dispatcher records verified-state WITH a False
        # overall_pass — it does NOT massage it to pass.
        res = disp.dispatch_one(
            FAKE_TASK, str(tmp_path), builder=_builder_ok(),
            verifier=_fake_verifier(False, passed=1, total=6))
        assert res.state == disp.STATE_VERIFIED
        assert bool(res) is False              # truthiness requires overall_pass
        assert res.verify["overall_pass"] is False
        rec = json.load(open(os.path.join(tmp_path, "routing", "task-record.json")))
        assert rec["verify_overall_pass"] is False
        assert rec["verify_passed"] == 1 and rec["verify_total"] == 6


# ── integration with the REAL ghl_verify (injected fetcher, no network) ───────

class TestWithRealVerifier:
    def test_real_verifier_consistent_files(self, tmp_path):
        # Use the REAL ghl_verify.verify_all but inject a fake fetcher so no
        # network happens — proves the dispatcher + canonical verifier compose.
        pages = [{"step": "optin", "page_id": "P1", "preview_url": "u1", "marker": "m"},
                 {"step": "home", "page_id": "P2", "preview_url": "u2", "marker": "m"}]
        results = {"u1": {"ok": True, "http": 200, "marker_found": True, "url": "u1"},
                   "u2": {"ok": False, "http": 200, "marker_found": False, "url": "u2"}}

        def _fetch(url, marker):
            return results.get(url, {"ok": False, "http": None, "marker_found": False, "url": url})

        def _real_verifier(evidence_root, pgs, **kw):
            return gv.verify_all(evidence_root, pgs, fetcher=_fetch, **kw)

        res = disp.dispatch_one(
            FAKE_TASK, str(tmp_path), builder=_builder_ok(pages=pages),
            verifier=_real_verifier)
        assert res.state == disp.STATE_VERIFIED
        # 1/2 truth -> overall FAIL, reported honestly.
        assert res.verify["passed"] == 1 and res.verify["total"] == 2
        assert res.verify["overall_pass"] is False
        # The two canonical files exist and agree.
        raw = json.load(open(os.path.join(tmp_path, "logs", "final-preview-verify.json")))
        summary = json.load(open(os.path.join(tmp_path, "scorecard", "verify-summary.json")))
        gv.assert_consistent(summary, raw)


# ── B6 ADDITIONS: gate-tamper and MOCK-trust assertions ──────────────────────
#
# The diagnostic showed the gate could be bypassed by hand-writing ledgers.
# These tests assert that:
#   (a) a build whose gate output is tampered becomes FAILED (never VERIFIED),
#   (b) a trust:'MOCK' / MOCK-DO-NOT-SHIP run can never be presented as shippable.

class TestGateTamperBecomesFailedState:
    """dispatch_one reaching 'verified' requires the gate output to be clean.

    Feed a build whose canonical verify output is tampered (summary.overall_pass
    flipped from False to True by hand) and assert the task becomes FAILED, not
    VERIFIED.  This tests the dispatcher's ability to re-validate the gate output
    rather than trusting the summary it reads from disk.

    If the dispatcher does not yet call a gate re-validator (B2 not landed), the
    test is skipped.
    """

    def test_tampered_gate_output_is_failed_not_verified(self, tmp_path):
        # Check whether the dispatcher supports a gate_validator injection.
        if not hasattr(disp, "dispatch_one") or "gate_validator" not in str(
            disp.dispatch_one.__code__.co_varnames
        ):
            pytest.skip(
                "dispatch_one does not yet accept gate_validator (B2 pending)"
            )

        pages = [{"step": "optin", "preview_url": "u1", "marker": "m"}]
        # The "honest" fetcher: page 500s → overall_pass = False.
        results = {"u1": {"ok": False, "http": 500, "marker_found": False, "url": "u1"}}

        def _fetch(url, marker):
            return results.get(url, {"ok": False, "http": None,
                                     "marker_found": False, "url": url})

        def _real_verifier(evidence_root, pgs, **kw):
            out = gv.verify_all(evidence_root, pgs, fetcher=_fetch, **kw)
            # Tamper the on-disk summary to claim overall_pass=True (the forgery).
            summary_path = out["summary_path"]
            forged = json.load(open(summary_path))
            forged["overall_pass"] = True        # the lie
            forged["passed"] = forged["total"]   # cover the counts
            forged["failed"] = 0
            with open(summary_path, "w") as f:
                json.dump(forged, f)
            return out

        def _gate_validator(summary_path, raw_path):
            """Re-derive from raw and reject if summary is more optimistic."""
            raw = json.load(open(raw_path))
            summary = json.load(open(summary_path))
            gv.assert_consistent(summary, raw)  # raises VerifyContradiction

        res = disp.dispatch_one(
            FAKE_TASK, str(tmp_path),
            builder=_builder_ok(pages=pages),
            verifier=_real_verifier,
            gate_validator=_gate_validator,
        )
        assert res.state == disp.STATE_FAILED, \
            "a tampered gate output must FAIL the build, not reach VERIFIED"
        assert "tamper" in res.reason.lower() or "contradiction" in res.reason.lower() \
               or "consistent" in res.reason.lower(), \
            f"reason must mention the contradiction; got: {res.reason!r}"


class TestMockTrustCannotShipAsVerified:
    """A run with trust:'MOCK' in the task or in the build output must never be
    presented as shippable/verified — it is test scaffolding only.

    The MOCK-DO-NOT-SHIP sentinel prevents a mock run from accidentally being
    promoted to a real build.  If the dispatcher does not yet check this flag,
    the test is skipped.
    """

    def test_mock_task_cannot_reach_verified(self, tmp_path):
        mock_task = dict(FAKE_TASK, trust="MOCK")
        if not hasattr(disp, "MOCK_DO_NOT_SHIP"):
            pytest.skip("MOCK_DO_NOT_SHIP sentinel not yet implemented (B2 pending)")

        res = disp.dispatch_one(
            mock_task, str(tmp_path),
            builder=_builder_ok(),
            verifier=_fake_verifier(True),
        )
        # A MOCK task must never reach STATE_VERIFIED (it is not shippable).
        assert res.state != disp.STATE_VERIFIED, \
            "a trust:'MOCK' task must not reach STATE_VERIFIED"

    def test_mock_sentinel_in_build_output_blocks_verified(self, tmp_path):
        """If the builder returns trust:'MOCK' in its output, the dispatcher must
        block the build from reaching STATE_VERIFIED."""
        if not hasattr(disp, "MOCK_DO_NOT_SHIP"):
            pytest.skip("MOCK_DO_NOT_SHIP sentinel not yet implemented (B2 pending)")

        def _mock_builder(task, root):
            os.makedirs(os.path.join(root, "funnel"), exist_ok=True)
            return {
                "pages": [{"step": "optin", "preview_url": "u", "marker": "m"}],
                "location_gate_ok": True,
                "duration_s": 5.0,
                "trust": disp.MOCK_DO_NOT_SHIP,  # the sentinel
            }

        res = disp.dispatch_one(
            FAKE_TASK, str(tmp_path),
            builder=_mock_builder,
            verifier=_fake_verifier(True),
        )
        assert res.state != disp.STATE_VERIFIED, \
            "a build with MOCK_DO_NOT_SHIP trust must not reach STATE_VERIFIED"


# ── STEP 0 template matcher injection + complete-funnel handoff ──────────────

class TestStep0AndFunnelHandoff:
    """STEP 0 matcher is an injected/advisory callable; it must run, never block, and
    its linked-automations must be persisted as the P4->P5 handoff on a verified build."""

    def test_injected_step0_runs_and_records_template_match(self, tmp_path):
        seen = {}

        def _step0(task, evidence_root):
            seen["called"] = True
            return {"decision": "USE_TEMPLATE",
                    "template_match": {"decision": "USE_TEMPLATE",
                                       "matched_template": "webinar-funnel"}}

        res = disp.dispatch_one(
            dict(FAKE_TASK), str(tmp_path), builder=_builder_ok(),
            verifier=_fake_verifier(True), step0_matcher=_step0)
        assert seen.get("called") is True
        assert res.state == disp.STATE_VERIFIED

    def test_step0_failure_never_blocks_the_build(self, tmp_path):
        def _boom_step0(task, evidence_root):
            raise RuntimeError("matcher exploded")

        res = disp.dispatch_one(
            dict(FAKE_TASK), str(tmp_path), builder=_builder_ok(),
            verifier=_fake_verifier(True), step0_matcher=_boom_step0)
        # advisory glue — a matcher crash is recorded but the build still verifies
        assert res.state == disp.STATE_VERIFIED

    def test_linked_automations_become_skill44_handoff_artifact(self, tmp_path):
        # A task carrying linked_automations (as STEP 0 would attach) must, on a verified
        # build, write routing/skill44-handoff.json with the build_now automations.
        task = dict(FAKE_TASK)
        task["funnel_template_id"] = "follow-up-funnel"
        task["linked_automations"] = {
            "found": True,
            "automations": [
                {"automation_id": "soap-opera-sequence", "category": "sales-close-sequences",
                 "build_now": True},
                {"automation_id": "seinfeld-daily-sequence", "category": "sales-close-sequences",
                 "build_now": False},
            ],
        }
        res = disp.dispatch_one(
            task, str(tmp_path), builder=_builder_ok(), verifier=_fake_verifier(True))
        assert res.state == disp.STATE_VERIFIED
        handoff_path = os.path.join(tmp_path, "routing", "skill44-handoff.json")
        assert os.path.isfile(handoff_path)
        handoff = json.load(open(handoff_path))
        assert handoff["funnel_template_id"] == "follow-up-funnel"
        ids = [a["automation_id"] for a in handoff["to_build"]]
        assert ids == ["soap-opera-sequence"]            # only build_now=True
        assert handoff["mandatory"] is False


# ── FAB-QC build-quality gate (>= 8.5) wired into the verified verdict ───────

class TestFabQcGate:
    """The FAB-QC overlay is BINDING when the build emits evidence, a NO-OP otherwise."""

    def _write_fab_evidence(self, root, *, placeholder: bool):
        os.makedirs(os.path.join(root, "routing"), exist_ok=True)
        os.makedirs(os.path.join(root, "build"), exist_ok=True)
        os.makedirs(os.path.join(root, "scorecard"), exist_ok=True)
        # template stored alongside, referenced relatively from routing/
        tmpl = {"pageStructure": [{"page": "optin", "blocks": ["hero"]}],
                "copyFramework": {"primaryPersona": "Russell Brunson"}, "books": ["DotCom Secrets"]}
        with open(os.path.join(root, "tmpl.json"), "w") as f:
            json.dump(tmpl, f)
        with open(os.path.join(root, "routing", "match-decision.json"), "w") as f:
            json.dump({"matched_template_id": "squeeze-page", "template_path": "../tmpl.json",
                       "intent_mode": "HANDS_OFF_DO_IT_ALL", "flex_decision": "USE_TEMPLATE",
                       "funnel_template_id": "squeeze-page"}, f)
        hero = "[HEADLINE]" if placeholder else "Get the free funnel swipe file and grow your list today"
        with open(os.path.join(root, "build", "fab-artifact.json"), "w") as f:
            json.dump({"pages": [{"copy": {"hero": hero}}]}, f)
        with open(os.path.join(root, "persona-selection-log.md"), "w") as f:
            f.write("selected_persona: russell-brunson\n")

    def test_subthreshold_fab_downgrades_to_failed(self, tmp_path):
        self._write_fab_evidence(str(tmp_path), placeholder=True)  # surviving [HEADLINE] -> D2 hard miss
        res = disp.dispatch_one(
            dict(FAKE_TASK), str(tmp_path), builder=_builder_ok(), verifier=_fake_verifier(True))
        assert res.state == disp.STATE_FAILED
        assert "FAB-QC GATE" in res.reason
        rec = json.load(open(os.path.join(tmp_path, "routing", "task-record.json")))
        assert rec["fab_qc"]["ran"] is True and rec["fab_qc"]["passed"] is False

    def test_passing_fab_stays_verified(self, tmp_path):
        self._write_fab_evidence(str(tmp_path), placeholder=False)
        res = disp.dispatch_one(
            dict(FAKE_TASK), str(tmp_path), builder=_builder_ok(), verifier=_fake_verifier(True))
        assert res.state == disp.STATE_VERIFIED
        rec = json.load(open(os.path.join(tmp_path, "routing", "task-record.json")))
        assert rec["fab_qc"]["ran"] is True and rec["fab_qc"]["passed"] is True

    def test_no_fab_evidence_is_a_noop(self, tmp_path):
        # No match-decision/fab-artifact -> overlay is a no-op, build still verifies.
        res = disp.dispatch_one(
            dict(FAKE_TASK), str(tmp_path), builder=_builder_ok(), verifier=_fake_verifier(True))
        assert res.state == disp.STATE_VERIFIED
        rec = json.load(open(os.path.join(tmp_path, "routing", "task-record.json")))
        assert rec["fab_qc"]["ran"] is False


# ── FAB-ARTIFACT PRODUCER (D4): the gate fires on a REAL build, not a hand fixture ──
#
# These prove the D4 closure: NOTHING hand-writes build/fab-artifact.json here. STEP 0
# writes routing/match-decision.json (a real receipt), the injected builder returns the
# pages it built WITH the copy it wrote, and the dispatcher's PRODUCER normalises that
# real build result into build/fab-artifact.json so the FAB-QC gate genuinely scores it.

class TestFabArtifactProducer:
    """The dispatcher emits build/fab-artifact.json from the real build result so FAB-QC fires."""

    @staticmethod
    def _step0_writes_receipt(pages, *, persona="Russell Brunson", flex="USE_TEMPLATE"):
        """An injected STEP 0 that writes a real routing/match-decision.json + matched template
        (exactly as funnel_matcher.step0_match does) and mutates the task to a template plan.
        It does NOT write build/fab-artifact.json — that is the dispatcher's job to prove."""
        def _s0(task, evidence_root):
            routing = os.path.join(evidence_root, "routing")
            os.makedirs(routing, exist_ok=True)
            tmpl = {"pageStructure": [{"page": n, "blocks": ["hero"]} for n in pages],
                    "copyFramework": {"primaryPersona": persona}, "books": ["DotCom Secrets"]}
            with open(os.path.join(routing, "matched-template.json"), "w") as f:
                json.dump(tmpl, f)
            with open(os.path.join(routing, "match-decision.json"), "w") as f:
                json.dump({"matched_template_id": "squeeze-page",
                           "template_path": "matched-template.json",
                           "intent_mode": "HANDS_OFF_DO_IT_ALL", "flex_decision": flex}, f)
            task["pages"] = [{"name": n} for n in pages]
            return {"decision": flex,
                    "template_match": {"decision": flex, "matched_template": "squeeze-page"}}
        return _s0

    @staticmethod
    def _builder_with_copy(copy):
        """A builder that returns the pages it built WITH the copy it wrote (the contract that
        lets the producer emit a scoreable artifact)."""
        def _b(task, evidence_root):
            os.makedirs(os.path.join(evidence_root, "funnel"), exist_ok=True)
            # the copy step logs which persona it used (build evidence FAB-QC D4 reads)
            with open(os.path.join(evidence_root, "persona-selection-log.md"), "w") as f:
                f.write("selected_persona: russell-brunson\nrationale: matched template voice\n")
            plan = task.get("pages") or [{"name": "Opt-In"}]
            built = [{"name": p.get("name", f"p{i}"), "preview_url": f"u{i}",
                      "marker": "m", "copy": dict(copy)} for i, p in enumerate(plan)]
            return {"pages": built, "location_gate_ok": True, "duration_s": 5.0}
        return _b

    def test_producer_emits_artifact_and_gate_fires_on_real_path(self, tmp_path):
        # NOTE: no build/fab-artifact.json is hand-written anywhere in this test.
        real_copy = {"hero": "Get the free funnel swipe file today and grow your email list fast",
                     "cta": "Enter your best email now to receive instant access to the download"}
        res = disp.dispatch_one(
            dict(FAKE_TASK), str(tmp_path),
            builder=self._builder_with_copy(real_copy),
            verifier=_fake_verifier(True, passed=2, total=2),
            step0_matcher=self._step0_writes_receipt(["Opt-In", "Thank You"]))
        # the dispatcher's PRODUCER created the artifact from the real build (it did not pre-exist)
        art_path = os.path.join(tmp_path, "build", "fab-artifact.json")
        assert os.path.isfile(art_path), "dispatcher must emit build/fab-artifact.json from the build"
        art = json.load(open(art_path))
        assert art["generated_by"] == "fab_artifact.build_funnel_artifact"
        assert art["pages"][0]["copy"]["hero"].startswith("Get the free funnel swipe")
        # the gate RAN against that produced artifact (not a fixture) and passed
        rec = json.load(open(os.path.join(tmp_path, "routing", "task-record.json")))
        assert rec["fab_artifact"]["emitted"] is True
        assert rec["fab_qc"]["ran"] is True and rec["fab_qc"]["passed"] is True
        assert res.state == disp.STATE_VERIFIED

    def test_producer_thin_copy_makes_the_gate_fail(self, tmp_path):
        # The builder echoes placeholder copy -> the produced artifact trips FAB-QC D2 -> FAILED.
        res = disp.dispatch_one(
            dict(FAKE_TASK), str(tmp_path),
            builder=self._builder_with_copy({"hero": "[HEADLINE]", "cta": "TODO"}),
            verifier=_fake_verifier(True, passed=2, total=2),
            step0_matcher=self._step0_writes_receipt(["Opt-In", "Thank You"]))
        assert res.state == disp.STATE_FAILED
        assert "FAB-QC GATE" in res.reason
        rec = json.load(open(os.path.join(tmp_path, "routing", "task-record.json")))
        assert rec["fab_artifact"]["emitted"] is True       # producer still emitted it
        assert rec["fab_qc"]["ran"] is True and rec["fab_qc"]["passed"] is False

    def test_real_funnel_matcher_receipt_then_producer_fires(self, tmp_path):
        """End-to-end with the REAL funnel_matcher against the REAL catalog: the matcher writes
        routing/match-decision.json, the builder echoes copy, and the dispatcher's producer emits
        the artifact so the gate RUNS — proving the wiring on the genuine matcher path."""
        import funnel_matcher as fm
        catalog_root = os.path.normpath(os.path.join(
            os.path.dirname(__file__), "..", "funnel-templates"))
        if not os.path.isdir(catalog_root):
            import pytest
            pytest.skip("funnel-templates catalog not present")

        def _s0(task, evidence_root):
            return fm.step0_match(task, evidence_root, catalog_root=catalog_root)

        real_copy = {"hero": "Discover the proven framework that turns cold visitors into buyers",
                     "cta": "Claim your free copy now before this limited-time bonus disappears"}
        task = dict(FAKE_TASK, just_do_it=True,
                    brief="just build the full lead squeeze page opt-in funnel for my list")
        res = disp.dispatch_one(
            task, str(tmp_path),
            builder=self._builder_with_copy(real_copy),
            verifier=_fake_verifier(True, passed=2, total=2),
            step0_matcher=_s0)
        # the real matcher wrote the receipt; the dispatcher's producer wrote the artifact
        assert os.path.isfile(os.path.join(tmp_path, "routing", "match-decision.json"))
        assert os.path.isfile(os.path.join(tmp_path, "build", "fab-artifact.json"))
        rec = json.load(open(os.path.join(tmp_path, "routing", "task-record.json")))
        assert rec["fab_artifact"]["emitted"] is True
        assert rec["fab_qc"]["ran"] is True       # the >=8.5 gate genuinely fired on the real path


# ---------------------------------------------------------------------------
# P2-4: RateGovernor + SessionKeepalive (rate-limit governor + session warmth)
# ---------------------------------------------------------------------------
class _FakeClock:
    """Deterministic monotonic clock whose sleeper advances it (no real wait)."""

    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += float(seconds)


class TestRateGovernor:
    """The governor only ever DELAYS write actions; it never speeds a build up."""

    def test_save_spacing_min_6s(self):
        fc = _FakeClock()
        gov = disp.RateGovernor(clock=fc, sleeper=fc.advance)
        assert gov.before("save") == 0.0                       # first save: no wait
        w2 = gov.before("save")                                # immediate 2nd save
        assert w2 >= disp.MIN_SAVE_INTERVAL_S == 6.0
        # the sleeper advanced the clock by the wait, so the 2nd save is now the
        # last allowed; a THIRD immediate save must again wait the full interval.
        w3 = gov.before("save")
        assert w3 >= disp.MIN_SAVE_INTERVAL_S
        # once enough wall-clock genuinely elapses, no wait is imposed.
        fc.advance(disp.MIN_SAVE_INTERVAL_S)
        assert gov.before("save") == 0.0

    def test_publish_spacing_min_15s(self):
        fc = _FakeClock()
        gov = disp.RateGovernor(clock=fc, sleeper=fc.advance)
        assert gov.before("publish") == 0.0
        assert gov.before("publish") >= disp.MIN_PUBLISH_INTERVAL_S == 15.0

    def test_save_and_publish_intervals_are_independent(self):
        fc = _FakeClock()
        gov = disp.RateGovernor(clock=fc, sleeper=fc.advance)
        gov.before("save")
        # a publish right after a save is NOT throttled by the save interval
        assert gov.before("publish") == 0.0

    def test_429_default_cooldown_when_no_header(self):
        fc = _FakeClock()
        gov = disp.RateGovernor(clock=fc, sleeper=fc.advance)
        assert gov.note_429(None) == disp.DEFAULT_429_COOLDOWN_S == 30.0

    def test_429_honors_retry_after_when_larger(self):
        fc = _FakeClock()
        gov = disp.RateGovernor(clock=fc, sleeper=fc.advance)
        assert gov.note_429("45") == 45.0                      # header > floor honored

    def test_429_floors_small_retry_after(self):
        fc = _FakeClock()
        gov = disp.RateGovernor(clock=fc, sleeper=fc.advance)
        assert gov.note_429("5") == disp.DEFAULT_429_COOLDOWN_S  # floored at 30s

    def test_429_malformed_header_falls_back_to_floor(self):
        fc = _FakeClock()
        gov = disp.RateGovernor(clock=fc, sleeper=fc.advance)
        assert gov.note_429("not-a-number") == disp.DEFAULT_429_COOLDOWN_S

    def test_429_cooldown_blocks_next_action(self):
        fc = _FakeClock()
        gov = disp.RateGovernor(clock=fc, sleeper=fc.advance)
        gov.note_429("30")                                     # cooldown until t=30
        w = gov.before("save")                                 # next action must wait the cooldown
        assert w >= disp.DEFAULT_429_COOLDOWN_S

    def test_defaults_mirror_gates_json(self):
        import json as _json
        gates = _json.load(open(os.path.join(_TOOLS_DIR, "gates.json")))
        rg = gates["rate_limit_governor"]
        assert rg["min_save_interval_s"] == disp.MIN_SAVE_INTERVAL_S
        assert rg["min_publish_interval_s"] == disp.MIN_PUBLISH_INTERVAL_S
        assert rg["default_429_cooldown_s"] == disp.DEFAULT_429_COOLDOWN_S
        assert (rg["session_keepalive"]["interval_minutes"] * 60
                == disp.SESSION_KEEPALIVE_INTERVAL_S)


class TestSessionKeepalive:
    """due() fires at most once per interval; never a navigate/reload (scheduler only)."""

    def test_not_due_before_interval(self):
        kc = _FakeClock()
        ka = disp.SessionKeepalive(clock=kc)
        assert ka.due() is False
        kc.advance(disp.SESSION_KEEPALIVE_INTERVAL_S - 1)
        assert ka.due() is False

    def test_due_exactly_at_interval(self):
        kc = _FakeClock()
        ka = disp.SessionKeepalive(clock=kc)
        kc.advance(disp.SESSION_KEEPALIVE_INTERVAL_S)
        assert ka.due() is True
        assert ka.due() is False          # resets — not due again immediately

    def test_interval_is_30_minutes(self):
        assert disp.SESSION_KEEPALIVE_INTERVAL_S == 30 * 60
