#!/usr/bin/env python3
"""PD-100b acceptance checker. Usage: check_pd100b.py <tree> [--base <ref>]

Rows (01-BUILD-SPEC.md, PD-100b):
  A1  the report lists each replaced line before and after
  A2  no line in the role file states a pace other than the decided value (140)
  A3  the mirror equals the role file's section 9

With --base, every read comes from `git show <ref>:<path>` so the same rows can
be measured on the pre-unit blob. Exit 0 = every row PASS.
"""
import re
import subprocess
import sys
import pathlib

tree = pathlib.Path(sys.argv[1])
base = None
if "--base" in sys.argv:
    base = sys.argv[sys.argv.index("--base") + 1]

ROLE = "23-ai-workforce-blueprint/templates/role-library/presentations/presenters-speech-writer.md"
MIRROR = "23-ai-workforce-blueprint/templates/role-library/presentations/sops/presenters-speech-writer-sops.md"
REPORT = "evidence/PD-100b/BUILD-REPORT.md"


def read(rel, missing_ok=False):
    if base:
        return subprocess.run(["git", "-C", str(tree), "show", f"{base}:{rel}"],
                              capture_output=True, text=True,
                              check=not missing_ok).stdout
    p = tree / rel
    return p.read_text() if p.exists() else ""

role = read(ROLE)
mirror = read(MIRROR)
report = read(REPORT, missing_ok=True)

# ---------------------------------------------------------------- A1
# Every replaced line, before -> after. The report must carry both sides and the
# role file must carry the "after" side (the "before" default statements gone).
PAIRS = [
    ("budget the spoken script at 130 words per minute",
     "budget the spoken script at 140 words per minute"),
    ("Speech at 130 wpm).", "Speech at 140 wpm)."),
    ("did the 130 wpm budget hold", "did the 140 wpm budget hold"),
    ("keep 130 wpm unless evidence", "keep 140 wpm unless evidence"),
    ("(DURATION_MIN x 130)", "(DURATION_MIN x 140)"),
    ("| 130 wpm (tunable) |", "| 140 wpm (tunable) |"),
    ("Webinar Speech at 130 wpm", "Webinar Speech at 140 wpm"),
    ("delivering it at 130 wpm", "delivering it at 140 wpm"),
    ("budgeted at 130 words per minute", "budgeted at 140 words per minute"),
    ("at 130 wpm (130 wpm = about 2.17 words/second)",
     "at 140 wpm (140 wpm = about 2.33 words/second)"),
    ("net spoken seconds x 2.17", "net spoken seconds x 2.33"),
    ("SPOKEN_RATE_WPM = 130", "SPOKEN_RATE_WPM = 140"),
    ("pause-adjusted 130 wpm budget", "pause-adjusted 140 wpm budget"),
    ("SPOKEN_RATE_WPM: 130 (", "SPOKEN_RATE_WPM: 140 ("),
    ("TARGET WORDS: ~3855 | ACTUAL: 3902 (+1.2%)",
     "TARGET WORDS: ~4149 | ACTUAL: 3902 (-5.9%)"),
    ("the 130 wpm math and pause subtraction",
     "the 140 wpm math and pause subtraction"),
]

a1_fail = []
for before, after in PAIRS:
    in_report = before in report and after in report
    in_role = after in role
    gone = before not in role
    if not (in_report and in_role and gone):
        a1_fail.append(f"{before!r} -> {after!r} report={in_report} role={in_role} before_gone={gone}")

# ---------------------------------------------------------------- A2
# Lines still mentioning 130 are allowed only when the 130 is explicitly a
# research band or a named teach-heavy/high-energy alternative. PD-023 (same
# decision D-3) keeps teaching=130 and high-energy=~155-160; D-3 fixes the
# DEFAULT at 140. So: every 130 mention must be qualified, and every statement
# of the procedure's own pace must read 140.
ALLOWED = [
    r"130 to 160",                       # research band (lines 25, 549, 552)
    r"allow 130 for teach-heavy",        # named alternative (line 28)
    r"130 teach-heavy",                  # named alternative (lines 107, 546)
    r"may want 130 WPM for clarity",     # edge case (line 577)
    r"TARGET_WPM=130 with the reason",   # edge case (line 577)
]
a2_fail = []
for n, line in enumerate(role.splitlines(), 1):
    if "130" in line and not any(re.search(p, line) for p in ALLOWED):
        a2_fail.append(f"line {n}: unqualified 130 -> {line[:110]}")
# The default-pace statements must now be 140.
for need in ("You budget the spoken script at 140 words per minute",
             "### SOP 9.1 -- Write the Word-for-Word Webinar Speech at 140 wpm",
             "budgeted at 140 words per minute against DURATION_MIN",
             "net spoken seconds x 2.33",
             "SPOKEN_RATE_WPM = 140",
             "pause-adjusted 140 wpm budget",
             "SPOKEN_RATE_WPM: 140 ("):
    if need not in role:
        a2_fail.append(f"missing default-pace statement: {need!r}")
if "2.17 words/second" in role or "x 2.17" in role:
    a2_fail.append("stale 130-derived arithmetic 2.17 still in the role file")

# ---------------------------------------------------------------- A3
r = role.splitlines(keepends=True)
i9a = next(i for i, l in enumerate(r) if l.startswith("## 9A."))
i10 = next(i for i, l in enumerate(r) if l.startswith("## 10."))
section9 = "".join(r[i9a:i10])
m = mirror.splitlines(keepends=True)
mi = next(i for i, l in enumerate(m) if l.startswith("## 9A."))
mirror_body = "".join(m[mi:])
a3_fail = []
if mirror_body != section9:
    a3_fail.append("mirror body is not byte-identical to role sections 9A+9")
if "130 wpm" in mirror_body and "140 wpm" not in mirror_body:
    a3_fail.append("mirror still states the old pace only")

rows = [("A1", a1_fail), ("A2", a2_fail), ("A3", a3_fail)]
for rid, fails in rows:
    print(f"{'PASS' if not fails else 'FAIL'}  {rid}")
    for f in fails:
        print(f"      {f}")
print(f"counts: pairs={len(PAIRS)} role_130={role.count('130')} "
      f"mirror_lines={len(m)} base={base or 'working-tree'}")
sys.exit(0 if not any(f for _, f in rows) else 1)
