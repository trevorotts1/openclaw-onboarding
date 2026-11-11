#!/usr/bin/env python3
"""test_compile_launch_route.py - ONE route-graph hash (issue 56). The compiler (49), the upsell
builder (80) and the thank-you builder (82) all hash the graph FILE's bytes: the emitted file matches
the launch record's hash in all three, and a re-saved (re-indented) file is a different hash in all
three, never a silent match in some. Stdlib only. Run: python3 test_compile_launch_route.py"""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))
import compile_launch_route as clr  # noqa: E402


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(Path(path).parent))
    spec.loader.exec_module(mod)
    return mod


B80 = load(REPO / "80-signature-upsell/components/pages/build_production_pages.py", "b80")
B82 = load(REPO / "82-signature-thank-you/scripts/build_thank_you_page.py", "b82")
LAUNCH = json.loads((HERE / "fixtures/finalized-launch-record-signature-launch-l4.json").read_text(encoding="utf-8"))


class RouteGraphHash(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.graph = clr.compile_route(LAUNCH)
        self.orig = Path(self.td.name) / "route-graph.json"
        self.orig.write_bytes(clr.serialize_graph(self.graph))
        self.resaved = Path(self.td.name) / "resaved.json"
        self.resaved.write_text(json.dumps(json.loads(self.orig.read_text(encoding="utf-8")), indent=4) + "\n", encoding="utf-8")

    def tearDown(self):
        self.td.cleanup()

    def three(self, path):
        raw = Path(path).read_bytes()
        g = json.loads(raw)
        return (clr.graph_file_hash(path), B80.graph_hash(g, raw), B82.graph_hash(g, raw))

    def test_emitted_file_equals_recorded_in_all_three(self):
        recorded = clr.graph_hash(self.graph)
        self.assertEqual(self.three(self.orig), (recorded,) * 3)

    def test_resaved_file_hashes_the_same_everywhere_and_differs_from_emit(self):
        a, b, c = self.three(self.resaved)
        self.assertEqual(a, b)
        self.assertEqual(b, c)
        self.assertNotEqual(a, clr.graph_hash(self.graph))

    def test_clis_hash_the_bytes_they_read(self):
        for mod in (B80, B82):
            src = Path(mod.__file__).read_text(encoding="utf-8")
            self.assertIn("graph_raw=graph_raw", src)


if __name__ == "__main__":
    unittest.main()
