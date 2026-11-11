"""Issue 57 (M5): the ``stage_state`` carrier. A client package can be assembled, and only a closed run passes.

Skill 71 writes every page run's closed-stage record at ``<page run>/private/state.json``. Skill 83's design gate
(page_designs) demands a copy of it in the package, named by each piece. Nothing wrote that copy and
``package._validate_piece`` dropped the key, so every non-test package was refused. Now:

* ``launch_bridge`` copies the run's state beside the piece (``pieces/<slot>.stage-state.json``) and records
  ``{path, sha256}`` on the piece, per landing slot from that slot's OWN run;
* ``package._validate_piece`` carries it only when the copy hashes to the recorded sha256
  (``AF-LAUNCH-PKG-PIECE: stage_state does not verify``) and requires it for a client delivery;
* ``package.assemble`` lays the copy into the package, where ``page_designs`` reads it: a closed run assembles,
  an open one is refused (``AF-LAUNCH-ASSEMBLE-DESIGN``).

Free: pure files and the fake page consumer. Nothing calls a provider or a hosting service.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parent
for entry in (SKILL_ROOT, SKILL_ROOT / "routes", SKILL_ROOT / "fixtures", HERE):
    sys.path.insert(0, str(entry))

import substrate  # noqa: E402
import test_check_rules as tcr  # noqa: E402  (a module reference, so its TestCases are not collected twice)
from launcher_core import launch_bridge, package, page_designs  # noqa: E402
from test_lane83_designs import make_piece  # noqa: E402
from test_only_readback import TEST_ONLY_CHECKOUT_READBACK  # noqa: E402
from test_page_designs_real import design_files  # noqa: E402

STAGES = ("desktop-wireframe", "mobile-tablet", "final-mockups", "design-board")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class CarrierBridgeTests(unittest.TestCase):
    """launch_bridge: the writer. No assemble, no dispatch: a piece, a page run and the copy that results."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / "launch"
        (self.out / "pieces").mkdir(parents=True)

    def page_run(self, name: str, state: dict) -> Path:
        run = Path(self.tmp.name) / "runs" / name
        (run / "private").mkdir(parents=True)
        (run / "private" / "state.json").write_text(json.dumps(state), encoding="utf-8")
        (run / "desktop-wireframes").mkdir()
        (run / "desktop-wireframes" / f"{name}_desktop_wireframe_s01-of-01_hero.png").write_bytes(b"png-" + name.encode())
        return run

    def piece_for(self, run: Path, *, absolute: bool) -> dict:
        rel = next((run / "desktop-wireframes").iterdir())
        path = str(rel) if absolute else str(rel.relative_to(run))
        return {"artifacts": [{"path": path, "sha256": sha(rel.read_bytes())}]}

    def test_the_run_state_is_copied_beside_the_piece_and_recorded_with_its_hash(self):
        run = self.page_run("upsell-1", {"stages": {"final-mockups": {"status": "closed"}}})
        piece = self.piece_for(run, absolute=True)
        self.assertTrue(launch_bridge.attach_stage_state(piece, "upsell_1", self.out, [self.out]))
        ref = piece["stage_state"]
        self.assertEqual(ref["path"], "pieces/upsell_1.stage-state.json")
        copy = self.out / ref["path"]
        self.assertEqual(copy.read_bytes(), (run / "private" / "state.json").read_bytes())
        self.assertEqual(ref["sha256"], sha(copy.read_bytes()))

    def test_a_relative_path_resolves_through_the_landing_run_folders(self):
        run = self.page_run("sales-run", {"stages": {}})
        (self.out / "dispatch").mkdir()
        (self.out / "dispatch" / "landing-bridge.json").write_text(
            json.dumps({"landing": {"run_dir": str(run)}}), encoding="utf-8")
        piece = self.piece_for(run, absolute=False)  # the bridge lists files run-relative
        bases = launch_bridge.stage_state_bases(self.out)
        self.assertTrue(launch_bridge.attach_stage_state(piece, "landing", self.out, bases))

    def test_each_landing_slot_carries_its_own_runs_state_never_the_other_pages(self):
        sales = self.page_run("sales-run", {"stages": {"final-mockups": {"status": "closed"}}})
        opt_in = self.page_run("optin-run", {"stages": {"final-mockups": {"status": "open"}}})
        a, b = self.piece_for(sales, absolute=True), self.piece_for(opt_in, absolute=True)
        launch_bridge.attach_stage_state(a, "sales", self.out, [self.out])
        launch_bridge.attach_stage_state(b, "landing", self.out, [self.out])
        self.assertNotEqual(a["stage_state"]["sha256"], b["stage_state"]["sha256"])
        self.assertIn('"closed"', (self.out / a["stage_state"]["path"]).read_text(encoding="utf-8"))
        self.assertIn('"open"', (self.out / b["stage_state"]["path"]).read_text(encoding="utf-8"))

    def test_a_piece_that_names_no_stage_gate_run_is_left_without_one(self):
        loose = self.out / "loose.png"
        loose.write_bytes(b"x")
        piece = {"artifacts": [{"path": str(loose), "sha256": sha(b"x")}]}
        self.assertFalse(launch_bridge.attach_stage_state(piece, "thank_you", self.out, [self.out]))
        self.assertNotIn("stage_state", piece)
        self.assertEqual(list((self.out / "pieces").iterdir()), [])

    def test_refresh_re_copies_the_state_after_a_later_stage_closed(self):
        run = self.page_run("upsell-1", {"stages": {"final-mockups": {"status": "open"}}})
        piece = self.piece_for(run, absolute=True)
        launch_bridge.attach_stage_state(piece, "upsell_1", self.out, [self.out])
        (self.out / "pieces" / "upsell_1.json").write_text(json.dumps(piece), encoding="utf-8")
        before = piece["stage_state"]["sha256"]
        (run / "private" / "state.json").write_text(
            json.dumps({"stages": {"final-mockups": {"status": "closed"}}}), encoding="utf-8")  # the driver closed it
        self.assertEqual(launch_bridge.refresh_stage_states(self.out), ["upsell_1"])
        after = json.loads((self.out / "pieces" / "upsell_1.json").read_text(encoding="utf-8"))["stage_state"]
        self.assertNotEqual(after["sha256"], before)
        self.assertEqual(after["sha256"], sha((self.out / after["path"]).read_bytes()))


class CarrierPackageTests(tcr.PackageCase):
    """package.assemble as a CLIENT delivery (test_only false). The dispatch binding and Skill 49's receipt store
    are the recorded stand-ins test_check_rules uses; everything about stage_state is real."""

    test_only = False

    def setUp(self):
        super().setUp()
        clocked = tcr._ClockedS79Validator(substrate.s79_validate_checkout())
        from launcher_core import checks
        for target, name in ((substrate, "s79_validate_checkout"), (checks, "_load_checkout_validator")):
            patcher = mock.patch.object(target, name, return_value=clocked)
            patcher.start()
            self.addCleanup(patcher.stop)

    def assemble_client(self, pieces, name="pkg", **kw):
        run = self.work / f"dispatch-run-{name}"
        (run / "dispatch").mkdir(parents=True, exist_ok=True)
        (run / "dispatch" / "result-landing.json").write_text("{}", encoding="utf-8")
        (run / "dispatch" / "bridge-receipt-result-landing.json").write_text(json.dumps(
            {"request_id": "req-landing", "draft": False, "receipt_validation": "schema", "pipeline_exit": 0}),
            encoding="utf-8")
        approved = self.normalized["approval"]["hash"]
        launch = launch_bridge.to_launch_record(self.normalized, self.graph,
                                                {"image_provider": "other_explicit", "design_style": "A"})
        readback = {**TEST_ONLY_CHECKOUT_READBACK, "native": {
            price["price_choice_id"]: {"native_product_id": f"TEST-ONLY-PRODUCT-{offer['offer_id']}",
                                       "native_price_id": f"TEST-ONLY-PRICE-{price['price_choice_id']}"}
            for offer in launch["offers"] for price in offer["prices"]}}
        binding = {"state": package.DISPATCH_STATE_BOUND, "root": run, "plan_document_hash": approved,
                   "requests": {}, "plan_hash_matches": True, "to_confirm": [], "landing_pages": ["landing"],
                   "landing_results": {"landing": run / "dispatch" / "result-landing.json"},
                   "record": {"state": package.DISPATCH_STATE_BOUND, "plan_document_hash": approved}}
        kw.setdefault("checkout_readback", readback)
        with mock.patch.object(package, "_find_dispatch_root", return_value=(run, True)), \
                mock.patch.object(package, "_bind_dispatch", return_value=binding), \
                mock.patch.object(package, "_bind_piece"), \
                mock.patch.object(package, "_load_receipt_module", return_value=tcr.store()):
            return package.assemble(self.work / name, self.normalized, self.graph, pieces,
                                    source_root=self.work, council=tcr.COUNCIL, **kw)

    def client_pieces(self, *, status: str = "closed", carry: bool = True) -> dict:
        """Every route page as a finished Skill 71 page run: real design files, a private/state.json whose closed
        stages hash them (keyed by the path the package will carry them at), and the carrier launch_bridge writes."""
        pieces = {}
        rules = page_designs.load_page_rules()
        for node in self.graph["nodes"]:
            role, piece = node["role"], make_piece(self.work, self.normalized, node, provider="kie")
            identity = {"role": role, "page_kind": piece.get("page_kind") or role}  # what package.assemble records
            counts = page_designs._section_rule(identity, rules)
            run = self.work / "runs" / role
            arts, hashes = design_files(run, "design", page_designs.label_slug(identity),
                                        min(counts) if counts else 2)
            keyed = {stage: {f"pieces/{node['page_id']}/{rel[len('design/'):]}": digest
                             for rel, digest in files.items()} for stage, files in hashes.items()}
            state = {"stages": {s: {"status": status, "receipt_status": "pass", "artifact_hashes": keyed[s]}
                                for s in STAGES}}
            (run / "private").mkdir(parents=True, exist_ok=True)
            (run / "private" / "state.json").write_text(json.dumps(state), encoding="utf-8")
            piece["artifacts"] = [{**a, "path": str(run / a["path"])} for a in arts]
            if carry:
                self.assertTrue(launch_bridge.attach_stage_state(piece, role, self.work, [self.work]))
            pieces[role] = piece
        return pieces

    def test_a_closed_run_assembles_as_a_client_package_and_the_state_rides_in_it(self):
        built = self.assemble_client(self.client_pieces(), refuse_incomplete_designs=True)
        manifest = built["manifest"]
        self.assertIs(manifest["test_only"], False)
        for piece in manifest["pieces"]:
            ref = piece["stage_state"]  # the key survives packaging (it was stripped here before)
            self.assertEqual(sha((self.work / "pkg" / ref["path"]).read_bytes()), ref["sha256"], piece["role"])
        self.assertEqual(page_designs.design_violations(manifest, self.work / "pkg"), [])

    def test_the_files_a_paid_run_leaves_assemble_through_the_packager_with_the_state_the_bridge_copies(self):
        # test_paid_run_designs_seam proves the paid run's files are the files AF-LAUNCH-PAGE-DESIGNS counts; this is
        # the same page going through package.assemble, which that test used to bypass.
        import test_paid_run_designs_seam as seam
        pieces = self.client_pieces()
        node = next(n for n in self.graph["nodes"] if n["role"] == seam.PAGE)
        paid = seam.PaidRun(self.work / "paid")
        for stage in ("desktop-wireframe", "mobile-tablet", "visual-mockup", "final-mockups"):
            paid.draw(stage)
        paid.board()
        relative = {a["path"]: a["sha256"] for a in paid.artifacts(relative=True)}
        hashes = {stage: {} for stage in STAGES}
        for path, digest in relative.items():
            stage = seam.STAGE_OF.get(page_designs.classify(path))
            if stage:  # keyed by the path the package will carry the file at
                hashes[stage][f"pieces/{node['page_id']}/{path}"] = digest
        hashes["design-board"] = {f"pieces/{node['page_id']}/{p}": d for p, d in relative.items()
                                  if page_designs.classify(p) == "board"}
        state = {"stages": {s: {"status": "closed", "receipt_status": "pass", "artifact_hashes": h}
                            for s, h in hashes.items()}}
        (paid.run / "private").mkdir(exist_ok=True)
        (paid.run / "private" / "state.json").write_text(json.dumps(state), encoding="utf-8")
        piece = pieces[seam.PAGE]
        piece["artifacts"] = paid.artifacts(relative=False)
        self.assertTrue(launch_bridge.attach_stage_state(piece, seam.PAGE, self.work, [self.work]))
        built = self.assemble_client(pieces, refuse_incomplete_designs=True)
        carried = next(p for p in built["manifest"]["pieces"] if p["role"] == seam.PAGE)
        self.assertEqual(carried["stage_state"], piece["stage_state"])
        self.assertEqual(page_designs.design_violations(built["manifest"], self.work / "pkg"), [])

    def test_a_run_whose_stages_never_closed_is_refused(self):
        with self.assertRaises(package.PackageError) as ctx:
            self.assemble_client(self.client_pieces(status="open"), refuse_incomplete_designs=True)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-ASSEMBLE-DESIGN")
        self.assertFalse((self.work / "pkg" / "package-manifest.json").exists())  # nothing was sealed

    def test_a_stage_state_whose_sha_is_wrong_is_refused_by_name(self):
        pieces = self.client_pieces()
        pieces["checkout"]["stage_state"]["sha256"] = "0" * 64
        with self.assertRaises(package.PackageError) as ctx:
            self.assemble_client(pieces, refuse_incomplete_designs=True)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-PKG-PIECE")
        self.assertIn("stage_state does not verify", ctx.exception.detail)

    def test_a_state_file_edited_after_the_piece_recorded_it_is_refused(self):
        pieces = self.client_pieces()
        path = self.work / pieces["checkout"]["stage_state"]["path"]
        path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
        with self.assertRaises(package.PackageError) as ctx:
            self.assemble_client(pieces, refuse_incomplete_designs=True)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-PKG-PIECE")

    def test_a_client_piece_with_no_stage_state_at_all_is_refused(self):
        with self.assertRaises(package.PackageError) as ctx:
            self.assemble_client(self.client_pieces(carry=False), refuse_incomplete_designs=True)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-PKG-PIECE")
        self.assertIn("stage_state is required for a client delivery", ctx.exception.detail)

    def test_a_stage_state_path_that_leaves_the_run_is_refused(self):
        pieces = self.client_pieces()
        pieces["checkout"]["stage_state"]["path"] = "../escape.json"
        with self.assertRaises(package.PackageError) as ctx:
            self.assemble_client(pieces, refuse_incomplete_designs=True)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-PKG-PIECE")


class PracticePieceTests(tcr.PackageCase):
    """A practice package needs no stage_state, but one that is given must still verify."""

    def test_a_practice_piece_without_stage_state_still_assembles(self):
        built, root = self.build()
        self.assertTrue(all("stage_state" not in p for p in built["manifest"]["pieces"]))

    def test_a_practice_piece_with_a_bad_stage_state_is_refused(self):
        pieces = self.pieces()
        pieces["checkout"]["stage_state"] = {"path": "missing.json", "sha256": "a" * 64}
        with self.assertRaises(package.PackageError) as ctx:
            self.build(pieces)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-PKG-PIECE")


if __name__ == "__main__":
    unittest.main()
