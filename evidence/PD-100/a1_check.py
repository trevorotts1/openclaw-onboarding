#!/usr/bin/env python3
"""PD-100 A1 checker. Usage: a1_check.py <tree> [--base <ref>]
Proves every row of PD-100 on the working tree, and (with --base) on the pre-unit blob.
Exit 0 = all PASS."""
import json, re, subprocess, sys, pathlib

tree = pathlib.Path(sys.argv[1])
base = None
if "--base" in sys.argv:
    base = sys.argv[sys.argv.index("--base") + 1]

ROLE_REL = "23-ai-workforce-blueprint/templates/role-library/presentations/presenters-speech-writer.md"
MIR_REL = "23-ai-workforce-blueprint/templates/role-library/presentations/sops/presenters-speech-writer-sops.md"
MAN_REL = "universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json"

def read(rel):
    if base:
        return subprocess.run(["git", "-C", str(tree), "show", f"{base}:{rel}"],
                              capture_output=True, text=True, check=True).stdout
    return (tree / rel).read_text()

role, mir = read(ROLE_REL), read(MIR_REL)
man = json.loads(read(MAN_REL))
manifest_paths = set()
for p in man["phases"]:
    pa = p.get("produces_artifact")
    for x in ([pa] if isinstance(pa, str) else (pa or [])):
        manifest_paths.add(x)
    for x in p.get("consumes", []):
        manifest_paths.add(x)

fails = []
def chk(label, cond, detail):
    print(("PASS  " if cond else "FAIL  ") + label + f"  [{detail}]")
    if not cond:
        fails.append(label)

c = lambda s, t: t.count(s)

R1 = "open slides.json and each prompt file and read them; compare each slide's copy with its spoken block"
R2 = "Hand the five files to the Delivery Concierge. This role does not copy files to the client and does not message the client."
R3 = "when the client's box has a Notion connection"
R4H = "### SOP 9.4 -- Audio synthesis is owned by the Audio procedure"
R4P = "single owner of voice synthesis"
OLDFAIL = "notion_url.json missing or URL does not resolve = FAIL"
OLD94 = "### SOP 9.4 -- Audio Demonstration via the TTS Fallback Chain"

chk("1a step 9.5-1 sentence in role", c(R1, role) == 1, f"count={c(R1, role)}")
chk("1b step 9.5-1 sentence in mirror", c(R1, mir) == 1, f"count={c(R1, mir)}")
chk("2a handoff sentence in role", c(R2, role) == 1, f"count={c(R2, role)}")
chk("2b handoff sentence in mirror", c(R2, mir) == 1, f"count={c(R2, mir)}")
chk("2c the role no longer runs a client message step", "Notify the owner via openclaw message send" not in role,
    f"count={c('Notify the owner via openclaw message send', role)}")
chk("2d the mirror no longer runs a client message step", "Notify the owner via openclaw message send" not in mir,
    f"count={c('Notify the owner via openclaw message send', mir)}")
chk("3a Notion conditional in role", c(R3, role) >= 4, f"count={c(R3, role)}")
chk("3b Notion conditional in mirror", c(R3, mir) >= 2, f"count={c(R3, mir)}")
chk("3c Notion '= FAIL' line gone (role)", c(OLDFAIL, role) == 0, f"count={c(OLDFAIL, role)}")
chk("3d Notion '= FAIL' line gone (mirror)", c(OLDFAIL, mir) == 0, f"count={c(OLDFAIL, mir)}")
chk("4a SOP 9.4 pointer heading in role", c(R4H, role) == 1, f"count={c(R4H, role)}")
chk("4b SOP 9.4 pointer heading in mirror", c(R4H, mir) == 1, f"count={c(R4H, mir)}")
chk("4c 'single owner of voice synthesis' in role", c(R4P, role) == 1, f"count={c(R4P, role)}")
chk("4d 'single owner of voice synthesis' in mirror", c(R4P, mir) == 1, f"count={c(R4P, mir)}")
chk("4e old SOP 9.4 synthesis block gone (role)", c(OLD94, role) == 0, f"count={c(OLD94, role)}")
chk("4f old SOP 9.4 synthesis block gone (mirror)", c(OLD94, mir) == 0, f"count={c(OLD94, mir)}")
chk("4g exactly one SOP 9.4 in role", c("### SOP 9.4", role) == 1, f"count={c('### SOP 9.4', role)}")
chk("4h exactly one SOP 9.4 in mirror", c("### SOP 9.4", mir) == 1, f"count={c('### SOP 9.4', mir)}")

NEW = ["working/deliverables/PRESENTERS-SPEECH.md", "working/deliverables/PRESENTERS-SPEECH.pdf",
       "working/deliverables/PRESENTERS-SPEECH-FISH-TAGGED.md",
       "working/deliverables/presenter-teleprompter.html", "working/delivery/PRESENTER-AUDIO.mp3"]
OLD = ["working/presenter-speech/presenters_speech.md", "working/presenter-speech/speech.md",
       "working/presenter-speech/speech_tagged.md", "working/presenter-speech/speech.md",
       "working/presenter-speech/Presenters_Speech_<DeckTitle>.pdf",
       "working/presenter-speech/audio/chunk-NN.mp3",
       "working/presenter-speech/audio/Presenters_Speech_<DeckTitle>_demo.mp3",
       "output/[DECK_SLUG]_presenters_speech.pdf"]
for p in NEW:
    chk(f"5a manifest row declares {p}", p in manifest_paths, "in manifest" if p in manifest_paths else "MISSING")
    chk(f"5b role names {p}", c(p, role) >= 1, f"count={c(p, role)}")
for p in OLD:
    chk(f"5c old output path gone from role: {p}", c(p, role) == 0, f"count={c(p, role)}")
chk("6a /tmp dry-run paths gone (mirror)", c("/tmp/speech_test", mir) == 0, f"count={c('/tmp/speech_test', mir)}")
chk("6b <SCRATCH> dry-run paths present (mirror)", c("<SCRATCH>/speech_test", mir) == 2, f"count={c('<SCRATCH>/speech_test', mir)}")

if base:
    print(f"NOTE  A1-core / A1-full not evaluated on the base blob ({base[:12]}): they are line-diff claims "
          f"against the working tree. Evaluated on the build only.")
    print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
    sys.exit(0 if not fails else 1)

# A1: mirror regenerated, measured two ways.
#   core = the SOPs this unit rewrites (9.4 pointer, 9.5) -> every changed line must be in the mirror
#   full = every changed Section 9 line -> printed in full; the pre-existing duplicated SOP 9.1/9.2
#          blocks have no counterpart in the (newer) mirror, so their path-only edits are disclosed.
r9 = role.index("## 9. Standard Operating Procedures")
r10 = role.index("## 10. Quality Gates")
r9_line = role[:r9].count("\n") + 1
r10_line = role[:r10].count("\n") + 1
s94 = role.find("### SOP 9.4 -- Audio synthesis is owned by the Audio procedure")
s94_line = (role[:s94].count("\n") + 1) if s94 >= 0 else 10**9

# The diff base must be explicit. Default to the branch point so the check is
# non-vacuous on a committed tree; a diff base that yields zero lines is a FAIL,
# never a pass (a control that cannot fail is not a control).
diff_base = None
if "--diff-base" in sys.argv:
    diff_base = sys.argv[sys.argv.index("--diff-base") + 1]
if not diff_base:
    r = subprocess.run(["git", "-C", str(tree), "merge-base", "HEAD", "origin/main"],
                       capture_output=True, text=True)
    diff_base = r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else "HEAD"
diff = subprocess.run(["git", "-C", str(tree), "diff", "-U0", diff_base, "--", ROLE_REL],
                      capture_output=True, text=True, check=True).stdout
added, newline = [], 0
for line in diff.split("\n"):
    m = re.match(r"^@@ -\S+ \+(\d+)(?:,(\d+))? @@", line)
    if m:
        newline = int(m.group(1)) - 1
        continue
    if line.startswith("+"):
        newline += 1
        body = line[1:]
        if body.strip() and body.strip() != "---" and r9_line <= newline < r10_line:
            added.append((newline, body))
    elif line.startswith("-") or line.startswith("\\"):
        pass
    elif line.startswith(" "):
        newline += 1
core = [(n, a) for n, a in added if n >= s94_line]
full_missing = [(n, a) for n, a in added if a.strip() not in mir]
core_missing = [(n, a) for n, a in core if a.strip() not in mir]
chk("A1-core mirror regenerated (every changed SOP 9.4-9.5 role line present in mirror)",
    len(core) > 0 and len(core_missing) == 0,
    f"diff-base={diff_base[:12]} checked={len(core)} missing={len(core_missing)}")
if len(core) == 0:
    print("        the diff base yielded no lines in SOP 9.4-9.5: pass --diff-base <unit base> (this is a FAIL, not a pass)")
if core_missing:
    for n, a in core_missing:
        print(f"        MISSING new-line {n}: {a[:110]}")
chk("A1-full every changed Section 9 role line present in mirror",
    len(added) > 0 and len(full_missing) == 0,
    f"diff-base={diff_base[:12]} checked={len(added)} missing={len(full_missing)}")
for n, a in full_missing:
    print(f"        disclosed divergence new-line {n}: {a[:110]}")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
sys.exit(0 if not fails else 1)
