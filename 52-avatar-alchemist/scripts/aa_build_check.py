#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""aa_build_check.py — fail-closed deterministic content prover for one
Avatar-Alchemist BRAND run (Skill 52). Loads AA-PIPELINE-MANIFEST.json and
enforces every runtime invariant of the 40-generator pipeline against the run's
artifacts + ledger.

Gates (all offline Python; a single violation is fail-closed sys.exit(2)):
  G-STAGE       generation-completeness: every brand stage produced a non-empty
                artifact WITH a foreman receipt.                 -> AF-AV-STAGE-MISSING
  G-FLOOR       stripped-word floors (per-stage minimums in the manifest, e.g.
                >=1300 avatar-q, >=850 blended-tone, >=550 each awareness,
                >=1600 booking bot). Padding cannot fake it (measured on
                whitespace/markdown-stripped text).              -> AF-AV-FLOOR
  G-COUNT       exactly 39 image prompts / top-39 (3x13); headline doc 12+12+12;
                each ad set >=10 ads.        -> AF-AV-COUNT-39 / -COUNT-HEADLINE / -ADCOUNT
  G-IMG-BAND    image-prompt artifacts inside the STRIPPED-char band [5000,19000];
                no repeated artist token.       -> AF-AV-IMG-BAND / AF-AV-UNIQUE-ARTIST
  G-ADSET-CAT   each of 13 ad sets carries its restored R4 category signature (no
                'category 2' drift).                             -> AF-AV-ADSET-CAT
  G-BOTDOC      bot docs carry H1 '# ... Section' + XML labels + {{contact.*}}
                merge tags.                                      -> AF-AV-BOTDOC
  G-HERO-12     hero page carries the 12 EXACTLY-NAMED, IN-ORDER "Trevor Otts
                Hero Page System" sections, each inside its char/word band (a
                floor-only heading count with an any-heading fallback is NOT
                enough).                          -> AF-AV-HERO-12 / AF-AV-HERO-BAND
  G-RELEVANCE   deterministic section-header/body relevance: the 13 named
                Q1-30 avatar questions and the "Five Core Values"/"Five
                Personality Traits" marketing sections must actually answer
                their header (keyword classes / >=5 distinctly named items
                present), not generic on-topic prose that ignores the ask.
                                                            -> AF-AV-SECTION-RELEVANCE
  G-PLACEHOLDER no unresolved {{...}} / $('...') tokens leaked into an artifact
                (whitelist: {{contact.*}} in bot docs).          -> AF-AV-PLACEHOLDER
  G-NOANTHROPIC EVERY manifest stage must carry a resolved model id (a stage
                simply absent from the models map fails closed, it cannot pass
                by omission); every resolved id fails /anthropic|claude/i.
                                                                   -> AF-AV-NOANTHROPIC

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
# G-HERO-12: the 12 EXACTLY-NAMED, IN-ORDER "Trevor Otts Hero Page System"
# sections (prompts/39-hero-page/methodology.md), each inside a char/word band
# derived from that spec's own suggested/required counts. Detected via
# "## Section N: <name>" headers (the format build_golden.py emits).
# ---------------------------------------------------------------------------
HERO_SECTION_NAMES = [
    "The Big Bold Claim",
    "The Big Bold Pain 1",
    "The Big Bold Pain 2",
    "The Big Bold Pain 3",
    "The Big Bold Why",
    "The Big Bold Who",
    "The Big Bold What",
    "The Big Bold Benefit 1",
    "The Big Bold Benefit 2",
    "The Big Bold Benefit 3",
    "The Big How To",
    "The Big Bold Heartfelt Message",
]
# (unit, lo, hi) per section, index-aligned with HERO_SECTION_NAMES.
#
# Sections 1-4 are the ONE HARD char band the methodology states as
# non-negotiable ("You MUST OBEY THES CHARACTER COUNT INSTRUCTIONS ... Cannot
# be more than 225 characters ... your output for each of the 4 section cannot
# be less than 180 characters ... You are forbidden from exceeding my word
# count"). So sections 1-4 = EXACTLY [180, 225] stripped chars — the true
# spec, NOT a looser substitute. (The prior [60,230]/[150,230] tolerance
# rubber-stamped the very floor-violation an independent re-grade caught.)
#
# Sections 5-10 and 12 carry only "SUGGESTED WORD COUNT" in the spec, so they
# use word bands with a modest tolerance around the suggestion. Section 11 has
# its OWN hard per-step char rule ("in steps 1-6 you are forbidden from
# exceeding 116 characters ... a minimum of 89 characters ... Step 7 ...
# forbidden from exceeding 170 characters"), enforced specially below (the
# ("steps", ...) unit), not as a single whole-section band.
HERO_BANDS: List[Tuple[str, int, int]] = [
    ("chars", 180, 225),   # 1 Big Bold Claim              (spec HARD: 180-225 chars)
    ("chars", 180, 225),   # 2 Big Bold Pain 1             (spec HARD: 180-225 chars)
    ("chars", 180, 225),   # 3 Big Bold Pain 2             (spec HARD: 180-225 chars)
    ("chars", 180, 225),   # 4 Big Bold Pain 3             (spec HARD: 180-225 chars)
    ("words", 8, 40),      # 5 Big Bold Why                (spec suggested: <=30 words)
    ("words", 12, 48),     # 6 Big Bold Who                (spec suggested: <=30 words, 3-6 personas)
    ("words", 55, 130),    # 7 Big Bold What               (spec suggested: 70-120 words, >=5 bullets)
    ("words", 8, 40),      # 8 Big Bold Benefit 1          (spec suggested: <=30 words)
    ("words", 8, 40),      # 9 Big Bold Benefit 2          (spec suggested: <=30 words)
    ("words", 8, 40),      # 10 Big Bold Benefit 3         (spec suggested: <=30 words)
    ("steps", 89, 116),    # 11 Big How To                 (spec HARD per step: 89-116 chars; step7 <=170)
    ("words", 150, 400),   # 12 Big Bold Heartfelt Message (spec: 6 parts, one letter)
]
HERO_STEP7_MAX_CHARS = 170  # spec HARD: "in Step 7 ... forbidden from exceeding 170 characters"

_HERO_HEADER_RE = re.compile(r"(?mi)^#{1,4}\s*Section\s+(\d{1,2})\s*:\s*(.+?)\s*$")
_HERO_STEP_RE = re.compile(r"(?m)^\s{0,3}(\d{1,2})[\.\)]\s+(.*)$")


def _hero_step_defects(section_num: int, name: str, body: str) -> List[Tuple[str, str]]:
    """Section 11: 5-10 numbered steps; steps 1..n-1 each 89-116 stripped chars;
    the final step <=170 chars (spec's hard per-step char rule)."""
    out: List[Tuple[str, str]] = []
    steps = _HERO_STEP_RE.findall(body)
    n = len(steps)
    if not (5 <= n <= 10):
        out.append(("AF-AV-HERO-BAND",
                     f"section {section_num} ({name}): {n} numbered steps, spec requires 5-10"))
        return out
    for i, (_num, step_text) in enumerate(steps, 1):
        c = _chars(step_text)
        if i < n:
            if not (89 <= c <= 116):
                out.append(("AF-AV-HERO-BAND",
                             f"section {section_num} ({name}) step {i}: {c} stripped chars outside the "
                             f"hard [89,116] per-step band"))
        else:  # final (motivational) step
            if c > HERO_STEP7_MAX_CHARS:
                out.append(("AF-AV-HERO-BAND",
                             f"section {section_num} ({name}) final step: {c} stripped chars exceeds the "
                             f"{HERO_STEP7_MAX_CHARS}-char cap"))
    return out


def _hero_sections_defects(text: str) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    matches = list(_HERO_HEADER_RE.finditer(str(text)))
    if len(matches) != 12:
        out.append(("AF-AV-HERO-12",
                     f"found {len(matches)} 'Section N: <name>' headers, need EXACTLY 12 "
                     f"(the Trevor Otts Hero Page System) — no any-heading fallback"))
        return out
    for idx, m in enumerate(matches):
        num = int(m.group(1))
        name = re.sub(r"\s+", " ", m.group(2)).strip().rstrip(".:")
        expected_num = idx + 1
        expected_name = HERO_SECTION_NAMES[idx]
        if num != expected_num:
            out.append(("AF-AV-HERO-12",
                         f"section at position {idx + 1} is numbered {num} (expected {expected_num}) "
                         f"— out of order"))
        if name.lower() != expected_name.lower():
            out.append(("AF-AV-HERO-12",
                         f"section {expected_num} is named {name!r} (expected exactly "
                         f"{expected_name!r} — 'never change the name of my page sections')"))
        body_start = m.end()
        body_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = str(text)[body_start:body_end]
        unit, lo, hi = HERO_BANDS[idx]
        if unit == "steps":
            out.extend(_hero_step_defects(expected_num, expected_name, body))
            continue
        n = _chars(body) if unit == "chars" else _words(body)
        if not (lo <= n <= hi):
            out.append(("AF-AV-HERO-BAND",
                         f"section {expected_num} ({expected_name}): {n} {unit} outside band "
                         f"[{lo},{hi}] (measured on stripped body text)"))
    return out


# ---------------------------------------------------------------------------
# G-RELEVANCE (AF-AV-SECTION-RELEVANCE): deterministic section-header/body
# relevance for the Avatar Q1-30 doc (13 named questions) and the marketing
# "Five Core Values" / "Five Personality Traits" sections baked into every
# awareness stage. A hollow body that ignores its header (generic on-topic
# prose standing in for a factual answer) fails closed here even though it
# would clear every other structural gate.
# ---------------------------------------------------------------------------
_Q_HEADER_RE = re.compile(r"(?mi)^#{1,4}\s*Question\s+(\d{1,2})\s*:\s*(.+?)\s*$")


def _kw_hit(body: str, words: List[str]) -> bool:
    low = body.lower()
    return any(w.lower() in low for w in words)


_AVATAR_Q_CHECKS: Dict[int, Any] = {
    1: lambda b: _kw_hit(b, ["archetype"]),
    2: lambda b: (_kw_hit(b, ["married", "single", "divorced", "widowed", "partnered",
                              "engaged", "in a relationship", "unmarried"])
                  and _kw_hit(b, ["child", "kids", "children", "spouse", "husband", "wife",
                                  "partner", "family"])),
    3: lambda b: (_kw_hit(b, ["urban", "suburban", "rural", "metro", "city", "state",
                              "country", "united states", "u.s.", "remote"])
                  and _kw_hit(b, ["lifestyle", "commute", "household", "home life", "routine"])),
    4: lambda b: (_kw_hit(b, ["founder", "owner", "coach", "consultant", "practice",
                              "business", "career", "self-employed", "job"])
                  and _kw_hit(b, ["income", "revenue", "earns", "salary", "$", "annual"])),
    5: lambda b: _kw_hit(b, ["degree", "bachelor", "master", "mba", "certification",
                             "credential", "certified", "college", "university"]),
    6: lambda b: _kw_hit(b, ['"', "“", "‘", "quote"]),
    7: lambda b: (_kw_hit(b, ["book"]) and _kw_hit(b, ["magazine"]) and _kw_hit(b, ["blog"])),
    8: lambda b: _kw_hit(b, ["conference", "summit", "community", "mastermind",
                             "association", "network"]),
    9: lambda b: len(_numbered(b)) >= 10,
    10: lambda b: len(_numbered(b)) >= 10,
    11: lambda b: (_kw_hit(b, ["fear", "afraid", "worried", "anxious", "scared", "dread"])
                   and len(_numbered(b)) >= 3),
    12: lambda b: (_kw_hit(b, ["desire", "want", "crave", "long for", "yearns", "wishes"])
                   and len(_numbered(b)) >= 3),
    13: lambda b: (_kw_hit(b, ["objection", "hesitat", "skeptic", "doubt", "worried that"])
                   and len(_numbered(b)) >= 3),
}


def _avatar_relevance_defects(text: str) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    matches = list(_Q_HEADER_RE.finditer(str(text)))
    by_num = {int(m.group(1)): m for m in matches}
    for n, check in _AVATAR_Q_CHECKS.items():
        m = by_num.get(n)
        if m is None:
            out.append(("AF-AV-SECTION-RELEVANCE", f"Question {n}: header not found"))
            continue
        start = m.end()
        # body runs to the next "### Question" header or "## Synthesis"
        rest = str(text)[start:]
        nxt = re.search(r"(?mi)^#{1,4}\s*(Question\s+\d|Synthesis)\b", rest)
        body = rest[: nxt.start()] if nxt else rest
        if not check(body):
            out.append(("AF-AV-SECTION-RELEVANCE",
                         f"Question {n} ({m.group(2).strip()}): body does not answer its own "
                         f"header (generic prose ignoring the specific ask)"))
    return out


_FIVE_LIST_RE = re.compile(r"(?mi)^#{1,4}\s*.*\bFive\s+(Core\s+Values|Personality\s+Traits)\b.*$")


def _five_list_defects(text: str) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    for m in _FIVE_LIST_RE.finditer(str(text)):
        label = m.group(1)
        start = m.end()
        rest = str(text)[start:]
        nxt = re.search(r"(?m)^#{1,4}\s", rest)
        body = rest[: nxt.start()] if nxt else rest
        n = len(_numbered(body))
        if n < 5:
            out.append(("AF-AV-SECTION-RELEVANCE",
                         f"'Five {label}' section names only {n} distinct item(s), needs >=5 "
                         f"named entries (not a paragraph of generic prose)"))
    return out


# ---------------------------------------------------------------------------
# core verify: (manifest, state) -> (violations, notes)
#   state = {"artifacts": {sid: text}, "models": {sid: model_id}, "receipts": [sid...]}
# ---------------------------------------------------------------------------
def verify(manifest: Dict[str, Any], state: Dict[str, Any],
           apply_repairs: bool | None = None) -> Tuple[List[Tuple[str, str]], List[str]]:
    violations: List[Tuple[str, str]] = []
    notes: List[str] = []

    def fail(code: str, msg: str) -> None:
        violations.append((code, msg))

    # Repairs R1-R6 are OFF BY DEFAULT (faithful to the live workflow); they are
    # applied only when the run was started with --apply-repairs. The only content
    # invariant tied to a repair is G-ADSET-CAT (R4). R7 (the Anthropic ban) is
    # ALWAYS enforced below (G-NOANTHROPIC) and is never gated.
    if apply_repairs is None:
        apply_repairs = bool(state.get("apply_repairs", False))
    notes.append(f"repairs mode: {'ON (--apply-repairs)' if apply_repairs else 'OFF (faithful-to-live default)'}")

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

        # G-ADSET-CAT (restored R4 category signature present) — REPAIR-GATED:
        # enforced ONLY under --apply-repairs. In the default faithful-to-live run
        # the source froze every ad set on 'category 2', so this is not enforced.
        cat = floors.get("adset_category")
        if cat and apply_repairs:
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

        # G-HERO-12 (12 EXACTLY-NAMED, IN-ORDER sections + per-section char/word band —
        # no floor-only count, no any-heading fallback)
        hs = floors.get("hero_sections")
        if hs:
            for code, msg in _hero_sections_defects(txt):
                fail(code, f"stage '{sid}': {msg}")

        # G-RELEVANCE (AF-AV-SECTION-RELEVANCE): section-header/body relevance
        if floors.get("avatar_relevance"):
            for code, msg in _avatar_relevance_defects(txt):
                fail(code, f"stage '{sid}': {msg}")
        if floors.get("five_list_relevance"):
            for code, msg in _five_list_defects(txt):
                fail(code, f"stage '{sid}': {msg}")

        # G-PLACEHOLDER (whitelist {{contact.*}} everywhere; other tokens fail)
        leaked = _tokens_left(txt)
        if leaked:
            fail("AF-AV-PLACEHOLDER",
                 f"stage '{sid}': {len(leaked)} unresolved token(s) leaked, e.g. {leaked[:3]}")

    # === G-NOANTHROPIC (fail-closed: EVERY manifest stage, not just the ones
    # the caller happened to populate — a stage missing from `models` used to
    # pass by silent omission; it now fails just like G-STAGE does) ==========
    for sid in stages:
        mid = models.get(sid)
        if not mid or not str(mid).strip():
            fail("AF-AV-NOANTHROPIC",
                 f"stage '{sid}': no resolved model id recorded (cannot prove client-path-only "
                 f"by omission — a ledger/receipt lacking a model id fails, it does not pass vacuously)")
            continue
        if re.search(r"anthropic|claude", str(mid), re.IGNORECASE):
            fail("AF-AV-NOANTHROPIC",
                 f"stage '{sid}': resolved model id {mid!r} matches /anthropic|claude/i (client-path ban)")
    # operator/anthropic credential-NAME ban (defense in depth only — the LIVE
    # enforcement of this half is entry.sh's env-credential-name bypass-scan
    # leg, which actually sees the process env; this loop only sees whatever
    # env_names the caller chose to report, so it can never be the sole guard).
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
    apply_repairs = False
    if art_dir.is_dir():
        for p in art_dir.glob("*.md"):
            artifacts[p.stem] = p.read_text(encoding="utf-8", errors="replace")
    rec_dir = root / "receipts"
    if rec_dir.is_dir():
        for p in rec_dir.glob("G-STAGE-*.json"):
            sid = p.stem.replace("G-STAGE-", "")
            receipts.append(sid)
            # G-NOANTHROPIC defense-in-depth: the on-disk receipt already carries
            # a 'model' field written at generation time (build_golden.write_run,
            # the real foreman path) — read it directly rather than relying
            # SOLELY on RUN-LEDGER.json, so a ledger stripped of model ids still
            # gets caught (a stage cannot pass G-NOANTHROPIC purely by which file
            # happens to be missing a field).
            try:
                rec = json.loads(p.read_text(encoding="utf-8", errors="replace"))
                if rec.get("model"):
                    models.setdefault(sid, rec["model"])
            except Exception:  # noqa: BLE001
                pass
    ledger = root / "RUN-LEDGER.json"
    if ledger.is_file():
        data = json.loads(ledger.read_text(encoding="utf-8", errors="replace"))
        apply_repairs = bool(data.get("apply_repairs")
                             or (data.get("mode") or {}).get("apply_repairs"))
        for sid, row in (data.get("stages") or {}).items():
            if row.get("model"):
                models[sid] = row["model"]
            if row.get("receipt"):
                receipts.append(sid)
    return {"artifacts": artifacts, "receipts": receipts, "models": models,
            "apply_repairs": apply_repairs}


# ---------------------------------------------------------------------------
# self-test: synth a fully-compliant run, then single-defect mutations.
# ---------------------------------------------------------------------------
def _lorem(n: int) -> str:
    base = ("the avatar craves clarity purpose and momentum while facing doubt fear "
            "and the quiet weight of unmet ambition every day ").split()
    return " ".join(base[i % len(base)] for i in range(n))


def _fit_band(unit: str, lo: int, hi: int) -> str:
    """Deterministic filler text whose stripped char/word count self-corrects
    into [lo, hi] (used only by the offline self-test fixture; the real golden
    uses hand-authored, header-answering copy — see examples/golden-lumen-rise)."""
    target = (lo + hi) // 2
    if unit == "words":
        body = _lorem(max(1, target))
        while _words(body) < lo:
            body += " " + _lorem(5)
        while _words(body) > hi:
            body = " ".join(body.split()[:-1])
        return body
    body = _lorem(40)
    while _chars(body) < lo:
        body += " " + _lorem(5)
    while _chars(body) > hi:
        body = body[:-5].rstrip()
    return body


def _synth_avatar_q1_30() -> str:
    qs = [
        (1, "Name and archetype",
         "Internal archetype label for this avatar profile: 'The Overlooked Authority.'"),
        (2, "Marital status and family",
         "Predominantly married or long-partnered, most raising school-age children while running the business."),
        (3, "Location and lifestyle",
         "Suburban and metro United States, a remote-first lifestyle built around a packed household routine."),
        (4, "Occupation and income",
         "Self-employed founder/owner of a service business; strong business revenue but a personal income/salary that "
         "still lags what the work is worth."),
        (5, "Education and credentials",
         "Bachelor's degree at minimum; frequently a master's degree or an industry certification/credential on top of it."),
        (6, "Favorite quote",
         "\"Clarity is the currency of trust.\" — a line she keeps pinned above her desk."),
        (7, "Books, magazines, and blogs",
         "Favorite book: a well-worn hardcover on positioning. Favorite magazine: a small-business monthly. "
         "Favorite blog: a marketing blog she checks every week."),
        (8, "Conferences and communities",
         "Attends one annual founder conference and stays active in a small paid mastermind community for accountability."),
        (9, "Ten needs and problems",
         "\n".join(f"{i}. Need/problem {i} facing this avatar." for i in range(1, 11))),
        (10, "Ten goals and motivations",
         "\n".join(f"{i}. Goal/motivation {i} driving this avatar." for i in range(1, 11))),
        (11, "Deepest fears",
         "She fears being permanently overlooked.\n" + "\n".join(f"{i}. Fear {i}." for i in range(1, 4))),
        (12, "Truest desires",
         "She desires a calendar that fills itself.\n" + "\n".join(f"{i}. Desire {i}." for i in range(1, 4))),
        (13, "Core objections",
         "Her core objection is doubt that visibility will actually convert.\n"
         + "\n".join(f"{i}. Objection {i}." for i in range(1, 4))),
    ]
    parts = ["# 01-avatar-questions-1-30 artifact\n"]
    for n, label, body in qs:
        parts.append(f"### Question {n}: {label}\n\n{body} {_lorem(40)}\n")
    parts.append("\n## Synthesis\n\n" + _lorem(2600))
    return "\n".join(parts)


def _synth_five_lists() -> str:
    traits = ["Meticulous", "Resilient", "Empathetic", "Quietly ambitious", "Under-confident-yet-capable"]
    values = ["Integrity", "Craft mastery", "Service", "Growth", "Earned recognition"]
    out = ["\n## Section 3 — Psychographics: Five Personality Traits\n"]
    out += [f"{i}. {t} — {_lorem(6)}." for i, t in enumerate(traits, 1)]
    out.append("\n## Section 4 — Five Core Values\n")
    out += [f"{i}. {v} — {_lorem(6)}." for i, v in enumerate(values, 1)]
    return "\n".join(out) + "\n"


def _synth(manifest: Dict[str, Any], apply_repairs: bool = True) -> Dict[str, Any]:
    artifacts, models, receipts = {}, {}, []
    for s in manifest["stages"]:
        sid = s["stage_id"]
        f = s.get("floors", {})
        parts = [f"# {sid} artifact\n"]
        if f.get("avatar_relevance"):
            artifacts[sid] = _synth_avatar_q1_30()
            models[sid] = "ollama-cloud/qwen3-235b" if s["tier"] == "A" else "openrouter/deepseek-chat"
            receipts.append(sid)
            continue
        if f.get("word_floor"):
            parts.append(_lorem(int(f["word_floor"]) + 60))
        if f.get("five_list_relevance"):
            parts.append(_synth_five_lists())
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
            for idx, name in enumerate(HERO_SECTION_NAMES):
                unit, lo, hi = HERO_BANDS[idx]
                if unit == "steps":
                    body = "\n".join(f"{i}. {_fit_band('chars', 89, 116)}" for i in range(1, 7))
                    body += "\n7. " + _fit_band("chars", 120, 168)
                    parts.append(f"\n## Section {idx + 1}: {name}\n{body}\n")
                else:
                    parts.append(f"\n## Section {idx + 1}: {name}\n{_fit_band(unit, lo, hi)}\n")
        artifacts[sid] = "".join(parts)
        models[sid] = "ollama-cloud/qwen3-235b" if s["tier"] == "A" else "openrouter/deepseek-chat"
        receipts.append(sid)
    return {"artifacts": artifacts, "models": models, "receipts": receipts,
            "apply_repairs": apply_repairs, "env_names": ["OLLAMA_HOST", "OPENROUTER_API_KEY"]}


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
    def anthropic_by_omission(st):
        # the exact QC-reproduced forgery: a ledger that simply OMITS a
        # stage's model id must fail closed, not pass vacuously by absence.
        del st["models"]["39-hero-page"]
    def adcount_short(st):
        lines = st["artifacts"]["25-ad-set-4"].splitlines()
        st["artifacts"]["25-ad-set-4"] = "\n".join(l for l in lines if not re.match(r"^\s*(9|10)\.\s", l))
    def hero_wrong_name(st):
        st["artifacts"]["39-hero-page"] = st["artifacts"]["39-hero-page"].replace(
            "The Big Bold Claim", "The Big Bold Promise (renamed)")
    def hero_band(st):
        st["artifacts"]["39-hero-page"] = st["artifacts"]["39-hero-page"].replace(
            f"## Section 1: {HERO_SECTION_NAMES[0]}\n{_fit_band(*HERO_BANDS[0])}",
            f"## Section 1: {HERO_SECTION_NAMES[0]}\ntoo short")
    def avatar_relevance(st):
        st["artifacts"]["01-avatar-questions-1-30"] = re.sub(
            r"### Question 2:.*?(?=### Question 3:)",
            "### Question 2: Marital status and family\n\nGeneric avatar-emotion prose that never "
            "names a marital status or a family detail at all.\n\n",
            st["artifacts"]["01-avatar-questions-1-30"], flags=re.DOTALL)
    def five_list_short(st):
        txt = st["artifacts"]["09-problem-aware"]
        idx = txt.index("Five Core Values")
        m = re.search(r"Five Core Values\n+1\..*?\n", txt[idx:], re.DOTALL)
        cut = idx + (m.end() if m else len("Five Core Values"))
        st["artifacts"]["09-problem-aware"] = txt[:cut]
    return [
        ("stage_missing_artifact", "AF-AV-STAGE-MISSING", missing),
        ("stage_missing_receipt", "AF-AV-STAGE-MISSING", no_receipt),
        ("word_floor_under", "AF-AV-FLOOR", short_floor),
        ("count_39_short", "AF-AV-COUNT-39", bad_39),
        ("headline_not_12", "AF-AV-COUNT-HEADLINE", bad_headline),
        ("adset_category_drift", "AF-AV-ADSET-CAT", drift),
        ("adcount_short", "AF-AV-ADCOUNT", adcount_short),
        ("image_band_too_small", "AF-AV-IMG-BAND", img_band),
        ("duplicate_artist", "AF-AV-UNIQUE-ARTIST", dup_artist),
        ("botdoc_missing_mergetag", "AF-AV-BOTDOC", botdoc),
        ("hero_missing_sections", "AF-AV-HERO-12", hero),
        ("hero_wrong_section_name", "AF-AV-HERO-12", hero_wrong_name),
        ("hero_section_out_of_band", "AF-AV-HERO-BAND", hero_band),
        ("avatar_question_ignores_header", "AF-AV-SECTION-RELEVANCE", avatar_relevance),
        ("five_list_under_5_named_items", "AF-AV-SECTION-RELEVANCE", five_list_short),
        ("placeholder_leak", "AF-AV-PLACEHOLDER", placeholder),
        ("anthropic_model_id", "AF-AV-NOANTHROPIC", anthropic),
        ("anthropic_model_id_omitted_by_ledger", "AF-AV-NOANTHROPIC", anthropic_by_omission),
    ]


def run_self_test(manifest) -> int:
    ok = True
    # (1) valid full run passes in BOTH repair modes.
    v_on, _ = verify(manifest, _synth(manifest, apply_repairs=True))
    v_off, _ = verify(manifest, _synth(manifest, apply_repairs=False))
    if v_on:
        ok = False; print(f"SELF-TEST FAIL: valid repairs-ON run produced {len(v_on)} violation(s): {v_on[:6]}")
    else:
        print("SELF-TEST ok: valid full-run fixture PASSES with repairs ON (0 violations).")
    if v_off:
        ok = False; print(f"SELF-TEST FAIL: valid repairs-OFF run produced {len(v_off)} violation(s): {v_off[:6]}")
    else:
        print("SELF-TEST ok: valid full-run fixture PASSES with repairs OFF/default (0 violations).")

    # (2) every single-defect mutation fails closed (repairs ON so R4/G-ADSET-CAT is live).
    for name, expected, mut in _violation_cases(manifest):
        st = _synth(manifest, apply_repairs=True)
        mut(st)
        vio, _ = verify(manifest, st)
        codes = {c for c, _ in vio}
        if not vio:
            ok = False; print(f"SELF-TEST FAIL: '{name}' produced NO violations (expected {expected}).")
        elif expected not in codes:
            ok = False; print(f"SELF-TEST FAIL: '{name}' -> {sorted(codes)} (expected {expected}).")
        else:
            print(f"SELF-TEST ok: '{name}' -> nonzero, carries {expected}.")

    # (3) REPAIR-GATING proof: the SAME 'category 2' drift that fails under repairs
    #     ON must NOT trip AF-AV-ADSET-CAT under the default faithful-to-live run.
    st_on = _synth(manifest, apply_repairs=True)
    st_on["artifacts"]["28-ad-set-7"] = st_on["artifacts"]["28-ad-set-7"].replace("category 5", "category 2")
    codes_on = {c for c, _ in verify(manifest, st_on)[0]}
    st_off = _synth(manifest, apply_repairs=False)
    st_off["artifacts"]["28-ad-set-7"] = st_off["artifacts"]["28-ad-set-7"].replace("category 5", "category 2")
    codes_off = {c for c, _ in verify(manifest, st_off)[0]}
    if "AF-AV-ADSET-CAT" in codes_on and "AF-AV-ADSET-CAT" not in codes_off:
        print("SELF-TEST ok: G-ADSET-CAT (R4) enforced under --apply-repairs, relaxed in the default live run.")
    else:
        ok = False
        print(f"SELF-TEST FAIL: repair-gating wrong (on={sorted(codes_on)} off={sorted(codes_off)}).")

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
