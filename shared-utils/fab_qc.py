#!/usr/bin/env python3
"""fab_qc.py — Funnel-&-Automation Build-Quality scorer (FAB-QC).

THE STANDING, LIBRARY-AWARE BUILD-QUALITY GATE both a Skill-6 funnel build AND a
Skill-44 automation build are held to. It is a SUPERSET overlay ON TOP of the
existing mechanical floors (ghl_verify for funnels, WF-1..21 for automations): it
does not replace them, it adds the six library-aware dimensions the mechanical gates
are blind to. Threshold = 8.5 (consistent with QC-PROTOCOL.md and every other rubric
in the repo — do NOT introduce a new threshold).

SIX DIMENSIONS (weights sum to 100; each scored 0-10):
  D1 Template fidelity       22  — the built artifact reproduces the MATCHED template's
                                    required structure (funnel: each pageStructure page +
                                    its blocks; automation: each `sequence` step + channel).
  D2 Copy substance          20  — every required section/step carries substantive copy:
                                    per-section word floor + ZERO surviving placeholder tokens.
  D3 Render / soundness       18  — funnel: ghl_verify overall_pass (200 + marker); automation:
                                    WF-1..21 mechanical PASS. This is the HARD mechanical floor.
  D4 Persona grounding        15  — the matched book persona is named in persona-selection-log
                                    AND voice markers are present. Fail-closed if the selector
                                    did not run (mirrors funnel_rubrics.persona_grounding_gate).
  D5 Flexibility honored      13  — the recorded flex decision is consistent: an EXPLICIT user
                                    spec was honored verbatim and NOT overridden by a template;
                                    deviations are intentional+logged, not accidental.
  D6 Funnel<->automation link 12  — when a funnel implies follow-ups (or an automation ties to a
                                    funnel), the _links pairing was honored. N/A => 10.

HARD-MISS rule (lifted from funnel_rubrics.py): any load-bearing sub-check that earns 0
fails its dimension regardless of the weighted mean — a surviving placeholder in a LIVE
artifact, <50% of the required template structure, a 5xx / WF mechanical FAIL, or a
missing persona selector run cannot be averaged away.

stdlib-only, deterministic, no network. The flex.py matcher core does NO scoring (it only
maps intent-mode -> decision); THIS module is the scorer, and D5 READS the persisted flex
decision (routing/match-decision.json) rather than re-deriving it.
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

try:
    import anti_copy_guard  # noqa: E402 — sibling; A-U10 hard-miss check (optional)
except ImportError:  # pragma: no cover — module always ships alongside fab_qc.py
    anti_copy_guard = None

THRESHOLD = 8.5

# Dimension weights (sum = 100).
W = {"D1": 22, "D2": 20, "D3": 18, "D4": 15, "D5": 13, "D6": 12}
assert sum(W.values()) == 100

# Placeholder tokens that must NOT survive into a LIVE artifact.
_PLACEHOLDER_PATTERNS = [
    r"lorem ipsum", r"\bTODO\b", r"\bTBD\b", r"your text here", r"insert\s+\w+\s+here",
    r"\[[^\]]*\]",            # [HEADLINE], [CLIENT TO SUPPLY], [...]
    r"\{\{[^}]*\}\}",         # {{merge}} / {{...}} mustache placeholders left unfilled
    r"xxx+", r"placeholder",
]
_PLACEHOLDER_RE = re.compile("|".join(_PLACEHOLDER_PATTERNS), re.IGNORECASE)

# Merge-field tokens that are LEGITIMATE in live copy (do NOT count as placeholders).
_ALLOWED_MERGE = re.compile(r"\{\{\s*(contact|first_?name|last_?name|email|user|company|appointment)", re.I)

# --------------------------------------------------------------------------- #
# FIX-XC-04a — lengthClass-keyed floors (adjustable constants table).
# The old flat 4-word floor let a 4-word body slot pass as "substantive". A real
# body slot must carry substantive copy; only legitimately-short slots (headline,
# subhead, CTA/button, eyebrow…) are exempt at the low headline floor. Page-level
# floors are keyed to the MATCHED TEMPLATE's lengthClass. Numbers are PROPOSED
# defaults (ratify exact values with Trevor) — kept here as one adjustable table.
# --------------------------------------------------------------------------- #
_HEADLINE_SLOT_FLOOR = 4          # legitimately-short slots (headline/subhead/CTA/button)
_BODY_SLOT_FLOOR = 40             # a substantive body/content slot carries >= this many words
_AUTOMATION_WORD_FLOOR = 4        # automation step copy keeps the light floor (funnel-scope train)

# Slot-name tokens that mark a legitimately-short slot (exempt at the headline floor).
_SHORT_SLOT_TOKENS = (
    "headline", "hed", "head", "title", "subhead", "subheadline", "sub_head",
    "cta", "button", "btn", "eyebrow", "kicker", "label", "badge", "tagline",
    "form", "confirm", "field", "placeholder_text", "menu", "nav", "footer_link",
)

# Page-level stripped-word floors keyed by the matched template's lengthClass.
# short-form >= 350 / medium >= 700 / long-form >= 1,800 (proposed defaults).
_PAGE_WORD_FLOOR = {
    "short-form": 350, "short": 350, "short-to-medium-form": 500,
    "medium-form": 700, "medium": 700, "mid-form": 700,
    "long-form": 1800, "long": 1800,
}

# Bounded re-author policy (verifier != author). The scorer FLAGS a below-floor
# HARD MISS; the orchestrating SOP/role runs the capped re-author loop (see
# conversion-copywriter.md Gate 1-2 + SOP-FUNNEL-02-COPY.md). Recorded here so the
# cap has one canonical source.
MAX_REAUTHOR_ATTEMPTS = 5


def _slot_floor(slot_name: str) -> int:
    """Word floor for a named slot: short slots (headline/CTA/…) are exempt at the
    low headline floor; everything else is a body slot held to the body floor."""
    s = str(slot_name or "").lower()
    return _HEADLINE_SLOT_FLOOR if any(tok in s for tok in _SHORT_SLOT_TOKENS) else _BODY_SLOT_FLOOR


def _lengthclass_floor(length_class) -> int:
    """Resolve a page-level stripped-word floor from a template lengthClass string.
    Accepts noisy values ('long-form (multi-page …)') by matching the leading token.
    Returns 0 (no floor / N/A) for variable/historical/unknown classes."""
    if not length_class:
        return 0
    lc = str(length_class).strip().lower()
    if lc in _PAGE_WORD_FLOOR:
        return _PAGE_WORD_FLOOR[lc]
    # take the leading token before a space / paren / pipe ('long-form (…)' -> 'long-form')
    lead = re.split(r"[\s(|]", lc, 1)[0].strip()
    return _PAGE_WORD_FLOOR.get(lead, 0)


@dataclass
class Dim:
    name: str
    weight: int
    score: float            # 0-10
    hard_miss: bool
    observed: str
    subchecks: list = field(default_factory=list)

    @property
    def earned(self) -> float:
        return round((0.0 if self.hard_miss else self.score) * self.weight / 10.0, 3)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _texts_of(artifact: dict) -> list[str]:
    """All copy strings in a normalised built artifact (funnel pages or automation steps)."""
    out: list[str] = []
    for page in artifact.get("pages", []) or []:
        copy = page.get("copy", {})
        if isinstance(copy, dict):
            out += [str(v) for v in copy.values() if v is not None]
        elif isinstance(copy, list):
            out += [str(v) for v in copy]
        elif copy:
            out.append(str(copy))
    for step in artifact.get("steps", []) or []:
        for k in ("copy", "body", "subject", "message", "text"):
            v = step.get(k)
            if v:
                out.append(str(v))
    return [t for t in out if t and t.strip()]


def _slot_texts_of(artifact: dict) -> list[tuple[str, str]]:
    """(slot_name, text) pairs so per-slot floors can be applied (FIX-XC-04a)."""
    out: list[tuple[str, str]] = []
    for page in artifact.get("pages", []) or []:
        copy = page.get("copy", {})
        if isinstance(copy, dict):
            for k, v in copy.items():
                if v is not None:
                    out.append((str(k), str(v)))
        elif isinstance(copy, list):
            for i, v in enumerate(copy):
                out.append((f"slot{i}", str(v)))
        elif copy:
            out.append(("copy", str(copy)))
    for step in artifact.get("steps", []) or []:
        for k in ("copy", "body", "subject", "message", "text"):
            v = step.get(k)
            if v:
                out.append((k, str(v)))
    return [(s, t) for s, t in out if t and t.strip()]


def _page_word_count(page: dict) -> int:
    """Total whitespace-token count across all copy strings on one funnel page."""
    copy = page.get("copy", {})
    if isinstance(copy, dict):
        vals = [str(v) for v in copy.values() if v is not None]
    elif isinstance(copy, list):
        vals = [str(v) for v in copy]
    elif copy:
        vals = [str(copy)]
    else:
        vals = []
    return sum(len(v.split()) for v in vals)


def _page_length_misses(inp: dict, art: dict) -> list[tuple]:
    """Pages whose total copy is under the matched template's lengthClass floor.
    Funnel-only; N/A for CREATE_NEW / no template / unknown lengthClass."""
    if inp.get("kind", "funnel") != "funnel":
        return []
    tmpl = inp.get("template") or {}
    md = inp.get("match_decision", {}) or {}
    if md.get("flex_decision") == "CREATE_NEW" or not tmpl:
        return []
    floor = _lengthclass_floor(tmpl.get("lengthClass") or tmpl.get("length_class"))
    if not floor:
        return []
    misses = []
    pages = art.get("pages", []) or []
    total = sum(_page_word_count(p) for p in pages)
    # Page-level floor is the whole-funnel stripped-word floor keyed to lengthClass.
    if total < floor:
        misses.append(("<all-pages>", total, floor,
                       tmpl.get("lengthClass") or tmpl.get("length_class")))
    return misses


def _has_placeholder(text: str) -> bool:
    # strip legitimate merge fields before scanning so {{contact.first_name}} is allowed
    scrubbed = _ALLOWED_MERGE.sub("OK", text)
    return bool(_PLACEHOLDER_RE.search(scrubbed))


def _is_live(match_decision: dict, verify: dict) -> bool:
    """A build is LIVE (not a mock) unless the verifier stamped trust=MOCK."""
    trust = (verify or {}).get("trust", "LIVE")
    return str(trust).upper() != "MOCK"


# --------------------------------------------------------------------------- #
# D1 — Template fidelity
# --------------------------------------------------------------------------- #
def score_d1(inp: dict) -> Dim:
    md = inp.get("match_decision", {}) or {}
    tmpl = inp.get("template")
    flex_decision = md.get("flex_decision")
    if flex_decision == "CREATE_NEW" or not tmpl:
        return Dim("D1 Template fidelity", W["D1"], 10.0, False,
                   "no matched template (CREATE_NEW / net-new) — fidelity N/A, scored 10")

    kind = inp.get("kind", "funnel")
    art = inp.get("artifact", {}) or {}
    if kind == "funnel":
        required = tmpl.get("pageStructure", []) or []
        built = art.get("pages", []) or []
        n = len(required) or 1
        # a template page is "present" if the built artifact has a page in that ORDER slot
        present = min(len(built), len(required))
        frac = present / n
        observed = f"{present}/{len(required)} template pages present in build"
    else:  # automation
        required = tmpl.get("sequence", []) or []
        built = art.get("steps", []) or []
        n = len(required) or 1
        present = min(len(built), len(required))
        frac = present / n
        observed = f"{present}/{len(required)} sequence steps present in build"

    score = round(10.0 * frac, 2)
    hard = frac < 0.5
    return Dim("D1 Template fidelity", W["D1"], score, hard,
               observed + (" — HARD MISS (<50% of required structure)" if hard else ""))


# --------------------------------------------------------------------------- #
# D2 — Copy substance / real-not-thin
# --------------------------------------------------------------------------- #
def score_d2(inp: dict) -> Dim:
    art = inp.get("artifact", {}) or {}
    live = _is_live(inp.get("match_decision", {}), inp.get("verify", {}))
    kind = inp.get("kind", "funnel")
    slot_items = _slot_texts_of(art)
    texts = [t for _, t in slot_items]
    if not texts:
        return Dim("D2 Copy substance", W["D2"], 0.0, live,
                   "no copy found in built artifact" + (" — HARD MISS (live)" if live else ""))
    placeholders = [t for t in texts if _has_placeholder(t)]
    ph_ids = set(map(id, placeholders))
    # FIX-XC-04a — per-slot floors: body slots >= 40 words; headline/CTA/short slots
    # exempt at >= 4. Automation steps keep the light floor (funnel-scope train).
    thin: list[tuple[str, str]] = []
    for slot, t in slot_items:
        floor = _AUTOMATION_WORD_FLOOR if kind != "funnel" else _slot_floor(slot)
        if len(t.split()) < floor:
            thin.append((slot, t))
    thin_ids = set(id(t) for _, t in thin)
    # FIX-XC-04a — page-level lengthClass floor (whole-funnel stripped-word floor).
    page_misses = _page_length_misses(inp, art)
    n = len(texts)
    substantive = n - len(ph_ids | thin_ids)
    frac = max(0.0, substantive / n)
    score = round(10.0 * frac, 2)
    # HARD MISS (live artifact): a surviving placeholder, ANY below-floor slot, or a
    # page under its lengthClass floor. Below-floor copy cannot be averaged away — it
    # triggers the bounded re-author loop (verifier != author; <= MAX_REAUTHOR_ATTEMPTS).
    hard = live and (bool(placeholders) or bool(thin) or bool(page_misses))
    body_floor = _AUTOMATION_WORD_FLOOR if kind != "funnel" else _BODY_SLOT_FLOOR
    observed = (f"{substantive}/{n} slots substantive; placeholders={len(placeholders)}; "
                f"thin(body<{body_floor}w)={len(thin)}"
                + (f"; slots={[s for s, _ in thin][:4]}" if thin else "")
                + (f"; page_floor_miss={page_misses[0][1]}w<{page_misses[0][2]}"
                   f"({page_misses[0][3]})" if page_misses else "")
                + f"; live={live}")
    if hard:
        reasons = []
        if placeholders:
            reasons.append("surviving placeholder")
        if thin:
            reasons.append("below-floor slot")
        if page_misses:
            reasons.append("page under lengthClass floor")
        observed += " — HARD MISS (" + "; ".join(reasons) + " in a live artifact)"
    return Dim("D2 Copy substance", W["D2"], score, hard, observed)


# --------------------------------------------------------------------------- #
# D3 — Render / soundness (the hard mechanical floor)
# --------------------------------------------------------------------------- #
def score_d3(inp: dict) -> Dim:
    kind = inp.get("kind", "funnel")
    verify = inp.get("verify", {}) or {}
    if kind == "funnel":
        overall = bool(verify.get("overall_pass"))
        pages = verify.get("pages", []) or []
        statuses = [int(p.get("status", 0) or 0) for p in pages]
        any_5xx = any(500 <= s < 600 for s in statuses)
        all_200 = all(s == 200 for s in statuses) if statuses else overall
        score = 10.0 if (overall and all_200) else (5.0 if overall else 0.0)
        hard = (not overall) or any_5xx
        observed = (f"ghl_verify overall_pass={overall}; statuses={statuses}; "
                    f"5xx={any_5xx}")
    else:  # automation — WF-1..21 mechanical checklist
        items = verify.get("items", []) or verify.get("wf_items", []) or []
        mech = [i for i in items if i.get("status") in ("PASS", "FAIL")]
        fails = [i for i in mech if i.get("status") == "FAIL"]
        passed = len(mech) - len(fails)
        score = round(10.0 * (passed / len(mech)), 2) if mech else (10.0 if verify.get("overall_pass") else 0.0)
        hard = bool(fails)
        observed = f"WF mechanical {passed}/{len(mech)} PASS; FAIL={len(fails)}"
    if hard:
        observed += " — HARD MISS (5xx / mechanical FAIL / overall_pass false)"
    return Dim("D3 Render/soundness", W["D3"], score, hard, observed)


# --------------------------------------------------------------------------- #
# D4 — Persona grounding (fail-closed)
# --------------------------------------------------------------------------- #
def _persona_str(v) -> str:
    """Flatten a persona field that may be a slug string OR a resolved record dict."""
    if isinstance(v, dict):
        return " ".join(str(v.get(k, "")) for k in ("id", "label", "author", "book")).strip()
    return str(v)


def _expected_personas(inp: dict) -> list[str]:
    tmpl = inp.get("template") or {}
    kind = inp.get("kind", "funnel")
    out: list[str] = []
    if kind == "funnel":
        cf = tmpl.get("copyFramework", {}) or {}
        for k in ("primaryPersonaResolved", "primaryPersona"):
            if cf.get(k):
                out.append(_persona_str(cf[k]))
        out += [_persona_str(b) for b in tmpl.get("books", []) or []]
    else:
        cp = tmpl.get("copy_persona", {}) or {}
        if cp.get("primary"):
            out.append(_persona_str(cp["primary"]))
        out += [_persona_str(b) for b in tmpl.get("source_books", []) or []]
    return [p for p in out if p]


def _bundle_active(bundle) -> bool:
    """A persona-bundle-acquisition-ladder receipt (B-U1/U15) is ACTIVE for D4
    grounding only when it named an actual source — an absent/missing receipt
    (the field is entirely omitted, or ``{}``, or ``source: absent``) must
    fall through to the legacy template-token path so a build with no bundle
    wiring is UNCHANGED (B-U5's byte-identical-legacy-path guarantee)."""
    return isinstance(bundle, dict) and bundle.get("source") not in (None, "", "absent")


def voice_persona_grounded(text: str, voice_persona_id: str) -> bool:
    """U117 (E6-3/G9) extension point: the exact "is this persona id named in
    this text" token-match rule ``score_d4``'s bundle-aware branch has always
    used, extracted as a standalone reusable predicate (previously inlined
    only inside ``score_d4``). Pure function, no state, no I/O — a sibling
    module (``page_qc.py``'s comms-conformance "blend actually used" check,
    U117) reuses this SAME predicate as its deterministic evidence input
    instead of re-deriving the token-match rule a second time (one canonical
    definition of "is this persona id named in this text", not two that can
    drift apart). ``score_d4`` below now calls this helper verbatim — a pure
    refactor, zero behavior change (proven by the existing D4 regression
    suite in ``tests/unit/fab-qc.test.py`` staying green unmodified, plus a
    new direct test of this helper).
    """
    pid = (voice_persona_id or "").strip()
    if not pid:
        return False
    low = (text or "").lower()
    toks = [t for t in re.split(r"[^a-z0-9]+", pid.lower()) if len(t) > 3]
    return bool(toks) and any(t in low for t in toks)


def score_d4(inp: dict) -> Dim:
    """D4 — Persona grounding (fail-closed).

    B-U5/U19 (bundle-aware voice grounding — the FAB-QC D4 v2 half of the
    U17<->U19 merge-paired unit, B.0 item 5): when ``inp['persona_bundle']``
    (loaded from ``routing/persona-bundle-receipt.json``, B-U1/U15) is
    ACTIVE, D4 verifies the bundle's VOICE persona is named in the log — NOT
    the template persona. A log naming only the template persona is now the
    HARD MISS (the prior spec's P0 self-defeat: honoring the displayed blend
    would otherwise fail this gate). When NO receipt is active (legacy run,
    or a build that never wired the bundle), this function is BYTE-IDENTICAL
    to the pre-B-U5 template-token behavior below. The ``no log -> 0.0
    HARD MISS`` fail-closed floor is unchanged in BOTH modes.
    """
    log = inp.get("persona_log") or ""
    if not log.strip():
        # fail-closed: the selector did not run / no log -> cannot prove grounding
        return Dim("D4 Persona grounding", W["D4"], 0.0, True,
                   "no persona-selection-log — fail-closed HARD MISS")

    bundle = inp.get("persona_bundle")
    if _bundle_active(bundle):
        voice_pid = (bundle.get("voice_persona_id") or "").strip()
        voice_hit = voice_persona_grounded(log, voice_pid)
        score = 10.0 if voice_hit else 3.0
        hard = not voice_hit
        observed = f"bundle source={bundle.get('source')}; blend voice persona {voice_pid!r} named in log: {voice_hit}"
        if hard:
            observed += " — HARD MISS (blend voice not grounded)"
        return Dim("D4 Persona grounding", W["D4"], score, hard, observed)

    # ── legacy path — byte-identical to pre-B-U5 behavior ──────────────────
    expected = _expected_personas(inp)
    md = inp.get("match_decision", {}) or {}
    if md.get("flex_decision") == "CREATE_NEW" or not expected:
        # net-new: only require that SOME persona grounding was logged
        named = bool(re.search(r"selected_persona", log, re.I))
        return Dim("D4 Persona grounding", W["D4"], 10.0 if named else 4.0, not named,
                   "net-new build; persona log present" if named else "net-new; no persona named")
    low = log.lower()
    # match on any significant token of an expected persona name/book
    hit = False
    for p in expected:
        toks = [t for t in re.split(r"[^a-z0-9]+", p.lower()) if len(t) > 3]
        if toks and any(t in low for t in toks):
            hit = True
            break
    score = 10.0 if hit else 3.0
    hard = not hit
    observed = (f"expected persona/book token in log: {hit}; "
                f"expected={expected[:3]}")
    if hard:
        observed += " — HARD MISS (matched persona not named in log)"
    return Dim("D4 Persona grounding", W["D4"], score, hard, observed)


# --------------------------------------------------------------------------- #
# D5 — Flexibility honored / guide-not-rule
# --------------------------------------------------------------------------- #
def score_d5(inp: dict) -> Dim:
    md = inp.get("match_decision")
    if not md:
        return Dim("D5 Flexibility honored", W["D5"], 0.0, True,
                   "no routing/match-decision.json receipt — cannot prove flexibility honored (HARD MISS)")
    mode = md.get("intent_mode")
    dec = md.get("flex_decision")
    # the matcher's invariant: it never imposes; an EXPLICIT spec must NOT be overridden.
    if mode == "EXPLICIT_USER_SPEC" and dec not in ("HONOR_USER",):
        return Dim("D5 Flexibility honored", W["D5"], 0.0, True,
                   f"EXPLICIT user spec was overridden by a template (decision={dec}) — HARD MISS")
    valid = {"HONOR_USER", "SUGGEST_TEMPLATE", "USE_TEMPLATE", "CREATE_NEW"}
    if dec not in valid:
        return Dim("D5 Flexibility honored", W["D5"], 4.0, False,
                   f"flex decision missing/invalid (decision={dec})")
    return Dim("D5 Flexibility honored", W["D5"], 10.0, False,
               f"flex decision recorded + consistent (mode={mode}, decision={dec})")


# --------------------------------------------------------------------------- #
# D6 — Funnel<->automation link integrity
# --------------------------------------------------------------------------- #
def score_d6(inp: dict) -> Dim:
    md = inp.get("match_decision", {}) or {}
    linked = md.get("linked_automations")
    funnel_id = md.get("funnel_template_id")
    if not funnel_id and not linked:
        return Dim("D6 Funnel<->automation link", W["D6"], 10.0, False,
                   "no funnel<->automation link implied — N/A, scored 10")
    link_map = inp.get("link_map")
    if not link_map:
        return Dim("D6 Funnel<->automation link", W["D6"], 6.0, False,
                   "link implied but link map unavailable to verify")
    entry = next((l for l in link_map.get("links", [])
                  if l.get("funnel_template_id") == funnel_id), None)
    if not entry:
        return Dim("D6 Funnel<->automation link", W["D6"], 5.0, False,
                   f"no link-map entry for funnel '{funnel_id}'")
    primary = (entry.get("primary_followup") or {}).get("automation_id")
    # index the attached automations by id, keeping the override flag.
    by_id = {}
    if isinstance(linked, dict):
        for a in linked.get("automations", []) or []:
            by_id[a.get("automation_id")] = a
    if not primary:
        return Dim("D6 Funnel<->automation link", W["D6"], 10.0, False,
                   "link entry has no primary follow-up — nothing to carry")
    rec = by_id.get(primary)
    if rec is None:
        # The funnel implies a primary follow-up but the complete-funnel handoff carried
        # NOTHING for it AND it was not an explicit user override -> the handoff broke.
        # (An explicit override would still appear here with overridden_by_user=true.)
        return Dim("D6 Funnel<->automation link", W["D6"], 0.0, True,
                   f"primary follow-up '{primary}' silently dropped (not attached, not overridden) "
                   f"— HARD MISS (complete-funnel handoff failed)")
    if rec.get("overridden_by_user"):
        return Dim("D6 Funnel<->automation link", W["D6"], 10.0, False,
                   f"primary '{primary}' explicitly overridden by user — honored (flexibility)")
    return Dim("D6 Funnel<->automation link", W["D6"], 10.0, False,
               f"primary follow-up '{primary}' attached; linked={sorted(x for x in by_id if x)}")


# --------------------------------------------------------------------------- #
# A-U10 — Anti-copy guard (deterministic similarity ceiling vs injected
# exemplars, key-free, hard-miss). Weight 0: this is a HARD-MISS-ONLY check,
# never part of the weighted D1-D6 score (the six dimensions above stay
# canonical — W's sum-to-100 invariant is untouched). It is the mechanical
# twin of the persona-impersonation guardrail bolted onto the hard-miss
# family, per master spec v2 A.9's A-U10 build text.
# --------------------------------------------------------------------------- #
def score_anti_copy(inp: dict) -> "Dim | None":
    """Returns None (excluded from ``dims`` entirely — a true no-op, not a
    zero-weight pass) whenever: the module is unavailable, the
    ANTI_COPY_GUARD_ENABLED flag is off (REVERT posture — flip the flag,
    no code revert needed), or no ``exemplar_packs`` were supplied. That last
    condition is the same "no applicable pack -> degrade to today's
    behavior" contract A-U9's own ``build_injection_block`` honors — a build
    with nothing to compare against is scored exactly as it was pre-A-U10."""
    if anti_copy_guard is None or not anti_copy_guard.guard_enabled():
        return None
    packs = inp.get("exemplar_packs") or []
    if not packs:
        return None
    texts = _texts_of(inp.get("artifact", {}) or {})
    if not texts:
        return None
    result = anti_copy_guard.anti_copy_check(texts, packs)
    hard = bool(result.get("hard_miss"))
    breached = result.get("breached_exemplars") or []
    observed = (f"checked {len(texts)} copy slot(s) against {len(packs)} injected "
                f"exemplar(s); ceiling={result.get('ceiling')}")
    if hard:
        observed += f" — HARD MISS (similarity ceiling breached vs {breached})"
    return Dim("D-anti-copy Anti-copy guard", 0, 0.0 if hard else 10.0, hard, observed)


# --------------------------------------------------------------------------- #
# grade
# --------------------------------------------------------------------------- #
def grade(inp: dict) -> dict:
    """Score a build. ``inp`` keys: kind('funnel'|'automation'), match_decision, template,
    artifact, verify, persona_log, link_map, persona_bundle (B-U5/U19, optional —
    the normalized persona-bundle-acquisition-ladder receipt; D4 grounds on the
    bundle's VOICE persona when active, else the legacy template-token path,
    byte-identical, when absent), exemplar_packs (A-U10, optional — list of
    {exemplar_id, gold_output_path|text} the anti-copy guard checks the built
    artifact's copy against; absent -> guard is a no-op, byte-identical to
    pre-A-U10 behavior). Returns the FAB-QC scorecard."""
    dims = [score_d1(inp), score_d2(inp), score_d3(inp),
            score_d4(inp), score_d5(inp), score_d6(inp)]
    anti_copy_dim = score_anti_copy(inp)
    if anti_copy_dim is not None:
        dims.append(anti_copy_dim)
    weighted = round(sum(d.earned for d in dims), 2)        # 0-100
    score_10 = round(weighted / 10.0, 2)                    # 0-10
    hard_misses = [d.name for d in dims if d.hard_miss]
    passed = (score_10 >= THRESHOLD) and not hard_misses
    lowest = min(dims, key=lambda d: (d.score - (100 if d.hard_miss else 0)))
    return {
        "tool": "fab_qc",
        "kind": inp.get("kind", "funnel"),
        "threshold": THRESHOLD,
        "weighted_score_100": weighted,
        "score": score_10,
        "passed": passed,
        "hard_misses": hard_misses,
        "lowest_dimension": lowest.name,
        "dimensions": [asdict(d) | {"earned": d.earned} for d in dims],
    }


# --------------------------------------------------------------------------- #
# evidence-tree loader (the CLI path the wrappers use)
# --------------------------------------------------------------------------- #
def _load_json(path: str):
    try:
        return json.load(open(path, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _load_exemplar_packs_from_receipt(evidence_root: str) -> list:
    """A-U10: resolve the REAL exemplar packs this build actually injected
    (A-U9's ``routing/exemplar-injection.json`` receipt, written by
    ``exemplar_injection.write_injection_receipt``) back to their on-disk
    gold-output text, so the anti-copy guard checks the built artifact
    against exactly what was shown to the writer — never a fabricated or
    unrelated exemplar set. Each ``exemplar_id`` is the deterministic
    ``<skill>/<deliverable_type>/<slug>`` format ``exemplar_injection.py``
    assigns (its own ``fallback_id`` / shipped ``provenance.json`` both use
    it), so it is resolved generically against the repo root — this module
    never hardcodes a specific skill directory. Returns [] (the anti-copy
    guard degrades to a no-op, same as A-U9's own no-match receipt) when no
    receipt exists, it named nothing, or a named exemplar can't be found on
    disk (a dangling id never fabricates a comparison text)."""
    doc = _load_json(os.path.join(evidence_root, "routing", "exemplar-injection.json"))
    if not isinstance(doc, dict):
        return []
    seen: dict = {}
    for injection in doc.get("injections", []) or []:
        for ex in injection.get("exemplars", []) or []:
            exemplar_id = ex.get("exemplar_id")
            if not exemplar_id or exemplar_id in seen:
                continue
            parts = str(exemplar_id).split("/")
            if len(parts) != 3:
                continue
            skill, deliverable_type, slug = parts
            gold_path = os.path.join(_REPO_ROOT, skill, "exemplars", deliverable_type, slug,
                                      "gold-output.md")
            if os.path.isfile(gold_path):
                seen[exemplar_id] = {"exemplar_id": exemplar_id, "gold_output_path": gold_path}
    return list(seen.values())


def load_inputs_from_evidence(evidence_root: str, kind: str) -> dict:
    routing = os.path.join(evidence_root, "routing")
    md = _load_json(os.path.join(routing, "match-decision.json")) or {}
    template = None
    tpath = md.get("template_path")
    if tpath:
        if not os.path.isabs(tpath):
            tpath = os.path.normpath(os.path.join(routing, tpath))
        template = _load_json(tpath)
    artifact = (_load_json(os.path.join(evidence_root, "build", "fab-artifact.json"))
                or _load_json(os.path.join(evidence_root, "funnel", "fab-artifact.json"))
                or {})
    if kind == "funnel":
        verify = (_load_json(os.path.join(evidence_root, "scorecard", "verify-summary.json")) or {})
    else:
        verify = (_load_json(os.path.join(evidence_root, "qc", "wf-checklist.json"))
                  or _load_json(os.path.join(evidence_root, "scorecard", "wf-checklist.json")) or {})
    persona_log = ""
    for cand in ("persona-selection-log.md",
                 os.path.join("..", "persona-selection-log.md")):
        p = os.path.join(evidence_root, cand)
        if os.path.isfile(p):
            persona_log = open(p, encoding="utf-8").read()
            break
    link_map = None
    lm = md.get("link_map_path") or os.environ.get("GHL_FUNNEL_AUTOMATION_LINKS") \
        or os.environ.get("CAF_FUNNEL_AUTOMATION_LINKS")
    if lm and os.path.isfile(lm):
        link_map = _load_json(lm)
    # B-U5/U19: the persona-bundle-acquisition-ladder receipt (B-U1/U15),
    # written to routing/persona-bundle-receipt.json alongside match-decision.
    # Absent on any build that hasn't wired the bundle -> {} -> D4's legacy
    # template-token path (byte-identical to pre-B-U5 behavior).
    persona_bundle = _load_json(os.path.join(routing, "persona-bundle-receipt.json")) or {}
    # A-U10: resolve the real injected exemplars (A-U9's own receipt) so the
    # anti-copy guard checks against exactly what the writer saw.
    exemplar_packs = _load_exemplar_packs_from_receipt(evidence_root)
    return {"kind": kind, "match_decision": md, "template": template, "artifact": artifact,
            "verify": verify, "persona_log": persona_log, "link_map": link_map,
            "persona_bundle": persona_bundle, "exemplar_packs": exemplar_packs}


def main(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="FAB-QC — funnel/automation build-quality gate (>=8.5)")
    ap.add_argument("--evidence", required=False, help="evidence root dir")
    ap.add_argument("--inputs", help="pre-assembled fab-input.json (testing)")
    ap.add_argument("--kind", choices=["funnel", "automation"], default="funnel")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--gate", action="store_true", help="exit non-zero if score < 8.5 or any hard miss")
    a = ap.parse_args(argv)

    if a.inputs:
        inp = _load_json(a.inputs) or {}
        inp.setdefault("kind", a.kind)
    elif a.evidence:
        inp = load_inputs_from_evidence(a.evidence, a.kind)
    else:
        ap.error("one of --evidence or --inputs is required")
        return 2

    result = grade(inp)
    if a.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"FAB-QC [{result['kind']}] score={result['score']}/10 "
              f"(threshold {THRESHOLD}) passed={result['passed']}")
        for d in result["dimensions"]:
            flag = "HARD-MISS" if d["hard_miss"] else f"{d['score']:.1f}/10"
            print(f"  {d['name']:<28} w={d['weight']:>2} {flag:<10} {d['observed']}")
        if not result["passed"]:
            print(f"  -> lowest: {result['lowest_dimension']}; hard_misses={result['hard_misses']}")
    if a.gate and not result["passed"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
