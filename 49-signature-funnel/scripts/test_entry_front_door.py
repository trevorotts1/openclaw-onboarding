#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A6 — the documentED front door WORKS end to end.

SCOPE-LEDGER PRMPT-001 #5 and #7. The documented entry point used to abort on the very run
dir it was handed: the shell minted a run nonce and passed `--nonce`, and the orchestrator
refuses a caller-supplied nonce (AF-FUN-FRONT-DOOR); it also wrote an env-reported model
receipt the execution-tier gate refuses. This test runs the shell exactly as the SOP
documents it, on a run dir built by the orchestrator's own valid-run fixture, and requires
exit 0 plus a signed PROCESS-CERTIFICATE.

The fixture mints the Skill 49 pin inside a TEMPORARY copy of the tree, exactly as CI's mint
job does, so this test exercises the DOOR (deps/version/hash-pin/bypass/model-tier/
orchestrator) rather than the committed pin's state. It never touches the repository's pin
file, and it does not weaken the hash-pin gate: the gate still compares the recomputed
digest to the copy's pin.

Run: python3 -m pytest 49-signature-funnel/scripts/test_entry_front_door.py -q
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
ROOT = SKILL.parent
for _p in (str(HERE), str(SKILL)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import front_door  # noqa: E402
import run_signature_funnel as runner  # noqa: E402

KEY = "a" * 64
ENTRY = "signature-funnel-entry.sh"


def _fixture_tree(tmp: Path) -> Path:
    """A skills root the door can resolve: a real copy of Skill 49 (so the fixture mint writes
    only the copy's pin) and links to the other pinned trees."""
    skills = tmp / "skills"
    skills.mkdir()
    shutil.copytree(SKILL, skills / "49-signature-funnel",
                    ignore=shutil.ignore_patterns("__pycache__", "working", "*.pyc"))
    # Every other tree the door, the pin and the orchestrator's phases resolve beside Skill 49
    # (83/71 for the pin, 22 for the persona registry, shared-utils for the policy). Linked, not
    # copied: the fixture must judge the same content the repository ships.
    for name in sorted(ROOT.iterdir()):
        if name.is_dir() and name.name not in ("49-signature-funnel", ".git"):
            (skills / name.name).symlink_to(name, target_is_directory=True)
    front_door.mint_pin_ci(skills / "49-signature-funnel", env={
        "GITHUB_ACTIONS": "true", "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REPOSITORY": "trevorotts1/openclaw-onboarding", "GITHUB_RUN_ID": "0"})
    return skills / "49-signature-funnel"


def test_bare_invocation_is_self_describing_and_exits_zero():
    r = subprocess.run(["bash", str(SKILL / ENTRY)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Usage:" in r.stdout


def test_the_documented_entry_script_certifies_a_valid_run_end_to_end():
    with tempfile.TemporaryDirectory(prefix="sf-entry-e2e-") as td:
        tmp = Path(td)
        skill = _fixture_tree(tmp)
        key_file = tmp / "operator.key"
        key_file.write_text(KEY, encoding="utf-8")
        key_file.chmod(0o600)          # the operator-key loader refuses group/other access
        env = {k: v for k, v in os.environ.items() if not k.startswith("SF_")}
        env.update({"HOME": str(tmp), "OPENCLAW_PLATFORM": "mac",
                    "SF_OPERATOR_KEY_FILE": str(key_file),
                    "GHL_VERIFY_NONCE_DIR": str(tmp / "ghl-nonces")})
        rd = tmp / "run"
        rd.mkdir()
        # The fixture writes the Skill 6 run-nonce files the P7 gate re-reads, so the SAME
        # directory must be visible while it builds the run and while the door runs it.
        prior = {k: os.environ.get(k) for k in ("SF_OPERATOR_KEY_FILE", "GHL_VERIFY_NONCE_DIR")}
        os.environ["SF_OPERATOR_KEY_FILE"] = str(key_file)
        os.environ["GHL_VERIFY_NONCE_DIR"] = str(tmp / "ghl-nonces")
        try:
            runner._write_valid_run(rd, KEY)
        finally:
            for k, v in prior.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        proc = subprocess.run(["bash", str(skill / ENTRY), "--run-dir", str(rd)],
                              capture_output=True, text=True, env=env, timeout=300)
        cert = rd / "PROCESS-CERTIFICATE.json"
        assert proc.returncode == 0, proc.stdout[-4000:] + proc.stderr[-4000:]
        assert cert.is_file(), "the door exited 0 without emitting a PROCESS-CERTIFICATE"
