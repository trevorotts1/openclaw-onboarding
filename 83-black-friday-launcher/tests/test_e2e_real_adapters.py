"""STR-27: one offline end-to-end run of a multiple_options launch through the REAL adapters.

The other dispatch tests swap every page skill for tests/lane83_fake_consumer.py, which fabricates labeled
design files, so a defect anywhere in the real adapter chain (selection, thank-you, checkout, upsell,
downsell, landing) cannot show up in them. This test builds the adapter commands with
launcher_core.launch_bridge from per-page inputs (the same path as `cli dispatch --adapter-inputs`), runs
them on the free stub provider, then runs `cli assemble` and `cli check` over what they wrote.

It must end in a package that `check` passes and that is labelled "images only, render pending": the stub
provider draws section images only, so nothing here may claim review PDFs or boards that were never made.
No network, no paid call, no fake consumer.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parent
REPO_ROOT = SKILL_ROOT.parent
for entry in (SKILL_ROOT, SKILL_ROOT / "routes", HERE):
    sys.path.insert(0, str(entry))

import lane83_fake_consumer  # noqa: E402  only for its marker constants: proves we did NOT use it
import test_lane83_dispatch as dispatch_tests  # noqa: E402  run_dispatch carries the approval and plan choices
from launcher_core import cli  # noqa: E402

S71 = REPO_ROOT / "71-blackceo-signature-page"
COPY_EXAMPLES = S71 / "tests" / "fixtures" / "copy_examples"
S80_FIXTURES = REPO_ROOT / "80-signature-upsell" / "components" / "80-signature-upsell" / "fixtures"
S80_JOURNEYS = REPO_ROOT / "80-signature-upsell" / "components" / "adapters" / "fixtures"
S81_PAGE = REPO_ROOT / "81-signature-downsell" / "fixtures" / "valid-downsell-page.json"
S49_FIXTURES = REPO_ROOT / "49-signature-funnel" / "scripts" / "fixtures"

BRAND_OWNER = "blackceo"  # Skill 71 refuses a brand file whose brand_id is not the run's owner
ROLES = ["landing", "product_selection", "checkout", "upsell_1", "downsell_1", "upsell_2", "thank_you"]
# What each upsell/downsell page's copy fixture was written against, so the offers say the same.
DELIVERABLES = {
    "upsell_1": ["TEST ONLY recorded lesson archive", "TEST ONLY printable workbooks",
                 "TEST ONLY bonus session recordings"],
    "upsell_2": ["TEST ONLY guided implementation sessions", "TEST ONLY individual asset review",
                 "TEST ONLY build plan"],
    "downsell_1": ["TEST ONLY lite start pass"],
}
LABEL = "images only, render pending"


def _design_prose(chars: int = 14500) -> str:
    """Pseudo-sentences standing in for a run's measured design system (Skill 71 refuses a prompt under
    its 16000-character floor without one). Deterministic, so a rerun builds identical requests."""
    syl = ["ba", "ke", "lo", "mi", "su", "ta", "ve", "zo", "ri", "na"]
    words = [a + b + c + d for a in syl for b in syl for c in syl for d in syl]
    text, state = [], 7
    while sum(len(t) + 1 for t in text) < chars:
        sentence = []
        for _ in range(12):
            state = (state * 1103515245 + 12345) % 2147483648
            sentence.append(words[state % len(words)])
        text.append(" ".join(sentence) + ".")
    return json.dumps({"rules_md": "\n".join(text)})


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RealAdaptersEndToEndTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        # a paid image adapter that fails loudly if anything starts it: proof of zero paid calls
        self.marker = self.root / "kie-was-called"
        adapter = self.root / "kie_live_adapter.py"
        adapter.write_text(f"import sys, pathlib\npathlib.Path({str(self.marker)!r}).write_text('called')\n"
                           "sys.exit(99)\n", encoding="utf-8")
        env = mock.patch.dict(os.environ, {"SKILL71_KIE_ADAPTER": str(adapter)})
        env.start()
        self.addCleanup(env.stop)

    def _intake(self) -> dict:
        brand = (S71 / "assets" / "brand" / "blackceo-brand.json").read_bytes()
        self.brand_file = self.root / "brand.json"
        self.brand_file.write_bytes(brand)
        doc = dispatch_tests.payload("elevation", design_style="B", image_provider="kie", image_cap=200,
                                     brand_file=str(self.brand_file), brand_owner=BRAND_OWNER)
        doc["brand"]["hash"] = _sha256(self.brand_file)  # the landing build re-hashes the brand file
        for offer in doc["offers"]:
            if offer["role"] in DELIVERABLES:  # the upsell and downsell pages refuse to invent deliverables
                offer["level"] = {"state": "supplied", "name": offer["name"],
                                  "deliverables": DELIVERABLES[offer["role"]]}
        return doc

    def _adapter_inputs(self, out: Path) -> dict:
        """The per-page inputs `cli dispatch --adapter-inputs` takes. Every file is a repo fixture or derived
        from one; nothing is a stand-in for a page skill's output."""
        inputs = self.root / "inputs"
        inputs.mkdir()

        def write(name: str, text: str) -> Path:
            path = inputs / name
            path.write_text(text, encoding="utf-8")
            return path

        def rebound(src: Path, name: str) -> Path:  # the fixtures name TEST-ONLY-U1/U2; this launch's offers are U1/U2
            return write(name, src.read_text(encoding="utf-8").replace("TEST-ONLY-U1", "U1").replace("TEST-ONLY-U2", "U2"))

        bridge = write("landing-bridge.json", json.dumps({
            "skill71": {"root": str(S71), "python": sys.executable},
            "landing": {"run_dir": str(self.root / "landing-run"), "page_version": "standard", "page_kind": "sales",
                        "brand_owner": BRAND_OWNER, "image_cap": 200, "launch_record": str(out / "launch.json"),
                        "brand_file": str(self.brand_file), "image_inputs": str(out / "image_inputs.json"),
                        "manuscript": str(COPY_EXAMPLES / "standard-path-b.md")}}))
        return {
            "bridge_config": str(bridge),
            "author_session": "e2e-real-adapters",
            "checkout_manuscript": str(COPY_EXAMPLES / "checkout-example.md"),
            "copy": {"upsell_1": rebound(S80_FIXTURES / "copy-upsell1-public.valid.json", "copy-upsell_1.json"),
                     "upsell_2": rebound(S80_FIXTURES / "copy-upsell2-public.valid.json", "copy-upsell_2.json"),
                     "downsell_1": S81_PAGE,
                     "thank_you": COPY_EXAMPLES / "thank-you-path-b.md"},
            "journey": {"upsell_1": S80_JOURNEYS / "journey-main-only.testonly.json",
                        "upsell_2": S80_JOURNEYS / "journey-upsell2-from-upsell1.testonly.json",
                        "downsell_1": write("journey-downsell_1.json", json.dumps(
                            {"main_purchased_verified": True, "u1_event": "explicit_decline", "u1_accepted": False}))},
            "enrichment": {"upsell_1": S49_FIXTURES / "enrichment-upsell_1.json",
                           "upsell_2": S49_FIXTURES / "enrichment-upsell_2-onetime.json",
                           "downsell_1": write("enrichment-downsell_1.json", json.dumps(
                               {"difference_kind": "reduced_scope", "rationale": "TEST ONLY recorded rationale.",
                                "entry_guard_ref": "TEST-ENTRY-GUARD"}))},
        }

    def _stage_operator_inputs(self, out: Path) -> None:
        """The two files the design stages need staged in the dispatch folder by the operator: the run's
        measured design system and the thank-you copy. (The Skill 82 result files are NOT staged: a page
        built before any sale has none, and nothing here may hand-write them.)"""
        work = out / "dispatch"
        work.mkdir(parents=True)
        for name in ("design-prose.json", "design-prose-checkout.json", "design-prose-product_selection.json"):
            (work / name).write_text(_design_prose(), encoding="utf-8")
        (work / "copy-thank_you.md").write_text((COPY_EXAMPLES / "thank-you-path-b.md").read_text(encoding="utf-8"),
                                                encoding="utf-8")

    def _cli(self, *argv: str):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cli.main(list(argv))
        return code, buf.getvalue()

    def test_a_multiple_options_launch_builds_assembles_and_checks_on_the_real_adapters(self):
        doc = self._intake()
        out = self.root / "run"
        self._stage_operator_inputs(out)
        report = dispatch_tests.run_dispatch(doc, out, adapters_config=None, adapter_inputs=self._adapter_inputs(out),
                                             landing_pages=["sales"])

        # dispatch: every page of the funnel, free, on the stub provider
        self.assertEqual(sorted(report["pages"]), sorted(ROLES))
        self.assertEqual((report["executor_provider"], report["paid_calls_allowed"]), ("stub", False))
        self.assertFalse(self.marker.exists(), "the paid image adapter must never be started")
        fake_png = lane83_fake_consumer.PNG
        for role in ROLES:
            piece = json.loads((out / "pieces" / f"{role}.json").read_text(encoding="utf-8"))
            self.assertNotEqual(piece.get("author_session"), "lane83-fake-consumer", role)
            self.assertTrue(piece["artifacts"], f"{role} came back with no files at all")
            for art in piece["artifacts"]:
                path = Path(art["path"])
                self.assertTrue(path.is_file(), f"{role}: {path} was listed but never written")
                self.assertEqual(_sha256(path), art["sha256"], f"{role}: {path.name} does not match its recorded hash")
                self.assertNotEqual(path.read_bytes(), fake_png, f"{role}: {path.name} is the fake consumer's picture")

        # assemble, exactly as a client runs it (pages alone: the calendar and automations are other skills')
        intake_path = self.root / "intake.json"
        intake_path.write_text(json.dumps(doc), encoding="utf-8")
        package_dir = self.root / "package"
        code, _ = self._cli("assemble", "--intake", str(intake_path), "--pieces", str(out / "pieces"),
                            "--out", str(package_dir), "--page-only")
        self.assertEqual(code, 0)
        manifest_path = package_dir / "package-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(sorted(p["role"] for p in manifest["pieces"]), sorted(ROLES))

        # check: passes, and says what it is: section images only, the render still pending
        code, shown = self._cli("check", "--manifest", str(manifest_path), "--root", str(package_dir))
        self.assertEqual((code, shown.strip().splitlines()[-1]), (0, "PASS package complete"), shown)
        wording = (json.dumps(manifest) + (package_dir / "receipt.json").read_text(encoding="utf-8")).lower()
        self.assertIn(LABEL, wording, "a stub-provider package must say it holds images only, render pending")


if __name__ == "__main__":
    unittest.main()
