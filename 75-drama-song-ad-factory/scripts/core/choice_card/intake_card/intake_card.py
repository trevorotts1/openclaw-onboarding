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
one carries a single option whose detail starts "Reply with" (the studio reads
that as "type it in"), and this module stays the one place their text lives.

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
screen carrying its question text, its price line and its "See a great answer"
example from the client guide (``studio_json``), so the Drama Studio renders the
same questions the card asks.

Stdlib only. No network: this module builds text and reads one local guide.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_CORE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

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
    typed = [q["label"].title() for q in qs if q.get("free_text")]
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
#: Client-facing names. "Hybrid" is the official name of the sketch-and-real-footage
#: look (its bible and id are still `hybrid`); the card label stays Sketch to Life.
_LOOK_NAME = {"sketch-to-life": "Sketch to Life (Hybrid)"}
_MUSIC_SENTENCE = {
    "soul-ballad": "slow, heartfelt singing; builds to a big emotional chorus.",
    "rnb-flow": "rhythmic rap verses, then a smooth sung hook you remember.",
    "soul-rise": "starts slow and sad, then lifts into an upbeat, hopeful groove.",
}


def _sample_links():
    """look id -> https sample-video link (style_samples.json); missing or null = no link."""
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "style_samples.json"), encoding="utf-8") as f:
        return {k: v for k, v in json.load(f).items() if v}


def _menu(ids, labels, sentences):
    return [(labels[i], sentences[i]) for i in ids]


def _looks():
    from choice_card.looks import looks as L
    labels = {i: _LOOK_NAME.get(i, L.LOOK_LABELS[i]) for i in L.LOOK_ORDER}
    return _menu(L.LOOK_ORDER, labels, _LOOK_SENTENCE)


def _look_links():
    """Sample link per look option, by option number (1-based); none = no entry."""
    from choice_card.looks import looks as L
    links = _sample_links()
    return {n: links[i] for n, i in enumerate(L.LOOK_ORDER, 1) if i in links}


def _musics():
    from music_styles import music_styles as MS
    return _menu(list(_MUSIC_SENTENCE), {k: MS.STYLES[k]["label"] for k in _MUSIC_SENTENCE},
                 _MUSIC_SENTENCE)


def _usd(x):
    return "$%.2f" % float(str(x).lstrip("$"))


def spend_question(price=None, limit=None, from_brief=False):
    """The ONE money question, asked here and nowhere else (FU-ONE-SPEND-QUESTION).
    price: the card's total in dollars (20% redo allowance included). limit: a
    maximum already known. from_brief: that maximum came from the brief (not a --limit
    override). Neither is ever defaulted: the client must reply."""
    opts, vals = [], {}
    if limit is not None:
        opts.append(("Your max: " + _usd(limit), "from your brief" if from_brief else None))
        vals[len(opts)] = str(limit).lstrip("$")
    if price is not None:
        opts.append((_usd(price), "the estimated price for your video, including a 20% allowance for redoing shots"))
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


def _models_q():
    from choice_card.intake_card import ai_models as AM
    return {"id": "models", "why": "One AI builds your video and a different AI checks the work.",
            "reason": "OpenRouter is the faster route, and a separate model checks the work.",
            "label": "AI MODELS",
            "ask": "Which AI should build your video, and which should check the work? "
                   "OpenRouter is recommended because it's faster; Ollama works too.",
            "options": [("Recommended setup", "An OpenRouter model builds, Claude Sonnet checks."),
                        ("Choose my own", "Reply with the build model and the check model, "
                         "e.g. 'DeepSeek builds, Sonnet checks'.")],
            "recommended": 0}


def _questions():
    return [
        _models_q(),
        {"id": "length", "why": "Length decides the story size and the price.", "reason": "the standard length for ads, and it fits stories, reels and ads.", "label": "LENGTH", "ask": "How long do you want your ad to be? The longer ads also come with short clips you can post on social media.",
         "options": [("60 seconds", "The standard ad length."),
                     ("90 seconds", "Room for a fuller story."),
                     ("3 minutes + 60s and 90s clips", "Plus a 60-second clip and a 90-second clip."),
                     ("5 minutes + 60s and 90s clips", "Plus a 60-second clip and a 90-second clip."),
                     ("10 minutes (the long version) + 60s and 90s clips", "Plus a 60-second clip and a 90-second clip.")],
         "recommended": 0},
        {"id": "music", "why": "The song carries the feeling of the whole ad.", "reason": "it is the style that tests best for emotional stories.", "label": "MUSIC STYLE", "ask": "Which sound fits your story?",
         "options": _musics(), "recommended": 0},
        {"id": "look", "why": "The look is what viewers see in every shot.", "reason": "it gives the most real, cinematic result.", "label": "VIDEO STYLE", "ask": "How should your video look? Tap a link to watch a sample.",
         "options": _looks(), "links": _look_links(), "recommended": 0},
        _model_question("60 seconds"),
        spend_question(),
        {"id": "storyboard", "why": "The storyboard is cheap to fix now and costly to fix after video is made.", "reason": "you see every scene before any money is spent on video.", "label": "STORYBOARD APPROVAL",
         "ask": "Do you want to approve the storyboard before any video is made?",
         "options": [("Yes, show me first", "Nothing is generated until you say go."),
                     ("No, just make it", "I start as soon as the card is approved.")],
         "recommended": 0},
        {"id": "song", "why": "The song is the heart of the ad, and it is cheap to change now and costly after video is made.", "reason": "you hear three labelled versions and pick your favourite before any money is spent on video.", "label": "SONG APPROVAL",
         "ask": "Do you want to hear and pick the song before any video is made?",
         "options": [("Yes, send me 3 versions to choose from", "Three labelled songs; nothing else starts until you pick, and two extra songs are added to the price."),
                     ("No, just make it", "I make one song and keep going.")],
         "recommended": 0},
        {"id": "script", "why": "The script is cheap to fix now and costly to fix after the song is made.", "reason": "you read the story and the lyrics before any money is spent on the song.", "label": "SCRIPT APPROVAL",
         "ask": "Do you want to read and approve the script - your story and the song lyrics - before the song is made?",
         "options": [("Yes, show me first", "Nothing is generated until you say go."),
                     ("No, just make it", "I start as soon as the card is approved.")],
         "recommended": 0},
    ]


def _model_price_line(length_label):
    """The one price sentence the VIDEO MODEL screen shows, from the length the
    client chose. The card's ask and the studio-json export both read it here,
    so the two price surfaces cannot drift apart."""
    from choice_card.video_models import video_models as VM
    return ("Prices are for your %s ad, with the song, pictures and a 20%% "
            "redo allowance." % VM.length_phrase(VM.length_seconds(length_label)))


def _vm():
    """The video-model table, imported the way this module imports everything it
    does not need to build the card's text (see _model_question)."""
    from choice_card.video_models import video_models as VM
    return VM


def _model_question(length_label, agnes_yes=False):
    """VIDEO MODEL: four models, each priced for the client's chosen length.
    A client who said yes to Agnes reads it as the backup it now is (SPEC A10):
    same models, same prices, one question of when they are used."""
    from choice_card.video_models import video_models as VM
    from catalog_calculator import card_render as CR
    cost = {m["n"]: "$%.2f" % CR.quote(m["n"], length_label) for m in VM.MODELS}
    ask = ("Which video model should make your shots if Agnes cannot? " if agnes_yes
           else "Which video model should make your shots? ")
    return {"id": "model", "why": "The video model sets how good the shots look and what they cost.",
            "reason": "it gives the best balance of quality and price.", "label": "VIDEO MODEL",
            "ask": ask + _model_price_line(length_label),
            "price": _model_price_line(length_label),
            "options": [(m["name"], "%s - about %s" % (m["blurb"], cost[m["n"]])) for m in VM.MODELS],
            "values": [cost[m["n"]] for m in VM.MODELS],
            "recommended": next(i for i, m in enumerate(VM.MODELS) if m["recommended"])}


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

#: The LENGTH seconds each use offers (SPEC B2). 30 seconds is Trevor's
#: 2026-10-13 paid-ad addition; the campaign is asked as EPISODE LENGTH instead.
_LENGTH_KEEP = {"testimonial": (60, 90, 180), "lesson": (60, 90, 180),
                "paid_ad": (30, 60, 90), "short_post": (60, 90)}

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
    return {"id": "episode_length", "label": "EPISODE LENGTH",
            "why": "The full episode lives on your YouTube channel; the trailers bring "
                   "people to it.",
            "reason": "it is the shortest episode that still earns two good trailers.",
            "ask": "How long should the full episode be? Your 60-second and 90-second "
                   "trailers and ad clips are included.",
            "options": [("3 minutes", "one full story with room for the turn and the offer."),
                        ("5 minutes", "a deeper story with more of the solution at work."),
                        ("7 minutes", "a fuller episode with another real step of the "
                         "solution. (made with KIE, not Agnes)"),
                        ("10 minutes", "the long version, a full show episode. "
                         "(made with KIE, not Agnes)")],
            "recommended": 0}


def _shape_q():
    """How every shot is framed (SPEC B1, purposes 1-3)."""
    return {"id": "shape", "label": "SHAPE",
            "why": "The shape decides how every shot is framed.",
            "reason": "it fits phones, Reels, Shorts and TikTok.",
            "ask": "How should your video be framed?",
            "options": [("Vertical", "phones, Reels, Shorts, TikTok."),
                        ("Wide", "YouTube on a TV or a computer.")],
            "recommended": 0}


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
            "recommended": 0,
            "rec_mark": "(RECOMMENDED when you said yes before)",
            "closing": "Reply with a number."}


_LENGTH_30 = ("30 seconds", "the shortest length that still tells the whole story.")


def _length_q(key):
    """LENGTH, filtered to the options the use really offers (SPEC B2). The
    option text comes from the card's own LENGTH question, so the two can never
    drift; only the 30-second paid-ad option is new."""
    base = next(q for q in QUESTIONS if q["id"] == "length")
    keep = _LENGTH_KEEP.get(key)
    if not keep:
        return base
    opts = ([_LENGTH_30] if 30 in keep else []) + list(base["options"])
    opts = [o for o in opts if _vm().length_seconds(o[0]) in keep]
    return dict(base, options=opts,
                #: the standard length stays the recommendation on every use
                #: (METHOD-INTEGRATION 3.2); the 30-second ad is an option, not
                #: a new recommendation.
                recommended=next(i for i, o in enumerate(opts)
                                 if _vm().length_seconds(o[0]) == 60))


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


def _shaped(qs, answers, client_dir=None):
    """The question list rebuilt from the answers so far -- the ``_priced`` idea
    applied to the whole list (SPEC B1).

    PURPOSE is first; its one follow-up sits right after it, except EPISODE
    LENGTH, which takes LENGTH's own slot so a campaign adds no screen; AI
    MODELS and the rest keep the order they already had; AGNES sits after VIDEO
    STYLE unless the client already said no, and only while the chosen length is
    one Agnes can make. The conditional ids are stripped before the rebuild, so
    shaping twice on the same answers gives the same list.
    """
    base = [q for q in qs if q["id"] not in _CONDITIONAL_IDS]
    out, pos = [], {}

    def place(q):
        pos[q["id"]] = len(out)
        out.append(q)

    place(_purpose_q())
    purpose_n = _pick(pos, answers, "purpose")
    if purpose_n is None:                       # nothing chosen yet
        return out + base
    length_text, agnes_yes = None, False
    if purpose_n in (2, 4):                     # the one follow-up, right after PURPOSE
        place(_permission_q() if purpose_n == 2 else _where_q())
    key = _purpose_key(purpose_n, _pick(pos, answers, "where"))
    for q in base:
        if q["id"] == "length":
            #: EPISODE LENGTH for a campaign is the LENGTH question in its own
            #: slot (METHOD-INTEGRATION 3.2: it replaces LENGTH), so a campaign
            #: grows by PURPOSE and no other screen.
            lq = _episode_length_q() if key == "campaign" else _length_q(key)
            ask_id = "episode_length" if key == "campaign" else "length"
            place(lq)
            if purpose_n in _SHAPE_PURPOSES:
                place(_shape_q())
            n = _pick(pos, answers, ask_id) or 0      # not answered yet: no length
            length_text = lq["options"][n - 1][0] if 0 < n <= len(lq["options"]) else None
            continue
        if q["id"] == "model":
            place(_model_question(length_text or "60 seconds", agnes_yes=agnes_yes))
            continue
        place(q)
        if q["id"] == "look":
            remembered = (_agnes_remembered(client_dir) if length_text
                          and _vm().length_seconds(length_text) <= _AGNES_MAX_LENGTH_S
                          else None)         # 7 and 10 minute episodes are KIE-only
            if remembered and remembered != "no":
                place(_agnes_q(remembered))
            agnes_yes = _pick(pos, answers, "agnes") == 1
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


def _brief_questions():
    return [
        _typed("offer", "OFFER",
               "The story, the song and the call to action are all built around this.",
               "What are we promoting? Give the exact name of your offer."),
        _typed("link", "OFFER LINK",
               "The link goes on screen at the end, so it has to be exact.",
               "What web address should the video send people to? Paste it rather than typing it from memory."),
        _typed("audience", "AUDIENCE",
               "One audience and one action beat ten of each.",
               "Who is this video for, and what should they do after watching it?"),
        _typed("character", "CHARACTER",
               "Your characters are the actors, and viewers spend the whole video with them.",
               "Who stars in your video? Describe them by name, age, look and clothing."),
        _typed("photos", "PHOTOS",
               "A real photo makes the story feel true instead of invented.",
               "Which photos or proof should we use - your logo, a product shot, a testimonial? Reply \"none\" if you have none."),
    ]


QUESTIONS = _brief_questions() + _questions()


def example_replies(questions=None):
    """One plausible reply per question, in order: the typed answer for a brief
    question, a dollar amount for BUDGET, the recommended pick for a choice.
    Fixtures and tests use it so a complete card needs no hand-counting."""
    out = []
    for q in (questions or QUESTIONS):
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
    """Numbered option lines; an option with a sample link gets an indented line under it."""
    out = []
    for n, (opt, sentence) in enumerate(q["options"], 1):
        mark = (" " + q.get("rec_mark", REC)) if n - 1 == q.get("recommended") else ""
        out.append("%d. %s%s%s" % (n, opt, " - " + sentence if sentence else "", mark))
        if n in q.get("links", {}):
            out.append("   Watch: " + q["links"][n])
    return out


def _typed_block(i, total, q, why=False):
    """A brief question's block: the ask, then the one line that says the
    answer is typed. There is no menu to number, so there is no menu to mark,
    and no blank line inside the block -- the blank line is what separates one
    question from the next."""
    lines = ["Question %d of %d - %s" % (i, total, q["label"])]
    if why:
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
    r = q.get("recommended", 0)
    if r is None:
        # nothing to recommend: the BUDGET asks for an amount, a yes/no
        # question (PERMISSION) only asks which one.
        lines += ["", q.get("closing", "Reply with a dollar amount, like $25.")]
        return "\n".join(lines)
    lines.append("")
    if q.get("reason"):                     # a question may only mark its pick
        lines.append("I recommend option %d (%s) because %s" % (r + 1, q["options"][r][0], q["reason"]))
    lines.append(q.get("closing") or "Reply with a number, or say \"recommended\".")
    return "\n".join(lines)


def render_recap(answers, questions=None):
    qs = _priced(questions or QUESTIONS, answers)
    lines = ["Here is what you picked:"]
    for i, (q, a) in enumerate(zip(qs, answers), 1):
        if "recap" in q and a.get("n"):
            lines.append("%d. %s" % (i, q["recap"][a["n"] - 1]))
            continue
        price = (" - about " + q["values"][a["n"] - 1]) if q["id"] == "model" and a.get("n") else ""
        lines.append("%d. %s: %s%s" % (i, q["label"].title().replace("Model", "model"), a["text"], price))
    lines += ["", 'Reply "yes" to start, or the number of a line to change it.']
    return "\n".join(lines)


_YES = ("yes", "y", "yep", "go", "ok", "okay", "start", "approve", "approved")

#: The words that mean "take the recommended option". A typed brief question
#: refuses them too, so they can never be stored as an answer.
_PICK_WORDS = ("recommended", "recommend", "rec")


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
                "text": AM.label(c["build"]) + " builds, " + AM.label(c["check"]) + " checks"}
    if q.get("free_text"):                 # a brief question: the answer IS the text
        raw = (reply or "").strip()
        # A mistyped "1", a stray "yes" or a stray "recommended" must never be
        # stored as somebody's offer, so none of the pick words is an answer.
        if len(raw) < 2 or t in _YES or t in _PICK_WORDS or len(raw) > MAX_TYPED_ANSWER_CHARS:
            return None
        return {"n": 1, "text": raw, "value": raw, "id": q["id"]}
    if t in _PICK_WORDS or (t in _YES and len(opts) > 0):
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
                 run_dir=None, target=None, client_dir=None, purpose_flow=False):
    """Replay the client's replies from the start; return the state and the ONE
    message to send next. Stateless, so claude-nine and OpenClaw can both call
    it with the replies so far. state: answers, done, message, video_model.
    With state_store + run_id, the client's video model is written to run state
    (the F14 lock) as soon as it is answered; the card and dispatch read it there.
    With run_dir, the recap confirmation writes the STORYBOARD and SONG APPROVAL
    answers to the run (approval_runner / song_choices record_card_answer), so Yes
    turns the pick gates on; target (the client's chat id) is stored with them.

    purpose_flow (SPEC B1) is what turns the PURPOSE card on: the question list
    is rebuilt from the answers so far (``_shaped``) instead of priced in place,
    a confirmed recap writes control/method.json and the receipt's agnes block,
    and the client's Agnes answer is remembered in their own data folder. It is
    off by default so every caller that has not been wired for it yet still gets
    the card it gets today, byte for byte. client_dir is the folder those
    remembered answers live in.
    """
    qs = questions or QUESTIONS
    answers, fix, note, done = [], None, "", False

    def shaped(list_, ans):
        return _shaped(list_, ans, client_dir) if purpose_flow else _priced(list_, ans)

    for r in replies:
        note = ""
        qs = shaped(qs, answers)
        if len(answers) < len(qs) and fix is None:
            a = _parse(r, qs[len(answers)])
            if a and "error" in a:
                note = a["error"] + " "
            elif a:
                answers.append(a)
            else:
                note = "Sorry, I did not catch that. "
        elif fix is not None:                       # re-answering one line
            a = _parse(r, qs[fix])
            if a and "error" in a:
                note = a["error"] + " "
            elif a:
                if qs[fix]["id"] == "purpose":
                    # the whole list was built around the old purpose, so every
                    # answer after it has to be given again (SPEC B1)
                    del answers[fix + 1:]
                answers[fix], fix = a, None
            else:
                note = "Sorry, I did not catch that. "
        else:                                       # recap: yes, or a line number
            t = r.strip().lower()
            if t in _YES:
                done = True
            elif t.isdigit() and 1 <= int(t) <= len(qs):
                fix = int(t) - 1
            else:
                note = "Sorry, I did not catch that. "
    qs = shaped(qs, answers)
    model_n = next((a["n"] for q, a in zip(qs, answers) if q["id"] == "model"), None)
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
        if run_dir:     # recap confirmed: the storyboard answer goes to the run
            from storyboard_director import approval_runner as _ar
            _ar.record_card_answer(run_dir, answers, qs, target)
            from song_choices import song_choices as _sc   # noqa: PLC0415
            _sc.record_card_answer(run_dir, answers, target)
            from script_approval import card_answers       # noqa: PLC0415
            card_answers.write(run_dir, answers, qs)
            if purpose_flow:
                record = _method_record(answers, qs)
                if record:
                    _write_json(os.path.join(run_dir, "control", "method.json"), record)
                _record_agnes_receipt(run_dir, answers, qs)
        if purpose_flow and client_dir:
            _remember_agnes(client_dir, answers, qs)
        msg = "Locked in. I am starting now."
    elif fix is not None:
        msg = note + render_step(fix + 1, qs)
    elif len(answers) < len(qs):
        msg = note + render_step(len(answers) + 1, qs)
        if not replies and qs[0].get("preface"):
            msg = qs[0]["preface"] + "\n\n" + msg
    else:
        msg = note + render_recap(answers, qs)
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
    """Plain question strings -> numbered, blank-line separated message.

    Used by intake / intake_book for their ``question_message`` so those
    questions get the same layout (one per line group, blank line between).
    """
    texts = [t for t in texts if t]
    if not texts:
        return None
    blocks = ["Question %d of %d\n%s" % (i, len(texts), t)
              for i, t in enumerate(texts, 1)]
    return "\n\n".join(blocks + ["Reply with one answer per question, in order."])


def _split_long(block, limit):
    """A block over the limit splits on line boundaries, never mid-line."""
    out, cur = [], ""
    for line in block.split("\n"):
        cand = cur + "\n" + line if cur else line
        if len(cand) > limit and cur:
            out.append(cur)
            cur = line
        else:
            cur = cand
    return out + ([cur] if cur else [])


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


def openclaw_send_argv(target, text, media=()):
    """Exact argv for ``openclaw message send`` on Telegram. A list, not a
    shell string: run it with subprocess (shell=False) and the newlines in
    ``text`` reach the sender untouched."""
    return (["openclaw", "message", "send", "--channel", "telegram",
             "--target", str(target), "--message", text]
            + [x for m in media for x in ("--media", str(m))])


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


def _with_saved_character(client_dir):
    """QUESTIONS, with the saved-character question where the brief's typed
    CHARACTER question sat when the client has saved characters (Part I, I6).
    Exactly one "who stars" question is ever asked: the pick replaces the typed
    description, so the total never moves -- the swap-in takes the typed
    CHARACTER question's own slot. With a client folder but no saved characters
    the card opens with one short line (``NO_SAVED_LINE``). No folder: the
    plain card. SWI-002: len() of every branch here equals len(QUESTIONS), and
    test_intake_card_h9.py asserts it."""
    if not client_dir:
        return QUESTIONS
    from character_library import character_library as CL
    q = CL.saved_character_question(client_dir)
    if not q:
        return [dict(QUESTIONS[0], preface=NO_SAVED_LINE)] + QUESTIONS[1:]
    plain = [x for x in QUESTIONS if x["id"] != "character"]
    i = len(BRIEF_IDS) - 1              # the brief's CHARACTER question's own slot
    return plain[:i] + [q] + plain[i:]  # PURPOSE leads (SPEC B1); AI MODELS leads
                                        # the production choices that follow it


try:
    from choice_card.intake_card.intro import INTRO as _INTRO, take as _intro_take
except ImportError:                                # run as a plain script
    from intro import INTRO as _INTRO, take as _intro_take  # noqa: E402


# --- U1: the studio-shaped export (studio-json) --------------------------------
#: The Drama Studio renders one screen per intake question, and each screen shows
#: three things: the question text, the price line (when that screen carries one)
#: and a "See a great answer" example from the client guide. This export hands
#: those to the studio from the SAME question list the card uses, so the card and
#: the studio can never disagree about a question or a price.
#:
#: A screen missing its question text or its example is a broken screen, not a
#: thin one: studio_json REFUSES it (StudioExportError -> exit 1) instead of
#: writing a json file the studio would render half-empty.

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
}

_HERE = os.path.dirname(os.path.abspath(__file__))
CLIENT_GUIDE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))),
    "references", "CLIENT-GUIDE.md")


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


def _studio_option(q, n, opt):
    """One option as the studio sees it: number, label, one sentence, its own
    price when the option has one, and whether it is the recommended pick."""
    text = opt[0] if isinstance(opt, (tuple, list)) else str(opt)
    detail = opt[1] if isinstance(opt, (tuple, list)) and len(opt) > 1 else ""
    values = q.get("values")
    raw = (values[n - 1] if isinstance(values, list) and n - 1 < len(values)
           else values.get(n) if isinstance(values, dict) else None)
    rec = q.get("recommended")
    return {"n": n, "text": text, "detail": detail or "",
            "price": None if raw is None else _usd(raw),
            "recommended": rec is not None and n - 1 == rec}


def _studio_screen(q, answers):
    """One question as the studio sees it. Raises StudioExportError when a
    screen has no question text, no example, or no options -- a broken screen,
    never a thin one."""
    ask = q.get("ask") or ""
    if not ask:
        raise StudioExportError(
            "STUDIO_JSON_FIELD_MISSING id=%r field=question" % q.get("id"))
    step = GUIDE_STEP.get(q.get("id"))
    example = answers.get(step) if step is not None else None
    if not example:
        raise StudioExportError(
            "STUDIO_JSON_FIELD_MISSING id=%r field=example" % q.get("id"))
    options = q.get("options") or []
    if not options:
        raise StudioExportError(
            "STUDIO_JSON_FIELD_MISSING id=%r field=options" % q.get("id"))
    return {
        "id": q.get("id"), "label": q.get("label", ""), "question": ask,
        "price": q.get("price"),
        "example": example,
        #: DSR-105: a brief question's answer is typed, not picked. The
        #: page reads this rather than sniffing the option text, so a
        #: reworded hint can never turn a text box back into a menu.
        "typed": bool(q.get("free_text")),
        "options": [_studio_option(q, n, o) for n, o in enumerate(options, 1)],
    }


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
    "agnes": {"agnes_remembered": ["unknown", "yes"],
              "purpose": [1, 2, 3, 4], "length_s_max": _AGNES_MAX_LENGTH_S},
}

#: Every screen the purpose flow never conditions on is shown for every purpose.
_EVERY_PURPOSE = {"purpose": [1, 2, 3, 4]}


def _conditional_questions():
    """The screens that are not on the plain card: they only exist for some
    purposes, so they ride beside the card's own list rather than in it."""
    return [_purpose_q(), _episode_length_q(), _shape_q(), _permission_q(),
            _where_q(), _agnes_q("unknown")]


def studio_questions(questions=None, guide=None, conditional=False):
    """The card's questions as studio screens: id, label, question, price,
    example, options. Raises StudioExportError when a screen has no question
    text, no example, or no options.

    conditional (SPEC B1) adds the purpose screens -- which the card only asks
    once it knows what the video is for -- each with the ``shows_when`` the page
    evaluates, and stamps every screen with its own condition. The card's own
    list is left as it is, so the page and the card still read the same source.
    """
    qs = QUESTIONS if questions is None else questions
    answers = _great_answers(guide)
    out = [_studio_screen(q, answers) for q in qs]
    if not conditional:
        return out
    for screen in out:
        screen["shows_when"] = _SHOWS_WHEN.get(screen["id"], _EVERY_PURPOSE)
    for q in _conditional_questions():
        screen = _studio_screen(q, answers)
        screen["shows_when"] = _SHOWS_WHEN[screen["id"]]
        out.append(screen)
    return out


def studio_json(questions=None, guide=None, conditional=False):
    """The studio-json envelope (version 0): every intake question as a studio
    screen carrying its question, price and example."""
    screens = studio_questions(questions, guide, conditional)
    return {"format": "studio-json", "version": 0,
            "question_count": len(screens), "questions": screens}


def main(argv=None):
    # SWI-002: the total is read off QUESTIONS here, so this line cannot go
    # stale; a saved character swaps into an existing slot, never adds one.
    ap = argparse.ArgumentParser(
        description="Print the intake card (%d questions, the same total with "
                    "a saved character)." % len(QUESTIONS))
    ap.add_argument("--format", choices=("text", "openclaw-json", "telegram-json", "studio-json"),
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
    ap.add_argument("--run-state-file", default="",
                    help="with --step and no replies: send the one-time intro as its "
                         "own message first (recorded as intro_shown in this file)")
    ap.add_argument("--price", default=None,
                    help="the card total in dollars (20%% redo allowance included); "
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
    ap.add_argument("--purpose-flow", action="store_true",
                    help="turn the purpose card on (SPEC B1): PURPOSE is asked "
                         "first with its own follow-up, and a confirmed recap "
                         "writes control/method.json to --run-dir")
    a = ap.parse_args(argv)
    qs = [spend_question(a.price, a.limit, a.limit_from_brief) if q["id"] == "spend" else q
          for q in _with_saved_character(a.client_dir)]
    if a.format == "studio-json":                  # U1: the studio export, whole card
        try:
            #: the purpose screens ride along with their shows_when, so the
            #: page can render the flow the card asks (SPEC B1)
            payload = studio_json(qs, conditional=True)
        except StudioExportError as e:
            sys.stderr.write("studio-json: %s\n" % e)
            return 1                               # refuse loudly, never a half file
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
        return 0
    if a.step:
        st = conversation(a.reply, qs, run_dir=a.run_dir or None, target=a.target or None,
                          client_dir=a.client_dir or None, purpose_flow=a.purpose_flow)
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
