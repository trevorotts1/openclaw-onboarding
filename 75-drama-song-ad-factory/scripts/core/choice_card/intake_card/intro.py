"""FU-INTRO-MESSAGE: the one-time intro a client sees before question 1.

Plain text (the intake card is plain text, no Markdown). Sent ONCE, as its own
message, at the start of a new interactive run; never on later replies, resume
or recap. `take(run_state_file)` says whether to show it and records that it
was shown in the run state (`intro_shown`), so a resumed run never repeats it.
"""
import json
import os
import tempfile

INTRO = """Turn your offer into a music video people actually feel.

Answer a few quick questions, and we handle the rest:
- Write the story and script, with the song lyrics woven in
- Create your characters (or bring back ones you've saved)
- Compose an original song in the music style you choose
- Create every image and build the storyboard, shot by shot
- Make the video shots and lip-sync the singers
- Edit it all together with captions and your call to action

You approve the script, pick your favorite of 3 song versions, and sign off on the storyboard before any video is made. Longer videos also come with 60- and 90-second clips for social media.

Before we start: if your video uses KIE.ai or OpenRouter models, top up your credits there first so your video doesn't stop halfway.

Let's start - just a few quick questions."""


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
