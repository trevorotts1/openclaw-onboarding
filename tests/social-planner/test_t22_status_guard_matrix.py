#!/usr/bin/env python3
"""test_t22_status_guard_matrix.py — T-22 read-path / guard agreement.

`status_surface` (the read path) and `assert_truthful_publication` (the guard)
must agree in BOTH directions for every combination of route, account_type,
personal_profile, status and receipt presence: never one blessing a claim the
other refuses, and never one refusing a claim the other blesses.

Both now delegate to the same truth evaluator, so agreement is structural; this
matrix is the proof that it holds, plus the known-good controls where a sanctioned
assisted placement passes both and an unattended publication is refused because
its coverage is unproved (B-04).

Run:  python3 -m unittest tests/social-planner/test_t22_status_guard_matrix.py -v
"""

import atexit
import copy
import hashlib
import hmac
import itertools
import json
import os
import shutil
import sys
import tempfile
import unittest

_ONB_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SHARED = os.path.join(_ONB_ROOT, "shared-utils")
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

# The provenance signing key is per installation and lives outside the repository.
# Point it at a per-run temporary directory so the suite is hermetic and never
# writes to the operator's real state directory.
_KEY_DIR = tempfile.mkdtemp(prefix="ppc-seal-")
atexit.register(shutil.rmtree, _KEY_DIR, ignore_errors=True)
os.environ.setdefault(
    "PERSONAL_PROFILE_CAPABILITY_SEAL_KEY_FILE", os.path.join(_KEY_DIR, "seal.key")
)

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

    def test_known_good_assisted_placements_pass_both_and_unattended_is_not_claimed(self):
        """B-04: only the assisted paths are proved here.

        No public monitor runs in this contract, so no unattended publication is
        certified — coverage is 'unproved' and the refusal names the proof needed
        and the owner who must decide it.
        """
        confirmed = ppc.record_operator_confirmation(
            ppc.prepare_assisted_placement("threads", "business", PLACEMENT),
            "Operator Name",
            confirmed_at="2026-10-24T15:00:00Z",
        )
        awaiting = ppc.prepare_assisted_placement("facebook", "personal", PLACEMENT)
        for record in (confirmed, awaiting):
            surface = ppc.status_surface(record)
            self.assertTrue(ppc.assert_truthful_publication(record), repr(record))
            self.assertEqual(surface["status"], record["status"])
            self.assertFalse(surface["published_by_system"])
            self.assertEqual(surface["provenance"], "sanctioned")
        self.assertEqual(ppc.status_surface(confirmed)["claim"], "operator-confirmed")
        self.assertEqual(ppc.status_surface(awaiting)["claim"], "nothing-posted")

        # A hand-built page publication is refused: this contract monitors nothing.
        page = {
            "placement_id": "plc_page",
            "route": "unattended",
            "channel": "facebook",
            "account_type": "page",
            "personal_profile": False,
            "status": "published-by-system",
            "receipt": None,
        }
        for fn in (ppc.status_surface, ppc.assert_truthful_publication):
            with self.assertRaises(ppc.UntruthfulPublication) as caught:
                fn(page)
            self.assertIn("coverage is 'unproved'", str(caught.exception))
            self.assertIn("Owner who must decide it", str(caught.exception))

        coverage = ppc.unattended_coverage()
        self.assertEqual(coverage["status"], "unproved")
        self.assertFalse(coverage["monitoring"])
        self.assertEqual(coverage["claim"], "coverage-unproved")
        self.assertTrue(coverage["required_proof"])
        self.assertTrue(coverage["owner_decision"]["owner"])
        self.assertTrue(coverage["owner_decision"]["decision"])
        self.assertEqual(coverage["owner_decision"]["status"], "pending")


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

    def test_fabricated_placement_id_is_refused_everywhere(self):
        """T-22c: a receipt is proof only when the placement_id recomputes."""
        package = ppc.prepare_assisted_placement("facebook", "personal", PLACEMENT)
        for fake_id in ("plc_minted", "anything-at-all", "plc_matrix"):
            forged_package = dict(package, placement_id=fake_id)
            with self.assertRaises(ppc.CapabilityError, msg=fake_id):
                ppc.record_operator_confirmation(forged_package, "Operator Name")
            forged = dict(
                forged_package,
                status="operator-confirmed",
                receipt={
                    "placement_id": fake_id,
                    "operator": "Operator Name",
                    "confirmed_at": "2026-10-24T15:00:00Z",
                    "method": "operator-asserted",
                },
            )
            for fn in (ppc.status_surface, ppc.assert_truthful_publication):
                with self.assertRaises(
                    ppc.UntruthfulPublication, msg=f"{fn.__name__}/{fake_id}"
                ):
                    fn(forged)

    def test_confirm_requires_the_digest_inputs(self):
        package = ppc.prepare_assisted_placement("facebook", "personal", PLACEMENT)
        for field in ("channel", "account_type", "action", "placement"):
            stripped = dict(package)
            stripped.pop(field)
            with self.assertRaises(ppc.CapabilityError, msg=field):
                ppc.record_operator_confirmation(stripped, "Operator Name")

    def test_placement_field_types_are_enforced(self):
        typed = {"text": 1, "asset": 1, "keyword": 1, "cta": 1, "timing": 1}
        with self.assertRaises(ppc.CapabilityError):
            ppc.prepare_assisted_placement("facebook", "personal", typed)
        package = ppc.prepare_assisted_placement("facebook", "personal", PLACEMENT)
        with self.assertRaises(ppc.CapabilityError):
            ppc.record_operator_confirmation(
                dict(package, placement=dict(typed)), "Operator Name"
            )


class TestArbitraryDictCannotMint(unittest.TestCase):
    """B-27: authority is minted only by the sanctioned constructor.

    Every attack here is a caller-supplied dict. The forged placement id is
    recomputed from public knowledge (the same canonical digest), so the tests do
    not depend on a private helper to show what an attacker can build.
    """

    def _forged_placement_id(self, channel="instagram", account_type="personal", action="post"):
        payload = json.dumps(
            {
                "channel": channel,
                "account_type": account_type,
                "action": action,
                "placement": PLACEMENT,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            default=str,
        )
        return "plc_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def _forged_package(self):
        return {
            "placement_id": self._forged_placement_id(),
            "channel": "instagram",
            "account_type": "personal",
            "action": "post",
            "route": "assisted",
            "status": "awaiting-operator",
            "placement": PLACEMENT,
            "receipt": None,
            "published_by_system": False,
        }

    def test_hand_built_package_cannot_become_an_approval(self):
        with self.assertRaises(ppc.CapabilityError) as caught:
            ppc.record_operator_confirmation(self._forged_package(), "Operator Name")
        self.assertIn("sanctioned provenance marker", str(caught.exception))

    def test_hand_built_operator_confirmed_record_is_refused_by_both(self):
        forged = dict(
            self._forged_package(),
            status="operator-confirmed",
            receipt={
                "placement_id": self._forged_placement_id(),
                "operator": "Operator Name",
                "confirmed_at": "2026-10-24T15:00:00Z",
                "method": "operator-asserted",
            },
        )
        for fn in (ppc.status_surface, ppc.assert_truthful_publication):
            with self.assertRaises(ppc.UntruthfulPublication, msg=fn.__name__):
                fn(forged)

    def test_a_copied_marker_does_not_fit_an_edited_record(self):
        package = ppc.prepare_assisted_placement("facebook", "personal", PLACEMENT)
        edited = dict(
            package,
            status="operator-confirmed",
            receipt={
                "placement_id": package["placement_id"],
                "operator": "Operator Name",
                "confirmed_at": "2026-10-24T15:00:00Z",
                "method": "operator-asserted",
            },
        )
        self.assertIn("provenance", edited)  # the marker travels with the copy
        for fn in (ppc.status_surface, ppc.assert_truthful_publication):
            with self.assertRaises(ppc.UntruthfulPublication, msg=fn.__name__):
                fn(edited)

    def test_undeclared_account_type_cannot_mint_a_publication(self):
        forged = {
            "placement_id": "plc_made_up",
            "channel": "instagram",
            "account_type": "brand",  # never declared; launders a personal profile
            "route": "unattended",
            "status": "published-by-system",
            "account_label": "Instagram personal profile",
        }
        for fn in (ppc.status_surface, ppc.assert_truthful_publication):
            with self.assertRaises(ppc.CapabilityError, msg=fn.__name__) as caught:
                fn(forged)
            self.assertIn("no declared account type", str(caught.exception))

    def test_route_the_declaration_does_not_grant_is_refused(self):
        # facebook/page is declared unattended; a hand-built assisted record for
        # it must not be renderable.
        forged = {
            "placement_id": "plc_made_up",
            "channel": "facebook",
            "account_type": "page",
            "route": "assisted",
            "status": "awaiting-operator",
            "receipt": None,
        }
        for fn in (ppc.status_surface, ppc.assert_truthful_publication):
            with self.assertRaises(ppc.CapabilityError, msg=fn.__name__):
                fn(forged)

    def test_record_with_no_placement_cannot_render_a_status(self):
        for fn in (ppc.status_surface, ppc.assert_truthful_publication):
            with self.assertRaises(ppc.CapabilityError, msg=fn.__name__):
                fn({"route": "assisted", "status": "awaiting-operator"})

    def test_refusal_path_takes_no_caller_capability(self):
        """A forged capability dict has no door left: _refusal resolves its own."""
        import inspect

        params = inspect.signature(ppc._refusal).parameters
        self.assertNotIn("capability", params)
        refused = ppc.request_placement(
            "instagram", "personal", action="post", unattended=True
        )
        self.assertTrue(refused["refused"])
        self.assertEqual(refused["capability"], ppc.get_capability("instagram", "personal"))

    def test_sanctioned_values_still_work(self):
        """Inverse control: the legitimate constructor path is untouched."""
        package = ppc.prepare_assisted_placement("instagram", "personal", PLACEMENT)
        awaiting = ppc.status_surface(package)
        self.assertEqual(awaiting["claim"], "nothing-posted")
        self.assertEqual(awaiting["provenance"], "sanctioned")
        confirmed = ppc.record_operator_confirmation(
            package, "Operator Name", confirmed_at="2026-10-24T15:00:00Z"
        )
        surface = ppc.status_surface(confirmed)
        self.assertEqual(surface["claim"], "operator-confirmed")
        self.assertEqual(surface["provenance"], "sanctioned")
        self.assertFalse(surface["published_by_system"])
        self.assertTrue(ppc.assert_truthful_publication(confirmed))


def _public_placement_id(channel="facebook", account_type="personal", action="post"):
    """The placement id an outside caller can compute from public knowledge."""
    payload = json.dumps(
        {
            "channel": channel,
            "account_type": account_type,
            "action": action,
            "placement": PLACEMENT,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )
    return "plc_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class TestMarkerIsNotReconstructible(unittest.TestCase):
    """B-27 class: the marker must not be derivable from shipped bytes.

    The 3.9.0 marker key was `sha256(domain + b"\\x00" + declaration)`. Both inputs
    ship in the repository, so any caller with stdlib `hashlib` + `hmac` could mint
    a marker on a hand-built dict without importing the module. These two pins fail
    if that derivation ever comes back, and fail if a marker computed from shipped
    bytes — at the CURRENT marker version, over the current payload shape — is
    accepted.
    """

    DOMAIN = b"personal-profile-capability/seal-v1"

    def _public_key(self):
        declaration = os.path.join(
            _ONB_ROOT, "35-social-media-planner", "config", "profile-capabilities.json"
        )
        with open(declaration, "rb") as handle:
            return hashlib.sha256(self.DOMAIN + b"\x00" + handle.read()).digest()

    def _marker(self, record, key, version):
        body = {k: v for k, v in record.items() if k != "provenance"}
        payload = json.dumps(
            body, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
        return {
            "algorithm": "hmac-sha256",
            "version": version,
            "mac": hmac.new(key, payload, hashlib.sha256).hexdigest(),
        }

    def _hand_built(self):
        return {
            "placement_id": _public_placement_id(),
            "channel": "facebook",
            "channel_label": "Facebook",
            "account_type": "personal",
            "account_label": "Personal Facebook profile",
            "action": "post",
            "route": "assisted",
            "status": "awaiting-operator",
            "placement": copy.deepcopy(PLACEMENT),
            "operator_action": {
                "step": "one-step-manual-action",
                "instruction": "ATTACKER INSTRUCTION",
                "expected_action": "post",
            },
            "receipt": None,
            "published_by_system": False,
            "capability_ref": {
                "checked_at": "2026-10-24",
                "source_urls": ["https://attacker.example/proof"],
            },
        }

    def test_installation_key_is_not_derived_from_shipped_bytes(self):
        self.assertNotEqual(ppc._installation_seal_key(), self._public_key())

    def test_public_key_cannot_mint_a_marker_at_the_current_version(self):
        record = self._hand_built()
        record["provenance"] = self._marker(record, self._public_key(), ppc._SEAL_VERSION)
        self.assertFalse(ppc._is_sanctioned(record))
        with self.assertRaises(ppc.CapabilityError):
            ppc.record_operator_confirmation(record, "Attacker Operator")

        confirmed = dict(
            self._hand_built(),
            status="operator-confirmed",
            receipt={
                "placement_id": _public_placement_id(),
                "operator": "Attacker Operator",
                "confirmed_at": "2026-10-24T15:00:00Z",
                "method": "operator-asserted",
            },
        )
        confirmed["provenance"] = self._marker(
            confirmed, self._public_key(), ppc._SEAL_VERSION
        )
        for fn in (ppc.status_surface, ppc.assert_truthful_publication):
            with self.assertRaises(ppc.UntruthfulPublication, msg=fn.__name__):
                fn(confirmed)

    def test_version_one_markers_are_refused(self):
        package = ppc.prepare_assisted_placement("facebook", "personal", PLACEMENT)
        package["provenance"]["version"] = 1
        self.assertFalse(ppc._is_sanctioned(package))


class TestSealCoversEveryRenderedField(unittest.TestCase):
    """B-27 class: a field that can be edited without breaking the seal is a defect.

    The 3.9.0 MAC covered route, channel, account_type, action, placement, status
    and the receipt core. `operator_action`, `capability_ref`, `channel_label` and
    `account_label` were outside it, so a copied marker fitted an edited record.
    The payload is now the whole record minus the marker; every mutation below must
    break the seal AND make the read path refuse the claim.
    """

    def _confirmed(self):
        return ppc.record_operator_confirmation(
            ppc.prepare_assisted_placement("facebook", "personal", PLACEMENT),
            "Operator Name",
            confirmed_at="2026-10-24T15:00:00Z",
        )

    def _edited(self, record, path, value):
        mutated = copy.deepcopy(record)
        target = mutated
        keys = path.split(".")
        for key in keys[:-1]:
            target = target[key]
        target[keys[-1]] = value
        return mutated

    def test_payload_covers_every_record_key(self):
        record = self._confirmed()
        covered = set(json.loads(ppc._seal_payload(record)))
        self.assertEqual(covered, set(record) - {"provenance"})
        for field in (
            "placement_id",
            "channel",
            "channel_label",
            "account_type",
            "account_label",
            "action",
            "route",
            "status",
            "placement",
            "operator_action",
            "receipt",
            "published_by_system",
            "capability_ref",
        ):
            self.assertIn(field, covered)

    def test_every_edit_breaks_the_seal_and_the_claim(self):
        record = self._confirmed()
        self.assertTrue(ppc._is_sanctioned(record))

        mutations = {
            "operator_action.instruction": self._edited(
                record, "operator_action.instruction", "ATTACKER"
            ),
            "capability_ref.checked_at": self._edited(
                record, "capability_ref.checked_at", "1999-01-01"
            ),
            "capability_ref.source_urls": self._edited(
                record, "capability_ref.source_urls", ["https://attacker.example"]
            ),
            "channel_label": self._edited(record, "channel_label", "ATTACKER CHANNEL"),
            "account_label": self._edited(
                record, "account_label", "VERIFIED BUSINESS PAGE"
            ),
            "placement.text": self._edited(record, "placement.text", "ATTACKER TEXT"),
            "receipt.operator": self._edited(record, "receipt.operator", "Someone Else"),
            "receipt.evidence": self._edited(record, "receipt.evidence", {"forged": True}),
            "status": self._edited(record, "status", "awaiting-operator"),
            "published_by_system": self._edited(record, "published_by_system", True),
            "route": self._edited(record, "route", "unattended"),
            "placement_id": self._edited(record, "placement_id", "plc_attacker"),
            "extra key added": dict(copy.deepcopy(record), smuggled="attacker"),
        }
        dropped = copy.deepcopy(record)
        dropped.pop("operator_action")
        mutations["operator_action (dropped)"] = dropped

        for name, mutated in mutations.items():
            self.assertFalse(ppc._is_sanctioned(mutated), name)
            for fn in (ppc.status_surface, ppc.assert_truthful_publication):
                with self.assertRaises(ppc.CapabilityError, msg=f"{fn.__name__}/{name}"):
                    fn(mutated)

    def test_sanctioned_record_still_survives_a_json_round_trip(self):
        """Inverse control: the seal travels with the record, not with the object."""
        record = self._confirmed()
        round_tripped = json.loads(json.dumps(record))
        self.assertTrue(ppc._is_sanctioned(round_tripped))
        self.assertEqual(ppc.status_surface(round_tripped)["claim"], "operator-confirmed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
