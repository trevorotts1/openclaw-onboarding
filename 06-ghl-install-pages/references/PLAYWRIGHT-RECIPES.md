# Skill 6 reusable builder recipes

Trevor's decision, 2026-11-08: let an agent prepare approved code and inputs once,
then run deterministic editor actions. AI browser control handles new controls,
selector changes and recovery. A captured repair becomes a reusable profile.
The execution scripts make no model calls.

Read [PLAYWRIGHT-PROGRESS.md](PLAYWRIGHT-PROGRESS.md) first when resuming this job.
Run `python3 06-ghl-install-pages/tools/playwright_recipes/checkpoint.py`
to save a dated source backup to Downloads on the executing Mac or VPS.

## Routing and ownership

For each exact operation, ask `tools/playwright_recipes/route.py` to choose:

1. A supported public API, official MCP or Skill 44 implementation, using a
   fresh receipt for this location, version and token scopes.
2. A ready Playwright recipe and its captured profile, when required.
3. The current OpenClaw Chrome extension on the client's paired Chrome.
4. Agent Browser by Vercel through the existing managed gateway.
5. Computer use, only when installed, enabled and needed.

A 401/403 is an authentication/scope problem, never proof an API is unsupported.
Course creation and course lesson quizzes use documented Courses v3 operations
first. Standalone marketing quizzes use `quiz-builder-app`, not the survey
builder. Native payment dependencies stay with Skill 44/79.

Skill 49/83/signature authoring still owns design, wireframes, mockups, copy and
their approval requirements. Skill 6 installs the approved result. Existing
inventory, dependency, evidence-hygiene, media, embeddability, payment and full
funnel verification gates still apply. An editor save never substitutes for QC.

## Files and entry points

The code lives in `tools/playwright_recipes/`:

| File | Purpose |
| --- | --- |
| `skill6_playwright.py` | Shared synchronous Playwright actions and protected run state |
| `recipe_cli.py` | Compile a named recipe and validated JSON inputs into actions |
| `host.py` | API-first routing, execution and recovery handoff for agent hosts |
| `route.py` | Deterministic capability-based lane selection |
| `catalog.json` | Operation names, best uses and evidence levels |
| `preflight.py` | Read-only Mac/Linux runtime check |
| `assessments.py` | Native field properties, conditions and preserved custom CSS |
| `quiz_ui.py` | Native quiz categories, authored answers, scoring and three result tiers |
| `survey_ui.py` | Native forward Jump To rules with source-slide checks |
| `checkout_ui.py` | Native checkout layout, contact fields, display switches and content |
| `pages_checkout.py` | Exact code targets and contract-bound native payment component adapter |
| `delivery.py` | Course and permanent calendar-link API execution through existing credentials |
| `course_outline.py` | Existing draft module/lesson API updates with exact target/version receipts |
| `form_schedule.py` | Native open/close scheduling, time zone and outside-window page/link settings |
| `intake.py` | Reject missing, ignored and contradictory inputs before browser work |
| `meetings.py` | Room creation/update, persisted identity and security checks |
| `checkpoint.py` | Dated source backups with a per-file integrity manifest |
| `test_*.py` | Validation, routing, recovery, provider and opt-in Chromium contracts |

There is one maintained executor, with multiple named recipes. Names below are
33 named entry points in the catalog. Shared handlers avoid copying browser programs.

| Recipe | Best use | Current coverage |
| --- | --- | --- |
| `01_create_funnel` / `funnels.create` | New funnel, initial page, optional HTML/SEO | Live UI path exercised |
| `02_add_funnel_page` / `funnels.add_page` | Add a page/path to an existing funnel | Live UI path exercised |
| `03_create_website` / `websites.create` | New website and initial page | Live UI path exercised |
| `04_add_website_page` / `websites.add_page` | Add a website page/path | Live UI path exercised |
| `05_install_external_code` / `pages.install_code` | Approved AI, Skill 49/83 or other HTML | Live rendered preview checked |
| `06_install_hosted_embed` / `pages.install_embed` | Supplied hosted-app embed | Executor; embeddability PASS receipt required |
| `07_wrap_native_checkout` / `checkout.wrap_native` | Code before/after a native GHL order form | Component path exercised; payments unverified |
| `08_configure_native_upsell` / `checkout.one_click_upsell` | Native one-click purchase-action binding | Recorded profile still required |
| `09_create_split_variant` / `funnels.split_variant` | Native variant and traffic allocation | Dedicated same-step inactive control/variation creation or exact reuse, native page IDs, and saved 100/0 allocation readback. Active traffic changes refuse before mutation pending native confirmation capture. |
| `10_fill_page_seo` / `pages.seo` | Title, description, keywords, author, canonical, language | Rendered metadata checked |
| `11_create_form` / `forms.create` | Native form and standard required fields | Saved and reopened live |
| `12_configure_form_options` / `forms.configure` | Existing standard-field labels, placeholders, keys, width, required/hidden/default values | Concrete saved-editor read-back; other field types and controls require capture |
| `13_polish_form_css` / `forms.style` | Input radius or approved custom CSS in an owned block | Preserves other CSS; saved-editor and optional computed-style read-back |
| `14_create_survey` / `surveys.create` | Native survey and standard-field placement | Native field placed/saved; branches need profiles |
| `15_create_marketing_quiz` / `quizzes.create` | Lead quiz, scoring and result pages | Native question path exercised; scoring/result profiles needed |
| `16_create_community` / `communities.create` | Native group creation | Group created, then retained inactive |
| `17_configure_community` / `communities.configure` | Channels, privacy, branding, course links | Classic channels/details captured; current new portal access returns Forbidden |
| `18_create_course` / `courses.create` | Course, outline, lesson content and quizzes via Courses v3 | Concrete API provider; location/version/scope capability and independent read-back required |
| `19_configure_course_ui` / `courses.configure_ui` | Genuinely UI-only course settings | Recorded profile required |
| `20_setup_meeting_room` / `meetings.setup` | Personal room and explicit security choices | Concrete create/reuse with independent reader; native fixture created and reopened |
| `21_integrate_meeting_room` / `meetings.integrate` | Explicit permanent calendar room link | Registered API provider with persisted read-back; dynamic appointment rooms and other associations remain uncaptured |
| `22_configure_form_settings` / `forms.settings` | Seven ordinary switches and native form scheduling | Captured time-zone/open/close/outside-window save/reopen; actual visitor behavior pending |
| `23_update_course` / `courses.update` | Existing course content and styling | Concrete API update and read-back; live client proof pending |
| `24_create_lesson_quiz` / `courses.lesson_quiz.create` | Course lesson quiz and questions | Courses API, separate from marketing quiz; live attempt proof pending |
| `25_configure_form_condition` / `forms.conditions` | Native Hide/Show Field conditions | Three-level save and exact persisted card check; other effects require capture |
| `26_configure_native_checkout` / `checkout.configure_native` | Native product/price/bump/action binding | Location/page-bound component capture and payment dependencies required; payment behavior pending |
| `27_update_meeting_room` / `meetings.update` | Update exact existing room | Existing room identity mandatory; cannot create on a missing target |
| `28_configure_quiz_scores_and_tiers` / `quizzes.configure` | Categories, existing question/answer authoring, appended answers, scores and three tiers | Concrete native read-back; shared-field edit acknowledgment required for text changes |
| `29_configure_survey_branch` / `surveys.configure` | Forward native Jump To condition | Concrete three-level save/read-back; separate live true/false preview exercise passed |
| `30_configure_native_checkout_ui` / `checkout.configure_ui` | Layout, contact fields, display switches, 37 text fields and input style | Concrete save/reopen path; stays pending payment verification |
| `31_configure_form_submission` / `forms.submission` | Native On Submit plain message or HTTPS redirect | Exact saved-mode/value read-back; conditional precedence requires acknowledgment; behavior remains unverified |
| `32_configure_form_notifications` / `forms.notifications` | Native email notifications and auto responder | Authored subjects/sender/recipients, recipient replacement handshake, inner/outer save and list-reopen checks; actual mail delivery remains unverified |

| `33_update_course_outline` / `courses.lessons` | Existing draft module/lesson content and metadata | API-first version/parent preflight and independent read-back; learner proof pending |

**Evidence limit:** LIVE_PATH means the control sequence was exercised through
the connected browser. The package and four actual Chromium fixtures passed on Mac and Linux CI.
The client Mac also passed the four fixtures and the managed browser lifecycle.
These are distinct from a final native GHL job and from an actual client VPS run. PROFILE means the common executor exists; it does not
mean all controls for that operation have been recorded. Do not describe this
catalog as complete coverage of every GHL option.

## Upfront intake

Collect only missing inputs once: location ID and visible account name; exact
container/page names and paths; approved HTML or embed fragment; responsive
design/width requirements; SEO copy and keyword sources; field keys/types and
pre-created custom-field receipts; consent/privacy/terms copy; submit behavior;
checkout product/price/currency/bump/upsell and prior-payment contract; quiz
categories/scoring/results/branches; community visibility/channels; course
outline/access; meeting room name/slug, waiting-room, guests and open-room
choices. Reuse already supplied answers and existing inventories.

Do not fabricate legal text, founders, products, quiz scores, recipient users,
domain names or security choices. Missing payment bindings are a dependency
handoff, not a reason to replace native checkout with raw card HTML.

## Run it

Use the existing Skill 6 Python environment. Check without opening a browser:

```bash
python3 06-ghl-install-pages/tools/playwright_recipes/preflight.py
python3 06-ghl-install-pages/tools/playwright_recipes/recipe_cli.py \
  --recipe websites.create --inputs /ABSOLUTE/CLIENT-RUN/website.json
python3 -m unittest discover \
  -s 06-ghl-install-pages/tools/playwright_recipes -p 'test_*.py'
```

An input example is in `tools/playwright_recipes/examples/website.json`. Its
sample values are placeholders; check mode validates structure, not the truth
of a domain or approval receipt. Source paths resolve relative to the input
file. Generated HTML is passed through the existing shared fragment converter
when it contains document wrappers; CSS/scripts are preserved by that tool.
For hosted content, use an actual embed snippet: a Vercel deployment URL alone
does not prove iframe permission, responsiveness or authentication behavior.
`embed_receipt` must contain `status: PASS`, the location ID, the normalized
fragment's `html_sha256`, every actual iframe/script `embed_urls`, and the
embeddability gate's `source` receipt. A PASS for unrelated HTML is rejected.
The upsell recipe similarly requires `checkout_contract`: location-bound PASS,
product/price IDs, source and upsell step IDs, a verified prior-payment flag and
the Skill 44/79 source receipt. This is a prerequisite, not a substitute for
the fixture's end-to-end payment test.

Agent integration is `host.run_recipe(operation, inputs, probes,
evidence_root, input_dir=..., page=managed_page)`. The page must be a synchronous
Playwright Page in the existing isolated, authenticated client context. Omit
`page` to use the existing `browser_manager.PlaywrightSession` and
`ghl_auth.mint_and_bridge` implementations. This reuses the custom extension's
captured refresh token through Skill 6's shared secret resolver; it never
scrapes tokens from another tab or types a username/password/2FA.

Build `probes` from the existing `capability_probe.run_probe()` report using
`route.from_capability_probe(report, api_capabilities=skill44_receipts,
recorded_profiles=available_profile_operations)`. This preserves its extension
version checks and host measurements while applying the new per-operation
order. Its legacy `selectedLane` field alone must not choose a recipe engine.

The optional CLI execution form is:

```bash
python3 06-ghl-install-pages/tools/playwright_recipes/recipe_cli.py \
  --recipe websites.create --inputs /ABSOLUTE/CLIENT-RUN/website.json \
  --execute --evidence-root /ABSOLUTE/CLIENT-RUN/evidence
```

The agent must consult `route.decide` first; `host.run_recipe` enforces it.
Direct CLI execution is a low-level operator interface, not an API fallback
probe. Do not route documented API writes through it merely because it exists.

Mac and Linux use the same Python/browser actions; no AppleScript, hardcoded
home directory or desktop coordinates are stored. VPS runs use the existing
headless gateway and Chromium dependencies. CDP attachment is optional through
`GHL_MANAGED_CDP_URL`, restricted to loopback. The host owns its authenticated
session; no browser is exposed on a public VPS interface or closed by this
adapter. The runner's lock prevents two recipe processes using that endpoint.

The Firebase bridge's explicit app-origin profile currently permits official
GHL and Convert & Flow. Other white-label hosts need a reviewed origin profile;
never seed auth into an arbitrary URL. Refresh-token revocation or an expired
portal password stops that route and requests the actual account recovery.
The inherited bridge receipt derives its location from the URL. It must not be
treated as authenticated location-access proof; keep the existing independent
token identity read-back in the canonical dispatcher/verifier.

## Captured options profiles

For an uncaptured UI option, use the next available browser lane to inspect the
actual current controls. Record exact role/name, frame, scope, expected count
and persisted read-back assertion, then supply `options` in the inputs. Every
profile needs a dated `capture_source`; never invent selectors from memory.

```json
{
  "frame": "form-builder-app",
  "capture_source": "CLIENT-RUN live DOM receipt, YYYY-MM-DD",
  "steps": [
    {"action":"fill","target":{"by":"role","role":"textbox","value":"Form Name"},"value":"ZHC Approved Form"},
    {"action":"click","target":{"by":"role","role":"button","value":"Save"}},
    {"action":"expect_text","target":{"by":"role","role":"textbox","value":"Form Name"},"value":"ZHC Approved Form"}
  ]
}
```

This example asserts the editor title only; it is not independent save proof.
Production profiles must reopen or inspect the persisted result and verify the
requested behavior. Available actions: click, fill, check, select, press, drag,
expect_text, expect_value, expect_count. Drag uses a `to` locator. Indexed
locators require a captured count. Publish, purchase, deletion, invitations and
credential actions remain outside this executor. An assertion must be present.

Profiles needed before broad deployment include: all form choice/advanced
controls, submit/redirect/tracking/notification rules; additional survey question
types/outcomes; quiz question creation, tier creation/removal and outcome behavior; native split creation/allocation;
checkout products/bumps/one-click behavior; portal settings; course UI-only
features; dynamic appointment-room and community/course meeting associations; recording/transcription integrations.

## Recovery and proof

Each step writes intent before a mutation, then its minimal outcome. Run state
is mode 0600 in a directory mode 0700; credential seed files are removed in
`finally`. No raw Playwright trace, storage dump or error containing secrets is
written. Interrupted or uncertain jobs never automatically replay writes.
The fallback agent must inspect saved IDs/URLs and continue with a reconciled
new job, preserving the original state file.

Exit 0 means validation only, or requested editor steps complete. Exit 2 means
STOP/recovery. Exit 3 means already executed or independent verification still
required. `EDITOR_STEPS_COMPLETE` is explicitly not a full-funnel QC PASS.
Checkout saves, assessment saves and room-save submissions remain
`NEEDS_VERIFICATION`. Survey/quiz reuse with requested fields is refused until
those fields are inventoried, avoiding silently incomplete builds.

Before release: run the final Python process on both a Mac and a Linux VPS,
with the existing Firebase bridge, then independently reopen outputs, check
rendered desktop/mobile pages, form submissions and quiz branches in a fixture,
and use the existing Skill 79 test-payment contract for upsell verification.
Do not merge as complete deployment readiness while those receipts are absent.

## Meeting Room research (2026-11-08)

HighLevel now documents built-in Meeting Room, reusable personal room links,
guest/waiting-room settings and integrations with calendars and delivery apps.
Room UI controls were inspected in the $497 agency's Convert & Flow account.
No public room-creation endpoint was confirmed during this research; probe
again per location before choosing the UI. This does not mean Zoom meetings
or client calendars have automatically migrated.

- [Official Meeting Room overview](https://help.gohighlevel.com/support/solutions/articles/155000009149-meeting-room-in-highlevel-overview)
- [Official Meeting Room release](https://ideas.gohighlevel.com/changelog/introducing-meeting-room)
- [Official Courses v3 create operation](https://marketplace.gohighlevel.com/docs/ghl/courses/create-course/)
- [Official course lesson quiz operations](https://marketplace.gohighlevel.com/docs/ghl/courses/quiz/)


## Concrete native option examples

See `tools/playwright_recipes/examples/NATIVE-OPTIONS.md` for captured form,
quiz, survey and custom-CSS schemas. See `examples/checkout_ui.md` and
`examples/checkout_ui.json` for the checkout UI recipe. Unknown keys are refused
rather than silently omitted. These examples are schemas, not client approvals.

For permanent calendar integration, use the host with
`operation=meetings.integrate` and explicit
`integration_mode=permanent_calendar_link`, exact `calendar_id`, verified `room`,
and a fresh location/version/scope capability. The canonical Skill 44 registry
owns `calendars.get` and `calendars.update`; default deny and read-back still
apply. A permanent link cannot silently substitute for native dynamic room
generation. Any authenticated invite is transient input; receipts retain only
its hash and safe mode flags. Supply no secret in a public input example.

## Captured form scheduling

`forms.settings` accepts `schedule`, `settings`, or both. For example, the schedule
below uses an explicit IANA zone, local dates and 24-hour local times. The compiler
rejects nonexistent or ambiguous DST times and a close preceding the open.

```json
{"schedule":{"enabled":true,"time_zone":"America/New_York",
 "opens":{"mode":"at","date":"2030-01-15","time":"09:00"},
 "closes":{"mode":"at","date":"2030-01-16","time":"17:00"},
 "before":{"mode":"redirect","url":"https://example.com/not-open"},
 "after":{"mode":"message","message":"This form is closed."}}}
```

Disable with exactly `{"schedule":{"enabled":false}}`. Omitted outside-window
settings and the ordinary switches are preserved. A saved/reopened receipt binds
the canonical schedule hash and keeps submission/visitor behavior unverified.
These examples are operation-specific fields; common location/name/start URL inputs
are still required by the host. Do not run fixture dates against a customer form.

## Existing draft course outline updates

Use `courses.lessons` through `host.py`, with the actual location/version/scope
capability. Supply `product_id` plus `category_changes` and/or `lesson_changes`.
Every edit requires the exact existing target and its inventoried
`expected_updated_at`. A lesson edit also requires its `category_id`.

```json
{"product_id":"course-from-inventory","publish":false,
 "category_changes":[{"category_id":"module-from-inventory",
 "expected_updated_at":"2026-11-09T00:00:00Z",
 "changes":{"title":"Updated draft module"}}],
 "lesson_changes":[{"category_id":"module-from-inventory",
 "lesson_id":"lesson-from-inventory",
 "expected_updated_at":"2026-11-09T00:00:00Z",
 "changes":{"title":"Updated draft lesson","description":"Approved content"}}]}
```

The implementation reads every target and parent before writing, checks versions
again immediately before each update, preserves known writable siblings, and
reads each result independently. Quiz/assignment transitions, publication,
enrollment, moving modules and access/drip/lock rules are outside this operation.
The receipt stays pending learner verification. Official MCP execution requires
an actual installed callback; it never silently substitutes the HTTP transport.

## November 9 native build continuation

`forms.configure` accepts captured Address child Query Keys, consent and
API-inventoried existing Radio fields. `surveys.configure` accepts complete ordered
forward rule stacks or exact existing-slide Radio placement. See package examples.

`quizzes.configure.configuration.result_page` edits existing Header business-name
and per-tier CTA plain text/button/HTTPS link values. Expected previous values and
existing dynamic mode/source are mandatory; see `quiz-result-copy.json`. Normal
question/category/scoring configuration remains a separate earlier action in the
same compiled job. Saved/replayed results bind exact editor and configuration.

`courses.configure_ui` accepts an inventoried inactive template with fourteen
text/visibility controls, six-color layout palette and primary/secondary font and
weight. It preserves the current active theme; Custom Block append/edit is also
implemented with exact block IDs and protected sibling snapshots. Approved background, Custom Block, Hero, Instructor and Image Block PNG paths are implemented; Video Blocks and image-removal modes remain unsupported. `courses.lessons` supports existing draft module/lesson moves and
drip/lock-reference metadata through the API-first provider.

`community_access.py` implements captured classic privacy/access controls;
`meeting_cohosts.py` reconciles the complete approved co-host roster of an exact
existing room. `meetings.setup` and `meetings.update` accept `meeting.cohosts`
with complete expected/desired native name/email identities and scoped access
acknowledgment. That compiles to a dedicated, journaled writer; the room name,
slug and all three security choices are unchanged inventory guards. Room creation
or security/name changes and roster changes use separate jobs with fresh inventory.
An independently reopened roster is required; functional access and notification
behavior remain pending. See `meeting-cohosts.md`. Dynamic meeting associations
remain incomplete.

Consult `PLAYWRIGHT-BUILD-STATUS.json` for exact scope; native functional acceptance
remains separately pending.

## Compound rules, existing quiz layouts and API course media

`forms.conditions.condition` accepts `clauses`, `match:all|any|mixed`, `effect` and
`target`. Mixed predicates carry one explicit ordered `and`/`or` connector per
clause boundary and both connector types. No Boolean precedence is inferred. The native effect has
one target field. Existing unrelated condition stacks are refused, while an exact
existing group can be reused. The saved summary, editor and configuration are
independently rebound after reopening. Legacy single-clause inputs remain valid.
See `form-compound-condition.json` and its accompanying explanation.

`quizzes.configure` can edit any captured existing tier layout using the exact
current labels, order and ranges. It does not create or remove tiers. See
`quiz-existing-tier-layout.json`.

`courses.update` accepts `media_assets` for approved, SHA256-bound PNG uploads and
API product appearance fields. The host selects `course_media` on the measured
same-location v3 route; its check mode requires course-read, course-write and
media-write scopes without uploading. This is separate from inactive theme media
and custom blocks. See `course-media-upload.md`. All native appearance/learner
acceptance stays pending after a saved API update.

`courses.configure_ui.custom_blocks` uses the exact inactive template, ordered
Category/Custom Block ID inventory, complete expected existing content and authored
plain-text/button changes. New blocks bind generated native IDs into saved replay
so a completed run never appends again. See `course-custom-block.md`.

`forms.settings.tracking` accepts inventoried Facebook Pixel ID and page/submission
event changes. It preserves unrequested values and independently reopens the saved
form. Export/embed controls are separate, and no event/submission verification is
claimed. See `form-tracking.json`.

## Native integration continuation

`meetings.integrate` with `integration_mode:dynamic_calendar_room` uses the native
single-staff calendar location selector and a complete, fresh same-location API
user inventory. It checks the exact staff ID and connected provider, saves once,
and independently reopens the calendar. A saved Meeting Room location does not
prove appointment creation or unique room generation. Static permanent links
remain their separate API mode. See `meeting-dynamic-calendar.md`.

`courses.configure_ui.background_image` accepts an absolute approved PNG, its
SHA256 and the exact current preview URL. It copies bytes privately, uses the
captured native upload input and proves changed preview/save/reopen while
preserving transparency, theme and body siblings. See `course-theme-background.md`.

`forms.configure.integration` is an independently journaled export job for one
exact form. Native Integrate/Embed choices produce a code artifact; the code is
read twice and validated against form identity, approved origins, layout/settings
and hash. Replay retains those exact validated bytes. No form Save, installation,
publishing, event or submission proof is claimed. See `form-native-embed.md`.

The dedicated `radio_dependencies` entry point provisions authored Radio contact
schemas only with measured same-location Skill44 route/POST/GET evidence. Its
managed existing-survey chain preflights slide ownership before any schema write
and never repeats uncertain schema creation or native placement. Other question
types and fresh survey creation stay separate. See `assessment-feature-builds.md`.

`communities.configure.course_associations` attaches a Private course through the
live authenticated caller-owned portal context and an exact same-location Courses
API title/ID inventory. It saves without sharing a post and independently reads
native product/group IDs. Zero-card course inventories refuse until authoritative
empty/loading evidence is captured. See `community-private-course.md`.

## Current reviewed control build checkpoint

Read `PLAYWRIGHT-BUILD-STATUS.json` `current_feature_progress` before interpreting
the older 21/11/1 operation audit. Broad partial operations contain completed
controls; their frozen classifications are not a count of unfinished Python files.
The current delta adds mixed predicate connectors, condition-card stack growth
and contraction/clear, inactive background transparency, explicit Custom Block
deletion, and the maintained
Contact dependency-to-form front door. Each remains pending final native/script
functional acceptance after independent saved-configuration verification.

Use `forms.configure.contact_field_plan` exclusively for documented Contact
LARGE_TEXT creation or exact existing Dropdown reuse plus captured native
placement. Supply the current API capability in the host probe, outside authored
inputs; see `examples/contact-field-frontdoor.md`. Dropdown option-array creation
and arbitrary legacy canvas adoption refuse before unsupported work.

Use `courses.configure_ui.background_transparency` exclusively with exact previous
background URL/percentage and desired integer percentage; see
`examples/course-background-transparency.md`. It preserves the inactive template
and image and uses measured arrow keys, never DOM mutation or assumed Home/End.

For Show/Hide cards, supply complete `condition.expected_rules` before edits or
count-changing replacement. Retained cards are edited and missing suffix cards
appended; contraction removes exact tail cards through scoped Delete confirmations.
An explicit empty desired `rules` list requires the complete old inventory and
positive loaded-empty proof before Save and after independent reopening. See
`examples/form-condition-stack-growth.md`, `examples/form-condition-stack-contraction.md`
and `examples/form-mixed-condition.md`. Native drag reordering and arbitrary
existing outcome-card editing remain unsupported.

`courses.configure_ui.custom_blocks.deletion` removes one explicitly inventoried
Custom Block from an inactive template through its exact target-bound native
confirmation. Retained sidebar/preview order and surrounding content must agree
before one Save and independent reopen; see
`examples/course-custom-block-delete.md`. This does not add arbitrary block or
image removal and does not activate or publish a template.

Explicit outcome ordering: `forms.conditions` accepts `recreate_order` with a complete `expected_rules` inventory and `rules` equal to that unchanged ordinal permutation. Non-message outcomes only; messages fail closed to preserve markup. The writer retains the common prefix, recreates the changed suffix using captured Delete/author controls, saves once and independently reopens. No native drag claim.
# Captured survey Multi Line properties

`surveys.configure` accepts `configuration.multiline_questions` with complete
`expected` and `desired` inventories for every numbered slide. This edits existing
native `LARGE_TEXT` textarea questions: Label, Placeholder, Short Label, Query Key,
Required, Hidden and Hidden value. Required and Hidden remain mutually exclusive.
See `tools/playwright_recipes/examples/survey-multiline-properties.json`.

The writer checks all current Multi Line properties before editing, preserves
other widgets, saves once and independently reopens the survey. Completed replay
reads the current native properties again and never rewrites a changed record.
Query Key changes alongside other widget families refuse until their complete
key inventory is available. This action does not create Multi Line questions or
claim survey branching/completion outcomes. The broad survey operations remain
partial. Native creation and Required/Hidden property persistence were captured
on November 10, 2026; reusable source contains no synthetic account identifiers.

Parent Address autocomplete/search-required control configuration is available as a separate `forms.configure` `address_parent` job; see `examples/form-address-parent.json`. Full child properties and query/type sibling inventories are required. Native mandatory=true requires autocomplete=true. Fresh writes and public CLI completed replay verify full bound receipts and current native saved state.
