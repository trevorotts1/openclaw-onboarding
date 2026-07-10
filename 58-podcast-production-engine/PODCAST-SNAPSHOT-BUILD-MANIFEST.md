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

## SECTION I - BUILD ORDER (serial, per spec Section 4)
Phase 0 preflight prove -> Phase 0.5 old-survey capture (HARD GATE) -> Phase 1 API objects (28 fields -> 6 values -> 2 tags) -> Phase 2 surveys via Skill 6 (Survey 1 then Survey 2, dry-run->live->QC each) -> Phase 3 workflows via Skill 44 (04, 06, 01, 02) -> Phase 4 independent QC + stamp `podcast_snapshot_version=v2.0.0` LAST -> Phase 5 snapshot from `CjxATjhv9Gt21qSqURIt`, verify 28 fields + 6 values + 2 surveys + 4 workflows + 2 tags ship inside it.

Engine-side companion (NOT part of this GHL build): E1 = extend the webhook mapper's `survey_answer_keys_by_style` + fixtures with the real legacy Group 2 keys in style order (CI: barry_q1,barry_q6 ; Vul: brene_q1,brene_q6 ; Pro: dan_q1,dan_q2,dan_q7 ; Pas: jia_q1,jia_q6,jia_q7), the shared visual/smiq/additional read from their dedicated fields.
