"""Plain-language music help, honest progress and a suggestion with a reason.

S75-T23 owns the client experience around the existing questions: one active
question, a one-line explanation of every style the catalog actually offers, a
recommendation that says WHY, and reuse of answers already given. It never
copies the catalog: labels, descriptions and display-only recognition names are
read from ``music_styles.STYLES`` (the owner of record) when help is built.

Nothing here rewrites a question, an option, a route or an approval. A
recommendation is a dict marked ``is_suggestion`` -- there is deliberately no
function that writes it into an answer; only the client's own reply does that.

``ponytail:`` shared Notion/library reuse waits on S75-T14; this offers reuse of
answers this run already holds, and says so.
"""
from __future__ import annotations

MUSIC_QUESTION_ID = "music"

#: Story signals -> (style id, the plain reason). Only the four examples the
#: specification itself names are encoded; no extra category is inferred.
_SIGNALS = (
    (("character", "argument", "argues", "debate", "scene", "play"),
     "musical-theater", "the story is carried by named characters arguing it out"),
    (("intimate", "detail", "memory", "childhood", "kitchen", "letter", "quiet"),
     "folk-storytelling", "the story lives in small, specific detail"),
    (("rise", "turnaround", "breakthrough", "comeback", "recover", "lift", "hope"),
     "soul-rise", "the story has a direct emotional rise at its turn"),
    (("rap", "punchy", "fast", "rhythm", "rhythmic", "dense", "back-and-forth"),
     "rnb-flow", "the story moves in dense, rhythmic exchange"),
)


def _catalog(catalog=None):
    """The one catalog of record: ``{style_id: record}``."""
    if catalog is not None:
        return catalog
    from music_styles import music_styles as MS
    return MS.STYLES


def style_ids(catalog=None):
    """Catalog order, never a second list."""
    if catalog is not None:
        return tuple(catalog)
    try:
        from music_styles import music_styles as MS
        return tuple(MS.style_ids())
    except (ImportError, AttributeError):
        return tuple(_catalog())


def _card_sentence(style_id):
    """The card's own client sentence, so the two surfaces cannot drift."""
    try:
        from . import intake_card as card
    except ImportError:
        return ""
    return card._MUSIC_SENTENCE.get(style_id, "")


def description(style_id, catalog=None):
    """One short client-facing sentence for a style, or ``""``.

    Precedence: the catalog's own client description (added by S75-T18), then
    the card's existing sentence, then the catalog's plain ``sound`` field.
    Provider fields (``suno_style_prompt`` etc.) are never read here.
    """
    rec = _catalog(catalog)[style_id]
    for key in ("client_description", "description"):
        value = rec.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    sentence = _card_sentence(style_id)
    if sentence:
        return sentence
    value = rec.get("sound")
    return value.strip() if isinstance(value, str) else ""


def _strings(value):
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        value = list(value.values())
    if isinstance(value, (list, tuple)):
        return [v for v in value if isinstance(v, str) and v.strip()]
    return []


def references(style_id, catalog=None):
    """Display-only recognition names for help text; never provider input."""
    rec = _catalog(catalog)[style_id]
    return _strings(rec.get("client_references"))[:2]


def _line(label, description, references):
    line = "%s - %s" % (label, description)
    if references:
        line += " Think: %s." % " / ".join(references)
    return line


def describe(style_id, catalog=None):
    """The client-facing help record for one style."""
    rec = _catalog(catalog)[style_id]
    label = rec.get("label") or style_id
    refs = references(style_id, catalog)
    plain = description(style_id, catalog)
    return {"style_id": style_id, "label": label, "description": plain,
            "references": refs, "help_line": _line(label, plain, refs)}


def help_line(style_id, catalog=None):
    """One numbered-menu-ready line: label, plain sentence, optional Think-of."""
    return describe(style_id, catalog)["help_line"]


def help_rows(catalog=None):
    """One row per offered style, in catalog order."""
    return [describe(style_id, catalog) for style_id in style_ids(catalog)]


def help_text(selected=None, catalog=None, answered=None, total=None,
              next_label=None):
    """The full plain help message, still one screen.

    ``selected`` echoes a stored choice; it is a statement, not a new
    suggestion. Progress uses real counts only, and is omitted when unknown.
    """
    lines = ["Music styles, one line each:"]
    for n, row in enumerate(help_rows(catalog), 1):
        lines.append("%d. %s" % (n, row["help_line"]))
    if selected:
        row = describe(selected, catalog)
        lines += ["", "You chose %s. That stays your choice." % row["label"]]
    lines += ["", 'Reply with a number, or say "recommended" for my suggestion.']
    progress_line = progress(answered, total, next_label)
    if progress_line:
        lines += ["", progress_line]
    lines.append("These lines are help, not a selection.")
    return "\n".join(lines)


def progress(answered, total, next_label=None):
    """True progress from actual answered/required counts; empty when unknown."""
    if not isinstance(answered, int) or not isinstance(total, int) or total <= 0:
        return ""
    line = "%d of %d answered." % (answered, total)
    if next_label:
        line += " Next: %s." % next_label
    return line


def recommend(story="", audience="", selected=None, catalog=None):
    """A suggestion with its reason, or ``None`` when the story says nothing.

    A stored ``selected`` style is echoed as the current choice with
    ``is_suggestion`` False -- a recommendation never replaces it. The result
    is never written to an answer, a route or an approval.
    """
    catalog = _catalog(catalog)
    if selected and selected in catalog:
        return {"style_id": selected, "label": catalog[selected].get("label", selected),
                "is_suggestion": False,
                "reason": "you already chose it, so this only restates your choice"}
    text = ("%s %s" % (story or "", audience or "")).casefold()
    if not text.strip():
        return None
    for words, style_id, reason in _SIGNALS:
        if style_id in catalog and any(w in text for w in words):
            return {"style_id": style_id,
                    "label": catalog[style_id].get("label", style_id),
                    "is_suggestion": True, "reason": reason,
                    "note": "A suggestion only. You still choose."}
    return None


def recommendation_line(result):
    """Plain sentence for a suggestion dict; empty for ``None``."""
    if not result:
        return ""
    if not result.get("is_suggestion"):
        return "You chose %s because %s." % (result["label"], result["reason"])
    return ("I would suggest %s because %s. %s"
            % (result["label"], result["reason"], result.get("note", ""))).strip()
