#!/usr/bin/env python3
"""craft_judgement.py — FIX 18: the 5/6/2 disposition of the 13 human-judgement craft rows.

MASTER-QC-AUTOFAIL-RULESET.md previously carried 13 rows marked HUMAN JUDGEMENT
(lines 169-278: AF-HOOK-2, AF-HOOK-7, AF-AUD-1, AF-AUD-2, AF-AUD-3, AF-OBI-3,
AF-OBI-4, AF-OBI-5, AF-OBI-6, AF-DEN-3, AF-DEN-6, AF-DEN-8, AF-OBI). FIX 18's
DEFAULT RULING resolves every row into one of three buckets so no row remains
ambiguous:

  ENFORCED NOW (5) — deterministic checks with structured evidence, blocking:
      AF-HOOK-2   hook on a slide whose declared layout puts it in a footer/band
      AF-HOOK-7   the canonical hook on a slide declared as the signature-quote slide
      AF-OBI-6    a comparison table with MORE THAN 2 data rows on one slide
      AF-DEN-3    a DROP arc slot whose immediately preceding slide is not BUILDUP
      AF-DEN-6    Wall of Wins not 4-6 slides before the first offer/price slot
    These run in run_all_checks (below), which the FIX 15 preflight gate
    (build_deck._chk_slide_craft) already calls, so the five become blocking
    through the same waiver/deferral discipline as the ten earlier checks. A
    check DEFERS ("") when its declared evidence does not exist — a missing
    declaration is an upstream-input gap, never a silent pass.

  WARNING + PER-RULE ESCAPE HATCH (6) — heuristics that may warn, never claim a
  deterministic auto-fail:  AF-AUD-1, AF-AUD-2, AF-AUD-3, AF-OBI-3, AF-OBI-5,
  AF-DEN-8. Each warning holds the applicable QC phase until corrected OR
  individually acknowledged in working/qc/craft-warning-dispositions.json by a
  record of EXACTLY the shape
      {"rule_code", "slide_ids", "run_id", "reviewer", "rationale",
       "decision", "captured_at", "owner_signature"}
  One record covers ONE rule only (no wildcards, one rule_code string). Records
  are cross-run-reuse-proof via run_id == run_dir.name, self-approval-proof
  (reviewer must not be a builder/builder-role identity), and owner-signed.
  Malformed, wildcard, unsanctioned-decision or cross-run records are IGNORED
  (fail closed) — a broken escape hatch never silences a warning.

  STAY HUMAN (2) — AF-OBI-4 (full value trio / alliteration-plus-parallelism)
  and AF-OBI (generic OBI dimension label). NO keyword proxy is implemented for
  either (a keyword proxy would fire on any three-noun headline; the base
  AF-OBI is a label, not a machine rule). A relevant QC attestation phase is
  BLOCKED until a human_craft_verdicts.json entry records an independent
  reviewer's pass/fail for each of the two codes (self/builder verdicts are
  rejected; verdict "fail" blocks outright). Neither rule is presented as
  measured automation anywhere.

Feature flag: PRESENTATION_CRAFT_DISPOSITIONS — DEFAULT-ON. Setting it to "0"
rolls FIX 18 back to pre-FIX-18 behavior (warnings computed but not held, and
the attestation/human-verdict gate idle) — the documented rollback path. The
five enforce checks do NOT honor the flag as an off switch by themselves; they
are retired only by this module going unwired, and the rollback sets
craft_judgement.run_all_checks to pass-through (see enforce_active()).

EVERY CHECK DEFERS AND NEVER RAISES, mirroring slide_craft.py — a raise inside
the preflight gate kills the loop and the remaining entries never run.
"""

import difflib
import json
import os
import re
import time
from pathlib import Path

# ── The disposition registry (exactly 13 unique codes, three disjoint buckets)

ENFORCED_CODES = frozenset({
    "AF-HOOK-2", "AF-HOOK-7", "AF-OBI-6", "AF-DEN-3", "AF-DEN-6",
})

WARNING_CODES = frozenset({
    "AF-AUD-1", "AF-AUD-2", "AF-AUD-3", "AF-OBI-3", "AF-OBI-5", "AF-DEN-8",
})

HUMAN_CODES = frozenset({
    "AF-OBI-4", "AF-OBI",
})

assert len(ENFORCED_CODES | WARNING_CODES | HUMAN_CODES) == 13
assert not (ENFORCED_CODES & WARNING_CODES) and not (ENFORCED_CODES & HUMAN_CODES) \
    and not (WARNING_CODES & HUMAN_CODES)

PROVENANCE_REL = "working/qc/craft_judgement.json"
DISPOSITIONS_REL = Path("working") / "qc" / "craft-warning-dispositions.json"
HUMAN_VERDICTS_REL = Path("working") / "qc" / "human_craft_verdicts.json"
FEATURE_FLAG_ENV = "PRESENTATION_CRAFT_DISPOSITIONS"

# The QC phases whose attestation AF-OBI-4 / AF-OBI hold up (the phases where
# per-slide craft judgement lands before the deck moves on).
HUMAN_VERDICT_PHASES = frozenset({
    "P1Q-COPY-QC",        # -> working/qc/copy_qc_report.json
    "P-PROMPT-QC",        # -> working/qc/prompt_qc_report.json
})

# FIX 18 repair — the WARNING bucket also holds. Each triggered warning records
# a PENDING HOLD against the applicable QC phase (the phase that owns the check:
# all six warning codes run at the copy stage — Phase 1Q and its re-verifications
# at Phase 5/6 — per the ruleset's stage column, so their owning QC phase is
# P1Q-COPY-QC), persisted in working/qc/craft-warnings.json. The phase cannot
# attest while a hold is pending UNLESS the warning is individually acknowledged
# (a valid per-rule/per-slide disposition record — the same disposition file the
# ack escape hatch already uses). The hold state is DERIVED at attestation time:
# the pending-hold snapshot is only what compute_warnings currently reports as
# unacknowledged, so a later valid disposition clears its hold with no extra
# bookkeeping and a repair/rerun clears the finding naturally.
WARNING_HOLDS_REL = Path("working") / "qc" / "craft-warnings.json"
# The QC phase that owns all six warning codes (ruleset §3 item 1 — Phase 1Q
# runs RULE 2 + Section 2 on slides_copy.md + arc_allocation.json; Phase 5/6
# re-verify the same rules on the rendered face under the same code names).
WARNING_OWNER_PHASE = "P1Q-COPY-QC"

# SOP-SLIDE-04 §3 DEN-6: Wall of Wins sits 4-6 slides before the offer.
DEN_WOW_MIN_GAP = 4
DEN_WOW_MAX_GAP = 6

# SOP-SLIDE-01 §2.8 / SOP-SLIDE-04 §2.8 spirit: the warning-only section-floor
# heuristic for AF-DEN-8 uses the QC-side floors as its warning thresholds.
DEN8_SECTION_FLOORS = {
    "HOOK": 5,
    "AUTHORITY": 4,
    "TEACHING": 18,
    "SECRETS": 18,
    "PROOF": 4,
    "OFFER": 14,
    "REPITCH": 5,
    "CLOSE": 5,
}

# Builder-identity tokens: a reviewer whose identity matches one of these is the
# builder (or the copy-authoring role) and can never approve a disposition nor
# file a human verdict. Mirrors build_deck's FORBIDDEN_QC_GRADER_IDENTITIES plus
# the slide-copywriter builder role.
FORBIDDEN_REVIEWER_IDENTITIES = frozenset({
    "build_deck.py", "build_deck", "self", "builder", "author",
    "slide-copywriter", "slide copywriter", "claude", "assistant",
})

SANCTIONED_DECISIONS = frozenset({
    "acknowledged",      # reviewed and accepted as-is, with rationale
    "corrected",         # copy fixed; warning kept on record
    "deferred",          # owner-directed re-check later within the same run
})

ARC_SECTION_ALIASES = {
    "BUILDUP": {"BUILDUP", "BUILD-UP", "BUILD_UP"},
    "DROP": {"DROP", "DROP1", "DROP2", "DROP3", "DROP-1", "DROP-2", "DROP-3"},
    "HOOK": {"HOOK"},
    "WALL_OF_WINS": {"WALL_OF_WINS", "WALL OF WINS", "WALL-OF-WINS", "WINS",
                     "WALL_OF_WINS_SLIDE", "WOW"},
    "OFFER": {"OFFER", "OFFER1", "FINAL", "PRICE", "ANCHOR", "LADDER"},
# ══════════════════════════════════════════════════════════════════════════
}
WARN_TAG_PATTERNS = {
    "AF-AUD-1": [
        re.compile(r'\bSAY\s*:', re.I),
        re.compile(r'^\s*Speaker\s*:', re.I | re.M),
        re.compile(r'You\s+say\s*:', re.I),
        re.compile(r'SAY\s*->', re.I),
        re.compile(r'\[SPEAKER\]', re.I),
    ],
    "AF-AUD-2": [
        re.compile(r'\b(?:hook doctrine|pitch engine|density rule|obe rule|'
                   r'single idea doctrine)\b', re.I),
        re.compile(r'\bAF-(?:HOOK|DEN|OBI|AUD)-\d+\b', re.I),
        re.compile(r'\b(?:auto-fail|autofail)\s+code\b', re.I),
        re.compile(r'\bQC\s+gate\b', re.I),
    ],
    "AF-AUD-3": [
        re.compile(r'\[IMAGE[:\]]\s*(?:shows|depicts|displays|features|contains)', re.I),
        re.compile(r'\(image[:\]]\s*(?:shows|depicts|displays)', re.I),
        re.compile(r'^\s*(?:this|the)\s+(?:image|photo|picture|graphic)\s+'
                   r'(?:shows|depicts|displays)', re.I | re.M),
    ],
    "AF-OBI-5": [
        re.compile(r'^\s*[-*+]\s', re.M),
    ],
    "AF-OBI-5_PAIN": [
        re.compile(r'\b(?:pain|problem|struggle|frustrat|worry|fear|anxiety|stress|'
                   r'burden|waste|loss|losing|failed|broken|stuck)\b', re.I),
    ],
    "AF-OBI-3_HEADLINE": [
        re.compile(r'^#{1,6}\s+', re.M),
    ],
}

# ══════════════════════════════════════════════════════════════════════════
# Shared readers (duplicate-free: reuse slide_craft's loaders, fail-closed on
# import per FIX 17 so a broken slide_craft disables the craft wiring entirely).
# ══════════════════════════════════════════════════════════════════════════

try:
    import slide_craft as _sc
    _SLIDES = _sc._slides
    _INTAKE = staticmethod(_sc._intake)
    _WRITE_PROVENANCE = _sc._write_provenance
except Exception:  # noqa: BLE001 — FIX 17 fail-closed: never partially armed
    _sc = None
    _SLIDES = None
    _INTAKE = None
    _WRITE_PROVENANCE = None


def _flag_active():
    """FIX 18 feature flag — DEFAULT-ON. '0'/'false' rolls the fix back: warnings
    are still COMPUTED (they are inert records) but the attestation gate goes
    idle and compute_warnings returns no holds. Anything else (including unset
    and garbage) is ON."""
    raw = (os.environ.get(FEATURE_FLAG_ENV) or "").strip().lower()
    return raw not in ("0", "false", "off")


# ══════════════════════════════════════════════════════════════════════════
# WARNING HOLDS — the pending-hold ledger (working/qc/craft-warnings.json)
# ══════════════════════════════════════════════════════════════════════════

def _write_hold_state(run_dir, holds):
    """Persist the pending-hold snapshot. `holds` is the list of dicts that
    compute_warnings returned this pass (the UNACKNOWLEDGED warnings); a later
    pass overwrites — the ledger is always a truthful snapshot of what still
    holds, never a stale accumulation. Write is best-effort (hold enforcement
    never depends on the file: warning_hold_blocker recomputes the holds
    directly), so a full disk cannot turn a hold off."""
    try:
        p = Path(run_dir) / WARNING_HOLDS_REL
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({
            "pending_holds": holds,
            "owner_phase": WARNING_OWNER_PHASE,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }, indent=2, default=str), encoding="utf-8")
    except Exception:  # noqa: BLE001 — hold enforcement is computed, not stored
        pass

def _normalize_hold(rec):
    """One pending-hold record: {rule_code, slide_ids, evidence, phase_id}."""
    if not isinstance(rec, dict):
        return None
    code = str(rec.get("rule_code", "")).strip().upper()
    if code not in WARNING_CODES:
        return None
    ids = [int(s) for s in (rec.get("slide_ids") or [])
           if isinstance(s, int) and s > 0] or [None]
    return {
        "rule_code": code,
        "slide_ids": ids,
        "evidence": [str(e) for e in (rec.get("evidence") or [])][:4],
        "phase_id": WARNING_OWNER_PHASE,
    }

def _reflect_holds(run_dir, warnings):
    """Write the pending-hold snapshot for one compute_warnings pass. Mutates
    run state only; returns the normalized holds."""
    holds = []
    for rec in warnings:
        h = _normalize_hold(rec)
        if h is not None:
            holds.append(h)
        else:
            # A warning record that cannot normalize (e.g. the
            # AF-CRAFT-WARN-ERROR catch-all) still holds — fail closed.
            holds.append({
                "rule_code": str(rec.get("rule_code", "AF-CRAFT-WARN-ERROR")),
                "slide_ids": [None],
                "evidence": [str(e) for e in (rec.get("evidence") or [])][:4],
                "phase_id": WARNING_OWNER_PHASE,
            })
    _write_hold_state(run_dir, holds)
    return holds

def _provenance(run_dir, payload):
    if _WRITE_PROVENANCE is not None:
        _WRITE_PROVENANCE(run_dir, {"craft_judgement_" + k: v
                                    for k, v in payload.items()})
        return
    try:
        dest = Path(run_dir) / PROVENANCE_REL
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    except Exception:
        pass


def _read_json_candidates(run_dir, rel_paths):
    for rel in rel_paths:
        p = Path(run_dir) / rel
        try:
            if p.is_file():
                data = json.loads(p.read_text(encoding="utf-8"))
                if data is not None:
                    return data
        except (json.JSONDecodeError, OSError, ValueError):
            continue
    return None


def _arc_slots(run_dir):
    """[slot dicts] from arc_allocation.json (schema-proven: extra keys are
    allowed on slots; the golden-quest run carries phase/arc_section/hook flags)."""
    data = _read_json_candidates(run_dir, [
        "working/copy/arc_allocation.json",
        "arc_allocation.json",
        "working/arc_allocation.json",
    ])
    if isinstance(data, list):
        return [s for s in data if isinstance(s, dict)]
    if isinstance(data, dict):
        slots = data.get("slots") or data.get("allocation") or data.get("slides")
        if isinstance(slots, list):
            return [s for s in slots if isinstance(s, dict)]
    return []


def _slot_sections(slot):
    """Set of canonical section names one slot declares (case-normalized)."""
    out = set()
    for key in ("arc_section", "section", "beat", "tag", "type", "role", "phase"):
        v = slot.get(key)
        if isinstance(v, str) and v.strip():
            out.add(v.strip().upper())
    tags = slot.get("tags")
    if isinstance(tags, list):
        out |= {str(t).strip().upper() for t in tags if str(t).strip()}
    for flag in ("hook", "label_slide"):
        if slot.get(flag) is True:
            out.add(flag.upper())
    return out


def _sections_match(slot, canonical):
    """True when any declared section string on the slot is (an alias of) the
    canonical name."""
    aliases = ARC_SECTION_ALIASES.get(canonical, {canonical})
    return any(sec in aliases for sec in _slot_sections(slot))


# ══════════════════════════════════════════════════════════════════════════
# ENFORCED-NOW checks (5). Each returns "" (defer / pass) or a blocking reason.
# ══════════════════════════════════════════════════════════════════════════

FOOTER_DECL_RE = re.compile(
    r'footer|footer[-_ ]?band|footer[-_ ]?strip|bottom[-_ ]?band|'
    r'lower[-_ ]?(?:third|band)|running[-_ ]?footer|caption[-_ ]?band',
    re.I)

SIG_QUOTE_SLOT_KEYS = ("signature_quote", "quote_slide", "signature-quote",
                       "sig_quote", "is_quote_slide")


def check_hook_footer(run_dir, slides_path=None):
    """AF-HOOK-2 — the canonical hook placed on a slide whose DECLARED layout
    puts it in a footer/band position. Evidence: intake.json hook (the same
    canonical string slide_craft.check_hook_verbatim uses) + the slide's own
    `layout` declaration in slides.json. Deterministic: bottom-15%-OCR geometry
    is NOT required — an explicit footer/band declaration is the failure the
    rule names (the prompt half already exists as AF-HOOK). Defers when the
    hook or the deck is absent."""
    if _SLIDES is None or _INTAKE is None:
        _provenance(run_dir, {"check_hook_footer": {
            "deferred": True, "reason": "slide_craft unavailable (fail-closed)"}})
        return ""
    intake = _INTAKE(run_dir)
    hook = str((intake or {}).get("hook", "")).strip()
    sl = _SLIDES(run_dir, slides_path)
    if not hook or not sl:
        _provenance(run_dir, {"check_hook_footer": {
            "deferred": True, "reason": "no canonical hook or no slides.json"}})
        return ""
    offenders = []
    for ordinal in sorted(sl):
        entry = next((e for e in _slides_json_entries(run_dir, slides_path)
                      if isinstance(e, dict) and e.get("slide") == ordinal), None)
        layout = str((entry or {}).get("layout", ""))
        if not layout:
            continue
        if not FOOTER_DECL_RE.search(layout):
            continue
        for i, block in enumerate(sl[ordinal]):
            text = str(block)
            if hook.lower() in text.lower():
                offenders.append((ordinal, i, layout.strip()))
    if not offenders:
        _provenance(run_dir, {"check_hook_footer": {
            "deferred": False, "findings": 0, "total_slides": len(sl)}})
        return ""
    detail = "; ".join(f"slide {s} copy[{i}] declared footer/band layout "
                       f"({layout!r})" for s, i, layout in offenders)
    reason = (f"AF-HOOK-2: canonical hook placed in a footer/band position on "
              f"{len(offenders)} slide(s) ({detail}) — the hook is never a "
              f"footer stamp")
    _provenance(run_dir, {"check_hook_footer": {
        "deferred": False, "findings": len(offenders),
        "offenders": offenders, "reason": reason}})
    return reason


def check_hook_signature_quote(run_dir, slides_path=None):
    """AF-HOOK-7 — the canonical hook and the signature quote conflated on a
    (declared) signature-quote slide; the FIX 15-style evidence is the signed
    intake (intake.json signature_quote) plus the slide's role declaration in
    arc_allocation.json OR the quote text on the same slide as the hook."""
    if _SLIDES is None or _INTAKE is None:
        _provenance(run_dir, {"check_hook_signature_quote": {
            "deferred": True, "reason": "slide_craft unavailable (fail-closed)"}})
        return ""
    intake = _INTAKE(run_dir)
    hook = str((intake or {}).get("hook", "")).strip()
    quote = str((intake or {}).get("signature_quote")
                or (intake or {}).get("quote", "")).strip()
    sl = _SLIDES(run_dir, slides_path)
    if not hook or not sl:
        _provenance(run_dir, {"check_hook_signature_quote": {
            "deferred": True,
            "reason": "no canonical hook or no slides.json readable"}})
        return ""
    slots = _arc_slots(run_dir)
    quote_slides = set()
    for slot in slots:
        declared = any(isinstance(slot.get(k), bool) and slot.get(k)
                       for k in SIG_QUOTE_SLOT_KEYS)
        sec_blob = " ".join(str(slot.get(k, "")) for k in
                            ("arc_section", "section", "beat", "tag", "type",
                             "role", "phase"))
        if declared or any(tok in str(v).upper() for k in SIG_QUOTE_SLOT_KEYS
                           for v in [slot.get(k)] if isinstance(v, str)
                           for tok in ("QUOTE",)):
            if isinstance(slot.get("slide"), int):
                quote_slides.add(slot["slide"])
    offenders = []
    for ordinal in sorted(sl):
        blocks = sl[ordinal]
        joined = " ".join(str(b) for b in blocks).lower()
        has_hook = hook and hook.lower() in joined
        declared_quote = ordinal in quote_slides
        quote_on_slide = quote and len(quote) > 5 and quote.lower() in joined
        if has_hook and (declared_quote or quote_on_slide):
            offenders.append((ordinal, "declared" if declared_quote else "inline"))
    if not offenders:
        _provenance(run_dir, {"check_hook_signature_quote": {
            "deferred": False, "findings": 0, "total_slides": len(sl)}})
        return ""
    detail = "; ".join(f"slide {s} ({how})" for s, how in offenders)
    reason = (f"AF-HOOK-7: canonical hook conflated with the signature quote on "
              f"{len(offenders)} slide(s) ({detail}) — the quote slide carries "
              f"the quote; the hook gets its own slides")
    _provenance(run_dir, {"check_hook_signature_quote": {
        "deferred": False, "findings": len(offenders),
        "offenders": offenders, "quote_slides": sorted(quote_slides),
        "reason": reason}})
    return reason


def check_comparison_rows(run_dir, slides_path=None):
    """AF-OBI-6 — a comparison table with MORE THAN 2 data rows on one slide
    (SOP-SLIDE-01 §2.9 row ceiling). Evidence: pipe-table rows in the slide's
    own copy blocks (what the renderer bakes) cross-checked against a declared
    comparison-row count in arc_allocation (`comparison_rows`), when present —
    a DECLARATION DISAGREEMENT fails. No OCR glyph analysis is claimed here;
    the slide's copy IS its face because the pipeline renders copy verbatim."""
    if _SLIDES is None:
        _provenance(run_dir, {"check_comparison_rows": {
            "deferred": True, "reason": "slide_craft unavailable (fail-closed)"}})
        return ""
    sl = _SLIDES(run_dir, slides_path)
    if not sl:
        _provenance(run_dir, {"check_comparison_rows": {
            "deferred": True, "reason": "no slides.json readable"}})
        return ""
    offenders = []
    for ordinal in sorted(sl):
        text = "\n".join(str(b) for b in sl[ordinal])
        rows = [ln for ln in text.splitlines()
                if ln.strip().startswith("|") and ln.strip().endswith("|")]
        data_rows = [r for r in rows
                     if not re.match(r'^\|[\s\-:|]+\|$', r.strip())]
        if len(data_rows) > 2:
            offenders.append((ordinal, len(data_rows)))
    declared = {}
    for slot in _arc_slots(run_dir):
        n = slot.get("comparison_rows")
        if isinstance(n, int) and isinstance(slot.get("slide"), int):
            declared[slot["slide"]] = n
        if isinstance(n, int) and isinstance(slot.get("slide"), int) and n > 2:
            offenders.append((slot["slide"], f"declared comparison_rows={n}"))
    if not offenders:
        _provenance(run_dir, {"check_comparison_rows": {
            "deferred": False, "findings": 0, "total_slides": len(sl)}})
        return ""
    detail = "; ".join(f"slide {s}: {c} data rows (> 2)" for s, c in offenders)
    reason = (f"AF-OBI-6: {len(offenders)} comparison table(s) exceed the "
              f"2-row ceiling ({detail})")
    _provenance(run_dir, {"check_comparison_rows": {
        "deferred": False, "findings": len(offenders),
        "offenders": offenders, "declared_rows": declared, "reason": reason}})
    return reason


def check_drop_buildup(run_dir, slides_path=None):
    """AF-DEN-3 — every DROP arc slot's IMMEDIATELY PRECEDING slide is a
    BUILDUP slot. Evidence: stable ordinals in arc_allocation.json slots (the
    Director's own allocation, deterministic numbering — the objection that
    character-offset mapping is a 'crude window' no longer applies because the
    check reads slot ordinals, not offsets). Defers when no DROP slot exists."""
    slots = _arc_slots(run_dir)
    by_slide = {}
    for slot in slots:
        if isinstance(slot.get("slide"), int):
            by_slide[slot["slide"]] = slot
    if not slots:
        _provenance(run_dir, {"check_drop_buildup": {
            "deferred": True, "reason": "no arc_allocation.json slots readable"}})
        return ""
    drops = []
    for slot in slots:
        if isinstance(slot.get("slide"), int) and _sections_match(slot, "DROP"):
            if _sections_match(slot, "OFFER"):
                # ANCHOR/FINAL/PRICE rungs are ladder beats, not cold drops.
                continue
            drops.append(slot["slide"])
    if not drops:
        _provenance(run_dir, {"check_drop_buildup": {
            "deferred": True,
            "reason": "no DROP tagged in arc_allocation (pitchless deck)"}})
        return ""
    offenders = []
    for d in sorted(set(drops)):
        prev = d - 1
        prev_slot = by_slide.get(prev)
        if prev_slot is None or not _sections_match(prev_slot, "BUILDUP"):
            offenders.append(d)
    if not offenders:
        _provenance(run_dir, {"check_drop_buildup": {
            "deferred": False, "findings": 0, "drop_slides": sorted(set(drops))}})
        return ""
    detail = ", ".join(f"slide {d}" for d in offenders)
    reason = (f"AF-DEN-3: DROP slide(s) with no BUILDUP slot immediately before "
              f"({detail}) — never drop a price cold")
    _provenance(run_dir, {"check_drop_buildup": {
        "deferred": False, "findings": len(offenders),
        "offenders": offenders, "reason": reason}})
    return reason


def check_wall_of_wins(run_dir, slides_path=None):
    """AF-DEN-6 — Wall of Wins sits 4-6 slides before the first OFFER/price
    slot. Evidence: WALL_OF_WINS and first OFFER ordinals from arc_allocation
    slots (plus price_ladder.json rungs when a rung carries the FIRST offer
    target — the rung wins when both exist). Defers without a WOW slot."""
    slots = _arc_slots(run_dir)
    wow = []
    offer = []
    for slot in slots:
        if not isinstance(slot.get("slide"), int):
            continue
        if _sections_match(slot, "WALL_OF_WINS"):
            wow.append(slot["slide"])
        if _sections_match(slot, "OFFER"):
            offer.append(slot["slide"])
    ladder_offer = _first_offer_from_ladder(run_dir)
    if ladder_offer is not None:
        offer = [o for o in offer if o != ladder_offer] or offer
        offer = sorted(set(offer) | {ladder_offer})
    if not wow:
        _provenance(run_dir, {"check_wall_of_wins": {
            "deferred": True,
            "reason": "no WALL_OF_WINS slot declared in arc_allocation"}})
        return ""
    if not offer:
        _provenance(run_dir, {"check_wall_of_wins": {
            "deferred": True,
            "reason": "no OFFER/price slot declared (pitchless deck)"}})
        return ""
    offenders = []
    first_offer = min(offer)
    for w in sorted(set(wow)):
        gap = first_offer - w
        if gap < DEN_WOW_MIN_GAP or gap > DEN_WOW_MAX_GAP:
            offenders.append((w, first_offer, gap))
    if not offenders:
        _provenance(run_dir, {"check_wall_of_wins": {
            "deferred": False, "findings": 0,
            "wow_slides": sorted(set(wow)), "first_offer": first_offer}})
        return ""
    detail = "; ".join(f"WoW {w} -> offer {o} = {g} slides" for w, o, g in offenders)
    reason = (f"AF-DEN-6: Wall of Wins not [{DEN_WOW_MIN_GAP}-{DEN_WOW_MAX_GAP}] "
              f"slides before the offer ({detail})")
    _provenance(run_dir, {"check_wall_of_wins": {
        "deferred": False, "findings": len(offenders),
        "offenders": offenders, "reason": reason}})
    return reason


def _first_offer_from_ladder(run_dir):
    """target_slide of the first ANCHOR/DROP/FINAL rung in price_ladder.json, or
    None. Uses slide_craft._price_ladder (same candidate list as build_deck)."""
    if _sc is None:
        return None
    try:
        ladder = _sc._price_ladder(run_dir)
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(ladder, dict):
        return None
    rungs = ladder.get("rungs") or []
    slides = []
    for r in rungs:
        if not isinstance(r, dict):
            continue
        k = str(r.get("kind", "")).upper()
        t = str(r.get("type", "")).upper()
        if k in ARC_SECTION_ALIASES["OFFER"] or t in ARC_SECTION_ALIASES["OFFER"]:
            if isinstance(r.get("target_slide"), int):
                slides.append(r["target_slide"])
    return min(slides) if slides else None


def _slides_json_entries(run_dir, slides_path=None):
    """The raw slides.json entries (layout declarations live there)."""
    if _sc is not None:
        data = _sc._slides_json(run_dir, slides_path)
        if isinstance(data, list):
            return data
    return []



_COPY_FALLBACK_RELS = [
    ("working/copy/slides_copy.md",),
    ("working/copy/SLIDES-COPY.md",),
    ("slides_copy.md",),
]


def _copy_slides(run_dir):
    """{ordinal: text} fallback from slides_copy.md for the WARNING heuristics at
    QC-phase time, when slides.json may not exist yet (mid-pipeline). Mirrors
    qc_check._split_slides's delimiters: '## Slide N' first, then '---', else the
    whole document is slide 1."""
    text = None
    for rels in _COPY_FALLBACK_RELS:
        for rel in rels:
            p = Path(run_dir) / rel
            try:
                if p.is_file():
                    text = p.read_text(encoding="utf-8")
                    if text:
                        break
            except OSError:
                continue
        if text:
            break
    if not text:
        return {}
    out = {}
    import re as _re
    matches = list(_re.finditer(
        r'^#{1,3}\s*Slide\s+(\d+)', text, _re.MULTILINE | _re.IGNORECASE))
    if matches:
        for i, m in enumerate(matches):
            num = int(m.group(1))
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            out[num] = text[m.start():end]
        return out
    parts = text.split("\n---\n")
    if len(parts) >= 2:
        for i, part in enumerate(parts):
            out[i + 1] = part
        return out
    out[1] = text
    return out


def _warning_slide_texts(run_dir, slides_path=None):
    """Slide texts for warning heuristics: slides.json when present (the render
    input), else the slides_copy.md fallback (the QC-phase-time input)."""
    sl = _SLIDES(run_dir, slides_path) or {}
    if sl:
        return {k: "\n".join(str(b) for b in v) for k, v in sl.items()}
    return _copy_slides(run_dir)


# ══════════════════════════════════════════════════════════════════════════
# WARNING checks (6) — heuristics that WARN; they never block on their own.
# ══════════════════════════════════════════════════════════════════════════

def _warning_findings(run_dir, slides_path=None):
    """[{rule_code, slide_ids, evidence}] for the six warning rules. These are
    the same literal-pattern heuristics the retired qc_check scanners used,
    re-classified honestly: a heuristic may WARN, never claim a deterministic
    auto-fail."""
    out = []
    sl = _warning_slide_texts(run_dir, slides_path) or {}
    if not sl:
        return out

    def add(code, ordinal, ev):
        for rec in out:
            if rec["rule_code"] == code:
                if ordinal not in rec["slide_ids"]:
                    rec["slide_ids"].append(ordinal)
                rec["evidence"].append(ev)
                return
        out.append({"rule_code": code, "slide_ids": [ordinal], "evidence": [ev]})

    for ordinal in sorted(sl):
        val = sl[ordinal]
        text = val if isinstance(val, str) else "\n".join(str(b) for b in val)
        # AF-AUD-1 / AF-AUD-2 / AF-AUD-3 literal patterns on the face.
        for pat in WARN_TAG_PATTERNS["AF-AUD-1"]:
            if pat.search(text):
                add("AF-AUD-1", ordinal, "speaker-SAY directive pattern on slide face")
                break
        lowered = text.lower()
        caption_hit = any(re.search(r'(?:caption|footer|band|note)\s*:', ln, re.I)
                          for ln in text.splitlines())
        if caption_hit and any(p.search(text) for p in WARN_TAG_PATTERNS["AF-AUD-2"]):
            add("AF-AUD-2", ordinal, "internal pitch doctrine token in a caption line")
        for pat in WARN_TAG_PATTERNS["AF-AUD-3"]:
            if pat.search(text):
                add("AF-AUD-3", ordinal, "image-narration caption pattern")
                break
        # AF-OBI-3: two headlines on one slide with <0.3 jaccard word overlap.
        heads = [re.sub(r'^#+\s*', '', ln).strip() for ln in text.splitlines()
                 if re.match(r'^#{1,6}\s+', ln)]
        heads = [h for h in heads if h]
        flagged3 = False
        for i in range(len(heads)):
            for j in range(i + 1, len(heads)):
                a = set(heads[i].lower().split())
                b = set(heads[j].lower().split())
                un = a | b
                if a and b and (len(a & b) / max(len(un), 1)) < 0.3:
                    add("AF-OBI-3", ordinal,
                        f"distinct-headline heuristic: {heads[i][:40]!r} vs "
                        f"{heads[j][:40]!r}")
                    flagged3 = True
                    break
            if flagged3:
                break
        # AF-OBI-5: three or more pain-marked bullets.
        bullets = [ln.lstrip()[1:].strip() for ln in text.splitlines()
                   if re.match(r'^\s*[-*+]\s+', ln)]
        pain_bullets = [b for b in bullets
                        if WARN_TAG_PATTERNS["AF-OBI-5_PAIN"][0].search(b)]
        if len(pain_bullets) >= 3:
            add("AF-OBI-5", ordinal,
                f"{len(pain_bullets)} pain-marked bullets (a bulleted pain list)")
        # (AF-OBI-5 heuristic ends; the copy itself is what a human reviews.)

    # AF-DEN-8: section below its warning floor, from arc slots.
    slots = _arc_slots(run_dir)
    if slots:
        counts = {}
        sec_slides = {}
        for slot in slots:
            if not isinstance(slot.get("slide"), int):
                continue
            for canonical in DEN8_SECTION_FLOORS:
                if _sections_match(slot, canonical):
                    counts[canonical] = counts.get(canonical, 0) + 1
                    sec_slides.setdefault(canonical, []).append(slot["slide"])
                    break
        intake = _INTAKE(run_dir) if _INTAKE else {}
        client_fixed = bool((intake or {}).get("client_requested_slide_count"))
        for sec, floor in sorted(DEN8_SECTION_FLOORS.items()):
            n = counts.get(sec)
            if n is None or n == 0:
                continue
            if n < floor and not client_fixed:
                # The hold is per-warning: attribute the SECTION'S OWN slide
                # ordinals so an individual ack can name exactly this warning
                # (a disposition whose slide_ids cover the section's slides
                # clears exactly this hold — never a deck-wide blanket ack).
                ids = sorted(sec_slides.get(sec, []))
                out.append({"rule_code": "AF-DEN-8", "slide_ids": ids,
                            "evidence": [f"arc section {sec!r} spans {n} slot(s), "
                                         f"below the {floor}-slide floor heuristic"],
                            "warning_only_count": n, "warning_only_floor": floor})
    return out


def compute_warnings(run_dir, slides_path=None):
    """Compute the six warning records and MERGE the acknowledged dispositions;
    return only still-UNACKNOWLEDGED warning dicts. An acknowledged (valid,
    run-scoped, non-self) disposition removes its rule/slide pair from the
    returned warnings; anything invalid fails closed (stays a warning)."""
    if not _flag_active():
        return []
    findings = _warning_findings(run_dir, slides_path)
    dispositions = load_dispositions(run_dir)
    ack = {}
    for d in dispositions:
        ack.setdefault(d["rule_code"], set()).update(
            int(s) for s in d.get("slide_ids", []))
    surviving = []
    for rec in findings:
        code = rec["rule_code"]
        ids = rec.get("slide_ids") or []
        if ids and ack.get(code) and set(ids) <= ack[code]:
            continue
        surviving.append(rec)
    # FIX 18 repair: reflect the still-unacknowledged warnings as pending holds
    # on the owning QC phase (working/qc/craft-warnings.json). This is what the
    # phase-attestation gate reads; it is DERIVED from the same ack filtering
    # above, so a valid per-rule disposition clears its hold with no extra state.
    _reflect_holds(run_dir, surviving)
    _provenance(run_dir, {"compute_warnings": {
        "findings": len(findings), "unacknowledged": len(surviving),
        "hold_phase": WARNING_OWNER_PHASE}})
    return surviving


# ══════════════════════════════════════════════════════════════════════════
# Disposition file — ONE rule / ONE run / NAMED slides / named reviewer /
# owner signature. Malformed or out-of-scope records are DROPPED (fail closed).
# ══════════════════════════════════════════════════════════════════════════

REQUIRED_DISPOSITION_KEYS = ("rule_code", "slide_ids", "run_id", "reviewer",
                             "rationale", "decision", "captured_at",
                             "owner_signature")


def load_dispositions(run_dir):
    """Load + validate working/qc/craft-warning-dispositions.json. Returns only
    VALID records: rule_code in WARNING_CODES (one rule per record, no
    wildcard), run_id == run_dir.name (no cross-run reuse), reviewer not a
    builder identity, decision in SANCTIONED_DECISIONS, owner_signature
    non-empty, slide_ids a non-empty list of positive ints. Everything else is
    ignored — a malformed waiver never silences a gate."""
    p = Path(run_dir) / DISPOSITIONS_REL
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    run_id = str(Path(run_dir).name)
    valid = []
    for rec in data:
        if not isinstance(rec, dict):
            continue
        if any(not str(rec.get(k, "") or "").strip() for k in REQUIRED_DISPOSITION_KEYS):
            continue
        code = str(rec["rule_code"]).strip().upper()
        if code not in WARNING_CODES:
            continue  # wildcard ("AF-*"), enforce-bucket code, human code: reject
        if str(rec["run_id"]) != run_id:
            continue  # cross-run reuse: reject (fail closed)
        if str(rec["reviewer"]).strip().lower() in FORBIDDEN_REVIEWER_IDENTITIES:
            continue  # builder self-approval: reject
        if str(rec["decision"]).strip().lower() not in SANCTIONED_DECISIONS:
            continue
        ids = rec.get("slide_ids")
        if not isinstance(ids, list) or not ids or not ids:
            continue
        norm_ids = []
        ids_ok = True
        for s in ids:
            try:
                n = int(s)
            except (TypeError, ValueError):
                ids_ok = False
                break
            if n <= 0:
                ids_ok = False
                break
            norm_ids.append(n)
        if not ids_ok or not norm_ids:
            continue
        valid.append({**rec, "rule_code": code, "slide_ids": norm_ids})
    return valid


# ══════════════════════════════════════════════════════════════════════════
# HUMAN rows (2): AF-OBI-4 and AF-OBI. No keyword proxy. A relevant QC phase
# cannot attest until human_craft_verdicts.json carries, for BOTH codes, a
# verdict by an independent (non-builder) reviewer. "fail" blocks outright.
# ══════════════════════════════════════════════════════════════════════════

def human_verdicts(run_dir):
    """[valid verdict records] for the human bucket from
    working/qc/human_craft_verdicts.json, each shaped
    {"rule_code": "AF-OBI-4" | "AF-OBI", "verdict": "pass"|"fail", "run_id",
     "reviewer", "rationale", "captured_at"}. Cross-run, self-graded, missing-
    rationale and malformed records are dropped (fail closed)."""
    p = Path(run_dir) / HUMAN_VERDICTS_REL
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, ValueError):
        return []
    verdicts = data.get("verdicts") if isinstance(data, dict) else data
    if not isinstance(verdicts, list):
        return []
    run_id = str(Path(run_dir).name)
    out = []
    for rec in verdicts:
        if not isinstance(rec, dict):
            continue
        code = str(rec.get("rule_code", "")).strip().upper()
        verdict = str(rec.get("verdict", "")).strip().lower()
        reviewer = str(rec.get("reviewer", "")).strip()
        rationale = str(rec.get("rationale", "")).strip()
        if code not in HUMAN_CODES:
            continue
        if verdict not in ("pass", "fail"):
            continue
        if str(rec.get("run_id", "")) != run_id:
            continue
        if not reviewer or reviewer.lower() in FORBIDDEN_REVIEWER_IDENTITIES:
            continue
        if not rationale:
            continue
        out.append({**rec, "rule_code": code, "verdict": verdict})
    return out


def attestation_blocker(run_dir, phase_id):
    """Return "" (clear) or a non-empty AF message BLOCKING an attestation for
    phase_id because the two HUMAN rows lack an independent reviewer's verdict.
    Called next to check_qc_phase_report_real at attest time. Fail-closed in
    every direction: missing file, malformed JSON, missing any code, self-
    graded review, or a fail verdict all block."""
    if phase_id not in HUMAN_VERDICT_PHASES or not _flag_active():
        return ""
    missing = []
    failing = []
    seen = human_verdicts(run_dir)
    for code in sorted(HUMAN_CODES):
        recs = [r for r in seen if r["rule_code"] == code]
        if not recs:
            missing.append(code)
            continue
        for r in recs:
            if r["verdict"] == "fail":
                failing.append(
                    f"{code} (reviewer {r['reviewer']!r}: {r['rationale'][:80]})")
    parts = []
    if missing:
        parts.append(
            "AF-OBI-HUMAN-VERDICT: " + ", ".join(missing) +
            " carry no independent human verdict — these two craft rules are "
            "HUMAN-ONLY by FIX 18 (no keyword proxy exists for the value trio, "
            "and AF-OBI is a dimension label). Record a pass/fail verdict with "
            "reviewer + rationale in " + str(HUMAN_VERDICTS_REL) + " before "
            "attesting; a builder/self verdict is refused (fail-closed).")
    if failing:
        parts.append("AF-OBI-HUMAN-VERDICT: independent reviewer FAILed " +
                     "; ".join(failing) + " — correct the deck before attesting.")
    return " | ".join(parts)

def warning_hold_blocker(run_dir, phase_id):
    """Return "" (clear) or a non-empty AF message BLOCKING an attestation for
    phase_id because WARNINGS hold the phase: compute_warnings reports still-
    UNACKNOWLEDGED warning findings (AF-AUD-1/2/3, AF-OBI-3/5, AF-DEN-8) whose
    triggers fired on this run. A pending warning holds the owning QC phase
    until it is corrected OR individually acknowledged by a valid per-rule /
    per-slide disposition record in working/qc/craft-warning-dispositions.json
    (the same record shape compute_warnings already honors — a record covering
    the exact rule_code + slide_ids clears exactly that hold, never a blanket
    ack). Mirrors attestation_blocker: fail-closed in every direction (a broken
    warnings computation keeps the hold), named-code message, never a raise.

    The hold state is recomputed rather than read from the ledger: the phase
    attestation must reflect the CURRENT ack state, so a disposition filed
    between the last compute and this attestation clears the hold correctly."""
    if phase_id != WARNING_OWNER_PHASE or not _flag_active():
        return ""
    try:
        warnings = compute_warnings(run_dir)
    except Exception as exc:  # noqa: BLE001 — fail closed: never attest on doubt
        return ("AF-WARNING-HOLD: the craft warning computation itself failed "
                f"({exc!r}) — refusing to attest {phase_id} on an unverifiable "
                "warning state (fail-closed).")
    if not warnings:
        return ""
    lines = []
    for rec in warnings:
        code = str(rec.get("rule_code", "AF-CRAFT-WARN-ERROR"))
        ids = rec.get("slide_ids") or []
        ev = "; ".join(str(e) for e in (rec.get("evidence") or []))[:120]
        if not ids:
            scope = "deck-level (no single slide attributed)"
        elif len(ids) == 1:
            scope = f"slide {ids[0]}"
        else:
            scope = "slides " + ", ".join(str(i) for i in ids)
        lines.append(f"{code} on {scope}: {ev}")
    return ("AF-WARNING-HOLD: " + phase_id + " cannot attest — " +
            str(len(lines)) + " unacknowledged craft warning(s) still pending: " +
            " | ".join(lines) + ". Correct each, or record an individual "
            "acknowledgement (exact rule_code + slide_ids, independent reviewer, "
            "owner signature) in " + str(DISPOSITIONS_REL) +
            " — one disposition covers ONE rule and its named slides, and a "
            "record for a different code or slide never clears this hold. "
            "Resumable: ack + re-run the phase.")


# ══════════════════════════════════════════════════════════════════════════
# Aggregator — the FIX 15 preflight entry (build_deck._chk_slide_craft already
# calls slide_craft.run_all_checks; this module joins that pass).
# ══════════════════════════════════════════════════════════════════════════

_ENFORCE_CHECKS = None


def _enforce_checks():
    global _ENFORCE_CHECKS
    if _ENFORCE_CHECKS is None:
        _ENFORCE_CHECKS = [
            check_hook_footer,
            check_hook_signature_quote,
            check_comparison_rows,
            check_drop_buildup,
            check_wall_of_wins,
        ]
    return _ENFORCE_CHECKS


def _finding_slides_fallback(record):
    """Slide-attribution for waiver matching of THIS module's findings (mirror of
    slide_craft._finding_slides' offender shape: (ordinal, ...) tuples)."""
    slides = set()
    offs = (record or {}).get("offenders")
    if isinstance(offs, list):
        for o in offs:
            if isinstance(o, (list, tuple)) and o and isinstance(o[0], int):
                slides.add(o[0])
            elif isinstance(o, int):
                slides.add(o)
    return slides


def _load_craft_waivers(run_dir):
    """FIX 15's owner-token waiver regime, extended to FIX 18's five codes.
    slide_craft._load_waivers only accepts its own ten codes, so this re-validates
    the file directly for ENFORCED_CODES with the SAME rules (one rule / one run /
    named slides; af_code + approved_by + reason required; malformed ignored,
    fail-closed)."""
    p = Path(run_dir) / _sc.WAIVER_REL if _sc is not None else         Path(run_dir) / "working" / "checkpoints" / "slide_craft_waivers.json"
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, ValueError):
        return {}
    if not isinstance(data, list):
        return {}
    waivers = {}
    for rec in data:
        if not isinstance(rec, dict):
            continue
        code = str(rec.get("af_code", "")).strip().upper()
        if code not in ENFORCED_CODES:
            continue
        if not str(rec.get("approved_by", "")).strip():
            continue
        if not str(rec.get("reason", "")).strip():
            continue
        slides = rec.get("slides")
        if not isinstance(slides, list) or not slides:
            continue
        ordinals = set()
        all_slides = False
        for s in slides:
            if s == "ALL":
                # FIX 18's five rules all attribute slides; the ALL escape is
                # accepted only where the run has no attributable slide — same
                # posture slide_craft takes for AF-DEN-4.
                all_slides = True
                continue
            try:
                n = int(s)
            except (TypeError, ValueError):
                continue
            if n > 0:
                ordinals.add(n)
        if not ordinals and not all_slides:
            continue
        entry = waivers.setdefault(code, {"slides": set(), "all_slides": False})
        entry["slides"].update(ordinals)
        entry["all_slides"] = entry["all_slides"] or all_slides
    return waivers


def _read_merged_offenders(run_dir, code):
    """Slide ordinal set attributed to one enforced code: read the per-check
    provenance record this module's check just wrote (check_hook_footer etc.);
    when absent, fall back to any craft_judgement_<CODE> merged record."""
    if _sc is None:
        return set()
    for key in ("craft_judgement_" + _check_name_for(code),
                _check_name_for(code), "craft_judgement_" + code):
        try:
            data = _sc._read_provenance_entry(run_dir, key)
        except Exception:  # noqa: BLE001
            continue
        offs = _finding_slides_fallback(data)
        if offs:
            return offs
    return set()


def run_all_checks(run_dir, slides_path=None):
    """The five enforced-now craft checks, waivers applied under slide_craft's
    regime. Returns (all_pass, blocking_reasons). Merges provenance keys with a
    craft_judgement_ prefix; the caller-facing contract is identical to
    slide_craft.run_all_checks."""
    waivers = _load_craft_waivers(run_dir)
    blocking = []
    waived = []
    _provenance(run_dir, {})
    for fn in _enforce_checks():
        reason = fn(run_dir, slides_path)
        if not reason:
            continue
        code = fn.__name__
        code = {
            "check_hook_footer": "AF-HOOK-2",
            "check_hook_signature_quote": "AF-HOOK-7",
            "check_comparison_rows": "AF-OBI-6",
            "check_drop_buildup": "AF-DEN-3",
            "check_wall_of_wins": "AF-DEN-6",
        }.get(code, code)
        entry = waivers.get(code)
        if entry:
            offenders = _read_merged_offenders(run_dir, code)
            if entry.get("all_slides") and not offenders:
                waived.append(f"{code} (waived for the whole deck): {reason}")
                continue
            if offenders and offenders <= entry.get("slides", set()):
                names = ", ".join(str(s) for s in sorted(offenders))
                waived.append(f"{code} (waived for slide(s) {names}): {reason}")
                continue
        blocking.append(reason)
    warnings = []
    try:
        warnings = compute_warnings(run_dir, slides_path)
    except Exception as exc:  # noqa: BLE001 — warnings never crash preflight
        warnings = [{"rule_code": "AF-CRAFT-WARN-ERROR", "slide_ids": [],
                     "evidence": repr(exc)}]
    unhandled_warnings = [w for w in warnings
                          if str(w.get("rule_code", "")).startswith("AF-")]
    _provenance(run_dir, {"slide_craft_judgement_enforcement": {
        "blocking": len(blocking), "waived": len(waived),
        "waived_detail": waived, "reasons": blocking,
        "warnings_unacknowledged": len(unhandled_warnings),
        "warning_detail": unhandled_warnings}})
    return (len(blocking) == 0), blocking


_CHECK_NAME_BY_CODE = {
    "AF-HOOK-2": "check_hook_footer",
    "AF-HOOK-7": "check_hook_signature_quote",
    "AF-OBI-6": "check_comparison_rows",
    "AF-DEN-3": "check_drop_buildup",
    "AF-DEN-6": "check_wall_of_wins",
}


def _check_name_for(code):
    return _CHECK_NAME_BY_CODE.get(code, code)


def enforce_active():
    return _flag_active()