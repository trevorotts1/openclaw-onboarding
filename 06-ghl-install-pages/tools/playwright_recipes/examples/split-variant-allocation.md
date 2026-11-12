# Authored split traffic allocation

Use `funnels.split_variant` with the complete existing same-step inventory:
`expected_variant_id`, `allow_creation: false`, `expected_active`, and the saved
`expected_control_traffic`. Set `active: true`, the desired `control_traffic`
(1–99), and `traffic_change_authorized: true` for any allocation/activation change.
The variation receives the remaining percentage. Active reuse with unchanged
allocation does not require another traffic authorization or write.

The script binds both native page IDs, stages whole percentages on the slider,
checks the exact native Apply prompt, accepts one JavaScript confirmation, and
independently reloads to verify the same page relation and requested allocation.
Unexpected dialogs, baseline changes, staged-but-unsaved traffic, or failed
readback stop without an automatic retry. Stopping an active split remains
unsupported until its native stop control is captured.

November 11 captures prove the existing running 50/50 state and keyboard staging
at 49/51. The browser extension could not accept the native confirmation, so a
saved 49/51 native run is still unverified. Source checks do not claim live
traffic delivery or conversion-results acceptance.
