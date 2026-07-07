#!/usr/bin/env bash
# 59-anthology-engine/verify.sh -- READ-ONLY, idempotent self-verify (W1.1 scope).
# ----------------------------------------------------------------------------
# Verifies the W1.1-owned house layout and interface contracts so the skill's
# skeleton is provably coherent BEFORE sibling modules land. It is scoped to the
# files this unit authors, so it stays green independent of other units, and it
# is safe to run in CI or post-install (read-only; changes nothing).
#
# Checks: house-layout presence; version agreement; ENGINE-MANIFEST parses with
# S0..S9; field-map carries the exact PRD Section 6 keys; model-map template has
# the five tiers and no Anthropic-family id; nudge templates are em-dash-free and
# fence-free; the PDF house style honors the 14-point floor; every stage runner
# byte-compiles and passes --self-test; no Anthropic-family id in any owned file.
#
# Exit 0 = verified; 4 = drift found.
set -uo pipefail
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
command -v python3 >/dev/null 2>&1 || { echo "verify: FATAL python3 required" >&2; exit 4; }

SELF_DIR="$SELF_DIR" python3 - <<'PY'
import io, json, os, re, subprocess, sys

root = os.environ["SELF_DIR"]
def p(*a): return os.path.join(root, *a)
fails = []
def need(cond, msg):
    if not cond: fails.append(msg)

# --- house layout presence ---
for rel in ["SKILL.md", "ENGINE-MANIFEST.json", "INSTRUCTIONS.md", "HOW-TO-USE.md",
            "MASTERDOC.md", "REPAIRS.md", "CHANGELOG.md", "skill-version.txt",
            "anthology-engine-entry.sh", "install.sh", "preflight.sh",
            "verify.sh", "verify-deps.sh",
            "config/engine-config.template.json", "config/model-map.template.json",
            "config/field-map.json"]:
    need(os.path.isfile(p(rel)), "missing owned file: %s" % rel)

# The ten S0..S9 dispatchers this unit authors, enumerated by exact basename so
# the check verifies precisely the W1.1-owned runners and stays green as sibling
# units land their own helpers in scripts/ (e.g. W1.18's stage_s9_assembly_logic.py).
# A glob over stage_s\d_*.py would over-match any stage_sN_*.py a sibling adds; an
# explicit roster is immune to that and to file-ordering surprises.
stage_files = [
    "stage_s0_intake.py", "stage_s1_avatar.py", "stage_s2_tone.py",
    "stage_s3_title.py", "stage_s4_outline.py", "stage_s5_chapter.py",
    "stage_s6_rewrite.py", "stage_s7_cover.py", "stage_s8_deliver.py",
    "stage_s9_assembly.py",
]
for f in stage_files:
    need(os.path.isfile(p("scripts", f)), "missing stage runner dispatcher: scripts/%s" % f)

# --- version agreement (skill-version.txt == SKILL.md frontmatter version) ---
try:
    ver_txt = io.open(p("skill-version.txt"), encoding="utf-8").read().strip()
    skill_md = io.open(p("SKILL.md"), encoding="utf-8").read()
    m = re.search(r"(?m)^version:\s*([0-9][0-9A-Za-z.\-]*)\s*$", skill_md)
    need(m is not None, "SKILL.md frontmatter has no 'version:' line")
    if m:
        need(m.group(1) == ver_txt, "version mismatch: skill-version.txt=%r SKILL.md=%r" % (ver_txt, m.group(1)))
except Exception as exc:
    fails.append("version check error: %s" % exc)

# --- ENGINE-MANIFEST parses with S0..S9 ---
try:
    man = json.load(io.open(p("ENGINE-MANIFEST.json"), encoding="utf-8"))
    stage_ids = {s.get("id") for s in man.get("stages", [])}
    for i in range(10):
        need(("S%d" % i) in stage_ids, "ENGINE-MANIFEST missing stage S%d" % i)
except Exception as exc:
    fails.append("ENGINE-MANIFEST parse error: %s" % exc)

# --- field-map carries the exact PRD Section 6 keys ---
try:
    fm = json.load(io.open(p("config/field-map.json"), encoding="utf-8"))
    want_deliver = {
        "avatar": ("contact.anthology_avatar_doc_url", "contact.anthology_avatar_pdf_url"),
        "tone": ("contact.anthology_tone_doc_url", "contact.anthology_tone_pdf_url"),
        "titles": ("contact.anthology_titles_doc_url", "contact.anthology_titles_pdf_url"),
        "blurb": ("contact.anthology_blurb_doc_url", "contact.anthology_blurb_pdf_url"),
        "outline": ("contact.anthology_outline_doc_url", "contact.anthology_outline_pdf_url"),
        "chapter": ("contact.anthology_chapter_doc_url", "contact.anthology_chapter_pdf_url"),
        "cover": ("contact.anthology_cover_image_url", "contact.anthology_cover_drive_url"),
        "manuscript": ("contact.anthology_manuscript_doc_url", "contact.anthology_manuscript_pdf_url"),
    }
    df = fm.get("deliverable_fields", {})
    for k, (d, pdf) in want_deliver.items():
        need(df.get(k, {}).get("doc_url") == d, "field-map %s.doc_url != %s" % (k, d))
        need(df.get(k, {}).get("pdf_url") == pdf, "field-map %s.pdf_url != %s" % (k, pdf))
    cf = fm.get("control_fields", {})
    need(cf.get("active_id") == "contact.anthology_active_id", "field-map control active_id wrong")
    need(cf.get("stage") == "contact.anthology_stage", "field-map control stage wrong")
    need(cf.get("rewrite_count") == "contact.anthology_rewrite_count", "field-map control rewrite_count wrong")
except Exception as exc:
    fails.append("field-map check error: %s" % exc)

# --- model-map template: five tiers, no Anthropic-family id ---
_a = "anthro" + "pic"; _c = "clau" + "de-"
banned = re.compile(_c + r"|" + _a + r"/|us\." + _a + r"\.", re.I)
try:
    mm_txt = io.open(p("config/model-map.template.json"), encoding="utf-8").read()
    mm = json.loads(mm_txt)
    for t in ("HEAVY-WRITER", "LIGHT", "JUDGE", "LONGCTX", "IMAGE"):
        need(t in mm.get("tiers", {}), "model-map missing tier %s" % t)
    def walk(node):
        if isinstance(node, dict):
            for v in node.values(): yield from walk(v)
        elif isinstance(node, list):
            for v in node: yield from walk(v)
        elif isinstance(node, str):
            yield node
    for s in walk(mm.get("tiers", {})):
        need(not banned.search(s), "model-map tier value carries an Anthropic-family id: %r" % s)
except Exception as exc:
    fails.append("model-map check error: %s" % exc)

# --- nudge templates: no em/en dash, no triple-backtick fence ---
DASHES = ("\u2014", "\u2013")   # em dash, en dash as escapes; no literal dash byte in this file
FENCE = "`" * 3
ndir = p("config", "nudge-templates")
for tpl in ("gate-open.md", "completion.md", "stuck-renudge.md"):
    fp = os.path.join(ndir, tpl)
    if not os.path.isfile(fp):
        fails.append("missing nudge template: %s" % tpl); continue
    body = io.open(fp, encoding="utf-8").read()
    need(not any(d in body for d in DASHES), "nudge template %s contains an em/en dash character" % tpl)
    need(FENCE not in body, "nudge template %s contains a triple-backtick fence" % tpl)

# --- PDF house style honors the 14-point floor ---
css_fp = p("config", "pdf-house-style", "house.css")
if os.path.isfile(css_fp):
    css = io.open(css_fp, encoding="utf-8").read()
    # Strip /* ... */ comments before scanning. The floor law governs rendered
    # glyphs -- i.e. real font-size *declarations* -- not prose. house.css records
    # its one deliberate deviation ("raised 12pt to 14pt") in comment text, and
    # those words must not be misread as sub-floor tokens. Non-greedy + DOTALL
    # removes block and inline comments alike, leaving only live declarations.
    css_code = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    for val in re.findall(r"(\d+(?:\.\d+)?)pt", css_code):
        need(float(val) >= 14.0, "house.css carries a font token below the 14pt floor: %spt" % val)
else:
    fails.append("missing config/pdf-house-style/house.css")

# --- stage runners: byte-compile + --self-test ---
for f in stage_files:
    fp = p("scripts", f)
    rc = subprocess.call([sys.executable, "-m", "py_compile", fp])
    need(rc == 0, "stage runner does not byte-compile: %s" % f)
    rc = subprocess.call([sys.executable, fp, "--self-test"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    need(rc == 0, "stage runner --self-test failed: %s" % f)

# --- no Anthropic-family id in any owned text file ---
owned = ["SKILL.md", "INSTRUCTIONS.md", "HOW-TO-USE.md", "MASTERDOC.md", "REPAIRS.md",
         "CHANGELOG.md", "ENGINE-MANIFEST.json", "anthology-engine-entry.sh",
         "install.sh", "preflight.sh", "verify.sh", "verify-deps.sh",
         "config/engine-config.template.json", "config/model-map.template.json",
         "config/field-map.json"] + ["scripts/" + f for f in stage_files]
for rel in owned:
    fp = p(rel)
    if not os.path.isfile(fp): continue
    try:
        txt = io.open(fp, encoding="utf-8", errors="replace").read()
    except Exception:
        continue
    if banned.search(txt):
        fails.append("Anthropic-family id shape found in owned file: %s" % rel)

if fails:
    print("verify: DRIFT (%d issue(s))" % len(fails))
    for m in fails: print("  - " + m)
    sys.exit(4)
print("verify: PASS (W1.1 house layout and interface contracts coherent)")
sys.exit(0)
PY
rc=$?
exit "$rc"
