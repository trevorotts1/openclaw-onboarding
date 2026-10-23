#!/usr/bin/env python3
"""sc20_nine_syllable_consistency.py — acceptance row SC-20 (S75-W10-U1).

Condition (SCENARIO-MATRIX.json, row SC-20, verbatim):
    "Nine-syllable consistency"

Required result (verbatim):
    "NEGATIVE: syllable count stays consistent at nine across takes; a drift
     is detected and refused, not silently shipped"

The measurement is the REAL ``lyric_writer/lyric_structure.line_syllables`` of
the tree under test and the refusal is the REAL
``lyric_writer.sung_meter_finding`` (THE single sung-meter rule, D09) plus the
structure lint ``lyric_structure.lint_singability``. Takes are fixtures: the
same hook line measured on three takes, then a drifted rewrite. No network,
no provider, no channel, no graph mutation.

Modes:
  (no flag)   run the scenario and print one assertion line per check
  --dry-run   identical checks, receipt marked mode=dry-run
  selftest    re-run under deliberate defects and REQUIRE the named
              assertions to turn RED (proves the harness can fail)

Exit 0 = every assertion held; 1 = at least one failed; 2 = tooling.
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _harness as H  # noqa: E402

ROW = "sc20"
TITLE = "nine-syllable hook consistent across takes"

TAKE_COUNT = 3
NINE = 9

#: every line measures nine syllables with the tree's own counter
BASE_LINES = (
    "I will carry every single mile",
    "We are stronger than the storm tonight",
    "Sing it loud and never let it fade",
    "We can make it through the darkest night",
)
HOOK_LINE = BASE_LINES[3]
DRIFT_LINE = "We can make it through the darkest night and rise again"
LONG_DRIFT_LINE = ("Rise up from the ashes one more time and never look "
                   "back down")


def load_core(core):
    pkg = str(core / "lyric_writer")
    sys.path.insert(0, pkg)
    try:
        ls = importlib.import_module("lyric_structure")
        lw = importlib.import_module("lyric_writer")
    finally:
        try:
            sys.path.remove(pkg)
        except ValueError:
            pass
    return ls, lw


def stanza(lines):
    return "[Sung - verse]\n" + "\n".join(lines)


def scenario(core, muts=frozenset()):
    ls, lw = load_core(core)
    c = H.Checks(ROW, TITLE)
    print("SC20 %s — tree %s%s"
          % (TITLE, core, (" [defect: %s]" % ",".join(sorted(muts)))
             if muts else ""))

    # ---- the baseline take: every line at nine ------------------------
    counts = [ls.line_syllables(ln) for ln in BASE_LINES]
    c.check("sc20:baseline-take-is-nine-syllables",
            counts == [NINE] * len(BASE_LINES),
            "line syllable counts=%s (want %d on every line)"
            % (counts, NINE))

    # ---- the same hook sung on three takes ---------------------------
    takes = []
    for i in range(TAKE_COUNT):
        takes.append({"take": i + 1, "line": HOOK_LINE,
                      "syllables": ls.line_syllables(HOOK_LINE)})
    takn = [t["syllables"] for t in takes]
    c.check("sc20:nine-syllables-consistent-across-takes",
            len(set(takn)) == 1 and takn[0] == NINE,
            "per-take hook syllable counts=%s over %d takes"
            % (takn, TAKE_COUNT))

    # ---- what the real rule says about nine --------------------------
    policy = lw.constraint_policy()
    nine_finding = lw.sung_meter_finding(NINE, policy)
    preferred = policy["sung_meter"]["preferred"]
    performable = policy["sung_meter"]["performable"]
    c.check("sc20:nine-syllable-line-inside-performable-band",
            (nine_finding is None
             or nine_finding["quality"] != lw.Q_REQUIRED)
            and not lw.blocking([nine_finding] if nine_finding else []),
            "9 syllables -> finding=%r quality=%r blocking=%s "
            "(preferred %s, performable %s)"
            % (nine_finding["error"] if nine_finding else None,
               nine_finding["quality"] if nine_finding else None,
               bool(lw.blocking([nine_finding] if nine_finding else [])),
               preferred, performable))

    # ---- the drifted take -------------------------------------------
    drift_line = HOOK_LINE if "silent_rewrite" in muts else DRIFT_LINE
    drift_syllables = ls.line_syllables(drift_line)
    c.check("sc20:drift-detected-by-measurement",
            drift_syllables != NINE,
            "baseline=%d drifted take=%d syllables, drift=%+d (%r)"
            % (NINE, drift_syllables, drift_syllables - NINE, drift_line))

    drift_finding = lw.sung_meter_finding(drift_syllables, policy)
    refused = bool(lw.blocking([drift_finding] if drift_finding else []))
    verdict = "REFUSED" if refused else "PASS"
    if "force_pass_verdict" in muts:
        verdict = "PASS"          # defect: the take is shipped anyway
    lint13 = ls.lint_singability([{"tag": "[Sung - verse]",
                                   "lines": [drift_line]}], 60)
    c.check("sc20:drifted-take-refused-not-shipped",
            refused and verdict == "REFUSED",
            "drifted take verdict=%s, meter finding=%r quality=%r "
            "blocking=%s; structure lint at %d syllables: %s"
            % (verdict,
               drift_finding["error"] if drift_finding else None,
               drift_finding["quality"] if drift_finding else None,
               refused, drift_syllables,
               "FAIL" if lint13["verdict"] == "FAIL" else "PASS"))

    # ---- a longer drift is caught by the structure lint as well ------
    long_counts = ls.line_syllables(LONG_DRIFT_LINE)
    long_lint = ls.lint_singability(
        [{"tag": "[Sung - verse]",
          "lines": [BASE_LINES[0], BASE_LINES[1], BASE_LINES[2],
                    LONG_DRIFT_LINE]}], 60)
    line_len_fail = any("sung-line-length" in r for r in long_lint["reasons"])
    c.check("sc20:long-drift-refused-by-structure-lint",
            long_lint["verdict"] == "FAIL" and line_len_fail,
            "%d-syllable line -> lint verdict=%s, sung-line-length reason=%s"
            % (long_counts, long_lint["verdict"], line_len_fail))
    return c


MUTATIONS = {
    "silent_rewrite": [
        "sc20:drift-detected-by-measurement",
        "sc20:drifted-take-refused-not-shipped",
    ],
    "force_pass_verdict": [
        "sc20:drifted-take-refused-not-shipped",
    ],
}


def selftest(core):
    ok = True
    for name in sorted(MUTATIONS):
        c = scenario(core, frozenset([name]))
        failed = [r["name"] for r in c.failed()]
        expected = MUTATIONS[name]
        hit = [e for e in expected if e in failed]
        good = len(hit) == len(expected) and len(failed) >= 1
        ok = ok and good
        print("selftest:%s — %s; red=%s"
              % (name, "RED as required" if good
                 else "DID NOT FAIL AS EXPECTED", failed or "none"))
        print("selftest:%s — expected hit=%d/%d"
              % (name, len(hit), len(expected)))
    print("selftest — %s"
          % ("harness fails on every defect" if ok
             else "HARNESS CANNOT PROVE A FAILURE"))
    return 0 if ok else 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "selftest":
        args = H.add_args(description="sc20 selftest").parse_args(argv[1:])
        return selftest(H.resolve_core(args))

    ap = H.add_args(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    core = H.resolve_core(args)
    result = scenario(core)
    if args.out:
        path = Path(args.out) / "receipts"
        code = result.finish(path)
        receipt = path / "sc20.scenario.json"
        if receipt.is_file():
            doc = json.loads(receipt.read_text("utf-8"))
            doc["mode"] = "dry-run" if args.dry_run else "run"
            receipt.write_text(json.dumps(doc, indent=2) + "\n", "utf-8")
        return code
    return result.finish()


if __name__ == "__main__":
    sys.exit(main())
