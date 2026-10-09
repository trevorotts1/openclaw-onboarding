#!/usr/bin/env python3
"""U15i: the docs say what the code does. Stdlib only, no network, no spend.

Proves, fail-first on the base tree:
  (a) the card's length list equals the keys of
      references/prompt-templates/length-classes.json, and the spec names that
      one table (3.1) instead of restating it as prose;
  (b) references/style-bibles/realism-cinematic.md contains no
      "Restated for emphasis", keeps the recipe as the source of the realism
      mode's phrases, and fixes the camera as per shot;
  (c) the docs point at the template system: SKILL.md has a "Prompt templates"
      section with a pointer from the Suno recipe and from the lip-sync
      bullets; the card's 3.3 points at looks/; QC.md names the H3 band, the
      prompt receipt, PROMPT_NOT_TEMPLATED and the prompt_compliance gate.

Run: python3 scripts/core/prompt_templates/test_docs_u15i.py
Exit 0 = all pass, 1 = failures. pytest-collectable (test_* functions).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORE = HERE.parent
SKILL = CORE.parent.parent          # .../<skill>
for _p in (str(CORE), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_CACHE = CORE / "__pycache__"
if _CACHE.is_dir():
    for _n in _CACHE.iterdir():
        if _n.suffix == ".pyc":
            try:
                _n.unlink()
            except OSError:
                pass

import prompt_templates as PT  # noqa: E402

FAILS = []

def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % (detail,)) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)

def _read(rel):
    p = SKILL / rel
    return p.read_text(encoding="utf-8") if p.is_file() else None

def _class_seconds():
    return sorted(int(row["chosen_s"]) for row in (PT.load("length_classes").get("classes") or {}).values())

def _seconds_in(text, unique=False):
    """Every 'N seconds' / 'N-minute' value in a passage, as seconds.
    unique=True keeps the first occurrence of each value, in order."""
    out = [int(n) * (60 if u.lower() == "minute" else 1)
           for n, u in re.findall(r"(\d+)[- ]?(second|minute)", text, re.I)]
    if not unique:
        return out
    seen, keep = set(), []
    for s in out:
        if s not in seen:
            seen.add(s)
            keep.append(s)
    return keep

# ---- (a) the card's length list IS the table -------------------------------
def test_card_lengths_equal_the_table_keys():
    text = _read("references/choice-card-spec.md")
    check("choice-card-spec.md exists", text is not None)
    if text is None:
        return
    want = _class_seconds()
    # 3.1 must name the one table the lengths come from.
    check("3.1 names references/prompt-templates/length-classes.json",
          "length-classes.json" in text)
    m = re.search(r"Offered values, in order:(.*?)(?:\n\n|\Z)", text, re.DOTALL)
    check("3.1 has the offered-values sentence", m is not None)
    if m:
        order = _seconds_in(m.group(1), unique=True)
        check("3.1's length list equals the table keys, in order",
              order == want, (order, want))
    # the layout block shows the same six, no more, no fewer.
    layout = re.search(r"Length:\s*(.*?)\n\s*\n", text, re.DOTALL) or \
        re.search(r"Length:\s*(.*?)\n\s*Shape:", text, re.DOTALL)
    check("the layout block shows a Length line", layout is not None)
    if layout:
        got = _seconds_in(layout.group(1), unique=True)
        check("the layout Length list equals the table keys",
              got == want, (got, want))
    # the five look labels the card offers are the look files' own labels.
    for look_id in PT.LOOKS:
        label = str((PT.load("look", look_id) or {}).get("label", ""))
        check("look %s is named on the card by its look label" % look_id,
              bool(label) and label.lower() in text.lower(), label)

# ---- (b) the realism recipe is the source, no restated duplicates ----------
def test_realism_recipe_is_the_source():
    text = _read("references/style-bibles/realism-cinematic.md")
    check("realism-cinematic.md exists", text is not None)
    if text is None:
        return
    check("realism-cinematic.md contains no 'Restated for emphasis'",
          "Restated for emphasis" not in text)
    check("the motion block appears exactly once",
          text.count("Motion realism: natural human motion") == 1,
          text.count("Motion realism: natural human motion"))
    check("the identity lock appears exactly once",
          text.count("Identity lock:") == 1, text.count("Identity lock:"))
    check("the camera is per shot",
          re.search(r"^Camera:[^\n]*per shot", text, re.M | re.I) is not None)
    low = text.lower()
    miss = [p for p in ("photoreal cinematic live-action look", "natural skin texture",
                        "shallow depth of field", "35mm film grade", "no cartoon")
            if p not in low]
    check("the recipe still carries the five realism mode phrases", not miss, miss)
    check("the Chanel identity is a worked example",
          "worked example" in low and "chanel" in low)

# ---- (c) the docs point at the template system -----------------------------
def test_docs_point_at_the_template_system():
    skill = _read("SKILL.md") or ""
    check("SKILL.md has a 'Prompt templates' section",
          re.search(r"^##+ .*Prompt templates", skill, re.M) is not None)
    check("SKILL.md points at references/prompt-templates/",
          "references/prompt-templates/" in skill)
    check("SKILL.md names the one assembler prompt_templates",
          "prompt_templates" in skill)
    check("SKILL.md carries the H3 band 5,000-6,800",
          "5,000" in skill and "6,800" in skill)
    check("SKILL.md names the prompt receipt",
          "receipt" in skill.lower() and "prompt_sha256" in skill)
    check("SKILL.md names PROMPT_NOT_TEMPLATED", "PROMPT_NOT_TEMPLATED" in skill)
    check("SKILL.md names the prompt_compliance gate", "prompt_compliance" in skill)
    # the two pointers the unit names: the Suno recipe and the lip-sync bullets.
    suno = re.search(r"## Suno song recipe(.*?)\n## ", skill, re.DOTALL)
    check("the Suno recipe section points at the template system",
          suno is not None and "Prompt templates" in suno.group(1))
    lipsync = re.search(r"- \*\*Lip-sync[^\n]*decision 33(.*?)\n- \*\*", skill, re.DOTALL)
    check("the lip-sync bullets point at the avatar template",
          lipsync is not None and "Prompt templates" in lipsync.group(1),
          "no Prompt templates pointer inside the lip-sync bullets")
    card = _read("references/choice-card-spec.md") or ""
    check("the card's 3.3 points at looks/", "looks/" in card)
    qc = _read("QC.md") or ""
    for token in ("prompt_templates", "PROMPT_NOT_TEMPLATED", "prompt_compliance",
                  "5,000-6,800", "receipt"):
        check("QC.md names %s" % token, token in qc)

def main():
    test_card_lengths_equal_the_table_keys()
    test_realism_recipe_is_the_source()
    test_docs_point_at_the_template_system()
    print()
    if FAILS:
        print("FAILED: %d" % len(FAILS))
        for f in FAILS:
            print("  - %s" % f)
        return 1
    print("ALL PASS")
    return 0

if __name__ == "__main__":
    sys.exit(main())
