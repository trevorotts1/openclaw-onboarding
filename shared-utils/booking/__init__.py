"""Booking and service follow-through (PBB-122 / T-28).

Public surface:

    from booking import (
        BookingFollowThrough, BookingPolicy, Slot, Offer, Booking, Outcome,
        Attribution, Refusal,
    )

See followthrough.py for the contract clauses each behaviour pins.
"""

from .followthrough import (  # noqa: F401
    SCHEMA,
    Attribution,
    Booking,
    BookingFollowThrough,
    BookingPolicy,
    Offer,
    Outcome,
    Refusal,
    Slot,
    OUTCOME_KINDS,
    R_BAD_EVIDENCE_SOURCE,
    R_BAD_SLOT,
    R_BOOKING_NOT_PRESENT,
    R_CALENDAR_UNAVAILABLE,
    R_CALENDAR_UNMAPPED,
    R_CONTENT_MISMATCH,
    R_INTENT_TERMINAL,
    R_NAIVE_DATETIME,
    R_NO_AUTHORITATIVE_SOURCE,
    R_NO_BOOKING,
    R_NO_EVIDENCE_SOURCE,
    R_NO_EXPLICIT_YES,
    R_OUTSIDE_POLICY,
    R_SLOT_TAKEN,
    R_UNKNOWN_TIMEZONE,
)

__all__ = [
    "SCHEMA", "Attribution", "Booking", "BookingFollowThrough", "BookingPolicy",
    "Offer", "Outcome", "Refusal", "Slot", "OUTCOME_KINDS",
    "R_BAD_EVIDENCE_SOURCE", "R_BAD_SLOT", "R_BOOKING_NOT_PRESENT",
    "R_CALENDAR_UNAVAILABLE", "R_CALENDAR_UNMAPPED", "R_CONTENT_MISMATCH",
    "R_INTENT_TERMINAL", "R_NAIVE_DATETIME", "R_NO_AUTHORITATIVE_SOURCE",
    "R_NO_BOOKING", "R_NO_EVIDENCE_SOURCE", "R_NO_EXPLICIT_YES",
    "R_OUTSIDE_POLICY", "R_SLOT_TAKEN",
    "R_UNKNOWN_TIMEZONE",
]
