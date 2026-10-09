#!/usr/bin/env python3
"""DEL-13 contract tests: the 12 package items, the folder, the packaging call.

Green on their own -- they exercise the folder contract and the packaging
entry point with injected producers, so neither half needs a sibling DEL unit
to be proven. The end-to-end run through the real components lives in
test_delivery_package_e2e.py.

Run: python3 delivery_package/test_delivery_package_contract.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_CORE = _HERE.parents[0]                       # .../scripts/core
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))

import delivery_package.contract as C           # noqa: E402
import delivery_package.packaging as P          # noqa: E402

PDF = b"%PDF-1.4\n1 0 obj\n<< >>\nendobj\n%%EOF\n"
SRT_OK = "1\n00:00:00,000 --> 00:00:01,000\nline\n"
SRT_BAD = "1\n00:00:00,000 - 00:00:01,000\nline\n"
MEDIA = b"media-bytes" * 8
PNG = b"\x89PNG\r\n\x1a\nimage" * 2
NOTE = b"# note\n"


def fake_producers(root):
    """One producer per package item writing contract-valid sources under root."""
    out = {}
    for item in C.PACKAGE_ITEMS:
        src_dir = Path(root) / ("src-" + item.key)
        src_dir.mkdir(parents=True, exist_ok=True)
        paths = []
        for i, (name, kind) in enumerate(zip(item.files, item.kinds), 1):
            if kind.startswith("images"):
                d = src_dir / name
                d.mkdir(parents=True, exist_ok=True)
                (d / ("%02d.png" % i)).write_bytes(PNG)
                paths.append(d)
                continue
            p = src_dir / name
            if kind == "pdf":
                p.write_bytes(PDF)
            elif kind == "srt":
                p.write_text(SRT_OK, encoding="utf-8")
            elif kind == "text":
                p.write_bytes(NOTE)
            else:
                p.write_bytes(MEDIA)
            paths.append(p)

        def make(paths):
            return lambda run_dir, item, _p=paths: list(_p)
        out[item.key] = make(paths)
    return out


class CanonicalList(unittest.TestCase):
    def test_twelve_items_numbered_1_to_12(self):
        self.assertEqual(len(C.PACKAGE_ITEMS), 12)
        self.assertEqual([i.number for i in C.PACKAGE_ITEMS],
                         list(range(1, 13)))
        self.assertEqual(len(set(i.key for i in C.PACKAGE_ITEMS)), 12)

    def test_file_names_carry_the_item_number(self):
        for item in C.PACKAGE_ITEMS:
            self.assertEqual(len(item.files), len(item.kinds),
                             item.key)
            prefix = "%02d - " % item.number
            for name in item.files:
                self.assertTrue(name.startswith(prefix),
                                "%s: %s lacks %s" % (item.key, name, prefix))

    def test_labels_cover_the_twelve_package_items(self):
        labels = " ".join(i.label for i in C.PACKAGE_ITEMS).upper()
        for word in ("AUDIO", "CHARACTER BIBLE", "SCRIPT", "STORYBOARD",
                     "VIDEO", "CLIPS", "READY-TO-POST", "THUMBNAIL",
                     "LYRIC", "SRT", "CHARACTER IMAGES", "WELCOME"):
            self.assertIn(word, labels)

    def test_every_item_names_its_del_unit(self):
        for item in C.PACKAGE_ITEMS:
            self.assertRegex(item.unit, r"^DEL-\d{2}$")


class FolderContract(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="del13-contract-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_reference_package_verifies_complete(self):
        folder = C.write_reference_package(self.tmp / "delivery")
        report = C.verify_folder(folder)
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["missing"], [])
        self.assertEqual(len(report["present"]), 12)

    def test_missing_folder_misses_all_twelve(self):
        report = C.verify_folder(self.tmp / "nope")
        self.assertFalse(report["ok"])
        self.assertEqual(len(report["missing"]), 12)
        self.assertIn("delivery folder missing", report["problems"][0]["problem"])

    def test_each_missing_item_is_named(self):
        for item in C.PACKAGE_ITEMS:
            folder = C.write_reference_package(self.tmp / ("d-" + item.key))
            first = folder / item.files[0]
            if first.is_dir():
                shutil.rmtree(first)
            else:
                first.unlink()
            report = C.verify_folder(folder)
            self.assertFalse(report["ok"], item.key)
            self.assertEqual(report["missing"], [item.key],
                             "%s not the only missing item" % item.key)
            self.assertEqual(report["problems"][0]["file"], item.files[0])
            self.assertEqual(report["problems"][0]["unit"], item.unit)

    def test_empty_file_does_not_open(self):
        folder = C.write_reference_package(self.tmp / "empty")
        (folder / "03 - SCRIPT.pdf").write_bytes(b"")
        report = C.verify_folder(folder)
        self.assertIn("script_pdf", report["missing"])
        self.assertEqual(report["problems"][0]["problem"], "empty")

    def test_renamed_text_file_is_not_a_pdf(self):
        folder = C.write_reference_package(self.tmp / "fakepdf")
        (folder / "12 - Welcome Sheet.pdf").write_text("not a pdf",
                                                       encoding="utf-8")
        report = C.verify_folder(folder)
        self.assertIn("welcome_sheet", report["missing"])
        self.assertIn("no %PDF- header", report["problems"][0]["problem"])

    def test_srt_needs_a_cue_timing_line(self):
        folder = C.write_reference_package(self.tmp / "badsrt")
        (folder / "10 - Captions.srt").write_text(SRT_BAD, encoding="utf-8")
        report = C.verify_folder(folder)
        self.assertIn("captions_srt", report["missing"])
        self.assertIn("cue timing line", report["problems"][0]["problem"])

    def test_image_item_needs_a_directory_of_images(self):
        folder = C.write_reference_package(self.tmp / "images")
        shutil.rmtree(folder / "11 - Character Images")
        (folder / "11 - Character Images").write_bytes(b"one blob")
        report = C.verify_folder(folder)
        self.assertIn("character_images", report["missing"])
        self.assertEqual(report["problems"][0]["problem"], "not a directory")


class PackagingEntryPoint(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="del13-pack-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.run = self.tmp / "run"
        self.run.mkdir()
        self.out = self.tmp / "delivery"

    def test_full_packaging_path_writes_a_verifying_folder(self):
        res = P.package_run(self.run, self.out, producers=fake_producers(self.tmp))
        report = C.verify_folder(self.out)
        self.assertTrue(report["ok"], report)
        self.assertEqual(len(res["items"]), 12)
        self.assertEqual(len(res["files"]), 18)   # 4+2+1+1+2+2+1+1+1+1+1+1 across the 12 items
        self.assertEqual(res["contract_version"], C.CONTRACT_VERSION)
        for item in C.PACKAGE_ITEMS:
            for name in item.files:
                self.assertTrue((self.out / name).exists(), name)

    def test_missing_component_surfaces_before_any_write(self):
        producers = fake_producers(self.tmp)
        del producers["welcome_sheet"]
        with self.assertRaises(P.PackageError) as ctx:
            P.package_run(self.run, self.out, producers=producers)
        self.assertEqual(ctx.exception.code, "COMPONENT_MISSING")
        self.assertIn("DEL-12", str(ctx.exception))
        self.assertIn("welcome_sheet", ctx.exception.items)
        self.assertFalse(self.out.exists(),
                         "a refused packaging call must write nothing")

    def test_no_discovered_component_reports_every_item(self):
        # Injected-empty producers: nothing is wired, so the call refuses
        # before writing and names all 12 items still owed.
        with self.assertRaises(P.PackageError) as ctx:
            P.package_run(self.run, self.out, producers={})
        self.assertEqual(ctx.exception.code, "COMPONENT_MISSING")
        self.assertEqual(set(ctx.exception.items),
                         {i.key for i in C.PACKAGE_ITEMS})

    def test_producer_raising_fails_the_call(self):
        def boom(run_dir, item):
            raise RuntimeError("encoder down")
        producers = fake_producers(self.tmp)
        producers["video"] = boom
        with self.assertRaises(P.PackageError) as ctx:
            P.package_run(self.run, self.out, producers=producers)
        self.assertEqual(ctx.exception.code, "COMPONENT_FAILED")
        self.assertIn("encoder down", str(ctx.exception))

    def test_producer_with_the_wrong_file_count_fails(self):
        def short(run_dir, item):
            return [self.run / "only-one.mp4"]
        producers = fake_producers(self.tmp)
        producers["clips"] = short
        (self.run / "only-one.mp4").write_bytes(MEDIA)
        with self.assertRaises(P.PackageError) as ctx:
            P.package_run(self.run, self.out, producers=producers)
        self.assertEqual(ctx.exception.code, "COMPONENT_FAILED")
        self.assertIn("contract wants 2", str(ctx.exception))

    def test_missing_run_folder_is_bad_input(self):
        with self.assertRaises(P.PackageError) as ctx:
            P.package_run(self.tmp / "absent", self.out)
        self.assertEqual(ctx.exception.code, "BAD_INPUT")

    def test_resolve_producer_says_which_component_owes_the_call(self):
        # A synthetic item whose only candidate is a module that does not
        # exist: discovery must say so, naming the unit and the module tried.
        item = C.ITEMS_BY_KEY["welcome_sheet"]._replace(
            producers=("del13_absent_component",))
        fn, note = P.resolve_producer(item)
        self.assertIsNone(fn)
        self.assertIn(item.unit, note)
        self.assertIn("del13_absent_component", note)

    def test_resolve_producer_finds_a_wired_component(self):
        import types
        def sample(run_dir, item):
            return []
        mod = types.ModuleType("del13_fake_component")
        mod.produce_delivery = sample
        sys.modules[mod.__name__] = mod
        self.addCleanup(sys.modules.pop, mod.__name__, None)
        item = C.PACKAGE_ITEMS[0]._replace(producers=("del13_fake_component",))
        fn, note = P.resolve_producer(item)
        self.assertIsNotNone(fn, note)
        self.assertIn("wired via", note)


if __name__ == "__main__":
    unittest.main(verbosity=2)
