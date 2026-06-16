#!/usr/bin/env python3
"""
test_preflight.py — proves the build_deck.py PROCESS PREFLIGHT gate.

Three cases, all driven through the real CLI (subprocess), no network needed:

  1. MISSING artifacts  -> exit 3, stderr lists each missing artifact + producer.
  2. PRESENT artifacts  -> preflight PASSES (does NOT exit 3); the run gets PAST
                           the gate (it then stops at the KIE_API_KEY / render
                           stage, which is fine — we only assert the gate passed).
  3. --adhoc-no-process -> preflight SKIPPED, loud non-deliverable banner printed,
                           run gets past the gate.

Run:  python3 test_preflight.py
Exit: 0 = all assertions passed; 1 = a case failed.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUILD = HERE / "build_deck.py"

# Import the module so unit tests can call its check functions directly.
sys.path.insert(0, str(HERE))
import build_deck  # noqa: E402

SLIDES = [
    {"slide": 1, "scene": "A sunlit modern office, editorial photography.",
     "copy": ["Northwind Co", "Three moves that doubled our pipeline"]},
]


def make_workdir(with_artifacts: bool) -> Path:
    root = Path(tempfile.mkdtemp(prefix="deck_preflight_test_"))
    (root / "slides.json").write_text(json.dumps(SLIDES))
    if with_artifacts:
        (root / "working" / "copy").mkdir(parents=True, exist_ok=True)
        (root / "working" / "research").mkdir(parents=True, exist_ok=True)
        (root / "working" / "qc").mkdir(parents=True, exist_ok=True)
        (root / "working" / "copy" / "intake.json").write_text(json.dumps(
            {"interview_confirmed": True, "presentation_mode": "general"}))
        (root / "working" / "research" / "brief-demo.md").write_text(
            "# Research brief\nresearch_complete: true\nCategories A,C,D,F,G,H,I,K,L\n")
        (root / "working" / "qc" / "copy_qc_report.json").write_text(json.dumps(
            {"gate": "Phase 1Q", "average": 9.1, "triggered_autofails": [], "pass": True}))
        # Phase 3 — converting arc allocation (Signature Presentation Architect).
        (root / "working" / "copy" / "arc_allocation.json").write_text(json.dumps(
            [{"slide": 1, "arc_section": "hook"}]))
        # Phase 4 — slide copy authored per doctrine.
        (root / "working" / "copy" / "slides_copy.md").write_text(
            "# Slide copy\n" + ("Authored converting copy per doctrine. " * 40) + "\n")
        # Phase F — typography/design brief (per-slide art direction).
        (root / "working" / "research" / "design-brief-demo.md").write_text(
            "# Design brief\n" + ("Per-slide art direction and typography. " * 20) + "\n")
        # Mode A: no mission_prd.json => source_slide_count 0 => coverage always passes.
    else:
        # create only the working/ shell so the run dir is found but artifacts absent
        (root / "working").mkdir(parents=True, exist_ok=True)
    return root


def run(root: Path, extra=None):
    cmd = [sys.executable, str(BUILD),
           str(root / "slides.json"), str(root / "out.pptx")]
    if extra:
        cmd += extra
    # Strip KIE key so a passed preflight cleanly halts at the config stage
    # instead of hitting the network.
    env = dict(os.environ)
    env.pop("KIE_API_KEY", None)
    return subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=60)


def _coverage_run_dir(source_slide_count, output_slides) -> Path:
    """Build a temp run dir with a mission_prd.json carrying source_slide_count
    (omitted when None) and a slides.json of `output_slides` slides."""
    root = Path(tempfile.mkdtemp(prefix="deck_coverage_test_"))
    (root / "working" / "copy").mkdir(parents=True, exist_ok=True)
    if source_slide_count is not None:
        (root / "working" / "copy" / "mission_prd.json").write_text(
            json.dumps({"source_slide_count": source_slide_count}))
    slides = [{"slide": i, "scene": "x", "copy": ["y"]}
              for i in range(1, output_slides + 1)]
    (root / "working" / "copy" / "slides.json").write_text(json.dumps(slides))
    return root


def test_chk_coverage():
    """ANTI-COMPRESSION (AF-COVERAGE-1) unit test:
      - source_slide_count=120 with 90 output slides FAILS,
      - source_slide_count=120 with 120 output slides PASSES,
      - source=0 (and source absent => Mode A) PASSES regardless of output count.
    Returns a list of failure strings ([] = all passed)."""
    fails = []

    # 120 source vs 90 output => must FAIL (non-empty AF reason).
    rd = _coverage_run_dir(120, 90)
    reason = build_deck._chk_coverage(rd)
    if not reason:
        fails.append("COVERAGE: 120 source / 90 output should FAIL but passed")
    elif "AF-COVERAGE-1" not in reason or "90" not in reason or "120" not in reason:
        fails.append(f"COVERAGE: fail message malformed: {reason!r}")

    # 120 source vs 120 output => must PASS ("").
    rd = _coverage_run_dir(120, 120)
    reason = build_deck._chk_coverage(rd)
    if reason:
        fails.append(f"COVERAGE: 120 source / 120 output should PASS but got: {reason!r}")

    # 120 source vs 150 output (ADD-only, more) => must PASS.
    rd = _coverage_run_dir(120, 150)
    reason = build_deck._chk_coverage(rd)
    if reason:
        fails.append(f"COVERAGE: 120 source / 150 output should PASS but got: {reason!r}")

    # source=0 (Mode A explicit) with fewer output slides => must PASS.
    rd = _coverage_run_dir(0, 5)
    reason = build_deck._chk_coverage(rd)
    if reason:
        fails.append(f"COVERAGE: source=0 should PASS regardless but got: {reason!r}")

    # source absent (Mode A) => must PASS.
    rd = _coverage_run_dir(None, 3)
    reason = build_deck._chk_coverage(rd)
    if reason:
        fails.append(f"COVERAGE: source absent (Mode A) should PASS but got: {reason!r}")

    print(f"COVERAGE (anti-compression) -> {'PASS' if not fails else 'FAIL'}")
    return fails


def main():
    failures = []

    # Unit test — _chk_coverage anti-compression gate (no subprocess/network).
    failures += test_chk_coverage()

    # CASE 1 — missing artifacts => refused, exit 3, lists what's missing.
    root = make_workdir(with_artifacts=False)
    r = run(root)
    out = r.stdout + r.stderr
    if r.returncode != 3:
        failures.append(f"CASE1 expected exit 3, got {r.returncode}")
    for needle in ("PROCESS PREFLIGHT FAILED",
                   "working/copy/intake.json",
                   "working/research/brief-*.md",
                   "working/qc/copy_qc_report.json",
                   "produced by:"):
        if needle not in out:
            failures.append(f"CASE1 stderr missing {needle!r}")
    print(f"CASE1 (missing)  -> exit {r.returncode} (expected 3)  "
          f"{'PASS' if r.returncode == 3 else 'FAIL'}")

    # CASE 2 — artifacts present => preflight passes (must NOT exit 3).
    # We only need to prove the GATE passed; we stop the process the moment it
    # gets past the gate and into render setup so the test never spends a real
    # KIE render (the box may have a KIE_API_KEY on disk).
    root = make_workdir(with_artifacts=True)
    passed_gate = False
    refused = False
    cmd = [sys.executable, str(BUILD), str(root / "slides.json"), str(root / "out.pptx")]
    env = dict(os.environ)
    env.pop("KIE_API_KEY", None)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, env=env)
    try:
        for line in proc.stdout:
            if "PREFLIGHT PASSED" in line:
                passed_gate = True
            if "PROCESS PREFLIGHT FAILED" in line:
                refused = True
            # As soon as we see render setup begin, the gate is proven passed; stop.
            if passed_gate and ("=== build_deck" in line or "[slide-" in line):
                proc.terminate()
                break
    finally:
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    if refused:
        failures.append("CASE2 preflight wrongly refused")
    if not passed_gate:
        failures.append("CASE2 expected 'PREFLIGHT PASSED' banner")
    print(f"CASE2 (present)  -> passed_gate={passed_gate} refused={refused}  "
          f"{'PASS' if passed_gate and not refused else 'FAIL'}")

    # CASE 3 — --adhoc-no-process => skips gate, loud banner, gets past gate.
    # Same streaming approach: prove the banner printed and the run got past the
    # gate without spending a real render.
    root = make_workdir(with_artifacts=False)
    banner = False
    refused = False
    got_past = False
    cmd = [sys.executable, str(BUILD), str(root / "slides.json"),
           str(root / "out.pptx"), "--adhoc-no-process"]
    env = dict(os.environ)
    env.pop("KIE_API_KEY", None)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, env=env)
    try:
        for line in proc.stdout:
            if "ADHOC MODE" in line:
                banner = True
            if "NOT a process-compliant deliverable" in line:
                banner = banner and True
            if "PROCESS PREFLIGHT FAILED" in line:
                refused = True
            if "=== build_deck" in line or "[slide-" in line:
                got_past = True
                proc.terminate()
                break
    finally:
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    if refused:
        failures.append("CASE3 adhoc override still refused")
    if not banner:
        failures.append("CASE3 missing loud adhoc banner")
    if not got_past:
        failures.append("CASE3 did not get past the (skipped) gate")
    print(f"CASE3 (adhoc)    -> banner={banner} got_past={got_past} refused={refused}  "
          f"{'PASS' if banner and got_past and not refused else 'FAIL'}")

    print()
    if failures:
        print("TEST FAILED:")
        for f in failures:
            print("  -", f)
        sys.exit(1)
    print("ALL PREFLIGHT TESTS PASSED")
    sys.exit(0)


if __name__ == "__main__":
    main()
