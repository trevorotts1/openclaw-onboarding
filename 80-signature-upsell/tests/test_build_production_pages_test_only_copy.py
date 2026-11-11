"""Issue 4 (harmony review): the production page builder refuses test_only copy.

`build_production_pages.py` used to read `test_only` from the launch record
only, never from the copy documents. A fixture copy (`test_only: true`) could
therefore be published as production on a launch that was not marked test.
These tests pin the refusal: a copy document (an upsell copy or the D1 page
document) carrying `test_only` on a non-test launch is a named
`PageBuildError`, nothing is written, and the same documents still build on a
launch that is itself marked test_only.

Run from the skill root:  python3 -m unittest discover -s tests
"""

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
REPO = SKILL.parent
PAGES = SKILL / "components" / "pages"
FIXTURES = SKILL / "components" / "80-signature-upsell" / "fixtures"
FAMILY = "order_upsell_v2_funnel"


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _import(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


sys.path.insert(0, str(PAGES))
sys.path.insert(0, str(REPO / "49-signature-funnel" / "scripts"))
bpp = _import("build_production_pages_under_test", PAGES / "build_production_pages.py")
compiler = _import("compile_launch_route_under_test",
                   REPO / "49-signature-funnel" / "scripts" / "compile_launch_route.py")


class TestOnlyCopyRefusal(unittest.TestCase):
    def setUp(self):
        launch = _load(REPO / "49-signature-funnel" / "scripts" / "fixtures"
                       / "finalized-launch-record-signature-launch-l4.json")
        launch["u2_entry_context"] = "from_upsell_1"
        self.graph = compiler.compile_route(launch)
        self.launch_test = launch                      # test_only: true
        self.launch_live = dict(launch, test_only=False)
        self.copies = {
            "upsell_1": _load(FIXTURES / "copy-upsell1-public.valid.json"),
            "upsell_2": _load(FIXTURES / "copy-upsell2-public.valid.json"),
        }
        self.d1 = _load(REPO / "81-signature-downsell" / "fixtures"
                        / "valid-downsell-page.json")
        for doc in self.copies.values():
            self.assertIs(doc.get("test_only"), True, "fixture premise")
        self.assertIs(self.d1.get("test_only"), True, "fixture premise")

    def _build(self, launch, copies=None, d1=None):
        return bpp.build(launch, self.graph, FAMILY,
                         self.copies if copies is None else copies,
                         self.d1 if d1 is None else d1, {})

    def _clean(self, doc):
        doc = copy.deepcopy(doc)
        doc.pop("test_only", None)
        if isinstance(doc.get("page"), dict):
            doc["page"].pop("test_only", None)
        return doc

    def test_control_test_launch_builds_with_test_copy(self):
        built = self._build(self.launch_test)
        self.assertEqual(sorted(built["pages"]),
                         ["downsell_1", "upsell_1", "upsell_2"])

    def test_control_live_launch_builds_with_clean_copy(self):
        copies = {k: self._clean(v) for k, v in self.copies.items()}
        built = self._build(self.launch_live, copies, self._clean(self.d1))
        self.assertEqual(sorted(built["pages"]),
                         ["downsell_1", "upsell_1", "upsell_2"])

    def test_live_launch_refuses_test_only_upsell_copy(self):
        for slot in ("upsell_1", "upsell_2"):
            copies = {k: self._clean(v) for k, v in self.copies.items()}
            copies[slot] = copy.deepcopy(self.copies[slot])   # keeps test_only
            with self.assertRaises(bpp.PageBuildError) as ctx:
                self._build(self.launch_live, copies, self._clean(self.d1))
            self.assertIn("test_only", str(ctx.exception))
            self.assertIn(slot, str(ctx.exception))

    def test_live_launch_refuses_test_only_downsell_page(self):
        copies = {k: self._clean(v) for k, v in self.copies.items()}
        with self.assertRaises(bpp.PageBuildError) as ctx:
            self._build(self.launch_live, copies, self.d1)
        self.assertIn("test_only", str(ctx.exception))
        self.assertIn("downsell_1", str(ctx.exception))

    def test_live_launch_refuses_test_only_inside_page_wrapper(self):
        # Skill 81 writes {"page": {...}}; a flag on the inner page counts too.
        copies = {k: self._clean(v) for k, v in self.copies.items()}
        inner = self._clean(self.d1)
        inner["page"]["test_only"] = True
        with self.assertRaises(bpp.PageBuildError):
            self._build(self.launch_live, copies, inner)

    def test_live_launch_with_unmarked_launch_key_still_refuses(self):
        # A launch record with no test_only key at all is not a test launch.
        launch = {k: v for k, v in self.launch_live.items() if k != "test_only"}
        copies = {k: self._clean(v) for k, v in self.copies.items()}
        copies["upsell_1"] = copy.deepcopy(self.copies["upsell_1"])
        with self.assertRaises(bpp.PageBuildError):
            self._build(launch, copies, self._clean(self.d1))

    def test_any_truthy_test_only_marker_on_copy_is_refused(self):
        # Fail closed: the marker need not be the JSON literal true.
        for marker in (1, "true", "yes"):
            for slot in ("upsell_1", "upsell_2"):
                copies = {k: self._clean(v) for k, v in self.copies.items()}
                copies[slot] = dict(copies[slot], test_only=marker)
                with self.assertRaises(bpp.PageBuildError, msg=(slot, marker)):
                    self._build(self.launch_live, copies, self._clean(self.d1))
            copies = {k: self._clean(v) for k, v in self.copies.items()}
            d1 = self._clean(self.d1)
            d1["page"]["test_only"] = marker
            with self.assertRaises(bpp.PageBuildError, msg=("downsell_1", marker)):
                self._build(self.launch_live, copies, d1)

    def test_launch_test_marker_is_read_by_truthiness_like_the_rest_of_the_builder(self):
        # The builder reads launch["test_only"] with bool() everywhere else
        # (page banner, manifest); the refusal must agree, not be stricter.
        built = self._build(dict(self.launch_test, test_only=1))
        self.assertEqual(sorted(built["pages"]),
                         ["downsell_1", "upsell_1", "upsell_2"])

    def test_cli_exit_2_and_nothing_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "launch.json").write_text(json.dumps(self.launch_live))
            (tmp / "graph.json").write_text(
                json.dumps(self.graph, indent=2, ensure_ascii=False) + "\n")
            out = tmp / "out"
            rc = bpp.main([
                "--launch", str(tmp / "launch.json"),
                "--route-graph", str(tmp / "graph.json"),
                "--checkout-family", FAMILY,
                "--copy", "upsell_1=%s" % (FIXTURES / "copy-upsell1-public.valid.json"),
                "--copy", "upsell_2=%s" % (FIXTURES / "copy-upsell2-public.valid.json"),
                "--downsell-page", str(REPO / "81-signature-downsell" / "fixtures"
                                       / "valid-downsell-page.json"),
                "--out-dir", str(out)])
            self.assertEqual(rc, 2)
            self.assertFalse(out.exists(), "a refusal must write nothing")


if __name__ == "__main__":
    unittest.main()
