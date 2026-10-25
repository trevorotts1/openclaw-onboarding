#!/usr/bin/env python3
"""T-28 acceptance tests: booking and service follow-through.

Every test pins one clause of SPEC.md "## Booking, handoff and outcomes" or
"## Runtime reliability and safety". Refusals are asserted by code, because a
refusal that is not proven to fire is not a refusal.

Run:  python3 -I -m unittest discover -s shared-utils/booking/tests
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # shared-utils

from booking import (  # noqa: E402
    BookingFollowThrough,
    BookingPolicy,
    Refusal,
    Slot,
    R_BAD_EVIDENCE_SOURCE,
    R_BOOKING_NOT_PRESENT,
    R_CALENDAR_UNAVAILABLE,
    R_CALENDAR_UNMAPPED,
    R_NO_AUTHORITATIVE_SOURCE,
    R_NO_BOOKING,
    R_NO_EVIDENCE_SOURCE,
    R_NO_EXPLICIT_YES,
    R_OUTSIDE_POLICY,
    R_SLOT_TAKEN,
    R_NAIVE_DATETIME,
    R_UNKNOWN_TIMEZONE,
)
from durable_store import DurableStore  # noqa: E402  (T-12 reuse, real store)

NY = ZoneInfo("America/New_York")
NOW = datetime(2027, 5, 3, 9, 0, tzinfo=NY)          # Monday
CAL_A = "CAL_A"
CAL_B = "CAL_B"


def slot(day=5, hour=10, calendar=CAL_A, minutes=0, tz=NY):
    start = datetime(2027, 5, day, hour, minutes, tzinfo=tz)
    return Slot(start, start + timedelta(hours=1), calendar)


def receipt(**over):
    base = {
        "provider": "fake-calendar",
        "provider_receipt_id": "pr_1",
        "provider_booking_id": "bk_1",
        "confirmed_at": "2027-05-03T13:05:00Z",
        "evidence_id": "ev_1",
    }
    base.update(over)
    return base


class FakeAvailability:
    """A live calendar read. It answers only from `free`, and can fail."""

    def __init__(self, free=()):
        self.free = list(free)
        self.reads = 0
        self.checks = 0
        self.fail = False
        self.booked = {}

    def free_slots(self, calendar_id, start, end):
        self.reads += 1
        if self.fail:
            raise RuntimeError("freeBusy unavailable")
        return [s for s in self.free
                if s.calendar_id == calendar_id and start <= s.start and s.end <= end]

    def is_free(self, calendar_id, candidate):
        self.checks += 1
        if self.fail:
            raise RuntimeError("freeBusy unavailable")
        return candidate in self.free

    def booked_count(self, calendar_id, day):
        if self.fail:
            raise RuntimeError("booked count unavailable")
        return self.booked.get((calendar_id, day), 0)


class FakeProvider:
    provider_name = "fake-calendar"
    authoritative_outcome_kinds = frozenset({"attended", "no_show"})

    def __init__(self):
        self.creates = []
        self.moves = []
        self.cancels = []
        self.receipt = receipt()
        self.move_receipt = receipt(provider_receipt_id="pr_2")
        self.cancel_receipt = receipt(provider_receipt_id="pr_3")
        self.raise_on_create = False
        self.raise_on_move = False
        self.observed = {}

    def create(self, *, slot, contact_id, idempotency_key):
        if self.raise_on_create:
            raise TimeoutError("no verdict")
        self.creates.append((slot, contact_id, idempotency_key))
        return dict(self.receipt)

    def move(self, *, provider_booking_id, slot, idempotency_key):
        if self.raise_on_move:
            raise TimeoutError("no verdict")
        self.moves.append((provider_booking_id, slot, idempotency_key))
        return dict(self.move_receipt)

    def cancel(self, *, provider_booking_id, idempotency_key):
        self.cancels.append((provider_booking_id, idempotency_key))
        return dict(self.cancel_receipt)

    def verify_outcome(self, *, provider_booking_id, kind):
        return self.observed.get(kind)


class CollidingIntentKeys(BookingFollowThrough):
    """Test double that forces every booking onto one intent key.

    That is exactly the identity the pre-repair key had (start only), so the
    replay guard is exercised the way a real collision would exercise it. The
    override takes its fifth argument positionally, so it holds for both the
    instant-keyed and the fingerprint-keyed callers.
    """

    def _intent_key(self, verb, calendar_id, contact_id, slot, purpose):
        return "forced-collision|" + verb


class PermissiveAvailability(FakeAvailability):
    """A calendar adapter whose read is wider than the window it was asked for
    (a stale cache, or a provider that ignores the bounds). What gets offered
    must be bounded by the module, never by the adapter's good behaviour."""

    def free_slots(self, calendar_id, start, end):
        self.reads += 1
        if self.fail:
            raise RuntimeError("freeBusy unavailable")
        return [s for s in self.free if s.calendar_id == calendar_id]


class CalendarCountingAvailability(FakeAvailability):
    """booked_count derived from what is actually on the calendar: this
    provider's one booking wherever its last write put it, plus `others`."""

    def __init__(self, free, provider, others=()):
        super().__init__(free)
        self.provider = provider
        self.others = list(others)

    def booked_count(self, calendar_id, day):
        mine = [s for s, _c, _k in self.provider.creates[-1:]]
        mine = [s for _b, s, _k in self.provider.moves[-1:]] or mine
        if self.provider.cancels:
            mine = []
        return sum(1 for s in mine + self.others
                   if s.calendar_id == calendar_id
                   and s.local("America/New_York").date() == day)


class BookingCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="t28-booking-")
        self.store = DurableStore(str(Path(self.tmp.name) / "booking.sqlite"))
        self.avail = FakeAvailability([slot(5, 10), slot(6, 14), slot(7, 9)])
        self.provider = FakeProvider()
        self.policy = BookingPolicy(
            calendars={"default": CAL_A, "on-site estimate": CAL_B},
            timezone="America/New_York",
            location="12 Main St, Raleigh NC",
            change_path="reply here or call the office",
            max_window_days=14,
            min_lead_hours=2,
            max_declines=3,
        )
        self.eng = BookingFollowThrough(
            store=self.store, availability=self.avail, provider=self.provider,
            policy=self.policy, tenant_id="tenant-1")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def assertRefused(self, code, fn, *args, **kwargs):
        with self.assertRaises(Refusal) as ctx:
            fn(*args, **kwargs)
        self.assertEqual(ctx.exception.code, code)
        return ctx.exception


# ── availability: actual, never invented ───────────────────────────────────

class AvailabilityTests(BookingCase):
    def test_offers_only_slots_the_calendar_reports_free(self):
        offer = self.eng.offer_slots("consult", now=NOW)
        self.assertEqual({s.instant_key() for s in offer.slots},
                         {s.instant_key() for s in self.avail.free})
        self.assertFalse(offer.escalate)

    def test_a_listed_slot_that_fails_free_busy_verification_is_dropped(self):
        self.avail.free = [slot(5, 10), slot(6, 14)]
        stale = self.avail.free[1]
        self.avail.free = [slot(5, 10)]
        self.avail.is_free = lambda cal, s: s.instant_key() != stale.instant_key()
        offer = self.eng.offer_slots("consult", now=NOW)
        self.assertNotIn(stale.instant_key(),
                         {s.instant_key() for s in offer.slots})

    def test_empty_calendar_offers_nothing(self):
        self.avail.free = []
        offer = self.eng.offer_slots("consult", now=NOW)
        self.assertEqual(offer.slots, ())
        self.assertTrue(offer.escalate)
        self.assertIn("operator", offer.message)

    def test_availability_read_failure_refuses_instead_of_promising(self):
        self.avail.fail = True
        self.assertRefused(R_CALENDAR_UNAVAILABLE,
                           self.eng.offer_slots, "consult", now=NOW)

    def test_booking_without_a_default_calendar_is_a_build_failure(self):
        self.assertRefused(R_CALENDAR_UNMAPPED, BookingPolicy,
                           calendars={"consult": CAL_A},
                           timezone="America/New_York", location="x",
                           change_path="y", max_window_days=7,
                           min_lead_hours=1)

    def test_purpose_routes_exact_key_then_default(self):
        self.assertEqual(self.eng.resolve_calendar("on-site estimate"), CAL_B)
        self.assertEqual(self.eng.resolve_calendar("Consult"), CAL_A)
        self.assertEqual(self.eng.resolve_calendar("something else"), CAL_A)

    def test_a_slot_on_a_non_routed_calendar_is_refused(self):
        self.assertRefused(
            R_CALENDAR_UNMAPPED, self.eng.book,
            purpose="consult", slot=slot(5, 10, calendar=CAL_B),
            contact_id="c1", confirmed=True, now=NOW)
        self.assertEqual(self.provider.creates, [])


# ── recheck at commit ──────────────────────────────────────────────────────

class RecheckTests(BookingCase):
    def test_taken_slot_refuses_at_commit_and_never_books(self):
        offered = self.eng.offer_slots("consult", now=NOW).slots[0]
        self.avail.free = [s for s in self.avail.free
                           if s.instant_key() != offered.instant_key()]
        self.assertRefused(R_SLOT_TAKEN, self.eng.book, purpose="consult",
                           slot=offered, contact_id="c1", confirmed=True, now=NOW)
        self.assertEqual(self.provider.creates, [],
                         "no provider write may happen on a stale read")
        action = self.store.action_by_intent(
            "booking|tenant-1|book|CAL_A|c1|" + offered.fingerprint() + "|consult")
        self.assertIsNotNone(
            action,
            "the intent key is booking|tenant|verb|calendar|contact|"
            "fingerprint|purpose; the fingerprint is the whole slot")
        self.assertEqual(action["state"], "canceled")

    def test_recheck_read_failure_refuses_and_writes_nothing(self):
        offered = self.eng.offer_slots("consult", now=NOW).slots[0]
        self.avail.fail = True
        self.assertRefused(R_CALENDAR_UNAVAILABLE, self.eng.book,
                           purpose="consult", slot=offered, contact_id="c1",
                           confirmed=True, now=NOW)
        self.assertEqual(self.provider.creates, [])

    def test_lead_time_is_enforced(self):
        inside_lead = Slot(NOW + timedelta(minutes=30),
                           NOW + timedelta(minutes=90), CAL_A)
        self.avail.free = [inside_lead]
        self.assertEqual(self.eng.offer_slots("consult", now=NOW).slots, ())
        self.assertRefused(R_OUTSIDE_POLICY, self.eng.book, purpose="consult",
                           slot=inside_lead, contact_id="c1", confirmed=True,
                           now=NOW)

    def test_excluded_weekday_and_hour_are_not_offered(self):
        policy = BookingPolicy(
            calendars={"default": CAL_A}, timezone="America/New_York",
            location="x", change_path="y", max_window_days=14,
            min_lead_hours=0, excluded_weekdays=frozenset({5}),  # Saturday
            excluded_hours=((9, 11),))
        eng = BookingFollowThrough(store=self.store, availability=self.avail,
                                   provider=self.provider, policy=policy,
                                   tenant_id="tenant-1")
        self.avail.free = [slot(8, 10), slot(10, 14)]  # Sat 10:00, Mon 14:00
        offer = eng.offer_slots("consult", now=NOW)
        self.assertEqual([s.local("America/New_York").strftime("%a") for s in offer.slots],
                         ["Mon"])

    def test_daily_cap_uses_a_real_booked_count(self):
        policy = BookingPolicy(
            calendars={"default": CAL_A}, timezone="America/New_York",
            location="x", change_path="y", max_window_days=14,
            min_lead_hours=0, daily_cap=1)
        eng = BookingFollowThrough(store=self.store, availability=self.avail,
                                   provider=self.provider, policy=policy,
                                   tenant_id="tenant-1")
        day = slot(5, 10).local("America/New_York").date()
        self.avail.booked[(CAL_A, day)] = 1
        offer = eng.offer_slots("consult", now=NOW)
        self.assertNotIn(5, [s.local("America/New_York").day for s in offer.slots])

    def test_the_beyond_window_path_never_offers_a_slot_that_already_passed(self):
        past = Slot(datetime(2027, 4, 1, 14, 0, tzinfo=ZoneInfo("UTC")),
                    datetime(2027, 4, 1, 15, 0, tzinfo=ZoneInfo("UTC")), CAL_A)
        policy = BookingPolicy(
            calendars={"default": CAL_A}, timezone="America/New_York",
            location="x", change_path="y", max_window_days=7,
            min_lead_hours=2, offer_next_available_beyond_window=True)
        eng = BookingFollowThrough(
            store=self.store, availability=PermissiveAvailability([past]),
            provider=self.provider, policy=policy, tenant_id="tenant-1")
        offer = eng.offer_slots("consult", now=NOW)
        self.assertEqual(offer.slots, (),
                         "a slot that already passed is never the next available")
        self.assertEqual(offer.stage, "escalate")

    def test_the_beyond_window_path_respects_the_min_lead_floor(self):
        too_soon = Slot(NOW + timedelta(hours=2), NOW + timedelta(hours=3), CAL_A)
        base = dict(calendars={"default": CAL_A},
                    timezone="America/New_York", location="x", change_path="y",
                    max_window_days=7, min_lead_hours=12)

        control = BookingFollowThrough(
            store=self.store, availability=PermissiveAvailability([too_soon]),
            provider=self.provider,
            policy=BookingPolicy(**base, offer_next_available_beyond_window=False),
            tenant_id="tenant-1")
        self.assertEqual(control.offer_slots("consult", now=NOW).slots, (),
                         "control: the normal path already applies the floor")

        eng = BookingFollowThrough(
            store=self.store, availability=PermissiveAvailability([too_soon]),
            provider=self.provider,
            policy=BookingPolicy(**base, offer_next_available_beyond_window=True),
            tenant_id="tenant-1")
        offer = eng.offer_slots("consult", now=NOW)
        self.assertEqual(offer.slots, (),
                         "the beyond-window path is held to the same min lead")
        self.assertEqual(offer.stage, "escalate")


# ── decline ladder and no-availability paths ───────────────────────────────

class DeclineTests(BookingCase):
    def test_first_decline_offers_up_to_three_distinct_days(self):
        offer = self.eng.offer_slots("consult", now=NOW, declines=1)
        self.assertEqual(offer.stage, "decline_1")
        self.assertLessEqual(len(offer.slots), 3)
        days = [s.local("America/New_York").date() for s in offer.slots]
        self.assertEqual(len(days), len(set(days)))

    def test_second_decline_offers_one_wider_slot(self):
        offer = self.eng.offer_slots("consult", now=NOW, declines=2)
        self.assertEqual(offer.stage, "decline_2")
        self.assertEqual(len(offer.slots), 1)

    def test_third_decline_stops_offering_and_escalates(self):
        offer = self.eng.offer_slots("consult", now=NOW, declines=3)
        self.assertEqual((offer.stage, offer.escalate, offer.slots),
                         ("escalate", True, ()))

    def test_no_availability_beyond_window_path(self):
        self.avail.free = []
        policy = BookingPolicy(
            calendars={"default": CAL_A}, timezone="America/New_York",
            location="x", change_path="y", max_window_days=7,
            min_lead_hours=0, offer_next_available_beyond_window=True)
        eng = BookingFollowThrough(store=self.store, availability=self.avail,
                                   provider=self.provider, policy=policy,
                                   tenant_id="tenant-1")
        beyond = Slot(NOW + timedelta(days=9), NOW + timedelta(days=9, hours=1), CAL_A)
        self.avail.free = [beyond]
        offer = eng.offer_slots("consult", now=NOW)
        self.assertEqual((offer.stage, len(offer.slots)), ("beyond_window", 1))

    def test_no_availability_waitlist_path(self):
        self.avail.free = []
        policy = BookingPolicy(
            calendars={"default": CAL_A}, timezone="America/New_York",
            location="x", change_path="y", max_window_days=7,
            min_lead_hours=0, offer_waitlist=True)
        eng = BookingFollowThrough(store=self.store, availability=self.avail,
                                   provider=self.provider, policy=policy,
                                   tenant_id="tenant-1")
        offer = eng.offer_slots("consult", now=NOW)
        self.assertEqual((offer.stage, offer.slots), ("waitlist", ()))


# ── timezone ───────────────────────────────────────────────────────────────

class TimezoneTests(unittest.TestCase):
    def test_naive_datetime_is_refused(self):
        with self.assertRaises(Refusal) as ctx:
            Slot(datetime(2027, 5, 5, 10, 0),
                 datetime(2027, 5, 5, 11, 0), CAL_A)
        self.assertEqual(ctx.exception.code, R_NAIVE_DATETIME)

    def test_unknown_zone_is_refused(self):
        fixed = timezone(timedelta(hours=2))   # a fixed offset is not an IANA zone
        with self.assertRaises(Refusal) as ctx:
            Slot(datetime(2027, 5, 5, 10, 0, tzinfo=fixed),
                 datetime(2027, 5, 5, 11, 0, tzinfo=fixed), CAL_A)
        self.assertEqual(ctx.exception.code, R_UNKNOWN_TIMEZONE)

    def test_same_instant_in_two_zones_is_the_same_slot(self):
        utc = ZoneInfo("UTC")
        a = slot(5, 14, tz=utc)          # 14:00 UTC == 10:00 EDT
        b = slot(5, 10, tz=NY)
        self.assertEqual(a.instant_key(), b.instant_key())
        self.assertEqual(a.fingerprint(), b.fingerprint())

    def test_confirmation_restates_timezone_location_and_change_path(self):
        with tempfile.TemporaryDirectory(prefix="t28-tz-") as tmp:
            store = DurableStore(str(Path(tmp) / "b.sqlite"))
            try:
                provider = FakeProvider()
                eng = BookingFollowThrough(
                    store=store, availability=FakeAvailability([slot(5, 10, tz=ZoneInfo("UTC"))]),
                    provider=provider,
                    policy=BookingPolicy(
                        calendars={"default": CAL_A},
                        timezone="America/New_York", location="12 Main St",
                        change_path="reply here", max_window_days=14,
                        min_lead_hours=0),
                    tenant_id="t")
                booking = eng.book(purpose="consult",
                                   slot=slot(5, 10, tz=ZoneInfo("UTC")),
                                   contact_id="c1", confirmed=True, now=NOW)
                text = eng.confirmation_text(booking)
            finally:
                store.close()
        self.assertIn("America/New_York", text)
        self.assertIn("12 Main St", text)
        self.assertIn("reply here", text)
        self.assertIn("6:00 AM EDT", text)   # 10:00 UTC rendered in New York


# ── booking receipts ───────────────────────────────────────────────────────

class ReceiptTests(BookingCase):
    def test_confirmation_is_required_before_booking(self):
        self.assertRefused(R_NO_EXPLICIT_YES, self.eng.book, purpose="consult",
                           slot=slot(5, 10), contact_id="c1", confirmed=False,
                           now=NOW)
        self.assertEqual(self.provider.creates, [])

    def test_a_real_receipt_is_the_only_way_to_claim_booked(self):
        booking = self.eng.book(purpose="consult", slot=slot(5, 10),
                                contact_id="c1", confirmed=True, now=NOW)
        self.assertTrue(booking.claimed)
        self.assertEqual(booking.provider_booking_id, "bk_1")
        kinds = self.store.receipts(booking.action_id)
        self.assertEqual({"dispatch", "ack", "completion"}, set(kinds))
        self.assertEqual(kinds["completion"]["payload"]["calendar_id"], CAL_A)

    def test_incomplete_receipt_is_never_promoted_to_booked(self):
        self.provider.receipt = receipt(evidence_id=None)
        booking = self.eng.book(purpose="consult", slot=slot(5, 10),
                                contact_id="c1", confirmed=True, now=NOW)
        self.assertFalse(booking.claimed)
        self.assertEqual(booking.state, "unknown")
        self.assertNotIn("completion", self.store.receipts(booking.action_id))

    def test_provider_exception_is_unknown_not_booked(self):
        self.provider.raise_on_create = True
        booking = self.eng.book(purpose="consult", slot=slot(5, 10),
                                contact_id="c1", confirmed=True, now=NOW)
        self.assertFalse(booking.claimed)
        self.assertEqual(booking.state, "unknown")
        self.assertNotIn("completion", self.store.receipts(booking.action_id))

    def test_same_intent_writes_once(self):
        first = self.eng.book(purpose="consult", slot=slot(5, 10),
                              contact_id="c1", confirmed=True, now=NOW)
        second = self.eng.book(purpose="consult", slot=slot(5, 10),
                               contact_id="c1", confirmed=True, now=NOW)
        self.assertEqual(len(self.provider.creates), 1)
        self.assertEqual(first.action_id, second.action_id)
        self.assertTrue(second.claimed)

    def test_same_start_different_duration_is_two_bookings_not_one(self):
        hour = Slot(datetime(2027, 5, 5, 10, 0, tzinfo=NY),
                    datetime(2027, 5, 5, 11, 0, tzinfo=NY), CAL_A)
        block = Slot(datetime(2027, 5, 5, 10, 0, tzinfo=NY),
                     datetime(2027, 5, 5, 13, 0, tzinfo=NY), CAL_A)
        self.avail.free = [hour, block]
        first = self.eng.book(purpose="consult", slot=hour, contact_id="c1",
                              confirmed=True, now=NOW)
        second = self.eng.book(purpose="consult", slot=block, contact_id="c1",
                               confirmed=True, now=NOW)
        self.assertEqual(len(self.provider.creates), 2,
                         "a different slot is a different booking")
        self.assertNotEqual(first.action_id, second.action_id)
        self.assertTrue(second.claimed)
        self.assertEqual(second.receipt["end"], block.end.isoformat(),
                         "the receipt must describe the slot that was booked")
        self.assertEqual(second.slot.end, block.end)

    def test_a_replay_never_claims_booked_on_a_different_slot(self):
        hour = Slot(datetime(2027, 5, 5, 10, 0, tzinfo=NY),
                    datetime(2027, 5, 5, 11, 0, tzinfo=NY), CAL_A)
        block = Slot(datetime(2027, 5, 5, 10, 0, tzinfo=NY),
                     datetime(2027, 5, 5, 13, 0, tzinfo=NY), CAL_A)
        self.avail.free = [hour, block]
        eng = CollidingIntentKeys(store=self.store, availability=self.avail,
                                  provider=self.provider, policy=self.policy,
                                  tenant_id="tenant-1")
        first = eng.book(purpose="consult", slot=hour, contact_id="c1",
                         confirmed=True, now=NOW)
        self.assertTrue(first.claimed)
        with self.assertRaises(Refusal) as ctx:
            eng.book(purpose="consult", slot=block, contact_id="c1",
                     confirmed=True, now=NOW)
        self.assertEqual(ctx.exception.code, "CONTENT_MISMATCH")
        self.assertEqual(len(self.provider.creates), 1,
                         "nothing is written for a slot the receipt does not describe")

    def test_confirmation_text_refuses_without_a_receipt(self):
        booking = self.eng.book(purpose="consult", slot=slot(5, 10),
                                contact_id="c1", confirmed=True, now=NOW)
        self.eng.provider.receipt = receipt(evidence_id=None)
        unclaimed = self.eng.book(purpose="consult", slot=slot(6, 14),
                                  contact_id="c1", confirmed=True, now=NOW)
        self.assertTrue(booking.claimed)
        self.assertRefused(R_NO_BOOKING, self.eng.confirmation_text, unclaimed)


# ── change path ────────────────────────────────────────────────────────────

class ChangePathTests(BookingCase):
    def test_reschedule_is_rechecked_receipted_and_supersedes(self):
        first = self.eng.book(purpose="consult", slot=slot(5, 10),
                              contact_id="c1", confirmed=True, now=NOW)
        moved = self.eng.reschedule(booking_action_id=first.action_id,
                                    new_slot=slot(6, 14), now=NOW)
        self.assertTrue(moved.claimed)
        self.assertEqual(len(self.provider.moves), 1)
        self.assertEqual(self.eng.supersedes(moved.action_id), first.action_id)
        # the prior receipt is untouched history, not overwritten
        self.assertEqual(
            self.store.receipts(first.action_id)["completion"]["payload"]
            ["provider_booking_id"], "bk_1")

    def test_reschedule_to_a_taken_slot_refuses_and_keeps_the_old_booking(self):
        first = self.eng.book(purpose="consult", slot=slot(5, 10),
                              contact_id="c1", confirmed=True, now=NOW)
        self.avail.free = [s for s in self.avail.free
                           if s.instant_key() != slot(6, 14).instant_key()]
        self.assertRefused(R_SLOT_TAKEN, self.eng.reschedule,
                           booking_action_id=first.action_id,
                           new_slot=slot(6, 14), now=NOW)
        self.assertEqual(self.provider.moves, [])
        self.assertEqual(
            self.store.receipts(first.action_id)["completion"]["payload"]
            ["provider_booking_id"], "bk_1",
            "the old booking stays authoritative until a new receipt exists")

    def test_reschedule_is_idempotent(self):
        first = self.eng.book(purpose="consult", slot=slot(5, 10),
                              contact_id="c1", confirmed=True, now=NOW)
        a = self.eng.reschedule(booking_action_id=first.action_id,
                                new_slot=slot(6, 14), now=NOW)
        b = self.eng.reschedule(booking_action_id=first.action_id,
                                new_slot=slot(6, 14), now=NOW)
        self.assertEqual(len(self.provider.moves), 1)
        self.assertEqual(a.action_id, b.action_id)

    def test_failed_move_is_unknown_and_old_booking_still_authoritative(self):
        first = self.eng.book(purpose="consult", slot=slot(5, 10),
                              contact_id="c1", confirmed=True, now=NOW)
        self.provider.raise_on_move = True
        result = self.eng.reschedule(booking_action_id=first.action_id,
                                     new_slot=slot(6, 14), now=NOW)
        self.assertFalse(result.claimed)
        self.assertEqual(result.state, "unknown")
        self.assertEqual(
            self.store.receipts(first.action_id)["completion"]["payload"]
            ["provider_booking_id"], "bk_1")

    def test_cancel_is_receipted_and_idempotent(self):
        first = self.eng.book(purpose="consult", slot=slot(5, 10),
                              contact_id="c1", confirmed=True, now=NOW)
        self.avail.free.remove(slot(5, 10))   # the appointment now occupies it
        a = self.eng.cancel(booking_action_id=first.action_id, now=NOW)
        b = self.eng.cancel(booking_action_id=first.action_id, now=NOW)
        self.assertTrue(a.claimed)
        self.assertEqual(a.action_id, b.action_id)
        self.assertEqual(len(self.provider.cancels), 1)

    def test_cancel_refuses_when_the_calendar_shows_the_slot_free(self):
        first = self.eng.book(purpose="consult", slot=slot(5, 10),
                              contact_id="c1", confirmed=True, now=NOW)
        # the slot is still open, so the appointment is not on the calendar
        self.assertRefused(R_BOOKING_NOT_PRESENT, self.eng.cancel,
                           booking_action_id=first.action_id, now=NOW)
        self.assertEqual(self.provider.cancels, [])

    def test_change_without_a_booking_receipt_is_refused(self):
        self.assertRefused(R_NO_BOOKING, self.eng.reschedule,
                           booking_action_id="act_missing",
                           new_slot=slot(6, 14), now=NOW)

    def test_reschedule_inside_the_min_lead_is_refused(self):
        first = self.eng.book(purpose="consult", slot=slot(5, 10),
                              contact_id="c1", confirmed=True, now=NOW)
        too_soon = Slot(NOW + timedelta(minutes=10), NOW + timedelta(minutes=70),
                        CAL_A)
        self.avail.free.append(too_soon)
        self.assertRefused(R_OUTSIDE_POLICY, self.eng.reschedule,
                           booking_action_id=first.action_id,
                           new_slot=too_soon, now=NOW)
        self.assertEqual(self.provider.moves, [])

    def test_reschedule_beyond_the_booking_window_is_refused(self):
        first = self.eng.book(purpose="consult", slot=slot(5, 10),
                              contact_id="c1", confirmed=True, now=NOW)
        far_out = Slot(NOW + timedelta(days=90), NOW + timedelta(days=90, hours=1),
                       CAL_A)
        self.avail.free.append(far_out)
        self.assertRefused(R_OUTSIDE_POLICY, self.eng.reschedule,
                           booking_action_id=first.action_id,
                           new_slot=far_out, now=NOW)
        self.assertEqual(self.provider.moves, [])

    def test_reschedule_over_the_daily_cap_is_refused(self):
        policy = BookingPolicy(
            calendars={"default": CAL_A}, timezone="America/New_York",
            location="x", change_path="y", max_window_days=14,
            min_lead_hours=2, daily_cap=1)
        eng = BookingFollowThrough(store=self.store, availability=self.avail,
                                   provider=self.provider, policy=policy,
                                   tenant_id="tenant-1")
        first = eng.book(purpose="consult", slot=slot(5, 10),
                         contact_id="c1", confirmed=True, now=NOW)
        self.avail.booked[(CAL_A, slot(6, 14).local("America/New_York").date())] = 1
        self.assertRefused(R_OUTSIDE_POLICY, eng.reschedule,
                           booking_action_id=first.action_id,
                           new_slot=slot(6, 14), now=NOW)
        self.assertEqual(self.provider.moves, [])


class DailyCapChangePathTests(BookingCase):
    """The day's count comes from what is really on the calendar, so it already
    holds the booking being moved. A same-day move vacates its own place; a move
    onto another day (or calendar) takes a new one. (PBB-178 C6a-C6d.)"""

    def _capped(self, cap, first, new, others=(), purpose="consult"):
        avail = CalendarCountingAvailability([first, new], self.provider, others)
        policy = BookingPolicy(
            calendars={"default": CAL_A, "on-site estimate": CAL_B},
            timezone="America/New_York", location="x", change_path="y",
            max_window_days=14, min_lead_hours=2, daily_cap=cap)
        eng = BookingFollowThrough(store=self.store, availability=avail,
                                   provider=self.provider, policy=policy,
                                   tenant_id="tenant-1")
        booked = eng.book(purpose=purpose, slot=first, contact_id="c1",
                          confirmed=True, now=NOW)
        self.assertTrue(booked.claimed)
        avail.free.remove(first)          # the appointment now occupies it
        return eng, avail, booked

    def _count(self, avail, s):
        return avail.booked_count(s.calendar_id, s.local("America/New_York").date())

    def test_C6a_the_only_booking_on_a_cap_1_day_moves_within_that_day(self):
        eng, avail, first = self._capped(1, slot(5, 10), slot(5, 14))
        self.assertEqual(self._count(avail, slot(5, 14)), 1)
        moved = eng.reschedule(booking_action_id=first.action_id,
                               new_slot=slot(5, 14), now=NOW)
        self.assertTrue(moved.claimed)
        self.assertEqual(len(self.provider.moves), 1)
        self.assertEqual(self._count(avail, slot(5, 14)), 1, "never over the cap")

    def test_C6b_a_same_day_move_on_a_day_at_its_cap_is_accepted(self):
        eng, avail, first = self._capped(2, slot(5, 10), slot(5, 14),
                                         others=[slot(5, 16)])
        self.assertEqual(self._count(avail, slot(5, 14)), 2)
        moved = eng.reschedule(booking_action_id=first.action_id,
                               new_slot=slot(5, 14), now=NOW)
        self.assertTrue(moved.claimed)
        self.assertEqual(len(self.provider.moves), 1)
        self.assertEqual(self._count(avail, slot(5, 14)), 2, "never over the cap")

    def test_C6c_a_move_into_a_different_day_that_is_full_is_refused(self):
        eng, avail, first = self._capped(1, slot(5, 10), slot(6, 14),
                                         others=[slot(6, 9)])
        self.assertEqual(self._count(avail, slot(6, 14)), 1)
        self.assertRefused(R_OUTSIDE_POLICY, eng.reschedule,
                           booking_action_id=first.action_id,
                           new_slot=slot(6, 14), now=NOW)
        self.assertEqual(self.provider.moves, [])

    def test_C6d_a_move_into_a_different_empty_day_is_accepted(self):
        eng, avail, first = self._capped(1, slot(5, 10), slot(6, 14))
        self.assertEqual(self._count(avail, slot(6, 14)), 0)
        moved = eng.reschedule(booking_action_id=first.action_id,
                               new_slot=slot(6, 14), now=NOW)
        self.assertTrue(moved.claimed)
        self.assertEqual(len(self.provider.moves), 1)

    def test_a_same_day_move_still_refuses_when_other_bookings_fill_the_day(self):
        eng, avail, first = self._capped(1, slot(5, 10), slot(5, 14))
        avail.others.append(slot(5, 16))  # another booking landed after this one
        self.assertRefused(R_OUTSIDE_POLICY, eng.reschedule,
                           booking_action_id=first.action_id,
                           new_slot=slot(5, 14), now=NOW)
        self.assertEqual(self.provider.moves, [])

    def test_the_same_date_on_another_calendar_takes_a_new_place(self):
        eng, avail, first = self._capped(1, slot(5, 10, CAL_B), slot(5, 14),
                                         others=[slot(5, 9)],
                                         purpose="on-site estimate")
        self.assertRefused(R_OUTSIDE_POLICY, eng.reschedule,
                           booking_action_id=first.action_id,
                           new_slot=slot(5, 14), now=NOW)
        self.assertEqual(self.provider.moves, [])


# ── outcomes: authoritative or labelled, never guessed ─────────────────────

class OthersOnlyCounting(CalendarCountingAvailability):
    """A second plausible reading of the adapter contract: `booked_count`
    answers for the OTHER bookings on the day, not for the caller's own.

    Nothing in the contract says which reading an adapter implements, so the
    change path may not assume either (PBB-258 defect 2).
    """

    def booked_count(self, calendar_id, day):
        return sum(1 for s in self.others
                   if s.calendar_id == calendar_id
                   and s.local("America/New_York").date() == day)


class UnprovenSelfExclusionTests(BookingCase):
    """PBB-258: a same-day move frees its own place only when every link of
    that is proven. A place already gone, a count that never held the booking,
    a receipt claiming another day: none of them frees a place, so each is
    counted in full - a refusal, never an overbooked day."""

    def _capped(self, cap, avail):
        policy = BookingPolicy(
            calendars={"default": CAL_A}, timezone="America/New_York",
            location="x", change_path="y", max_window_days=14,
            min_lead_hours=2, daily_cap=cap)
        return BookingFollowThrough(store=self.store, availability=avail,
                                    provider=self.provider, policy=policy,
                                    tenant_id="tenant-1")

    def test_a_cancelled_booking_has_no_place_left_to_vacate(self):
        """Defect 1: the exclusion was granted to a booking that held none."""
        avail = CalendarCountingAvailability(
            [slot(5, 10), slot(5, 16), slot(5, 14)], self.provider)
        eng = self._capped(1, avail)
        first = eng.book(purpose="consult", slot=slot(5, 10),
                         contact_id="c1", confirmed=True, now=NOW)
        avail.free.remove(slot(5, 10))
        self.assertTrue(eng.cancel(booking_action_id=first.action_id,
                                   now=NOW).claimed)
        avail.free.append(slot(5, 10))       # the place is vacated
        avail.others.append(slot(5, 16))     # and someone else takes the day
        self.assertRefused(R_OUTSIDE_POLICY, eng.reschedule,
                           booking_action_id=first.action_id,
                           new_slot=slot(5, 14), now=NOW)
        self.assertEqual(self.provider.moves, [])

    def test_the_exclusion_never_rests_on_a_count_that_may_exclude_the_mover(
            self):
        """Defect 2: the subtraction assumed a precondition no contract gave.

        The inverse - a count that does hold the mover - is what
        `test_C6a_the_only_booking_on_a_cap_1_day_moves_within_that_day`
        proves is still accepted.
        """
        avail = OthersOnlyCounting([slot(5, 10), slot(5, 14)], self.provider)
        eng = self._capped(1, avail)
        first = eng.book(purpose="consult", slot=slot(5, 10),
                         contact_id="c1", confirmed=True, now=NOW)
        avail.free.remove(slot(5, 10))
        avail.others.append(slot(5, 16))     # the day's one place, by another
        self.assertRefused(R_OUTSIDE_POLICY, eng.reschedule,
                           booking_action_id=first.action_id,
                           new_slot=slot(5, 14), now=NOW)
        self.assertEqual(self.provider.moves, [])

    def test_a_receipt_that_claims_another_day_buys_no_exclusion(self):
        """Defect 3: the guard read the provider's echo, which can say any day."""
        self.provider.receipt = receipt(
            start="2027-05-05T10:00:00-04:00", end="2027-05-05T11:00:00-04:00")
        avail = CalendarCountingAvailability(
            [slot(6, 10), slot(5, 14)], self.provider)
        avail.others.append(slot(5, 16))
        eng = self._capped(1, avail)
        first = eng.book(purpose="consult", slot=slot(6, 10),
                         contact_id="c1", confirmed=True, now=NOW)
        avail.free.remove(slot(6, 10))
        self.assertRefused(R_OUTSIDE_POLICY, eng.reschedule,
                           booking_action_id=first.action_id,
                           new_slot=slot(5, 14), now=NOW)
        self.assertEqual(self.provider.moves, [])

    def test_cancel_frees_the_slot_this_module_booked_not_the_receipts_echo(
            self):
        """The same provider-owned field, one path along: the place to free."""
        self.provider.receipt = receipt(
            start=slot(5, 10).start.isoformat(), end=slot(5, 10).end.isoformat())
        avail = CalendarCountingAvailability([slot(6, 10), slot(5, 10)],
                                             self.provider)
        eng = self._capped(1, avail)
        first = eng.book(purpose="consult", slot=slot(6, 10),
                         contact_id="c1", confirmed=True, now=NOW)
        avail.free.remove(slot(6, 10))
        self.assertTrue(eng.cancel(booking_action_id=first.action_id,
                                   now=NOW).claimed)
        self.assertEqual(len(self.provider.cancels), 1)



# ── outcomes: authoritative or labelled, never guessed ─────────────────────

class OutcomeTests(BookingCase):
    def _booked(self):
        return self.eng.book(purpose="consult", slot=slot(5, 10),
                             contact_id="c1", confirmed=True, now=NOW)

    def test_booked_alone_is_not_attendance(self):
        booking = self._booked()
        self.assertEqual(self.eng.outcome_state(booking.action_id), "unverified")

    def test_outcome_without_evidence_is_refused(self):
        booking = self._booked()
        self.assertRefused(R_NO_EVIDENCE_SOURCE, self.eng.record_outcome,
                           booking_action_id=booking.action_id, kind="attended",
                           source="owner_labeled", owner="Trevor")

    def test_unknown_evidence_source_is_refused(self):
        booking = self._booked()
        self.assertRefused(R_BAD_EVIDENCE_SOURCE, self.eng.record_outcome,
                           booking_action_id=booking.action_id, kind="attended",
                           source="vibes", evidence_id="ev1")

    def test_outcome_needs_a_booking_receipt(self):
        self.assertRefused(R_NO_BOOKING, self.eng.record_outcome,
                           booking_action_id="act_missing", kind="attended",
                           source="owner_labeled", owner="Trevor",
                           evidence_id="ev1")

    def test_provider_verified_attendance(self):
        booking = self._booked()
        self.provider.observed["attended"] = True
        out = self.eng.record_outcome(
            booking_action_id=booking.action_id, kind="attended",
            source="provider_verified", evidence_id="ev-att-1")
        self.assertEqual(out.state, "verified")

    def test_provider_cannot_confirm_is_unverified(self):
        booking = self._booked()
        self.provider.observed["attended"] = None
        out = self.eng.record_outcome(
            booking_action_id=booking.action_id, kind="attended",
            source="provider_verified", evidence_id="ev-att-1")
        self.assertEqual(out.state, "unverified")

    def test_provider_contradiction_is_reported_not_flipped(self):
        booking = self._booked()
        self.provider.observed["no_show"] = False
        out = self.eng.record_outcome(
            booking_action_id=booking.action_id, kind="no_show",
            source="provider_verified", evidence_id="ev-ns-1")
        self.assertEqual(out.state, "contradicted")

    def test_sales_are_not_provider_authoritative_for_this_calendar(self):
        booking = self._booked()
        self.assertRefused(
            R_NO_AUTHORITATIVE_SOURCE, self.eng.record_outcome,
            booking_action_id=booking.action_id, kind="sold",
            source="provider_verified", evidence_id="ev-1")

    def test_sales_need_labelled_owner_evidence(self):
        booking = self._booked()
        out = self.eng.record_outcome(
            booking_action_id=booking.action_id, kind="sold",
            source="owner_labeled", owner="Trevor", evidence_id="ev-sale-1")
        self.assertEqual(out.state, "owner_labeled")
        self.assertIn("Trevor", out.note)

    def test_a_recorded_outcome_is_readable_after_the_call(self):
        booking = self._booked()
        self.provider.observed["attended"] = True
        out = self.eng.record_outcome(
            booking_action_id=booking.action_id, kind="attended",
            source="provider_verified", evidence_id="ev-att-1")
        self.assertEqual(out.state, "verified")
        self.assertEqual(self.eng.outcome_state(booking.action_id), "verified",
                         "a verified attendance is not discarded on return")

    def test_a_recorded_outcome_survives_a_new_reader(self):
        booking = self._booked()
        self.provider.observed["attended"] = True
        self.eng.record_outcome(
            booking_action_id=booking.action_id, kind="attended",
            source="provider_verified", evidence_id="ev-att-1")
        fresh = BookingFollowThrough(store=self.store, availability=self.avail,
                                     provider=self.provider, policy=self.policy,
                                     tenant_id="tenant-1")
        self.assertEqual(fresh.outcome_state(booking.action_id), "verified",
                         "the outcome lives in the durable store, not in memory")


# ── the declared public surface ────────────────────────────────────────────

class PublicSurfaceTests(unittest.TestCase):
    def test_every_name_the_package_declares_exists(self):
        import booking
        missing = [name for name in booking.__all__
                   if not hasattr(booking, name)]
        self.assertEqual(missing, [],
                         "names declared in __all__ must exist: %s" % (missing,))


# ── attribution ────────────────────────────────────────────────────────────

class AttributionTests(BookingCase):
    def test_single_keyword_is_preserved_without_causal_claim(self):
        a = self.eng.attribute(keyword="PODCAST42")
        self.assertEqual((a.basis, a.keyword, a.exact_causality),
                         ("keyword", "PODCAST42", False))

    def test_multi_touch_keeps_the_keyword(self):
        a = self.eng.attribute(keyword="PODCAST42", touches=["ad", "dm", "referral"])
        self.assertEqual((a.basis, a.keyword, len(a.touches)),
                         ("multi_touch", "PODCAST42", 3))

    def test_no_evidence_is_unknown_not_a_guess(self):
        a = self.eng.attribute()
        self.assertEqual((a.basis, a.keyword, a.exact_causality),
                         ("unknown", None, False))


# ── PBB-376: pin every load-bearing link of the exclusion proof ────────────
# The exclusion that lets a same-day move free its own place is proved by a
# conjunction of independent links (_vacates_a_place). A cancelled booking is
# caught by three of them at once (_was_cancelled, _cancel_recorded, and the
# free-slot check), so any one of those can be dropped and the others still
# refuse - which is why a single "cancelled booking" test leaves all three
# unpinned. Each test below isolates ONE link so dropping it is observable.

class _MarkerlessStore(DurableStore):
    """The cancellation marker write is best-effort and can be lost while the
    cancel receipt itself still lands (DurableStoreError is swallowed in
    _record_cancellation). This double models that: no marker, only a receipt."""

    def record_reconciliation(self, *args, **kwargs):  # the marker is never written
        return None


class _CancelUnknownProvider(FakeProvider):
    """A cancel whose provider call raises before any verdict: the cancel action
    is left UNKNOWN, not completed, so it is not proof the place was given up."""

    def cancel(self, *, provider_booking_id, idempotency_key):
        raise TimeoutError("no verdict")


class SelfExclusionLinkPins(BookingCase):
    """One pin per link of `_vacates_a_place` that the older tests left
    redundant. Each test FAILS when its link is removed and PASSES when it is
    present, because in each scenario that link is the only one that can refuse
    (or, for the unconfirmed-cancel pin, the only one that can accept)."""

    def _eng(self, cap, avail, provider=None, store=None):
        policy = BookingPolicy(
            calendars={"default": CAL_A}, timezone="America/New_York",
            location="x", change_path="y", max_window_days=14,
            min_lead_hours=2, daily_cap=cap)
        return BookingFollowThrough(store=store or self.store, availability=avail,
                                    provider=provider or self.provider,
                                    policy=policy, tenant_id="tenant-1")

    def _book(self, eng, avail, slot_to_book):
        booked = eng.book(purpose="consult", slot=slot_to_book, contact_id="c1",
                          confirmed=True, now=NOW)
        self.assertTrue(booked.claimed)
        return booked

    def test_a_cancellation_marker_alone_frees_no_place(self):
        """The booking is recorded as cancelled but still occupies its place on
        the calendar (a stale free/busy read) and there is no cancel receipt.
        Only the marker link refuses, so it must stay load-bearing."""
        avail = CalendarCountingAvailability([slot(5, 10), slot(5, 14)],
                                             self.provider)
        eng = self._eng(1, avail)
        first = self._book(eng, avail, slot(5, 10))
        avail.free.remove(slot(5, 10))            # the place is still taken
        self.store.record_reconciliation(first.action_id, "cancelled",
                                         {"record": "booking_cancellation"})
        self.assertRefused(R_OUTSIDE_POLICY, eng.reschedule,
                           booking_action_id=first.action_id,
                           new_slot=slot(5, 14), now=NOW)
        self.assertEqual(self.provider.moves, [])

    def test_a_cancel_receipt_without_the_marker_frees_no_place(self):
        """The cancel receipt landed but the marker write was lost, and the
        place is still taken. Only the cancel-receipt link refuses."""
        store = _MarkerlessStore(str(Path(self.tmp.name) / "m5.sqlite"))
        avail = CalendarCountingAvailability([slot(5, 10), slot(5, 14)],
                                             self.provider)
        eng = self._eng(1, avail, store=store)
        first = self._book(eng, avail, slot(5, 10))
        avail.free.remove(slot(5, 10))            # the place is still taken
        self.assertTrue(eng.cancel(booking_action_id=first.action_id,
                                   now=NOW).claimed)
        avail.others.append(slot(5, 16))          # someone else fills the day
        self.assertRefused(R_OUTSIDE_POLICY, eng.reschedule,
                           booking_action_id=first.action_id,
                           new_slot=slot(5, 14), now=NOW)
        self.assertEqual(self.provider.moves, [])

    def test_a_place_already_free_holds_nothing_to_vacate(self):
        """The old place is already free on the read, so the move frees no new
        place. Only the free-slot link refuses."""
        avail = CalendarCountingAvailability([slot(5, 10), slot(5, 14)],
                                             self.provider)
        eng = self._eng(1, avail)
        first = self._book(eng, avail, slot(5, 10))
        self.assertTrue(avail.is_free(CAL_A, slot(5, 10)))   # left free on purpose
        self.assertRefused(R_OUTSIDE_POLICY, eng.reschedule,
                           booking_action_id=first.action_id,
                           new_slot=slot(5, 14), now=NOW)
        self.assertEqual(self.provider.moves, [])

    def test_an_echo_of_another_day_still_frees_no_place(self):
        """The record says the booking sits on day 5; the provider's echo claims
        day 6. The echo must not buy an exclusion. Only the echo-agreement link
        refuses (the start/day branch)."""
        self.provider.receipt = receipt(
            start="2027-05-06T10:00:00-04:00", end="2027-05-06T11:00:00-04:00")
        avail = CalendarCountingAvailability([slot(5, 10), slot(5, 14)],
                                             self.provider)
        eng = self._eng(1, avail)
        first = self._book(eng, avail, slot(5, 10))
        avail.free.remove(slot(5, 10))            # the place is still taken
        self.assertRefused(R_OUTSIDE_POLICY, eng.reschedule,
                           booking_action_id=first.action_id,
                           new_slot=slot(5, 14), now=NOW)
        self.assertEqual(self.provider.moves, [])

    def test_an_echo_of_another_calendar_still_frees_no_place(self):
        """The record says CAL_A; the provider's echo claims CAL_B. Only the
        echo-agreement link refuses (the calendar branch)."""
        self.provider.receipt = receipt(calendar_id=CAL_B)
        avail = CalendarCountingAvailability([slot(5, 10), slot(5, 14)],
                                             self.provider)
        eng = self._eng(1, avail)
        first = self._book(eng, avail, slot(5, 10))
        avail.free.remove(slot(5, 10))            # the place is still taken
        self.assertRefused(R_OUTSIDE_POLICY, eng.reschedule,
                           booking_action_id=first.action_id,
                           new_slot=slot(5, 14), now=NOW)
        self.assertEqual(self.provider.moves, [])

    def test_an_unconfirmed_cancel_still_lets_the_move_free_its_place(self):
        """The cancel never confirmed (UNKNOWN). A booking that still holds its
        place keeps its exclusion. Only the completed-state link, if dropped,
        would wrongly treat that in-flight cancel as proof of a given-up place."""
        provider = _CancelUnknownProvider()
        avail = CalendarCountingAvailability([slot(5, 10), slot(5, 14)], provider)
        eng = self._eng(1, avail, provider=provider)
        first = self._book(eng, avail, slot(5, 10))
        avail.free.remove(slot(5, 10))            # the place is still taken
        gone = eng.cancel(booking_action_id=first.action_id, now=NOW)
        self.assertFalse(gone.claimed)            # unknown, not cancelled
        moved = eng.reschedule(booking_action_id=first.action_id,
                               new_slot=slot(5, 14), now=NOW)
        self.assertTrue(moved.claimed)            # the move frees its own place
        self.assertEqual(len(provider.moves), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
