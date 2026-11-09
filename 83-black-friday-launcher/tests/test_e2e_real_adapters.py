"""STR-27: one offline end-to-end run of a multiple_options launch through the REAL adapters.

The other dispatch tests swap every page skill for tests/lane83_fake_consumer.py, which fabricates labeled
design files, so a defect anywhere in the real adapter chain (selection, thank-you, checkout, upsell,
downsell, landing) cannot show up in them. This test builds the adapter commands with
launcher_core.launch_bridge from per-page inputs (the same path as `cli dispatch --adapter-inputs`), runs
them on the free stub provider, then runs `cli assemble` and `cli check` over what they wrote.

It ends at the design gate. A stub run draws unlabeled layout proofs only (Skill 71 labels and composes only
paid renders), and final mockups need the client's recorded approval of a real (non-stub) Design Board, so
`check` refuses with exactly the missing section kinds for every page and nothing else. Every earlier step
must pass.
No network, no paid call, no fake consumer.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import re
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

import substrate  # noqa: E402
import lane83_fake_consumer  # noqa: E402  only for its marker constants: proves we did NOT use it
import test_lane83_dispatch as dispatch_tests  # noqa: E402  run_dispatch carries the approval and plan choices
from test_only_readback import TEST_ONLY_CHECKOUT_READBACK  # noqa: E402  (its path is added by test_lane83_dispatch)
from launcher_core import checks, cli, page_designs  # noqa: E402

S71 = REPO_ROOT / "71-blackceo-signature-page"
COPY_EXAMPLES = S71 / "tests" / "fixtures" / "copy_examples"
S80_FIXTURES = REPO_ROOT / "80-signature-upsell" / "components" / "80-signature-upsell" / "fixtures"
S80_JOURNEYS = REPO_ROOT / "80-signature-upsell" / "components" / "adapters" / "fixtures"
S81_PAGE = REPO_ROOT / "81-signature-downsell" / "fixtures" / "valid-downsell-page.json"
S81_EXTENSION = REPO_ROOT / "81-signature-downsell" / "fixtures" / "valid-downsell-result.json"
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
# the offer names the upsell copy fixtures were written for: the upsell page binds copy.offer_name to the offer
OFFER_NAMES = {"upsell_1": "TEST ONLY Deep Work Library", "upsell_2": "TEST ONLY Implementation Studio"}
D1_PRICE_MINOR = 3700  # the one-time D1 price the pinned Skill 81 result fixture records (due_now_minor); the page copy is re-priced to it
# The intake accepts one_time prices only, and Skill 49 refuses a one_time D1 whose copy promises a renewal, so the
# fixture's $1-trial-then-$27-a-month page is re-priced to a one-time D1 (the same way Skill 49's own wrapper test does).
_RENEWAL_PROMISE = ('After the trial, $27 per month continues the membership unless you cancel. The first renewal charge is '
                    'on day 31, and renewals are monthly after that. You can cancel anytime before a renewal charge to '
                    'stop future charges. If you cancel, your access continues until the end of the trial or the current '
                    'paid month, then your membership access ends and you will not be charged again. ')


_SPOOL = {}


def setUpModule():
    # Building a package appends launch events to ~/.openclaw/data/signature-launch/events-spool when no ingest
    # URL is set. Send them to a temp folder, so nothing in this module (or in a child launcher it starts,
    # which inherits the variable) writes into the real home folder.
    _SPOOL["dir"] = tempfile.TemporaryDirectory()
    _SPOOL["env"] = mock.patch.dict(os.environ, {"LAUNCH_EVENTS_SPOOL": _SPOOL["dir"].name})
    _SPOOL["env"].start()


def tearDownModule():
    _SPOOL["env"].stop()
    _SPOOL["dir"].cleanup()


def _one_time_d1_page() -> str:
    text = S81_PAGE.read_text(encoding="utf-8")
    text = json.dumps(json.loads(text))
    assert _RENEWAL_PROMISE in text
    page = json.loads(re.sub(r"\$1(?!\d)", "$%d" % (D1_PRICE_MINOR // 100), text.replace(_RENEWAL_PROMISE, "")))
    page["page"]["approved_amounts_minor"] = [D1_PRICE_MINOR]
    return json.dumps(page)


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
        doc = dispatch_tests.payload("elevation", design_style="B", image_provider="kie", image_cap=264,
                                     brand_file=str(self.brand_file), brand_owner=BRAND_OWNER)
        doc["brand"]["hash"] = _sha256(self.brand_file)  # the landing build re-hashes the brand file
        # every price names an entry of the client's answers file, which must say what this launch's offers say
        answers = json.loads((SKILL_ROOT / doc["answers_file"]).read_text(encoding="utf-8"))
        for offer in doc["offers"]:
            offer["name"] = OFFER_NAMES.get(offer["role"], offer["name"])
            if offer["role"] == "downsell_1":
                offer["price"]["amount_minor"] = D1_PRICE_MINOR
            if offer["role"] in DELIVERABLES:  # the upsell and downsell pages refuse to invent deliverables
                offer["level"] = {"state": "supplied", "name": offer["name"],
                                  "deliverables": DELIVERABLES[offer["role"]]}
                entry = answers["answers"][offer["role"]]["value"]
                entry["display_name"] = offer["name"]
                entry["price"]["amount_minor"] = offer["price"]["amount_minor"]
                entry["deliverables"] = DELIVERABLES[offer["role"]]
        self.answers_file = self.root / "answers.json"
        self.answers_file.write_text(json.dumps(answers), encoding="utf-8")
        doc["answers_file"] = str(self.answers_file)
        return doc

    def _checkout_manuscript(self, doc: dict) -> str:
        """The order-form copy for THIS launch: the fixture's five-section shape, with the offer, price, bump and
        the approved guarantee, terms and consent written from the launch record and the intake (the checkout
        wrapper refuses a price, name or terms text that differs from them)."""
        main = next(o for o in doc["offers"] if o["role"] == "main")
        bump = next(o for o in doc["offers"] if o["role"] == "bump")
        terms = doc.get("checkout_terms")
        if not terms:  # an intake from before the approved-terms block: the fixture's own copy, as shipped
            return (COPY_EXAMPLES / "checkout-example.md").read_text(encoding="utf-8")
        money = lambda o: f"${o['price']['amount_minor'] // 100}"  # noqa: E731  whole-dollar test prices
        shape = (COPY_EXAMPLES / "checkout-example.md").read_text(encoding="utf-8")
        head, rest = shape.split("## Section 2", 1)
        tail = "## Section 5" + rest.split("## Section 5", 1)[1]
        return (f"{head}## Section 2: Offer details and price\n\n{main['name']}, one payment of {money(main)}.\n\n"
                f"Due today: {money(main)}.\n\n"
                f"## Section 3: Order bump\n\nYes, add the {bump['name']} to my order.\n\n"
                f"Ten ready-to-use planning templates. One-time price of {money(bump)}.\n\n"
                f"## Section 4: Guarantee and terms\n\n{terms['guarantee_text']}\n\n{terms['terms_text']}\n\n"
                f"{terms['consent_text']}\n\n{tail}")

    def _adapter_inputs(self, out: Path, doc: dict) -> dict:
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

        difference_table = write("difference-table.json", json.dumps(
            {"difference_kind": "reduced_scope", "rationale": "TEST ONLY recorded rationale."}))

        bridge = write("landing-bridge.json", json.dumps({
            "skill71": {"root": str(S71), "python": sys.executable},
            "landing": {"run_dir": str(self.root / "landing-run"), "page_version": "standard", "page_kind": "sales",
                        "brand_owner": BRAND_OWNER, "image_cap": 264, "launch_record": str(out / "launch.json"),
                        # the 14 production stages are closed by an agent-driven process, never in an offline run:
                        # the landing lane is a declared draft, so the bridge places its result with the gate open
                        "draft": True,
                        "brand_file": str(self.brand_file), "image_inputs": str(out / "image_inputs.json"),
                        "manuscript": str(COPY_EXAMPLES / "standard-path-b.md")}}))
        return {
            "bridge_config": str(bridge),
            "author_session": "e2e-real-adapters",
            "checkout_manuscript": str(write("checkout-manuscript.md", self._checkout_manuscript(doc))),
            "copy": {"upsell_1": rebound(S80_FIXTURES / "copy-upsell1-public.valid.json", "copy-upsell_1.json"),
                     "upsell_2": rebound(S80_FIXTURES / "copy-upsell2-public.valid.json", "copy-upsell_2.json"),
                     "downsell_1": write("copy-downsell_1.json", _one_time_d1_page()),
                     "thank_you": COPY_EXAMPLES / "thank-you-path-b.md"},
            "journey": {"upsell_1": S80_JOURNEYS / "journey-main-only.testonly.json",
                        "upsell_2": S80_JOURNEYS / "journey-upsell2-from-upsell1.testonly.json",
                        "downsell_1": write("journey-downsell_1.json", json.dumps(
                            {"main_purchased_verified": True, "u1_event": "explicit_decline", "u1_accepted": False}))},
            "enrichment": {"upsell_1": S49_FIXTURES / "enrichment-upsell_1.json",
                           "upsell_2": S49_FIXTURES / "enrichment-upsell_2-onetime.json",
                           "downsell_1": write("enrichment-downsell_1.json", json.dumps(
                               {"difference_kind": "reduced_scope", "rationale": "TEST ONLY recorded rationale.",
                                "entry_guard_ref": "TEST-ENTRY-GUARD",
                                "difference_table_ref": str(difference_table)}))},
        }

    def _stage_operator_inputs(self, out: Path, launch_id: str) -> None:
        """What the operator stages in the dispatch folder: the run's measured design system, the thank-you copy
        and the downsell's result extension. (The Skill 82 result files are NOT staged: a page
        built before any sale has none, and nothing here may hand-write them.)"""
        work = out / "dispatch"
        work.mkdir(parents=True)
        for name in ("design-prose.json", "design-prose-checkout.json"):
            (work / name).write_text(_design_prose(), encoding="utf-8")
        # the downsell wrapper assembles its result around the extension record the Skill 81 side stages beside it
        # (the fixture matched to the page fixture above); it checks it against the launch record and the route,
        # so it names this launch's upsell_2 page (Skill 49 ids a page <launch_id>-<ROLE>: the launch id as
        # given, the role in upper case)
        extension = json.loads(S81_EXTENSION.read_text(encoding="utf-8"))
        extension["downsell_result_extension"]["route_result"]["canonical_u2_page_id"] = \
            f"{launch_id}-UPSELL_2"
        (work / "extension-downsell_1.json").write_text(json.dumps(extension), encoding="utf-8")
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
        self._stage_operator_inputs(out, doc["launch_id"])
        # the measured design system reaches the order-page inputs through the intake's declared image_plan key
        doc["image_plan"]["design_prose_ref"] = str(out / "dispatch" / "design-prose.json")
        # the intake names the approval on record: the verified ref and the hash of the plan it approves (the
        # CLI's assemble refuses an intake whose approval is not the one the dispatch bound)
        doc["approval"] = {"ref": "APPR-TEST", "hash": substrate.dispatch().vlp.plan_document_hash(
            dispatch_tests.launch_for(doc, landing_pages=["sales"]))}
        report = dispatch_tests.run_dispatch(doc, out, adapters_config=None, adapter_inputs=self._adapter_inputs(out, doc),
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
                # a relative path is relative to the folder holding pieces/, or (the landing bridge lists its files
                # run-relative) to the landing run folder: the two places assemble looks
                path = next((b / art["path"] for b in (out, self.root / "landing-run") if (b / art["path"]).is_file()),
                            out / art["path"])
                self.assertTrue(path.is_file(), f"{role}: {path} was listed but never written")
                self.assertEqual(_sha256(path), art["sha256"], f"{role}: {path.name} does not match its recorded hash")
                self.assertNotEqual(path.read_bytes(), fake_png, f"{role}: {path.name} is the fake consumer's picture")

        # assemble, exactly as a client runs it (pages alone: the calendar and automations are other skills')
        intake_path = self.root / "intake.json"
        intake_path.write_text(json.dumps(doc), encoding="utf-8")
        package_dir = self.root / "package"
        readback = self.root / "checkout-readback.json"  # what the Skill 06 install read-back records for the order form
        readback.write_text(json.dumps(TEST_ONLY_CHECKOUT_READBACK), encoding="utf-8")
        code, shown = self._cli("assemble", "--intake", str(intake_path), "--pieces", str(out / "pieces"),
                                "--out", str(package_dir), "--page-only", "--checkout-readback", str(readback))
        self.assertEqual(code, 0, shown)
        manifest_path = package_dir / "package-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(sorted(p["role"] for p in manifest["pieces"]), sorted(ROLES))

        # every default the launcher chose for the client is confirmed by the client before check will pass
        confirmations = [{"field": e["field"], "confirmation_ref": "TEST-CLIENT-CONFIRMATION"}
                         for e in report["to_confirm"]]
        (package_dir / "client-confirmations.json").write_text(json.dumps({"confirmations": confirmations}),
                                                               encoding="utf-8")

        # check: everything passes up to the design gate, which refuses exactly the designs a stub run
        # cannot honestly have (IMG-02: only labeled, client-approved final mockups count; a stub run labels nothing)
        code, shown = self._cli("check", "--manifest", str(manifest_path), "--root", str(package_dir))
        self.assertEqual(code, 2, shown)
        self.assertIn("delivery level: designs: failed", shown)
        self.assertNotIn("PASS package complete", shown)
        expected = {f"{page_designs.CODE}: {page_designs.page_key(p)} is missing {k.replace('_', ' ')}"
                    for p in manifest["pieces"] for k in checks.SECTION_KINDS}
        self.assertEqual(len(expected), len(ROLES) * len(checks.SECTION_KINDS))
        got = {line.strip()[2:] for line in shown.splitlines() if line.strip().startswith("- ")}
        self.assertEqual(got, expected, shown)
        # the package says the client has approved nothing yet: no approval was recorded, none is claimed
        self.assertEqual(manifest["design_approvals"], page_designs.default_approvals())


if __name__ == "__main__":
    unittest.main()
