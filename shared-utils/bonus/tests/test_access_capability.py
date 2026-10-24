#!/usr/bin/env python3
"""Self-check for T-14 — bonus membership/access capability decision.

Pins every acceptance clause of the task record (R-13, C-14, C-F07) and the
refusal cases, so a future edit cannot quietly promote an unproved step to
"supported" or gate the original gift on the bonus lane.

  C-14  current official route/tenant requirements, mobile-only
        identity/token/recovery evidence or the EXACT capability block, and no
        fabricated API;
  C-F07 original gift proceeds while the bonus is unavailable.

Run: python3 -m unittest discover -s shared-utils/bonus/tests -v
     python3 -m unittest shared-utils.bonus.tests.test_access_capability -v
"""

from __future__ import annotations

import json
import os
import re
import sys
import unittest
from pathlib import Path

_TESTS = Path(__file__).resolve().parent
_BONUS = _TESTS.parent
_SHARED = _BONUS.parent
_REPO = _SHARED.parent
for _p in (str(_SHARED), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bonus import access_capability as ac  # noqa: E402


# --------------------------------------------------------------------------
# Fabricated-API detector
# --------------------------------------------------------------------------
# One place decides what an invented interface looks like. The route surface is
# searched for every shape; Python source is searched for the four that cannot
# be legitimate there. A dotted token is NOT searched in Python source because
# attribute access (`cap.transport.value`) is real Python — a smuggled operation
# id has to reach the returned surface to matter, and that surface is covered.

_URL = re.compile(r"https?://", re.I)
# `\s*`, not `\s+`: a verb glued to its path (`POST/memberships/grant`) is the
# same fabrication as a spaced one.
_VERB_PATH = re.compile(r"\b(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s*/\S*", re.I)
# A bare operation path, in two forms:
#   1. slash-led, delimited by whitespace, a quote or a value separator
#      (`"/memberships/grant"`). Always flagged.
#   2. identifier-prefixed: any [A-Za-z0-9_] run glued in front of the first
#      `/` (`v1/memberships/grant`, `memberships/grant`). Shape alone cannot
#      tell it from real prose (`memberships/communities`, `assisted/operator`),
#      so the world is closed: it passes only as file provenance or as one of
#      the reviewed slash tokens below. A new one fails until a human reviews it.
# The two forms cannot overlap, so form 1 flags exactly what it did before.
_BARE_PATH = re.compile(
    r"(?:^|(?<=[\s\"'=(:,]))/[A-Za-z0-9_{][A-Za-z0-9_\-{}/.]*"
    r"|(?<![A-Za-z0-9_\-.{}/])[A-Za-z0-9_{][A-Za-z0-9_\-.{}]*(?:/[A-Za-z0-9_\-.{}]*[A-Za-z0-9_}])+"
)
REVIEWED_SLASH_TOKENS = frozenset({
    "assisted/operator",
    "course/credential",
    "courses/memberships",
    "create/delete",
    "identity/grant/credential/SMS/resource",
    "login/credential",
    "Membership/course",
    "memberships/communities",
    "return/recovery",
    "shared-utils/ghl",
})
_SCHEMELESS_HOST = re.compile(r"\b(?:[a-z0-9][a-z0-9-]*\.)+[a-z][a-z0-9-]*(?::\d+)?/[A-Za-z0-9]")
_DOTTED_OPERATION = re.compile(r"\b[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+\b")
_FILE_SUFFIXES = (
    ".py", ".md", ".json", ".txt", ".sh", ".yml", ".yaml", ".toml", ".cfg",
    ".ini", ".html", ".js", ".ts", ".css", ".csv", ".xml", ".png", ".jpg",
)

# Every smuggle shape a fabricated interface has been seen to take. The scan
# must catch all of them; the table below is the proof it does.
#
# FIXTURES, NOT DELIVERABLE: these literals are attack inputs, and this test
# file is the only file in shared-utils/bonus/ allowed to carry an API-shaped
# string. `test_the_evidence_doc_carries_no_api_shape` and
# `test_module_source_carries_no_api_shape` keep the other files at zero.
SMUGGLE_SHAPES = (
    ("scheme url", "https://api.leadconnectorhq.com/v1/memberships/grant"),
    ("uppercase verb+path", "GET  /memberships/grant"),
    ("lowercase verb+path", "post /memberships/grant"),
    ("bare operation path", '"api": "/memberships/grant"'),
    ("schemeless host+path", "api.leadconnectorhq.com/v1/memberships/grant"),
    ("dotted operation id", '"api": "memberships.grant"'),
    # PBB-132 QC: an identifier glued in front of the `/` defeated every rule.
    ("glued uppercase verb+path", "POST/memberships/grant"),
    ("glued lowercase verb+path", "post/memberships/grant"),
    ("glued mixed-case verb+path", "Get/memberships/grant"),
    ("glued delete verb+path", "DELETE/memberships/grant"),
    ("version-prefixed path", "v1/memberships/grant"),
    ("api-prefixed path", "api/memberships/grant"),
    ("unprefixed operation path", "memberships/grant"),
    ("identifier-prefixed path", "x/memberships/grant"),
)

# Text that must NOT be flagged: real repo provenance and plain prose.
LEGITIMATE_TEXT = (
    "#!/usr/bin/env python3",
    '    _REGISTRY = f"{_GHL}/tools/engine/cli_anything/gohighlevel/public/operations.py"',
    "44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/public/operations.py",
    "shared-utils/ghl/capability_inventory.py",
    "05-ghl-setup/INSTRUCTIONS.md",
    "06-ghl-install-pages/tools/SELECTORS-LIVE-course.md",
    "36-ghl-mcp-setup/ghl-mcp-setup-full.md",
    "the assisted/operator path and the R-13 / DEC-16 authority",
    "select_route(OpClass.EXECUTE, resource=\"memberships\") returns []",
    "in the frozen v3 production spec, contact enrollment against an existing "
    "workflow is not authoring",
)


def _dotted_operation_hits(text):
    hits = []
    for match in _DOTTED_OPERATION.finditer(text):
        token = match.group(0)
        if token.lower().endswith(_FILE_SUFFIXES):
            continue  # a filename is provenance, not an operation id
        hits.append(token)
    return hits


def _api_shape_hits(text):
    """API shapes that cannot be legitimate in this module's source or surface."""
    hits = [f"url:{m.group(0)}" for m in _URL.finditer(text)]
    hits += [f"verb+path:{m.group(0)}" for m in _VERB_PATH.finditer(text)]
    for match in _BARE_PATH.finditer(text):
        token = match.group(0)
        if not token.startswith("/") and (
            token.lower().endswith(_FILE_SUFFIXES) or token in REVIEWED_SLASH_TOKENS
        ):
            continue  # file provenance or reviewed prose, not an operation
        hits.append(f"bare-path:{token}")
    hits += [f"host+path:{m.group(0)}" for m in _SCHEMELESS_HOST.finditer(text)]
    return hits


def _fabricated_api_hits(text):
    return _api_shape_hits(text) + [
        f"operation-id:{t}" for t in _dotted_operation_hits(text)
    ]


class _BlockImport:
    """meta_path finder that makes `import ghl...` genuinely raise ImportError."""

    def find_spec(self, fullname, path=None, target=None):
        if fullname == "ghl" or fullname.startswith("ghl."):
            raise ImportError(f"blocked for this test: {fullname}")
        return None


class TestCapabilityBlock(unittest.TestCase):
    """C-14: the exact block, announced rather than an invented interface."""

    def test_every_step_is_declared_exactly_once_in_order(self):
        self.assertEqual(list(ac.STEP_ORDER), ["identity", "grant", "credential", "return", "recovery"])
        self.assertEqual([e.step for e in ac.EVIDENCE], list(ac.STEP_ORDER))

    def test_all_five_steps_are_blocked_today(self):
        self.assertEqual(ac.blocked_steps(), list(ac.STEP_ORDER))

    def test_every_step_names_the_exact_missing_evidence(self):
        for step, row in ac.capability_evidence().items():
            self.assertFalse(row["routable"], f"{step} was promoted to routable")
            self.assertTrue(row["missing"], f"{step} names no missing evidence")
            for clause in row["missing"]:
                self.assertTrue(str(clause).strip(), f"{step} carries a blank missing clause")
            self.assertTrue(row["authority"], f"{step} cites no authority")
            self.assertTrue(row["claim"].strip(), f"{step} carries no claim")

    def test_every_provenance_file_exists_in_this_tree(self):
        for step, row in ac.capability_evidence().items():
            self.assertTrue(row["provenance"], f"{step} cites no provenance")
            for rel in row["provenance"]:
                self.assertFalse(os.path.isabs(rel), f"{step} provenance must be repo-relative: {rel}")
                self.assertTrue(
                    (_REPO / rel).is_file(), f"{step} provenance does not exist: {rel}"
                )

    def test_no_step_is_proved_or_claims_a_tenant_observation(self):
        for step, row in ac.capability_evidence().items():
            self.assertNotEqual(row["state"], ac.PROVED, step)
            self.assertNotIn("verified on this box", row["claim"].lower(), step)


class TestNoFabricatedApi(unittest.TestCase):
    """C-14: no fabricated API anywhere in the route surface."""

    def test_supported_route_exposes_no_api(self):
        route = ac.supported_route()
        self.assertIsNone(route["api"])
        self.assertTrue(route["no_invented_api"])
        self.assertNotIn("endpoint", route["supported_path"].lower())

    def test_route_values_contain_no_url_or_verb_path(self):
        blob = json.dumps(ac.supported_route(), sort_keys=True)
        self.assertIsNone(re.search(r"https?://", blob))
        self.assertIsNone(re.search(r"\b(?:GET|POST|PUT|PATCH|DELETE)\s+/[A-Za-z0-9{]", blob))

    def test_module_source_carries_no_url_or_verb_path(self):
        source = Path(ac.__file__).read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"https?://", source), "module carries a URL")
        self.assertIsNone(
            re.search(r"\b(?:GET|POST|PUT|PATCH|DELETE)\s+/[A-Za-z0-9{]", source),
            "module carries a verb+path operation",
        )

    def test_membership_family_has_no_route_in_the_shared_inventory(self):
        # Reuse of the upstream inventory, not a second local table.
        self.assertEqual(ac.membership_inventory_routes(), [])
        # Instrument control on the negative: the SAME call path answers
        # non-empty for a family the inventory does document, so the zero above
        # is discriminating and not a broken instrument reported as a block.
        from ghl import capability_inventory as inventory

        control = inventory.select_route(
            inventory.OpClass.EXECUTE, resource="workflows", dynamic_confirmed=False
        )
        self.assertTrue(
            control,
            "shared inventory answered nothing for a documented family — "
            "the memberships zero is a broken instrument, not a capability block",
        )

    def test_a_broken_reuse_path_fails_closed_and_is_never_a_capability_block(self):
        # A missing inventory is an instrument failure. Returning [] for it would
        # make a broken reuse path indistinguishable from a proven "no route".
        # The cached modules are dropped first so the import genuinely re-runs
        # and the blocker is what fails it, not a stale sys.modules entry.
        saved = {k: v for k, v in sys.modules.items() if k == "ghl" or k.startswith("ghl.")}
        for name in saved:
            del sys.modules[name]
        sys.meta_path.insert(0, _BlockImport())
        try:
            with self.assertRaises(ac.BonusCapabilityError):
                ac.membership_inventory_routes()
        finally:
            sys.meta_path.pop(0)
            sys.modules.update(saved)
        # Inverse: with the inventory reachable again, the honest answer is
        # still the empty list — the block is real, not an import artifact.
        self.assertEqual(ac.membership_inventory_routes(), [])

    def test_route_surface_carries_no_api_shape_at_all(self):
        # `api` is None, so any API-shaped token anywhere in what the module
        # hands back is a fabrication. Zero tolerance for every enumerated shape.
        for name, blob in (
            ("supported_route", json.dumps(ac.supported_route(), sort_keys=True)),
            ("decision_document", json.dumps(ac.decision_document(), sort_keys=True)),
        ):
            self.assertEqual(_fabricated_api_hits(blob), [], name)

    def test_module_source_carries_no_api_shape(self):
        source = Path(ac.__file__).read_text(encoding="utf-8")
        self.assertEqual(_api_shape_hits(source), [], "module source carries an API shape")

    def test_the_evidence_doc_carries_no_api_shape(self):
        doc = (_BONUS / "BONUS-ACCESS-CAPABILITY-DECISION.md").read_text(encoding="utf-8")
        self.assertEqual(_api_shape_hits(doc), [], "evidence doc carries an API shape")

    def test_no_other_bonus_file_carries_an_api_shape(self):
        # The whole deliverable is scanned, so nothing can hide beside the
        # module. The attack fixtures above are the single sanctioned exception.
        for path in sorted(_BONUS.rglob("*")):
            if not path.is_file() or path.name == "test_access_capability.py":
                continue
            if path.suffix not in (".py", ".md", ".json", ".txt"):
                continue
            text = path.read_text(encoding="utf-8")
            self.assertEqual(_api_shape_hits(text), [], str(path.relative_to(_REPO)))

    def test_the_scan_catches_every_known_smuggle_shape(self):
        for name, shape in SMUGGLE_SHAPES:
            self.assertTrue(
                _fabricated_api_hits(shape), f"{name} passes the scan uncaught"
            )

    def test_the_scan_leaves_legitimate_text_alone(self):
        # The inverse: a stricter scan must not become a blanket refusal. Real
        # provenance paths, filenames and plain prose carry no fabricated API.
        for text in LEGITIMATE_TEXT:
            self.assertEqual(_fabricated_api_hits(text), [], text[:60])

    def test_the_scan_guarantee_is_not_overstated(self):
        # A pattern scan catches the enumerated shapes; it is not a proof that
        # nothing can slip in, and the delivered prose may not promise more.
        for name, path in (
            ("module", Path(ac.__file__)),
            ("evidence doc", _BONUS / "BONUS-ACCESS-CAPABILITY-DECISION.md"),
        ):
            flat = " ".join(path.read_text(encoding="utf-8").split())
            self.assertNotIn("cannot slip a fabricated", flat, name)
            self.assertIn("pattern scan, not a proof", flat, name)

    def test_supported_route_reports_the_block_reason(self):
        route = ac.supported_route()
        self.assertFalse(route["available"])
        self.assertFalse(route["advertised_bonus_ready"])
        self.assertEqual(route["reason_code"], ac.BLOCK_REASON)
        self.assertEqual(route["route"], "assisted_operator")


class TestRequestRefusal(unittest.TestCase):
    """C-14: an unattended grant is refused, never silently downgraded."""

    def test_unattended_request_is_refused_with_the_exact_block(self):
        result = ac.request_bonus_access(unattended=True)
        self.assertFalse(result["granted"])
        self.assertTrue(result["refused"])
        self.assertEqual(result["route"], "refused")
        self.assertEqual(result["reason_code"], ac.BLOCK_REASON)
        self.assertEqual(result["blocked_steps"], list(ac.STEP_ORDER))
        self.assertTrue(result["no_silent_downgrade"])
        for step in ac.STEP_ORDER:
            self.assertIn(step, result["reason"])

    def test_refusal_offers_exactly_the_assisted_route(self):
        offer = ac.request_bonus_access(unattended=True)["offer"]
        self.assertEqual(offer["route"], "assisted_operator")
        self.assertEqual(offer["next"], "prepare_operator_instruction")

    def test_assisted_request_awaits_the_operator_and_has_no_receipt(self):
        result = ac.request_bonus_access(unattended=False)
        self.assertFalse(result["granted"])
        self.assertFalse(result["refused"])
        self.assertEqual(result["route"], "assisted_operator")
        self.assertEqual(result["status"], "awaiting-operator")
        self.assertIsNone(result["receipt"])
        self.assertFalse(result["system_claimed_grant"])
        self.assertEqual(result["blocked_steps"], list(ac.STEP_ORDER))

    def test_non_bool_unattended_is_refused(self):
        for value in ("yes", 1, None):
            with self.assertRaises(ac.BonusCapabilityError):
                ac.request_bonus_access(unattended=value)  # type: ignore[arg-type]


class TestOriginalGiftIndependence(unittest.TestCase):
    """C-F07: the original gift proceeds while the bonus is unavailable."""

    def test_original_is_ready_while_bonus_is_unavailable(self):
        plan = ac.plan_fulfillment(original_ready=True)
        self.assertTrue(plan["original"]["ready"])
        self.assertEqual(plan["original"]["route"], "direct_chat")
        self.assertFalse(plan["original"]["blocked_by_bonus"])
        self.assertFalse(plan["original"]["depends_on_bonus"])
        self.assertFalse(plan["bonus"]["available"])
        self.assertFalse(plan["advertised_bonus_ready"])
        self.assertEqual(plan["continuation"], "original_only")

    def test_a_not_ready_original_names_its_own_reason_never_the_bonus(self):
        plan = ac.plan_fulfillment(
            original_ready=False, original_reason="asset not yet approved for release"
        )
        self.assertFalse(plan["original"]["ready"])
        self.assertEqual(plan["original"]["reason"], "asset not yet approved for release")
        self.assertFalse(plan["original"]["blocked_by_bonus"])
        self.assertEqual(plan["continuation"], "original_repair")
        self.assertNotIn("bonus", plan["original"]["reason"].lower())

    def test_a_not_ready_original_must_name_its_reason(self):
        for reason in ("", "   "):
            with self.assertRaises(ac.BonusCapabilityError):
                ac.plan_fulfillment(original_ready=False, original_reason=reason)

    def test_original_lane_is_identical_when_the_bonus_lane_changes(self):
        # Prove no coupling: even a hypothetical proved bonus cannot move the
        # original lane. Same inputs must yield the same original dict.
        before = ac.plan_fulfillment(original_ready=True)["original"]
        proved = {
            "available": True,
            "route": "unattended",
            "blocked_steps": [],
            "missing_evidence": {},
            "api": None,
            "no_invented_api": True,
            "advertised_bonus_ready": True,
        }
        with _patched_route(proved):
            after_plan = ac.plan_fulfillment(original_ready=True)
        self.assertEqual(before, after_plan["original"])
        self.assertEqual(after_plan["continuation"], "original_and_bonus")

    def test_the_guard_rejects_a_hand_built_coupled_plan(self):
        coupled = ac.plan_fulfillment(original_ready=True)
        coupled["original"]["blocked_by_bonus"] = True
        with self.assertRaises(ac.BonusCouplingError):
            ac.assert_original_not_gated_by_bonus(coupled)
        coupled = ac.plan_fulfillment(original_ready=True)
        coupled["original"]["depends_on_bonus"] = True
        with self.assertRaises(ac.BonusCouplingError):
            ac.assert_original_not_gated_by_bonus(coupled)
        with self.assertRaises(ac.BonusCouplingError):
            ac.assert_original_not_gated_by_bonus({"bonus": {}})

    def test_non_bool_plan_inputs_are_refused(self):
        for kwargs in (
            {"original_ready": "true"},
            {"original_ready": True, "bonus_requested": "no"},
        ):
            with self.assertRaises(ac.BonusCapabilityError):
                ac.plan_fulfillment(**kwargs)  # type: ignore[arg-type]

    def test_the_guard_refuses_a_malformed_plan_with_the_domain_error(self):
        # The guard's job is to reject a bad plan. It must not answer a bad plan
        # with a bare AttributeError from duck-typed attribute access.
        for bad in (None, [], "plan", 1, object()):
            with self.assertRaises(ac.BonusCapabilityError):
                ac.assert_original_not_gated_by_bonus(bad)  # type: ignore[arg-type]
        # Inverse: a well-formed plan still passes the guard.
        self.assertTrue(
            ac.assert_original_not_gated_by_bonus(ac.plan_fulfillment(original_ready=True))
        )

    def test_a_not_ready_original_reason_must_be_a_real_string(self):
        # No silent coercion: str(None) would store the literal "None" as the
        # member-facing reason a not-ready lane is required to name.
        for reason in (None, 12345, [], {}, True):
            with self.assertRaises(ac.BonusCapabilityError):
                ac.plan_fulfillment(
                    original_ready=False, original_reason=reason
                )  # type: ignore[arg-type]
        # Inverse: a real reason still plans, and is stored verbatim minus padding.
        plan = ac.plan_fulfillment(
            original_ready=False, original_reason="  asset pending release  "
        )
        self.assertEqual(plan["original"]["reason"], "asset pending release")


class TestCredentialVersusResource(unittest.TestCase):
    """R-13: an expired credential is not expired guides."""

    def test_expired_credential_does_not_close_authorized_guides(self):
        state = ac.resolve_member_state(credential_state="expired", resource_authorized=True)
        self.assertFalse(state["credential_valid"])
        self.assertTrue(state["resource_available"])
        self.assertFalse(state["conflated"])
        self.assertIn("nothing about the guides", state["statement"])

    def test_valid_credential_does_not_authorize_guides(self):
        state = ac.resolve_member_state(credential_state="valid", resource_authorized=False)
        self.assertTrue(state["credential_valid"])
        self.assertFalse(state["resource_available"])

    def test_resource_availability_ignores_the_credential_on_every_state(self):
        for cred in ac.CREDENTIAL_STATES:
            self.assertTrue(
                ac.resolve_member_state(credential_state=cred, resource_authorized=True)[
                    "resource_available"
                ],
                cred,
            )
            self.assertFalse(
                ac.resolve_member_state(credential_state=cred, resource_authorized=False)[
                    "resource_available"
                ],
                cred,
            )

    def test_unknown_credential_state_is_refused(self):
        for value in ("good", "", None, "expir'd"):
            with self.assertRaises(ac.BonusCapabilityError):
                ac.resolve_member_state(credential_state=value, resource_authorized=True)  # type: ignore[arg-type]

    def test_uppercase_and_padded_credential_state_is_normalised(self):
        state = ac.resolve_member_state(credential_state=" EXPIRED ", resource_authorized=True)
        self.assertEqual(state["credential_state"], "expired")

    def test_non_bool_authorization_is_refused(self):
        for value in ("true", 1, None):
            with self.assertRaises(ac.BonusCapabilityError):
                ac.resolve_member_state(credential_state="valid", resource_authorized=value)  # type: ignore[arg-type]


class TestDecisionDocument(unittest.TestCase):
    def test_document_is_serialisable_and_self_consistent(self):
        doc = ac.decision_document()
        blob = json.dumps(doc, sort_keys=True)
        round_trip = json.loads(blob)
        self.assertEqual(round_trip["verdict"], "BLOCKED")
        self.assertEqual(round_trip["blocked_steps"], list(ac.STEP_ORDER))
        self.assertEqual(round_trip["steps"], list(ac.STEP_ORDER))
        self.assertEqual(round_trip["check_ids"], ["C-14", "C-F07"])
        self.assertTrue(round_trip["original_gift_independent"])
        self.assertIsNone(round_trip["route"]["api"])
        self.assertEqual(set(round_trip["evidence"]), set(ac.STEP_ORDER))


class TestEvidenceWording(unittest.TestCase):
    """The workflow ceiling is scoped, not stated as an absolute.

    The frozen registry carries v3 workflow rows that are NOT read-only (contact
    enrollment and unenrollment against an existing workflow), and the
    definition-authoring rows sit at staging-doc level. An absolute "read-only"
    claim overstates the registry it cites as authority. The ceiling that is
    true is the authoring ceiling in the frozen v3 production spec.
    """

    UNQUALIFIED_CLAIMS = (
        "cannot build or edit a workflow at all",
        "its only workflow operation is the read-only list",
        "workflows are read-only there",
        "workflows read-only on the public API",
    )
    QUALIFIERS = ("frozen v3 production spec", "not authoring", "staging")

    def _doc(self):
        raw = (_BONUS / "BONUS-ACCESS-CAPABILITY-DECISION.md").read_text(encoding="utf-8")
        return re.sub(r"\s+", " ", raw)  # prose wraps across lines

    def test_the_evidence_doc_does_not_overstate_the_workflow_ceiling(self):
        doc = self._doc()
        for phrase in self.UNQUALIFIED_CLAIMS:
            self.assertNotIn(phrase, doc, f"unqualified claim left in the doc: {phrase}")
        for qualifier in self.QUALIFIERS:
            self.assertIn(qualifier, doc, f"scope qualifier missing from the doc: {qualifier}")

    def test_the_module_claim_is_scoped_the_same_way(self):
        source = Path(ac.__file__).read_text(encoding="utf-8")
        for phrase in self.UNQUALIFIED_CLAIMS:
            self.assertNotIn(phrase, source, f"unqualified claim left in the module: {phrase}")
        claim = ac.capability_evidence()["grant"]["claim"]
        self.assertIn("frozen v3 production spec", claim)
        self.assertIn("not authoring", claim)

    def test_the_scoped_ceiling_does_not_change_the_block(self):
        # Scoping the wording is not softening the decision: the enrollment rows
        # are not a membership grant, so the grant step stays blocked.
        evidence = ac.capability_evidence()
        self.assertEqual(evidence["grant"]["state"], ac.RETIRED_RAIL_ONLY)
        self.assertFalse(evidence["grant"]["routable"])
        self.assertEqual(ac.decision_document()["verdict"], "BLOCKED")


class _patched_route:
    """Context manager: replace supported_route with a hypothetical proved one."""

    def __init__(self, value):
        self.value = value
        self._orig = None

    def __enter__(self):
        self._orig = ac.supported_route
        ac.supported_route = lambda: dict(self.value)
        return self

    def __exit__(self, *exc):
        ac.supported_route = self._orig
        return False


if __name__ == "__main__":
    unittest.main(verbosity=2)
