#!/usr/bin/env python3
"""Seam test: the real Skill 49 plan, through Skill 50's launch adapter and
email emitter, into Skill 44's launch-c plan reader.

Each skill's own verify.sh is green on its own fixtures; none of them proves
the three agree. This runs the REAL producer end to end and asserts that no
step refuses and no blocking warning is raised:

  1. 49  launch_intake: answers.elevation.json -> assemble_plan (the launch plan)
  2. 50  launch_intake_adapter.adapt_launch_plan  (the email-count gate lives here)
  3. 50  emit_build_plan.build_plan               (one DRAFT build plan per sequence)
  4. 44  launch-c/plan_reader.py                  (launch plan + every build plan)

It was red at origin/main (the planner asks for 4 pre-launch emails, the family
registry fixes 5); it goes green when Skill 49 plans the registry's counts.
It is the producer-through-consumer test the issue 58 class needs.

Hermetic: no network, no provider call, no credential, writes only to a temp dir.
Run: python3 -m pytest 50-email-engine/tests/test_seam_49_to_44.py -q
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
REPO = SKILL.parent
TOOLS = SKILL / "tools"
READER = (REPO / "44-convert-and-flow-operator" / "automation-templates"
          / "launch-c" / "plan_reader.py")
ANSWERS = REPO / "shared-utils" / "client_intake" / "fixtures" / "answers.elevation.json"
WORKER = "worker:seam-test"
PRE_LAUNCH_WINDOW = "2026-10-01T00:00:00-04:00"  # before every send, so nothing is "late"


def _load(name, path, *extra_paths):
    for extra in extra_paths:
        if str(extra) not in sys.path:
            sys.path.insert(0, str(extra))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


intake = _load("seam_launch_intake", REPO / "49-signature-funnel" / "scripts" / "launch_intake.py",
               REPO / "49-signature-funnel" / "scripts", REPO / "shared-utils" / "client_intake")
adapter = _load("seam_launch_intake_adapter", TOOLS / "launch_intake_adapter.py", TOOLS)
emitter = _load("seam_emit_build_plan", TOOLS / "emit_build_plan.py", TOOLS)
profiles = _load("seam_launch_profiles", TOOLS / "launch_profiles.py", TOOLS)
reader = _load("seam_plan_reader", READER)


def _facts(launch):
    offer = launch["offers"][0]["display_name"]
    provenance = {"state": "provided", "source_kind": "owner",
                  "source_ref": "seam fixture", "approval_ref": "APPR-SEAM"}
    brand = {"brand_ref": "brand:seam", "brand_hash": "0" * 64,
             "founder_name": "Elevation Coaching Co", "brand_voice": "bold, warm, direct",
             "provenance": dict(provenance)}
    landing = {"launch_id": launch["launch_id"], "offer": offer,
               "landing": {
                   "section_5_why": "After 6 weeks a clear offer.",
                   "section_6_who": {"audience": "new coaches", "pains": [
                       {"ref": "p1", "pain": "No steady income"},
                       {"ref": "p2", "pain": "Feeling like a fraud"},
                       {"ref": "p3", "pain": "Family asking for a real job"}]},
                   "section_8_what_is_inside": ["12 video lessons"],
                   "section_9_how_it_works": ["weekly calls"],
                   "section_10_support": ["email support"],
                   "round_timing": {"ref": "r", "fact": "rolling 30-day rounds"},
                   "testimonial_evidence": None},
               "provenance": dict(provenance)}
    return brand, landing


def _emails(kind, brief):
    """One authored sequence for a brief, exactly as long as its family fixes."""
    family = profiles.families()[kind]
    emails = []
    for slot in range(1, family["email_count"] + 1):
        emails.append({
            "e_slot": slot,
            "framework": family["framework_map"][str(slot)],
            "objective": brief["answers"]["objective"],
            "subjects": ["Subject A %d" % slot, "Subject B %d" % slot],
            "previews": ["Preview A %d" % slot, "Preview B %d" % slot][:family["preview_count"]],
            "body": "{{contact.first_name}},\n\nBody %d.\n\nElevation Coaching Co" % slot,
            "ctas": ["[Go ->]"]})
    return {"sequence_type": family["profile"], "profile": family["profile"],
            "sequence_id": family["sequence_id"], "founder_name": "Elevation Coaching Co",
            "emails": emails}


class Seam49To50To44(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _producer_output(self):
        """49's real intake, approved: (session, approval)."""
        session = intake.new_session(
            tenant_id="tenant-seam", location_id="loc-seam", launch_id="elevation-2026-11",
            client_identity_ref="client:seam", brand_ref="brand:seam", brand_hash="0" * 64,
            test_only=True)
        intake.ingest_answers(session, json.loads(ANSWERS.read_text(encoding="utf-8")))
        # No intake question produces the access destination (an operator fact).
        session["answers"]["launch.access_url"] = {
            "value": "https://example.test/access", "state": "provided",
            "source_ref": "test:seam-access", "question_id": None}
        result = intake.assemble_plan(session)
        self.assertNotEqual(result.get("state"), "awaiting_missing_fact", result.get("missing"))
        from datetime import datetime, timedelta, timezone
        approval = {"schema_version": "1.0", "approval_id": "APPR-SEAM",
                    "kind": "launch_plan_build", "plan_hash": session["plan_hash"],
                    "client_identity": session["client_identity_ref"],
                    "source_message_ref": "msg-seam", "scope": ["launch_plan_build"],
                    "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                    "revoked": False,
                    "verification_class": "recorded_consent_not_cryptographically_sealed"}
        intake.approve(session, approval, worker_identity_ref=WORKER)
        return session, approval

    def test_real_49_plan_flows_through_50_into_44_without_refusal_or_blocking_warning(self):
        session, approval = self._producer_output()
        plan = session["launch_plan"]
        self.assertIsInstance(plan, dict)
        launch = session["plan"]
        brand, landing = _facts(launch)

        # 49 -> 50: the adapter's count gate (_launch_sequences) must accept 49's counts.
        try:
            briefs = adapter.adapt_launch_plan(
                session, launch, approval, brand, landing, plan, worker_identity_ref=WORKER)
        except adapter.Refusal as exc:
            self.fail("Skill 50 refused the real Skill 49 launch plan: %s" % exc)
        planned = [u["id"] for u in plan["email_sequences"] if u.get("provider") == "skill50"]
        self.assertEqual([b["sequence_id"] for b in briefs], planned)

        # 50: one valid DRAFT build plan per planned sequence, as long as the plan says.
        counts = {u["id"]: u["email_count"] for u in plan["email_sequences"]}
        sequence_map = {}
        for item in briefs:
            doc = emitter.build_plan(item["brief"], _emails(item["kind"], item["brief"]))
            self.assertEqual(emitter.validate_plan(doc), [], item["sequence_id"])
            emails = sum(1 for key, wf in doc.items() if key not in ("folder", "_meta")
                         for step in wf["templates"] if step.get("type") == "email")
            self.assertEqual(emails, counts[item["sequence_id"]], item["sequence_id"])
            path = self.dir / ("build-%s.json" % item["sequence_id"])
            path.write_text(json.dumps(doc), encoding="utf-8")
            sequence_map[item["sequence_id"]] = str(path)

        # 50 -> 44: the reader reads the same plan and every build plan.
        for page in plan.get("pages", []):
            # Page URLs are a later stage (pages not built yet); without one the
            # reader blocks on page_url by design, which is not a seam defect.
            page["url"] = page.get("url") or "https://example.test/%s" % page["id"]
        for text_set in plan.get("text_sets", []):
            text_set.setdefault("messages", 3)
        plan_path = self.dir / "launch-plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        map_path = self.dir / "sequence-map.json"
        map_path.write_text(json.dumps(sequence_map), encoding="utf-8")
        out = self.dir / "automation-builds.json"
        argv = ["--launch-plan", str(plan_path), "--sequence-map", str(map_path),
                "--out", str(out), "--now", PRE_LAUNCH_WINDOW]
        for path in sequence_map.values():
            argv += ["--build-plan", path]
        rc = reader.main(argv)
        document = json.loads(out.read_text(encoding="utf-8")) if out.exists() else None
        self.assertIsNotNone(document, "Skill 44's reader refused the plan (rc=%s)" % rc)
        blocking = [w for w in document["warnings"] if w.get("blocking")]
        self.assertEqual(blocking, [], "blocking warnings: %s" % blocking)
        self.assertEqual(document["unused_build_plan_workflows"], [])
        # rc 4 only means some automation is blocked; this seam owns the reasons that
        # come from the plan -> adapter -> emitter -> reader hand-off itself: a count
        # that disagrees, a build plan that did not bind to its sequence, metadata the
        # build plan failed to carry. (The reader exits 2 or 3 on a refusal.)
        self.assertIn(rc, (0, 4), "Skill 44's reader refused the plan (rc=%s)" % rc)
        for build in document["builds"]:
            for reason in build["blocked_by"]:
                self.assertFalse(reason.startswith("email_count:"), (build["id"], reason))
                self.assertNotIn(reason, planned, (build["id"], "build plan did not bind"))
                self.assertNotIn(reason, ("lifecycle", "eligibility", "sender"), build["id"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
