#!/usr/bin/env python3
# =============================================================================
# SKILL 50 — EMAIL ENGINE :: THE FLOOR PROVER
# -----------------------------------------------------------------------------
# DETERMINISTIC, NO-AI, FAIL-CLOSED prover (Python stdlib only). Cloned in
# spirit from the Presentations deterministic stripped-length prover pattern
# (build_deck.py) and Skill 51's prove_sp_intake.py: every SACRED rule below is
# fail-closed — a violating email/sequence/brief is NOT accepted and NOT
# unlocked for deploy. A violation is sys.exit(2) with a named AF-EMAIL-* code.
# No network, no model judgement, no third-party imports. It runs identically on
# every box (operator or client); it never touches a provider.
#
# WHAT THIS ENFORCES — the SACRED IP from SOURCE-EMAIL-CORPUS.md:
#   * Framework set — framework is one of the 13 canonical ids; a supplied
#     sections[] must match the framework's declared part count.
#   * Buyer-type -> email# -> framework map (12-email) + landing-page map (10-email).
#   * Sequence lengths — landing=10, high-ticket/buyer-type=12; slots contiguous.
#   * Objective validity — exactly one of the 4 objectives.
#   * Persona-style validity + NEVER named/quoted.
#   * Subject count (exactly 2), preview count (C&F=1 / HT=2), subject char band,
#     first-name placement, word band (150-300, 3-B < 150), CTA count, formatting,
#     founder signature (no placeholder), high-ticket disruptive element.
#   * Process integrity — a signed certificate is required before deploy.
#   * Intake gate — one-block delivery, matching skill type, complete brief.
#
# INPUT SHAPES (auto-detected; forced with --kind):
#   * single email   — object with body + subjects (no emails[]).
#   * sequence ledger — object with emails[] (+ sequence_type, founder_name,
#                       process_certificate, deploy_requested).
#   * intake / brief  — object with answers{} / asked_all_at_once (no emails/body).
#
# EXIT CODES:
#   0  PASS      — every SACRED rule satisfied.
#   2  AUTOFAIL  — one or more AF-EMAIL-* / AF-PROCESS-INTEGRITY violations.
#   3  USAGE/IO  — missing file, unreadable/invalid JSON (still fail-closed).
#
# USAGE:
#   python3 prove-email.py <emails.json | email.json | brief.json> [--json] [--kind K]
#   python3 prove-email.py --self-test
# =============================================================================
"""Fail-closed deterministic floor prover for the Email Engine (Skill 50)."""

import argparse
import json
import re
import sys
from pathlib import Path

# ---- exit codes -------------------------------------------------------------
EXIT_PASS = 0
EXIT_AUTOFAIL = 2
EXIT_USAGE = 3

# ---- autofail codes (verbatim; documented in EMAIL-MANIFEST.json) -----------
AF_FRAMEWORK_UNKNOWN = "AF-EMAIL-FRAMEWORK-UNKNOWN"
AF_FRAMEWORK_INCOMPLETE = "AF-EMAIL-FRAMEWORK-INCOMPLETE"
AF_BUYERTYPE_MAP = "AF-EMAIL-BUYERTYPE-MAP"
AF_SEQUENCE_MAP = "AF-EMAIL-SEQUENCE-MAP"
AF_SEQUENCE_LENGTH = "AF-EMAIL-SEQUENCE-LENGTH"
AF_OBJECTIVE_INVALID = "AF-EMAIL-OBJECTIVE-INVALID"
AF_PERSONA_INVALID = "AF-EMAIL-PERSONA-INVALID"
AF_PERSONA_NAMED = "AF-EMAIL-PERSONA-NAMED"
AF_SUBJECT_COUNT = "AF-EMAIL-SUBJECT-COUNT"
AF_PREVIEW_COUNT = "AF-EMAIL-PREVIEW-COUNT"
AF_WORDBAND = "AF-EMAIL-WORDBAND"
AF_CTA_COUNT = "AF-EMAIL-CTA-COUNT"
AF_SUBJECT_CHARBAND = "AF-EMAIL-SUBJECT-CHARBAND"
AF_FIRSTNAME = "AF-EMAIL-FIRSTNAME-PLACEMENT"
AF_FORMAT = "AF-EMAIL-FORMAT"
AF_SIGNATURE = "AF-EMAIL-SIGNATURE-PLACEHOLDER"
AF_DISRUPTIVE = "AF-EMAIL-DISRUPTIVE-MISSING"
AF_PROCESS = "AF-PROCESS-INTEGRITY"
AF_TYPE_MISMATCH = "AF-EMAIL-TYPE-MISMATCH"
AF_INTAKE_SPLIT = "AF-EMAIL-INTAKE-SPLIT"
AF_BRIEF_INCOMPLETE = "AF-EMAIL-BRIEF-INCOMPLETE"
AF_OVERRIDE_UNLOGGED = "AF-EMAIL-OVERRIDE-UNLOGGED"

# ---- SACRED constants (preserved VERBATIM from the corpus) ------------------
FRAMEWORKS = (
    "features-to-benefit", "pas", "aida", "pastor-solutions", "pastor-story",
    "million-dollar-sales", "before-after-bridge", "six-ws", "star-chain-hook",
    "star-story-solution", "three-b-plan", "acca", "cold-outreach-variants",
)
# Declared part counts for the frameworks whose structure is countable. When an
# email supplies an explicit sections[] list, its length must equal this.
FRAMEWORK_PARTS = {
    "pas": 3, "aida": 4, "before-after-bridge": 3, "acca": 4,
    "pastor-solutions": 6, "pastor-story": 6, "six-ws": 6,
    "star-chain-hook": 3, "star-story-solution": 3, "million-dollar-sales": 12,
}
OBJECTIVES = ("promotional", "abandoned-cart", "upsell", "downsell")
BUYER_TYPES = ("spontaneous", "methodical", "humanistic", "competitive")
PERSONA_STYLES = (
    "les-brown", "lisa-nichols", "brene-brown-gifts", "brene-brown-daring",
    "simon-sinek", "david-goggins", "dan-pink", "malcolm-gladwell",
    "michelle-obama", "iyanla-vanzant", "td-jakes", "tony-robbins",
)
# Buyer-type -> email# -> framework (Convert&Flow + High-Ticket, 12-email).
TWELVE_MAP = {
    1: "three-b-plan", 2: "star-chain-hook", 3: "features-to-benefit",
    4: "six-ws", 5: "acca", 6: "pastor-solutions", 7: "pastor-story",
    8: "star-story-solution", 9: "pas", 10: "aida",
    11: "million-dollar-sales", 12: "before-after-bridge",
}
BUYER_BAND = {
    1: "spontaneous", 2: "spontaneous", 3: "methodical", 4: "methodical",
    5: "methodical", 6: "methodical", 7: "humanistic", 8: "humanistic",
    9: "humanistic", 10: "competitive", 11: "competitive", 12: "competitive",
}
# The 10-email landing-page promo map (corpus section A).
LANDING_MAP = {
    1: "pastor-solutions", 2: "pastor-solutions", 3: "pastor-solutions",
    4: "features-to-benefit", 5: "six-ws", 6: "before-after-bridge",
    7: "three-b-plan", 8: "million-dollar-sales", 9: "aida", 10: "pas",
}
SEQ_LENGTHS = {"landing_page_10": 10, "high_ticket_12": 12, "buyer_type_12": 12}
PREVIEW_EXPECTED = {"landing_page_10": 2, "buyer_type_12": 1, "high_ticket_12": 2}

REQUIRED_BRIEF = ("objective", "buyer_type", "offer", "brand_voice",
                  "sequence_position", "founder_name")

# ---- regexes ----------------------------------------------------------------
_MERGE_RE = re.compile(r"\{\{.*?\}\}")
_BRACKET_RE = re.compile(r"\[[^\]]*\]")
_MARKDOWN_RE = re.compile(r"[*_#>`~]")
_URL_RE = re.compile(r"https?://\S+")
_WORD_RE = re.compile(r"[A-Za-z0-9']+")
# Emoji ranges: pictographs + misc symbols + dingbats + regional indicators.
# Deliberately EXCLUDES the arrows block so a CTA arrow is never miscounted.
_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]"
)
_PRICING_RE = re.compile(r"\$|\bUSD\b|\b\d+\s*%\s*off\b|\bdollars?\b", re.I)
_PLACEHOLDER_RE = re.compile(
    r"\[[^\]]*(?:name|founder|signature|your\s+name)[^\]]*\]|"
    r"\{\{\s*founder|FOUNDER_NAME|\bYOUR NAME\b",
    re.I,
)
_PERSONA_NAME_RES = [re.compile(p, re.I) for p in (
    r"\bles\s+brown\b", r"\blisa\s+nichols\b", r"\bbren[eé]\s+brown\b",
    r"\bsimon\s+sinek\b", r"\bdavid\s+goggins\b", r"\bdan\s+pink\b",
    r"\bmalcolm\s+gladwell\b", r"\bmichelle\s+obama\b", r"\biyanla\s+vanzant\b",
    r"\bt\.?\s*d\.?\s+jakes\b", r"\btony\s+robbins\b", r"\btoni\s+morrison\b",
)]


# ---- small helpers ----------------------------------------------------------
def _nonempty_str(v):
    return isinstance(v, str) and v.strip() != ""


def _strip(text):
    """Strip merge tags, bracketed tokens, markdown, and urls for word counting."""
    text = _MERGE_RE.sub(" ", text or "")
    text = _BRACKET_RE.sub(" ", text)
    text = _URL_RE.sub(" ", text)
    text = _MARKDOWN_RE.sub(" ", text)
    return text


def _words(text):
    return _WORD_RE.findall(_strip(text))


def _subject_words(subject):
    """Count subject words, counting a merge tag as ONE word (as the corpus does)."""
    s = _MERGE_RE.sub(" Name ", subject or "")
    return _WORD_RE.findall(s)


def _count_emojis(text):
    return len(_EMOJI_RE.findall(text or ""))


def _render_subject(subject):
    """Render a subject the way GHL would (merge tag -> a representative name)."""
    return _MERGE_RE.sub("Jordan", subject or "")


def _has_persona_name(text):
    return any(rx.search(text or "") for rx in _PERSONA_NAME_RES)


def _sequence_type(obj):
    st = obj.get("sequence_type")
    if _nonempty_str(st):
        return st
    # infer from sequence_id / sequence_position
    sid = (obj.get("sequence_id") or obj.get("sequence_position") or "").lower()
    if "high-ticket" in sid or "high_ticket" in sid:
        return "high_ticket_12"
    if "landing" in sid:
        return "landing_page_10"
    if "buyer" in sid or "convert-and-flow" in sid or "convert_and_flow" in sid:
        return "buyer_type_12"
    return "single"


def _subject_mode(seq_type, email):
    """INFER the subject mode from the sequence type / high-ticket flag ONLY.

    A caller-supplied ``subject_mode`` override on the authoring-written email is
    NOT read here — it is gated against the LOCKED brief in evaluate_email
    (FIX-XC-12a) so an unlogged override can never silently flip the subject
    rules. This function is the SACRED default."""
    if seq_type == "high_ticket_12" or str(email.get("high_ticket", "")).lower() in ("yes", "true", "1"):
        return "high_ticket"
    return "convert_and_flow"


def _expected_previews(seq_type, mode):
    """The SACRED default preview count for a sequence/mode. A per-email
    ``expected_preview_count`` override is NOT read here — it is gated against the
    LOCKED brief in evaluate_email (FIX-XC-12a)."""
    if seq_type in PREVIEW_EXPECTED:
        return PREVIEW_EXPECTED[seq_type]
    return 2 if mode == "high_ticket" else 1


def _locked_overrides(brief):
    """The client-exact override channel carried by the LOCKED brief. Returns the
    dict of authorized overrides (``word_band_override`` / ``expected_preview_count``
    / ``subject_mode``) or ``{}``. An override is honored on an email ONLY when its
    identical value is echoed here — never from the authoring-written email alone
    (that would be self-authorization). ``brief is None`` -> ``{}`` (no override is
    honored; the SACRED default stands)."""
    if not isinstance(brief, dict):
        return {}
    lo = brief.get("locked_overrides")
    if isinstance(lo, dict):
        return lo
    ans = brief.get("answers")
    if isinstance(ans, dict) and isinstance(ans.get("locked_overrides"), dict):
        return ans["locked_overrides"]
    return {}


def _override_honored(email, key, locked, tag, fails):
    """FIX-XC-12a: a per-email SACRED-band override is honored ONLY when the
    identical value is echoed in the LOCKED brief's override channel. An override
    present on the (authoring-written) email but NOT logged in the locked brief is
    REFUSED with AF-EMAIL-OVERRIDE-UNLOGGED and the SACRED default is enforced
    instead — an unlogged override can never loosen a gate. Returns the honored
    value, or ``None`` (no override, or refused)."""
    if not isinstance(email, dict) or key not in email or email.get(key) is None:
        return None
    val = email.get(key)
    if isinstance(locked, dict) and key in locked and locked.get(key) == val:
        return val
    fails.append((AF_OVERRIDE_UNLOGGED,
                  "%s: %s %r is not echoed in the LOCKED brief override channel — "
                  "override REFUSED, SACRED default enforced" % (tag, key, val)))
    return None


# ---- per-email evaluation ---------------------------------------------------
def evaluate_email(email, ctx):
    """Return [(AF_CODE, message)] for one email. ctx carries sequence context."""
    fails = []
    tag = ctx.get("tag", "email")
    seq_type = ctx.get("seq_type", "single")

    if not isinstance(email, dict):
        return [(AF_FRAMEWORK_UNKNOWN, "%s: not a JSON object" % tag)]

    framework = email.get("framework")
    objective = email.get("objective")
    persona = email.get("persona_style")
    subjects = email.get("subjects")
    previews = email.get("previews")
    body = email.get("body") or ""
    ctas = email.get("ctas")
    buyer_type = email.get("buyer_type")
    founder = email.get("founder_name") or ctx.get("founder_name") or ""

    # --- client-exact overrides (FIX-XC-12a): honored ONLY when echoed in the
    #     LOCKED brief; an unlogged override is refused (AF-EMAIL-OVERRIDE-UNLOGGED)
    #     and the SACRED default is enforced. ---
    locked = ctx.get("locked_overrides") or {}
    smode_override = _override_honored(email, "subject_mode", locked, tag, fails)
    mode = smode_override if _nonempty_str(smode_override) else _subject_mode(seq_type, email)
    prev_override = _override_honored(email, "expected_preview_count", locked, tag, fails)

    # --- framework set (AF-EMAIL-FRAMEWORK-UNKNOWN) ---
    if framework not in FRAMEWORKS:
        fails.append((AF_FRAMEWORK_UNKNOWN,
                      "%s: framework %r is not one of the 13 canonical frameworks" % (tag, framework)))
    else:
        # structured part-count completeness (AF-EMAIL-FRAMEWORK-INCOMPLETE)
        sections = email.get("sections")
        if isinstance(sections, list) and framework in FRAMEWORK_PARTS:
            want = FRAMEWORK_PARTS[framework]
            have = len([s for s in sections if _nonempty_str(s)])
            if have != want:
                fails.append((AF_FRAMEWORK_INCOMPLETE,
                              "%s: %s declares %d sections, needs exactly %d" % (tag, framework, have, want)))

    # --- objective validity (AF-EMAIL-OBJECTIVE-INVALID) ---
    if objective not in OBJECTIVES:
        fails.append((AF_OBJECTIVE_INVALID,
                      "%s: objective %r is not one of %s" % (tag, objective, "|".join(OBJECTIVES))))

    # --- buyer_type validity (AF-EMAIL-BUYERTYPE-MAP) ---
    if buyer_type is not None and buyer_type not in BUYER_TYPES:
        fails.append((AF_BUYERTYPE_MAP,
                      "%s: buyer_type %r is not one of %s" % (tag, buyer_type, "|".join(BUYER_TYPES))))

    # --- persona-style validity (AF-EMAIL-PERSONA-INVALID) ---
    if persona is not None and persona not in PERSONA_STYLES:
        fails.append((AF_PERSONA_INVALID,
                      "%s: persona_style %r is not one of the 12 canonical styles" % (tag, persona)))

    # --- persona NEVER named/quoted (AF-EMAIL-PERSONA-NAMED) ---
    scan = " ".join([body] + (subjects if isinstance(subjects, list) else []))
    if _has_persona_name(scan):
        fails.append((AF_PERSONA_NAMED,
                      "%s: a persona person is named/quoted in the copy (tone only, never the name)" % tag))

    # --- subject count exactly 2 (AF-EMAIL-SUBJECT-COUNT) ---
    if not (isinstance(subjects, list) and len(subjects) == 2 and all(_nonempty_str(s) for s in subjects)):
        fails.append((AF_SUBJECT_COUNT,
                      "%s: needs exactly 2 non-empty subject lines (A/B)" % tag))
        subjects = subjects if isinstance(subjects, list) else []

    # --- preview count (AF-EMAIL-PREVIEW-COUNT) ---
    want_prev = prev_override if isinstance(prev_override, int) else _expected_previews(seq_type, mode)
    if not (isinstance(previews, list) and len(previews) == want_prev and all(_nonempty_str(p) for p in previews)):
        fails.append((AF_PREVIEW_COUNT,
                      "%s: needs exactly %d non-empty preview line(s) for this sequence" % (tag, want_prev)))

    # --- word band (AF-EMAIL-WORDBAND) — a client-exact override wins ONLY when
    #     the SAME band is logged in the LOCKED brief (FIX-XC-12a). ---
    wc = len(_words(body))
    override = _override_honored(email, "word_band_override", locked, tag, fails)
    if isinstance(override, list) and len(override) == 2 and all(isinstance(x, int) for x in override):
        lo, hi = override[0], override[1]
        band_note = "client-exact override (logged) %d-%d" % (lo, hi)
    elif framework == "three-b-plan":
        lo, hi, band_note = 1, 149, "3-B Plan (< 150)"
    else:
        lo, hi, band_note = 150, 300, "default 150-300"
    if not (lo <= wc <= hi):
        fails.append((AF_WORDBAND,
                      "%s: body is %d words, outside %s" % (tag, wc, band_note)))

    # --- CTA count (AF-EMAIL-CTA-COUNT) ---
    cta_min = ctx.get("cta_min", 1)
    if not (isinstance(ctas, list) and len([c for c in ctas if _nonempty_str(c)]) >= cta_min):
        fails.append((AF_CTA_COUNT,
                      "%s: needs at least %d non-empty CTA(s)" % (tag, cta_min)))

    # --- subject char band (AF-EMAIL-SUBJECT-CHARBAND) ---
    # `mode` was resolved above (gated subject_mode override or the SACRED default).
    for i, s in enumerate(subjects, 1):
        if not _nonempty_str(s):
            continue
        if mode == "high_ticket":
            rlen = len(_render_subject(s))
            if not (80 <= rlen <= 87):
                fails.append((AF_SUBJECT_CHARBAND,
                              "%s subject %d: rendered length %d outside high-ticket 80-87" % (tag, i, rlen)))
            emc = _count_emojis(s)
            if emc != 1:
                fails.append((AF_SUBJECT_CHARBAND,
                              "%s subject %d: high-ticket needs exactly ONE emoji (found %d)" % (tag, i, emc)))
        else:
            nwords = len(_subject_words(s))
            if not (8 <= nwords <= 12):
                fails.append((AF_SUBJECT_CHARBAND,
                              "%s subject %d: %d words outside Convert&Flow 8-12" % (tag, i, nwords)))
            if _PRICING_RE.search(s):
                fails.append((AF_SUBJECT_CHARBAND,
                              "%s subject %d: contains a pricing token (no pricing in subjects)" % (tag, i)))

    # --- first-name placement (AF-EMAIL-FIRSTNAME-PLACEMENT) ---
    if mode == "high_ticket":
        placed = any("{{contact.first_name}}" in (s or "") for s in subjects)
    else:
        placed = any(0 <= (s or "").find("{{contact.first_name}}") < 40 for s in subjects)
    if subjects and not placed:
        fails.append((AF_FIRSTNAME,
                      "%s: {{contact.first_name}} not placed in a subject%s"
                      % (tag, " (first 40 chars)" if mode != "high_ticket" else "")))

    # --- formatting (AF-EMAIL-FORMAT) ---
    if _count_emojis(body) > 4:
        fails.append((AF_FORMAT,
                      "%s: more than 4 emojis in the body" % tag))
    for para in re.split(r"\n\s*\n", body):
        if len(re.findall(r"[.!?]+", para)) > 3:
            fails.append((AF_FORMAT,
                          "%s: a paragraph runs more than 3 sentences without a break" % tag))
            break

    # --- founder signature (AF-EMAIL-SIGNATURE-PLACEHOLDER) ---
    if _PLACEHOLDER_RE.search(body):
        fails.append((AF_SIGNATURE,
                      "%s: a placeholder signature token is present (use the founder's actual name)" % tag))
    elif not (_nonempty_str(founder) and founder.lower() in body.lower()):
        fails.append((AF_SIGNATURE,
                      "%s: founder's actual name (%r) not found in the close" % (tag, founder)))

    # --- high-ticket disruptive element (AF-EMAIL-DISRUPTIVE-MISSING) ---
    if ctx.get("require_disruptive"):
        de = email.get("disruptive_elements")
        if not (isinstance(de, list) and any(_nonempty_str(x) for x in de)):
            fails.append((AF_DISRUPTIVE,
                          "%s: high-ticket email carries no disruptive element" % tag))

    return fails


# ---- sequence evaluation ----------------------------------------------------
def evaluate_sequence(ledger, brief=None):
    fails = []
    locked = _locked_overrides(brief)
    seq_type = _sequence_type(ledger)
    if seq_type not in SEQ_LENGTHS:
        fails.append((AF_TYPE_MISMATCH,
                      "sequence_type %r is not one of %s" % (seq_type, "|".join(SEQ_LENGTHS))))
        seq_type = seq_type if seq_type in SEQ_LENGTHS else "buyer_type_12"

    emails = ledger.get("emails")
    if not isinstance(emails, list):
        return [(AF_SEQUENCE_LENGTH, "sequence has no emails[] array")]

    want_len = SEQ_LENGTHS.get(seq_type)
    if want_len is not None and len(emails) != want_len:
        fails.append((AF_SEQUENCE_LENGTH,
                      "sequence has %d emails, needs exactly %d for %s" % (len(emails), want_len, seq_type)))

    # slot contiguity 1..N
    slots = []
    for i, e in enumerate(emails, 1):
        slot = e.get("e_slot", i) if isinstance(e, dict) else i
        slots.append(slot)
    if sorted(slots) != list(range(1, len(emails) + 1)):
        fails.append((AF_SEQUENCE_LENGTH,
                      "e_slot values are not the contiguous set 1..%d (got %s)" % (len(emails), sorted(slots))))

    founder = ledger.get("founder_name", "")
    require_disruptive = (seq_type == "high_ticket_12")

    for i, e in enumerate(emails, 1):
        slot = e.get("e_slot", i) if isinstance(e, dict) else i
        ctx = {"tag": "E%d" % slot, "seq_type": seq_type,
               "founder_name": founder, "require_disruptive": require_disruptive,
               "cta_min": 1, "locked_overrides": locked}
        # framework map + CTA floor per map
        if seq_type == "landing_page_10":
            want_fw = LANDING_MAP.get(slot)
            if want_fw and isinstance(e, dict) and e.get("framework") != want_fw:
                fails.append((AF_SEQUENCE_MAP,
                              "E%d: framework %r must be %r (landing-page map)"
                              % (slot, e.get("framework"), want_fw)))
            if slot in (1, 2, 3):
                ctx["cta_min"] = 3  # PASTOR landing emails: >=3 CTAs
        elif seq_type in ("buyer_type_12", "high_ticket_12"):
            want_fw = TWELVE_MAP.get(slot)
            want_bt = BUYER_BAND.get(slot)
            if want_fw and isinstance(e, dict) and e.get("framework") != want_fw:
                fails.append((AF_BUYERTYPE_MAP,
                              "E%d: framework %r must be %r (buyer-type map)"
                              % (slot, e.get("framework"), want_fw)))
            if want_bt and isinstance(e, dict) and e.get("buyer_type") not in (None, want_bt):
                fails.append((AF_BUYERTYPE_MAP,
                              "E%d: buyer_type %r must be %r for this slot"
                              % (slot, e.get("buyer_type"), want_bt)))
        fails.extend(evaluate_email(e, ctx))

    # process integrity — a signed certificate is required before deploy
    if ledger.get("deploy_requested") is True:
        cert = ledger.get("process_certificate")
        if not (isinstance(cert, dict) and cert.get("signed") is True
                and _nonempty_str(str(cert.get("signed_by", "")))):
            fails.append((AF_PROCESS,
                          "deploy_requested but no signed process certificate (signed:true + signed_by)"))

    return fails


# ---- intake / brief evaluation ----------------------------------------------
def _ledger_oneblock(ledger):
    """INDEPENDENT one-block verification (FIX-S36-47). Derives the one-block
    property from an EXPORTED conversation ledger — the actual transcript, not a
    self-attested boolean. Exactly ONE assistant turn may carry the intake question
    block; more than one (or zero) means the brief was split across turns / never
    asked as a block. Returns [(AF, msg)]."""
    blocks = [t for t in ledger if isinstance(t, dict)
              and str(t.get("role", "")).lower() in ("assistant", "agent", "bot")
              and str(t.get("kind", t.get("type", ""))).lower()
              in ("intake", "intake_questions", "questions", "question_block")]
    if len(blocks) != 1:
        return [(AF_INTAKE_SPLIT,
                 "conversation_ledger shows %d intake question block(s) (INDEPENDENT "
                 "transcript check) — the brief must be asked in exactly ONE block" % len(blocks))]
    return []


def evaluate_intake(rec):
    fails = []
    skill = rec.get("skill") or rec.get("skill_type")
    if skill is not None and skill != "email-engine":
        fails.append((AF_TYPE_MISMATCH, "skill is %r, expected 'email-engine'" % skill))

    seq_pos = (rec.get("answers") or {}).get("sequence_position") if isinstance(rec.get("answers"), dict) else None
    if _nonempty_str(seq_pos):
        st = _sequence_type({"sequence_position": seq_pos})
        if st not in SEQ_LENGTHS and st != "single":
            fails.append((AF_TYPE_MISMATCH, "sequence_position %r resolves to unknown type" % seq_pos))

    # one-block delivery (FIX-S36-47) — when an INDEPENDENT conversation-ledger
    # export is supplied it is AUTHORITATIVE (derived from the transcript, not a
    # self-attested boolean); the self-attested flags are only a fallback and are
    # explicitly labeled attestation-based when no ledger is present.
    ledger = rec.get("conversation_ledger")
    if isinstance(ledger, list) and ledger:
        fails.extend(_ledger_oneblock(ledger))
    else:
        if rec.get("asked_all_at_once") is not True:
            fails.append((AF_INTAKE_SPLIT,
                          "asked_all_at_once is not true (got %r) [attestation-based: "
                          "no conversation_ledger export supplied]" % rec.get("asked_all_at_once")))
        if rec.get("one_question_per_turn") is True:
            fails.append((AF_INTAKE_SPLIT,
                          "one_question_per_turn is true — brief was split across turns "
                          "[attestation-based]"))
        msg = rec.get("question_block_msg_id")
        if isinstance(msg, (list, tuple)):
            real = [m for m in msg if _nonempty_str(m)]
            if len(real) != 1:
                fails.append((AF_INTAKE_SPLIT,
                              "question_block_msg_id must reference exactly ONE block "
                              "[attestation-based]"))

    # complete brief
    answers = rec.get("answers")
    if not isinstance(answers, dict):
        fails.append((AF_BRIEF_INCOMPLETE, "no answers object on the brief"))
        answers = {}
    missing = [f for f in REQUIRED_BRIEF if not _nonempty_str(str(answers.get(f, "")))]
    if missing:
        fails.append((AF_BRIEF_INCOMPLETE, "missing/empty brief fields: %s" % ", ".join(missing)))
    obj = answers.get("objective")
    if obj is not None and obj not in OBJECTIVES:
        fails.append((AF_BRIEF_INCOMPLETE, "objective %r is not one of %s" % (obj, "|".join(OBJECTIVES))))

    return fails


# ---- dispatch ---------------------------------------------------------------
def _detect_kind(obj):
    if not isinstance(obj, dict):
        return "email"
    if obj.get("kind") in ("intake", "brief"):
        return "intake"
    if "emails" in obj:
        return "sequence"
    if ("answers" in obj or "asked_all_at_once" in obj) and "body" not in obj:
        return "intake"
    return "email"


def evaluate(obj, kind=None, brief=None):
    k = kind or _detect_kind(obj)
    if k == "sequence":
        return evaluate_sequence(obj, brief=brief)
    if k == "intake":
        return evaluate_intake(obj)
    # single email — build a standalone context. Overrides are honored ONLY from a
    # separately-supplied LOCKED brief (never from the authoring-written email
    # itself — that would be self-authorization); brief is None -> no override.
    seq_type = _sequence_type(obj) if isinstance(obj, dict) else "single"
    ctx = {"tag": "email", "seq_type": seq_type,
           "founder_name": obj.get("founder_name", "") if isinstance(obj, dict) else "",
           "require_disruptive": False, "cta_min": 1,
           "locked_overrides": _locked_overrides(brief)}
    return evaluate_email(obj, ctx)


def decide_exit(failures):
    return EXIT_PASS if not failures else EXIT_AUTOFAIL


# ---- runner -----------------------------------------------------------------
def prove(path, as_json=False, kind=None, brief_path=None):
    p = Path(path)
    if not p.is_file():
        _emit(str(p), "?", [("USAGE", "file not found: %s" % p)], as_json)
        return EXIT_USAGE
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        _emit(str(p), "?", [("USAGE", "cannot read/parse JSON: %s" % exc)], as_json)
        return EXIT_USAGE
    # The LOCKED brief (when supplied) is the ONLY source that can authorize a
    # client-exact override on the authored emails (FIX-XC-12a).
    brief = None
    if brief_path:
        bp = Path(brief_path)
        if bp.is_file():
            try:
                brief = json.loads(bp.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                brief = None
    k = kind or _detect_kind(obj)
    failures = evaluate(obj, kind=k, brief=brief)
    _emit(str(p), k, failures, as_json)
    return decide_exit(failures)


def _emit(source, kind, failures, as_json):
    if as_json:
        print(json.dumps({
            "gate": "email-engine-floor-prover",
            "source": source, "kind": kind,
            "pass": not failures,
            "failures": [{"code": c, "message": m} for c, m in failures],
        }, indent=2))
        return
    print("== Email Engine :: floor prover (kind=%s) ==" % kind)
    print("source: %s" % source)
    if not failures:
        print("RESULT: PASS — every SACRED invariant satisfied.")
        return
    print("RESULT: FAIL (fail-closed) — %d violation(s):" % len(failures))
    for code, msg in failures:
        print("  [%s] %s" % (code, msg))


# =============================================================================
# SELF-TEST — built-in VALID (exit 0) + VIOLATION (exit nonzero) fixtures.
# =============================================================================
FOUNDER = "Morgan Vale"


def _make_body(target_words, founder=FOUNDER, cta="[Book your strategic assessment ->]", extra_emojis=0):
    fwords = len(_words(founder))
    K = max(1, target_words - fwords)
    words = ["value"] * K
    sentences = [" ".join(words[i:i + 3]) + "." for i in range(0, K, 3)]
    paras = [" ".join(sentences[i:i + 3]) for i in range(0, len(sentences), 3)]
    filler = "\n\n".join(paras)
    emoji_str = ("  " + ("✨" * extra_emojis)) if extra_emojis else ""
    return ("{{contact.first_name}},\n\n" + filler + emoji_str + "\n\n" + cta + "\n\n" + founder)


def _cf_subjects():
    return [
        "{{contact.first_name}}, the quiet cost of waiting another full week",
        "Everyone booked it but you last call now",
    ]


def _ht_subject(target=83, emoji="\U0001F511"):
    tag = "{{contact.first_name}}"
    base = "a private strategic assessment most founders never actually unlock for themselves this quarter here".split()
    core = ""
    for w in base:
        cand = (core + " " + w).strip()
        if 8 + len(cand) + 2 <= target:
            core = cand
        else:
            break
    while 8 + len(core) + 2 < target:
        core += "x"
    return tag + ", " + core + " " + emoji


def _ht_subjects():
    return [_ht_subject(83), _ht_subject(85)]


def _valid_email():
    return {
        "framework": "pas", "objective": "promotional",
        "subjects": _cf_subjects(), "previews": ["Tease the core value without repeating the subject"],
        "body": _make_body(200), "ctas": ["[Read the full story ->]"],
        "founder_name": FOUNDER,
    }


def _landing_ledger():
    emails = []
    for slot in range(1, 11):
        fw = LANDING_MAP[slot]
        target = 90 if fw == "three-b-plan" else 200
        ctas = ["[Start now ->]", "[See the details ->]", "[Claim your spot ->]"] if slot in (1, 2, 3) else ["[Read more ->]"]
        emails.append({
            "e_slot": slot, "framework": fw, "objective": "promotional",
            "subjects": _cf_subjects(),
            "previews": ["Preview line one for this email", "A bolder disruptive angle that stops the scroll"],
            "body": _make_body(target), "ctas": ctas,
        })
    return {
        "sequence_type": "landing_page_10", "sequence_id": "sequence-landing-page-10-promo",
        "founder_name": FOUNDER, "deploy_requested": True,
        "process_certificate": {"signed": True, "signed_by": "operator", "ts": "2026-07-02T00:00:00Z"},
        "emails": emails,
    }


def _buyer12_ledger():
    emails = []
    for slot in range(1, 13):
        fw = TWELVE_MAP[slot]
        target = 90 if fw == "three-b-plan" else 200
        emails.append({
            "e_slot": slot, "framework": fw, "buyer_type": BUYER_BAND[slot],
            "objective": "promotional", "subjects": _cf_subjects(),
            "previews": ["One Convert&Flow preview line for this email"],
            "body": _make_body(target), "ctas": ["[Book a call ->]"],
        })
    return {"sequence_type": "buyer_type_12", "sequence_id": "sequence-convert-and-flow-buyer-12",
            "founder_name": FOUNDER, "emails": emails}


def _ht12_ledger():
    emails = []
    for slot in range(1, 13):
        fw = TWELVE_MAP[slot]
        target = 90 if fw == "three-b-plan" else 200
        emails.append({
            "e_slot": slot, "framework": fw, "buyer_type": BUYER_BAND[slot],
            "objective": "promotional", "subjects": _ht_subjects(),
            "previews": ["Tease exclusive strategic insight A", "Tease exclusive strategic insight B"],
            "body": _make_body(target), "ctas": ["[Reserve your assessment ->]"],
            "disruptive_elements": ["Consultation Value Inversion"],
        })
    return {"sequence_type": "high_ticket_12", "sequence_id": "sequence-high-ticket-appointment",
            "founder_name": FOUNDER, "emails": emails}


def _valid_intake():
    return {
        "kind": "intake", "skill": "email-engine", "asked_all_at_once": True,
        "one_question_per_turn": False, "question_block_msg_id": "blk_0001",
        "answers": {
            "objective": "promotional", "buyer_type": "all", "offer": "The Momentum System",
            "brand_voice": "punchy and direct", "sequence_position": "landing-page-10-promo",
            "founder_name": FOUNDER,
        },
    }


def self_test():
    ok = True

    def check_pass(name, fixture, kind=None):
        nonlocal ok
        fails = evaluate(fixture, kind=kind)
        good = not fails and decide_exit(fails) == EXIT_PASS
        ok = ok and good
        print("  [%s] VALID %-24s -> exit %d %s"
              % ("PASS" if good else "MISS", name, decide_exit(fails),
                 "" if good else ("(unexpected: %r)" % fails[:4])))

    def check_fail(name, fixture, expect_code, kind=None):
        nonlocal ok
        fails = evaluate(fixture, kind=kind)
        codes = [c for c, _ in fails]
        good = bool(fails) and decide_exit(fails) != EXIT_PASS and expect_code in codes
        ok = ok and good
        print("  [%s] VIOLATION %-22s -> exit %d has %s %s"
              % ("PASS" if good else "MISS", name, decide_exit(fails), expect_code,
                 "" if good else ("codes=%s" % codes)))

    print("== self-test: VALID fixtures (must PASS / exit 0) ==")
    check_pass("single-email", _valid_email())
    check_pass("landing-page-10", _landing_ledger())
    check_pass("buyer-type-12", _buyer12_ledger())
    check_pass("high-ticket-12", _ht12_ledger())
    check_pass("intake-brief", _valid_intake())

    print("== self-test: VIOLATION fixtures (must FAIL / exit nonzero) ==")

    e = _valid_email(); e["framework"] = "webinar"
    check_fail("framework-unknown", e, AF_FRAMEWORK_UNKNOWN)

    e = _valid_email(); e["objective"] = "newsletter"
    check_fail("objective-invalid", e, AF_OBJECTIVE_INVALID)

    e = _valid_email(); e["persona_style"] = "oprah"
    check_fail("persona-invalid", e, AF_PERSONA_INVALID)

    e = _valid_email(); e["body"] = e["body"].replace(FOUNDER, "As Tony Robbins says, " + FOUNDER)
    check_fail("persona-named", e, AF_PERSONA_NAMED)

    e = _valid_email(); e["subjects"] = ["only one subject line here now"]
    check_fail("subject-count", e, AF_SUBJECT_COUNT)

    e = _valid_email(); e["previews"] = ["one preview", "two preview"]  # single expects 1
    check_fail("preview-count", e, AF_PREVIEW_COUNT)

    e = _valid_email(); e["body"] = _make_body(400)
    check_fail("wordband-over-300", e, AF_WORDBAND)

    e = _valid_email(); e["framework"] = "three-b-plan"; e["body"] = _make_body(200)
    check_fail("wordband-3b-over-150", e, AF_WORDBAND)

    lg = _landing_ledger(); lg["emails"][0]["ctas"] = ["only one CTA"]
    check_fail("cta-under-3-landing", lg, AF_CTA_COUNT)

    e = _valid_email(); e["body"] = _make_body(200, founder="[Founder Name]")
    check_fail("signature-placeholder", e, AF_SIGNATURE)

    lg = _landing_ledger(); lg["emails"] = lg["emails"][:9]
    check_fail("sequence-length", lg, AF_SEQUENCE_LENGTH)

    bg = _buyer12_ledger(); bg["emails"][1]["framework"] = "aida"  # slot2 should be star-chain-hook
    check_fail("buyertype-map", bg, AF_BUYERTYPE_MAP)

    lg = _landing_ledger(); lg["emails"][3]["framework"] = "pas"  # slot4 should be features-to-benefit
    check_fail("landing-map", lg, AF_SEQUENCE_MAP)

    hg = _ht12_ledger(); hg["emails"][0].pop("disruptive_elements", None)
    check_fail("disruptive-missing", hg, AF_DISRUPTIVE)

    e = _valid_email(); e["subjects"] = ["{{contact.first_name}}, grab it for $99 this week only now",
                                         "Everyone booked it but you last call"]
    check_fail("charband-cf-pricing", e, AF_SUBJECT_CHARBAND)

    hg = _ht12_ledger(); hg["emails"][0]["subjects"] = ["{{contact.first_name}}, too short \U0001F511",
                                                         "also short here now \U0001F511"]
    check_fail("charband-ht-length", hg, AF_SUBJECT_CHARBAND)

    e = _valid_email(); e["subjects"] = ["The quiet cost of waiting another full week",
                                         "Everyone booked it but you last call now"]
    check_fail("firstname-placement", e, AF_FIRSTNAME)

    e = _valid_email(); e["body"] = _make_body(200, extra_emojis=5)
    check_fail("format-emoji", e, AF_FORMAT)

    lg = _landing_ledger(); lg["process_certificate"] = {"signed": False}
    check_fail("process-integrity", lg, AF_PROCESS)

    it = _valid_intake(); it["asked_all_at_once"] = False
    check_fail("intake-split", it, AF_INTAKE_SPLIT)

    it = _valid_intake(); del it["answers"]["founder_name"]
    check_fail("brief-incomplete", it, AF_BRIEF_INCOMPLETE)

    it = _valid_intake(); it["skill"] = "deck-engine"
    check_fail("type-mismatch", it, AF_TYPE_MISMATCH)

    # FIX-XC-12a — an override present on the email but NOT logged in the LOCKED
    # brief is REFUSED (AF-EMAIL-OVERRIDE-UNLOGGED) and the SACRED band re-applies.
    e = _valid_email(); e["body"] = _make_body(400); e["word_band_override"] = [350, 450]
    check_fail("override-unlogged", e, AF_OVERRIDE_UNLOGGED)  # no brief -> refused
    # same over-length band trips the SACRED wordband too (default 150-300 re-applied).
    check_fail("override-unlogged-band", e, AF_WORDBAND)

    def check_brief(name, fixture, brief, kind=None, expect_pass=True, expect_code=None):
        nonlocal ok
        fails = evaluate(fixture, kind=kind, brief=brief)
        codes = [c for c, _ in fails]
        good = (not fails) if expect_pass else (bool(fails) and expect_code in codes)
        ok = ok and good
        print("  [%s] BRIEF-GATED %-18s -> %s %s"
              % ("PASS" if good else "MISS", name,
                 ("no violations" if expect_pass else "has %s" % expect_code),
                 "" if good else ("codes=%s" % codes)))

    # honored ONLY when the identical band is echoed in the LOCKED brief.
    e_ok = _valid_email(); e_ok["body"] = _make_body(400); e_ok["word_band_override"] = [350, 450]
    good_brief = {"locked_overrides": {"word_band_override": [350, 450]}}
    check_brief("override-logged", e_ok, good_brief, expect_pass=True)
    wrong_brief = {"locked_overrides": {"word_band_override": [10, 20]}}
    check_brief("override-mismatch", e_ok, wrong_brief, expect_pass=False,
                expect_code=AF_OVERRIDE_UNLOGGED)

    # FIX-S36-47 — an INDEPENDENT conversation-ledger export is authoritative.
    it = _valid_intake()
    it["conversation_ledger"] = [
        {"role": "assistant", "kind": "intake_questions", "msg_id": "b1"},
        {"role": "user", "kind": "answer", "msg_id": "u1"},
        {"role": "assistant", "kind": "intake_questions", "msg_id": "b2"},
    ]
    check_fail("intake-ledger-split", it, AF_INTAKE_SPLIT)
    # one real block in the ledger is AUTHORITATIVE even when a stale self-attested
    # flag says otherwise.
    it2 = _valid_intake(); it2["asked_all_at_once"] = False
    it2["conversation_ledger"] = [
        {"role": "assistant", "kind": "intake_questions", "msg_id": "b1"},
        {"role": "user", "kind": "answer", "msg_id": "u1"},
    ]
    check_pass("intake-ledger-oneblock", it2)

    print("== self-test: %s ==" % ("ALL ASSERTIONS PASSED" if ok else "FAILED"))
    return 0 if ok else 1


# ---- main -------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description="Fail-closed floor prover for the Email Engine (Skill 50).")
    ap.add_argument("path", nargs="?", help="emails.json / email.json / brief.json to prove")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    ap.add_argument("--kind", choices=("email", "sequence", "intake"), help="force the input kind")
    ap.add_argument("--brief", dest="brief", default=None,
                    help="path to the LOCKED brief.json — the ONLY source that can "
                         "authorize a client-exact override (word_band_override / "
                         "expected_preview_count / subject_mode) on the authored emails")
    ap.add_argument("--self-test", dest="self_test", action="store_true",
                    help="run built-in VALID + VIOLATION fixtures and exit")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.path:
        ap.error("a path is required (or use --self-test)")
    return prove(args.path, as_json=args.json, kind=args.kind, brief_path=args.brief)


if __name__ == "__main__":
    sys.exit(main())
