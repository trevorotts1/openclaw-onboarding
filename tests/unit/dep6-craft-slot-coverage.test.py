#!/usr/bin/env python3
"""
tests/unit/dep6-craft-slot-coverage.test.py — DEP-6 (F3.8 / Q3-code-image-personas)
CONTRACT test: the persona library covers the CODE and IMAGE craft slots with REAL
specialists, so slot-based work (a website/app build decomposed into CODE / IMAGE /
CONTENT sub-tasks) resolves to a genuine craft persona instead of a nearest-domain
proxy — and the addition is INERT for every pre-existing non-craft selection.

Offline, stdlib-only. No DB, no network, no live persona index. It reads the SAME
literals the selector runs (imported by path) and the shipped persona-categories.json
+ INDEX-MANIFEST.json, then asserts:

  CODE slot
    C1  'software-craft' is in the controlled-vocab domainTags (persona-categories.json)
    C2  hunt-thomas-pragmatic-programmer exists: blueprint on disk, categories entry
        valid (non-empty domain, every domain in vocab, custom kebab-case), and it
        carries the 'software-craft' domain
    C3  the FOUR selector tables all carry software-craft in ONE change:
        DEPT_DOMAIN_TAGS['engineering'], _CATEGORY_DOMAINS['code'],
        CRAFT_PRIMARY_DOMAINS['code'] == {'software-craft'}, and hunt's domain
    C4  craft_domain_bonus fires (> 0) for hunt-thomas on a CODE task and is exactly
        0.0 for a representative non-craft persona (the specialist wins, proxies don't)
    C5  INERTNESS: NO persona without a 'software-craft' domain earns any CODE craft
        bonus (the tag can never falsely surface a non-engineering persona)

  IMAGE slot (surface/tag only — no new source)
    I1  budelmann-brand-identity-essentials is the IMAGE-craft specialist: earns the
        design/image craft bonus via visual-communication (now a design craft-primary)
    I2  opara-color-works (color-heavy union) also earns the design craft bonus
    I3  the pre-existing design specialist rohde-the-sketchnote-workbook is NOT
        displaced — it still earns a craft bonus via visual-storytelling

  SET triad
    T1  the N38 count triad agrees at 83 (blueprint dirs == categories keys ==
        manifest.persona_count == manifest.canonical_persona_count)

  Mirror invariant (software-craft must be a KNOWN domain, not off-vocab)
    M1  build-workforce.py dept_to_domains['engineering'] also carries software-craft
        (both byte-identical copies), so test-dept-domain-mirror T3 VOCAB stays green

EXIT 0 = every assertion passed; 1 otherwise.
Usage: python3 tests/unit/dep6-craft-slot-coverage.test.py [REPO_ROOT]
"""
import ast
import importlib.util
import json
import re
import sys
from pathlib import Path

REPO = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]
SK22 = REPO / "22-book-to-persona-coaching-leadership-system"
SCRIPTS = REPO / "23-ai-workforce-blueprint" / "scripts"
SELECTOR = SCRIPTS / "persona-selector-v2.py"
BUILDER = SCRIPTS / "build-workforce.py"
CATS = SK22 / "persona-categories.json"
MANIFEST = REPO / "shared-utils" / "prebuilt-index" / "INDEX-MANIFEST.json"

CODE_PERSONA = "hunt-thomas-pragmatic-programmer"
IMAGE_PRIMARY = "budelmann-brand-identity-essentials"
IMAGE_UNION = "opara-color-works"
DESIGN_INCUMBENT = "rohde-the-sketchnote-workbook"
SOFTWARE_CRAFT = "software-craft"

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


def check(label, cond, detail=""):
    (ok if cond else bad)(label + (f" ({detail})" if detail and not cond else ""))


# ── load the selector module by path (imports pure funcs + tag literals) ───────
spec = importlib.util.spec_from_file_location("sel_dep6", SELECTOR)
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)
norm = S._norm_tag

cats = json.loads(CATS.read_text(encoding="utf-8"))
P = cats["personas"]
vocab = set(cats.get("domainTags", []))
KEBAB = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def dom(slug):
    return {norm(t) for t in P[slug]["domain"]}


print("=" * 70)
print("DEP-6 CRAFT-SLOT COVERAGE CONTRACT (CODE + IMAGE)")
print("=" * 70)

# ─────────────────────────────── CODE slot ────────────────────────────────────
print("--- CODE slot ---")

# C1
check("C1: 'software-craft' in controlled-vocab domainTags", SOFTWARE_CRAFT in vocab)

# C2
entry = P.get(CODE_PERSONA)
check("C2a: hunt-thomas categories entry present", entry is not None)
bp = SK22 / "personas" / CODE_PERSONA / "persona-blueprint.md"
check("C2b: hunt-thomas persona-blueprint.md on disk", bp.is_file())
if entry:
    d = entry.get("domain", [])
    check("C2c: hunt-thomas domain is a non-empty list", isinstance(d, list) and bool(d))
    bad_dom = [t for t in d if t not in vocab]
    check("C2d: every hunt-thomas domain is in the controlled vocab", not bad_dom,
          f"off-vocab: {bad_dom}")
    bad_cus = [t for t in entry.get("custom", []) if not KEBAB.match(str(t))]
    check("C2e: hunt-thomas custom tags are kebab-case", not bad_cus, f"bad: {bad_cus}")
    check("C2f: hunt-thomas carries the 'software-craft' domain", SOFTWARE_CRAFT in dom(CODE_PERSONA))

# C3 — all four tables in one change
eng = {norm(t) for t in S.DEPT_DOMAIN_TAGS.get("engineering", [])}
codecat = {norm(t) for t in S._CATEGORY_DOMAINS.get("code", set())}
prim_code = {norm(t) for t in S.CRAFT_PRIMARY_DOMAINS.get("code", set())}
check("C3a: DEPT_DOMAIN_TAGS['engineering'] carries software-craft", SOFTWARE_CRAFT in eng)
check("C3b: _CATEGORY_DOMAINS['code'] carries software-craft", SOFTWARE_CRAFT in codecat)
check("C3c: CRAFT_PRIMARY_DOMAINS['code'] == {'software-craft'}", prim_code == {SOFTWARE_CRAFT},
      f"got {sorted(prim_code)}")

# C4 — specialist wins the craft bonus; a proxy earns nothing
prim_code_raw = S.CRAFT_PRIMARY_DOMAINS["code"]
b_hunt = S.craft_domain_bonus(P[CODE_PERSONA]["domain"], prim_code_raw, task_fit=0.9)
# a representative non-craft, non-engineering persona
proxy = next((s for s in ("clear-atomic-habits", "attwood-passion-test") if s in P), None)
b_proxy = S.craft_domain_bonus(P[proxy]["domain"], prim_code_raw, task_fit=0.9) if proxy else 0.0
check("C4a: hunt-thomas earns a CODE craft bonus (> 0)", b_hunt > 0, f"bonus={b_hunt}")
check("C4b: a non-craft proxy earns 0.0 CODE craft bonus", b_proxy == 0.0, f"bonus={b_proxy}")

# C5 — inertness: no non-software-craft persona earns the CODE bonus
false_pos = [s for s in P
             if SOFTWARE_CRAFT not in dom(s)
             and S.craft_domain_bonus(P[s]["domain"], prim_code_raw, 0.9) > 0]
check("C5: no non-software-craft persona earns the CODE craft bonus (inertness)",
      not false_pos, f"false positives: {false_pos}")
sc = [s for s in P if SOFTWARE_CRAFT in dom(s)]
check("C5b: exactly one software-craft persona in the library", sc == [CODE_PERSONA],
      f"got {sc}")

# ─────────────────────────────── IMAGE slot ───────────────────────────────────
print("--- IMAGE slot (surface/tag only) ---")
prim_design = S.CRAFT_PRIMARY_DOMAINS["design"]
check("I0: visual-communication is a design craft-primary",
      "visual-communication" in {norm(t) for t in prim_design})
if IMAGE_PRIMARY in P:
    b_bud = S.craft_domain_bonus(P[IMAGE_PRIMARY]["domain"], prim_design, 0.9)
    check("I1: budelmann earns the design/image craft bonus (> 0)", b_bud > 0, f"bonus={b_bud}")
if IMAGE_UNION in P:
    b_op = S.craft_domain_bonus(P[IMAGE_UNION]["domain"], prim_design, 0.9)
    check("I2: opara-color-works earns the design/image craft bonus (> 0)", b_op > 0, f"bonus={b_op}")
if DESIGN_INCUMBENT in P:
    b_ro = S.craft_domain_bonus(P[DESIGN_INCUMBENT]["domain"], prim_design, 0.9)
    check("I3: rohde (incumbent design specialist) NOT displaced — still earns a bonus (> 0)",
          b_ro > 0, f"bonus={b_ro}")

# ─────────────────────────────── SET triad ────────────────────────────────────
print("--- SET triad (N38) ---")
m = json.loads(MANIFEST.read_text(encoding="utf-8"))
bp_dirs = sum(1 for p in (SK22 / "personas").iterdir() if p.is_dir())
cat_keys = len(P)
triad = {
    "blueprint_dirs": bp_dirs,
    "categories_keys": cat_keys,
    "manifest.persona_count": int(m.get("persona_count", -1)),
    "manifest.canonical_persona_count": int(m.get("canonical_persona_count", -1)),
}
check("T1: N38 count triad agrees at 83", set(triad.values()) == {83}, f"{triad}")

# ─────────────────────────── Mirror invariant ─────────────────────────────────
print("--- Mirror invariant (build-workforce dept_to_domains) ---")


def extract_all(path, name):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == name:
                    out.append(ast.literal_eval(node.value))
    return out


builds = extract_all(BUILDER, "dept_to_domains")
check("M1a: build-workforce dept_to_domains copies are byte-identical (lockstep)",
      len(builds) >= 1 and all(b == builds[0] for b in builds), f"copies={len(builds)}")
if builds:
    eng_build = {norm(t) for t in builds[0].get("engineering", [])}
    check("M1b: build-workforce engineering carries software-craft (mirror T3 VOCAB)",
          SOFTWARE_CRAFT in eng_build, f"got {sorted(eng_build)}")

print("=" * 70)
print(f"RESULTS: {PASS} passed, {FAIL} failed")
print("=" * 70)
sys.exit(0 if FAIL == 0 else 1)
