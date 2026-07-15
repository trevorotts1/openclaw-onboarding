#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prove_command_center_discovery.py — U23: Command Center ZERO-CHANGE
discovery proof (ledger U23 / checklist item 24, spec Section 2.2 "Default
ruling" + Section 21.2 "Conditional Command Center changes").

NOT a CWFE-MANIFEST.json phase gate (this skill's P0-P16 run never calls it).
It is a standalone, repeatable prover — same family as
`funnel_engine_selector.py --self-test` (U22) — that proves the existing
Command Center generic skill matcher (`matchSkillsForTask()` in
`blackceo-command-center/src/lib/context-pack.ts`) discovers and ranks THIS
engine's real, unmodified, shipped SKILL.md with ZERO changes to the Command
Center repository, using only its already-documented env-var overrides
(`CC_SKILL_ROOTS` / `CC_SKILL_DEPARTMENT_MAP`) — exactly the fixture pattern
`tests/unit/departments-use-skills-layer-a.test.ts` already demonstrates on
the Command Center side.

Command Center is an EXTERNAL repository. This script never vendors it, never
assumes it is present, and never writes into it — it only ever READS a
checkout the caller supplies via --cc-repo (or CC_REPO_PATH). The Node/TS
harness it shells out to (scripts/lib/cc_discovery_harness.mjs, shipped
alongside this file) does the actual import-and-call against that checkout.

Two run modes:

  --self-test
      Fully offline. No Node, no network, no external repo required. Proves
      this script's OWN logic: fixture-building from the real files this
      skill ships (hash-verified against the live SKILL.md/department-map on
      disk, so a future edit that silently drifts the proven content is
      caught), evidence-JSON pass/fail rollup against canned mock harness
      output (both a clean-PASS and a deliberately-rigged-FAIL case), and
      fail-closed behavior when --cc-repo is missing/absent/incomplete.

  --cc-repo PATH --run-dir DIR
      Live mode. Builds the fixture skill root + department-map copy under
      --run-dir, shells out to `node --import tsx` against the real harness,
      captures its JSON stdout as evidence, writes
      <run-dir>/cc-discovery-evidence.json (on PASS or FAIL — a failed run
      still leaves a full evidence trail, matching every other prove_*.py in
      this skill), and exits 0/1 accordingly. Requires the target checkout to
      already have its own `npm install` run (this script never mutates the
      external repo, including its node_modules — that is the caller's own
      setup step, done once, outside this proof).

Exit codes: 0 = PASS, 1 = FAIL (genuine discovery mismatch), 3 = usage/setup
error (missing --cc-repo, incomplete checkout, node/tsx unavailable — this is
a "could not run the proof" signal, never conflated with a "the proof ran and
failed" signal).

stdlib only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional, Tuple

_SCRIPT_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _SCRIPT_DIR.parent
_HARNESS_PATH = _SCRIPT_DIR / "lib" / "cc_discovery_harness.mjs"

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_USAGE = 3

# Real neighbor skills copied alongside this skill's own SKILL.md to give the
# zero-config keyword matcher a non-trivial (but still small/fast) candidate
# pool, exactly mirroring the shape of the CC repo's own fixture test.
_NEIGHBOR_SKILLS = ["49-signature-funnel", "25-video-creator"]


class DiscoveryProofError(Exception):
    """Raised for a usage/setup failure (never for a genuine discovery mismatch)."""


def onboarding_repo_root() -> Path:
    """This skill ships inside the onboarding repo at <root>/62-cinematic-web-funnel-engine/.
    Two parents up from this file (scripts/prove_command_center_discovery.py) is that root."""
    root = _SKILL_DIR.parent
    if not (root / "23-ai-workforce-blueprint" / "skill-department-map.json").exists():
        raise DiscoveryProofError(
            f"could not locate the onboarding repo root from {_SCRIPT_DIR} "
            f"(expected {root}/23-ai-workforce-blueprint/skill-department-map.json)"
        )
    return root


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def build_fixture(onboarding_root: Path, dest_dir: Path) -> Tuple[Path, Path]:
    """Copies REAL SKILL.md files (this skill + neighbors) and the REAL
    skill-department-map.json into dest_dir. Never fabricates content — raises
    if any real source file is missing. Returns (fixture_skill_root, dept_map_copy)."""
    fixture_root = dest_dir / "fixture-skill-root"
    fixture_root.mkdir(parents=True, exist_ok=True)

    own_skill_md = _SKILL_DIR / "SKILL.md"
    if not own_skill_md.exists():
        raise DiscoveryProofError(f"this skill's own SKILL.md is missing: {own_skill_md}")
    own_dest = fixture_root / _SKILL_DIR.name / "SKILL.md"
    own_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(own_skill_md, own_dest)

    for neighbor in _NEIGHBOR_SKILLS:
        src = onboarding_root / neighbor / "SKILL.md"
        if not src.exists():
            raise DiscoveryProofError(f"expected neighbor skill fixture missing on disk: {src}")
        dst = fixture_root / neighbor / "SKILL.md"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)

    real_map = onboarding_root / "23-ai-workforce-blueprint" / "skill-department-map.json"
    if not real_map.exists():
        raise DiscoveryProofError(f"real skill-department-map.json missing: {real_map}")
    map_copy = dest_dir / "skill-department-map.json"
    shutil.copyfile(real_map, map_copy)

    return fixture_root, map_copy


def validate_cc_repo(cc_repo: Path) -> None:
    if not cc_repo.exists() or not cc_repo.is_dir():
        raise DiscoveryProofError(f"--cc-repo does not exist or is not a directory: {cc_repo}")
    ctx_pack = cc_repo / "src" / "lib" / "context-pack.ts"
    if not ctx_pack.exists():
        raise DiscoveryProofError(f"--cc-repo does not contain src/lib/context-pack.ts (not a blackceo-command-center checkout?): {cc_repo}")
    pkg = cc_repo / "package.json"
    if not pkg.exists():
        raise DiscoveryProofError(f"--cc-repo has no package.json: {cc_repo}")
    try:
        pkg_name = json.loads(pkg.read_text(encoding="utf-8")).get("name")
    except (json.JSONDecodeError, OSError) as exc:
        raise DiscoveryProofError(f"--cc-repo package.json unreadable/invalid: {exc}") from exc
    if pkg_name != "mission-control":
        raise DiscoveryProofError(f"--cc-repo package.json name is '{pkg_name}', expected 'mission-control' — wrong repo?")
    tsx_bin = cc_repo / "node_modules" / ".bin" / "tsx"
    tsx_pkg = cc_repo / "node_modules" / "tsx"
    if not tsx_bin.exists() and not tsx_pkg.exists():
        raise DiscoveryProofError(
            f"--cc-repo has no node_modules/tsx — run `npm install` in {cc_repo} first "
            f"(this prover never mutates the external checkout, including installing its dependencies)"
        )
    node_path = shutil.which("node")
    if not node_path:
        raise DiscoveryProofError("`node` not found on PATH")


def run_harness(cc_repo: Path, run_dir: Path) -> Tuple[bool, dict, str]:
    """Live mode: build the fixture, shell out to the Node harness, return
    (passed, evidence_dict, human_detail). Raises DiscoveryProofError on any
    setup failure (distinct from a genuine discovery FAIL)."""
    validate_cc_repo(cc_repo)
    if not _HARNESS_PATH.exists():
        raise DiscoveryProofError(f"harness script missing: {_HARNESS_PATH}")

    onboarding_root = onboarding_repo_root()
    fixture_root, dept_map_copy = build_fixture(onboarding_root, run_dir)

    isolated_db = run_dir / f"cc-discovery-isolated-{os.getpid()}.db"
    env = dict(os.environ)
    env["CC_REPO_PATH"] = str(cc_repo)
    env["FIXTURE_SKILL_ROOT"] = str(fixture_root)
    env["FIXTURE_DEPT_MAP"] = str(dept_map_copy)
    env["DATABASE_PATH"] = str(isolated_db)
    for leak_key in ("OPENAI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_AI_STUDIO_API_KEY", "GEMINI_API_KEY", "SOP_EMBEDDING_PROVIDER"):
        env.pop(leak_key, None)

    try:
        proc = subprocess.run(
            ["node", "--import", "tsx", str(_HARNESS_PATH)],
            cwd=str(cc_repo),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        raise DiscoveryProofError(f"harness timed out after 120s: {exc}") from exc
    except OSError as exc:
        raise DiscoveryProofError(f"failed to invoke node: {exc}") from exc

    stdout = (proc.stdout or "").strip()
    if not stdout:
        raise DiscoveryProofError(f"harness produced no stdout (exit {proc.returncode}); stderr: {(proc.stderr or '').strip()[:2000]}")

    try:
        evidence = json.loads(stdout.splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as exc:
        raise DiscoveryProofError(f"harness stdout was not valid JSON: {exc}; raw: {stdout[:2000]}") from exc

    overall = evidence.get("overall")
    if overall == "USAGE_ERROR":
        raise DiscoveryProofError(f"harness usage error: {evidence.get('detail')}")

    passed = overall == "PASS"
    checks = evidence.get("checks", [])
    n_pass = sum(1 for c in checks if c.get("pass"))
    detail = f"{n_pass}/{len(checks)} checks passed; overall={overall}"
    if not passed:
        first_fail = next((c for c in checks if not c.get("pass")), None)
        if first_fail:
            detail += f"; first failing check: {first_fail.get('name')} — {first_fail.get('detail')}"
    return passed, evidence, detail


def evaluate(run_dir: Path, cc_repo: Optional[Path]) -> Tuple[bool, str]:
    """py_symbol-style entry point mirroring this skill's other prove_*.py
    scripts. Always writes cc-discovery-evidence.json into run_dir on any
    outcome the harness itself reached (PASS or FAIL); a usage/setup error
    that never reached the harness writes no evidence file (nothing to
    record) and is reported via the returned detail string instead."""
    run_dir.mkdir(parents=True, exist_ok=True)

    if cc_repo is None:
        return False, (
            "USAGE ERROR: no --cc-repo supplied. This prover requires an operator-provided "
            "blackceo-command-center checkout (never assumed, never auto-cloned, never defaults "
            "to the live ~/command-center/app) — pass --cc-repo <path> to a throwaway clone."
        )

    try:
        passed, evidence, detail = run_harness(cc_repo, run_dir)
    except DiscoveryProofError as exc:
        return False, f"USAGE ERROR: {exc}"

    out_path = run_dir / "cc-discovery-evidence.json"
    out_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    return passed, f"{detail} (evidence: {out_path.name})"


# ---------------------------------------------------------------------------
# --self-test — fully offline, no Node, no network, no external repo required
# ---------------------------------------------------------------------------

def _self_test() -> bool:
    ok = True

    def check(label: str, cond: bool, detail: str = "") -> None:
        nonlocal ok
        status = "PASS" if cond else "FAIL"
        print(f"[{status}] {label}" + (f" — {detail}" if detail else ""))
        if not cond:
            ok = False

    # 1. onboarding_repo_root() resolves correctly from this script's real
    #    shipped location.
    try:
        root = onboarding_repo_root()
        check("onboarding_repo_root() resolves", True, str(root))
    except DiscoveryProofError as exc:
        check("onboarding_repo_root() resolves", False, str(exc))
        return False

    # 2. build_fixture() copies REAL bytes (hash-verified against the live
    #    source files) — never fabricates content, catches silent drift.
    with tempfile.TemporaryDirectory(prefix="cwfe-cc-discovery-selftest-") as tmp:
        tmp_path = Path(tmp)
        try:
            fixture_root, dept_map_copy = build_fixture(root, tmp_path)
            own_src = _SKILL_DIR / "SKILL.md"
            own_copy = fixture_root / _SKILL_DIR.name / "SKILL.md"
            check(
                "fixture copy of own SKILL.md is byte-identical to the shipped file",
                own_copy.exists() and sha256_file(own_copy) == sha256_file(own_src),
                str(own_copy),
            )
            real_map = root / "23-ai-workforce-blueprint" / "skill-department-map.json"
            check(
                "fixture copy of skill-department-map.json is byte-identical to the real map",
                dept_map_copy.exists() and sha256_file(dept_map_copy) == sha256_file(real_map),
                str(dept_map_copy),
            )
            for neighbor in _NEIGHBOR_SKILLS:
                n_src = root / neighbor / "SKILL.md"
                n_copy = fixture_root / neighbor / "SKILL.md"
                check(
                    f"fixture copy of neighbor {neighbor}/SKILL.md is byte-identical",
                    n_copy.exists() and sha256_file(n_copy) == sha256_file(n_src),
                    str(n_copy),
                )
        except DiscoveryProofError as exc:
            check("build_fixture() succeeds against real repo files", False, str(exc))

    # 3. build_fixture() fails closed (raises, fabricates nothing) when a real
    #    source file is missing — simulate by pointing at a bogus onboarding root.
    with tempfile.TemporaryDirectory(prefix="cwfe-cc-discovery-selftest-bogus-") as tmp:
        bogus_root = Path(tmp) / "not-a-real-onboarding-checkout"
        bogus_root.mkdir()
        raised = False
        try:
            build_fixture(bogus_root, Path(tmp) / "dest")
        except DiscoveryProofError:
            raised = True
        check("build_fixture() fails closed against a bogus onboarding root", raised)

    # 4. evaluate() fails closed with no --cc-repo (usage error, never a false PASS).
    with tempfile.TemporaryDirectory(prefix="cwfe-cc-discovery-selftest-noccrepo-") as tmp:
        passed, detail = evaluate(Path(tmp), None)
        check("evaluate() fails closed with no --cc-repo", passed is False and "USAGE ERROR" in detail, detail)

    # 5. validate_cc_repo() fails closed against a directory that is not a CC checkout.
    with tempfile.TemporaryDirectory(prefix="cwfe-cc-discovery-selftest-notcc-") as tmp:
        raised = False
        try:
            validate_cc_repo(Path(tmp))
        except DiscoveryProofError:
            raised = True
        check("validate_cc_repo() fails closed against a non-CC directory", raised)

    # 6. validate_cc_repo() fails closed against a real-shaped-but-dependency-
    #    less checkout (context-pack.ts + correct package.json name present,
    #    but no node_modules/tsx) — proves the "never auto-npm-install" rule
    #    surfaces a clear, distinct error rather than silently degrading.
    with tempfile.TemporaryDirectory(prefix="cwfe-cc-discovery-selftest-nodeps-") as tmp:
        fake_cc = Path(tmp) / "fake-cc"
        (fake_cc / "src" / "lib").mkdir(parents=True)
        (fake_cc / "src" / "lib" / "context-pack.ts").write_text("export {};\n", encoding="utf-8")
        (fake_cc / "package.json").write_text(json.dumps({"name": "mission-control"}), encoding="utf-8")
        raised = False
        detail = ""
        try:
            validate_cc_repo(fake_cc)
        except DiscoveryProofError as exc:
            raised = True
            detail = str(exc)
        check("validate_cc_repo() fails closed when node_modules/tsx is absent", raised and "npm install" in detail, detail)

    # 7. run_harness() evidence-JSON pass/fail rollup logic, exercised against
    #    CANNED mock harness stdout (both a clean PASS and a rigged FAIL) —
    #    proves the parsing/rollup path itself without invoking Node at all.
    def _fake_run(monkey_stdout: str, monkey_returncode: int):
        class _P:
            pass

        p = _P()
        p.stdout = monkey_stdout
        p.stderr = ""
        p.returncode = monkey_returncode
        return p

    orig_run = subprocess.run
    try:
        good_json = json.dumps({"overall": "PASS", "checks": [{"name": "a", "pass": True, "detail": ""}]})
        subprocess.run = lambda *a, **k: _fake_run(good_json, 0)  # type: ignore[assignment]
        with tempfile.TemporaryDirectory(prefix="cwfe-cc-discovery-selftest-mockpass-") as tmp:
            fake_cc = Path(tmp) / "fake-cc"
            (fake_cc / "src" / "lib").mkdir(parents=True)
            (fake_cc / "src" / "lib" / "context-pack.ts").write_text("export {};\n", encoding="utf-8")
            (fake_cc / "package.json").write_text(json.dumps({"name": "mission-control"}), encoding="utf-8")
            (fake_cc / "node_modules").mkdir()
            (fake_cc / "node_modules" / "tsx").mkdir()
            run_dir = Path(tmp) / "run"
            passed, detail = evaluate(run_dir, fake_cc)
            check("evaluate() PASS rollup on canned good harness output", passed is True, detail)
            check("evaluate() PASS writes evidence file", (run_dir / "cc-discovery-evidence.json").exists())

        bad_json = json.dumps({"overall": "FAIL", "checks": [{"name": "a", "pass": True, "detail": ""}, {"name": "b", "pass": False, "detail": "rigged mismatch"}]})
        subprocess.run = lambda *a, **k: _fake_run(bad_json, 1)  # type: ignore[assignment]
        with tempfile.TemporaryDirectory(prefix="cwfe-cc-discovery-selftest-mockfail-") as tmp:
            fake_cc = Path(tmp) / "fake-cc"
            (fake_cc / "src" / "lib").mkdir(parents=True)
            (fake_cc / "src" / "lib" / "context-pack.ts").write_text("export {};\n", encoding="utf-8")
            (fake_cc / "package.json").write_text(json.dumps({"name": "mission-control"}), encoding="utf-8")
            (fake_cc / "node_modules").mkdir()
            (fake_cc / "node_modules" / "tsx").mkdir()
            run_dir = Path(tmp) / "run"
            passed, detail = evaluate(run_dir, fake_cc)
            check("evaluate() FAIL rollup on canned rigged-bad harness output", passed is False and "b" in detail, detail)
            check("evaluate() FAIL still writes evidence file (never a bare non-zero with no record)", (run_dir / "cc-discovery-evidence.json").exists())
    finally:
        subprocess.run = orig_run  # type: ignore[assignment]

    print("RESULT:", "PASS" if ok else "FAIL")
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(
        description="U23 — prove Command Center's generic matchSkillsForTask() discovers this "
        "skill's real, unmodified SKILL.md with ZERO Command Center changes."
    )
    parser.add_argument("--cc-repo", help="path to a blackceo-command-center checkout (throwaway clone; never the live app)")
    parser.add_argument("--run-dir", help="directory to write cc-discovery-evidence.json into")
    parser.add_argument("--self-test", action="store_true", help="run fully offline self-checks (no Node/network/external repo needed)")
    args = parser.parse_args()

    if args.self_test:
        sys.exit(EXIT_PASS if _self_test() else EXIT_FAIL)

    if not args.cc_repo or not args.run_dir:
        print("USAGE ERROR: live mode requires both --cc-repo and --run-dir (or use --self-test)", file=sys.stderr)
        sys.exit(EXIT_USAGE)

    run_dir = Path(args.run_dir)
    cc_repo = Path(args.cc_repo)
    passed, detail = evaluate(run_dir, cc_repo)
    if detail.startswith("USAGE ERROR"):
        print(detail, file=sys.stderr)
        sys.exit(EXIT_USAGE)
    if passed:
        print(f"[PASS] Command Center discovery — {detail}")
        sys.exit(EXIT_PASS)
    print(f"[FAIL] Command Center discovery — {detail}", file=sys.stderr)
    sys.exit(EXIT_FAIL)


if __name__ == "__main__":
    main()
