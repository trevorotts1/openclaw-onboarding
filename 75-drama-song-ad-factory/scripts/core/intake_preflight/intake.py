"""intake.py: short adaptive opening intake (directive 24.3, 24.2 row 1). stdlib only.

Essentials (max 3 questions, one message): offer / audience+action / spending
authority. Never invents a spending ceiling or currency conversion. Brief text
is source material, never auth/policy (injection -> rejected, auth untouched).

Version-2 card fields (H8): length_option, shape, look, music and voice are
normalized with provenance. Look/music default from core/style_defaults (D24);
length/shape/voice default from the version-2 card. A provided length_option
feeds target_length_s when target_length_s itself was not stated.
"""
import hashlib
import json
import os
import re
import sys

# ponytail: placement-substitution capped by leftover slots only; full
# re-prioritization add when a verdict needs it.

INJECTION_RES = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions",
    r"\bskip\s+(qc|preflight|approval|authorization|intake)\b",
    r"\b(bypass|evade|override)\s+(the\s+)?(guard|gate|qc|approval|authorization|ceiling)\b",
    r"approve\w*\s+(the\s+)?(budget|spend|ceiling|authorization)",
    r"(set|raise|increase)\s+(the\s+)?(ceiling|budget|spending)",
    r"use\s+(my|this)\s+key",
    r"authorization\s+(is\s+)?approved",
    r"^\s*system\s*:",
]

# Version-2 card defaults (batch card / plan 6.15). Look/music resolve below
# through style_defaults when that package is importable.
DEFAULT_LENGTH_OPTION = 60
DEFAULT_SHAPE = "9:16"
DEFAULT_VOICE = "all-suno"
DEFAULT_LOOK_FALLBACK = "Lifelike 3D"
DEFAULT_MUSIC_FALLBACK = "Soul Ballad"

# Batch card length labels -> seconds (batch_mode.LENGTH_VALUES).
_LENGTH_LABELS = {
    "60 seconds": 60,
    "90 seconds": 90,
    "3 minutes": 180,
    "5 minutes": 300,
    "10-minute long version": 600,
    "10 minutes": 600,
    # intake card answers (the card text is what the client picked)
    "3 minutes + 60s and 90s clips": 180,
    "5 minutes + 60s and 90s clips": 300,
    "10 minutes (the long version) + 60s and 90s clips": 600,
}

_SHAPE_ALIASES = {
    "9:16": "9:16",
    "9x16": "9:16",
    "9:16 vertical": "9:16",
    "vertical": "9:16",
    "16:9": "16:9",
    "16x9": "16:9",
    "16:9 widescreen": "16:9",
    "widescreen": "16:9",
    "both": "both",
}


def _load_style_defaults():
    """(look, music, source) from core/style_defaults (D24); else hardcoded."""
    core = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if core not in sys.path:
        sys.path.insert(0, core)
    try:
        import style_defaults as SD  # noqa: PLC0415
        pair = SD.default_pair()
        look = pair.get("style_label") or pair.get("style") or DEFAULT_LOOK_FALLBACK
        music = (pair.get("music_style_label") or pair.get("music_style")
                 or DEFAULT_MUSIC_FALLBACK)
        return look, music, "default"
    except Exception:  # noqa: BLE001 - package missing/broken: keep intake alive
        return DEFAULT_LOOK_FALLBACK, DEFAULT_MUSIC_FALLBACK, "assumed"


DEFAULT_LOOK, DEFAULT_MUSIC, _LOOK_MUSIC_SOURCE = _load_style_defaults()


def _load_card_gate():
    """card_gate (F15) when style_defaults is importable, else None."""
    core = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if core not in sys.path:
        sys.path.insert(0, core)
    try:
        import style_defaults.card_gate as CG  # noqa: PLC0415
        return CG
    except Exception:  # noqa: BLE001 - gate missing: fail closed in-card below
        return None


_CARD_GATE = _load_card_gate()
#: F15 fail-closed copy for the (defensive) case card_gate cannot import:
#: the gate must never open just because a module is missing.
_CARD_UNANSWERED = "CARD_UNANSWERED"
_CARD_NEXT_ACTION = ("Show the choice card and record all four answers "
                     "(video style, audio style, length, video model) with "
                     "who and when before any paid job.")

def _card_refusal(run_state):
    """F15: (reason, next_action) when the run state lacks the recorded
    card receipt; None when the card is answered. Falls back to a local
    fail-closed check of the four fields when card_gate is unavailable."""
    record = None
    if isinstance(run_state, dict):
        record = run_state.get("card_receipt")
        if not isinstance(record, dict):
            inner = run_state.get("card") or run_state.get("choice_card")
            record = inner if isinstance(inner, dict) else None
    if _CARD_GATE is not None:
        ok, refusal = _CARD_GATE.gate_run_state(record)
        return (refusal["reason_code"], refusal["next_action"]) if not ok else None
    if not isinstance(record, dict):
        return _CARD_UNANSWERED, _CARD_NEXT_ACTION
    for f in ("video_style", "audio_style", "length", "video_model"):
        v = record.get(f, run_state.get(f) if isinstance(run_state, dict) else None)
        if v is None or (isinstance(v, str) and not v.strip()):
            return _CARD_UNANSWERED, _CARD_NEXT_ACTION
    return None

DEFAULTS = {
    "placement": "unspecified (default: 9:16 vertical)",
    "aspect_ratio": "unspecified (default: 9:16)",
    "target_length_s": 60,
    "brand_rules": "unspecified (default: none)",
    "creative_prefs": "unspecified (default: none)",
    "repair_allowance": "unspecified (default: none authorized)",
    "length_option": DEFAULT_LENGTH_OPTION,
    "shape": DEFAULT_SHAPE,
    "look": DEFAULT_LOOK,
    "music": DEFAULT_MUSIC,
    "voice": DEFAULT_VOICE,
}

Q_OFFER = "What product/offer are we promoting, and what link or assets should we use?"
Q_AUDIENCE = ("Who is this ad for, and what should they do after watching it?\n"
              "For example: 'Women 35-55 who want a second income - register for my free masterclass.'")
Q_AUDIENCE_ONLY = ("Who is this ad for? "
                   "For example: 'Women 35-55 who want a second income.'")
Q_ACTION_ONLY = ("What should people do after watching? "
                 "For example: 'Register for my free masterclass.'")
Q_SPENDING = "What is the most you want to spend on this video? For example: $25."
Q_WEBSITE = ("What is the exact website address you want people to go to? "
             "Type it exactly as it should appear, for example: example.com. "
             "We will use it word for word in the song, captions and end card.")
Q_PLACEMENT = "What placement/format should we produce (aspect ratio + target length)?"

APPROVAL_AFFECTING = ("offer", "audience", "action", "budget_minor", "budget_currency")


def _fmt(texts):
    """question_message: one block per question, blank line between (H9)."""
    core = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if core not in sys.path:
        sys.path.insert(0, core)
    from choice_card.intake_card import format_questions  # noqa: PLC0415
    return format_questions(texts)


def _text(v):
    return v.strip() if isinstance(v, str) and v.strip() else None


def _as_length(v):
    """Card/brief length -> positive seconds when parseable, else raw text.

    None means "not stated": 60/90 numbers, the batch-card labels ("3 minutes")
    and plain "90s"/"3m" spellings all convert; anything else passes through
    unchanged so a caller's own length never silently disappears.
    """
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        n = int(v)
        return n if n > 0 else None
    if isinstance(v, str) and v.strip():
        key = re.sub(r"\s+", " ", v.strip().lower())
        if key in _LENGTH_LABELS:
            return _LENGTH_LABELS[key]
        m = re.match(r"^(\d+)\s*(?:s|sec|secs|second|seconds)?$", key)
        if m and int(m.group(1)) > 0:
            return int(m.group(1))
        m = re.match(r"^(\d+)\s*(?:m|min|mins|minute|minutes)$", key)
        if m and int(m.group(1)) > 0:
            return int(m.group(1)) * 60
        return v.strip()
    return None


def _as_shape(v):
    """Card/brief shape -> canonical 9:16 / 16:9 / both; else raw text."""
    if not isinstance(v, str) or not v.strip():
        return None
    return _SHAPE_ALIASES.get(re.sub(r"\s+", " ", v.strip().lower()), v.strip())


def _load_protected_names():
    """U8: protected_names for the client-word spelling question, else None."""
    core = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if core not in sys.path:
        sys.path.insert(0, core)
    try:
        import protected_names as PN  # noqa: PLC0415
        return PN
    except Exception:  # noqa: BLE001 - module missing: no question, no crash
        return None


_PN = _load_protected_names()

def client_typo_question(fields):
    """U8: (question dict, None) when the CLIENT's own words carry a word
    that is not a real word, else (None, None).

    Doc 18 B.2: a typo in the client's packet is never auto-fixed. It goes
    back as ONE plain question naming the word, and the words are left
    exactly as the client wrote them. Words the client approved
    (``approved_spellings`` on the brief: dialect, vernacular, brand forms)
    are never asked about, and the question rides the story questions -- it
    does not add a fourth slot.
    """
    if _PN is None:
        return None, None
    lines = []
    for value in (fields.get("packet_lines"), fields.get("on_screen_text")):
        lines.extend(_PN._lines(value))
    if not lines:
        return None, None
    protected = list(fields.get("protected") or [])
    extra = list(fields.get("approved_spellings") or [])
    errors = _PN.check_lyrics_spelling(lines, protected, extra)
    if not errors:
        return None, None
    words, seen = [], set()
    for e in errors:
        for tok in _PN._tokens(e.split("word", 1)[-1]):
            if tok and tok not in seen:
                seen.add(tok)
                words.append(tok)
    shown = ", ".join(repr(w) for w in words[:3])
    return ({"id": "client_typo",
             "question": ("Your storyboard says %s. Is that exactly right, "
                          "or did you mean something else? We will use your "
                          "words as written." % shown),
             "words": words}, None)

def detect_injection(brief):
    """NAMES of brief fields whose text matches instruction-override patterns."""
    hits = []
    if not isinstance(brief, dict):
        return hits
    for key, val in brief.items():
        texts = val if isinstance(val, list) else [val]
        for t in texts:
            if not isinstance(t, str):
                continue
            low = t.lower()
            if any(re.search(p, low) for p in INJECTION_RES):
                hits.append(str(key))
                break
    return hits


def normalize(brief, settings=None):
    """Merge brief > settings > visible defaults. Spending never defaulted."""
    brief = brief or {}
    settings = settings or {}
    fields, prov = {}, {}

    def take(name, *sources):
        for value, src in sources:
            if value is not None:
                fields[name] = value
                prov[name] = src
                return
        fields[name] = None
        prov[name] = "missing"

    b = lambda k: _text(brief.get(k))  # noqa: E731
    s = lambda k: _text((settings.get("defaults") or {}).get(k)) if isinstance(settings.get("defaults"), dict) else None  # noqa: E731
    sdef = settings.get("defaults") if isinstance(settings.get("defaults"), dict) else {}

    take("offer", (b("offer"), "provided"), (s("offer"), "inherited"))
    assets = brief.get("assets") or brief.get("link") or settings.get("assets")
    if isinstance(assets, str) and assets.strip():
        assets = [assets.strip()]
    take("assets", (assets or None, "provided" if "assets" in brief or "link" in brief else "inherited"))
    take("audience", (b("audience"), "provided"), (s("audience"), "inherited"))
    take("action", (b("action") or b("cta"), "provided"), (s("action"), "inherited"))
    bmin = brief.get("budget_minor", brief.get("budget_amount_minor"))
    smin = sdef.get("budget_minor")
    take("budget_minor", ((bmin if isinstance(bmin, int) and bmin > 0 else None), "provided"),
         ((smin if isinstance(smin, int) and smin > 0 else None), "inherited"))
    # credits still accepted: budget_currency may be "credits" or a fiat code
    take("budget_currency", (b("budget_currency") or b("currency"), "provided"), (s("budget_currency"), "inherited"))
    take("website", (b("website"), "provided"), (s("website"), "inherited"))
    for name in ("placement", "aspect_ratio", "brand_rules", "creative_prefs", "repair_allowance"):
        take(name, (b(name), "provided"), (s(name), "inherited"), (DEFAULTS[name], "assumed"))

    # --- version-2 card fields (H8), with provenance -------------------------
    take("length_option",
         (_as_length(brief.get("length_option")), "provided"),
         (_as_length(sdef.get("length_option")), "inherited"),
         (DEFAULT_LENGTH_OPTION, "default"))
    take("shape",
         (_as_shape(brief.get("shape")), "provided"),
         (_as_shape(sdef.get("shape")), "inherited"),
         (DEFAULT_SHAPE, "default"))

    take("look", (b("look"), "provided"), (s("look"), "inherited"),
         (DEFAULT_LOOK, _LOOK_MUSIC_SOURCE))
    take("music", (b("music"), "provided"), (s("music"), "inherited"),
         (DEFAULT_MUSIC, _LOOK_MUSIC_SOURCE))
    take("voice", (b("voice"), "provided"), (s("voice"), "inherited"),
         (DEFAULT_VOICE, "default"))

    tlen = brief.get("target_length_s", sdef.get("target_length_s"))
    take("target_length_s", ((tlen if isinstance(tlen, (int, float)) and tlen > 0 else None),
                             "provided" if "target_length_s" in brief else "inherited"),
         (DEFAULTS["target_length_s"], "assumed"))
    # A card length_option wins over the assumed 60s default, never over an
    # explicit target_length_s.
    if isinstance(fields.get("length_option"), int) and prov.get("target_length_s") == "assumed":
        fields["target_length_s"] = fields["length_option"]
    return fields, prov


_WEBSITE_RE = re.compile(r"\b(web\s?site|web\s?page|url|link|visit|go to|\w+\.(com|net|org|co|io|us))\b", re.I)


def wants_website(fields):
    """I1: the ad sends people to a website and the exact address is unknown."""
    if fields.get("website"):
        return False
    return bool(_WEBSITE_RE.search("%s %s" % (fields.get("action") or "", fields.get("offer") or "")))


def missing_essentials(fields, prov):
    """At most 3 questions. Placement substitutes into leftover slots only."""
    qs = []
    if not fields.get("offer"):
        qs.append({"id": "offer", "question": Q_OFFER})
    no_aud, no_act = not fields.get("audience"), not fields.get("action")
    if no_aud or no_act:
        # Ask only for the piece that is missing; same id either way.
        qs.append({"id": "audience_action",
                   "question": Q_AUDIENCE if no_aud and no_act
                   else Q_AUDIENCE_ONLY if no_aud else Q_ACTION_ONLY})
    if not isinstance(fields.get("budget_minor"), int) or not fields.get("budget_currency"):
        qs.append({"id": "spending_authority", "question": Q_SPENDING})
    if wants_website(fields) and len(qs) < 3:
        qs.append({"id": "website", "question": Q_WEBSITE})
    qs = qs[:3]
    ambiguous = prov.get("placement") == "assumed" and len(qs) < 3
    if ambiguous and not any(q["id"] == "placement" for q in qs):
        qs.append({"id": "placement", "question": Q_PLACEMENT})
    return qs[:3]


def _master_max(length_s):
    """I4: the master is planned and QC'd to chosen length minus 2 seconds."""
    core = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if core not in sys.path:
        sys.path.insert(0, core)
    from master_length import master_max_s  # noqa: PLC0415
    try:
        return master_max_s(length_s)
    except ValueError:
        return None


def summarize(fields, auth_status="missing"):
    summary = {
        "offer": fields.get("offer"),
        "assets": fields.get("assets"),
        "audience": fields.get("audience"),
        "cta": fields.get("action"),
        "website": fields.get("website"),
        "placement": fields.get("placement"),
        "format": fields.get("aspect_ratio"),
        "target_length_s": fields.get("target_length_s"),
        "master_max_s": _master_max(fields.get("target_length_s")),
        "length_option": fields.get("length_option"),
        "shape": fields.get("shape"),
        "look": fields.get("look"),
        "music": fields.get("music"),
        "voice": fields.get("voice"),
        "assumptions": [f"{k}={v!r} (assumed default)" for k, v in fields.items()
                        if v == DEFAULTS.get(k)],
        "generation_ceiling": {"amount_minor": fields.get("budget_minor"),
                               "currency": fields.get("budget_currency")},
        "repair_allowance": fields.get("repair_allowance"),
        "auth_status": auth_status,
    }
    digest = hashlib.sha256(json.dumps(summary, sort_keys=True, default=str).encode()).hexdigest()[:16]
    return summary, digest


def auth_status_for(fields, digest, settings, now_unix=None):
    """Brief maximum is never an approval receipt; needs explicit auth object."""
    import time
    auth = (settings or {}).get("authorization") or {}
    if not auth:
        return "missing"
    exp = auth.get("expires_unix")
    now = now_unix if now_unix is not None else int(time.time())
    if isinstance(exp, (int, float)) and now > exp:
        return "expired"
    if auth.get("currency") and fields.get("budget_currency") and auth["currency"] != fields["budget_currency"]:
        return "out-of-scope"
    scope = auth.get("scope")
    if scope not in ("campaign", digest):
        return "out-of-scope"
    return "bound"


# --- FU-U4: mode flag and notices ---------------------------------------------
MODES = ("quick", "concept")
MASTER_FPS = 30
_SFX_SPEAKERS = ("sfx", "sound", "sound effect", "sound effects", "fx")
_SFX_RE = re.compile(r"[\[(]\s*([A-Z][A-Z0-9' -]{2,})\s*[\])]")
_ECHO_RE = re.compile(r"\b(echo\w*|reverb\w*)\b", re.I)


def _core_path():
    core = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if core not in sys.path:
        sys.path.insert(0, core)


def mode_of(brief):
    """"concept" when the brief says so, else "quick" (the default)."""
    m = str((brief or {}).get("mode") or "").strip().lower()
    return m if m in MODES else "quick"


def notices(brief, packet_lines=None):
    """Storyboard items the skill will NOT make, as plain notices (never options):
    sound effects, an echo/reverb voice, a length that is not offered, fps.
    Returns [{"kind", "items", "text"}], empty when nothing applies."""
    _core_path()
    from music_styles import music_styles as MS  # noqa: PLC0415
    brief = brief or {}
    lines = packet_lines if packet_lines is not None else brief.get("packet_lines") or []
    sfx = [str(x).strip().upper() for x in (brief.get("sfx") or [])]
    texts = [brief.get("voice"), brief.get("notes")]
    for ln in lines:
        if not isinstance(ln, dict):
            ln = {"text": str(ln)}
        text = str(ln.get("text") or "")
        speaker = str(ln.get("speaker") or "").strip().lower()
        if speaker in _SFX_SPEAKERS or str(ln.get("kind") or "").lower() == "sfx":
            sfx.append(text.strip().upper())
        notes = [ln.get("direction"), ln.get("note")]
        for t in [text] + notes:
            if isinstance(t, str):
                sfx.extend(m.strip().upper() for m in _SFX_RE.findall(t))
        texts += notes
    echo = sorted({m.lower() for t in texts if isinstance(t, str) for m in _ECHO_RE.findall(t)})
    out = []
    sfx = [x for i, x in enumerate(sfx) if x and x not in sfx[:i]]
    if sfx:
        out.append({"kind": "sfx", "items": sfx,
                    "text": "Sound effects (%s) are not made: sound effects stay off." % ", ".join(sfx)})
    if echo:
        out.append({"kind": "echo_voice", "items": echo,
                    "text": "An echo or reverb voice is not made: the voice is dry and close "
                            "(All Suno, or Velvet Voiceover with no echo effect)."})
    n = _as_length(brief.get("length_option") or brief.get("target_length_s"))
    if isinstance(n, int) and n not in MS.OFFERED_LENGTHS_S:
        out.append({"kind": "length_not_offered", "items": [n],
                    "text": "%d seconds is not an offered length; offered lengths are %s seconds."
                            % (n, ", ".join(str(x) for x in MS.OFFERED_LENGTHS_S))})
    fps = brief.get("fps")
    if fps not in (None, "", MASTER_FPS, str(MASTER_FPS)):
        out.append({"kind": "fps", "items": [fps],
                    "text": "%s fps is not made: the master is %d fps." % (fps, MASTER_FPS)})
    return out


def evaluate(brief, settings=None, resume_state=None, run_id=None, now_unix=None):
    """_evaluate plus the FU-U4 mode flag and notices. Concept mode with no
    packet_lines is waiting (PACKET_REQUIRED_IN_CONCEPT_MODE), never ok."""
    r = _evaluate(brief, settings, resume_state, run_id, now_unix)
    r["mode"] = mode_of(brief)
    r["notices"] = notices(brief)
    if r["mode"] == "concept" and r.get("outcome") == "ok" and not (brief or {}).get("packet_lines"):
        r.update(outcome="waiting", reason_code="PACKET_REQUIRED_IN_CONCEPT_MODE",
                 next_action="Concept mode: send the client's own script or storyboard lines "
                             "(brief.packet_lines) before anything else.")
    return r


def _evaluate(brief, settings=None, resume_state=None, run_id=None, now_unix=None):
    settings = settings or {}
    hits = detect_injection(brief or {})
    fields, prov = normalize(brief, settings)
    summary, digest = summarize(fields)
    status = auth_status_for(fields, digest, settings, now_unix)
    summary["auth_status"] = status
    if hits:  # untrusted text never touches auth/summary scope
        return {"outcome": "rejected", "reason_code": "untrusted-injection-blocked",
                "questions": [], "question_message": None, "summary": summary,
                "digest": digest, "provenance": prov, "untrusted_fields": hits,
                "auth_status": status, "approval_invalidated": False, "changes": [],
                "next_action": "Remove instruction language from brief fields and resubmit."}
    # U8: the CLIENT's own words are spell-checked at intake, for free. A
    # word that is not a real word goes BACK AS ONE QUESTION naming it --
    # never an auto-fix, and the brief keeps the client's spelling.
    probe = dict(fields, packet_lines=(brief or {}).get("packet_lines"),
                 on_screen_text=(brief or {}).get("on_screen_text"),
                 approved_spellings=(brief or {}).get("approved_spellings"),
                 protected=(_PN.protected_list(brief)
                            if _PN is not None else []))
    typo, _ = client_typo_question(probe)
    if typo is not None:
        return {"outcome": "waiting", "reason_code": "client-typo-confirmation",
                "questions": [typo],
                "question_message": _fmt([typo["question"]]),
                "summary": summary, "digest": digest, "provenance": prov,
                "auth_status": status, "approval_invalidated": False,
                "changes": [],
                "next_action": "Answer the one question about your own words; "
                               "your text stays exactly as you wrote it "
                               "either way."}
    if resume_state and isinstance(resume_state, dict) and resume_state.get("digest"):
        prior = resume_state.get("summary") or {}
        cur = {k: summary.get(k) for k in ("offer", "audience", "cta", "placement",
                                           "generation_ceiling", "target_length_s")}
        old = {k: prior.get(k) for k in cur}
        changes = sorted(k for k in cur if json.dumps(cur[k], sort_keys=True, default=str) !=
                         json.dumps(old[k], sort_keys=True, default=str))
        affecting = sorted(set(changes) & {a for a in APPROVAL_AFFECTING if a in changes} |
                           ({"offer"} if "offer" in changes else set()) |
                           ({"audience"} if "audience" in changes else set()) |
                           ({"action"} if "cta" in changes else set()) |
                           ({"budget_minor", "budget_currency"} if "generation_ceiling" in changes else set()))
        if not changes and not (resume_state.get("outstanding") or []):
            card_refusal = _card_refusal(resume_state)
            if card_refusal is not None:
                reason, next_action = card_refusal
                return {"outcome": "waiting", "reason_code": reason,
                        "questions": [], "question_message": None,
                        "summary": summary, "digest": digest, "provenance": prov,
                        "auth_status": status, "approval_invalidated": False,
                        "changes": [], "next_action": next_action}
            return {"outcome": "ok", "reason_code": "resume-no-changes", "questions": [],
                    "question_message": None, "summary": summary, "digest": digest,
                    "provenance": prov, "auth_status": status, "approval_invalidated": False,
                    "changes": [], "next_stage": resume_state.get("next_stage"),
                    "next_action": resume_state.get("next_stage") or "Proceed to preflight."}
        if affecting:
            return {"outcome": "parked", "reason_code": "resume-approval-invalidated",
                    "questions": [], "question_message": None, "summary": summary,
                    "digest": digest, "provenance": prov, "auth_status": status,
                    "approval_invalidated": True, "changes": changes,
                    "next_action": "Re-approve scope: approval-affecting change invalidated prior approval."}
        outstanding = (resume_state.get("outstanding") or [])[:3]
        if outstanding:
            return {"outcome": "waiting", "reason_code": "resume-outstanding-decisions",
                    "questions": [{"id": f"resume-{i}", "question": q} for i, q in enumerate(outstanding)],
                    "question_message": _fmt(outstanding),
                    "summary": summary, "digest": digest, "provenance": prov,
                    "auth_status": status, "approval_invalidated": False, "changes": changes,
                    "next_stage": resume_state.get("next_stage"),
                    "next_action": "Answer outstanding decisions; questionnaire is not rerun."}
        card_refusal = _card_refusal(resume_state)
        if card_refusal is not None:
            reason, next_action = card_refusal
            return {"outcome": "waiting", "reason_code": reason,
                    "questions": [], "question_message": None,
                    "summary": summary, "digest": digest, "provenance": prov,
                    "auth_status": status, "approval_invalidated": False,
                    "changes": changes, "next_action": next_action}
        return {"outcome": "ok", "reason_code": "resume-material-changes",
                "questions": [], "question_message": None, "summary": summary,
                "digest": digest, "provenance": prov, "auth_status": status,
                "approval_invalidated": False, "changes": changes,
                "next_stage": resume_state.get("next_stage"),
                "next_action": resume_state.get("next_stage") or "Proceed to preflight."}
    qs = missing_essentials(fields, prov)
    if qs:
        # The <=3 story questions are asked first; the choice card comes at
        # the approval step, not instead of them (directive 24.3 note: the
        # cap applies to the story questions only).
        return {"outcome": "waiting", "reason_code": "missing-essentials",
                "questions": qs,
                "question_message": _fmt([q["question"] for q in qs]),
                "summary": summary, "digest": digest, "provenance": prov,
                "auth_status": status, "approval_invalidated": False,
                "changes": [],
                "next_action": ("Answer the bundled questions in one reply; "
                                "nothing else is asked.")}
    # F15: a complete brief (zero questions) is not a launch -- the choice
    # card must still be shown and its four answers recorded before any
    # paid job, whichever entry path filled the brief.
    card_refusal = _card_refusal(resume_state)
    if card_refusal is not None:
        reason, next_action = card_refusal
        return {"outcome": "waiting", "reason_code": reason,
                "questions": [], "question_message": None, "summary": summary,
                "digest": digest, "provenance": prov, "auth_status": status,
                "approval_invalidated": False, "changes": [],
                "next_action": next_action}
    return {"outcome": "ok", "reason_code": "complete-brief-zero-questions",
                "questions": [], "question_message": None, "summary": summary,
                "digest": digest, "provenance": prov, "auth_status": status,
                "approval_invalidated": False, "changes": [],
                "next_action": "Record summary digest + auth scope, then run preflight before paid work."}
    return {"outcome": "waiting", "reason_code": "missing-essentials",
            "questions": qs,
            "question_message": _fmt([q["question"] for q in qs]),
            "summary": summary, "digest": digest, "provenance": prov,
            "auth_status": status, "approval_invalidated": False, "changes": [],
            "next_action": "Answer the bundled questions in one reply; nothing else is asked."}
