#!/usr/bin/env python3
"""followthrough.py - real availability, recheck-at-commit, booking receipts,
timezone/location/change path, and non-guessed attendance/sales outcomes.

Contract basis: Purple-Billboard SPEC.md "## Booking, handoff and outcomes" --
"Use actual approved calendar capacity, recheck at commit and claim booked only
with a real receipt. Confirm timezone/location/change path; follow the approved
service process for reschedule/no-show/fulfillment. ... Sales/attendance/service
outcomes need authoritative or labeled owner evidence. Track the full funnel and
preserve keyword/multi-touch/unknown attribution instead of inventing exact post
causality." Plus T-12's durable runtime contract (DATA-CONTRACTS section 4).

What this module refuses to do, by construction:

  * invent a slot        - every offered and every booked slot came from a live
                           availability read, and each offered slot is re-verified
                           free before it is shown;
  * book on a stale read  - the exact slot is re-queried immediately before the
                           provider write; a taken slot refuses, it never books;
  * claim booked          - a booking is CLAIMED only when the provider returned a
                           complete confirmation receipt. Admission, confirmation
                           and the booking receipt are three separate durable
                           receipts (dispatch / ack / completion, T-12 semantics);
  * guess an outcome      - attendance and sale exist only from an authoritative
                           provider read or a named owner's labelled evidence.
                           "Booked" never implies "attended"; "attended" never
                           implies "sold";
  * invent attribution    - keyword, multi-touch and unknown are preserved, and
                           exact post-hoc causality is never asserted.

Reuse (accepted upstream, T-12, commit a2d8b3720 on main):

    38-conversational-ai-system/tools/durable_store.py

The durable store supplies the action identity, the idempotency key uniqueness,
the dispatch lease/fence, and the three-receipt ladder. This module adds only the
booking-specific vocabulary and the live calendar reads. `outbound_gate.dispatch`
is deliberately NOT used for the appointment write: its verdict vocabulary
(SUPPRESSED / QUARANTINED / WAIT_UNTIL) is message-policy, not calendar
availability, and no message is sent here. Confirmation delivery is a separate
person-directed action and passes that gate on its own (T-12).

Python 3 standard library only. No network IO in this module: the calendar and
provider are injected and are the caller's real adapter.

Import:

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared-utils
    from booking import BookingFollowThrough, BookingPolicy, Slot

Assert-based self-check:  python3 -I followthrough.py
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, FrozenSet, Iterable, List, Mapping, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# ── reuse the accepted T-12 durable runtime ────────────────────────────────
# Repo layout:      <repo>/shared-utils/booking/followthrough.py
# Installed layout: <skills>/shared-utils/booking/followthrough.py
# Both put Skill 38's tools two levels up, next to shared-utils.
_SKILL38_TOOLS = Path(
    os.environ.get("PB_SKILL38_TOOLS")
    or (Path(__file__).resolve().parents[2] / "38-conversational-ai-system" / "tools")
)
if not (_SKILL38_TOOLS / "durable_store.py").is_file():
    raise ImportError(
        "booking.followthrough needs the accepted T-12 durable runtime at "
        f"{_SKILL38_TOOLS}/durable_store.py (38-conversational-ai-system/tools). "
        "Set PB_SKILL38_TOOLS to that tools directory."
    )
if str(_SKILL38_TOOLS) not in sys.path:
    sys.path.insert(0, str(_SKILL38_TOOLS))

from durable_store import (  # noqa: E402  (path set above)
    DurableStore,
    DurableStoreError,
    STATE_COMPLETED,
    STATE_NOT_REQUESTED,
    STATE_UNKNOWN,
)

SCHEMA = "skill38.booking.followthrough.v1"

# ── refusal vocabulary (each one is a proven stop, never a soft warning) ───
R_CALENDAR_UNMAPPED = "CALENDAR_UNMAPPED"
R_CALENDAR_UNAVAILABLE = "CALENDAR_UNAVAILABLE"
R_NAIVE_DATETIME = "NAIVE_DATETIME"
R_UNKNOWN_TIMEZONE = "UNKNOWN_TIMEZONE"
R_BAD_SLOT = "BAD_SLOT"
R_NO_EXPLICIT_YES = "NO_EXPLICIT_YES"
R_SLOT_TAKEN = "SLOT_TAKEN"
R_BOOKING_NOT_PRESENT = "BOOKING_NOT_PRESENT"
R_OUTSIDE_POLICY = "OUTSIDE_POLICY"
R_INTENT_TERMINAL = "INTENT_TERMINAL"
R_NO_BOOKING = "NO_BOOKING"
R_NO_EVIDENCE_SOURCE = "NO_EVIDENCE_SOURCE"
R_NO_AUTHORITATIVE_SOURCE = "NO_AUTHORITATIVE_SOURCE"
R_BAD_EVIDENCE_SOURCE = "BAD_EVIDENCE_SOURCE"
R_CONTENT_MISMATCH = "CONTENT_MISMATCH"

# Offer stages. Mirrors the booking playbook's decline ladder.
STAGE_INITIAL = "initial"
STAGE_DECLINE_1 = "decline_1"
STAGE_DECLINE_2 = "decline_2"
STAGE_BEYOND_WINDOW = "beyond_window"
STAGE_WAITLIST = "waitlist"
STAGE_ESCALATE = "escalate"

# Outcome vocabulary and how it may be evidenced.
OUTCOME_KINDS = (
    "attended", "no_show", "sold", "not_sold", "service_delivered",
    "service_failed",
)
EVIDENCE_PROVIDER = "provider_verified"
EVIDENCE_OWNER = "owner_labeled"
OUTCOME_VERIFIED = "verified"
OUTCOME_LABELED = "owner_labeled"
OUTCOME_CONTRADICTED = "contradicted"
OUTCOME_UNVERIFIED = "unverified"

# Terminal states where the intent can never run again.
_TERMINAL_INTENT_STATES = frozenset({
    "canceled", "failed", "suppressed", "quarantined", "completed",
})


class Refusal(ValueError):
    """A proven refusal. Callers branch on `.code`; nothing was booked."""

    def __init__(self, code: str, reason: str = "") -> None:
        self.code = code
        self.reason = reason
        super().__init__(f"{code}: {reason}" if reason else code)


# ── value objects ──────────────────────────────────────────────────────────

def _tz(name: str) -> ZoneInfo:
    if not isinstance(name, str) or not name.strip():
        raise Refusal(R_UNKNOWN_TIMEZONE, "timezone name required")
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise Refusal(R_UNKNOWN_TIMEZONE, f"{name!r} is not an IANA zone") from exc


def _long_date(value: datetime) -> str:
    """Portable long date (no %-d: that is glibc/macOS only)."""
    return f"{value.strftime('%A, %B')} {value.day}, {value.year}"


def _clock(value: datetime) -> str:
    """Portable 12-hour local label with the zone abbreviation."""
    hour = value.hour % 12 or 12
    suffix = "AM" if value.hour < 12 else "PM"
    return f"{hour}:{value.minute:02d} {suffix} {value.tzname()}"


def _require_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise Refusal(R_BAD_SLOT, f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise Refusal(
            R_NAIVE_DATETIME,
            f"{field_name} must be timezone-aware; a wall-clock datetime has no "
            "provable instant",
        )


@dataclass(frozen=True)
class Slot:
    """One real calendar slot. Both instants are aware and carry an IANA zone."""

    start: datetime
    end: datetime
    calendar_id: str

    def __post_init__(self) -> None:
        _require_aware(self.start, "slot.start")
        _require_aware(self.end, "slot.end")
        if self.end <= self.start:
            raise Refusal(R_BAD_SLOT, "slot.end must be after slot.start")
        if not self.calendar_id:
            raise Refusal(R_BAD_SLOT, "slot.calendar_id required")
        _tz(self.timezone)

    @property
    def timezone(self) -> str:
        key = getattr(self.start.tzinfo, "key", None)
        if not key:
            raise Refusal(
                R_UNKNOWN_TIMEZONE,
                "slot.start must carry an IANA zone, not a fixed offset",
            )
        return key

    @property
    def start_utc(self) -> datetime:
        return self.start.astimezone(timezone.utc)

    def local(self, tz_name: str) -> datetime:
        return self.start.astimezone(_tz(tz_name))

    def instant_key(self) -> str:
        return self.start_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    def fingerprint(self) -> str:
        """Stable content hash: the same real instant is the same intent."""
        raw = "|".join((self.calendar_id, self.instant_key(),
                        self.end.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class BookingPolicy:
    """Operator-authored location rules. Never hardcoded, never guessed."""

    calendars: Mapping[str, str]          # purpose -> calendar id; needs "default"
    timezone: str                         # the location's IANA zone
    location: str                         # service location or meeting link
    change_path: str                      # how a customer changes or cancels
    max_window_days: int
    min_lead_hours: float
    daily_cap: Optional[int] = None
    excluded_weekdays: FrozenSet[int] = frozenset()
    excluded_hours: Tuple[Tuple[int, int], ...] = ()
    offer_next_available_beyond_window: bool = False
    offer_waitlist: bool = False
    max_declines: int = 3
    prefer_first_72h: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.calendars, Mapping) or "default" not in self.calendars:
            raise Refusal(
                R_CALENDAR_UNMAPPED,
                "calendar map has no 'default'; an unmapped purpose has nowhere "
                "to go and that is a build failure, not a runtime guess",
            )
        _tz(self.timezone)
        for name, value in (("location", self.location),
                            ("change_path", self.change_path),
                            ("default calendar id", self.calendars.get("default"))):
            if not isinstance(value, str) or not value.strip():
                raise Refusal(R_BAD_SLOT, f"policy.{name} must be configured")
        if self.max_window_days <= 0:
            raise Refusal(R_BAD_SLOT, "policy.max_window_days must be > 0")
        if self.min_lead_hours < 0:
            raise Refusal(R_BAD_SLOT, "policy.min_lead_hours must be >= 0")
        if self.daily_cap is not None and self.daily_cap < 1:
            raise Refusal(R_BAD_SLOT, "policy.daily_cap must be >= 1 or None")
        if self.max_declines < 1:
            raise Refusal(R_BAD_SLOT, "policy.max_declines must be >= 1")


@dataclass(frozen=True)
class Offer:
    calendar_id: str
    slots: Tuple[Slot, ...]
    stage: str
    escalate: bool
    message: str


@dataclass(frozen=True)
class Booking:
    action_id: str
    claimed: bool
    state: str
    slot: Slot
    provider_booking_id: Optional[str] = None
    receipt: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""


@dataclass(frozen=True)
class Outcome:
    booking_action_id: str
    kind: str
    state: str
    source: str
    evidence_id: Optional[str] = None
    note: str = ""


@dataclass(frozen=True)
class Attribution:
    basis: str                 # keyword | multi_touch | unknown
    keyword: Optional[str]
    touches: Tuple[str, ...]
    exact_causality: bool = False


# ── the adapter ────────────────────────────────────────────────────────────

class BookingFollowThrough:
    """Booking writes, changes and follow-through over a real calendar adapter.

    `availability` must implement:

        free_slots(calendar_id, window_start, window_end) -> Sequence[Slot]
        is_free(calendar_id, slot) -> bool                 # the commit recheck
        booked_count(calendar_id, day: date) -> int        # only when daily_cap set

    `booked_count` answers the number of bookings the calendar holds on that
    day, whether or not one of them is the booking being changed. Which of the
    two readings an adapter implements is not assumed anywhere: it is measured
    around this module's own create and remembered with the receipt
    (`_counted_self`, `booked_count_includes_self`), and the same-day change
    path subtracts its own place only when that measurement says the count
    holds it. A count that cannot be measured is counted in full - it can
    refuse a move, never overbook a day.

    `provider` must implement:

        provider_name: str
        authoritative_outcome_kinds: FrozenSet[str]
        create(*, slot, contact_id, idempotency_key) -> Mapping
        move(*, provider_booking_id, slot, idempotency_key) -> Mapping
        cancel(*, provider_booking_id, idempotency_key) -> Mapping
        verify_outcome(*, provider_booking_id, kind) -> Optional[bool]

    A provider receipt is complete only with `provider`, `provider_receipt_id`,
    `provider_booking_id`, `confirmed_at` and `evidence_id`. An incomplete
    receipt is never promoted to "booked".
    """

    def __init__(self, *, store: DurableStore, availability: Any, provider: Any,
                 policy: BookingPolicy, tenant_id: str,
                 worker_id: str = "booking-worker") -> None:
        if not isinstance(policy, BookingPolicy):
            raise Refusal(R_BAD_SLOT, "policy must be a BookingPolicy")
        if not tenant_id:
            raise Refusal(R_BAD_SLOT, "tenant_id required")
        self.store = store
        self.availability = availability
        self.provider = provider
        self.policy = policy
        self.tenant_id = tenant_id
        self.worker_id = worker_id
        self._intent_notes: Dict[str, str] = {}
        self._supersedes: Dict[str, str] = {}

    # ── routing (operator map only) ────────────────────────────────────

    def resolve_calendar(self, purpose: Optional[str]) -> str:
        """Exact purpose key first, then default. No customer input here."""
        key = (purpose or "").strip().lower()
        calendars = self.policy.calendars
        if key and key != "default" and key in calendars:
            return calendars[key]
        default = calendars.get("default")
        if not default:
            raise Refusal(R_CALENDAR_UNMAPPED, "no 'default' calendar configured")
        return default

    # ── availability ───────────────────────────────────────────────────

    def _window(self, now: datetime) -> Tuple[datetime, datetime]:
        _require_aware(now, "now")
        start = now + timedelta(hours=self.policy.min_lead_hours)
        end = now + timedelta(days=self.policy.max_window_days)
        return start, end

    def _read_free(self, calendar_id: str, start: datetime,
                   end: datetime) -> List[Slot]:
        try:
            raw = self.availability.free_slots(calendar_id, start, end)
        except Exception as exc:
            raise Refusal(
                R_CALENDAR_UNAVAILABLE,
                f"availability read failed ({type(exc).__name__}); booking is "
                "unavailable and must be escalated, never promised",
            ) from exc
        if raw is None:
            raise Refusal(R_CALENDAR_UNAVAILABLE,
                          "availability read returned nothing provable")
        return list(raw)

    def _verify_free(self, calendar_id: str, slot: Slot) -> bool:
        try:
            return bool(self.availability.is_free(calendar_id, slot))
        except Exception as exc:
            raise Refusal(
                R_CALENDAR_UNAVAILABLE,
                f"free/busy verification failed ({type(exc).__name__})",
            ) from exc

    def _excluded(self, slot: Slot) -> bool:
        local = slot.local(self.policy.timezone)
        if local.weekday() in self.policy.excluded_weekdays:
            return True
        for first, last in self.policy.excluded_hours:
            if first <= last:
                if first <= local.hour < last:
                    return True
            elif local.hour >= first or local.hour < last:  # overnight range
                return True
        return False

    def _has_daily_capacity(self, calendar_id: str, slot: Slot,
                            already_counted: int = 0) -> bool:
        """`already_counted`: bookings in the day's count that leave the day
        when this one lands (a same-day move vacates its own place)."""
        cap = self.policy.daily_cap
        if cap is None:
            return True
        day = slot.local(self.policy.timezone).date()
        try:
            booked = self.availability.booked_count(calendar_id, day)
        except Exception as exc:
            raise Refusal(
                R_CALENDAR_UNAVAILABLE,
                f"daily cap needs a real booked count ({type(exc).__name__}); "
                "refusing to guess remaining capacity",
            ) from exc
        return int(booked) - already_counted < cap

    def _acceptable(self, calendar_id: str, slot: Slot, start: datetime,
                    end: datetime) -> bool:
        if slot.calendar_id != calendar_id:
            return False
        if slot.start < start or slot.end > end:
            return False
        if self._excluded(slot):
            return False
        if not self._has_daily_capacity(calendar_id, slot):
            return False
        return self._verify_free(calendar_id, slot)

    def offer_slots(self, purpose: Optional[str], *, now: datetime,
                    declines: int = 0,
                    preference: str = "any") -> Offer:
        """Offer only real, verified-free slots from the live calendar."""
        if declines < 0:
            raise Refusal(R_BAD_SLOT, "declines must be >= 0")
        calendar_id = self.resolve_calendar(purpose)
        if declines >= self.policy.max_declines:
            return Offer(calendar_id, (), STAGE_ESCALATE, True,
                         self._escalate_message(purpose))

        start, end = self._window(now)
        free = self._read_free(calendar_id, start, end)
        candidates = [s for s in free if self._acceptable(calendar_id, s, start, end)]
        candidates.sort(key=lambda s: s.start)

        chosen = self._shape(candidates, declines, preference)
        if chosen:
            stage = (STAGE_INITIAL if declines == 0 else
                     STAGE_DECLINE_1 if declines == 1 else STAGE_DECLINE_2)
            return Offer(calendar_id, tuple(chosen), stage, False,
                         self._offer_message(chosen))

        # Nothing in the window: the configured no-availability path only.
        # Beyond the window is not outside the policy: the same bounds hold,
        # so nothing past and nothing inside the min-lead floor is offered.
        if self.policy.offer_next_available_beyond_window:
            beyond_end = end + timedelta(days=self.policy.max_window_days)
            beyond = [
                s for s in self._read_free(calendar_id, end, beyond_end)
                if self._acceptable(calendar_id, s, end, beyond_end)
                and s.start >= start
            ]
            beyond.sort(key=lambda s: s.start)
            if beyond:
                return Offer(calendar_id, (beyond[0],), STAGE_BEYOND_WINDOW,
                             False, self._offer_message(beyond[:1]))
        if self.policy.offer_waitlist:
            return Offer(calendar_id, (), STAGE_WAITLIST, False,
                         "I'm fully booked in that window. I can put you on the "
                         "waitlist and message you first if anything opens up. "
                         "Would you like that?")
        return Offer(calendar_id, (), STAGE_ESCALATE, True,
                     self._escalate_message(purpose))

    def _shape(self, candidates: Sequence[Slot], declines: int,
               preference: str) -> List[Slot]:
        pool = list(candidates)
        pref = (preference or "any").strip().lower()
        if pref in ("morning", "afternoon", "evening"):
            bounds = {"morning": (0, 12), "afternoon": (12, 17),
                      "evening": (17, 24)}[pref]
            matching = [s for s in pool
                        if bounds[0] <= s.local(self.policy.timezone).hour < bounds[1]]
            pool = matching or pool  # preference shapes order, never invents

        if self.policy.prefer_first_72h and declines == 0 and pool:
            horizon = pool[0].start + timedelta(days=3)
            soon = [s for s in pool if s.start <= horizon]
            pool = soon or pool

        distinct: List[Slot] = []
        seen_days = set()
        for slot in pool:
            day = slot.local(self.policy.timezone).date()
            if day in seen_days:
                continue
            seen_days.add(day)
            distinct.append(slot)

        if declines >= 2:
            return pool[-1:]        # one wider-range slot, then hand off
        return distinct[:3]         # two or three real slots, different days

    # ── booking (recheck at commit, claim only with a receipt) ─────────

    def book(self, *, purpose: Optional[str], slot: Slot, contact_id: str,
             confirmed: bool, now: datetime,
             intent_note: str = "") -> Booking:
        if not confirmed:
            raise Refusal(
                R_NO_EXPLICIT_YES,
                "restate purpose/date/time/timezone and book only after an "
                "explicit yes",
            )
        if not contact_id:
            raise Refusal(R_BAD_SLOT, "contact_id required")
        _require_aware(now, "now")
        calendar_id = self.resolve_calendar(purpose)
        if slot.calendar_id != calendar_id:
            raise Refusal(
                R_CALENDAR_UNMAPPED,
                "slot predates routing: it is not on the resolved calendar",
            )
        if not self._within_policy(slot, now):
            raise Refusal(R_OUTSIDE_POLICY,
                          "slot is outside lead time, window or exclusions")
        if not self._has_daily_capacity(calendar_id, slot):
            raise Refusal(R_OUTSIDE_POLICY, "the daily cap is already reached")

        intent_key = self._intent_key("book", calendar_id, contact_id,
                                      slot, purpose)
        action_id, created = self._intent(intent_key, slot, contact_id, purpose,
                                          intent_note)
        existing = self.store.get_action(action_id)
        if not created and existing["state"] == STATE_COMPLETED:
            return self._replay_completed(action_id, slot)

        return self._commit(
            action_id=action_id,
            slot=slot,
            recheck=lambda: self._verify_free(calendar_id, slot),
            write=lambda idem: self.provider.create(
                slot=slot, contact_id=contact_id, idempotency_key=idem),
            force_unconfirmed=(not created and existing["state"] == STATE_UNKNOWN),
        )

    def _within_policy(self, slot: Slot, now: datetime) -> bool:
        start, end = self._window(now)
        return (start <= slot.start and slot.end <= end
                and not self._excluded(slot))

    def _commit(self, *, action_id: str, slot: Slot, recheck: Any, write: Any,
                force_unconfirmed: bool = False,
                failure_code: str = R_SLOT_TAKEN,
                counted_self: Optional[bool] = None) -> Booking:
        """Recheck the exact slot, then write once inside a fenced attempt."""
        state = self.store.get_action(action_id)["state"]
        if state in _TERMINAL_INTENT_STATES:
            raise Refusal(R_INTENT_TERMINAL, f"intent is {state}")
        if force_unconfirmed:
            return Booking(action_id, False, STATE_UNKNOWN, slot,
                           reason="prior attempt is unknown; reconcile before retry")

        if state == STATE_NOT_REQUESTED:
            self.store.queue(action_id)
        claim = self.store.claim_for_dispatch(action_id, self.worker_id)
        if claim is None:
            row = self.store.get_action(action_id)
            return Booking(action_id, False, row["state"], slot,
                           reason="no lease: not queued, deferred or unresolved")
        fence = int(claim["fence"])

        # THE RECHECK: a fresh live read microseconds before the write.
        try:
            still_valid = bool(recheck())
        except Refusal:
            self.store.release_lease(action_id, fence)
            raise
        if not still_valid:
            self.store.release_lease(action_id, fence)
            self.store.cancel(action_id, failure_code)
            raise Refusal(
                failure_code,
                "the commit recheck failed: the slot is not free, or the "
                "booking it would change is not on the calendar; nothing ran")

        if not self.store.begin_attempt(action_id, fence, self.worker_id):
            return Booking(action_id, False, self.store.get_action(action_id)["state"],
                           slot, reason="canceled or lease lost; nothing was written")

        day_count_before = self._day_count(slot)
        try:
            receipt = write(self._idempotency_key(action_id))
        except Exception as exc:
            self.store.mark_attempt_unknown(
                action_id, fence,
                f"provider_exception:{type(exc).__name__}:{exc}")
            return Booking(action_id, False, STATE_UNKNOWN, slot,
                           reason="provider raised before a verdict; unknown")
        if not self._receipt_complete(receipt):
            self.store.mark_attempt_unknown(action_id, fence,
                                            "incomplete_provider_receipt")
            return Booking(action_id, False, STATE_UNKNOWN, slot,
                           reason="provider did not return a complete receipt")
        if counted_self is None:
            counted_self = self._counted_self(day_count_before, slot)
        receipt = self._enrich(receipt, slot, counted_self)

        # Admission, confirmation and the booking receipt are three states.
        self.store.record_dispatch(action_id, fence, dict(receipt))
        self.store.record_ack(action_id, dict(receipt))
        self.store.record_completion(action_id, dict(receipt))
        row = self.store.get_action(action_id)
        return Booking(
            action_id=action_id,
            claimed=(row["state"] == STATE_COMPLETED),
            state=row["state"],
            slot=slot,
            provider_booking_id=str(receipt["provider_booking_id"]),
            receipt=dict(receipt),
        )

    # ── change path ────────────────────────────────────────────────────

    def reschedule(self, *, booking_action_id: str, new_slot: Slot,
                   now: datetime) -> Booking:
        """Move a booked appointment; the old receipt stays authoritative offline."""
        prior = self._completion_receipt(booking_action_id)
        calendar_id = str(new_slot.calendar_id)
        if new_slot.calendar_id not in set(self.policy.calendars.values()):
            raise Refusal(R_CALENDAR_UNMAPPED,
                          "new slot is not on an operator-approved calendar")
        # The change path is held to the approved booking policy exactly as
        # book() is: lead time, window, exclusions and real daily capacity.
        if not self._within_policy(new_slot, now):
            raise Refusal(R_OUTSIDE_POLICY,
                          "new slot is outside lead time, window or exclusions")
        # A same-day move on the same calendar vacates one place and takes one,
        # so it is not counted against its own place - but only when the module
        # owns every link of that proof: the place it vacates is its own booked
        # slot (never a field the provider echoed), it still holds that place
        # (a cancelled booking holds none), and the day's count is known to hold
        # it. Anything less is counted in full: it can refuse, never overbook.
        same_day = int(self._vacates_a_place(prior["payload"], calendar_id,
                                             new_slot, booking_action_id))
        if not self._has_daily_capacity(calendar_id, new_slot,
                                        already_counted=same_day):
            raise Refusal(R_OUTSIDE_POLICY, "the daily cap is already reached")

        intent_key = self._intent_key("change", calendar_id,
                                      prior["payload"].get("canonical_contact_id") or "",
                                      new_slot, booking_action_id)
        action_id, created = self._intent(intent_key, new_slot,
                                          prior["payload"].get("canonical_contact_id"),
                                          "reschedule", "")
        existing = self.store.get_action(action_id)
        if not created and existing["state"] == STATE_COMPLETED:
            return self._replay_completed(action_id, new_slot)

        result = self._commit(
            action_id=action_id, slot=new_slot,
            recheck=lambda: self._verify_free(calendar_id, new_slot),
            write=lambda idem: self.provider.move(
                provider_booking_id=str(prior["payload"]["provider_booking_id"]),
                slot=new_slot, idempotency_key=idem),
            force_unconfirmed=(not created and existing["state"] == STATE_UNKNOWN),
            # whether the day's count holds this booking is a property of the
            # adapter, not of the day: carry the measurement made at its write.
            counted_self=bool(prior["payload"].get("booked_count_includes_self")),
        )
        if result.claimed:
            self._note_supersession(result.action_id, booking_action_id)
        return result

    def _occupies_day(self, payload: Mapping[str, Any], calendar_id: str,
                      slot: Slot) -> bool:
        """True when the booking sits on `slot`'s calendar and local day.

        "Sits" is read from the record this module wrote (`_booked_place`),
        never from the provider's echo of it alone, and the echo must not
        contradict that record. An unreadable, naive or contradicting claim is
        not proof of the same day, so the full count applies (the conservative
        side: it can refuse, never overbook).
        """
        tz_name = self.policy.timezone
        booked = self._booked_place(payload)
        if booked is None:
            return False
        if booked.calendar_id != calendar_id:
            return False
        if booked.local(tz_name).date() != slot.local(tz_name).date():
            return False
        return self._echo_agrees(payload, booked, tz_name)

    def _aware(self, value: Any, tz_name: str) -> Optional[datetime]:
        """`value` as an aware datetime in `tz_name`, or None when it is not
        proof of one. A naive stamp is not a time, and unreadable is not a day."""
        if not isinstance(value, str) or not value:
            return None
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(_tz(tz_name))

    def _booked_place(self, payload: Mapping[str, Any]) -> Optional[Slot]:
        """The slot this module booked, from the record it wrote itself.

        `booked_start`/`booked_end`/`booked_calendar_id` come from `_enrich`,
        which writes the slot this module was asked to book. The provider
        receipt's own `start`/`end`/`calendar_id` are that provider's echo and
        are never read back as the booking's place: a receipt can claim any day
        it likes. For a receipt written before that record existed, the echo is
        the only description there is, so it is used only when it is readable,
        aware and self-consistent.
        """
        tz_name = self.policy.timezone
        if payload.get("booked_start"):
            start = self._aware(payload.get("booked_start"), tz_name)
            end = self._aware(payload.get("booked_end"), tz_name)
            if start is None or end is None:
                return None
            place = (start, end, str(payload.get("booked_calendar_id") or ""))
        else:
            if not (payload.get("start") and payload.get("end")
                    and payload.get("calendar_id")):
                return None
            start = self._aware(payload.get("start"), tz_name)
            end = self._aware(payload.get("end"), tz_name)
            if start is None or end is None:
                return None
            place = (start, end, str(payload.get("calendar_id") or ""))
        try:
            return Slot(start=place[0], end=place[1], calendar_id=place[2])
        except Refusal:
            return None

    def _echo_agrees(self, payload: Mapping[str, Any], booked: Slot,
                     tz_name: str) -> bool:
        """The provider's own claim must not contradict the record this module
        wrote. A claim of another day, or one that cannot be read as a day, is
        not proof that the booking is where the record says: the full count
        applies."""
        if "start" in payload:
            day = self._aware(payload.get("start"), tz_name)
            if day is None or day.date() != booked.local(tz_name).date():
                return False
        if "calendar_id" in payload:
            if str(payload.get("calendar_id") or "") != booked.calendar_id:
                return False
        return True

    def _cancel_recorded(self, booking_action_id: str,
                         payload: Mapping[str, Any]) -> bool:
        """True when this module receipted a cancel for that booking.

        The intent key is rebuilt from the same place `cancel` acts on, so a
        cancel that really was receipted is found whatever else the record says.
        """
        place = self._booked_place(payload)
        if place is None:
            return False
        key = self._intent_key(
            "cancel", place.calendar_id,
            str(payload.get("canonical_contact_id") or ""), place,
            booking_action_id)
        try:
            row = self.store.action_by_intent(key)
        except DurableStoreError:
            return False
        return bool(row) and row.get("state") == STATE_COMPLETED

    def _vacates_a_place(self, payload: Mapping[str, Any], calendar_id: str,
                         slot: Slot, booking_action_id: str) -> bool:
        """True only on proof that this move frees a place in `slot`'s day.

        A move that frees no place takes a new one, so it is counted in full.
        Proof is three links after the day itself (`_occupies_day`), and each is
        the module's own to make: the booking still holds the place (a
        cancelled booking holds none - the same evidence `cancel` reads), the
        place really is taken (a free slot holds nothing to vacate), and the
        day's count is known to hold it (`booked_count_includes_self`,
        measured at the booking's own write rather than assumed from an
        adapter contract that never promised it). An unproven link is not proof.
        """
        if not self._occupies_day(payload, calendar_id, slot):
            return False
        if payload.get("booked_count_includes_self") is not True:
            return False
        if self._was_cancelled(booking_action_id):
            return False
        if self._cancel_recorded(booking_action_id, payload):
            return False
        booked = self._booked_place(payload)
        if booked is None:
            return False
        try:
            if self._verify_free(booked.calendar_id, booked):
                return False          # a free slot holds no place to vacate
        except Refusal:
            return False
        return True

    def cancel(self, *, booking_action_id: str, now: datetime,
               reason: str = "customer_request") -> Booking:
        prior = self._completion_receipt(booking_action_id)
        # The place to free is the slot this module booked. The provider's echo
        # of it is a claim, not a place: a receipt can date a booking anywhere.
        booked = self._booked_place(prior["payload"])
        if booked is None:
            raise Refusal(R_NO_BOOKING,
                          "the receipt does not say what was booked, so there "
                          "is no place proven to free")
        calendar_id = booked.calendar_id
        slot = booked
        contact = prior["payload"].get("canonical_contact_id")
        intent_key = self._intent_key("cancel", calendar_id, contact or "",
                                      slot, booking_action_id)
        action_id, created = self._intent(intent_key, slot, contact, "cancel",
                                          reason)
        existing = self.store.get_action(action_id)
        if not created and existing["state"] == STATE_COMPLETED:
            return self._replay_completed(action_id, slot)
        result = self._commit(
            action_id=action_id, slot=slot,
            # cancel only when the appointment really occupies the calendar;
            # a free slot means the booking is already gone, so reconcile.
            recheck=lambda: not self._verify_free(calendar_id, slot),
            write=lambda idem: self.provider.cancel(
                provider_booking_id=str(prior["payload"]["provider_booking_id"]),
                idempotency_key=idem),
            force_unconfirmed=(not created and existing["state"] == STATE_UNKNOWN),
            failure_code=R_BOOKING_NOT_PRESENT,
        )
        if result.claimed:
            self._record_cancellation(booking_action_id)
        return result

    def _record_cancellation(self, booking_action_id: str) -> None:
        """Record, on the booking's own action, that it was cancelled.

        The cancel receipt is its own action; without this the booking would
        still read as holding its place, and a change path could move a booking
        that no longer holds one. It is an observation in the store's
        append-only log - the same durable record outcomes use - so it never
        moves the booking action through its own state machine and never
        touches the old receipt, which stays authoritative offline.
        """
        try:
            self.store.record_reconciliation(
                booking_action_id, "cancelled",
                {"record": "booking_cancellation", "schema": SCHEMA})
        except DurableStoreError:
            pass      # the cancel itself is receipted; the marker is best effort

    def _was_cancelled(self, booking_action_id: str) -> bool:
        for run in self.store.reconciliation_runs(booking_action_id):
            try:
                evidence = json.loads(run["evidence_json"])
            except (TypeError, ValueError):
                continue
            if evidence.get("record") == "booking_cancellation":
                return True
        return False

    # ── outcomes: authoritative or labelled, never guessed ─────────────

    def record_outcome(self, *, booking_action_id: str, kind: str, source: str,
                       evidence_id: Optional[str] = None,
                       owner: Optional[str] = None) -> Outcome:
        if kind not in OUTCOME_KINDS:
            raise Refusal(R_BAD_EVIDENCE_SOURCE, f"{kind!r} is not an outcome")
        receipt = self._completion_receipt(booking_action_id)
        booking_id = str(receipt["payload"]["provider_booking_id"])

        if source == EVIDENCE_PROVIDER:
            if kind not in getattr(self.provider, "authoritative_outcome_kinds",
                                  frozenset()):
                raise Refusal(
                    R_NO_AUTHORITATIVE_SOURCE,
                    f"{type(self.provider).__name__} is not an authoritative "
                    f"source for {kind}; use labelled owner evidence",
                )
            if not evidence_id:
                raise Refusal(R_NO_EVIDENCE_SOURCE,
                              "provider-verified outcome needs an evidence id")
            try:
                observed = self.provider.verify_outcome(
                    provider_booking_id=booking_id, kind=kind)
            except Exception:
                observed = None       # unreadable is unverified, not a guess
            if observed is True:
                return self._persist_outcome(
                    Outcome(booking_action_id, kind, OUTCOME_VERIFIED,
                            source, evidence_id))
            if observed is False:
                return self._persist_outcome(
                    Outcome(booking_action_id, kind, OUTCOME_CONTRADICTED,
                            source, evidence_id,
                            note="provider says the opposite"))
            return self._persist_outcome(
                Outcome(booking_action_id, kind, OUTCOME_UNVERIFIED, source,
                        evidence_id, note="provider could not confirm"))

        if source == EVIDENCE_OWNER:
            if not owner or not evidence_id:
                raise Refusal(
                    R_NO_EVIDENCE_SOURCE,
                    "labelled owner evidence needs the owner and an evidence id",
                )
            return self._persist_outcome(
                Outcome(booking_action_id, kind, OUTCOME_LABELED, source,
                        evidence_id, note=f"labelled by {owner}"))

        raise Refusal(R_BAD_EVIDENCE_SOURCE,
                      f"{source!r} is neither provider_verified nor owner_labeled")

    def _persist_outcome(self, outcome: Outcome) -> Outcome:
        """Write the observed outcome where it is durable and readable.

        The T-12 store's append-only observation log (the reconciliation runs)
        is where a fact observed about an action is recorded; it never moves the
        booking action through its own state machine.
        """
        self.store.record_reconciliation(
            outcome.booking_action_id,
            outcome.state,
            {"record": "booking_outcome", "schema": SCHEMA,
             "kind": outcome.kind, "source": outcome.source,
             "evidence_id": outcome.evidence_id, "note": outcome.note},
        )
        return outcome

    def outcome_state(self, booking_action_id: str) -> str:
        """What was last recorded about this booking's outcome.

        A booking by itself proves nothing about attendance or sale: with no
        recorded outcome this reads "unverified", and a recorded but
        unconfirmable check reads the same. What it never does is forget a
        verified or owner-labelled outcome.
        """
        # ponytail: this reads one state per booking -- the last outcome
        # recorded. Rows already carry their kind, so when one booking must be
        # read for attendance and sale apart, add a kind filter here.
        recorded = None
        for run in self.store.reconciliation_runs(booking_action_id):
            try:
                evidence = json.loads(run["evidence_json"])
            except (TypeError, ValueError):
                continue
            if evidence.get("record") != "booking_outcome":
                continue      # another subsystem's row in the same log
            recorded = run["outcome"]
        return recorded or OUTCOME_UNVERIFIED

    def attribute(self, *, keyword: Optional[str] = None,
                  touches: Iterable[str] = ()) -> Attribution:
        """Preserve keyword / multi-touch / unknown. Never invent causality."""
        clean = tuple(t for t in touches if t)
        if len(clean) > 1:
            basis = "multi_touch"
        elif keyword:
            basis = "keyword"
        elif clean:
            basis = "keyword"
        else:
            basis = "unknown"
        return Attribution(basis=basis, keyword=keyword or None,
                           touches=clean, exact_causality=False)

    # ── confirmation text ──────────────────────────────────────────────

    def confirmation_text(self, booking: Booking) -> str:
        if not booking.claimed:
            raise Refusal(R_NO_BOOKING,
                          "no booking receipt exists; nothing to confirm")
        local = booking.slot.local(self.policy.timezone)
        return (f"You're booked for {_long_date(local)} at {_clock(local)} "
                f"({self.policy.timezone}) at {self.policy.location}. "
                f"To change or cancel: {self.policy.change_path}.")

    # ── internals ──────────────────────────────────────────────────────

    def _intent_key(self, verb: str, calendar_id: str, contact_id: str,
                    slot: Slot, purpose: Optional[str]) -> str:
        # Identity is the whole slot (calendar + start + end), not its start:
        # two durations at the same start are two different bookings.
        return "|".join(("booking", self.tenant_id, verb, calendar_id,
                         contact_id, slot.fingerprint(),
                         (purpose or "default").strip().lower()))

    def _intent(self, intent_key: str, slot: Slot, contact_id: Optional[str],
                purpose: Optional[str], note: str) -> Tuple[str, bool]:
        if not contact_id:
            raise Refusal(R_BAD_SLOT,
                          "a booking intent needs a canonical contact id")
        try:
            row, created = self.store.create_intent(
                logical_intent_key=intent_key,
                idempotency_key=self._idempotency_key(intent_key),
                tenant_id=self.tenant_id,
                scope="person_directed",
                canonical_contact_id=contact_id,
                content_sha256=slot.fingerprint(),
                purpose=(purpose or "default"),
            )
        except DurableStoreError as exc:
            raise Refusal(R_INTENT_TERMINAL, str(exc)) from exc
        if note:
            self._intent_notes[row["action_id"]] = note
        return str(row["action_id"]), created

    def _day_count(self, slot: Slot) -> Optional[int]:
        """The day's real count, or None when it cannot be read.

        Only meaningful with a daily cap: an adapter without one need not
        answer `booked_count` at all. An unreadable count is never guessed.
        """
        if self.policy.daily_cap is None:
            return None
        try:
            return int(self.availability.booked_count(
                slot.calendar_id, slot.local(self.policy.timezone).date()))
        except Exception:                              # noqa: BLE001
            return None

    def _counted_self(self, before: Optional[int], slot: Slot) -> bool:
        """Did this module's own write land in the day's count?

        `booked_count` may or may not hold the booking being changed - the
        adapter contract does not say. It is measured here, around this
        module's own write, instead of assumed: when the count did not move
        for a booking this module just wrote, it does not hold such bookings,
        and the change path must never subtract one. Unreadable is not proof.
        """
        after = self._day_count(slot)
        return before is not None and after is not None and after > before

    def _enrich(self, receipt: Mapping[str, Any], slot: Slot,
                counted_self: Optional[bool] = None) -> Dict[str, Any]:
        """Persist the canonical booking record beside the provider receipt.

        `start`/`end`/`calendar_id` stay as the provider receipt carried them
        (this module fills only what the receipt left out), because that echo
        is the receipt's own claim. What this module BOOKED is written beside
        it in `booked_*`, from the slot this module was asked to book - never
        from anything the provider said back. The capacity guard reads the
        module's own record; the echo is corroboration and cannot buy an
        exclusion on its own.
        """
        record = dict(receipt)
        record.setdefault("start", slot.start.isoformat())
        record.setdefault("end", slot.end.isoformat())
        record.setdefault("calendar_id", slot.calendar_id)
        record.setdefault("timezone", slot.timezone)
        record.setdefault("location", self.policy.location)
        record.setdefault("change_path", self.policy.change_path)
        record["booked_start"] = slot.start.isoformat()
        record["booked_end"] = slot.end.isoformat()
        record["booked_calendar_id"] = slot.calendar_id
        record["booked_count_includes_self"] = bool(counted_self)
        return record

    @staticmethod
    def _idempotency_key(source: str) -> str:
        return "bk_" + hashlib.sha256(source.encode("utf-8")).hexdigest()

    def _receipt_complete(self, receipt: Any) -> bool:
        return (isinstance(receipt, Mapping)
                and all(receipt.get(k) for k in
                        ("provider", "provider_receipt_id",
                         "provider_booking_id", "confirmed_at", "evidence_id")))

    def _completion_receipt(self, action_id: str) -> Dict[str, Any]:
        receipts = self.store.receipts(action_id)
        completion = receipts.get("completion")
        if completion is None:
            raise Refusal(R_NO_BOOKING,
                          f"{action_id} has no booking receipt")
        payload = dict(completion["payload"])
        action = self.store.get_action(action_id)
        payload.setdefault("canonical_contact_id",
                           action["canonical_contact_id"])
        payload.setdefault("purpose", action["purpose"])
        return {"payload": payload, "row": completion}

    def _replay_completed(self, action_id: str, slot: Slot) -> Booking:
        # Replay is a replay only when the stored content is this slot. A
        # differing slot never claims booked on another slot's receipt.
        stored = self.store.get_action(action_id).get("content_sha256")
        if stored and stored != slot.fingerprint():
            raise Refusal(
                R_CONTENT_MISMATCH,
                "the intent on file was completed for a different slot, so its "
                "receipt does not describe this booking")
        payload = self._completion_receipt(action_id)["payload"]
        return Booking(action_id=action_id, claimed=True, state=STATE_COMPLETED,
                       slot=slot,
                       provider_booking_id=str(payload["provider_booking_id"]),
                       receipt=payload)

    def _note_supersession(self, new_action_id: str, old_action_id: str) -> None:
        self._supersedes[new_action_id] = old_action_id

    def supersedes(self, action_id: str) -> Optional[str]:
        return self._supersedes.get(action_id)

    def _offer_message(self, slots: Sequence[Slot]) -> str:
        lines = []
        for slot in slots:
            local = slot.local(self.policy.timezone)
            lines.append("  - " + f"{_long_date(local)} at {_clock(local)}"
                         + f" ({self.policy.timezone})")
        return "I have these open times:\n" + "\n".join(lines) + \
               "\n\nWhich works best?"

    def _escalate_message(self, purpose: Optional[str]) -> str:
        return ("I don't want to promise a time I can't keep. I'll have the "
                "operator reach out directly to find a time with you.")


# ── assert-based self-check (stdlib only) ──────────────────────────────────

def _selfcheck() -> int:
    import tempfile

    passed = 0

    def ok(cond: bool, label: str) -> None:
        nonlocal passed
        if not cond:
            raise AssertionError("FAIL: " + label)
        passed += 1

    NY = ZoneInfo("America/New_York")
    now = datetime(2027, 5, 3, 9, 0, tzinfo=NY)
    slot = Slot(datetime(2027, 5, 5, 10, 0, tzinfo=NY),
                datetime(2027, 5, 5, 11, 0, tzinfo=NY), "CAL_A")

    class Avail:
        def __init__(self):
            self.free = [slot]
            self.checks = 0

        def free_slots(self, calendar_id, start, end):
            return [s for s in self.free if start <= s.start and s.end <= end]

        def is_free(self, calendar_id, candidate):
            self.checks += 1
            return candidate in self.free

        def booked_count(self, calendar_id, day):
            return 0

    class Provider:
        provider_name = "fake"
        authoritative_outcome_kinds = frozenset({"attended"})

        def __init__(self):
            self.creates = 0

        def create(self, *, slot, contact_id, idempotency_key):
            self.creates += 1
            return {"provider": "fake", "provider_receipt_id": "r1",
                    "provider_booking_id": "b1", "confirmed_at": "2027-05-03T13:05:00Z",
                    "evidence_id": "ev1", "start": slot.start.isoformat(),
                    "end": slot.end.isoformat(), "calendar_id": slot.calendar_id}

        def move(self, **_kw):
            raise AssertionError("not used")

        def cancel(self, **_kw):
            raise AssertionError("not used")

        def verify_outcome(self, *, provider_booking_id, kind):
            return True

    policy = BookingPolicy(calendars={"default": "CAL_A"},
                           timezone="America/New_York", location="12 Main St",
                           change_path="reply here", max_window_days=14,
                           min_lead_hours=2)
    work = Path(tempfile.mkdtemp(prefix="booking-selfcheck-"))
    store = DurableStore(str(work / "b.sqlite"))
    av = Avail()
    prov = Provider()
    eng = BookingFollowThrough(store=store, availability=av, provider=prov,
                               policy=policy, tenant_id="ten")

    offer = eng.offer_slots("consult", now=now)
    ok([s.instant_key() for s in offer.slots] == [slot.instant_key()],
       "only the real free slot is offered")

    booking = eng.book(purpose="consult", slot=slot, contact_id="c1",
                       confirmed=True, now=now)
    ok(booking.claimed and booking.provider_booking_id == "b1", "receipt claims booked")
    kinds = store.receipts(booking.action_id)
    ok({"dispatch", "ack", "completion"} <= set(kinds),
       "admission, confirmation and booking receipt are separate")
    ok("America/New_York" in eng.confirmation_text(booking), "confirmation states tz")

    again = eng.book(purpose="consult", slot=slot, contact_id="c1",
                     confirmed=True, now=now)
    ok(prov.creates == 1 and again.action_id == booking.action_id,
       "same intent never writes twice")

    try:
        eng.book(purpose="consult", slot=slot, contact_id="c1",
                 confirmed=False, now=now)
        ok(False, "unconfirmed booking refused")
    except Refusal as exc:
        ok(exc.code == R_NO_EXPLICIT_YES, "unconfirmed booking refused")

    ok(eng.outcome_state(booking.action_id) == OUTCOME_UNVERIFIED,
       "a booking proves nothing about attendance")

    store.close()
    print(f"OK {passed} PASS")
    return 0


if __name__ == "__main__":
    sys.exit(_selfcheck())
