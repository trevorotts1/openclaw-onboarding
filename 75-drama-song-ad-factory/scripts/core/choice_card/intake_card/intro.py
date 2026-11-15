"""FU-INTRO-MESSAGE: the one-time intro a client sees before question 1.

Plain text (the intake card is plain text, no Markdown). Sent ONCE, as its own
message, at the start of a new interactive run; never on later replies, resume
or recap. `take(run_state_file)` says whether to show it and records that it
was shown in the run state (`intro_shown`), so a resumed run never repeats it.

S75-006: the intro says HOW MANY short questions are coming, read from the
card's own list (``intake_card.intro_question_count``), and it no longer ends
with a second promise of "a few quick questions".
"""
import json
import os
import tempfile

_TEMPLATE = """Turn your offer into a video dramatization with music that people actually feel.

I'll ask about {count} short questions, and we handle the rest:
- Write the story and script, with the song lyrics woven in
- Create your characters (or bring back ones you've saved)
- Compose an original song in the music style you choose
- Create every image and build the storyboard, shot by shot
- Make the video shots and lip-sync the singers
- Edit it all together with captions and your call to action

You approve the script, pick your favorite of 3 song versions, and sign off on the storyboard before any video is made. Longer videos also come with 60- and 90-second clips for social media.

Before we start: if your video uses KIE.ai or OpenRouter models, top up your credits there first so your video doesn't stop halfway.

Let's start."""


def build(count):
    """The intro text, carrying the live question count."""
    return _TEMPLATE.format(count=count)


def _live_count():
    """The count the card itself asks in the common case (one source)."""
    from . import intake_card as IC
    return IC.intro_question_count()


def __getattr__(name):
    """``INTRO`` is built on first use from the card's live count.

    A module-level literal would be a second source of the total, and importing
    the card at import time here would make the two modules import each other
    mid-load."""
    if name == "INTRO":
        return build(_live_count())
    raise AttributeError("module %r has no attribute %r" % (__name__, name))


def take(run_state_file):
    """True exactly once per run state file: when it has no `intro_shown`."""
    try:
        with open(run_state_file, encoding="utf-8") as fh:
            state = json.load(fh)
    except FileNotFoundError:
        state = {}
    except (OSError, ValueError):
        return False                      # unreadable state: never clobber it
    if not isinstance(state, dict) or state.get("intro_shown"):
        return False
    state["intro_shown"] = True
    d = os.path.dirname(os.path.abspath(run_state_file))
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, sort_keys=True)
    os.replace(tmp, run_state_file)
    return True
