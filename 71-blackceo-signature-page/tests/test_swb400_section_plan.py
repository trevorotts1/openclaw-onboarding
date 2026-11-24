#!/usr/bin/env python3
"""SWB-400 item 2: the wireframe section plan is written by a tool from tool inputs, and a stale one is caught.

Trevor's diagnosis (2026-11-24): <stage>/section-plan.json was typed by hand on Nov 21 and never regenerated: its
section 2 note still described a table of Paid, Pending and Failed rows, section 3 a WHAT IT UNLOCKS bar, and its
hero slot was 1:1 where the request's was 4:3. No tool wrote it and validate_wireframe.py only checked its shape.

  - scripts/write_section_plan.py builds the plan ONLY from the stage's production request, the copy manifest, the
    closed font map, the closed image inventory and the wireframe spec; validates it with the wireframe validator's
    own checks; replaces the file atomically; the first section carries the request's sha256 in `plan_header`;
  - the plan states what the sheet prints: the request's section names and printed behavior notes, the font map's
    sizes, the closed inventory's slot id, ratio and treatment;
  - validate_wireframe.py gains a staleness check (a TIGHTENING): a differing name, note, ratio or slot count, a
    missing header or a header whose sha is not the request's is a named failure; no request means no check;
  - a request that plans another slot ratio than the closed inventory is refused (the spec said 4:3, 1:1 is closed).
No paid call is made.
"""
import contextlib
import copy
import io
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

os.environ["SKILL71_FIXTURE_RUN"] = "1"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
from test_page_role_thank_you import PY, RunCase, SPEC, builder  # noqa: E402
from test_swb400_heading_roles import HEADINGS, ITEM, PAYMENT, manuscript, public_copy  # noqa: E402
from test_section_count import REAL_MODEL  # noqa: E402
from test_swb310_floor_and_slot import realistic_prose  # noqa: E402
import section_plan  # noqa: E402
import wireframe_spec as w  # noqa: E402

WRITER = SCRIPTS / "write_section_plan.py"
VALIDATOR = SCRIPTS / "validate_wireframe.py"
STAGES = ("desktop-wireframe", "mobile-tablet")


def typography(h2=44):
    def row(element, role, d, t, m, lh):
        return {"element": element, "role": role, "sizes": {
            "desktop": {"px": d, "line_height": lh}, "tablet": {"px": t, "line_height": lh},
            "mobile": {"px": m, "line_height": lh}}}
    return [row("hero_headline", "display", 72, 56, 38, 1.02), row("section_heading", "display", h2, 36, 28, 1.1),
            row("body", "body", 21, 20, 18, 1.6), row("cta_label", "accent", 19, 18, 17, 1.0)]


FONT_MAP = {"fonts": {"display": "Playfair Display", "body": "Source Sans 3", "accent": "Source Sans 3"},
            "typography": typography()}
INVENTORY = {"images": [{"id": "IMG-001", "slot_id": "TY-IMG-01", "section_id": "1", "aspect_ratio": "1:1",
                         "art_direction": "warm celebration of the decision, a confident moment for the buyer, "
                                          "never a product pitch",
                         "shape": "rect", "treatment": "overlay-light", "slot_name": "TY-IMG-01"}]}


class PlanCase(RunCase):
    def setUp(self):
        super().setUp()
        run = self.run
        (run / "copy" / "internal-manuscript.md").write_text(manuscript(), encoding="utf-8")
        (run / "copy" / "public-copy.md").write_text(public_copy(), encoding="utf-8")
        (run / "copy" / "copy-manifest.json").write_text(json.dumps(
            {"sections": [{"id": i, "name": f"S{i}"} for i in "12345"]}), encoding="utf-8")
        self.put("font-action-plan/font-map.json", FONT_MAP)
        self.put("desktop-wireframe/image-inventory.json", INVENTORY)

    def put(self, rel, data):
        path = self.run / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return path

    def request_for(self, stage):
        request = self.build(stage=stage, model=REAL_MODEL, prose=realistic_prose())
        path = self.put("production-request.json", request)
        return request, path

    def write(self, stage, *extra):
        self.request_for(stage)
        return subprocess.run([PY, str(WRITER), str(self.run), "--stage", stage, *extra],
                              capture_output=True, text=True)

    def plan(self, stage):
        return json.loads((self.run / stage / "section-plan.json").read_text(encoding="utf-8"))


class WriterTests(PlanCase):
    def test_the_plan_is_built_from_the_request_the_inventory_and_the_font_map(self):
        for stage in STAGES:
            proc = self.write(stage)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            plan = self.plan(stage)
            request = json.loads((self.run / "production-request.json").read_text(encoding="utf-8"))
            self.assertEqual([s["section_id"] for s in plan], list("12345"))
            self.assertEqual([s["section_number"] for s in plan], [1, 2, 3, 4, 5])
            for entry, section in zip(plan, request["sections"]):
                self.assertEqual(entry["section_name"], section["section_name"], stage)
                self.assertEqual(entry["behavior_notes"], w.printed_note(stage, section, request), stage)
            two = plan[1]
            self.assertEqual(two["section_name"], "Order summary")
            self.assertEqual(two["behavior_notes"], SPEC["sections"][1]["note"])
            self.assertEqual(two["image_slot_ids"], [])
            self.assertEqual(plan[0]["image_slot_ids"], ["IMG-001"])
            label = plan[0]["slot_labels"]["IMG-001"]
            self.assertEqual((label["aspect_ratio"], label["treatment"], label["slot_name"]),
                             ("1:1", "overlay-light", "TY-IMG-01"))
            self.assertEqual(plan[0]["header_strip"], {"page_width_px": 1440 if stage == "desktop-wireframe" else 390,
                                                       "content_width_px": 1200 if stage == "desktop-wireframe" else 342})
            self.assertEqual(plan[0]["plan_header"]["request_sha256"],
                             section_plan.sha256_file(self.run / "production-request.json"))
            self.assertNotIn("plan_header", plan[1])

    def test_nothing_the_copy_dropped_survives_in_the_plan(self):
        for stage in STAGES:
            self.assertEqual(self.write(stage).returncode, 0)
            blob = json.dumps(self.plan(stage))
            for gone in ("Real table", "Paid, Pending and Failed", "WHAT IT UNLOCKS", "grey bars", "grey placeholder"):
                self.assertNotIn(gone, blob, (stage, gone))

    def test_type_specs_are_the_font_maps_sizes_per_stage(self):
        self.assertEqual(self.write("desktop-wireframe").returncode, 0)
        specs = self.plan("desktop-wireframe")[0]["type_specs"]
        self.assertEqual(specs, {"h1": "Playfair Display 72px / 1.02 desktop, 56px / 1.02 tablet",
                                 "h2": "Playfair Display 44px / 1.1 desktop, 36px / 1.1 tablet",
                                 "body": "Source Sans 3 21px / 1.6 desktop, 20px / 1.6 tablet",
                                 "cta": "Source Sans 3 19px / 1 desktop, 18px / 1 tablet"})
        self.assertEqual(self.write("mobile-tablet").returncode, 0)
        self.assertEqual(self.plan("mobile-tablet")[0]["type_specs"]["h2"],
                         "Playfair Display 36px / 1.1 tablet, 28px / 1.1 mobile")

    def test_a_hand_edit_is_replaced_and_a_rewrite_is_byte_for_byte_stable(self):
        self.assertEqual(self.write("desktop-wireframe").returncode, 0)
        target = self.run / "desktop-wireframe" / "section-plan.json"
        first = target.read_bytes()
        stale = json.loads(first)
        stale[1]["behavior_notes"] = "Real table, never an image of a receipt; status labels Paid, Pending and Failed"
        target.write_text(json.dumps(stale), encoding="utf-8")
        proc = subprocess.run([PY, str(WRITER), str(self.run), "--stage", "desktop-wireframe"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("replaced a differing plan", proc.stdout)
        self.assertEqual(target.read_bytes(), first)
        self.assertEqual([p.name for p in target.parent.iterdir() if p.name.endswith(".tmp")], [])

    def test_check_only_writes_nothing_and_says_what_is_on_disk(self):
        proc = self.write("desktop-wireframe", "--check-only")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("(absent on disk)", proc.stdout)
        self.assertFalse((self.run / "desktop-wireframe" / "section-plan.json").exists())
        self.assertEqual(self.write("desktop-wireframe").returncode, 0)
        proc = subprocess.run([PY, str(WRITER), str(self.run), "--stage", "desktop-wireframe", "--check-only"],
                              capture_output=True, text=True)
        self.assertIn("(current on disk)", proc.stdout)


class RefusalTests(PlanCase):
    def refused(self, stage="desktop-wireframe", needle=""):
        proc = subprocess.run([PY, str(WRITER), str(self.run), "--stage", stage], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("REFUSED", proc.stdout)
        self.assertIn(needle, proc.stdout)
        return proc

    def test_a_refusal_leaves_the_plan_on_disk_untouched(self):
        self.assertEqual(self.write("desktop-wireframe").returncode, 0)
        target = self.run / "desktop-wireframe" / "section-plan.json"
        before = target.read_bytes()
        (self.run / "desktop-wireframe" / "image-inventory.json").unlink()
        self.refused(needle="image-inventory.json")
        self.assertEqual(target.read_bytes(), before)
        self.assertEqual([p.name for p in target.parent.iterdir() if "tmp" in p.name], [])

    def test_a_request_built_for_another_stage_is_refused(self):
        self.request_for("mobile-tablet")
        self.refused("desktop-wireframe", "was built for stage 'mobile-tablet'")

    def test_a_request_that_plans_another_ratio_than_the_closed_inventory_is_refused(self):
        request, _ = self.request_for("desktop-wireframe")
        request["sections"][0]["slots"][0]["aspect_ratio"] = "4:3"  # what the spec said before 1.3.54
        self.put("production-request.json", request)
        proc = self.refused(needle="the closed image inventory says 1:1")
        self.assertIn("never the plan", proc.stdout)
        self.assertFalse((self.run / "desktop-wireframe" / "section-plan.json").exists())

    def test_a_request_slot_the_inventory_does_not_hold_and_an_unplaced_inventory_slot_are_refused(self):
        self.request_for("desktop-wireframe")
        inventory = copy.deepcopy(INVENTORY)
        inventory["images"][0].update(id="IMG-009", slot_id="OTHER", slot_name="OTHER")
        self.put("desktop-wireframe/image-inventory.json", inventory)
        self.refused(needle="has no slot by that id or name")
        inventory = copy.deepcopy(INVENTORY)
        inventory["images"].append({"id": "IMG-002", "slot_id": "TY-IMG-02", "section_id": "3", "aspect_ratio": "1:1",
                                    "art_direction": "an extra image the request never places", "treatment": "split"})
        self.put("desktop-wireframe/image-inventory.json", inventory)
        self.refused(needle="that no section of the request places")

    def test_a_declared_treatment_that_differs_from_the_inventory_is_refused(self):
        request, _ = self.request_for("desktop-wireframe")
        request["sections"][0]["slots"][0]["treatment"] = "mask-circle"
        self.put("production-request.json", request)
        self.refused(needle="closed inventory says 'overlay-light'")

    def test_the_manifest_and_the_font_map_are_required_and_complete(self):
        self.request_for("desktop-wireframe")
        self.put("copy/copy-manifest.json", {"sections": [{"id": i} for i in "1234"]})
        self.refused(needle="copy manifest")
        self.put("copy/copy-manifest.json", {"sections": [{"id": i} for i in "12345"]})
        broken = copy.deepcopy(FONT_MAP)
        broken["typography"] = [r for r in broken["typography"] if r["element"] != "section_heading"]
        self.put("font-action-plan/font-map.json", broken)
        self.refused(needle="section_heading")
        (self.run / "font-action-plan" / "font-map.json").unlink()
        self.refused(needle="closed font plan")

    def test_no_request_is_a_refusal(self):
        self.refused(needle="build the stage's request first")


class StalenessTests(PlanCase):
    def written(self, stage="desktop-wireframe"):
        self.assertEqual(self.write(stage).returncode, 0)
        return self.plan(stage)

    def stale(self, plan, stage="desktop-wireframe"):
        return section_plan.staleness_failures(plan, stage, self.run)

    def test_a_fresh_plan_has_no_staleness_failure(self):
        for stage in STAGES:
            self.assertEqual(self.stale(self.written(stage), stage), [], stage)

    def test_a_differing_name_note_ratio_or_slot_count_is_named(self):
        plan = self.written()
        cases = [("section name", lambda p: p[1].update(section_name="What you purchased"), "section 2 is named"),
                 ("behavior note", lambda p: p[1].update(behavior_notes="Real table, never an image of a receipt"),
                  "section 2 behavior note"),
                 ("slot ratio", lambda p: p[0]["slot_labels"]["IMG-001"].update(aspect_ratio="4:3"), "has ratio '4:3'"),
                 ("slot count", lambda p: p[0].update(image_slot_ids=[]), "places 0 image slot(s) in the plan but 1")]
        for label, change, needle in cases:
            broken = copy.deepcopy(plan)
            change(broken)
            lines = self.stale(broken)
            self.assertTrue(any(needle in l for l in lines), (label, lines))
            self.assertTrue(all(l.startswith("stale plan:") for l in lines), label)

    def test_a_missing_or_wrong_header_is_stale_and_no_request_means_no_check(self):
        plan = self.written()
        no_header = copy.deepcopy(plan)
        del no_header[0]["plan_header"]
        self.assertTrue(any("carries no plan_header" in l for l in self.stale(no_header)))
        wrong = copy.deepcopy(plan)
        wrong[0]["plan_header"]["request_sha256"] = "0" * 64
        self.assertTrue(any("was built from a request with sha256 000000000000" in l for l in self.stale(wrong)))
        # the request is rebuilt (a changed copy line): the plan written before it is now stale
        request = json.loads((self.run / "production-request.json").read_text(encoding="utf-8"))
        request["sections"][1]["copy"] += "\nOne more approved line."
        self.put("production-request.json", request)
        self.assertTrue(any("was built from a request with sha256" in l for l in self.stale(plan)))
        (self.run / "production-request.json").unlink()
        self.assertEqual(self.stale(no_header), [])  # nothing to compare against: judged as before

    def test_a_request_saved_for_the_stage_is_found_when_the_runner_has_moved_on(self):
        desktop = self.written("desktop-wireframe")
        saved = self.run / "production-request-desktop-wireframe.json"
        saved.write_bytes((self.run / "production-request.json").read_bytes())
        self.request_for("mobile-tablet")  # production-request.json is now the other stage's
        self.assertEqual(self.stale(desktop), [])
        stale = copy.deepcopy(desktop)
        stale[1]["section_name"] = "Order summary and payment"
        self.assertTrue(any("is named" in l for l in self.stale(stale)))

    def test_the_wireframe_validator_reports_the_stale_lines(self):
        plan = self.written()
        plan[1]["behavior_notes"] = "Real table, never an image of a receipt; status labels Paid, Pending and Failed"
        (self.run / "desktop-wireframe" / "section-plan.json").write_text(json.dumps(plan), encoding="utf-8")
        proc = subprocess.run([PY, str(VALIDATOR), str(self.run), "desktop-wireframe"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("- stale plan: section 2 behavior note", proc.stdout)
        # the fresh plan carries none of the stale lines (other failures, such as the absent slices, remain)
        self.assertEqual(self.write("desktop-wireframe").returncode, 0)
        proc = subprocess.run([PY, str(VALIDATOR), str(self.run), "desktop-wireframe"], capture_output=True, text=True)
        self.assertNotIn("stale plan", proc.stdout)


class RunnerTests(PlanCase):
    def test_the_runner_writes_the_plan_after_each_wireframe_request_and_only_checks_in_a_preview(self):
        import run_page_role_stages as runner
        calls = []
        original = runner.subprocess.run
        quiet = contextlib.redirect_stdout(io.StringIO())
        quiet.__enter__()
        self.addCleanup(quiet.__exit__, None, None, None)
        try:
            runner.subprocess.run = lambda argv: calls.append(list(map(str, argv))) or type("R", (), {"returncode": 0})()
            for preview in (True, False):
                calls.clear()
                (self.run / "production-request.json").write_text("{}", encoding="utf-8")
                self.assertTrue(runner.write_plan(self.run, "mobile-tablet", self.run / "production-request.json",
                                                  preview=preview))
                self.assertEqual(len(calls), 1)
                self.assertEqual(calls[0][1:5], [str(WRITER), str(self.run), "--stage", "mobile-tablet"])
                self.assertEqual("--check-only" in calls[0], preview)
                saved = self.run / "production-request-mobile-tablet.json"
                self.assertEqual(saved.exists(), not preview)  # a preview writes nothing into the run
                if saved.exists():
                    saved.unlink()
            # no closed inventory yet (a first pass): skipped, said once, never a failure
            (self.run / "desktop-wireframe" / "image-inventory.json").unlink()
            calls.clear()
            self.assertTrue(runner.write_plan(self.run, "desktop-wireframe", self.run / "production-request.json",
                                              preview=False))
            self.assertEqual(calls, [])
            # a failing writer stops the run
            self.put("desktop-wireframe/image-inventory.json", INVENTORY)
            runner.subprocess.run = lambda argv: type("R", (), {"returncode": 1})()
            self.assertFalse(runner.write_plan(self.run, "desktop-wireframe", self.run / "production-request.json",
                                               preview=False))
        finally:
            runner.subprocess.run = original


class SpecRatioTests(unittest.TestCase):
    def test_the_hero_slot_is_one_to_one_like_the_closed_inventory(self):
        slot = SPEC["sections"][0]["default_slots"][0]
        self.assertEqual((slot["slot_id"], slot["aspect_ratio"]), ("TY-IMG-01", "1:1"))
        note = next(d for d in SPEC["structure_approval"]["later_decisions"]
                    if d["decision"] == "hero_slot_ratio_is_the_closed_inventory_ratio")
        self.assertEqual(note["date"], "2026-11-24")
        self.assertIn("1:1", note["basis"])


if __name__ == "__main__":
    unittest.main()
