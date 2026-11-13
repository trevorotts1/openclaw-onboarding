#!/usr/bin/env python3
"""
test-qc-nudge-cadence-hotpatch.py — lock for WF-026 / BU-26: the completion
gate no longer decides the nudge-cadence check by text search.

WHY THIS EXISTS: check_nudges_wired() used to answer "is the nudge cadence
wired?" by reading files around the box — an existence test on
interview-nudge-cron.sh, a substring search of ensure-pipeline-crons.sh's
text, and a text search of the nudge worker's cadence constants. Two things
were wrong with that:

  1. It is box plumbing for an EARLIER lifecycle stage (nudging an owner who
     has not yet finished). It says nothing about whether THIS interview is
     complete, and it has nothing to do with this gate's real checks.
  2. It decided its answer by substring search of another script's text — the
     same defect class this gate has been fixed for repeatedly: a check that
     reports a fact it never actually established (text can match while the
     mechanism is broken, and vice versa).

THE RULE (BU-26): check_nudges_wired() reports
    wired: None
    note: "not checked at completion time"
    issues: []
and adds NOTHING to warnings. The verdict's nudgesWired field carries None.

THIS SUITE PROVES:
  U1  The check returns wired=None with that exact note and no issues on a
      fixture box that the OLD check would have failed on (a broken/stale
      registrar present, the nudge worker absent).
  U2  The SAME answer on a path that does not exist at all — the check reads
      no files, so its answer cannot depend on what is on disk.
  U3  SEVERITY / WARNINGS: build_verdict() on an otherwise-clean interview
      reports nudgesWired=None, carries the note, and puts nothing about
      nudges in warnings or hardFailures; the verdict stays PASS exit 0.
  U4  CONTROL: a genuine hard-failure check (a jargon hit) still HARD fails
      (exit 3) with the same nudge result, so the fix did not weaken any
      other check.
  U5  NO WARNING PATH LEFT: even a caller that hands build_verdict() a
      wired=False result with issues produces no nudge warning — the old
      "[nudge-cadence] ..." path is gone, not merely unreachable.

NEVER touches a client box. Fixtures live under a tempdir and are deleted on
exit. No secrets, tokens, or client transcript/answer text of any kind are
used or printed anywhere in this file.

EXIT: 0 = every assertion passed; 1 otherwise.
Usage: python3 test-qc-nudge-cadence-hotpatch.py [REPO_ROOT]
"""

import importlib.util
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "23-ai-workforce-blueprint" / "scripts"
QC_SCRIPT = SCRIPTS / "qc-interview-completion.py"

NOTE = "not checked at completion time"

PASS = 0
FAIL = 0


def ok(msg):
    global PASS
    PASS += 1
    print(f"  [PASS] {msg}")


def bad(msg):
    global FAIL
    FAIL += 1
    print(f"  [FAIL] {msg}")


def load_module_from_path(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_broken_plumbing_fixture(root: Path) -> Path:
    """A skills tree whose nudge plumbing is genuinely broken: the registrar
    exists but wires a different cron, and the nudge worker is absent. The
    OLD check reported wired=False here; the new one must report None."""
    skills = root / "skills"
    s23 = skills / "23-ai-workforce-blueprint" / "scripts"
    s23.mkdir(parents=True, exist_ok=True)
    (skills / "shared-utils").mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "scripts" / "ensure-pipeline-crons.sh").write_text(
        "#!/usr/bin/env bash\n_ensure_closeout_watchdog() { :; }\n",
        encoding="utf-8",
    )
    return skills


def clean_verdict_inputs():
    count = {"transcriptCount": 28, "stateCount": 28, "disagreeWarning": None}
    fields = {"missing": [], "checked": []}
    return count, fields


def main():
    if not QC_SCRIPT.is_file():
        print(f"FATAL: {QC_SCRIPT} not found", file=sys.stderr)
        return 1

    tmproot = Path(tempfile.mkdtemp(prefix="qc-nudge-cadence-test-"))
    try:
        mod = load_module_from_path(QC_SCRIPT, "qc_under_test")

        # ── U1: broken plumbing fixture -> wired None, note, no issues ───────
        print("\n[U1] broken nudge plumbing (stale registrar, worker absent) -> wired is None")
        broken_skills = build_broken_plumbing_fixture(tmproot / "box")
        result1 = mod.check_nudges_wired(broken_skills)
        if (result1.get("wired") is None
                and result1.get("note") == NOTE
                and result1.get("issues") == []):
            ok(f"check_nudges_wired() reports wired=None, note={NOTE!r}, no issues "
               f"even on a box whose plumbing the old check failed: {result1}")
        else:
            bad(f"expected wired=None + note {NOTE!r} + no issues, got: {result1}")

        # ── U2: a path that does not exist -> identical answer ───────────────
        print("\n[U2] a repo path that does not exist -> the same answer (no files read)")
        missing_path = tmproot / "does-not-exist" / "skills"
        result2 = mod.check_nudges_wired(missing_path)
        if (result2.get("wired") is None
                and result2.get("note") == NOTE
                and result2.get("issues") == []):
            ok("the answer is identical on an absent path — the check reads no files, "
               "so it cannot report a wiring fact it did not establish")
        else:
            bad(f"expected the same wired=None answer on an absent path, got: {result2}")

        # ── U3: verdict — PASS, nudgesWired None, nothing in warnings ────────
        print("\n[U3] build_verdict(): nudgesWired=None, the note is carried, no nudge warning")
        count, fields = clean_verdict_inputs()
        verdict, exit_code, details = mod.build_verdict(
            count, [], fields, mod.check_nudges_wired(REPO),
            fabrication_result=None, legacy_result=None, legacy_substance=None,
            state={}, web_store_result=None,
        )
        warn_text = " ".join(details["warnings"]).lower()
        hard_text = " ".join(details["hardFailures"]).lower()
        if (verdict == "PASS" and exit_code == 0
                and details.get("nudgesWired") is None
                and details.get("nudgeNote") == NOTE
                and "nudge" not in warn_text
                and "nudge" not in hard_text):
            ok(f"clean interview -> PASS (exit {exit_code}), nudgesWired=None, "
               f"note={details.get('nudgeNote')!r}, no nudge text in warnings or hardFailures")
        else:
            bad(f"expected PASS/exit0 + nudgesWired=None + note + no nudge warning; got "
                f"verdict={verdict} exit={exit_code} nudgesWired={details.get('nudgesWired')!r} "
                f"nudgeNote={details.get('nudgeNote')!r} warnings={details['warnings']} "
                f"hardFailures={details['hardFailures']}")

        # ── U4: control — a genuine hard failure still blocks ────────────────
        print("\n[U4] CONTROL: a genuine jargon hit still HARD fails with the same nudge result")
        verdict_b, exit_code_b, _details_b = mod.build_verdict(
            count, [{"term": "leverage synergy", "line": 3, "text": "..."}], fields,
            mod.check_nudges_wired(REPO),
            fabrication_result=None, legacy_result=None, legacy_substance=None,
            state={}, web_store_result=None,
        )
        if verdict_b == "FAIL" and exit_code_b == 3:
            ok(f"control: a genuine jargon hit still hard-fails (verdict={verdict_b}, "
               f"exit={exit_code_b}) — the other checks were not weakened")
        else:
            bad(f"expected the jargon hit to still hard-fail, got verdict={verdict_b} "
                f"exit={exit_code_b}")

        # ── U5: the old warning path is gone, not just unreachable ───────────
        print("\n[U5] a caller passing wired=False + issues produces NO nudge warning")
        legacy_wired_false = {
            "wired": False,
            "issues": ["ensure-pipeline-crons.sh (fixture) does not register the interview-nudge cron"],
        }
        verdict_c, exit_code_c, details_c = mod.build_verdict(
            count, [], fields, legacy_wired_false,
            fabrication_result=None, legacy_result=None, legacy_substance=None,
            state={}, web_store_result=None,
        )
        warn_text_c = " ".join(details_c["warnings"]).lower()
        if (verdict_c == "PASS" and exit_code_c == 0
                and "nudge" not in warn_text_c
                and details_c.get("nudgesWired") is False):
            ok("wired=False from any caller no longer produces a nudge warning — the "
               "[nudge-cadence] warning path was removed, and the value is reported verbatim")
        else:
            bad(f"expected PASS with no nudge warning even for wired=False, got "
                f"verdict={verdict_c} warnings={details_c['warnings']} "
                f"nudgesWired={details_c.get('nudgesWired')!r}")

    finally:
        shutil.rmtree(tmproot, ignore_errors=True)

    print("\n" + "=" * 70)
    print(f"RESULTS: {PASS} passed, {FAIL} failed")
    print("=" * 70)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
