"""RFX-014: one Upsell 2 page carries one acknowledgement that is true for every buyer who reaches it.

The builder used to write "Your Upsell 1 purchase is confirmed" or "Your alternative offer purchase is
confirmed" from a caller-chosen u2_entry_context. With a downsell routed, both U1 and D1 pay into the
SAME U2 page, so either wording was false for the buyer who arrived the other way.

Now the entry paths are read from the approved route graph (verified paid edges into upsell_2):
  * both paths -> the neutral "Your purchase is confirmed." with no context needed;
  * one path   -> that path's specific wording, unchanged;
  * a stated context the graph does not have ALONE (either path on a two-entry graph) is refused,
    never obeyed and never silently overridden, because it would claim a purchase one buyer never made.

Run from the skill root:  python3 -m unittest discover -s tests
"""

import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
REPO = SKILL.parent
PAGES = SKILL / "components" / "pages"
FIXTURES = SKILL / "components" / "80-signature-upsell" / "fixtures"
FAMILY = "order_upsell_v2_funnel"
U1_WORDS = "Upsell 1 purchase is confirmed"
D1_WORDS = "alternative offer purchase is confirmed"
NEUTRAL = "Your purchase is confirmed."


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _import(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


sys.path.insert(0, str(PAGES))
bpp = _import("build_production_pages_u2_ack", PAGES / "build_production_pages.py")
compiler = _import("compile_launch_route_u2_ack",
                   REPO / "49-signature-funnel" / "scripts" / "compile_launch_route.py")


class U2Acknowledgement(unittest.TestCase):
    def setUp(self):
        self.launch = _load(REPO / "49-signature-funnel" / "scripts" / "fixtures"
                            / "finalized-launch-record-signature-launch-l4.json")
        self.assertNotIn("u2_entry_context", self.launch, "fixture premise: no context is supplied")
        self.copies = {"upsell_1": _load(FIXTURES / "copy-upsell1-public.valid.json"),
                       "upsell_2": _load(FIXTURES / "copy-upsell2-public.valid.json")}
        self.d1 = _load(REPO / "81-signature-downsell" / "fixtures" / "valid-downsell-page.json")

    def _build(self, launch, graph):
        launch = dict(launch, route_graph_hash=bpp.graph_hash(graph))
        return bpp.build(launch, graph, FAMILY, self.copies, self.d1, {})

    def _u2(self, built):
        row = next(p for p in built["manifest"]["pages"] if p["slot"] == "upsell_2")
        return built["pages"]["upsell_2"], row

    def _no_downsell(self):
        launch = copy.deepcopy(self.launch)
        launch["extras"] = dict(launch["extras"], downsell_1=False)
        launch["offers"] = [o for o in launch["offers"] if o["slot"] != "downsell_1"]
        return launch

    def _d1_only_graph(self):
        """U1 paid goes straight to thank-you; only D1 pays into U2 (an approved graph shape the
        builder must read, even though today's compiler routes U1 paid to U2)."""
        graph = compiler.compile_route(self.launch)
        role = {n["page_id"]: n["role"] for n in graph["nodes"]}
        ty = next(p for p, r in role.items() if r == "thank_you")
        for edge in graph["edges"]:
            if role[edge["from"]] == "upsell_1" and edge["event"] == "payment_succeeded":
                edge["to"] = ty
        return graph

    def test_two_entry_graph_uses_the_neutral_wording_with_no_context(self):
        graph = compiler.compile_route(self.launch)
        text, row = self._u2(self._build(self.launch, graph))
        self.assertEqual(row["entry_paths"], ["from_upsell_1", "from_downsell_1"])
        self.assertIn(NEUTRAL, text)
        self.assertNotIn(U1_WORDS, text)
        self.assertNotIn(D1_WORDS, text)

    def test_two_entry_graph_refuses_either_one_path_context(self):
        graph = compiler.compile_route(self.launch)
        for wrong in ("from_upsell_1", "from_downsell_1"):
            with self.subTest(wrong=wrong):
                with self.assertRaises(bpp.PageBuildError) as ctx:
                    self._build(dict(self.launch, u2_entry_context=wrong), graph)
                self.assertIn("disagrees with the approved route graph", str(ctx.exception))

    def test_upsell_1_only_graph_keeps_the_upsell_1_wording(self):
        launch = self._no_downsell()
        graph = compiler.compile_route(launch)
        for stated in (None, "from_upsell_1"):
            with self.subTest(stated=stated):
                text, row = self._u2(self._build(dict(launch, u2_entry_context=stated), graph))
                self.assertEqual(row["entry_paths"], ["from_upsell_1"])
                self.assertIn(U1_WORDS, text)
                self.assertNotIn(NEUTRAL, text)
        with self.assertRaises(bpp.PageBuildError):
            self._build(dict(launch, u2_entry_context="from_downsell_1"), graph)

    def test_downsell_1_only_graph_keeps_the_downsell_wording(self):
        graph = self._d1_only_graph()
        text, row = self._u2(self._build(self.launch, graph))
        self.assertEqual(row["entry_paths"], ["from_downsell_1"])
        self.assertIn(D1_WORDS, text)
        self.assertNotIn(U1_WORDS, text)
        with self.assertRaises(bpp.PageBuildError):
            self._build(dict(self.launch, u2_entry_context="from_upsell_1"), graph)

    def test_one_page_serves_both_paths(self):
        graph = compiler.compile_route(self.launch)
        built = self._build(self.launch, graph)
        u2_nodes = [n["page_id"] for n in graph["nodes"] if n["role"] == "upsell_2"]
        self.assertEqual(len(u2_nodes), 1)
        self.assertEqual(self._u2(built)[1]["page_id"], u2_nodes[0])
        self.assertEqual(built["pages"]["upsell_2"].count('class="ack"'), 1)


if __name__ == "__main__":
    unittest.main()
