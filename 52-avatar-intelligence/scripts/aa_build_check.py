#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""aa_build_check.py — fail-closed deterministic content prover for one
Avatar-Alchemist BRAND run (Skill 52). Loads AA-PIPELINE-MANIFEST.json and
enforces every runtime invariant of the 40-generator pipeline against the run's
artifacts + ledger.

Gates (all offline Python; a single violation is fail-closed sys.exit(2)):
  G-STAGE       generation-completeness: every brand stage produced a non-empty
                artifact WITH a foreman receipt.                 -> AF-AV-STAGE-MISSING
  G-FLOOR       stripped-word floors (>=3000 avatar-q/blended-tone, >=1500 each
                awareness pt1, >=5000 booking bot).              -> AF-AV-FLOOR
  G-COUNT       exactly 39 image prompts / top-39 (3x13); headline doc 12+12+12;
                each ad set >=10 ads.        -> AF-AV-COUNT-39 / -COUNT-HEADLINE / -ADCOUNT
  G-IMG-BAND    image-prompt artifacts inside the STRIPPED-char band [5000,19000];
                no repeated artist token.       -> AF-AV-IMG-BAND / AF-AV-UNIQUE-ARTIST
  G-ADSET-CAT   each of 13 ad sets carries its restored R4 category signature (no
                'category 2' drift).                             -> AF-AV-ADSET-CAT
  G-BOTDOC      bot docs carry H1 '# ... Section' + XML labels + {{contact.*}}
                merge tags.                                      -> AF-AV-BOTDOC
  G-HERO-12     hero page carries the 12 Hero Landing Page System sections. -> AF-AV-HERO-12
  G-PLACEHOLDER no unresolved {{...}} / $('...') tokens leaked into an artifact
                (whitelist: {{contact.*}} in bot docs).          -> AF-AV-PLACEHOLDER
  G-NOANTHROPIC no resolved model id matches /anthropic|claude/i. -> AF-AV-NOANTHROPIC

Self-reported counts are IGNORED — every measurement is on markdown/whitespace-
STRIPPED text so padding can't fake a floor. stdlib only.
Exit 0 = pass, 2 = violation, 3 = usage/IO error.
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _manifest_path() -> Path:
    return Path(__file__).resolve().parent.parent / "AA-PIPELINE-MANIFEST.json"


# ---------------------------------------------------------------------------
# stripped-length teeth (clone of the presentations build_deck.py pattern):
# measure NON-markdown, NON-whitespace content so padding never satisfies a floor.
# ---------------------------------------------------------------------------
_MD = re.compile(r"(^\s{0,3}[#>\-\*\+]+\s?|[`*_~\[\]\(\)>#]|^\s{0,3}\d{1,3}[\.\)]\s)", re.MULTILINE)


def _strip(text: str) -> str:
    t = re.sub(r"<!--.*?-->", " ", str(text), flags=re.DOTALL)   # drop comments/headers
    t = _MD.sub(" ", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def _words(text: str) -> int:
    s = _strip(text)
    return len(s.split()) if s else 0


def _chars(text: str) -> int:
    return len(_strip(text))


def _numbered(text: str) -> List[int]:
    """Distinct integers used as list markers at line start (1. / 1) )."""
    nums = []
    for m in re.finditer(r"(?m)^\s{0,3}(\d{1,3})[\.\)]\s", str(text)):
        nums.append(int(m.group(1)))
    return sorted(set(nums))


def _tokens_left(text: str) -> List[str]:
    """Unresolved template/Make.com tokens (excluding {{contact.*}} merge tags)."""
    out = []
    for m in re.finditer(r"\{\{([^}]*)\}\}", str(text)):
        inner = m.group(1).strip()
        if inner.startswith("contact."):
            continue
        out.append(m.group(0))
    for m in re.finditer(r"\$\(([^)]*)\)", str(text)):
        out.append(m.group(0))
    # Make.com module refs / bracketed template leftovers
    for m in re.finditer(r"\{\{\d+\.\w+", str(text)):
        out.append(m.group(0))
    return out


# ---------------------------------------------------------------------------
# core verify: (manifest, state) -> (violations, notes)
#   state = {"artifacts": {sid: text}, "models": {sid: model_id}, "receipts": [sid...]}
# ---------------------------------------------------------------------------
def verify(manifest: Dict[str, Any], state: Dict[str, Any]) -> Tuple[List[Tuple[str, str]], List[str]]:
    violations: List[Tuple[str, str]] = []
    notes: List[str] = []

    def fail(code: str, msg: str) -> None:
        violations.append((code, msg))

    stages = {s["stage_id"]: s for s in manifest.get("stages", [])}
    artifacts: Dict[str, str] = state.get("artifacts", {})
    models: Dict[str, str] = state.get("models", {})
    receipts = set(state.get("receipts", []))
    band = manifest.get("image_prompt_band", {})
    band_min = int(band.get("min_chars", 5000))
    band_max = int(band.get("max_chars", 19000))

    # === G-STAGE: generation-completeness =================================
    for sid, spec in stages.items():
        txt = artifacts.get(sid, "")
        if not str(txt).strip():
            fail("AF-AV-STAGE-MISSING", f"stage '{sid}' produced no non-empty artifact")
            continue
        if sid not in receipts:
            fail("AF-AV-STAGE-MISSING", f"stage '{sid}' has no foreman receipt (author self-attestation is not accepted)")

    # === per-stage floors / counts / bands / structure ====================
    for sid, spec in stages.items():
        txt = str(artifacts.get(sid, ""))
        if not txt.strip():
            continue  # already flagged missing
        floors = spec.get("floors", {})

        # G-FLOOR (stripped word floor)
        wf = floors.get("word_floor")
        if wf:
            wc = _words(txt)
            if wc < int(wf):
                fail("AF-AV-FLOOR", f"stage '{sid}': {wc} stripped words < floor {wf}")

        # G-COUNT-39 (image prompts / top-39)
        if floors.get("count_39"):
            nums = _numbered(txt)
            if nums != list(range(1, 40)):
                fail("AF-AV-COUNT-39",
                     f"stage '{sid}': expected exactly 39 numbered items (1..39, i.e. 3x13); "
                     f"found {len(nums)} distinct markers")

        # G-COUNT-HEADLINE (12 + 12 + 12)
        hc = floors.get("headline_counts")
        if hc:
            got = _headline_counts(txt)
            if got != hc:
                fail("AF-AV-COUNT-HEADLINE",
                     f"stage '{sid}': headline/short/long counts {got} != required {hc} (12+12+12)")

        # G-ADCOUNT (>=10 ads per set)
        ac = floors.get("ad_count")
        if ac:
            nums = _numbered(txt)
            if len(nums) < int(ac):
                fail("AF-AV-ADCOUNT", f"stage '{sid}': {len(nums)} numbered ads < required {ac}")

        # G-ADSET-CAT (restored R4 category signature present)
        cat = floors.get("adset_category")
        if cat:
            if not re.search(re.escape(cat), txt, re.IGNORECASE):
                fail("AF-AV-ADSET-CAT",
                     f"stage '{sid}': artifact does not name its restored category '{cat}' "
                     f"(the 'category 2' drift repair did not hold)")

        # G-IMG-BAND (stripped-char band) + unique artist
        cb = floors.get("char_band")
        if cb:
            n = _chars(txt)
            lo, hi = int(cb[0]), int(cb[1])
            if not (lo <= n <= hi):
                fail("AF-AV-IMG-BAND",
                     f"stage '{sid}': {n} stripped chars outside image-prompt band [{lo},{hi}]")
        if floors.get("unique_artist"):
            dups = _dup_artists(txt)
            if dups:
                fail("AF-AV-UNIQUE-ARTIST",
                     f"stage '{sid}': repeated artist/style token(s) {sorted(dups)} "
                     f"(each image prompt must name a UNIQUE artist/photographer/producer)")

        # G-BOTDOC
        if floors.get("botdoc"):
            for code, msg in _botdoc_defects(txt):
                fail(code, f"stage '{sid}': {msg}")

        # G-HERO-12
        hs = floors.get("hero_sections")
        if hs:
            sections = len(re.findall(r"(?mi)^#{1,4}\s*.*section\b", txt)) or len(re.findall(r"(?mi)^#{2,3}\s", txt))
            if sections < int(hs):
                fail("AF-AV-HERO-12",
                     f"stage '{sid}': found {sections} sections, under the {hs}-section Hero Landing Page System")

        # G-PLACEHOLDER (whitelist {{contact.*}} everywhere; other tokens fail)
        leaked = _tokens_left(txt)
        if leaked:
            fail("AF-AV-PLACEHOLDER",
                 f"stage '{sid}': {len(leaked)} unresolved token(s) leaked, e.g. {leaked[:3]}")

    # === G-NOANTHROPIC ====================================================
    for sid, mid in models.items():
        if re.search(r"anthropic|claude", str(mid), re.IGNORECASE):
            fail("AF-AV-NOANTHROPIC",
                 f"stage '{sid}': resolved model id {mid!r} matches /anthropic|claude/i (client-path ban)")
    for k in state.get("env_names", []):
        if re.search(r"operator|blackceo|anthropic", str(k), re.IGNORECASE):
            fail("AF-AV-NOANTHROPIC", f"operator/anthropic credential name {k!r} present in run env")

    return violations, notes


def _headline_counts(text: str) -> List[int]:
    """Count numbered items under headline / short-form / long-form headers."""
    sections = {"headline": 0, "short": 0, "long": 0}
    cur = None
    for line in str(text).splitlines():
        h = re.match(r"(?i)^#{1,6}\s*(.*)$", line.strip())
        if h:
            label = h.group(1).lower()
            if "headline" in label:
                cur = "headline"
            elif "short" in label:
                cur = "short"
            elif "long" in label:
                cur = "long"
            else:
                cur = None
            continue
        if cur and re.match(r"^\s{0,3}\d{1,3}[\.\)]\s", line):
            sections[cur] += 1
    return [sections["headline"], sections["short"], sections["long"]]


def _dup_artists(text: str) -> set:
    seen: Dict[str, int] = {}
    for m in re.finditer(r"(?i)(?:in the style of|by|photographer|artist|director|producer)[:\s]+([A-Z][A-Za-z0-9 .'-]{2,40})", str(text)):
        name = re.sub(r"\s+", " ", m.group(1)).strip().lower()
        seen[name] = seen.get(name, 0) + 1
    return {k for k, v in seen.items() if v > 1}


def _botdoc_defects(text: str) -> List[Tuple[str, str]]:
    d = []
    if not re.search(r"(?mi)^#\s+.*section\b", str(text)):
        d.append(("AF-AV-BOTDOC", "missing an H1 '# ... Section' header"))
    if not re.search(r"<\w+>.*?</\w+>", str(text), re.DOTALL):
        d.append(("AF-AV-BOTDOC", "missing XML-style labels (e.g. <intro_message>...</intro_message>)"))
    if not re.search(r"\{\{contact\.\w+\}\}", str(text)):
        d.append(("AF-AV-BOTDOC", "missing a {{contact.*}} merge tag (the one whitelisted placeholder class)"))
    return d


# ---------------------------------------------------------------------------
# run-dir loader
# ---------------------------------------------------------------------------
def load_run(run_dir: str) -> Dict[str, Any]:
    root = Path(run_dir)
    art_dir = root / "artifacts"
    artifacts, receipts, models = {}, [], {}
    if art_dir.is_dir():
        for p in art_dir.glob("*.md"):
            artifacts[p.stem] = p.read_text(encoding="utf-8", errors="replace")
    rec_dir = root / "receipts"
    if rec_dir.is_dir():
        for p in rec_dir.glob("G-STAGE-*.json"):
            receipts.append(p.stem.replace("G-STAGE-", ""))
    ledger = root / "RUN-LEDGER.json"
    if ledger.is_file():
        data = json.loads(ledger.read_text(encoding="utf-8", errors="replace"))
        for sid, row in (data.get("stages") or {}).items():
            if row.get("model"):
                models[sid] = row["model"]
            if row.get("receipt"):
                receipts.append(sid)
    return {"artifacts": artifacts, "receipts": receipts, "models": models}


# ---------------------------------------------------------------------------
# self-test: synth a fully-compliant run, then single-defect mutations.
# ---------------------------------------------------------------------------
def _lorem(n: int) -> str:
    base = ("the avatar craves clarity purpose and momentum while facing doubt fear "
            "and the quiet weight of unmet ambition every day ").split()
    return " ".join(base[i % len(base)] for i in range(n))


def _synth(manifest: Dict[str, Any]) -> Dict[str, Any]:
    artifacts, models, receipts = {}, {}, []
    for s in manifest["stages"]:
        sid = s["stage_id"]
        f = s.get("floors", {})
        parts = [f"# {sid} artifact\n"]
        if f.get("word_floor"):
            parts.append(_lorem(int(f["word_floor"]) + 60))
        if f.get("adset_category"):
            parts.append(f"\n## Ad Set for {f['adset_category']} — restored category\n")
            parts += [f"{i}. Ad hook variant number {i} for this set in harmony.\n" for i in range(1, 11)]
        if f.get("headline_counts"):
            parts.append("\n## Headlines\n")
            parts += [f"{i}. Headline {i}\n" for i in range(1, 13)]
            parts.append("\n## Short-Form Primary Text\n")
            parts += [f"{i}. Short body {i}\n" for i in range(1, 13)]
            parts.append("\n## Long-Form Primary Text\n")
            parts += [f"{i}. Long body number {i} carries the full narrative.\n" for i in range(1, 13)]
        if f.get("count_39"):
            for i in range(1, 40):
                if f.get("char_band"):
                    parts.append(f"{i}. Ad words here then a Midjourney prompt in the style of Artist{i}: "
                                 f"a disruptive scene, cinematic lighting, rule of thirds, --ar 1:1 --r 10 --c 25 --s 750. "
                                 f"{_lorem(12)}\n")
                else:
                    parts.append(f"{i}. Ad Set {((i-1)//3)+1} selection {i} with suggested image information.\n")
        elif f.get("char_band"):
            parts.append("\n## Landing Page Image Prompts\n")
            for i in range(1, 13):
                parts.append(f"{i}. Section {i} prompt in the style of Muralist{i}: African American subject, "
                             f"disruptive composition, ::4 facial expression, ::3 clothing, rule of thirds placement, "
                             f"cinematic key lighting, 35mm lens, unique environment never repeated. {_lorem(90)}\n")
        if f.get("botdoc"):
            parts.append("\n# Intro Message Section\n<intro_message>\nHello {{contact.first_name}}, welcome.\n</intro_message>\n"
                         "\n# Role Section\n<role>\nYou are the booking assistant.\n</role>\n")
        if f.get("hero_sections"):
            for i in range(1, 13):
                parts.append(f"\n## Section {i}\nHero section {i} copy. {_lorem(8)}\n")
        artifacts[sid] = "".join(parts)
        models[sid] = "ollama-cloud/qwen3-235b" if s["tier"] == "A" else "openrouter/deepseek-chat"
        receipts.append(sid)
    return {"artifacts": artifacts, "models": models, "receipts": receipts, "env_names": ["OLLAMA_HOST", "OPENROUTER_API_KEY"]}


def _violation_cases(manifest):
    def missing(st): st["artifacts"]["16-brand-bio"] = ""
    def no_receipt(st): st["receipts"] = [r for r in st["receipts"] if r != "19-booking-bot"]
    def short_floor(st): st["artifacts"]["09-problem-aware"] = "# short\n" + _lorem(200)
    def bad_39(st):
        # drop item 39 from the image-prompt doc
        st["artifacts"]["36-image-prompts-39"] = "\n".join(
            l for l in st["artifacts"]["36-image-prompts-39"].splitlines() if not l.startswith("39."))
    def bad_headline(st):
        st["artifacts"]["37-fb-headline-copy"] = st["artifacts"]["37-fb-headline-copy"].replace("12. Headline 12\n", "")
    def drift(st):
        st["artifacts"]["28-ad-set-7"] = st["artifacts"]["28-ad-set-7"].replace("category 5", "category 2")
    def img_band(st):
        st["artifacts"]["40-landing-image-prompts"] = "# tiny\n1. one prompt only\n"
    def dup_artist(st):
        st["artifacts"]["36-image-prompts-39"] = st["artifacts"]["36-image-prompts-39"].replace(
            "in the style of Artist2:", "in the style of Artist1:")
    def botdoc(st):
        st["artifacts"]["19-booking-bot"] = st["artifacts"]["19-booking-bot"].replace("{{contact.first_name}}", "there")
    def hero(st):
        lines = st["artifacts"]["39-hero-page"].splitlines()
        st["artifacts"]["39-hero-page"] = "\n".join(l for l in lines if not l.startswith("## Section 1"))[:200] + "\n" + _lorem(50)
    def placeholder(st):
        st["artifacts"]["16-brand-bio"] += "\n\nUnresolved {{intake.offer_name}} leaked here.\n"
    def anthropic(st):
        st["models"]["39-hero-page"] = "anthropic/claude-sonnet-4"
    return [
        ("stage_missing_artifact", "AF-AV-STAGE-MISSING", missing),
        ("stage_missing_receipt", "AF-AV-STAGE-MISSING", no_receipt),
        ("word_floor_under", "AF-AV-FLOOR", short_floor),
        ("count_39_short", "AF-AV-COUNT-39", bad_39),
        ("headline_not_12", "AF-AV-COUNT-HEADLINE", bad_headline),
        ("adset_category_drift", "AF-AV-ADSET-CAT", drift),
        ("image_band_too_small", "AF-AV-IMG-BAND", img_band),
        ("duplicate_artist", "AF-AV-UNIQUE-ARTIST", dup_artist),
        ("botdoc_missing_mergetag", "AF-AV-BOTDOC", botdoc),
        ("hero_missing_sections", "AF-AV-HERO-12", hero),
        ("placeholder_leak", "AF-AV-PLACEHOLDER", placeholder),
        ("anthropic_model_id", "AF-AV-NOANTHROPIC", anthropic),
    ]


def run_self_test(manifest) -> int:
    ok = True
    v, _ = verify(manifest, _synth(manifest))
    if v:
        ok = False
        print(f"SELF-TEST FAIL: valid run produced {len(v)} violation(s): {v[:6]}")
    else:
        print("SELF-TEST ok: valid full-run fixture PASSES (0 violations).")
    for name, expected, mut in _violation_cases(manifest):
        st = _synth(manifest)
        mut(st)
        vio, _ = verify(manifest, st)
        codes = {c for c, _ in vio}
        if not vio:
            ok = False; print(f"SELF-TEST FAIL: '{name}' produced NO violations (expected {expected}).")
        elif expected not in codes:
            ok = False; print(f"SELF-TEST FAIL: '{name}' -> {sorted(codes)} (expected {expected}).")
        else:
            print(f"SELF-TEST ok: '{name}' -> nonzero, carries {expected}.")
    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def _report(violations, notes) -> None:
    for n in notes:
        print(f"NOTE: {n}")
    if not violations:
        print("PASS: run clears every Avatar-Alchemist content invariant.")
        return
    print(f"FAIL: {len(violations)} content violation(s) — delivery refused.")
    for code, msg in violations:
        print(f"  VIOLATION [{code}] {msg}")


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Fail-closed Avatar-Alchemist content prover (40-generator pipeline).")
    ap.add_argument("--run", help="path to a run dir (artifacts/, receipts/, RUN-LEDGER.json)")
    ap.add_argument("--manifest", help="path to AA-PIPELINE-MANIFEST.json (default: ../AA-PIPELINE-MANIFEST.json)")
    ap.add_argument("--self-test", action="store_true", help="synth a valid run (PASS) + single-defect mutations (FAIL)")
    args = ap.parse_args(argv)
    try:
        manifest = json.loads(Path(args.manifest or _manifest_path()).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"USAGE/IO ERROR: cannot load manifest: {exc}")
        return 3
    if args.self_test:
        return run_self_test(manifest)
    if not args.run:
        print("USAGE ERROR: pass --run <run-dir> (or --self-test).")
        return 3
    try:
        state = load_run(args.run)
    except Exception as exc:  # noqa: BLE001
        print(f"USAGE/IO ERROR: cannot load run: {exc}")
        return 3
    violations, notes = verify(manifest, state)
    _report(violations, notes)
    return 0 if not violations else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
