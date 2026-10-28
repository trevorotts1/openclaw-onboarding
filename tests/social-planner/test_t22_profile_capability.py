#!/usr/bin/env python3
"""test_t22_profile_capability.py — T-22 honest personal-profile capability
and assisted contract.

Covers the four required behaviours:
  1. an unattended personal-profile request is refused with a clear reason and
     an assisted offer (no silent downgrade, no fake success);
  2. the assisted route produces a receipt ONLY after an operator confirmation;
  3. a system-claimed publication without an operator receipt FAILS the guard;
  4. the capability data round-trips and is the single source consumed by the
     status surface.

Run:  python3 -m unittest tests/social-planner/test_t22_profile_capability.py -v
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

_ONB_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SHARED = os.path.join(_ONB_ROOT, "shared-utils")
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

import personal_profile_capability as ppc  # noqa: E402

CAPABILITIES = os.path.join(
    _ONB_ROOT, "35-social-media-planner", "config", "profile-capabilities.json"
)
CLI = os.path.join(
    _ONB_ROOT, "35-social-media-planner", "scripts", "profile_capability.py"
)

PLACEMENT = {
    "text": "Three of Seven: the part nobody tells you about pricing.",
    "asset": {"type": "image", "url": "https://assets.cdn.filesafe.space/test/media/pricing.png"},
    "keyword": "PRICING",
    "cta": "Comment PRICING and we will send the guide.",
    "timing": {"date": "2026-10-27", "local_time": "09:15", "timezone": "America/Chicago"},
}


def _declaration():
    with open(CAPABILITIES, encoding="utf-8") as handle:
        return json.load(handle)


def _personal_accounts():
    caps = _declaration()
    for channel_id, channel in caps["channels"].items():
        for account_id, account in channel["account_types"].items():
            if account.get("personal_profile"):
                yield channel_id, account_id, account


class TestUnattendedRefusal(unittest.TestCase):
    def test_every_personal_profile_refuses_unattended(self):
        caps = _declaration()
        for channel_id, account_id, account in _personal_accounts():
            action = (account.get("operator_action") or account.get("unavailable") or ["post"])[0]
            result = ppc.request_placement(
                channel_id, account_id, action=action, unattended=True
            )
            self.assertTrue(result["refused"], f"{channel_id}/{account_id} accepted unattended")
            self.assertEqual(result["route"], "refused")
            if account.get("mode") == "unavailable":
                self.assertEqual(result["reason_code"], "capability_unavailable")
            else:
                self.assertEqual(result["reason_code"], "unattended_not_supported")
                self.assertEqual(result["reason"], caps["policy"]["refusal_language"])
                self.assertIn("no supported public posting", result["reason"])
            if account.get("operator_action"):
                self.assertIsNotNone(result["offer"], f"{channel_id}/{account_id}")
                self.assertEqual(result["offer"]["route"], "assisted")
            else:
                self.assertIsNone(result["offer"])
            self.assertTrue(result["no_silent_downgrade"])

    def test_unavailable_personal_profile_refused_without_offer(self):
        result = ppc.request_placement(
            "google-business-profile", "personal", action="update", unattended=True
        )
        self.assertTrue(result["refused"])
        self.assertEqual(result["reason_code"], "capability_unavailable")
        self.assertIsNone(result["offer"])

    def test_declaration_never_marks_personal_automated(self):
        for channel_id, account_id, account in _personal_accounts():
            self.assertEqual(account["unattended"], [], f"{channel_id}/{account_id}")
            self.assertNotEqual(account["mode"], "unattended", f"{channel_id}/{account_id}")


class TestAssistedReceipt(unittest.TestCase):
    def test_receipt_only_after_operator_confirmation(self):
        requested = ppc.request_placement(
            "facebook", "personal", action="post", placement=PLACEMENT
        )
        self.assertTrue(requested["ok"])
        self.assertEqual(requested["route"], "assisted")
        package = requested["package"]
        self.assertEqual(package["status"], "awaiting-operator")
        self.assertIsNone(package["receipt"])
        self.assertFalse(package["published_by_system"])
        for field in ("text", "asset", "keyword", "cta", "timing"):
            self.assertIn(field, package["placement"])
        self.assertTrue(package["operator_action"]["instruction"])

        with self.assertRaises(ppc.CapabilityError):
            ppc.record_operator_confirmation(package, "")
        with self.assertRaises(ppc.CapabilityError):
            ppc.record_operator_confirmation(package, "   ")

        awaiting = ppc.status_surface(package)
        self.assertEqual(awaiting["status"], "awaiting-operator")
        self.assertFalse(awaiting["published_by_system"])
        self.assertIsNone(awaiting["receipt"])

        confirmed = ppc.record_operator_confirmation(
            package, "Operator Name", confirmed_at="2026-10-24T15:00:00Z"
        )
        self.assertEqual(confirmed["status"], "operator-confirmed")
        self.assertFalse(confirmed["published_by_system"])
        receipt = confirmed["receipt"]
        self.assertEqual(receipt["placement_id"], package["placement_id"])
        self.assertEqual(receipt["operator"], "Operator Name")
        self.assertEqual(receipt["confirmed_at"], "2026-10-24T15:00:00Z")
        self.assertEqual(receipt["method"], "operator-asserted")

        surface = ppc.status_surface(confirmed)
        self.assertEqual(surface["status"], "operator-confirmed")
        self.assertEqual(surface["claim"], "operator-confirmed")
        self.assertFalse(surface["published_by_system"])
        self.assertEqual(surface["label"], _declaration()["policy"]["assisted_statuses"]["operator-confirmed"])

    def test_operator_confirmation_requires_awaiting_placement(self):
        package = ppc.prepare_assisted_placement("facebook", "personal", PLACEMENT)
        confirmed = ppc.record_operator_confirmation(package, "Operator Name")
        with self.assertRaises(ppc.CapabilityError):
            ppc.record_operator_confirmation(confirmed, "Operator Name")

    def test_placement_requires_all_prepared_fields(self):
        for missing in ("text", "asset", "keyword", "cta", "timing"):
            broken = dict(PLACEMENT)
            broken.pop(missing)
            with self.assertRaises(ppc.CapabilityError):
                ppc.prepare_assisted_placement("facebook", "personal", broken)


class TestPublicationGuard(unittest.TestCase):
    def test_published_by_system_is_forbidden_for_assisted(self):
        package = ppc.prepare_assisted_placement("facebook", "personal", PLACEMENT)
        lying = dict(package, status="published-by-system")
        with self.assertRaises(ppc.UntruthfulPublication):
            ppc.status_surface(lying)

    def test_bare_published_status_is_forbidden_for_assisted(self):
        package = ppc.prepare_assisted_placement("facebook", "personal", PLACEMENT)
        lying = dict(package, status="published")
        with self.assertRaises(ppc.UntruthfulPublication):
            ppc.assert_truthful_publication(lying)

    def test_system_publication_claim_without_receipt_fails(self):
        package = ppc.prepare_assisted_placement("facebook", "personal", PLACEMENT)
        claims = [
            dict(package, published_by_system=True),
            dict(package, published=True),
            dict(package, status="operator-confirmed", receipt=None),
        ]
        for record in claims:
            with self.assertRaises(ppc.UntruthfulPublication, msg=str(record)):
                ppc.assert_truthful_publication(record)

    def test_awaiting_operator_cannot_carry_receipt(self):
        package = ppc.prepare_assisted_placement("facebook", "personal", PLACEMENT)
        confirmed = ppc.record_operator_confirmation(package, "Operator Name")
        contradictory = dict(confirmed, status="awaiting-operator")
        with self.assertRaises(ppc.UntruthfulPublication):
            ppc.assert_truthful_publication(contradictory)

    def test_personal_never_uses_unattended_route(self):
        lying = {
            "placement_id": "plc_fake",
            "route": "unattended",
            "channel": "facebook",
            "account_type": "personal",
            "personal_profile": True,
            "status": "published-by-system",
            "published_by_system": True,
        }
        with self.assertRaises(ppc.UntruthfulPublication):
            ppc.assert_truthful_publication(lying)

    def test_honest_receipt_passes_guard(self):
        package = ppc.prepare_assisted_placement("facebook", "personal", PLACEMENT)
        confirmed = ppc.record_operator_confirmation(package, "Operator Name")
        self.assertTrue(ppc.assert_truthful_publication(confirmed))


class TestSingleSourceRoundTrip(unittest.TestCase):
    def test_module_matches_declaration_for_every_channel_and_account(self):
        caps = _declaration()
        seen = 0
        for channel_id, channel in caps["channels"].items():
            for account_id, account in channel["account_types"].items():
                capability = ppc.get_capability(channel_id, account_id)
                self.assertEqual(capability["mode"], account["mode"])
                self.assertEqual(capability["personal_profile"], bool(account["personal_profile"]))
                self.assertEqual(capability["unattended"], account["unattended"])
                self.assertEqual(capability["operator_action"], account["operator_action"])
                self.assertEqual(capability["unavailable"], account["unavailable"])
                self.assertEqual(capability["checked_at"], channel["checked_at"])
                seen += 1
        summary = ppc.capability_summary()
        self.assertEqual(summary["version"], caps["policy"]["version"])
        self.assertEqual(summary["source"], caps["policy"]["single_source_of_truth"])
        self.assertEqual(len(summary["records"]), seen)

    def test_status_vocabulary_comes_from_the_declaration(self):
        caps = _declaration()
        package = ppc.prepare_assisted_placement("facebook", "personal", PLACEMENT)
        surface = ppc.status_surface(package)
        self.assertEqual(
            surface["label"], caps["policy"]["assisted_statuses"]["awaiting-operator"]
        )
        self.assertEqual(
            sorted(ppc.load_capabilities()["policy"]["assisted_statuses"]),
            sorted(["awaiting-operator", "operator-confirmed"]),
        )

    def test_declaration_path_is_the_documented_single_source(self):
        caps = _declaration()
        self.assertEqual(
            caps["policy"]["single_source_of_truth"],
            "35-social-media-planner/config/profile-capabilities.json",
        )
        self.assertEqual(os.path.abspath(ppc.CAPABILITIES_PATH), os.path.abspath(CAPABILITIES))


class TestCapabilityCli(unittest.TestCase):
    def _run(self, *args, cwd=_ONB_ROOT):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run(
            [sys.executable, CLI, *args],
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )

    def test_cli_refuses_unattended_and_confirms_assisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            placement_path = os.path.join(tmp, "placement.json")
            with open(placement_path, "w", encoding="utf-8") as handle:
                json.dump(PLACEMENT, handle)

            refused = self._run(
                "request", "--channel", "facebook", "--account-type", "personal",
                "--action", "post", "--placement", placement_path, "--unattended",
            )
            self.assertEqual(refused.returncode, 3, refused.stderr)
            payload = json.loads(refused.stdout)
            self.assertTrue(payload["refused"])
            self.assertEqual(payload["offer"]["route"], "assisted")

            prepared = self._run(
                "request", "--channel", "facebook", "--account-type", "personal",
                "--action", "post", "--placement", placement_path,
            )
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            package = json.loads(prepared.stdout)["package"]
            self.assertEqual(package["status"], "awaiting-operator")
            package_path = os.path.join(tmp, "package.json")
            with open(package_path, "w", encoding="utf-8") as handle:
                json.dump(package, handle)

            status = self._run("status", "--package", package_path)
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertEqual(json.loads(status.stdout)["status"], "awaiting-operator")

            confirmed = self._run(
                "confirm", "--package", package_path, "--operator", "Operator Name",
                "--confirmed-at", "2026-10-24T15:00:00Z",
            )
            self.assertEqual(confirmed.returncode, 0, confirmed.stderr)
            surface = json.loads(confirmed.stdout)
            self.assertEqual(surface["status"], "operator-confirmed")
            self.assertFalse(surface["published_by_system"])

            lying_path = os.path.join(tmp, "lying.json")
            with open(lying_path, "w", encoding="utf-8") as handle:
                json.dump(dict(package, status="published-by-system"), handle)
            guard = self._run("guard", "--record", lying_path)
            self.assertEqual(guard.returncode, 4, guard.stderr)
            self.assertFalse(json.loads(guard.stdout)["ok"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
