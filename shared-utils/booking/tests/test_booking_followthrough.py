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
            "booking|tenant-1|book|CAL_A|c1|" + offered.instant_key() + "|consult")
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
