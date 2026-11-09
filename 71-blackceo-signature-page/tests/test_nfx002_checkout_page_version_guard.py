#!/usr/bin/env python3
"""NFX-002: FIX-01 Stage A (the forward checkout pair) and FIX-15 (the page-version guard).

FIX-01 Stage A is a pair, and neither half alone is correct:
  * 49-signature-funnel/scripts/checkout_wrapper.py asks Skill 71 to admit the checkout page
    with --page-version "checkout";
  * 71-blackceo-signature-page/scripts/copy_forms.py SPEC_FILES defines "checkout".
FIX-15 makes the guard that compares a page version to the role's spec actually fire:
  * discovery under references/copy-specs/ is recursive, so roles/checkout.json is found;
  * discovery is not filtered by wireframe.form_label;
  * a role with a spec on disk that discovery misses raises a named error (never None);
  * build_production_request.py refuses a role with no registered form instead of silently
    falling back to the spec's own `form`.

The load-bearing control (Document 3 FIX-15 Verification) is the same probe run against an
unmodified origin/main tree: there, --page-version "standard" reaches the route_graph_hash
refusal with exit 2 because the page-version guard is inert. Set NFX002_CONTROL_ROOT to a
worktree of unmodified origin/main to exercise it.

No provider is called anywhere in this module.
"""
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SCRIPTS = ROOT / "scripts"
REPO = ROOT.parent
CHECKOUT_WRAPPER = REPO / "49-signature-funnel" / "scripts" / "checkout_wrapper.py"
PY = sys.executable
sys.path.insert(0, str(SCRIPTS))


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


copy_forms = load("copy_forms")
page_role = load("page_role")
builder = load("build_production_request")


def role_files():
    """Every role spec file on disk at any depth, derived at test time (never a hand list)."""
    out = []
    for path in sorted(page_role.SPEC_DIR.rglob("*.json")):
        spec = json.loads(path.read_text(encoding="utf-8"))
        if page_role.declared_roles(spec):
            out.append((path, spec))
    return out


class StageARegistryTests(unittest.TestCase):
    def test_the_one_registry_defines_the_checkout_form(self):
        self.assertEqual(copy_forms.SPEC_FILES.get("checkout"), "roles/checkout.json")
        self.assertIn("checkout", copy_forms.FORMS)
        self.assertEqual(copy_forms.load_spec("checkout")["page_role"], "checkout")
        self.assertEqual(copy_forms.form_for_role("checkout"), "checkout")

    def test_the_wrapper_asks_for_checkout_not_standard(self):
        text = CHECKOUT_WRAPPER.read_text(encoding="utf-8")
        self.assertIn('"--page-version", "checkout"', text)
        self.assertNotIn('"--page-version", "standard"', text)


class DiscoveryTests(unittest.TestCase):
    def test_every_role_spec_on_disk_resolves(self):
        paths = role_files()
        self.assertTrue(paths, "no role spec found under references/copy-specs/")
        seen = set()
        for path, spec in paths:
            for role in page_role.declared_roles(spec):
                seen.add(role)
                got = page_role.spec_for_role(role)
                self.assertIsNotNone(got, f"{role} ({path}) resolved to None")
                self.assertEqual(page_role.declared_roles(got)[0], page_role.declared_roles(spec)[0], path)
        self.assertIn("checkout", seen)
        self.assertIn("thank_you", seen)
        self.assertIn("product_selection", seen)

    def test_discovery_reaches_the_nested_checkout_spec(self):
        self.assertEqual(Path(page_role.role_spec_paths()["checkout"]).name, "checkout.json")
        self.assertEqual(page_role.role_specs()["checkout"]["page_role"], "checkout")

    def test_a_spec_on_disk_that_discovery_misses_raises_named_error(self):
        # Discovery is made to miss every spec while the files stay on disk. The pre-fix
        # spec_for_role returned None here; FIX-15 fails closed instead.
        with mock.patch.object(page_role, "role_specs", return_value={}):
            with self.assertRaises(page_role.RoleSpecNotDiscovered) as ctx:
                page_role.spec_for_role("checkout")
        message = str(ctx.exception)
        self.assertIn("'checkout'", message)
        self.assertIn("roles/checkout.json", message)

    def test_a_role_with_no_spec_file_still_returns_none(self):
        self.assertIsNone(page_role.spec_for_role("landing"))
        self.assertIsNone(page_role.spec_for_role("downsell_1"))


class BuilderFallbackTests(unittest.TestCase):
    def build(self, page_role_name="checkout"):
        return builder.build("visual-mockup", None, "", {}, {}, [], "STUB-NO-MODEL", "",
                             Path(tempfile.mkdtemp(prefix="nfx002-")), page_role_name)

    def test_a_role_spec_without_a_registered_form_is_refused(self):
        # Stage A makes the registry complete; if the checkout key is absent the builder must
        # refuse, not silently use spec["form"] (the pre-fix fallback).
        registry = builder.copy_forms  # the module instance the builder itself reads
        with mock.patch.dict(registry.SPEC_FILES):
            registry.SPEC_FILES.pop("checkout")
            with mock.patch.object(registry, "FORMS",
                                   tuple(f for f in registry.FORMS if f != "checkout")):
                with self.assertRaises(builder.BuildError) as ctx:
                    self.build()
        self.assertIn("registers no form", str(ctx.exception))
        self.assertIn("'checkout'", str(ctx.exception))

    def test_the_registry_keeps_the_checkout_role_buildable(self):
        # The positive half: with Stage A's registry the builder knows the role's form and
        # does not raise the registry error (it continues to the manuscript check).
        self.assertEqual(copy_forms.form_for_role("checkout"), "checkout")
        with self.assertRaises(builder.BuildError) as ctx:
            self.build()
        self.assertNotIn("registers no form", str(ctx.exception))


class PageVersionProbeTests(unittest.TestCase):
    """shared_page_service.py is the probe: the page-version guard fires before route_graph_hash."""

    def probe(self, skill_root, version):
        sys.path.insert(0, str(Path(skill_root) / "71-blackceo-signature-page" / "tests"))
        try:
            import test_launch_profile as t
        finally:
            sys.path.pop(0)
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            brand = td / "brand.json"
            brand.write_text('{"x":1}', encoding="utf-8")
            bh = hashlib.sha256(brand.read_bytes()).hexdigest()
            graph = t.dump(t.graph_doc())
            gh = hashlib.sha256(graph).hexdigest()
            (td / "graph.json").write_bytes(graph)
            (td / "launch.json").write_bytes(t.dump(t.launch_doc(gh, brand_ref="brand.json", brand_hash=bh)))
            request = t.request_doc(gh, page_role="checkout", assigned_skill=79, copy_profile="standard",
                                    page_id="page-checkout-1", brand_ref="brand.json", brand_hash=bh,
                                    route_graph_hash="0" * 64)  # deliberately stale: the guard must win
            (td / "request.json").write_bytes(t.dump(request))
            return subprocess.run(
                [PY, str(Path(skill_root) / "71-blackceo-signature-page" / "scripts" / "shared_page_service.py"),
                 "--request", str(td / "request.json"), "--run-dir", str(td / "run"),
                 "--page-version", version, "--brand-owner", "Acme Owner", "--image-cap", "1",
                 "--brand-file", str(brand), "--launch-record", str(td / "launch.json"),
                 "--route-graph", str(td / "graph.json"), "--validation-only"],
                capture_output=True, text=True)

    def test_standard_is_refused_by_the_page_version_guard(self):
        proc = self.probe(REPO, "standard")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        text = proc.stdout + proc.stderr
        self.assertIn("takes --page-version checkout", text)
        self.assertNotIn("route graph", text)

    def test_checkout_passes_the_guard_and_reaches_the_route_graph_check(self):
        proc = self.probe(REPO, "checkout")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        text = proc.stdout + proc.stderr
        self.assertIn("route graph", text)
        self.assertNotIn("takes --page-version", text)


class LoadBearingControlTests(unittest.TestCase):
    def test_unmodified_origin_main_lets_standard_reach_the_route_graph_refusal(self):
        control = os.environ.get("NFX002_CONTROL_ROOT")
        if not control:
            self.skipTest("NFX002_CONTROL_ROOT is not set to an unmodified origin/main worktree")
        probe = PageVersionProbeTests()
        proc = probe.probe(Path(control), "standard")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        text = proc.stdout + proc.stderr
        self.assertIn("route graph", text)  # the guard is inert there: the measured pre-fix control
        self.assertNotIn("takes --page-version", text)


if __name__ == "__main__":
    unittest.main()
