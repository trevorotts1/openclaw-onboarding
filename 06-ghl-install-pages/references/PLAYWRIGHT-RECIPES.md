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
| `test_recipes.py` | Offline validation, routing and recovery tests |

There is one maintained executor, with multiple named recipes. Names below are
entry points in the catalog, not 21 copied browser programs.

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
| `09_create_split_variant` / `funnels.split_variant` | Native variant and traffic allocation | Recorded profile still required; live alert blocked capture |
| `10_fill_page_seo` / `pages.seo` | Title, description, keywords, author, canonical, language | Rendered metadata checked |
| `11_create_form` / `forms.create` | Native form and standard required fields | Saved and reopened live |
| `12_configure_form_options` / `forms.configure` | Fields, choices, rules, legal copy, redirects, notifications | Executor; per-control recorded profiles required |
| `13_polish_form_css` / `forms.style` | Native iframe input/button polish | Four input types checked at 12 px |
| `14_create_survey` / `surveys.create` | Native survey and standard-field placement | Native field placed/saved; branches need profiles |
| `15_create_marketing_quiz` / `quizzes.create` | Lead quiz, scoring and result pages | Native question path exercised; scoring/result profiles needed |
| `16_create_community` / `communities.create` | Native group creation | Group created, then retained inactive |
| `17_configure_community` / `communities.configure` | Channels, privacy, branding, course links | Portal password expired; profile capture blocked |
| `18_create_course` / `courses.create` | Course creation | API-first handoff, not a new UI implementation |
| `19_configure_course_ui` / `courses.configure_ui` | Genuinely UI-only course settings | Recorded profile required |
| `20_setup_meeting_room` / `meetings.setup` | Personal room and explicit security choices | Live controls captured; final creation/read-back unverified |
| `21_integrate_meeting_room` / `meetings.integrate` | Calendar/community/course event room links | Recorded profile required |

**Evidence limit:** LIVE_PATH means the control sequence was exercised through
the connected browser. The final Python process has not yet been run end to end
on a client Mac or VPS. PROFILE means the common executor exists; it does not
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
controls, submit/redirect/tracking/notification rules; survey slides/conditional
jumps; quiz categories/weights/results; native split creation/allocation;
checkout products/bumps/one-click behavior; portal settings; course UI-only
features; meeting calendar/co-host/recording/transcription integrations.

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
