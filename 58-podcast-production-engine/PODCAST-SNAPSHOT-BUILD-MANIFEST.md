# PODCAST PRODUCTION ENGINE - AUTHORITATIVE GHL SNAPSHOT BUILD MANIFEST

Build target: Convert and Flow (Go High Level) subaccount **`Template ZHC Podcasts Engine`**, location ID **`CjxATjhv9Gt21qSqURIt`**.
Purpose: the single reconciled, build-ready object list the API rail (Skill 44 caf / Skill 29 REST), the Skill 6 headless survey builder, and the Skill 44 workflow builder execute against. Then snapshot.

Reconciliation basis (all READ, not guessed):
- Spec: `PODCAST-ENGINE-SPEC-v2-UPDATED.md` (authoritative on payload contract and build method).
- Old-system review: `OLD-PODCAST-SYSTEM-REVIEW.md` (legacy location `w4A5LiurmAjBbvJOXmyz`; authoritative on the REAL legacy field keys, dataTypes, and topology recovered live via the v2 + internal API).
- Engine source (byte-for-byte authority for what the box asserts): `scripts/caf/field_layer/constants.py`, `scripts/caf/enrollment/enroll.py`, `scripts/webhook/aliases.json`, `config/questionnaires/*.json`, `config/questionnaires/index.json`.

**Decision rule applied throughout:** where a key/tag is byte-asserted by the box engine (`constants.py READ_KEYS/WRITE_KEYS`, `enroll.py WF_TAGS`), the ENGINE wins. Where a key is NOT asserted by the engine (Group 2 per-style fields, the visual-description field), the REAL LEGACY key wins (task directive + continuity), because the engine resolves those positionally through the webhook and never checks their spelling. dataTypes are non-load-bearing (the engine asserts KEYS, not types) so we adopt the proven-live legacy dataTypes.

---

## SECTION A - CUSTOM FIELDS (28, all on the `contact` model)

Create each field with `name = <create-name>`; GHL derives `fieldKey = contact.<create-name>`. Idempotent build: GET the customFields list first, create only the missing ones, read back every key byte-for-byte (including every double underscore). dataType enum strings confirmed against the live customFields API before create (TEXT / LARGE_TEXT / RADIO / DATE).

### Group 1 - selectors and standing fields (11)

| # | Create name | Key status | dataType | Options / folder | Notes |
|---|---|---|---|---|---|
| 1 | `podcast_survey_writing_style` | VERBATIM (engine READ_KEY) | RADIO | Options: `Counter Intuitive` / `Vulnerable` / `Provocative` / `Passionate` ; folder `Podcast Survey` | Interview-survey Q1 router. Stored value MUST be the short label (workflow/engine branch on it). Descriptive parentheticals go in the survey question help text, NOT the option value. |
| 2 | `select_your_presentation_style_personal_podcast` | VERBATIM (engine READ_KEY) | RADIO | Options: `Counterintuitive` / `Passionate` (no space, no descriptor) ; folder `Podcast Survey` | Personal-survey Q1 router (see Survey 2). |
| 3 | `my_preferred_pronoun` | VERBATIM | TEXT | folder `Additional Info` | Governs pronoun/honorific; never guessed. |
| 4 | `podcast_interview_smiq` | VERBATIM | LARGE_TEXT | folder `Podcast Survey` | SMIQ, mandatory transparency beat; REQUIRED. |
| 5 | `smiq_answers` | VERBATIM | LARGE_TEXT | folder `Podcast Survey` | SMIQ supporting (optional). |
| 6 | `smiq_history` | VERBATIM | LARGE_TEXT | folder `Podcast Survey` | SMIQ supporting (optional). |
| 7 | `my_client_smiq_answers` | VERBATIM | **TEXT** (live legacy; spec draft wrongly said LARGE_TEXT) | folder `Podcast Survey` | SMIQ supporting (optional). |
| 8 | `my_client_smiq_history` | VERBATIM | **TEXT** (live legacy; spec draft wrongly said LARGE_TEXT) | folder `Podcast Survey` | SMIQ supporting (optional). |
| 9 | `podcast_survey__additional_info` | VERBATIM - DOUBLE underscore | LARGE_TEXT | folder `Podcast Survey` | Optional extra context. Never normalize to single underscore. |
| 10 | `date_for_release` | VERBATIM | DATE | folder `Personal Podcast` | Future date = scheduled Podbean publish. |
| 11 | `podcast_survey__quick_visual_description` | **RECOVERED-LEGACY - DOUBLE underscore** (spec draft wrongly used single underscore `podcast_survey_quick_visual_description`) | LARGE_TEXT | folder `Podcast Survey` | Cover-image description; feeds image gen ONLY, never spoken; REQUIRED. NOT in engine READ_KEYS - resolved via webhook, so legacy key is free-choice and adopted. |

### Group 2 - per-style question fields (10) - REAL LEGACY KEYS

All: dataType `LARGE_TEXT`, folder `Podcast Survey`, DOUBLE underscore after `survey`. NOT byte-asserted by the engine (`constants.py READ_KEYS` excludes them; the webhook mapper resolves them positionally via `survey_answer_keys_by_style`, which ships empty and is filled per-template at onboarding = task E1). The `ghl_internal_label` in each `config/questionnaires/*.json` maps 1:1 to these keys.

| # | Create name (REAL legacy key) | Internal label | Style | Role |
|---|---|---|---|---|
| 12 | `podcast_survey__barry_q1` | Barry Q1 | Counter Intuitive | Thesis (<=2,000 words) |
| 13 | `podcast_survey__barry_q6` | Barry Q6 | Counter Intuitive | Speaking tone |
| 14 | `podcast_survey__brene_q1` | Brene Q1 | Vulnerable | Thesis (<=2,000 words) |
| 15 | `podcast_survey__brene_q6` | Brene Q6 | Vulnerable | Speaking tone |
| 16 | `podcast_survey__dan_q1` | Dan Q1 | Provocative | Popular assumption on trial (thesis 1) |
| 17 | `podcast_survey__dan_q2` | Dan Q2 | Provocative | Overturning evidence (thesis 2) |
| 18 | `podcast_survey__dan_q7` | Dan Q7 | Provocative | Speaking tone |
| 19 | `podcast_survey__jia_q1` | Jia Q1 | Passionate | Thesis / key insight (<=2,000 words) |
| 20 | `podcast_survey__jia_q6` | Jia Q6 | Passionate | Feelings the talk should inspire |
| 21 | `podcast_survey__jia_q7` | Jia Q7 | Passionate | Speaking tone |

### Group 3 - engine WRITE-back fields (7)

All dataType `LARGE_TEXT` (live legacy; spec draft said TEXT for several - adopted live because the engine byte-asserts the KEY, not the dataType, and does URL hygiene at write time). folder `Podcast Survey`.

| # | Create name | Key status | dataType | Notes |
|---|---|---|---|---|
| 22 | `podcast_survey_episode_url` | VERBATIM (engine EPISODE_URL_KEY) | LARGE_TEXT | Podbean permalink. Written LAST + ALONE; its change fires WF-3 (04). |
| 23 | `podcast_survey_episode_title` | VERBATIM | LARGE_TEXT | |
| 24 | `podcast_survey_episode_description` | VERBATIM | LARGE_TEXT | |
| 25 | `finish_podcast_google_doc_link` | VERBATIM | LARGE_TEXT | Episode Package doc link (bare URL). |
| 26 | `podcast_transcript_link` | VERBATIM | LARGE_TEXT | Speech Script doc link (bare URL). |
| 27 | `podcast_full_transcript` | VERBATIM | LARGE_TEXT | Optional transcript text store. |
| 28 | `book_teaser` | VERBATIM (engine BOOK_TEASER_KEY) | LARGE_TEXT | Interview mode only. NEW field - no legacy counterpart (old review §4). Bare URL. Ships in template so no client hits the missing-field reminder. |

**Field QC:** all 28 create-names present; derived `contact.<name>` keys byte-for-byte; the four double-underscore keys intact (`podcast_survey__additional_info`, `podcast_survey__quick_visual_description`, and all ten Group 2 keys); ZERO `anthology` substring anywhere (no-conflation hard gate); RADIO option labels correct on fields 1 and 2.

---

## SECTION B - CUSTOM VALUES (6, location level)

All SPEC-DEFINED portability placeholders (the engine reads NONE directly; the two intake workflows read 1-5 as merge fields so the snapshot ships with placeholders and per-client provisioning is a 5-value fill). Idempotent: GET customValues, create only missing.

| # | Custom value name | Template content | Filled by |
|---|---|---|---|
| 1 | `podcast_show_name` | `SET_AT_PROVISIONING` | Provisioner (payload `show_name`, required in Interview mode) |
| 2 | `podcast_host_name` | `SET_AT_PROVISIONING` | Provisioner (payload `host_name`, required in Interview mode) |
| 3 | `podbean_podcast_id` | `SET_AT_PROVISIONING` | Provisioner (payload `podcast_id`, required always) |
| 4 | `podcast_intake_webhook_url` | `https://SET-AT-PROVISIONING/hooks/podcast-intake` | Provisioner (Cloudflare Tunnel host of the client box; never Tailscale) |
| 5 | `podcast_intake_hook_secret` | `SET_AT_PROVISIONING` | Provisioner (`PODCAST_INTAKE_HOOK_SECRET`) |
| 6 | `podcast_snapshot_version` | `v2.0.0` | Build stamps LAST (idempotency marker) |

**DECISION on custom value #5 (secret transport):** DEFAULT = keep the custom-value form; both intake workflows reference `{{custom_values.podcast_intake_hook_secret}}`. WHY: it keeps the snapshot fully portable (per-client = fill 5 values, edit 0 workflows). CAVEAT (recorded): a custom value is visible to any user in the subaccount UI; the template ships only the placeholder, and per client the operator MAY instead blank this custom value and paste the secret directly into the two intake workflows' webhook headers. Operator-overridable per client; not a build blocker.

---

## SECTION C - TAGS (2, exact strings)

Pre-create via the API rail (they are the engine's enrollment-verification surface). **KEEP the space-separated strings below - NOT the legacy hyphenated variants.**

1. `podcast episode is ready`
2. `Podcast Completed Survey Style`

**Authority:** `scripts/caf/enrollment/enroll.py` hardcodes `WF_TAGS = {WF_04: "Podcast Completed Survey Style", WF_06: "podcast episode is ready"}` and verifies enrollment with `has_tag()`, comparing `tag.strip().lower()` - case-insensitive but NOT hyphen-insensitive. The legacy hyphenated tags (`podcast-completed-survey-style`, `podcast-episode-is-ready`, old review §6.7) would lowercase to a hyphenated string that never equals the space-separated one, so they would SILENTLY FAIL enrollment verification. The workflows below MUST apply these two exact strings.

---

## SECTION D - WORKFLOWS (4 required + 1 optional)

Names of 04 and 06 are EXACT and engine-asserted (`enroll.py` resolves by these names). WF-1/WF-2 post to ONE box endpoint carrying ALL fields; the BOX does the style routing, so neither intake workflow needs an internal IF/ELSE branch (unlike the retired legacy n8n workflows, which branched to per-style webhooks). Build via Skill 44 `caf workflows build` (Firebase refresh token; PLAN MODE gate first; parentKey-first). Order: 04, 06, 01, 02.

### WF-1: `01-Podcast Intake Submitted (Interview)`
- **Trigger:** Survey Submitted, survey = `ZHC Podcast Intake - Interview Style`.
- **Action:** Custom Webhook POST -> `{{custom_values.podcast_intake_webhook_url}}`.
- **Payload `customData`:**
  - `source`: `podcast-intake` (static)
  - `mode`: `interview_style_podcast` (static)
  - `style`: `{{contact.podcast_survey_writing_style}}`
  - all 10 Group 2 fields, each under a payload key = its real legacy key: `podcast_survey__barry_q1`, `podcast_survey__barry_q6`, `podcast_survey__brene_q1`, `podcast_survey__brene_q6`, `podcast_survey__dan_q1`, `podcast_survey__dan_q2`, `podcast_survey__dan_q7`, `podcast_survey__jia_q1`, `podcast_survey__jia_q6`, `podcast_survey__jia_q7` (each `{{contact.<key>}}`; unfilled branches arrive empty)
  - `visual_description`: `{{contact.podcast_survey__quick_visual_description}}`
  - `smiq`: `{{contact.podcast_interview_smiq}}`
  - `additional_info`: `{{contact.podcast_survey__additional_info}}`
  - `preferred_pronoun`: `{{contact.my_preferred_pronoun}}`
  - `first_name`, `last_name`, `email`, `phone`: standard contact merge fields
  - `show_name`: `{{custom_values.podcast_show_name}}`; `host_name`: `{{custom_values.podcast_host_name}}`; `podcast_id`: `{{custom_values.podbean_podcast_id}}`
  - `contact_id`, `location_id`: GHL standard merge fields
  - `secret`: `{{custom_values.podcast_intake_hook_secret}}` (header if supported, else payload field)
- **Required-to-start (payload law):** mode, style, contact_id, location_id, podcast_id, first_name, show_name, host_name.

### WF-2: `02-Podcast Intake Submitted (Personal)`
- **Trigger:** Survey Submitted, survey = `ZHC Podcast Intake - Personal Podcast`.
- Same action + payload as WF-1 EXCEPT: `mode`: `personal_podcast_style` (static); `style`: `{{contact.select_your_presentation_style_personal_podcast}}` (dedicated field - see resolved open question); ADD `date_for_release`: `{{contact.date_for_release}}`; OMIT `show_name` / `host_name`.
- **Required-to-start:** mode, style, contact_id, location_id, podcast_id, first_name.

### WF-3: `04-Podcast is Completed` (EXACT name)
- **Trigger:** Custom Field Changed - field = `podcast_survey_episode_url`.
- **Actions:** Add Contact Tag `Podcast Completed Survey Style` (engine's caf-observable enrollment proof), then client-facing SMS/email notification placeholders (each client's own copy; the box engine NEVER sends customer messages - Convert and Flow owns messaging).

### WF-4: `06-Podcast_Episode_Is_Ready` (EXACT name, underscores included)
- **Trigger:** Contact Tag Added `podcast episode is ready` (exact string).
- **Actions:** the client-facing "your episode is ready" notification placeholders. Enrolled EXPLICITLY by the engine at Step 17 (by workflow ID, or by applying this trigger tag). Build so tag-trigger enrollment works.
- NOTE (old review §6 item 8): the legacy `06` contained NO client messaging (only tag + opportunity move). The new build's placeholder notification steps are NEW scope, deliberately added so the template ships a ready-to-customize notification; the box engine still owns none of it.

### WF-5 (OPTIONAL): `05-Podcast Board Mover`
- Only if the optional ops pipeline (Section E) is built. Trigger = Custom Field Changed `podcast_survey_episode_url`; action = move the contact's opportunity to the terminal stage. Engine never drives the pipeline.

---

## SECTION E - PIPELINE (OPTIONAL, ops-visibility only)
`Podcast Production`: Received, Researching, Writing, QC, Art, Audio, Publishing, Enrolling, Complete. No public create API - the ONE hand-built (UI) object if built at all, else skipped. NOT required for the engine. Build WF-5 only if this is built.

---

## SECTION F - THE COMPLETE SURVEY QUESTION + ROUTING MAP (browser-builder ready)

Two GHL SURVEYS (conditional, multi-step), 0 plain forms. Built via Skill 6 headless-browser survey builder (TOKEN-ONLY Firebase seed, sub-account gate, singleton pooled browser, `--dry-run` first, map ONLY pre-existing fields via Add Object Fields, `qc-built-form.sh` per survey). Question text below is VERBATIM from `config/questionnaires/*.json`.

**TOPOLOGY NOTE (contingency, old review §8):** the workflow-level branch logic proves exactly 4 Interview branches + 2 Personal branches and the router field, but the survey builder's native page-jump wiring could NOT be recaptured (auth reached the sign-in form; not touched, per rule). Section 5A of the spec still requires a fresh read-only capture with a re-grabbed token before Phase 2. If that capture reveals ONE combined survey, rebuild it faithfully - the field bindings below are unchanged; the two intake workflows then filter on the mode-bearing field instead of one-workflow-per-survey.

### SURVEY 1: `ZHC Podcast Intake - Interview Style`
Audience: the GUEST (SHUA lead-gen). `show_name` / `host_name` are NEVER asked (per-client custom values). Never guess the guest's name.

**Step 1 - Style selection (required) - THE Q1 ROUTER:**
Radio -> `contact.podcast_survey_writing_style`. Option VALUES (short labels the engine/workflow branch on); put the parenthetical promise in the question help text, not the value:
1. `Counter Intuitive` -> routes to Branch A
2. `Vulnerable` -> routes to Branch B
3. `Provocative` -> routes to Branch C
4. `Passionate` -> routes to Branch D

(Help-text promises, verbatim from questionnaires: Counter Intuitive = "Introduce a different way of thinking about something." ; Vulnerable = "High levels of empathy and perfect for people who are sharing emotional and personal stories of tragedy and triumph." ; Provocative = "In your face, disruptive, and willing to challenge the norm." ; Passionate = "Inspirational and Motivational." The engine mapper also accepts the full long label `Counter Intuitive (Introduce a different way of thinking about something.)` etc. via `accepted_labels`, so if the builder stores the long label the engine still normalizes - but the GHL survey option VALUE should be the short label to keep it clean.)

**Branch A - Counter Intuitive (5 content Qs + contact/consent):**
| Pos | Question (verbatim) | Required | Maps to |
|---|---|---|---|
| 1 | "What surprising insight or unexpected perspective will you share in your talk that might challenge how people typically think about this topic?" (guidance: be detailed; the majority of the episode is based on this; include details, quotes, affirmations, stories; up to 2,000 words) | YES | `contact.podcast_survey__barry_q1` |
| 2 | "How would you describe your speaking tone?" | YES | `contact.podcast_survey__barry_q6` |
| 3 | "Visually describe the type of image you want on your podcast." (guidance: we create a graphic image from this) | YES | `contact.podcast_survey__quick_visual_description` |
| 4 | "VERY IMPORTANT Being Totally Transparent: What is the number 1 thing that you are struggling with related to [topic]?" (the SMIQ; the blank is customized per person) | YES | `contact.podcast_interview_smiq` |
| 5 | "Share any additional information and details that will be beneficial for us to know." | no | `contact.podcast_survey__additional_info` |

**Branch B - Vulnerable (5 content Qs + contact/consent):**
| Pos | Question (verbatim) | Required | Maps to |
|---|---|---|---|
| 1 | "What big idea or key message do you want your listeners to walk away with?" (same detail guidance, up to 2,000 words) | YES | `contact.podcast_survey__brene_q1` |
| 2 | "How would you describe your speaking tone?" | YES | `contact.podcast_survey__brene_q6` |
| 3 | "Visually describe the type of image you want on your podcast." | YES | `contact.podcast_survey__quick_visual_description` |
| 4 | SMIQ (same wording as Branch A pos 4) | YES | `contact.podcast_interview_smiq` |
| 5 | "Share any additional information and details that will be beneficial for us to know." | no | `contact.podcast_survey__additional_info` |

**Branch C - Provocative (6 content Qs + contact/consent; the ONLY 2-thesis path):**
| Pos | Question (verbatim) | Required | Maps to |
|---|---|---|---|
| 1 | "What popular assumption in your field needs to be challenged or rethought?" (detail guidance, up to 2,000 words) | YES | `contact.podcast_survey__dan_q1` |
| 2 | "What fresh perspective or evidence challenges this assumption?" | YES | `contact.podcast_survey__dan_q2` |
| 3 | "How would you describe your speaking tone?" | YES | `contact.podcast_survey__dan_q7` |
| 4 | "Visually describe the type of image you want on your podcast." | YES | `contact.podcast_survey__quick_visual_description` |
| 5 | SMIQ | YES | `contact.podcast_interview_smiq` |
| 6 | "Share any additional information and details that will be beneficial for us to know." | no | `contact.podcast_survey__additional_info` |

**Branch D - Passionate (6 content Qs + contact/consent):**
| Pos | Question (verbatim) | Required | Maps to |
|---|---|---|---|
| 1 | "What is the one key insight or message your listeners should remember from your talk?" (detail guidance, up to 2,000 words) | YES | `contact.podcast_survey__jia_q1` |
| 2 | "What feelings or emotions do you want your talk to inspire in your listeners?" | YES | `contact.podcast_survey__jia_q6` |
| 3 | "How would you describe your speaking tone?" | YES | `contact.podcast_survey__jia_q7` |
| 4 | "Visually describe the type of image you want on your podcast." | YES | `contact.podcast_survey__quick_visual_description` |
| 5 | SMIQ | YES | `contact.podcast_interview_smiq` |
| 6 | "Share any additional information and details that will be beneficial for us to know." | no | `contact.podcast_survey__additional_info` |

**Final step (all 4 branches converge) - Contact and consent (required):**
- First Name, Last Name, Email, Phone (GHL standard contact fields, via Quick Add).
- Optional: "What is your preferred pronoun?" -> `contact.my_preferred_pronoun` (design decision: collect here so it is never guessed; questionnaires index declares it a standing Additional Info field).
- Plain Terms and Conditions block, verbatim consent text: consent to receive SMS notifications, alerts and occasional marketing communication from BlackCEO LLC; "Message frequency varies. Message and data rates may apply. Text HELP to (301) 579-0472 for assistance. Reply STOP to unsubscribe at any time."

Fixture synthetic submission: guest "Ava Example", style Provocative, assumption "more options always help buyers", evidence "choice overload data", tone "warm but direct".

### SURVEY 2: `ZHC Podcast Intake - Personal Podcast`
Audience: the CLIENT (own weekly episode in cloned voice, Solo preset). Two style branches only.

**Step 1 - Style selection (required) - THE Q1 ROUTER:**
Radio -> `contact.select_your_presentation_style_personal_podcast`. Option VALUES exactly:
1. `Counterintuitive` -> routes to Branch A
2. `Passionate` -> routes to Branch B

(RESOLVED OPEN QUESTION - see Section G. Personal survey writes the DEDICATED field, not the shared `podcast_survey_writing_style`.)

**Branch A - Counterintuitive (5 content Qs, then release date, then contact/consent):** identical question wording and field bindings as Survey 1 Branch A:
| Pos | Maps to |
|---|---|
| 1 (thesis) | `contact.podcast_survey__barry_q1` |
| 2 (tone) | `contact.podcast_survey__barry_q6` |
| 3 (visual) | `contact.podcast_survey__quick_visual_description` |
| 4 (SMIQ) | `contact.podcast_interview_smiq` |
| 5 (additional, optional) | `contact.podcast_survey__additional_info` |

**Branch B - Passionate (6 content Qs, then release date, then contact/consent):** identical to Survey 1 Branch D:
| Pos | Maps to |
|---|---|
| 1 (thesis/insight) | `contact.podcast_survey__jia_q1` |
| 2 (emotions) | `contact.podcast_survey__jia_q6` |
| 3 (tone) | `contact.podcast_survey__jia_q7` |
| 4 (visual) | `contact.podcast_survey__quick_visual_description` |
| 5 (SMIQ) | `contact.podcast_interview_smiq` |
| 6 (additional, optional) | `contact.podcast_survey__additional_info` |

**Release-date step (both branches, before contact/consent):**
- "When would you like this episode to be released?" date picker -> `contact.date_for_release` (optional; a future date schedules the Podbean episode instead of publishing immediately).

**Final step - Contact and consent:** same block as Survey 1 (First/Last/Email/Phone, optional pronoun -> `contact.my_preferred_pronoun`, same verbatim consent text).

---

## SECTION G - RESOLVED DECISIONS

1. **Group 2 field keys (spec-invented -> real legacy):** adopt `podcast_survey__barry_q1/q6`, `__brene_q1/q6`, `__dan_q1/q2/q7`, `__jia_q1/q6/q7`. WHY: not engine-asserted (absent from `constants.py READ_KEYS`; resolved positionally via the webhook), so the legacy keys cost nothing engine-side and preserve continuity; E1 aliases FROM these keys.
2. **Visual-description key:** `podcast_survey__quick_visual_description` (DOUBLE underscore) - the real legacy key; spec draft's single-underscore was wrong.
3. **Tags:** keep `Podcast Completed Survey Style` / `podcast episode is ready` (space-separated), NOT the legacy hyphenated strings. WHY: `enroll.py WF_TAGS` + `has_tag()` case-insensitive-but-hyphen-sensitive comparison; hyphenated legacy tags would silently fail verification.
4. **Personal-survey Q1 field (THE flagged open question, old review §3/§7):** RESOLVED to the DEDICATED field `select_your_presentation_style_personal_podcast`. WHY: the box engine's `constants.py READ_KEYS` includes it and `questionnaires/index.json` names it the `personal_variant_field` for style resolution; it keeps the two style selectors cleanly separated; the box mapper reads either field and normalizes both values; the legacy's shared-field branch was a retired-n8n implementation detail, not a box-engine constraint. WF-2 sends `style` from this dedicated field; no IF/ELSE branch needed (box routes).
5. **dataTypes:** adopt live legacy - `my_client_smiq_answers`/`my_client_smiq_history` = TEXT; all Group 3 write-backs + `book_teaser` = LARGE_TEXT. WHY: engine asserts KEYS not types; live values are proven.
6. **Custom value #5 secret transport:** DEFAULT custom-value form (portable snapshot); per-client operator override to paste-into-workflow-header allowed. Recorded, not a blocker.

## SECTION H - DELIBERATELY EXCLUDED FROM THE SNAPSHOT (conscious scope, old review §4/§5/§7)
These legacy features are NOT carried into v2 (leaner snapshot; recorded so nothing is silently lost):
- Batch/pre-scheduled multi-episode mode (`single_episode_or_4_pre_scheduled_episodes` + 8 `episode_N_details` + `day_of_the_week`).
- The `2nd-*` parallel-show family (two shows on one subaccount).
- FB Lead Ads side-channel (workflows 02/02a/03 + `podcast-lead-from-fb-ad` tag + FB Conversion API).
- Legacy extra custom values (`Podcast_Channel_Name`, `About My Podcast Channel`, `Be_Featured_Link`, `Work_With_Us_Link`, Google Doc/Sheet IDs, ElevenLabs voice/key/speed, `podcast_rules`).
- The SMIQ-history running AI-context workflow (`SMIQ Answer Tracker`) and the `05-Create Note...SMIQ` note workflow.
- Post-completion upsell SMS + links.
- Engine swap already known: legacy ElevenLabs -> new Fish Audio/Kie.ai; legacy n8n webhook target -> new client-box Cloudflare tunnel. The stray make.com `{"black woman focused":"yes"}` node is legacy contamination and is NOT replicated.

> **⚠️ OVERRIDE — 2026-07-10 (explicit operator directive).** The workflow-level §H exclusions above were RECREATED into the NEW sub-account `CjxATjhv9Gt21qSqURIt` per an explicit operator override of this section. The 8 recreated legacy workflows (the task named 9; the 9th, "SMIQ Tracker", is a **folder**, not a workflow — recreated as a folder) are: `01a Update FB audience`, `02 Fb Lead didn't complete`, `02a 2nd Fb interview`, `03 Podcast LeadForm Fb Ad`, `04a 2nd interview completed`, `05 Create Note SMIQ`, `07 2nd Podcast Survey v2.1`, `SMIQ Answer Tracker`. See **SECTION J-2** for live ids/status/triggers and the honest dependency-gap list. This override does NOT re-cut the snapshot: these land AFTER the v1 golden snapshot (`IEmFFkIngiskcfJk9MH6`) was cut, so they only ship once a **v2 snapshot re-cut** is taken from `CjxATjhv9Gt21qSqURIt`. The non-workflow §H exclusions (batch mode, extra custom values, upsell SMS, engine swaps) remain excluded — only the workflow objects were recreated.

## SECTION I - BUILD ORDER (serial, per spec Section 4)
Phase 0 preflight prove -> Phase 0.5 old-survey capture (HARD GATE) -> Phase 1 API objects (28 fields -> 6 values -> 2 tags) -> Phase 2 surveys via Skill 6 (Survey 1 then Survey 2, dry-run->live->QC each) -> Phase 3 workflows via Skill 44 (04, 06, 01, 02) -> Phase 4 independent QC + stamp `podcast_snapshot_version=v2.0.0` LAST -> Phase 5 snapshot from `CjxATjhv9Gt21qSqURIt`, verify 28 fields + 6 values + 2 surveys + 4 workflows + 2 tags ship inside it.

Engine-side companion (NOT part of this GHL build): E1 = extend the webhook mapper's `survey_answer_keys_by_style` + fixtures with the real legacy Group 2 keys in style order (CI: barry_q1,barry_q6 ; Vul: brene_q1,brene_q6 ; Pro: dan_q1,dan_q2,dan_q7 ; Pas: jia_q1,jia_q6,jia_q7), the shared visual/smiq/additional read from their dedicated fields.

---

## SECTION J - WORKFLOW BUILD STATE (LIVE, verified 2026-07-10)

All four required workflows exist in the TEMPLATE sub-account `CjxATjhv9Gt21qSqURIt`, each `status=published` with its trigger COMMITTED (non-null `triggersFilePath`) and `active=true`. Verified by live re-GET on the internal rail. Re-run the gate any time: `scripts/verify-podcast-ghl-workflows.py` (exit 0 = all four PASS).

| WF | Live workflow id | Trigger type | Trigger condition | active | steps |
|---|---|---|---|---|---|
| 01-Podcast Intake Submitted (Interview) | `e008e027-3505-4fa2-87c0-a624357f53a6` | `survey_submission` | survey = `ExAPmAV3Llo0tREenfJy` (ZHC Podcast Intake - Interview Style) | true | 1 (webhook -> box) |
| 02-Podcast Intake Submitted (Personal) | `55d7f054-757e-43c1-933a-0faf34c60f69` | `survey_submission` | survey = `vX5BuhxSeucMHrcKOwEn` (ZHC Podcast Intake - Personal Podcast) | true | 1 (webhook -> box) |
| 04-Podcast is Completed | `912d7ac7-ff26-4a5e-810c-a0957d70dfb0` | `contact_changed` | `has-changed` on `contact.podcast_survey_episode_url` (field id `UQUZa9x80H4JWq52RbmI`) | true | 3 (tag, email, sms) |
| 06-Podcast_Episode_Is_Ready | `91c0c5a4-3dcb-4a6e-b8e1-73d8b812148f` | `contact_tag` | tag added = `podcast episode is ready` | true | 2 (email, sms) |

**Recreation mechanism (PROVEN, supported rail).** Workflows/triggers are built via the GHL INTERNAL API at `backend.leadconnectorhq.com` (Firebase-JWT `token-id` header, agency/owner refresh token) — the SAME rail Skill-44 `caf` uses. There is NO public create-workflow API; the public `/workflows/` endpoint is read-only and the agency PIT 403s on sub reads. Endpoints used: list `GET /workflow/{loc}/list`, read steps `GET /workflow/{loc}/{wf}`, read triggers `GET /workflow/{loc}/trigger?workflowId={wf}`, create trigger `POST /workflow/{loc}/trigger`, link trigger `PUT /workflow/{loc}/trigger/{tr}` (sets `targetActionId`), commit+activate `PUT /workflow/{loc}/{wf}`.

**ACTIVATION MODEL (the subtlety that caused the original "inactive shell" failure).** A trigger is only live when BOTH are true: (a) it is committed into the workflow's trigger file, and (b) the workflow doc carries `status:"published"`. Committing is a `PUT /workflow/{loc}/{wf}` that includes `triggersChanged:true` + `oldTriggers`/`newTriggers` (the trigger objects, `active:true`) AND re-asserts `status:"published"` and the current `version` and the EXISTING `workflowData.templates`. Omitting `status` on that PUT silently demotes the workflow to draft and de-activates every trigger — so the commit PUT must always carry `status:"published"`. A bare `POST /workflow/{loc}/trigger` (or a `PUT /workflow/{loc}/trigger/{tr}` alone) creates the trigger row but leaves it `active:false` and uncommitted — this is exactly what shipped the first time.

**PER-CLIENT / POST-SNAPSHOT CAVEAT (verify after each provision).** GHL snapshot imports frequently land workflows in DRAFT with triggers inactive in the destination sub-account. Provisioning edits 0 workflows by design (§B/§I), so after cutting the snapshot AND after each `provision-podcast-client.sh` run, re-run `scripts/verify-podcast-ghl-workflows.py --location <client-loc> --token-env <client-refresh-var>` and, if any workflow is draft/inactive, re-publish it (toggle Publish in the builder, or re-assert `status:"published"` via the commit PUT above). This gate is the fail-loud check the first build lacked.

---

## SECTION J-2 - LEGACY WORKFLOWS RECREATED (per §H override, LIVE, verified 2026-07-10)

> **➡️ SUPERSEDED 2026-07-10 by SECTION K.** The dependency GAPS listed at the bottom of this
> section (dead pipeline, dead make.com/n8n webhooks, per-client FB steps, the SMIQ tracker
> firing on a field the podcast flow never writes) were RESOLVED — pipeline built + every
> `create_opportunity` remapped, dead webhooks removed, FB steps taken to the honest per-client
> template boundary, and the SMIQ capture made bulletproof. See **SECTION K** for the live
> after-state; the table/gaps below are kept as the pre-functionalization record.

Recreated into `CjxATjhv9Gt21qSqURIt` via the same PROVEN internal rail + activation model as §J. Steps copied VERBATIM from OLD `w4A5LiurmAjBbvJOXmyz` (step ids preserved so `goto`/`parentKey`/`next` stay wired); only trigger survey/field ids and the SMIQ update-target field were remapped OLD→NEW. Two folders created in NEW: **`AI Podcast Survey`** (`bad049cd-ace0-46a4-bb7f-201fc1016473`) and **`SMIQ Tracker`** (`b5b63418-b30b-4f65-9f52-624d36e41cb1`). The original 4 (§J) were NOT touched. Live re-GET below.

| Legacy WF | NEW live id | status | steps | trigger (NEW) | committed |
|---|---|---|---|---|---|
| 05-Create Note SMIQ | `bdf6c354-55b4-4913-8623-b0a73c385404` | published | 1 | `survey_submission` survey=`ExAPmAV3Llo0tREenfJy` (interview) — active | yes |
| SMIQ Answer Tracker | `0795e466-cfe2-4f05-845a-7751927839d9` | published | 1 | `contact_changed` on `contact.smiq_answers` (`habMrKcRAKTFN8EZP2RT`) — active; step writes `contact.smiq_history` (`i08poncoJMo6abdET5nI`) | yes |
| 04a-Podcast is Completed (2nd interview) | `f3776ba3-ad79-4d49-8f87-5ec47355e316` | published | 13 | `contact_changed` on `contact.podcast_survey_episode_url` (`UQUZa9x80H4JWq52RbmI`) — active | yes |
| 07-2nd Podcast Interview/Survey v2.1 | `34c8c3cd-43f8-4b1e-9a61-cd1b2fd77de3` | published | 17 | 2× `survey_submission` survey=`vX5BuhxSeucMHrcKOwEn` (personal) — active | yes |
| 03-Podcast LeadForm Fb Ad | `8abd4d30-ee3f-4e40-a60f-dfd6f3307da6` | published | 3 | **NONE** (FB Lead Form trigger — see gaps) | n/a |
| 01a-Update FB audience | `5f6c90a9-6d41-4d71-b822-695b670da8dd` | draft | 1 | **NONE** (FB — see gaps) | n/a |
| 02-Fb Lead didn't complete | `e8fc8a75-43bc-4f97-b951-3f446372f4ac` | published | 29 | **NONE** (FB Lead Form trigger — see gaps) | n/a |
| 02a-2nd Fb interview | `49c56f90-50d3-47cb-97fc-7ab8b6cc7ac5` | draft | 29 | **NONE** (FB Lead Form trigger — see gaps) | n/a |

`status`/`draft` mirror OLD exactly. The 4 FB workflows carry **NO trigger in OLD either** — OLD's own names say "MUST ADD TRIGGER FOR FB LEAD FORM AD"; their trigger arrays are `[]` live. No trigger was fabricated.

**DEPENDENCY GAPS — what each recreated workflow needs to actually fire (honest, complete):**
- **05 / SMIQ Answer Tracker / 04a** — FULLY FUNCTIONAL in NEW as-is (triggers + referenced fields all exist). NOTE: 04a fires on the SAME `podcast_survey_episode_url` change as the required §J `04`, so BOTH run on completion (faithful to OLD, which also had 04 + 04a); 04a uses the hyphenated tag `podcast-completed-survey-style` (≠ the canonical space tag `Podcast Completed Survey Style` in §C) and its `internal_notification` needs an assigned user to reach anyone.
- **07** — trigger fires, but 3 step-level deps are dead/absent in NEW: (1) `facebook_add_to_custom_audience` needs a FB integration + audience (OLD `act_666564130483785` / `120225224137710367`); (2) two external webhooks — make.com `hook.us1.make.com/98jx8j883frnv18uw95vfskibbf2r0cl` and n8n `n8n.apptime.me/webhook/954f12b5-...` — are LEGACY external targets, NOT the new client-box Cloudflare tunnel, and are almost certainly dead; (3) `create_opportunity` references OLD pipeline `yOomdMVVZgM9x4oB2fvK` / stage — no such pipeline in NEW (§E pipeline is optional/unbuilt). Uses hyphenated tags `podcast-2nd-interview-survey-submitted`, `podcast-survey-submission-completed`.
- **03** — needs: (a) a **FB Lead Form trigger** (none in OLD/NEW); (b) FB Conversion API config — OLD carries placeholder pixel `8787656` / token `2343243` ("MUST BE UPDATED"); (c) `create_opportunity` OLD pipeline `yOomdMVVZgM9x4oB2fvK` / stage `58c6add9-...` (absent in NEW). Applies tag `podcast-lead-from-fb-ad`.
- **01a** — needs: a trigger (OLD intended "survey completed") + a FB Custom Audience integration (OLD `act_666564130483785` / audience `120225224137710367`). One step only.
- **02 / 02a** — need: (a) a **FB Lead Form trigger**; (b) FB add/remove Custom Audience integration; (c) `create_opportunity` OLD pipeline (absent in NEW); (d) custom value `{{custom_values.podcast_survey_podcast_title}}` referenced in email copy (not among §B's 6 custom values). 29-step reminder ladders (wait/if_else/goto) recreated intact.

**No fabrication:** FB integrations, FB Lead Forms, the OLD pipeline, and the external webhook targets were NOT connected or invented — the workflows are faithful recreations of OLD's structure, and the above is the exact connect-list for them to fire. Re-GET verify: `legacy-recreate/verify_final.py` (scratchpad) or list `GET /workflow/CjxATjhv9Gt21qSqURIt/list`.

---

## SECTION K - FB WORKFLOWS FUNCTIONALIZED + SMIQ BULLETPROOFED (LIVE, verified 2026-07-10)

Executed on the internal rail against `CjxATjhv9Gt21qSqURIt` (write-guarded to NEW; OLD
`w4A5LiurmAjBbvJOXmyz` read-only). Both gates exit 0: `scripts/verify-podcast-ghl-workflows.py`
(required 4 still published/active) AND the new `scripts/verify-podcast-smiq.py` (this work).

### K.1 - Pipeline built + every `create_opportunity` remapped
Created **`Podcast Interview System Pipeline`** id **`a9RNaoDAYoVqLLaS964Q`** (mirrors OLD
`yOomdMVVZgM9x4oB2fvK`), 5 stages: `Lead Form Ad` `7363deae-1e88-43d2-952a-4d407023a684` ·
`Did Not Complete Interview` `893d6321-81ac-46da-a86f-f85294987398` · `Completed Interview
Survey Form` `68774da0-9ad5-4172-b5f4-7b58bc03775f` · `Podcast Episode Is Ready`
`a5c4c4ff-5593-4dce-bd0e-bad8b0b5f0a4` · `Made A Purchase` `e54ec70c-cb95-4132-b30e-75359dd8c151`.
Every `create_opportunity` step in 03 (Lead Form Ad), 02 + 02a (Did Not Complete Interview),
and 07 (Completed Interview Survey Form) was remapped OLD pipeline/stage -> NEW. Zero OLD
pipeline id remains in any workflow (re-GET verified).

### K.2 - Dead webhooks removed from 07 (no dead endpoint left pointed-to)
07 shrank 17 -> 13 steps. Removed: the make.com `hook.us1.make.com/...2r0cl` node carrying the
stray `{"black woman focused":"yes"}` payload (legacy contamination, already flagged NOT-to-
replicate in §H); the two `n8n.apptime.me/webhook/954f12b5-...` per-style production webhooks
(their job — box-side production — is owned in v2 by the required `02-Podcast Intake Submitted
(Personal)` posting to `{{custom_values.podcast_intake_webhook_url}}` (client-box Cloudflare
tunnel), where the BOX does per-style routing, so 07's per-style n8n branch is superseded); and
07's per-client `facebook_add_to_custom_audience` step (01a owns that function). 07 kept its
tags + branch + (remapped) opportunities + reminder waits, stays published, both triggers
retargeted to the new head and active. No `make.com`/`apptime.me` string remains anywhere.

### K.3 - FB steps at the honest per-client template boundary (nothing fabricated)
The four FB-ad workflows are STRUCTURALLY CORRECT but **DRAFT**, with the hard-coded OLD
Facebook ids **blanked** (`facebook_account_id` / `facebook_custom_audience_id` = "" on 01a/02/
02a; `pixel_id` / `access_token` = "" on 03) so no other account's Facebook ids ship in a
fleet template. Draft is REQUIRED here (and correct): GoHighLevel refuses to PUBLISH a workflow
whose Facebook custom-audience/CAPI step is unconfigured (`MISSING_REQUIRED_FIELDS`), and these
cannot run until a client connects Facebook anyway. This is DELIBERATE per-client-activation
state, NOT the original "inactive shell" bug (that bug was the required 4 intake workflows
silently shipping unpublished + triggerless; those 4 remain published + active + committed, and
the fail-loud gate covers them).

| FB workflow | live id | template state | needs at per-client connect |
|---|---|---|---|
| 01a Update FB audience | `5f6c90a9-6d41-4d71-b822-695b670da8dd` | draft, FB audience blanked, 1 step | connect FB + pick audience; add a "survey completed" trigger; publish |
| 02 Fb Lead didn't complete | `e8fc8a75-43bc-4f97-b951-3f446372f4ac` | draft, NEW pipeline, FB add/remove blanked, 29-step ladder | connect FB + pick audience; add FB Lead Form trigger; publish |
| 02a 2nd Fb interview | `49c56f90-50d3-47cb-97fc-7ab8b6cc7ac5` | draft, NEW pipeline, FB blanked, 29-step ladder | connect FB + pick audience; add FB Lead Form trigger; publish |
| 03 LeadForm Fb Ad | `8abd4d30-ee3f-4e40-a60f-dfd6f3307da6` | draft, NEW pipeline, CAPI pixel/token blanked, 3 steps | connect FB + pixel/CAPI; add FB Lead Form trigger; publish |

### K.4 - Per-client FB-connect provisioning step (process improvement, authorized)
`scripts/activate-podcast-fb-workflows.py` (NEW): given the client's connected FB ids
(`--fb-account`/`--fb-audience`/`--fb-pixel`/`--fb-token`), fills the blanked FB steps and
PUBLISHES (activates) the four workflows; runs a DRY report with no ids. `provision-podcast-
client.sh` STEP 7 (`fb-ads-connect`, opt-in via `PODCAST_FB_ADS_READY=1`) records the connect
checklist and delegates to the activator. The Facebook OAuth connection + Lead Form/Audience
selection is done by the client in the GHL UI (inherently per-client); the FB Lead Form trigger
for 02/02a/03 is added in the builder because it must bind a live connected form.

### K.5 - SMIQ Tracker BULLETPROOFED (operator: "very important")
Evidence (`scripts/caf/field_layer/constants.py` READ_KEYS + `config/questionnaires/index.json`):
the podcast SMIQ answer ALWAYS lands in `contact.podcast_interview_smiq` (canonical source of
record); NOTHING in the podcast flow writes `contact.smiq_answers`. So the recreated SMIQ Answer
Tracker (which triggered on `smiq_answers`) NEVER fired on a podcast submission, and its
accumulator value referenced `{{contact.smiq_answer}}` — a field key present in NEITHER OLD nor
NEW (a real typo) — so the just-changed answer was dropped. Fixes (live-verified):
- **SMIQ Answer Tracker** `0795e466-cfe2-4f05-845a-7751927839d9`: trigger now `contact_changed`
  ACTIVE on `contact.podcast_interview_smiq` (`pTkurBfVPJOuiAv7HELI`); accumulator reads
  `{{contact.podcast_interview_smiq}}`, still self-appends `{{contact.smiq_history}}` and writes
  `contact.smiq_history` (`i08poncoJMo6abdET5nI`). Published + committed. Fires for BOTH surveys
  (both write `podcast_interview_smiq`). No re-trigger loop (writes a different field).
- **05 Create Note SMIQ** `bdf6c354-55b4-4913-8623-b0a73c385404`: added a 2nd trigger so it fires
  on the PERSONAL survey `vX5BuhxSeucMHrcKOwEn` too (was interview-only) — personal-podcast SMIQ
  answers now also get a timeline note. Both triggers active + committed; step reads
  `{{contact.podcast_interview_smiq}}`.
- **SMIQ fields (live keys/types confirmed):** `podcast_interview_smiq` (`pTkur`, LARGE_TEXT,
  canonical) · `smiq_history` (`i08pon`, LARGE_TEXT, accumulator target) · `smiq_answers`
  (`habMr`, LARGE_TEXT) · `my_client_smiq_answers` (`fPAbt`, LARGE_TEXT) · `my_client_smiq_history`
  (`AXIud`, LARGE_TEXT). NOTE: §A recorded the two `my_client_smiq_*` as TEXT (live OLD); in NEW
  they were built LARGE_TEXT — non-load-bearing (engine asserts KEYS not types; these are
  supporting-optional READ fields; not on the active tracker path).

### K.6 - OPEN DECISIONS for the operator (flagged, not guessed)
> **✅ ALL FOUR RESOLVED 2026-07-10 (operator-APPROVED) — applied LIVE on the internal rail
> against `CjxATjhv9Gt21qSqURIt`, demote-trap-safe, re-GET-verified. Both gates
> (`scripts/verify-podcast-ghl-workflows.py` + `scripts/verify-podcast-smiq.py`) exit 0 after.
> See SECTION K.8 for the after-state + evidence.** The original text of each open decision is
> preserved below for provenance; the resolution follows each item.
1. **07 vs 02 personal-survey collision:** both `07-2nd Podcast Interview/Survey v2.1` and the v2
   required `02-Podcast Intake Submitted (Personal)` trigger on the SAME personal survey
   `vX5BuhxSeucMHrcKOwEn`. 07 no longer posts production (webhooks removed) so there is no
   double-production today, but if 07 is ever re-pointed at the box it would double-fire.
   Recommend deciding whether 07 stays (CRM/opportunity side-effects only) or its trigger is
   retired in favor of 02. Not changed unilaterally.
   → **RESOLVED: 07 kept CRM-only, trigger(s) retired.** Both of 07's `survey_submission`
   triggers (`HM5lUUPFtao0MjgNCOPV`, `LG4QedMbESVeClkvCIqe`) DELETED; workflow re-committed
   `status:published`, all 13 steps intact, `triggers=[]`. It can no longer double-fire with the
   required `02` on the personal survey. Re-GET: 0 triggers.
2. **02/02a completion-tag semantics:** the reminder ladders stop reminding when the contact has
   tag `podcast-survey-submission-completed`. In v2 that tag is applied by 07 (personal), not by
   the required `01` interview intake — so a FB *interview* lead who completes may keep getting
   reminders. Recommend applying `podcast-survey-submission-completed` on interview-survey
   completion (or repointing the ladder check to the canonical `Podcast Completed Survey Style`).
   The ladder MECHANICS are sound (verified: escalating 60m/8h/2d/7d waits; the `goto` steps all
   jump to the completion handler, not a loop; terminal opportunity at day 7).
   → **RESOLVED: completion tag now applied on INTERVIEW completion.** Added an `add_contact_tag`
   step (tag `podcast-survey-submission-completed`) to the required **`01-Podcast Intake Submitted
   (Interview)`** (`e008e027-…`), chained after its intake webhook. WHY 01 (not 04/04a): the FB
   reminder ladders are "reminder to *complete the interview survey*", and their stop-condition is
   this tag; a lead is done being reminded the moment they SUBMIT the interview survey
   `ExAPmAV3Llo0tREenfJy` — which is exactly what fires `01`. This is the clean mirror of `07`,
   which already applies the same tag on PERSONAL survey submission. (`04`/`04a` fire on
   *episode-url produced*, which is days later — the wrong semantic point, would leave leads
   over-reminded meanwhile.) Demote-trap-safe: `01` re-asserted `status:published`, its
   `survey_submission` trigger stays committed + active, steps 1→2. Re-GET confirms + required-4
   gate still ALL PASS.
3. **`{{custom_values.podcast_survey_podcast_title}}`** appears in 02/02a email copy but is not
   among §B's 6 custom values, so it renders empty (cosmetic). Recommend the provisioner set it
   (or map the copy to `podcast_show_name`). Not a fire blocker; 29-step email bodies left intact.
   → **RESOLVED: remapped to `podcast_show_name`.** All 7 occurrences of
   `{{custom_values.podcast_survey_podcast_title}}` in **02 Fb Lead didn't complete**
   (`e8fc8a75-…`) and all 7 in **02a 2nd Fb interview** (`49c56f90-…`) were rewritten to
   `{{custom_values.podcast_show_name}}` (§B custom value #1, filled at provisioning). Both stay
   `status:draft` (per §K.3 FB-workflow boundary; verify-smiq still PASS). Re-GET: 0 old refs
   remain, 7 new refs each. NOTE (flag, out of approved scope, NOT changed): the same copy also
   references `{{custom_values.podcast_survey_host_name}}`, likewise absent from §B — recommend
   remapping to `podcast_host_name` in a follow-up.
4. **04a** (untouched) still fires on the same `podcast_survey_episode_url` change as the required
   `04` and uses the hyphenated tag `podcast-completed-survey-style`; its `internal_notification`
   needs an assigned user. Left as recreated (out of this task's FB/SMIQ scope) — flagged.
   → **RESOLVED: 04a's duplicate trigger retired.** 04a's `contact_changed` trigger
   (`d8Qvp8l44XpUNBaOfqDG`, on `contact.podcast_survey_episode_url` field `UQUZa9x80H4JWq52RbmI`)
   DELETED; workflow re-committed `status:published`, all 13 steps intact, `triggers=[]`. It no
   longer double-fires with the required `04` on the same episode-url change. Re-GET: 0 triggers.
   (04a's hyphenated tag + unassigned `internal_notification` are moot while it has no active
   trigger; left as recreated.)

### K.8 - K.6 RESOLUTION AFTER-STATE (LIVE, verified 2026-07-10)
Applied on the internal rail (`backend.leadconnectorhq.com`, Firebase-JWT `token-id`), write-guarded
to NEW `CjxATjhv9Gt21qSqURIt` (OLD `w4A5LiurmAjBbvJOXmyz` read-only; agency `Mct54Bwi1KlNouGXQcDX`
never touched). Trigger retirement = `DELETE /workflow/{loc}/trigger/{tr}` + re-commit
`PUT /workflow/{loc}/{wf}` with `newTriggers:[]`. Step-add + copy-edit = `PUT /workflow/{loc}/{wf}`
re-asserting `status` + `version` + `workflowData.templates` (demote-trap-safe; the required `01`
also re-asserted `triggersChanged`/trigger `active:true`).

| WF | id | change | after (re-GET) |
|---|---|---|---|
| 01 Interview intake (REQUIRED) | `e008e027-…` | +`add_contact_tag` `podcast-survey-submission-completed` | published, 2 steps, 1 active `survey_submission` trigger |
| 02 Fb Lead didn't complete | `e8fc8a75-…` | merge field →`podcast_show_name` (×7) | draft, 29 steps, 0 old refs |
| 02a 2nd Fb interview | `49c56f90-…` | merge field →`podcast_show_name` (×7) | draft, 29 steps, 0 old refs |
| 04a 2nd interview completed | `f3776ba3-…` | `contact_changed` trigger DELETED | published, 13 steps, 0 triggers |
| 07 2nd Podcast Survey v2.1 | `34c8c3cd-…` | both `survey_submission` triggers DELETED | published, 13 steps, 0 triggers |

Gates after (both exit 0): `verify-podcast-ghl-workflows.py` → required-4 (01/02/04/06) ALL PASS
(01 now `steps=2`, trigger still active); `verify-podcast-smiq.py` → SMIQ + FB (02/02a still
draft+clean) + pipeline + 07 (no dead endpoint) ALL PASS.

### K.7 - Snapshot note
This work — **including the four §K.6/§K.8 resolutions** — lands AFTER the v1 golden snapshot
(`IEmFFkIngiskcfJk9MH6`); it ships only on a v2 re-cut from `CjxATjhv9Gt21qSqURIt`. Per operator
doctrine the operator re-syncs the SAME snapshot id (`IEmFFkIngiskcfJk9MH6`) after the re-cut.
Repo changes are branch-only pending QC >= 8.5 (single-writer onboarding train); the repo version
roll + fleet rollout are deferred to the train, not done per-fix.

---

## SECTION L - GK-05/U67: SNAPSHOT v2 + `PODCAST_SNAPSHOT_ID` CONFIRMATION (mechanism)

**Spec:** GK-05 — P1 — Podcast golden snapshot v2 + `PODCAST_SNAPSHOT_ID` confirmation. **Deps:
GK-01/U63** (the publish-path fix must land BEFORE the golden snapshot bakes in the current
`image_url = null` failure as "golden"). As of this build U63 is **operator-gated/deferred**
(2 of 3 legs blocked; branch `skill6-v2/U63`; see LEDGER U63) — so this unit's live half cannot
proceed yet. This section ships the repo-side mechanism only, structurally gated on that
dependency, so the operator's live step (mirroring GK-04/U66, which Trevor executed personally
once GK-04's repo half was ready) is a single command once U63 clears.

**Canonical record:** `config/podcast-snapshot-registry.json` — the repo-side half of the BINARY
acceptance ("the v2 snapshot exists with its id recorded in `trevorotts1/openclaw-onboarding`").
Tracks `template_location_id` (`CjxATjhv9Gt21qSqURIt`), the Snapshot Provisioner n8n workflow id
(`ol9YLeCpvYdNsbsg`) and its env var name (`PODCAST_SNAPSHOT_ID`), and one row per snapshot
version (`v1` = live today at `IEmFFkIngiskcfJk9MH6`; `v2` = `snapshot_id: null`, `status:
pending`, `blocked_on: ["GK-01/U63"]` until cut). Per §K.7 precedent, a "v2 re-cut" may land
under the SAME snapshot id (operator doctrine re-syncs in place) rather than a newly-minted one —
the registry does not require v2's id to differ from v1's; that is the operator's call at cut
time, not a constraint this mechanism enforces.

**Gate:** `scripts/confirm-podcast-snapshot.py` (read `--help` for the full contract; unit-tested
in `scripts/tests/test_confirm_podcast_snapshot.py`, 34 tests, no network).
- `--record-snapshot v2 <id>` — repo-only write-back once the operator cuts the live snapshot
  (there is no public create-snapshot API — see Section I Phase 5; it is a hand-built GHL UI
  action, same class as every other snapshot cut in this manifest). Clears `blocked_on`, sets
  `status: cut-pending-n8n-confirm`. Never flips `current` — that stays a deliberate operator step
  taken only after the two proofs below both pass.
- `--confirm-n8n-value <value>` — compares a `PODCAST_SNAPSHOT_ID` value the operator already read
  back from the n8n deployment (its own channel — n8n exposes no REST endpoint for reading an
  arbitrary OS-level `$env.*` value by design, the same surface `N8N_BLOCK_ENV_ACCESS_IN_NODE`
  gates per `59-anthology-engine/config/n8n/README.md`) against the registry's recorded id,
  byte-for-byte.
- `--dry-run-provision` — fires ONE real request at the production `provision-snapshot` webhook
  via the already-proven `shared-utils/fire-provision-snapshot.sh` against a clearly-labeled
  SCRATCH client slug (`gk05-scratch-confirm`, never a real client), and classifies the response:
  PASS only on a clean 2xx accept; a literal 409 (`PODCAST_SNAPSHOT_ID` unset/stale) FAILs, and so
  does any other non-2xx outcome — "does not 409" names the known failure mode, not a license to
  accept a different live error. This is a genuine live side effect on production n8n; it is
  opt-in only and was not invoked by this build.

**Operator runbook (once GK-01/U63 clears):**
1. Cut (or re-sync) the v2 snapshot from `CjxATjhv9Gt21qSqURIt` in the GHL UI.
2. `scripts/confirm-podcast-snapshot.py --record-snapshot v2 <snapshot_id>`
3. Read `PODCAST_SNAPSHOT_ID` back from the Snapshot Provisioner deployment (n8n host/container),
   then `scripts/confirm-podcast-snapshot.py --confirm-n8n-value <value>` — must PASS.
4. `scripts/confirm-podcast-snapshot.py --confirm-n8n-value <value> --dry-run-provision` — must
   PASS (no 409).
5. Only then flip `"current": "v2"` in the registry (hand-edit or a follow-up script) and record
   the live-proof evidence, mirroring GK-04/U66's evidence pattern.
