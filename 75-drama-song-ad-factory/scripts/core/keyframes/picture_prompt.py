"""picture_prompt.py: the picture-prompt builder (rows N-26 and N-121). Stdlib only.

Section 9.3 gives `scripts/core/keyframes/` "the picture-prompt builder", so a
keyframe prompt is assembled here from locked blocks, never hand-written:

* N-26 (3A.5): the words on props come from the text record; the builder writes
  one sentence per written object, with the exact words in quotes and the
  phrase "reads exactly", plus the Prop Facing sentence (3P).
* N-121 (3M.4): the place block carries the World Bible's own numbers -- the
  room's size, its set pieces, the crowd sentence for the shot's state, and the
  story clock's light. The blanket "no extra people" line is sent only when the
  shot's crowd state is empty.

The dispatcher's rule then holds: a prompt for a shot with a record entry must
carry every recorded string in quotes and "reads exactly"
(``text_on_screen.text_prompt_ok``). No provider call, no spend, no picture.
"""
from __future__ import annotations

from storyboard import text_on_screen as _text

TEXT_PROMPT_MISSING = _text.TEXT_PROMPT_MISSING

PLACE_BLOCK_INCOMPLETE = "PLACE_BLOCK_INCOMPLETE"
CROWD_SENTENCE_MISSING = "CROWD_SENTENCE_MISSING"

#: The line that survives only for a shot whose crowd state is empty (3M.4.3).
EMPTY_ROOM_LINE = "The room is empty of other people."

#: Crowd states the story calls a service, a class or a meeting are full by
#: count unless the beat says otherwise (3M.4.2).
FULL_STATES = frozenset({"full", "service", "class", "meeting", "congregation"})

class PromptError(ValueError):
    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code

def _text_of(value):
    return value if isinstance(value, str) else ""

def _places(world):
    if not isinstance(world, dict):
        return []
    rows = world.get("locations") or world.get("places")
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []

def _size_sentence(place):
    """The room's size in numbers (3M.4, "the room's size, in numbers")."""
    size = place.get("size") or place.get("size_text")
    if isinstance(size, str) and size.strip():
        return "The room, in numbers: %s." % size.strip()
    if isinstance(size, dict):
        parts = ["%s %s" % (k.replace("_", " "), v) for k, v in size.items()
                 if isinstance(v, (int, float)) and not isinstance(v, bool)]
        if parts:
            return "The room, in numbers: %s." % ", ".join(parts)
    return ""

def crowd_sentence(place, state):
    """The crowd's own sentence for this state (3M.4 rule 3).

    Empty (or no state) sends the "room is empty" line and nothing else; any
    other state says who is there and how many from the place's own numbers.
    """
    state = _text_of(state).strip().lower()
    if not state or state == "empty":
        return EMPTY_ROOM_LINE
    states = place.get("crowd_states") or {}
    entry = states.get(state) if isinstance(states, dict) else None
    if isinstance(entry, dict):
        lo, hi = entry.get("min"), entry.get("max")
        count = entry.get("count")
        life = place.get("background_life") or {}
        who = _text_of(life.get("who")).strip()
        doing = _text_of(life.get("doing")).strip()
        if isinstance(lo, (int, float)) and isinstance(hi, (int, float)):
            how_many = "about %d to %d people" % (lo, hi)
        elif isinstance(count, (int, float)) and not isinstance(count, bool):
            how_many = "about %d people" % count
        else:
            how_many = "the people its state gives"
        out = "The room holds %s" % how_many
        if who:
            out += ": %s" % who
        if doing:
            out += ", %s" % doing
        return out + "."
    if state in FULL_STATES:
        raise PromptError(
            CROWD_SENTENCE_MISSING,
            "crowd state %r is a service/class/meeting but the place names no "
            "count for it; a full room is recorded by count (3M.4)" % state)
    return ""

def place_block(place, state="", time_of_day=""):
    """The place block: size, set pieces, crowd sentence, clock light (3M.4)."""
    if not isinstance(place, dict):
        raise PromptError(PLACE_BLOCK_INCOMPLETE,
                          "no World Bible entry for this shot's place")
    lid = _text_of(place.get("location_id")).strip()
    sentences = ["The place is %s." % (lid or "the named set")]
    size = _size_sentence(place)
    if size:
        sentences.append(size)
    pieces = [str(p) for p in place.get("set_pieces") or [] if str(p).strip()]
    if pieces:
        sentences.append("Its set pieces are there: %s." % ", ".join(pieces))
    crowd = crowd_sentence(place, state)
    if crowd:
        sentences.append(crowd)
    clock = place.get("clock") or {}
    tod = _text_of(time_of_day).strip().lower()
    if isinstance(clock, dict) and tod in clock:
        light = _text_of(clock[tod]).strip()
        if light:
            sentences.append("The light is %s light, the story clock's own." % light)
    return " ".join(sentences)

def place_for(world, location_id):
    """The World Bible entry for one place, or None."""
    lid = _text_of(location_id).strip()
    for place in _places(world):
        if _text_of(place.get("location_id")).strip() == lid:
            return place
    return None

def build_picture_prompt(shot, text_entry=None, world=None):
    """Assemble one keyframe prompt: the shot's part, the place, the words.

    ``shot["picture_part"]`` is the section writer's own part (3H.1). The place
    block comes from the World Bible (N-121); the written objects from the text
    record (N-26). A prompt that does not carry every recorded string is
    refused ``TEXT_PROMPT_MISSING`` (3A.5.3).
    """
    if not isinstance(shot, dict):
        raise PromptError(TEXT_PROMPT_MISSING, "shot is not a row")
    sid = _text_of(shot.get("shot_id")) or "the shot"
    parts = [_text_of(shot.get("picture_part")).strip()
             or _text_of(shot.get("picture_prompt")).strip()]
    if world is not None:
        place = place_for(world, shot.get("location_id"))
        if place is None:
            raise PromptError(
                PLACE_BLOCK_INCOMPLETE,
                "shot %s names place %r with no World Bible entry; the run "
                "creates and locks it first (3C.10, 3M.4 rule 7)"
                % (sid, shot.get("location_id")))
        parts.append(place_block(place, shot.get("crowd_state"),
                                 shot.get("time_of_day")))
    if text_entry:
        parts.extend(_text.picture_prompt_sentences(text_entry))
        parts.extend(_text.facing_sentence(text_entry))
    prompt = " ".join(p for p in parts if p)
    if text_entry and not all(_text.text_prompt_ok(prompt, [obj])
                              for obj in text_entry):
        raise PromptError(TEXT_PROMPT_MISSING,
                          "shot %s prompt does not quote every recorded string "
                          "and say \"reads exactly\" (3A.5.3)" % sid)
    return prompt
