#!/usr/bin/env python3
"""G-3 (fix plan B2, unowned): the wireframe provider never DEFAULTS to stub, and a stub run
cannot certify without a recorded owner approval.

legacy_downsell_images.py had `--image-provider ... default="stub"`, so the default path
produced placeholder wireframes. Per the fix plan: default to the real provider, and have the
gate refuse a stub run whose owner approval is not recorded.

FAILS before the change: no flag produced the "spends money" refusal with no provider given
(the default was stub), and a receipt recording provider=stub with no approval produced no
AF-FUN-BUILD-VISUAL-STUB violation.

Harmony issue 38: "a recorded approval" is a Command Center record (kind stub_render, bound to the sha256 of
the copy ledger), verified by the shared verifier, not a string. A loopback fake Command Center answers here.
"""
import hashlib
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "49-signature-funnel" / "scripts" / "legacy_downsell_images.py"
BUILD = ROOT / "49-signature-funnel" / "scripts" / "prove_sf_build.py"
FAKE_CC = ROOT / "49-signature-funnel" / "tests" / "fake_command_center.py"


def run(*extra):
    """Run the CLI with dummy required paths. The provider check runs BEFORE any file is read."""
    cmd = [sys.executable, str(TOOL), "--ledger", "/nonexistent/ledger.json",
           "--skill71-root", "/nonexistent/71", "--brand-file", "/nonexistent/brand.json",
           "--brand-owner", "test", "--out-dir", "/nonexistent/out", *extra]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return p.returncode, (p.stdout + p.stderr)


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def main() -> int:
    fails = []

    rc, out = run()
    if rc != 2 or "spends money" not in out:
        fails.append("G-3: with NO provider given the tool did not default to kie "
                     "(rc=%r out=%r)" % (rc, out[-300:]))

    rc, out = run("--image-provider", "stub")
    if rc != 2 or "--stub-approved-by" not in out:
        fails.append("G-3: an unapproved stub run was not refused (rc=%r out=%r)" % (rc, out[-300:]))

    led = Path(tempfile.mkdtemp(prefix="bld002-g3-led-")) / "ledger.json"
    led.write_text("{}", encoding="utf-8")
    rc, out = run("--image-provider", "stub", "--stub-approved-by", "OWNER-APPROVAL-1", "--ledger", str(led))
    if rc != 2 or "not a verified stub_render approval" not in out:
        fails.append("G-3 / issue 38: a free-text stub approval was not refused as unverified (rc=%r out=%r)"
                     % (rc, out[-300:]))

    cc_mod = load("fake_cc_g3", FAKE_CC)
    build = load("sf_build_g3", BUILD)
    with cc_mod.FakeCommandCenter() as cc, tempfile.TemporaryDirectory(prefix="bld002-g3-") as d:
        saved = {k: os.environ.get(k) for k in cc.env()}
        os.environ.update(cc.env())
        try:
            rd = Path(d) / "run"
            rd.mkdir()
            build.write_valid_run_evidence(rd, 5)
            ledger = rd / "copy_ledger.json"
            ledger.write_text(json.dumps({"funnel_size": 5}), encoding="utf-8")
            plan_hash = hashlib.sha256(ledger.read_bytes()).hexdigest()
            rec = rd / build.PAGE_IMAGES_REL / build.PAGE_IMAGES_RECEIPT
            data = json.loads(rec.read_text(encoding="utf-8"))
            data["provider"] = "stub"
            data.pop("stub_approval", None)
            rec.write_text(json.dumps(data), encoding="utf-8")
            v = build.visual_direction_violations(rd, 5)
            if not any(c == "AF-FUN-BUILD-VISUAL-STUB" for c, _m in v):
                fails.append("G-3: an unapproved stub receipt did not fail the build gate: %r" % (v,))

            data["stub_approval"] = "OWNER-APPROVAL-1"
            rec.write_text(json.dumps(data), encoding="utf-8")
            v1 = build.visual_direction_violations(rd, 5)
            if not any(c == "AF-FUN-BUILD-VISUAL-STUB" for c, _m in v1):
                fails.append("G-3 / issue 38: a free-text stub_approval string passed the build gate: %r" % (v1,))

            approval_id = cc.mint("stub_render", plan_hash)
            data["stub_approval"] = {"approval_id": approval_id, "kind": "stub_render",
                                     "plan_hash": plan_hash, "verified": True}
            rec.write_text(json.dumps(data), encoding="utf-8")
            v2 = build.visual_direction_violations(rd, 5)
            if any(c == "AF-FUN-BUILD-VISUAL-STUB" for c, _m in v2):
                fails.append("G-3: a stub receipt WITH a verified Command Center approval was still refused: %r" % (v2,))
        finally:
            for k, v_ in saved.items():
                if v_ is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v_

    for f in fails:
        print("FAIL: " + f)
    if fails:
        return 1
    print("PASS G-3: provider defaults to kie; an unapproved stub run (and a free-text approval) is refused by "
          "the tool and by the build gate; a verified Command Center approval is allowed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
