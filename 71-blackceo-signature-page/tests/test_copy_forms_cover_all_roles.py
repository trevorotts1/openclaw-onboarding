#!/usr/bin/env python3
"""Harmony issue 50: every page role has a copy form (or its own role structure), and the shared
image service refuses a role that has neither or a wrong form label.

Before: scripts/copy_forms.py had no downsell form, Skill 49's downsell wrapper passed
`--page-version standard` for downsell_1, and shared_page_service.py's form guard compared two
None values and passed. A page-type guard that silently accepts a wrong label is the pattern that
lets a step be skipped later.

Covered here:
  * every role in references/page-request.schema.json resolves to a registered copy form
    (copy_forms.form_for_role), to a landing form (landing), or to its own role structure
    (references/copy-specs/roles/<role>.json, checkout);
  * every role in references/page-structures.json has a registered form, and that form's spec
    carries the structure's own sequence, section names and jobs (two copies, one truth);
  * shared_page_service.py refuses downsell_1 with --page-version standard, admits it with
    --page-version downsell, and refuses a page role with neither a form nor a role structure.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import copy_forms  # noqa: E402
import role_spec  # noqa: E402
import wireframe_spec  # noqa: E402

REQUEST_SCHEMA = json.loads((ROOT / "references" / "page-request.schema.json").read_text(encoding="utf-8"))
ROLES = REQUEST_SCHEMA["properties"]["page_role"]["enum"]
STRUCTURES = json.loads((ROOT / "references" / "page-structures.json").read_text(encoding="utf-8"))["roles"]


class RoleCoverage(unittest.TestCase):
    def test_every_non_landing_role_has_a_form_or_a_role_structure(self):
        gaps = [r for r in ROLES if r != "landing"
                and copy_forms.form_for_role(r) is None and role_spec.load(r) is None]
        self.assertEqual(gaps, [], f"page roles with no copy form and no role structure: {gaps}")

    def test_every_page_structures_role_has_a_registered_form(self):
        for role, structure in STRUCTURES.items():
            form = copy_forms.form_for_role(role)
            self.assertIsNotNone(form, f"{role} is built from references/page-structures.json but has no copy form")
            self.assertEqual(form, structure["copy_version"], role)
            self.assertEqual(copy_forms.norm(structure["copy_version"]), form)

    def test_the_downsell_form_carries_the_structures_own_sequence_names_and_jobs(self):
        structure = STRUCTURES["downsell_1"]
        spec = copy_forms.load_spec("downsell")
        self.assertEqual(spec["page_roles"], ["downsell_1"])
        self.assertNotIn("page_role", spec, "a singular page_role would let a lost role marker be recovered from a copy_version")
        self.assertEqual(spec["sequence"], structure["sequence"])
        self.assertEqual([s["id"] for s in spec["sections"]], [s["id"] for s in structure["sections"]])
        self.assertEqual([s["framework_name"] for s in spec["sections"]], [s["name"] for s in structure["sections"]])
        self.assertEqual([s["job"] for s in spec["sections"]], [s["job"] for s in structure["sections"]])
        self.assertEqual(spec["cta_map"]["required_in_sections"], structure["cta_map"]["required_in_sections"])
        self.assertEqual(spec["cta_map"]["standalone_total"]["value"], len(structure["sequence"]))

    def test_downsell_is_a_non_landing_form(self):
        self.assertIn("downsell", copy_forms.FORMS)
        self.assertNotIn("downsell", copy_forms.LANDING_FORMS)
        self.assertEqual(copy_forms.norm("Downsell"), "downsell")


def request_for(role):
    return {
        "schema_version": "1.0", "tenant_id": "T", "location_id": "L", "launch_id": "LA", "revision": 1,
        "request_id": "R-1", "page_id": "P-1", "page_role": role, "assigned_skill": 81,
        "approval_ref": "A-1", "input_hash": "H", "brand_ref": "brand.json", "brand_hash": "0" * 64,
        "route_graph_ref": "route-graph.json", "route_graph_hash": "0" * 64, "offer_refs": [],
        "copy_profile": "standard", "allowed_write_target": "local_only", "test_only": True,
    }


class DownsellWiring(unittest.TestCase):
    """The downsell form is also wired where a wireframe prompt reads its form label and style sheet."""

    def test_wireframe_spec_labels_the_downsell_form(self):
        self.assertEqual(wireframe_spec.FORM_LABEL["downsell"], "Downsell")

    def test_the_visual_standards_manifest_lists_the_downsell_style_sheets_the_build_spec_attaches(self):
        manifest = json.loads((ROOT / "assets" / "visual-standards" / "manifest.json").read_text(encoding="utf-8"))
        listed = manifest["wireframe_style_references"]
        attached = json.loads((ROOT / "references" / "wireframe-build-spec.json").read_text(encoding="utf-8"))["style_references"]
        self.assertIn("downsell", listed)
        self.assertIn("downsell", attached)
        for form, stages in attached.items():
            self.assertEqual(listed.get(form), {st: e["file"] for st, e in stages.items()}, form)
        for stage in wireframe_spec.WIREFRAME_STAGES:
            self.assertEqual(wireframe_spec.style_reference(stage, "downsell")["form"], "downsell")


class SharedServiceFormGuard(unittest.TestCase):
    """Drives the real entry point as a subprocess, validation-only: the guard runs before any file
    is read, so the refusal arrives without a route graph, a brand file or a pipeline command."""

    def admit(self, role, version, schema_roles=None):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            req = td / "request.json"
            req.write_text(json.dumps(request_for(role)), encoding="utf-8")
            for name in ("route-graph.json", "brand.json", "launch.json"):
                (td / name).write_text("{}", encoding="utf-8")
            cmd = [sys.executable, str(SCRIPTS / "shared_page_service.py"), "--request", str(req),
                   "--run-dir", str(td / "run"), "--page-version", version, "--brand-owner", "Acme",
                   "--image-cap", "1", "--brand-file", str(td / "brand.json"),
                   "--launch-record", str(td / "launch.json"), "--route-graph", str(td / "route-graph.json"),
                   "--validation-only"]
            return subprocess.run(cmd, capture_output=True, text=True)

    def test_downsell_with_the_standard_label_is_refused_by_name(self):
        proc = self.admit("downsell_1", "standard")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("REFUSED", proc.stdout)
        self.assertIn("downsell", proc.stdout)
        self.assertIn("standard", proc.stdout)

    def test_downsell_with_its_own_label_passes_the_form_guard(self):
        proc = self.admit("downsell_1", "downsell")
        # The form guard is the first failing point for a wrong label; with the right label the
        # request moves on to the next check (the route-graph hash), which this fixture does not
        # satisfy, so the refusal that arrives is the hash one, not a form one.
        self.assertNotIn("does not fit page_role", proc.stdout, proc.stdout)
        self.assertNotIn("takes --page-version", proc.stdout, proc.stdout)

    def test_a_landing_label_for_the_checkout_role_still_passes_the_form_guard(self):
        proc = self.admit("checkout", "standard")
        self.assertNotIn("does not fit page_role", proc.stdout, proc.stdout)
        self.assertNotIn("has no copy form", proc.stdout, proc.stdout)

    def test_a_role_with_neither_a_form_nor_a_role_structure_is_refused(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("shared_page_service", SCRIPTS / "shared_page_service.py")
        svc = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(svc)
        with self.assertRaises(svc.ServiceError) as ctx:
            svc.require_role_form("mystery_page", None)
        self.assertIn("has no copy form", str(ctx.exception))
        svc.require_role_form("landing", None)  # the landing page takes standard or long-form
        svc.require_role_form("checkout", None)  # checkout has its own role structure
        svc.require_role_form("downsell_1", "downsell")


class SharedServiceEntryPointRefusesFormlessRole(unittest.TestCase):
    """Drives shared_page_service.main() itself (the real entry point), not require_role_form: a
    role in the request enum that has neither a copy form nor a role structure must be refused by
    the entry point. Deleting the require_role_form call in main() leaves the form comparison
    (None against None) passing, so only this test notices."""

    def test_main_refuses_a_non_landing_role_with_no_form_and_no_role_structure(self):
        import importlib.util
        import io
        from contextlib import redirect_stdout
        spec = importlib.util.spec_from_file_location("shared_page_service_main", SCRIPTS / "shared_page_service.py")
        svc = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(svc)
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            schema = json.loads((ROOT / "references" / "page-request.schema.json").read_text(encoding="utf-8"))
            schema["properties"]["page_role"]["enum"] = ROLES + ["mystery_page"]
            (td / "schema.json").write_text(json.dumps(schema), encoding="utf-8")
            (td / "request.json").write_text(json.dumps(dict(request_for("mystery_page"), assigned_skill=71)),
                                             encoding="utf-8")
            for name in ("route-graph.json", "brand.json", "launch.json"):
                (td / name).write_text("{}", encoding="utf-8")
            svc.REQUEST_SCHEMA = td / "schema.json"
            out = io.StringIO()
            with redirect_stdout(out):
                code = svc.main(["--request", str(td / "request.json"), "--run-dir", str(td / "run"),
                                 "--page-version", "standard", "--brand-owner", "Acme", "--image-cap", "1",
                                 "--brand-file", str(td / "brand.json"), "--launch-record", str(td / "launch.json"),
                                 "--route-graph", str(td / "route-graph.json"), "--validation-only"])
            self.assertEqual(code, 2, out.getvalue())
            self.assertIn("REFUSED", out.getvalue())
            self.assertIn("has no copy form", out.getvalue())
            self.assertFalse((td / "run").exists(), "a refused request must write nothing")

if __name__ == "__main__":
    unittest.main()
