"""lyric_writer.py: sung-copy rules (directive 11.3) over campaign-schema lyrics. stdlib only.

Rules: short first-person lines, one idea per line, critical=true on every
line carrying offer/claim/product/CTA wording (100% coverage per acceptance
profile), pronunciation_map on every line naming the product. CTA lines
(line_id containing "cta") are exempt from first-person (imperative voice).
A line that is the client's OWN words -- a contiguous run of at least
CLIENT_RUN_MIN words of the brief's offer, website, claims or packet_lines --
is exempt from first-person too: the hook gate (suno_recipe.check_hook)
demands the client's words, so without this no client hook in another voice
could ever pass both gates (the v2.9.70 stage-3 deadlock). The comparison
folds the apostrophe variants (curly U+2019 from a pasted brief vs the
straight one usually written) so the client's own words match themselves;
``words`` and every gate built on it keep their tokenisation. A dot inside a
word (VoyageToVirtue.com, 3.5) is not a sentence break for one-idea-per-line;
"I rise. I fall" still is.

W-G-002 amend (Trevor order 2026-10-08 11:50 EDT, part G; review item G5):
lines marked ``delivery: "sung"`` must be SINGABLE -- short metered lines
inside the 4..12 syllable band, each connected to another sung line by
rhyme or repetition, with at least one hook (a line or three-word phrase)
repeated twice in the song.

WW-27 amend: the CAST DECISION precedes drafting. A brief that declares a cast
is judged FIRST (character_bible.check_cast): every character needs its full
treatment and Suno voice, an ensemble needs at least two characters, a villain
or foil must speak and be answered, and no two characters share one voice
direction. A brief with no cast declares nothing and is judged exactly as
before. A sung line that connects to nothing is script
prose cut at line breaks -- the O3 fault -- and is refused as
"prose-line-in-sung-block"; prose belongs in spoken blocks. Lines that do
not carry a ``delivery`` field are judged exactly as before (no behaviour
change for existing callers).

CONSTRAINT POLICY (Skill_75 repair D09; spec 6.3 / 15.3): this module owns THE
single versioned, mode- and duration-aware constraint policy
(``constraint_policy``). lyric_writer, suno_recipe (wired by S75-W05-U3),
words_fit, the spoken-share rules, the hook checks and the final audio
evaluator all consume THIS object, so the writer receives exactly the
constraints downstream enforces. The W-G-002 4..12 band versus suno_recipe's
"8 at most" contradiction is resolved by ONE mode-specific rule:

  * PREFERRED sung meter is 4..8 syllables (the meter the provider sings
    cleanly -- 5-6 aimed, 8 at most). Outside the preferred range the line is
    still singable, so the finding is ACCEPT WITH WARNING, never a failure.
  * A required correction fires ONLY where violating the range makes the
    provider request invalid or the line impossible to perform: outside the
    performable band 1..12 (over 12 syllables one short metered sung line
    cannot be delivered; the provider splits or rewrites it), over a REAL
    destination provider cap (a mode/destination-specific reason recorded on
    the finding -- the only sanctioned way to contradict an accepted 9- or
    11-syllable line), or more syllables than the line's slot can hold at the
    policy's sung rate.
  * A line whose meter cannot be measured at all is USER DECISION REQUIRED
    (remeasure or decide) -- never fabricated into a pass or a failure.
  * Story information and natural delivery beat mechanical padding: the
    policy never asks for meaningless words to satisfy a count.

Spoken sections: for the dramatization mode spoken scenes are preserved
ANYWHERE in the sheet -- the legacy "spoken only in [Intro]/[Outro]"
assumption is retired here and survives only in constraint mode "standard",
carrying its mode-specific reason.

Three quality outcomes (spec 15.3): required_correction, accept_with_warning,
user_decision_required. ``result["findings"]`` carries ONLY required
corrections BY CONTRACT, so a generic ``any(findings)`` check can never convert
a warning into failure; the complete typed inventory is ``quality_findings``,
and warnings travel to final delivery in ``result["warnings"]``. Use
``exit_code_for`` and ``delivery_status`` for the exit-code mapper and the
Command Center projection -- both are warning-proof.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import protected_names  # noqa: E402  H7 build gate

SCHEMA_VERSION = "blackceo.lyric-writer/v1"
TOOL_VERSION = "0.3.0"

# ponytail: fixed ceilings, no per-campaign override; add when directive names numbers.
MAX_WORDS = 18
MIN_SIGNIFICANT_LEN = 4
LINE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
FIRST_PERSON = frozenset({
    "i", "me", "my", "mine", "myself", "we", "us", "our", "ours",
    "ourselves", "i'm", "i've", "i'll", "i'd", "we're", "we've",
    "we'll", "we'd",
})
EXIT = {"ok": 0, "rejected": 4, "error": 1, "decision": 3}
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"

# ---------------------------------------------------------------------------
# THE constraint policy (D09; spec 6.3 / 15.3). One versioned, mode- and
# duration-aware table, consumed by lyric_writer, suno_recipe (S75-W05-U3
# wires it), words_fit, the spoken-share rules, the hook checks and the final
# audio evaluator. Mirrored numbers are drift-guarded against their owning
# modules in selftest, so the writer receives exactly what downstream enforces.
# ---------------------------------------------------------------------------
CONSTRAINT_POLICY_VERSION = "blackceo.constraint-policy/v1"
POLICY_MODE_DEFAULT = "dramatization"
POLICY_MODES = ("dramatization", "standard")

#: Three quality outcomes (spec 15.3). Every finding carries exactly one and
#: only a required_correction ever blocks. A warning can never become a
#: failure: ``result["findings"]`` is blocking-only BY CONTRACT, and the
#: exit-code / aggregator / Command Center mappers below are typed.
Q_REQUIRED = "required_correction"
Q_WARNING = "accept_with_warning"
Q_DECISION = "user_decision_required"

#: G5 singability band, restated by the policy: the PREFERRED sung meter is
#: 4..8 syllables (the meter the provider sings cleanly, 5-6 aimed, 8 at most
#: -- suno_recipe's retired "at most 8" folded in as the preference); 1..12 is
#: the PERFORMABLE band (over 12 one short metered sung line cannot be
#: delivered); outside it the request is invalid or the line impossible to
#: perform and the finding is a required correction. Values read from the
#: policy at judge time; these names stay for existing importers.
SUNG_SYL_MIN = 4
SUNG_SYL_MAX = 12
HOOK_REPEAT = 2      # a hook line/phrase repeats at least this many times
PHRASE_WORDS = 3     # a run this long shared by two lines is a hook phrase

#: A sung line faster than this cannot be performed in its slot (fast sung
#: delivery measures well under 5 syllables/second; beyond it the line is
#: spoken, not sung).
MAX_SUNG_RATE_SPS = 5.0

#: Duration-aware canonical lengths (spec 6.2/6.3). The recipe duration
#: registry (S75-W05-U3) binds to this table; no second copy.
CANONICAL_DURATION_S = (60, 90, 120, 180, 300, 600)


def finding(code, detail, quality=Q_REQUIRED, **extra):
    """One typed finding. ``error`` keeps the legacy key name so existing
    consumers of the findings lists read the code exactly as before."""
    f = {"error": code, "detail": detail,
         "quality": quality, "blocking": quality == Q_REQUIRED}
    f.update(extra)
    return f


def blocking(findings):
    """The only findings that may refuse a sheet. Warnings and decisions are
    NEVER in this list -- a generic ``any(findings)`` check over the result's
    ``findings`` field therefore cannot convert a warning into a failure."""
    return [f for f in (findings or [])
            if f.get("quality", Q_REQUIRED) == Q_REQUIRED]


def has_required_correction(findings):
    return bool(blocking(findings))


def outcome_from_findings(findings):
    """THE one findings mapper (spec 15.3). Refuses only on a required
    correction; a decision holds; everything else accepts, warnings included."""
    f = list(findings or [])
    if any(x.get("quality", Q_REQUIRED) == Q_REQUIRED for x in f):
        return "rejected"
    if any(x.get("quality") == Q_DECISION for x in f):
        return "decision"
    return "ok"


def exit_code_for(result):
    """THE one exit-code mapper. A warning-carrying result exits 0 exactly
    like a clean one; only a required correction exits non-zero, and a held
    decision gets its own code (3), never the failure code."""
    return EXIT.get((result or {}).get("outcome"), EXIT["error"])


def delivery_status(result):
    """Command Center projection. A warning is projected as
    ``accepted_with_warnings`` -- never as failure."""
    r = result or {}
    if has_required_correction(r.get("findings")):
        return "failed"
    if r.get("decisions"):
        return "user_decision_required"
    if r.get("warnings"):
        return "accepted_with_warnings"
    return "accepted"


def aggregate_status(results):
    """Downstream aggregator: worst delivery status wins, but no aggregation
    of warnings may ever read as failure."""
    statuses = [delivery_status(r) for r in (results or [])]
    for s in ("failed", "user_decision_required",
              "accepted_with_warnings", "accepted"):
        if s in statuses:
            return s
    return "accepted"


def constraint_policy(mode=None, duration_s=None):
    """Resolve THE constraint policy for ``mode`` (default ``dramatization``)
    and an optional runtime ``duration_s``. Mode-specific rules carry their
    ``reason`` so any downstream contradiction is forced to name one."""
    m = str(mode or POLICY_MODE_DEFAULT).strip().lower() or POLICY_MODE_DEFAULT
    if m not in POLICY_MODES:
        raise ValueError("unknown constraint mode %r (want one of %s)"
                         % (mode, POLICY_MODES))
    dur = None
    if duration_s is not None:
        try:
            dur = float(duration_s)
        except (TypeError, ValueError):
            raise ValueError("duration_s must be a number, got %r" % (duration_s,))
        if dur <= 0:
            raise ValueError("duration_s must be positive, got %r" % (duration_s,))
    if m == "standard":
        # Legacy provider contract kept whole, WITH its reason: sung lines the
        # provider would rewrite and spoken outside [Intro]/[Outro] make the
        # request invalid as authored.
        meter = {"preferred": (4, 8), "performable": (1, 8), "provider_cap": 8,
                 "reason": "mode standard: the provider caps sung lines at 8 "
                           "syllables and rewrites longer ones -- the request "
                           "would be invalid as authored"}
        spoken = {"allowed_tags": ("intro", "outro"),
                  "reason": "mode standard (legacy provider rule 1): spoken "
                            "tags are only allowed in [Intro]/[Outro]"}
    else:
        # Dramatization: story scenes speak anywhere; the sung meter's
        # preference warns, its performable band corrects (D09 resolution).
        meter = {"preferred": (4, 8), "performable": (1, 12),
                 "provider_cap": None,
                 "reason": "mode dramatization: over 12 syllables one short "
                           "metered sung line cannot be delivered -- the "
                           "provider splits or rewrites it"}
        spoken = {"allowed_tags": ("*",),
                  "reason": "mode dramatization: spoken story scenes are "
                            "preserved anywhere in the sheet; the legacy "
                            "[Intro]/[Outro]-only assumption is retired here"}
    p = {
        "policy_version": CONSTRAINT_POLICY_VERSION,
        "mode": m,
        "duration_s": dur,
        "duration": {"canonical_s": CANONICAL_DURATION_S},
        "sung_meter": dict(meter, max_rate_sps=MAX_SUNG_RATE_SPS,
                           retired_bounds={"suno_recipe."
                                           "MAX_SUNG_LINE_SYLLABLES": 8}),
        "spoken_sections": spoken,
        "hook": {"min_repeats": HOOK_REPEAT, "phrase_words": PHRASE_WORDS,
                 "hook_opens_song": False,
                 "first_sung_target_pct": 15.0,
                 # ponytail: percentages mirrored from spoken_share/words_fit
                 # (drift-guarded in selftest); route reads through those
                 # modules' own accessors when they consume this policy.
                 "source": "core/sung_hook + core/spoken_share (owners)"},
        "spoken_share": {"target_pct": 22.5, "min_pct": 12.5, "max_pct": 32.5,
                         "sung_of_voice_pct": 77.5, "accept_pts": 5,
                         "flag_pts": 10,
                         "owner": "core/spoken_share"},
        "words_fit": {"intro_outro_s": 8.0, "headroom": 0.15,
                      "owner": "core/words_fit"},
        "quality": {"outcomes": (Q_REQUIRED, Q_WARNING, Q_DECISION),
                    "findings_field_is_blocking_only": True,
                    "warning_never_failure": True},
    }
    if dur is not None:
        p["hook"]["first_sung_target_s"] = round(
            dur * p["hook"]["first_sung_target_pct"] / 100.0, 3)
        p["spoken_share"]["budget_s"] = [
            round(dur * p["spoken_share"]["min_pct"] / 100.0, 3),
            round(dur * p["spoken_share"]["max_pct"] / 100.0, 3)]
    return p


def sung_meter_finding(syllables, policy=None, slot_s=None, measurable=True,
                       label="line"):
    """THE single sung-meter rule (D09), for the writer AND the recipe.

    None when the line sits in the preferred meter. Outside the preference but
    performable: accept_with_warning. Outside the performable band, over a
    real provider cap (mode-specific ``reason`` recorded), or too many
    syllables for its slot: required_correction. Unmeasurable: a user
    decision -- never fabricated into pass or failure."""
    p = (policy or constraint_policy())["sung_meter"]
    if not measurable:
        return finding("sung-meter-unmeasurable",
                       "%s: syllables not measurable; remeasure or decide"
                       % label, Q_DECISION)
    try:
        syl = int(syllables)
    except (TypeError, ValueError):
        return finding("sung-meter-unmeasurable",
                       "%s: syllable count %r is not a number; remeasure or "
                       "decide" % (label, syllables), Q_DECISION)
    lo_p, hi_p = (int(x) for x in p["preferred"])
    lo_f, hi_f = (int(x) for x in p["performable"])
    if p.get("provider_cap") is not None:
        hi_f = min(hi_f, int(p["provider_cap"]))
    if slot_s is not None:
        try:
            slot = float(slot_s)
        except (TypeError, ValueError):
            slot = None
        if slot is not None and slot > 0 and syl > slot * p["max_rate_sps"]:
            return finding("sung-line-unperformable-in-slot",
                           "%s: %d syllables in a %.2fs slot exceeds %.1f "
                           "syllables/s -- impossible to perform"
                           % (label, syl, slot, p["max_rate_sps"]),
                           Q_REQUIRED, mode_reason=p["reason"])
    if lo_p <= syl <= hi_p:
        return None
    if lo_f <= syl <= hi_f:
        return finding("sung-line-not-metered",
                       "%s: %d syllables; preferred sung meter is %d..%d -- "
                       "singable with effort, accepted with warning"
                       % (label, syl, lo_p, hi_p), Q_WARNING)
    return finding("sung-line-not-metered",
                   "%s: %d syllables; %d..%d cannot be performed as one sung "
                   "line (preferred meter %d..%d)"
                   % (label, syl, lo_f, hi_f, lo_p, hi_p),
                   Q_REQUIRED, mode_reason=p["reason"])


def spoken_section_findings(sheet, policy=None):
    """Spoken placement per mode (D09). Dramatization preserves spoken scenes
    ANYWHERE -- including outside [Intro]/[Outro]; the legacy placement rule
    applies only in mode "standard" and carries its reason."""
    pol = policy or constraint_policy()
    sp = pol["spoken_sections"]
    allowed = tuple(str(t).lower() for t in sp["allowed_tags"])
    out = []
    for i, s in enumerate(sheet or []):
        if not isinstance(s, dict) or \
                str(s.get("delivery") or "").strip().lower() != "spoken":
            continue
        tag = str(s.get("tag") or ("section %d" % i))
        head = tag.strip().lower().split()[0] if tag.strip() else ""
        if "*" in allowed or head in allowed:
            continue
        out.append(finding("spoken-section-not-allowed",
                           "spoken section %r: %s" % (tag, sp["reason"]),
                           Q_REQUIRED, mode_reason=sp["reason"]))
    return out

#: WW-27: the ensemble cast gate (character_bible.character_bible), imported
#: LAZILY so a brief that declares no cast never loads it.
#:
#: The gate fires on a WW-27 CAST DECLARATION (cast_mode / cast_decision /
#: cast), never on the legacy ``characters`` name list alone: a brief whose
#: ``characters`` are there for protected-name checks (H7) is judged exactly as
#: before, so this unit changes nothing for an existing caller.
#:
#: S75-T13: that legacy surface is now the ONLY open one. An ABSENT cast
#: foundation is missing input, never an opt-out, so every script-authoring
#: entry goes through ``require_cast_manifest`` / ``validate_authored_lyrics``,
#: which never return None and have no argument that turns them off. A brief
#: carrying the Skill 75 foundation envelope (``episode_cast_manifest``) always
#: runs the required gate, even through the legacy ``validate_lyrics`` surface,
#: so omitting a cast field can no longer skip it by shape.
_CAST_MOD = None
_CAST_KEYS = ("cast_mode", "cast_decision", "cast")
CAST_MANIFEST_KEY = "episode_cast_manifest"
CAST_GATE_SCHEMA = "s75.cast_gate.v1"
CODE_CAST_FOUNDATION_MISSING = "CAST_FOUNDATION_MISSING"
CODE_CAST_FOUNDATION_INVALID = "CAST_FOUNDATION_INVALID"


def _cast_mod():
    """``character_bible``, imported lazily (a cast-less legacy brief never loads it)."""
    global _CAST_MOD
    if _CAST_MOD is None:
        from character_bible import character_bible as _cb   # noqa: PLC0415
        _CAST_MOD = getattr(_cb, "character_bible", _cb)
    return _CAST_MOD


def _cast_declared(b):
    """A WW-27 cast declaration is present (the legacy gate's own trigger)."""
    return any(b.get(k) for k in _CAST_KEYS)


def _has_foundation_manifest(b):
    """The Skill 75 foundation envelope names its cast artifact explicitly."""
    return CAST_MANIFEST_KEY in b


def _foundation_receipt(code, reason):
    """S75-T13: the FAIL receipt for an absent or invalid cast foundation."""
    return {"tool": "character_bible", "schema": CAST_GATE_SCHEMA,
            "verdict": "FAIL", "reason_code": code, "reasons": [reason],
            "blocked": True, "purchases": 0, "measures_no_audio": True,
            "decision": "absent" if code == CODE_CAST_FOUNDATION_MISSING else "invalid",
            "mode": "absent", "mode_declared": None,
            "characters": [], "characters_n": 0, "detail": reason}


def _manifest_defects(manifest):
    """Defects of a T03 ``episode_cast_manifest`` payload (same contract)."""
    try:
        import story_first_contracts as C     # sibling module in core/
    except ImportError:
        from .. import story_first_contracts as C  # imported as core.*
    return C.validate_cast_manifest(manifest)


def require_cast_manifest(brief):
    """S75-T13: THE cast gate for a script-authoring path. NEVER returns None.

    An absent cast declaration, an absent/empty ``episode_cast_manifest`` and an
    invalid manifest each return a FAIL receipt naming exactly what is missing,
    so no authoring call can skip the gate by omitting cast fields. A declared
    WW-27 cast is judged by ``check_cast`` and a T03 manifest by the shared
    contract, so the two shapes stay one decision with two readers.
    """
    b = brief if isinstance(brief, dict) else {}
    if _has_foundation_manifest(b):
        manifest = b.get(CAST_MANIFEST_KEY)
        if not isinstance(manifest, dict) or not manifest:
            return _foundation_receipt(
                CODE_CAST_FOUNDATION_MISSING,
                "%s: the %s foundation is absent; an absent field is missing "
                "input, never an opt-out" % (CODE_CAST_FOUNDATION_MISSING,
                                             CAST_MANIFEST_KEY))
        defects = _manifest_defects(manifest)
        if defects:
            return _foundation_receipt(
                CODE_CAST_FOUNDATION_INVALID,
                "%s: the %s does not satisfy the cast contract (%s)"
                % (CODE_CAST_FOUNDATION_INVALID, CAST_MANIFEST_KEY,
                   "; ".join("%s %s" % (d.get("field"), d.get("issue"))
                             for d in defects)))
        return {"tool": "character_bible", "schema": CAST_GATE_SCHEMA,
                "verdict": "PASS", "reason_code": "ENSEMBLE_CAST_OK",
                "reasons": [], "blocked": False, "purchases": 0,
                "measures_no_audio": True, "decision": "declared",
                "mode": "manifest", "mode_declared": True,
                "characters": [c.get("character_id") for c in manifest.get("cast") or []
                               if isinstance(c, dict)],
                "characters_n": len(manifest.get("cast") or []),
                "detail": "the episode cast manifest satisfies the cast contract"}
    if not _cast_declared(b):
        return _foundation_receipt(
            CODE_CAST_FOUNDATION_MISSING,
            "%s: the cast foundation is absent (no cast_mode / cast_decision / "
            "cast and no %s); a missing cast is missing input, never an opt-out"
            % (CODE_CAST_FOUNDATION_MISSING, CAST_MANIFEST_KEY))
    return _cast_mod().check_cast(b)


def _cast_gate(brief, required=False):
    """WW-27 + S75-T13: the cast decision, taken BEFORE the lines are judged.

    With a declared cast, ``check_cast`` refuses an incomplete character, a cast
    under the ensemble default, a villain/foil that never speaks or is never
    answered, or a shared Suno voice direction -- so the script's drafting never
    begins on a broken cast. PRE-GENERATION: audio gate D5 alone confirms the
    delivered voices.

    ``required`` (or a foundation-envelope brief) FAILS CLOSED: an absent cast
    is a named missing-input refusal, never a silent None, so there is no skip
    path through this function for an authoring caller. Only the documented
    legacy validation surface may still read a cast-less brief as before.
    """
    b = brief if isinstance(brief, dict) else {}
    if required or _has_foundation_manifest(b):
        return require_cast_manifest(b)
    if not _cast_declared(b):
        return None
    return _cast_mod().check_cast(b)


def _with_cast(res, cast_rcpt):
    """Every lyric verdict carries the cast decision that preceded it."""
    res["cast_decision"] = cast_rcpt
    return res


def _structure():
    try:
        import lyric_structure  as ls       # same dir on sys.path
    except ImportError:
        from . import lyric_structure as ls  # imported as core.*
    return ls


def words(text):
    return re.findall(r"[a-z0-9]+(?:'[a-z]+)?", text.lower())


#: the hook gate demands the client's OWN words, so a line that is a
#: contiguous run of the client's text is exempt from first-person.
CLIENT_RUN_MIN = 3

#: A brief pasted from Word/Google Docs carries CURLY apostrophes (U+2019) while
#: the written lyric usually carries straight ones, and ``words`` splits on the
#: curly form ("isn't" -> one token, "isn\u2019t" -> "isn" + "t"). Comparing the
#: exemption on that raw split made a client's OWN line silently refuse, which is
#: the exact stage-3 deadlock v2.9.70 exists to remove. Normalised for the
#: EXEMPTION COMPARISON ONLY: ``words`` and every gate built on it keep the
#: tokenisation they had, so no length/coverage gate changes behaviour.
_APOSTROPHES = "\u2018\u2019\u02bc"

def exempt_tokens(text):
    """``words`` of ``text`` with the apostrophe variants folded to ASCII '."""
    for a in _APOSTROPHES:
        text = text.replace(a, "'")
    return words(text)

def client_word_runs(brief):
    """Word lists of the client's own text in the brief.

    Sources are only the fields the intake recorded as the CLIENT'S OWN
    ANSWERS: the essentials question (offer / audience+action / website),
    the client's claims and packet lines, the book intake's own-fields
    (pain_or_transformation, excerpt_lines) and the research brief's
    sub-avatar answers (avatar, emotional_wound, desired_transformation --
    validated non-empty client-confirmed answers). ``sub_avatar.notes`` is
    deliberately NOT a source: it is the authoring provenance remark, the
    one model-written field inside the sub-avatar block. The same rule
    keeps research/gather output out of here -- the model-written claim
    lines a search filled in are never the client's words.
    """
    b = brief if isinstance(brief, dict) else {}
    src = [b.get("offer"), b.get("website"), b.get("audience"),
           b.get("action") or b.get("cta"),
           b.get("pain_or_transformation")]
    for key in ("claims", "packet_lines", "excerpt_lines"):
        v = b.get(key) or []
        for c in v.splitlines() if isinstance(v, str) else v:
            src.append(c.get("text") if isinstance(c, dict) else c)
    sub = b.get("sub_avatar")
    if isinstance(sub, dict):
        src.extend(sub.get(k) for k in
                   ("avatar", "emotional_wound", "desired_transformation"))
    return [exempt_tokens(t) for t in src if isinstance(t, str) and t.strip()]

def client_verbatim(toks, runs):
    n = len(toks)
    return n >= CLIENT_RUN_MIN and any(
        r[i:i + n] == toks for r in runs for i in range(len(r) - n + 1))

def client_run_inside(toks, runs):
    """:``True`` when ``toks`` CONTAINS a contiguous client run of at least
    CLIENT_RUN_MIN tokens (a whole-line run passes already: the first case).
    A rewritten line that carries a >=3-word chunk of the client's own text
    is the client's voice, so it is exempt from first-person; a line built
    from invented wording carries no such run and is still refused. The run
    must be CONTIGUOUS in the line (no crossing filler gaps), so two stray
    client words never exempt a line."""
    n = len(toks)
    if n < CLIENT_RUN_MIN:
        return False
    if client_verbatim(toks, runs):
        return True
    for w in range(CLIENT_RUN_MIN, n + 1):
        for start in range(n - w + 1):
            win = toks[start:start + w]
            if client_verbatim(win, runs):
                return True
    return False

def significant(text):
    """Brief words that force critical coverage (len>=4 alnum tokens)."""
    if not isinstance(text, str):
        return set()
    return {w for w in words(text) if len(w) >= MIN_SIGNIFICANT_LEN}


def brief_words(brief):
    out = set()
    b = brief or {}
    for key in ("product_name", "offer_text", "cta_text"):
        out |= significant(b.get(key))
    claims = b.get("claims") or []
    for c in claims if isinstance(claims, list) else []:
        out |= significant(c)
    return out


#: Words that never make two sung lines "repeat" each other (G5): shared
#: "the" is not a hook.
_FILLER = frozenset({
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "at", "by",
    "it", "is", "was", "be", "for", "with", "as", "if", "when", "that",
    "this", "you", "your", "i", "my", "me", "we", "our", "he", "she",
    "they", "them", "his", "her", "their", "so", "but", "not",
})


def is_sung_line(ln):
    """True when a line is marked for sung delivery (G5)."""
    return (isinstance(ln, dict)
            and str(ln.get("delivery") or "").strip().lower() == "sung")


def _phrases3(text):
    """Every 3-word run in a line, filler stripped, lowercased."""
    toks = [w for w in words(text) if w not in _FILLER]
    return {" ".join(toks[i:i + PHRASE_WORDS])
            for i in range(len(toks) - PHRASE_WORDS + 1)}


def audit_sung_lines(lines, policy=None):
    """Full typed G5 audit of the lines marked sung (D09 policy).

    Meter is judged by ``sung_meter_finding`` -- the SAME rule suno_recipe
    consumes -- so the 4..12 versus 8 contradiction cannot reappear: outside
    the preferred meter the finding is accept_with_warning, and only an
    unperformable or provider-invalid line is a required correction. The
    connection rule (prose-line-in-sung-block) and the hook rule stay required
    corrections: prose cut at line breaks and a missing hook are script
    faults, not meter preferences. Returns findings with ``quality``; use
    ``blocking`` for the refuse list."""
    pol = policy or constraint_policy()
    ls = _structure()
    sung = [(i, ln.get("line_id") or "line %d" % i, ln.get("text") or "")
            for i, ln in enumerate(lines or []) if is_sung_line(ln)]
    if not sung:
        return []
    out = []

    # 1. meter: one mode/duration-aware rule, preferred range warns
    for i, lid, text in sung:
        f = sung_meter_finding(ls.line_syllables(text), pol,
                               slot_s=(lines[i] or {}).get("seconds"),
                               label=lid)
        if f is not None:
            out.append(f)

    # 2. connection: each sung line rhymes with, repeats, or shares a
    #    3-word phrase with another sung line (pairs or fours)
    ends = [ls.words(t)[-1:] for _, _, t in sung]
    texts = [re.sub(r"\s+", " ", t.strip().lower()) for _, _, t in sung]
    phrs = [_phrases3(t) for _, _, t in sung]
    for k, (_, lid, text) in enumerate(sung):
        connected = False
        for j in range(len(sung)):
            if j == k:
                continue
            if texts[k] and texts[k] == texts[j]:
                connected = True
                break
            if ends[k] and ends[j] and ls.rhymes(ends[k][0], ends[j][0]):
                connected = True
                break
            if phrs[k] & phrs[j]:
                connected = True
                break
        if not connected:
            out.append(finding(
                "prose-line-in-sung-block",
                "%s: %r connects to no other sung line by rhyme "
                "or repetition -- prose belongs in a spoken block"
                % (lid, text[:60])))

    # 3. hook: one line or 3-word phrase repeats at least twice
    hmin = pol["hook"]["min_repeats"]
    pwords = pol["hook"]["phrase_words"]
    counts = {}
    for t in texts:
        if t:
            counts[t] = counts.get(t, 0) + 1
    hook = max(counts.values(), default=0)
    if hook < hmin:
        pc = {}
        for s in phrs:
            for p in s:
                pc[p] = pc.get(p, 0) + 1
        hook = max(pc.values(), default=0)
    if hook < hmin:
        out.append(finding(
            "no-repeated-hook",
            "no sung line and no %d-word phrase repeats: sing a "
            "hook at least %d times (G5)" % (pwords, hmin)))
    return out


def check_sung_lines(lines, policy=None):
    """G5 singability gate: the BLOCKING findings only ([] = nothing refuses
    the sheet). Meter outside the preferred band is accepted with warning and
    is NOT returned here; use ``audit_sung_lines`` for the full typed
    inventory. Prose-in-sung-block and a missing hook are still refused."""
    return blocking(audit_sung_lines(lines, policy))


def product_tokens(brief):
    return significant((brief or {}).get("product_name"))


def _policy_from_brief(brief):
    """The policy the brief names. ``constraint_mode`` (dramatization |
    standard) and ``duration_s``/``length_s`` are the writer's constraint
    inputs -- ``brief["mode"]`` stays the intake's own concept/standard key."""
    b = brief if isinstance(brief, dict) else {}
    dur = b.get("duration_s", b.get("length_s"))
    return constraint_policy(b.get("constraint_mode"), dur)


def _res(outcome, reason_code, errors, lines, coverage,
         warnings=None, decisions=None, policy=None):
    warnings, decisions = warnings or [], decisions or []
    return {
        "schema_version": SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "outcome": outcome,
        "reason_code": reason_code,
        "errors": errors,
        # findings is blocking-only BY CONTRACT: any(findings) can never
        # convert a warning into a failure (spec 15.3). Warnings travel to
        # final delivery in "warnings"; "quality_findings" is the full audit.
        "findings": blocking(errors),
        "warnings": warnings,
        "decisions": decisions,
        "quality_findings": list(errors) + warnings + decisions,
        "quality": {"required_correction": len(blocking(errors)),
                    "accept_with_warning": len(warnings),
                    "user_decision_required": len(decisions)},
        "constraint_policy": CONSTRAINT_POLICY_VERSION,
        "policy": policy,
        "line_count": len(lines) if isinstance(lines, list) else 0,
        "coverage": coverage,
        "next_action": (
            "Proceed to lyric QC." if outcome == "ok"
            else "A user decision is required before proceeding (see "
                 "decisions)." if outcome == "decision"
            else "Fix the listed lyric errors and re-run validate_lyrics."
        ),
    }


def _from_findings(errors, warnings, decisions, lines, coverage, policy):
    """THE findings-to-verdict mapping: only a required correction refuses,
    a decision holds for the user, a warning rides along on an ok verdict."""
    errors = blocking(errors)
    if errors:
        return _res("rejected", errors[0]["error"], errors, lines, coverage,
                    warnings, decisions, policy)
    if decisions:
        return _res("decision", decisions[0]["error"], errors, lines, coverage,
                    warnings, decisions, policy)
    if warnings:
        return _res("ok", "lyrics-valid-with-warnings", errors, lines, coverage,
                    warnings, decisions, policy)
    return _res("ok", "lyrics-valid", errors, lines, coverage,
                warnings, decisions, policy)


def validate_lyrics(lines, brief=None, policy=None, require_cast=False):
    """Validate sung lines against the brief. Returns outcome/reason/coverage.

    WW-27: the CAST DECISION is taken FIRST. A declared cast that is not a
    complete ensemble refuses here, before one line is judged, so drafting never
    begins on a broken cast; with no declared cast nothing changes.

    S75-T13: ``require_cast`` fails closed on an absent cast, and a brief that
    carries the foundation envelope (``episode_cast_manifest``) always does --
    so the new authoring shape cannot bypass the gate by omitting cast fields.
    New script-authoring callers use ``validate_authored_lyrics``, which sets
    it and offers no way to turn it off.

    D09: the resolved ``constraint_policy`` (mode + duration) is passed down
    verbatim and echoed in the result, so the writer receives exactly the
    constraints downstream enforces. Only required corrections refuse; warnings
    ride along on an ok verdict and decisions hold for the user.
    """
    brief = brief or {}
    pol = policy or _policy_from_brief(brief)
    cast_rcpt = _cast_gate(brief, required=require_cast)
    if cast_rcpt is not None and cast_rcpt["reasons"]:
        return _with_cast(
            _res("rejected", cast_rcpt["reason_code"],
                 [{"error": cast_rcpt["reason_code"].lower().replace("_", "-"),
                   "detail": m} for m in cast_rcpt["reasons"]],
                 lines, {"critical_words": 0, "covered": 0, "missing": []},
                 policy=pol), cast_rcpt)
    if not isinstance(lines, list) or not lines:
        return _with_cast(
            _res("rejected", "lyrics-empty",
                 [{"error": "lyrics-empty",
                   "detail": "lyrics must be a non-empty list"}],
                 lines, {"critical_words": 0, "covered": 0, "missing": []},
                 policy=pol), cast_rcpt)

    errors, seen, ok_lines = [], set(), []
    client_runs = client_word_runs(brief)
    crit_words = brief_words(brief)
    prod = product_tokens(brief)

    for i, ln in enumerate(lines):
        tag = "line %d" % i
        if not isinstance(ln, dict):
            errors.append({"error": "line-not-an-object", "detail": tag})
            continue
        lid = ln.get("line_id")
        if not isinstance(lid, str) or not LINE_ID_RE.match(lid):
            errors.append({"error": "line-id-invalid", "detail": "%s: %r" % (tag, lid)})
            lid = tag
        elif lid in seen:
            errors.append({"error": "line-id-duplicate", "detail": lid})
        seen.add(lid if isinstance(lid, str) else tag)

        text = ln.get("text")
        if not isinstance(text, str) or not text.strip():
            errors.append({"error": "line-empty", "detail": lid})
            continue
        toks = words(text)
        if len(toks) > MAX_WORDS:
            errors.append({"error": "line-too-long",
                           "detail": "%s: %d words, max %d" % (lid, len(toks), MAX_WORDS)})
        core = text.strip().rstrip(".!?;").lower()
        # a dot inside a word (VoyageToVirtue.com, 3.5) is not a sentence break
        if re.search(r"[.!?;]", re.sub(r"(?<=\w)\.(?=\w)", "", core)):
            errors.append({"error": "line-multi-idea",
                           "detail": "%s: one idea per line" % lid})
        cta = "cta" in str(lid).lower()
        if not cta and not (set(toks) & FIRST_PERSON) \
                and not client_run_inside(exempt_tokens(text), client_runs):
            errors.append({"error": "line-not-first-person", "detail": lid})

        ltoks = set(toks)
        hits = sorted(crit_words & ltoks)
        if hits and ln.get("critical") is not True:
            errors.append({"error": "critical-missing",
                           "detail": "%s: carries %s but critical != true" % (lid, hits)})

        ptoks = sorted(prod & ltoks)
        pmap = ln.get("pronunciation_map")
        if ptoks:
            if not isinstance(pmap, dict) or not pmap:
                errors.append({"error": "pronunciation-missing",
                               "detail": "%s: names product %s, needs pronunciation_map" % (lid, ptoks)})
            else:
                for k, v in pmap.items():
                    if not isinstance(v, str) or not v.strip():
                        errors.append({"error": "pronunciation-invalid",
                                       "detail": "%s: map[%r] must be a non-empty string" % (lid, k)})
                    elif str(k).lower() not in text.lower():
                        errors.append({"error": "pronunciation-key-absent",
                                       "detail": "%s: map key %r not in line text" % (lid, k)})
        elif isinstance(pmap, dict):
            for k, v in pmap.items():
                if not isinstance(v, str) or not v.strip():
                    errors.append({"error": "pronunciation-invalid",
                                   "detail": "%s: map[%r] must be a non-empty string" % (lid, k)})
                elif str(k).lower() not in text.lower():
                    errors.append({"error": "pronunciation-key-absent",
                                   "detail": "%s: map key %r not in line text" % (lid, k)})
        ok_lines.append(ln)

    # W-G-002 amend (review G5): lines marked sung must be singable. The
    # audit is typed (D09): meter outside the preferred band is a warning.
    errors.extend(audit_sung_lines(lines, pol))

    # H7: the sheet may not change a protected name or rewrite a packet line.
    packet = brief.get("packet_lines")
    # FU-U4: concept mode without the client's lines is refused, never passed.
    for msg in protected_names.packet_required(brief, packet):
        errors.append({"error": "packet-required-in-concept-mode", "detail": msg})
    if packet is not None:
        for msg in protected_names.check_sheet(
                lines, packet, protected_names.protected_list(brief)):
            errors.append({"error": msg.split()[0].lower().replace("_", "-"),
                           "detail": msg})

    covered = {w for ln in ok_lines if ln.get("critical") is True
               for w in crit_words & set(words(ln.get("text") or ""))}
    missing = sorted(crit_words - covered)
    if missing:
        errors.append({"error": "coverage-missing",
                       "detail": "critical words with no critical line: %s" % missing})
    coverage = {"critical_words": len(crit_words), "covered": len(covered), "missing": missing}

    # D09 three quality outcomes: partition before the verdict. Untyped
    # (legacy) findings are required corrections; only typed warnings and
    # decisions leave the refuse list.
    warnings = [f for f in errors if f.get("quality") == Q_WARNING]
    decisions = [f for f in errors if f.get("quality") == Q_DECISION]
    return _with_cast(
        _from_findings(blocking(errors), warnings, decisions,
                       lines, coverage, pol), cast_rcpt)


def _spoken_share():
    try:
        import spoken_share as ss               # core/ on sys.path
    except ImportError:
        from .. import spoken_share as ss       # imported as core.*
    return ss


def spoken_word_budget(sections):
    """SPK001: judge a lyric sheet's spoken lines against the word budget
    derived from the ad's spoken target (spoken_share.spoken_word_budget_pct,
    default 20-25% of runtime). ``sections`` = [{"delivery", "lines"}]. The rule
    and the numbers are owned by core/spoken_share; nothing re-derived."""
    return _spoken_share().check_spoken_word_budget(sections)


def steer_opening(blocks, length_s=None, basis="planned"):
    """H6: steer the sheet's opening toward first real singing at 15% of
    runtime (about 9 s in a 60 s ad). ``blocks`` is the planned timeline
    [{"delivery": "spoken"|"sung"|"rap", "seconds": n}, ...]; pass the
    vocal-stem measurement with basis="measured" for a take. Returns the
    spoken_share verdict plus action (keep / shorten_opener /
    lengthen_opener / add_sung_hook) and move_by_s: how far to move the
    sung hook. One rule, owned by core/spoken_share; nothing re-derived.
    """
    ss = _spoken_share()
    res = ss.steer_first_sung(blocks, basis)
    if length_s is not None:
        res["plan_target_s"] = ss.seconds_for(length_s)["first_sung_target_s"]
    return res


def validate_authored_lyrics(lines, brief=None, policy=None):
    """S75-T13: THE lyric entry for a new script-authoring path.

    The cast foundation is required, unconditionally: an absent ``cast`` /
    ``cast_mode`` / ``cast_decision`` or an absent/empty/invalid
    ``episode_cast_manifest`` refuses with a named missing-input code before a
    single line is judged. There is no argument that turns it off, so an
    authoring caller cannot bypass ``_cast_gate`` by omitting cast fields.
    """
    return validate_lyrics(lines, brief, policy=policy, require_cast=True)


def validate_campaign(campaign):
    """Validate a campaign record's lyrics (campaign-schema shape) + brief."""
    if not isinstance(campaign, dict):
        return _res("error", "campaign-not-an-object",
                    [{"error": "campaign-not-an-object", "detail": "campaign must be a JSON object"}],
                    None, {"critical_words": 0, "covered": 0, "missing": []})
    if not isinstance(campaign.get("brief"), dict):
        return _res("rejected", "brief-missing",
                    [{"error": "brief-missing", "detail": "campaign.brief object is required"}],
                    campaign.get("lyrics"), {"critical_words": 0, "covered": 0, "missing": []})
    return validate_lyrics(campaign.get("lyrics"), campaign.get("brief"))


def load_fixture(name):
    with open(FIXTURE_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def selftest():
    checks, fails = [], []

    def expect(name, want_outcome, want_reason):
        try:
            fx = load_fixture(name)
        except (OSError, json.JSONDecodeError) as e:
            checks.append(name)
            fails.append("%s: unreadable (%s)" % (name, e))
            return
        r = validate_lyrics(fx.get("lines"), fx.get("brief"))
        ok = r["outcome"] == want_outcome and (
            want_reason is None or r["reason_code"] == want_reason)
        checks.append(name)
        if not ok:
            fails.append("%s: outcome=%s reason=%s, want %s/%s"
                         % (name, r["outcome"], r["reason_code"],
                            want_outcome, want_reason))

    expect("valid.json", "ok", "lyrics-valid")
    expect("missing-critical.json", "rejected", "critical-missing")
    expect("coverage-gap.json", "rejected", "coverage-missing")
    expect("multi-idea.json", "rejected", "line-multi-idea")
    expect("not-first-person.json", "rejected", "line-not-first-person")
    expect("pronunciation-missing.json", "rejected", "pronunciation-missing")

    for bad in (None, [], {"lines": [], "brief": {}}):
        r = validate_lyrics(bad if isinstance(bad, list) else (bad or {}).get("lines"),
                            (bad or {}).get("brief") if isinstance(bad, dict) else None)
        checks.append("inline:%r" % (str(bad)[:40],))
        if r["outcome"] == "ok":
            fails.append("inline %r accepted, want reject" % (bad,))

    # CTA exemption holds: second-person imperative with cta line_id passes
    r = validate_lyrics(
        [{"line_id": "cta01", "text": "Tap to claim your kit today", "critical": True}],
        {"product_name": "", "offer_text": "", "cta_text": "Tap to claim your kit",
         "claims": []})
    checks.append("cta-exempt")
    if r["outcome"] != "ok":
        fails.append("cta-exempt rejected: %s" % r["reason_code"])

    # v2.9.70 stage-3 deadlock: client verbatim / URL dot / still-strict cases
    vbrief = {"offer": "Voyage To Virtue: A Journey of Becoming",
              "website": "VoyageToVirtue.com/journeyofbecoming",
              "claims": [{"id": "c4", "text": "virtue isn't something you have"
                          " - it's something you choose"}]}
    for name, line, brief, want_ok, want_reason in (
        ("client-verbatim-passes",
         {"line_id": "h1a", "text": "Virtue isn't something you have"},
         vbrief, True, None),
        ("invented-second-person-rejects",
         {"line_id": "h1a", "text": "You never had a choice"},
         vbrief, False, "line-not-first-person"),
        ("client-two-word-fragment-rejects",
         {"line_id": "h1a", "text": "Virtue isn't"},
         vbrief, False, "line-not-first-person"),
        ("url-line-passes",
         {"line_id": "cta2", "text": "at VoyageToVirtue.com/journeyofbecoming"},
         vbrief, True, None),
        ("two-sentences-rejects",
         {"line_id": "v1", "text": "I rise. I fall"},
         {}, False, "line-multi-idea"),
        ("packet-string-verbatim-passes",
         {"line_id": "h1a", "text": "Nobody ever asks the strong one"},
         {"packet_lines": "Nobody ever asks the strong one\nI take my name"},
         True, None),
        # a brief pasted from Word carries a CURLY apostrophe; the written
        # lyric usually carries a straight one. Same words, same exemption.
        ("curly-brief-straight-lyric-passes",
         {"line_id": "h1a", "text": "Virtue isn't something you have"},
         {"claims": [{"text": "virtue isn\u2019t something you have"}]}, True, None),
        ("straight-brief-curly-lyric-passes",
         {"line_id": "h1a", "text": "Virtue isn\u2019t something you have"},
         {"claims": [{"text": "virtue isn't something you have"}]}, True, None)):
        r = validate_lyrics([line], brief)
        checks.append(name)
        errs = {e["error"] for e in r["errors"]}
        if want_ok and errs & {"line-not-first-person", "line-multi-idea"}:
            fails.append("%s: %s" % (name, sorted(errs)))
        if not want_ok and want_reason not in errs:
            fails.append("%s: %s not raised (%s)" % (name, want_reason, sorted(errs)))

    # ---- D09: the one constraint policy (spec 6.3 / 15.3) ----------------
    def t(name, cond, why=""):
        checks.append(name)
        if not cond:
            fails.append("%s: %s" % (name, why))

    pol = constraint_policy()
    t("policy-version",
      pol["policy_version"] == CONSTRAINT_POLICY_VERSION, pol["policy_version"])
    try:
        constraint_policy("no-such-mode")
        t("unknown-mode-refused", False, "accepted")
    except ValueError:
        t("unknown-mode-refused", True)
    try:
        constraint_policy(duration_s="x")
        t("bad-duration-refused", False, "accepted")
    except ValueError:
        t("bad-duration-refused", True)
    pol60 = constraint_policy(duration_s=60)
    t("duration-aware",
      pol60["hook"]["first_sung_target_s"] == 9.0
      and pol60["spoken_share"]["budget_s"] == [7.5, 19.5],
      "%s %s" % (pol60["hook"].get("first_sung_target_s"),
                 pol60["spoken_share"].get("budget_s")))
    t("d09-legacy-8-retired-as-bound",
      pol["sung_meter"]["performable"] == (1, 12)
      and pol["sung_meter"].get("provider_cap") is None, repr(pol["sung_meter"]))
    ls_mod = _structure()
    sung11 = "I " + " ".join(["la"] * 10)      # 11 syllables
    sung9 = "I " + " ".join(["la"] * 8)        # 9 syllables
    t("counterexample-shape",
      ls_mod.line_syllables(sung11) == 11 and ls_mod.line_syllables(sung9) == 9,
      "%d/%d" % (ls_mod.line_syllables(sung11), ls_mod.line_syllables(sung9)))

    def sung_pair(text):
        return [{"line_id": "h1", "delivery": "sung", "text": text},
                {"line_id": "h2", "delivery": "sung", "text": text}]

    # 11-syllable counterexample passes the WRITER and the RECIPE's rule
    # under one policy (the recipe's <=8 hard bound is retired).
    r11 = validate_lyrics(sung_pair(sung11), {})
    t("d09-11syl-passes-writer",
      r11["outcome"] == "ok", "%s/%s" % (r11["outcome"], r11["reason_code"]))
    f11 = sung_meter_finding(ls_mod.line_syllables(sung11), pol)
    t("d09-11syl-passes-recipe-rule",
      f11 is None or f11["quality"] == Q_WARNING, repr(f11))
    t("d09-11syl-warns-never-fails",
      not r11["findings"] and not r11["errors"] and r11["warnings"]
      and all(w["quality"] == Q_WARNING for w in r11["warnings"]),
      "%s %s" % (r11["findings"], r11["warnings"]))

    # 9-syllable acceptance cannot be contradicted downstream without a
    # clear mode-specific reason.
    r9 = validate_lyrics(sung_pair(sung9), {})
    t("d09-9syl-accepted",
      r9["outcome"] == "ok", "%s/%s" % (r9["outcome"], r9["reason_code"]))
    f9 = sung_meter_finding(ls_mod.line_syllables(sung9), pol)
    t("d09-9syl-not-contradicted",
      f9 is None or f9["quality"] == Q_WARNING, repr(f9))
    f9s = sung_meter_finding(ls_mod.line_syllables(sung9),
                             constraint_policy("standard"))
    t("d09-9syl-contradicted-only-with-mode-reason",
      f9s is not None and f9s.get("blocking") and f9s.get("mode_reason"),
      repr(f9s))

    # Warning propagation to final delivery: no seam converts a warning
    # into failure (generic any-findings check, exit-code mapper, downstream
    # aggregator, Command Center projection).
    t("seam-any-findings-never-fires",
      not any(r9["findings"]) and not any(r9["errors"]),
      "%s" % (r9["findings"],))
    t("seam-exit-code-mapper", exit_code_for(r9) == 0, exit_code_for(r9))
    t("seam-aggregator",
      aggregate_status([r9, r11]) == "accepted_with_warnings",
      aggregate_status([r9, r11]))
    t("seam-cc-projection",
      delivery_status(r9) == "accepted_with_warnings", delivery_status(r9))
    rclean = validate_lyrics(
        [{"line_id": "cta01", "text": "Tap to claim your kit today",
          "critical": True}],
        {"product_name": "", "offer_text": "", "cta_text": "Tap to claim your kit",
         "claims": []})
    t("seam-clean-accepted",
      delivery_status(rclean) == "accepted"
      and aggregate_status([rclean, r9]) == "accepted_with_warnings",
      "%s %s" % (delivery_status(rclean), aggregate_status([rclean, r9])))
    rdec = _from_findings(
        [], [], [finding("sung-meter-unmeasurable", "x", Q_DECISION)],
        [], {"critical_words": 0, "covered": 0, "missing": []}, pol)
    t("seam-decision-not-failure",
      rdec["outcome"] == "decision" and exit_code_for(rdec) == EXIT["decision"]
      and delivery_status(rdec) == "user_decision_required"
      and aggregate_status([rdec, r9]) == "user_decision_required",
      "%s %s" % (rdec["outcome"], delivery_status(rdec)))
    t("d09-unmeasurable-decides",
      sung_meter_finding(None, pol, measurable=False)["quality"] == Q_DECISION)
    t("d09-over12-corrected",
      sung_meter_finding(13, pol)["quality"] == Q_REQUIRED)
    t("d09-slot-infeasible-corrected",
      sung_meter_finding(7, pol, slot_s=1.0)["quality"] == Q_REQUIRED)

    # Spoken scenes outside Intro/Outro preserved (dramatization); the
    # legacy placement rule survives only in mode "standard", with a reason.
    sheet = [{"tag": "Intro", "delivery": "spoken", "lines": ["One closed door."]},
             {"tag": "Scene 2", "delivery": "spoken",
              "lines": ["I lost everything that winter."]},
             {"tag": "Outro", "delivery": "spoken", "lines": ["Get the book."]}]
    t("d09-mid-song-spoken-preserved",
      spoken_section_findings(sheet, pol) == [],
      repr(spoken_section_findings(sheet, pol)))
    fsp = spoken_section_findings(sheet, constraint_policy("standard"))
    t("d09-spoken-legacy-rule-mode-specific",
      len(fsp) == 1 and fsp[0].get("mode_reason"), repr(fsp))
    rsc = validate_lyrics(
        [{"line_id": "sc1", "text": "I lost everything that winter."}], {})
    t("d09-spoken-scene-kept-by-writer",
      rsc["outcome"] == "ok" and rsc["line_count"] == 1,
      "%s %s" % (rsc["outcome"], rsc["line_count"]))

    # Mirrored constraints equal their owners: the writer receives exactly
    # the constraints downstream enforces (drift guard).
    try:
        from spoken_share import spoken_share as ss_mod
        t("mirror-spoken_share",
          pol["spoken_share"]["target_pct"] == ss_mod.SPOKEN_TARGET_PCT
          and pol["spoken_share"]["min_pct"] == ss_mod.SPOKEN_MIN_PCT
          and pol["spoken_share"]["max_pct"] == ss_mod.SPOKEN_MAX_PCT
          and pol["spoken_share"]["sung_of_voice_pct"] == ss_mod.SUNG_TARGET_PCT
          and pol["spoken_share"]["accept_pts"] == ss_mod.ACCEPT_PTS
          and pol["spoken_share"]["flag_pts"] == ss_mod.FLAG_PTS
          and pol["hook"]["first_sung_target_pct"]
          == ss_mod.FIRST_SUNG_TARGET_PCT,
          "policy mirrors drift from core/spoken_share")
    except Exception as e:  # noqa: BLE001  an unreadable owner is UNCHECKED
        t("mirror-spoken_share", False, "mirror UNCHECKED: %s" % e)
    try:
        from words_fit import words_fit as wf_mod
        t("mirror-words_fit",
          pol["words_fit"]["intro_outro_s"] == wf_mod.INTRO_OUTRO_S
          and pol["words_fit"]["headroom"] == wf_mod.HEADROOM,
          "policy mirrors drift from core/words_fit")
    except Exception as e:  # noqa: BLE001
        t("mirror-words_fit", False, "mirror UNCHECKED: %s" % e)
    try:
        from suno_recipe import suno_recipe as sr_mod
        t("mirror-suno_recipe",
          pol["hook"]["min_repeats"] == sr_mod.MIN_HOOK_REPEATS,
          "policy mirrors drift from core/suno_recipe")
    except Exception as e:  # noqa: BLE001
        t("mirror-suno_recipe", False, "mirror UNCHECKED: %s" % e)

    print("lyric_writer selftest: %s (%d checks, %d failures)"
          % ("PASS" if not fails else "FAIL", len(checks), len(fails)))
    for f in fails:
        print(" -", f)
    return 0 if not fails else 1


def main(argv=None):
    ap = argparse.ArgumentParser(prog="lyric_writer.py",
                                 description="Sung-copy rules over campaign-schema lyrics.")
    ap.add_argument("--selftest", action="store_true", help="Run QC fixtures.")
    ap.add_argument("--lyrics", default=None, help="JSON file: campaign record or fixture.")
    ap.add_argument("--brief", default=None, help="JSON file: brief (skip if lyrics file is a campaign).")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.lyrics:
        ap.error("one of --selftest or --lyrics is required")
    try:
        with open(a.lyrics, encoding="utf-8") as f:
            doc = json.load(f)
        brief = None
        if a.brief:
            with open(a.brief, encoding="utf-8") as f:
                brief = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        r = {"schema_version": SCHEMA_VERSION, "tool_version": TOOL_VERSION,
             "outcome": "error", "reason_code": "lyrics-unreadable",
             "errors": [{"error": "lyrics-unreadable", "detail": str(e)[:200]}],
             "line_count": 0, "coverage": {"critical_words": 0, "covered": 0, "missing": []},
             "next_action": "Supply readable JSON lyric input."}
    else:
        if (isinstance(doc, dict) and isinstance(doc.get("brief"), dict)
                and "lines" not in doc and isinstance(doc.get("lyrics"), list)):
            r = validate_campaign(doc)
        elif isinstance(doc, dict) and "lines" in doc:
            r = validate_lyrics(doc.get("lines"), doc.get("brief") if brief is None else brief)
        else:
            r = validate_lyrics(doc if isinstance(doc, list) else None, brief)
    json.dump(r, sys.stdout, indent=2, sort_keys=True, default=str)
    sys.stdout.write("\n")
    return exit_code_for(r)


if __name__ == "__main__":
    sys.exit(main())
