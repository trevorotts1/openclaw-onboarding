#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_certified_funnel_e2e.py — the end-to-end proof that a PASSING run,
driven through the REAL canonical front door and orchestrator, produces ONE
genuine HMAC-SHA256-signed PROCESS-CERTIFICATE and that the orchestrator
finale PRESERVES it (never overwrites it with a placeholder).

This is the offline counterpart of the held live U26 canary (spec 19.2:
"mocked fixtures only, no live paid provider calls"; the real live-spend/live-
deploy canary stays held). It exercises the whole certificate path for real —
the real cinematic-web-funnel-entry.sh front door mints a run-scoped 0600
nonce, the real run_cinematic_web_funnel.py walks the P0..P16 spine no-skip,
the real scripts/prove_certificate.py (P16-CERTIFY gate) aggregates the spine
and signs the certificate, and the real _finalize_certificate() re-verifies
and preserves it — with the 16 upstream phase GATES swapped for deterministic
all-pass fixture scripts so the run can go fully green offline without live
Vercel/GHL/Kie or generated media (the phases whose real gates fundamentally
require a live service or generated media).

It is the regression guard for the "broken certificate emission" fix: an
earlier orchestrator signed its own weak nonce-keyed sha256 "seed" hash after
the phase loop and CLOBBERED the prover's real HMAC-signed certificate. This
test fails loudly if that placeholder ever returns (it asserts the emitted
certificate is the prover's real HMAC-SHA256 object and carries no
placeholder seed field), and it independently re-verifies the signature
through the prover's own standalone --verify path.

Mutates a COPIED skill dir only (never the real tree), exactly like
test_breakit_adversarial.py's manifest cases.

Run with:
  python3 -m unittest discover -s 62-cinematic-web-funnel-engine/tests/e2e -v
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _e2e_support as sup  # noqa: E402

_FIXTURE_GATE_SRC = (
    "#!/usr/bin/env python3\n"
    "# Deterministic all-pass fixture phase gate (offline certified-funnel e2e).\n"
    "import sys\n"
    "print('fixture phase gate PASS')\n"
    "sys.exit(0)\n"
)


def _install_all_pass_fixture_manifest(skill_dir: Path) -> None:
    """Rewrites the copied CWFE-MANIFEST.json so every upstream phase (order
    0..15) points at a deterministic all-pass fixture gate script, leaving
    P16-CERTIFY pointed at the REAL scripts/prove_certificate.py. Phase ids,
    orders, names, af_codes and produces_artifact strings are left untouched,
    so the orchestrator's own manifest validation (17 contiguous phases,
    unique AF codes, P0..P16 ids) and the prover's certificate construction
    still operate on the real phase spine."""
    manifest_path = skill_dir / "CWFE-MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    scripts_dir = skill_dir / "scripts"
    for phase in manifest["phases"]:
        if phase["order"] == 16:
            continue  # keep the REAL prove_certificate.py as the P16 gate
        rel = f"scripts/_fixture_gate_{phase['order']:02d}.py"
        phase["gate"] = rel
        (skill_dir / rel).write_text(_FIXTURE_GATE_SRC, encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


class CertifiedFunnelE2ETests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="cwfe-e2e-certified-funnel-")
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = Path(self._tmp.name)
        self.skill_dir = sup.copy_skill_dir_to_temp(self.tmp_path)
        _install_all_pass_fixture_manifest(self.skill_dir)
        self.run_dir = self.tmp_path / "run"
        self.run_dir.mkdir()

    def _drive_front_door(self) -> sup.RunResult:
        entry = self.skill_dir / "cinematic-web-funnel-entry.sh"
        return sup.run(["bash", str(entry), "--run-dir", str(self.run_dir)], timeout=120)

    def test_passing_run_emits_one_real_hmac_signed_certificate_and_finale_preserves_it(self) -> None:
        result = self._drive_front_door()

        # 1) The real front door + orchestrator certify the passing run.
        self.assertEqual(result.returncode, 0, msg=result.combined)
        self.assertIn("RESULT: CERTIFIED", result.combined)
        self.assertIn("HMAC-SHA256", result.combined)

        cert_path = self.run_dir / "PROCESS-CERTIFICATE.json"
        self.assertTrue(cert_path.exists(), msg="no PROCESS-CERTIFICATE.json was emitted")
        cert = json.loads(cert_path.read_text(encoding="utf-8"))

        # 2) It is the PROVER's real certificate, not the old placeholder.
        self.assertEqual(cert.get("certificate"), "cinematic-web-funnel-process-certificate")
        self.assertEqual(cert.get("signature_algorithm"), "HMAC-SHA256")
        self.assertIn("nonce_fingerprint", cert)
        self.assertIn("signature", cert)
        self.assertRegex(cert["signature"], r"^[0-9a-f]{64}$")
        self.assertIs(cert.get("all_phases_pass"), True)
        # The clobbering placeholder's tell-tale field must never appear.
        self.assertNotIn(
            "signature_sha256_hmac_seed",
            cert,
            msg="the orchestrator's old placeholder certificate overwrote the prover's real one",
        )

        # 3) All 17 phases present, contiguous 0..16, every one PASS.
        orders = sorted(p["order"] for p in cert["phases"])
        self.assertEqual(orders, list(range(17)))
        self.assertEqual([p["id"] for p in sorted(cert["phases"], key=lambda p: p["order"])][0], "P0-ENVIRONMENT")
        self.assertEqual([p["id"] for p in sorted(cert["phases"], key=lambda p: p["order"])][-1], "P16-CERTIFY")
        self.assertTrue(all(p["status"] == "PASS" for p in cert["phases"]))

        # 4) Independently re-verify the signature through the prover's own
        #    standalone --verify path, reading the run's real nonce — the same
        #    re-verification the orchestrator finale performed.
        verify = sup.run(
            [
                sup.PY,
                str(self.skill_dir / "scripts" / "prove_certificate.py"),
                "--verify",
                str(cert_path),
                "--run-dir",
                str(self.run_dir),
            ],
            timeout=60,
        )
        self.assertEqual(verify.returncode, 0, msg=verify.combined)
        self.assertIn("PROCESS-CERTIFICATE valid", verify.combined)

    def test_tampering_with_the_signed_certificate_is_caught_on_reverification(self) -> None:
        """A certified run, then a post-hoc tamper of a phase status — the
        prover's --verify (the same re-verification the finale runs) must
        reject it, proving the signature actually binds the phase ledger."""
        result = self._drive_front_door()
        self.assertEqual(result.returncode, 0, msg=result.combined)
        cert_path = self.run_dir / "PROCESS-CERTIFICATE.json"
        cert = json.loads(cert_path.read_text(encoding="utf-8"))
        cert["phases"][5]["status"] = "FAIL"  # tamper without re-signing
        tampered_path = self.tmp_path / "tampered-cert.json"
        tampered_path.write_text(json.dumps(cert), encoding="utf-8")

        verify = sup.run(
            [
                sup.PY,
                str(self.skill_dir / "scripts" / "prove_certificate.py"),
                "--verify",
                str(tampered_path),
                "--run-dir",
                str(self.run_dir),
            ],
            timeout=60,
        )
        self.assertEqual(verify.returncode, 2, msg=verify.combined)
        self.assertIn("invalid", verify.combined.lower())


if __name__ == "__main__":
    # Standalone run prints the certificate summary as human-readable evidence.
    import unittest as _ut

    suite = _ut.defaultTestLoader.loadTestsFromTestCase(CertifiedFunnelE2ETests)
    _ut.TextTestRunner(verbosity=2).run(suite)
