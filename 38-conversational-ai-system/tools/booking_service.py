#!/usr/bin/env python3
"""booking_service.py - production caller for the T-28 booking adapter.

Skill 38's booking playbook (launch/booking-playbook.md steps 2-5) resolves the
calendar from the operator map, offers only slots a live calendar reports free,
books only on an explicit yes, and records attendance/sales only from an
authoritative source. That behaviour lives in ``shared-utils/booking`` (T-28,
PBB-122 / PBB-420). This module is the production call site: it composes the
adapter over the accepted T-12 durable runtime, and it takes the operator's
policy and the live calendar/provider adapters from the caller.

Nothing is invented here: a missing policy field refuses, an unknown policy key
refuses (so a typo cannot silently drop a rule), and no adapter is defaulted.
Calling :func:`open_runtime` with a live ``availability`` and ``provider`` is the
one supported way to offer, book, change or record a booking outcome.

Import:

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from booking_service import load_policy, open_runtime

Assert-based self-check:  python3 -I booking_service.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Mapping

# Repo layout:      <repo>/38-conversational-ai-system/tools/booking_service.py
# Installed layout: <skills>/38-conversational-ai-system/tools/booking_service.py
# Both put shared-utils beside the skill, exactly as shared-utils/booking does.
_SHARED_UTILS = Path(
    os.environ.get("PB_SHARED_UTILS")
    or (Path(__file__).resolve().parents[2] / "shared-utils")
)
if not (_SHARED_UTILS / "booking" / "followthrough.py").is_file():
    raise ImportError(
        "booking_service needs the T-28 adapter at "
        f"{_SHARED_UTILS}/booking/followthrough.py. Set PB_SHARED_UTILS to that "
        "shared-utils directory."
    )
if str(_SHARED_UTILS) not in sys.path:
    sys.path.insert(0, str(_SHARED_UTILS))

from booking import BookingFollowThrough, BookingPolicy  # noqa: E402  (path set above)

# The whole operator-authored policy surface, and nothing else. A key outside
# this set is a configuration bug, not a value to ignore.
POLICY_FIELDS = (
    "calendars",
    "timezone",
    "location",
    "change_path",
    "max_window_days",
    "min_lead_hours",
    "daily_cap",
    "excluded_weekdays",
    "excluded_hours",
    "offer_next_available_beyond_window",
    "offer_waitlist",
    "max_declines",
    "prefer_first_72h",
)


def load_policy(document: Mapping[str, Any]) -> BookingPolicy:
    """Build the operator policy from configuration, refusing unknown keys."""
    if not isinstance(document, Mapping):
        raise ValueError("policy document must be a mapping")
    unknown = sorted(set(document) - set(POLICY_FIELDS))
    if unknown:
        raise ValueError(f"unknown policy field(s): {', '.join(unknown)}")
    return BookingPolicy(**dict(document))


def open_runtime(*, store: Any, availability: Any, provider: Any,
                 policy: BookingPolicy, tenant_id: str,
                 worker_id: str = "booking-worker") -> BookingFollowThrough:
    """Compose the T-28 adapter over the durable store and the real adapters.

    ``store`` is the T-12 DurableStore; ``availability`` and ``provider`` are the
    caller's live calendar adapters (contract in the adapter's docstring).
    """
    return BookingFollowThrough(
        store=store,
        availability=availability,
        provider=provider,
        policy=policy,
        tenant_id=tenant_id,
        worker_id=worker_id,
    )


def _selfcheck() -> int:
    policy = load_policy({
        "calendars": {"default": "cal_default"},
        "timezone": "America/New_York",
        "location": "12 Example St",
        "change_path": "reply CHANGE",
        "max_window_days": 14,
        "min_lead_hours": 12,
    })
    assert policy.calendars["default"] == "cal_default"
    assert policy.max_window_days == 14

    # Both refusal directions: a missing default calendar and a misspelled field.
    bad_documents = (
        {"calendars": {}, "timezone": "America/New_York", "location": "l",
         "change_path": "c", "max_window_days": 1, "min_lead_hours": 0},
        {"calendars": {"default": "c"}, "timezone": "America/New_York",
         "location": "l", "change_path": "c", "max_window_days": 1,
         "min_lead_hours": 0, "dailycap": 1},
    )
    for bad in bad_documents:
        try:
            load_policy(bad)
        except Exception:  # Refusal or ValueError - refusing is the contract
            continue
        raise AssertionError(f"load_policy accepted {bad!r}")

    print("booking_service self-check: OK 4 PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(_selfcheck())
