"""F10: live proof that sandbox_wrapper really confines an untrusted producer.

Offline (no provider/network/spend). macOS Seatbelt only; skipped elsewhere.
Each denial is paired with an unsandboxed control that is ALLOWED, so the
test cannot pass because the probe itself is broken.
"""
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CORE = Path(__file__).resolve().parent
sys.path.insert(0, str(CORE))
import production_process as process
import sandbox_wrapper as sw

HAVE_SB = sys.platform == "darwin" and Path(sw.SANDBOX_EXEC).exists()

WRITE = "import sys; open(sys.argv[1], 'w').write('x')"
NET = ("import socket,sys; s=socket.socket(); s.settimeout(2); "
       "s.connect(('127.0.0.1', int(sys.argv[1])))")


class SandboxWrapperTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="f10-sandbox-")
        self.addCleanup(self.tmp.cleanup)
        # realpath: Seatbelt subpath matches the resolved path (/var -> /private/var)
        self.store = (Path(self.tmp.name).resolve() / "store")
        self.store.mkdir()

    def test_template_matches_product_descriptor_and_shipped_profile(self):
        self.assertEqual(sw.PROFILE_TEMPLATE, process._F10_SANDBOX_PROFILE_TEMPLATE)
        sb = (CORE / "sandbox_f10.sb").read_text()
        for rule in ("(allow default)", "(deny file-write*", "(deny network*)"):
            self.assertIn(rule, sb)
            self.assertIn(rule, sw.PROFILE_TEMPLATE)
        self.assertEqual(process._sandbox_wiring()["template_sha256"],
                         hashlib.sha256(sw.PROFILE_TEMPLATE.encode()).hexdigest())

    def test_build_argv_fails_closed_without_sandbox_exec(self):
        orig = sw.SANDBOX_EXEC
        sw.SANDBOX_EXEC = str(self.store / "missing-sandbox-exec")
        self.addCleanup(setattr, sw, "SANDBOX_EXEC", orig)
        with self.assertRaises(FileNotFoundError):
            sw.build_argv(self.store, ["true"])
        with self.assertRaises(ValueError):
            sw.wiring_attestation()

    @unittest.skipUnless(HAVE_SB, "needs macOS sandbox-exec")
    def test_store_write_denied_under_sandbox_allowed_without(self):
        target = self.store / "forged-receipt.json"
        ctl = subprocess.run([sys.executable, "-c", WRITE, str(target)], capture_output=True, text=True)
        self.assertEqual(ctl.returncode, 0, ctl.stderr)  # control: allowed
        target.unlink()
        out = sw.spawn_untrusted(self.store, [sys.executable, "-c", WRITE, str(target)])
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("Operation not permitted", out.stderr)
        self.assertFalse(target.exists())

    @unittest.skipUnless(HAVE_SB, "needs macOS sandbox-exec")
    def test_alternate_interpreter_cannot_write_store(self):
        target = self.store / "sh-forged"
        out = sw.spawn_untrusted(self.store, ["/bin/sh", "-c", f"echo x > '{target}'"])
        self.assertNotEqual(out.returncode, 0)
        self.assertFalse(target.exists())

    @unittest.skipUnless(HAVE_SB, "needs macOS sandbox-exec")
    def test_writes_outside_store_still_work(self):
        other = Path(self.tmp.name).resolve() / "scratch.txt"
        out = sw.spawn_untrusted(self.store, [sys.executable, "-c", WRITE, str(other)])
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertTrue(other.exists())

    @unittest.skipUnless(HAVE_SB, "needs macOS sandbox-exec")
    def test_network_denied_under_sandbox_allowed_without(self):
        import socket
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        self.addCleanup(srv.close)
        port = str(srv.getsockname()[1])
        ctl = subprocess.run([sys.executable, "-c", NET, port], capture_output=True, text=True)
        self.assertEqual(ctl.returncode, 0, ctl.stderr)  # control: connect allowed
        out = sw.spawn_untrusted(self.store, [sys.executable, "-c", NET, port])
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("Operation not permitted", out.stderr)

    @unittest.skipUnless(HAVE_SB, "needs macOS sandbox-exec")
    def test_nested_looser_profile_cannot_escape(self):
        loose = self.store.parent / "loose.sb"
        loose.write_text("(version 1)\n(allow default)\n")
        target = self.store / "escaped"
        out = sw.spawn_untrusted(
            self.store, [sw.SANDBOX_EXEC, "-f", str(loose), sys.executable, "-c", WRITE, str(target)])
        self.assertNotEqual(out.returncode, 0)
        self.assertFalse(target.exists())

    @unittest.skipUnless(HAVE_SB, "needs macOS sandbox-exec")
    def test_attestation_matches_admission_descriptor(self):
        att = sw.wiring_attestation()
        wiring = process._sandbox_wiring()
        for key in ("enforced", "launcher", "deny", "template_sha256"):
            self.assertEqual(att[key], wiring[key])


if __name__ == "__main__":
    unittest.main()
