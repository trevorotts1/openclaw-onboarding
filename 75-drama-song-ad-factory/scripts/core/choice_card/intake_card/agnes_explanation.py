"""Supplementary explanation for the two existing AGNES choices.

The question and its option identities stay in intake_card._agnes_q.  This
module only supplies read-only text after that menu; it neither parses an
answer nor selects a route, checks a key, or makes a provider request.

S75-074 step 7: the five paragraphs that named vendors and daily quota figures
are two plain sentences. The client is choosing between a plan they already pay
for and the studio's own models; nothing here claims a remaining balance, and
no vendor name appears, because the page check forbids one.
"""
from __future__ import annotations

#: The two paragraphs, in order. Option 1 is the client's own Agnes plan;
#: option 2 is the studio's own models for everything.
PARAGRAPHS = (
    "Option 1 uses the plan you already pay Agnes for to make the pictures and "
    "clips. The song and the talking close-ups are still charged to your studio "
    "balance, and that cost is in your estimate.",
    "Option 2 uses the studio's own models for everything. You pick the quality "
    "next and see the cost before anything is made.",
)


def lines(env=None):
    """Both choices in plain language. ``env`` is accepted for callers that read
    the old quota settings; this text reads no setting and no credential."""
    del env
    return list(PARAGRAPHS)
