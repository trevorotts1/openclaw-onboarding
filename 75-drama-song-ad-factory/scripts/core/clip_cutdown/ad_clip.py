#!/usr/bin/env python3
"""The 60 s and 90 s AD_CLIP cut: a complete compressed sales arc (F19).

Trevor 2026-10-13: every campaign master also ships two ad clips that sell
the OFFER, where a trailer sells the EPISODE (method 8.1). Same planner,
same piece records, same 0.3 s crossfades and the same end-card renderer as
``trailer.plan_trailers`` -- only the arc's completeness and the destination
differ::

    opening -> ERM range (with its first sung line) -> Hero Shift ->
    breakthrough -> hook -> offer CTA end card with the offer destination

The offer destination is the checkout/booking link and nothing else
(``AD_NO_OFFER_DESTINATION``); an arc with no visible breakthrough is refused
(``AD_ARC_INCOMPLETE``); the Transformation Lock is checked on the chosen
ranges (``TRANSFORMATION_LOCK_BROKEN``).

stdlib only; no network, no spend.
"""
from __future__ import annotations

import os
import sys

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

from clip_cutdown import trailer  # noqa: E402

TOOL_NAME = "ad_clip"


def plan_ad_clips(timeline, blueprint, chosen_length_s, offer):
    """The 60 s and 90 s offer cuts; [] when the chosen length owes no derivative."""
    return trailer.plan("ad", timeline, blueprint, chosen_length_s, offer=offer)
