#!/usr/bin/env python3
# tests/unit/rescue-escalation-v4-stamp.test.py
#
# Proves the section-5j stamper (scripts/stamp-rescue-escalation.py, called by
# scripts/apply-fleet-standards.sh 5j and by install.sh) on the real box
# populations:
#   1. CLIENT box with NO section -> inserted once, after the first top-level
#      block, never inside another marker pair, far below 150,000 chars, with a
#      timestamped backup next to AGENTS.md. (origin/main logged "WIRING GAP"
#      and left every client box without the section.)
#   2. re-run -> byte-identical no-op, no second backup.
#   3. V3-stamped box (V3 markers + the V3 tail section) -> upgraded in place
#      to V4, no orphaned V3 marker, no leftover tail, no duplicate heading.
#   4. V1-marked and unmarked sections -> upgraded, no orphaned marker.
#   5. OPERATOR box with no section -> skipped, untouched, no backup.
#   6. 5j itself calls the stamper and no longer refuses to create the section.
# Hermetic: temp files only. Run: python3 tests/unit/rescue-escalation-v4-stamp.test.py
import glob
import json
import os
import subprocess
import sys
import tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
STAMP = os.path.join(REPO, "scripts", "stamp-rescue-escalation.py")
TPL = os.path.join(REPO, "scripts", "rescue-escalation-section.md.tpl")
AFS = os.path.join(REPO, "scripts", "apply-fleet-standards.sh")
V4 = "<!-- RESCUE_ESCALATION_BOXNAME_V4 -->"
HEADING = "## Escalate to Rescue Rangers"

PASS = FAIL = 0


def check(cond, name, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok " + name)
    else:
        FAIL += 1
        print("  FAIL " + name + (("\n       " + str(detail)[:600]) if detail else ""))


if not os.path.isfile(STAMP):
    print("FAIL: %s does not exist -- 5j has no stamper that can create the section" % STAMP)
    sys.exit(1)


def box(agents_text, env_vars=None):
    d = tempfile.mkdtemp(prefix="rr-stamp-test.")
    a = os.path.join(d, "AGENTS.md")
    with open(a, "w") as fh:
        fh.write(agents_text)
    cfg = os.path.join(d, "openclaw.json")
    with open(cfg, "w") as fh:
        json.dump({"env": {"vars": {"FLEET_STANDING_BOX_SLUG": "box-fixture"} if env_vars is None else env_vars}}, fh)
    return d, a, cfg


def stamp(a, cfg, ts="20260101000000"):
    env = {k: v for k, v in os.environ.items()
           if k not in ("IS_OPERATOR_BOX", "OPERATOR_BOX", "N8N_API_KEY", "FLEET_STANDING_BOX_SLUG")}
    env["TIMESTAMP"] = ts
    p = subprocess.run([sys.executable, STAMP, "--agents", a, "--tpl", TPL, "--config", cfg],
                       env=env, capture_output=True, text=True, timeout=60)
    return p.stdout.strip()


def read(p):
    return open(p).read()


CEO = ("<!-- CEO_EXECUTION_POLICY_V3 -->\n## Task intake\n\npolicy text\n"
       "<!-- END CEO_EXECUTION_POLICY_V3 -->\n")
MANAGED = ("<!-- MULTI_HEADING_V1 -->\n## Managed A\n\ntext\n\n## Managed B\n\n"
           "```\n## not a heading, inside a fence\n```\n<!-- END MULTI_HEADING_V1 -->\n")
FILLER = "## Big Section\n\n" + ("filler line for size\n" * 9000)  # ~190K chars

print("== 1. client box with no section: inserted once, near the top ==")
original = CEO + "---\n\n# AGENTS.md\n\n" + MANAGED + "\n## First Run\n\nhello\n\n" + FILLER
d, a, cfg = box(original)
verdict = stamp(a, cfg)
txt = read(a)
pos = txt.find(V4)
check(verdict.startswith("insert:"), "verdict is insert", verdict)
check(txt.count(V4) == 1 and txt.count(HEADING) == 1, "exactly one section, one heading")
check(0 < pos < 150000, "inserted well before char 150,000 (at %d)" % pos)
check(pos > txt.find("<!-- END CEO_EXECUTION_POLICY_V3 -->"), "inserted AFTER the first top-level block")
check(not (txt.find("<!-- MULTI_HEADING_V1 -->") < pos < txt.find("<!-- END MULTI_HEADING_V1 -->")),
      "never inside another managed marker pair")
check("box-fixture" in txt and "rr-escalate.sh" in txt, "box slug rendered, section points at rr-escalate.sh")
check(txt.startswith(CEO) and txt.rstrip().endswith("filler line for size")
      and len(txt) - len(original) == int(verdict.split(":")[2]), "only the section was added")
baks = glob.glob(a + ".bak-rescue-esc-*")
check(len(baks) == 1 and read(baks[0]) == original, "timestamped backup next to AGENTS.md holds the original bytes", baks)

print("== 2. re-run is a no-op ==")
before = read(a)
verdict = stamp(a, cfg, ts="20260101000001")
check(verdict == "noop" and read(a) == before, "second run: verdict noop, bytes identical", verdict)
check(len(glob.glob(a + ".bak-rescue-esc-*")) == 1, "no backup written for a no-op")

print("== 3. V3-stamped box upgrades to V4 in place ==")
v3 = ("# AGENTS\n\nintro\n\n<!-- RESCUE_ESCALATION_BOXNAME_V3 -->\n" + HEADING + " (when you are stuck)\n\n"
      "old V3 body with a hand-built curl\n<!-- END RESCUE_ESCALATION_BOXNAME_V3 -->\n\n"
      "## What Rescue Rangers IS + your own wiring (READ BEFORE ANSWERING)\n\nold tail\n\n"
      "## Some Other Section\nUntouched.\n")
d, a, cfg = box(v3)
verdict = stamp(a, cfg)
txt = read(a)
check(verdict.startswith("upgrade:"), "verdict is upgrade", verdict)
check(V4 in txt and "BOXNAME_V3" not in txt, "V4 present, no orphaned V3 marker")
check("What Rescue Rangers IS + your own wiring" not in txt and "hand-built curl" not in txt,
      "V3 body and V3 tail section consumed")
check(txt.count(HEADING) == 1 and "## Some Other Section\nUntouched." in txt, "one heading, next section untouched")
check(stamp(a, cfg) == "noop", "upgraded box is then a no-op")

print("== 4. V1-marked and unmarked sections upgrade ==")
for label, body in (("V1", "<!-- RESCUE_ESCALATION_BOXNAME_V1 -->\n" + HEADING + "\n\nv1\n<!-- END RESCUE_ESCALATION_BOXNAME_V1 -->\n\n"),
                    ("unmarked", HEADING + " (when you are stuck)\n\nancient\n\n")):
    d, a, cfg = box("# AGENTS\n\n" + body + "## Tail\nkeep\n")
    verdict = stamp(a, cfg)
    txt = read(a)
    check(verdict.startswith("upgrade:") and V4 in txt and "BOXNAME_V1" not in txt
          and txt.count(HEADING) == 1 and txt.endswith("## Tail\nkeep\n"), label + " section upgraded cleanly", verdict)

print("== 5. operator box is skipped ==")
plain = "# AGENTS\n\nintro\n\n## First Run\n\nhello\n"
d, a, cfg = box(plain, {"FLEET_STANDING_BOX_SLUG": "operator-box", "IS_OPERATOR_BOX": "1"})
verdict = stamp(a, cfg)
check(verdict == "skipped-operator" and read(a) == plain and not glob.glob(a + ".bak-rescue-esc-*"),
      "IS_OPERATOR_BOX=1: skipped, untouched, no backup", verdict)

print("== 6. unseeded slug still gets the section, with an honest note ==")
d, a, cfg = box(plain, {})
verdict = stamp(a, cfg)
check(verdict.startswith("insert:") and "NOT SEEDED YET" in read(a), "section inserted, says the slug is missing", verdict)

print("== 7. section 5j calls the stamper ==")
afs = read(AFS)
check("stamp-rescue-escalation.py" in afs, "apply-fleet-standards.sh 5j invokes stamp-rescue-escalation.py")
check("not creating one" not in afs, "5j no longer refuses to create a missing section")

print("\nRESULT: %d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
