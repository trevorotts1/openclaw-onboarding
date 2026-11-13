#!/usr/bin/env python3
"""intake_card: the intake questions (the story-brief questions then the
production choices) as a card a client can read (H9).

SWI-002 count truth: the card's own total -- len(QUESTIONS) -- is the only
number any string here may repeat, and it is printed from the live list, never
written into prose. A docstring cannot read the live count, so no docstring
here states one. test_intake_card_h9.py carries the count and goes red the
moment a hardcoded total disagrees with the card.

DSR-105: the studio page used to ask only the production choices, so an
order placed on the page carried no brief at all -- no offer, no link, no
audience, no character, no photos -- while an order started in chat did. The
BRIEF questions close that gap. They are typed answers, not picks, so each
one carries a single option whose detail starts "Reply with" on the chat card;
the studio export marks the screen ``typed`` and sends no option row, so the
page asks for the words itself (S75-074). This module stays the one place their
text lives.

Trevor 2026-10-08: the questions arrived "smashed together, no spaces, nothing
on different lines". Cause: nothing built the card -- the agent wrote it free
hand, the JSON envelope carried it as one escaped string, and the only joiner
(``"\\n".join``) gave no blank line between questions. This module is the one
place the text is built, with a fixed layout:

    Question 1 of <total> - LENGTH
    How long should the ad be?
    1. 60 seconds - one sentence. (RECOMMENDED)
    2. 90 seconds - one sentence.
    <blank line>
    ...
    How to answer: reply with one number per question ...

Plain text only: no Markdown, no HTML, no parse mode, so nothing is stripped
or escaped on the way out. ``render_messages`` splits on question boundaries
under Telegram's 4096-character limit. ``telegram_payload`` and
``openclaw_send_argv`` build the exact send payloads with the text untouched
(an argv list, never a shell string, so no shell flattens the newlines).

``--format studio-json`` (U1) is the studio-shaped export: every question as a
screen carrying a plain heading, its question text, the example a typed answer
shows, and the price inputs the page turns into a true price for the length the
client picks (``studio_json``), so the Drama Studio renders the same questions
the card asks.

Stdlib only. No network: this module builds text and reads one local guide.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile

_CORE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)
import budget_contingency as BC      # the one planning-allowance policy

#: Telegram's hard limit is 4096 characters per message; stay under it.
TELEGRAM_LIMIT = 4000

#: A typed (brief) answer is capped at the studio service's own per-reply
#: limit, so an answer the card accepts is an answer the order can store.
MAX_TYPED_ANSWER_CHARS = 2000

_CLOSING_FMT = ('How to answer: reply with one number per question, in order, '
                'like "{ex}". Say "all recommended" to take every RECOMMENDED choice.')

_SHORT_CLOSING_FMT = ('How to answer: reply with one number per question, in order, '
                      'like "{ex}". For the BUDGET, reply with a dollar amount.')

REC = "(RECOMMENDED)"

#: The line a typed (brief) question ends with. The studio reads the same
#: sentence off that question's single option detail, so the card and the page
#: always agree about which answers are typed rather than picked.
FREE_TEXT_HINT = "Reply with your own words."


def _closing(qs):
    """'all recommended' is offered only when every question has a recommended option."""
    choices = [q for q in qs if not q.get("free_text")]
    shortcut = (' Say "all recommended" to take every RECOMMENDED choice.'
                if all(q.get("recommended") is not None for q in choices) else "")
    typed = [q["label"].title() for q in qs
             if q.get("free_text") and not q.get("defaulted")]
    if typed:
        return ("How to answer: type your own words for %s, one number for the "
                "choice questions, and a dollar amount for the BUDGET.%s"
                % (", ".join(typed), shortcut))
    fmt = _CLOSING_FMT if shortcut else _SHORT_CLOSING_FMT
    return fmt.format(ex=", ".join(["1"] * len(qs)))

#: (label, question, [(option, one short sentence)], recommended option index)
#: Looks and music come from the choice-card modules so the menu cannot drift.
#: Short plain sentences (the library descriptions are build notes, not client text).
_LOOK_SENTENCE = {
    "lifelike-3d": "polished animated movie look with lifelike faces.",
    "2d-hand-painted": "a warm, hand-painted cartoon from start to finish.",
    "sketch-to-life": "black-and-white pencil sketch that turns into real footage.",
    "canvas-to-life": "painted cartoon that turns into real footage.",
    "canvas-to-3d": "painted cartoon that turns into lifelike 3D.",
}
#: Shown under a look whose source registry has no verified sample (Canvas to Life).
#: Never substitute another look's link; the choice stays usable and explained.
SAMPLE_MISSING = "Sample not available yet."
#: Client-facing names. "Hybrid" is the official name of the sketch-and-real-footage
#: look (its bible and id are still `hybrid`); the card label stays Sketch to Life.
_LOOK_NAME = {"sketch-to-life": "Sketch to Life (Hybrid)"}
_MUSIC_SENTENCE = {
    "soul-ballad": "slow, heartfelt singing; builds to a big emotional chorus.",
    "rnb-flow": "rhythmic rap verses, then a smooth sung hook you remember.",
    "soul-rise": "starts slow and sad, then lifts into an upbeat, hopeful groove.",
    # The card's own short line (4-12 words) for the five styles whose owner
    # catalog description is longer than the card allows. The catalog text is
    # unchanged and still feeds help; every other style shows it as-is.
    "trap-rap": "punchy rap over deep bass and rolling hi-hats.",
    "cinematic-orchestral-song": "sweeping strings and a powerful, film-style chorus.",
    "contemporary-gospel": "faith-centered singing with piano, organ, and a powerful choir.",
    "urban-gospel": "faith-centered singing with R&B and hip-hop grooves, plus choir.",
    "country-rap": "country storytelling meets rock power and hip-hop rhythm.",
}


def _sample_links():
    """look id -> https sample-video link (style_samples.json); None = no verified sample."""
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "style_samples.json"), encoding="utf-8") as f:
        return json.load(f)


def _menu(ids, labels, sentences):
    return [(labels[i], sentences[i]) for i in ids]


def _looks():
    from choice_card.looks import looks as L
    labels = {i: _LOOK_NAME.get(i, L.LOOK_LABELS[i]) for i in L.LOOK_ORDER}
    return _menu(L.LOOK_ORDER, labels, _LOOK_SENTENCE)


def _look_links():
    """Sample link per look option (1-based); an option with no verified sample is absent."""
    from choice_card.looks import looks as L
    links = _sample_links()
    return {n: links[i] for n, i in enumerate(L.LOOK_ORDER, 1) if links.get(i)}


def _musics():
    """The eighteen canonical styles, from the catalog owner of record."""
    from music_styles import catalog as CAT
    return [(row["label"], _MUSIC_SENTENCE.get(row["style_id"], row["description"]))
            for row in CAT.choice_rows()]


def _usd(x):
    return "$%.2f" % float(str(x).lstrip("$"))


def spend_question(price=None, limit=None, from_brief=False):
    """The ONE money question, asked here and nowhere else (FU-ONE-SPEND-QUESTION).
    price: the card's total in dollars (planning allowance included). limit: a
    maximum already known. from_brief: that maximum came from the brief (not a --limit
    override). Neither is ever defaulted: the client must reply."""
    opts, vals = [], {}
    if limit is not None:
        opts.append(("Your max: " + _usd(limit), "from your brief" if from_brief else None))
        vals[len(opts)] = str(limit).lstrip("$")
    if price is not None:
        opts.append((_usd(price), "the estimated price for your video, including a "
                     "%s allowance for redoing shots" % BC.label()))
        vals[len(opts)] = str(price).lstrip("$")
    opts.append(("A different maximum", "reply with a dollar amount, like $25"))
    return {"id": "spend", "why": "This keeps you in control of the cost.",
            "reason": ("it is the maximum you already gave in your brief." if limit is not None and from_brief else
                       "it is the maximum you set." if limit is not None else
                       "it covers the whole price, with room to redo shots." if price is not None else
                       "you choose the number."),
            "label": "BUDGET",
            "ask": ("What's the most you want to spend on this video?" if opts[:-1] else
                    "What's the most you want to spend on this video? Reply with a dollar amount, like $25."),
            # no price and no limit: nothing to recommend, the client types an amount
            "options": opts, "values": vals, "recommended": 0 if opts[:-1] else None,
            #: the price line the studio BUDGET screen shows (U1 studio-json export);
            #: None when no price and no limit is known yet.
            "price": (_usd(price) if price is not None else
                      "up to " + _usd(limit) if limit is not None else None)}


def _plain_label(mid):
    """A model's name for a client: the catalog label without its route in
    brackets (S75-006: no vendor name in a question)."""
    from choice_card.intake_card import ai_models as AM
    text = AM.label(mid)
    for vendor in VENDOR_JARGON:
        text = text.replace(" (%s)" % vendor, "").replace(" %s" % vendor, "")
    return text.strip()


def _ai_setup_q():
    """The AI setup question, asked ONCE on a computer with no saved pair
    (S75-006). A saved pair moves it to the recap as a changeable line, so the
    client is never asked what this computer is already set up to do."""
    from choice_card.intake_card import ai_models as AM
    rec = AM.recommended()
    return {"id": "models", "label": "AI MODELS",
            "why": "One AI does the writing and planning, and a different one checks the work.",
            "reason": "it is already set up and tested here.",
            "ask": "Which AI setup should work on your video?",
            "options": [("Use the setup on this computer",
                         "%s builds, %s checks." % (_plain_label(rec["build"]),
                                                    _plain_label(rec["check"]))),
                        ("Choose different ones",
                         "Tell me which one builds and which one checks.")],
            "recommended": 0}


def _duration_options(episode=False):
    """The owner's six durations, in the canonical registry's order.

    Retained card labels and descriptions are unchanged. The restored 120 s
    row uses the registry's existing "2 minutes" label; no new story claim is
    invented for it. A purpose never removes a chosen canonical duration.
    """
    from music_styles import music_styles as MS
    rows = {
        60: ("60 seconds", "The standard ad length."),
        90: ("90 seconds", "Room for a fuller story."),
        120: ("2 minutes", None),
        180: ("3 minutes + 60s and 90s clips", "Plus a 60-second clip and a 90-second clip."),
        300: ("5 minutes + 60s and 90s clips", "Plus a 60-second clip and a 90-second clip."),
        600: ("10 minutes (the long version) + 60s and 90s clips", "Plus a 60-second clip and a 90-second clip."),
    }
    if episode:
        rows.update({
            180: ("3 minutes", "one full story with room for the turn and the offer."),
            300: ("5 minutes", "a deeper story with more of the solution at work."),
            600: ("10 minutes", "the long version, a full show episode."),
        })
    return [rows[seconds] for seconds in MS.CANONICAL_DURATION_S]


def _length_prices(options):
    """option number -> "- about $X" for every length choice (S75-006 step 5).

    One function, the same price table the VIDEO MODEL line reads, priced for
    the model that screen recommends. A length the table cannot price simply
    carries no price; the choice is never removed for it."""
    from catalog_calculator import card_render as CR
    models = _vm().require_choices()
    chosen = next((m["n"] for m in models if m.get("recommended")), models[0]["n"])
    out = {}
    for n, (label, _sentence) in enumerate(options, 1):
        try:
            out[n] = "- about %s" % ("$%.2f" % CR.quote(chosen, label))
        except (KeyError, ValueError, TypeError):
            continue
    return out


def _length_question(options=None, recommended=None):
    """LENGTH: the owner's six durations, each ending with its price (S75-006)."""
    from music_styles import music_styles as MS
    options = _duration_options() if options is None else options
    return {"id": "length", "why": "Length decides the story size and the price.",
            "reason": "the standard length for ads, and it fits stories, reels and ads.",
            "label": "LENGTH",
            "ask": "How long do you want your ad to be? The longer ads also come with "
                   "short clips you can post on social media.",
            "options": options, "prices": _length_prices(options),
            "recommended": 0 if recommended is None else recommended}


def _music_q():
    """MUSIC STYLE: the three original styles, then the full list on request.

    ``full_options`` carries all eighteen; the expansion is its own question
    (``music_full``) so the screen the client is looking at never changes out
    from under an answer already recorded."""
    styles = _musics()
    return {"id": "music", "why": "The song carries the feeling of the whole ad.",
            "reason": "it is the style that tests best for emotional stories.",
            "label": "MUSIC STYLE", "ask": "Which sound fits your story?",
            "options": styles[:3] + [("Show me all %d styles" % len(styles), None)],
            "full_options": styles, "recommended": 0}


def _music_full_q():
    """The eighteen-style menu, asked as its own screen when the client says
    "more" (option 4). Same id family as MUSIC STYLE; its answer is folded back
    into the music line when the run records its answers."""
    return {"id": "music_full", "why": "Every style the studio can make.",
            "reason": "it is the style that tests best for emotional stories.",
            "label": "MUSIC STYLE (ALL)", "ask": "Which sound fits your story?",
            "options": _music_q()["full_options"], "recommended": 0}


def _checkpoints_q():
    """CHECKPOINTS: one screen in place of the three approval screens
    (S75-006 step 1). Option 1 turns every gate on, option 2 only the
    storyboard, option 3 none, option 4 asks each approval on its own."""
    return {"id": "checkpoints", "label": "CHECKPOINTS",
            "why": "Fixing a script or a song is cheap; fixing a finished video is not.",
            "reason": "fixing a script or a song is cheap, and fixing a finished video is not.",
            "ask": "How much do you want to see before video money is spent?",
            "body": [
                "How much do you want to see before video money is spent?",
                "1. Everything - the script, 3 song versions to pick from, and the storyboard. (RECOMMENDED)",
                "2. Just the storyboard.",
                "3. Nothing - just make it.",
                "",
                "I recommend option 1 because fixing a script or a song is cheap, "
                "and fixing a finished video is not.",
                'Reply with a number, or say "recommended". You can also say '
                '"custom" to choose each one.',
            ],
            "options": [("Everything", "the script, 3 song versions to pick from, and the storyboard."),
                        ("Just the storyboard", "the storyboard, and nothing else."),
                        ("Nothing - just make it", "Work starts as soon as you lock in your order."),
                        ("Choose each one", "answer the script, song and storyboard questions one by one.")],
            "recommended": 0}


#: CHECKPOINTS option -> (storyboard, song, script) approval, 1 = shown first.
_CHECKPOINT_GATES = {1: (1, 1, 1), 2: (1, 2, 2), 3: (2, 2, 2)}


def _gate_questions():
    """The approval screens, asked only by CHECKPOINTS option 4."""
    return [
        {"id": "storyboard",
         "why": "The storyboard is cheap to fix now and costly to fix after video is made.",
         "reason": "you see every scene before any money is spent on video.",
         "label": "STORYBOARD APPROVAL",
         "ask": "Do you want to approve the storyboard before any video is made?",
         "options": [("Yes, show me first", "Nothing is generated until you say go."),
                     ("No, just make it", "Work starts as soon as you lock in your order.")],
         "recommended": 0},
        {"id": "song",
         "why": "The song is the heart of the ad, and it is cheap to change now and costly after video is made.",
         "reason": "you hear three labelled versions and pick your favourite before any money is spent on video.",
         "label": "SONG APPROVAL",
         "ask": "Do you want to hear and pick the song before any video is made?",
         "options": [("Yes, send me 3 versions to choose from",
                      "Three labelled songs; nothing else starts until you pick, and two extra songs are added to the price."),
                     ("No, just make it", "I make one song and keep going.")],
         "recommended": 0},
        {"id": "script",
         "why": "The script is cheap to fix now and costly to fix after the song is made.",
         "reason": "you read the story and the lyrics before any money is spent on the song.",
         "label": "SCRIPT APPROVAL",
         "ask": "Do you want to read and approve the script - your story and the song lyrics - before the song is made?",
         "options": [("Yes, show me first", "Nothing is generated until you say go."),
                     ("No, just make it", "Work starts as soon as you lock in your order.")],
         "recommended": 0},
    ]


def _legacy_questions():
    """The card a run that already started keeps, exactly as it was asked.

    Frozen on purpose: a resumed run's answers belong to HIS list, and changing
    this list would migrate the answers he already gave (S75-006 step 5)."""
    return [
        _ai_setup_q(),
        _length_question(),
        {"id": "music", "why": "The song carries the feeling of the whole ad.", "reason": "it is the style that tests best for emotional stories.", "label": "MUSIC STYLE", "ask": "Which sound fits your story?",
         "options": _musics(), "recommended": 0},
        {"id": "look", "why": "The look is what viewers see in every shot.", "reason": "it gives the most real, cinematic result.", "label": "VIDEO STYLE", "ask": "How should your video look? Tap a link to watch a sample.",
         "options": _looks(), "links": _look_links(), "recommended": 0},
        _model_question("60 seconds"),
        spend_question(),
    ] + _gate_questions()


def _new_questions():
    """The card a NEW run asks (S75-006): only what the client can answer.

    The last three carry ``defaulted``: they are shown as numbered lines on the
    recap with their default and are never asked one by one.
    """
    return [_offer_q(), _link_q(), _audience_q(), _character_q(), _ai_setup_q(),
            _length_question(), _music_q(),
            {"id": "look", "why": "The look is what viewers see in every shot.", "reason": "it gives the most real, cinematic result.", "label": "VIDEO STYLE", "ask": "How should your video look? Tap a link to watch a sample.",
             "options": _looks(), "links": _look_links(), "recommended": 0},
            _checkpoints_q(), spend_question(),
            _model_question("60 seconds", defaulted=True), _shape_q(), _photos_q()]


def _model_price_line(length_label):
    """The one price sentence the VIDEO MODEL screen shows, from the length the
    client chose. The card's ask and the studio-json export both read it here,
    so the two price surfaces cannot drift apart."""
    from choice_card.video_models import video_models as VM
    return ("Prices are for your %s ad, with the song, pictures and a %s "
            "redo allowance." % (VM.length_phrase(VM.length_seconds(length_label)),
                                 BC.label()))


def _vm():
    """The video-model table, imported the way this module imports everything it
    does not need to build the card's text (see _model_question)."""
    from choice_card.video_models import video_models as VM
    return VM


def _model_question(length_label, agnes_yes=False, defaulted=False):
    """VIDEO MODEL: the models the live KIE catalog proves it carries, each
    priced for the client's chosen length. A client who said yes to Agnes
    reads it as the backup it now is (SPEC A10): same models, same prices,
    one question of when they are used.

    ``defaulted`` (S75-006): the screen is shown on the recap with its default
    -- the recommended row -- and asked only when the client asks to change it.

    L3 (v2.9.73): the choices come from the price table filtered through the
    LIVE registry (refs/kie-model-registry.json, the file dispatch reads).
    A list that cannot be resolved -- the registry is unreadable, or a row's
    model is not in the catalog (the live defect: a card row the KIE catalog
    did not carry) -- refuses with the reason and never renders a model the
    catalog does not have."""
    from choice_card.video_models import video_models as VM
    from catalog_calculator import card_render as CR
    models = VM.require_choices()               # raises ModelResolutionError fail-closed
    cost = {m["n"]: "$%.2f" % CR.quote(m["n"], length_label) for m in models}
    ask = ("Which video model should make your shots if Agnes cannot? " if agnes_yes
           else "Which video model should make your shots? ")
    q = {"id": "model", "why": "The video model sets how good the shots look and what they cost.",
         "reason": "it gives the best balance of quality and price.", "label": "VIDEO MODEL",
         "ask": ask + _model_price_line(length_label),
         "price": _model_price_line(length_label),
         "options": [(m["name"], "%s - about %s" % (m["blurb"], cost[m["n"]])) for m in models],
         "values": [cost[m["n"]] for m in models],
         "recommended": next(i for i, m in enumerate(models) if m["recommended"])}
    if defaulted:
        q["defaulted"] = True
        q["optional"] = True
    return q


def _priced(qs, answers):
    """Swap in the VIDEO MODEL question priced for the length already answered."""
    ids = [q["id"] for q in qs]
    if "length" not in ids or len(answers) <= ids.index("length"):
        return qs
    length_text = answers[ids.index("length")]["text"]       # AI MODELS (and the saved character) may come first
    return [_model_question(length_text) if q["id"] == "model" else q for q in qs]


# --- W1-card-questions-U1: the PURPOSE flow and the AGNES question (SPEC B1) ----
#: The plain choices the client sees first (PURPOSE itself offers four options),
#: and the method purpose each one names in control/method.json. Choice 4
#: becomes two purposes once the WHERE
#: answer is in: a paid ad and a free post are made to different platform rules
#: (SPEC B2), so the record carries two names, not one.
_PURPOSE = {1: "campaign", 2: "testimonial", 3: "lesson", 4: "social"}

#: WHERE option number -> the platform row the run is checked against (SPEC B1).
_PLATFORM = {1: "meta", 2: "tiktok", 3: "linkedin", 4: "organic"}

#: What each use produces (method 8.1, SPEC B2). A campaign's two trailers and
#: two ad clips are the 60-second and the 90-second of each.
_OUTPUT_TYPES = {
    "campaign": ["MASTER_EPISODE", "TRAILER_CLIP", "TRAILER_CLIP", "AD_CLIP", "AD_CLIP"],
    "testimonial": ["MASTER_EPISODE"],
    "lesson": ["MASTER_EPISODE"],
    "paid_ad": ["STANDALONE_SALES_EDIT"],
    "short_post": ["STANDALONE_SALES_EDIT"],
}

#: Trevor 2026-10-13: Agnes is capped at five minutes, so the AGNES question is
#: asked only when the chosen length can be made with it (SPEC A15).
_AGNES_MAX_LENGTH_S = 300

#: The SHAPE question belongs to the uses whose video is not pinned to one
#: frame. A paid ad and a free post are both made 9:16, so they never see it.
_SHAPE_PURPOSES = (1, 2, 3)

#: The ids the purpose flow rebuilds around. Every one of them is stripped from
#: the base list before the rebuild, so shaping twice over the same answers
#: gives the same list -- positional replay stays deterministic (SPEC B1).
_CONDITIONAL_IDS = ("purpose", "episode_length", "shape", "permission", "where", "agnes")

#: Method jargon that must never reach a client-facing question. Matched as
#: WHOLE words, case-insensitive ("terms" is not "ERM"), so ordinary prose is
#: never flagged. The card asks what the video is for and who it is for; the
#: method's own vocabulary stays in the method documents.
METHOD_JARGON = ("MOS", "ERM", "ERM drop", "beat sheet", "screenwriting",
                 "inciting incident", "story arc", "master scene", "turning point")

#: Vendor and build-tool names that mean nothing to a client (S75-006). Checked
#: everywhere METHOD_JARGON is, except the option details of the VIDEO MODEL and
#: AGNES questions -- there the client is choosing between those very products.
VENDOR_JARGON = ("OpenRouter", "Ollama", "KIE", "Suno", "Skill 74", "sqlite")


def jargon_hits(text, terms=None):
    """The jargon terms in ``text``, whole-word and case-insensitive.

    ``terms`` defaults to every blocked tuple; a caller that checks one family
    passes it (the tests check method words and vendor names separately).
    """
    import re
    hits = []
    for term in (METHOD_JARGON + VENDOR_JARGON) if terms is None else terms:
        if re.search(r"(?<![A-Za-z])" + re.escape(term) + r"(?![A-Za-z])",
                     text or "", re.IGNORECASE):
            hits.append(term)
    return hits


#: Run-folder files a card writes once it has already been asked. Any one of
#: them means the run is RESUMED: its answers belong to the list it was asked
#: with, so the card is replayed exactly and nothing is migrated or rewritten.
_RESUME_MARKERS = ("card-answers.json",
                   os.path.join("control", "card-receipt.json"),
                   os.path.join("control", "state.sqlite3"))

#: The durable session file a --format session-json run writes (intake_session).
#: It records the flow it started with, so a resume keeps that flow exactly.
_SESSION_FILE = os.path.join("control", "intake-session.json")

#: The records only a purpose-flow card writes, plus the studio order whose
#: screens ARE the purpose flow. A run carrying one is replayed THROUGH the
#: purpose flow, never back through the old list: a replay is not a migration.
_FLOW_MARKERS = (os.path.join("control", "method.json"),
                 os.path.join("control", "studio-order.json"))


def _run_history(run_dir):
    """Which card this run already used: True (the purpose flow), False (the old
    list) or None when the folder shows neither -- a NEW run.

    Strictly read-only: a resumed project is never migrated or rewritten, and a
    new one has nothing yet to read.
    """
    if not run_dir or not os.path.isdir(run_dir):
        return None
    if any(os.path.exists(os.path.join(run_dir, p)) for p in _FLOW_MARKERS):
        return True
    #: S75-006 step 5: the durable session records the flow it started with, so
    #: a run that asked the new card keeps asking it (and a resumed old run
    #: keeps the old one) -- the presence of the file alone is not the answer.
    try:
        with open(os.path.join(run_dir, _SESSION_FILE), encoding="utf-8") as fh:
            sess = json.load(fh)
    except (OSError, ValueError):
        sess = None
    if isinstance(sess, dict) and "purpose_flow" in sess:
        return bool(sess["purpose_flow"])
    if any(os.path.exists(os.path.join(run_dir, p)) for p in _RESUME_MARKERS):
        return False
    return None


def _intro_shown(run_state_file):
    """Read-only: has this chat run already seen the intro (so it is a resume)?"""
    if not run_state_file:
        return False
    try:
        with open(run_state_file, encoding="utf-8") as fh:
            state = json.load(fh)
    except (OSError, ValueError):
        return False
    return bool(isinstance(state, dict) and state.get("intro_shown"))


def new_run_flow(run_dir=None, run_state_file=None):
    """The opening-coaching default for the launcher.

    A run that recorded which card it used keeps that card (``_run_history``).
    A run folder with nothing recorded yet is a NEW Drama-to-Demand run: it
    opens on the purpose flow, unless the chat run is already past its intro
    (a resume stays on the card it started with). No run folder at all is a
    question preview, not a run, and is left exactly as it was.
    """
    history = _run_history(run_dir)
    if history is not None:
        return history
    if not run_dir or not os.path.isdir(run_dir):
        return False
    return not _intro_shown(run_state_file)


def _loud(kind, code, detail):
    """Named, visible failure/warning that reaches the receipt (loud_failure.py)."""
    import os as _os, sys as _sys
    d = _os.path.dirname(_os.path.abspath(__file__))
    while d != _os.path.dirname(d) and not _os.path.exists(_os.path.join(d, "loud_failure.py")):
        d = _os.path.dirname(d)
    if d not in _sys.path:
        _sys.path.insert(0, d)
    import loud_failure
    getattr(loud_failure, kind)(code, detail)


def _purpose_q():
    """Question 1 (METHOD-INTEGRATION 3.1): what the video is for."""
    return {"id": "purpose", "label": "PURPOSE",
            "why": "What the video is for decides its shape, its length and where it goes.",
            "reason": "one production gives you the full package: your YouTube episode, "
                      "two trailers for it, and two ready-to-run ad clips for Facebook, "
                      "YouTube and TikTok.",
            "ask": "What is this video for?",
            "options": [
                ("Grow my business", "the full package: a full episode for your YouTube "
                 "channel, plus 60-second and 90-second trailers that send people to the "
                 "full episode, and 60-second and 90-second ad clips that sell your product "
                 "or service on Facebook, YouTube and TikTok."),
                ("Tell a client's success story", "turn a real client's own words into a "
                 "short drama."),
                ("Teach a lesson", "turn one point from your course or webinar into a song "
                 "people remember."),
                ("A video for social media", "a paid ad or a free post, made to fit the app "
                 "you pick."),
            ],
            "recap": ["Purpose: full campaign (episode + 2 trailers)",
                      "Purpose: client success story",
                      "Purpose: teaching song",
                      "Purpose: social media video"],
            "recommended": 0}


def _episode_length_q():
    """The campaign's one follow-up (METHOD-INTEGRATION 3.2). It takes LENGTH's
    own slot, so a campaign grows by the PURPOSE question and nothing else."""
    from music_styles import music_styles as MS
    options = _duration_options(episode=True)
    return {"id": "episode_length", "label": "EPISODE LENGTH",
            "why": "The full episode lives on your YouTube channel; the trailers bring "
                   "people to it.",
            "reason": "it is the shortest episode that still earns two good trailers.",
            "ask": "How long should the full episode be? Your 60-second and 90-second "
                   "trailers and ad clips are included.",
            "options": options, "prices": _length_prices(options),
            "recommended": MS.CANONICAL_DURATION_S.index(180)}


def _shape_q():
    """How every shot is framed (SPEC B1, purposes 1-3).

    S75-006: shown on the recap with its default -- Wide for a campaign episode,
    Vertical for everything else -- and asked only when the client changes it."""
    return {"id": "shape", "label": "SHAPE",
            "why": "The shape decides how every shot is framed.",
            "reason": "it fits phones, Reels, Shorts and TikTok.",
            "ask": "How should your video be framed?",
            "options": [("Vertical", "phones, Reels, Shorts, TikTok."),
                        ("Wide", "YouTube on a TV or a computer.")],
            "recommended": 0, "defaulted": True, "optional": True,
            #: the default option for a purpose (1-based); a campaign episode is wide
            "default_by_purpose": {1: 2, 2: 1, 3: 1}}


def _permission_q():
    """The testimonial's one follow-up (METHOD-INTEGRATION 3.2): one yes/no
    question, nothing more. Nothing is recommended here on purpose -- "all
    recommended" can never answer it, and a No stops the order."""
    return {"id": "permission", "label": "PERMISSION",
            # METHOD-INTEGRATION 3.2 prints this block with no why line: the
            # question is only ever the yes/no itself, so render_step skips it.
            "ask": "Do you have your client's permission to use their testimonial?",
            "options": [("Yes", None),
                        ("No - pause this order until I have it.", None)],
            "recommended": None, "closing": "Reply 1 or 2."}


def _where_q():
    """The social video's one follow-up (METHOD-INTEGRATION 3.2)."""
    return {"id": "where", "label": "WHERE",
            "why": "Each app has its own length and shape rules, so the video is made to "
                   "fit the one you pick.",
            "reason": "one vertical video fits Reels, Stories and the feed there.",
            "ask": "Where will this video run?",
            "options": [("Facebook or Instagram - paid ad.", None),
                        ("TikTok - paid ad.", None),
                        ("LinkedIn - paid ad.", None),
                        ("A free post - Reels, Stories or YouTube Shorts.", None)],
            "recommended": 0}


def _agnes_q(remembered):
    """The AGNES question (METHOD-INTEGRATION 3.3), asked after VIDEO STYLE.
    ``remembered`` is "yes" or "unknown"; a remembered "no" hides it, so it is
    never asked here."""
    return {"id": "agnes", "label": "AGNES",
            "why": "If you pay for an Agnes AI plan, your pictures and video clips can be "
                   "made with it at no extra cost.",
            "ask": "Do you have a paid Agnes subscription (Starter, Plus or Pro), and "
                   "should it make this video's pictures and clips?",
            "recap": ["Agnes: used", "Agnes: not used"],
            "options": [
                ("Yes - use my Agnes plan.", "Agnes video is 720p, a little softer than the "
                 "studio's standard models, and the song and the talking close-ups still "
                 "use the studio's providers."),
                ("No - use the studio's standard models.", None),
            ],
            # S75-020: mark a pick only for a client who said yes before; with
            # nothing recommended the closing says how many choices there are.
            "recommended": 0 if remembered == "yes" else None,
            "rec_mark": "(RECOMMENDED when you said yes before)",
            "closing": ("Reply with a number." if remembered == "yes"
                        else "Reply 1 or 2.")}


def _length_q(key):
    """Every purpose retains the owner's six canonical duration choices."""
    return next(q for q in QUESTIONS if q["id"] == "length")


def _answered(answers, ids, qid):
    """The option number the client picked for ``qid``, or None. Answers are
    positional, so the question must be in the list they were given against."""
    if qid not in ids:
        return None
    at = ids.index(qid)
    a = answers[at] if len(answers) > at else None
    return (a or {}).get("n") or None


def _purpose_key(purpose_n, where_n):
    """The method purpose this card is for; choice 4 splits on the WHERE answer."""
    if purpose_n != 4:
        return _PURPOSE.get(purpose_n)
    return "short_post" if where_n == 4 else "paid_ad"


def _length_text(answers, ids, key):
    """The length the client chose, as the card asked it."""
    qid = "episode_length" if key == "campaign" else "length"
    n = _answered(answers, ids, qid)
    if n is None:
        return None
    q = _episode_length_q() if key == "campaign" else _length_q(key)
    return q["options"][n - 1][0] if 0 < n <= len(q["options"]) else None


def _agnes_remembered(client_dir):
    """The client's remembered Agnes answer: "yes", "no" or "unknown".

    ``agnes_access`` is another unit of this same program, so an ImportError is
    "unknown" -- the question is asked rather than quietly hidden -- and it is a
    WARNING, never a crash: a card must still be readable."""
    if not client_dir:
        return "unknown"
    try:
        from agnes_access import agnes_access as AG
    except ImportError:
        _loud("warn", "AGNES_ACCESS_UNAVAILABLE",
              "agnes_access could not be imported; the Agnes question is asked as unknown.")
        return "unknown"
    try:
        return AG.remembered(client_dir) or "unknown"
    except OSError as e:
        _loud("warn", "AGNES_REMEMBERED_UNREADABLE", str(e))
        return "unknown"


def _remember_agnes(client_dir, answers, qs):
    """Write this card's Agnes answer to the client's own data folder (SPEC A2)."""
    n = _answered(answers, [q["id"] for q in qs], "agnes")
    if n is None:
        return
    try:
        from agnes_access import agnes_access as AG
    except ImportError:
        _loud("warn", "AGNES_ACCESS_UNAVAILABLE",
              "agnes_access could not be imported; the Agnes answer was not remembered.")
        return
    AG.remember(client_dir, "yes" if n == 1 else "no")


def _remember_ai_setup(client_dir, answers, qs):
    """Save this computer's AI setup once the client has chosen it (S75-006).

    The saved pair is what later runs reuse instead of asking again; it is
    never a per-machine answer the Studio export reads."""
    a = next((x for x in answers if x.get("id") == "models"), None)
    if not isinstance((a or {}).get("value"), dict):
        return
    try:
        from choice_card.intake_card import ai_models as AM
    except ImportError:
        _loud("warn", "AI_SETUP_UNAVAILABLE",
              "ai_models could not be imported; the AI setup was not saved.")
        return
    try:
        AM.remember_setup(client_dir, a["value"])
    except (OSError, ValueError) as e:
        _loud("warn", "AI_SETUP_NOT_SAVED", str(e))


def _runtime_targets(length_s):
    """The one length function's numbers for the chosen length (SPEC B1). The
    method's own runtime row is used when the length function carries it; every
    other run plans against the delivered length it already returns."""
    try:
        import length_formula as LF
    except ImportError:
        _loud("warn", "LENGTH_FORMULA_UNAVAILABLE",
              "length_formula could not be imported; runtime_targets is empty.")
        return {}
    try:
        plan = LF.plan(length_s, method=True)
    except TypeError:                      # before the method row exists
        plan = LF.plan(length_s)
    return plan.get("method") or {"chosen_length_s": plan["chosen_length_s"],
                                  "delivered_s": plan["delivered_s"]}


def _method_record(answers, qs):
    """control/method.json (SPEC B1): what this run is for, where it runs, what
    it produces, the length it plans against and the gates the factory fills in.
    None when no PURPOSE was answered, so a card asked the old way writes
    nothing."""
    ids = [q["id"] for q in qs]
    purpose_n = _answered(answers, ids, "purpose")
    if purpose_n is None:
        return None
    where = _answered(answers, ids, "where")
    key = _purpose_key(purpose_n, where)
    length_text = _length_text(answers, ids, key)
    length_s = _vm().length_seconds(length_text) if length_text else None
    permission = _answered(answers, ids, "permission")
    return {"purpose": key,
            "platform": _PLATFORM.get(where) if purpose_n == 4 else None,
            "output_types": _OUTPUT_TYPES[key],
            "chosen_length_s": length_s,
            "runtime_targets": _runtime_targets(length_s) if length_s else {},
            #: the PERMISSION answer, "yes" or "no"; null when it was never asked
            "testimonial_permission": (None if permission is None
                                       else "yes" if permission == 1 else "no"),
            #: the factory records the measured result on each gate (SPEC C6)
            "gates": {g: "planned" for g in "ABCDEF"}}


def _write_json(path, obj):
    """One atomic write, the shape every control record here already uses."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True)
    os.replace(tmp, path)


def _read_json(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f) or {}
    except (OSError, ValueError):
        return {}


def _record_agnes_receipt(run_dir, answers, qs):
    """The ``agnes`` block in control/card-receipt.json: merged into whatever is
    already there, never clobbering another stage's keys."""
    n = _answered(answers, [q["id"] for q in qs], "agnes")
    if n is None:
        return
    path = os.path.join(run_dir, "control", "card-receipt.json")
    rec = _read_json(path)
    rec["agnes"] = {"answer": "yes" if n == 1 else "no"}
    _write_json(path, rec)


def _pick(pos, answers, qid):
    """The option number picked for an already-placed question. The client's
    replies are positional, so a question's answer is the one at its own index
    in the list it was asked in -- which is why _shaped places a question before
    it reads anything that depends on the answer to it."""
    at = pos.get(qid)
    a = answers[at] if at is not None and len(answers) > at else None
    return (a or {}).get("n") or None


def _ai_setup_remembered(client_dir):
    """The AI setup saved for this computer, or None (S75-006).

    ``ai_models`` is read lazily, like the Agnes answer: a missing module is a
    WARNING, never a crash, and the question is asked rather than hidden."""
    if not client_dir:
        return None
    try:
        from choice_card.intake_card import ai_models as AM
    except ImportError:
        _loud("warn", "AI_SETUP_UNAVAILABLE",
              "ai_models could not be imported; the AI setup question is asked.")
        return None
    try:
        return AM.remembered_setup(client_dir)
    except OSError as e:
        _loud("warn", "AI_SETUP_UNREADABLE", str(e))
        return None


def _default_row(q, purpose_n=None, client_dir=None):
    """The default a recap line shows for a defaulted screen: {"n", "text", ...}."""
    if q["id"] == "model":
        n = (q.get("recommended") or 0) + 1
        return {"n": n, "text": q["options"][n - 1][0], "id": q["id"]}
    if q["id"] == "shape":
        n = (q.get("default_by_purpose") or {}).get(purpose_n, 1)
        return {"n": n, "text": q["options"][n - 1][0], "id": q["id"]}
    if q["id"] == "photos":
        return {"n": 1, "text": q.get("default_text", "none yet - send them any time"),
                "id": q["id"]}
    if q["id"] == "models":
        saved = _ai_setup_remembered(client_dir)
        if saved:
            return {"n": 1, "value": dict(saved), "id": q["id"],
                    "text": "%s builds, %s checks" % (_plain_label(saved["build"]),
                                                      _plain_label(saved["check"]))}
        return {"n": 1, "text": q["options"][0][0], "id": q["id"]}
    return {"n": 1, "text": q.get("default_text", ""), "id": q["id"]}


def _defaults(qs, answers, client_dir=None, given=None):
    """{question id: {"n", "text", "value"?}} for every defaulted screen.

    A client's own change (``given``) always wins over the default."""
    out = dict(given or {})
    purpose_n = next((a.get("n") for a in answers if a.get("id") == "purpose"), None)
    for q in qs:
        if q.get("defaulted") and q["id"] not in out:
            out[q["id"]] = _default_row(q, purpose_n, client_dir)
    return out


def _record_lists(answers, qs, client_dir=None, defaults=None):
    """(questions, answers) the run records when the recap is confirmed.

    The two lists stay aligned pair for pair. Screens nobody was asked one by
    one carry their default, or the client's change. CHECKPOINTS becomes the
    three approval answers the run has always kept (S75-006 step 1), the full
    music menu folds back into the MUSIC STYLE line, and a saved AI setup is
    recorded as the pair it is.
    """
    d = _defaults(qs, answers, client_dir, defaults)
    asked_qs = [q for q in qs if not q.get("defaulted")]
    by_id = {}
    for q, a in zip(asked_qs, answers):
        by_id[q["id"]] = dict(a)
    if "music_full" in by_id:                 # the expanded list answers MUSIC STYLE
        by_id["music"] = dict(by_id.pop("music_full"), id="music")
    rec_qs = [q for q in asked_qs if q["id"] != "music_full"]
    rec_ans = [by_id[q["id"]] for q in rec_qs]
    for q in qs:
        if q.get("defaulted"):
            rec_qs.append(q)
            rec_ans.append(dict(d.get(q["id"]) or {"n": 1, "text": ""}, id=q["id"]))
    if "checkpoints" in by_id and "storyboard" not in by_id:
        mapping = _CHECKPOINT_GATES.get(by_id["checkpoints"].get("n"), _CHECKPOINT_GATES[1])
        for gate, option_n in zip(_gate_questions(), mapping):
            if gate["id"] in by_id:
                continue                      # "custom": already asked and answered
            rec_qs.append(gate)
            rec_ans.append({"n": option_n, "text": gate["options"][option_n - 1][0],
                            "value": None, "id": gate["id"]})
    if "link" not in by_id:
        #: the merged OFFER screen answered the address too (S75-006 step 2).
        #: Question and answer are appended together, so every pair above keeps
        #: its own position.
        addr = (by_id.get("offer") or {}).get("address")
        if addr:
            rec_qs.append(_link_q())
            rec_ans.append({"n": 1, "text": addr, "value": addr, "id": "link"})
    return rec_qs, rec_ans


def _shaped(qs, answers, client_dir=None):
    """The question list rebuilt from the answers so far -- the ``_priced`` idea
    applied to the whole list (SPEC B1), and since S75-006 the list a NEW run
    asks: only the questions the client can answer.

    PURPOSE is first; its one follow-up sits right after it, except EPISODE
    LENGTH, which takes LENGTH's own slot so a campaign adds no screen; AI
    MODELS and the rest keep the order they already had; AGNES sits after VIDEO
    STYLE unless the client already said no, and only while the chosen length is
    one Agnes can make. The screen that is not asked one by one -- the video
    model, the shape, the photos and a saved AI setup -- rides at the END,
    marked ``defaulted``, so the recap can number it and the client can change
    it. The conditional ids are stripped before the rebuild, so shaping twice
    on the same answers gives the same list.
    """
    base = [q for q in qs if q["id"] not in _CONDITIONAL_IDS and not q.get("defaulted")]
    tail = [q for q in qs if q.get("defaulted")]
    out, pos = [], {}

    def place(q):
        pos[q["id"]] = len(out)
        out.append(q)

    place(_purpose_q())
    purpose_n = _pick(pos, answers, "purpose")
    if purpose_n is None:                       # nothing chosen yet
        return out + base + tail
    length_text, agnes_yes = None, False
    if purpose_n in (2, 4):                     # the one follow-up, right after PURPOSE
        place(_permission_q() if purpose_n == 2 else _where_q())
    key = _purpose_key(purpose_n, _pick(pos, answers, "where"))
    for q in base:
        qid = q["id"]
        if qid == "link":
            #: S75-006 step 2: the OFFER screen carries the address too, so the
            #: address is asked on its own only when that reply had none.
            prev = next((a for a in answers if a.get("id") == "offer"), None)
            if prev is not None and not prev.get("address"):
                place(q)
            continue
        if qid == "models":
            if _ai_setup_remembered(client_dir) is None:
                place(q)
            continue
        if qid == "length":
            #: EPISODE LENGTH for a campaign is the LENGTH question in its own
            #: slot (METHOD-INTEGRATION 3.2: it replaces LENGTH), so a campaign
            #: grows by PURPOSE and no other screen.
            lq = _episode_length_q() if key == "campaign" else _length_q(key)
            ask_id = "episode_length" if key == "campaign" else "length"
            place(lq)
            n = _pick(pos, answers, ask_id) or 0      # not answered yet: no length
            length_text = lq["options"][n - 1][0] if 0 < n <= len(lq["options"]) else None
            continue
        if qid == "music":
            place(q)
            if _pick(pos, answers, "music") == len(q["options"]):
                place(_music_full_q())     # "Show me all N styles": its own screen
            continue
        place(q)
        if qid == "look":
            remembered = (_agnes_remembered(client_dir) if length_text
                          and _vm().length_seconds(length_text) <= _AGNES_MAX_LENGTH_S
                          else None)         # episodes over five minutes are KIE-only
            if remembered and remembered != "no":
                place(_agnes_q(remembered))
            agnes_yes = _pick(pos, answers, "agnes") == 1
        if qid == "checkpoints" and _pick(pos, answers, "checkpoints") == 4:
            for gate in _gate_questions():     # "custom": ask the three in place
                place(gate)
    for q in tail:
        if q["id"] == "model":
            place(_model_question(length_text or "60 seconds", agnes_yes=agnes_yes,
                                  defaulted=True))
        elif q["id"] == "shape":
            if purpose_n in _SHAPE_PURPOSES:
                place(q)
        elif q["id"] == "models":
            if _ai_setup_remembered(client_dir) is not None:
                place(q)
        else:
            place(q)
    return out


def _wait_reason(answers, qs):
    """A testimonial without permission never starts production (SPEC B2): the
    card answers waiting and writes nothing that could charge the client."""
    ids = [q["id"] for q in qs]
    if _purpose_key(_answered(answers, ids, "purpose"),
                    _answered(answers, ids, "where")) != "testimonial":
        return None
    return None if _answered(answers, ids, "permission") == 1 \
        else "testimonial-permission-pending"


# --- DSR-105: the story brief --------------------------------------------------
#: The questions the chat intake asks and the studio page never did
#: (operator trace section 1: "It sends no offer, no link, no audience, no
#: character and no photos"). They open the card, in the Client Guide's own
#: order (STEP 4, 5, 6), so a run started on the page carries the same brief a
#: run started in chat carries. BRIEF_IDS below is the count; nothing here
#: writes it out a second time.
BRIEF_IDS = ("offer", "link", "audience", "character", "photos")
#: Without these four the crew has no brief to write from. `photos` is asked
#: and stored but never required: plenty of ads are made from what the client
#: already has, and a client with nothing to send must still be able to lock in.
BRIEF_REQUIRED = ("offer", "link", "audience", "character")


def _typed(id_, label, why, ask):
    """One typed brief question. The single option is what the studio renders
    and what the card's parser keys off; its detail opens "Reply with" so the
    page knows to show a text box instead of a menu."""
    return {"id": id_, "label": label, "why": why, "ask": ask, "free_text": True,
            "options": [("Type it in", FREE_TEXT_HINT)]}


def _offer_q():
    """OFFER and the web address in ONE typed question (S75-006 step 2).

    A reply that carries a web address answers the address too (``_parse``
    splits it out); a reply without one asks only for the address next."""
    q = _typed("offer", "OFFER",
               "The story, the song and the call to action are all built around this.",
               "What are we promoting, and where should the video send people? "
               "Give the exact name, then paste the web address.")
    q["merge_link"] = True
    return q


def _link_q():
    """The web address on its own, asked only when the OFFER reply had none."""
    q = _typed("link", "OFFER LINK", None,
               "Thanks. What web address should the video send people to?")
    q["why"] = None
    return q


def _audience_q():
    return _typed("audience", "AUDIENCE",
                  "One audience and one action beat ten of each.",
                  "Who is this video for, and what should they do after watching it?")


def _character_q():
    return _typed("character", "CHARACTER",
                  "Your characters are the actors, and viewers spend the whole video with them.",
                  "Who stars in your video? Give a name, an age, and how they look and "
                  "dress. You can send photos in your next message, or skip that.")


def _photos_q():
    """PHOTOS as a recap line (S75-006): nothing to send is a real answer, so it
    is never a question the client has to get past to start."""
    q = _typed("photos", "PHOTOS",
               "A real photo makes the story feel true instead of invented.",
               "Which photos or proof should we use - your logo, a product shot, a testimonial?")
    q["defaulted"] = True
    q["optional"] = True
    q["default_text"] = "none yet - send them any time"
    return q


QUESTIONS = _new_questions()
#: The card a resumed run keeps, exactly as it was asked (S75-006 step 5).
LEGACY_QUESTIONS = _legacy_questions()


def example_replies(questions=None):
    """One plausible reply per question, in order: the typed answer for a brief
    question, a dollar amount for BUDGET, the recommended pick for a choice.
    Fixtures and tests use it so a complete card needs no hand-counting.

    The default is the card a plain replay asks -- ``conversation(replies)``
    with no run folder replays the one a resumed run keeps -- because that is
    what a fixture feeding ``conversation`` needs. Pass ``QUESTIONS`` for the
    new card."""
    out = []
    for q in (LEGACY_QUESTIONS if questions is None else questions):
        if q["id"] == "spend":
            out.append("$25")
        elif q.get("free_text"):
            out.append("Sweet Details Cookie-Decorating Class")
        else:
            out.append("recommended")
    return out
CLOSING_LINE = _closing(QUESTIONS)     # whatever the whole card actually closes with
SHORT_CLOSING_LINE = _SHORT_CLOSING_FMT.format(ex=", ".join(["1"] * len(QUESTIONS)))


#: Shown once, before the first question, when the client has no saved characters.
NO_SAVED_LINE = ("You don't have any saved characters yet, so I'll create a new one "
                 "for this ad and save it for next time.")


def song_required(answers):
    """True when the client answered Yes to SONG APPROVAL (3 versions, then a pick)."""
    return any(a.get("id") == "song" and a.get("n") == 1 for a in answers)


def _option_lines(q):
    """Numbered option lines; an option with a sample link gets an indented line under it.

    A look with no verified sample says so plainly instead of borrowing a link.
    A priced option (LENGTH) ends with its price, ``- about $X`` (S75-006)."""
    out = []
    prices = q.get("prices") or {}
    for n, (opt, sentence) in enumerate(q["options"], 1):
        mark = (" " + q.get("rec_mark", REC)) if n - 1 == q.get("recommended") else ""
        price = (" " + prices[n]) if n in prices else ""
        out.append("%d. %s%s%s%s" % (n, opt, " - " + sentence if sentence else "", price, mark))
        if n in q.get("links", {}):
            out.append("   Watch: " + q["links"][n])
        elif q["id"] == "look":
            out.append("   " + SAMPLE_MISSING)
    return out


def _typed_block(i, total, q, why=False):
    """A brief question's block: the ask, then the one line that says the
    answer is typed. There is no menu to number, so there is no menu to mark,
    and no blank line inside the block -- the blank line is what separates one
    question from the next."""
    lines = ["Question %d of %d - %s" % (i, total, q["label"])]
    if why and q.get("why"):     # the address follow-up asks its one sentence only
        lines += [q["why"], ""]
    lines += [q["ask"], FREE_TEXT_HINT]
    return "\n".join(lines)


def _block(i, total, q):
    if q.get("free_text"):                 # brief question: a typed answer
        return _typed_block(i, total, q)
    if "body" in q:                       # saved-character question: fixed text
        return "\n".join(["Question %d of %d - %s" % (i, total, q["label"])] + q["body"])
    lines = ["Question %d of %d - %s" % (i, total, q["label"]), q["ask"]]
    lines += _option_lines(q)
    if q["id"] == "agnes":
        from choice_card.intake_card.agnes_explanation import lines as explanation_lines
        lines += [""] + explanation_lines()
    return "\n".join(lines)


def _blocks(questions):
    blocks = [_block(i, len(questions), q) for i, q in enumerate(questions, 1)]
    if questions and questions[0].get("preface"):
        blocks[0] = questions[0]["preface"] + "\n\n" + blocks[0]
    return blocks


def render_step(i, questions=None):
    """ONE question as its own message (Trevor 2026-10-08, I7): a one-sentence
    why, numbered options one per line, the RECOMMENDED one marked and
    explained, then how to answer."""
    qs = questions or QUESTIONS
    q = qs[i - 1]
    if q.get("free_text"):
        return _typed_block(i, len(qs), q, why=True)
    if "body" in q:
        return _block(i, len(qs), q)
    lines = ["Question %d of %d - %s" % (i, len(qs), q["label"])]
    if q.get("why"):        # PERMISSION carries none: it is the yes/no, nothing else
        lines += [q["why"], ""]
    lines.append(q["ask"])
    lines += _option_lines(q)
    if q["id"] == "agnes":
        from choice_card.intake_card.agnes_explanation import lines as explanation_lines
        lines += [""] + explanation_lines()
    r = q.get("recommended", 0)
    if r is None:
        # nothing to recommend: the BUDGET asks for an amount, a yes/no
        # question (PERMISSION) only asks which one.
        lines += ["", q.get("closing", "Reply with a dollar amount, like $25.")]
        return "\n".join(lines)
    lines.append("")
    if q.get("reason"):                     # a question may only mark its pick
        lines.append("I recommend option %d (%s) because %s" % (r + 1, q["options"][r][0], q["reason"]))
    if q.get("id") == "music":
        # S75-T23: the plain help for every offered style is one word away; the
        # question, its options and its recommendation are unchanged.
        lines.append('Say "help me choose" to hear what each style sounds like.')
    lines.append(q.get("closing") or "Reply with a number, or say \"recommended\".")
    return "\n".join(lines)


#: S75-030: the recap's own heading for a screen whose card label is jargon or
#: shouts; every other screen reads its label with a plain first capital.
_RECAP_LABEL = {"models": "AI setup", "model": "Video model",
                "link": "Web address", "spend": "Budget"}


def render_recap(answers, questions=None, defaults=None, client_dir=None):
    """The recap: one numbered line per answer, then one per defaulted screen.

    S75-006: a screen the client never had to answer is marked "(default -
    reply <n> to change)"; replying its number asks the full question."""
    qs = list(questions or QUESTIONS)
    if not any(q.get("defaulted") for q in qs):
        qs = _priced(qs, answers)          # the older card, priced in place
    d = _defaults(qs, answers, client_dir, defaults)
    lines = ["Here is what you picked:"]
    for i, q in enumerate(qs, 1):
        if q.get("defaulted"):
            row = d.get(q["id"]) or {}
            lines.append("%d. %s: %s (default - reply %d to change)"
                         % (i, _RECAP_LABEL.get(q["id"]) or q["label"].capitalize(),
                            row.get("text", ""), i))
            continue
        if i > len(answers):
            break
        a = answers[i - 1]
        if "recap" in q and a.get("n"):
            lines.append("%d. %s" % (i, q["recap"][a["n"] - 1]))
            continue
        price = (" - about " + q["values"][a["n"] - 1]) if q["id"] == "model" and a.get("n") else ""
        lines.append("%d. %s: %s%s" % (i, _RECAP_LABEL.get(q["id"]) or q["label"].capitalize(),
                                       a["text"], price))
    lines += ["", 'Reply "yes" to start, or the number of a line to change it.']
    return "\n".join(lines)


_YES = ("yes", "y", "yep", "go", "ok", "okay", "start", "approve", "approved")

#: S75-020: a bare yes answers only these choice questions, and then only when
#: their first option is itself a yes (CHECKPOINTS names its own top option).
_YES_CHOICE_IDS = ("storyboard", "song", "script", "permission", "agnes",
                   "checkpoints")

#: The words that mean "take the recommended option". A typed brief question
#: refuses them too, so they can never be stored as an answer.
_PICK_WORDS = ("recommended", "recommend", "rec")


def _address_in(text):
    """The first token of ``text`` that parses as a web address, or None.

    Scheme optional, a dot in the host required (S75-006 step 2). A price like
    "1.5" is not an address: the last label must be letters."""
    from urllib.parse import urlsplit
    import re as _re
    for token in _re.split(r"[\s,;]+", text or ""):
        word = token.strip("()[]<>\"'")
        if not word or "." not in word or not any(c.isalpha() for c in word):
            continue
        try:
            parts = urlsplit(word if "://" in word else "//" + word)
        except ValueError:
            continue
        host = parts.hostname or ""
        last = host.rsplit(".", 1)[-1]
        if "." in host and last.isalpha() and len(last) >= 2 and all(host.split(".")):
            return word
    return None


def _parse_offer(reply, q):
    """The merged OFFER question: the text, plus the address when there is one."""
    import re as _re
    raw = (reply or "").strip()
    low = raw.lower()
    if len(raw) < 2 or low in _YES or low in _PICK_WORDS or len(raw) > MAX_TYPED_ANSWER_CHARS:
        return None
    address = _address_in(raw)
    if not address:
        return {"n": 1, "text": raw, "value": raw, "id": "offer"}
    offer = _re.sub(r"\s+", " ", raw.replace(address, " ")).strip(" ,;.-")
    if len(offer) < 2:                     # the client sent only the address
        offer = address
    return {"n": 1, "text": offer, "value": offer, "id": "offer", "address": address}


def _parse(reply, q):
    """Reply -> {"n": option number, "text": ..., "value": ...} or None."""
    t = (reply or "").strip().lower()
    opts = q["options"]
    if q["id"] == "models":
        from choice_card.intake_card import ai_models as AM
        c, err = AM.parse(reply)
        if not c:
            return {"error": err}
        return {"n": 1 if c == AM.recommended() else 2, "value": c,
                "text": _plain_label(c["build"]) + " builds, " + _plain_label(c["check"]) + " checks"}
    if q.get("merge_link"):                # OFFER and the address in one reply
        return _parse_offer(reply, q)
    if q.get("free_text"):                 # a brief question: the answer IS the text
        raw = (reply or "").strip()
        # A mistyped "1", a stray "yes" or a stray "recommended" must never be
        # stored as somebody's offer, so none of the pick words is an answer.
        if len(raw) < 2 or t in _YES or t in _PICK_WORDS or len(raw) > MAX_TYPED_ANSWER_CHARS:
            return None
        return {"n": 1, "text": raw, "value": raw, "id": q["id"]}
    if q["id"] == "checkpoints" and t in ("custom", "choose each one", "each one"):
        return {"n": 4, "text": opts[3][0], "value": None, "id": q["id"]}
    if t in _YES:
        # S75-020: a yes word picks the recommended option on an approval
        # question whose first option is a yes; on every other choice question
        # it is not an answer, so the question is asked again.
        if (q["id"] not in _YES_CHOICE_IDS or q.get("recommended") is None
                or not (q["id"] == "checkpoints" or opts[0][0].startswith("Yes"))):
            return None
        n = q["recommended"] + 1
    elif t in _PICK_WORDS:
        if q.get("recommended") is None:
            return None
        n = q.get("recommended", 0) + 1
    elif t.isdigit() and 1 <= int(t) <= len(opts):
        n = int(t)
    elif q["id"] == "spend" and t.lstrip("$").replace(".", "", 1).isdigit():
        return {"n": len(opts), "text": "up to " + _usd(t), "value": t.lstrip("$"), "id": q["id"]}
    else:
        return None
    _v = q.get("values")
    value = _v.get(n) if isinstance(_v, dict) else None
    if q["id"] == "spend" and value is None:      # "A different maximum" with no amount, or a
        return None                               # bare "yes": no amount = no spend
    return {"n": n, "text": "up to " + _usd(value) if q["id"] == "spend" else opts[n - 1][0], "value": value, "id": q["id"]}


def conversation(replies, questions=None, state_store=None, run_id=None,
                 run_dir=None, target=None, client_dir=None, purpose_flow=None,
                 run_state_file=None):
    """Replay the client's replies from the start; return the state and the ONE
    message to send next. Stateless, so claude-nine and OpenClaw can both call
    it with the replies so far. state: answers, done, message, video_model.
    With state_store + run_id, the client's video model is written to run state
    (the F14 lock) as soon as it is answered; the card and dispatch read it there.
    With run_dir, the recap confirmation writes the STORYBOARD and SONG APPROVAL
    answers to the run (approval_runner / song_choices record_card_answer), so Yes
    turns the pick gates on; target (the client's chat id) is stored with them.

    purpose_flow (SPEC B1) is what turns the purpose card on: the question list
    is rebuilt from the answers so far (``_shaped``) instead of priced in place,
    a confirmed recap writes control/method.json and the receipt's agnes block,
    and the client's Agnes answer is remembered in their own data folder.
    client_dir is the folder those remembered answers live in.

    S75X-W1-U1: the default is now ``None`` = decide from the run. A NEW run
    folder opens on the purpose flow (the client answers what the video is for
    first, one plain question per message, reusing the brief and any saved
    character instead of asking again). A run that already asked a card is
    replayed with the SAME list it used -- purpose flow when it recorded
    control/method.json or a studio order, the old list otherwise -- so a
    resumed project and its approved artifacts are preserved exactly and are
    never migrated or rewritten. ``run_state_file`` is the same run state the
    launcher reads: a chat run already past its intro is a resume and keeps the
    card it started with. The decision itself lives in ``new_run_flow`` so the
    API and the launcher can never disagree. True/False still force either list.
    """
    if purpose_flow is None:
        purpose_flow = new_run_flow(run_dir, run_state_file)
    #: The list every rebuild starts from. Shaping a SHAPED list again would
    #: lose LENGTH's own slot on a campaign (EPISODE LENGTH took it), so the
    #: rebuild always reads the base list. A run that already asked a card keeps
    #: the one it was asked with (LEGACY_QUESTIONS), never the new one.
    base_qs = questions or (QUESTIONS if purpose_flow else LEGACY_QUESTIONS)
    answers, defaults, fix, note, done = [], {}, None, "", False

    def shaped(list_, ans):
        return _shaped(list_, ans, client_dir) if purpose_flow else _priced(list_, ans)

    def ask_at(list_, ans):
        """The index of the next question to ask, or None at the recap."""
        at = len(ans)
        if at < len(list_) and not list_[at].get("defaulted"):
            return at
        return None

    for r in replies:
        note = ""
        qs = shaped(base_qs, answers)
        at = ask_at(qs, answers)
        if fix is not None:                         # re-answering one line
            q = qs[fix]
            a = _parse(r, q)
            if a and "error" in a:
                note = a["error"] + " "
            elif a:
                if q.get("defaulted"):
                    defaults[q["id"]] = a           # a recap line, never asked inline
                else:
                    before = [x["id"] for x in qs]
                    if q["id"] == "purpose":
                        # the whole list was built around the old purpose, so every
                        # answer after it has to be given again (SPEC B1)
                        del answers[fix + 1:]
                        defaults.clear()
                    answers[fix] = a
                    after = [x["id"] for x in shaped(base_qs, answers)]
                    if after[fix:] != before[fix:]:
                        # S75-021: the later questions moved, so the answers given
                        # for them no longer belong to them; ask those again.
                        del answers[fix + 1:]
                        note = ("That changes a few of the later choices, so I'll "
                                "ask those again. ")
                fix = None
            else:
                note = "Sorry, I did not catch that. "
        elif at is not None:
            a = _parse(r, qs[at])
            if a and "error" in a:
                note = a["error"] + " "
            elif a:
                answers.append(a)
            else:
                note = "Sorry, I did not catch that. "
        else:                                       # recap: yes, or a line number
            t = r.strip().lower()
            if t in _YES:
                done = True
            elif t.isdigit() and 1 <= int(t) <= len(qs):
                k = int(t) - 1
                if k < len(answers) or qs[k].get("defaulted"):
                    fix = k
                else:
                    note = "Sorry, I did not catch that. "
            else:
                note = "Sorry, I did not catch that. "
    qs = shaped(base_qs, answers)
    full = _defaults(qs, answers, client_dir, defaults)
    model_n = (next((a["n"] for a in answers if a.get("id") == "model"), None)
               or (full.get("model") or {}).get("n"))
    if model_n and state_store and run_id:
        from choice_card.video_models import video_models as VM
        VM.lock_choice(state_store, run_id, model_n)
    if done:
        blocked = _wait_reason(answers, qs) if purpose_flow else None
        if blocked:     # SPEC B2: nothing is generated or charged
            return {"answers": answers, "done": False, "waiting": True,
                    #: the factory's own waiting shape (intake_preflight.EXIT)
                    "outcome": "waiting", "reason_code": blocked,
                    "reason": blocked, "video_model": model_n,
                    "message": ("Paused, and your answers are saved. I will not "
                                "generate anything or charge you until you have "
                                "your client's permission. Tell me when you have "
                                "it and I will pick this straight back up.")}
        #: the shapes the run has always recorded: every asked answer, the three
        #: approvals CHECKPOINTS stands for, and every defaulted screen (S75-006)
        rec_qs, rec_ans = _record_lists(answers, qs, client_dir, defaults)
        if run_dir:
            from storyboard_director import approval_runner as _ar
            _ar.record_card_answer(run_dir, rec_ans, rec_qs, target)
            from song_choices import song_choices as _sc   # noqa: PLC0415
            _sc.record_card_answer(run_dir, rec_ans, target)
            from script_approval import card_answers       # noqa: PLC0415
            card_answers.write(run_dir, rec_ans, rec_qs)
            if purpose_flow:
                record = _method_record(answers, qs)
                if record:
                    _write_json(os.path.join(run_dir, "control", "method.json"), record)
                _record_agnes_receipt(run_dir, answers, qs)
        if purpose_flow and client_dir:
            _remember_agnes(client_dir, answers, qs)
            _remember_ai_setup(client_dir, answers, qs)
        msg = "Locked in. I am starting now."
    elif fix is not None:
        msg = note + render_step(fix + 1, qs)
    elif ask_at(qs, answers) is not None:
        i = ask_at(qs, answers)
        msg = note + render_step(i + 1, qs)
        if not replies and qs[0].get("preface"):
            msg = qs[0]["preface"] + "\n\n" + msg
    else:
        msg = note + render_recap(answers, qs, defaults, client_dir)
    return {"answers": answers, "done": done, "message": msg, "video_model": model_n}


def render_card(questions=None, book_plan=None, notes=()):
    """The whole card as one string: blank line between questions, closing line.

    FU-U11: a book card also carries the Book shots APPROVAL BLOCK. It shows
    approvals and notices only -- it adds no question and no option, so the
    card's answer shape (one number per question, then yes) is unchanged.
    """
    qs = questions or QUESTIONS
    blocks = _blocks(qs) + [_closing(qs)]
    book = _book_block(book_plan, notes)
    if book:
        blocks = blocks + book
    return "\n\n".join(blocks)


def _book_block(book_plan, notes=()):
    """FU-U11: the Book shots approval block, or [] for a non-book card."""
    if not book_plan:
        return []
    _core = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    if _core not in sys.path:
        sys.path.insert(0, _core)
    try:
        from book_shot import book_shot as BS
    except ImportError:
        return ["Book shots: the book plan is present but the book module "
                "could not be loaded, so its rows cannot be shown."]
    return ["\n".join(BS.plan_card_block(book_plan, notes))]


def format_questions(texts):
    """Plain question strings -> a message.

    ONE question is ONE message (Trevor 2026-10-21): a single text is sent as
    its own message, unnumbered, so the client answers it before the next
    question is asked. Several texts keep the numbered, blank-line separated
    layout for callers that legitimately send a whole batch.

    Used by intake / intake_book for their ``question_message``.
    """
    texts = [t for t in texts if t]
    if not texts:
        return None
    if len(texts) == 1:
        return texts[0] + "\n\nReply with your answer."
    blocks = ["Question %d of %d\n%s" % (i, len(texts), t)
              for i, t in enumerate(texts, 1)]
    return "\n\n".join(blocks + ["Reply with one answer per question, in order."])


def _split_long(block, limit):
    """A block over the limit splits on line boundaries, never mid-line.

    A question that does not fit one message (the eighteen-style MUSIC STYLE
    menu) continues in the next message under its own header plus
    "(continued)", so no message opens with option lines and no context.
    """
    lines = block.split("\n")
    cont = lines[0] + " (continued)" if lines[0].startswith("Question ") else None
    out, cur = [], []
    for line in lines:
        if cur and len("\n".join(cur + [line])) > limit:
            out.append("\n".join(cur))
            cur = ([cont] if cont else []) + [line]
        else:
            cur.append(line)
    return out + (["\n".join(cur)] if cur else [])


def render_messages(questions=None, limit=TELEGRAM_LIMIT, book_plan=None,
                    notes=()):
    """The card as a list of messages, each <= limit chars, split only between
    questions (one message per question when they do not all fit).

    FU-U11: a book card's approval block rides as its own message(s), after
    the closing line; it is never split mid-row unless a single row exceeds
    the limit.
    """
    parts = []
    for b in _blocks(questions or QUESTIONS) + [_closing(questions or QUESTIONS)] + \
            _book_block(book_plan, notes):
        parts.extend(_split_long(b, limit) if len(b) > limit else [b])
    msgs, cur = [], ""
    for p in parts:
        cand = cur + "\n\n" + p if cur else p
        if len(cand) > limit and cur:
            msgs.append(cur)
            cur = p
        else:
            cur = cand
    return msgs + ([cur] if cur else [])


def telegram_payload(chat_id, text):
    """Exact JSON body for the Bot API ``sendMessage``. No ``parse_mode`` on
    purpose: with none, Telegram shows the text verbatim, newlines included."""
    return {"chat_id": chat_id, "text": text}


def _staged_media(media):
    """Media paths the channel will actually accept.

    OpenClaw only sends files inside its own state roots (media, workspace,
    delivery-queue-media, canvas, sandboxes) or tmp; a run-folder attachment
    is refused with LocalMediaAccessError. Anything else is COPIED into
    <state>/delivery-queue-media first -- the copy is what gets sent, the
    original is never moved or rewritten.
    """
    root = os.path.join(os.path.expanduser("~"), ".openclaw")
    allowed = tuple(os.path.join(root, d) for d in
                    ("media", "workspace", "delivery-queue-media", "canvas",
                     "sandboxes")) + (tempfile.gettempdir(),)
    staged = []
    for m in media or ():
        path = os.path.abspath(str(m))
        if path.startswith(allowed) and os.path.isfile(path):
            staged.append(path)
            continue
        dest_dir = os.path.join(root, "delivery-queue-media")
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, os.path.basename(path))
        if not os.path.isfile(path):
            staged.append(path)      # let the sender name the real error
            continue
        if not (os.path.isfile(dest)
                and os.path.getsize(dest) == os.path.getsize(path)):
            shutil.copy2(path, dest)
        staged.append(dest)
    return staged

def channel_send_argv(channel, target, text, media=(), account=None, thread_id=None):
    """THE command builder (W03-U1, finding D06): one ``openclaw message send``
    argv for the RESOLVED channel. ``channel`` arrives as data -- from the run's
    origin record (``delivery_outbox.resolve_origin``) or an explicit caller --
    and this builder never picks one. Telegram resolves the correct
    authenticated bot/account, chat and thread through ``--account`` /
    ``--target`` / ``--thread-id``; an OpenClaw-app conversation is addressed by
    its own conversation id. A list, not a shell string: run it with subprocess
    (shell=False) and the newlines in ``text`` reach the sender untouched. The
    argv is the STABLE identity of one piece (message text last); the transport
    executor adds ``--json`` when it runs the command, so the channel's receipt
    (a message id) can be recorded -- that receipt is what allows a delivery to
    be claimed sent."""
    channel = (channel or "").strip()
    if not channel:
        raise ValueError("channel_send_argv needs the RESOLVED channel; "
                         "refusing to guess a default channel")
    return (["openclaw", "message", "send", "--channel", channel,
             "--target", str(target), "--message", text]
            + [x for m in _staged_media(media) for x in ("--media", str(m))]
            + (["--account", str(account)] if account else [])
            + (["--thread-id", str(thread_id)] if thread_id else []))


def openclaw_send_argv(target, text, media=(), channel=None, account=None,
                       thread_id=None, run_dir=None):
    """Backward-compatible entry for legacy callers that pass a bare chat id.

    Resolution order: an explicit ``channel``; else the run's canonical origin
    record (``run_dir``); else the DEPRECATED legacy contract -- a caller that
    hands in a bare chat id addressed Telegram explicitly (the storyboard
    approval runner and the song-choice sender document exactly that). New code
    must route through ``channel_send.send`` / ``channel_send_argv`` with a
    resolved channel so no path hardcodes Telegram."""
    if channel is None and run_dir:
        from choice_card.intake_card import delivery_outbox as _DO   # noqa: PLC0415
        rec = _DO.resolve_origin(run_dir)
        channel = (rec or {}).get("channel") or None
        account = account or (rec or {}).get("account_id") or None
        thread_id = thread_id or (rec or {}).get("thread_id") or None
    if channel is None:
        channel = "telegram"     # deprecated legacy default (caller-explicit)
    return channel_send_argv(channel, target, text, media=media,
                             account=account, thread_id=thread_id)


# --- FU-U4: the fit STOP card (registry-only options, plan 2.3) ----------------

FEWER_WORDS_ID = "fewer_words"


def _client_words(packet_lines):
    """[(line_id, word_count)] for the client's own lines, in order."""
    import protected_names as PN
    out = []
    for n, ln in enumerate(packet_lines or [], 1):
        lid = (ln.get("id") or ln.get("line_id")) if isinstance(ln, dict) else None
        text = ln.get("text", "") if isinstance(ln, dict) else str(ln)
        out.append((lid or "line %d" % n, len(PN._tokens(text))))
    return out


def _fit_row(style_id, length_s, words):
    """One style's numbers for the client's words at length_s. Rap styles may
    carry the words as spoken (intro/outro) plus rap; the others only as spoken
    in [Intro]/[Outro] (suno recipe rule 1)."""
    import length_formula as LF
    import words_fit as WF
    from music_styles import music_styles as MS
    plan = LF.plan(length_s, style_id=style_id)
    cap_spoken = plan["words"]["spoken"]
    cap_rap = plan["words"].get("rap", 0)
    rap_style = "rap" in MS.style(style_id)["deliveries"]
    spoken = min(words, cap_spoken) if rap_style else words
    rap = words - spoken if rap_style else 0
    planned_s = WF.planned_seconds(0, spoken, rap, rates=WF.rates_for(style_id))
    cap = cap_spoken + cap_rap
    return {"style_id": style_id, "label": MS.style(style_id)["label"],
            "length_s": length_s, "client_words": words, "capacity_words": cap,
            "split": {"sung": 0, "spoken": spoken, "rap": rap},
            "planned_s": round(planned_s, 1),
            "fits": words <= cap and planned_s <= length_s}


def assert_registry_options(card):
    """Refuse any card option whose id is not in the registries: lengths in
    music_styles.OFFERED_LENGTHS_S, styles in music_styles.style_ids(), voices
    in voice_velvet_echo, and the one words_fit fewer_words option."""
    import words_fit as WF
    from music_styles import music_styles as MS
    from voice_velvet_echo import velvet_voiceover as VV
    opts = card.get("options") or {}
    ok = {"longer_ad": set(MS.OFFERED_LENGTHS_S), "music_style": set(MS.style_ids()),
          "voice": {VV.ALL_SUNO_ID, VV.VELVET_ID}}
    for kind, allowed in ok.items():
        for o in opts.get(kind, []):
            if o.get("id") not in allowed:
                raise ValueError("FIT_CARD_OPTION_NOT_IN_REGISTRY %s option %r; allowed %s"
                                 % (kind, o.get("id"), sorted(allowed, key=str)))
    fw = opts.get(FEWER_WORDS_ID)
    if fw is not None and fw.get("id") not in WF.preflight(60, 0, 9999)["options"]:
        raise ValueError("FIT_CARD_OPTION_NOT_IN_REGISTRY fewer_words id %r" % (fw.get("id"),))
    return card


def fit_card(brief, packet_lines):
    """The STOP card for a client who brought their own lines: for each real
    music style, the numbers at the client's length; options only from the
    registries; notices for what the skill will not make. Free: no spend.
    outcome "ok" when the chosen style (brief.music, default Soul Ballad) fits,
    else "waiting" (exit 2). Nothing is cut: fewer_words names exact line ids
    for the client to approve."""
    from intake_preflight import intake as INT
    from music_styles import music_styles as MS
    from voice_velvet_echo import velvet_voiceover as VV
    import words_fit as WF
    brief = brief or {}
    packet_lines = brief.get("packet_lines") if packet_lines is None else packet_lines
    fields, _ = INT.normalize(brief)
    length_s = fields["target_length_s"]
    per_line = _client_words(packet_lines)
    words = sum(n for _, n in per_line)
    rows = [_fit_row(sid, length_s, words) for sid in MS.style_ids()]
    chosen = MS._style_key(fields["music"])
    crow = next(r for r in rows if r["style_id"] == chosen)
    longer = []
    for L in MS.OFFERED_LENGTHS_S:
        if L > length_s:
            fits = [r["style_id"] for r in (_fit_row(sid, L, words) for sid in MS.style_ids())
                    if r["fits"]]
            longer.append({"id": L, "fits_styles": fits})
    kept, cut = 0, []
    for lid, n in per_line:                       # keep from the top; the tail is named
        if kept + n <= crow["capacity_words"]:
            kept += n
        else:
            cut.append(lid)
    card = {
        "outcome": "ok" if crow["fits"] else "waiting",
        "reason_code": "FIT_OK" if crow["fits"] else "CLIENT_LINES_DO_NOT_FIT",
        "length_s": length_s, "chosen_style": chosen, "client_words": words,
        "rows": rows,
        "options": {
            "longer_ad": longer,
            "music_style": [{"id": r["style_id"], "fits": r["fits"]} for r in rows],
            "voice": [{"id": VV.ALL_SUNO_ID, "default": True}, {"id": VV.VELVET_ID}],
            FEWER_WORDS_ID: {"id": FEWER_WORDS_ID, "cut_line_ids": cut,
                             "cut_words": words - kept, "needs_client_approval": True},
        },
        "notices": INT.notices(brief, packet_lines),
    }
    assert_registry_options(card)
    card["text"] = _render_fit(card)
    return card


def _render_fit(card):
    from music_styles import music_styles as MS
    L = card["length_s"]
    out = ["Your lines are %d words. Here is how each music style handles them at %d seconds:"
           % (card["client_words"], L)]
    for r in card["rows"]:
        out.append("- %s: room for %d words at the planned share, all your words need %.1f seconds (%d spoken, %d rap) - %s"
                   % (r["label"], r["capacity_words"], r["planned_s"], r["split"]["spoken"],
                      r["split"]["rap"], "fits" if r["fits"] else "does not fit"))
    if card["outcome"] == "ok":
        return "\n".join(out + ["Everything fits. Nothing is cut."])
    o = card["options"]
    out += ["", "Nothing is cut until you approve it. Your options:"]
    n = 1
    for x in o["longer_ad"]:
        out.append("%d. A %d second ad - %s" % (n, x["id"], (
            "fits in " + ", ".join(MS.style(s)["label"] for s in x["fits_styles"]))
            if x["fits_styles"] else "does not fit any style"))
        n += 1
    out.append("%d. A different music style (see the lines above)" % n)
    n += 1
    out.append("%d. Voice: All Suno (default) or Velvet Voiceover" % n)
    n += 1
    fw = o[FEWER_WORDS_ID]
    out.append("%d. Fewer words - these exact lines would be cut, and you approve the list: %s"
               % (n, ", ".join(fw["cut_line_ids"]) or "none"))
    for nt in card["notices"]:
        out.append("Notice: " + nt["text"])
    return "\n".join(out)


def _with_saved_character(client_dir, base=None):
    """THE card, with the saved-character question where the brief's typed
    CHARACTER question sat when the client has saved characters (Part I, I6).
    Exactly one "who stars" question is ever asked: the pick replaces the typed
    description, so the total never moves -- the swap-in takes the typed
    CHARACTER question's own slot. With a client folder but no saved characters
    the card opens with one short line (``NO_SAVED_LINE``). No folder: the
    plain card. ``base`` is the card being asked (the new one by default; a
    resumed run passes the one it was asked with)."""
    base = QUESTIONS if base is None else base
    if not client_dir:
        return base
    from character_library import character_library as CL
    q = CL.saved_character_question(client_dir)
    if not q:
        return [dict(base[0], preface=NO_SAVED_LINE)] + list(base[1:])
    plain = [x for x in base if x["id"] != "character"]
    i = next((n for n, x in enumerate(base) if x["id"] == "character"), len(plain))
    return plain[:i] + [q] + plain[i:]  # PURPOSE leads (SPEC B1); AI MODELS leads
                                        # the production choices that follow it


def intro_question_count():
    """The number the intro states: what a new run asks in the common case.

    PURPOSE, plus every question the card asks one by one -- with the offer
    reply carrying the web address (so the address screen is not asked) and
    this computer's AI setup already saved (S75-006)."""
    asked = [q for q in QUESTIONS
             if not q.get("defaulted") and q["id"] not in ("models", "link")]
    return 1 + len(asked)                  # 1 is PURPOSE, which leads the card


try:
    from choice_card.intake_card.intro import build as _intro_build, take as _intro_take
except ImportError:                                # run as a plain script
    from intro import build as _intro_build, take as _intro_take  # noqa: E402

_INTRO = _intro_build(intro_question_count())


# --- U1 / S75-074: the studio-shaped export (studio-json) ---------------------
#: The Drama Studio renders one screen per intake question: a plain heading, the
#: question text, the example a typed answer shows, and -- for a priced option --
#: the price inputs the page turns into a true price for the length the client
#: picks. This export hands those to the studio from the SAME question list the
#: card uses, so the card and the studio can never disagree about a question.
#:
#: A typed screen with no example, or a choice screen with no question text or
#: no options, is a broken screen, not a thin one: studio_json REFUSES it
#: (StudioExportError -> exit 1) instead of writing a json file the studio would
#: render half-empty.

#: question id -> the Client Guide STEP that carries that question's example.
GUIDE_STEP = {
    "models": 3, "saved_character": 6, "length": 7, "music": 8, "look": 9,
    "model": 10, "spend": 11, "script": 13, "song": 14, "storyboard": 15,
    # DSR-105: the brief. STEP 4 covers the offer name, its web address and the
    # assets to use (logo, photos, one proof), so offer, link and photos all
    # take its example; STEP 5 is the audience and the action, STEP 6 casting.
    "offer": 4, "link": 4, "audience": 5, "character": 6, "photos": 4,
    # W1-card-questions-U1: the purpose screens (SPEC B1) carry their own steps
    # at the end of the guide, each with one Great answer line.
    "purpose": 18, "episode_length": 19, "shape": 20, "permission": 21,
    "where": 22, "agnes": 23,
    # S75-006: the CHECKPOINTS screen's own step (lane F adds it to the guide).
    "checkpoints": 24,
}

_HERE = os.path.dirname(os.path.abspath(__file__))
CLIENT_GUIDE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))),
    "references", "CLIENT-GUIDE.md")

#: question id -> the heading the page shows (S75-074 step 1). The page never
#: turns the card's shouting LABEL into a heading.
STUDIO_TITLES = {
    "purpose": "What is this video for?",
    "permission": "Your client's permission",
    "where": "Where it will run",
    "offer": "What you are promoting",
    "link": "Where to send people",
    "audience": "Who it is for",
    "character": "Who stars in it",
    "photos": "Photos and logos",
    "models": "Who builds and who checks",
    "length": "How long",
    "episode_length": "How long",
    "shape": "Tall or wide",
    "music": "The sound",
    "music_full": "The sound",
    "look": "The look",
    "agnes": "Your Agnes plan",
    "model": "Picture quality",
    "spend": "Your spending limit",
    #: the three approvals CHECKPOINTS replaces all say the same thing
    "checkpoints": "What you want to see first",
    "script": "What you want to see first",
    "song": "What you want to see first",
    "storyboard": "What you want to see first",
}

#: The exact example a typed screen shows (S75-074 step 3). Every other typed
#: screen takes its example from the Client Guide; a choice screen shows none.
STUDIO_EXAMPLES = {
    "link": '"https://example.com/speaker"',
    "photos": '"My logo and one product photo. I will send them after this."',
    "character": '"Tasha, a warm 40-year-old braider with locs, in a denim apron."',
}

#: S75-074 step 4: BUDGET in the page's own words. The chat card keeps its own
#: wording (``spend_question``); this is the exporter half the page renders.
STUDIO_BUDGET_ASK = ("What is the most this video may spend? Work stops and asks "
                     "you before going over.")
STUDIO_BUDGET_USE = "Use the recommended limit - about %s"
STUDIO_BUDGET_OWN = "Set my own limit"

#: The price function adds this many keyframes on top of the one-per-shot count
#: (the cover and the character plates). The page needs it to reproduce the
#: total exactly.
#: ponytail: a constant because the price function's plan is fixed today; derive
#: it from card_render's line items once the keyframe plan varies by length.
_KEYFRAME_EXTRA = 7


class StudioExportError(ValueError):
    """A studio screen is missing a field the studio cannot render without."""


def _great_answers(path=None):
    """STEP number -> the '**Great answer:**' line under that STEP in the guide.

    One example per step: the first 'Great answer' line after the heading, never
    one carried over from the previous step (the step resets on every heading).
    """
    import re
    try:
        with open(path or CLIENT_GUIDE, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError as e:
        raise StudioExportError("STUDIO_JSON_GUIDE_UNREADABLE %s" % e)
    out, step = {}, None
    for line in lines:
        m = re.match(r"^## STEP (\d+):", line)
        if m:
            step = int(m.group(1))
            continue
        if step and step not in out and line.startswith("**Great answer:**"):
            out[step] = line.split("**Great answer:**", 1)[1].strip()
    return out


def _rate_fields(n):
    """The price inputs the page turns into a true price for the length the
    client picks (S75-059 step 1), read from the same table and the same policy
    the one price function reads."""
    from catalog_calculator import card_render as CR
    vm = _vm()
    row = next((m for m in vm.MODELS if m.get("n") == n), None)
    if row is None:
        return {}
    return {"rate_usd": row["rate_usd"], "unit": row["unit"],
            "shot_s": row["shot_s"],
            "keyframe_usd": vm.RATES["keyframe_usd"],
            "song_usd": vm.RATES["song_usd"],
            #: the live planning allowance, not the stale figure in the table
            "redo_rate": CR.RETAKE_RATE,
            "keyframe_count_extra": _KEYFRAME_EXTRA}


def _recommended_model_n():
    """The model row the card marks recommended (the table's own default)."""
    models = _vm().require_choices()
    return next((m["n"] for m in models if m.get("recommended")), models[0]["n"])


def _recommended_limit_usd(length_label="60 seconds"):
    """The card total for the recommended model at the card's default length,
    from the one price function. None when the card cannot price it."""
    from catalog_calculator import card_render as CR
    try:
        return CR.quote(_recommended_model_n(), length_label)
    except (KeyError, ValueError, TypeError):
        return None


def _studio_title(q):
    """The page heading for a screen (S75-074 step 1), never the LABEL."""
    return STUDIO_TITLES.get(q.get("id")) or str(q.get("label") or "").title()


def _studio_example(q, answers):
    """The "great answer" a screen shows, or None (S75-074 step 3).

    A choice screen shows none: the option text is the answer. A typed screen
    shows its exact page example, or the Client Guide's example for its step."""
    if not q.get("free_text"):
        return None
    if q.get("id") in STUDIO_EXAMPLES:
        return STUDIO_EXAMPLES[q["id"]]
    step = GUIDE_STEP.get(q.get("id"))
    return answers.get(step) if step is not None else None


def _studio_option(q, n, opt, priced=False):
    """One option as the studio sees it: number, text, one sentence, whether it
    is the recommended pick, its sample link when one exists, and -- for a
    priced option -- the price inputs instead of a fixed dollar string."""
    text = opt[0] if isinstance(opt, (tuple, list)) else str(opt)
    detail = opt[1] if isinstance(opt, (tuple, list)) and len(opt) > 1 else ""
    if priced and " - about $" in detail:
        #: the card prices this option for its default length; the page prices
        #: the length the client picks, so the fixed figure never travels.
        detail = detail.split(" - about $")[0]
    rec = q.get("recommended")
    out = {"n": n, "text": text, "detail": detail or "", "price": None,
           "recommended": rec is not None and n - 1 == rec}
    if priced:
        out.update(_rate_fields(n))
    links = q.get("links") or {}
    if isinstance(links, dict) and n in links:
        out["sample_url"] = links[n]
    return out


def _studio_screen(q, answers):
    """One question as the studio sees it. Raises StudioExportError when a
    screen has no question text, a typed screen has no example, or a choice
    screen has no options -- a broken screen, never a thin one."""
    ask = str(q.get("ask") or "")
    if not ask:
        raise StudioExportError(
            "STUDIO_JSON_FIELD_MISSING id=%r field=question" % q.get("id"))
    qid = q.get("id")
    typed = bool(q.get("free_text"))
    #: S75-059 step 2: the fixed "60-second ad ... 50% redo allowance" sentence
    #: is gone from the screen the page draws; the page prices the length it is
    #: given instead.
    priced = qid == "model"
    if priced and q.get("price"):
        ask = ask.replace(str(q["price"]), "").strip()
    example = _studio_example(q, answers)
    if typed and not example:
        raise StudioExportError(
            "STUDIO_JSON_FIELD_MISSING id=%r field=example" % qid)
    options = [] if typed else [_studio_option(q, n, o, priced=priced)
                                for n, o in enumerate(q.get("options") or [], 1)]
    if not typed and not options:
        raise StudioExportError(
            "STUDIO_JSON_FIELD_MISSING id=%r field=options" % qid)
    screen = {
        "id": qid, "label": q.get("label", ""), "title": _studio_title(q),
        "question": ask, "price": None, "why": q.get("why"),
        "example": example,
        #: DSR-105 / S75-074 step 2: the page asks for the words itself, so a
        #: typed screen carries no option row at all.
        "typed": typed,
        #: S75-006: a screen the card never asks one by one. The page shows it
        #: behind "More options" and still sends its default answer in order.
        "optional": bool(q.get("optional")),
        "options": options,
    }
    if qid == "agnes":
        #: S75-020 / S75-074 step 7: the page marks an Agnes option recommended
        #: only when the client's remembered answer is yes -- and this export
        #: reads no per-machine state, so here it marks none.
        for o in screen["options"]:
            o["recommended"] = False
        from choice_card.intake_card.agnes_explanation import lines as explanation_lines
        screen["supplementary_explanation"] = explanation_lines()
    return screen


def _studio_spend_screen(q):
    """BUDGET in the page's own words (S75-074 step 4): the computed
    recommended limit first, the client's own limit second."""
    limit = _recommended_limit_usd()
    options = []
    if limit is not None:
        options.append({
            "n": 1, "text": STUDIO_BUDGET_USE % _usd(limit),
            "detail": ("the estimated price for your video, including a %s "
                       "allowance for redoing shots" % BC.label()),
            "price": None, "recommended": True,
            **_rate_fields(_recommended_model_n())})
    options.append({"n": len(options) + 1, "text": STUDIO_BUDGET_OWN,
                    "detail": "type a dollar amount, like $25",
                    "price": None, "recommended": False})
    return {"id": "spend", "label": q.get("label", "BUDGET"),
            "title": _studio_title(q), "question": STUDIO_BUDGET_ASK,
            "why": q.get("why"), "price": None, "example": None,
            "typed": False, "optional": bool(q.get("optional")),
            "options": options}


#: W1-card-questions-U1 (SPEC B1): which screens the studio page shows, and on
#: what. The page evaluates this instead of guessing, so a screen a purpose
#: never asks is never rendered. ``length_s_max`` is Trevor's rule that Agnes
#: only makes up to five minutes of video (SPEC A15).
_SHOWS_WHEN = {
    "purpose": {"purpose": [1, 2, 3, 4]},
    "episode_length": {"purpose": [1]},
    "shape": {"purpose": [1, 2, 3]},
    "permission": {"purpose": [2]},
    "where": {"purpose": [4]},
    #: a campaign answers EPISODE LENGTH instead, so LENGTH is not its screen
    "length": {"purpose": [2, 3, 4]},
    #: S75-006: CHECKPOINTS replaces the three approval screens for every purpose
    "checkpoints": {"purpose": [1, 2, 3, 4]},
    "agnes": {"agnes_remembered": ["unknown", "yes"],
              "purpose": [1, 2, 3, 4], "length_s_max": _AGNES_MAX_LENGTH_S},
}

#: Every screen the purpose flow never conditions on is shown for every purpose.
_EVERY_PURPOSE = {"purpose": [1, 2, 3, 4]}


def _conditional_questions():
    """The screens that are not on the plain card: they only exist for some
    purposes, so they ride beside the card's own list rather than in it.
    SHAPE is not one of them since S75-006: it is on the card as a defaulted
    recap screen, and it carries its purpose rule from ``_SHOWS_WHEN``."""
    return [_purpose_q(), _episode_length_q(), _permission_q(),
            _where_q(), _agnes_q("unknown")]


def _studio_for(q, answers):
    """One question as its studio screen; BUDGET in the page's own words."""
    return _studio_spend_screen(q) if q.get("id") == "spend" else _studio_screen(q, answers)


def studio_questions(questions=None, guide=None, conditional=False):
    """The card's questions as studio screens: id, label, title, question, why,
    example, typed, options. Raises StudioExportError when a screen has no
    question text, a typed screen has no example, or a choice screen has no
    options.

    conditional (SPEC B1) adds the purpose screens -- which the card only asks
    once it knows what the video is for -- each with the ``shows_when`` the page
    evaluates, and stamps every screen with its own condition. The card's own
    list is left as it is, so the page and the card still read the same source.
    """
    qs = QUESTIONS if questions is None else questions
    answers = _great_answers(guide)
    out = [_studio_for(q, answers) for q in qs]
    if not conditional:
        return out
    for screen in out:
        screen["shows_when"] = _SHOWS_WHEN.get(screen["id"], _EVERY_PURPOSE)
    for q in _conditional_questions():
        screen = _studio_for(q, answers)
        screen["shows_when"] = _SHOWS_WHEN[screen["id"]]
        out.append(screen)
    return out


def studio_json(questions=None, guide=None, conditional=False):
    """The studio-json envelope (version 0): every intake question as a studio
    screen carrying its heading, question, example and price inputs."""
    screens = studio_questions(questions, guide, conditional)
    return {"format": "studio-json", "version": 0,
            "question_count": len(screens), "questions": screens}


def main(argv=None):
    # SWI-002: the total is read off QUESTIONS here, so this line cannot go
    # stale; a saved character swaps into an existing slot, never adds one.
    ap = argparse.ArgumentParser(
        description="Print the intake card (%d questions, the same total with "
                    "a saved character)." % len(QUESTIONS))
    ap.add_argument("--format", choices=("text", "openclaw-json", "telegram-json", "studio-json", "session-json"),
                    default="text",
                    help="text: raw card for the Claude Code chat. "
                         "openclaw-json / telegram-json: one send payload per message. "
                         "studio-json: the studio question/price/example export (U1).")
    ap.add_argument("--target", default="", help="Telegram chat id (send formats)")
    ap.add_argument("--step", action="store_true",
                    help="one question at a time: print only the NEXT message, "
                         "given every --reply the client has sent so far (I7)")
    ap.add_argument("--reply", action="append", default=[],
                    help="a client reply, in order (repeat the flag)")
    ap.add_argument("--question-id", default=None,
                    help="Question identity from the last rendered session response.")
    ap.add_argument("--question-digest", default=None,
                    help="Digest of the exact question and options being answered.")
    ap.add_argument("--reply-source", default="client",
                    help="Answer provenance; client choices require client evidence.")
    ap.add_argument("--seed-answers-file", default=None,
                    help="JSON list of explicit prior raw client answers with source references.")
    ap.add_argument("--answer-source-ref", default=None,
                    help="Source reference for this explicit client answer.")
    ap.add_argument("--runtime", choices=("openclaw", "claude-nine", "openrouter-direct"),
                    default=None, help="Runtime that consumes the selected model bindings.")
    ap.add_argument("--run-state-file", default="",
                    help="with --step and no replies: send the one-time intro as its "
                         "own message first (recorded as intro_shown in this file)")
    ap.add_argument("--price", default=None,
                    help="the card total in dollars (planning allowance included); "
                         "shown as spend option 1 or 2")
    ap.add_argument("--limit", default=None,
                    help="a spend limit the brief already gave, in dollars; "
                         "shown as spend option 1")
    ap.add_argument("--limit-from-brief", action="store_true",
                    help="the --limit came from the brief; labels option 1 'from your brief'")
    ap.add_argument("--run-dir", default="",
                    help="run folder; when the recap is confirmed the storyboard "
                         "answer is written to its control/card-receipt.json")
    ap.add_argument("--client-dir", default="",
                    help="client data folder; when it holds saved characters the "
                         "card opens with the saved-character question (I6)")
    flow = ap.add_mutually_exclusive_group()
    flow.add_argument("--purpose-flow", dest="purpose_flow", action="store_true",
                      default=None,
                      help="turn the purpose card on (SPEC B1): PURPOSE is asked "
                           "first with its own follow-up, and a confirmed recap "
                           "writes control/method.json to --run-dir. Default: on "
                           "for a NEW run, off for a run already underway.")
    flow.add_argument("--no-purpose-flow", dest="purpose_flow", action="store_false",
                      help="ask the old card list, exactly as before the purpose "
                           "flow (a resumed project is always replayed as it was).")
    a = ap.parse_args(argv)
    #: S75X-W1-U1: the launcher decides the default once, from the run itself.
    #: A new order opens on the opening-coaching flow; a resumed run -- one that
    #: recorded what it used, or a chat run already past its intro -- keeps the
    #: card it was asked with and is never migrated or rewritten.
    purpose_flow = (a.purpose_flow if a.purpose_flow is not None
                    else new_run_flow(a.run_dir or None, a.run_state_file or None))

    def _priced_card(base):
        return [spend_question(a.price, a.limit, a.limit_from_brief)
                if q["id"] == "spend" else q
                for q in _with_saved_character(a.client_dir, base)]

    #: The card this caller is asking: the new one for a NEW run, and the one a
    #: resumed run was asked with (S75-006 step 5).
    qs = _priced_card(QUESTIONS if purpose_flow else LEGACY_QUESTIONS)
    if a.format == "studio-json":                  # U1: the studio export, whole card
        try:
            #: the purpose screens ride along with their shows_when, so the
            #: page can render the flow the card asks (SPEC B1). The export is
            #: always the NEW card the page serves, never a legacy list.
            payload = studio_json(_priced_card(QUESTIONS), conditional=True)
        except StudioExportError as e:
            sys.stderr.write("studio-json: %s\n" % e)
            return 1                               # refuse loudly, never a half file
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
        return 0
    # A run-bound card is an intake turn, even when the caller omits --step.
    # The unbound preview and the Studio export above retain their own shapes.
    if (a.seed_answers_file or a.format == "session-json"
            or a.run_dir or a.run_state_file):
        from intake_preflight.card_session_cli import run
        return run(a, questions=qs, purpose_flow=purpose_flow)
    if a.step:
        st = conversation(a.reply, qs, run_dir=a.run_dir or None, target=a.target or None,
                          client_dir=a.client_dir or None, purpose_flow=purpose_flow)
        if not a.reply and a.run_state_file and _intro_take(a.run_state_file):
            st = dict(st, message=_INTRO)          # FU-INTRO-MESSAGE
        if a.format == "text":
            sys.stdout.write(st["message"] + "\n")
        else:
            send = openclaw_send_argv if a.format == "openclaw-json" else telegram_payload
            sys.stdout.write(json.dumps(
                {"done": st["done"], "send": send(a.target, st["message"])}, indent=2) + "\n")
        return 2 if st.get("outcome") == "waiting" else 0   # the factory's exit 2
    if a.format == "text":
        sys.stdout.write(render_card(qs) + "\n")      # raw newlines, no JSON escaping
        return 0
    msgs = render_messages(qs)
    if a.format == "openclaw-json":
        out = [openclaw_send_argv(a.target, m) for m in msgs]
    else:
        out = [telegram_payload(a.target, m) for m in msgs]
    sys.stdout.write(json.dumps(out, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
