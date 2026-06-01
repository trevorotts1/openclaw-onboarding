#!/usr/bin/env bash
# test-sop-substance-models.sh — SOP substance-gate regression guard.
#
# Proves, from a clean checkout (no live OpenClaw install required), that the
# v10.15.25 / v10.16.24 substance gate in qc-completeness.sh accepts BOTH SOP
# models WITHOUT weakening the gate against real garbage:
#
#   * Standalone-SOP model (existing): a standalone sops/.../NN-*.md file is
#     substantive iff >=7KB + all five DMAIC headers + no "[Step N - to be
#     personalized]" / "to be personalized based on research" stub.
#   * Embedded-Section-9 model (NEW, the WS-2 instantiate shape): a role's
#     how-to.md is substantive iff >=7KB AND has a "## 9." SOP section with >=1
#     "### SOP 9.x" block carrying the When/Frequency/Inputs/Steps/Outputs/
#     Hand-to/Failure-mode structure AND no {{token}} leak. Embedded SOP blocks
#     count toward substantive_sop_count.
#   * A role passes its floor if EITHER model is satisfied.
#
# It STILL must FAIL on: [Step N...] stubs, {{token}} leaks, <7KB how-tos, or a
# missing Section 9. Goal = stop false-NEGATIVES on instantiated content, NOT
# weaken the gate against real garbage.
#
# Mechanism: this test EXTRACTS the real sop_is_substantive() / embedded_sop_count()
# functions (and their regex constants) out of the SHIPPED qc-completeness.sh
# analyzer heredoc and runs them against on-disk fixtures — so it tests the exact
# code that ships, not a copy.
#
# Exit 0 on pass, 1 on any failure.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QC_SCRIPT="$SCRIPT_DIR/qc-completeness.sh"

if [ ! -f "$QC_SCRIPT" ]; then
  echo "test-sop-substance-models: qc-completeness.sh missing at $QC_SCRIPT" >&2
  exit 1
fi

python3 - "$QC_SCRIPT" <<'PY'
import sys, os, re, tempfile, ast
from pathlib import Path

QC = Path(sys.argv[1])
src = QC.read_text()

# ---- pull the analyzer heredoc out of the shipped script --------------------
# The main analyzer is the `python3 - <<'PYEOF' ... PYEOF` block. Grab the body
# between the opener line and its terminator.
lines = src.split("\n")
opener_idx = None
for i, ln in enumerate(lines):
    if ln.startswith("python3 - <<'PYEOF'"):
        opener_idx = i
        break
if opener_idx is None:
    print("FAIL: could not locate analyzer heredoc opener in qc-completeness.sh")
    sys.exit(1)
term_idx = None
for j in range(opener_idx + 1, len(lines)):
    if lines[j].strip() == "PYEOF":
        term_idx = j
        break
if term_idx is None:
    print("FAIL: could not locate analyzer heredoc terminator")
    sys.exit(1)
analyzer_src = "\n".join(lines[opener_idx + 1:term_idx])

# Sanity: it must parse.
ast.parse(analyzer_src)

# ---- exec ONLY the substance machinery from the shipped analyzer ------------
# We can't exec the whole analyzer (it reads os.environ and walks disk on import),
# so we slice out the top of the analyzer up to the end of embedded_sop_count(),
# which contains the regex constants + both substance functions and nothing that
# touches the environment.
end_marker = "def embedded_sop_count("
if end_marker not in analyzer_src:
    print("FAIL: embedded_sop_count() not present in shipped qc-completeness.sh — BUG 2 fix missing")
    sys.exit(1)

# Slice out ONLY the substance machinery: from the first regex constant
# (LIBRARY_MARKER) through the end of embedded_sop_count(). This deliberately
# EXCLUDES the analyzer preamble that reads os.environ["SKILL_DIR"] / walks disk,
# so we can exec the real shipped functions in isolation.
asl = analyzer_src.split("\n")
const_start = next(k for k, l in enumerate(asl) if l.startswith("LIBRARY_MARKER"))
emb_start = next(k for k, l in enumerate(asl) if l.startswith("def embedded_sop_count("))
# walk to the end of embedded_sop_count(): first subsequent line at column 0 that
# is not part of the function body (non-indented, non-blank).
emb_end = len(asl)
for k in range(emb_start + 1, len(asl)):
    l = asl[k]
    if l and not l[0].isspace():
        emb_end = k
        break
slice_src = "\n".join(asl[const_start:emb_end])

# The sliced functions reference `re` and `Path` (imported in the excluded
# preamble), so seed the exec namespace with them.
ns = {"re": re, "Path": Path}
exec(compile(slice_src, "qc-substance-slice", "exec"), ns)
sop_is_substantive = ns["sop_is_substantive"]
embedded_sop_count = ns["embedded_sop_count"]
SUBSTANTIVE_MIN_BYTES = ns["SUBSTANTIVE_MIN_BYTES"]

# Replicate the per-role floor decision EXACTLY as the analyzer applies it.
SOP_FLOOR = 4
EMBEDDED_SOP_FLOOR = 1
def role_meets_floor(role_dir: Path):
    howto = role_dir / "how-to.md"
    howto_embedded = embedded_sop_count(howto) if howto.is_file() else 0
    standalone = sum(1 for sf in sorted(role_dir.glob("0[1-9]-*.md")) if sop_is_substantive(sf))
    substantive = standalone + howto_embedded
    meets = (standalone >= SOP_FLOOR) or (howto_embedded >= EMBEDDED_SOP_FLOOR)
    return meets, substantive, howto_embedded, standalone

# ---- fixtures ---------------------------------------------------------------
fails = 0
def check(cond, msg):
    global fails
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {msg}")
    if not cond:
        fails += 1

PAD = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 200  # ~11KB filler

def embedded_howto(company="Acme Co", n_blocks=3, leak=False, stub=False, small=False, no_section9=False):
    """Build a WS-2-style instantiated how-to.md with embedded Section-9 SOPs."""
    head = f"# Role Name\n\n<!-- Filled from role-library v10.15.25 -->\nGenerated for: {company}\nIndustry: Widgets\n\n"
    body = "## 1. Mission\n\n" + PAD + "\n\n## 8. Tools\n\n" + PAD + "\n\n"
    sec9 = "" if no_section9 else "## 9. Standard Operating Procedures\n\n"
    for i in range(1, n_blocks + 1):
        sec9 += (
            f"### SOP 9.{i} — Do the thing #{i}\n"
            "- When to run: every Monday at 9am or when a new lead arrives\n"
            "- Frequency: weekly\n"
            "- Inputs: the lead record, the CRM, the prior week's report\n"
            "- Steps:\n  1. open the CRM\n  2. pull the report\n  3. send the summary\n"
            "- Outputs: a delivered summary + an updated CRM record\n"
            "- Hand-to: the closer agent\n"
            "- Failure-mode: if the CRM is down, escalate to ops and retry in 1h\n\n"
            + PAD + "\n\n"
        )
    text = head + body + sec9
    if leak:
        text += "\nCompany: {{COMPANY_NAME}} persona {{ASSIGNED_PERSONA_VERSION}}\n"
    if stub:
        text += "\n[Step 3 - to be personalized based on research]\n"
    if small:
        # tiny file: strip the padding
        text = head + "## 9. SOPs\n### SOP 9.1 — x\n- When to run: now\n- Frequency: daily\n- Steps: do it\n"
    return text

def standalone_dmaic(small=False, stub=False):
    body = "# SOP: Lead Intake\n\n"
    for h in ("DEFINE", "MEASURE", "ANALYZE", "IMPROVE", "CONTROL"):
        body += f"## {h}\n\n" + PAD + "\n\n"
    if stub:
        body += "\n[Step 2 - to be personalized based on research]\n"
    if small:
        body = "# SOP\n## DEFINE\nx\n## MEASURE\nx\n## ANALYZE\nx\n## IMPROVE\nx\n## CONTROL\nx\n"
    return body

with tempfile.TemporaryDirectory() as td:
    root = Path(td)

    # 1. INSTANTIATED-EMBEDDED role -> substantive + meets floor (the false-negative we fix)
    r1 = root / "marketing" / "00-cmo"; r1.mkdir(parents=True)
    (r1 / "how-to.md").write_text(embedded_howto(n_blocks=3))
    meets, subst, emb, sa = role_meets_floor(r1)
    check((r1 / "how-to.md").stat().st_size >= SUBSTANTIVE_MIN_BYTES, "embedded fixture is >=7KB")
    check(emb == 3, f"embedded how-to counts 3 substantive Section-9 SOP blocks (got {emb})")
    check(meets, "instantiated-embedded role MEETS the floor (was a false-NEGATIVE before the fix)")
    check(subst >= 1, f"embedded role contributes to substantive_sop_count (got {subst})")

    # 2. EMBEDDED with {{token}} leak -> FAIL (must stay strict)
    r2 = root / "sales" / "closer"; r2.mkdir(parents=True)
    (r2 / "how-to.md").write_text(embedded_howto(leak=True))
    meets, subst, emb, sa = role_meets_floor(r2)
    check(emb == 0, "embedded how-to with a {{token}} leak counts 0 SOPs")
    check(not meets, "{{token}}-leaking role FAILS the floor")

    # 3. EMBEDDED with a [Step N - to be personalized] stub -> FAIL
    r3 = root / "ops" / "coordinator"; r3.mkdir(parents=True)
    (r3 / "how-to.md").write_text(embedded_howto(stub=True))
    meets, subst, emb, sa = role_meets_floor(r3)
    check(emb == 0, "embedded how-to with a [Step N...] stub counts 0 SOPs")
    check(not meets, "stub-bearing role FAILS the floor")

    # 4. EMBEDDED but <7KB -> FAIL
    r4 = root / "research" / "analyst"; r4.mkdir(parents=True)
    (r4 / "how-to.md").write_text(embedded_howto(small=True))
    meets, subst, emb, sa = role_meets_floor(r4)
    check((r4 / "how-to.md").stat().st_size < SUBSTANTIVE_MIN_BYTES, "small fixture is <7KB")
    check(emb == 0, "embedded how-to <7KB counts 0 SOPs")
    check(not meets, "<7KB role FAILS the floor")

    # 5. EMBEDDED but no "## 9." Section -> FAIL
    r5 = root / "finance" / "controller"; r5.mkdir(parents=True)
    (r5 / "how-to.md").write_text(embedded_howto(no_section9=True))
    meets, subst, emb, sa = role_meets_floor(r5)
    check((r5 / "how-to.md").stat().st_size >= SUBSTANTIVE_MIN_BYTES, "no-section9 fixture is still >=7KB")
    check(emb == 0, "how-to with NO Section 9 counts 0 SOPs (even when >=7KB)")
    check(not meets, "role with no Section 9 and no standalone SOPs FAILS the floor")

    # 6. STANDALONE-SOP model still works (regression guard) -> meets floor at 4 good files
    r6 = root / "crm" / "specialist"; r6.mkdir(parents=True)
    for i in range(1, 5):
        (r6 / f"0{i}-topic-{i}.md").write_text(standalone_dmaic())
    meets, subst, emb, sa = role_meets_floor(r6)
    check(sa == 4, f"4 standalone DMAIC SOP files are all substantive (got {sa})")
    check(meets, "standalone-model role with 4 good SOPs MEETS the floor (regression guard)")

    # 7. STANDALONE model with only thin/stub files -> FAIL (gate stays strict)
    r7 = root / "crm" / "thin"; r7.mkdir(parents=True)
    (r7 / "01-a.md").write_text(standalone_dmaic(small=True))   # <7KB
    (r7 / "02-b.md").write_text(standalone_dmaic(stub=True))    # stub
    meets, subst, emb, sa = role_meets_floor(r7)
    check(sa == 0, "thin/stub standalone SOP files are NOT substantive")
    check(not meets, "standalone role with only thin/stub SOPs FAILS the floor")

print("")
if fails:
    print(f"SOP substance-model checks: FAIL ({fails} failed)")
    sys.exit(1)
print("SOP substance-model checks: PASS")
PY
rc=$?
exit $rc
