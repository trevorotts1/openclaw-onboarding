"""Update plan Item 32 tests: the signature page's funnel handoff contract.

Leg 2 (copy manifest CTA handoff types, enforced by
scripts/validate_copy_structure.py) and leg 3 (the page-side check,
scripts/validate_handoff.py). Legs 1 and 4 are covered in
tests/test_delivery_funnel.py (the intake writer and the funnel-completion
receipt). Synthetic fixtures only; no network, no browser.
"""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
VALIDATE_HANDOFF = ROOT / "scripts" / "validate_handoff.py"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


VCS = load_module("validate_copy_structure",
                  ROOT / "scripts" / "validate_copy_structure.py")

# The handoff typing rule is spec-independent; the minimal spec keeps every
# other validate() leg inert (no sections, no sequence, no CTA map rules).
MIN_SPEC = {"copy_version": "standard", "sequence": [], "sections": [],
            "cta_map": {}, "qualitative_rules": []}


def handoff_fails(manifest):
    rep = VCS.validate([], [], [], MIN_SPEC, manifest=manifest)
    return [f for f in rep.fails if f.startswith("CTA handoff")]


class CopyManifestHandoffTest(unittest.TestCase):
    def test_manifest_without_ctas_is_untouched(self):
        self.assertEqual(handoff_fails({"offer_name": "X"}), [])
        self.assertEqual(handoff_fails({}), [])
        self.assertEqual(handoff_fails(None), [])

    def test_valid_entries_pass(self):
        manifest = {"ctas": [
            {"section": "1", "label": "Claim Your Seat",
             "handoff_type": "form_pop", "primary": True},
            {"section": "5", "label": "See how it works",
             "handoff_type": "in_page_anchor"},
            {"section": "9", "label": "Partner site",
             "handoff_type": "external_link"}]}
        self.assertEqual(handoff_fails(manifest), [])

    def test_entry_without_handoff_type_fails_by_name(self):
        fails = handoff_fails({"ctas": [{"label": "Claim Your Seat",
                                         "primary": True}]})
        self.assertEqual(len(fails), 2)  # untyped entry + primary not form_pop
        self.assertTrue(any("Claim Your Seat" in f for f in fails))

    def test_bogus_handoff_type_fails(self):
        fails = handoff_fails({"ctas": [{"label": "Go",
                                         "handoff_type": "teleport"}]})
        self.assertEqual(len(fails), 1)
        self.assertIn("teleport", fails[0])

    def test_two_primaries_fail(self):
        fails = handoff_fails({"ctas": [
            {"label": "One", "handoff_type": "form_pop", "primary": True},
            {"label": "Two", "handoff_type": "form_pop", "primary": True}]})
        self.assertTrue(any("exactly one primary" in f for f in fails))

    def test_primary_must_be_the_form_pop(self):
        fails = handoff_fails({"ctas": [
            {"label": "Buy", "handoff_type": "external_link",
             "primary": True}]})
        self.assertEqual(len(fails), 1)
        self.assertIn("form pop", fails[0])

    def test_ctas_must_be_a_list(self):
        fails = handoff_fails({"ctas": {"label": "Go"}})
        self.assertEqual(len(fails), 1)
        self.assertIn("must be a list", fails[0])

    def test_entry_must_be_an_object(self):
        fails = handoff_fails({"ctas": ["Claim Your Seat"]})
        self.assertEqual(len(fails), 1)
        self.assertIn("not an object", fails[0])


def write(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, (dict, list)):
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    else:
        path.write_text(data, encoding="utf-8")


FORM = {"name": "Elevation Registration", "form_id": "FORM-1"}
STEP_ORDER = ["signature_page", "product_selection_page", "order_form_page"]

GOOD_PAGE = """<!doctype html><html><body>
<h1>Elevate</h1>
<button class="cta" data-form-id="FORM-1"
        onclick="ghlFormPop('FORM-1')">Claim Your Seat</button>
<iframe id="inline-FORM-1" src="https://api.leadconnectorhq.com/widget/form/FORM-1"></iframe>
</body></html>"""

PLACEHOLDER_PAGE = """<!doctype html><html><body>
<h1>Elevate</h1>
<a class="cta" href="#join">Claim Your Seat</a>
</body></html>"""

WIRED_PLACEHOLDER_PAGE = """<!doctype html><html><body>
<h1>Elevate</h1>
<a class="cta" href="#join" data-form-id="FORM-1"
   onclick="ghlFormPop('FORM-1')">Claim Your Seat</a>
</body></html>"""

EXTERNAL_PAGE = """<!doctype html><html><body>
<h1>Elevate</h1>
<a class="cta" href="https://example.com/buy">Claim Your Seat</a>
<iframe id="inline-FORM-1" src="https://api.leadconnectorhq.com/widget/form/FORM-1"></iframe>
</body></html>"""


def make_page_run(td: Path, handoff, page=GOOD_PAGE, manifest_ctas="default"):
    run = td / "run"
    intake = {"page_version": "standard", "brand_owner": "Fixture",
              "brand_file": "brand-fixture.json", "image_cap": 5,
              "image_engine": "kie", "test_run": False}
    if handoff is not None:
        intake["funnel_handoff"] = handoff
    write(run / "intake.json", intake)
    if manifest_ctas == "default":
        manifest_ctas = [{"section": "1", "label": "Claim Your Seat",
                          "handoff_type": "form_pop", "primary": True}]
    if manifest_ctas is not None:
        write(run / "copy" / "copy-manifest.json", {"ctas": manifest_ctas})
    if page is not None:
        write(run / "responsive-html" / "index.html", page)
    return run


class ValidateHandoffTest(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp(prefix="s71-handoff-page-"))

    def validate(self, run):
        return subprocess.run([PY, str(VALIDATE_HANDOFF), str(run)],
                              text=True, capture_output=True)

    def test_good_page_passes(self):
        run = make_page_run(self.td, {"form": FORM, "behavior": "form_pop",
                                      "step_order": STEP_ORDER})
        proc = self.validate(run)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("PASS: funnel handoff verified", proc.stdout)

    def test_no_handoff_record_fails(self):
        run = make_page_run(self.td, None)
        proc = self.validate(run)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("records no funnel_handoff", proc.stdout)

    def test_placeholder_primary_cta_fails_by_name(self):
        run = make_page_run(self.td, {"form": FORM, "behavior": "form_pop",
                                      "step_order": STEP_ORDER},
                            page=PLACEHOLDER_PAGE)
        proc = self.validate(run)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("Claim Your Seat", proc.stdout)
        self.assertIn("placeholder", proc.stdout)
        self.assertIn("#join", proc.stdout)

    def test_wired_placeholder_primary_cta_fails_by_name(self):
        # Item 32 review, defect D1: the placeholder test applies to the
        # primary CTA's href regardless of other attributes on the
        # element. A placeholder anchor that also carries the form id in
        # its own markup fails by name when no missing-input flag is on
        # record.
        run = make_page_run(self.td, {"form": FORM, "behavior": "form_pop",
                                      "step_order": STEP_ORDER},
                            page=WIRED_PLACEHOLDER_PAGE)
        proc = self.validate(run)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("Claim Your Seat", proc.stdout)
        self.assertIn("placeholder", proc.stdout)
        self.assertIn("#join", proc.stdout)

    def test_wired_placeholder_carried_under_missing_input_flag(self):
        # The same wired-placeholder construction passes only under the
        # recorded missing-input flag, with the flag printed.
        run = make_page_run(self.td,
                            {"status": "missing_input",
                             "missing": "form_identity",
                             "reason": "client has not created the form yet",
                             "behavior": "form_pop",
                             "step_order": STEP_ORDER},
                            page=WIRED_PLACEHOLDER_PAGE)
        proc = self.validate(run)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("recorded missing input", proc.stdout)
        self.assertIn("client has not created the form yet", proc.stdout)

    def test_external_primary_cta_fails(self):
        run = make_page_run(self.td, {"form": FORM, "behavior": "form_pop",
                                      "step_order": STEP_ORDER},
                            page=EXTERNAL_PAGE)
        proc = self.validate(run)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("links away", proc.stdout)

    def test_page_that_never_references_the_form_fails(self):
        page = ("<!doctype html><html><body><h1>Elevate</h1>"
                "<button class=\"cta\">Claim Your Seat</button>"
                "</body></html>")
        run = make_page_run(self.td, {"form": FORM, "behavior": "form_pop",
                                      "step_order": STEP_ORDER}, page=page)
        proc = self.validate(run)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("never references the named form object", proc.stdout)

    def test_primary_cta_missing_from_page_fails(self):
        page = ("<!doctype html><html><body><h1>Elevate</h1>"
                "<button data-form-id=\"FORM-1\">Some other button</button>"
                "</body></html>")
        run = make_page_run(self.td, {"form": FORM, "behavior": "form_pop",
                                      "step_order": STEP_ORDER}, page=page)
        proc = self.validate(run)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("no element carries the primary CTA", proc.stdout)

    def test_manifest_without_primary_fails(self):
        run = make_page_run(self.td, {"form": FORM, "behavior": "form_pop",
                                      "step_order": STEP_ORDER},
                            manifest_ctas=[{"section": "5", "label": "More",
                                            "handoff_type": "in_page_anchor"}])
        proc = self.validate(run)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("no primary CTA entry", proc.stdout)

    def test_missing_input_flag_carries_the_placeholder(self):
        run = make_page_run(self.td,
                            {"status": "missing_input",
                             "missing": "form_identity",
                             "reason": "client has not created the form yet",
                             "behavior": "form_pop",
                             "step_order": STEP_ORDER},
                            page=PLACEHOLDER_PAGE)
        proc = self.validate(run)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("recorded missing input", proc.stdout)
        self.assertIn("client has not created the form yet", proc.stdout)

    def test_missing_input_without_reason_fails(self):
        run = make_page_run(self.td,
                            {"status": "missing_input",
                             "missing": "form_identity", "reason": "  ",
                             "behavior": "form_pop",
                             "step_order": STEP_ORDER},
                            page=PLACEHOLDER_PAGE)
        proc = self.validate(run)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("names no reason", proc.stdout)

    def test_half_a_form_identity_fails(self):
        run = make_page_run(self.td,
                            {"form": {"name": "Elevation Registration"},
                             "behavior": "form_pop",
                             "step_order": STEP_ORDER})
        proc = self.validate(run)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("name AND object id", proc.stdout)


if __name__ == "__main__":
    unittest.main()
