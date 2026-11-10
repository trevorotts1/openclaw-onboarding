# Current build recovery - November 9, 2026

Skill 6 v27.1.100 is delivered through [batch #3085](https://github.com/trevorotts1/openclaw-onboarding/pull/3085),
merge commit `dd9e52592d52db6037d845ce5cd5d02326b15f99`. This lands unit #3078:
survey shell/Radio creation, mixed quiz questions and fixed-three Picture Choice.
The exact batch head completed 45 successful checks and two expected skips.
Earlier batches #3059, #3053 and #3042 remain delivered.

The v27.1.101 source adds three independently reviewed capabilities:

1. Picture Choice within mixed quiz batches, preserving its persisted media,
   Unique Key and full prior inventory through the other captured writers.
2. One to four standard-field survey slides, with an explicit chosen slide for
   authored Radio placement and complete untouched-slide preservation.
3. Removal of fully inventoried form condition outcomes, including middle cards
   and clear-all, preserving retained order and rich-message content.

These changes have focused source checks and independent review. Publication
and merge delivery are recorded separately in `PLAYWRIGHT-BUILD-STATUS.json`.
Native installed Python execution and behavioral acceptance remain pending.

The full operation audit still identifies 21 built, 11 partial and one generic
operation across 33 named operations. Twelve operation areas retain missing code;
these operation groups are not counts of Python files or a feature-weighted percent.
Fourteen additions were delivered after the original audit; three more are built
in the current source. Neither count means all twelve areas are complete.

| Operation | Remaining executable scope |
| --- | --- |
| `funnels.split_variant` | Native variation creation/reuse and traffic allocation/readback. |
| `forms.configure` | Remaining widgets/properties, Address controls, Dropdown creation and embed controls. |
| `forms.conditions` | Reordering/nested groups, broader identities and existing outcome edits. Inventoried outcome removal is now built. |
| `surveys.create` | Additional question types, multiple Radio target slides and complete survey flows. |
| `surveys.configure` | Additional question controls, compound predicates and completion/rule lifecycle. |
| `quizzes.create` | Picture Choice creation chain, populated-page append and complete scoring/results flow. |
| `quizzes.configure` | Picture option/style/upload controls, populated-page append, Jump To, tier lifecycle and result media/styles. |
| `courses.configure_ui` | Video lifecycle, image removal and uncaptured controls. |
| `communities.configure` | Authoritative first-course empty state, non-Private modes and portal parity/reuse. |
| `meetings.setup` | Authoritative empty co-host roster and first-assignment path. |
| `meetings.update` | Authoritative empty co-host roster and clear-all path. |
| `meetings.integrate` | Course Live Sessions, wider provider/event shapes, recording/transcription. |

## Execution policy for finishing quickly

Build independent features in parallel. Run only focused new/changed checks,
then one independent source review. Repeat a check only for a new change or an
actual failure. Preserve required repository checks and the existing merge
coordinator. Do not rerun the optional complete local suite or rebuild landed work.
Do not wait for one merge to finish before building the next independent feature.

The private Convert and Flow origin was denied by automatic approval review for
this request. Remaining native capture is blocked until explicitly authorized;
do not recreate that access through another browser, API or credential path.
No native acceptance is claimed for the source changes above.

See `tools/playwright_recipes/examples/survey-radio-creation.md`,
`quiz-picture-choice.md` and `form-condition-outcome-removal.md` for inputs.

---

# Preserved prior recovery history

# Current build recovery — November 9, 2026

This checkpoint supersedes older operation counts below. The exact build inventory
is `PLAYWRIGHT-BUILD-STATUS.json`: 33 named operations, 21 BUILT, 11 PARTIAL and
1 GENERIC_ONLY. Twelve operations still need feature implementation. These are
equal-weight operation counts, not remaining hours or final native readiness.

Earlier batches #2877 and #2951 are merged. The remaining-features draft #2962
preserves the third batch. Its newer continuation recovers Header/CTA quiz-result
copy and integrates compiler, validation, handler outcomes and hash-bound replay.
Existing draft course outline hierarchy/drip/lock edits close that operation's
old implementation gap. Active course publication and learner proof stay separate.

Recovered additions include consent/Address/existing Radio placement, ordered
survey forward rules, quiz property/category controls, inactive theme palette and
font controls, draft outline/access metadata and classic community access controls.
The continuation also preflights complete form-placement batches, schedules course
moves without temporary hierarchy cycles, and verifies preserved calendar and
checkout state. A read-only co-host roster/candidate inspector is available;
it never assigns/removes/saves and does not complete co-host provisioning.

Still partial: additional form/question types and compound conditions; survey
completion effects; quiz question creation and remaining result surfaces;
community branding/media/course links and exact app-to-portal reuse identity;
course media/custom blocks; co-host writing, dynamic rooms and native meeting
associations. Split variation/traffic execution remains generic-only.
Tracking/integrations and payment-owned Order Confirmation remain separate gaps.

Optional/manual/live testing is deferred. Required repository merge checks remain
enabled. Preserve uncertain client journals and existing object IDs. Do not infer
native final-script, submission, learner, payment or VPS proof from source checks.

---

# Skill 6 recovery and continuation ledger

Updated: November 8, 2026. Owner: Trevor Otts.

## Current checkpoint — November 9, 2026

This section supersedes older recovery counts and next-step lists below.

- Batch 1 merged to main in PR #2877, merge commit
  `a89a789a2d36199956f42c64aa78e94bf1ac3525`. Mac/Linux Chromium CI and
  canonical authentication checks passed for that batch.
- Batch 2 source review passed: 542 tests discovered, 535 passed, 7 optional
  browser tests skipped locally. Its Mac/Linux Chromium CI runs separately.
- Current source adds native form scheduling (IANA time zone, open/close windows,
  before/after message or redirect), twelve simple built-in field property paths,
  and existing draft course category/lesson edits through Courses v3.
- Provider receipts bind the exact requested course, parent categories and lessons
  before initial completion or replay. Generic recorded actions retain pending
  independent read-back, and every action checks the requested editor identity.
- Intake rejects unsupported, ignored or contradictory inputs before editor writes.
  Successful form saves still do not prove submission behavior; course edits still
  require learner proof. No final native Python client run is claimed.
- Catalog: 33 named operations. This is an inventory count, not a completion
  percentage. The 47-row acceptance matrix remains the completion contract.

Remaining boundaries: native split traffic capture and uncertain variant intent;
advanced/custom field dependencies and uncaptured controls; complete community
portal controls where the current portal returns Forbidden; payment contracts and
approved test-mode purchase journeys; genuinely UI-only course controls; dynamic
meeting associations; final client Mac/VPS execution and functional receipts.
Preserve uncertain journals and reconcile by independent read-back before retry.

## Start here in a new chat

Read this file, PLAYWRIGHT-RECIPES.md, PLAYWRIGHT-REQUIREMENTS.md,
and tools/playwright_recipes/catalog.json.
Inspect actual source and rerun tests before reporting completion. Preserve existing
location/page/form IDs from each client's state.json. An uncertain mutation must
be reconciled by read-back before another create. Never infer completion from chat.

Repository: https://github.com/trevorotts1/openclaw-onboarding
Recovery branch: skill6/recovered-recipes-20261108
Original branch: skill6/playwright-recipes-20261108
Recovery base: 6edc66a74d01b4a77e592df4f50241487ba4a6ee (original branch at d50b3841a contained no new recipe implementation).

## Recovered and checked

The previous workspace survived at /workspace/scratch/59aa6a7ca6e6.
The package under 06-ghl-install-pages/tools/playwright_recipes is the maintained
copy. The separate skill6-playwright directory was a development copy.

- Recovered shared executor, compiler, router, host adapter, preflight, catalog,
  example inputs and source tests, plus the recipe guide and Skill 6 instructions.
- Recovered Firebase bridge origin guard change for Convert & Flow.
- Reran all 18 recovered offline tests: PASS. This proves offline behavior only.
- 22 catalog routes: 21 executor entries and 1 API-first course handoff.
- Historical live-path observations are recorded in the catalog/guide; they were
  reported by the prior chat, not independently repeated in this recovery.
- No final Python end-to-end Mac or VPS run was recovered.
- Added 3 checkpoint tests; recipe and checkpoint suite: 21/21 PASS.
- This Linux workspace lacks Playwright and the OpenClaw/Agent Browser CLIs;
  preflight returns HOST_SETUP_REQUIRED. No live Python run claimed.
- Run-state JSON now flushes and fsyncs before atomic replacement.
- Added checkpoint.py to export source, requirements summary, progress and a
  per-file SHA-256 manifest to ~/Downloads/BlackCEO-Skill6 on the executing host.

## Recovery verification details

- Recipe/checkpoint suite: 21 passed. Python and JSON syntax: PASS.
- Auth/manager combined pytest: 63 passed, 1 teardown timeout at 60 seconds.
  Unchanged baseline isolated test: PASS. Candidate isolated retest also timed out at 60 seconds; unresolved.
  The browser-manager implementation differs only by its release version marker.
- Release-bundle checks passed, but the root release roll was removed to keep this
  recovery limited to Skill 6. No release/merge performed. Skill 6 changelog and
  version carriers are updated; release integration remains for the merge train.
- Split-test capture retried on the existing probe funnel/page:
  named ZHC Skill 6 Playwright Funnel Probe 2026-11-08. Create variation opened a
  JavaScript alert; browser connection timed out attempting dismissal. No variant
  creation or allocation was verified. Reconcile the screen before another click.

## Remaining work, in order

1. Save source to a remote commit and draft PR; resolve the host teardown timeout
   before declaring host integration clean. Checkpoint integrity tests pass.
2. Capture native split variant creation and traffic allocation. Prior browser alert
   prevented reliable capture. Do not substitute guessed selectors.
3. Capture all advanced form choices/options, survey branches, quiz scoring/results
   with persisted read-back assertions.
4. Verify native checkout products, bumps and one-click bindings under the existing
   Skill 44/79 payment contract. Component insertion alone is not payment proof.
5. Recover community portal access through the actual account flow. Prior portal
   showed expired password. Group creation was exercised; settings were blocked.
6. Finish meeting creation/read-back and integrations. Prior controls were inspected;
   final room creation/read-back was not verified. Recheck official documentation.
7. Exercise API-first course dispatch; capture genuinely UI-only course settings.
8. Run final Python process on client Mac and Linux VPS, then independently verify
   desktop/mobile render, form submission, quiz branches and test-payment behavior.

## Checkpoint discipline

After each completed script/profile or meaningful correction:

1. Update this ledger and catalog evidence levels with actual outcomes and next step.
2. Run appropriate tests; record their command, counts, failures and limitations.
3. Commit and push the feature branch. Do not wait for the end of the chat.
4. Run checkpoint.py on the client host for a dated Downloads archive.
5. Keep client state.json and handoff.json in that client's protected persistent run
   directory. They contain object IDs and last-step intent. Do not put credentials,
   browser storage, seed files or client evidence into the source archive or repo.

The archive's manifest records exact bytes even if edits have not been committed.
It does not upload anything or automatically run after every edit. The executor
already writes state before and after mutations; this is separate from source backup.

## Commands

```bash
python3 -m unittest discover -s 06-ghl-install-pages/tools/playwright_recipes -p 'test_*.py' -v
python3 06-ghl-install-pages/tools/playwright_recipes/preflight.py
python3 06-ghl-install-pages/tools/playwright_recipes/checkpoint.py
```

## Resume instruction

Continue the existing Skill 6 Playwright job from PLAYWRIGHT-PROGRESS.md. Verify
the latest remote branch and source manifest, read the catalog, rerun tests and
continue the first unfinished item. Do not recreate existing live test objects or
claim PROFILE/CAPTURED entries are verified. API/MCP/Skill 44 first when the exact
operation is supported; ready Playwright recipe next; current OpenClaw extension,
Agent Browser, then computer control. Publish and payment actions retain their
existing authorization requirements.

## Continuation: native form settings

Added forms.settings for seven explicit native settings: save progress, submission
document, recommendations, sticky contact, create conversation, timezone and font.
Captured the actual eight-switch order and each containing row label in the live
form editor. The script checks both before clicks, saves and reloads the editor
to compare persisted values. Scheduling is excluded because it requires dates
and messages. Python end-to-end execution remains pending, not marked LIVE_PATH.

The private handoff now links to the original owner attachment in full. The
repository was verified public; the full conversation is not published there.

## Parallel implementation pass

Six workers implemented runtime, delivery API, assessments, meetings, native
checkout, and acceptance review in parallel. New source modules assessments.py,
delivery.py, meetings.py and pages_checkout.py have functional offline tests.
Shared compiler/runner now dispatch captured form fields/conditions, native
checkout, and room creation/update; host executes course API providers.
Unknown, incomplete or missing handler results stop subsequent writes. Supplied
page runs have an evidence-root exclusive lock.

Current combined package suite: 103 tests passed before final follow-up edits.
Prior auth/browser-manager suite: 64 passed unchanged, timeout not reproduced.
Playwright package/driver installed, but Chromium download failed (corrupt
response) and no supported browser executable is installed here.
No final Mac/VPS Python live proof is claimed.

Live room creation in a clearly named ZHC test fixture succeeded with waiting
room enabled, guest access disabled and open room disabled; no call started, no
cohosts added. Native saved detail and Edit settings controls were captured.
Room invitation query credentials are excluded from source and receipts.
Meeting Integrations confirms static calendar links and dynamic per-appointment
connections are separate features. Native integrations screen is instructional.

See PLAYWRIGHT-COMPLETION-MATRIX.md for 47 required acceptance checks. Added
modules and catalog entries do not close pending live/profile/payment checks.
Remaining actual UI capture includes advanced choices, survey branching, quiz
scoring/results, split traffic/native binding maps, portal privacy/branding, and
native calendar connections. Continue work; do not treat this checkpoint as done.

## Native quiz, survey and layout continuation

Added quiz_ui.py with categories, choice category/score binding, three score
tiers, independent saved-editor readback and explicit known-control guards.
Added survey_ui.py with source-slide ownership, forward-only Jump To creation,
three save levels, independent native saved-card readback and idempotent reuse.
Root exercised the saved survey fixture: matching synthetic email skipped Slide2
to LastName/Submit; nonmatching synthetic email went to FirstName/Next. No final
submission was clicked. An unfinished-submission prompt required Start over when
resetting the preview; no real contact details were entered.

Captured actual section width #width dropdown and Full option, separate from
Allow Rows to take entire width. Runner now sets the dropdown rather than only
checking class; section-toolbar targeting avoids overlapping row toolbar.
Explicit native element/name/section identity now supports safe existing code
updates on multi-section pages and returns code identity receipts.

Created GitHub Actions Ubuntu/Mac real-Chromium fixture workflow; local Chromium
remains unavailable. Offline tests and skipped fixture count are recorded by
final suite. Do not claim native Mac/VPS proof or paid checkout proof from CI.
Community portal independently still shows expired-password screen.


## Client Mac and portability proof (20:10 UTC continuation)

The saved d86983 checkpoint passed all 178 tests on Ubuntu and Mac GitHub runners,
including four opt-in real Chromium fixtures. The browser lifecycle guard then
caught the fixture's bare launch; it has been corrected to a persistent owned
context without changing/exempting the guard. The guard passes locally; the
corrected fixture needs a fresh CI run. This is synthetic browser proof, not
native client API/payment/build proof.

The existing OpenClaw app ran an isolated client-Mac worker. It verified the
remote checkpoint, ran 178 tests (four opt-in skips), then passed all four actual
Chromium fixtures using the already-installed Homebrew Python and matching
cached headless shell. A separate unchanged PlaywrightSession smoke passed with
about:blank/local content and clean teardown. No dependency was installed or
credential/configuration changed. The earlier read-only preflight incorrectly
required the full Chromium executable even with a working headless shell;
preflight is being corrected to detect the matching installed shell revision.

A source checkpoint was actually written to the client Mac's default Downloads
folder and independently verified (34 manifest entries, zero mismatches). Exact
private machine paths and execution receipts stay in the private owner handoff.
Source archives exclude private auth/runtime state.

Latest native additions include hidden field values with six-input shape guards,
quiz question/answer authoring with explicit shared-field acknowledgment, owned
custom-CSS preservation, native checkout settings/content/input style and a
permanent-calendar-link API provider. Native checkout headline and Box input
appearance were saved and independently reopened in the browser fixture.
The native Python forms.settings host run is being tested separately; no success
is claimed until its persisted setting and replay receipt are observed.

Canonical Skill44 regression after calendar registry integration: 511 passed,
3 skipped and 1,515 subtests passed. Registry breadth now explicitly checks the
calendar operation contract. A preexisting stale automation fake signature was
corrected with a callback-propagation assertion; production CLI was unchanged.
Thirty named catalog operations exist; this is not a count of fully live-verified
scripts. Consult the 47-row acceptance matrix for unfinished work.


## Latest integrated source checkpoint

Whole recipe package: 230 discovered, 223 passed, seven opt-in Chromium tests
skipped in this workspace. Six new hydration tests cover the actual Mac-discovered
race: exact editor routes wait for the expected iframe, then recheck origin,
location and route. Dashboard navigation is never used as editor readiness.
Direct/package imports share one Stop type; CLI native validator refusals are
structured exit-2 outcomes. Native form settings support the captured eight- or
nine-switch layout without changing scheduling or agency branding.

Seven mandatory real-browser fixtures will run on both OSs in the next source
checkpoint CI. No current source test is failed; native GHL forms.settings proof
remains pending its separately recorded guarded run. An alternate documented
host-API attempt left intent recorded and must be reconciled before any retry.
All native client receipts and diagnostic scripts remain private and outside
source checkpoints. Do not reset or overwrite uncertain client state.


## Additional native coverage and real-DOM correction

Added forms.submission (message/HTTPS redirect, conditional-precedence guard)
and forms.notifications (authored recipient/settings, inner+outer Save and
reopened native values). Catalog now has 32 named operations. Notification
receipts hash addresses/content; no submission or email delivery was triggered.
Native checkout Terms can use explicit caller-approved plaintext for both steps;
no legal text is invented and no legal agreement is accepted by this script.

A live inspection caught a condition-selector bug masked by an earlier fake:
the native search input stays blank while selected text is rendered in an
adjacent overlay. The script now checks the captured label/title and overlay.
Single Show Field and Hide Field use independently reopened exact rule cards.
A new clearly named advanced-condition fixture was created after exact-name
absence was verified; its Show Field rule and hidden Last Name were persisted.
Preview behavior was exercised without submission: First Name empty showed Last
Name, entering synthetic text hid it, clearing the text showed it again.
This is browser UI behavior proof, distinct from the final native Python process.

The dae5006 checkpoint completed all 230 tests on BOTH Mac and Linux CI; the
actual client Mac also completed all 230 with seven real Chromium fixtures and
READY_FOR_HOST_PROBE. Its updated 50-entry Downloads archive passed integrity.
Live auth stopped after a P4 identity refusal and retained uncertain form intent;
no further token/login/bootstrap attempt was made. Exact client receipts remain
private. Further source additions above need their own saved checkpoint/checks.


## Integrated 32-operation review

Whole recipe suite: 262 discovered, 255 passed, seven actual-browser fixtures
skipped only because this workspace has no Chromium executable. New submission
and notification result statuses are registered centrally; explicit false
functional/submission/behavior/payment proof keeps the run NEEDS_VERIFICATION.
Ten acceptance-boundary tests pass, including these two new saved outcomes.
Both new recipes validate through the actual CLI, and invalid inputs produce
structured refusals without a traceback. Independent review checked the
notification two-save flow, recipient inventory handshake and hash-only receipts.
The guide lists all 32 operation names and their remaining limits.

The prior dae5006 CI checkpoint is green on all completed guards; QC static was
still running at the last observation. The newly integrated source must receive
its own Mac/Linux mandatory-browser CI and Downloads checkpoint. Native scope
identity remains unconfirmed; this is not evidence that a key is absent/invalid.
Do not bypass the canonical authentication check or clear uncertain client intent.
