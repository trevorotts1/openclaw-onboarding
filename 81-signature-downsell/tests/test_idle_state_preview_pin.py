"""S81 idle-state pin accounting (fixture-review gap G15; lane-idle-pin-1850).

Native state `idle` (references/native-action-states.md, States table):
"CTAs enabled; decline action visible." Schema UI term `default` maps to
it in the same document's vocabulary mapping.

WHY THIS FILE CONTAINS A SKIP AND NOT A BEHAVIOR PIN: no local artifact
models the idle state, verified firsthand by this lane on 2026-10-16:

- fixtures/valid-downsell-page.json: every CTA and the decline action
  carry only `action_ref` and `label`. Nothing in the fixture encodes
  enabled or visible, so asserting "CTAs enabled; decline visible" from
  mere presence would over-claim what the artifact proves.
- fixtures/valid-downsell-result.json: `cta_map` entries carry only
  `action_ref` and `section`; `decline_action_ref` is a reference, not
  a rendered or visibility state.
- The packet reference contract has no idle behavior to route-test:
  resolve_after("downsell_1", "idle", ...) raises ValueError
  ("Unknown event; do not infer a decline or success."), probed
  firsthand. Idle is the pre-action UI state, not an event.
- Lane review 7 gap G15 records the honest fixture shape verbatim: "A
  fixture would be a UI-state preview check at installed proof, not a
  route test." Installed proof is blocked on the S06 authorized test
  location and the installed page (see rooms/S81/installed-proof-plan.md
  entry criteria), so that preview cannot be produced locally yet.

The idle preview is therefore filed as CR-S81-010 (to S06, cc S79) and
accounted for here as a CR-labeled skip in the established form used by
test_d1_route_law_pins.py for CR-S81-001 / CR-S81-002: the test below is
skipped while the CR is open and FAILS CLOSED if it is ever reached
(the skip removed before a real preview pin exists).

This file does NOT pin idle behavior and must not be read as doing so.
When CR-S81-010's acceptance evidence lands, this skip is replaced by a
real installed-preview pin test in this file.

NOTE FOR THE META-TEST OWNER (tests/test_state_inventory_completeness.py,
not edited by this lane): that file's CR_SKIP_FOR_STATE map at this
writing names only processing -> CR-S81-001 and
unknown_outcome -> CR-S81-002, and its pin_categories() consults only
that map, so its pin test will still report `idle` until the map gains
an "idle": "CR-S81-010" entry. That one-line accounting update belongs
to the meta-test's owner; this lane was forbidden to edit that file.

Run: python3 -m unittest discover -s tests -v
"""
import unittest


class IdleStatePreviewPinTests(unittest.TestCase):
    @unittest.skip("CR-S81-010: no idle/default UI-state preview carrier exists "
                   "yet; the idle state (CTAs enabled, decline action visible) "
                   "can only be pinned as an installed-proof preview check, "
                   "which is blocked on the S06 authorized test location and "
                   "the installed D1 page, so it cannot be pinned at L1")
    def test_CR_S81_010_idle_state_preview(self):
        self.fail("unreachable while CR-S81-010 is open: if this test runs, "
                  "the idle preview pin is missing and the state inventory "
                  "must be reported incomplete, never passed")


if __name__ == "__main__":
    unittest.main()
