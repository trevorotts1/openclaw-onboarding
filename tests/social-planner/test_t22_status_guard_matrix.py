#!/usr/bin/env python3
"""test_t22_status_guard_matrix.py — T-22 read-path / guard agreement.

`status_surface` (the read path) and `assert_truthful_publication` (the guard)
must agree in BOTH directions for every combination of route, account_type,
personal_profile, status and receipt presence: never one blessing a claim the
other refuses, and never one refusing a claim the other blesses.

Both now delegate to the same truth evaluator, so agreement is structural; this
matrix is the proof that it holds, plus the known-good control where a genuine
page publication passes both.

Run:  python3 -m unittest tests/social-planner/test_t22_status_guard_matrix.py -v
"""

import itertools
import os
import sys
import unittest

_ONB_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SHARED = os.path.join(_ONB_ROOT, "shared-utils")
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

import personal_profile_capability as ppc  # noqa: E402

PLACEMENT_ID = "plc_matrix"
PLACEMENT = {
    "text": "matrix control",
    "asset": {"type": "image", "url": "https://assets.example/matrix.png"},
    "keyword": "MATRIX",
    "cta": "Comment MATRIX",
    "timing": {"date": "2026-11-01", "local_time": "09:00", "timezone": "UTC"},
}

ROUTES = ("assisted", "unattended", "refused", None)
ACCOUNT_TYPES = ("personal", "page")
PERSONAL_FLAGS = (True, False, None)
STATUSES = (
    "awaiting-operator",
    "operator-confirmed",
    "published-by-system",
    "published",
    "not-a-status",
)
RECEIPTS = ("absent", "valid", "wrong-placement", "empty")
STATUS_SURFACE = "status_surface"
GUARD = "assert_truthful_publication"


def _receipts():
    valid = {
        "placement_id": PLACEMENT_ID,
        "operator": "Operator Name",
        "confirmed_at": "2026-10-24T15:00:00Z",
        "method": "operator-asserted",
    }
    return {
        "absent": None,
        "valid": valid,
        "wrong-placement": dict(valid, placement_id="plc_somewhere_else"),
        "empty": {},
    }


def _verdict(fn, record):
    """('pass', None) or ('refuse', exact exception type)."""
    try:
        fn(record)
        return ("pass", None)
    except ppc.CapabilityError as exc:  # UntruthfulPublication is a subclass
        return ("refuse", type(exc).__name__)


def _matrix_rows():
    receipts = _receipts()
    for route, account, personal, status, receipt in itertools.product(
        ROUTES, ACCOUNT_TYPES, PERSONAL_FLAGS, STATUSES, RECEIPTS
    ):
        record = {
            "placement_id": PLACEMENT_ID,
            "route": route,
            "channel": "facebook",
            "account_type": account,
            "personal_profile": personal,
            "status": status,
            "receipt": receipts[receipt],
        }
        yield {
            "route": route,
            "account_type": account,
            "personal_profile": personal,
            "status": status,
            "receipt": receipt,
            STATUS_SURFACE: _verdict(ppc.status_surface, record),
            GUARD: _verdict(ppc.assert_truthful_publication, record),
        }


class TestStatusGuardAgreement(unittest.TestCase):
    def test_status_and_guard_agree_in_both_directions(self):
        rows = list(_matrix_rows())
        self.assertEqual(len(rows), 480)  # 4 routes x 2 accounts x 3 flags x 5 statuses x 4 receipts
        for row in rows:
            surface, guard = row[STATUS_SURFACE], row[GUARD]
            self.assertEqual(
                surface[0],
                guard[0],
                "status/guard disagree: " + repr(row),
            )
            self.assertEqual(
                surface[1],
                guard[1],
                "status/guard raise different errors: " + repr(row),
            )

    def test_reported_unattended_personal_defect_is_refused_everywhere(self):
        # the exact record the QC failure was reproduced with
        lying = {
            "placement_id": "plc_fake",
            "route": "unattended",
            "channel": "facebook",
            "account_type": "personal",
            "personal_profile": True,
            "status": "published-by-system",
        }
        for fn in (ppc.status_surface, ppc.assert_truthful_publication):
            with self.assertRaises(ppc.UntruthfulPublication):
                fn(lying)
        # account_type alone, without the flag, is personal too
        for record in (dict(lying, personal_profile=None), dict(lying, personal_profile=False)):
            for fn in (ppc.status_surface, ppc.assert_truthful_publication):
                with self.assertRaises(ppc.UntruthfulPublication):
                    fn(record)

    def test_known_good_page_publication_passes_both(self):
        controls = [
            # a genuine page publication on the declared unattended path
            {
                "placement_id": "plc_page",
                "route": "unattended",
                "channel": "facebook",
                "account_type": "page",
                "personal_profile": False,
                "status": "published-by-system",
                "receipt": None,
            },
            # a page placement the operator confirmed, with a bound receipt
            {
                "placement_id": PLACEMENT_ID,
                "route": "assisted",
                "channel": "facebook",
                "account_type": "page",
                "personal_profile": False,
                "status": "operator-confirmed",
                "receipt": {
                    "placement_id": PLACEMENT_ID,
                    "operator": "Operator Name",
                    "confirmed_at": "2026-10-24T15:00:00Z",
                    "method": "operator-asserted",
                },
            },
            # an honest personal placement, awaiting the operator
            {
                "placement_id": PLACEMENT_ID,
                "route": "assisted",
                "channel": "facebook",
                "account_type": "personal",
                "personal_profile": True,
                "status": "awaiting-operator",
                "receipt": None,
            },
        ]
        for record in controls:
            surface = ppc.status_surface(record)
            self.assertTrue(ppc.assert_truthful_publication(record), repr(record))
            self.assertEqual(surface["status"], record["status"])
        self.assertEqual(ppc.status_surface(controls[0])["claim"], "published-by-system")
        self.assertTrue(ppc.status_surface(controls[0])["published_by_system"])
        self.assertFalse(ppc.status_surface(controls[2])["published_by_system"])


class TestUnattendedRefusalHeld(unittest.TestCase):
    def test_every_personal_triple_still_refused_with_no_package(self):
        """The enforced honesty behaviour must survive the repair: 36/36 held."""
        caps = ppc.load_capabilities()
        seen = 0
        for channel_id, channel in caps["channels"].items():
            for account_id, account in channel["account_types"].items():
                if not account.get("personal_profile"):
                    continue
                actions = sorted(
                    set(account["operator_action"]) | set(account["unavailable"])
                )
                self.assertTrue(actions, f"{channel_id}/{account_id} offers nothing to try")
                for action in actions:
                    seen += 1
                    result = ppc.request_placement(
                        channel_id, account_id, action=action, unattended=True
                    )
                    where = f"{channel_id}/{account_id}/{action}"
                    self.assertTrue(result["refused"], where)
                    self.assertEqual(result["route"], "refused", where)
                    self.assertNotIn("package", result, where)
                    self.assertTrue(result["reason"], where)
                    if account["mode"] == "unavailable":
                        self.assertEqual(result["reason_code"], "capability_unavailable", where)
                    else:
                        self.assertEqual(result["reason_code"], "unattended_not_supported", where)
        self.assertEqual(seen, 36, f"expected 36 personal triples, saw {seen}")


class TestOperatorConfirmationHardening(unittest.TestCase):
    def test_confirmation_never_mints_an_unprovable_receipt(self):
        package = ppc.prepare_assisted_placement("facebook", "personal", PLACEMENT)
        bad = [
            ("no placement_id", dict(package, placement_id=None), {}),
            ("blank placement_id", dict(package, placement_id="   "), {}),
            ("claims published", dict(package, published=True), {}),
            ("claims published_by_system", dict(package, published_by_system=True), {}),
            ("unparseable confirmed_at", package, {"confirmed_at": "yesterday"}),
            ("never prepared", {
                "placement_id": "plc_minted", "route": "assisted",
                "account_type": "personal", "personal_profile": True,
                "status": "awaiting-operator", "published_by_system": False,
            }, {}),
        ]
        for name, pkg, extra in bad:
            with self.assertRaises(ppc.CapabilityError, msg=name):
                ppc.record_operator_confirmation(pkg, "Operator Name", **extra)

    def test_receipt_must_bind_to_the_records_placement(self):
        ghost = {
            "placement_id": None,
            "route": "assisted",
            "channel": "facebook",
            "account_type": "personal",
            "personal_profile": True,
            "status": "operator-confirmed",
            "receipt": {
                "placement_id": "plc_somewhere_else",
                "operator": "Operator Name",
                "confirmed_at": "2026-10-24T15:00:00Z",
                "method": "operator-asserted",
            },
        }
        for fn in (ppc.status_surface, ppc.assert_truthful_publication):
            with self.assertRaises(ppc.UntruthfulPublication):
                fn(ghost)

    def test_confirmation_result_is_accepted_by_its_own_guard(self):
        package = ppc.prepare_assisted_placement("facebook", "personal", PLACEMENT)
        confirmed = ppc.record_operator_confirmation(
            package, "Operator Name", confirmed_at="2026-10-24T15:00:00Z"
        )
        self.assertTrue(ppc.assert_truthful_publication(confirmed))
        surface = ppc.status_surface(confirmed)
        self.assertEqual(surface["claim"], "operator-confirmed")
        self.assertFalse(surface["published_by_system"])
        self.assertEqual(surface["receipt"]["placement_id"], package["placement_id"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
