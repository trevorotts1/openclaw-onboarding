#!/usr/bin/env python3
"""IMG-21 / IMG-06: the executor enforces the approved image ceiling and writes transport-bound receipts.

Pins (no paid API is called; a fake Skill 74 adapter stands in):
  (a) image_cap 2 refuses the third paid render, and the adapter is never called for it;
  (b) a paid run with no intake image_cap is refused before anything is written;
  (c) a provider failure does not use up the ceiling (only successful calls count);
  (d) a clean executor run writes receipts/kie74/<task_id>.json binding task_id, sha256 of the
      saved bytes and numeric credits_before/credits_after (after <= before), and that receipt
      satisfies the legacy gate's own task check with no manual receipt step;
  (e) a receipt for task id 'abc123' whose PNG hash differs, or a run with no receipt store, fails;
  (f) shared_page_service refuses a production run without receipts and accepts one with them.
"""
import hashlib
import json
import os
import shlex
import shutil
import sys
import tempfile
import textwrap
import unittest
from argparse import Namespace
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "scripts"))
import stage_executor as exe  # noqa: E402
import stage_gate  # noqa: E402
import test_shared_page_service_generation as base  # noqa: E402

RECEIPT_MODULE = ROOT.parent / "49-signature-funnel" / "scripts" / "kie74_receipt.py"

FAKE_ADAPTER = textwrap.dedent('''
    import json, os, sys
    from pathlib import Path
    state = Path(os.environ["FAKE_STATE"])
    n = int(state.read_text()) if state.exists() else 0
    cmd = sys.argv[1]
    if cmd == "credits":
        print(json.dumps({"state": "success", "data": {"credits": 1000 - 4 * n}}, indent=2))
    elif cmd == "run":
        if os.environ.get("FAKE_FAIL"):
            print(json.dumps({"state": "fail", "error": {"msg": "provider said no"}}, indent=2))
            sys.exit(1)
        n += 1
        state.write_text(str(n))
        save = Path(sys.argv[sys.argv.index("--save-dir") + 1])
        png = save / f"out-{n}.png"
        png.write_bytes(b"\\x89PNG\\r\\n\\x1a\\n" + f"bytes-{n}".encode())
        print(json.dumps({"provider": "kie", "adapter": "74-kie-live-adapter", "adapter_mode": "active",
                          "backend": "native-live", "model_id": "gpt-image-x", "task_id": f"task-{n:03d}",
                          "state": "success", "result_urls": ["https://example.invalid/a.png"],
                          "saved_paths": [str(png)], "fallback_used": False, "warnings": [],
                          "data": {}}, indent=2))
''')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class CapAndReceipts(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp(prefix="s71-cap-"))
        self.addCleanup(lambda: shutil.rmtree(self.td, ignore_errors=True))
        self.run_dir = self.td / "run"
        self.run_dir.mkdir()
        self.adapter = self.td / "fake_adapter.py"
        self.adapter.write_text(FAKE_ADAPTER, encoding="utf-8")
        self.state = self.td / "calls.txt"
        env = {"FAKE_STATE": str(self.state)}
        for key, value in env.items():
            os.environ[key] = value
            self.addCleanup(os.environ.pop, key, None)
        self.set_cap(2)

    def set_cap(self, cap):
        doc = {} if cap is None else {"image_cap": cap}
        (self.run_dir / "intake.json").write_text(json.dumps(doc), encoding="utf-8")

    def render(self, n):
        provider = exe.KieProvider(self.adapter, self.run_dir)
        # F18: the paid boundary freezes and re-checks the prompt; use an in-band prompt
        # (97.5 percent of the recorded 20,000-char maximum) so this test measures the
        # spend ledger, not the prompt band.
        job = {"stage": "visual-mockup", "index": n, "out": self.run_dir / "visual-mockup" / f"part-{n:02d}.png",
               "prompt": "x" * 19500, "references": []}
        return provider.generate(job, {"model": "gpt-image-2-5-sunburst-text-to-image"}), job["out"]

    def adapter_calls(self):
        return int(self.state.read_text()) if self.state.exists() else 0

    def test_image_cap_2_refuses_the_third_paid_render(self):
        self.render(1)
        self.render(2)
        with self.assertRaises(exe.ExecutorError) as ctx:
            self.render(3)
        self.assertIn("image ceiling reached", str(ctx.exception))
        self.assertEqual(self.adapter_calls(), 2, "the refused render must not reach the provider")
        ledger = json.loads((self.run_dir / exe.LEDGER).read_text(encoding="utf-8"))["calls"]
        self.assertEqual([c["status"] for c in ledger], ["done", "done"])

    def test_paid_run_without_an_approved_cap_is_refused(self):
        self.set_cap(None)
        os.environ["KIE_API_KEY"] = "dummy"
        self.addCleanup(os.environ.pop, "KIE_API_KEY", None)
        args = Namespace(provider="kie", allow_paid=True, kie_adapter=str(self.adapter))
        with self.assertRaises(exe.ExecutorError) as ctx:
            exe.make_provider(args, self.run_dir)
        self.assertIn("image_cap", str(ctx.exception))
        with self.assertRaises(exe.ExecutorError):
            self.render(1)
        self.assertEqual(self.adapter_calls(), 0)

    def test_a_provider_failure_does_not_use_up_the_ceiling(self):
        os.environ["FAKE_FAIL"] = "1"
        self.addCleanup(os.environ.pop, "FAKE_FAIL", None)
        with self.assertRaises(exe.ExecutorError):
            self.render(1)
        ledger = json.loads((self.run_dir / exe.LEDGER).read_text(encoding="utf-8"))["calls"]
        self.assertEqual(ledger, [])

    def test_clean_run_writes_a_bound_receipt_the_gate_accepts(self):
        result, out = self.render(1)
        receipt = json.loads(Path(result["receipt"]).read_text(encoding="utf-8"))
        rel = str(out.relative_to(self.run_dir))
        b = receipt["binding"]
        self.assertEqual(Path(result["receipt"]).name, "task-001.json")
        self.assertEqual((b["task_id"], b["sha256"], b["file"]), ("task-001", sha(out), rel))
        self.assertTrue(all(isinstance(b[k], (int, float)) for k in ("credits_before", "credits_after")))
        self.assertLessEqual(b["credits_after"], b["credits_before"])
        self.assertEqual(stage_gate._kie74_problems(self.run_dir, "image-generation-qc",
                                                    [{"task_id": "task-001", "file": rel}]), [])
        mod = exe._kie74_receipt()
        self.assertEqual(mod.store_problems(self.run_dir, [rel]), [])
        self.assertTrue(mod.check_file(Path(result["receipt"]))[0])

    def test_forged_task_id_or_swapped_png_or_missing_store_fails(self):
        mod = exe._kie74_receipt()
        self.assertTrue(mod.store_problems(self.run_dir), "no receipt store must fail")
        result, out = self.render(1)
        rel = str(out.relative_to(self.run_dir))
        receipt_path = Path(result["receipt"])
        # a hand-made receipt: invented task id 'abc123' over a PNG whose bytes were never the provider's
        forged = json.loads(receipt_path.read_text(encoding="utf-8"))
        forged["task_id"] = forged["binding"]["task_id"] = "abc123"
        forged["binding"]["sha256"] = "0" * 64
        (receipt_path.parent / "abc123.json").write_text(json.dumps(forged), encoding="utf-8")
        problems = mod.store_problems(self.run_dir, [rel])
        self.assertTrue(any("abc123.json" in p and "does not hash" in p for p in problems), problems)
        (receipt_path.parent / "abc123.json").unlink()
        self.assertEqual(mod.store_problems(self.run_dir, [rel]), [])
        out.write_bytes(out.read_bytes() + b"tampered")  # the PNG changes after the receipt was written
        self.assertTrue(mod.store_problems(self.run_dir, [rel]))

    def test_credits_after_above_before_is_refused(self):
        mod = exe._kie74_receipt()
        (self.run_dir / "a.png").write_bytes(b"x")
        result = {"provider": "kie", "adapter": "74-kie-live-adapter", "adapter_mode": "active",
                  "backend": "native-live", "model_id": "m", "task_id": "t-1", "state": "success",
                  "result_urls": [], "saved_paths": ["a.png"], "fallback_used": False}
        with self.assertRaises(ValueError):
            mod.write_bound_receipt(self.run_dir, result, "a.png", 5, 9)
        with self.assertRaises(ValueError):
            mod.write_bound_receipt(self.run_dir, result, "a.png", "5", "4")


class ProductionRunNeedsReceipts(base.ZeroImageGenerationIsFailure):
    test_generation_run_with_zero_images_fails = None  # the inherited pin is not this file's

    def pipeline(self, with_receipt):
        script = self.td / "pipeline.py"
        script.write_text(textwrap.dedent(f'''
            import importlib.util, json, sys
            from pathlib import Path
            run = Path.cwd()
            png = run / "desktop-wireframe" / "section-01.png"
            png.parent.mkdir(parents=True, exist_ok=True)
            png.write_bytes(b"\\x89PNG\\r\\n\\x1a\\n" + b"one")
            (png.parent / "stage-executor-record.json").write_text(json.dumps(
                {{"images": [{{"file": "desktop-wireframe/section-01.png"}}]}}))
            if {with_receipt!r}:
                spec = importlib.util.spec_from_file_location("k74", {str(RECEIPT_MODULE)!r})
                mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
                mod.write_bound_receipt(run, {{"provider": "kie", "adapter": "74-kie-live-adapter",
                    "adapter_mode": "active", "backend": "native-live", "model_id": "m", "task_id": "t-9",
                    "state": "success", "result_urls": [], "saved_paths": ["x.png"],
                    "fallback_used": False}}, "desktop-wireframe/section-01.png", 10, 6)
        '''), encoding="utf-8")
        return shlex.join([sys.executable, str(script)])

    def test_production_run_refuses_without_the_receipt_store(self):
        self.seal_fixtures()
        proc = self.run_service("--pipeline-command", self.pipeline(False))
        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("receipt store", proc.stdout)
        # the same run is fine when it is declared a test run, and when the receipts exist
        shutil.rmtree(self.run_dir)
        proc = self.run_service("--test-run", "--pipeline-command", self.pipeline(False))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        shutil.rmtree(self.run_dir)
        proc = self.run_service("--pipeline-command", self.pipeline(True))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def stub_pipeline(self, entry_provider="stub", ledger=False):
        """The record the stub executor writes (provider and mode 'stub' on the record and every image)."""
        script = self.td / "stub_pipeline.py"
        script.write_text(textwrap.dedent(f'''
            import json
            from pathlib import Path
            run = Path.cwd()
            png = run / "desktop-wireframe" / "section-01.png"
            png.parent.mkdir(parents=True, exist_ok=True)
            png.write_bytes(b"\\x89PNG\\r\\n\\x1a\\n" + b"one")
            (png.parent / "stage-executor-record.json").write_text(json.dumps(
                {{"provider": "stub", "mode": "stub", "images": [{{"file": "desktop-wireframe/section-01.png",
                  "provider": {entry_provider!r}, "mode": "stub"}}]}}))
            if {ledger!r}:
                (run / "image-spend-ledger.json").write_text(json.dumps({{"calls": []}}))
        '''), encoding="utf-8")
        return shlex.join([sys.executable, str(script)])

    def test_stub_placeholder_run_needs_no_receipts_but_a_provider_claim_does(self):
        self.seal_fixtures()
        proc = self.run_service("--pipeline-command", self.stub_pipeline())
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)  # Skill 49 downsell stub path
        for kwargs in ({"entry_provider": "kie"}, {"ledger": True}):  # a provider claim or a paid spend
            shutil.rmtree(self.run_dir)
            proc = self.run_service("--pipeline-command", self.stub_pipeline(**kwargs))
            self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("receipt store", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
