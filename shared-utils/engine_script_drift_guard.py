#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""engine_script_drift_guard.py -- E10 drift guard for the four scripts that ship,
independently, under the same basename in BOTH 58-podcast-production-engine/scripts
and 59-anthology-engine/scripts (alert-dedup.py, guard-cron-inventory.py,
guard-no-anthropic-runtime.py, delivery_report.py).

See docs/E10-SHARED-SCRIPT-DRIFT-CLASSIFICATION.md for the full classification.
Short version: these are NOT byte-drifted copies of one shared origin -- they are
independently-designed implementations of an analogous role, verified pair by pair.
Blind "extract a common core" unification is forbidden by the classification (it
would either wrap nothing real, or risk a rewrite of safety-critical guard code for
marginal benefit). Instead this script freezes today's classification as a
sha256 + structural fingerprint BASELINE and fails (exit 2) if any of the eight
files drifts from that baseline WITHOUT a conscious `--update-baseline` re-run --
turning silent, unreviewed rot into a reviewed, deliberate act.

Exit 0 = every tracked file matches the baseline (no unreviewed drift).
Exit 2 = at least one file has drifted from its recorded baseline.
Exit 3 = usage / IO error (a tracked file is missing, or the baseline is unreadable).
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = Path(__file__).resolve().parent / "engine-script-drift-baseline.json"

TRACKED_BASENAMES = (
    "alert-dedup.py",
    "guard-cron-inventory.py",
    "guard-no-anthropic-runtime.py",
    "delivery_report.py",
)
TRACKED_ENGINES = {
    "58-podcast": REPO_ROOT / "58-podcast-production-engine" / "scripts",
    "59-anthology": REPO_ROOT / "59-anthology-engine" / "scripts",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _top_level_names(path: Path) -> list:
    """Sorted list of top-level `def`/`class` names -- a cheap structural
    fingerprint that is far more sensitive to a real interface change than the
    sha256 alone is useful for (the sha256 tells you SOMETHING changed; this
    tells you roughly WHAT KIND of change, e.g. a renamed/added/removed symbol)."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return ["<unparseable>"]
    names = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
    return sorted(names)


def _tracked_files():
    for engine, scripts_dir in TRACKED_ENGINES.items():
        for basename in TRACKED_BASENAMES:
            yield engine, basename, scripts_dir / basename


def build_fingerprint():
    fp = {}
    for engine, basename, path in _tracked_files():
        key = "%s/%s" % (engine, basename)
        if not path.is_file():
            fp[key] = {"present": False}
            continue
        fp[key] = {
            "present": True,
            "sha256": _sha256(path),
            "line_count": len(path.read_text(encoding="utf-8", errors="replace").splitlines()),
            "top_level_names": _top_level_names(path),
        }
    return fp


def load_baseline():
    if not BASELINE_PATH.is_file():
        return None
    try:
        return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def write_baseline(fp):
    payload = {
        "$schema_note": (
            "E10 drift baseline. See docs/E10-SHARED-SCRIPT-DRIFT-CLASSIFICATION.md. "
            "Regenerate ONLY via engine_script_drift_guard.py --update-baseline, after "
            "reviewing the diff that caused the drift -- never blind-accept a fingerprint "
            "change without reading what changed and why."
        ),
        "classification_doc": "docs/E10-SHARED-SCRIPT-DRIFT-CLASSIFICATION.md",
        "files": fp,
    }
    BASELINE_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def diff_against_baseline(current, baseline):
    drift = []
    baseline_files = (baseline or {}).get("files", {})
    for key, cur in current.items():
        base = baseline_files.get(key)
        if base is None:
            drift.append("%s: not in baseline (new tracked file -- run --update-baseline)" % key)
            continue
        if cur.get("present") != base.get("present"):
            drift.append("%s: presence changed (baseline present=%s, now present=%s)"
                         % (key, base.get("present"), cur.get("present")))
            continue
        if not cur.get("present"):
            continue
        if cur["sha256"] != base.get("sha256"):
            drift.append("%s: sha256 drift (%d -> %d lines)"
                         % (key, base.get("line_count", -1), cur["line_count"]))
        added = sorted(set(cur["top_level_names"]) - set(base.get("top_level_names", [])))
        removed = sorted(set(base.get("top_level_names", [])) - set(cur["top_level_names"]))
        if added:
            drift.append("%s: new top-level def/class: %s" % (key, ", ".join(added)))
        if removed:
            drift.append("%s: removed top-level def/class: %s" % (key, ", ".join(removed)))
    for key in baseline_files:
        if key not in current:
            drift.append("%s: no longer tracked (was in baseline)" % key)
    return drift


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--update-baseline", action="store_true",
                    help="write the CURRENT fingerprint as the new baseline "
                         "(a deliberate, reviewed acceptance of drift)")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    ap.add_argument("--self-test", action="store_true", help="run the offline self-test")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()

    for engine, basename, path in _tracked_files():
        if not path.is_file():
            msg = "USAGE/IO ERROR: tracked file missing: %s/%s (%s)" % (engine, basename, path)
            print(msg)
            return 3

    fp = build_fingerprint()

    if args.update_baseline:
        write_baseline(fp)
        print("Baseline updated: %s (%d files fingerprinted)" % (BASELINE_PATH, len(fp)))
        return 0

    baseline = load_baseline()
    if baseline is None:
        print("USAGE/IO ERROR: no baseline at %s -- run --update-baseline first" % BASELINE_PATH)
        return 3

    drift = diff_against_baseline(fp, baseline)
    if args.json:
        print(json.dumps({"ok": not drift, "drift": drift}, indent=2, sort_keys=True))
    elif drift:
        print("AF-E10-SCRIPT-DRIFT: %d unreviewed drift(s) from the recorded baseline." % len(drift))
        for d in drift:
            print("  DRIFT %s" % d)
        print("If this drift is intentional and reviewed (see "
              "docs/E10-SHARED-SCRIPT-DRIFT-CLASSIFICATION.md), re-run with "
              "--update-baseline to accept it.")
    else:
        print("PASS: all %d tracked files match the recorded E10 drift baseline." % len(fp))
    return 2 if drift else 0


# ---------------------------------------------------------------------------
# Self-test: offline, uses throwaway files under a temp dir, never touches the
# real baseline or the real tracked engine files.
# ---------------------------------------------------------------------------
def self_test() -> int:
    import tempfile

    passed, failed = [], []

    def check(name, cond):
        (passed if cond else failed).append(name)

    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        f1 = tdp / "a.py"
        f1.write_text("def foo():\n    return 1\n", encoding="utf-8")

        fp1 = {"engineX/a.py": {
            "present": True, "sha256": _sha256(f1),
            "line_count": 2, "top_level_names": _top_level_names(f1),
        }}
        baseline1 = {"files": fp1}
        check("identical fingerprint -> zero drift",
              diff_against_baseline(fp1, baseline1) == [])

        # sha256 drift (content changed, symbol set unchanged)
        f1.write_text("def foo():\n    return 2\n", encoding="utf-8")
        fp2 = {"engineX/a.py": {
            "present": True, "sha256": _sha256(f1),
            "line_count": 2, "top_level_names": _top_level_names(f1),
        }}
        d2 = diff_against_baseline(fp2, baseline1)
        check("content-only change flagged as sha256 drift",
              any("sha256 drift" in x for x in d2))

        # symbol added
        f1.write_text("def foo():\n    return 1\n\ndef bar():\n    return 2\n", encoding="utf-8")
        fp3 = {"engineX/a.py": {
            "present": True, "sha256": _sha256(f1),
            "line_count": 4, "top_level_names": _top_level_names(f1),
        }}
        d3 = diff_against_baseline(fp3, baseline1)
        check("new top-level def flagged", any("new top-level def/class: bar" in x for x in d3))

        # symbol removed (fp1 lacks 'bar'; baseline_with_bar has it)
        baseline_with_bar = {"files": fp3}
        d4 = diff_against_baseline(fp1, baseline_with_bar)
        check("removed top-level def flagged", any("removed top-level def/class: bar" in x for x in d4))

        # file disappears
        d5 = diff_against_baseline({}, baseline1)
        check("missing-from-current flagged as no-longer-tracked",
              any("no longer tracked" in x for x in d5))

        # new untracked-in-baseline file
        d6 = diff_against_baseline(fp1, {"files": {}})
        check("new-vs-baseline flagged as not in baseline",
              any("not in baseline" in x for x in d6))

        # write_baseline + load_baseline round-trip (against a REAL temp baseline path,
        # never the module-level BASELINE_PATH constant).
        global BASELINE_PATH
        real_path = BASELINE_PATH
        try:
            BASELINE_PATH = tdp / "baseline.json"
            write_baseline(fp1)
            loaded = load_baseline()
            check("write/load baseline round-trips", loaded is not None
                  and loaded.get("files") == fp1)
        finally:
            BASELINE_PATH = real_path

    # The real repo's tracked files + baseline (read-only proof: build_fingerprint()
    # over the real files does not crash, and every tracked file is present).
    try:
        real_fp = build_fingerprint()
        check("real repo: all 8 tracked files present",
              all(v.get("present") for v in real_fp.values()) and len(real_fp) == 8)
    except Exception as exc:  # pragma: no cover - defensive
        check("real repo fingerprint buildable (%s)" % exc, False)

    total = len(passed) + len(failed)
    print("engine_script_drift_guard self-test: %d/%d passed" % (len(passed), total))
    for f in failed:
        print("  FAIL: %s" % f)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
