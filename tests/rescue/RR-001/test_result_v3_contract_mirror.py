#!/usr/bin/env python3
"""RR-001 — ONB mirror drift guard for the rescue result v3 contract.

The canonical contract lives in the FLEET repo (blackceo-fleet-ops) at the FLAT
path `rescue/result-v3.schema.json`. OpenClaw Onboarding carries a PUBLIC
RECEIVER SUBSET of it at `65-rescue-receiver/contracts/result-v3.schema.json`.
The mirror is pinned by its own `x-canonical` block (repo + path + $id +
version + sha256), so a drift in the mirror's own pointer, in the pin, or in
the canonical file it names is detectable without network access.

CONTRACT OF THIS TEST (deliberate, not incidental):
  * FLEET repo ABSENT  -> SKIP, with a NAMED reason. A developer checking out
    only the ONB repo must not get a red run for a file they cannot see.
  * FLEET repo PRESENT and the mirror DRIFTS -> FAIL. Never a silent skip:
    "skip" is reserved for "cannot check", never for "checked and unhappy".
  * FLEET repo PRESENT and the pin AGREES -> PASS.

Wired into the repo's python test convention (`test_*.py`, `unittest`), so
`python3 -m unittest discover` and a bare `python3 tests/rescue/RR-001/
test_result_v3_contract_mirror.py` both work.

FLEET location resolution order (first that exists wins):
  1. $RR_FLEET_REPO (explicit override; also used by CI to point at a checkout)
  2. sibling directory of the ONB repo root named `blackceo-fleet-ops`
     (this is how the two repos sit side by side in ~ on the operator box)
  3. ~/blackceo-fleet-ops

There is deliberately NO hard-coded absolute operator path: a repo test that
can only resolve one machine's layout cannot be run anywhere else, and it would
make the absent-FLEET SKIP branch unreachable (and therefore untested) on the
very box it was written for.
"""
import hashlib
import json
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ONB_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))

MIRROR_REL = os.path.join("65-rescue-receiver", "contracts", "result-v3.schema.json")
MIRROR_PATH = os.path.join(ONB_ROOT, MIRROR_REL)

# The conduit decision this test enforces: the canonical path is FLAT.
CANON_PATH = "rescue/result-v3.schema.json"
FLEET_REPO = "blackceo-fleet-ops"


def _find_fleet_repo():
    """Locate the FLEET checkout, or None when it is genuinely not present."""
    candidates = []
    env = os.environ.get("RR_FLEET_REPO")
    if env:
        candidates.append(env)
    candidates.append(os.path.join(os.path.dirname(ONB_ROOT), FLEET_REPO))
    candidates.append(os.path.expanduser(os.path.join("~", FLEET_REPO)))
    for c in candidates:
        if c and os.path.exists(os.path.join(c, "rescue")):
            return c
    return None


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


class TestResultV3ContractMirror(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fleet = _find_fleet_repo()

    def _mirror(self):
        if not os.path.isfile(MIRROR_PATH):
            self.fail("mirror missing at %s" % MIRROR_REL)
        return _load_json(MIRROR_PATH)

    def _canonical_path(self):
        return os.path.join(self.fleet, CANON_PATH)

    # -- the skip: only when the canonical repo cannot be read --------------
    def _require_fleet(self):
        if not self.fleet:
            self.skipTest(
                "RR-001 drift check SKIPPED: FLEET repo %r not found "
                "(looked at $RR_FLEET_REPO, the sibling dir of %s, and ~/%s). "
                "The mirror's canonical contract lives at %s inside FLEET; "
                "without that checkout this cross-repo pin cannot be verified. "
                "This is a MISSING DEPENDENCY, not a passing check."
                % (FLEET_REPO, ONB_ROOT, FLEET_REPO, CANON_PATH)
            )

    # ------------------------------------------------------------------
    # 1. THE PIN ITSELF — the mirror's own x-canonical pointer
    # ------------------------------------------------------------------
    def test_mirror_declares_the_flat_canonical_path(self):
        """x-canonical.path must name the FLAT canonical path, not the old
        rescue/contracts/ location."""
        xc = self._mirror().get("x-canonical")
        self.assertIsInstance(xc, dict, "mirror carries no x-canonical pin block")
        self.assertEqual(
            xc.get("path"), CANON_PATH,
            "x-canonical.path drifted from the conduit-decided FLAT canonical "
            "path %r (got %r)" % (CANON_PATH, xc.get("path")),
        )
        self.assertNotIn(
            "rescue/contracts/", str(xc.get("path")),
            "x-canonical.path still names the retired rescue/contracts/ location",
        )

    def test_mirror_canonical_id_matches_flat_path(self):
        xc = self._mirror().get("x-canonical") or {}
        self.assertEqual(xc.get("$id"), CANON_PATH,
                         "x-canonical.$id must equal the FLAT canonical path")
        self.assertEqual(xc.get("repo"), FLEET_REPO,
                         "x-canonical.repo must be %r" % FLEET_REPO)

    def test_mirror_description_names_the_flat_path(self):
        desc = self._mirror().get("description", "")
        self.assertIn(CANON_PATH, desc,
                      "mirror description must name the canonical FLAT path")
        self.assertNotIn("rescue/contracts/", desc,
                         "mirror description still names the retired path")

    # ------------------------------------------------------------------
    # 2. THE VERSION PIN
    # ------------------------------------------------------------------
    def test_mirror_pins_version_and_agrees_with_canonical(self):
        self._require_fleet()
        m = self._mirror()
        mc = m.get("x-canonical") or {}
        canon_path = self._canonical_path()
        if not os.path.isfile(canon_path):
            self.fail("canonical contract missing at %s in FLEET" % CANON_PATH)
        canon = _load_json(canon_path)
        self.assertEqual(
            mc.get("version"), canon.get("version"),
            "mirror pins version %r but canonical is %r"
            % (mc.get("version"), canon.get("version")),
        )
        self.assertEqual(
            m.get("version"), canon.get("version"),
            "mirror's own version %r disagrees with canonical %r"
            % (m.get("version"), canon.get("version")),
        )

    # ------------------------------------------------------------------
    # 3. THE DIGEST PIN — the whole point of a pin
    # ------------------------------------------------------------------
    def test_mirror_digest_pin_matches_canonical_bytes(self):
        self._require_fleet()
        mc = self._mirror().get("x-canonical") or {}
        pin = mc.get("sha256")
        self.assertTrue(
            pin, "mirror x-canonical carries no sha256 digest pin; a digest "
                 "that is not re-computed after an edit is a defect"
        )
        canon_path = self._canonical_path()
        if not os.path.isfile(canon_path):
            self.fail("canonical contract missing at %s in FLEET" % CANON_PATH)
        actual = _sha256_file(canon_path)
        self.assertEqual(
            pin, actual,
            "MIRROR DRIFT: x-canonical.sha256 is %s but FLEET %s hashes to %s "
            "-- the canonical contract changed and the mirror pin was not "
            "re-stamped" % (pin, CANON_PATH, actual),
        )

    # ------------------------------------------------------------------
    # 4. THE SUBSET INVARIANT — the mirror may not invent requirements
    # ------------------------------------------------------------------
    def test_mirror_is_a_subset_of_canonical(self):
        """Canonical must be a SUPERSET of the mirror: every property and
        every required entry the mirror demands has to exist canonically."""
        self._require_fleet()
        canon_path = self._canonical_path()
        if not os.path.isfile(canon_path):
            self.fail("canonical contract missing at %s in FLEET" % CANON_PATH)
        mirror = self._mirror()
        canon = _load_json(canon_path)
        cprops = set((canon.get("properties") or {}).keys())
        mprops = set((mirror.get("properties") or {}).keys())
        invented = sorted(mprops - cprops)
        self.assertEqual(
            invented, [],
            "mirror declares properties absent from canonical: %s" % invented,
        )
        mreq = set(mirror.get("required") or [])
        creq = set(canon.get("required") or [])
        missing = sorted(mreq - creq)
        self.assertEqual(
            missing, [],
            "mirror requires fields canonical does not require: %s" % missing,
        )
        mc = mirror.get("x-canonical") or {}
        self.assertEqual(
            sorted(mc.get("required") or []), sorted(mreq),
            "x-canonical.required disagrees with the mirror's own required list",
        )
        for field in ("repair_status", "verification_status"):
            mvals = set(((mirror.get("properties") or {}).get(field) or {}).get("enum") or [])
            cvals = set(((canon.get("properties") or {}).get(field) or {}).get("enum") or [])
            extra = sorted(mvals - cvals)
            self.assertEqual(
                extra, [],
                "mirror's %s enum carries values canonical does not: %s"
                % (field, extra),
            )

    # ------------------------------------------------------------------
    # 5. THE CONDUIT DECISION, ENFORCED
    # ------------------------------------------------------------------
    def test_canonical_is_flat_and_no_contracts_dir(self):
        """The canonical contract must sit at the FLAT path, and the retired
        rescue/contracts/ directory must not exist in FLEET."""
        self._require_fleet()
        self.assertTrue(
            os.path.isfile(self._canonical_path()),
            "canonical contract is not at the FLAT path %s" % CANON_PATH,
        )
        retired = os.path.join(self.fleet, "rescue", "contracts")
        self.assertFalse(
            os.path.isdir(retired),
            "retired rescue/contracts/ directory still exists in FLEET; the "
            "canonical path is FLAT",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
