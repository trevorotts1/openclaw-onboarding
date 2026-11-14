# Client intake: one question bank, one answers file

Skill 49 (launch mode and legacy mode), Skill 71 and Skill 83 all ask the client the same questions from one bank and
write the answers to one file. Where the client answers (claude-nine, Claude Code or OpenClaw) changes only how a
question is shown, never which question is asked or where the answer goes.

| Piece | File |
|---|---|
| Question bank (62 questions, the canonical source) | `shared-utils/client_intake/question-bank.json` |
| Run-mode routing (`mode_routing`) | `shared-utils/client_intake/question-bank.json` + `engine.route_mode` |
| Engine: `next`, `record`, `resolve_unknown`, `check`, `finalize` | `shared-utils/client_intake/engine.py` |
| Colour help: logo, website, three palettes, safe default | `shared-utils/client_intake/palette_help.py`, `palette-defaults.json` |
| Answers file contract (C1) | `shared-utils/client_intake/answers.schema.json` |
| Two worked examples | `shared-utils/client_intake/fixtures/answers.elevation.json`, `answers.7fig.json` |

## What a client experiences

One short question at a time, in plain English, with a one-line reason ("why we ask"), at most three choices, and always
a fourth way out: **I'm not sure, help me**.

Colours work like this. The client sends colour codes or names, or says "help me". When two or more colours come
without roles, the engine asks exactly: *"Which of these is your MAIN color: the one people think of first when they
think of your brand? (#0A7E8C, #E76F51)"*. It then asks for the second colour and the accent only when there is a real
choice left, asks what the background should be, and picks readable text colour itself by contrast. If the client labels
roles in one message ("primary #0A7E8C, background white"), nothing more is asked.

## When the client does not know

1. First "I don't know": help. For colours the engine offers three ways: read the colours from the logo file, read them
   from the website (plain HTTP fetch of the page and its CSS; no browser, no agent-browser, no Playwright), or pick one of
   three palettes, each with roles, a plain-English reason and an example, and a readability check. For other questions it
   explains in plain English with examples.
   The client's next reply goes straight to `record(doc, id, reply)`, no special call: `1`, `2` or `3` picks a palette; a
   website link or a logo file path reads the colours and asks "Should I use them?", and a `yes` saves them; plain words
   such as "calm trust" reorder the three palettes. For the design style, the three feel words the help asks for get a
   recommendation, a `yes` saves it, and a second "not sure" uses those words instead of the plain default.
2. Second "I don't know": the safe default, clearly flagged **to confirm**, with the reason. The build is never blocked
   silently. Colours fall back to a neutral palette that belongs to no client (never another client's palette). Logo falls
   back to the business name as text. Photos fall back to an empty photo frame; a likeness of a real person is never
   generated.
3. Everything defaulted or suggested is listed in the answers file under `to_confirm`, each with a one-line way to change
   it, and must be reported at delivery.

## Which run mode, and what an answer IS

`engine.route_mode(text)` reads the client's own opening words against the bank's `mode_routing`. An
explicit Black Friday or launch request routes into the signature launch; a deliberate request for the
older step-by-step funnel keeps `legacy` exactly as it was. Both markers, or neither, is asked as one
plain question — never resolved by a default.

Every saved answer carries a provenance class (`engine.provenance_of`): `confirmed_fact`, `ai_proposal`,
`user_selected_recommendation`, `generated_asset`, or `unresolved_capability`. An answer the client has
not given can be turned into a proposal on the same launch record (`engine.propose`), and accepted
through ONE shared transition (`engine.accept_proposal`) that Skill 49 and Skill 83 both call.

## Revision

`engine.reconcile_revision(doc, changed)` reconciles a change instead of re-interviewing: disabling
upsell 1 reopens the saved downsell 1 and upsell 2 and invalidates the plan approval, while every
unrelated brand and context answer is kept.

## Offers, billing and brand

- Ordinary extra-offer prose is normalised into the existing structured offer record
  (`engine.normalize_offer_prose`) and the client's own words are kept as `source_text`.
- The first package is saved as a valid partial record before the next one is collected.
- A free item is its own `free_entry` record with its own opt-in and thank-you journey: it never goes
  through the paid checkout, and paid offers keep the positive-price rule.
- A repeating price is carried with how often it repeats: the client's own words (`weekly`, `monthly`, `quarterly`,
  `yearly`, `every three months`) become `billing_type: recurring` plus `recurring_interval` (`week`, `month`,
  `quarter`, `year`) from the one table in `shared-utils/signature_launch_contract/billing.py`. The bank's three billing
  choices still work; a client can say any of the four cadences instead, for any offer.
- Billing is carried whole (`engine.billing_terms`). Where the chosen execution path cannot serve a
  plan, `engine.billing_supported` names the specific limit and exactly one supported alternative and
  keeps the request unresolved until the client accepts it — never flattened into a one-time payment.
- One approved brand record (`engine.brand_record`) holds the logo variants, colour roles, typography,
  image direction and voice. A new logo is an asset job: offers and copy keep moving while it is made.
- `engine.asset_map(doc)` is the one map every page reads for its files.

## Never defaulted

These stay blocked, by name, until the client answers: price (a suggested price is a proposal until approved), offer
name and claims (description, audience, result, problems, what the buyer gets, story), who appears in images,
packages or levels, funnel shape, community link and bonus truth gate, entitlement, paid-render approval, plan approval.
`check()` names each one in `blocking`.

## How each skill reads the answers file

- Skill 49 launch mode: `python3 scripts/launch_intake.py --session S --answers-file A [--brand-file B]` fills the session;
  a question already answered is never asked again; a default or suggestion enters as `recommended_unapproved`.
- Skill 49 legacy mode: `engine.to_sf_brief_answers(doc)` yields the `q1`..`q18` keys the `prove_sf_intake.py` gate reads.
- Skill 71: `python3 scripts/write_intake.py RUN --answers-file A` fills owner, image cap, page version, design style and
  image engine, writes the client brand file (`scripts/brand_colors.py record-answers`) and records `to_confirm`.
- Skill 83: `brand_ref` is the path of the brand file the answers produced and `brand_hash` its sha256 (the same two values
  `launch_intake.ingest_answers` records).

## Full launch plan facts (Skill 49 `--launch-plan`, Skill 83's plan)

`scripts/launch_plan.py` reads these answers (spec §3.5) to plan the emails, texts, automations and Conversation AI
beside the pages. They are asked by the shared question bank — this skill only reads them; a missing launch date, doors
time, timezone or AI mode blocks the launch plan by name and is never filled in.

| Answer key | Meaning |
|---|---|
| `launch.launch_at`, `launch.doors_open_at`, `launch.doors_close_at`, `launch.timezone` | Launch date and the truthful doors open/close window (IANA zone) |
| `launch.black_friday.{teaser_at,countdown_at,cyber_monday_at,last_call_at}` | Optional Black Friday calendar (Skill 83); all four or none |
| `launch.channels` | `["email"]` or `["email", "text"]` |
| `launch.texts_enabled` | Boolean alternative to `launch.channels` |
| `launch.text_keyword` | Optional opt-in keyword (for example `EARLY`); absent means no keyword set |
| `launch.a2p_ready` | A2P 10DLC registration done. False (or missing) keeps every text a draft and the package warns |
| `launch.conversation_ai` | Boolean: the optional Skill 38 bot was requested |
| `launch.conversation_ai_mode` | `faq`, `booking`, `checkout` or `full`; required when requested |
| `launch.conversation_ai_channels` | Optional `["sms"]`, `["chat"]` or both |
| `launch.send_window` | Optional `{start, end, timezone}`; default `08:00`–`21:00` recipient local |
| `offers.main.payment_plans` | Boolean: opens the failed-payment automation family (else derived from an instalment/recurring billing type) |
| `launch.{landing,sales_page,checkout,thank_you}_url` | Approved page URLs; null while a page is only planned |

## Question id map

Every legacy and launch question id maps to one canonical id through `legacy_ids` in the bank. A test fails if a question
in `sf-intake-questions.json` or `launch-questions.json`, or a field required by the launch record, Skill 83 intake or
Skill 71 `write_intake.py`, has no question and no stated system reason.

## Deliverables and exclusions (launch interview)

`a4_deliverables` stores a list (split on new lines, semicolons or commas) on `offers.main.deliverables` only. What is
NOT included is its own question, `a4b_exclusions`, stored on `offers.main.exclusions`; until it is answered the plan
carries `exclusions: []`, and "none" is a valid answer. The raw deliverables text is never copied to exclusions.
