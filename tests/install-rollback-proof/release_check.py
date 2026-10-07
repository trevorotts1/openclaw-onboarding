#!/usr/bin/env python3
"""release_check.py — release verifier for a box holding BOTH distributions.

W4-04-U1. Named by `core/release_scaffolds/DEPENDENCY-MANIFEST.md` as the
release verifier ("manifest comparison, clean helper install proof, supported
versions, migration/rollback, test receipts"). The distribution-root
`release_check.py` that the manifest also names is still NOT built — see
`docs/operating-and-recovery/OPERATING.md` NOT-IMPLEMENTED. This is the
verifier the clean-install / migration / rollback proof runs against a
scratch copy of both distributions; nothing here writes to a source tree.

Box layout expected under --box:

  openclaw-onboarding/75-drama-song-ad-factory/     distribution A
  999-setup/.claude/skills/drama-song-ad-factory/   distribution B
  999-setup/CONTROL/bundled-skills.txt              999 install manifest
  999-setup/THIRD_PARTY_NOTICES.md                  notices shipped with B

Exit: 0 = no FAIL row, 1 = at least one FAIL, 2 = resolve/tooling failure.
UNDETERMINED rows are never counted as passes.

  python3 release_check.py --box <dir> [--require-receipts] [--receipt out.json]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _lib  # noqa: E402

SCHEMA = "blackceo.release-check/v1"
DEPT_SLUG = _lib.DEPT_SLUG
OPENCLAW_DIR = _lib.OPENCLAW_DIR
ENVELOPE = "blackceo.intake-preflight/envelope/v1"
# Harness-declared floor. DEPENDENCY-MANIFEST defers the real pin to W5-02
# ("Pin + hash + Python/tool versions release verification on both clean
# installs"), so this is declared here, not inherited.
PYTHON_FLOOR = (3, 10)
SEMVER = re.compile(r"^v?\d+\.\d+\.\d+$")

A_REQUIRED = [
    "SKILL.md", "skill-version.txt", "DEPENDENCY-MANIFEST.md",
    "THIRD_PARTY_NOTICES.md",
    "scripts/core/intake_preflight/factory.py",
    "scripts/core/contracts/campaign-schema.json",
    "scripts/core/contracts/artifact-schema.json",
    "scripts/core/contracts/qc-schema.json",
    "scripts/core/acceptance-profile.json",
]
B_REQUIRED = [
    "SKILL.md", "VERSION", "CHANGELOG.md", "INSTRUCTIONS.md",
    "references/cli-contract.md", "references/parity-contract.md",
    "assets/example-brief.json",
    "adapters/claude-nine/README.md", "adapters/claude-code/README.md",
    "tests/test_cli_smoke.py", "tests/test_parity_layout.py",
    "scripts/core/intake_preflight/factory.py",
    "scripts/core/contracts/campaign-schema.json",
    "scripts/core/contracts/artifact-schema.json",
    "scripts/core/contracts/qc-schema.json",
    "scripts/core/acceptance-profile.json",
]


class Report:
    def __init__(self):
        self.families = {}

    def row(self, family, name, status, detail=""):
        assert status in ("pass", "fail", "undetermined")
        row = {"check": name, "status": status}
        if detail:
            row["detail"] = detail
        self.families.setdefault(family, []).append(row)

    def status(self, family):
        rows = self.families.get(family, [])
        if any(r["status"] == "fail" for r in rows):
            return "fail"
        if not rows or any(r["status"] == "undetermined" for r in rows):
            return "undetermined"
        return "pass"

    def counts(self):
        n = {"pass": 0, "fail": 0, "undetermined": 0}
        for rows in self.families.values():
            for r in rows:
                n[r["status"]] += 1
        return n


def _run(cmd, env=None, timeout=180):
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                          env=env)
    return proc.returncode, proc.stdout, proc.stderr


def _parse_envelope(text):
    """The CLI prints one JSON envelope; accept pretty-printed or bare."""
    text = (text or "").strip()
    if not text:
        return None
    candidates = [text, text.splitlines()[-1]]
    if "{" in text and "}" in text:
        candidates.append(text[text.find("{"):text.rfind("}") + 1])
    for candidate in candidates:
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(data, dict) and "outcome" in data:
            return data
    return None


def _factory_run(factory, args, timeout=120):
    rc, out, err = _run([sys.executable, str(factory)] + list(args),
                        timeout=timeout)
    return rc, _parse_envelope(out), err.strip()


def family_resolve(rep, p):
    """Layout gate: the box must hold both install roots. Content gaps
    (a missing SKILL.md, an unregistered skill) are manifest FAILs, not
    resolve failures, so a stale install reports what is wrong."""
    fam = "resolve"
    ok = True
    for key, label in (("a", "openclaw install root"),
                       ("b", "claude install root")):
        if p[key].is_dir():
            rep.row(fam, "%s present" % label, "pass", str(p[key]))
        else:
            rep.row(fam, "%s present" % label, "fail", str(p[key]))
            ok = False
    if p["registry"].is_file():
        rep.row(fam, "999 install manifest present", "pass", str(p["registry"]))
    else:
        rep.row(fam, "999 install manifest present", "fail", str(p["registry"]))
        ok = False
    if p["notices_b"].is_file():
        rep.row(fam, "999 third-party notices present", "pass",
                str(p["notices_b"]))
    else:
        rep.row(fam, "999 third-party notices present", "fail",
                str(p["notices_b"]))
        ok = False
    return ok


def family_manifest(rep, p):
    fam = "manifest-comparison"
    for rel in A_REQUIRED:
        rep.row(fam, "A ships %s" % rel,
                "pass" if (p["a"] / rel).is_file() else "fail")
    for rel in B_REQUIRED:
        rep.row(fam, "B ships %s" % rel,
                "pass" if (p["b"] / rel).is_file() else "fail")

    # 999 registry: source presence alone is not proof of installation
    # (directive 2.4) — the skill must be listed.
    if p["registry"].is_file():
        names = [ln.strip() for ln in
                 p["registry"].read_text().splitlines()
                 if ln.strip() and not ln.strip().startswith("#")]
        if DEPT_SLUG in names:
            rep.row(fam, "999 registry lists %s" % DEPT_SLUG, "pass")
        else:
            rep.row(fam, "999 registry lists %s" % DEPT_SLUG, "fail",
                    "entries: %s" % ", ".join(names))
    else:
        rep.row(fam, "999 registry lists %s" % DEPT_SLUG, "fail",
                "bundled-skills.txt missing")

    # Byte parity of the packaged core across both distributions.
    if p["core_a"].is_dir() and p["core_b"].is_dir():
        da, fa = _lib.tree_digest(p["core_a"])
        db, fb = _lib.tree_digest(p["core_b"])
        if fa and fa == fb and da == db:
            rep.row(fam, "core tree byte-identical across distributions",
                    "pass", "%d files, sha256=%s" % (len(fa), da))
        else:
            rep.row(fam, "core tree byte-identical across distributions",
                    "fail", "A=%s(%d) B=%s(%d)" % (da, len(fa), db, len(fb)))
    else:
        rep.row(fam, "core tree byte-identical across distributions", "fail",
                "scripts/core missing on one side")

    # Version stamps.
    av = (p["a"] / "skill-version.txt")
    bv = (p["b"] / "VERSION")
    if av.is_file():
        val = av.read_text().strip()
        rep.row(fam, "A version stamp parses",
                "pass" if SEMVER.match(val) else "fail", val)
    else:
        rep.row(fam, "A version stamp parses", "fail", "skill-version.txt missing")
    if bv.is_file():
        val = bv.read_text().strip()
        rep.row(fam, "B version stamp parses",
                "pass" if SEMVER.match(val) else "fail", val)
    else:
        rep.row(fam, "B version stamp parses", "fail", "VERSION missing")


def family_install(rep, p, env_extra=None):
    """Clean helper install proof: run the INSTALLED copy, never the source."""
    fam = "clean-helper-install"
    results = {}

    py = shutil.which("python3")
    if py:
        rep.row(fam, "python3 resolves on PATH", "pass", py)
    else:
        rep.row(fam, "python3 resolves on PATH", "fail")
        return results

    for side, core in (("A", p["core_a"]), ("B", p["core_b"])):
        code = ("import importlib;"
                "mods='state_store spend_ledger artifact_graph qc_gate "
                "timing_guard job_recovery cc_sync'.split();"
                "[importlib.import_module(m) for m in mods];"
                "print('imported:%d' % len(mods))")
        env = dict(os.environ)
        env["PYTHONPATH"] = str(core)
        if env_extra:
            env.update(env_extra)
        rc, out, err = _run([py, "-c", code], env=env)
        if rc == 0 and "imported:7" in out:
            rep.row(fam, "%s core modules import from installed copy" % side,
                    "pass", str(core))
        else:
            rep.row(fam, "%s core modules import from installed copy" % side,
                    "fail", (err or out).strip()[:300])

    brief = _lib.FIXTURES / "complete-brief.json"
    for side, factory in (("A", p["factory_a"]), ("B", p["factory_b"])):
        if not factory.is_file():
            rep.row(fam, "%s intake runs from installed copy" % side, "fail",
                    "missing %s" % factory)
            continue
        rc, env, err = _factory_run(factory, [
            "intake", "--brief-file", str(brief), "--run-id", "w404-release"])
        ok = (rc == 0 and isinstance(env, dict)
              and env.get("outcome") == "ok"
              and env.get("schema_version") == ENVELOPE
              and env.get("reason_code") == "complete-brief-zero-questions")
        results["intake_%s" % side] = env
        rep.row(fam, "%s intake runs from installed copy" % side,
                "pass" if ok else "fail",
                "rc=%s outcome=%s schema=%s" % (
                    rc,
                    env.get("outcome") if isinstance(env, dict) else None,
                    env.get("schema_version") if isinstance(env, dict) else None))

    # preflight must reject without approval — names-only, never generates.
    if p["factory_b"].is_file():
        rc, env, err = _factory_run(p["factory_b"], [
            "preflight", "--root", str(p["box"])])
        ok = (rc == 4 and isinstance(env, dict)
              and env.get("outcome") == "rejected"
              and env.get("reason_code") == "approval-missing")
        results["preflight_B"] = env
        rep.row(fam, "B preflight rejects without approval",
                "pass" if ok else "fail",
                "rc=%s reason=%s" % (rc,
                                     env.get("reason_code") if isinstance(env, dict) else None))

    ff = shutil.which("ffmpeg")
    if ff:
        rep.row(fam, "ffmpeg resolves (DEPENDENCY-MANIFEST: verify both clean installs)",
                "pass", ff)
    else:
        rep.row(fam, "ffmpeg resolves (DEPENDENCY-MANIFEST: verify both clean installs)",
                "fail", "not on PATH")

    code = "import faster_whisper"  # noqa: F841
    rc, _out, err = _run([py, "-c", code])
    if rc == 0:
        rep.row(fam, "faster-whisper helper present", "pass")
    else:
        rep.row(fam, "faster-whisper helper present", "undetermined",
                "proven absent (rc=%s %s); pin deferred to W5-02 per "
                "DEPENDENCY-MANIFEST" % (rc, err.strip().splitlines()[-1]
                                         if err.strip() else "no stderr"))
    return results


def family_versions(rep, install_results):
    fam = "supported-versions"
    ver = sys.version_info[:2]
    if ver >= PYTHON_FLOOR:
        rep.row(fam, "python >= declared floor", "pass",
                "%d.%d (floor %d.%d declared by this verifier; pin W5-02)"
                % (ver[0], ver[1], PYTHON_FLOOR[0], PYTHON_FLOOR[1]))
    else:
        rep.row(fam, "python >= declared floor", "fail",
                "%d.%d < %d.%d" % (ver[0], ver[1], *PYTHON_FLOOR))
    for side in ("A", "B"):
        env = install_results.get("intake_%s" % side)
        if not isinstance(env, dict):
            rep.row(fam, "%s envelope schema pinned" % side, "fail",
                    "no envelope captured")
            continue
        if env.get("schema_version") == ENVELOPE:
            rep.row(fam, "%s envelope schema pinned" % side, "pass", ENVELOPE)
        else:
            rep.row(fam, "%s envelope schema pinned" % side, "fail",
                    str(env.get("schema_version")))
        if env.get("tool_version"):
            rep.row(fam, "%s envelope carries tool_version" % side, "pass",
                    str(env.get("tool_version")))
        else:
            rep.row(fam, "%s envelope carries tool_version" % side, "fail",
                    "missing")


def family_test_receipts(rep, p, env_extra=None):
    fam = "test-receipts"
    # A (OpenClaw) ships no test files: verified, never counted as a pass.
    shipped_a = sorted(x for x in (p["a"] / "tests").glob("*.py")
                       ) if (p["a"] / "tests").is_dir() else []
    if shipped_a:
        for t in shipped_a:
            rc, out, err = _run([sys.executable, str(t)])
            rep.row(fam, "A test %s" % t.name,
                    "pass" if rc == 0 else "fail",
                    (out.strip().splitlines() or [""])[-1][:200])
    else:
        rep.row(fam, "A test receipts", "undetermined",
                "distribution A ships no test files (verified: %s is empty or "
                "absent) — not counted as a pass" % (p["a"] / "tests"))

    tests_b = sorted((p["b"] / "tests").glob("test_*.py")) \
        if (p["b"] / "tests").is_dir() else []
    if not tests_b:
        rep.row(fam, "B test receipts", "fail", "no test_*.py shipped")
        return
    for t in tests_b:
        env = dict(os.environ)
        # The packaged parity test resolves its canonical core relative to the
        # install; point it at distribution A inside this box.
        env["DSAF_CANONICAL_CORE"] = str(p["core_a"])
        if env_extra:
            env.update(env_extra)
        out = subprocess.run([sys.executable, str(t)], capture_output=True,
                             text=True, timeout=300, env=env)
        tail = (out.stdout.strip().splitlines() or [""])[-1][:200]
        rep.row(fam, "B test %s" % t.name,
                "pass" if out.returncode == 0 else "fail",
                "rc=%s %s" % (out.returncode, tail))


def family_receipts(rep, require, receipts_dir=None):
    fam = "migration-rollback-receipts"
    receipts_dir = Path(receipts_dir) if receipts_dir else _lib.RECEIPTS
    for name in ("migration.json", "rollback.json"):
        path = receipts_dir / name
        label = "receipt %s" % name
        if not path.is_file():
            status = "fail" if require else "undetermined"
            rep.row(fam, label, status,
                    "absent%s" % (" (required)" if require else
                                  " — run test_migration.py / test_rollback.py"))
            continue
        try:
            data = json.loads(path.read_text())
        except ValueError as exc:
            rep.row(fam, label, "fail", "unparseable: %s" % exc)
            continue
        problems = []
        if data.get("schema") != _lib.SCHEMA:
            problems.append("schema=%r" % data.get("schema"))
        if data.get("unit_id") != _lib.UNIT_ID:
            problems.append("unit_id=%r" % data.get("unit_id"))
        if data.get("verdict") != "PASS":
            problems.append("verdict=%r" % data.get("verdict"))
        for side in ("openclaw", "nine"):
            if side not in (data.get("covered") or []):
                problems.append("missing side %r" % side)
        if problems:
            rep.row(fam, label, "fail", "; ".join(problems))
        else:
            rep.row(fam, label, "pass",
                    "verdict=PASS covered=%s"
                    % ",".join(data.get("covered") or []))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--box", required=True, help="box root holding both installs")
    ap.add_argument("--require-receipts", action="store_true",
                    help="absent migration/rollback receipts are a FAIL")
    ap.add_argument("--receipt", help="write the JSON receipt here")
    ap.add_argument("--receipts-dir",
                    help="directory holding migration.json / rollback.json "
                         "(default: this folder's receipts/)")
    ap.add_argument("--json", action="store_true",
                    help="print the receipt JSON to stdout instead of a table")
    ap.add_argument("--quiet", action="store_true", help="no stdout table")
    args = ap.parse_args(argv)

    box = Path(args.box).expanduser()
    if not box.is_dir():
        print("resolve-failure: box not found: %s" % box, file=sys.stderr)
        return 2
    p = _lib.box_paths(box)
    rep = Report()

    if not family_resolve(rep, p):
        if not args.quiet:
            print("resolve-failure: box incomplete, nothing was checked",
                  file=sys.stderr)
        return 2

    family_manifest(rep, p)
    install_results = family_install(rep, p)
    family_versions(rep, install_results)
    family_test_receipts(rep, p)
    family_receipts(rep, args.require_receipts, args.receipts_dir)

    counts = rep.counts()
    receipt = {
        "schema": SCHEMA,
        "unit_id": _lib.UNIT_ID,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "box": str(box),
        "python": "%d.%d.%d" % sys.version_info[:3],
        "require_receipts": bool(args.require_receipts),
        "families": {k: {"status": rep.status(k), "checks": v}
                     for k, v in rep.families.items()},
        "counts": counts,
        "verdict": "PASS" if counts["fail"] == 0 else "FAIL",
    }
    if args.receipt:
        path = Path(args.receipt)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    if not args.quiet and not args.json:
        for fam in sorted(rep.families):
            print("%-10s %s" % (rep.status(fam).upper(), fam))
            for row in rep.families[fam]:
                mark = {"pass": "  ok", "fail": "FAIL",
                        "undetermined": " UND"}[row["status"]]
                print("   %s  %s%s" % (mark, row["check"],
                                       (" -- " + row["detail"]) if row.get("detail") else ""))
        print("counts: pass=%d fail=%d undetermined=%d (undetermined is never "
              "a pass)" % (counts["pass"], counts["fail"],
                           counts["undetermined"]))
        print("release_check: %s" % receipt["verdict"])
        if args.receipt:
            print("receipt: %s" % args.receipt)
    return 0 if counts["fail"] == 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:  # tooling failure, never a silent pass
        print("tooling-failure: %s" % exc, file=sys.stderr)
        raise SystemExit(2)
